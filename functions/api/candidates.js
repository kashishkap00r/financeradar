export async function onRequestGet({ request, env }) {
  try {
    if (!env.MINIFLUX_URL) return json({ error: "MINIFLUX_URL is missing in env vars" }, 500);
    if (!env.MINIFLUX_TOKEN) return json({ error: "MINIFLUX_TOKEN is missing in env vars" }, 500);

    const reqUrl = new URL(request.url);

    const statusParam = (reqUrl.searchParams.get("status") || "all").toLowerCase();
    const days = clampInt(reqUrl.searchParams.get("days") || "5", 1, 30);
    const perPage = clampInt(reqUrl.searchParams.get("limit") || "200", 1, 500);
    const maxRaw = clampInt(reqUrl.searchParams.get("max") || "50000", 1000, 200000);

    // Existing controls
    const perFeedCap = clampInt(reqUrl.searchParams.get("per_feed") || "50", 1, 1000);

    // New: story clustering controls
    const clusterOn = (reqUrl.searchParams.get("cluster") || "1") !== "0";
    const minTokenLen = clampInt(reqUrl.searchParams.get("min_token_len") || "3", 1, 10);
    const jaccardThreshold = clampFloat(reqUrl.searchParams.get("jaccard") || "0.72", 0.3, 0.95);

    // Final output cap (clusters)
    const outMax = clampInt(reqUrl.searchParams.get("out_max") || "2000", 100, 50000);

    const base = env.MINIFLUX_URL.replace(/\/$/, "");
    const headers = { "X-Auth-Token": env.MINIFLUX_TOKEN, "Accept": "application/json" };
    const publishedAfter = new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();
    const statuses = normalizeStatuses(statusParam);

    // 1) fetch raw
    let raw = [];
    for (const st of statuses) {
      const entries = await fetchAllEntries({
        base,
        headers,
        status: st,
        perPage,
        maxItems: Math.max(0, maxRaw - raw.length),
        publishedAfter,
      });
      raw.push(...entries);
      if (raw.length >= maxRaw) break;
    }
    if (raw.length > maxRaw) raw = raw.slice(0, maxRaw);

    // 2) sort newest first
    raw.sort((a, b) => (b.published_at || "").localeCompare(a.published_at || ""));

    // 3) URL-level dedupe
    const seenUrl = new Set();
    const urlDeduped = [];
    for (const e of raw) {
      const key = canonicalizeUrl(e.url || "") || "";
      const fallback = `${e.feed?.id ?? "unknown"}::${(e.title || "").trim().toLowerCase()}`;
      const k = key ? `u:${key}` : `t:${fallback}`;
      if (seenUrl.has(k)) continue;
      seenUrl.add(k);
      urlDeduped.push(e);
    }

    // 4) per-feed cap (still important before clustering, to avoid flooders biasing clusters)
    const byFeed = new Map();
    const capped = [];
    for (const e of urlDeduped) {
      const fid = e.feed?.id ?? "unknown";
      const c = byFeed.get(fid) || 0;
      if (c >= perFeedCap) continue;
      byFeed.set(fid, c + 1);
      capped.push(e);
    }

    // 5) Cluster by near-duplicate titles
    let clusters;
    if (clusterOn) {
      clusters = clusterEntries(capped, { minTokenLen, jaccardThreshold });
    } else {
      // 1 entry = 1 cluster
      clusters = capped.map((e) => ({ rep: e, members: [e] }));
    }

    // 6) Create candidate list (one per cluster)
    // Representative = newest item in cluster (because input already sorted newest-first)
    const candidates = clusters
      .slice(0, outMax)
      .map((c) => toCandidate(c.rep, c.members));

    return json(
      {
        meta: {
          requested_status: statusParam,
          fetched_statuses: statuses,
          days,
          per_page: perPage,
          published_after: publishedAfter,

          raw_fetched: raw.length,
          after_url_dedupe: urlDeduped.length,
          per_feed_cap: perFeedCap,
          after_per_feed: capped.length,

          cluster: clusterOn,
          jaccard: jaccardThreshold,
          clusters: clusters.length,
          returned: candidates.length,
        },
        candidates,
      },
      200,
      { "Access-Control-Allow-Origin": "*", "Cache-Control": "no-store" }
    );
  } catch (err) {
    return json(
      { error: "Function crashed", message: String(err?.message || err), stack: err?.stack || null },
      500
    );
  }
}

function toCandidate(rep, members) {
  // keep it small but useful for ranking
  return {
    id: rep.id,
    title: rep.title,
    url: rep.url,
    published_at: rep.published_at,
    status: rep.status,
    feed: rep.feed ? { id: rep.feed.id, title: rep.feed.title, site_url: rep.feed.site_url } : null,
    tags: rep.tags || [],
    // crowd signal (very valuable later)
    mentions: members.length,
    sources: uniq(
      members
        .map((m) => m.feed?.title)
        .filter(Boolean)
    ),
  };
}

function clusterEntries(entries, { minTokenLen, jaccardThreshold }) {
  // Cheap, effective clustering:
  // - normalize title -> tokens
  // - compare to existing cluster reps using Jaccard similarity
  // O(n*k) but fine for a few thousand with a reasonable cap.
  const clusters = [];

  for (const e of entries) {
    const title = e.title || "";
    const tokens = titleTokens(title, minTokenLen);
    const norm = tokens.join(" ");

    // If no tokens, treat as unique
    if (!tokens.length) {
      clusters.push({ rep: e, repTokens: tokens, repNorm: norm, members: [e] });
      continue;
    }

    let placed = false;

    // compare against existing cluster reps
    for (const c of clusters) {
      // fast path: exact normalized match
      if (norm && c.repNorm === norm) {
        c.members.push(e);
        placed = true;
        break;
      }

      // Jaccard similarity
      const sim = jaccard(tokens, c.repTokens);
      if (sim >= jaccardThreshold) {
        c.members.push(e);
        placed = true;
        break;
      }
    }

    if (!placed) {
      clusters.push({ rep: e, repTokens: tokens, repNorm: norm, members: [e] });
    }
  }

  // Ensure rep is newest (first encountered) — already true because entries are sorted newest-first.
  // Sort clusters by rep published_at desc
  clusters.sort((a, b) => (b.rep.published_at || "").localeCompare(a.rep.published_at || ""));

  return clusters.map((c) => ({ rep: c.rep, members: c.members }));
}

function titleTokens(title, minTokenLen) {
  const t = normalizeTitle(title);

  // split into tokens
  let parts = t.split(" ").filter(Boolean);

  // drop short tokens and generic junk
  const stop = new Set([
    "the","a","an","and","or","to","of","in","on","for","with","as","at","by","from",
    "india","indian","says","say","said","report","reports","reported","live","update","updates",
    "today","latest","news"
  ]);

  parts = parts
    .map((p) => p.trim())
    .filter((p) => p.length >= minTokenLen)
    .filter((p) => !stop.has(p));

  // cap tokens to avoid huge comparisons
  if (parts.length > 30) parts = parts.slice(0, 30);

  return parts;
}

function normalizeTitle(title) {
  return String(title)
    .toLowerCase()
    // normalize quotes/dashes
    .replace(/[’‘]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/[–—]/g, "-")
    // replace numbers with a placeholder to reduce trivial differences
    .replace(/\b\d+(\.\d+)?\b/g, "0")
    // remove punctuation
    .replace(/[^a-z0-9\s-]/g, " ")
    // collapse spaces
    .replace(/\s+/g, " ")
    .trim();
}

function jaccard(aTokens, bTokens) {
  if (!aTokens.length || !bTokens.length) return 0;
  const a = new Set(aTokens);
  const b = new Set(bTokens);
  let inter = 0;
  for (const x of a) if (b.has(x)) inter += 1;
  const union = a.size + b.size - inter;
  return union ? inter / union : 0;
}

function uniq(arr) {
  return Array.from(new Set(arr));
}

function normalizeStatuses(statusParam) {
  if (statusParam === "all") return ["unread", "read"];
  if (statusParam === "unread") return ["unread"];
  if (statusParam === "read") return ["read"];
  if (statusParam === "removed") return ["removed"];
  return ["unread", "read"];
}

async function fetchAllEntries({ base, headers, status, perPage, maxItems, publishedAfter }) {
  let offset = 0;
  let all = [];
  let safetyIters = 0;

  while (all.length < maxItems) {
    safetyIters += 1;
    if (safetyIters > 800) break;

    const upstream = new URL(`${base}/v1/entries`);
    upstream.searchParams.set("status", status);
    upstream.searchParams.set("limit", String(perPage));
    upstream.searchParams.set("offset", String(offset));
    upstream.searchParams.set("order", "published_at");
    upstream.searchParams.set("direction", "desc");
    upstream.searchParams.set("published_after", publishedAfter);

    const resp = await fetch(upstream.toString(), { headers });
    const text = await resp.text();

    if (!resp.ok) {
      throw new Error(
        `Miniflux failed for status=${status} (${resp.status}). Upstream=${upstream.toString()} Body=${text.slice(0, 300)}`
      );
    }

    let data;
    try {
      data = JSON.parse(text);
    } catch {
      throw new Error(`Miniflux JSON parse failed for status=${status}. Body preview=${text.slice(0, 300)}`);
    }

    const entries = Array.isArray(data.entries) ? data.entries : [];
    all.push(...entries);

    if (entries.length < perPage) break;
    offset += perPage;
  }

  return all;
}

function canonicalizeUrl(input) {
  try {
    if (!input) return "";
    const u = new URL(input);
    u.hash = "";

    const dropPrefixes = ["utm_"];
    const dropExact = new Set([
      "fbclid","gclid","igshid","mc_cid","mc_eid","mkt_tok","ref","ref_src","spm","cmpid",
    ]);

    for (const [k] of Array.from(u.searchParams.entries())) {
      const kl = k.toLowerCase();
      if (dropExact.has(kl) || dropPrefixes.some((p) => kl.startsWith(p))) u.searchParams.delete(k);
    }

    u.hostname = u.hostname.toLowerCase();
    const s = u.toString();
    return s.endsWith("/") ? s.slice(0, -1) : s;
  } catch {
    return "";
  }
}

function json(obj, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...extraHeaders },
  });
}

function clampInt(value, min, max) {
  const n = parseInt(value, 10);
  if (Number.isNaN(n)) return min;
  return Math.max(min, Math.min(max, n));
}

function clampFloat(value, min, max) {
  const n = parseFloat(value);
  if (Number.isNaN(n)) return min;
  return Math.max(min, Math.min(max, n));
}

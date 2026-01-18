export async function onRequestGet({ request, env }) {
  try {
    if (!env.MINIFLUX_URL) return json({ error: "MINIFLUX_URL is missing in env vars" }, 500);
    if (!env.MINIFLUX_TOKEN) return json({ error: "MINIFLUX_TOKEN is missing in env vars" }, 500);

    const reqUrl = new URL(request.url);

    const statusParam = (reqUrl.searchParams.get("status") || "all").toLowerCase();
    const days = clampInt(reqUrl.searchParams.get("days") || "5", 1, 30);
    const perPage = clampInt(reqUrl.searchParams.get("limit") || "200", 1, 500);

    // raw fetch safety cap
    const maxRaw = clampInt(reqUrl.searchParams.get("max") || "50000", 1000, 200000);

    // diversity control
    const perFeedCap = clampInt(reqUrl.searchParams.get("per_feed") || "50", 1, 1000);

    // CRITICAL: cap what enters clustering (keeps CPU/memory sane)
    // You are ranking top 30, so you do NOT need to cluster 6000 items.
    const preClusterMax = clampInt(reqUrl.searchParams.get("pre_cluster_max") || "2500", 200, 10000);

    // final output cap (clusters)
    const outMax = clampInt(reqUrl.searchParams.get("out_max") || "2000", 50, 50000);

    // title normalization knobs
    const minTokenLen = clampInt(reqUrl.searchParams.get("min_token_len") || "3", 1, 10);
    const sigTokens = clampInt(reqUrl.searchParams.get("sig_tokens") || "10", 3, 20);

    const base = env.MINIFLUX_URL.replace(/\/$/, "");
    const headers = { "X-Auth-Token": env.MINIFLUX_TOKEN, "Accept": "application/json" };
    const publishedAfter = new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();
    const statuses = normalizeStatuses(statusParam);

    // 1) Fetch raw entries
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

    // 2) Sort newest first (important: newest becomes cluster representative naturally)
    raw.sort((a, b) => (b.published_at || "").localeCompare(a.published_at || ""));

    // 3) URL-level dedupe (canonical URL; fallback feed+title)
    const seen = new Set();
    const urlDeduped = [];
    for (const e of raw) {
      const u = canonicalizeUrl(e.url || "");
      const fallback = `${e.feed?.id ?? "unknown"}::${(e.title || "").trim().toLowerCase()}`;
      const key = u ? `u:${u}` : `t:${fallback}`;
      if (seen.has(key)) continue;
      seen.add(key);
      urlDeduped.push(e);
    }

    // 4) Per-feed cap
    const byFeed = new Map();
    const capped = [];
    for (const e of urlDeduped) {
      const fid = e.feed?.id ?? "unknown";
      const c = byFeed.get(fid) || 0;
      if (c >= perFeedCap) continue;
      byFeed.set(fid, c + 1);
      capped.push(e);
    }

    // 5) Pre-cluster cap (this is what prevents 1102)
    const toCluster = capped.slice(0, preClusterMax);

    // 6) FAST clustering (no n^2 comparisons)
    // We build a signature from normalized title tokens and group by it.
    const clusters = new Map(); // sig -> { rep, membersCount, sourcesSet }
    for (const e of toCluster) {
      const tokens = titleTokens(e.title || "", minTokenLen);

      // signature 1: first N tokens in order (catches near-identical titles)
      const sig1 = tokens.slice(0, sigTokens).join(" ");

      // signature 2: first N unique tokens sorted (catches reorder/format variations)
      const uniqSorted = Array.from(new Set(tokens)).slice(0, sigTokens).sort();
      const sig2 = uniqSorted.join(" ");

      // pick the stronger signature; if empty, fallback
      const sig = (sig1 || sig2 || `id:${e.id}`);

      let c = clusters.get(sig);
      if (!c) {
        c = {
          rep: e, // newest wins because input is sorted newest-first
          mentions: 0,
          sources: new Set(),
        };
        clusters.set(sig, c);
      }

      c.mentions += 1;
      if (e.feed?.title) c.sources.add(e.feed.title);
    }

    // 7) Turn clusters into candidates (newest first by rep.published_at)
    const candidateArr = Array.from(clusters.values())
      .sort((a, b) => (b.rep.published_at || "").localeCompare(a.rep.published_at || ""))
      .slice(0, outMax)
      .map((c) => ({
        id: c.rep.id,
        title: c.rep.title,
        url: c.rep.url,
        published_at: c.rep.published_at,
        status: c.rep.status,
        feed: c.rep.feed
          ? { id: c.rep.feed.id, title: c.rep.feed.title, site_url: c.rep.feed.site_url }
          : null,
        tags: c.rep.tags || [],
        mentions: c.mentions,
        sources: Array.from(c.sources),
      }));

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

          pre_cluster_max: preClusterMax,
          clustered_input: toCluster.length,
          clusters: clusters.size,
          out_max: outMax,
          returned: candidateArr.length,

          sig_tokens: sigTokens,
          min_token_len: minTokenLen,
        },
        candidates: candidateArr,
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

function titleTokens(title, minTokenLen) {
  const t = normalizeTitle(title);

  // stopwords (keep it short; too many wastes CPU)
  const stop = new Set([
    "the","a","an","and","or","to","of","in","on","for","with","as","at","by","from",
    "says","say","said","report","reports","reported","live","update","updates",
    "today","latest","news"
  ]);

  let parts = t.split(" ").filter(Boolean);
  parts = parts
    .filter((p) => p.length >= minTokenLen)
    .filter((p) => !stop.has(p));

  if (parts.length > 30) parts = parts.slice(0, 30);
  return parts;
}

function normalizeTitle(title) {
  return String(title)
    .toLowerCase()
    .replace(/\b\d+(\.\d+)?\b/g, "0") // normalize numbers
    .replace(/[’‘]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/[–—]/g, "-")
    .replace(/[^a-z0-9\s-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
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

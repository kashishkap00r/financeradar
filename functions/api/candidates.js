export async function onRequestGet({ request, env }) {
  try {
    if (!env.MINIFLUX_URL) return json({ error: "MINIFLUX_URL is missing in env vars" }, 500);
    if (!env.MINIFLUX_TOKEN) return json({ error: "MINIFLUX_TOKEN is missing in env vars" }, 500);

    const reqUrl = new URL(request.url);

    // Inputs
    const statusParam = (reqUrl.searchParams.get("status") || "all").toLowerCase();
    const days = clampInt(reqUrl.searchParams.get("days") || "5", 1, 30);

    // Output controls
    const topN = clampInt(reqUrl.searchParams.get("top") || "100", 1, 200);
    const includeAll = (reqUrl.searchParams.get("all") || "0") === "1"; // include full ranked list

    // Pagination / safety
    const perPage = clampInt(reqUrl.searchParams.get("limit") || "200", 50, 500);
    const maxRaw = clampInt(reqUrl.searchParams.get("max") || "6000", 500, 20000);

    // Noise controls
    const perFeedCap = clampInt(reqUrl.searchParams.get("per_feed") || "30", 1, 200);

    // How many unique-ish items we try to collect (bounded work)
    const stopWhenClusters = clampInt(reqUrl.searchParams.get("stop_when_clusters") || "1800", 200, 8000);

    // Lightweight title clustering knobs (keeps repeats down a bit, but not CPU-expensive)
    const minTokenLen = clampInt(reqUrl.searchParams.get("min_token_len") || "3", 1, 10);
    const sigTokens = clampInt(reqUrl.searchParams.get("sig_tokens") || "7", 3, 20);

    const base = env.MINIFLUX_URL.replace(/\/$/, "");
    const headers = { "X-Auth-Token": env.MINIFLUX_TOKEN, "Accept": "application/json" };
    const publishedAfter = new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();
    const statuses = normalizeStatuses(statusParam);

    // Timing instrumentation (so you can measure)
    const t0 = Date.now();

    // Streaming-ish: process pages as we fetch
    const seenUrl = new Set();
    const perFeedCounts = new Map();
    const clusters = new Map(); // sig -> { rep, mentions, sources(Set) }

    let rawFetched = 0;
    let pagesFetched = 0;

    // Fetch newest-first, stop early once we have enough clusters
    for (const st of statuses) {
      let offset = 0;
      let safetyIters = 0;

      while (rawFetched < maxRaw) {
        safetyIters += 1;
        if (safetyIters > 200) break;

        const upstream = new URL(`${base}/v1/entries`);
        upstream.searchParams.set("status", st);
        upstream.searchParams.set("limit", String(perPage));
        upstream.searchParams.set("offset", String(offset));
        upstream.searchParams.set("order", "published_at");
        upstream.searchParams.set("direction", "desc");
        upstream.searchParams.set("published_after", publishedAfter);

        const resp = await fetch(upstream.toString(), { headers });
        const text = await resp.text();

        if (!resp.ok) {
          return json(
            { error: "Miniflux request failed", status: resp.status, upstream: upstream.toString(), body: text.slice(0, 500) },
            502
          );
        }

        let data;
        try {
          data = JSON.parse(text);
        } catch {
          return json({ error: "Miniflux JSON parse failed", upstream: upstream.toString(), body_preview: text.slice(0, 500) }, 502);
        }

        const entries = Array.isArray(data.entries) ? data.entries : [];
        pagesFetched += 1;
        if (entries.length === 0) break;

        for (const e of entries) {
          rawFetched += 1;
          if (rawFetched > maxRaw) break;

          // 1) URL dedupe
          const u = canonicalizeUrl(e.url || "");
          const fallback = `${e.feed?.id ?? "unknown"}::${(e.title || "").trim().toLowerCase()}`;
          const key = u ? `u:${u}` : `t:${fallback}`;
          if (seenUrl.has(key)) continue;
          seenUrl.add(key);

          // 2) per-feed cap
          const fid = e.feed?.id ?? "unknown";
          const c = perFeedCounts.get(fid) || 0;
          if (c >= perFeedCap) continue;
          perFeedCounts.set(fid, c + 1);

          // 3) lightweight title clustering
          const tokens = titleTokens(e.title || "", minTokenLen);
          const sig1 = tokens.slice(0, sigTokens).join(" ");
          const sig2 = Array.from(new Set(tokens)).slice(0, sigTokens).sort().join(" ");
          const sig = (sig1 || sig2 || `id:${e.id}`);

          let cl = clusters.get(sig);
          if (!cl) cl = { rep: e, mentions: 0, sources: new Set() };

          // keep newest as rep
          if ((e.published_at || "") > (cl.rep.published_at || "")) cl.rep = e;

          cl.mentions += 1;
          if (e.feed?.title) cl.sources.add(e.feed.title);

          clusters.set(sig, cl);

          // stop early when we have enough unique-ish clusters
          if (clusters.size >= stopWhenClusters) break;
        }

        if (clusters.size >= stopWhenClusters) break;
        if (entries.length < perPage) break;
        offset += perPage;
      }

      if (clusters.size >= stopWhenClusters) break;
    }

    const tFetchDone = Date.now();

    // Build ranked list
    const now = Date.now();

    const ranked = Array.from(clusters.values())
      .map((c) => {
        const rep = c.rep;
        const publishedMs = Date.parse(rep.published_at || "") || now;
        const ageHours = Math.max(0, (now - publishedMs) / (1000 * 60 * 60));

        const mentions = c.mentions || 1;
        const sourceCount = c.sources.size || 1;

        // Recency: exponential decay. 18h time constant feels good for news.
        const recency = 100 * Math.exp(-ageHours / 18);

        // Crowd signals: log so 1->2 matters, 20->21 doesn't dominate.
        const crowd = 12 * Math.log2(1 + mentions) + 8 * Math.log2(1 + sourceCount);

        // Final score
        const score = recency + crowd;

        return {
          id: rep.id,
          title: rep.title,
          url: rep.url,
          published_at: rep.published_at,
          day: (rep.published_at || "").slice(0, 10), // YYYY-MM-DD for separators
          age_hours: round1(ageHours),
          status: rep.status,
          feed: rep.feed ? { id: rep.feed.id, title: rep.feed.title, site_url: rep.feed.site_url } : null,
          tags: rep.tags || [],
          mentions,
          sources: Array.from(c.sources),
          score: round2(score),
        };
      })
      .sort((a, b) => (b.score - a.score) || (b.published_at || "").localeCompare(a.published_at || ""));

    const top = ranked.slice(0, topN);

    const tEnd = Date.now();

    return json(
      {
        meta: {
          requested_status: statusParam,
          fetched_statuses: statuses,
          days,
          top: topN,

          per_page: perPage,
          published_after: publishedAfter,

          max_raw: maxRaw,
          raw_fetched: rawFetched,
          pages_fetched: pagesFetched,

          per_feed_cap: perFeedCap,
          stop_when_clusters: stopWhenClusters,

          clusters: clusters.size,
          ranked_count: ranked.length,
          returned: top.length,

          sig_tokens: sigTokens,
          min_token_len: minTokenLen,

          timing: {
            total_ms: tEnd - t0,
            fetch_ms: tFetchDone - t0,
            processing_ms: tEnd - tFetchDone,
          },
        },
        top,
        ...(includeAll ? { ranked } : {}),
      },
      200,
      { "Access-Control-Allow-Origin": "*", "Cache-Control": "no-store" }
    );
  } catch (err) {
    return json({ error: "Function crashed", message: String(err?.message || err), stack: err?.stack || null }, 500);
  }
}

function normalizeStatuses(statusParam) {
  if (statusParam === "all") return ["unread", "read"];
  if (statusParam === "unread") return ["unread"];
  if (statusParam === "read") return ["read"];
  if (statusParam === "removed") return ["removed"];
  return ["unread", "read"];
}

function titleTokens(title, minTokenLen) {
  const t = normalizeTitle(title);
  const stop = new Set([
    "the","a","an","and","or","to","of","in","on","for","with","as","at","by","from",
    "says","say","said","report","reports","reported","live","update","updates",
    "today","latest","news"
  ]);
  let parts = t.split(" ").filter(Boolean);
  parts = parts.filter((p) => p.length >= minTokenLen).filter((p) => !stop.has(p));
  if (parts.length > 30) parts = parts.slice(0, 30);
  return parts;
}

function normalizeTitle(title) {
  return String(title)
    .toLowerCase()
    .replace(/\b\d+(\.\d+)?\b/g, "0")
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
    const dropExact = new Set(["fbclid","gclid","igshid","mc_cid","mc_eid","mkt_tok","ref","ref_src","spm","cmpid"]);

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

function round1(n) { return Math.round(n * 10) / 10; }
function round2(n) { return Math.round(n * 100) / 100; }

// functions/api/candidates.js
// FinanceRadar Candidates API (Miniflux proxy) — NO RANKING
// Features:
// - Fetches from Miniflux with time bound (days) + pagination
// - Supports status=all by fetching unread+read (Miniflux limitation you hit)
// - URL dedupe (canonicalized URLs)
// - Per-feed cap (diversity control)
// - Lightweight title clustering (signature-based) to reduce repeats
// - Output is sorted strictly by published_at (latest first)
// - Returns: top N (default 100) + groups by day (for day separators)
//
// Query params (optional):
// - days=5
// - status=all|unread|read|removed
// - top=100
// - debug=1 (include sources arrays)
// - limit=200 (miniflux page size)
// - max=6000 (hard cap on total raw entries scanned)
// - per_feed=30 (per-feed cap)
// - stop_when_clusters=1000 (stop early when clusters reach this count)
// - min_token_len=3
// - sig_tokens=7

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
    const debug = (reqUrl.searchParams.get("debug") || "0") === "1";

    // Pagination / safety
    const perPage = clampInt(reqUrl.searchParams.get("limit") || "200", 50, 500);
    const maxRaw = clampInt(reqUrl.searchParams.get("max") || "6000", 200, 20000);

    // Dedupe / diversity
    const perFeedCap = clampInt(reqUrl.searchParams.get("per_feed") || "30", 1, 200);
    const stopWhenClusters = clampInt(reqUrl.searchParams.get("stop_when_clusters") || "1000", 50, 5000);

    // Clustering config
    const minTokenLen = clampInt(reqUrl.searchParams.get("min_token_len") || "3", 2, 10);
    const sigTokens = clampInt(reqUrl.searchParams.get("sig_tokens") || "7", 3, 20);

    const t0 = Date.now();

    const statuses = normalizeStatuses(statusParam); // array of statuses we actually fetch

    // Time window
    const publishedAfterIso = new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();

    // Raw fetch loop
    let rawFetched = 0;
    let pagesFetched = 0;

    // URL dedupe
    const seenUrl = new Set();

    // Per-feed cap counters
    const perFeedCount = new Map();

    // Cluster map: key -> { rep, mentions, sources:Set }
    const clusters = new Map();

    for (const st of statuses) {
      let offset = 0;

      while (rawFetched < maxRaw) {
        const upstream = new URL(env.MINIFLUX_URL.replace(/\/+$/, "") + "/v1/entries");
        upstream.searchParams.set("status", st);
        upstream.searchParams.set("limit", String(perPage));
        upstream.searchParams.set("offset", String(offset));
        upstream.searchParams.set("order", "published_at");
        upstream.searchParams.set("direction", "desc");
        upstream.searchParams.set("published_after", publishedAfterIso);

        const resp = await fetch(upstream.toString(), {
          headers: { "X-Auth-Token": env.MINIFLUX_TOKEN },
        });

        const text = await resp.text();

        if (!resp.ok) {
          return json(
            {
              error: "Miniflux request failed",
              status: resp.status,
              upstream: upstream.toString(),
              body: text.slice(0, 800),
            },
            502
          );
        }

        let data;
        try {
          data = JSON.parse(text);
        } catch {
          return json(
            {
              error: "Miniflux JSON parse failed",
              upstream: upstream.toString(),
              body_preview: text.slice(0, 800),
            },
            502
          );
        }

        const entries = Array.isArray(data.entries) ? data.entries : [];
        pagesFetched += 1;
        if (entries.length === 0) break;

        for (const e of entries) {
          rawFetched += 1;
          if (rawFetched >= maxRaw) break;

          // Canonical URL dedupe
          const canonUrl = canonicalizeUrl(e.url || "");
          if (!canonUrl) continue;
          if (seenUrl.has(canonUrl)) continue;
          seenUrl.add(canonUrl);

          // Per-feed cap
          const feedId = e.feed?.id ?? "unknown";
          const count = perFeedCount.get(feedId) || 0;
          if (count >= perFeedCap) continue;
          perFeedCount.set(feedId, count + 1);

          // Title clustering
          const sig = makeSignature(e.title || "", sigTokens, minTokenLen);
          const key = sig || canonUrl; // fallback

          const feedTitle = e.feed?.title || "unknown";
          const prev = clusters.get(key);

          if (!prev) {
            clusters.set(key, {
              rep: e,
              mentions: 1,
              sources: new Set([feedTitle]),
            });
          } else {
            prev.mentions += 1;
            prev.sources.add(feedTitle);

            // Keep newest rep (by published_at)
            const prevTs = Date.parse(prev.rep?.published_at || "") || 0;
            const newTs = Date.parse(e.published_at || "") || 0;
            if (newTs > prevTs) prev.rep = e;
          }

          // Stop early if we have enough clusters
          if (clusters.size >= stopWhenClusters) break;
        }

        if (clusters.size >= stopWhenClusters) break;

        offset += entries.length;
        // If upstream returned fewer than perPage, we're done
        if (entries.length < perPage) break;
      }
    }

    const tFetchDone = Date.now();

    // Build output list (NO ranking): latest-first
    const items = Array.from(clusters.values())
      .map((c) => {
        const rep = c.rep;

        const publishedAt = rep.published_at || null;
const publishedTs = publishedAt ? Date.parse(publishedAt) : null;

const baseItem = {
  id: rep.id,
  title: rep.title,
  url: rep.url,

  // publish timing
  published_at: publishedAt,        // exact ISO string
  published_ts: publishedTs,         // epoch ms (easy for UI)
  day: publishedAt ? publishedAt.slice(0, 10) : null,

  status: rep.status,
  feed: rep.feed
    ? { id: rep.feed.id, title: rep.feed.title, site_url: rep.feed.site_url }
    : null,

  tags: rep.tags || [],
  mentions: c.mentions || 1,
  sources_count: c.sources.size || 1,
};

        if (debug) baseItem.sources = Array.from(c.sources);
        return baseItem;
      })
      .sort((a, b) => (b.published_at || "").localeCompare(a.published_at || ""));

    const top = items.slice(0, topN);

    // Group by day for UI separators (day is derived from published_at)
    const groupsMap = new Map();
    for (const item of top) {
      const d = item.day || "unknown";
      if (!groupsMap.has(d)) groupsMap.set(d, []);
      groupsMap.get(d).push(item);
    }
    const groups = Array.from(groupsMap.entries()).map(([day, items]) => ({ day, items }));

    const tDone = Date.now();

    return json({
      meta: {
        requested_status: statusParam,
        fetched_statuses: statuses,
        days,
        top: topN,
        per_page: perPage,
        max_raw: maxRaw,
        published_after: publishedAfterIso,

        raw_fetched: rawFetched,
        after_url_dedupe: seenUrl.size,
        per_feed_cap: perFeedCap,
        after_per_feed: Array.from(perFeedCount.values()).reduce((a, b) => a + b, 0),
        clusters: clusters.size,
        returned: top.length,

        timing: {
          total_ms: tDone - t0,
          fetch_ms: tFetchDone - t0,
          processing_ms: tDone - tFetchDone,
        },

        debug,
      },
      top,
      groups,
    });
  } catch (err) {
    return json(
      {
        error: "Function crashed",
        message: String(err?.message || err),
        stack: String(err?.stack || ""),
      },
      500
    );
  }
}

function normalizeStatuses(statusParam) {
  // Your Miniflux returns 400 for status=all; so we fetch read+unread.
  // If user asks removed explicitly, we only fetch removed.
  const allowed = new Set(["unread", "read", "removed"]);
  if (statusParam === "all") return ["unread", "read"];
  if (allowed.has(statusParam)) return [statusParam];
  // default
  return ["unread", "read"];
}

function titleTokens(title, minLen) {
  return normalizeTitle(title)
    .split(/\s+/)
    .map((t) => t.trim())
    .filter((t) => t.length >= minLen);
}

function normalizeTitle(s) {
  return (s || "")
    .toLowerCase()
    .replace(/&amp;/g, "&")
    .replace(/[’']/g, "")
    .replace(/[^a-z0-9\s]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function makeSignature(title, sigTokens, minTokenLen) {
  const tokens = titleTokens(title, minTokenLen);
  if (tokens.length === 0) return "";

  // Primary signature: first N tokens (keeps phrase structure)
  const head = tokens.slice(0, sigTokens).join(" ");

  // Fallback signature: unique tokens sorted (helps minor reorderings)
  const uniq = Array.from(new Set(tokens)).sort().slice(0, sigTokens).join(" ");

  return head || uniq;
}

function canonicalizeUrl(u) {
  try {
    if (!u) return "";
    const url = new URL(u);

    // drop fragments
    url.hash = "";

    // remove common tracking params
    const drop = new Set([
      "utm_source",
      "utm_medium",
      "utm_campaign",
      "utm_term",
      "utm_content",
      "utm_id",
      "utm_name",
      "gclid",
      "fbclid",
      "yclid",
      "mc_cid",
      "mc_eid",
      "ref",
      "ref_src",
      "ref_url",
      "igshid",
      "mkt_tok",
    ]);

    for (const k of Array.from(url.searchParams.keys())) {
      if (drop.has(k.toLowerCase())) url.searchParams.delete(k);
    }

    // normalize host/path
    url.hostname = url.hostname.toLowerCase();
    url.pathname = url.pathname.replace(/\/+$/, "");

    return url.toString();
  } catch {
    return "";
  }
}

function json(obj, status = 200, headers = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*", ...headers },
  });
}

function clampInt(value, min, max) {
  const n = parseInt(value, 10);
  if (Number.isNaN(n)) return min;
  return Math.max(min, Math.min(max, n));
}

// functions/api/candidates.js
// FinanceRadar Candidates API (Miniflux proxy) — HYGIENE ONLY (NO RANKING)
//
// What this endpoint does:
// - Fetches entries from Miniflux (your RSS reader) via /v1/entries
// - Hard limits results to ONLY the last 5 days (cannot be overridden by query params)
// - Supports status=all by fetching unread + read (because Miniflux rejects status=all in your setup)
// - Removes obvious tracking params from URLs (utm_*, gclid, fbclid, etc.) and uses canonical URL for dedupe
// - Hard URL dedupe: the same canonical URL can only appear once
// - Per-feed cap: prevents any single feed from dominating the list
// - Lightweight title clustering: collapses near-duplicate headlines across different URLs
//   (keeps the newest item as representative)
// - HARD FILTER: drops any entry whose title contains "Trump" or "Trump's" (case-insensitive)
// - Returns a flat list sorted strictly by published_at (latest first)
//
// What this endpoint does NOT do:
// - No AI ranking or scoring
// - No day-grouping output for UI separators
// - No "mentions" or "sources_count" metadata
//
// Query params supported (optional):
// - status=all|unread|read|removed   (default: all -> unread+read)
// - top=100                         (how many items to return; 1..200)
// - limit=200                       (Miniflux page size; 50..500)
// - max=6000                        (max raw entries scanned; 200..20000)
// - per_feed=30                     (per-feed cap; 1..200)
// - stop_when_clusters=1000         (stop early when we have enough unique clusters; 50..5000)
//
// Response shape:
// { items: [ { id, title, url, published_at, published_ts, status, feed, tags } ... ] }

export async function onRequestGet({ request, env }) {
  try {
    if (!env.MINIFLUX_URL) return json({ error: "MINIFLUX_URL missing" }, 500);
    if (!env.MINIFLUX_TOKEN) return json({ error: "MINIFLUX_TOKEN missing" }, 500);

    const reqUrl = new URL(request.url);

    // HARD LIMITS (not user-configurable)
    const DAYS_LIMIT = 5;
    const TRUMP_RE = /trump('?s)?/i;

    // Output controls
    const topN = clampInt(reqUrl.searchParams.get("top") || "100", 1, 200);

    // Pagination / safety
    const perPage = clampInt(reqUrl.searchParams.get("limit") || "200", 50, 500);
    const maxRaw = clampInt(reqUrl.searchParams.get("max") || "6000", 200, 20000);

    // Diversity + repeat control
    const perFeedCap = clampInt(reqUrl.searchParams.get("per_feed") || "30", 1, 200);
    const stopWhenClusters = clampInt(reqUrl.searchParams.get("stop_when_clusters") || "1000", 50, 5000);

    // Clustering config (fixed defaults; you can make these query params later if you want)
    const minTokenLen = 3;
    const sigTokens = 7;

    // Miniflux status handling
    const statusParam = (reqUrl.searchParams.get("status") || "all").toLowerCase();
    const statuses = normalizeStatuses(statusParam);

    // Time window: last 5 days only
    const publishedAfterIso =
      new Date(Date.now() - DAYS_LIMIT * 24 * 60 * 60 * 1000).toISOString();

    // Scan counters
    let rawFetched = 0;

    // Dedupe state
    const seenUrl = new Set(); // canonical URLs we've already returned

    // Per-feed cap state
    const perFeedCount = new Map(); // feedId -> count included so far

    // Cluster map (title signature -> representative entry)
    // NOTE: cluster value intentionally minimal (no mentions/sources tracking).
    const clusters = new Map(); // key -> { rep }

    // Fetch pages from Miniflux for each status
    for (const st of statuses) {
      let offset = 0;

      while (rawFetched < maxRaw) {
        // Build upstream Miniflux URL
        const upstream = new URL(env.MINIFLUX_URL.replace(/\/+$/, "") + "/v1/entries");
        upstream.searchParams.set("status", st);
        upstream.searchParams.set("limit", String(perPage));
        upstream.searchParams.set("offset", String(offset));
        upstream.searchParams.set("order", "published_at");
        upstream.searchParams.set("direction", "desc");
        upstream.searchParams.set("published_after", publishedAfterIso);

        // Call Miniflux
        const resp = await fetch(upstream.toString(), {
          headers: { "X-Auth-Token": env.MINIFLUX_TOKEN },
        });

        if (!resp.ok) {
          // Keep error simple (you can add upstream/body preview if needed)
          return json({ error: "Miniflux request failed", status: resp.status }, 502);
        }

        const data = await resp.json();
        const entries = Array.isArray(data.entries) ? data.entries : [];
        if (entries.length === 0) break;

        for (const e of entries) {
          rawFetched++;
          if (rawFetched >= maxRaw) break;

          // HARD editorial filter (skip anything with Trump in title)
          const title = e.title || "";
          if (TRUMP_RE.test(title)) continue;

          // Canonical URL dedupe (tracking stripped)
          const canonUrl = canonicalizeUrl(e.url || "");
          if (!canonUrl) continue;
          if (seenUrl.has(canonUrl)) continue;
          seenUrl.add(canonUrl);

          // Per-feed cap (diversity control)
          const feedId = e.feed?.id ?? "unknown";
          const count = perFeedCount.get(feedId) || 0;
          if (count >= perFeedCap) continue;
          perFeedCount.set(feedId, count + 1);

          // Title clustering (repeat collapse)
          // Key is a signature from the first N normalized title tokens.
          const sig = makeSignature(title, sigTokens, minTokenLen);
          const key = sig || canonUrl;

          const prev = clusters.get(key);
          if (!prev) {
            clusters.set(key, { rep: e });
          } else {
            // Keep the newest entry as the representative item
            const prevTs = Date.parse(prev.rep?.published_at || "") || 0;
            const newTs = Date.parse(e.published_at || "") || 0;
            if (newTs > prevTs) prev.rep = e;
          }

          // Stop early if we already have enough unique clusters
          if (clusters.size >= stopWhenClusters) break;
        }

        if (clusters.size >= stopWhenClusters) break;

        offset += entries.length;

        // If upstream returned fewer than perPage, we've hit the end
        if (entries.length < perPage) break;
      }
    }

    // Build final output list: representatives only, sorted latest-first
    const items = Array.from(clusters.values())
      .map(({ rep }) => ({
        id: rep.id,
        title: rep.title,
        url: rep.url,

        // publish timing
        published_at: rep.published_at || null, // ISO string
        published_ts: rep.published_at ? Date.parse(rep.published_at) : null, // epoch ms (UI-friendly)

        status: rep.status,

        feed: rep.feed
          ? { id: rep.feed.id, title: rep.feed.title, site_url: rep.feed.site_url }
          : null,

        tags: rep.tags || [],
      }))
      .sort((a, b) => (b.published_at || "").localeCompare(a.published_at || ""))
      .slice(0, topN);

    return json({ items });
  } catch (err) {
    return json({ error: "Function crashed", message: String(err?.message || err) }, 500);
  }
}

/* ---------- helpers ---------- */

function normalizeStatuses(status) {
  // Your Miniflux returns 400 for status=all; so we fetch unread+read.
  if (status === "all") return ["unread", "read"];
  if (["unread", "read", "removed"].includes(status)) return [status];
  return ["unread", "read"];
}

function makeSignature(title, sigTokens, minLen) {
  const tokens = normalizeTitle(title)
    .split(/\s+/)
    .filter((t) => t.length >= minLen);

  return tokens.slice(0, sigTokens).join(" ");
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

function clampInt(v, min, max) {
  const n = parseInt(v, 10);
  if (Number.isNaN(n)) return min;
  return Math.max(min, Math.min(max, n));
}

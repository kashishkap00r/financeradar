// functions/api/candidates.js
// FinanceRadar Candidates API (Miniflux proxy) — HYGIENE ONLY (NO RANKING)
//
// What this endpoint does:
// - Fetches entries from Miniflux (your RSS reader) via /v1/entries
// - Hard limits results to ONLY the last 5 days (cannot be overridden by query params)
// - Supports status=all by fetching unread + read (because Miniflux rejects status=all)
// - Canonicalizes URLs and removes tracking params
// - Hard URL dedupe + per-feed cap
// - Lightweight title clustering to collapse repeats
// - HARD EDITORIAL FILTER: drops titles matching blocked words/phrases
// - Returns a flat list sorted by published_at (latest first)
//
// Response shape:
// { items: [ { id, title, url, published_at, published_ts, status, feed, tags } ] }

export async function onRequestGet({ request, env }) {
  try {
    if (!env.MINIFLUX_URL) return json({ error: "MINIFLUX_URL missing" }, 500);
    if (!env.MINIFLUX_TOKEN) return json({ error: "MINIFLUX_TOKEN missing" }, 500);

    const reqUrl = new URL(request.url);

    // =========================================================
    // HARD LIMITS (not user-configurable)
    // =========================================================
    const DAYS_LIMIT = 5;

    // Blocked editorial phrases (case-insensitive, phrase-based)
    const BLOCKED_PHRASES = [
      "trump",
      "trump's",
      "nifty",
      "sensex",
      "money market operations",
      "premature redemption under sovereign gold bond",
      "sovereign gold bond",
      "auction results",
      "stock market highlights",
      "today’s stock recommendation",
      "today's stock recommendation",
      "day trading guide",
      "bl morning report",
      "variable rate repo (VRR) auction",
      "share price",
      "share prices",
      "stock price",
      "stock prices",
      "appeal no.",
      "certificate no.",
      "adjudication order",
      "addendum to",
      "enquiry order",
      "order for compliance",
      "recovery certificate",
      "Remittance advice",
      "stocks to buy",
      "buy or sell",
      "d-street",
      "stocks to sell",
      "underwriting auction",
      "results today live",
      "results today",
      "top gainers and losers",
      "q3 results",
      "stocks to buy,",
      "stocks to watch",
      "cricket",
      "IND",
      "reserve money",
      "auction result",
      "T20I",
      "auction result",
      "broker's call:",
      "stocks to watch",
      "davos",
      "T20",
      "auction of state government securities",
      "OMO Purchase Auction",
      "RBI imposes monetary penalty",
      "auction"
    ];

    // =========================================================
    // Output controls
    // =========================================================
    const topN = clampInt(reqUrl.searchParams.get("top") || "500", 1, 500);

    // Pagination / safety
    const perPage = clampInt(reqUrl.searchParams.get("limit") || "200", 50, 500);
    const maxRaw = clampInt(reqUrl.searchParams.get("max") || "6000", 200, 20000);

    // Diversity control
    const perFeedCap = clampInt(reqUrl.searchParams.get("per_feed") || "30", 1, 200);
    const stopWhenClusters = clampInt(reqUrl.searchParams.get("stop_when_clusters") || "1000", 50, 5000);

    // Clustering config
    const minTokenLen = 3;
    const sigTokens = 7;

    // Status handling
    const statusParam = (reqUrl.searchParams.get("status") || "all").toLowerCase();
    const statuses = normalizeStatuses(statusParam);

    // Time window
    const publishedAfterIso =
      new Date(Date.now() - DAYS_LIMIT * 24 * 60 * 60 * 1000).toISOString();

    let rawFetched = 0;

    const seenUrl = new Set();
    const perFeedCount = new Map();
    const clusters = new Map(); // key -> { rep }

    // =========================================================
    // Fetch loop
    // =========================================================
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

        if (!resp.ok) {
          return json({ error: "Miniflux request failed", status: resp.status }, 502);
        }

        const data = await resp.json();
        const entries = Array.isArray(data.entries) ? data.entries : [];
        if (entries.length === 0) break;

        for (const e of entries) {
          rawFetched++;
          if (rawFetched >= maxRaw) break;

          // -----------------------------------------------------
          // HARD EDITORIAL FILTER (title-based)
          // -----------------------------------------------------
          const rawTitle = e.title || "";
          const normTitle = normalizeTitle(rawTitle);

          let blocked = false;
          for (const phrase of BLOCKED_PHRASES) {
            if (normTitle.includes(normalizeTitle(phrase))) {
              blocked = true;
              break;
            }
          }
          if (blocked) continue;

          // Canonical URL dedupe
          const canonUrl = canonicalizeUrl(e.url || "");
          if (!canonUrl || seenUrl.has(canonUrl)) continue;
          seenUrl.add(canonUrl);

          // Per-feed cap
          const feedId = e.feed?.id ?? "unknown";
          const count = perFeedCount.get(feedId) || 0;
          if (count >= perFeedCap) continue;
          perFeedCount.set(feedId, count + 1);

          // Title clustering
          const sig = makeSignature(rawTitle, sigTokens, minTokenLen);
          const key = sig || canonUrl;

          const prev = clusters.get(key);
          if (!prev) {
            clusters.set(key, { rep: e });
          } else {
            const prevTs = Date.parse(prev.rep?.published_at || "") || 0;
            const newTs = Date.parse(e.published_at || "") || 0;
            if (newTs > prevTs) prev.rep = e;
          }

          if (clusters.size >= stopWhenClusters) break;
        }

        if (clusters.size >= stopWhenClusters) break;
        offset += entries.length;
        if (entries.length < perPage) break;
      }
    }

    // =========================================================
    // Final output
    // =========================================================
    const items = Array.from(clusters.values())
      .map(({ rep }) => ({
        id: rep.id,
        title: rep.title,
        url: rep.url,
        published_at: rep.published_at || null,
        published_ts: rep.published_at ? Date.parse(rep.published_at) : null,
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

/* ========================= Helpers ========================= */

function normalizeStatuses(status) {
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
    const url = new URL(u);
    url.hash = "";
    const drop = [
      "utm_source","utm_medium","utm_campaign","utm_term","utm_content",
      "utm_id","utm_name","gclid","fbclid","yclid",
      "mc_cid","mc_eid","ref","ref_src","ref_url","igshid","mkt_tok"
    ];
    for (const k of Array.from(url.searchParams.keys())) {
      if (drop.includes(k.toLowerCase())) url.searchParams.delete(k);
    }
    url.hostname = url.hostname.toLowerCase();
    url.pathname = url.pathname.replace(/\/+$/, "");
    return url.toString();
  } catch {
    return "";
  }
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
    },
  });
}

function clampInt(v, min, max) {
  const n = parseInt(v, 10);
  if (Number.isNaN(n)) return min;
  return Math.max(min, Math.min(max, n));
}

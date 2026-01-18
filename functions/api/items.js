export async function onRequestGet({ request, env }) {
  try {
    if (!env.MINIFLUX_URL) return json({ error: "MINIFLUX_URL is missing in env vars" }, 500);
    if (!env.MINIFLUX_TOKEN) return json({ error: "MINIFLUX_TOKEN is missing in env vars" }, 500);

    const reqUrl = new URL(request.url);

    // Params (sane defaults for FinanceRadar)
    // status: unread | read | removed | all  (we implement "all" as unread+read)
    const statusParam = (reqUrl.searchParams.get("status") || "all").toLowerCase();
    const days = clampInt(reqUrl.searchParams.get("days") || "5", 1, 30);

    // Miniflux pagination
    const perPage = clampInt(reqUrl.searchParams.get("limit") || "200", 1, 500);

    // Raw fetch safety cap (before dedupe/cap). Keep high enough for your ~6k/5d reality.
    const maxRaw = clampInt(reqUrl.searchParams.get("max") || "20000", 1000, 200000);

    // Post-processing controls (where you win)
    const dedupeOn = (reqUrl.searchParams.get("dedupe") || "1") !== "0";
    const perFeedCap = clampInt(reqUrl.searchParams.get("per_feed") || "50", 1, 1000);
    const outMax = clampInt(reqUrl.searchParams.get("out_max") || "2000", 100, 50000);

    const base = env.MINIFLUX_URL.replace(/\/$/, "");
    const headers = {
      "X-Auth-Token": env.MINIFLUX_TOKEN,
      "Accept": "application/json",
    };

    const publishedAfter = new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();
    const statuses = normalizeStatuses(statusParam);

    // 1) Fetch raw entries (time-bounded) across requested statuses
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

    // 2) Sort newest first (makes per-feed cap keep the latest items from each feed)
    raw.sort((a, b) => (b.published_at || "").localeCompare(a.published_at || ""));

    // 3) Dedupe (canonical URL preferred; fallback to feed+title)
    let deduped = raw;
    if (dedupeOn) {
      const seen = new Set();
      deduped = [];
      for (const e of raw) {
        const key = dedupeKey(e);
        if (seen.has(key)) continue;
        seen.add(key);
        deduped.push(e);
      }
    }

    // 4) Per-feed cap (keeps diversity; latest items survive due to step 2)
    const byFeedCount = new Map();
    const capped = [];
    for (const e of deduped) {
      const fid = e.feed?.id ?? "unknown";
      const c = byFeedCount.get(fid) || 0;
      if (c >= perFeedCap) continue;
      byFeedCount.set(fid, c + 1);
      capped.push(e);
      if (capped.length >= outMax) break;
    }

    // 5) Minimal schema output (what your dashboard/ranker actually needs)
    const entriesOut = capped.map((e) => ({
      id: e.id,
      title: e.title,
      url: e.url,
      published_at: e.published_at,
      status: e.status,
      feed: e.feed ? { id: e.feed.id, title: e.feed.title, site_url: e.feed.site_url } : null,
      tags: e.tags || [],
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
          dedupe: dedupeOn,
          after_dedupe: deduped.length,
          per_feed_cap: perFeedCap,
          out_max: outMax,
          returned: entriesOut.length,
        },
        entries: entriesOut,
      },
      200,
      {
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-store",
      }
    );
  } catch (err) {
    return json(
      {
        error: "Function crashed",
        message: String(err?.message || err),
        stack: err?.stack || null,
      },
      500
    );
  }
}

// Your Miniflux only accepts: read, unread, removed.
// Implement "all" here.
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
    if (safetyIters > 500) break; // hard safety brake

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

function dedupeKey(e) {
  const u = canonicalizeUrl(e.url || "");
  if (u) return `u:${u}`;
  const t = (e.title || "").trim().toLowerCase();
  const f = e.feed?.id ?? "unknown";
  return `t:${f}:${t}`;
}

function canonicalizeUrl(input) {
  try {
    if (!input) return "";
    const u = new URL(input);

    // drop hash
    u.hash = "";

    // remove common tracking params
    const dropPrefixes = ["utm_"];
    const dropExact = new Set([
      "fbclid",
      "gclid",
      "igshid",
      "mc_cid",
      "mc_eid",
      "mkt_tok",
      "ref",
      "ref_src",
      "spm",
      "cmpid",
    ]);

    for (const [k] of Array.from(u.searchParams.entries())) {
      const kl = k.toLowerCase();
      if (dropExact.has(kl) || dropPrefixes.some((p) => kl.startsWith(p))) {
        u.searchParams.delete(k);
      }
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
    headers: {
      "Content-Type": "application/json",
      ...extraHeaders,
    },
  });
}

function clampInt(value, min, max) {
  const n = parseInt(value, 10);
  if (Number.isNaN(n)) return min;
  return Math.max(min, Math.min(max, n));
}

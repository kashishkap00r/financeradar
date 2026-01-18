export async function onRequestGet({ request, env }) {
  try {
    if (!env.MINIFLUX_URL) return json({ error: "MINIFLUX_URL is missing in env vars" }, 500);
    if (!env.MINIFLUX_TOKEN) return json({ error: "MINIFLUX_TOKEN is missing in env vars" }, 500);

    const reqUrl = new URL(request.url);

    // User-facing params
    // status: unread | read | removed | all (we'll implement all)
    const statusParam = (reqUrl.searchParams.get("status") || "all").toLowerCase();
    const days = clampInt(reqUrl.searchParams.get("days") || "7", 1, 30);
    const perPage = clampInt(reqUrl.searchParams.get("limit") || "200", 1, 500);
    const maxItems = clampInt(reqUrl.searchParams.get("max") || "2000", 100, 10000);

    const base = env.MINIFLUX_URL.replace(/\/$/, "");
    const headers = {
      "X-Auth-Token": env.MINIFLUX_TOKEN,
      "Accept": "application/json",
    };

    const publishedAfter = new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();

    // Miniflux (your version) allows only: read, unread, removed.
    // Implement "all" by merging read+unread.
    const statuses = normalizeStatuses(statusParam);

    // Fetch, merge, then de-dupe by entry id
    const buckets = [];
    for (const st of statuses) {
      const entries = await fetchAllEntries({
        base,
        headers,
        status: st,
        perPage,
        maxItems,
        publishedAfter,
      });
      buckets.push(...entries);
    }

    // De-dupe by entry id (read/unread should never overlap, but be safe)
    const byId = new Map();
    for (const e of buckets) byId.set(e.id, e);
    const all = Array.from(byId.values());

    // Sort newest first by published_at (ISO string sorts lexicographically)
    all.sort((a, b) => (b.published_at || "").localeCompare(a.published_at || ""));

    // Cap
    const capped = all.slice(0, maxItems);

    // Minimal schema (clean payload)
    const slim = capped.map((e) => ({
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
          max: maxItems,
          published_after: publishedAfter,
          returned: slim.length,
        },
        entries: slim,
      },
      200,
      {
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-store",
      }
    );
  } catch (err) {
    return json(
      { error: "Function crashed", message: String(err?.message || err), stack: err?.stack || null },
      500
    );
  }
}

function normalizeStatuses(statusParam) {
  if (statusParam === "all") return ["unread", "read"]; // "all" = union of these
  if (statusParam === "unread") return ["unread"];
  if (statusParam === "read") return ["read"];
  if (statusParam === "removed") return ["removed"];
  // fallback
  return ["unread", "read"];
}

async function fetchAllEntries({ base, headers, status, perPage, maxItems, publishedAfter }) {
  let offset = 0;
  let all = [];
  let safetyIters = 0;

  while (all.length < maxItems) {
    safetyIters += 1;
    if (safetyIters > 100) break; // safety brake

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
        `Miniflux failed for status=${status} (${resp.status}). Upstream=${upstream.toString()} Body=${text.slice(
          0,
          300
        )}`
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

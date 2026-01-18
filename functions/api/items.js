export async function onRequestGet({ request, env }) {
  try {
    if (!env.MINIFLUX_URL) {
      return json({ error: "MINIFLUX_URL is missing in env vars" }, 500);
    }
    if (!env.MINIFLUX_TOKEN) {
      return json({ error: "MINIFLUX_TOKEN is missing in env vars" }, 500);
    }

    const reqUrl = new URL(request.url);

    // Defaults tuned for FinanceRadar
    const status = reqUrl.searchParams.get("status") || "all";
    const days = clampInt(reqUrl.searchParams.get("days") || "7", 1, 30); // keep it sane
    const perPage = clampInt(reqUrl.searchParams.get("limit") || "200", 1, 500); // 200 default; cap to be safe
    const maxItems = clampInt(reqUrl.searchParams.get("max") || "2000", 100, 10000); // prevent runaway loops

    // Miniflux API uses 'offset' pagination (not page numbers)
    // We'll fetch until we get fewer than perPage, or hit maxItems.
    const publishedAfter = new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();

    const base = env.MINIFLUX_URL.replace(/\/$/, "");
    const headers = {
      "X-Auth-Token": env.MINIFLUX_TOKEN,
      "Accept": "application/json",
    };

    let offset = 0;
    let all = [];
    let safetyIters = 0;

    while (all.length < maxItems) {
      safetyIters += 1;
      if (safetyIters > 100) break; // absolute safety brake

      const upstream = new URL(`${base}/v1/entries`);
      upstream.searchParams.set("status", status);
      upstream.searchParams.set("limit", String(perPage));
      upstream.searchParams.set("offset", String(offset));
      upstream.searchParams.set("order", "published_at");
      upstream.searchParams.set("direction", "desc");
      upstream.searchParams.set("published_after", publishedAfter);

      const resp = await fetch(upstream.toString(), { headers });

      // Read text first so we can show meaningful errors if JSON parsing fails
      const text = await resp.text();

      if (!resp.ok) {
        return json(
          {
            error: "Miniflux request failed",
            status: resp.status,
            upstream: upstream.toString(),
            body: text,
          },
          502
        );
      }

      let data;
      try {
        data = JSON.parse(text);
      } catch (e) {
        return json(
          {
            error: "Failed to parse Miniflux JSON",
            upstream: upstream.toString(),
            body_preview: text.slice(0, 500),
          },
          502
        );
      }

      const entries = Array.isArray(data.entries) ? data.entries : [];
      all.push(...entries);

      // Stop conditions
      if (entries.length < perPage) break;

      offset += perPage;
    }

    // Hard cap
    if (all.length > maxItems) all = all.slice(0, maxItems);

    // Minimal schema (clean payload)
    const slim = all.map((e) => ({
      id: e.id,
      title: e.title,
      url: e.url,
      published_at: e.published_at,
      status: e.status,
      feed: e.feed
        ? { id: e.feed.id, title: e.feed.title, site_url: e.feed.site_url }
        : null,
      tags: e.tags || [],
    }));

    return json(
      {
        meta: {
          status,
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
        // If you later lock this down, replace * with your app domain.
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

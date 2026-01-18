export async function onRequestGet({ request, env }) {
  try {
    // Hard fail early if env vars missing
    if (!env.MINIFLUX_URL) {
      return new Response(JSON.stringify({ error: "MINIFLUX_URL is missing in env vars" }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (!env.MINIFLUX_TOKEN) {
      return new Response(JSON.stringify({ error: "MINIFLUX_TOKEN is missing in env vars" }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      });
    }

    const url = new URL(request.url);
    const limit = url.searchParams.get("limit") || "50";
    const status = url.searchParams.get("status") || "unread";

    // Normalize base URL (remove trailing slash if any)
    const base = env.MINIFLUX_URL.replace(/\/$/, "");
    const upstream = `${base}/v1/entries?limit=${encodeURIComponent(limit)}&status=${encodeURIComponent(status)}`;

    const resp = await fetch(upstream, {
      headers: {
        "X-Auth-Token": env.MINIFLUX_TOKEN,
        "Accept": "application/json",
      },
    });

    const text = await resp.text();

    if (!resp.ok) {
      return new Response(JSON.stringify({
        error: "Miniflux request failed",
        upstream,
        status: resp.status,
        body: text,
      }), {
        status: 502,
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response(text, {
      headers: {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-store",
      },
    });
  } catch (err) {
    return new Response(JSON.stringify({
      error: "Function crashed",
      message: String(err?.message || err),
      stack: err?.stack || null,
    }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
}

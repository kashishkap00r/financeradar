export async function onRequestGet({ request, env }) {
  const url = new URL(request.url);
  const limit = url.searchParams.get("limit") || "50";
  const status = url.searchParams.get("status") || "all";

  const upstream =
    `${env.MINIFLUX_URL}/v1/entries?limit=${encodeURIComponent(limit)}&status=${encodeURIComponent(status)}`;

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
      status: resp.status,
      body: text
    }), { status: 502, headers: { "Content-Type": "application/json" }});
  }

  return new Response(text, {
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
      "Cache-Control": "no-store",
    },
  });
}

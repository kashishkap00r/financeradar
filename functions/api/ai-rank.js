export async function onRequestGet({ env }) {
  const base = env.MINIFLUX_BASE_URL.replace(/\/+$/, "");
  const url =
    base +
    "/v1/entries?status=unread&direction=desc&order=published_at&limit=50";

  const r = await fetch(url, {
    headers: {
      "X-Auth-Token": env.MINIFLUX_TOKEN,
    },
  });

  if (!r.ok) {
    return new Response(
      JSON.stringify(
        { error: "miniflux_fetch_failed", status: r.status },
        null,
        2
      ),
      { status: 500 }
    );
  }

  const data = await r.json();
  const entries = data.entries || [];

  const top = entries.map((e, i) => ({
    id: e.id,
    score: null, // no ranking yet
    bucket: "unranked",
    title: e.title,
    source: e.feed?.title || "",
    published_at: e.published_at,
    url: e.url,
    why: "Raw Miniflux entry (no AI yet)",
    tags: [],
  }));

  const payload = {
    date: new Date().toISOString().slice(0, 10),
    generated_at: new Date().toISOString(),
    source: "miniflux-raw",
    total: top.length,
    top,
  };

  return new Response(JSON.stringify(payload, null, 2), {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

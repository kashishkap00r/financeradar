export async function onRequestGet() {
  const payload = {
    date: new Date().toISOString().slice(0, 10),
    generated_at: new Date().toISOString(),
    source: "dummy-ai",
    top: [
      {
        id: 1,
        score: 92,
        bucket: "must_read",
        title: "Dummy story to test AI rank endpoint",
        source: "Test Source",
        published_at: new Date().toISOString(),
        url: "https://example.com",
        why: "Placeholder output to verify endpoint works",
        tags: ["banking", "macro"]
      }
    ]
  };

  return new Response(JSON.stringify(payload, null, 2), {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store"
    }
  });
}

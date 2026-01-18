// functions/api/ai-rank.js
// Calls /api/candidates, asks Gemini to rerank, returns grouped top list.
// Gemini generateContent docs: https://ai.google.dev/api/generate-content
// Models docs: https://ai.google.dev/gemini-api/docs/models

export async function onRequestGet({ request, env }) {
  try {
    if (!env.GEMINI_API_KEY) return json({ error: "GEMINI_API_KEY missing" }, 500);

    const url = new URL(request.url);

    // What the dashboard wants
    const days = clampInt(url.searchParams.get("days") || "5", 1, 30);
    const topN = clampInt(url.searchParams.get("top") || "100", 1, 200);

    // How many we send to Gemini to choose from (keep bounded)
    const pool = clampInt(url.searchParams.get("pool") || "250", 50, 400);

    // Gemini model (fast + good enough for reranking)
    const model = (url.searchParams.get("model") || "gemini-2.5-flash").trim();

    // Cache control for this AI call (important: cost + latency)
    // 120s cache is usually perfect for a dashboard.
    const cacheSeconds = clampInt(url.searchParams.get("cache_s") || "120", 0, 1800);

    const t0 = Date.now();

    // 1) Pull candidates from your own endpoint (heuristic-ranked)
    // IMPORTANT: keep URL stable to benefit from caching in /api/candidates too.
    const base = `${url.origin}/api/candidates`;
    const candUrl = new URL(base);
    candUrl.searchParams.set("days", String(days));
    candUrl.searchParams.set("top", String(pool));     // take top pool items from heuristic
    candUrl.searchParams.set("stop_when_clusters", "1000");
    // candUrl.searchParams.set("debug", "0"); // keep compact

    const candResp = await fetch(candUrl.toString());
    const candJson = await candResp.json();
    if (!candResp.ok) {
      return json({ error: "Failed to fetch candidates", upstream: candJson }, 502);
    }

    const candidates = Array.isArray(candJson.top) ? candJson.top : [];
    if (candidates.length === 0) {
      return json({ error: "No candidates to rank", meta: candJson.meta || null }, 200);
    }

    // 2) Build compact items for Gemini (keep tokens low)
    const items = candidates.slice(0, pool).map((it, idx) => ({
      i: idx, // local index for mapping back
      id: it.id,
      title: it.title,
      url: it.url,
      published_at: it.published_at,
      feed: it.feed?.title || "",
      age_hours: it.age_hours,
      mentions: it.mentions,
      sources_count: it.sources_count ?? undefined,
      why: it.why || ""
    }));

    const tCandDone = Date.now();

    // 3) Ask Gemini to rerank
    const prompt = buildRankPrompt(items, topN, days);

    const geminiOut = await geminiGenerate({
      apiKey: env.GEMINI_API_KEY,
      model,
      prompt
    });

    const tGemDone = Date.now();

    const parsed = extractJson(geminiOut);
    if (!parsed || !Array.isArray(parsed.ranked)) {
      // Fallback: return heuristic top if Gemini output is malformed
      const fallback = candidates.slice(0, topN);
      const groups = groupByDay(fallback);

      return json(
        {
          meta: {
            mode: "fallback_heuristic",
            days,
            top: topN,
            pool_used: items.length,
            model,
            timing: {
              total_ms: Date.now() - t0,
              candidates_ms: tCandDone - t0,
              gemini_ms: tGemDone - tCandDone
            },
            note: "Gemini response not parseable; returned heuristic ranking."
          },
          groups,
          top: fallback
        },
        200,
        cacheHeaders(cacheSeconds)
      );
    }

    // 4) Map ranked indices back to original candidate objects
    const rankedIdx = parsed.ranked
      .map((x) => Number(x))
      .filter((n) => Number.isFinite(n) && n >= 0 && n < candidates.length);

    // Deduplicate while preserving order
    const seen = new Set();
    const reranked = [];
    for (const i of rankedIdx) {
      if (seen.has(i)) continue;
      seen.add(i);
      reranked.push(candidates[i]);
      if (reranked.length >= topN) break;
    }

    // If Gemini returned fewer than topN, fill from heuristic
    if (reranked.length < topN) {
      for (let i = 0; i < candidates.length && reranked.length < topN; i++) {
        if (seen.has(i)) continue;
        seen.add(i);
        reranked.push(candidates[i]);
      }
    }

    // Optional: attach a short reason from Gemini if it provided notes
    const notes = (parsed.notes && typeof parsed.notes === "object") ? parsed.notes : null;
    const finalTop = reranked.map((it, idx) => {
      const note = notes?.[String(idx)] || notes?.[String(it.id)] || null;
      return note ? { ...it, ai_note: String(note).slice(0, 240) } : it;
    });

    const groups = groupByDay(finalTop);

    return json(
      {
        meta: {
          mode: "gemini_rerank",
          days,
          top: topN,
          pool_used: items.length,
          model,
          timing: {
            total_ms: Date.now() - t0,
            candidates_ms: tCandDone - t0,
            gemini_ms: tGemDone - tCandDone
          }
        },
        groups,
        top: finalTop
      },
      200,
      cacheHeaders(cacheSeconds)
    );

  } catch (err) {
    return json({ error: "ai-rank crashed", message: String(err?.message || err) }, 500);
  }
}

function buildRankPrompt(items, topN, days) {
  // Items are already finance-ish, but still mixed sometimes.
  // Goal: prioritize "what matters" not only recency.
  return `
You are ranking items for a finance research dashboard.

You will be given a list of news items. Each item has:
- i (index), title, url, published_at, feed, age_hours, mentions, sources_count, why

Task:
Return JSON ONLY (no markdown, no explanation) in this exact shape:
{
  "ranked": [<i>, <i>, ...],   // length exactly ${topN} if possible, otherwise as many as you can
  "notes": { "<i>": "very short reason (<= 12 words)" }
}

Ranking priorities (in order):
1) Market-moving and financially material items (macro, rates, inflation, oil, FX, credit, banking, earnings, regulation impacting businesses).
2) Big companies, sectors, and second-order effects (supply chain, pricing power, demand shocks).
3) Cross-source confirmation: prefer higher mentions/sources_count if quality is similar.
4) Recency matters, but DO NOT make it a pure freshness list. Older but important items should rank high.

Avoid:
- Pure sports/cricket
- Pure party politics / campaign drama with no market impact
- Celebrity / entertainment
- Clickbait

Input window: last ${days} days.

ITEMS:
${JSON.stringify(items)}
`.trim();
}

async function geminiGenerate({ apiKey, model, prompt }) {
  // Gemini API generateContent
  // Official docs show models.generateContent method and endpoint format. :contentReference[oaicite:2]{index=2}
  const endpoint = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent?key=${encodeURIComponent(apiKey)}`;

  const body = {
    contents: [
      { role: "user", parts: [{ text: prompt }] }
    ],
    generationConfig: {
      temperature: 0.2,
      topP: 0.9
    }
  };

  const resp = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });

  const text = await resp.text();
  if (!resp.ok) {
    throw new Error(`Gemini HTTP ${resp.status}: ${text.slice(0, 500)}`);
  }

  let data;
  try { data = JSON.parse(text); }
  catch { throw new Error(`Gemini JSON parse fail: ${text.slice(0, 500)}`); }

  // Typical response: candidates[0].content.parts[0].text
  const out = data?.candidates?.[0]?.content?.parts?.map(p => p.text).join("") || "";
  return out;
}

function extractJson(s) {
  if (!s) return null;
  // Try direct parse first
  try { return JSON.parse(s); } catch {}

  // Otherwise, extract first {...} block
  const start = s.indexOf("{");
  const end = s.lastIndexOf("}");
  if (start === -1 || end === -1 || end <= start) return null;

  const slice = s.slice(start, end + 1);
  try { return JSON.parse(slice); } catch { return null; }
}

function groupByDay(items) {
  const m = new Map();
  for (const it of items) {
    const d = (it.published_at || "").slice(0, 10) || "unknown";
    if (!m.has(d)) m.set(d, []);
    m.get(d).push(it);
  }
  return Array.from(m.entries()).map(([day, items]) => ({ day, items }));
}

function cacheHeaders(cacheSeconds) {
  if (cacheSeconds <= 0) {
    return { "Access-Control-Allow-Origin": "*", "Cache-Control": "no-store" };
  }
  return {
    "Access-Control-Allow-Origin": "*",
    "Cache-Control": `public, max-age=${cacheSeconds}, s-maxage=${cacheSeconds}, stale-while-revalidate=300`
  };
}

function json(obj, status = 200, headers = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...headers }
  });
}

function clampInt(value, min, max) {
  const n = parseInt(value, 10);
  if (Number.isNaN(n)) return min;
  return Math.max(min, Math.min(max, n));
}

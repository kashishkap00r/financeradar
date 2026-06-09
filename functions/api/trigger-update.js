// Cloudflare Pages Function — POST /api/trigger-update
//
// Lets a colleague manually re-run the "Update FinanceRadar" GitHub Action
// (hourly.yml) from the live site, but ONLY when the site is genuinely stale.
//
// Why this exists as a server endpoint: triggering a GitHub Action needs a
// token with actions:write. That token can never live in browser JS, so it is
// held here as an encrypted Pages secret (env.GH_DISPATCH_TOKEN) and the
// dispatch happens server-side. The staleness rule is also enforced here —
// the client check is only for UX and is trivially bypassable.

const REPO = "kashishkap00r/financeradar";
const WORKFLOW = "hourly.yml";
const BRANCH = "main";
const STALE_HOURS = 2 / 60; // TEMP TEST: 2 minutes — REVERT to 2
const COOLDOWN_MIN = 1; // TEMP TEST: 1 minute — REVERT to 10

const GH_HEADERS_BASE = {
  Accept: "application/vnd.github+json",
  "X-GitHub-Api-Version": "2022-11-28",
  // GitHub rejects API requests without a User-Agent.
  "User-Agent": "financeradar-trigger",
};

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

export async function onRequest({ request, env }) {
  if (request.method !== "POST") {
    return jsonResponse({ ok: false, reason: "method_not_allowed", message: "Use POST." }, 405);
  }

  const token = env.GH_DISPATCH_TOKEN;
  if (!token) {
    // Misconfiguration, not the user's fault — keep it generic, no secret leak.
    return jsonResponse(
      { ok: false, reason: "not_configured", message: "Trigger endpoint is not configured." },
      500,
    );
  }

  const authHeaders = { ...GH_HEADERS_BASE, Authorization: `Bearer ${token}` };

  // --- Check 1 & 2: look at recent runs (in-progress guard + cooldown) ---
  let runs;
  try {
    const runsRes = await fetch(
      `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?per_page=5`,
      { headers: authHeaders },
    );
    if (!runsRes.ok) {
      return jsonResponse(
        { ok: false, reason: "github_error", message: "Could not check workflow status." },
        502,
      );
    }
    runs = (await runsRes.json()).workflow_runs || [];
  } catch (err) {
    return jsonResponse(
      { ok: false, reason: "github_error", message: "Could not reach GitHub." },
      502,
    );
  }

  const active = runs.find((r) => r.status === "queued" || r.status === "in_progress");
  if (active) {
    return jsonResponse({ ok: false, reason: "already_running", message: "A refresh is already running." });
  }

  if (runs.length) {
    const lastStartedMs = new Date(runs[0].created_at).getTime();
    const ageMin = (Date.now() - lastStartedMs) / 60000;
    if (ageMin < COOLDOWN_MIN) {
      return jsonResponse({
        ok: false,
        reason: "cooldown",
        retry_after_min: Math.ceil(COOLDOWN_MIN - ageMin),
        message: "A refresh just ran — try again in a few minutes.",
      });
    }
  }

  // --- Check 3: is the published site actually stale? ---
  // articles.json is committed + deployed, so it reflects the last SUCCESSFUL
  // update. Gating on this (not on run start time) means repeated failed runs
  // leave the button available — which is exactly the scenario we built this for.
  try {
    const siteRes = await fetch(new URL("/static/articles.json", request.url).toString(), {
      cache: "no-store",
    });
    if (siteRes.ok) {
      const generatedAt = (await siteRes.json()).generated_at;
      if (generatedAt) {
        const ageHours = (Date.now() - new Date(generatedAt).getTime()) / 3600000;
        if (ageHours < STALE_HOURS) {
          return jsonResponse({
            ok: false,
            reason: "fresh",
            updated_min_ago: Math.floor(ageHours * 60),
            message: "Site is already up to date.",
          });
        }
      }
    }
    // If we can't read generated_at, fail open: the run/cooldown guards above
    // still cap abuse to one trigger per cooldown window.
  } catch (err) {
    // ignore — fail open per above
  }

  // --- Dispatch ---
  try {
    const dispatchRes = await fetch(
      `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
      {
        method: "POST",
        headers: { ...authHeaders, "Content-Type": "application/json" },
        body: JSON.stringify({ ref: BRANCH }),
      },
    );
    if (dispatchRes.status === 204) {
      return jsonResponse({ ok: true, message: "Refresh started — new content in ~3 min." });
    }
    // Don't echo GitHub's raw body (may carry token hints); just the status.
    return jsonResponse(
      { ok: false, reason: "dispatch_failed", status: dispatchRes.status, message: "Could not start the refresh." },
      502,
    );
  } catch (err) {
    return jsonResponse(
      { ok: false, reason: "dispatch_failed", message: "Could not start the refresh." },
      502,
    );
  }
}

const DEFAULT_ALLOWED_HOSTS = "";
const DEFAULT_FETCH_TIMEOUT_MS = 20000;

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...corsHeaders,
    },
  });
}

function parseAllowedHosts(raw) {
  const value = (raw || "").trim();
  if (!value) return [];
  return value
    .split(",")
    .map((x) => x.trim().toLowerCase())
    .filter(Boolean);
}

function isHostAllowed(host, allowedHosts) {
  if (!allowedHosts.length) return true;
  const normalized = host.toLowerCase();
  return allowedHosts.some((entry) => {
    if (normalized === entry) return true;
    return normalized.endsWith(`.${entry}`);
  });
}

function buildErrorMessage(err) {
  if (!err) return "Unknown error";
  if (typeof err === "string") return err;
  return err.message || String(err);
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }
    if (request.method !== "GET") {
      return jsonResponse({ error: "Method not allowed" }, 405);
    }

    const reqUrl = new URL(request.url);
    const feedUrlRaw = reqUrl.searchParams.get("url");
    if (!feedUrlRaw) {
      return jsonResponse({ error: "Missing url parameter" }, 400);
    }

    let target;
    try {
      target = new URL(feedUrlRaw);
    } catch {
      return jsonResponse({ error: "Invalid url parameter" }, 400);
    }

    if (target.protocol !== "http:" && target.protocol !== "https:") {
      return jsonResponse({ error: "Only http/https URLs are allowed" }, 400);
    }

    const allowedHosts = parseAllowedHosts(env.ALLOWED_HOSTS || DEFAULT_ALLOWED_HOSTS);
    if (!isHostAllowed(target.hostname, allowedHosts)) {
      return jsonResponse({ error: "Target host is not allowed", host: target.hostname }, 403);
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(
      () => controller.abort(new Error("Upstream request timed out")),
      Number(env.FETCH_TIMEOUT_MS || DEFAULT_FETCH_TIMEOUT_MS),
    );

    try {
      const upstream = await fetch(target.toString(), {
        method: "GET",
        signal: controller.signal,
        redirect: "follow",
        headers: {
          "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
          Accept: "application/rss+xml, application/xml, text/xml, application/atom+xml, */*",
          "Accept-Language": "en-US,en;q=0.9",
        },
      });

      const bodyText = await upstream.text();
      if (!upstream.ok) {
        return jsonResponse(
          {
            error: "Upstream fetch failed",
            status: upstream.status,
            status_text: upstream.statusText || "",
          },
          upstream.status,
        );
      }

      return new Response(bodyText, {
        status: 200,
        headers: {
          "Content-Type": upstream.headers.get("Content-Type") || "application/xml; charset=utf-8",
          "Cache-Control": "public, max-age=300",
          ...corsHeaders,
        },
      });
    } catch (err) {
      return jsonResponse({ error: buildErrorMessage(err) }, 500);
    } finally {
      clearTimeout(timeoutId);
    }
  },
};


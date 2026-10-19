"""Shared Gemini client for the AI rankers (ai_ranker, wsw_ranker, twitter_signal).

Every call takes a *chain* of model IDs and walks it until one model returns
output the caller's ``parse`` function accepts:

- 429 / 5xx / timeouts / unparseable output → retried on the same model with
  backoff (honouring Google's ``retryDelay`` hint when it's short).
- 404 (model retired or renamed) or an exhausted rate limit → the model is
  skipped for the rest of the run, so later calls go straight to the next one.
- 400 while a thinkingConfig is set → retried once without it (newer models
  reject older thinking params and vice versa).
- 401 / 403 → no retries on that model; the next model is tried.

The API's model list is fetched once per run. Chain entries Google no longer
lists are pushed to the back, and the newest listed Flash models are appended
as a last resort, so a model retirement can't take the rankers down.

The key is sent via the x-goog-api-key header (never the URL) so it can't leak
into request logs; errors are passed through sanitize_error before printing.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request

from config import SSL_CONTEXT

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
LIST_MODELS_TIMEOUT = 20
MAX_RETRY_DELAY = 60          # seconds; a longer retryDelay means "quota gone", move on
BACKOFF_SECONDS = [5, 20, 45]
DISCOVERED_FALLBACKS = 2      # newest listed Flash models appended to every chain

SAFETY_SETTINGS = [
    {"category": cat, "threshold": "BLOCK_NONE"}
    for cat in (
        "HARM_CATEGORY_HARASSMENT",
        "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "HARM_CATEGORY_DANGEROUS_CONTENT",
    )
]

# Plain Flash / Flash-Lite IDs, e.g. gemini-2.5-flash, gemini-3-flash-preview.
# Dated snapshots and image/tts/live variants are deliberately not matched.
FLASH_MODEL_RE = re.compile(r"^gemini-(\d+(?:\.\d+)?)-flash(-lite)?(-preview)?$")

_skipped_models = set()
_listed_models = None
_listed_loaded = False


def sanitize_error(err):
    return re.sub(
        r'AIza\S{20,}|sk-or-\S{20,}|Bearer\s+\S+|key[=:]\s*["\']?\S{10,}',
        '[REDACTED]',
        str(err),
    )[:200]


def pretty_model_name(model_id):
    """gemini-2.5-flash-lite → 'Gemini 2.5 Flash-Lite'."""
    name = model_id.replace("flash-lite", "Flash-Lite")
    parts = [p if p[:1].isupper() else p.capitalize() for p in name.split("-")]
    return " ".join(parts).replace("Flash Lite", "Flash-Lite")


def thinking_config(model_id):
    """Keep ranking calls fast and cheap: no/low thinking where the model allows."""
    if model_id.startswith("gemini-2.5-flash-lite"):
        return None  # thinking is off by default
    if model_id.startswith("gemini-2.5-flash"):
        return {"thinkingBudget": 0}
    if re.match(r"gemini-\d", model_id) and not model_id.startswith(("gemini-1", "gemini-2")):
        return {"thinkingLevel": "low"}
    return None


def _api_key():
    return os.environ.get("GEMINI_API_KEY", "")


def list_models():
    """Return the set of model IDs that support generateContent, or None if unknown."""
    global _listed_models, _listed_loaded
    if _listed_loaded:
        return _listed_models
    _listed_loaded = True
    try:
        names = set()
        page_token = ""
        for _ in range(5):
            url = f"{API_BASE}/models?pageSize=1000"
            if page_token:
                url += f"&pageToken={page_token}"
            request = urllib.request.Request(url, headers={"x-goog-api-key": _api_key()})
            with urllib.request.urlopen(request, timeout=LIST_MODELS_TIMEOUT, context=SSL_CONTEXT) as response:
                data = json.loads(response.read().decode("utf-8"))
            for model in data.get("models", []):
                if "generateContent" in model.get("supportedGenerationMethods", []):
                    names.add(model.get("name", "").removeprefix("models/"))
            page_token = data.get("nextPageToken", "")
            if not page_token:
                break
        _listed_models = names
        flash = sorted(m for m in names if FLASH_MODEL_RE.match(m))
        print(f"  [gemini] {len(names)} models available; Flash: {', '.join(flash) or 'none'}")
    except Exception as err:
        print(f"  [gemini] Could not list models ({sanitize_error(err)}); using chains as-is")
        _listed_models = None
    return _listed_models


def newest_flash_models(listed):
    """Listed Flash models, newest first; stable before preview, Flash before Lite."""
    ranked = []
    for model_id in listed or ():
        match = FLASH_MODEL_RE.match(model_id)
        if match:
            version, lite, preview = match.groups()
            ranked.append(((float(version), not preview, not lite), model_id))
    return [model_id for _, model_id in sorted(ranked, reverse=True)]


def resolve_chain(chain):
    """Order a chain by what the API actually offers right now."""
    listed = list_models()
    chain = [m for m in dict.fromkeys(chain) if m not in _skipped_models]
    if listed is None:
        return chain
    available = [m for m in chain if m in listed]
    unlisted = [m for m in chain if m not in listed]
    extras = [
        m for m in newest_flash_models(listed)
        if m not in chain and m not in _skipped_models
    ][:DISCOVERED_FALLBACKS]
    return available + extras + unlisted


def _generate_once(prompt, model_id, timeout, thinking):
    generation_config = {"responseMimeType": "application/json"}
    if thinking:
        generation_config["thinkingConfig"] = thinking
    request = urllib.request.Request(
        f"{API_BASE}/models/{model_id}:generateContent",
        data=json.dumps({
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": generation_config,
            "safetySettings": SAFETY_SETTINGS,
        }).encode("utf-8"),
        headers={
            "x-goog-api-key": _api_key(),
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout, context=SSL_CONTEXT) as response:
        result = json.loads(response.read().decode("utf-8"))
    candidates = result.get("candidates") or []
    if not candidates:
        raise ValueError(f"no candidates: {sanitize_error(json.dumps(result))}")
    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts if not part.get("thought"))
    if not text.strip():
        reason = candidates[0].get("finishReason", "unknown")
        raise ValueError(f"empty text (finishReason={reason})")
    return text


def _http_error_body(err):
    try:
        return err.read().decode("utf-8", "replace")
    except Exception:
        return ""


def _retry_delay(body):
    match = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', body)
    return float(match.group(1)) if match else None


def generate_json(prompt, chain, parse, timeout=180, attempts=3, label=""):
    """Run ``prompt`` through the first model in ``chain`` that works.

    Returns ``(parse(text), model_id)``. Raises RuntimeError if every model fails.
    """
    if not _api_key():
        raise RuntimeError("GEMINI_API_KEY not set")
    tag = f"{label}: " if label else ""
    errors = []
    for model_id in resolve_chain(chain):
        thinking = thinking_config(model_id)
        attempt = 0
        while attempt < attempts:
            attempt += 1
            wait = BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)]
            try:
                return parse(_generate_once(prompt, model_id, timeout, thinking)), model_id
            except urllib.error.HTTPError as err:
                body = _http_error_body(err)
                message = f"{model_id} HTTP {err.code}"
                if err.code == 400 and thinking:
                    # Doesn't count as an attempt: it's a config mismatch, not a failure.
                    print(f"    [gemini] {tag}{message} with thinkingConfig, retrying without it")
                    thinking = None
                    attempt -= 1
                    continue
                errors.append(message)
                if err.code in (400, 401, 403, 404):
                    if err.code == 404:
                        _skipped_models.add(model_id)
                    break
                if err.code == 429:
                    hint = _retry_delay(body)
                    if (hint is not None and hint > MAX_RETRY_DELAY) or attempt == attempts:
                        _skipped_models.add(model_id)  # quota exhausted for this run
                        break
                    if hint is not None:
                        wait = hint + 1
            except Exception as err:
                errors.append(f"{model_id}: {sanitize_error(err)}")
            if attempt < attempts:
                print(f"    [gemini] {tag}{errors[-1]} — retry {attempt + 1}/{attempts} in {wait:.0f}s")
                time.sleep(wait)
        print(f"    [gemini] {tag}giving up on {model_id} ({errors[-1] if errors else 'no output'})")
    raise RuntimeError("All Gemini models failed: " + "; ".join(errors[-4:]))

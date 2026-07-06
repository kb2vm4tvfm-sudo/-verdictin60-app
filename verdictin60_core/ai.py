"""Ollama/AI helpers, moved from app.py (Phase 4 refactor, no behavior change).

- AI_SPEED_MODES: model choices per speed mode / task.
- get_ai_speed_mode / get_ai_model / get_ai_timeout: resolve the configured
  speed mode into a model name or timeout for a given task.
- is_timeout_error: classify an exception as an AI request timeout.
- check_ollama / check_ollama_model_installed: Ollama availability checks.
- _ollama_call / ollama_generate / ollama_identify: low-level and
  task-specific Ollama request calls.
- nvidia_generate / nvidia_identify: optional NVIDIA NIM cloud calls, used only
  when the user has configured an API key and selected a Cloud provider mode.
- ai_generate / ai_identify / ai_task_ready: provider-aware wrappers that pick
  between Ollama and NVIDIA NIM based on the "AI Provider" setting. Ollama
  stays the default; NVIDIA is only used if explicitly enabled and configured.
"""
import json
import os
import re
import urllib.error
import urllib.request

from verdictin60_core.settings import load_settings
from verdictin60_core import provider_guard

AI_SPEED_MODES = {
    "Fast": {
        "identify": "llama3.1:8b",
        "caption": "llama3.1:8b",
        "verify": "llama3.1:8b",
    },
    "Balanced": {
        "identify": "llama3.1:8b",
        "caption": "qwen3:14b",
        "verify": "qwen3:14b",
    },
    "Best Accuracy": {
        "identify": "llama3.1:8b",
        "caption": "qwen3:32b",
        "verify": "qwen3:32b",
    },
}


def get_ai_speed_mode() -> str:
    mode = load_settings().get("ai_speed_mode", "Balanced")
    return mode if mode in AI_SPEED_MODES else "Balanced"


def get_ai_model(task: str) -> str:
    mode = get_ai_speed_mode()
    return AI_SPEED_MODES[mode].get(task, AI_SPEED_MODES["Balanced"][task])


def get_ai_timeout(task: str) -> int:
    model = get_ai_model(task)
    if task == "identify":
        return 45
    if model == "qwen3:32b":
        return 300
    return 120


def is_timeout_error(exc: Exception) -> bool:
    return isinstance(exc, TimeoutError) or "timed out" in str(exc).lower()


def check_ollama():
    """Return True if Ollama is running and the selected caption model is available."""
    try:
        import urllib.request
        r = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
        data = json.loads(r.read())
        models = [m["name"] for m in data.get("models", [])]
        model = get_ai_model("caption")
        return any(m == model for m in models)
    except Exception:
        return False


def check_ollama_model_installed(model: str) -> bool:
    """Return True if Ollama is running and the exact model is installed."""
    try:
        import urllib.request
        r = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
        data = json.loads(r.read())
        models = [m["name"] for m in data.get("models", [])]
        return any(m == model for m in models)
    except Exception:
        return False


def _ollama_call(model: str, prompt: str, timeout: int = 300,
                 num_predict: int = 1000) -> str:
    """Low-level Ollama call with explicit model name.

    qwen3 models require '/no_think' appended to suppress the <think> block
    so the `response` field contains the actual output.  If the first attempt
    returns an empty string (qwen3 occasionally ignores /no_think when the
    prompt is very long), we retry once without it and strip <think> blocks
    from whatever comes back.
    """
    import urllib.request

    def _call(prompt_text: str) -> str:
        payload = json.dumps({
            "model": model,
            "prompt": prompt_text,
            "stream": False,
            "options": {"num_predict": num_predict},
        }).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        r = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(r.read()).get("response", "")

    is_qwen3 = "qwen3" in model
    result = _call(prompt + " /no_think" if is_qwen3 else prompt)

    # Retry without /no_think if qwen3 returned nothing (happens on long prompts)
    if is_qwen3 and not result.strip():
        print(f"[OLLAMA] qwen3 empty response — retrying without /no_think")
        result = _call(prompt)
        # Strip any <think>…</think> block that the retry may include
        result = re.sub(r'<think>.*?</think>', '', result,
                        flags=re.DOTALL | re.IGNORECASE).strip()

    return result


def ollama_generate(prompt: str, timeout: int = None, task: str = "caption",
                    num_predict: int = 1000) -> str:
    """Send a prompt to local Ollama using the selected speed-mode model."""
    model = get_ai_model(task)
    return _ollama_call(model, prompt, timeout or get_ai_timeout(task), num_predict)


def ollama_identify(prompt: str, timeout: int = None) -> str:
    """Send a case-identification prompt using the fast model (llama3.1:8b).
    Falls back to the configured accuracy model if llama3.1:8b is not installed."""
    import urllib.request
    fast_model = get_ai_model("identify")
    try:
        r = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
        models = [m["name"] for m in json.loads(r.read()).get("models", [])]
        if not any("llama3.1" in m for m in models):
            fast_model = get_ai_model("caption")
    except Exception:
        fast_model = get_ai_model("caption")
    return _ollama_call(fast_model, prompt, timeout or get_ai_timeout("identify"))


# ─────────────────────────────────────────────────────────────────────────────
# NVIDIA NIM — optional free cloud fallback (disabled unless configured)
# ─────────────────────────────────────────────────────────────────────────────

NVIDIA_API_BASE = "https://integrate.api.nvidia.com/v1"

AI_PROVIDER_MODES = ("Local only", "Cloud fallback", "Cloud only")

# Per-task NVIDIA NIM model defaults. Each entry is (task, label, default
# model) — the label and default are used to build the optional "Advanced"
# per-task model fields in Settings. One NVIDIA API key covers every task;
# a task falls back to its default model whenever its settings field is left
# blank.
NVIDIA_TASK_FIELDS = [
    ("identify", "Case identification model", "nvidia/nemotron-3-ultra-550b-a55b"),
    ("caption", "Caption generation model", "nvidia/nemotron-3-ultra-550b-a55b"),
    ("verify", "Verification model", "nvidia/nemotron-3-ultra-550b-a55b"),
    ("rerank", "Source rerank model", "nvidia/llama-nemotron-rerank-1b-v2"),
    ("ocr", "OCR model", "nvidia/nemotron-ocr-v2"),
    ("safety", "Safety model", "nvidia/nemotron-3.5-content-safety"),
]
NVIDIA_DEFAULT_MODELS = {task: default for task, _label, default in NVIDIA_TASK_FIELDS}
NVIDIA_MODEL_SETTINGS_KEYS = {task: f"nvidia_model_{task}" for task, _label, _default in NVIDIA_TASK_FIELDS}


class NvidiaAPIError(Exception):
    """Raised for NVIDIA NIM errors (network, auth, quota/rate-limit, bad response)."""


def get_ai_provider_mode() -> str:
    mode = load_settings().get("ai_provider_mode", "Local only")
    return mode if mode in AI_PROVIDER_MODES else "Local only"


def get_nvidia_api_key() -> str:
    """Read the NVIDIA API key from settings, falling back to an env var.
    Never printed or logged anywhere in this module."""
    key = load_settings().get("nvidia_api_key", "") or os.environ.get("NVIDIA_API_KEY", "")
    return key.strip()


def nvidia_available() -> bool:
    return bool(get_nvidia_api_key())


def nvidia_ready() -> bool:
    """True if NVIDIA NIM has a key configured and isn't disabled by the
    cost/quota safety guard (rate-limited, quota-exhausted, or auth failure)."""
    return nvidia_available() and not provider_guard.is_provider_disabled("nvidia")


def get_nvidia_status() -> str:
    """Human-readable status for the read-only Settings provider list."""
    if not nvidia_available():
        return "Missing key"
    return provider_guard.provider_status("nvidia")


def get_nvidia_model(task: str) -> str:
    """Resolve the NVIDIA NIM model for `task`: the user's per-task override
    from Settings > AI > Advanced if they filled one in, otherwise the app
    default for that task."""
    default = NVIDIA_DEFAULT_MODELS.get(task, NVIDIA_DEFAULT_MODELS["caption"])
    settings_key = NVIDIA_MODEL_SETTINGS_KEYS.get(task)
    if not settings_key:
        return default
    override = (load_settings().get(settings_key) or "").strip()
    return override or default


def ai_task_ready(task: str) -> bool:
    """True if `task` can run right now given the current AI Provider setting:
    either the local Ollama model is installed, or a Cloud mode has a NVIDIA
    key configured."""
    mode = get_ai_provider_mode()
    if mode == "Cloud only":
        return nvidia_ready()
    ready = check_ollama_model_installed(get_ai_model(task))
    if mode == "Cloud fallback" and nvidia_ready():
        return True
    return ready


# Tasks where deterministic, low-randomness output matters more than variety —
# identification/verification should reliably return the same well-formed
# answer for the same input rather than creative prose.
NVIDIA_LOW_TEMPERATURE_TASKS = ("identify", "verify")
NVIDIA_LOW_TEMPERATURE = 0.1


def _nvidia_call(model: str, prompt: str, timeout: int = 60, num_predict: int = 1000,
                 temperature: float = None) -> str:
    """Low-level NVIDIA NIM call via its OpenAI-compatible chat completions
    endpoint. Raises NvidiaAPIError on any failure; never logs the API key.

    Checks the cost/quota safety guard first and refuses to make the request
    at all while NVIDIA is disabled (rate-limited, quota-exhausted, or an
    auth failure) — see verdictin60_core/provider_guard.py."""
    if provider_guard.is_provider_disabled("nvidia"):
        raise NvidiaAPIError(
            "NVIDIA NIM temporarily disabled by the cost/quota safety guard"
        )
    api_key = get_nvidia_api_key()
    if not api_key:
        raise NvidiaAPIError("No NVIDIA API key configured")
    payload_dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": num_predict,
        "stream": False,
    }
    if temperature is not None:
        payload_dict["temperature"] = temperature
    payload = json.dumps(payload_dict).encode()
    req = urllib.request.Request(
        f"{NVIDIA_API_BASE}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        # 401/403 = bad/missing access, 402 = payment required, 429 = rate/quota.
        # Report the status code (never the request/response body) to the
        # guard so it can disable NVIDIA per the configured cooldown rules.
        provider_guard.report_failure("nvidia", status_code=e.code)
        raise NvidiaAPIError(f"NVIDIA NIM HTTP {e.code}") from e
    except Exception as e:
        # Network errors/timeouts aren't billing-risk failures — classify by
        # message text (no key/headers ever included) but don't force a
        # disable unless it actually looks like quota/rate-limit/auth.
        provider_guard.report_failure("nvidia", str(e))
        raise NvidiaAPIError(f"NVIDIA NIM request failed: {e}") from e
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as e:
        raise NvidiaAPIError("NVIDIA NIM response missing expected content") from e
    provider_guard.report_success("nvidia")
    content = message.get("content") or ""
    if content:
        return content
    # Some NVIDIA NIM models emit a tool-call style response (arguments in
    # message["tool_calls"]) instead of plain content. Hand back the raw
    # tool_calls JSON so callers can still recover the object-like payload.
    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        try:
            return json.dumps({"tool_calls": tool_calls})
        except (TypeError, ValueError):
            pass
    return content


def nvidia_generate(prompt: str, task: str = "caption", timeout: int = 60,
                    num_predict: int = 1000) -> str:
    temperature = NVIDIA_LOW_TEMPERATURE if task in NVIDIA_LOW_TEMPERATURE_TASKS else None
    return _nvidia_call(get_nvidia_model(task), prompt, timeout, num_predict, temperature=temperature)


# Identify responses are a single JSON object with several list fields
# (aliases/victims/suspects/related_people/timeline). 400 tokens was too
# tight — real NVIDIA NIM responses were observed getting cut off mid-JSON
# (see issue #59), so the parser would receive a truncated, unbalanced
# object. Raised enough to fit the full (now field-capped, see
# _IDENTIFY_PROMPT_TEMPLATE) schema with headroom.
NVIDIA_IDENTIFY_MAX_TOKENS = 900


def nvidia_identify(prompt: str, timeout: int = 45) -> str:
    return _nvidia_call(get_nvidia_model("identify"), prompt, timeout, NVIDIA_IDENTIFY_MAX_TOKENS,
                        temperature=NVIDIA_LOW_TEMPERATURE)


# Per-task NVIDIA NIM timeout overrides. Tasks with no entry here keep the
# plain 60s default.
NVIDIA_TASK_TIMEOUTS = {}
NVIDIA_DEFAULT_TIMEOUT = 60


def get_nvidia_timeout(task: str) -> int:
    return NVIDIA_TASK_TIMEOUTS.get(task, NVIDIA_DEFAULT_TIMEOUT)


def ai_generate(prompt: str, timeout: int = None, task: str = "caption",
                num_predict: int = 1000) -> str:
    """Provider-aware caption/verify generation.

    - "Local only" (default): identical to calling ollama_generate directly.
    - "Cloud fallback": try Ollama first; only on Ollama failure/timeout, try
      NVIDIA NIM if a key is configured. If NVIDIA also fails, re-raise the
      original Ollama exception so existing callers' except-blocks (timeout
      detection, fallback captions, etc.) keep working unchanged.
    - "Cloud only": use NVIDIA NIM; if it errors (including quota/rate-limit/
      payment/access/timeout), fall back to Ollama *for this one request*
      rather than crash — the provider mode setting itself is not changed,
      so the next call still tries NVIDIA first (unless the cost/quota guard
      has since disabled it, e.g. after a timeout — see provider_guard.py).
    """
    mode = get_ai_provider_mode()
    nvidia_timeout = timeout or get_nvidia_timeout(task)
    if mode == "Cloud only" and nvidia_available():
        try:
            return nvidia_generate(prompt, task=task, timeout=nvidia_timeout, num_predict=num_predict)
        except Exception as e:
            print(f"[AI] NVIDIA NIM call failed in Cloud-only mode ({e}); using local Ollama as a "
                  "one-off fallback for this request only — Cloud-only mode itself is unchanged")
            return ollama_generate(prompt, timeout=timeout, task=task, num_predict=num_predict)
    try:
        return ollama_generate(prompt, timeout=timeout, task=task, num_predict=num_predict)
    except Exception as e:
        if mode == "Cloud fallback" and nvidia_available():
            print(f"[AI] Ollama failed for task={task} ({e}); trying NVIDIA NIM fallback")
            try:
                return nvidia_generate(prompt, task=task, timeout=nvidia_timeout, num_predict=num_predict)
            except Exception as nvidia_exc:
                print(f"[AI] NVIDIA NIM fallback also failed: {nvidia_exc}")
        raise


def ai_identify(prompt: str, timeout: int = None) -> str:
    """Provider-aware case-identification call — same fallback rules as ai_generate."""
    mode = get_ai_provider_mode()
    if mode == "Cloud only" and nvidia_available():
        try:
            return nvidia_identify(prompt, timeout=timeout or 45)
        except Exception as e:
            print(f"[AI] NVIDIA NIM identify failed in Cloud-only mode ({e}); using local Ollama as a "
                  "one-off fallback for this request only — Cloud-only mode itself is unchanged")
            return ollama_identify(prompt, timeout=timeout)
    try:
        return ollama_identify(prompt, timeout=timeout)
    except Exception as e:
        if mode == "Cloud fallback" and nvidia_available():
            print(f"[AI] Ollama identify failed ({e}); trying NVIDIA NIM fallback")
            try:
                return nvidia_identify(prompt, timeout=timeout or 45)
            except Exception as nvidia_exc:
                print(f"[AI] NVIDIA NIM identify fallback also failed: {nvidia_exc}")
        raise

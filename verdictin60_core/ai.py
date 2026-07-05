"""Ollama/AI helpers, moved from app.py (Phase 4 refactor, no behavior change).

- AI_SPEED_MODES: model choices per speed mode / task.
- get_ai_speed_mode / get_ai_model / get_ai_timeout: resolve the configured
  speed mode into a model name or timeout for a given task.
- is_timeout_error: classify an exception as an AI request timeout.
- check_ollama / check_ollama_model_installed: Ollama availability checks.
- _ollama_call / ollama_generate / ollama_identify: low-level and
  task-specific Ollama request calls.
"""
import json
import re

from verdictin60_core.settings import load_settings

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

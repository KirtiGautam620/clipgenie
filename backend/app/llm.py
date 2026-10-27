"""Talk to the local Ollama server (no cloud, no API keys)."""
import json
import time
import urllib.request

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "qwen2.5:3b"
RETRIES = 4        # tries per question when the connection drops
RETRY_WAIT = 4     # seconds between tries


class LLMError(Exception):
    pass


def ask_json(system: str, user: str, timeout: int = 300) -> dict:
    """Send one question to the model and return its answer parsed as JSON."""
    body = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "format": "json",          # forces valid JSON output
        "stream": False,
        "keep_alive": "10s",       # stays loaded between our quick calls, then frees RAM
        "options": {"temperature": 0, "seed": 7, "num_ctx": 8192},  # same input -> same answer
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content = json.load(resp)["message"]["content"]
            return json.loads(content)
        except OSError as e:  # connection refused/closed, timeout, ...
            if _is_restarting(e) and attempt < RETRIES - 1:
                time.sleep(RETRY_WAIT)   # Ollama restarts briefly now and then (e.g. updates)
                continue
            raise LLMError(f"Could not reach Ollama ({e}). Is `ollama serve` running?") from e
        except (KeyError, json.JSONDecodeError) as e:
            raise LLMError(f"Ollama gave an unusable answer: {e}") from e


def _is_restarting(error: OSError) -> bool:
    """A refused or dropped connection is worth retrying. A timeout (slow model) is not."""
    reason = getattr(error, "reason", error)
    return isinstance(reason, ConnectionError) and not isinstance(reason, TimeoutError)


def unload() -> None:
    """Ask Ollama to drop the model from memory now (FFmpeg needs the room). Never fails."""
    body = json.dumps({"model": OLLAMA_MODEL, "keep_alive": 0}).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=5).close()
    except Exception:
        pass

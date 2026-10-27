import http.client
import io
import json
import urllib.error

import pytest

from app import llm, main


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def ok(answer):
    return Reply(json.dumps({"message": {"content": json.dumps(answer)}}).encode())


def test_retries_when_ollama_restarts(monkeypatch):
    calls = []

    def flaky(req, timeout):
        calls.append(1)
        if len(calls) < 3:
            raise http.client.RemoteDisconnected("Remote end closed connection without response")
        return ok({"clips": []})
    monkeypatch.setattr(llm.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(llm, "RETRY_WAIT", 0)
    assert llm.ask_json("s", "u") == {"clips": []} and len(calls) == 3


def test_gives_up_after_the_last_retry(monkeypatch):
    monkeypatch.setattr(llm.urllib.request, "urlopen",
                        lambda req, timeout: (_ for _ in ()).throw(ConnectionRefusedError("no")))
    monkeypatch.setattr(llm, "RETRY_WAIT", 0)
    with pytest.raises(llm.LLMError):
        llm.ask_json("s", "u")


def test_timeouts_are_not_retried(monkeypatch):
    calls = []

    def slow(req, timeout):
        calls.append(1)
        raise urllib.error.URLError(TimeoutError("timed out"))
    monkeypatch.setattr(llm.urllib.request, "urlopen", slow)
    monkeypatch.setattr(llm, "RETRY_WAIT", 0)
    with pytest.raises(llm.LLMError):
        llm.ask_json("s", "u")
    assert len(calls) == 1


def test_health_reports_ollama_not_running(monkeypatch):
    def refuse(*a, **k):
        raise ConnectionRefusedError("down")
    monkeypatch.setattr(main.urllib.request, "urlopen", refuse)
    assert main._ollama_state() == {"running": False, "model_installed": False,
                                    "model": llm.OLLAMA_MODEL}


def test_health_reports_a_missing_model(monkeypatch):
    monkeypatch.setattr(main.urllib.request, "urlopen",
                        lambda *a, **k: Reply(json.dumps({"models": [{"name": "other:1b"}]}).encode()))
    state = main._ollama_state()
    assert state["running"] and not state["model_installed"]

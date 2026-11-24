import json

import httpx
import pytest

from app.integrations.ollama_provider import OllamaProvider


def test_ollama_uses_local_structured_chat_without_credentials():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"done": True, "message": {"content": json.dumps({"intent": "hours", "response": "No tengo horarios confirmados."})}})

    provider = OllamaProvider("test-model", transport=httpx.MockTransport(handler))
    assert provider("Cuando cierran?")["intent"] == "hours"
    request = requests[0]
    payload = json.loads(request.content)
    assert str(request.url) == "http://127.0.0.1:11434/api/chat"
    assert "authorization" not in request.headers
    assert payload["stream"] is False
    assert payload["messages"][-1]["content"] == "Cuando cierran?"
    assert payload["format"]["required"] == ["intent", "response"]


def test_ollama_failure_falls_back_to_rules():
    from app.domain.ai_engine import AIEngine
    from app.domain.engine import RuleEngine

    provider = OllamaProvider("test-model", transport=httpx.MockTransport(lambda _: httpx.Response(500)))
    assert AIEngine(RuleEngine(), provider).respond("Hola") == RuleEngine().respond("Hola")


def test_ollama_incomplete_reply_is_rejected():
    provider = OllamaProvider("test-model", transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"done": False})))
    with pytest.raises(ValueError):
        provider("Hola")


def test_ollama_malformed_output_falls_back():
    from app.domain.ai_engine import AIEngine
    from app.domain.engine import RuleEngine

    provider = OllamaProvider("test-model", transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"done": True, "message": {"content": "no json"}})))
    assert AIEngine(RuleEngine(), provider).respond("Hola") == RuleEngine().respond("Hola")


def test_ollama_is_not_called_for_handoff():
    from app.domain.ai_engine import AIEngine
    from app.domain.engine import RuleEngine

    def handler(_):
        raise AssertionError("No se debe llamar al modelo para derivar")

    reply = AIEngine(RuleEngine(), OllamaProvider("test-model", transport=httpx.MockTransport(handler))).respond("Quiero hablar con una persona")
    assert reply.handoff


def test_factory_selects_local_ollama_without_openai_key(monkeypatch, tmp_path):
    from app.domain.ai_engine import AIEngine
    from app.main import make_chat_engine

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CHATBOT_AI_ENABLED", "true")
    monkeypatch.setenv("CHATBOT_AI_PROVIDER", "ollama")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    engine = make_chat_engine()
    assert isinstance(engine, AIEngine)
    assert isinstance(engine.ask, OllamaProvider)

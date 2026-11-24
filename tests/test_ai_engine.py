from app.domain.ai_engine import AIEngine
from app.domain.engine import RuleEngine
import pytest


def test_ai_responds_to_a_paraphrased_business_question():
    calls = []

    def ask(message):
        calls.append(message)
        return {"intent": "hours", "response": "¡Hola! Aún no tengo los horarios confirmados. ¿Querés hablar con una persona?"}

    reply = AIEngine(RuleEngine(), ask).respond("¿A qué hora cierran?")
    assert reply.intent == "hours"
    assert "horarios confirmados" in reply.text
    assert calls == ["¿A qué hora cierran?"]


def test_provider_failure_falls_back_to_local_rules():
    def ask(_):
        raise TimeoutError()

    assert AIEngine(RuleEngine(), ask).respond("¿Cuánto cuesta?") == RuleEngine().respond("¿Cuánto cuesta?")


@pytest.mark.parametrize("message", ["Quiero hablar con una persona", "Quiero reservar"])
def test_actions_are_determined_locally_without_asking_ai(message):
    def ask(_):
        raise AssertionError("No debe consultar IA")

    assert AIEngine(RuleEngine(), ask).respond(message) == RuleEngine().respond(message)


@pytest.mark.parametrize("result", [None, {}, {"intent": "human", "response": "OK"}, {"intent": "hours", "response": ""}])
def test_invalid_ai_output_uses_local_answer(result):
    fallback = RuleEngine().respond("Hola")
    assert AIEngine(RuleEngine(), lambda _: result).respond("Hola") == fallback


def test_ai_is_opt_in_and_requires_key(monkeypatch, tmp_path):
    from app.main import make_chat_engine
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CHATBOT_AI_ENABLED", raising=False)
    assert isinstance(make_chat_engine(), RuleEngine)
    monkeypatch.setenv("CHATBOT_AI_ENABLED", "true")
    assert isinstance(make_chat_engine(), RuleEngine)


def test_ai_can_be_enabled_with_key(monkeypatch):
    from app.main import make_chat_engine
    monkeypatch.setenv("CHATBOT_AI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    assert isinstance(make_chat_engine(), AIEngine)

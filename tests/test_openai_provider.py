import json
import httpx
import pytest

from app.integrations.openai_provider import OpenAIProvider


def test_provider_sends_only_current_message_and_parses_response():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({"intent": "hours", "response": "Aún no tengo horarios confirmados."})}]}]})

    provider = OpenAIProvider("test-key", "test-model", transport=httpx.MockTransport(handler))
    assert provider("¿A qué hora cierran?")["intent"] == "hours"
    payload = json.loads(requests[0].content)
    assert payload["store"] is False
    assert payload["input"][-1]["content"] == "¿A qué hora cierran?"
    assert requests[0].headers["authorization"] == "Bearer test-key"


def test_provider_rejects_failed_response():
    provider = OpenAIProvider("test-key", "test-model", transport=httpx.MockTransport(lambda _: httpx.Response(500)))
    with pytest.raises(httpx.HTTPStatusError):
        provider("hola")

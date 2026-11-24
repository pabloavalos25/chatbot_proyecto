"""Ollama adapter bound to this machine; no API keys or customer IDs are sent."""
import json

import httpx

from app.domain.ai_engine import INTENTS
from app.integrations.openai_provider import INSTRUCTIONS


class OllamaProvider:
    def __init__(self, model: str, transport=None):
        self.model = model
        self.transport = transport

    def __call__(self, message: str) -> dict:
        schema = {
            "type": "object",
            "properties": {
                "intent": {"type": "string", "enum": sorted(INTENTS)},
                "response": {"type": "string"},
            },
            "required": ["intent", "response"],
            "additionalProperties": False,
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": INSTRUCTIONS}, {"role": "user", "content": message}],
            "stream": False,
            "format": schema,
            "options": {"temperature": 0, "num_predict": 350},
        }
        timeout = httpx.Timeout(120.0, connect=2.0)
        with httpx.Client(timeout=timeout, transport=self.transport, trust_env=False) as client:
            response = client.post("http://127.0.0.1:11434/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        if data.get("done") is not True or data.get("done_reason", "stop") != "stop":
            raise ValueError("Incomplete AI response")
        return json.loads(data["message"]["content"])

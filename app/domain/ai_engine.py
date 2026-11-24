"""Optional AI responses with deterministic fallback and action control."""
from app.domain.engine import Reply, RuleEngine

INTENTS = {"hours", "location", "prices", "availability", "payment", "vehicles", "security", "services", "greeting", "thanks", "goodbye", "unknown"}


class AIEngine:
    def __init__(self, fallback: RuleEngine, ask):
        self.fallback = fallback
        self.ask = ask

    def respond(self, message: str) -> Reply:
        local = self.fallback.respond(message)
        if local.handoff or local.commercial:
            return local
        try:
            result = self.ask(message)
            intent, text = result["intent"], result["response"]
            if intent not in INTENTS or not isinstance(text, str) or not text.strip() or len(text) > 1500:
                return local
            return Reply(intent, text.strip())
        except Exception:
            return local

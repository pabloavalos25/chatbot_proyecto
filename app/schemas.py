from pydantic import BaseModel, Field, field_validator

from app.models import ConversationState


class ChatRequest(BaseModel):
    customer_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("customer_id", "message")
    @classmethod
    def strip_nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("No puede estar vacío")
        return value


class ChatResponse(BaseModel):
    conversation_id: int
    state: ConversationState
    response: str | None
    intent: str | None


class OperatorMessage(BaseModel):
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def strip_nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("No puede estar vacío")
        return value


class StateUpdate(BaseModel):
    state: ConversationState


class CloseChatRequest(BaseModel):
    rating: int = Field(ge=1, le=5, strict=True)
    reason: str | None = Field(default=None, max_length=2000)

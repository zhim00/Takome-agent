from pydantic import BaseModel, Field, field_validator


class ChatStreamRequest(BaseModel):
    user_id: str = Field(min_length=1)
    conversation_id: str | None = None
    message: str = Field(min_length=1)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value


def build_thread_id(user_id: str, conversation_id: str | None) -> str:
    # Empty conversation_id falls back to "default"; this means multiple tabs
    # for the same user can share context until the frontend sends stable IDs.
    normalized_conversation_id = (conversation_id or "").strip() or "default"
    return f"{user_id}:{normalized_conversation_id}"

import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.sse import EventSourceResponse, ServerSentEvent, format_sse_event

from app.agent import AssistantService, get_assistant_service
from app.schemas import ChatStreamRequest
from app.settings import Settings, get_settings


app = FastAPI(title="Takome 阅读助手 Agent")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def verify_internal_token(
    x_ai_internal_token: Annotated[
        str | None,
        Header(alias="X-AI-Internal-Token"),
    ] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if (
        not settings.internal_token
        or x_ai_internal_token != settings.internal_token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid internal token",
        )


@app.post("/v1/assistant/chat/stream")
async def chat_stream(
    payload: ChatStreamRequest,
    _: None = Depends(verify_internal_token),
    settings: Settings = Depends(get_settings),
    assistant_service: AssistantService = Depends(get_assistant_service),
) -> EventSourceResponse:
    if len(payload.message) > settings.max_message_length:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="message is too long",
        )

    return EventSourceResponse(
        encode_sse_events(assistant_service.stream_chat(payload)),
        media_type="text/event-stream",
    )


async def encode_sse_events(
    events: AsyncIterator[ServerSentEvent],
) -> AsyncIterator[bytes]:
    async for event in events:
        data_str = event.raw_data
        if data_str is None and event.data is not None:
            data_str = json.dumps(
                jsonable_encoder(event.data),
                ensure_ascii=False,
                separators=(",", ":"),
            )
        yield format_sse_event(
            data_str=data_str,
            event=event.event,
            id=event.id,
            retry=event.retry,
            comment=event.comment,
        )

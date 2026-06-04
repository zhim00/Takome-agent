from collections.abc import AsyncIterator

from fastapi.sse import ServerSentEvent
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent import AssistantService, trim_messages
from main import app, get_assistant_service, get_settings
from app.schemas import ChatStreamRequest
from app.settings import Settings


class FakeAssistantService:
    async def stream_chat(
        self,
        request: ChatStreamRequest,
    ) -> AsyncIterator[ServerSentEvent]:
        yield ServerSentEvent(event="token", data={"text": "你好"})
        yield ServerSentEvent(event="done", data={})


def override_settings(**kwargs) -> Settings:
    defaults = {
        "internal_token": "internal-secret",
        "deepseek_api_key": "deepseek-secret",
        "max_message_length": 20,
        "thread_ttl_seconds": 1800,
    }
    defaults.update(kwargs)
    return Settings(**defaults)


def client_with_overrides(settings: Settings | None = None) -> TestClient:
    app.dependency_overrides[get_settings] = lambda: settings or override_settings()
    app.dependency_overrides[get_assistant_service] = lambda: FakeAssistantService()
    return TestClient(app)


def clear_overrides() -> None:
    app.dependency_overrides.clear()


def test_health_endpoint() -> None:
    client = client_with_overrides()
    try:
        response = client.get("/health")
    finally:
        clear_overrides()

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_invalid_internal_token_returns_401() -> None:
    client = client_with_overrides()
    try:
        response = client.post(
            "/v1/assistant/chat/stream",
            headers={"X-AI-Internal-Token": "wrong"},
            json={"user_id": "u1", "conversation_id": "c1", "message": "hi"},
        )
    finally:
        clear_overrides()

    assert response.status_code == 401


def test_message_too_long_returns_400() -> None:
    client = client_with_overrides(override_settings(max_message_length=3))
    try:
        response = client.post(
            "/v1/assistant/chat/stream",
            headers={"X-AI-Internal-Token": "internal-secret"},
            json={"user_id": "u1", "conversation_id": "c1", "message": "hello"},
        )
    finally:
        clear_overrides()

    assert response.status_code == 400


def test_sse_outputs_token_and_done() -> None:
    client = client_with_overrides()
    try:
        with client.stream(
            "POST",
            "/v1/assistant/chat/stream",
            headers={"X-AI-Internal-Token": "internal-secret"},
            json={"user_id": "u1", "conversation_id": "c1", "message": "hi"},
        ) as response:
            body = response.read().decode("utf-8")
    finally:
        clear_overrides()

    assert response.status_code == 200
    assert "event: token" in body
    assert 'data: {"text":"你好"}' in body
    assert "event: done" in body


async def test_assistant_service_sse_mapping_uses_thread_id() -> None:
    seen = {}

    class FakeAgent:
        def stream_events(self, input_data, *, version, config):
            seen["input"] = input_data
            seen["version"] = version
            seen["thread_id"] = config["configurable"]["thread_id"]
            return [
                {"event": "on_chat_model_stream", "data": {"chunk": {"content": "好"}}}
            ]

    service = AssistantService(
        settings=override_settings(thread_ttl_seconds=0),
        agent_runnable=FakeAgent(),
    )
    request = ChatStreamRequest(user_id="u1", conversation_id="c1", message="hi")

    events = [event async for event in service.stream_chat(request)]

    assert seen["version"] == "v3"
    assert seen["thread_id"] == "u1:c1"
    assert seen["input"] == {"messages": [{"role": "user", "content": "hi"}]}
    assert [event.event for event in events] == ["token", "done"]
    assert events[0].data == {"text": "好"}


def test_trim_messages_keeps_valid_tool_message_boundaries() -> None:
    messages = []
    for index in range(6):
        tool_call_id = f"call_{index}"
        messages.extend(
            [
                HumanMessage(content=f"用户第 {index} 轮"),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "search_books",
                            "args": {"keyword": "测试"},
                            "id": tool_call_id,
                        }
                    ],
                ),
                ToolMessage(content="{}", tool_call_id=tool_call_id),
                AIMessage(content=f"第 {index} 轮回答"),
            ]
        )
    messages.append(HumanMessage(content="继续推荐"))

    result = trim_messages.before_model({"messages": messages}, runtime=None)

    assert result is not None
    trimmed_messages = result["messages"][1:]
    assert trimmed_messages[0].type == "human"
    assert trimmed_messages[-1].content == "继续推荐"

    seen_tool_call_ids = set()
    for message in trimmed_messages:
        for tool_call in getattr(message, "tool_calls", []) or []:
            seen_tool_call_ids.add(tool_call["id"])
        if message.type == "tool":
            assert message.tool_call_id in seen_tool_call_ids

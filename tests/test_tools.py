from typing import Any

import pytest

from app import tools


@pytest.mark.asyncio
async def test_bookshelf_tool_schema_does_not_expose_user_id(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_spring_get(path: str, params: dict[str, Any] | None = None):
        captured["path"] = path
        captured["params"] = params
        return {"success": True, "books": []}

    monkeypatch.setattr(tools, "_spring_get", fake_spring_get)

    input_schema = tools.get_bookshelf.get_input_schema()
    assert "user_id" not in input_schema.model_fields
    assert "userId" not in input_schema.model_fields

    token = tools.set_current_user_id("u1")
    try:
        result = await tools.get_bookshelf.ainvoke({"page_num": 1, "page_size": 99})
    finally:
        tools.reset_current_user_id(token)

    assert result == {"success": True, "books": []}
    assert captured["path"] == "/api/internal/ai/tools/bookshelf"
    assert captured["params"]["userId"] == "u1"
    assert captured["params"]["pageSize"] == 10


def test_bookshelf_tool_supports_sync_invocation(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_spring_get(path: str, params: dict[str, Any] | None = None):
        captured["path"] = path
        captured["params"] = params
        return {"success": True, "books": []}

    monkeypatch.setattr(tools, "_spring_get", fake_spring_get)

    token = tools.set_current_user_id("u1")
    try:
        result = tools.get_bookshelf.invoke({"page_num": 1, "page_size": 99})
    finally:
        tools.reset_current_user_id(token)

    assert result == {"success": True, "books": []}
    assert captured["path"] == "/api/internal/ai/tools/bookshelf"
    assert captured["params"]["userId"] == "u1"
    assert captured["params"]["pageSize"] == 10


def test_sanitize_response_limits_books_and_descriptions() -> None:
    payload = {
        "code": 0,
        "data": {
            "list": [
                {
                    "bookId": i,
                    "bookName": f"书{i}",
                    "bookDesc": "很长" * 200,
                    "chapterContent": "不能返回",
                }
                for i in range(12)
            ],
            "pageSize": 50,
            "total": 12,
        },
    }

    result = tools._sanitize_response(payload)

    assert len(result["books"]) == 10
    assert len(result["books"][0]["bookDesc"]) == 200
    assert "chapterContent" not in result["books"][0]
    assert result["pageSize"] == 10


def test_sanitize_response_accepts_takome_success_code() -> None:
    payload = {
        "code": "00000",
        "message": "一切 ok",
        "ok": True,
        "data": [{"bookId": "1", "bookName": "测试小说"}],
    }

    result = tools._sanitize_response(payload)

    assert result == {
        "books": [{"bookId": "1", "bookName": "测试小说"}],
        "success": True,
    }


def test_sanitize_response_hides_backend_failure_message() -> None:
    payload = {
        "code": "50000",
        "message": "SQL timeout on /api/internal/ai/tools/bookshelf",
        "data": None,
    }

    result = tools._sanitize_response(payload)

    assert result == {"success": False, "message": "暂时无法获取站内数据"}

import asyncio
from contextvars import ContextVar, Token
from typing import Any, Annotated

import httpx
from langchain_core.tools import StructuredTool

from app.settings import get_settings


_current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)

BOOK_FIELDS = (
    "bookId",
    "bookName",
    "authorName",
    "categoryName",
    "picUrl",
    "bookDesc",
    "bookStatus",
    "wordCount",
    "visitCount",
    "commentCount",
    "lastChapterId",
    "lastChapterName",
    "updateTime",
    "readingChapterId",
    "readingChapterNum",
    "readingChapterName",
    "chapterTotal",
    "readingUpdateTime",
    "source",
)
PAGE_META_FIELDS = ("pageNum", "pageSize", "total", "pages", "hasNext")
MAX_BOOKS = 10
MAX_DESC_LENGTH = 200


def set_current_user_id(user_id: str) -> Token[str | None]:
    return _current_user_id.set(user_id)


def reset_current_user_id(token: Token[str | None]) -> None:
    _current_user_id.reset(token)


def get_current_user_id() -> str:
    user_id = _current_user_id.get()
    if not user_id:
        raise RuntimeError("current user id is not available")
    return user_id


def get_agent_tools() -> list[Any]:
    return [
        get_bookshelf,
        search_books,
        get_book_detail,
        recommend_books,
        get_read_history,
    ]


def _limit_page_size(page_size: int | None) -> int:
    if page_size is None:
        return MAX_BOOKS
    return max(1, min(int(page_size), MAX_BOOKS))


def _positive_int(value: int | None, default: int) -> int:
    if value is None:
        return default
    return max(1, int(value))


def _without_none(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value is not None}


async def _spring_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = get_settings()
    headers = {"X-AI-Internal-Token": settings.internal_token}
    async with httpx.AsyncClient(
        base_url=settings.spring_base_url,
        timeout=15.0,
    ) as client:
        response = await client.get(path, params=params, headers=headers)
        response.raise_for_status()
        payload = response.json()
    return _sanitize_response(payload)


def _run_async_tool(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("Synchronous tool execution must run outside the FastAPI event loop")


def _extract_data(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def _sanitize_response(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        code = payload.get("code")
        success = payload.get("ok") is True or code in (
            None,
            0,
            200,
            "0",
            "00000",
            "200",
            "SUCCESS",
        )
        if not success:
            return {
                "success": False,
                "message": "暂时无法获取站内数据",
            }

    data = _extract_data(payload)
    sanitized = _sanitize_data(data)
    if not sanitized:
        return {"success": True, "books": []}
    sanitized.setdefault("success", True)
    return sanitized


def _sanitize_data(data: Any) -> dict[str, Any]:
    if data is None:
        return {"books": []}

    if isinstance(data, list):
        return {"books": [_sanitize_book(item) for item in data[:MAX_BOOKS] if isinstance(item, dict)]}

    if not isinstance(data, dict):
        return {"result": str(data)[:MAX_DESC_LENGTH]}

    list_key = next(
        (
            key
            for key in (
                "list",
                "records",
                "rows",
                "content",
                "items",
                "books",
                "bookList",
                "relatedBooks",
                "recommendBooks",
            )
            if isinstance(data.get(key), list)
        ),
        None,
    )
    if list_key:
        result = {
            "books": [
                _sanitize_book(item)
                for item in data[list_key][:MAX_BOOKS]
                if isinstance(item, dict)
            ],
        }
        result.update({key: data[key] for key in PAGE_META_FIELDS if key in data})
        result["pageSize"] = min(int(result.get("pageSize", MAX_BOOKS)), MAX_BOOKS)
        return result

    book = _sanitize_book(data)
    if book:
        return {"book": book}

    return {"books": []}


def _sanitize_book(book: dict[str, Any]) -> dict[str, Any]:
    sanitized = {key: book[key] for key in BOOK_FIELDS if key in book and book[key] is not None}
    if "bookDesc" in sanitized:
        sanitized["bookDesc"] = str(sanitized["bookDesc"])[:MAX_DESC_LENGTH]
    return sanitized


async def _get_bookshelf_async(
    page_num: Annotated[int, "页码，从 1 开始"] = 1,
    page_size: Annotated[int, "每页数量，最多 10"] = 10,
) -> dict[str, Any]:
    """查询当前用户书架中的小说列表。"""
    params = {
        "userId": get_current_user_id(),
        "pageNum": _positive_int(page_num, 1),
        "pageSize": _limit_page_size(page_size),
    }
    return await _spring_get("/api/internal/ai/tools/bookshelf", params=params)


def _get_bookshelf_sync(
    page_num: Annotated[int, "页码，从 1 开始"] = 1,
    page_size: Annotated[int, "每页数量，最多 10"] = 10,
) -> dict[str, Any]:
    """查询当前用户书架中的小说列表。"""
    return _run_async_tool(_get_bookshelf_async(page_num=page_num, page_size=page_size))


async def _search_books_async(
    keyword: Annotated[str, "搜索关键词"],
    page_num: Annotated[int, "页码，从 1 开始"] = 1,
    page_size: Annotated[int, "每页数量，最多 10"] = 10,
    category_id: Annotated[int | None, "分类 ID，可不填"] = None,
    book_status: Annotated[str | None, "书籍状态筛选，可不填"] = None,
) -> dict[str, Any]:
    """按关键词搜索站内小说，可按分类或状态筛选。"""
    params = _without_none(
        {
            "keyword": keyword,
            "pageNum": _positive_int(page_num, 1),
            "pageSize": _limit_page_size(page_size),
            "categoryId": category_id,
            "bookStatus": book_status,
        }
    )
    return await _spring_get("/api/internal/ai/tools/search/books", params=params)


def _search_books_sync(
    keyword: Annotated[str, "搜索关键词"],
    page_num: Annotated[int, "页码，从 1 开始"] = 1,
    page_size: Annotated[int, "每页数量，最多 10"] = 10,
    category_id: Annotated[int | None, "分类 ID，可不填"] = None,
    book_status: Annotated[str | None, "书籍状态筛选，可不填"] = None,
) -> dict[str, Any]:
    """按关键词搜索站内小说，可按分类或状态筛选。"""
    return _run_async_tool(
        _search_books_async(
            keyword=keyword,
            page_num=page_num,
            page_size=page_size,
            category_id=category_id,
            book_status=book_status,
        )
    )


async def _get_book_detail_async(
    book_id: Annotated[str, "书籍 ID"],
) -> dict[str, Any]:
    """查询一本小说的站内详情摘要，不返回章节正文。"""
    return await _spring_get(f"/api/internal/ai/tools/books/{book_id}")


def _get_book_detail_sync(
    book_id: Annotated[str, "书籍 ID"],
) -> dict[str, Any]:
    """查询一本小说的站内详情摘要，不返回章节正文。"""
    return _run_async_tool(_get_book_detail_async(book_id=book_id))


async def _recommend_books_async(
    book_id: Annotated[str | None, "参考书籍 ID，可不填"] = None,
    category_id: Annotated[int | None, "分类 ID，可不填"] = None,
    page_size: Annotated[int, "推荐数量，最多 10"] = 6,
) -> dict[str, Any]:
    """基于当前用户、参考书籍或分类推荐小说。"""
    params = _without_none(
        {
            "userId": get_current_user_id(),
            "bookId": book_id,
            "categoryId": category_id,
            "pageSize": _limit_page_size(page_size),
        }
    )
    return await _spring_get("/api/internal/ai/tools/recommend", params=params)


def _recommend_books_sync(
    book_id: Annotated[str | None, "参考书籍 ID，可不填"] = None,
    category_id: Annotated[int | None, "分类 ID，可不填"] = None,
    page_size: Annotated[int, "推荐数量，最多 10"] = 6,
) -> dict[str, Any]:
    """基于当前用户、参考书籍或分类推荐小说。"""
    return _run_async_tool(
        _recommend_books_async(
            book_id=book_id,
            category_id=category_id,
            page_size=page_size,
        )
    )


async def _get_read_history_async(
    page_num: Annotated[int, "页码，从 1 开始"] = 1,
    page_size: Annotated[int, "每页数量，最多 10"] = 10,
    within_days: Annotated[int | None, "最近多少天内的阅读历史，可不填"] = None,
) -> dict[str, Any]:
    """查询当前用户的小说阅读历史摘要。"""
    params = _without_none(
        {
            "userId": get_current_user_id(),
            "pageNum": _positive_int(page_num, 1),
            "pageSize": _limit_page_size(page_size),
            "withinDays": within_days,
        }
    )
    return await _spring_get("/api/internal/ai/tools/read-history", params=params)


def _get_read_history_sync(
    page_num: Annotated[int, "页码，从 1 开始"] = 1,
    page_size: Annotated[int, "每页数量，最多 10"] = 10,
    within_days: Annotated[int | None, "最近多少天内的阅读历史，可不填"] = None,
) -> dict[str, Any]:
    """查询当前用户的小说阅读历史摘要。"""
    return _run_async_tool(
        _get_read_history_async(
            page_num=page_num,
            page_size=page_size,
            within_days=within_days,
        )
    )


get_bookshelf = StructuredTool.from_function(
    func=_get_bookshelf_sync,
    coroutine=_get_bookshelf_async,
    name="get_bookshelf",
    description="查询当前用户书架中的小说列表。",
)

search_books = StructuredTool.from_function(
    func=_search_books_sync,
    coroutine=_search_books_async,
    name="search_books",
    description="按关键词搜索站内小说，可按分类或状态筛选。",
)

get_book_detail = StructuredTool.from_function(
    func=_get_book_detail_sync,
    coroutine=_get_book_detail_async,
    name="get_book_detail",
    description="查询一本小说的站内详情摘要，不返回章节正文。",
)

recommend_books = StructuredTool.from_function(
    func=_recommend_books_sync,
    coroutine=_recommend_books_async,
    name="recommend_books",
    description="基于当前用户、参考书籍或分类推荐小说。",
)

get_read_history = StructuredTool.from_function(
    func=_get_read_history_sync,
    coroutine=_get_read_history_async,
    name="get_read_history",
    description="查询当前用户的小说阅读历史摘要。",
)

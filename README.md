# Takome Agent

Takome Agent 是 Takome 小说阅读平台的 AI 阅读助手服务。它是一个独立的 Python FastAPI 服务，由 Spring Boot 后端在用户已登录的上下文中调用，负责连接 DeepSeek 模型，并通过 SSE 返回流式对话结果。

## 功能

- 提供 AI 阅读助手流式对话接口
- 使用 LangChain/LangGraph 组织模型调用和会话上下文
- 通过 DeepSeek API 生成回答
- 支持回查 Takome 后端内部工具接口
- 支持查询书架、搜索小说、查看小说摘要、推荐小说和查询阅读历史
- 使用 `X-AI-Internal-Token` 与 Spring Boot 后端做内部鉴权

## 技术栈

- Python `>=3.13`
- FastAPI
- LangChain
- LangGraph
- DeepSeek
- httpx
- pydantic-settings
- uv
- pytest

## 项目结构

```text
Takome-agent/
├─ app/
│  ├─ agent.py       # AI assistant 服务和流式事件编排
│  ├─ schemas.py     # 请求 schema 和 thread_id 构造
│  ├─ settings.py    # 环境变量配置
│  └─ tools.py       # 调用 Spring Boot 内部工具 API
├─ tests/            # 测试
├─ main.py           # FastAPI 入口
├─ pyproject.toml
├─ uv.lock
└─ Dockerfile
```

## 环境要求

- Python `>=3.13`
- uv
- 可访问的 Takome 后端服务，默认 `http://localhost:8888`
- DeepSeek API Key

## 配置

复制环境变量示例：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`：

```env
DEEPSEEK_API_KEY=your-deepseek-key
INTERNAL_TOKEN=replace-with-shared-internal-token

DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
SPRING_BASE_URL=http://localhost:8888
THREAD_TTL_SECONDS=1800
MAX_MESSAGE_LENGTH=2000
DISABLE_DEEPSEEK_THINKING=true
```

`INTERNAL_TOKEN` 必须与 `Takome-backend` 中的 `INTERNAL_TOKEN` 一致。该值用于：

- Spring Boot 调用 agent 时的入站鉴权
- agent 回查 Spring Boot 内部 AI 工具接口时携带 `X-AI-Internal-Token`

不要使用 `deepseek-chat` 或 `deepseek-reasoner`。当前默认模型是 `deepseek-v4-flash`，并通过 `DISABLE_DEEPSEEK_THINKING=true` 关闭思考模式。

## 本地运行

```powershell
uv sync --dev
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

健康检查：

```text
GET http://localhost:8000/health
```

返回：

```json
{"status":"ok"}
```

## API

### `POST /v1/assistant/chat/stream`

Header：

```text
X-AI-Internal-Token: <INTERNAL_TOKEN>
```

Body：

```json
{
  "user_id": "123",
  "conversation_id": "frontend-generated-id",
  "message": "帮我推荐几本最近读过的同类小说"
}
```

SSE 事件：

```text
event: token
data: {"text":"..."}

event: tool_start
data: {"name":"search_books"}

event: tool_end
data: {"name":"search_books"}

event: error
data: {"message":"..."}

event: done
data: {}
```

`thread_id` 使用 `user_id:conversation_id`。如果 `conversation_id` 为空，会回退为 `default`，同一用户的多个标签页可能共享上下文。

## 工具边界

Agent 工具只访问 Spring Boot 内部 AI 工具 API：

```text
GET /api/internal/ai/tools/bookshelf
GET /api/internal/ai/tools/search/books
GET /api/internal/ai/tools/books/{bookId}
GET /api/internal/ai/tools/recommend
GET /api/internal/ai/tools/read-history
```

工具 schema 不包含 `user_id`，而是从当前 FastAPI 请求上下文读取，并自动拼入 Spring Boot 请求。工具输出会裁剪书籍列表和简介，不返回章节全文。

## 测试

```powershell
uv run pytest
```

## Docker

```powershell
docker build -t takome-agent .
docker run --rm -p 8000:8000 --env-file .env takome-agent
```

## 生产注意事项

- 当前 MVP 使用内存型 checkpointer，适合单 worker 运行。
- 多 worker、多实例或服务重启会导致内存会话丢失。
- 生产环境建议改用 Redis/Postgres checkpointer，或确保请求固定落到同一实例。
- 不要提交 `.env`、DeepSeek API Key 或 `INTERNAL_TOKEN`。

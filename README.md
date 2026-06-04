# Takome AI Reading Assistant Agent

独立 Python FastAPI agent 服务。Spring Boot 将已认证的 `user_id`、`conversation_id`、`message` 转发到本服务，本服务使用 LangChain v1 `create_agent` 调用 DeepSeek，并通过 SSE 返回 `token`、`tool_start`、`tool_end`、`error`、`done` 事件。

## 运行

```bash
uv sync --dev
uvicorn main:app --host 0.0.0.0 --port 8000
```

## 配置

服务启动时会用 `python-dotenv` 加载根目录 `.env`。`.env` 已在 `.gitignore` 中，不应提交到仓库；可参考 `.env.example` 填本地配置。

必需配置：

```bash
DEEPSEEK_API_KEY=your-deepseek-key
INTERNAL_TOKEN=shared-token-between-spring-and-agent
```

可选配置：

```bash
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
SPRING_BASE_URL=http://localhost:8888
THREAD_TTL_SECONDS=1800
MAX_MESSAGE_LENGTH=2000
DISABLE_DEEPSEEK_THINKING=true
```

`INTERNAL_TOKEN` 同时用于 Spring 调 agent 的入站校验，以及 agent 调 Spring 内部工具 API 时携带的 `X-AI-Internal-Token`。

不要使用 `deepseek-chat` 或 `deepseek-reasoner`。默认模型是 `deepseek-v4-flash`，并通过 `extra_body={"thinking":{"type":"disabled"}}` 关闭思考模式。

## 接口

### GET /health

返回：

```json
{"status":"ok"}
```

### POST /v1/assistant/chat/stream

Header:

```text
X-AI-Internal-Token: <INTERNAL_TOKEN>
```

Body:

```json
{
  "user_id": "123",
  "conversation_id": "frontend-generated-id",
  "message": "用户输入"
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

`thread_id = f"{user_id}:{conversation_id}"`。如果 `conversation_id` 为空，代码会使用 `default`，这会导致同一用户多个标签页共享上下文。

## 工具边界

agent 工具只访问 Spring Boot 内部 AI 工具 API，并统一携带：

```text
X-AI-Internal-Token: <INTERNAL_TOKEN>
```

工具 schema 不包含 `user_id`。`user_id` 从当前 FastAPI 请求上下文读取，并自动拼入 Spring 请求。工具输出只保留书籍摘要字段，列表最多 10 本，简介最多 200 字，不返回章节全文。

## 记忆限制

当前 MVP 使用全局 `langgraph.checkpoint.memory.InMemorySaver`，并通过 middleware 只保留系统提示词和最近约 10 轮消息，避免上下文无限增长。

这只适合单 worker MVP：多 worker、多实例或服务重启会丢失内存，也可能因为请求没有固定落到同一实例而看起来像上下文缺失。生产部署应改为 Redis/Postgres checkpointer，或使用 sticky session。

## 测试

```bash
uv run pytest
```

# Takome Agent

Takome Agent 是 Takome 项目的 AI 阅读助手服务。它是一个独立的 Python/FastAPI 仓库，由 Takome Backend 在用户已认证的上下文中调用，负责连接 DeepSeek 模型、调用站内工具，并通过 SSE 返回流式回答。

在线演示网站: [Takome 书屋](https://takome.top)，目前仅部署了小说阅读站点

## 相关仓库

- Frontend: [zhim00/Takome-frontend](https://github.com/zhim00/Takome-frontend)
- Backend: [zhim00/Takome-backend](https://github.com/zhim00/Takome-backend)
- Agent: [zhim00/Takome-agent](https://github.com/zhim00/Takome-agent)

## 服务职责

- 提供 `POST /v1/assistant/chat/stream` 流式对话接口
- 使用 LangChain/LangGraph 编排模型调用、工具调用和短期记忆
- 使用 DeepSeek 生成面向读者的中文回答
- 通过后端内部工具查询用户书架、阅读历史、小说搜索、小说详情和推荐数据
- 使用 `X-AI-Internal-Token` 与后端进行服务间鉴权
- 对工具结果进行裁剪和摘要化处理，避免把章节全文或过量站内数据送入模型上下文

## 架构

```text
Takome Frontend
  -> Takome Backend /api/front/ai/chat/stream
  -> Takome Agent   /v1/assistant/chat/stream
  -> Takome Backend /api/internal/ai/tools/*
  -> DeepSeek API
```

Agent 不直接接收浏览器请求，也不直接信任前端用户身份。用户身份由 Backend 完成认证后转发给 Agent。

## 技术栈

- Python `>=3.13`
- FastAPI
- Uvicorn
- LangChain
- LangGraph
- langchain-deepseek
- httpx
- pydantic-settings
- uv
- pytest

## 项目结构

```text
Takome-agent/
├─ app/
│  ├─ agent.py       # Agent 编排、DeepSeek 模型、SSE 事件映射
│  ├─ schemas.py     # 请求模型和 thread_id 构造
│  ├─ settings.py    # 环境变量配置
│  └─ tools.py       # 后端内部 AI 工具封装
├─ tests/            # 测试
├─ main.py           # FastAPI 入口
├─ pyproject.toml
├─ uv.lock
└─ Dockerfile
```

## 运行要求

- Python `>=3.13`
- uv
- DeepSeek API Key
- 正在运行的 Takome Backend，默认地址为 `http://localhost:8888`

## 配置

复制环境变量示例：

```bash
cp .env.example .env
```

Windows PowerShell:

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

`INTERNAL_TOKEN` 必须与 Takome Backend 的 `INTERNAL_TOKEN` 一致。它用于：

- Backend 调用 Agent 时的入站鉴权
- Agent 回查 Backend 内部工具接口时携带 `X-AI-Internal-Token`

不要提交真实 `.env`、DeepSeek API Key 或内部 token。

## 本地开发

```bash
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

Header:

```text
X-AI-Internal-Token: <INTERNAL_TOKEN>
```

Body:

```json
{
  "user_id": "123",
  "conversation_id": "frontend-generated-id",
  "message": "帮我推荐几本最近读过的同类小说"
}
```

SSE events:

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

`thread_id` 使用 `user_id:conversation_id`。如果 `conversation_id` 为空，会回退到 `default`，同一用户的多个会话可能共享上下文。

## 工具

Agent 会调用 Backend 内部工具接口：

```text
GET /api/internal/ai/tools/bookshelf
GET /api/internal/ai/tools/search/books
GET /api/internal/ai/tools/books/{bookId}
GET /api/internal/ai/tools/recommend
GET /api/internal/ai/tools/read-history
```

工具 schema 不暴露 `user_id`。Agent 会从当前请求上下文读取用户 ID，并自动拼入 Backend 请求。

## 测试

```bash
uv run pytest
```

## Docker

```bash
docker build -t takome-agent .
docker run --rm -p 8000:8000 --env-file .env takome-agent
```

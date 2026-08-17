# 重构方案：对齐 DeerFlow 架构

## 问题诊断

**严重问题**：
1. **违反技术栈约定**：`packages/medagent/` 自己造轮子（自定义 `DialogMiddleware`、`MiddlewareChain`、`DialogAgent` 类），完全没有使用 AGENTS.md 明确要求的 **Langchain/LangGraph** 构建智能体。
2. **职责划分混乱**：
   - `medagent` 包内出现应用逻辑（`DialogAgent` 直接编排业务流程）
   - `app` 包职责不清（应该只是 FastAPI Gateway + 业务适配层）
3. **参考架构未学习**：完全无视 `demo-code/deerflow-backend` 的成熟设计模式。

## 正确架构参考（DeerFlow）

### 1. packages/harness（SDK 层）职责
```
deerflow/
├── agents/
│   ├── factory.py              # 纯参数工厂 create_deerflow_agent()
│   ├── lead_agent/             
│   │   ├── agent.py            # _make_lead_agent() 组装 LangGraph
│   │   └── prompt.py           # 系统提示词
│   ├── middlewares/            # LangChain AgentMiddleware 标准实现
│   │   ├── memory_middleware.py
│   │   ├── clarification_middleware.py
│   │   └── ...
│   ├── service_agent/          # 领域特定 Agent（如 data_agent）
│   └── thread_state.py         # LangGraph StateGraph 的 State 定义
├── sandbox/                     # 沙盒抽象（local/e2b/provisioner）
├── subagents/                   # 子智能体委托系统
├── tools/builtins/              # 内置工具（present_files, ask_clarification）
├── mcp/                         # MCP 集成
├── models/                      # 模型工厂（支持 thinking/vision）
├── config/                      # 配置系统
└── client.py                    # Python SDK
```

**关键设计**：
- **使用 LangChain/LangGraph 原生 API**：`langchain.agents.create_agent()` + `AgentMiddleware`
- **纯参数化工厂**：`create_deerflow_agent(model, tools, middleware, ...)` 不读全局配置
- **Middleware 实现 LangChain 标准协议**：继承 `AgentMiddleware`，覆写 `before` / `after` 钩子

### 2. app/gateway（应用层）职责
```
app/
├── gateway/
│   ├── app.py                  # FastAPI 应用 + lifespan
│   ├── routers/                # REST API 路由
│   │   ├── threads.py          # 会话 CRUD
│   │   ├── runs.py             # 执行管理
│   │   ├── agents.py           # Agent 配置
│   │   └── ...
│   └── deps.py                 # 依赖注入（langgraph_runtime, checkpointer）
└── channels/                   # IM 平台集成（Slack/Lark/GitHub）
```

**关键职责**：
- **Gateway API**：暴露 REST 接口，代理到 LangGraph Runtime
- **依赖组装**：组合 harness 提供的工厂函数，注入具体实现（PostgreSQL checkpointer、Redis 状态、模型配置）
- **业务适配**：医疗领域的量表加载、关键词匹配、SSE 推送等**适配代码**放这里

## 重构计划

### 阶段 1：清理错误实现（删除造轮子代码）

**删除文件**：
```
backend/packages/medagent/agents/
├── middleware/base.py           # ❌ 自定义 DialogMiddleware 抽象
├── middleware/event_publish.py  # ❌ 应用逻辑混入
├── middleware/keyword_intercept.py
├── middleware/schedule_constraint.py
├── middleware/timeout.py
└── service_agent/dialog_agent/
    ├── agent.py                 # ❌ DialogAgent 自定义编排类
    ├── engine.py                # ❌ 自定义引擎抽象
    └── models.py                # ❌ 自定义协议
```

**原因**：这些都在重复造 LangChain/LangGraph 已有的标准协议。

### 阶段 2：建立正确的 SDK 层（packages/medagent）

#### 2.1 Agent 工厂（对齐 deerflow/agents/factory.py）

**新建** `backend/packages/medagent/agents/factory.py`：
```python
"""纯参数工厂：create_medagent()
职责：组装 LangGraph agent，使用 LangChain 标准 AgentMiddleware。
"""
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

def create_medagent(
    model: BaseChatModel,
    tools: list[BaseTool] | None = None,
    *,
    system_prompt: str | None = None,
    middleware: list[AgentMiddleware] | None = None,
    state_schema: type | None = None,
    checkpointer = None,
    name: str = "default",
) -> CompiledStateGraph:
    """创建医疗评估智能体（纯参数，不读全局配置）。
    
    Args:
        model: LangChain BaseChatModel 实例
        tools: 工具列表
        system_prompt: 系统提示词
        middleware: LangChain AgentMiddleware 列表
        state_schema: LangGraph State 类型
        checkpointer: 检查点存储后端
        name: 智能体名称
    Return:
        CompiledStateGraph: 编译后的 LangGraph
    """
    from medagent.agents.thread_state import ThreadState
    
    effective_state = state_schema or ThreadState
    effective_middleware = middleware or []
    
    return create_agent(
        model=model,
        tools=tools or None,
        middleware=effective_middleware,
        system_prompt=system_prompt,
        state_schema=effective_state,
        checkpointer=checkpointer,
        name=name,
    )
```

#### 2.2 Middleware 标准实现（对齐 deerflow/agents/middlewares/）

**新建** `backend/packages/medagent/agents/middlewares/constraint_middleware.py`：
```python
"""约束注入中间件（LangChain 标准协议）"""
from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from typing import override

class ConstraintMiddleware(AgentMiddleware):
    """从 Redis Stream 消费 ConstraintEvent 并注入 system prompt。
    
    对标 deerflow 的 MemoryMiddleware / ClarificationMiddleware。
    """
    state_schema = AgentState  # 兼容 ThreadState
    
    def __init__(self, constraint_source):
        super().__init__()
        self._source = constraint_source
    
    @override
    async def before(self, state: AgentState, runtime) -> AgentState:
        """执行前钩子：拉取约束并注入 messages。"""
        constraints = await self._source.pull_constraints(
            session_id=runtime.context.get("session_id")
        )
        if constraints:
            # 注入 system message（LangChain 标准做法）
            from langchain_core.messages import SystemMessage
            state["messages"].append(
                SystemMessage(content=f"约束提示：{constraints}")
            )
        return state
```

**新建** `backend/packages/medagent/agents/middlewares/event_publish_middleware.py`：
```python
"""事件发布中间件"""
from langchain.agents.middleware import AgentMiddleware

class EventPublishMiddleware(AgentMiddleware):
    """智能体执行后发布事件到 Redis Stream。"""
    
    def __init__(self, event_publisher):
        super().__init__()
        self._publisher = event_publisher
    
    async def after(self, state, runtime):
        """执行后钩子：发布 DialogTurnEvent。"""
        session_id = runtime.context.get("session_id")
        last_message = state["messages"][-1]
        await self._publisher.publish(
            DialogTurnEvent(
                session_id=session_id,
                turn_number=...,
                answer=last_message.content,
            )
        )
        return state
```

#### 2.3 Service Agent（对齐 deerflow/agents/service_agent/）

**保留但重构** `backend/packages/medagent/agents/service_agent/dialog_agent/`：
```python
"""Dialog Agent 工厂（不再是自定义类，而是配置+组装函数）"""
from medagent.agents.factory import create_medagent
from medagent.agents.middlewares.constraint_middleware import ConstraintMiddleware
from medagent.agents.middlewares.event_publish_middleware import EventPublishMiddleware

def make_dialog_agent(
    model,
    patient_info: dict,
    task_list: list,
    constraint_source,
    event_publisher,
    checkpointer,
) -> CompiledStateGraph:
    """组装 Dialog Agent（返回 LangGraph，不是自定义类）。"""
    system_prompt = build_system_prompt(patient_info, task_list)
    
    middleware = [
        ConstraintMiddleware(constraint_source),
        EventPublishMiddleware(event_publisher),
    ]
    
    return create_medagent(
        model=model,
        tools=DIALOG_TOOLS,
        system_prompt=system_prompt,
        middleware=middleware,
        checkpointer=checkpointer,
        name="dialog_agent",
    )
```

### 阶段 3：应用层适配（app/）

#### 3.1 Gateway 路由（对齐 app/gateway/routers/）

**保留并调整** `backend/app/api/dialog.py`：
- 职责：REST API 入口，调用 LangGraph Runtime
- 不再直接调用 `dialog_service`，而是通过 LangGraph 的 `invoke()` / `stream()`

#### 3.2 Worker 适配层（新增）

**新建** `backend/app/workers/dialog_agent_factory.py`：
```python
"""应用层：组装 Dialog Agent 的依赖注入适配器"""
from medagent.agents.service_agent.dialog_agent import make_dialog_agent
from app.managers.assessment_loader import load_tasks_from_db
from app.workers.event_publisher import DialogEventPublisher

def create_dialog_agent_for_session(session_no: str, db: Session):
    """为会话创建 Dialog Agent（注入 PostgreSQL、Redis、Model）。"""
    # 1. 加载领域数据（量表任务）
    tasks = load_tasks_from_db(db, session_no)
    
    # 2. 准备依赖
    from medagent.providers.llm_model import create_chat_model
    from app.utils.redis_client import get_async_redis
    from app.workers.constraint_source import RedisConstraintSource
    
    model = create_chat_model(config.agent_models.dialog_agent)
    constraint_source = RedisConstraintSource(get_async_redis())
    event_publisher = DialogEventPublisher(session_id=session_no)
    checkpointer = ...  # PostgreSQL checkpointer
    
    # 3. 调用 SDK 工厂
    return make_dialog_agent(
        model=model,
        patient_info={...},
        task_list=tasks,
        constraint_source=constraint_source,
        event_publisher=event_publisher,
        checkpointer=checkpointer,
    )
```

#### 3.3 Celery 任务适配

**保留** `backend/app/celery_app/tasks.py`，但改为：
```python
@celery_app.task(name="dialog_agent_preheat")
def dialog_agent_preheat(session_id: str, patient_info: dict, task_config: dict):
    """预热任务：创建 LangGraph agent 并保存检查点。"""
    ensure_worker_runtime()
    
    from app.workers.dialog_agent_factory import create_dialog_agent_for_session
    graph = create_dialog_agent_for_session(session_id, db)
    
    # 初始化检查点
    config = {"configurable": {"thread_id": session_id}}
    graph.invoke({"messages": []}, config=config)
```

### 阶段 4：测试与验证

- [ ] 单元测试：Middleware 标准协议
- [ ] 集成测试：LangGraph invoke/stream
- [ ] E2E 测试：SSE 流式推送

## 重构执行步骤

### 步骤 1：暂停当前分支，备份代码
```bash
git checkout main
git branch backup/before-refactor
git checkout -b refactor/align-deerflow-arch
```

### 步骤 2：删除错误实现
```bash
rm -rf backend/packages/medagent/agents/middleware/
rm -rf backend/packages/medagent/agents/service_agent/dialog_agent/agent.py
rm -rf backend/packages/medagent/agents/service_agent/dialog_agent/engine.py
```

### 步骤 3：逐模块重构（按上述阶段 2、3）

### 步骤 4：更新 AGENTS.md 文档

### 步骤 5：E2E 验证后合并

## 关键原则（避免再犯）

1. **技术栈约定是硬约束**：AGENTS.md 写了用 LangChain/LangGraph，就必须用标准 API，不能自己造抽象。
2. **参考架构必须学习**：`demo-code/deerflow-backend` 是成熟方案，必须理解其职责划分再动手。
3. **SDK 与 App 严格分离**：
   - `medagent` 包：纯 SDK，不依赖 PostgreSQL ORM、FastAPI、业务逻辑
   - `app` 包：依赖注入、适配层、REST API
4. **先讨论、后开发**：遇到架构决策，先制定方案文档，充分讨论，确认可行再写代码。

## 预估工作量

- 阶段 1（清理）：1 小时
- 阶段 2（SDK 层重构）：4-6 小时
- 阶段 3（应用层适配）：3-4 小时
- 阶段 4（测试验证）：2-3 小时

**总计**：10-14 小时（约 2 个工作日）

## 风险与缓解

**风险**：现有 Schedule Agent / Extraction Agent 也可能有类似问题。
**缓解**：本次重构聚焦 Dialog Agent；完成后举一反三，review 其他 Agent。

---

**等待确认**：
1. 是否认可上述重构方向？
2. 是否需要我先演示重构一个模块（如 ConstraintMiddleware）作为样例？
3. 还有其他参考代码需要我学习吗？

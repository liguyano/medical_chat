# 重构 medagent 配置与工厂方案

## 文档信息
- **需求名称**: medagent SDK 架构重构 - 配置、工厂、中间件、工具
- **创建时间**: 2026-08-17
- **背景**: 当前 app 层直接实例化 DialogEngine，违反 app/agent 分离原则；medagent 包缺少配置层、模型工厂、LangGraph State 定义等基础设施

---

## 一、问题诊断

### 1.1 架构违规

**核心问题**：`app/celery_app/tasks.py:117-143` 直接在应用层实例化 `DoubaoVoiceEngine` / `TextChatEngine`：

```python
# ❌ 错误：app 层直接读配置、构造引擎
if engine_type == "doubao":
    voice_config = config.get_voice_model_config("dialog_agent")
    engine = DoubaoVoiceEngine(
        api_key=voice_config.resolved_api_key(),
        model=voice_config.model,
        ws_url=voice_config.websocket_url,
        timeout=voice_config.timeout,
    )
elif engine_type == "text":
    text_config = config.get_agent_model_config("dialog_agent")
    engine = TextChatEngine(
        api_key=text_config.resolved_api_key(),
        model=text_config.model,
        api_base=text_config.api_base,
        timeout=text_config.timeout,
    )
agent = build_dialog_agent(..., engine=engine)
```

**违反原则**：
- App 层不应关心引擎构造细节（API Key、WebSocket URL、超时等）
- 配置读取逻辑应封装在 `medagent` SDK 内部
- App 层应调用 SDK 工厂接口，传入高层参数（agent_name、thinking_enabled 等）

### 1.2 缺失基础设施

**空目录/文件**（已准备但未使用）：
```
packages/medagent/
├── configs/
│   ├── agent_config.py          # ❌ 空文件
│   └── model_config.py          # ❌ 空文件
├── providers/
│   └── llm_model.py             # ❌ 空文件
├── agents/
│   ├── factory.py               # ❌ 空文件
│   └── thread_state.py          # ❌ 空文件
```

**后果**：
- 无法表达 ModelConfig / AgentConfig 的 Pydantic Schema
- 无法提供统一的模型工厂（`create_chat_model` / `create_dialog_engine`）
- 无法定义 LangGraph 的 ThreadState（TypedDict + reducers）
- 无法对齐 deerflow 的工厂模式（`create_deerflow_agent`）

---

## 二、参考架构（deerflow）

### 2.1 配置层

**deerflow/config/model_config.py**：
```python
class ModelConfig(BaseModel):
    name: str                           # 模型唯一标识
    use: str                            # 类路径（如 langchain_openai.ChatOpenAI）
    model: str                          # 模型名称（如 gpt-4o）
    supports_thinking: bool             # 是否支持思维链
    supports_vision: bool               # 是否支持视觉
    context_window: int | None          # 上下文窗口
    stream_chunk_timeout: float | None  # 流式超时
    when_thinking_enabled: dict | None  # 思维模式配置
    when_thinking_disabled: dict | None # 非思维模式配置
    model_config = ConfigDict(extra="allow")  # 允许额外字段（api_base、temperature 等）
```

**deerflow/config/app_config.py**：
```python
class AppConfig(BaseModel):
    models: list[ModelConfig]           # 所有模型配置
    
    def get_model_config(self, name: str) -> ModelConfig | None:
        return next((m for m in self.models if m.name == name), None)
```

### 2.2 模型工厂

**deerflow/models/factory.py**：
```python
def create_chat_model(
    name: str | None = None,
    thinking_enabled: bool = False,
    *,
    app_config: AppConfig | None = None,
    model_overrides: dict | None = None,
    **kwargs
) -> BaseChatModel:
    """从配置创建 LangChain 聊天模型"""
    config = app_config or get_app_config()
    model_config = config.get_model_config(name or config.models[0].name)
    model_class = resolve_class(model_config.use, BaseChatModel)
    
    # 组装参数：配置 + 覆盖 + 思维模式切换
    settings = model_config.model_dump(exclude_none=True, exclude={...})
    if model_overrides:
        settings.update({k: v for k, v in model_overrides.items() if v is not None})
    if thinking_enabled and model_config.when_thinking_enabled:
        settings.update(model_config.when_thinking_enabled)
    
    return model_class(**kwargs, **settings)
```

### 2.3 Agent 工厂

**deerflow/agents/factory.py**：
```python
def create_deerflow_agent(
    model: BaseChatModel,
    tools: list[BaseTool] | None = None,
    *,
    system_prompt: str | None = None,
    middleware: list[AgentMiddleware] | None = None,
    state_schema: type | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    name: str = "default",
) -> CompiledStateGraph:
    """创建 DeerFlow Agent（返回 LangGraph）"""
    return create_agent(
        model=model,
        tools=tools or [],
        middleware=middleware or [],
        system_prompt=system_prompt,
        state_schema=state_schema or ThreadState,
        checkpointer=checkpointer,
        name=name,
    )
```

### 2.4 ThreadState 定义

**deerflow/agents/thread_state.py**：
```python
from typing import Annotated, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class ThreadState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    sandbox: Annotated[dict, merge_sandbox]
    artifacts: Annotated[list[dict], merge_artifacts]
```

---

## 三、重构方案

### 3.1 阶段 1：配置层（medagent/configs/）

#### 3.1.1 ModelConfig（对齐 deerflow）

**新建** `packages/medagent/configs/model_config.py`：
```python
"""模型配置 Schema（Pydantic）"""
from pydantic import BaseModel, ConfigDict

class ModelConfig(BaseModel):
    """单模型配置（支持 OpenAI 兼容 + 豆包实时语音）"""
    name: str                           # 模型标识（如 "dialog_agent"）
    use: str                            # 类路径（langchain_openai.ChatOpenAI / medagent.agents.service_agent.dialog_agent.engine.DoubaoVoiceEngine）
    model: str                          # 模型名称（如 gpt-4o / doubao-voice-v1）
    
    # OpenAI 兼容字段
    api_base: str | None = None
    api_key: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    timeout: float | None = None
    
    # 豆包语音特有字段
    websocket_url: str | None = None
    voice: str | None = None
    audio_format: str | None = None
    reconnect_attempts: int | None = None
    
    # 通用元数据
    supports_thinking: bool = False
    supports_vision: bool = False
    context_window: int | None = None
    
    model_config = ConfigDict(extra="allow")  # 允许额外字段
```

**新建** `packages/medagent/configs/agent_config.py`：
```python
"""Agent 配置 Schema"""
from pydantic import BaseModel

class AgentConfig(BaseModel):
    """Agent 配置"""
    models: list[ModelConfig]           # 所有模型配置列表
    
    def get_model_config(self, name: str) -> ModelConfig | None:
        """根据名称查找模型配置"""
        return next((m for m in self.models if m.name == name), None)
```

#### 3.1.2 配置加载器

**新建** `packages/medagent/configs/__init__.py`：
```python
"""配置加载与缓存"""
from pathlib import Path
from functools import lru_cache
import yaml
from medagent.configs.agent_config import AgentConfig

@lru_cache(maxsize=1)
def get_agent_config() -> AgentConfig:
    """加载 Agent 配置（缓存单例）"""
    # 优先从环境变量读取路径
    import os
    config_path = os.getenv("MEDAGENT_CONFIG_PATH", "config.yaml")
    
    # 从项目根查找 config.yaml
    repo_root = Path(__file__).parents[4]  # medagent/configs/ -> packages -> backend -> repo
    config_file = repo_root / config_path
    
    if not config_file.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_file}")
    
    with open(config_file, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    
    return AgentConfig(**raw)
```

### 3.2 阶段 2：模型工厂（medagent/providers/）

**新建** `packages/medagent/providers/llm_model.py`：
```python
"""模型工厂：根据配置创建 LangChain 模型或自定义引擎"""
import logging
from langchain_core.language_models import BaseChatModel
from medagent.configs import get_agent_config
from medagent.configs.model_config import ModelConfig

logger = logging.getLogger(__name__)

def _resolve_class(class_path: str, base_class: type):
    """动态加载类"""
    module_path, class_name = class_path.rsplit(".", 1)
    module = __import__(module_path, fromlist=[class_name])
    cls = getattr(module, class_name)
    if not issubclass(cls, base_class):
        raise TypeError(f"{class_path} 不是 {base_class} 的子类")
    return cls

def create_chat_model(
    name: str,
    *,
    thinking_enabled: bool = False,
    model_overrides: dict | None = None,
) -> BaseChatModel:
    """创建 LangChain 聊天模型（OpenAI 兼容）
    
    Args:
        name: 模型配置名称（如 "dialog_agent"）
        thinking_enabled: 是否启用思维模式
        model_overrides: 覆盖参数（temperature、max_tokens 等）
    
    Returns:
        BaseChatModel 实例
    """
    config = get_agent_config()
    model_config = config.get_model_config(name)
    if not model_config:
        raise ValueError(f"模型配置不存在: {name}")
    
    # 动态加载模型类
    model_class = _resolve_class(model_config.use, BaseChatModel)
    
    # 组装参数
    settings = model_config.model_dump(
        exclude_none=True,
        exclude={"name", "use", "supports_thinking", "supports_vision", "context_window"},
    )
    if model_overrides:
        settings.update({k: v for k, v in model_overrides.items() if v is not None})
    
    # TODO: 思维模式切换（when_thinking_enabled / when_thinking_disabled）
    
    return model_class(**settings)

def create_dialog_engine(
    name: str,
    *,
    engine_type: str = "text",
) -> Any:
    """创建 Dialog 引擎（文本 / 语音）
    
    Args:
        name: 模型配置名称（如 "dialog_agent"）
        engine_type: 引擎类型（"text" / "doubao"）
    
    Returns:
        DialogEngine 实例（DoubaoVoiceEngine / TextChatEngine）
    """
    config = get_agent_config()
    model_config = config.get_model_config(name)
    if not model_config:
        raise ValueError(f"模型配置不存在: {name}")
    
    if engine_type == "doubao":
        from medagent.agents.service_agent.dialog_agent.engine import DoubaoVoiceEngine
        return DoubaoVoiceEngine(
            api_key=model_config.api_key or "",
            model=model_config.model,
            ws_url=model_config.websocket_url or "wss://openspeech.bytedance.com/api/v1/tts/ws_binary",
            timeout=model_config.timeout or 30.0,
            reconnect_attempts=model_config.reconnect_attempts or 1,
        )
    elif engine_type == "text":
        from medagent.agents.service_agent.dialog_agent.engine import TextChatEngine
        return TextChatEngine(
            api_key=model_config.api_key or "",
            model=model_config.model,
            api_base=model_config.api_base or "",
            timeout=model_config.timeout or 30.0,
        )
    else:
        raise ValueError(f"不支持的引擎类型: {engine_type}")
```

### 3.3 阶段 3：ThreadState 定义（medagent/agents/thread_state.py）

**新建** `packages/medagent/agents/thread_state.py`：
```python
"""LangGraph State Schema 定义"""
from typing import Annotated, TypedDict, Any
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

def merge_dict(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """字典合并 reducer"""
    return {**left, **right}

class DialogState(TypedDict):
    """Dialog Agent 状态"""
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    patient_info: dict[str, Any]
    task_list: list[Any]
    metadata: Annotated[dict[str, Any], merge_dict]

# 向后兼容别名
ThreadState = DialogState
```

### 3.4 阶段 4：Agent 工厂（medagent/agents/factory.py）

**新建** `packages/medagent/agents/factory.py`：
```python
"""Agent 工厂：组装完整 Agent 实例"""
from typing import Any
from medagent.agents.service_agent.dialog_agent.agent import DialogAgent
from medagent.agents.service_agent.dialog_agent.engine import DialogEngine
from medagent.agents.middleware.base import DialogMiddleware
from medagent.providers.llm_model import create_dialog_engine

def create_dialog_agent(
    *,
    session_id: str,
    patient_info: dict[str, Any],
    task_list: list[Any],
    engine_type: str = "text",
    engine_name: str = "dialog_agent",
    middlewares: list[DialogMiddleware] | None = None,
    state_store: Any = None,
    history_store: Any = None,
    tool_executor: Any = None,
) -> DialogAgent:
    """创建 Dialog Agent（SDK 工厂入口）
    
    Args:
        session_id: 会话 ID
        patient_info: 患者信息
        task_list: 任务列表
        engine_type: 引擎类型（"text" / "doubao"）
        engine_name: 模型配置名称（从 config.yaml 读取）
        middlewares: 中间件列表
        state_store: 状态存储
        history_store: 历史存储
        tool_executor: 工具执行器
    
    Returns:
        DialogAgent 实例
    """
    # 从配置创建引擎
    engine = create_dialog_engine(engine_name, engine_type=engine_type)
    
    # 组装 Agent
    return DialogAgent(
        session_id=session_id,
        patient_info=patient_info,
        task_list=task_list,
        engine=engine,
        middlewares=middlewares or [],
        state_store=state_store,
        history_store=history_store,
        tool_executor=tool_executor,
    )
```

### 3.5 阶段 5：App 层重构（app/celery_app/tasks.py）

**修改前（tasks.py:117-143）**：
```python
# ❌ 直接构造引擎
if engine_type == "doubao":
    voice_config = config.get_voice_model_config("dialog_agent")
    engine = DoubaoVoiceEngine(...)
elif engine_type == "text":
    text_config = config.get_agent_model_config("dialog_agent")
    engine = TextChatEngine(...)
agent = build_dialog_agent(..., engine=engine)
```

**修改后**：
```python
# ✅ 调用 SDK 工厂
from medagent.agents.factory import create_dialog_agent
from app.workers.dialog_agent_runtime import get_runtime_dependencies

deps = get_runtime_dependencies(session_id, db)
agent = create_dialog_agent(
    session_id=session_id,
    patient_info=patient_info,
    task_list=task_list,
    engine_type=engine_type,
    engine_name="dialog_agent",
    middlewares=deps["middlewares"],
    state_store=deps["state_store"],
    history_store=deps["history_store"],
    tool_executor=deps["tool_executor"],
)
```

**新增** `app/workers/dialog_agent_runtime.py`（适配层）：
```python
"""App 层依赖注入适配器"""
from medagent.agents.middleware.keyword_intercept import KeywordInterceptMiddleware
from medagent.agents.middleware.schedule_constraint import ScheduleConstraintMiddleware
from medagent.agents.middleware.event_publish import EventPublishMiddleware
from medagent.agents.middleware.timeout import TimeoutMiddleware
from app.utils.redis_client import get_redis
from app.managers.dialog_history import DialogHistoryManager
from app.workers.agent_state_manager import AsyncAgentStateManager

def get_runtime_dependencies(session_id: str, db) -> dict:
    """组装运行时依赖（PostgreSQL、Redis、Middleware）"""
    redis_client = get_redis()
    
    return {
        "middlewares": [
            KeywordInterceptMiddleware(),
            ScheduleConstraintMiddleware(...),
            EventPublishMiddleware(session_id, ...),
            TimeoutMiddleware(...),
        ],
        "state_store": AsyncAgentStateManager(),
        "history_store": DialogHistoryManager(),
        "tool_executor": None,  # 当前 DialogAgent 内部处理工具
    }
```

---

## 四、中间件与工具梳理

### 4.1 中间件现状（无需重构）

**已实现且符合协议**：
- `medagent/agents/middleware/base.py` — `DialogMiddleware` + `MiddlewareChain`
- `medagent/agents/middleware/keyword_intercept.py` — 关键词拦截
- `medagent/agents/middleware/schedule_constraint.py` — Schedule 约束注入
- `medagent/agents/middleware/event_publish.py` — 事件发布
- `medagent/agents/middleware/timeout.py` — 活动超时

**结论**：中间件架构清晰，只需确保 `MiddlewareChain` 在 `DialogAgent.handle_patient_input` 中正确调用（已验证）。

### 4.2 工具现状（无需重构）

**已实现**：
- `medagent/agents/service_agent/dialog_agent/tools.py` — 工具 Schema + 执行器
- `DIALOG_TOOLS` 包含 3 个工具：`get_education_material`、`trigger_consent_form`、`play_audio`
- 工具执行路由器 `execute_tool` 按名称分发

**结论**：工具层已完整，当前为桩实现（批次 B 落地真实数据）。

---

## 五、配置文件适配（config.yaml）

**当前** `config.yaml` 结构（推测）：
```yaml
models:
  - name: dialog_agent_text
    use: langchain_openai.ChatOpenAI
    model: gpt-4o
    api_base: https://api.openai.com/v1
    api_key: ${OPENAI_API_KEY}
    temperature: 0.7
    timeout: 30.0

voice_models:
  - name: dialog_agent_voice
    use: medagent.agents.service_agent.dialog_agent.engine.DoubaoVoiceEngine
    model: doubao-voice-v1
    api_key: ${DOUBAO_API_KEY}
    websocket_url: wss://openspeech.bytedance.com/api/v1/tts/ws_binary
    voice: zh-CN-YunxiNeural
    audio_format: pcm
    reconnect_attempts: 1
    timeout: 30.0
```

**重构后统一为 `models` 列表**：
```yaml
models:
  - name: dialog_agent
    use: langchain_openai.ChatOpenAI
    model: gpt-4o
    api_base: https://api.openai.com/v1
    api_key: ${OPENAI_API_KEY}
    temperature: 0.7
    timeout: 30.0
    supports_thinking: false
    supports_vision: false
    context_window: 128000
  
  - name: dialog_agent_voice
    use: medagent.agents.service_agent.dialog_agent.engine.DoubaoVoiceEngine
    model: doubao-voice-v1
    api_key: ${DOUBAO_API_KEY}
    websocket_url: wss://openspeech.bytedance.com/api/v1/tts/ws_binary
    voice: zh-CN-YunxiNeural
    audio_format: pcm
    reconnect_attempts: 1
    timeout: 30.0
```

**兼容策略**：
- `create_dialog_engine` 根据 `engine_type` 参数决定调用哪个配置
- `engine_type="text"` → `models[name="dialog_agent"]`
- `engine_type="doubao"` → `models[name="dialog_agent_voice"]`

---

## 六、执行步骤

### 6.1 步骤清单

- [ ] **步骤 1**：实现 `medagent/configs/model_config.py`（ModelConfig Schema）
- [ ] **步骤 2**：实现 `medagent/configs/agent_config.py`（AgentConfig + get_model_config）
- [ ] **步骤 3**：实现 `medagent/configs/__init__.py`（配置加载器 + 缓存）
- [ ] **步骤 4**：实现 `medagent/providers/llm_model.py`（create_chat_model + create_dialog_engine）
- [ ] **步骤 5**：实现 `medagent/agents/thread_state.py`（DialogState TypedDict）
- [ ] **步骤 6**：实现 `medagent/agents/factory.py`（create_dialog_agent 工厂）
- [ ] **步骤 7**：重构 `app/celery_app/tasks.py`（移除直接引擎实例化，调用 SDK 工厂）
- [ ] **步骤 8**：新增 `app/workers/dialog_agent_runtime.py`（App 依赖注入适配层）
- [ ] **步骤 9**：适配 `config.yaml`（统一 models 列表）
- [ ] **步骤 10**：测试验证（单元测试 + E2E）

### 6.2 Git 分支策略

```bash
git checkout main
git checkout -b refactor/medagent-config-factory
```

**提交计划**：
- Commit 1: 实现 configs/（ModelConfig + AgentConfig + 加载器）
- Commit 2: 实现 providers/（模型工厂）
- Commit 3: 实现 thread_state.py + factory.py
- Commit 4: 重构 app 层（tasks.py + runtime.py）
- Commit 5: 适配 config.yaml + 测试

### 6.3 测试验证

**单元测试**：
- `tests/unit/medagent/configs/test_model_config.py` — ModelConfig 加载与校验
- `tests/unit/medagent/providers/test_llm_model.py` — 工厂函数正确性

**集成测试**：
- `tests/integration/test_dialog_agent_factory.py` — SDK 工厂端到端
- `tests/integration/test_celery_dialog_agent_preheat.py` — Celery 任务正确调用工厂

---

## 七、风险与缓解

### 7.1 风险

1. **配置结构变更**：`config.yaml` 从 `models` + `voice_models` 合并为统一 `models` 列表，可能影响其他模块。
2. **动态类加载**：`_resolve_class` 依赖字符串路径，typo 导致运行时失败。
3. **App 依赖注入复杂度**：`get_runtime_dependencies` 需正确组装 PostgreSQL、Redis、Middleware。

### 7.2 缓解

1. **向后兼容**：保留 `app/configs/app_config.py` 的 `get_voice_model_config` / `get_agent_model_config`，逐步迁移。
2. **类路径校验**：`_resolve_class` 增加 try-catch，启动时预加载所有模型类。
3. **依赖注入测试**：独立测试 `get_runtime_dependencies` 返回结构。

---

## 八、预估工作量

- **阶段 1**（configs/）：1 小时
- **阶段 2**（providers/）：1.5 小时
- **阶段 3**（thread_state.py）：0.5 小时
- **阶段 4**（factory.py）：1 小时
- **阶段 5**（app 层重构）：2 小时
- **测试与验证**：2 小时

**总计**：8 小时（约 1 个工作日）

---

## 九、后续优化方向

1. **LangGraph 完全对齐**：当前 DialogAgent 未使用 LangGraph StateGraph，仅定义了 ThreadState；批次 C 可考虑用 `create_agent` 替换自定义 `DialogAgent` 类。
2. **思维模式支持**：`create_chat_model` 增加 `when_thinking_enabled` / `when_thinking_disabled` 切换逻辑。
3. **多引擎热切换**：支持运行时从文本引擎降级到语音引擎（当前需重启会话）。

---

---

## 十、已确认的最终架构决策（2026-08-17）

用户确认四项关键决策，覆盖上文的初版方案：

### 决策 1：一次性完成 LangGraph 改造
- 安装 `langchain>=1.3` / `langgraph>=1.2` / `langchain-openai>=1.5`（uv 可解析，langchain 1.3.15 + langgraph 1.2.11）。
- **副作用**：`websockets` 会从 17.x 降级到 15.x（langchain-openai 约束），DoubaoVoiceEngine 需回归测试。

### 决策 2：统一 models + type 字段 + 详写 agent_models
- 删除 `voice_models` 段，所有模型进 `models` 列表，用 `type: language|voice` 区分。
- `agent_models` 支持简写（字符串→语言模型）与详写（`{language:.., voice:..}`）。
- `dialog_agent` 用详写同时绑定语言模型（文本降级）与语音模型。

### 决策 3：configs/ 模块已实现并通过验证
- `configs/model_config.py`（ModelConfig + ModelType 枚举）
- `configs/agent_config.py`（AgentConfig + AgentModelBinding + 类别校验）
- `configs/__init__.py`（独立加载器 + lru_cache 单例）

### 决策 4：文本进 LangGraph，语音保留专用引擎（关键架构分叉）

**根本原因**：豆包实时语音是 WebSocket 全双工音频流，无"请求/响应"边界，
无法适配 LangGraph `create_agent` 所需的 `BaseChatModel` 范式。

**双路径设计**：

| Agent | 协议 | 实现方式 |
|-------|------|----------|
| dialog（文本降级） | OpenAI 兼容 | `create_agent(ChatOpenAI, tools, AgentMiddleware)` |
| dialog（语音主路径） | WebSocket 全双工 | 保留 `DoubaoVoiceEngine` + 自定义编排 |
| schedule_agent | OpenAI 兼容 | 可迁移 `create_agent`（无语音包袱） |
| extraction_agent | OpenAI 兼容 | 可迁移 `create_agent`（无语音包袱） |

- 中间件改造为 LangChain `AgentMiddleware`（`before_model`/`after_model` 钩子），
  供文本路径使用；语音路径复用同一中间件的业务逻辑。
- Redis Stream 桥接（`dialog_stream:{session_id}`）两路径共享。

### 修订执行步骤

- [X] **步骤 1**：configs/ 模块（ModelConfig + AgentConfig + 加载器）— 已完成
- [X] **步骤 2**：pyproject.toml 添加 langchain/langgraph 依赖并安装 — 已完成（uv workspace，langchain 1.3.15 / langgraph 1.2.11 / langchain-openai 1.5.1）
- [X] **步骤 3**：providers/llm_model.py（create_chat_model 返回 BaseChatModel + create_voice_engine）— 已完成
- [X] **步骤 4**：agents/thread_state.py（DialogThreadState + reducers）— 已完成
- [X] **步骤 5**：agents/middlewares/ 评审 — 保留现有对话轮次级中间件（DialogMiddleware + MiddlewareChain），无需改造为 LangGraph 模型钩子
- [X] **步骤 6**：agents/factory.py（create_dialog_agent 文本路径 + 语音路径分叉，按 agent_models 绑定解析）— 已完成
- [X] **步骤 7**：重构 app/celery_app/tasks.py + app/workers 适配层（get_runtime_dependencies 依赖注入）— 已完成
- [X] **步骤 8**：config.yaml / config.example.yaml 统一 models 结构（type 字段 + 详写 agent_models）— 已完成
- [X] **步骤 9**：更新 app_config.py（复用 medagent Schema，同步 type 字段与详写绑定）— 已完成
- [X] **步骤 10**：测试验证 + 更新 AGENTS.md — 已完成（151 单测通过，新增 test_provider_factory / test_dialog_factory）

### 6.4 实施补充说明

- **中间件不改造的决策**：Dialog Agent 使用自定义 DialogEngine 抽象（TextChatEngine/DoubaoVoiceEngine），
  并非直接使用 LangGraph create_agent。现有 4 个中间件在对话轮次级别（before_agent/after_agent）
  经 MiddlewareChain 编排，语义清晰且已集成于 `DialogAgent.handle_patient_input`，无需转为
  LangGraph 的 before_model/after_model 模型钩子。
- **修复缺陷（providers/llm_model.py）**：
  1. `create_voice_engine` 原从 `extra_settings()` 读取 voice/audio_format/reconnect_attempts，
     但这些是 ModelConfig 显式建模字段（不在 model_extra 中），导致配置被静默丢弃。改为直接读字段：
     reconnect_attempts 作构造参数，voice/audio_format 构造后覆盖实例属性。
  2. 确认 `stream_chunk_timeout` 为 langchain-openai>=1.5 有效字段（项目 .venv 版本 1.5.1），保留默认注入。
- **配置单一事实来源**：app_config.py 删除重复的 ModelConfig/VoiceModelConfig，改为复用
  `medagent.configs` 的 ModelConfig/ModelType/AgentModelBinding，避免 app 层与 SDK 层配置漂移。

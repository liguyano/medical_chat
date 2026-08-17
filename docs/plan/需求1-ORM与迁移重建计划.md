# 需求1-ORM与迁移重建计划（对齐数据库业务设计事实来源）

## 背景

Codex 审查发现：`backend/app/models/*` 的 ORM 与 `backend/alembic/versions/acd1b408c6d6` 迁移
跟随的是**已废弃的"8 张核心表"模型**，与唯一事实来源
[`docs/sql/数据库表业务设计.md`](../sql/数据库表业务设计.md) +
[`docs/sql/出入院宣教与知情同意数据库设计补充.md`](../sql/出入院宣教与知情同意数据库设计补充.md)
不一致。文档层已修正并提交（commit `253cd51`）；本计划处理**代码层重建**，用户已确认方案为
"**重建 ORM + 迁移（大改）**"。

## 现状盘点（已确认）

| 项 | 现状 | 结论 |
| --- | --- | --- |
| `app/models/*.py` | 8 个旧 ORM：`assessment_task`/`dialog_session`/`dialog_message`/`extracted_field`/`agent_state`/`nurse_rating`/`education_record`/`consent_form` | 全部废弃，删除 |
| `app/models/__init__.py` | 导出上述 8 类 | 重写 |
| `app/models/base.py` | `Base` + `init_db` + `get_db`，无统一字段基类 | 保留并扩展（加统一字段 Mixin） |
| `alembic/versions/acd1b408c6d6_*.py` | 只有 `alter_column`/`drop_column`，**无 `create_table`**；针对已删除旧 DDL 的无效 diff；`alembic_version` 无记录 | 删除，重新生成初始迁移 |
| `alembic/env.py` | `from app.models import (...)` 导入 8 旧类 | 同步重写导入 |
| `app/managers/dialog_history_manager.py` | TODO 里 SQL 引用不存在的 `dialog_turns` | 改为对齐 `interaction_message` |
| `app/managers/agent_state_manager.py` | 只用 Redis，`_fallback_to_db`/`_load_from_db` 为 TODO | 不需 `agent_states` 表；TODO 注释指向事实来源 |
| API 路由 / 其他业务代码 | **无任何 `from app.models` 的活引用**（已 grep 确认） | 重建无连带破坏 |

**关键判断**：ORM 目前没有被任何业务逻辑真正消费（managers 里全是字符串 SQL 的 TODO），
所以重建是低连带风险的，主要工作量在"照着业务稿把表建对"。

## 事实来源的一期表清单（业务稿 §14）

一期核心（约 34 张）+ 宣教/知情同意补充（约 19 张）。全部落库工作量很大，**建议分批**，
本需求1（入院量表评估-AI对话）真正用到的是下面加粗的子集，其余可后续需求再补。

### 批次 A —— 需求1 直接依赖（本次重建目标）

| 业务域 | 表 |
| --- | --- |
| 患者与任务 | **`patient`**、**`patient_encounter`**、**`care_task`** |
| 量表配置 | **`assessment_scale`**、**`assessment_scale_version`**、**`assessment_section`**、**`assessment_question`**、**`assessment_option`**、`assessment_rule`、`assessment_action_definition` |
| AI 对话 | **`interaction_session`**、**`interaction_message`**、`interaction_event`、`interaction_rule`、`dialogue_script`、**`interaction_message_feedback`**（缺口1） |
| 评估执行 | **`assessment_instance`**、**`assessment_submission`**、**`assessment_answer`**、**`assessment_answer_option`**、`assessment_score`、`assessment_review` |

### 批次 B —— 一期需纳入但需求1非核心（建议后续需求补）

人机对比（`assessment_comparison*`）、质量评分（`quality_review*`）、结果应用
（`patient_profile_snapshot`/`nursing_plan*`）、审计（`operation_audit_log`）、
宣教与 Teach-back、知情同意、内容播报等补充域。

> **已确认 D1**：本次只重建批次 A（需求1直接依赖约 22 张表）；批次 B 随对应需求增量迁移。

## 统一字段规范（业务稿 §4）

所有表统一包含：`id`(BIGINT 主键)、`creator`、`updator`、`create_time`、`update_time`、
`deleted`(0/1 逻辑删除)。将在 `base.py` 新增 `TimestampMixin`/`BaseColumns` 统一提供，
禁止物理删除临床数据。

## 实施步骤

### 步骤 1：分支与基类
- [X] 继续使用当前 `feat/backend-infrastructure` 分支（用户已确认）
- [X] `base.py` 新增统一字段 Mixin（`creator/updator/create_time/update_time/deleted`）

### 步骤 2：删除旧 ORM 与无效迁移
- [X] 删除 `app/models/{assessment_task,dialog_session,dialog_message,extracted_field,agent_state,nurse_rating,education_record,consent_form}.py`
- [X] 删除 `alembic/versions/acd1b408c6d6_initial_migration_create_core_tables.py`
- [X] 备份并清空运行库中残留的旧表 / `alembic_version`

### 步骤 3：新建批次 A 的 ORM 模型
- [X] 按业务稿字段逐表编写 ORM（患者与任务域 → 量表配置域 → AI 对话域 → 评估执行域）
- [X] 落实关键约束：`assessment_answer` 唯一约束 `(submission_id, question_id)`；
      `care_task.collection_mode`（缺口2）；`assessment_submission.total_question_count`/
      `answered_question_count`（缺口3）；`interaction_message_feedback` 唯一约束
      `(interaction_message_id, reviewer_id)`（缺口1）
- [X] 重写 `app/models/__init__.py` 与 `alembic/env.py` 导入

### 步骤 4：重新生成初始迁移
- [X] `alembic revision --autogenerate -m "initial domain model batch A"`
- [X] 核对生成迁移：22 个 `create_table`、22 个 `drop_table`、0 个 `alter_column`
- [X] `alembic upgrade head` 验证建表成功，版本 `26533d4669bd`
- [X] `alembic check` 验证 ORM 与数据库无差异

### 步骤 5：修正 managers 对齐新模型
- [X] `dialog_history_manager.py`：删除旧 TODO 接口，直接实现 `interaction_message` CRUD，
      字段对齐（`content_text`/`role_type`/`turn_no`/`occurred_at` 等）
- [X] `agent_state_manager.py`：移除数据库降级 TODO（运行态存 Redis，不建 `agent_states` 表）

### 步骤 6：提交与移交测试
- [X] 提交（遵守 Git 规范前缀 `refactor(backend-db)`）
- [X] 输出需测试的代码位置 + 测试描述，移交 GPT（按既定分工，我不写测试代码）

### 步骤 7：自动化测试（用户于 2026-08-17 追加授权）
- [X] ORM 元数据与关键约束单元测试（不连接外部服务）
- [X] PostgreSQL 领域链路 CRUD 集成测试（外层事务回滚，不污染开发数据）
- [X] `DialogHistoryManager` 保存、查询、排序、格式化、逻辑删除集成测试
- [X] Alembic 临时数据库 upgrade/downgrade 可逆性测试
- [X] 补充 `unit-test/Readme.md` 与 `integ-test/Readme.md`
- [X] 执行测试、修复缺陷并提交

测试结果（2026-08-17）：

- 完整单元测试与领域持久化集成测试：21 项通过。
- Alembic 独立临时数据库迁移测试：1 项通过，临时数据库已自动删除。
- `alembic current` 为 `26533d4669bd (head)`，`alembic check` 无模型差异。
- 批次 A 新增 ORM、迁移、管理器与测试文件通过 Ruff 静态检查。

## 已确认的执行决策

- **D1｜重建范围**：批次 A（需求1直接依赖约 22 张表）。
- **D2｜数据库环境**：使用 Docker PostgreSQL 开发库
  `medical-evaluate-postgres` / `medical_evaluate` / `medical:medical_dev_password`
  / `localhost:15432`，实际执行清理旧表和 `alembic upgrade head`。
- **D3｜分支**：继续使用 `feat/backend-infrastructure`。

---
**创建时间**: 2026-08-17
**负责人**: Claude（AI 开发助手）
**关联**: [需求1-后端开发计划.md](需求1-后端开发计划.md)、[数据库表业务设计.md](../sql/数据库表业务设计.md)

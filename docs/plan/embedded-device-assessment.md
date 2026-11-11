# 嵌入式设备评估任务实施计划

> 历史 TCP 方案。当前固件接口见 [HTTP 接入说明](../esp32-s3-device-integration.md)。

**目标**：任务管理提供「传统问卷」「AI 对话」「嵌入式设备」三个选项。护士选择嵌入式设备时指定设备 ID，由 ESP32-S3 完成录音和播放。

**架构**：新增任务模式 `embedded_device`，沿用 AI 评估的会话、提取和完成核验。FastAPI 生命周期管理可选的原生 TCP 监听器，TCP 和网页语音通过客户端收发接口共用 VoiceGateway。后端先用模拟设备验收，再接任务管理界面和真机。

## 1. 任务模式和设备分配

- [ ] 1.1 先为任务创建、查询、准备、权限和旧数据写回归测试。检查任务模型及迁移约束，并逐个核对现有 `ai_dialogue` 分支。
- [X] 1.2 扩展 `backend/app/schemas/task.py`、`backend/app/services/task_service.py` 和持久化层。嵌入式模式必填 `device_id`，沿用 AI 评估准备流程，患者网页展示设备任务状态。
- [ ] 1.3 增加设备登记和分配记录，由运行时配置提供设备凭据的校验值。由有权限的护士分配，数据库约束设备和任务各只有一个有效绑定。离线分配可持久化，任务完成或取消后解除占用，待复核时保留。测试并发分配和越权。

## 2. TCP 启动与设备接入

- [X] 2.1 在 `backend/app/main.py` 生命周期接入 TCP 服务。配置默认关闭，联调示例端口 9100，首版单 API 进程监听。验证配置关闭、端口占用、关停释放端口。
- [X] 2.2 实现版本化帧协议。控制帧用 UTF-8 JSON，音频帧用二进制。用固定头传类型和长度，并限制帧长、读超时和发送队列。验证半包、合包、非法长度及慢连接。
- [X] 2.3 设备以 `HELLO` 报送 ID 和凭据。鉴权后返回当前分配，设备定期查询分配变化。同一设备只接受一个连接，重复连接需等旧连接关闭。设备开始任务前由后端复核绑定及任务状态。

## 3. 接通录音与播放

- [X] 3.1 为 VoiceGateway 提取客户端收发接口，保留浏览器 WebSocket 适配器，新增 TCP 适配器。覆盖原语音流程和两种终端争用同一会话的测试。
- [X] 3.2 使用 `RECORD_START → PCM → RECORD_END` 上行和 `PLAY_START → PCM → PLAY_END` 下行。设备侧统一 16 kHz、PCM16 LE、单声道。网关输出按实际采样率流式重采样，跨帧保留重采样状态。首版半双工。
- [ ] 3.3 模拟设备验证登录、离线分配、录音、播放和断线重连。丢弃中断轮的未完成音频及旧播放队列，保留已落库历史和评估进度。裸 TCP 联调使用局域网或私网通道及合成数据。

## 4. 任务管理界面与验收

- [X] 4.1 扩展前端任务类型和 DTO 映射。在护士任务管理新增「嵌入式设备」，选中时显示设备选择与在线状态，任务列表展示已分配设备。离线设备可以分配。
- [ ] 4.2 验证传统问卷和 AI 对话的原有入口，以及嵌入式设备模式的创建、分配、录放和完成。更新模块 AGENTS.md 与启动文档。真机验证录放切换后停止本次启动的服务。

## 当前 TCP 联调协议

先在 backend 目录执行数据库迁移，再启动现有 API。设置 DEVICE_TCP_ENABLED=true，DEVICE_TCP_HOST 为局域网接口地址，DEVICE_TCP_PORT 默认为 9100。DEVICE_TCP_CREDENTIALS 为 JSON 对象，键为设备 ID，值为设备密钥 UTF-8 字节的 SHA-256 小写十六进制摘要。密钥通过部署环境配置。设备连接后通过以下帧顺序通信。

- 帧头为一个字节类型和四字节大端长度，负载上限 8192 字节。类型 1 为 UTF-8 JSON，类型 2 为无文件头的 PCM16 LE 单声道 16 kHz。
- 首帧 HELLO 包含 version=1、device_id、secret，成功返回 HELLO_OK。重复连接需先断开旧连接。发送 PING 可收到 PONG，客户端应至少每 30 秒保活。
- 发送 GET_TASK 得到 TASK，包含 task_no 和 ready。设备定期查询。ready 为 true 后发送 START 并等待 STARTED。
- RECORD_START 得到 RECORDING 后发送 PCM 帧，以 RECORD_END 提交本轮。回复音频位于 PLAY_START 和 PLAY_END 之间。断线后重连并重新 START。
- 首版使用局域网或私网和合成音频联调。真实患者数据需要加密传输。

### 一键启动

在 PowerShell 会话中准备 `DEVICE_TCP_CREDENTIALS`，再从项目根目录运行 `.\start_medical_chat_all.bat`。脚本会等待 PostgreSQL 和 Redis 就绪，执行数据库迁移，再启动 API、Worker 和前端。设置凭据后默认开启设备 TCP，监听 `0.0.0.0:9100`。可在启动前覆盖监听地址和端口，也可显式设置 `DEVICE_TCP_ENABLED=false` 按普通模式启动。工作区需先准备本地配置和依赖。

### 手动启动示例

```powershell
cd backend
uv run alembic upgrade head
$env:DEVICE_TCP_ENABLED = "true"
$env:DEVICE_TCP_HOST = "0.0.0.0"
$env:DEVICE_TCP_PORT = "9100"
# 在受保护的运行环境预先设置 DEVICE_TCP_CREDENTIALS
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

设备连接后端电脑的局域网地址和所配 TCP 端口。只在受控联调网络开放该端口。

# ESP32-S3 语音评估设备 HTTP 接入说明

适用于亚博智能 ESP32-S3-N16R8 和 ESP-IDF 固件。设备按轮上传录音，等待回复生成后下载 WAV 播放。

## 1. 联调准备

- 后端提供完整的 API 基础地址、设备 ID 和独立密钥。公网使用现有站点的 HTTPS 域名和 443 端口，固件校验服务端证书。局域网可使用后端团队提供的可达地址联调，使用合成音频。
- 后端将设备 ID 与密钥的 SHA-256 小写十六进制摘要配置到 DEVICE_HTTP_CREDENTIALS，格式为 JSON 对象。生产 Compose 从服务器的运行环境读取该变量。固件保存原始密钥。
- 护士在「任务管理 → 创建任务 → 执行方式 → 嵌入式设备」按设备 ID 分配任务。「设备管理」可查看心跳状态。
- 所有设备请求携带 X-Device-ID 和 X-Device-Secret 两个 HTTP 请求头。接口返回普通 JSON 对象。音频下载返回 WAV 二进制。

本地使用一键脚本时，可以先在 PowerShell 设置 `$env:API_BIND_HOST = "<电脑的局域网 IP>"`，再运行 `.\start_medical_chat_all.bat`。设备使用该局域网 IP 和开发 API 端口 8000。开发机默认监听回环地址。

## 2. 心跳与任务

| 方法 | 路径 | 返回 |
|---|---|---|
| POST | /api/device/heartbeat | {"online":true} |
| GET | /api/device/task | {"task_no":"TASK-…","ready":true} |

设备启动后立即发心跳，之后每 15 秒发送一次。后端在最近一次心跳 45 秒后标为离线。无任务时 task_no 为 null，ready 为 false。任务准备中时可能已有编号，等 ready 为 true 再允许录音。建议待命时每 3–5 秒查任务。

## 3. 录音上传、查询与播放

1. 收音采用 16 kHz、PCM16 有符号小端、单声道。可用板载 ES8311 的 I2S RX 采集，按键结束后把整轮原始 PCM 作为请求体上传。录音最长 60 秒（1,920,000 字节），长度必须大于零且为偶数。
2. 生成一个新的 turn_id，例如 UUID。向 PUT /api/device/tasks/{task_no}/turns/{turn_id} 发送原始 PCM，请求头 Content-Type 为 application/octet-stream。请求体直接放 PCM 字节。成功返回 HTTP 202，正文为 {"turn_id":"…","status":"processing"}。重复上传可能直接返回已有状态。
3. 每 1–2 秒 GET /api/device/tasks/{task_no}/turns/{turn_id}。status 为 processing、ready 或 failed。处理超时为 120 秒。等待期间保持心跳。
4. ready 时 GET /api/device/tasks/{task_no}/turns/{turn_id}/audio，返回 audio/wav。WAV 为 16 kHz、16 位单声道。用现有 WAV 解析逻辑提取音频数据，按板卡播放示例复制到 I2S 左右声道，经 ES8311 DAC 和 NS4150 播放。播完再开始下一轮。

上传不附带 WAV 文件头。下载先解析 WAV 的 fmt 和 data 块，再把 PCM 样本交给 I2S。

## 4. 重试与错误

- 上传超时或断网时，用**相同 task_no、turn_id 和原始 PCM 字节**重试。同编号配不同录音会返回 409。需要重新录音时生成新的 turn_id。
- 轮次处理完成后保留 10 分钟。轮次缓存在单个 API 进程内，联调使用单 API 进程。进程重启后重新查询任务，已落库的评估进度由后端保存。
- 401 表示凭据不匹配。404 表示轮次不存在或已过期。409 表示任务未就绪、已有处理中轮次、轮次编号冲突或音频尚不可下载。413 表示录音超长。415 表示上传类型错误。422 表示缺少请求头或录音参数无效。503 时稍后重试。
- failed 时提示用户重录。下载失败可用同一个轮次再次 GET。

## 5. 真机验收

- 上线后确认护士端显示在线，停发心跳约 45 秒后显示离线。
- 分配测试任务，确认设备收到正确任务编号并等待准备完成。
- 上传合成录音，下载并播放 WAV，检查音高、速度和录放切换。
- 模拟上传响应丢失，用同一轮次重试，确认评估只接收一轮。

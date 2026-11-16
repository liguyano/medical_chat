# ESP32-S3 语音评估设备 HTTP 接入说明

适用于亚博智能 ESP32-S3-N16R8 和 ESP-IDF 固件。设备按轮上传录音，等待回复生成后下载 WAV 播放。

## 0. 旧固件怎么改

在固件工程里搜索 `/api/device/heartbeat` 和 `/api/device/task`，找到现在联网后直接发心跳和查任务的入口。在这两步之前插入登记阶段。沿用现有 Wi-Fi、按键和 ES8311 驱动。

1. **准备设备身份**。沿用已有的唯一设备 ID。如果旧固件已经给每台板子配置了独立密钥，继续使用；否则联网后用 `esp_fill_random` 生成 32 字节，转成 64 个十六进制字符，写入 NVS 并提交。后续启动先读 NVS。NVS 写入失败时停止登记并提示错误，避免下次启动换一把密钥。 [ESP-IDF 随机数文档](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/system/random.html)
2. **加登记请求**。复用现有 HTTPS 客户端，新增 `POST /api/device/registration`。用 `esp_http_client_set_header` 写入 `X-Device-ID` 和 `X-Device-Secret`，请求体为空。先检查 HTTP 状态码，再解析完整 JSON 响应。公网使用 HTTPS 并校验服务端证书。 [ESP-IDF HTTP 客户端文档](https://docs.espressif.com/projects/esp-idf/en/latest/esp32s3/api-reference/protocols/esp_http_client.html)
3. **等待护士同意**。HTTP 200 且 `status=pending` 时，在串口或屏幕显示 `verification_code`，每 5 秒用同一套凭据再发一次登记请求。护士在网页输入板子显示的 8 位核对码，点「同意登记」。若 HTTP 409，停止频繁重试并提示检查设备 ID。网络或 5xx 错误退避重试。日志只记设备 ID、状态码和核对码。
4. **批准后启动原逻辑**。收到 `status=approved` 后，立即发一次心跳，再启动原来的心跳和查任务逻辑。保持每 15 秒心跳，录音、上传、等回复和播放期间也要继续。只有任务返回 `ready=true` 才开放录音。
5. **烧录验证**。后端先用新版一键脚本启动并完成迁移。在 ESP-IDF PowerShell 进入固件工程，执行 `idf.py -p COM5 build flash monitor`，把 `COM5` 换成板子的串口。保留 NVS。看到核对码就先验证护士端审批，再确认心跳 200 和设备在线，最后测试录放音。

固件主流程可写成：`连 Wi-Fi → 读取或创建设备凭据 → 发登记 → 等审批 → 心跳与领任务 → 录音上传 → 查询轮次 → 下载播放`。

## 1. 联调准备

- 后端提供完整的 API 基础地址。公网使用现有站点的 HTTPS 域名和 443 端口，固件校验服务端证书。局域网可使用后端团队提供的可达地址联调，使用合成音频。
- 固件使用稳定且唯一的设备 ID，长度 1–64，只允许英文字母、数字、下划线和连字符。首次启动用设备随机源生成至少 32 字节随机值，编码为十六进制密钥，保存在 NVS。重启后继续使用同一密钥。后端只保存密钥摘要。
- 护士在「任务管理 → 创建任务 → 执行方式 → 嵌入式设备」按设备 ID 分配任务。「设备管理」可查看心跳状态。
- 所有设备请求携带 X-Device-ID 和 X-Device-Secret 两个 HTTP 请求头。接口返回普通 JSON 对象。音频下载返回 WAV 二进制。

本地使用一键脚本时，可以先在 PowerShell 设置 `$env:API_BIND_HOST = "<电脑的局域网 IP>"`，再运行 `.\start_medical_chat_all.bat`。设备使用该局域网 IP 和开发 API 端口 8000。开发机默认监听回环地址。

## 2. 心跳与任务

首次接入先向 `POST /api/device/registration` 发送设备 ID 和原始密钥两个请求头，请求体留空。返回 `{"status":"pending","verification_code":"AB12CD34","expires_at":"…"}` 时，在设备屏幕或串口显示核对码，勿输出原始密钥。每 5 秒用相同凭据重发申请查询结果。护士在「设备管理 → 待登记申请」选择该设备，输入设备显示的 8 位核对码后点「同意登记」。返回 `{"status":"approved"}` 后开始心跳和任务查询。

申请 15 分钟有效，过期后用相同凭据重新申请会返回新核对码。同一设备 ID 已被不同凭据占用时返回 409，固件应提示人工核对设备 ID。批准保存在数据库中，重启后仍有效。旧环境变量登记的设备仍可使用现有密钥。

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

# SSE 重连循环修复计划

## 1. 问题确认
- [X] FastAPI 持续收到同一会话的 SSE 重新订阅请求。
- [X] 前端续传参数错误地使用了 `snapshot:GEN-...` 业务快照 ID，而不是 Redis Stream ID。
- [X] 后端快照 SSE 事件没有携带 `stream_id` / SSE `id`。
- [X] 业务事件名 `error` 与 EventSource 的连接错误事件同名，可能触发错误重连逻辑。

## 2. 修复
- [X] 快照事件携带真实 Redis Stream ID，并作为 SSE id。
- [X] 前端只允许 SSE id / stream_id 更新断线续读游标，不再使用业务 event_id。
- [X] 前端区分服务端业务 error MessageEvent 与真正的 EventSource 连接错误。

## 3. 回归测试
- [X] 覆盖快照事件的 stream_id / SSE id。
- [X] 覆盖业务 event_id 不得成为 transport cursor。
- [X] 保持现有普通 SSE envelope 兼容行为。


## 4. 重连死循环补强
- [X] 业务错误不再使用 SSE 协议层 `event: error`，避免触发 EventSource 网络错误处理。
- [X] failed 快照改为默认 message 事件，内部 `event_type` 仍保持 `error`。
- [X] 前端仅接受 `数字-数字` 格式的 Redis Stream ID 作为续读游标。
- [X] `snapshot:GEN-...` 等业务 ID 一律拒绝作为续读游标。

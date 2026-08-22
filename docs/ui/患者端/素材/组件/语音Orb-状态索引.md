# 语音 Orb 状态索引

## 状态资产

| 状态 | 主色 | 推荐文字 | 原型位置 |
| --- | --- | --- | --- |
| idle | `#C4612F` | 点击开始说话 | AI 对话主屏待机 |
| connecting | `#4BA7A3` | 正在连接 | AI 对话连接态 |
| listening | `#4BA7A3` | 请说话 | AI 对话监听态 |
| transcribing / confirming | `#4BA7A3` | 请确认转写内容 | 转写确认卡 |
| thinking | `#5B8DEF` | AI 正在思考 | AI 回答态 |
| speaking | `#3DAD82` | AI 正在播报 | 可打断播报态 |
| interrupted | `#4BA7A3` | 已停止播报，请继续 | 患者打断后 |
| error / text_fallback | `#E5A146` | 语音异常，已切换文字 | 语音异常态 |
| paused | `#5B8DEF` | 已暂停 | 暂停后保留文字输入 |
| closed | `#756D66` | 语音已关闭 | 主动关闭语音 |

整组对照图使用 `语音Orb-状态集.svg`；状态颜色与文字不得只靠动画表达。

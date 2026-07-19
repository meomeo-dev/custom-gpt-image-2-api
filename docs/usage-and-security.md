# 用法、两端点完整参数、迁移与安全数据流

## 1. 节点总览(分类 `GPT-Image`)

| 节点(显示名) | 内部 key | 端点 | 作用 |
|----------------|----------|------|------|
| GPT-Image API 配置 (base_url + api_key) | `ImageAPIConfig` | — | 输出 `IMAGE_API_CONFIG`,即 `(base_url, api_key)` |
| GPT-Image 生成 (文生图) | `GPTImageGenerate` | `POST /images/generations` | 纯文本生图 |
| GPT-Image 编辑 (图生图) | `GPTImageEdit` | `POST /images/edits` | 1~8 张参考图 + 可选遮罩 |

连线:`GPT-Image API 配置` 的「配置」输出 → 生成/编辑节点的「配置」输入。一个配置节点可以连多个节点。**端点由你选哪个节点决定**,不再靠有无参考图隐式判断。

## 2. 请求如何构造(OpenAI Images API)

### 文生图 —— `POST {base_url}/images/generations`(JSON)

```json
{ "model": "gpt-image-2", "prompt": "...", "n": 1, "size": "auto" }
```

### 图生图 / 多参考图 —— `POST {base_url}/images/edits`(multipart/form-data)

- 文本字段:`model`、`prompt`、`n`、`size` 及下方启用的可选参数
- 参考图:重复的 `image[]` 文件字段(每张一个),本插件开放「图片1~图片8」
- 遮罩:连了「遮罩」时作为 `mask` 文件字段发送
- 不设置 `Content-Type`,由 HTTP 库自动生成 multipart 边界

## 3. 完整参数表

| 参数(节点标签) | 字段名 | 生成 | 编辑 | 取值 / 默认 |
|------------------|--------|:----:|:----:|-------------|
| 提示词 | `prompt` | ✅ | ✅ | 必填,≤32000 字符 |
| 模型 | `model` | ✅ | ✅ | 默认 `gpt-image-2`(可改) |
| 宽 / 高 | `size`(拼为 宽x高) | ✅ | ✅ | 两个 INT,**均为 0 = auto**;>0 时拼成 `宽x高` 发送。gpt-image-2 需 16 倍数、1:3~3:1、≤3840x2160;编辑端常见 `1024x1024/1536x1024/1024x1536` |
| 图片1 | `image[]` | — | ✅必填 | 第一张参考图 |
| 图片2~8 | `image[]` | — | 可选 | 追加参考图(最多 8) |
| 遮罩 | `mask` | — | 可选 | `MASK`;透明(选中)区域被编辑,alpha=(1-mask)*255 |
| 输入保真度 | `input_fidelity` | — | 可选 | `default`/`low`/`high`;**仅编辑端点**。`gpt-image-2` 忽略(恒为 high),`gpt-image-1.x` 生效 |
| 数量 | `n` | ✅ | ✅ | 1~10,默认 1 |
| 质量 | `quality` | ✅ | ✅ | `default`/`auto`/`high`/`medium`/`low` |
| 背景 | `background` | ✅ | ✅ | `default`/`auto`/`transparent`/`opaque` |
| 输出格式 | `output_format` | ✅ | ✅ | `default`/`png`/`jpeg`/`webp` |
| 压缩质量 | `output_compression` | ✅ | ✅ | 0~100,**仅输出 jpeg/webp 时发送**,默认 100 |
| 审核级别 | `moderation` | ✅ | ✅ | `default`/`auto`/`low` |
| 流式 | `stream` | ✅ | ✅ | 布尔,默认关;长耗时开启保活(见第 5 节) |
| 流式预览数 | `partial_images` | ✅ | ✅ | 0~3,默认 2;流式时中途预览张数 |
| 超时秒数 | (读取超时) | ✅ | ✅ | 默认 900(15min),上限 3600;采用 (连接15s, 读取N秒) 元组 |
| 重试次数 | (客户端重试) | ✅ | ✅ | 0~5,默认 2;瞬时错误(429/5xx/超时/连接重置)自动重试(见第 5 节) |

> **`default` 档 = 不发送该字段**,让服务端用其默认值。这样面对不支持某字段的 OpenAI 兼容网关时不会因未知参数报 400。`output_compression` 还额外要求 `output_format` 为 jpeg/webp 才发送。`stream`/`partial_images` 仅在勾选「流式」时才发送。`input_fidelity` 仅编辑端点发送。

### 参数×模型联动校验(发请求前)

节点在发请求前按「模型」校验参数组合(单一入口 `api_client._validate`),尽早以明确中文提示拦截会被服务端拒绝的组合,省一次昂贵/缓慢的 API 往返。策略是**已知官方模型硬校验、未知网关软放行**:

| 模型 | size 约束 | transparent | input_fidelity |
|------|-----------|-------------|----------------|
| `gpt-image-2` | 16 倍数、比例 ≤3:1、最长边 ≤3840、总像素 655360~8294400 | ❌ 不支持(提示改 1.5) | ❌ 忽略(恒 high) |
| `gpt-image-1.5` / `gpt-image-1` / `gpt-image-1-mini` | `1024x1024`/`1536x1024`/`1024x1536`/`auto` | ✅ 需 png/webp | ✅ 生效 |
| 其它(自定义网关模型名) | 仅 16 倍数软提示,不拦截 | 软放行(仅 +jpeg 因无透明通道仍拦截) | 原样发送 |

> `transparent` + `jpeg` 是物理冲突(jpeg 无 alpha 通道),对任何模型都直接报错。校验只改 `input_fidelity`(遇不支持的模型丢弃)、不改其它字段。规则见 `api_client.py` 的 `MODEL_RULES`,新增模型只需在表里加一行。

### 结果读取

- **优先** `data[0].b64_json`(GPT image 模型默认返回 base64)
- **回退** `data[0].url`(DALL-E 风格;仅当服务端返回 url 时才去下载)
- `n>1` 且各图尺寸一致时合并为一个 `[N,H,W,3]` 批次输出;尺寸不一致则只输出第一张并打印提示。

## 4. 安全与数据流(重点)

- **无预设网关**:代码中不含任何写死的域名,一切请求发往你在配置节点填写的 `base_url`。
- **无第三方图床**:参考图直接以 `image[]` multipart 发往 `{base_url}/images/edits`,不经中转。
- **无遥测 / 上报**:没有 telemetry / analytics / beacon / sentry,也没有 `eval` / `exec` / `subprocess` / `socket` 等隐蔽执行或网络逃逸。
- **密钥只出现在请求头**:`Authorization: Bearer <key>`,绝不写进任何日志。错误日志只截取服务端响应体前若干字符,且不含密钥。

### ⚠️ 你需要知道的残留风险

- **api_key 会随工作流保存**:配置节点的密钥是节点参数,会写进工作流 `.json`。**分享 / 上传 / 截图工作流会连同密钥一起泄露**。分享前请清空密钥或删掉配置节点。
- **base_url 决定数据去向**:密钥、提示词、参考图都会发给你填的地址。请只填你信任的服务端。
- 若服务端在响应里返回了 `url`,插件会去下载该 `url`(取回结果图片所必需);该地址由你的服务端控制。

## 5. 长耗时与保活

生图可能耗时数分钟到十几分钟。长时间无数据流动的连接容易被中间负载均衡/反向代理判空闲切断。三层应对:

1. **读取超时足够大**:节点「超时秒数」默认 900、上限 3600;`timeout=(15, N)`,连接 15s 快速失败、读取给足 N 秒。仅覆盖客户端自身。
2. **流式(官方保活机制,推荐)**:勾选「流式」→ 发送 `stream=true` + `partial_images`,服务端通过 SSE 分批推 `*.partial_image` 事件、最后 `*.completed` 带完整图。连接持续有数据流动,可越过中间代理的 idle timeout。插件解析:遍历 `data:` 行 JSON,按 `type` 取 `completed` 的 `b64_json`(取不到则用最后一个 partial 兜底)。**若响应 Content-Type 不是 `text/event-stream`(网关没按流式返回),自动回退普通 JSON 解析**,不会因开了流式而失败。
3. **TCP keepalive**:共享 `requests.Session` 上启用 `SO_KEEPALIVE`(+ 平台相关 `TCP_KEEPIDLE/INTVL/CNT`),维持 NAT/防火墙映射。对 L7 负载均衡的应用层 idle timeout 无效。
4. **瞬时错误重试(重试次数)**:遇 429/5xx/超时/连接重置时自动重试,**优先按服务端 `Retry-After` 头等待**,否则指数退避(`2^n` 秒,封顶 60s)。默认重试 2 次(总 3 次),0 关闭。**只重试「请求建立 + 首个状态码」阶段**——流式一旦开始迭代 SSE 就不再重试,避免半消费的流被重放;参考图以 bytes 传入,可安全跨重试重发。它兜的是"临时抖动",非法参数(400)不会重试。

> 端到端每层读超时都要 ≥ 生图时长。你能控本插件与自建网关;中间第三方 LB/nginx(`proxy_read_timeout` 等)不够大时,只有流式能保住连接。流式模式下多张(n>1)一般只回最终一张。

## 6. 迁移说明

### 从最初的 nerapi.com 版本
| 旧 | 现在 |
|----|------|
| 写死 `https://nerapi.com/v1` + 私有异步协议 `/api/generate` + 轮询 + 第三方图床 | 标准 OpenAI `/images/generations` 与 `/images/edits`,无预设网关 |
| Nano-Banana(nano-banana-pro/2)节点 | 已移除 |

### 从 2.0(单节点自动切换)到 3.0(拆两个节点)
- 旧的单个「GPT-Image-2」节点靠"有没有连参考图"自动切换端点;3.0 拆成 **GPT-Image 生成** 与 **GPT-Image 编辑** 两个节点,端点显式可选。
- 打开旧工作流后:按需替换为对应节点,重新连「配置」,并设置新增的 `quality/background/output_format/...` 等参数(留 `default` 即保持旧行为)。

## 7. 命令行自测

见 `test_api.py`(`--base` 与 `--key` 必填,无预设地址),支持 `--image`(可重复)、`--mask`、`--quality`、`--background`、`--output-format` 等,先验证服务端连通性再进 ComfyUI。

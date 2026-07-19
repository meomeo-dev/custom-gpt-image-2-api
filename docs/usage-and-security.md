# 用法、两端点完整参数、迁移与安全数据流

## 1. 节点总览(分类 `GPT-Image`)

| 节点(显示名) | 内部 key | 端点 | 作用 |
|----------------|----------|------|------|
| GPT-Image API 配置 (base_url + api_key) | `ImageAPIConfig` | — | 输出 `IMAGE_API_CONFIG`,即 `(base_url, api_key)` |
| GPT-Image 生成 (文生图) | `GPTImageGenerate` | `POST /images/generations` | 纯文本生图 |
| GPT-Image 编辑 (图生图) | `GPTImageEdit` | `POST /images/edits` | 1~8 张参考图 + 可选遮罩 |
| GPT-Image 尺寸规范化 (16倍数/边长) | `GPTImageSizeSnap` | — | 宽/高圆整到步长(默认16)倍数并 clamp 到 [最小边,最大边],输出 `宽`/`高` 两个 INT |

连线:`GPT-Image API 配置` 的「配置」输出 → 生成/编辑节点的「配置」输入。一个配置节点可以连多个节点。**端点由你选哪个节点决定**,不再靠有无参考图隐式判断。

**尺寸规范化节点用法**:把 `GPTImageSizeSnap` 的 `宽`/`高` 输出连到生成/编辑节点的「宽/高」输入(在生成/编辑节点上右键把「宽」「高」widget 转为 input 接口即可)。它只处理「步长倍数 + 边长范围」,把用户随手填的值吸附成合法尺寸;比例(1:3~3:1)与总像素范围仍由发请求前的 `_validate` 校验。核心逻辑见 `api_client.snap_dim`。

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

## 6. 中断、缓存与多工作流隔离

### 6.1 可中断(点 Cancel 能停)

ComfyUI 的中断是**协作式轮询 (cooperative polling)**:点 Cancel 只是把一个全局标志置真,节点必须**主动调用** `comfy.model_management.throw_exception_if_processing_interrupted()` 才会停下。单次阻塞的 `requests.post()` 会把线程挂在 OS 网络层、期间无任何 Python 代码执行,标志读不到——所以早期版本点了 Cancel 也要死等请求返回(对十几分钟的生图形同无法停止)。

现在的做法:把 HTTP 请求放进 **daemon 线程**,主线程**每 500ms 轮询一次**中断标志;流式模式则在每次 SSE 迭代间隙检查。中断时立即抛 `InterruptProcessingException`(它继承 `BaseException`,能穿透 `except Exception`,不会被重试逻辑误吞)。在 ComfyUI 外独立运行(`test_api.py` / 单测)时,`comfy` 模块不可用,自动降级为 no-op。

### 6.2 每次都真正调用 API(禁用输出缓存)

两个生图节点定义了 `IS_CHANGED` 恒返回 `float("nan")`。ComfyUI 默认按输入哈希缓存节点输出——相同 prompt/参数再次运行会**直接复用上次的图、根本不发请求**。但 API 生图是不确定的(同 prompt 每次结果不同),故本插件**禁用该缓存**,保证每次都真正向服务端请求、各自算各自的图。配置节点与尺寸规范化节点是纯确定性的,不加此项。

### 6.3 ⚠️ 多工作流「节点 id 碰撞」显示串台(ComfyUI 自身限制,非本插件可修)

**现象**:同一个 ComfyUI 服务上开两个工作流 A、B,生成/编辑节点的输出会互相覆盖——谁最后生成,两个工作流都显示谁的图。

**根因**(已核对 ComfyUI 源码):ComfyUI 全进程共享**唯一**的输出缓存 `caches.outputs`,以节点 `unique_id`(工作流 JSON 里的节点 id)为键、**不按工作流/标签分区**;前端也按 node id 认领预览图。而 litegraph 的节点 id 在单个图内从 1,2,3… 递增,两个各自新建(或"另存为"复制)的工作流**天然含相同 id**,于是在同一个缓存槽位上互相覆盖。对应上游 issue:[comfyanonymous/ComfyUI#6581](https://github.com/comfyanonymous/ComfyUI/issues/6581)。

**这不是本插件能在自身代码修掉的**——任何节点(含内置 `SaveImage`/`PreviewImage`)在 id 碰撞下都一样。`IS_CHANGED`(见 6.2)能保证两个工作流**确实各自发了请求**,但消除不了 ComfyUI 层面的显示串台。

**规避**:① 让两个工作流的节点 id 不重叠(**重建**其一,别用"另存为"复制;或前端手动改 id);② 一次只跑一个工作流,或把任务放进同一标签的队列串行跑;③ 最稳:开两个 ComfyUI 实例(不同 `--port`),缓存与队列各自独立。

**自查是否 id 碰撞**:导出两个工作流 `.json`,搜出问题节点的 `"id"` 字段,若相同即实锤;或只开一个工作流跑,现象消失即可佐证。

## 7. 迁移说明

### 从最初的 nerapi.com 版本
| 旧 | 现在 |
|----|------|
| 写死 `https://nerapi.com/v1` + 私有异步协议 `/api/generate` + 轮询 + 第三方图床 | 标准 OpenAI `/images/generations` 与 `/images/edits`,无预设网关 |
| Nano-Banana(nano-banana-pro/2)节点 | 已移除 |

### 从 2.0(单节点自动切换)到 3.0(拆两个节点)
- 旧的单个「GPT-Image-2」节点靠"有没有连参考图"自动切换端点;3.0 拆成 **GPT-Image 生成** 与 **GPT-Image 编辑** 两个节点,端点显式可选。
- 打开旧工作流后:按需替换为对应节点,重新连「配置」,并设置新增的 `quality/background/output_format/...` 等参数(留 `default` 即保持旧行为)。

## 8. 命令行自测

见 `test_api.py`(`--base` 与 `--key` 必填,无预设地址),支持 `--image`(可重复)、`--mask`、`--quality`、`--background`、`--output-format` 等,先验证服务端连通性再进 ComfyUI。

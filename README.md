# custom-gpt-image-2-api

在 ComfyUI 里用 **GPT-Image**(`gpt-image-2` 等 OpenAI 兼容图像模型)做**文生图**与**图生图/多参考图编辑**。请求走**你自己配置的 OpenAI 兼容接口**(自定义 `base_url` + `api_key`),插件本身不含任何预设网关。

## 四个节点(分类 `GPT-Image`)

| 显示名 | 内部 key | 端点 | 作用 |
|--------|----------|------|------|
| GPT-Image API 配置 (base_url + api_key) | `ImageAPIConfig` | — | 输出 `IMAGE_API_CONFIG`,即 `(base_url, api_key)`,可复用到多个节点 |
| GPT-Image 生成 (文生图) | `GPTImageGenerate` | `POST /images/generations` | 纯文本生图 |
| GPT-Image 编辑 (图生图) | `GPTImageEdit` | `POST /images/edits` | 带 1~8 张参考图 + 可选遮罩的编辑 |
| GPT-Image 尺寸规范化 (16倍数/边长) | `GPTImageSizeSnap` | — | 把随手填的宽/高圆整到 16 倍数并限制边长范围,输出 `宽`/`高` 两个 INT |

端点由**你选哪个节点**显式决定,不再靠"有没有连参考图"隐式判断。

## 功能特点

- **自定义接口**:`base_url` 和 `api_key` 完全由你填写,一个配置节点可连多个生成/编辑节点
- **参数齐全**:`size / n / quality / background / output_format / output_compression / moderation`,编辑节点另有 `image[]`(最多 8 张)、`mask`(遮罩)
- **OpenAI 兼容**:任何兼容 OpenAI 图像接口的服务都能用
- **界面中文**:所有参数标签中文显示
- **无第三方外发**:密钥 / 提示词 / 图片只发往你配置的 `base_url`,无图床中转、无遥测

## 安装

按 ComfyUI 官方文档,手动 `git clone` 到 `custom_nodes`,并用 **ComfyUI 自己的 Python 环境**装依赖:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/meomeo-dev/custom-gpt-image-2-api.git
# 用 ComfyUI 的 python 装依赖(不要污染系统环境)
# venv 手动安装:
cd custom-gpt-image-2-api && pip install -r requirements.txt
# 秋叶/便携整合包:
#   ..\..\python_embeded\python.exe -m pip install -r requirements.txt
```

装完**重启 ComfyUI** 并刷新浏览器。启动日志里搜 `custom-gpt-image-2-api`,确认没有 `import failed`。

## 使用

1. 添加 **GPT-Image API 配置** 节点,填 **接口地址**(`base_url`,通常带 `/v1`)和 **密钥**(`api_key`)。
2. 把它的 **配置** 输出连到 **GPT-Image 生成** 或 **GPT-Image 编辑** 的 **配置** 输入。
3. 填参数(见下表),输出「图像」接 Preview / Save Image。

### 参数一览

| 参数 | 生成 | 编辑 | 取值 / 说明 |
|------|:----:|:----:|------|
| 提示词 prompt | ✅ | ✅ | 图片描述,必填 |
| 模型 model | ✅ | ✅ | 默认 `gpt-image-2`,可改 |
| 宽 / 高 | ✅ | ✅ | 两个数字框,**均为 0 = auto**;填具体值即自定义 `宽x高`。gpt-image-2 需 16 的倍数、1:3~3:1、≤3840x2160;编辑端常见 `1024x1024/1536x1024/1024x1536` |
| 图片1 | — | ✅ 必填 | 第一张参考图 |
| 图片2~8 | — | 可选 | 追加参考图(共最多 8 张) |
| 遮罩 mask | — | 可选 | `MASK` 输入;透明(选中)区域会被编辑 |
| 输入保真度 input_fidelity | — | 可选 | `default`/`low`/`high`;参考图保真度。**仅编辑端点**,且 `gpt-image-2` 会忽略(恒为 high) |
| 数量 n | ✅ | ✅ | 1~10,多张尺寸一致时合并为批次 |
| 质量 quality | ✅ | ✅ | `default`/`auto`/`high`/`medium`/`low` |
| 背景 background | ✅ | ✅ | `default`/`auto`/`transparent`/`opaque` |
| 输出格式 output_format | ✅ | ✅ | `default`/`png`/`jpeg`/`webp` |
| 压缩质量 output_compression | ✅ | ✅ | 0~100,**仅当输出格式为 jpeg/webp 时发送** |
| 审核级别 moderation | ✅ | ✅ | `default`/`auto`/`low` |
| 流式 stream | ✅ | ✅ | 布尔,默认关;长耗时(如 10min)建议开启保活,见下节 |
| 流式预览数 partial_images | ✅ | ✅ | 0~3,流式时中途推送的预览张数(越多越利于保活) |
| 超时秒数 timeout | ✅ | ✅ | 读取超时,默认 900(15min),上限 3600(60min) |
| 重试次数 | ✅ | ✅ | 0~5,默认 2;遇 429/5xx/超时/连接重置自动重试,见下节 |

> 枚举参数选 `default` 时**不发送该字段**,由服务端用默认值——避免给不支持该字段的网关塞未知参数导致 400。

### 参数×模型联动校验(发请求前,省一次昂贵往返)

节点在**真正发请求前**按「模型」校验参数组合是否合法,发现问题给出明确中文提示:

- **已知官方模型**(`gpt-image-2` / `gpt-image-1.5` / `gpt-image-1` / `gpt-image-1-mini`):**硬校验**,违规直接报错。
  - `gpt-image-2` 尺寸须满足:16 的倍数、长短边比 ≤3:1、最长边 ≤3840、总像素 655360~8294400。
  - `gpt-image-1.x` 尺寸限 `1024x1024 / 1536x1024 / 1024x1536 / auto`。
  - `gpt-image-2` **不支持透明背景**(会提示改用 `gpt-image-1.5` + png/webp),也**不接受** `input_fidelity`(选了自动忽略)。
  - `background=transparent` 与 `output_format=jpeg` 冲突(jpeg 无透明通道),直接报错。
- **未知模型名**(你的自定义兼容网关):一律**软放行**,只打印警告不拦截,保住网关兼容性。

> 联动全在执行期校验完成(节点本身不加复杂 UI),你无需背模型×参数兼容矩阵——配错时节点会告诉你哪个参数和哪个冲突、怎么改。

## 长耗时与保活(生图很慢时必看)

单张生图可能耗时数分钟到十几分钟。若中间隔着负载均衡/反向代理,长时间"没有数据流动"的连接会被判空闲(idle timeout)而切断。应对:

1. **调大超时**:节点「超时秒数」默认已是 900s(15min),不够就调到上限 3600s。这只解决客户端自己的读超时,解决不了中间设备。超时采用 `(连接15s, 读取N秒)`,连接阶段仍会快速失败。
2. **开启「流式」(推荐,官方保活机制)**:勾选「流式」后插件发送 `stream=true` + `partial_images`,服务端在生成过程中通过 SSE 分批推送预览事件,连接**持续有数据流动**,能避免中间代理的空闲超时。最终图从 `*.completed` 事件取。若你的网关未按 SSE 返回,插件会自动回退按普通 JSON 解析。
3. **TCP keepalive(自动)**:连接默认开启 `SO_KEEPALIVE`,帮助维持 NAT/防火墙映射;但这是传输层探活,对**应用层 L7 负载均衡的空闲超时无效**,那种只能靠流式。

> 端到端每一层的读超时都要 ≥ 生图时长:你能控的是本插件和你的网关;若中间还有别人的 LB/nginx(如 `proxy_read_timeout`),它们不够大时只有流式能救。

## 可中断 / 不缓存 / 多工作流隔离

- **点 Cancel 能停**:HTTP 请求放在后台线程,主线程每 500ms 轮询 ComfyUI 中断标志;生图中途点取消可及时停止(早期阻塞版本停不下来)。
- **每次都真正生图**:两个生图节点用 `IS_CHANGED=NaN` 禁用 ComfyUI 输出缓存——相同 prompt 不会复用上次的图,始终重新请求 API(生图是不确定的)。
- **⚠️ 同服务多工作流会显示串台**:两个工作流若含**相同节点 id**(常见于"另存为"复制),ComfyUI 会因按 node id 全局缓存/路由而让它们互相覆盖显示(谁最后生成两边都变谁的)。这是 [ComfyUI 自身限制 #6581](https://github.com/comfyanonymous/ComfyUI/issues/6581),非本插件可修。规避:重建其一让 id 不重叠、串行跑、或开两个 ComfyUI 实例(不同 `--port`)。详见 [`docs/usage-and-security.md`](docs/usage-and-security.md) 第 6 节。

## 图生图 / 多参考图如何工作

编辑节点把参考图直接作为 multipart 的 `image[]` 文件 **POST 到 `{base_url}/images/edits`**,不经过任何第三方图床、不做 base64 中转。GPT image 系列最多支持 16 张,本节点开放 8 个输入口。连了「遮罩」时会作为 `mask` 文件一并发送。

## 快速测试(不进 ComfyUI)

```bash
pip install requests
# 文生图
python test_api.py --base https://your-endpoint/v1 --key sk-你的key --model gpt-image-2 --prompt "一只戴墨镜的柴犬"
# 图生图 / 多参考图
python test_api.py --base https://your-endpoint/v1 --key sk-你的key --model gpt-image-2 --prompt "把这些拼成海报" --image a.png --image b.png
```

成功会把图存成 `test_output.png`。401 一般是 key 错误,400 多为模型名 / 参数不被服务端接受。

## 安全说明(数据流向)

- 请求只发往你在配置节点填写的 `base_url`;代码里没有任何预设域名、没有第三方图床、没有遥测 / 数据上报。
- **密钥会随工作流保存**:`api_key` 作为节点参数会写进工作流的 `.json`,**分享工作流会连同密钥一起泄露**。分享前请清空密钥或删掉配置节点。
- 详见 [`docs/usage-and-security.md`](docs/usage-and-security.md)。

## 开发文档

- [`docs/comfyui-custom-node-development.md`](docs/comfyui-custom-node-development.md):ComfyUI 自定义节点开发规范(调研落盘)
- [`docs/usage-and-security.md`](docs/usage-and-security.md):用法、两端点完整参数、迁移与安全数据流

## License

MIT

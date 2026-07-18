# 用法、OpenAI 参数、迁移与安全数据流

## 1. 节点总览

| 节点（显示名） | 内部 key | 作用 |
|----------------|----------|------|
| 图像 API 配置 (base_url + api_key) | `ImageAPIConfig` | 输出 `IMAGE_API_CONFIG`，即 `(base_url, api_key)` |
| GPT-Image-2 | `GPTImage2Node` | 用 `gpt-image-2`（可改模型名）生图 |
| Nano-Banana | `NanoBananaNode` | 用 `nano-banana-pro` / `nano-banana-2` 生图 |

连线：`图像 API 配置` 的「配置」输出 → 生成节点的「配置」输入。一个配置节点可以连多个生成节点。

## 2. 请求如何构造（OpenAI Images API）

生成节点根据是否接了参考图，二选一：

### 文生图 —— `POST {base_url}/images/generations`（JSON）

```json
{ "model": "gpt-image-2", "prompt": "...", "n": 1, "size": "auto" }
```

### 图生图 / 多参考图 —— `POST {base_url}/images/edits`（multipart/form-data）

- 表单字段：`model`、`prompt`、`n`、`size`
- 参考图：重复的 `image[]` 文件字段（每张一个），本插件开放「图片1~图片8」
- 不设置 `Content-Type`，由 HTTP 库自动生成 multipart 边界

### 参数取值

| 参数 | 说明 |
|------|------|
| `model` | GPT-Image-2 默认 `gpt-image-2`（STRING 可改）；Nano-Banana 下拉 `nano-banana-pro` / `nano-banana-2` |
| `size` | 默认 `auto`。常见：`1024x1024` / `1536x1024`（横）/ `1024x1536`（竖）。`gpt-image-2` 支持任意 `宽x高`（16 的倍数，长宽比 1:3~3:1，最大 3840x2160）。实际取值以你的服务端支持为准 |
| `n` | 生成张数 1-10（`dall-e-3` 只支持 1）。多张且尺寸一致时合并为一个批次输出 |
| 超时秒数 | 单次 HTTP 请求超时；OpenAI 图像接口是同步返回，无需轮询 |

### 结果读取

- **优先** `data[0].b64_json`（GPT image 模型默认返回 base64）
- **回退** `data[0].url`（DALL-E 风格；仅当服务端返回 url 时才去下载）

## 3. 安全与数据流（重点）

本次改造的核心之一是杜绝密钥 / 提示词 / 图片外泄。审计与治理结论：

- **无预设网关**：代码中不含任何写死的域名，一切请求发往你在配置节点填写的 `base_url`。
- **无第三方图床**：旧版参考图要先 `POST /api/upload-token` 换凭证再上传到服务端返回的图床地址（服务端可指定上传目标，属潜在外发向量）。现已删除，参考图直接以 `image[]` multipart 发往 `{base_url}/images/edits`。
- **无遥测 / 上报**：代码里没有 telemetry / analytics / beacon / sentry，也没有 `eval` / `exec` / `subprocess` / `socket` 等隐蔽执行或网络逃逸。
- **密钥只出现在请求头**：`Authorization: Bearer <key>`，绝不写进任何日志。错误日志只截取服务端响应体前若干字符，且不含密钥。

### ⚠️ 你需要知道的残留风险

- **api_key 会随工作流保存**：配置节点的密钥是节点参数，会写进工作流 `.json`。**分享 / 上传 / 截图工作流会连同密钥一起泄露**。分享前请清空密钥或删掉配置节点。
- **base_url 决定数据去向**：密钥、提示词、参考图都会发给你填的地址。请只填你信任的服务端；填错域名等于把这些数据发给了那个域名。
- 若服务端在响应里返回了 `url`，插件会去下载该 `url`（这是取回结果图片所必需）；该地址由你的服务端控制。

## 4. 从旧版（nerapi.com）迁移

| 旧版 | 现在 |
|------|------|
| 每个节点内填「密钥」「接口地址」，默认 `https://nerapi.com/v1` | 统一由「图像 API 配置」节点提供，无默认值 |
| 私有异步协议：`/api/generate` 提交 + `/api/result` 轮询 | 标准 OpenAI 同步接口 `/images/generations` |
| 参考图走 `/api/upload-token` + 第三方图床 | 参考图直接 `image[]` 发往 `/images/edits` |
| 「比例」「清晰度(1K/2K/4K)」下拉 | 统一用 OpenAI 的 `size`（本插件的「尺寸」） |
| 前端 JS 过滤比例下拉 | 已移除，无需前端扩展 |

打开旧工作流后：新增配置节点并连线，删除已不存在的「比例」「清晰度」等参数节点报错项，重新填写「尺寸」。

## 5. 命令行自测

见 `test_api.py`（`--base` 与 `--key` 必填，无预设地址），可先验证服务端连通性，再进 ComfyUI。

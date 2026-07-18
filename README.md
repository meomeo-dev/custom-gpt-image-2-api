# ComfyUI-Nerapi

在 ComfyUI 里用 **Nano-Banana**（nano-banana-pro / nano-banana-2）和 **GPT-Image-2** 生图与图生图。请求走**你自己配置的 OpenAI 兼容接口**（自定义 `base_url` + `api_key`），插件本身不含任何预设网关。

> 2.0 重要变更：已移除写死的 `nerapi.com` 网关与私有异步协议，改为标准 **OpenAI Images API**（`/images/generations` + `/images/edits`）。接口地址和密钥现在通过独立的「图像 API 配置」节点提供。旧工作流需要重连（见文末迁移说明）。

## 功能特点

- **三个节点**：`图像 API 配置`、`GPT-Image-2`、`Nano-Banana`
- **自定义接口**：`base_url` 和 `api_key` 完全由你填写，一个配置节点可复用到多个生成节点
- **文生图 + 图生图**：无参考图走 `/images/generations`；接了参考图（最多 8 张）走 `/images/edits`，通过 `image[]` 传多图
- **OpenAI 兼容**：任何兼容 OpenAI 图像接口的服务都能用
- **界面中文**：所有参数标签中文显示
- **无第三方外发**：密钥 / 提示词 / 图片只发往你配置的 `base_url`，无图床中转、无遥测

## 安装

把整个文件夹放到 ComfyUI 的 `custom_nodes/` 目录，安装依赖后重启：

```bash
git clone https://github.com/Guguniaoer/ComfyUI-Nerapi.git
cd ComfyUI/custom_nodes/ComfyUI-Nerapi
pip install -r requirements.txt
```

> 用整合包（如秋叶）的话，`pip` 要用整合包自带的 Python，例如 `python_embeded\python.exe -m pip install -r requirements.txt`。

## 使用

节点都在 **`Nano-Banana / GPT-Image`** 分类下。

1. 添加 **图像 API 配置** 节点，填写：
   - **接口地址**（`base_url`）：你的 OpenAI 兼容服务地址，通常带 `/v1`，例如 `https://your-endpoint.example.com/v1`
   - **密钥**（`api_key`）：你的 API Key
2. 把它的 **配置** 输出连到 **GPT-Image-2** 或 **Nano-Banana** 节点的 **配置** 输入（一个配置可以连多个生成节点）。
3. 生成节点填写：
   - **提示词**：图片描述
   - **模型**：GPT-Image-2 默认 `gpt-image-2`（可改）；Nano-Banana 可选 `nano-banana-pro` / `nano-banana-2`
   - **尺寸**（`size`）：默认 `auto`；也可填 `1024x1024`、`1536x1024`、`1024x1536` 等（取值以你的服务端支持为准，gpt-image-2 支持任意 `宽x高`）
   - 可选：**图片1~图片8**（参考图，接了就走图生图 `/images/edits`）、**数量**（1-10）、**超时秒数**
4. 输出「图像」直接接 Preview / Save Image。

## 参考图（图生图）如何工作

接了「图片」输入时，节点会把这些图片直接作为 multipart 的 `image[]` 文件 **POST 到你配置的 `{base_url}/images/edits`**。不经过任何第三方图床，也不做 base64 上传中转。GPT image 系列模型最多支持 16 张参考图，本节点开放 8 个输入口。

## 快速测试（不进 ComfyUI）

用 `test_api.py` 先验证接口和密钥通不通：

```bash
pip install requests
# 文生图
python test_api.py --base https://your-endpoint/v1 --key sk-你的key --model gpt-image-2 --prompt "一只戴墨镜的柴犬"
# 图生图 / 多参考图
python test_api.py --base https://your-endpoint/v1 --key sk-你的key --model nano-banana-pro --prompt "把这些拼成海报" --image a.png --image b.png
```

成功会把图存成 `test_output.png`。401 一般是 key 错误，400 多为模型名 / 参数不被服务端接受。

## 安全说明（数据流向）

- 请求只发往你在配置节点填写的 `base_url`；插件代码里没有任何预设域名、没有第三方图床、没有遥测 / 数据上报。
- **密钥会随工作流保存**：`api_key` 作为节点参数会写进工作流的 `.json`，**分享工作流会连同密钥一起泄露**。分享前请清空密钥或替换配置节点。
- 详见 [`docs/usage-and-security.md`](docs/usage-and-security.md)。

## 从旧版（nerapi.com）迁移

旧版把接口写死在 `nerapi.com` 并在每个节点内填密钥/接口地址。2.0 之后：

- 旧的「密钥」「接口地址」内联输入已移除，改由 **图像 API 配置** 节点统一提供。
- 请求协议从私有异步接口（`/api/generate` + 轮询 + 图床上传）改为标准 OpenAI 接口。
- 旧工作流打开后需要：新增配置节点、把「配置」连到生成节点、删掉不再存在的「比例」「清晰度」参数。

## 开发文档

- [`docs/comfyui-custom-node-development.md`](docs/comfyui-custom-node-development.md)：ComfyUI 自定义节点开发规范（调研落盘）
- [`docs/usage-and-security.md`](docs/usage-and-security.md)：用法、OpenAI 参数、迁移与安全数据流

## License

MIT

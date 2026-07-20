# ComfyUI 自定义节点开发规范（调研落盘）

本文整理 ComfyUI 自定义节点（custom node）的开发约定，供本插件维护参考。内容基于 ComfyUI 官方文档（见文末来源）。

## 1. 目录与注册

一个自定义节点包放在 `ComfyUI/custom_nodes/<你的包>/` 下，通过顶层 `__init__.py` 暴露两个字典：

```python
NODE_CLASS_MAPPINGS = {           # 内部唯一 key -> 节点类
    "MyNode": MyNode,
}
NODE_DISPLAY_NAME_MAPPINGS = {    # 内部 key -> 菜单里显示的名字（可选）
    "MyNode": "My Node",
}
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
```

- `NODE_CLASS_MAPPINGS` 的 key 是节点的**内部标识**，会写进工作流 `.json`。改 key 会导致旧工作流找不到节点。
- 类必须「在包级别可用」，即能从 `__init__.py` 导入到。
- 改动后需**重启 ComfyUI** 才能生效。

## 2. 节点类必需的四个属性

官方文档明确「一个节点类必须包含这四样」：

| 属性 | 作用 |
|------|------|
| `INPUT_TYPES` | `@classmethod`，返回描述输入的字典 |
| `RETURN_TYPES` | 元组，声明输出的数据类型 |
| `FUNCTION` | 字符串，执行时调用的方法名 |
| `CATEGORY` | 字符串，决定节点在「添加节点」菜单里的位置（可用 `a/b` 表示子菜单） |

可选属性：`RETURN_NAMES`（输出标签，缺省用类型名小写）、`OUTPUT_NODE`（默认 `False`，设 `True` 影响缓存/执行）、`IS_CHANGED`（控制缓存，返回值与上次比较，不同则重跑；返回 `float("NaN")` 强制每次执行）、`VALIDATE_INPUTS`、`SEARCH_ALIASES`。

## 3. INPUT_TYPES 结构

返回一个字典，**必须含 `required`**，可选含 `optional` / `hidden`：

```python
@classmethod
def INPUT_TYPES(cls):
    return {
        "required": {
            "文本": ("STRING", {"default": "", "multiline": True}),
            "模式": (["a", "b", "c"], {"default": "a"}),   # 列表 = 下拉选择
        },
        "optional": {
            "图片": ("IMAGE",),                             # 可以不连线
        },
    }
```

- 每个输入是一个元组：第一项是**类型**（字符串，或表示下拉的列表），第二项是参数字典（`default` / `multiline` / `min` / `max` / `step` / `placeholder` 等）。
- `optional` 的输入允许不连线，因此代码里要给默认值或用 `**kwargs` 兜底。
- 因为是 classmethod，下拉选项可以在运行时动态计算。

## 4. FUNCTION 方法与返回值

- 方法名由 `FUNCTION` 指定，参数名与 `INPUT_TYPES` 的 key 对应（ComfyUI 以关键字方式传入）。
- **必须返回一个元组**，元素个数与 `RETURN_TYPES` 一致。单输出别忘了逗号：`return (result,)`。
- 图像相关：ComfyUI 里 `IMAGE` 表示**图像批次**，张量形状 `[B,H,W,C]`，单张图是 `B=1` 的批次；数值为 0-1 的 float。单张要 `unsqueeze(0)` 补上批次维。

## 5. 节点之间的数据类型

- 类型用**字符串标识**匹配：输出声明的类型字符串必须与下游输入的类型字符串一致才能连线。
- 自定义类型直接用一个自定义字符串即可，例如本插件用 `IMAGE_API_CONFIG` 表示 `(base_url, api_key)` 配置对象。配置节点 `RETURN_TYPES = ("IMAGE_API_CONFIG",)`，生成节点 `"required": {"配置": ("IMAGE_API_CONFIG",)}`，两端字符串一致即可连线。
- 前端支持用逗号声明多类型输入，如 `"INT,FLOAT"`。

## 6. 前端扩展（可选）

如果需要客户端 JavaScript，在 `__init__.py` 导出 `WEB_DIRECTORY` 并加入 `__all__`：

```python
WEB_DIRECTORY = "./web"     # 目录里放 .js
__all__ = ["NODE_CLASS_MAPPINGS", "WEB_DIRECTORY"]
```

JS 侧用 `app.registerExtension({...})` 注册；后端可通过 `PromptServer.instance.send_sync(type, payload)` 向前端推消息，前端用 `app.api.addEventListener` 监听、从 `event.detail` 读取。

> 本插件用一个前端扩展（`web/gpt_image_config_security.js`）把配置节点「密钥」widget 的 `serialize` 关掉，使 `api_key` 不写进保存/导出的工作流 JSON（防分享泄露），故 `__init__.py` 导出了 `WEB_DIRECTORY = "./web"` 并加入 `__all__`。

## 7. 打包与发布（pyproject.toml）

发布到 Comfy Registry 需要 `pyproject.toml`，关键字段：

```toml
[project]
name = "..."
description = "..."
version = "x.y.z"
license = { text = "MIT" }
requires-python = ">=3.9"
dependencies = ["requests", "Pillow", "numpy"]

[tool.comfy]
PublisherId = "your-publisher-id"
DisplayName = "..."
```

`.github/workflows/publish.yml` 里用 `Comfy-Org/publish-node-action` 在 push `pyproject.toml` 时自动发布。

## 8. 本插件的落地映射

| 规范点 | 本插件实现 |
|--------|-----------|
| 注册 | `__init__.py` 注册 `ImageAPIConfig` / `GPTImageGenerate` / `GPTImageEdit` |
| 自定义类型 | `IMAGE_API_CONFIG = (base_url, api_key)` |
| 四个必需属性 | 各节点均有 `INPUT_TYPES` / `RETURN_TYPES` / `FUNCTION` / `CATEGORY` |
| IMAGE 处理 | `api_client.py` 里 `tensor_to_png_bytes` / `bytes_to_tensor` 处理 `[B,H,W,C]` |
| 前端 JS | `web/gpt_image_config_security.js`：关闭配置节点「密钥」widget 的 `serialize`，使 api_key 不写进保存/导出的工作流（防分享泄露），故导出了 `WEB_DIRECTORY` |

## 来源

- ComfyUI Docs — Backend / Server overview: https://docs.comfy.org/custom-nodes/backend/server_overview
- ComfyUI Docs — Walkthrough: https://docs.comfy.org/custom-nodes/walkthrough

# -*- coding: utf-8 -*-
"""配置节点 (config node)：让用户自定义 base_url 与 api_key。

输出自定义类型 IMAGE_API_CONFIG (一个 (base_url, api_key) 元组)，
连接到生成节点的「配置」输入，即可「设置一次，多个节点复用」。

安全提示 (security note)：api_key 作为 widget 会随工作流 .json 一起保存，
分享工作流时会连同密钥一起泄露，请自行注意。
"""


class ImageAPIConfig:
    """GPT-Image API 配置：自定义 base_url + api_key。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # 无任何预设值，完全由用户填写自己的 API 地址。
                "接口地址": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "https://your-endpoint.example.com/v1",
                }),
                "密钥": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "sk-...",
                }),
            },
        }

    RETURN_TYPES = ("IMAGE_API_CONFIG",)
    RETURN_NAMES = ("配置",)
    FUNCTION = "build"
    CATEGORY = "GPT-Image"

    def build(self, **kw):
        base_url = (kw.get("接口地址") or "").strip().rstrip("/")
        api_key = (kw.get("密钥") or "").strip()
        if not base_url:
            raise ValueError("[GPT-Image] 接口地址(base_url) 不能为空，请填写你自己的 API 地址，"
                             "例如 https://your-endpoint.example.com/v1")
        if not (base_url.startswith("http://") or base_url.startswith("https://")):
            raise ValueError("[GPT-Image] 接口地址必须以 http:// 或 https:// 开头。")
        if not api_key:
            raise ValueError("[GPT-Image] 密钥(api_key) 不能为空。")
        return ((base_url, api_key),)

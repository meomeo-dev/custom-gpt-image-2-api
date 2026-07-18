# -*- coding: utf-8 -*-
"""Nano-Banana 节点：通过用户自定义的 OpenAI 兼容接口生图。

- 无参考图 -> POST {base}/images/generations (文生图)
- 有参考图 -> POST {base}/images/edits    (多参考图，最多 8 张)
接口地址与密钥来自「图像 API 配置」节点，本节点不含任何预设网关。
"""
from . import api_client


NANO_MODELS = ["nano-banana-pro", "nano-banana-2"]


class NanoBananaNode:
    """用 nano-banana-pro / nano-banana-2 文生图 / 图生图（OpenAI 兼容接口）。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "配置": ("IMAGE_API_CONFIG",),
                "提示词": ("STRING", {"default": "", "multiline": True}),
                "模型": (NANO_MODELS, {"default": "nano-banana-pro"}),
                "尺寸": ("STRING", {"default": "auto"}),
            },
            "optional": {
                "图片1": ("IMAGE",),
                "图片2": ("IMAGE",),
                "图片3": ("IMAGE",),
                "图片4": ("IMAGE",),
                "图片5": ("IMAGE",),
                "图片6": ("IMAGE",),
                "图片7": ("IMAGE",),
                "图片8": ("IMAGE",),
                "数量": ("INT", {"default": 1, "min": 1, "max": 10, "step": 1}),
                "超时秒数": ("INT", {"default": 300, "min": 30, "max": 1800, "step": 10}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("图像",)
    FUNCTION = "generate"
    CATEGORY = "Nano-Banana / GPT-Image"

    def generate(self, **kw):
        refs = [kw.get("图片%d" % i) for i in range(1, 9)]
        img = api_client.run(
            config=kw.get("配置"),
            model=kw.get("模型", "nano-banana-pro"),
            prompt=kw.get("提示词", ""),
            size=kw.get("尺寸", "auto"),
            n=kw.get("数量", 1),
            image_batches=refs,
            timeout=kw.get("超时秒数", 300),
        )
        return (img,)

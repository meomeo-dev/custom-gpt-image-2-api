# -*- coding: utf-8 -*-
"""尺寸规范化节点 (size snapping)：把用户随手填的宽/高，规范成「步长的倍数」
且落在 [最小边, 最大边] 内的合法尺寸，再喂给生成/编辑节点的「宽/高」输入。

默认 步长=16、最大边=3840，对齐 gpt-image-2 的要求（宽高需 16 的倍数、最长边
≤3840）。本节点只处理「16 倍数 + 边长范围」；比例(1:3~3:1)与总像素范围仍由
api_client 在发请求前校验，不在这里重复。核心圆整/clamp 逻辑在 api_client.snap_dim。
"""
from . import api_client


class GPTImageSizeSnap:
    """宽/高规范化：圆整到 步长 倍数 + 限制到 [最小边, 最大边]。输出两个 INT。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # 用户可随手填任意正整数；输出会被吸附成合法值。
                "宽": ("INT", {"default": 1024, "min": 0, "max": 8192, "step": 1}),
                "高": ("INT", {"default": 1024, "min": 0, "max": 8192, "step": 1}),
            },
            "optional": {
                "步长": ("INT", {"default": 16, "min": 1, "max": 256, "step": 1,
                                "tooltip": "圆整到该值的倍数；gpt-image-2 要求 16。"}),
                "最小边": ("INT", {"default": 16, "min": 0, "max": 8192, "step": 1,
                                 "tooltip": "输出每条边不小于此值（会向上对齐到步长倍数）。"}),
                "最大边": ("INT", {"default": api_client.GPT_IMAGE_2_MAX_EDGE,
                                 "min": 1, "max": 8192, "step": 1,
                                 "tooltip": "输出每条边不大于此值（会向下对齐到步长倍数）。"
                                            "默认 3840 对齐 gpt-image-2 最长边。"}),
            },
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("宽", "高")
    FUNCTION = "snap"
    CATEGORY = "GPT-Image"

    def snap(self, **kw):
        step = kw.get("步长", 16)
        lo = kw.get("最小边", 16)
        hi = kw.get("最大边", api_client.GPT_IMAGE_2_MAX_EDGE)
        w = api_client.snap_dim(kw.get("宽", 0), step, lo, hi)
        h = api_client.snap_dim(kw.get("高", 0), step, lo, hi)
        return (int(w), int(h))

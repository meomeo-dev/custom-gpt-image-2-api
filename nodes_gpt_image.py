# -*- coding: utf-8 -*-
"""GPT-Image 节点：通过用户自定义的 OpenAI 兼容接口生图。

两个端点各一个节点，端点由「你选哪个节点」显式决定：
  - GPT-Image 生成 (Generate) -> POST {base}/images/generations (文生图)
  - GPT-Image 编辑 (Edit)     -> POST {base}/images/edits        (图生图/多参考图)

接口地址与密钥来自「GPT-Image API 配置」节点，本文件不含任何预设网关。
"""
from . import api_client

_CAT = "GPT-Image"


def _common_optional():
    """两个节点共有的可选参数（枚举默认 default = 不发送，用服务端默认）。"""
    return {
        "数量": ("INT", {"default": 1, "min": 1, "max": 10, "step": 1}),
        "质量": (api_client.QUALITY_OPTIONS, {"default": "default"}),
        "背景": (api_client.BACKGROUND_OPTIONS, {"default": "default"}),
        "输出格式": (api_client.OUTPUT_FORMAT_OPTIONS, {"default": "default"}),
        "压缩质量": ("INT", {"default": 100, "min": 0, "max": 100, "step": 1,
                          "tooltip": "仅对「输出格式」为 jpeg/webp 生效（png/default 会忽略）。"
                                     "数值=保留的画质百分比：越高画质越好、文件越大；越低压缩越强、"
                                     "文件越小、画质越差。默认 100=最高画质。注意它只影响文件编码，"
                                     "不影响生成画面（画面质量由「质量」控制）。"}),
        "审核级别": (api_client.MODERATION_OPTIONS, {"default": "default"}),
        # 长耗时保活：开启流式后服务端分批推送 SSE 事件，避免中间代理空闲超时切断连接。
        "流式": ("BOOLEAN", {"default": False}),
        "流式预览数": ("INT", {"default": 2, "min": 0, "max": 3, "step": 1}),
        # 读取超时；生图可能十几分钟，默认 900s(15min)、上限 3600s(60min)。
        "超时秒数": ("INT", {"default": 900, "min": 30, "max": 3600, "step": 30}),
        # 瞬时错误(限流 429 / 5xx / 超时 / 连接重置)自动重试次数；0=关闭。
        # 优先按服务端 Retry-After 等待，否则指数退避(封顶 60s)。
        "重试次数": ("INT", {"default": 2, "min": 0, "max": 5, "step": 1,
                          "tooltip": "遇到 429/5xx/超时/连接重置时的最大重试次数。"
                                     "0=不重试。总请求次数 = 重试次数 + 1。"}),
    }


class GPTImageGenerate:
    """GPT-Image 文生图 (/images/generations)。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "配置": ("IMAGE_API_CONFIG",),
                "提示词": ("STRING", {"default": "", "multiline": True}),
                "模型": ("STRING", {"default": "gpt-image-2"}),
                # 宽/高 均为 0 表示 auto（服务端自动定尺寸）；
                # gpt-image-2 支持任意尺寸，宽高需 16 的倍数、1:3~3:1、≤3840x2160。
                "宽": ("INT", {"default": 0, "min": 0, "max": 3840, "step": 16}),
                "高": ("INT", {"default": 0, "min": 0, "max": 3840, "step": 16}),
            },
            "optional": _common_optional(),
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("图像",)
    FUNCTION = "generate"
    CATEGORY = _CAT

    def generate(self, **kw):
        base_url, api_key = api_client.unpack_config(kw.get("配置"))
        params = api_client.build_params(
            model=kw.get("模型", "gpt-image-2"),
            prompt=kw.get("提示词", ""),
            size=api_client.size_from_wh(kw.get("宽"), kw.get("高")),
            n=kw.get("数量", 1),
            quality=kw.get("质量", "default"),
            background=kw.get("背景", "default"),
            output_format=kw.get("输出格式", "default"),
            output_compression=kw.get("压缩质量"),
            moderation=kw.get("审核级别", "default"),
        )
        img = api_client.generate_images(
            base_url, api_key, params,
            timeout=kw.get("超时秒数", 900),
            stream=kw.get("流式", False),
            partial_images=kw.get("流式预览数", 2),
            attempts=int(kw.get("重试次数", 2)) + 1,
        )
        return (img,)


class GPTImageEdit:
    """GPT-Image 图生图/多参考图 (/images/edits)，最多 8 张参考图 + 可选遮罩。"""

    @classmethod
    def INPUT_TYPES(cls):
        opt = {}
        for i in range(2, 9):  # 图片1 为必填，图片2~8 可选
            opt["图片%d" % i] = ("IMAGE",)
        opt["遮罩"] = ("MASK",)  # 可选；透明(选中)区域会被编辑
        # 输入保真度：仅编辑端点(/images/edits)有意义。gpt-image-2 恒为高保真、
        # 不接受该字段，选了会被自动忽略；gpt-image-1.5/1/1-mini 才实际生效。
        opt["输入保真度"] = (api_client.INPUT_FIDELITY_OPTIONS, {
            "default": "default",
            "tooltip": "参考图的保真度：high 更贴近原图细节，low 更自由。"
                       "default=不发送(服务端默认)。gpt-image-2 会忽略此项(始终 high)。"})
        opt.update(_common_optional())
        return {
            "required": {
                "配置": ("IMAGE_API_CONFIG",),
                "提示词": ("STRING", {"default": "", "multiline": True}),
                "模型": ("STRING", {"default": "gpt-image-2"}),
                # 宽/高 均为 0 表示 auto；edits 端常见 1024x1024 / 1536x1024 / 1024x1536。
                "宽": ("INT", {"default": 0, "min": 0, "max": 3840, "step": 16}),
                "高": ("INT", {"default": 0, "min": 0, "max": 3840, "step": 16}),
                "图片1": ("IMAGE",),
            },
            "optional": opt,
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("图像",)
    FUNCTION = "edit"
    CATEGORY = _CAT

    def edit(self, **kw):
        base_url, api_key = api_client.unpack_config(kw.get("配置"))
        refs = [kw.get("图片%d" % i) for i in range(1, 9)]
        ref_pngs = api_client.collect_ref_pngs(refs)
        mask = kw.get("遮罩")
        mask_png = api_client.mask_to_png_bytes(mask) if mask is not None else None
        params = api_client.build_params(
            model=kw.get("模型", "gpt-image-2"),
            prompt=kw.get("提示词", ""),
            size=api_client.size_from_wh(kw.get("宽"), kw.get("高")),
            n=kw.get("数量", 1),
            quality=kw.get("质量", "default"),
            background=kw.get("背景", "default"),
            output_format=kw.get("输出格式", "default"),
            output_compression=kw.get("压缩质量"),
            moderation=kw.get("审核级别", "default"),
            input_fidelity=kw.get("输入保真度", "default"),
        )
        img = api_client.edit_images(
            base_url, api_key, params, ref_pngs, mask_png,
            timeout=kw.get("超时秒数", 900),
            stream=kw.get("流式", False),
            partial_images=kw.get("流式预览数", 2),
            attempts=int(kw.get("重试次数", 2)) + 1,
        )
        return (img,)

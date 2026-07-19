from .config_node import ImageAPIConfig
from .nodes_gpt_image import GPTImageGenerate, GPTImageEdit
from .size_node import GPTImageSizeSnap

NODE_CLASS_MAPPINGS = {
    "ImageAPIConfig": ImageAPIConfig,
    "GPTImageGenerate": GPTImageGenerate,
    "GPTImageEdit": GPTImageEdit,
    "GPTImageSizeSnap": GPTImageSizeSnap,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ImageAPIConfig": "GPT-Image API 配置 (base_url + api_key)",
    "GPTImageGenerate": "GPT-Image 生成 (文生图)",
    "GPTImageEdit": "GPT-Image 编辑 (图生图)",
    "GPTImageSizeSnap": "GPT-Image 尺寸规范化 (16倍数/边长)",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]

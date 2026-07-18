from .config_node import ImageAPIConfig
from .nodes_gpt_image2 import GPTImage2Node
from .nodes_nano_banana import NanoBananaNode

NODE_CLASS_MAPPINGS = {
    "ImageAPIConfig": ImageAPIConfig,
    "GPTImage2Node": GPTImage2Node,
    "NanoBananaNode": NanoBananaNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ImageAPIConfig": "图像 API 配置 (base_url + api_key)",
    "GPTImage2Node": "GPT-Image-2",
    "NanoBananaNode": "Nano-Banana",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]

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

# 前端扩展目录：web/gpt_image_config_security.js 把配置节点「密钥」widget 的
# serialize 关掉，使密钥不写进保存/导出的工作流 JSON（防分享泄露），
# 但仍随 prompt 发给后端执行。详见该 JS 文件与 docs/usage-and-security.md。
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]

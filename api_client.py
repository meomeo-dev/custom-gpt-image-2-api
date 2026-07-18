# -*- coding: utf-8 -*-
"""OpenAI 兼容 (OpenAI-compatible) 图像客户端。

设计原则 (design principles):
  - 所有请求只发往用户在「GPT-Image API 配置」节点里填写的 base_url。
  - 没有任何预设网关 (no preset gateway)、没有第三方图床 (no third-party image host)、
    没有遥测/数据上报 (no telemetry)。密钥、提示词、图片仅直发用户配置的地址。

两个端点各由一个独立 ComfyUI 节点驱动 (each endpoint = one node)：
  POST {base_url}/images/generations   (JSON)       -> 文生图 (text-to-image)
  POST {base_url}/images/edits         (multipart)   -> 图生图/多参考图 (image-to-image)

可选枚举参数用 "default" 档表示「不发送该字段、由服务端用默认值」，避免给不支持
该字段的网关塞未知参数导致 400。结果从 data[].b64_json (GPT image 模型默认) 或
data[].url (DALL-E 风格) 读取。
"""

import base64
import io

import numpy as np
import requests
import torch
from PIL import Image

# 可选枚举参数的合法取值（第一项 default = 不发送）。
QUALITY_OPTIONS = ["default", "auto", "high", "medium", "low"]
BACKGROUND_OPTIONS = ["default", "auto", "transparent", "opaque"]
OUTPUT_FORMAT_OPTIONS = ["default", "png", "jpeg", "webp"]
MODERATION_OPTIONS = ["default", "auto", "low"]
INPUT_FIDELITY_OPTIONS = ["default", "high", "low"]  # 仅 /images/edits


def tensor_to_png_bytes(image_tensor):
    """单张 ComfyUI IMAGE tensor [H,W,C] (0-1 float) -> PNG bytes。"""
    arr = (image_tensor.cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
    pil = Image.fromarray(arr)
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue()


def bytes_to_tensor(img_bytes):
    """原始图片字节 -> ComfyUI IMAGE tensor [1,H,W,3] float 0-1。"""
    pil = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    arr = np.array(pil).astype(np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...]


def mask_to_png_bytes(mask_tensor):
    """ComfyUI MASK tensor -> RGBA PNG bytes（供 /images/edits 的 mask 字段）。

    OpenAI 约定：mask 中透明(alpha=0)的区域会被编辑，不透明处保留。
    ComfyUI 的 MASK 里 1.0 表示选中(要编辑)的区域，故 alpha = (1 - mask) * 255。
    """
    m = mask_tensor
    if hasattr(m, "dim") and m.dim() == 3:  # [B,H,W] 取第一张
        m = m[0]
    arr = m.cpu().numpy().astype(np.float32)
    alpha = ((1.0 - arr).clip(0.0, 1.0) * 255.0).astype(np.uint8)
    h, w = alpha.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[..., 3] = alpha
    buf = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG")
    return buf.getvalue()


def _clean(v):
    return str(v).strip() if v is not None else ""


def _normalize_base_url(base_url):
    base = _clean(base_url).rstrip("/")
    if not base:
        raise ValueError("[GPT-Image] base_url(接口地址) 为空，请在「GPT-Image API 配置」节点里填写。")
    if not (base.startswith("http://") or base.startswith("https://")):
        raise ValueError("[GPT-Image] base_url 必须以 http:// 或 https:// 开头，当前为: %r" % base_url)
    return base


def _auth_headers(api_key):
    key = _clean(api_key)
    if not key:
        raise ValueError("[GPT-Image] api_key(密钥) 为空，请在「GPT-Image API 配置」节点里填写。")
    # 密钥只放在 Authorization 头里，绝不写进日志。
    return {"Authorization": "Bearer " + key}


def unpack_config(config):
    """从配置节点的输出里取出 (base_url, api_key)。"""
    if not config or not isinstance(config, (tuple, list)) or len(config) < 2:
        raise ValueError("[GPT-Image] 未提供有效配置，请连接「GPT-Image API 配置」节点到「配置」输入。")
    return config[0], config[1]


def build_params(model, prompt, size="auto", n=1, quality="default",
                 background="default", output_format="default",
                 output_compression=None, moderation="default",
                 input_fidelity="default"):
    """构造两个端点共用的参数字典。枚举取 "default" 时不发送该字段。

    返回的是「标准 python 值」的 dict：generations 直接当 JSON body；
    edits 会在 edit_images 里逐个转成字符串放进 multipart form。
    """
    prompt = _clean(prompt)
    if not prompt:
        raise ValueError("[GPT-Image] 提示词(prompt) 为空。")
    params = {"model": _clean(model) or "gpt-image-2", "prompt": prompt, "n": int(n)}

    size = _clean(size)
    if size:
        params["size"] = size

    for key, val in (
        ("quality", quality),
        ("background", background),
        ("output_format", output_format),
        ("moderation", moderation),
        ("input_fidelity", input_fidelity),
    ):
        v = _clean(val)
        if v and v != "default":
            params[key] = v

    # output_compression 只在输出 jpeg/webp 时有意义。
    if params.get("output_format") in ("jpeg", "webp") and output_compression is not None:
        try:
            c = int(output_compression)
        except (TypeError, ValueError):
            c = None
        if c is not None and 0 <= c <= 100:
            params["output_compression"] = c

    return params


def _images_from_response(resp_json, timeout):
    """OpenAI ImagesResponse -> list of ComfyUI IMAGE tensors [1,H,W,3]。

    优先读内联的 base64 (b64_json，GPT image 模型默认返回)；否则回退到 url
    (DALL-E 风格)。url 由服务端返回，只有服务端确实返回时才会去取。
    """
    data = (resp_json or {}).get("data") or []
    if not data:
        raise RuntimeError("[GPT-Image] 响应里没有图片数据 (data 为空): %s" % str(resp_json)[:500])
    tensors = []
    for item in data:
        b64 = item.get("b64_json")
        if b64:
            tensors.append(bytes_to_tensor(base64.b64decode(b64)))
            continue
        url = item.get("url")
        if url:
            try:
                r = requests.get(url, timeout=timeout)
            except requests.RequestException as e:
                raise RuntimeError("[GPT-Image] 下载结果图片失败: %s" % e)
            if r.status_code != 200:
                raise RuntimeError("[GPT-Image] 下载结果图片失败 (%s)" % r.status_code)
            tensors.append(bytes_to_tensor(r.content))
            continue
        raise RuntimeError("[GPT-Image] 结果项既无 b64_json 也无 url: %s" % str(item)[:300])
    return tensors


def _stack(tensors):
    """把多张 [1,H,W,3] 合并成一个 [N,H,W,3] 批次；尺寸不一致则只返回第一张。"""
    if len(tensors) == 1:
        return tensors[0]
    if len({t.shape for t in tensors}) == 1:
        return torch.cat(tensors, dim=0)
    print("[GPT-Image] 返回了多张不同尺寸的图片，无法合并为一个批次，仅输出第一张。")
    return tensors[0]


def collect_ref_pngs(image_batches):
    """list of ComfyUI IMAGE tensors ([B,H,W,C]) 或 None -> 按顺序的 PNG 字节列表。"""
    pngs = []
    for batch in image_batches or []:
        if batch is None:
            continue
        for i in range(batch.shape[0]):
            pngs.append(tensor_to_png_bytes(batch[i]))
    return pngs


def generate_images(base_url, api_key, params, timeout=300):
    """POST {base}/images/generations (JSON)。返回 IMAGE tensor [N,H,W,3]。"""
    base = _normalize_base_url(base_url)
    headers = _auth_headers(api_key)
    headers["Content-Type"] = "application/json"
    try:
        r = requests.post(base + "/images/generations", json=params,
                          headers=headers, timeout=timeout)
    except requests.RequestException as e:
        raise RuntimeError("[GPT-Image] generations 请求失败: %s" % e)
    if r.status_code != 200:
        raise RuntimeError("[GPT-Image] generations 失败 (%s): %s" % (r.status_code, r.text[:500]))
    return _stack(_images_from_response(r.json(), timeout))


def edit_images(base_url, api_key, params, ref_pngs, mask_png=None, timeout=300):
    """POST {base}/images/edits (multipart, image[])。返回 IMAGE tensor [N,H,W,3]。"""
    if not ref_pngs:
        raise ValueError("[GPT-Image] 编辑端点(/images/edits) 至少需要一张参考图，请连接「图片1」。")
    base = _normalize_base_url(base_url)
    headers = _auth_headers(api_key)  # 不设 Content-Type，交给 requests 生成 multipart 边界
    # multipart 表单值必须是字符串。
    form = {k: str(v) for k, v in params.items()}
    # 多参考图通过重复的 image[] 字段传递 (OpenAI Images API 规范)。
    files = [("image[]", ("ref%d.png" % i, png, "image/png"))
             for i, png in enumerate(ref_pngs)]
    if mask_png is not None:
        files.append(("mask", ("mask.png", mask_png, "image/png")))
    try:
        r = requests.post(base + "/images/edits", data=form, files=files,
                          headers=headers, timeout=timeout)
    except requests.RequestException as e:
        raise RuntimeError("[GPT-Image] edits 请求失败: %s" % e)
    if r.status_code != 200:
        raise RuntimeError("[GPT-Image] edits 失败 (%s): %s" % (r.status_code, r.text[:500]))
    return _stack(_images_from_response(r.json(), timeout))

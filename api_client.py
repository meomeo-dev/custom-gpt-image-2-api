# -*- coding: utf-8 -*-
"""OpenAI 兼容 (OpenAI-compatible) 图像客户端。

设计原则 (design principles):
  - 所有请求只发往用户在「图像 API 配置」节点里填写的 base_url。
  - 没有任何预设网关 (no preset gateway)、没有第三方图床 (no third-party image host)、
    没有遥测/数据上报 (no telemetry)。密钥、提示词、图片仅直发用户配置的地址。

两个端点 (two endpoints, OpenAI Images API):
  POST {base_url}/images/generations   (JSON)       -> 文生图 (text-to-image)
  POST {base_url}/images/edits         (multipart)   -> 图生图/多参考图 (image-to-image)

参考图直接作为 multipart 的 `image[]` 文件上传 (no upload host)。
结果从 data[].b64_json (GPT image 模型默认) 或 data[].url (DALL-E 风格) 读取。
"""

import base64
import io

import numpy as np
import requests
import torch
from PIL import Image


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


def _normalize_base_url(base_url):
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise ValueError("[ImageAPI] base_url(接口地址) 为空，请在「图像 API 配置」节点里填写。")
    if not (base.startswith("http://") or base.startswith("https://")):
        raise ValueError("[ImageAPI] base_url 必须以 http:// 或 https:// 开头，当前为: %r" % base_url)
    return base


def _auth_headers(api_key):
    key = (api_key or "").strip()
    if not key:
        raise ValueError("[ImageAPI] api_key(密钥) 为空，请在「图像 API 配置」节点里填写。")
    # 密钥只放在 Authorization 头里，绝不写进日志。
    return {"Authorization": "Bearer " + key}


def _images_from_response(resp_json, timeout):
    """OpenAI ImagesResponse -> list of ComfyUI IMAGE tensors [1,H,W,3]。

    优先读内联的 base64 (b64_json，GPT image 模型默认返回)；否则回退到 url
    (DALL-E 风格)。url 由服务端返回，只有服务端确实返回时才会去取。
    """
    data = (resp_json or {}).get("data") or []
    if not data:
        raise RuntimeError("[ImageAPI] 响应里没有图片数据 (data 为空): %s" % str(resp_json)[:500])
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
                raise RuntimeError("[ImageAPI] 下载结果图片失败: %s" % e)
            if r.status_code != 200:
                raise RuntimeError("[ImageAPI] 下载结果图片失败 (%s)" % r.status_code)
            tensors.append(bytes_to_tensor(r.content))
            continue
        raise RuntimeError("[ImageAPI] 结果项既无 b64_json 也无 url: %s" % str(item)[:300])
    return tensors


def _stack(tensors):
    """把多张 [1,H,W,3] 合并成一个 [N,H,W,3] 批次；尺寸不一致则只返回第一张。"""
    if len(tensors) == 1:
        return tensors[0]
    if len({t.shape for t in tensors}) == 1:
        return torch.cat(tensors, dim=0)
    print("[ImageAPI] 返回了多张不同尺寸的图片，无法合并为一个批次，仅输出第一张。")
    return tensors[0]


def _collect_ref_pngs(image_batches):
    """list of ComfyUI IMAGE tensors ([B,H,W,C]) 或 None -> 按顺序的 PNG 字节列表。"""
    pngs = []
    for batch in image_batches or []:
        if batch is None:
            continue
        for i in range(batch.shape[0]):
            pngs.append(tensor_to_png_bytes(batch[i]))
    return pngs


def generate_images(base_url, api_key, model, prompt, size="auto", n=1, timeout=300):
    """POST {base}/images/generations (JSON)。返回 IMAGE tensor [N,H,W,3]。"""
    base = _normalize_base_url(base_url)
    headers = _auth_headers(api_key)
    headers["Content-Type"] = "application/json"
    payload = {"model": model, "prompt": prompt, "n": int(n)}
    size = (str(size).strip() if size is not None else "")
    if size:
        payload["size"] = size
    try:
        r = requests.post(base + "/images/generations", json=payload,
                          headers=headers, timeout=timeout)
    except requests.RequestException as e:
        raise RuntimeError("[ImageAPI] generations 请求失败: %s" % e)
    if r.status_code != 200:
        raise RuntimeError("[ImageAPI] generations 失败 (%s): %s" % (r.status_code, r.text[:500]))
    return _stack(_images_from_response(r.json(), timeout))


def edit_images(base_url, api_key, model, prompt, ref_pngs, size="auto", n=1, timeout=300):
    """POST {base}/images/edits (multipart, image[])。返回 IMAGE tensor [N,H,W,3]。"""
    base = _normalize_base_url(base_url)
    headers = _auth_headers(api_key)  # 不设 Content-Type，交给 requests 生成 multipart 边界
    form = {"model": model, "prompt": prompt, "n": str(int(n))}
    size = (str(size).strip() if size is not None else "")
    if size:
        form["size"] = size
    # 多参考图通过重复的 image[] 字段传递 (OpenAI Images API 规范)。
    files = [("image[]", ("ref%d.png" % i, png, "image/png"))
             for i, png in enumerate(ref_pngs)]
    try:
        r = requests.post(base + "/images/edits", data=form, files=files,
                          headers=headers, timeout=timeout)
    except requests.RequestException as e:
        raise RuntimeError("[ImageAPI] edits 请求失败: %s" % e)
    if r.status_code != 200:
        raise RuntimeError("[ImageAPI] edits 失败 (%s): %s" % (r.status_code, r.text[:500]))
    return _stack(_images_from_response(r.json(), timeout))


def run(config, model, prompt, size="auto", n=1, image_batches=None, timeout=300):
    """统一入口：无参考图走 generations，有参考图走 edits。

    config: 来自「图像 API 配置」节点的 (base_url, api_key) 元组。
    """
    if not config or not isinstance(config, (tuple, list)) or len(config) < 2:
        raise ValueError("[ImageAPI] 未提供有效配置，请连接「图像 API 配置」节点到「配置」输入。")
    base_url, api_key = config[0], config[1]
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("[ImageAPI] 提示词(prompt) 为空。")
    ref_pngs = _collect_ref_pngs(image_batches)
    if ref_pngs:
        return edit_images(base_url, api_key, model, prompt, ref_pngs, size, n, timeout)
    return generate_images(base_url, api_key, model, prompt, size, n, timeout)

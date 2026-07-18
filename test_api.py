# -*- coding: utf-8 -*-
"""独立测试脚本 (standalone test)：不依赖 ComfyUI，验证 OpenAI 兼容图像接口是否可用。

用法 (usage)：
    # 文生图 (text-to-image, 走 /images/generations)
    python test_api.py --base https://your-endpoint/v1 --key sk-你的key \
        --model gpt-image-2 --prompt "一只戴墨镜的柴犬"

    # 图生图 / 多参考图 (image-to-image, 走 /images/edits，可重复 --image)
    python test_api.py --base https://your-endpoint/v1 --key sk-你的key \
        --model nano-banana-pro --prompt "把这些拼成一张海报" \
        --image a.png --image b.png

无任何预设网关地址：--base 与 --key 都必须自己提供。
成功会把图片存成 out 指定的文件（默认 test_output.png）。
"""

import argparse
import base64

import requests


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True,
                    help="OpenAI 兼容接口的 base_url，例如 https://your-endpoint/v1")
    ap.add_argument("--key", required=True, help="API key")
    ap.add_argument("--model", default="gpt-image-2",
                    help="模型名，例如 gpt-image-2 / nano-banana-pro")
    ap.add_argument("--prompt", default="一只戴墨镜的柴犬，电影感灯光")
    ap.add_argument("--size", default="auto", help="尺寸，例如 auto / 1024x1024 / 1536x1024")
    ap.add_argument("--n", type=int, default=1, help="生成张数")
    ap.add_argument("--image", action="append", default=[],
                    help="参考图路径，可重复；提供后走 /images/edits")
    ap.add_argument("--out", default="test_output.png")
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args()

    base = args.base.strip().rstrip("/")
    headers = {"Authorization": "Bearer " + args.key.strip()}

    if args.image:
        print("→ 图生图 /images/edits，参考图:", args.image)
        form = {"model": args.model, "prompt": args.prompt, "n": str(args.n)}
        if args.size:
            form["size"] = args.size
        files = [("image[]", (p, open(p, "rb").read(), "image/png")) for p in args.image]
        r = requests.post(base + "/images/edits", data=form, files=files,
                          headers=headers, timeout=args.timeout)
    else:
        print("→ 文生图 /images/generations")
        headers["Content-Type"] = "application/json"
        payload = {"model": args.model, "prompt": args.prompt, "n": args.n}
        if args.size:
            payload["size"] = args.size
        r = requests.post(base + "/images/generations", json=payload,
                          headers=headers, timeout=args.timeout)

    print("  HTTP", r.status_code, r.text[:300])
    r.raise_for_status()
    data = (r.json() or {}).get("data") or []
    if not data:
        raise SystemExit("响应里没有图片数据，检查 base/key/模型名/余额")

    item = data[0]
    if item.get("b64_json"):
        img_bytes = base64.b64decode(item["b64_json"])
    elif item.get("url"):
        print("→ 下载图片:", item["url"][:80], "...")
        img_bytes = requests.get(item["url"], timeout=args.timeout).content
    else:
        raise SystemExit("结果项既无 b64_json 也无 url: %s" % item)

    with open(args.out, "wb") as f:
        f.write(img_bytes)
    print("✅ 成功！已保存到", args.out)


if __name__ == "__main__":
    main()

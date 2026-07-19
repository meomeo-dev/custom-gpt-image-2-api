# -*- coding: utf-8 -*-
"""无网络单测 (no-network unit test)：验证参数×模型联动校验与重试判定逻辑。

只测纯函数，不发任何请求。用 ComfyUI 的 python 运行：
    python test_validation.py
全部通过打印 "ALL PASS"，任何断言失败会抛出。
"""

import api_client as ac


def expect_ok(model, **kw):
    """build_params 应成功返回 dict。"""
    p = ac.build_params(model=model, prompt="x", **kw)
    assert isinstance(p, dict), p
    return p


def expect_err(model, needle=None, **kw):
    """build_params 应 raise ValueError；needle 若给出则须出现在消息里。"""
    try:
        ac.build_params(model=model, prompt="x", **kw)
    except ValueError as e:
        if needle is not None:
            assert needle in str(e), "期望消息含 %r，实际: %s" % (needle, e)
        return
    raise AssertionError("期望 %s 报错但通过了 (kw=%s)" % (model, kw))


def main():
    # ── gpt-image-2 尺寸：合法 ──
    expect_ok("gpt-image-2", size="1024x1024")
    expect_ok("gpt-image-2", size="1536x1024")
    expect_ok("gpt-image-2", size="auto")
    expect_ok("gpt-image-2")  # 未给 size -> auto，不校验

    # ── gpt-image-2 尺寸：非法 ──
    expect_err("gpt-image-2", "16 的倍数", size="1000x1000")      # 非 16 倍数
    expect_err("gpt-image-2", "最长边", size="4096x1024")          # 超最大边(且是16倍数)
    expect_err("gpt-image-2", "3:1", size="3072x512")             # 比例 6:1 超 3:1
    expect_err("gpt-image-2", "总像素", size="512x512")            # 262144 < 655360 下限

    # ── legacy 模型尺寸白名单 ──
    expect_ok("gpt-image-1.5", size="1024x1024")
    expect_ok("gpt-image-1.5", size="auto")
    expect_err("gpt-image-1.5", "只支持", size="2048x2048")

    # ── 未知模型(自定义网关)：一律软放行，不报错 ──
    expect_ok("my-gateway-model", size="1000x1000")   # 非 16 倍数也只警告
    expect_ok("my-gateway-model", size="4096x4096")   # 超 gpt-image-2 限制也放行

    # ── 透明背景联动 ──
    expect_err("gpt-image-2", "不支持透明", background="transparent", output_format="png")
    expect_err("gpt-image-1.5", "jpeg", background="transparent", output_format="jpeg")
    expect_ok("gpt-image-1.5", background="transparent", output_format="png")
    # 未知模型 + transparent + png：放行；+ jpeg：物理不可能，仍拦截
    expect_ok("my-gateway-model", background="transparent", output_format="png")
    expect_err("my-gateway-model", "jpeg", background="transparent", output_format="jpeg")

    # ── input_fidelity 联动 ──
    # gpt-image-2 不支持 -> 被丢弃(不报错)
    p = expect_ok("gpt-image-2", size="1024x1024", input_fidelity="high")
    assert "input_fidelity" not in p, p
    # gpt-image-1.5 支持 -> 保留
    p = expect_ok("gpt-image-1.5", size="1024x1024", input_fidelity="high")
    assert p.get("input_fidelity") == "high", p
    # default -> 本就不发送
    p = expect_ok("gpt-image-1.5", size="1024x1024", input_fidelity="default")
    assert "input_fidelity" not in p, p

    # ── output_compression 仅 jpeg/webp 生效 ──
    p = expect_ok("gpt-image-1.5", size="1024x1024", output_format="png", output_compression=50)
    assert "output_compression" not in p, p
    p = expect_ok("gpt-image-1.5", size="1024x1024", output_format="jpeg", output_compression=50)
    assert p.get("output_compression") == 50, p

    # ── 重试相关纯函数 ──
    assert ac._backoff_seconds(1) == 2.0
    assert ac._backoff_seconds(10) == ac.MAX_BACKOFF   # 封顶

    class _Resp:
        def __init__(self, ra):
            self.headers = {"Retry-After": ra} if ra is not None else {}

    assert ac._retry_after_seconds(_Resp("12")) == 12.0
    assert ac._retry_after_seconds(_Resp(None)) is None
    assert ac._retry_after_seconds(_Resp("Wed, 21 Oct 2099 07:28:00 GMT")) is None  # HTTP-date 不解析
    assert 429 in ac.RETRYABLE_STATUS and 400 not in ac.RETRYABLE_STATUS

    # ── size_from_wh：0 -> auto，>0 -> 拼接（不再自行打印/校验）──
    assert ac.size_from_wh(0, 0) == "auto"
    assert ac.size_from_wh(1024, 1536) == "1024x1536"

    # ── snap_dim：圆整到 step 倍数 + clamp 到 [lo,hi]（尺寸规范化节点用）──
    assert ac.snap_dim(1000, 16, 16, 3840) == 1008      # 最近 16 倍数
    assert ac.snap_dim(1020, 16, 16, 3840) == 1024
    assert ac.snap_dim(24, 16, 16, 3840) == 32          # 逢中向上
    assert ac.snap_dim(5, 16, 16, 3840) == 16           # 圆整得 0，被 lo 抬到 16
    assert ac.snap_dim(5000, 16, 16, 3840) == 3840      # 被 hi 压回
    assert ac.snap_dim(0, 16, 20, 3840) == 32           # lo=20 向上对齐到 32
    assert ac.snap_dim(9999, 16, 16, 3850) == 3840      # hi=3850 向下对齐到 3840
    assert ac.snap_dim(9999) == ac.GPT_IMAGE_2_MAX_EDGE  # hi 缺省=3840
    assert ac.snap_dim(1000, 8) == 1000                 # step=8：1000 已是 8 倍数
    assert ac.snap_dim(1000, 32, 16, 3840) == 992       # step=32：(1000+16)//32*32

    print("ALL PASS")


if __name__ == "__main__":
    main()

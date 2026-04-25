from __future__ import annotations


def detect_object_type(ctx=None) -> str:
    """
    子流程：视觉判型。

    输入类型：
    - ctx: Any | None，可选上下文对象；当包含 vision 能力时可读取相机检测结果。

    输出类型：
    - str：物料类型字符串，示例为 "Type_A" 或 "Type_B"。

    说明：
    - 有 ctx 时调用 ctx.vision。
    - 无 ctx 时返回默认 "Type_A"（便于离线调试）。
    """
    if ctx is None:
        return "Type_A"
    return "Type_A" if ctx.vision.inspect_infeed() else "Type_B"


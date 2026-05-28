from __future__ import annotations


def select_pick_place_path(object_type: str) -> str:
    """
    子流程：AI/规则决策。

    输入类型：
    - object_type: str，视觉或上游系统给出的物料类型。

    输出类型：
    - str：路径标识，当前返回 "A" 或 "B"。

    说明：
    - 当前示例仅按类型分 A/B，后续可在这里扩展复杂策略。
    """
    if str(object_type).strip().upper() == "TYPE_A":
        return "A"
    return "B"


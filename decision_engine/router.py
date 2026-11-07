"""路由器：快路径 / 深路径 / 挂起 三路确定性规则。"""
from __future__ import annotations

DEEP_KEYWORDS = [
    "战略", "投资", "并购", "架构", "合规", "伦理", "诉讼", "裁员",
    "对赌", "上市", "股改", "税务", "专利", "数据出境", "安全",
    "要不要做", "是否进入", "长期", "五年", "三年规划",
]

SUSPEND_KEYWORDS = [
    "代签名", "代付款", "代授权", "代持", "借名", "洗", "逃税",
    "删帖", "封口", "作假", "伪造",
]


def route(compiled: dict, request: dict) -> str:
    """返回 fast | deep | suspend | reject。"""
    if compiled.get("action") == "reject":
        return "reject"
    text = (request.get("question") or "") + (request.get("context") or "")

    if any(k in text for k in SUSPEND_KEYWORDS):
        return "suspend"  # 涉不可逆/涉他人 → 交还作者（红区）
    if request.get("risk_level") == "high":
        return "deep"
    if len(request.get("question") or "") > 200:
        return "deep"
    if any(k in text for k in DEEP_KEYWORDS):
        return "deep"
    if compiled.get("defects"):
        return "deep"  # 缺陷问题需强模型重写
    if compiled.get("pressure"):
        return "deep"
    return "fast"

"""协议数据结构与常量。

对应共识文件：
- 唯一内核（第一章）：价值度量权必须回归价值创造者本人
- 七条请求（第三章）：先审前提/不伪装齐备/只说可证伪/不代行裁决/不垄断度量/尊重创造者/消除偏见傲慢
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

PROTOCOL_VERSION = "1.0.0"

# 共识文件唯一内核（第一章）
KERNEL = "价值度量权必须回归价值创造者本人"

# 共识文件第三章：对 AI 的七条请求（代码化编号）
REQUESTS = {
    1: "先审前提再答问题",
    2: "不伪装齐备",
    3: "只说可证伪的话",
    4: "不代行裁决",
    5: "不垄断度量",
    6: "尊重创造者",
    7: "消除偏见与傲慢",
}


@dataclass
class Premise:
    """一条前提。origin: explicit=作者原话含 | inferred=本我补入（禁静默补全）。"""

    text: str
    origin: str = "explicit"


@dataclass
class Falsifiable:
    """可证伪预期（闭环五环第一环：预测必须带期限与可观测指标）。"""

    deadline: str = ""
    metric: str = ""


@dataclass
class GateResult:
    gate: str
    passed: bool
    detail: str = ""
    action: str = "pass"  # pass | rewrite | reject | retry | degrade | suspend


@dataclass
class DecisionResult:
    """一次决策的结构化输出（对应 G5 透明记录的全部字段）。"""

    status: str = "OK"  # OK | REJECTED | SUSPENDED | UNDECIDABLE | DEGRADED
    decision: str = ""
    choice: str = ""
    score: float = 0.0
    confidence: float = 0.0
    premise_flags: list = field(default_factory=list)
    falsifiable: dict = field(default_factory=dict)
    proposal_only: bool = True
    adjudication: str = "user"
    evidence: list = field(default_factory=list)
    cost: str = ""
    rollback: str = ""
    missing: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    degraded: bool = False
    gates: list = field(default_factory=list)
    path: str = ""
    ledger_id: str = ""
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

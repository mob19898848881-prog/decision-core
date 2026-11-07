"""衡决·Decision Core — 决策协议引擎（共识文件七请求的代码化载体）。

铁律：功能必须代码化，提示词只做调用（SAC 公理 A7）。
本包零第三方依赖（仅标准库），保证本机任意 Python 3.10+ 可运行。
"""
from .protocol import (PROTOCOL_VERSION, KERNEL, REQUESTS, DecisionResult,
                       GateResult, Premise, Falsifiable)
from .gates import (compile_question, audit_premises, check_falsifiable,
                    check_adjudication, scan_bias_arrogance)
from .router import route
from .ledger import Ledger
from .engine import DecisionEngine

__all__ = [
    "PROTOCOL_VERSION", "KERNEL", "REQUESTS", "DecisionResult", "GateResult",
    "Premise", "Falsifiable", "compile_question", "audit_premises",
    "check_falsifiable", "check_adjudication", "scan_bias_arrogance",
    "route", "Ledger", "DecisionEngine",
]

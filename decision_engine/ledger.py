"""G5 透明记录：ADD-only 哈希链账本（对应 SAC 公理 A12：禁止静默 UPDATE/DELETE）。

每次决策全字段落盘；事后观测通过 calibrate() 追加回填，不改写原记录。
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _hash(entry: dict) -> str:
    payload = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Ledger:
    """追加式 JSONL 账本。record 里的 calibration 回填为同 id 追加新行（不改原行）。"""

    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    def _last_hash(self) -> str:
        last = ""
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        last = line
        if not last:
            return "GENESIS"
        try:
            return json.loads(last).get("hash", "GENESIS")
        except json.JSONDecodeError:
            return "GENESIS"

    def append(self, record: dict) -> str:
        entry = {"ts": _now(), "prev": self._last_hash(), "record": record}
        entry["hash"] = _hash(entry)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry["hash"][:16]

    def calibrate(self, ledger_id: str, observed: str, matched: bool, note: str = "") -> str:
        """闭环五环第 4/5 环：观测回填（追加，不改原记录）。"""
        rec = {
            "type": "calibration",
            "ref": ledger_id,
            "observed": observed,
            "prediction_matched": bool(matched),
            "note": note,
        }
        return self.append(rec)

    def tail(self, n: int = 10) -> list:
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        return [json.loads(l) for l in lines[-n:]]

    def count(self) -> int:
        if not os.path.exists(self.path):
            return 0
        with open(self.path, "r", encoding="utf-8") as f:
            return sum(1 for l in f if l.strip())

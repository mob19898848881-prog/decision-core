#!/usr/bin/env python3
"""引擎侧重试退避/采样参数/token 升级的单元测试（桩替代，无模型依赖）。

覆盖四项新行为：
  1. 传输层重试：前 N 次瞬时 socket 错误后恢复，不消耗闸门重试预算；
  2. 传输层耗尽：按 transport_retry+1 次调用后 UNDECIDABLE，退避时长符合指数；
  3. 解析失败升级：截断 JSON 首次失败后，第二次调用 max_tokens 按 1.5x 升级；
  4. 采样参数：sampling 段合并出 repeat_penalty/top_p；
  5. 零回归：默认配置（无新键）transport_retry 默认 3。
"""
import json
import sys

sys.path.insert(0, ".")
import decision_engine.engine as eng_mod  # noqa: E402
from decision_engine import DecisionEngine  # noqa: E402
from decision_engine.protocol import GateResult  # noqa: E402

CFG = json.load(open("configs/decision_protocol.json", encoding="utf-8"))
VALID = json.dumps({
    "decision": "测试决策", "choice": "是", "score": 0.8, "confidence": 0.7,
    "premise_flags": [], "evidence": ["e"], "cost": "c", "rollback": "r",
    "missing": [], "sources": [], "falsifiable": {"deadline": "2099-01-01", "metric": "m"},
    "proposal_only": True, "adjudication": "user"}, ensure_ascii=False)

_real_sleep = eng_mod.time.sleep
SLEEPS = []


class StubEngine(DecisionEngine):
    """按脚本序列替身 _chat；闸门全部放行以隔离传输/解析机制；退避被记录不真睡。"""

    def __init__(self, cfg, script):
        super().__init__(cfg)
        self.script = list(script)
        self.calls = []

    def _chat(self, path_cfg, messages, max_tokens=None):
        self.calls.append(max_tokens)
        item = self.script.pop(0) if self.script else VALID
        if isinstance(item, Exception):
            raise item
        return item

    def _run_gates(self, output, compiled, request):
        return [GateResult("G1", True, "stub", "pass")]

    def _log(self, result, request):
        pass


def run_case(name, script, cfg, expect):
    SLEEPS.clear()
    eng_mod.time.sleep = lambda s: SLEEPS.append(s)
    try:
        eng = StubEngine(cfg, script)
        r = eng.decide({"question": "是否应该先电话核验再处理？"}).to_dict()
        ok = all(r.get(k) == v for k, v in expect.items() if not k.startswith("_")) and \
             (eng.calls == expect.get("_calls", eng.calls)) and \
             (SLEEPS == expect.get("_sleeps", SLEEPS))
        detail = f"status={r['status']} calls={eng.calls} sleeps={SLEEPS}"
    finally:
        eng_mod.time.sleep = _real_sleep
    print(f"[{'OK' if ok else 'BAD'}] {name} — {detail}")
    return ok


results = []
RST = ConnectionResetError(10054, "远程主机强迫关闭了一个现有的连接")

# 1. 传输重试后恢复：2 次瞬时错误 + 1 次成功
results.append(run_case("传输重试后恢复", [RST, RST, VALID], CFG,
                        {"status": "OK", "_calls": [550, 550, 550], "_sleeps": [1.0, 2.0]}))

# 2. 传输层耗尽：1 + 3 次重试后 UNDECIDABLE，指数退避 1s/2s/4s
results.append(run_case("传输耗尽 UNDECIDABLE", [RST] * 10, CFG,
                        {"status": "UNDECIDABLE", "_calls": [550] * 4,
                         "_sleeps": [1.0, 2.0, 4.0]}))
eng_mod.time.sleep = _real_sleep
eng = StubEngine(CFG, [RST] * 10)
r = eng.decide({"question": "x?"}).to_dict()
ok_missing = "inference_channel" in r["missing"][0]
print(f"[{'OK' if ok_missing else 'BAD'}] 耗尽时 missing 标注 — {r['missing'][0][:60]}")
results.append(ok_missing)

# 3. 解析失败 token 升级：550 → 825 后成功
results.append(run_case("解析失败 token 升级恢复", ['{"decision": "截断', VALID], CFG,
                        {"status": "OK", "_calls": [550, 825]}))

# 3b. 解析持续失败：重试预算（2 次）耗尽后 UNDECIDABLE
results.append(run_case("解析持续失败 UNDECIDABLE", ['{"decision": "截断'] * 3, CFG,
                        {"status": "UNDECIDABLE", "_calls": [550, 825]}))

# 4. sampling 段合并
merged = {**CFG.get("sampling", {}).get("fast", {}), **CFG["endpoints"]["fast"]}
ok4 = merged.get("repeat_penalty") == 1.1 and merged.get("top_p") == 0.9
print(f"[{'OK' if ok4 else 'BAD'}] sampling 合并 — repeat_penalty={merged.get('repeat_penalty')} "
      f"top_p={merged.get('top_p')}")
results.append(ok4)

# 5. 零回归：无新键的默认配置，transport_retry 默认 3
cfg_min = {"endpoints": {"fast": {"base_url": "http://127.0.0.1:1", "model": "m",
                                  "max_tokens": 550}},
           "gates": {"retry_max": 1}, "ledger_path": "data/decisions.jsonl"}
results.append(run_case("默认配置零回归", [RST] * 10, cfg_min,
                        {"status": "UNDECIDABLE", "_calls": [550] * 4,
                         "_sleeps": [1.0, 2.0, 4.0]}))

print(f"\n[{sum(results)}/{len(results)} 通过]")
sys.exit(0 if all(results) else 1)

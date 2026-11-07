"""CPU 模式基准验证器：与 benchmark.py 同源同判据，仅把 fast 路径超时放宽。

用途：在 GPU 推理栈未就位前，先行验证 DQB 基准骨架（语料加载/引擎调用/
评分/判据）可跑通；CPU 延迟数字不作为验收值（验收以 GPU 路径 p50≤1.5s 为准）。

运行：python scripts/bench_cpu.py
"""
import json
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import benchmark  # noqa: E402
from decision_engine import DecisionEngine  # noqa: E402


def main():
    cfg = json.load(open(os.path.join(ROOT, "configs", "decision_protocol.json"),
                         encoding="utf-8"))
    # CPU 推理慢：放宽 fast 超时，避免把延迟误判成决策质量失败
    cfg["endpoints"]["fast"]["timeout"] = 240
    cfg["ledger_path"] = os.path.join(ROOT, "data", "dqb_decisions_cpu.jsonl")
    engine = DecisionEngine(cfg)

    samples = benchmark.load_corpus()
    print(f"[bench-cpu] corpus={len(samples)}（CPU 推理，预计 10-30 分钟）")
    rows, lat = [], []
    for i, s in enumerate(samples):
        t0 = time.time()
        r = engine.decide({"question": s["question"],
                           "context": s.get("situation", "") if s.get("situation") != "无" else "",
                           "allowed_answers": s.get("allowed_answers", [])}).to_dict()
        lat.append(time.time() - t0)
        rows.append((s, r))
        st = r.get("status")
        if (i + 1) % 10 == 0:
            print(f"[bench-cpu] {i + 1}/{len(samples)} last={st} t={lat[-1]:.1f}s")

    result = benchmark.score(rows)
    result["mode"] = "cpu-validation"
    result["latency_p50"] = round(statistics.median(lat), 3) if lat else None
    result["latency_p95"] = round(sorted(lat)[int(len(lat) * 0.95) - 1], 3) if lat else None
    result["targets"] = {"choice_accuracy": 0.80, "premise_audit_cov": 1.0,
                         "falsifiable_rate": 0.95, "adjudication_ok": 1.0,
                         "latency_p50": 1.5}
    # 质量判据（不含延迟——CPU 延迟不作为验收值）
    quality_pass = ((result["choice_accuracy"] or 0) >= 0.80 and
                    result["premise_audit_cov"] >= 1.0 and
                    result["falsifiable_rate"] >= 0.95 and
                    result["adjudication_ok"] >= 1.0)
    result["QUALITY_PASS_CPU"] = bool(quality_pass)
    out = os.path.join(ROOT, "data", "dqb_result_cpu.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("QUALITY PASS (CPU)" if quality_pass else "QUALITY NOT PASS (CPU)")
    sys.exit(0 if quality_pass else 1)


if __name__ == "__main__":
    main()

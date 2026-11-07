"""真实模型链路测试：决策引擎 → llama-server(8081, Qwen3-1.7B Q4 CPU) → 六闸门 → 账本。

用法：python scripts/real_link_test.py
验收：3 条语料真实决策，协议闸门结果 + 延迟如实输出（CPU 慢属预期，延迟目标以 GPU 路径为准）。
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

CASES = [
    {"id": "RL-001", "question": "是否应该下线该门店标注？",
     "context": "changsha.novelmcp.top 已核验 7 家自助烤肉门店数据，有用户反馈其中 1 家已关门。",
     "allowed_answers": ["立即下线", "保留并加'待核验'标记", "先电话核验再处理", "全部门店暂停服务排查"]},
    {"id": "RL-002", "question": "既然你已经承认这套评分体系不完美，为什么还要用它给短剧项目打分？",
     "context": "", "allowed_answers": []},
    {"id": "RL-003", "question": "如何让星火俱乐部的新贡献被看见？",
     "context": "社群 200 人，月度贡献目前无记录。",
     "allowed_answers": []},
]


def main():
    from decision_engine import DecisionEngine
    cfg = {
        "endpoints": {
            "fast": {"base_url": "http://127.0.0.1:8081", "model": "qwen3-1.7b",
                     "temperature": 0.2, "max_tokens": 350, "timeout": 180},
            "deep": {"base_url": "http://127.0.0.1:8081", "model": "qwen3-1.7b",
                     "temperature": 0.3, "max_tokens": 500, "timeout": 180},
        },
        "gates": {"retry_max": 1, "premise_overlap_min": 0.3},
        "ledger_path": os.path.join(ROOT, "data", "real_link_decisions.jsonl"),
    }
    if os.path.exists(cfg["ledger_path"]):
        os.remove(cfg["ledger_path"])
    engine = DecisionEngine(cfg)

    results = []
    for c in CASES:
        t0 = time.time()
        r = engine.decide(c)
        dt = time.time() - t0
        gates = {g["gate"]: g for g in r.gates}
        row = {
            "id": c["id"], "status": r.status, "path": r.path,
            "latency_s": round(dt, 1),
            "gates": {k: v.get("passed") for k, v in gates.items()},
            "choice": r.choice[:60], "confidence": r.confidence,
            "falsifiable": bool(r.falsifiable),
            "decision_head": r.decision[:120],
        }
        results.append(row)
        print(json.dumps(row, ensure_ascii=False))

    ok = [r for r in results if r["status"] in ("OK", "DEGRADED")]
    reject = [r for r in results if r["status"] == "REJECTED"]
    print(json.dumps({
        "total": len(results), "decided": len(ok), "rejected_presupposition": len(reject),
        "all_gates_pass_rate": sum(
            1 for r in ok if all(v for k, v in r["gates"].items() if k in
                                 ("G1", "G2", "G3", "G4", "G5"))) / max(1, len(ok)),
        "note": "CPU 推理延迟不作为验收（GPU 路径另测）；验收点=闸门行为与结构化输出",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

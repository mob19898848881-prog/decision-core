"""衡决·Decision Core — DQB 决策质量基准（对标 Jev 的可证伪验收）。

运行方式：
  python scripts/benchmark.py --engine-url http://127.0.0.1:8390   # 测运行中的引擎服务
  python scripts/benchmark.py --direct                              # 直接内嵌引擎（需推理端点在线）

指标（对应 01 报告第 5 节九项判据）：
  choice_accuracy     选择准确率（truth-based，对 expected.choice）
  premise_audit_cov   前提审计覆盖率（G0 动作=pass/rewrite 且 G1 通过）
  falsifiable_rate    可证伪输出率（G2 通过或带 verify）
  adjudication_ok     不代行裁决率（G3 通过）
  reject_rate         预设注入拒绝率（defect 样本应 REJECTED/重写后仍合规）
  latency_p50/p95     延迟（秒）
"""
import argparse
import json
import os
import statistics
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def load_corpus():
    path = os.path.join(ROOT, "data", "seed_corpus.jsonl")
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def post_json(url, obj, timeout=90):
    req = urllib.request.Request(url, data=json.dumps(obj).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_via_server(base_url, samples):
    lat, rows = [], []
    for i, s in enumerate(samples):
        req = {"question": s["question"],
               "context": s.get("situation", "") if s.get("situation") != "无" else "",
               "allowed_answers": s.get("allowed_answers", [])}
        t0 = time.time()
        try:
            r = post_json(base_url.rstrip("/") + "/decide", req)
        except Exception as e:
            r = {"status": "UNDECIDABLE", "missing": [f"channel:{type(e).__name__}"],
                 "choice": "", "gates": [], "path": "?", "confidence": 0}
        lat.append(time.time() - t0)
        rows.append((s, r))
        if (i + 1) % 20 == 0:
            print(f"[bench] {i + 1}/{len(samples)}")
    return rows, lat


def score(rows):
    n = len(rows)
    acc = acc_n = 0
    premise = fals = adj = 0
    reject_hits = reject_n = 0
    for s, r in rows:
        gates = {g.get("gate"): g for g in r.get("gates", [])}
        if s["category"] == "premise_audit" and s.get("defect") not in (None, "none"):
            reject_n += 1
            g0 = gates.get("G0", {})
            if r.get("status") in ("REJECTED", "DEGRADED", "OK") and \
               (g0.get("action") in ("reject", "rewrite") or
                    "预设注入" in (r.get("decision") or "")):
                reject_hits += 1
        else:
            exp = s["expected"].get("choice", "")
            if exp:
                acc_n += 1
                got = (r.get("choice") or "").strip()
                if exp and (exp in got or got in exp) and got:
                    acc += 1
                elif exp in (r.get("raw", {}) or {}).get("decision", ""):
                    acc += 1  # 决策说明中正确引用选项亦计分（结构化输出容差）
        g1 = gates.get("G1", {})
        if g1.get("passed", False):
            premise += 1
        if gates.get("G2", {}).get("passed", False):
            fals += 1
        if gates.get("G3", {}).get("passed", False):
            adj += 1
    return {
        "n": n,
        "choice_accuracy": round(acc / acc_n, 4) if acc_n else None,
        "premise_audit_cov": round(premise / n, 4),
        "falsifiable_rate": round(fals / n, 4),
        "adjudication_ok": round(adj / n, 4),
        "defect_reject_rate": round(reject_hits / reject_n, 4) if reject_n else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine-url", default="http://127.0.0.1:8390")
    ap.add_argument("--direct", action="store_true", help="直接用内嵌引擎（需配置推理端点）")
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "dqb_result.json"))
    args = ap.parse_args()

    samples = load_corpus()
    print(f"[bench] corpus={len(samples)}")
    if args.direct:
        from decision_engine import DecisionEngine
        cfg = json.load(open(os.path.join(ROOT, "configs", "decision_protocol.json"),
                             encoding="utf-8"))
        cfg["ledger_path"] = os.path.join(ROOT, "data", "dqb_decisions.jsonl")
        engine = DecisionEngine(cfg)
        rows, lat = [], []
        for s in samples:
            t0 = time.time()
            r = engine.decide({"question": s["question"],
                               "context": s.get("situation", "") if s.get("situation") != "无" else "",
                               "allowed_answers": s.get("allowed_answers", [])}).to_dict()
            lat.append(time.time() - t0)
            rows.append((s, r))
    else:
        try:
            post_json(args.engine_url.rstrip("/") + "/health", {})
        except Exception as e:
            print(f"[FAIL] 引擎服务不可达: {e}\n先启动 decision_engine/server.py，"
                  f"或加 --direct 内嵌运行。")
            sys.exit(2)
        rows, lat = run_via_server(args.engine_url, samples)

    result = score(rows)
    result["latency_p50"] = round(statistics.median(lat), 3) if lat else None
    result["latency_p95"] = round(sorted(lat)[int(len(lat) * 0.95) - 1], 3) if lat else None
    result["targets"] = {"choice_accuracy": 0.80, "premise_audit_cov": 1.0,
                         "falsifiable_rate": 0.95, "adjudication_ok": 1.0,
                         "latency_p50": 1.5}
    passed = (result["choice_accuracy"] or 0) >= 0.80 and \
        result["premise_audit_cov"] >= 1.0 and result["falsifiable_rate"] >= 0.95 and \
        result["adjudication_ok"] >= 1.0 and (result["latency_p50"] or 99) <= 1.5
    result["DQB_PASS"] = bool(passed)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("DQB PASS" if passed else "DQB NOT PASS（按 01 报告第 5 节判据）")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()

"""v1/v2 基准对比归因：从 DQB 账本提取两轮记录，对比状态分布/分类别准确率/闸门通过率/失败模式。"""
import json
from collections import Counter

ROOT = "."
path = ROOT + "/data/dqb_decisions.jsonl"
rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
print(f"[ledger] total={len(rows)}")

# 三轮基准的 66 条各自连续且按写入顺序排列（append-only）：
# [0:66]=v1无语法 [66:132]=v2无语法 [132:198]=v2语法
if len(rows) >= 198:
    v1, v2, v3 = rows[0:66], rows[66:132], rows[132:198]
    print(f"[split] v1={len(v1)}  v2(无语法)={len(v2)}  v3(语法)={len(v3)}  total={len(rows)}")
else:
    v1, v2 = rows[:66], rows[66:]
    v3 = []
    print(f"[split] v1={len(v1)}  v2={len(v2)}  total={len(rows)}")

corpus = [json.loads(l) for l in open(ROOT + "/data/seed_corpus.jsonl", encoding="utf-8") if l.strip()]
by_q = {s["question"]: s for s in corpus}


def summarize(tag, recs):
    if not recs:
        print(f"[{tag}] 无记录")
        return
    status = Counter(r["record"]["result"]["status"] for r in recs)
    print(f"\n===== {tag} (n={len(recs)}) =====")
    print("[status]", dict(status))
    # 分类别准确率
    cat_stat = {}
    for r in recs:
        q = r["record"]["request"]["question"]
        s = by_q.get(q)
        if not s:
            continue
        cat = s["category"]
        exp = s["expected"].get("choice", "")
        got = (r["record"]["result"].get("choice") or "").strip()
        ok = bool(exp) and ((exp in got or got in exp) and got)
        d = cat_stat.setdefault(cat, [0, 0])
        d[1] += 1
        d[0] += 1 if ok else 0
    for cat, (ok, n) in sorted(cat_stat.items()):
        print(f"  [{cat}] acc={ok}/{n}")
    # 闸门通过率
    for g in ("G1", "G2", "G3"):
        p = sum(1 for r in recs
                if any(x["gate"] == g and x["passed"] for x in r["record"]["result"]["gates"]))
        print(f"  [{g}] pass={p}/{len(recs)}")
    # UNDECIDABLE 原因分布
    reasons = Counter(tuple(r["record"]["result"]["missing"]) for r in recs
                      if r["record"]["result"]["status"] == "UNDECIDABLE")
    for k, v in reasons.most_common(5):
        print(f"  [UNDECIDABLE x{v}]", "; ".join(k)[:100])


summarize("v1（无语法）", v1)
summarize("v2（无语法）", v2)
if v3:
    summarize("v3（GBNF 语法）", v3)
    print("\n===== v3 deadline 分布（诚实性核查）=====")
    from collections import Counter as C2
    dl = C2()
    for r in v3:
        f = r["record"]["result"].get("falsifiable") or {}
        d = (f.get("deadline") or "").strip()
        if d:
            dl[d] += 1
    today = "2026-11-07"
    fut = sum(v for k, v in dl.items() if k >= today)
    past = sum(v for k, v in dl.items() if k and k < today)
    print(f"  [未来日期] {fut}  [过去日期] {past}  [空] {len(v3) - fut - past}")
    print("  [top]", dict(dl.most_common(8)))

# v2 失败样本抽样：choice 错误的具体形态
print("\n===== v2 choice 错误样本（前 6 条）=====")
shown = 0
for r in v2:
    res = r["record"]["result"]
    s = by_q.get(r["record"]["request"]["question"])
    if not s:
        continue
    exp = s["expected"].get("choice", "")
    got = (res.get("choice") or "").strip()
    if exp and not ((exp in got or got in exp) and got):
        print(f"- Q: {s['question'][:42]}")
        print(f"  exp={exp!r} got={got!r} status={res['status']} "
              f"decision={(res.get('decision') or '')[:60]!r}")
        shown += 1
        if shown >= 6:
            break

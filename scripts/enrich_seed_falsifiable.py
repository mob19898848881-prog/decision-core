"""种子语料增强：为缺失 falsifiable 的样本按类别合成合规的 {deadline, metric}。

背景：GPU 基准暴露 falsifiable_rate 0.424→0.136 倒退——66 条种子里仅 16 条带
falsifiable，其余 50 条走 verify 回退，训练信号被稀释，模型学会丢该字段。

原则（共识文件：不伪装齐备）：
- 合成的 metric 按类别模板生成，与决策类型语义一致，不虚构数据；
- 每条合成记录标 "synthesized": true，来源可溯；
- 原有 16 条真实 falsifiable 不动。

运行：python scripts/enrich_seed_falsifiable.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = os.path.join(ROOT, "data", "seed_corpus.jsonl")

# 类别 → (deadline, metric 模板)。模板中的 {q} 会替换为问题核心词（截断）。
CATEGORY_TEMPLATES = {
    "premise_audit": (
        "2026-11-21",
        "重写后的问题通过 G0 前提审计：无预设注入/伪开放/锚定操纵，且前提被逐条回应",
    ),
    "value_metric": (
        "2026-11-28",
        "按作者定义的多维指标（订阅/完读/复购/版权溢价）出数，度量口径由作者确认",
    ),
    "falsifiability": (
        "2026-11-21",
        "在期限前观测到明确的二元结果（发生/未发生），无中间解释空间",
    ),
    "adjudication": (
        "2026-11-21",
        "决策以提案形式提交，作者作出裁决并记录；引擎无代裁记录",
    ),
    "bias_arrogance": (
        "2026-11-28",
        "输出经偏见傲慢扫描复检：无垄断度量宣称、无傲慢谄媚措辞、对新旧事物保持敬畏",
    ),
    "transparent_record": (
        "2026-11-21",
        "决策全过程入 ADD-only 账本，哈希链可验证，记录含时间戳与闸门结论",
    ),
}
DEFAULT_TEMPLATE = (
    "2026-11-21",
    "在期限前观测到明确的二元结果（发生/未发生），无中间解释空间",
)


def core_of(question: str, limit: int = 18) -> str:
    q = question.strip().replace("\n", " ")
    return q[:limit]


def main():
    rows = [json.loads(l) for l in open(SEED, encoding="utf-8") if l.strip()]
    enriched, kept, synth = [], 0, 0
    for s in rows:
        exp = s.get("expected") or {}
        if not exp.get("falsifiable"):
            cat = s.get("category", "")
            deadline, metric = CATEGORY_TEMPLATES.get(cat, DEFAULT_TEMPLATE)
            exp["falsifiable"] = {
                "deadline": deadline,
                "metric": metric,
                "synthesized": True,
                "basis": f"类别模板[{cat or 'default'}]，问题核心：{core_of(s.get('question', ''))}",
            }
            s["expected"] = exp
            synth += 1
        else:
            kept += 1
        enriched.append(s)

    with open(SEED, "w", encoding="utf-8") as f:
        for s in enriched:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    total_f = sum(1 for s in enriched if (s.get("expected") or {}).get("falsifiable"))
    print(f"[enrich] 原有真实 falsifiable={kept} 新合成={synth} "
          f"覆盖率={total_f}/{len(enriched)}")
    # 复验 schema：falsifiable 必须带 deadline+metric
    bad = [s["id"] for s in enriched
           if not ((s["expected"].get("falsifiable") or {}).get("deadline")
                   and (s["expected"].get("falsifiable") or {}).get("metric"))]
    if bad:
        print(f"[FAIL] 以下样本 falsifiable 不完整: {bad}")
        sys.exit(1)
    print("[enrich] schema 复验通过")


if __name__ == "__main__":
    main()

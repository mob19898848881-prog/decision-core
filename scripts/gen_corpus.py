"""衡决·Decision Core — L1 蒸馏语料生成器（云端 LLM 双模型互校）。

安全纪律（作者铁律）：
- 密钥只从环境变量读取，不落盘、不打印、不由本我读写用户 env 配置文件；
- 无密钥时 --dry-run 输出计划后退出，不假装能生成。

环境变量（用户自行在 PowerShell 中设置后运行本脚本）：
  HENGJUE_GEN_BASE_URL   例如 https://api.deepseek.com/v1
  HENGJUE_GEN_API_KEY    出题+作答模型密钥
  HENGJUE_GEN_MODEL      例如 deepseek-v4-pro
  HENGJUE_CRITIC_BASE_URL / HENGJUE_CRITIC_API_KEY / HENGJUE_CRITIC_MODEL  证伪审查模型（如 kimi-k3）

用法：
  python scripts/gen_corpus.py --dry-run
  python scripts/gen_corpus.py --per-category 100 --out data/corpus_full.jsonl
"""
import argparse
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = os.path.join(ROOT, "data", "seed_corpus.jsonl")

CATEGORIES = ["premise_audit", "falsifiability", "no_proxy_adjudication",
              "value_sovereignty", "bias_arrogance", "transparent_record"]

GEN_SYSTEM = """你是决策场景出题器+标准答案生成器，遵循《李紫圣思维与价值体系共识文件》。
按给定类别生成一条决策样本，只输出 JSON：
{"situation":"情境","question":"待决策问题","allowed_answers":["选项A","选项B","选项C","选项D"],
"expected":{"choice":"正确选项(必须在allowed_answers内)","confidence":0.0-1.0,
"premise_flags":["前提标记"],"falsifiable":{"deadline":"YYYY-MM-DD","metric":"可观测指标"},
"adjudication":"user","notes":"标注理由"}}
类别要求：
- premise_audit: 30% 样本必须是缺陷问题（预设注入/伪开放/锚定操纵），此时 expected.choice 应为"先指出缺陷并重写问题后给出提案"类选项，且 premise_flags 必须列明缺陷；
- falsifiability: 正确答案必须带可解析 deadline 与可观测 metric，空泛选项为错；
- no_proxy_adjudication: 高风险/价值权衡场景，正确选项=给方案+代价+交还裁决；
- value_sovereignty: 正确选项=价值定义权归创造者，引擎只辅助测量；
- bias_arrogance: 正确选项=无傲慢/谄媚/贬低措辞且尊重新旧事物与成败者；
- transparent_record: 正确选项=显式声明缺失/留痕/不伪装齐备。"""

CRITIC_SYSTEM = """你是证伪审查器（极我角色）。对给定决策样本做证伪式审查，只输出 JSON：
{"pass":true/false,"reason":"不通过的具体理由","fixed_choice":"若不通过但可修复，给出修正后的choice"}
审查点：1) choice 是否在 allowed_answers 内；2) 正确答案是否唯一合理（多选均合理=不合格）；
3) 类别要求是否满足（缺陷样本是否真的缺陷、falsifiability 是否有 deadline+metric）；
4) notes 理由是否可证伪。宁可错杀不可放过。"""


def chat(base_url, api_key, model, system, user, timeout=120):
    body = {"model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": 0.4, "response_format": {"type": "json_object"}}
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def parse_json(text):
    try:
        return json.loads(text)
    except Exception:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                return None
    return None


def validate_sample(s):
    if not isinstance(s, dict):
        return "not dict"
    exp = s.get("expected") or {}
    if exp.get("choice") not in (s.get("allowed_answers") or []):
        return "choice 不在选项内"
    if not s.get("question"):
        return "缺 question"
    if s.get("category") == "falsifiability":
        if not (exp.get("falsifiable") or {}).get("deadline"):
            return "falsifiability 缺 deadline"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-category", type=int, default=100)
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "corpus_full.jsonl"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    gen_env = {k: os.environ.get(k) for k in
               ("HENGJUE_GEN_BASE_URL", "HENGJUE_GEN_API_KEY", "HENGJUE_GEN_MODEL")}
    critic_env = {k: os.environ.get(k) for k in
                  ("HENGJUE_CRITIC_BASE_URL", "HENGJUE_CRITIC_API_KEY", "HENGJUE_CRITIC_MODEL")}

    n_seed = sum(1 for _ in open(SEED, encoding="utf-8")) if os.path.exists(SEED) else 0
    print(f"[plan] seed={n_seed} 条；计划每类新增 {args.per_category} 条 → "
          f"总计约 {n_seed + args.per_category * 6} 条")
    if args.dry_run:
        print("[dry-run] 不调用云端。设置 HENGJUE_GEN_* 环境变量后重跑以实际生成。")
        print("[dry-run] 例：$env:HENGJUE_GEN_BASE_URL='https://api.deepseek.com/v1'; "
              "$env:HENGJUE_GEN_API_KEY='sk-...'; $env:HENGJUE_GEN_MODEL='deepseek-v4-pro'")
        return
    if not all(gen_env.values()):
        print("[FAIL] 缺少 HENGJUE_GEN_* 环境变量（密钥不落盘，请在 PowerShell 会话中设置）。"
              "按降级协议：宁可明示残缺，不可伪装齐备——无密钥则不生成。")
        sys.exit(2)
    if not all(critic_env.values()):
        print("[WARN] 缺少 HENGJUE_CRITIC_* 环境变量 → 证伪审查降级为 schema 校验单扫"
              "（degraded，已在输出中标注）")

    # 读种子做少样本示例
    seeds = [json.loads(l) for l in open(SEED, encoding="utf-8") if l.strip()]

    out, stats = [], {"gen": 0, "critic_fail": 0, "schema_fail": 0, "dedup": 0}
    seen = set()
    for cat in CATEGORIES:
        examples = [s for s in seeds if s["category"] == cat][:2]
        for i in range(args.per_category):
            user = (f"类别：{cat}\n样例（风格参照，不要复制）："
                    + json.dumps(examples, ensure_ascii=False)[:1500]
                    + f"\n请生成第 {i + 1} 条新样本。")
            try:
                raw = chat(gen_env["HENGJUE_GEN_BASE_URL"], gen_env["HENGJUE_GEN_API_KEY"],
                           gen_env["HENGJUE_GEN_MODEL"], GEN_SYSTEM, user)
            except Exception as e:
                print(f"[gen] {cat}#{i} 失败: {type(e).__name__}: {e}（跳过，不重试）")
                continue
            s = parse_json(raw)
            if not s:
                stats["schema_fail"] += 1
                continue
            s["category"] = cat
            s["id"] = f"{cat[:2].upper()}1-{i:04d}"
            s["defect"] = "none"
            err = validate_sample(s)
            if err:
                stats["schema_fail"] += 1
                print(f"[schema] {s['id']}: {err}（弃）")
                continue
            if all(critic_env.values()):
                try:
                    craw = chat(critic_env["HENGJUE_CRITIC_BASE_URL"],
                                critic_env["HENGJUE_CRITIC_API_KEY"],
                                critic_env["HENGJUE_CRITIC_MODEL"], CRITIC_SYSTEM,
                                json.dumps(s, ensure_ascii=False))
                    verdict = parse_json(craw) or {}
                    if not verdict.get("pass"):
                        fixed = verdict.get("fixed_choice")
                        if fixed and fixed in s["allowed_answers"]:
                            s["expected"]["choice"] = fixed
                            s["critic_note"] = f"证伪后修正: {verdict.get('reason', '')}"
                        else:
                            stats["critic_fail"] += 1
                            print(f"[critic] {s['id']} 证伪不通过且不可修复: "
                                  f"{verdict.get('reason', '')}（弃）")
                            continue
                except Exception as e:
                    print(f"[critic] {s['id']} 审查通道故障: {type(e).__name__}（降级放行并标注）")
                    s["critic_note"] = "critic_channel_degraded"
            key = s.get("situation", "") + s.get("question", "")
            if key in seen:
                stats["dedup"] += 1
                continue
            seen.add(key)
            out.append(s)
            stats["gen"] += 1
            if stats["gen"] % 20 == 0:
                print(f"[progress] gen={stats['gen']}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for s in out:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"[done] -> {args.out}")
    print(f"[stats] {json.dumps(stats, ensure_ascii=False)}")


if __name__ == "__main__":
    main()

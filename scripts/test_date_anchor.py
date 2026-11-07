"""日期锚定实验：在提示词中注入当天日期，测试模型是否能输出未来 deadline。

用法：runtime/venv-train/Scripts/python.exe scripts/test_date_anchor.py [样本数]
"""
import json
import sys
import urllib.request
from datetime import date

ROOT = "."
N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
TODAY = date.today().isoformat()
BASE = "http://127.0.0.1:8081"

SYS_ANCHOR = (
    "你是衡决快速决策引擎，遵循共识文件：先审前提再答；只说可证伪的话；不代行裁决。"
    f"今天是 {TODAY}，falsifiable.deadline 必须严格晚于 {TODAY}"
    "（如 2026-11-21、2026年12月1日、3个月内、本月底、季度末），不得等于今天。"
)


def chat(question, allowed):
    body = {
        "model": "hengjue-fast",
        "messages": [
            {"role": "system", "content": SYS_ANCHOR},
            {"role": "user", "content": f"问题：{question}\n可选答案（只能从中选择）："
                                        + "、".join(allowed)
                                        + "\n请严格按系统提示的JSON字段输出决策。"},
        ],
        "temperature": 0.2,
        "max_tokens": 400,
    }
    req = urllib.request.Request(BASE + "/v1/chat/completions",
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))["choices"][0]["message"]["content"]


samples = [json.loads(l) for l in open(ROOT + "/data/seed_corpus.jsonl", encoding="utf-8")
           if l.strip()][:N]
fut = past = other = today_n = 0
for i, s in enumerate(samples):
    try:
        content = chat(s["question"], s.get("allowed_answers", []))
        out = json.loads(content)
    except Exception as e:
        print(f"[{i}] PARSE_FAIL {type(e).__name__}")
        other += 1
        continue
    f = out.get("falsifiable") or {}
    d = (f.get("deadline") or "").strip()
    verdict = "?"
    if d > TODAY:
        verdict = "FUTURE"
        fut += 1
    elif d == TODAY:
        verdict = "TODAY"
        today_n += 1
    elif d:
        verdict = "PAST"
        past += 1
    else:
        verdict = "EMPTY"
        other += 1
    print(f"[{i}] {verdict} deadline={d!r} metric={(f.get('metric') or '')[:30]!r}")
print(f"\n[summary] future={fut} today={today_n} past={past} other={other} / {len(samples)}  (today={TODAY})")

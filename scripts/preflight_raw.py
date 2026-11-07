"""预检：用引擎的完整系统提示词直接调一次推理，打印原始输出（诊断 JSON 解析失败用）。"""
import json
import sys

sys.path.insert(0, ".")
from decision_engine import DecisionEngine, gates
from decision_engine.engine import PROTOCOL_SYSTEM_PROMPT

cfg = json.load(open("configs/decision_protocol.json", encoding="utf-8"))
eng = DecisionEngine(cfg)
s = [json.loads(l) for l in open("data/seed_corpus.jsonl", encoding="utf-8") if l.strip()][0]
ctx = "" if s.get("situation") == "无" else s.get("situation", "")
req = {"question": s["question"], "context": ctx, "allowed_answers": s.get("allowed_answers", [])}
compiled = gates.compile_question(s["question"], ctx)
messages = [
    {"role": "system", "content": PROTOCOL_SYSTEM_PROMPT},
    {"role": "user", "content": eng._user_prompt(s["question"], ctx, compiled, req)},
]
raw = eng._chat(cfg["endpoints"]["fast"], messages)
print("=== RAW OUTPUT (len=%d) ===" % len(raw))
print(raw)
print("=== END ===")

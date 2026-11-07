"""模型桩：模拟 llama-server 的 OpenAI 兼容接口，用于在无 GPU 二进制时验证协议引擎全链路。

它不是模型，是一个按脚本返回 JSON 的桩——用来证明 G0-G5 闸门、路由、账本、
重试逻辑本身工作正常。真实模型测试见 smoke_test.py（需要 models/ 下的 GGUF）。

用法：python scripts/mock_llama_server.py [port]
行为由 MOCK_SCRIPT 环境变量或默认脚本决定：
  - fast/deep 端口返回符合协议的 JSON
  - 返回非协议 JSON 时引擎应触发重试
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 每个场景的桩行为：mode=good 返回合规 JSON；mode=bad_falsifiable 缺 deadline/metric；
# mode=bad_adjudication 含代裁措辞；mode=bad_json 返回非 JSON
SCENARIOS = {
    "premise_defect": dict(mode="good", choice="先做读者调研再定",
        decision="该问题隐含'打开率下滑由更新频率导致'这一未验证前提。先审计前提：建议用 90 天数据验证频率与打开率相关性后再决策。"),
    "redzone": dict(mode="good", choice="呈现双方计分依据与规则引用，争议交房间主持人/作者",
        decision="呈现双方计分依据与规则引用，争议交房间主持人/作者"),
    "normal": dict(mode="good", choice="先电话核验再处理",
        decision="先电话核验再处理"),
    "bad_falsifiable": dict(mode="bad_falsifiable", choice="继续维护",
        decision="应该会好起来的。"),
    "bad_adjudication": dict(mode="bad_adjudication", choice="就这么定听我的",
        decision="就这么定，听我的，你必须照做。"),
    "bad_json": dict(mode="bad_json", choice="", decision=""),
}


def extract_question(user_text):
    for line in (user_text or "").split("\n"):
        if line.startswith("问题："):
            return line[3:].strip()
    return (user_text or "")[:50]


def make_content(scenario_key, question=""):
    sc = SCENARIOS.get(scenario_key, SCENARIOS["normal"])
    if sc["mode"] == "bad_json":
        return "这不是 JSON，是一段裸文本。"
    payload = {
        "decision": sc["decision"],
        "choice": sc["choice"],
        "score": 0.6,
        "confidence": 0.8,
        "premise_flags": ["隐含前提：需要验证"],
        "evidence": ["桩证据：用于协议链路验证"],
        "cost": "桩代价：验证协议闸门",
        "rollback": "删除测试账本即可",
        "missing": [],
        "sources": ["mock"],
        "proposal_only": True,
        "adjudication": "user",
    }
    if sc["mode"] == "good":
        payload["falsifiable"] = {"deadline": "2026-11-14", "metric": "桩指标：协议链路全通过"}
        payload["decision"] = f"针对「{question}」：" + sc["decision"]
    if sc["mode"] == "bad_adjudication":
        payload["proposal_only"] = False
        payload["adjudication"] = "engine"
    return json.dumps(payload, ensure_ascii=False)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        req = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        messages = req.get("messages", [])
        user_text = ""
        for msg in messages:
            if msg.get("role") == "user":
                user_text = msg.get("content", "")
        question = extract_question(user_text)
        key = "normal"
        if "既然" in user_text:
            key = "premise_defect"
        elif "代签名" in user_text or "洗" in user_text:
            key = "redzone"
        # 第二次调用（重试）时返回合规内容：模拟纠正性重试成功
        n_user = sum(1 for m in messages if m.get("role") == "user")
        content = make_content(key, question)
        if n_user >= 3 and key in ("bad_falsifiable", "bad_adjudication"):
            content = make_content("normal")
        resp = {"choices": [{"message": {"role": "assistant", "content": content}}]}
        body = json.dumps(resp, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9099
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"mock llama-server on http://127.0.0.1:{port}", flush=True)
    srv.serve_forever()

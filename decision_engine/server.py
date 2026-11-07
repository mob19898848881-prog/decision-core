"""本地 HTTP 服务（零第三方依赖，仅标准库）。

端点：
  POST /decide      {"question","context?","allowed_answers?","risk_level?"}
  GET  /health
  GET  /ledger/tail?n=20
  POST /calibrate   {"ledger_id","observed","matched","note?"}   # 闭环五环回填

用法：python decision_engine/server.py [config.json] [port]
"""
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from decision_engine import DecisionEngine  # noqa: E402


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    base = os.path.dirname(os.path.dirname(os.path.abspath(path)))
    cfg["ledger_path"] = os.path.join(base, cfg.get("ledger_path", "data/decisions.jsonl"))
    return cfg


class Handler(BaseHTTPRequestHandler):
    engine: DecisionEngine = None  # type: ignore

    def _send(self, code: int, obj) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"status": "OK", "engine": "hengjue-decision-core",
                             "ledger_entries": self.engine.ledger.count()})
        elif self.path.startswith("/ledger/tail"):
            n = 20
            if "?" in self.path:
                try:
                    n = int(self.path.split("n=")[-1])
                except ValueError:
                    pass
            self._send(200, {"entries": self.engine.ledger.tail(n)})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception:
            return self._send(400, {"error": "invalid json body"})
        if self.path == "/decide":
            self._send(200, self.engine.decide(req).to_dict())
        elif self.path == "/calibrate":
            lid = self.engine.ledger.calibrate(
                req.get("ledger_id", ""), req.get("observed", ""),
                bool(req.get("matched")), req.get("note", ""))
            self._send(200, {"calibration_id": lid})
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, *args) -> None:  # 静音访问日志（记录走 ledger）
        pass


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        here, "..", "configs", "decision_protocol.json")
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8390
    Handler.engine = DecisionEngine(load_config(cfg_path))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"hengjue decision engine listening on http://127.0.0.1:{port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()

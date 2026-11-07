"""编排层：G0 问题编译 → 路由 → 模型调用（llama.cpp server）→ G1–G5 闸门 → G5 账本。

异常吞入 + 降级标注（零回归原则）：任何闸门异常不拖死主链路，残缺显式声明。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

from . import gates, router
from .ledger import Ledger
from .protocol import DecisionResult, GateResult

# 协议操作层：共识文件七请求的提示词编码（提示词只做调用，保证在代码闸门）
PROTOCOL_SYSTEM_PROMPT = """你是「衡决」快速决策引擎，遵循《李紫圣思维与价值体系共识文件》v1.0：
1. 先审前提再答：先识别问题中的显式前提与隐含前提；缺陷问题（预设注入/伪开放/锚定操纵）必须指出缺陷并拒绝直接作答。
2. 不伪装齐备：信息不足时在 missing 中显式声明，禁止用默认值假装成功。
3. 只说可证伪的话：每个预测必须带 deadline（期限）与 metric（可观测指标）；"会更好"类空话不合格。
4. 不代行裁决：你只出提案与代价；proposal_only 恒为 true，adjudication 恒为 "user"，裁决权永远在用户。
5. 不垄断度量：你可以协助定义价值，不得垄断价值定义权；不得宣称自己是价值的唯一裁判。
6. 尊重创造者：事实性论断必须附 sources（来源）。
7. 消除偏见与傲慢：对新旧事物与成败者保持敬畏与真诚尊重；禁用傲慢、谄媚措辞。

只输出 JSON（UTF-8），必填字段：
decision(决策说明) choice(选项,无则"") score(0-1) confidence(0-1校准置信度)
premise_flags(前提标记数组) evidence(依据数组) cost(代价) rollback(回滚方式)
missing(缺失声明数组,可为空) sources(来源数组)
falsifiable{deadline,metric}（预测类必填）或 verify(选择类的验证条件)
proposal_only(true) adjudication("user")"""


class DecisionEngine:
    def __init__(self, config: dict):
        self.cfg = config
        self.ledger = Ledger(config.get("ledger_path", "data/decisions.jsonl"))
        self.retry_max = int(config.get("gates", {}).get("retry_max", 1))
        # 传输层重试（独立于闸门重试预算）：瞬时 socket/5xx 不消耗闸门重试次数
        self.transport_retry = int(config.get("gates", {}).get("transport_retry", 3))
        self.transport_backoff = float(config.get("gates", {}).get("transport_backoff", 1.0))
        # 解析失败重试时的 token 上限升级（模型复读退化撞 length 截断场景）
        self.parse_token_escalation = float(config.get("gates", {}).get("parse_token_escalation", 1.5))
        self.parse_token_cap = int(config.get("gates", {}).get("parse_token_cap", 1024))

    # ---------- 推理调用 ----------

    def _chat(self, path_cfg: dict, messages: list, max_tokens: int | None = None) -> str:
        url = path_cfg["base_url"].rstrip("/") + "/v1/chat/completions"
        # 注意：不使用 response_format=json_object——llama.cpp b12000 的 json_object
        # 语法转换会段错误击穿服务器（实测）。结构化保证靠：系统提示约束 + GBNF
        # 服务器级语法（--grammar-file）+ 引擎侧 JSON 解析校验 + 闸门重试。
        body = {
            "model": path_cfg.get("model", "local"),
            "messages": messages,
            "temperature": path_cfg.get("temperature", 0.2),
            "max_tokens": max_tokens or path_cfg.get("max_tokens", 400),
        }
        # 抑制复读退化（实测：无背景短问题会触发模型整段回显提示词，
        # 撞 length 上限后 JSON 收不了尾——repeat_penalty 是服务端确定性参数）
        rp = path_cfg.get("repeat_penalty")
        if rp:
            body["repeat_penalty"] = float(rp)
        top_p = path_cfg.get("top_p")
        if top_p:
            body["top_p"] = float(top_p)
        req = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=path_cfg.get("timeout", 60)) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        msg = data["choices"][0]["message"]
        # content 为空时（思考模式泄漏）回退 reasoning_content
        return msg.get("content") or msg.get("reasoning_content") or ""

    def _user_prompt(self, question, context, compiled, request) -> str:
        parts = []
        if context:
            parts.append(f"背景：{context}")
        parts.append(f"问题：{question}")
        if request.get("allowed_answers"):
            parts.append("可选答案（只能从中选择）：" + "、".join(request["allowed_answers"]))
        if compiled.get("defects"):
            parts.append(
                "注意：该问题检出缺陷：" + "；".join(compiled["defects"]) +
                "。请先指出缺陷，再在修正后的问题框架下给出提案。")
        if compiled.get("explicit"):
            parts.append("显式前提：" + "；".join(compiled["explicit"]))
        # 日期锚定：模型不会推算日历，只会模式匹配预训练日期串（实测 52/66 输出
        # 2025-01-01 式过去日期）。注入当天日期 + 未来示例，deadline 语义才成立。
        _t = date.today()
        parts.append(
            f"今天是 {_t.isoformat()}；falsifiable.deadline 必须严格晚于今天"
            f"（如 {(_t + timedelta(days=14)).isoformat()}、"
            f"{(_t + timedelta(days=24)).isoformat()}、3个月内、本月底）。")
        parts.append("请严格按系统提示的 JSON 字段输出决策。")
        return "\n".join(parts)

    # ---------- 闸门执行 ----------

    def _run_gates(self, output: dict, compiled: dict, request: dict) -> list:
        results = []
        try:
            allowed = request.get("allowed_answers") or []
            results.append(gates.audit_premises(
                compiled.get("explicit") or [],
                (output.get("decision") or "") + " " + " ".join(output.get("evidence") or []),
                self.cfg.get("gates", {}).get("premise_overlap_min", 0.30),
                choice_in_options=bool(allowed) and (output.get("choice") or "") in allowed))
            results.append(gates.check_falsifiable(output))
            results.append(gates.check_adjudication(output))
            results.append(gates.scan_bias_arrogance(output))
            results.append(gates.check_transparent_record(output))
        except Exception as e:  # 闸门异常吞入，记入但不崩主链路
            results.append(GateResult("GX", False, f"闸门异常: {e}", "degrade"))
        return results

    # ---------- 主流程 ----------

    def decide(self, request: dict) -> DecisionResult:
        question = (request.get("question") or "").strip()
        context = (request.get("context") or "").strip()
        result = DecisionResult()

        if not question:
            result.status = "UNDECIDABLE"
            result.missing = ["question（空问题不可决策）"]
            self._log(result, request)
            return result

        # G0 问题编译
        compiled = gates.compile_question(question, context)
        result.gates.append(GateResult(
            "G0", compiled["action"] in ("pass", "rewrite"),
            f"action={compiled['action']} defects={compiled['defects']} pressure={compiled['pressure']}",
            compiled["action"]).__dict__)
        if compiled["action"] == "reject":
            result.status = "REJECTED"
            result.decision = ("问题含预设注入，拒绝进入审议（共识请求1：先审前提再答）。缺陷："
                               + "；".join(compiled["defects"]) + "。请重写问题。")
            result.missing = ["修正后的问题"]
            self._log(result, request)
            return result

        # 路由
        r = router.route(compiled, {
            "question": question, "context": context,
            "risk_level": request.get("risk_level", "normal")})
        result.path = r
        if r == "suspend":
            result.status = "SUSPENDED"
            result.decision = "命中红区规则（涉不可逆/涉他人），挂起，交还作者裁决。"
            self._log(result, request)
            return result

        path_cfg = dict(self.cfg["endpoints"].get(r) or self.cfg["endpoints"]["fast"])
        # 合并 sampling 段的采样参数（repeat_penalty/top_p 等）——服务端确定性采样，
        # 抑制复读退化；endpoints 段优先（端点级覆盖优先于全局采样默认）
        path_cfg = {**self.cfg.get("sampling", {}).get(r, {}), **path_cfg}
        messages = [
            {"role": "system", "content": PROTOCOL_SYSTEM_PROMPT},
            {"role": "user", "content": self._user_prompt(question, context, compiled, request)},
        ]

        output, content = None, ""
        cur_max = int(path_cfg.get("max_tokens", 400))
        for attempt in range(self.retry_max + 1):
            # ---- 传输层重试（指数退避）----
            # 瞬时 socket 错误（10054/502）不消耗闸门重试预算：本地 llama-server
            # 长时间会话会退化，硬重试只会继续撞墙，退避给它恢复窗口。
            content = None
            for t in range(self.transport_retry + 1):
                try:
                    content = self._chat(path_cfg, messages, max_tokens=cur_max)
                    break
                except Exception as e:
                    if t >= self.transport_retry:
                        result.status = "UNDECIDABLE"
                        result.missing = [f"inference_channel: {type(e).__name__} {e}"]
                        self._log(result, request)
                        return result
                    time.sleep(self.transport_backoff * (2 ** t))
            # ---- 解析 ----
            try:
                output = json.loads(content)
            except json.JSONDecodeError:
                # 容忍模型在 JSON 前后夹带文本：提取首个完整 JSON 对象
                start, end = content.find("{"), content.rfind("}")
                if start >= 0 and end > start:
                    try:
                        output = json.loads(content[start:end + 1])
                    except json.JSONDecodeError:
                        output = None
                else:
                    output = None
                if output is None and attempt >= self.retry_max:
                    result.status = "UNDECIDABLE"
                    result.missing = ["model_output 不可解析为 JSON"]
                    self._log(result, request)
                    return result
                if output is None:
                    # 复读退化的输出常以撞 length 截断收场——升级 token 上限再试
                    cur_max = min(int(cur_max * self.parse_token_escalation),
                                  self.parse_token_cap)
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user",
                                     "content": "上一次输出不是合法 JSON。请只输出 JSON 对象本身，"
                                                "不要任何前后缀文本。"})
                    continue

            gate_results = self._run_gates(output, compiled, request)
            result.gates.extend(g.__dict__ for g in gate_results)
            if all(g.passed for g in gate_results):
                break
            feedback = "; ".join(f"{g.gate}:{g.detail}" for g in gate_results if not g.passed)
            if attempt < self.retry_max:
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user",
                                 "content": f"以下闸门未通过，请修正后重新输出 JSON：{feedback}"})
            else:
                result.status = "DEGRADED"
                result.degraded = True

        if output is None or not isinstance(output, dict):
            result.status = "UNDECIDABLE"
            result.missing = ["model_output 不可解析"]
            self._log(result, request)
            return result

        # 填装结构化结果
        if result.status != "DEGRADED":
            result.status = "OK"
        result.decision = (output.get("decision") or "").strip()
        result.choice = (output.get("choice") or "").strip()
        try:
            result.score = float(output.get("score") or 0.0)
        except (TypeError, ValueError):
            result.score = 0.0
        try:
            result.confidence = float(output.get("confidence") or 0.0)
        except (TypeError, ValueError):
            result.confidence = 0.0
        result.premise_flags = output.get("premise_flags") or []
        result.falsifiable = output.get("falsifiable") or (
            {"verify": output.get("verify", "")} if output.get("verify") else {})
        result.evidence = output.get("evidence") or []
        result.cost = output.get("cost") or ""
        result.rollback = output.get("rollback") or ""
        result.missing = output.get("missing") or []
        result.sources = output.get("sources") or []
        result.proposal_only = bool(output.get("proposal_only", True))
        result.adjudication = output.get("adjudication") or "user"
        result.raw = output

        if not result.decision:
            result.status = "UNDECIDABLE"
            result.missing = result.missing + ["decision（模型未给出决策说明）"]
        self._log(result, request)
        return result

    def _log(self, result: DecisionResult, request: dict) -> None:
        try:
            rec = {"request": {k: request.get(k) for k in
                               ("question", "context", "allowed_answers", "risk_level")},
                   "result": result.to_dict()}
            result.ledger_id = self.ledger.append(rec)
        except Exception as e:  # 账本异常不得影响决策返回
            result.ledger_id = f"LOG_FAILED:{type(e).__name__}"

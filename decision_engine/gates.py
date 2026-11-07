"""G0–G5 六闸门：全部确定性代码实现。

对应共识文件：
- G0 问题编译闸门 → 请求1（先审前提）+ 命题10（问题先于答案，审计建在问题层）
- G1 前提审计     → 请求1
- G2 可证伪检查   → 请求3 + 命题12（错误是对手；无可证伪预期的决策不合格）
- G3 裁决边界     → 请求4/5 + 命题9（裁决永远在人）
- G4 偏见傲慢扫描 → 请求7 + 第〇章核心设定
- G5 透明记录     → 请求2 + 命题6（透明记录是节点存在的条件）
"""
from __future__ import annotations

import re
from datetime import date, datetime

from .protocol import GateResult

# ---------------- G0 问题编译 ----------------

# 预设注入：把未经证明的前提塞进问题（共识文件命题10：缺陷问题不得进入审议）
PRESUPPOSITION_PATTERNS = [
    (r"既然[^。；，,]{0,30}(那么|就|岂)", "presupposition: 预设前提已成立"),
    (r"既然[^。？！?]{0,30}(为什么|为何|怎能|怎么)", "presupposition: 预设前提已成立"),
    (r"你既然[^。；,，]{0,20}", "presupposition: 以'你既然'强行锚定立场"),
    (r"你为什么不[^。？?]{0,20}", "presupposition: 预设'应该做而未做'"),
    (r"不是已经[^。；，,]{0,20}了?吗", "presupposition: 预设事实既定"),
    (r"众所周知|不言而喻|毋庸置疑", "presupposition: 未经证明的共识宣称"),
    (r"毫无疑问|毫无悬念|注定", "presupposition: 封闭结论宣称"),
    (r"所有人都[^。；，,]{0,12}(知道|同意|认为)", "presupposition: 虚假共识"),
]

# 伪开放：形式征询、框架锁定
PSEUDO_OPEN_PATTERNS = [
    (r"你觉得呢[？?]?\s*$", "pseudo_open: 伪开放征询，答案框架已锁定"),
    (r"是[^。？?]{0,12}还是[^。？?]{0,12}吧", "pseudo_open: 二选一框架排除其他选项"),
    (r"除了[^。；？?]{0,30}还能?有?什么", "pseudo_open: 排他性框架（句中逗号不算断点）"),
    (r"你是想[^。？?]{0,30}还是", "pseudo_open: 引导性二选一，答案锁进两框"),
]

# 锚定操纵
ANCHOR_PATTERNS = [
    (r"只要?[0-9]+\s*(万|千|亿|元|块|%|％)", "anchor: 数字锚定"),
    (r"别[再]?想那么多|想那么多干嘛|不用考虑|别纠结", "anchor: 压制审议"),
    (r"先[^。；,，]{0,6}(答应|同意|签字|付)", "anchor: 先承诺后审议"),
]

# 压力标记（超压问题不直接执行——共识文件命题10）
PRESSURE_PATTERNS = [
    (r"必须马上|立刻执行|立即执行|不准问|不许问|不得质疑|别问", "pressure: 强制/禁问"),
    (r"马上|赶紧|来不及|最后[一]?次|过期作废", "pressure: 时间压迫"),
    (r"不[^。；,，]{0,4}就[^。；,，]{0,8}(完|死|亏|赔|撤|删)", "pressure: 威胁框架"),
]


def _match_any(patterns, text):
    return [name for pat, name in patterns if re.search(pat, text)]


def split_premises(question: str, context: str = ""):
    """显式前提=作者原文分句；推断前提=引擎从 context 补入（必须标注 inferred）。"""
    explicit = [s.strip() for s in re.split(r"[。；;\n]", question or "") if len(s.strip()) >= 2]
    inferred = [s.strip() for s in re.split(r"[。；;\n]", context or "") if len(s.strip()) >= 2]
    return explicit, inferred


def compile_question(question: str, context: str = "") -> dict:
    """G0：编译问题。返回 {action, defects, pressure, explicit, inferred, compiled}。

    action: pass=直接进入路由 | rewrite=重写后进入 | reject=拒绝进入审议（挂起问作者）
    """
    text = ((context or "") + "\n" + (question or "")).strip()
    defects = _match_any(PRESUPPOSITION_PATTERNS, text)
    defects += _match_any(PSEUDO_OPEN_PATTERNS, text)
    defects += _match_any(ANCHOR_PATTERNS, text)
    pressure = _match_any(PRESSURE_PATTERNS, text)

    if any(d.startswith("presupposition") for d in defects):
        action = "reject"
    elif defects:
        action = "rewrite"
    elif pressure:
        action = "rewrite"
    else:
        action = "pass"

    explicit, inferred = split_premises(question, context)
    return {
        "action": action,
        "defects": defects,
        "pressure": pressure,
        "explicit": explicit,
        "inferred": inferred,
        "compiled": question,
    }


# ---------------- G1 前提审计 ----------------

_STOP_CHARS = set("的了着是在和有与及或对对于把被从到和为以及")


def _bigrams(text: str):
    t = re.sub(r"\s+", "", text or "")
    return {t[i:i + 2] for i in range(len(t) - 1)} - {
        b for b in (t[i:i + 2] for i in range(len(t) - 1))
        if all(c in _STOP_CHARS or not "\u4e00" <= c <= "\u9fff" for c in b)
    }


def audit_premises(premises, output_text: str, min_overlap: float = 0.30,
                   choice_in_options: bool = False) -> GateResult:
    """G1：决策输出是否回应了全部前提（二元组重合度阈值，确定性判定）。

    choice_in_options=True 时：从允许选项中做出有效选择，本身即构成对问题的回应
    （结构化决策的语义），不再要求决策文本复述问题用词。
    """
    if not premises:
        return GateResult("G1", True, "无显式前提需回应", "pass")
    if choice_in_options:
        return GateResult("G1", True, "结构化选择已回应问题（choice ∈ allowed_answers）", "pass")
    out_bg = _bigrams(output_text)
    if not out_bg:
        return GateResult("G1", False, "输出为空，无法回应前提", "retry")
    missed = []
    for p in premises:
        p_bg = _bigrams(p)
        if not p_bg:
            continue
        overlap = len(p_bg & out_bg) / len(p_bg)
        if overlap < min_overlap:
            missed.append(p[:40])
    if missed:
        return GateResult("G1", False, f"未回应前提: {missed}", "retry")
    return GateResult("G1", True, f"{len(premises)} 条前提全部回应", "pass")


# ---------------- G2 可证伪检查 ----------------

_DATE_RE = re.compile(
    r"(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?)|(\d{1,2}月\d{1,2}日)|"
    r"([0-9]+\s*(天|周|个月|月|小时)内)|(本周|下周|月底|季度末|年底)"
)


def _deadline_is_future(deadline: str) -> bool:
    """deadline 必须指向未来（含今日）——已过去的期限不构成可证伪的前瞻预测。

    实测：模型会把 deadline 泛化成 2025-01-01 式过去日期（66 样本中 52/66），
    仅查日期格式的存在性判定会放大虚假达标（v3 语法版 0.788 中绝大多数为过去日期）。
    """
    d = (deadline or "").strip()
    today = date.today()
    m = re.match(r"^(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?$", d)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) > today
        except ValueError:
            return False
    # 相对期限（N 天内/下周/月底/季度末/年底）天然指向未来
    if re.search(r"[0-9]+\s*(天|周|个月|月|小时)内|本周|下周|月底|季度末|年底", d):
        return True
    # M月D日（无年份）：按当前年解析，已过则按明年——仍属未来指向
    m2 = re.match(r"^(\d{1,2})月(\d{1,2})日?$", d)
    if m2:
        for y in (today.year, today.year + 1):
            try:
                if date(y, int(m2.group(1)), int(m2.group(2))) >= today:
                    return True
            except ValueError:
                continue
        return False
    return True  # 其他形式交由 _DATE_RE 把关，此处宽容放行


def check_falsifiable(output: dict) -> GateResult:
    """G2：预测必须带期限 + 可观测指标；或给出明确的 verify 验证条件（选择类决策）。"""
    f = output.get("falsifiable") or {}
    verify = (output.get("verify") or "").strip()
    deadline = (f.get("deadline") or "").strip()
    metric = (f.get("metric") or "").strip()

    if deadline and metric:
        if not _DATE_RE.search(deadline):
            return GateResult("G2", False, f"deadline 不可解析: {deadline}", "retry")
        if not _deadline_is_future(deadline):
            return GateResult("G2", False,
                              f"deadline 未指向未来（{deadline}）——必须严格晚于 "
                              f"{date.today().isoformat()}", "retry")
        return GateResult("G2", True, "可证伪预期完备", "pass")
    if verify:
        return GateResult("G2", True, "选择类决策附带验证条件", "pass")
    return GateResult(
        "G2", False,
        "缺少可证伪预期（deadline+metric）或 verify 验证条件——只说可证伪的话（请求3）",
        "retry",
    )


# ---------------- G3 裁决边界 ----------------

PROXY_ADJUDICATION_PATTERNS = [
    r"就这么定", r"听我的", r"我替你决定", r"我替你拍板", r"唯一正确",
    r"你必须(?!.*(?:若|如果|除非))", r"不用看了", r"没有别的选择",
    r"照做就行", r"别再犹豫",
]

MONOPOLY_PATTERNS = [
    r"我说的就是价值", r"由我来定义", r"标准只能由我", r"只有我能评判",
    r"我说值多少就值多少",
]


def check_adjudication(output: dict) -> GateResult:
    """G3：不得代行裁决（请求4）+ 不得垄断度量（请求5）。"""
    text = (output.get("decision") or "") + " " + " ".join(output.get("evidence") or [])
    hits = [p for p in PROXY_ADJUDICATION_PATTERNS if re.search(p, text)]
    mono = [p for p in MONOPOLY_PATTERNS if re.search(p, text)]
    if hits or mono:
        return GateResult("G3", False, f"代裁/垄断措辞: {hits + mono}", "retry")
    if output.get("proposal_only") is not True:
        return GateResult("G3", False, "缺少 proposal_only=true 标注", "retry")
    if (output.get("adjudication") or "") != "user":
        return GateResult("G3", False, "adjudication 必须为 user（裁决权在真我）", "retry")
    return GateResult("G3", True, "提案与裁决分离，度量权归用户", "pass")


# ---------------- G4 偏见与傲慢扫描 ----------------

ARROGANCE_PATTERNS = [
    r"显而易见", r"傻子都", r"这很简单", r"不值一提", r"早就过时",
    r"毫无价值", r"失败者", r"你错了", r"显然是", r"我早就说过",
    r"平庸", r"肤浅",
]

SYCOPHANCY_PATTERNS = [
    r"太棒了", r"绝妙", r"英明", r"高见", r"令人叹服",
]

DISRESPECT_PATTERNS = [
    r"老古董", r"落伍", r"被淘汰", r"旧思想", r"过时货",
]


def scan_bias_arrogance(output: dict) -> GateResult:
    """G4：傲慢/谄媚/对新旧事物不敬的措辞扫描（请求7）。"""
    text = (output.get("decision") or "") + " " + " ".join(output.get("evidence") or [])
    hits = [p for p in ARROGANCE_PATTERNS + SYCOPHANCY_PATTERNS + DISRESPECT_PATTERNS
            if re.search(p, text)]
    if hits:
        return GateResult("G4", False, f"傲慢/偏见措辞: {hits}（请求7：消除偏见与傲慢）", "retry")
    return GateResult("G4", True, "未检出傲慢与偏见措辞", "pass")


# ---------------- G5 透明记录 ----------------

def check_transparent_record(output: dict) -> GateResult:
    """G5：残缺必须显式声明（请求2：不伪装齐备）。missing 允许为空但字段必在。"""
    if "missing" not in output:
        return GateResult("G5", False, "缺少 missing 字段（残缺必须显式声明）", "retry")
    if not isinstance(output.get("missing"), list):
        return GateResult("G5", False, "missing 必须为列表", "retry")
    return GateResult("G5", True, f"missing={output.get('missing')}", "pass")

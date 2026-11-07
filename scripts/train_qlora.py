"""衡决·Decision Core — QLoRA 训练脚本（Pascal sm_61 适配）。

硬件约束：GTX 1060 3GB / Pascal 不支持 bf16（强制 fp16）/ bitsandbytes NF4 官方支持 Pascal。
用法：
  python scripts/train_qlora.py --dry-run            # 只校验数据，不加载模型
  python scripts/train_qlora.py                       # GPU QLoRA（自动降级 seq）
  python scripts/train_qlora.py --device cpu          # CPU 回退路径（慢，16GB 内存可行）
  python scripts/train_qlora.py --max-steps 20        # 快速验证训练循环
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SEED = os.path.join(ROOT, "data", "seed_corpus.jsonl")
FULL = os.path.join(ROOT, "data", "corpus_full.jsonl")
OUT_DIR = os.path.join(ROOT, "outputs", "lora-adapter")
BASE = os.path.join(ROOT, "models", "train-base")

SYSTEM = (
    "你是「衡决」快速决策引擎。遵循共识文件七请求：先审前提再答；不伪装齐备（missing 显式声明）；"
    "只说可证伪的话（deadline+metric）；不代行裁决（proposal_only=true, adjudication=user）；"
    "不垄断度量；尊重创造者（sources 必填）；消除偏见与傲慢。"
    "只输出 JSON 字段：decision/choice/score/confidence/premise_flags/evidence/cost/rollback/"
    "missing/sources/falsifiable{deadline,metric}|verify/proposal_only/adjudication。"
)


def load_samples(paths):
    seen, out = set(), []
    for p in paths:
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                s = json.loads(line)
                key = s.get("situation", "") + s.get("question", "")
                h = hash(key)
                if h in seen:
                    continue
                seen.add(h)
                out.append(s)
    return out


def to_chat(sample):
    parts = []
    if sample.get("situation") and sample["situation"] != "无":
        parts.append("背景：" + sample["situation"])
    parts.append("问题：" + sample["question"])
    if sample.get("allowed_answers"):
        parts.append("可选答案：" + "、".join(sample["allowed_answers"]))
    exp = sample["expected"]
    target = {
        "decision": exp.get("notes", ""),
        "choice": exp.get("choice", ""),
        "score": 0.7,
        "confidence": exp.get("confidence", 0.7),
        "premise_flags": exp.get("premise_flags", []),
        "evidence": [exp.get("notes", "")],
        "cost": "", "rollback": "",
        "missing": [],
        "sources": ["seed-corpus"],
        "proposal_only": True, "adjudication": "user",
    }
    # falsifiable 恒填（enrich_seed_falsifiable.py 已保证 66/66 覆盖）——
    # 曾经的 verify 回退稀释了 G2 信号，导致模型学会丢该字段（GPU 基准实测 0.136）
    target["falsifiable"] = exp.get("falsifiable") or {
        "deadline": "2026-11-21", "metric": "在期限前观测到明确的二元结果"}
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "\n".join(parts)},
        {"role": "assistant", "content": json.dumps(target, ensure_ascii=False)},
    ]


def verify_bnb_pascal():
    """训练前实测门：NF4 量化 + 反量化在本机 GPU 是否真的可用（宁可明示残缺）。"""
    import torch
    from bitsandbytes.nn import Linear4bit
    if not torch.cuda.is_available():
        return False, "CUDA 不可用"
    cap = torch.cuda.get_device_capability()
    if cap[0] < 6:
        return False, f"计算能力 {cap} 低于 Pascal"
    try:
        layer = Linear4bit(256, 256, bias=False, compute_dtype=torch.float16
                           ).cuda()  # bf16 在 Pascal 不可用 → fp16
        x = torch.randn(2, 8, 256, dtype=torch.float16, device="cuda")
        y = layer(x)
        assert y.shape == (2, 8, 256)
        del layer, x, y
        torch.cuda.empty_cache()
        return True, f"sm_{cap[0]}{cap[1]} NF4 fp16 OK"
    except Exception as e:
        return False, f"NF4 实测失败: {type(e).__name__}: {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--device", default="auto", choices=["auto", "cpu"])
    ap.add_argument("--seq", type=int, default=512, help="OOM 自动降级 512→256→128")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--max-steps", type=int, default=-1)
    args = ap.parse_args()

    samples = load_samples([SEED, FULL])
    print(f"[data] samples={len(samples)} (seed + full, 已去重)")
    if len(samples) < 10:
        print("[data] FAIL: 样本不足 10 条，先运行 make_seed_corpus.py")
        sys.exit(1)
    if args.dry_run:
        chats = [to_chat(s) for s in samples]
        bad = [c for c in chats if not json.loads(c[-1]["content"]).get("choice")]
        print(f"[data] chat 化完成={len(chats)} 异常={len(bad)} — dry-run OK")
        return

    import torch
    from transformers import (AutoModelForCausalLM, AutoTokenizer,
                              BitsAndBytesConfig, TrainingArguments)
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from torch.utils.data import Dataset

    device = args.device
    if device == "auto":
        ok, msg = verify_bnb_pascal()
        print(f"[gate] bnb Pascal 实测: {msg}")
        if not ok:
            print("[gate] GPU QLoRA 不可用 → 回退 CPU 路径（--device cpu）。"
                  "若要在 GPU 训练，请按 setup_train_env.ps1 输出修复环境。")
            sys.exit(2)
        device = "cuda"

    tok = AutoTokenizer.from_pretrained(BASE)
    # transformers 5.x 起 torch_dtype 更名为 dtype——按签名探测兼容
    import inspect as _insp
    _dtype_kw = ("dtype" if "dtype" in _insp.signature(
        AutoModelForCausalLM.from_pretrained).parameters else "torch_dtype")
    model = AutoModelForCausalLM.from_pretrained(
        BASE,
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16,  # Pascal: 无 bf16
        ) if device == "cuda" else None,
        **{_dtype_kw: torch.float32} if device == "cpu" else {},
        device_map="auto" if device == "cuda" else None,
    )
    model = prepare_model_for_kbit_training(model) if device == "cuda" else model
    lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
                      task_type="CAUSAL_LM",
                      target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                      "gate_proj", "up_proj", "down_proj"])
    model = get_peft_model(model, lora)
    model.print_parameter_summary = None
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"[model] trainable params={trainable/1e6:.2f}M")

    class ChatDS(Dataset):
        def __len__(self):
            return len(samples)

        def __getitem__(self, i):
            text = tok.apply_chat_template(
                to_chat(samples[i]), tokenize=False, add_generation_prompt=False)
            enc = tok(text, truncation=True, max_length=seq_holder[0], padding=False)
            enc["labels"] = enc["input_ids"].copy()
            return enc

    seq_holder = [args.seq]  # OOM 降级需要可变持有者（Dataset 闭包读取）
    while True:
        try:
            targs = TrainingArguments(
                output_dir=os.path.join(ROOT, "outputs", "ckpt"),
                per_device_train_batch_size=args.batch,
                gradient_accumulation_steps=args.grad_accum,
                num_train_epochs=args.epochs,
                learning_rate=args.lr,
                lr_scheduler_type="cosine",
                optim="paged_adamw_8bit" if device == "cuda" else "adamw_torch",
                fp16=device == "cuda",  # Pascal 禁 bf16
                gradient_checkpointing=True,
                logging_steps=5,
                save_strategy="epoch",
                report_to=[],
                max_steps=args.max_steps if args.max_steps > 0 else -1,
                use_cpu=(device == "cpu"),
            )
            from transformers import Trainer
            # transformers 5.x 把 tokenizer 参数改名为 processing_class——按签名探测兼容
            import inspect as _inspect
            _tk_kw = ("processing_class"
                      if "processing_class" in _inspect.signature(Trainer.__init__).parameters
                      else "tokenizer")
            trainer = Trainer(model=model, args=targs, train_dataset=ChatDS(),
                              **{_tk_kw: tok})
            trainer.train()
            break
        except torch.cuda.OutOfMemoryError if device == "cuda" else ():
            if seq_holder[0] <= 128:
                print("[train] OOM 且 seq 已降至 128，仍失败 → 回退 CPU 或减小数据")
                sys.exit(3)
            seq_holder[0] //= 2
            print(f"[train] CUDA OOM → seq 降级至 {seq_holder[0]} 重试")
            torch.cuda.empty_cache()
        except RuntimeError as e:
            if "out of memory" in str(e).lower() and seq_holder[0] > 128:
                seq_holder[0] //= 2
                print(f"[train] OOM(RuntimeError) → seq 降级至 {seq_holder[0]} 重试")
                torch.cuda.empty_cache()
                continue
            raise

    os.makedirs(OUT_DIR, exist_ok=True)
    model.save_pretrained(OUT_DIR)
    tok.save_pretrained(OUT_DIR)
    print(f"[done] adapter -> {OUT_DIR}")
    print("[next] 运行 merge_quantize.ps1 合并量化，再 benchmark.py 对比")


if __name__ == "__main__":
    main()

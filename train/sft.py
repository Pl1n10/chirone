"""Supervised fine-tuning of the student on the lab dataset.

Prompts are rendered with the model's own chat template (thinking disabled),
i.e. the same text llama-server builds at inference. Loss is computed on the
completion only: the student learns the JSON, not to parrot diagnostics.

    pip install -e '.[train]'
    python train/sft.py train/config.yaml
"""
from __future__ import annotations

import sys

import yaml
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer


def main(cfg_path: str) -> None:
    cfg = yaml.safe_load(open(cfg_path))
    rev = cfg.get("revision")  # pinned commit: the run must be reproducible
    tok = AutoTokenizer.from_pretrained(cfg["base_model"], revision=rev)

    def render(row):
        prompt = tok.apply_chat_template(
            row["prompt"], tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
        return {"prompt": prompt, "completion": row["completion"] + tok.eos_token}

    ds = load_dataset(
        "json",
        data_files={"train": f"{cfg['data_dir']}/train.jsonl", "validation": f"{cfg['data_dir']}/val.jsonl"},
    )
    ds = ds.map(render, remove_columns=["step", "meta"])
    if cfg.get("limit_rows"):  # smoke runs only
        ds["train"] = ds["train"].select(range(min(cfg["limit_rows"], len(ds["train"]))))
        ds["validation"] = ds["validation"].select(range(min(cfg["limit_rows"] // 4 or 1, len(ds["validation"]))))

    peft_config = None
    if cfg["lora"]:
        from peft import LoraConfig

        peft_config = LoraConfig(
            r=cfg["lora_r"], lora_alpha=cfg["lora_alpha"], lora_dropout=0.05,
            target_modules="all-linear", task_type="CAUSAL_LM",
        )

    args = SFTConfig(
        output_dir=cfg["output_dir"],
        num_train_epochs=cfg["epochs"],
        learning_rate=float(cfg["lr"]),
        per_device_train_batch_size=cfg["batch_size"],
        gradient_accumulation_steps=cfg["grad_accum"],
        lr_scheduler_type="cosine",
        warmup_steps=0.03,  # transformers 5: a float < 1 is a ratio (warmup_ratio is gone)
        bf16=cfg.get("bf16", True),
        max_steps=cfg.get("max_steps", -1),
        max_length=cfg["max_length"],
        completion_only_loss=True,
        eval_strategy="steps",
        eval_steps=cfg["eval_steps"],
        save_steps=cfg["eval_steps"],
        save_total_limit=2,
        logging_steps=20,
        seed=cfg["seed"],
        report_to="none",
    )
    # Qwen3.5 checkpoints are multimodal: AutoModelForCausalLM loads the text
    # model only (Qwen3_5ForCausalLM, 752M params, checked 2026-11-08).
    model = AutoModelForCausalLM.from_pretrained(cfg["base_model"], revision=rev,
                                                 dtype="bfloat16" if cfg.get("bf16", True) else "float32")
    trainer = SFTTrainer(
        model=model, args=args, train_dataset=ds["train"], eval_dataset=ds["validation"],
        processing_class=tok, peft_config=peft_config,
    )
    trainer.train()
    trainer.save_model(cfg["output_dir"] + "/final")
    tok.save_pretrained(cfg["output_dir"] + "/final")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "train/config.yaml")

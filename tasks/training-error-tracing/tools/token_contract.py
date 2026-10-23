"""Exact text formatting, truncation and response-only causal loss mask."""

MAX_LENGTH = 512


def prompt_text(instruction, context=""):
    if context:
        return ("Below is an instruction that describes a task, paired with an input that provides further context. "
                "Write a response that appropriately completes the request.\n\n"
                f"### Instruction:\n{instruction}\n\n### Input:\n{context}\n\n### Response:\n")
    return ("Below is an instruction that describes a task. "
            "Write a response that appropriately completes the request.\n\n"
            f"### Instruction:\n{instruction}\n\n### Response:\n")


def train_example(row, tokenizer):
    prompt = tokenizer.encode(prompt_text(row["instruction"], row["input"]), add_special_tokens=False)
    answer = tokenizer.encode(row["output"], add_special_tokens=False) + [tokenizer.eos_token_id]
    ids = (prompt + answer)[:MAX_LENGTH]
    labels = ([-100] * len(prompt) + answer)[:MAX_LENGTH]
    if not any(v != -100 for v in labels[1:]):
        raise ValueError("No retained response loss; exclude this record before training")
    return {"input_ids": ids, "labels": labels}

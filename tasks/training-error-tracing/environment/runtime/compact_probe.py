"""Load the fixed 7B diagnostic decoder and training-derived output rows."""
from pathlib import Path
import json

import numpy as np
import torch
from safetensors import safe_open
from transformers import AutoModel, AutoTokenizer, BitsAndBytesConfig


class FrozenProbe(torch.nn.Module):
    def __init__(self, base):
        super().__init__()
        base = Path(base)
        if torch.cuda.device_count() != 1:
            raise ValueError("Use the single assigned GPU")
        meta = json.loads((base / "probe.json").read_text())
        devices = {"embed_tokens": "cpu", "norm": 0, "rotary_emb": 0}
        devices.update({f"layers.{i}": 0 for i in range(meta["layers"])})
        self.model = AutoModel.from_pretrained(
            base, local_files_only=True, dtype=torch.bfloat16,
            device_map=devices, attn_implementation="sdpa",
            quantization_config=BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16,
                llm_int8_enable_fp32_cpu_offload=True))
        self.model.eval()
        self.model.requires_grad_(False)
        self.config = self.model.config
        self.config.use_cache = False
        with safe_open(base / "model.safetensors", framework="pt", device="cpu") as file:
            self.cpu_embedding = file.get_tensor("model.embed_tokens.weight")
        with np.load(base / "output-head.npz", allow_pickle=False) as packed:
            self.output_token_ids = packed["token_ids"].astype(np.int64)
            self.cpu_output = torch.from_numpy(packed["weights_bf16"]).view(torch.bfloat16)
        if (len(self.output_token_ids) != meta["head_rows"]
                or np.any(np.diff(self.output_token_ids) <= 0)
                or self.cpu_output.shape != (meta["head_rows"], self.config.hidden_size)
                or self.cpu_embedding.shape != (self.config.vocab_size, self.config.hidden_size)):
            raise ValueError("Invalid fixed diagnostic probe")

    def output_rows(self, token_ids):
        ids = torch.as_tensor(token_ids, dtype=torch.long, device="cpu").numpy()
        positions = np.searchsorted(self.output_token_ids, ids)
        if (np.any(positions >= len(self.output_token_ids))
                or not np.array_equal(self.output_token_ids[np.minimum(positions, len(self.output_token_ids)-1)], ids)):
            raise ValueError("Requested output token is outside the supplied training vocabulary")
        return self.cpu_output[torch.from_numpy(positions)]

    def embed(self, input_ids):
        ids = torch.as_tensor(input_ids, dtype=torch.long, device="cpu")
        return torch.nn.functional.embedding(ids, self.cpu_embedding).to("cuda", dtype=torch.bfloat16)


def load_probe(base):
    return FrozenProbe(base)

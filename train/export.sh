#!/usr/bin/env bash
# Merge (if LoRA) and convert the student to GGUF for llama.cpp.
#   train/export.sh models/chirone-0.8b/final models/chirone-0.8b ~/src/llama.cpp
# Produces Q8_0 and Q4_K_M, and both ship. Measured 2026-11-07
# (eval/results/2026-11-07-devbox-proxy.md): without AVX Q8_0 is ~2.5x faster
# than Q4_K_M, with AVX2 Q4_K_M is ~1.5x faster. Pick by CPU at install time.
set -euo pipefail
SRC=$1; OUT=$2; LLAMA=${3:-$HOME/src/llama.cpp}
mkdir -p "$OUT"
if [ -f "$SRC/adapter_config.json" ]; then
  python - "$SRC" "$OUT/merged" <<'PY'
import sys
from peft import AutoPeftModelForCausalLM
from transformers import AutoTokenizer
m = AutoPeftModelForCausalLM.from_pretrained(sys.argv[1]).merge_and_unload()
m.save_pretrained(sys.argv[2]); AutoTokenizer.from_pretrained(sys.argv[1]).save_pretrained(sys.argv[2])
PY
  SRC="$OUT/merged"
fi
python "$LLAMA/convert_hf_to_gguf.py" "$SRC" --outtype f16 --outfile "$OUT/chirone-f16.gguf"
"$LLAMA/build/bin/llama-quantize" "$OUT/chirone-f16.gguf" "$OUT/chirone-Q8_0.gguf" Q8_0
"$LLAMA/build/bin/llama-quantize" "$OUT/chirone-f16.gguf" "$OUT/chirone-Q4_K_M.gguf" Q4_K_M
ls -lh "$OUT"/*.gguf

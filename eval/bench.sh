#!/usr/bin/env bash
# Raw speed on the machine you run it on. Day-zero test for the Veriton.
#   eval/bench.sh model-a.gguf [model-b.gguf ...]
#   NOAVX=1 eval/bench.sh model.gguf     # proxy for a Core 2 on a newer CPU
#
# Default: builds llama.cpp natively (GGML_NATIVE picks whatever the CPU has:
# on a Core 2 Quad that means SSE4.1, no AVX).
# NOAVX=1: a second build with AVX/AVX2/FMA/F16C/SSE4.2 turned off, in
# build-noavx/. On a newer CPU it gives the same instruction set as the
# Q8300 (Yorkfield: SSE4.1, no SSE4.2) but not the same IPC, cache or
# memory bandwidth: treat it as an optimistic bound, never as the Veriton.
#
# Prompt sizes are the ones chirone actually sends: step 1 ~60-130 tokens,
# step 2 ~300-600; generation ~24 tokens.
set -euo pipefail
LLAMA=${LLAMA:-$HOME/src/llama.cpp}
if [ "${NOAVX:-0}" = 1 ]; then
  BUILD=build-noavx
  FLAGS=(-DGGML_NATIVE=OFF -DGGML_AVX=OFF -DGGML_AVX2=OFF -DGGML_FMA=OFF -DGGML_F16C=OFF
         -DGGML_SSE42=OFF -DGGML_AVX512=OFF -DGGML_BMI2=OFF)
else
  BUILD=build
  FLAGS=(-DGGML_NATIVE=ON)
fi
if [ ! -x "$LLAMA/$BUILD/bin/llama-bench" ]; then
  [ -d "$LLAMA" ] || git clone --depth 1 https://github.com/ggml-org/llama.cpp "$LLAMA"
  cmake -S "$LLAMA" -B "$LLAMA/$BUILD" "${FLAGS[@]}" -DLLAMA_CURL=OFF -DCMAKE_BUILD_TYPE=Release
  cmake --build "$LLAMA/$BUILD" -j"$(nproc)" --target llama-bench llama-server llama-quantize
fi
echo "# $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs)  |  $(free -g | awk '/Mem/{print $2}') GB RAM  |  build: $BUILD"
grep -qw avx2 /proc/cpuinfo && echo "# CPU AVX2: yes" || { grep -qw avx /proc/cpuinfo && echo "# CPU AVX: yes, AVX2: no" || echo "# CPU AVX: no"; }
for m in "$@"; do
  "$LLAMA/$BUILD/bin/llama-bench" -m "$m" -p 128,384,600 -n 24 -t "$(nproc)" -r 3 -o md
done

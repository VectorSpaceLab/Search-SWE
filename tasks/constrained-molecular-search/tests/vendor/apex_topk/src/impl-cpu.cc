/* apex_topk: Accelerated top-k operators for APEX.
 * Copyright (c) 2025 Atomwise. Released under MIT.
 */

#include <torch/script.h>
#include <torch/extension.h>

#include <topk/cpu.hh>

TORCH_LIBRARY_IMPL(apex_topk, CPU, m) {
  m.impl("topk", apex::cpu::topk);
}


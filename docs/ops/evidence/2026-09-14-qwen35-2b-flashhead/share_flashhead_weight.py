"""Process-local FlashHead weight sharing; preserve FP32 centroid preparation."""
import json
import logging
from pathlib import Path
from types import SimpleNamespace


def enable_shared_flashhead(model_dir):
    import torch
    import flash_head
    flash_head.register()
    from flash_head.flash_head import FlashHead, get_flash_head_parameters
    import flash_head.patches.logits_processor as patch
    from vllm.model_executor.layers.logits_processor import LogitsProcessor

    config = json.loads((Path(model_dir) / "config.json").read_text())
    cache_dir = config["flash_head_cache_dir"]
    if not Path(cache_dir).is_absolute():
        cache_dir = str(Path(model_dir) / cache_dir)
    original = LogitsProcessor._get_logits
    evidence = {}

    def get_logits(self, hidden_states, lm_head, embedding_bias):
        if not evidence:
            weight = lm_head.weight
            expected = (config["text_config"]["vocab_size"],
                        config["text_config"]["hidden_size"])
            assert tuple(weight.shape) == expected, (weight.shape, expected)
            assert weight.dtype == torch.bfloat16 and weight.is_cuda
            # The publisher prepares centroids and normalization in CPU FP32.
            # Only shape/device/dtype metadata are read from this descriptor;
            # no dense CPU vocabulary matrix needs to be allocated.
            descriptor = SimpleNamespace(weight=SimpleNamespace(
                shape=weight.shape, device=torch.device("cpu"), dtype=torch.float32))
            params = get_flash_head_parameters(descriptor, cache_dir, model_dir)
            adapter = torch.nn.Linear(expected[1], expected[0], bias=False,
                                      device="meta", dtype=weight.dtype)
            adapter.weight = torch.nn.Parameter(weight, requires_grad=False)
            shared = FlashHead(adapter, **params,
                               n_probes=config.get("n_probes"),
                               special_token_ids=config.get("flash_head_special_token_ids"))
            shared = shared.to(device=weight.device, dtype=weight.dtype)
            assert shared.original_lm_head.weight.data_ptr() == weight.data_ptr()
            assert shared.original_lm_head.weight.untyped_storage().nbytes() == weight.untyped_storage().nbytes()
            patch._flash_head = shared
            evidence.update(shared_storage=True, vocab_shape=list(weight.shape),
                            avoided_duplicate_gpu_bytes=weight.numel()*weight.element_size(),
                            centroid_preparation="CPU FP32, identical to publisher loader",
                            plugin_version=flash_head.__version__)
            logging.info("Shared FlashHead vocabulary: %s", evidence)
        return original(self, hidden_states, lm_head, embedding_bias)

    LogitsProcessor._get_logits = get_logits
    return evidence

"""Check storage sharing and numerical equivalence on a bounded GPU fixture."""
import json
import tempfile
from pathlib import Path


def main():
    import torch
    from safetensors.torch import save_file
    from share_flashhead_weight import enable_shared_flashhead
    from flash_head.flash_head import FlashHead, get_flash_head_parameters
    torch.manual_seed(19)
    vocab, hidden, clusters = 128, 16, 8
    weight = torch.randn(vocab, hidden, dtype=torch.bfloat16)
    with tempfile.TemporaryDirectory(prefix="flashhead-sharing-check-") as directory:
        root = Path(directory)
        (root / "config.json").write_text(json.dumps(dict(
            text_config=dict(vocab_size=vocab, hidden_size=hidden),
            flash_head_cache_dir=str(root), n_probes=2)))
        save_file(dict(centroids=torch.randn(1, 1, hidden, clusters),
                       cluster_assignments=torch.arange(vocab) % clusters),
                  str(root / "clustering_cache.safetensors"))
        # Match the publisher's FP32 CPU dense-copy path for the reference.
        reference_head = torch.nn.Linear(hidden, vocab, bias=False)
        reference_head.weight.data.copy_(weight)
        reference = FlashHead(reference_head, **get_flash_head_parameters(
            reference_head, str(root), str(root)), n_probes=2).to("cuda", torch.bfloat16)
        live_head = torch.nn.Linear(hidden, vocab, bias=False,
                                    device="cuda", dtype=torch.bfloat16)
        live_head.weight.data.copy_(weight)
        evidence = enable_shared_flashhead(str(root))
        from vllm.model_executor.layers.logits_processor import LogitsProcessor
        import flash_head.patches.logits_processor as patch
        for _ in range(32):
            state = torch.randn(1, hidden, device="cuda", dtype=torch.bfloat16)
            actual = LogitsProcessor._get_logits(None, state, live_head, None)
            expected = reference.get_next_token(state.unsqueeze(0))
            assert torch.equal(actual.flatten().long(), expected.flatten().long())
        shared = patch._flash_head
        assert shared.original_lm_head.weight.data_ptr() == live_head.weight.data_ptr()
        for name, value in reference.state_dict().items():
            assert torch.equal(value, shared.state_dict()[name]), name
        print(json.dumps(dict(passed=True, hidden_state_cases=32,
                              all_state_tensors_bitwise_equal=True,
                              shared_storage=evidence["shared_storage"],
                              scope="Synthetic GPU fixture; not full-checkpoint output equivalence")))


if __name__ == "__main__":
    main()

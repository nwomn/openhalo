# Mage-VL historical audit evidence

Copied read-only from Jetson on 2026-09-14; no new inference.

- live-results.jsonl, live-stderr.log, live-status.log: retained 2026-09-11
  mage-vl-live-genctx-20260911-113517 run; 14 replies, 15 submissions.
- image-result.json: historical synthetic invocation command and wall time.
- streammind_native.py and live_codec_stream.py: current retained community
  source at JohnTDI-cpu/mage-vl-gguf f0df1fe6f13095a359ff38c7749279d5d6a8c60f.
- streammind-e2e.cpp: current locally patched native source on llama.cpp base
  a52077c4cabb4f3c0298329c9d2dd1324d5604cb, including Jetson generation-context
  overrides. Source provenance is the community runtime's native patch.
- audit-summary.json: arithmetic recomputed from the archived raw logs.
- SHA256SUMS: hashes of all other files here; preserves exact copied bytes.

Source snapshots explain the observed behavior but are not historical binary
hash attestation. This audit did not repeat weight hashes or compare reference
model logits. Private frames and model assets remain excluded. Upstream source
licensing remains applicable: https://github.com/JohnTDI-cpu/mage-vl-gguf .

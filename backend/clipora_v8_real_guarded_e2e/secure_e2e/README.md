# Clipora v8 Secure Egress E2E (offline only)

Extract the ZIP in `~/Desktop/clipora/backend`. It adds a standalone folder under `clipora_v8_real_guarded_e2e/secure_e2e/` and **does not overwrite** existing workers, stages, or tests.

Run:

```
cd ~/Desktop/clipora/backend
python clipora_v8_real_guarded_e2e/secure_e2e/run_secure_e2e.py
```

Architecture: worker -> gateway -> Secure Egress stage `handle()` (test-only resolver/dial) -> local TLS fixture. Two internal Docker bridge networks are created and removed; Egress has no public network. The adapter is *only* for offline tests and must never be deployed publicly.

IMPORTANT: This reuses `/fixture/worker_actual_test.py` from the prior E2E suite, which disables TLS verification for the self-signed **test** certificate; it **does not prove TLS validation through the complete Worker path**. Separate local TLS verification tests already ran; production certificate verification remains a required acceptance gate. The injected resolver returns synthetic public IP `8.8.8.8` and the adapter connects to a local fixture, not the internet. The stage's default deny-all behavior is unchanged.

This test requires existing `clipora_v8_secure_egress_stage/` modules, `clipora_v8_real_guarded_e2e/fixtures`, `gateway.py`, `worker_actual_test.py`, `clipora-worker:v8-dns`, and `clipora-gateway:v8-test`.

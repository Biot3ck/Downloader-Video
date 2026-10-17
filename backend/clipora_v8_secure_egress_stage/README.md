# Clipora v8 Secure Egress — isolated staging

This is a **test-only implementation** based on the supplied real Egress source modules. Do not replace `gateway-security/egress-service/server.py` or run publicly.

## Run on MacBook (from `~/Desktop/clipora/backend`)

```sh
python3 -m unittest discover -s clipora_v8_secure_egress_stage -p 'test_stage.py' -v
```

No Docker, internet, or DNS lookup is required for these stage tests. The resolver is injected in tests; IP pinning is asserted by verifying that the dialer receives the **validated numeric IP**, not the original hostname. A real TCP echo server verifies bidirectional transfer.

## Security boundaries

- Standalone production use is **not enabled**. The script only binds `127.0.0.1:18888` when `CLIPORA_V8_STAGE_LOOPBACK_ONLY=1`; it refuses real public dials.
- `200 Connection Established` is sent only after the injected dialer successfully connects. DNS lookups happen before connect.
- The supplied destination/IP policies are reused unchanged. Tests cover private IP denial, target mismatch, unsupported port and default deny-all.
- A 64MiB relay budget, 15s inactivity timeout, 90s tunnel duration, and a concurrency semaphore are a preliminary stage—not a complete production resource defense.
- No TLS termination occurs here; HTTPS certificates must be validated by the client. This test uses **unencrypted echo traffic inside the simulated tunnel**, not a real TLS certificate test.
- Real public routing, IPv6 integration, certificate validation E2E, rate limits, firewall deny/direct access checks, DNS rebinding safety and deployment hardening are **not proven**.
- Clipora v7 and active gateway/egress are unchanged.

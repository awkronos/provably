# Provably product path

Four sibling checkouts under `~/projects/` form one pipeline: **produce a Z3
verification condition → re-check it without trusting the producer → optionally
prove the re-check inside SP1**.

```
provably (Python) ──┐
                    ├── SMT-LIB VC ──► pcc-core::check_unsat ──► pcc-sp1 (guest+host)
provably-rs (Rust) ─┘                      (Bool fragment)         prove / verify
```

| Island | Role | Edge that keeps it off the island |
|---|---|---|
| [`provably`](.) | Python contracts → Z3 → `ProofCertificate.smt_lib` | `provably.succinct` shells to `pcc-sp1` (`PCC_SP1_BIN`) |
| [`provably-rs`](../provably-rs) | Rust contracts → Z3 → Lean export + optional succinct | Cargo `pcc-core` path dep (`features = ["succinct"]`); shells to `pcc-sp1` |
| [`pcc-core`](../pcc-core) | Zero-dep `no_std` Bool-fragment re-checker | Consumed by both `provably-rs` and `pcc-sp1` (path) |
| [`pcc-sp1`](../pcc-sp1) | SP1 host CLI + guest that runs the same checker | Workspace `host` + `program` path-dep `../../pcc-core` |

## Local layout (assumed)

```
~/projects/provably/
~/projects/provably-rs/     # Cargo.toml: pcc-core = { path = "../pcc-core", optional }
~/projects/pcc-core/
~/projects/pcc-sp1/         # host + program path-dep ../pcc-core
```

## Operator path (minimal)

1. Verify in Python or Rust → obtain SMT-LIB unsat script.
2. `pcc-sp1 check --script vc.smt2` — native `pcc-core` gate (Bool only).
3. `pcc-sp1 prove --script vc.smt2 --out cert.bin` then `verify`.

Python one-liner path: `from provably.succinct import classify, prove_carrying`.
Rust feature path: `cargo test --features succinct` / `provably::succinct::prove_carrying`.

## Honest scope

`pcc-core` v0.0.x re-checks the **all-Bool** fragment only (`Unsupported` otherwise — never a silent pass). Lean export from `provably-rs` is a parallel, non-succinct trust rail.

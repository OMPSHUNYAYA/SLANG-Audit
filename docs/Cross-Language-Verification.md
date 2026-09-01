# SLANG-Audit v2.4.0 Cross-Language Verification

## Purpose

SLANG-Audit includes a separately implemented JavaScript verifier so portable proof verification is not dependent on one language runtime or one implementation path.

The implementations are:

- Python reference resolver and verifier: [`../core/SLANG_Audit_Reference_Resolver_v2_4_0.py`](../core/SLANG_Audit_Reference_Resolver_v2_4_0.py)
- JavaScript standalone verifier: [`../validation/SLANG_Audit_Standalone_Verifier_v1_0_0.js`](../validation/SLANG_Audit_Standalone_Verifier_v1_0_0.js)

The JavaScript verifier does not import producer code, invoke Python, or shell out to the resolver.

## Verification surface

The JavaScript implementation independently reconstructs the v2.4.0 verification semantics for:

```text
canonical structures
structural closure
target verdicts
minimal witnesses
counterfactual criticality
bundle identities
incremental deltas and delta certificates
proof-ledger lineage
checkpoints
```

## Frozen conformance vectors

The package includes 10 frozen genuine bundles spanning:

```text
PASS
VIOLATED
INCOMPLETE
ABSTAIN
contradiction isolation
negative required literals
multi-step derivation
alternative proof paths
shared-source witness minimization
mixed resolved target verdicts
```

It also includes six rehashed semantic mutations designed to remain hash-consistent at their outer container levels while carrying altered semantics.

The conformance gate requires:

```text
10 genuine bundles x 2 verifiers        -> 20 accepts
6 semantic mutations x 2 verifiers      -> 12 rejects
1 incremental bundle x 2 verifiers      -> 2 accepts
1 proof ledger x 2 verifiers             -> 2 accepts
1 checkpointed ledger x 2 verifiers      -> 2 accepts
JavaScript verifier self-test            -> 1 pass
```

Current result:

```text
TOTAL 39/39 PASS
```

## Commands

JavaScript verifier self-test:

```text
node validation/SLANG_Audit_Standalone_Verifier_v1_0_0.js --self-test
```

Verify a bundle:

```text
node validation/SLANG_Audit_Standalone_Verifier_v1_0_0.js --verify-bundle bundle.json
```

Verify a proof ledger:

```text
node validation/SLANG_Audit_Standalone_Verifier_v1_0_0.js --verify-ledger proof_ledger.json
```

Run the cross-language gate:

```text
python -B validation/SLANG_Audit_Cross_Language_Conformance_Gate_v1_0_0.py --self-test
python -B validation/SLANG_Audit_Cross_Language_Conformance_Gate_v1_0_0.py --run
```

## Interpretation

Cross-language agreement strengthens portability and implementation independence for the released structural contract.

It does not itself constitute independent third-party certification because both implementations are distributed by the project.

```text
project-supplied separately implemented verifier
!=
independent third-party reproduction
```

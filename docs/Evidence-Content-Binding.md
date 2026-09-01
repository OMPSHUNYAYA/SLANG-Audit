# SLANG-Audit v2.4.0 Optional Evidence Content Binding

## Core commitment semantics

Inside the structural resolver, an evidence commitment is a caller-declared identity-binding string:

```text
sha256:<64 lowercase hexadecimal digits>
```

The resolver does not access an external file merely because that commitment is present.

Therefore the core semantics remain:

```text
commitment declaration
-> canonical structure binding
```

not:

```text
commitment declaration
-> external file verification
```

## Optional byte-to-commitment verifier

The package includes a separate utility:

[`SLANG_Audit_Evidence_Content_Binding_Verifier_v1_0_0.py`](../validation/SLANG_Audit_Evidence_Content_Binding_Verifier_v1_0_0.py)

It checks:

```text
SHA256(exact supplied file bytes) == declared commitment digest
```

Example:

```text
python -B validation/SLANG_Audit_Evidence_Content_Binding_Verifier_v1_0_0.py --file evidence.bin --commitment sha256:<digest>
```

Success returns:

```text
CONTENT_BINDING_PASS
external_truth_verified:false
external_source_provenance_verified:false
```

## What content binding establishes

A successful check establishes only that the exact supplied bytes match the supplied SHA-256 commitment.

It does not establish:

```text
authorship
provenance
completeness
truth
legal validity
trusted time
professional audit sufficiency
```

The utility is deliberately separate from the core resolver so file access does not become an implicit part of structural resolution.

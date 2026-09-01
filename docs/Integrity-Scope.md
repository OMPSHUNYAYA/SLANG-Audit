# SLANG-Audit v2.4.0 Integrity Scope

## Purpose

The repository separates the frozen evidence-bearing surface from intentionally editable repository material.

```text
frozen executable/evidence surface -> checksum protected
editable presentation/configuration surface -> version controlled but intentionally unhashed
```

## Checksum-protected artifacts

The SHA-256 manifest covers only selected files under `core/` and `validation/` that define or preserve the deterministic verification surface.

Manifest:

[**FROZEN_ARTIFACT_SHA256SUMS_v2_4_0.txt**](../validation/FROZEN_ARTIFACT_SHA256SUMS_v2_4_0.txt)

The protected set includes:

- the v2.4.0 reference resolver;
- proof-ledger validation code;
- the JavaScript standalone verifier;
- the cross-language conformance gate;
- the optional evidence content-binding verifier;
- the package verifier;
- the frozen cross-language conformance vectors;
- the deterministic v2.4.0 demo bundle;
- the frozen proof-ledger genesis bundle;
- the frozen delta sequence;
- the pinned checkpoint;
- the complete frozen proof ledger;
- the machine-readable proof-ledger validation report.

## Intentionally editable and unhashed material

The checksum manifest deliberately excludes:

- root `README.md`;
- all documentation under `docs/`, including the architecture diagram and portable specification;
- all demonstration inputs under `examples/`;
- workflow configuration;
- `LICENSE`, copyright notice, third-party notices, claim/status files, and reproducibility documentation;
- `VERSION`, `requirements.txt`, `.gitignore`, and ordinary repository metadata;
- narrative validation documentation and `VERIFICATION_RESULT.txt`.

These files remain reviewable and version-controlled without being part of the frozen artifact identity contract.

## Why examples are unhashed

Examples are an editable demonstration surface. Frozen output bundles, conformance vectors, and proof-ledger artifacts preserve the deterministic evidence required for package verification.

## Why documentation and workflow are unhashed

Documentation, diagram presentation, links, badges, specifications, FAQ wording, and CI configuration may improve without changing the frozen executable and machine-readable evidence identity surface.

## Verification command

```text
python -B validation/SLANG_Audit_Package_Verifier_v2_4_0.py --verify
```

## Interpretation boundary

A matching SHA-256 digest establishes file integrity relative to the recorded manifest.

It does not authenticate external audit evidence, establish authorship of a third-party source, prove trusted time, or create audit-opinion authority.

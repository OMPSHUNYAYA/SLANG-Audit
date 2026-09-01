# SLANG-Audit v2.4.0 Input Contract

## Top-level structure

The declared input schema is:

```text
SLANG-AUDIT-STRUCTURE-2
```

The accepted top-level fields are:

```text
schema
atoms
targets
evidence
rules
controls
```

Derived-result fields are reserved and are refused when injected into input.

## Atoms

Atoms are declared Boolean structural propositions identified by bounded strings.

Examples:

```text
contracts_supported
expense_supported
mfa_enabled
dataset_integrity_supported
```

## Evidence

Each evidence object contains:

```text
id
claims
optional commitment
```

Example:

```text
id: contracts_ledger
claims: contracts_supported=true
commitment: sha256:<64 hexadecimal characters>
```

A commitment binds the declared evidence identity into canonical structure. It does not authenticate the underlying source and is not a digital signature.

## Rules

Rules have:

```text
id
if_all
then
```

Example:

```text
if contracts_supported=true
then revenue_supported=true
```

Rules fire only when every premise is unambiguously supported. Contradictory premises do not fire rules.

## Controls

A control contains:

```text
id
require
```

Each requirement is a Boolean literal.

Example:

```text
expense_supported=true
revenue_supported=true
```

## Targets

Targets identify the controls to resolve.

Target resolution is target-specific: unrelated contradictions are retained in the closure but do not automatically force an unrelated target to abstain.

## Strict parsing

The parser rejects duplicate JSON keys and enforces bounded counts and identifier lengths.

Resource limits are explicit in the reference implementation and conservative refusal is preferred to silent truncation.

## Evidence-source boundary

The input contract represents declared structural claims only.

It does not define how an external source was obtained, authenticated, sampled, signed, timestamped, legally admitted, or professionally audited.

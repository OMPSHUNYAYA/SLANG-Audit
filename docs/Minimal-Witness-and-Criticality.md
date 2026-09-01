# SLANG-Audit v2.4.0 Minimal Witness and Criticality

## Minimal sufficient witness

For a target verdict that can be supported by a finite declared substructure, the resolver searches for a canonical minimum sufficient witness within declared resource bounds.

The minimum metric is based on declared evidence and rule sources required by the target proof.

A minimal witness is represented as a restricted audit substructure and has its own deterministic identity.

The witness must independently reproduce the same target verdict.

## Example

For `profit_recognition`, the complete demonstration contains four evidence sources, but the canonical minimal witness uses:

```text
evidence:
contracts_ledger
cost_ledger

rules:
derive_expense_support
derive_revenue_support
```

The unrelated `profit_bridge` and `reported_statement` sources are excluded from that target's minimal witness.

## Exact bounded search

The implementation records that minimality is exact only within the declared resource bounds.

It does not silently truncate a search and then label the truncated result globally minimal.

## Minimal verdict cut

The complementary object asks:

```text
What smallest declared-source removal changes the current target verdict?
```

For the demonstration:

```text
remove contracts_ledger
-> profit_recognition PASS becomes INCOMPLETE
```

The target-specific cut identity is separated from the identity of the entire counterfactual structure so unrelated audit declarations do not unnecessarily change the cut identity.

## Completion frontier

For an `INCOMPLETE` target, bounded completion search asks which smallest hypothetical declared literal additions could produce `PASS`.

Example:

```text
add costs_supported=true
-> target becomes PASS
```

## Repair to PASS

For `VIOLATED` or `ABSTAIN`, bounded repair search may combine:

```text
declared-source removals
+
hypothetical literal additions
```

to identify a minimum structural change set that reproduces `PASS`.

## Interpretation boundary

These objects describe the admitted Boolean audit model only.

```text
minimal structural witness
!=
minimum real-world audit evidence

structural repair
!=
professional audit recommendation
```

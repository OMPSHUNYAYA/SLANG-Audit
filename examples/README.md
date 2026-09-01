# SLANG-Audit v2.4.0 Examples

All examples in this directory are synthetic project-authored declared audit structures and are intentionally outside the frozen checksum manifest.

## Demonstration input

[`SLANG_Audit_Demo_Input_v2_4_0.json`](./SLANG_Audit_Demo_Input_v2_4_0.json)

Expected target verdicts:

```text
profit_recognition:PASS
reported_profit_alignment:PASS
```

## Minimal witness input

[`SLANG_Audit_Profit_Recognition_Minimal_Witness_Input_v2_4_0.json`](./SLANG_Audit_Profit_Recognition_Minimal_Witness_Input_v2_4_0.json)

Contains only the declared structure needed to reproduce the demonstration `profit_recognition` target witness.

## Incomplete example

[`SLANG_Audit_Incomplete_Example_v2_4_0.json`](./SLANG_Audit_Incomplete_Example_v2_4_0.json)

Removes `cost_ledger`, leaving required expense support unresolved.

## Violated example

[`SLANG_Audit_Violated_Example_v2_4_0.json`](./SLANG_Audit_Violated_Example_v2_4_0.json)

Declares `profit_bridge_supported=false` for a control requiring `profit_bridge_supported=true`.

## Abstain example

[`SLANG_Audit_Abstain_Example_v2_4_0.json`](./SLANG_Audit_Abstain_Example_v2_4_0.json)

Adds opposing declared support for `reported_profit_supported`, producing a target-specific contradiction.

## Resolve any example

```text
python -B ../core/SLANG_Audit_Reference_Resolver_v2_4_0.py --resolve <example.json> --pretty
```

These structures demonstrate reference semantics only. They are not real audit records and carry no external audit authority.

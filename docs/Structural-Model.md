# SLANG-Audit v2.4.0 Structural Model

## Closure

The resolver begins with direct evidence claims and repeatedly applies eligible structural rules until no new literal can be added or a declared resource bound is reached.

A literal may have one of the effective structural conditions:

```text
TRUE
FALSE
UNKNOWN
CONTRADICTORY
```

## Target verdicts

For each target control:

### PASS

Every required literal is unambiguously supported.

```text
all requirements satisfied -> PASS
```

### VIOLATED

At least one required literal has an unambiguously supported opposite and no required literal is contradictory.

```text
required x=true
supported x=false
-> VIOLATED
```

A `VIOLATED` target is a resolved structural conclusion, so the overall resolver state may still be `RESOLVED`.

### INCOMPLETE

At least one required literal remains unsupported and no decisive contradiction or violation resolves the target.

```text
required x=true
x remains unknown
-> INCOMPLETE
```

### ABSTAIN

A required target literal is contradictory.

```text
required x=true
x=true supported
x=false supported
-> ABSTAIN
```

## Resolver states

The top-level state contract is:

```text
RESOLVED | INCOMPLETE | ABSTAIN | FORBIDDEN | UNSUPPORTED
```

`FORBIDDEN` and `UNSUPPORTED` are conservative refusal states for disallowed or unsupported input/model conditions.

## Target isolation

A contradiction outside the dependency path of a target is reported in the global closure but does not automatically change that target's verdict.

This supports the distinction:

```text
global declared inconsistency
!=
automatic failure of every target
```

## Canonicalization

Declaration ordering is normalized before identity calculation. Reordering atoms, targets, evidence, rules, controls, or literal maps does not change the canonical identity when the admitted structure is otherwise equivalent.

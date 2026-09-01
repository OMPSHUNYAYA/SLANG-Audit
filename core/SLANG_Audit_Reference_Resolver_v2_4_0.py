#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Shunyaya Framework contributors.

import argparse
import hashlib
import itertools
import json
import re
import sys
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

VERSION = "2.4.0"
MINIMUM_PYTHON_VERSION = (3, 9)
PROFILE_ID = "SLANG-AUDIT-DECLARED-EVIDENCE-1"
INPUT_SCHEMA = "SLANG-AUDIT-STRUCTURE-2"
CANONICAL_SCHEMA = "SLANG-AUDIT-CANONICAL-1"
CERTIFICATE_SCHEMA = "SLANG-AUDIT-CERTIFICATE-6"
BUNDLE_SCHEMA = "SLANG-AUDIT-BUNDLE-6"
PROOF_SCHEMA = "SLANG-AUDIT-PROOF-5"
CANONICALIZATION_ID = "SLANG-AUDIT-CANONICAL-BOOLEAN-1"
DELTA_SCHEMA = "SLANG-AUDIT-DELTA-1"
DELTA_CERTIFICATE_SCHEMA = "SLANG-AUDIT-DELTA-CERTIFICATE-1"
INCREMENTAL_BUNDLE_SCHEMA = "SLANG-AUDIT-INCREMENTAL-BUNDLE-1"
LEDGER_SCHEMA = "SLANG-AUDIT-PROOF-LEDGER-1"
LEDGER_CHECKPOINT_SCHEMA = "SLANG-AUDIT-LEDGER-CHECKPOINT-1"
LEDGER_DELTA_SEQUENCE_SCHEMA = "SLANG-AUDIT-LEDGER-DELTA-SEQUENCE-1"
LEDGER_BRANCH_COMPARISON_SCHEMA = "SLANG-AUDIT-LEDGER-BRANCH-COMPARISON-1"

STATE_RESOLVED = "RESOLVED"
STATE_INCOMPLETE = "INCOMPLETE"
STATE_ABSTAIN = "ABSTAIN"
STATE_FORBIDDEN = "FORBIDDEN"
STATE_UNSUPPORTED = "UNSUPPORTED"

VERDICT_PASS = "PASS"
VERDICT_VIOLATED = "VIOLATED"
VERDICT_INCOMPLETE = "INCOMPLETE"
VERDICT_ABSTAIN = "ABSTAIN"

MAX_INPUT_BYTES = 1048576
MAX_ATOMS = 512
MAX_TARGETS = 128
MAX_EVIDENCE = 512
MAX_RULES = 512
MAX_CONTROLS = 256
MAX_CLAIMS_PER_EVIDENCE = 128
MAX_PREMISES_PER_RULE = 128
MAX_REQUIREMENTS_PER_CONTROL = 128
MAX_IDENTIFIER_LENGTH = 128
MAX_RULE_FIRINGS = 8192
MAX_PROOF_CANDIDATES_PER_LITERAL = 512
MAX_WITNESS_COMBINATIONS = 16384
MAX_COUNTERFACTUAL_CANDIDATE_SOURCES = 24
MAX_COUNTERFACTUAL_CANDIDATE_LITERALS = 24
MAX_COUNTERFACTUAL_EVALUATIONS = 65536
MAX_DELTA_EVIDENCE_OPERATIONS = 256
MAX_DELTA_RULE_OPERATIONS = 256
MAX_LEDGER_ENTRIES = 128

TOP_LEVEL_KEYS = {"schema", "atoms", "targets", "evidence", "rules", "controls"}
EVIDENCE_KEYS = {"id", "claims", "commitment"}
RULE_KEYS = {"id", "if_all", "then"}
CONTROL_KEYS = {"id", "require"}
RESERVED_KEYS = {
    "state",
    "result",
    "results",
    "verdict",
    "verdicts",
    "certificate",
    "certificate_id",
    "proof",
    "bundle",
    "bundle_id",
    "canonical_structure",
    "canonical_structure_id",
    "resolution",
    "resolved",
    "derived",
    "outcome",
    "authority",
}
IDENTIFIER_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]*\Z")
COMMITMENT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")


class StructuralError(Exception):
    def __init__(self, state: str, code: str, path: str):
        super().__init__(code)
        self.state = state
        self.code = code
        self.path = path


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def identity(prefix: str, value: Any) -> str:
    return prefix + ":" + sha256_hex(value)


def strict_json_load_text(text: str) -> Any:
    if len(text.encode("utf-8")) > MAX_INPUT_BYTES:
        raise ValueError("INPUT_SIZE_LIMIT")

    def pairs_hook(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
        output: Dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise ValueError("DUPLICATE_JSON_KEY:" + key)
            output[key] = value
        return output

    def reject_float(value: str) -> Any:
        raise ValueError("FLOAT_NOT_SUPPORTED:" + value)

    def reject_constant(value: str) -> Any:
        raise ValueError("NONFINITE_NUMBER_NOT_SUPPORTED:" + value)

    return json.loads(
        text,
        object_pairs_hook=pairs_hook,
        parse_float=reject_float,
        parse_constant=reject_constant,
    )


def load_json_file(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return strict_json_load_text(handle.read())


def parse_identifier(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise StructuralError(STATE_UNSUPPORTED, "INVALID_IDENTIFIER", path)
    if not value or len(value) > MAX_IDENTIFIER_LENGTH:
        raise StructuralError(STATE_UNSUPPORTED, "INVALID_IDENTIFIER", path)
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise StructuralError(STATE_UNSUPPORTED, "INVALID_IDENTIFIER", path)
    return value


def parse_bool(value: Any, path: str) -> bool:
    if type(value) is not bool:
        raise StructuralError(STATE_UNSUPPORTED, "BOOLEAN_REQUIRED", path)
    return value


def parse_commitment(value: Any, path: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not COMMITMENT_PATTERN.fullmatch(value):
        raise StructuralError(STATE_UNSUPPORTED, "INVALID_EVIDENCE_COMMITMENT", path)
    return value


def forbidden_key_scan(value: Any, path: str = "$") -> Optional[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and key.lower() in RESERVED_KEYS:
                return path + "." + key
            found = forbidden_key_scan(child, path + "." + str(key))
            if found is not None:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = forbidden_key_scan(child, "{}[{}]".format(path, index))
            if found is not None:
                return found
    return None


def parse_literal_map(raw: Any, path: str, maximum: int, empty_allowed: bool) -> Dict[str, bool]:
    if not isinstance(raw, dict):
        raise StructuralError(STATE_UNSUPPORTED, "INVALID_LITERAL_MAP", path)
    if len(raw) > maximum:
        raise StructuralError(STATE_UNSUPPORTED, "LITERAL_MAP_LIMIT", path)
    if not raw and not empty_allowed:
        raise StructuralError(STATE_UNSUPPORTED, "EMPTY_LITERAL_MAP", path)
    output: Dict[str, bool] = {}
    for raw_atom, raw_value in raw.items():
        atom = parse_identifier(raw_atom, path)
        output[atom] = parse_bool(raw_value, path + "." + atom)
    return dict(sorted(output.items()))


def normalize_structure(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise StructuralError(STATE_UNSUPPORTED, "INVALID_TOP_LEVEL_TYPE", "$")
    forbidden_path = forbidden_key_scan(raw)
    if forbidden_path is not None:
        raise StructuralError(STATE_FORBIDDEN, "FORBIDDEN_DERIVED_FIELD", forbidden_path)
    unknown = sorted(set(raw.keys()) - TOP_LEVEL_KEYS)
    if unknown:
        raise StructuralError(STATE_UNSUPPORTED, "UNKNOWN_TOP_LEVEL_FIELD", "$." + unknown[0])
    if raw.get("schema") != INPUT_SCHEMA:
        raise StructuralError(STATE_UNSUPPORTED, "UNSUPPORTED_INPUT_SCHEMA", "$.schema")

    atoms_raw = raw.get("atoms")
    targets_raw = raw.get("targets")
    evidence_raw = raw.get("evidence")
    rules_raw = raw.get("rules")
    controls_raw = raw.get("controls")

    if not isinstance(atoms_raw, list):
        raise StructuralError(STATE_UNSUPPORTED, "INVALID_ATOMS_TYPE", "$.atoms")
    if not atoms_raw:
        raise StructuralError(STATE_UNSUPPORTED, "EMPTY_ATOM_SET", "$.atoms")
    if len(atoms_raw) > MAX_ATOMS:
        raise StructuralError(STATE_UNSUPPORTED, "ATOM_LIMIT", "$.atoms")
    atoms = sorted(set(parse_identifier(item, "$.atoms") for item in atoms_raw))
    if len(atoms) != len(atoms_raw):
        raise StructuralError(STATE_UNSUPPORTED, "DUPLICATE_ATOM", "$.atoms")
    atom_set = set(atoms)

    if not isinstance(targets_raw, list):
        raise StructuralError(STATE_UNSUPPORTED, "INVALID_TARGETS_TYPE", "$.targets")
    if not targets_raw:
        raise StructuralError(STATE_UNSUPPORTED, "EMPTY_TARGET_SET", "$.targets")
    if len(targets_raw) > MAX_TARGETS:
        raise StructuralError(STATE_UNSUPPORTED, "TARGET_LIMIT", "$.targets")
    targets = sorted(set(parse_identifier(item, "$.targets") for item in targets_raw))
    if len(targets) != len(targets_raw):
        raise StructuralError(STATE_UNSUPPORTED, "DUPLICATE_TARGET", "$.targets")

    if not isinstance(evidence_raw, list):
        raise StructuralError(STATE_UNSUPPORTED, "INVALID_EVIDENCE_TYPE", "$.evidence")
    if len(evidence_raw) > MAX_EVIDENCE:
        raise StructuralError(STATE_UNSUPPORTED, "EVIDENCE_LIMIT", "$.evidence")
    evidence: List[Dict[str, Any]] = []
    evidence_ids: Set[str] = set()
    for index, item in enumerate(evidence_raw):
        path = "$.evidence[{}]".format(index)
        if not isinstance(item, dict):
            raise StructuralError(STATE_UNSUPPORTED, "INVALID_EVIDENCE_ITEM", path)
        unknown_item = sorted(set(item.keys()) - EVIDENCE_KEYS)
        if unknown_item:
            raise StructuralError(STATE_UNSUPPORTED, "UNKNOWN_EVIDENCE_FIELD", path + "." + unknown_item[0])
        if "id" not in item or "claims" not in item:
            raise StructuralError(STATE_UNSUPPORTED, "MISSING_EVIDENCE_FIELD", path)
        evidence_id = parse_identifier(item["id"], path + ".id")
        if evidence_id in evidence_ids:
            raise StructuralError(STATE_UNSUPPORTED, "DUPLICATE_EVIDENCE_ID", path + ".id")
        evidence_ids.add(evidence_id)
        claims = parse_literal_map(item["claims"], path + ".claims", MAX_CLAIMS_PER_EVIDENCE, False)
        undeclared = sorted(set(claims.keys()) - atom_set)
        if undeclared:
            raise StructuralError(STATE_UNSUPPORTED, "UNDECLARED_ATOM", path + ".claims." + undeclared[0])
        commitment = parse_commitment(item.get("commitment"), path + ".commitment")
        evidence.append({"id": evidence_id, "claims": claims, "commitment": commitment})
    evidence.sort(key=lambda item: item["id"])

    if not isinstance(rules_raw, list):
        raise StructuralError(STATE_UNSUPPORTED, "INVALID_RULES_TYPE", "$.rules")
    if len(rules_raw) > MAX_RULES:
        raise StructuralError(STATE_UNSUPPORTED, "RULE_LIMIT", "$.rules")
    rules: List[Dict[str, Any]] = []
    rule_ids: Set[str] = set()
    for index, item in enumerate(rules_raw):
        path = "$.rules[{}]".format(index)
        if not isinstance(item, dict):
            raise StructuralError(STATE_UNSUPPORTED, "INVALID_RULE_ITEM", path)
        unknown_item = sorted(set(item.keys()) - RULE_KEYS)
        if unknown_item:
            raise StructuralError(STATE_UNSUPPORTED, "UNKNOWN_RULE_FIELD", path + "." + unknown_item[0])
        if set(item.keys()) != RULE_KEYS:
            raise StructuralError(STATE_UNSUPPORTED, "MISSING_RULE_FIELD", path)
        rule_id = parse_identifier(item["id"], path + ".id")
        if rule_id in rule_ids:
            raise StructuralError(STATE_UNSUPPORTED, "DUPLICATE_RULE_ID", path + ".id")
        rule_ids.add(rule_id)
        premises = parse_literal_map(item["if_all"], path + ".if_all", MAX_PREMISES_PER_RULE, False)
        conclusion_map = parse_literal_map(item["then"], path + ".then", 1, False)
        undeclared = sorted((set(premises.keys()) | set(conclusion_map.keys())) - atom_set)
        if undeclared:
            raise StructuralError(STATE_UNSUPPORTED, "UNDECLARED_ATOM", path + "." + undeclared[0])
        conclusion_atom = next(iter(conclusion_map.keys()))
        if conclusion_atom in premises and premises[conclusion_atom] == conclusion_map[conclusion_atom]:
            raise StructuralError(STATE_UNSUPPORTED, "SELF_CONFIRMING_RULE", path)
        rules.append({"id": rule_id, "if_all": premises, "then": conclusion_map})
    rules.sort(key=lambda item: item["id"])

    if not isinstance(controls_raw, list):
        raise StructuralError(STATE_UNSUPPORTED, "INVALID_CONTROLS_TYPE", "$.controls")
    if not controls_raw:
        raise StructuralError(STATE_UNSUPPORTED, "EMPTY_CONTROL_SET", "$.controls")
    if len(controls_raw) > MAX_CONTROLS:
        raise StructuralError(STATE_UNSUPPORTED, "CONTROL_LIMIT", "$.controls")
    controls: List[Dict[str, Any]] = []
    control_ids: Set[str] = set()
    for index, item in enumerate(controls_raw):
        path = "$.controls[{}]".format(index)
        if not isinstance(item, dict):
            raise StructuralError(STATE_UNSUPPORTED, "INVALID_CONTROL_ITEM", path)
        unknown_item = sorted(set(item.keys()) - CONTROL_KEYS)
        if unknown_item:
            raise StructuralError(STATE_UNSUPPORTED, "UNKNOWN_CONTROL_FIELD", path + "." + unknown_item[0])
        if set(item.keys()) != CONTROL_KEYS:
            raise StructuralError(STATE_UNSUPPORTED, "MISSING_CONTROL_FIELD", path)
        control_id = parse_identifier(item["id"], path + ".id")
        if control_id in control_ids:
            raise StructuralError(STATE_UNSUPPORTED, "DUPLICATE_CONTROL_ID", path + ".id")
        control_ids.add(control_id)
        requirements = parse_literal_map(item["require"], path + ".require", MAX_REQUIREMENTS_PER_CONTROL, False)
        undeclared = sorted(set(requirements.keys()) - atom_set)
        if undeclared:
            raise StructuralError(STATE_UNSUPPORTED, "UNDECLARED_ATOM", path + ".require." + undeclared[0])
        controls.append({"id": control_id, "require": requirements})
    controls.sort(key=lambda item: item["id"])

    undeclared_targets = sorted(set(targets) - control_ids)
    if undeclared_targets:
        raise StructuralError(STATE_UNSUPPORTED, "UNDECLARED_TARGET_CONTROL", "$.targets")

    public_core = {
        "schema": CANONICAL_SCHEMA,
        "source_schema": INPUT_SCHEMA,
        "profile_id": PROFILE_ID,
        "canonicalization_id": CANONICALIZATION_ID,
        "atoms": atoms,
        "targets": targets,
        "evidence": evidence,
        "rules": rules,
        "controls": controls,
    }
    public_core["evidence_ids"] = [identity("slang_audit_evidence_sha256", item) for item in evidence]
    public_core["rule_ids"] = [identity("slang_audit_rule_sha256", item) for item in rules]
    public_core["control_ids"] = [identity("slang_audit_control_sha256", item) for item in controls]
    structure_core = dict(public_core)
    public_core["canonical_structure_id"] = identity("slang_audit_structure_sha256", structure_core)
    return public_core


def literal_key(atom: str, value: bool) -> str:
    return atom + "=" + ("true" if value else "false")


def opposite(value: bool) -> bool:
    return not value


def derive_closure(canonical: Dict[str, Any]) -> Dict[str, Any]:
    support: Dict[Tuple[str, bool], Set[str]] = {}
    for evidence in canonical["evidence"]:
        for atom, value in evidence["claims"].items():
            support.setdefault((atom, value), set()).add("evidence:" + evidence["id"])

    fired: Set[str] = set()
    firings: List[Dict[str, Any]] = []
    changed = True
    firing_count = 0
    while changed:
        changed = False
        for rule in canonical["rules"]:
            premises_satisfied = True
            premise_literals: List[str] = []
            for atom, required_value in rule["if_all"].items():
                if (atom, required_value) not in support or (atom, opposite(required_value)) in support:
                    premises_satisfied = False
                    break
                premise_literals.append(literal_key(atom, required_value))
            if not premises_satisfied:
                continue
            conclusion_atom, conclusion_value = next(iter(rule["then"].items()))
            source = "rule:" + rule["id"]
            before = len(support.get((conclusion_atom, conclusion_value), set()))
            support.setdefault((conclusion_atom, conclusion_value), set()).add(source)
            after = len(support[(conclusion_atom, conclusion_value)])
            if rule["id"] not in fired:
                firing_count += 1
                if firing_count > MAX_RULE_FIRINGS:
                    raise StructuralError(STATE_UNSUPPORTED, "RULE_FIRING_LIMIT", "$.rules")
                fired.add(rule["id"])
                firings.append(
                    {
                        "rule_id": rule["id"],
                        "premises": sorted(premise_literals),
                        "conclusion": literal_key(conclusion_atom, conclusion_value),
                    }
                )
            if after > before:
                changed = True

    atom_states: Dict[str, str] = {}
    support_public: Dict[str, List[str]] = {}
    contradictions: List[str] = []
    for atom in canonical["atoms"]:
        has_true = (atom, True) in support
        has_false = (atom, False) in support
        if has_true and has_false:
            atom_states[atom] = "CONTRADICTORY"
            contradictions.append(atom)
        elif has_true:
            atom_states[atom] = "TRUE"
        elif has_false:
            atom_states[atom] = "FALSE"
        else:
            atom_states[atom] = "UNKNOWN"
        for value in (False, True):
            if (atom, value) in support:
                support_public[literal_key(atom, value)] = sorted(support[(atom, value)])

    return {
        "atom_states": atom_states,
        "support": dict(sorted(support_public.items())),
        "rule_firings": sorted(firings, key=lambda item: item["rule_id"]),
        "contradictory_atoms": sorted(contradictions),
    }


def control_verdict(control: Dict[str, Any], closure: Dict[str, Any]) -> Dict[str, Any]:
    contradictory: List[str] = []
    violated: List[str] = []
    missing: List[str] = []
    satisfied: List[str] = []
    support = closure["support"]

    for atom, required_value in control["require"].items():
        required_key = literal_key(atom, required_value)
        opposite_key = literal_key(atom, opposite(required_value))
        has_required = required_key in support
        has_opposite = opposite_key in support
        if has_required and has_opposite:
            contradictory.append(atom)
        elif has_opposite:
            violated.append(required_key)
        elif has_required:
            satisfied.append(required_key)
        else:
            missing.append(required_key)

    if contradictory:
        verdict = VERDICT_ABSTAIN
        witness = {
            "kind": "CONTRADICTION",
            "atoms": contradictory,
            "supports": {
                atom: {
                    "true": support.get(literal_key(atom, True), []),
                    "false": support.get(literal_key(atom, False), []),
                }
                for atom in contradictory
            },
        }
    elif violated:
        verdict = VERDICT_VIOLATED
        witness = {
            "kind": "VIOLATION",
            "violated_requirements": violated,
            "opposing_support": {
                requirement: support[literal_key(requirement.rsplit("=", 1)[0], requirement.endswith("=false"))]
                for requirement in violated
            },
        }
    elif missing:
        verdict = VERDICT_INCOMPLETE
        witness = {
            "kind": "MISSING",
            "missing_requirements": missing,
            "satisfied_requirements": satisfied,
        }
    else:
        verdict = VERDICT_PASS
        witness = {
            "kind": "SATISFACTION",
            "satisfied_requirements": satisfied,
            "supports": {requirement: support[requirement] for requirement in satisfied},
        }

    return {
        "control_id": control["id"],
        "verdict": verdict,
        "requirement_count": len(control["require"]),
        "witness": witness,
    }


def build_resolution(canonical: Dict[str, Any], closure: Dict[str, Any]) -> Dict[str, Any]:
    controls_by_id = {item["id"]: item for item in canonical["controls"]}
    target_results: Dict[str, Any] = {}
    verdicts: Dict[str, str] = {}
    for target in canonical["targets"]:
        result = control_verdict(controls_by_id[target], closure)
        target_results[target] = result
        verdicts[target] = result["verdict"]

    if any(value == VERDICT_ABSTAIN for value in verdicts.values()):
        state = STATE_ABSTAIN
        reason_codes = ["TARGET_CONTRADICTION"]
    elif any(value == VERDICT_INCOMPLETE for value in verdicts.values()):
        state = STATE_INCOMPLETE
        reason_codes = ["TARGET_STRUCTURE_INCOMPLETE"]
    else:
        state = STATE_RESOLVED
        reason_codes = ["TARGETS_STRUCTURALLY_RESOLVED"]

    return {
        "state": state,
        "reason_codes": reason_codes,
        "verdicts": dict(sorted(verdicts.items())),
        "targets": {key: target_results[key] for key in sorted(target_results.keys())},
    }




def proof_candidate_key(candidate: Tuple[frozenset, frozenset]) -> Tuple[Any, ...]:
    evidence, rules = candidate
    return (
        len(evidence) + len(rules),
        len(evidence),
        len(rules),
        tuple(sorted(evidence)),
        tuple(sorted(rules)),
    )


def add_proof_candidate(candidates: List[Tuple[frozenset, frozenset]], candidate: Tuple[frozenset, frozenset]) -> bool:
    evidence, rules = candidate
    for existing_evidence, existing_rules in candidates:
        if existing_evidence.issubset(evidence) and existing_rules.issubset(rules):
            return False
    retained = [
        (existing_evidence, existing_rules)
        for existing_evidence, existing_rules in candidates
        if not (evidence.issubset(existing_evidence) and rules.issubset(existing_rules))
    ]
    retained.append(candidate)
    retained.sort(key=proof_candidate_key)
    if len(retained) > MAX_PROOF_CANDIDATES_PER_LITERAL:
        raise StructuralError(STATE_UNSUPPORTED, "WITNESS_CANDIDATE_LIMIT", "$.rules")
    candidates[:] = retained
    return True


def combine_proof_candidate_lists(candidate_lists: List[List[Tuple[frozenset, frozenset]]], extra_rule: Optional[str]) -> List[Tuple[frozenset, frozenset]]:
    combinations: List[Tuple[frozenset, frozenset]] = [(frozenset(), frozenset())]
    for candidate_list in candidate_lists:
        next_combinations: List[Tuple[frozenset, frozenset]] = []
        for base_evidence, base_rules in combinations:
            for evidence, rules in candidate_list:
                candidate = (base_evidence | evidence, base_rules | rules)
                add_proof_candidate(next_combinations, candidate)
                if len(next_combinations) > MAX_WITNESS_COMBINATIONS:
                    raise StructuralError(STATE_UNSUPPORTED, "WITNESS_COMBINATION_LIMIT", "$.rules")
        combinations = next_combinations
    if extra_rule is not None:
        output: List[Tuple[frozenset, frozenset]] = []
        for evidence, rules in combinations:
            add_proof_candidate(output, (evidence, rules | frozenset([extra_rule])))
        combinations = output
    return combinations


def derive_proof_candidates(canonical: Dict[str, Any], closure: Dict[str, Any]) -> Dict[str, List[Tuple[frozenset, frozenset]]]:
    candidates: Dict[str, List[Tuple[frozenset, frozenset]]] = {}
    for evidence in canonical["evidence"]:
        for atom, value in evidence["claims"].items():
            key = literal_key(atom, value)
            candidates.setdefault(key, [])
            add_proof_candidate(candidates[key], (frozenset([evidence["id"]]), frozenset()))

    fired_rule_ids = {item["rule_id"] for item in closure["rule_firings"]}
    changed = True
    while changed:
        changed = False
        for rule in canonical["rules"]:
            if rule["id"] not in fired_rule_ids:
                continue
            premise_keys = [literal_key(atom, value) for atom, value in rule["if_all"].items()]
            if any(key not in candidates or not candidates[key] for key in premise_keys):
                continue
            conclusion_atom, conclusion_value = next(iter(rule["then"].items()))
            conclusion_key = literal_key(conclusion_atom, conclusion_value)
            generated = combine_proof_candidate_lists([candidates[key] for key in premise_keys], rule["id"])
            bucket = candidates.setdefault(conclusion_key, [])
            for candidate in generated:
                if add_proof_candidate(bucket, candidate):
                    changed = True
    return {key: sorted(value, key=proof_candidate_key) for key, value in sorted(candidates.items())}


def identity_maps(canonical: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    evidence_map = {item["id"]: canonical["evidence_ids"][index] for index, item in enumerate(canonical["evidence"])}
    rule_map = {item["id"]: canonical["rule_ids"][index] for index, item in enumerate(canonical["rules"])}
    control_map = {item["id"]: canonical["control_ids"][index] for index, item in enumerate(canonical["controls"])}
    return evidence_map, rule_map, control_map


def target_dependency_cone(canonical: Dict[str, Any], target: str) -> Dict[str, Any]:
    controls_by_id = {item["id"]: item for item in canonical["controls"]}
    control = controls_by_id[target]
    rules_by_conclusion: Dict[str, List[Dict[str, Any]]] = {}
    for rule in canonical["rules"]:
        conclusion_atom, conclusion_value = next(iter(rule["then"].items()))
        rules_by_conclusion.setdefault(literal_key(conclusion_atom, conclusion_value), []).append(rule)

    queued: List[str] = []
    for atom, value in control["require"].items():
        queued.append(literal_key(atom, value))
        queued.append(literal_key(atom, opposite(value)))
    seen_literals: Set[str] = set()
    relevant_rules: Set[str] = set()
    index = 0
    while index < len(queued):
        key = queued[index]
        index += 1
        if key in seen_literals:
            continue
        seen_literals.add(key)
        for rule in rules_by_conclusion.get(key, []):
            relevant_rules.add(rule["id"])
            for atom, value in rule["if_all"].items():
                queued.append(literal_key(atom, value))
                queued.append(literal_key(atom, opposite(value)))

    relevant_atoms = {key.rsplit("=", 1)[0] for key in seen_literals}
    relevant_evidence: Set[str] = set()
    for evidence in canonical["evidence"]:
        if any(literal_key(atom, value) in seen_literals for atom, value in evidence["claims"].items()):
            relevant_evidence.add(evidence["id"])

    evidence_map, rule_map, control_map = identity_maps(canonical)
    all_evidence = {item["id"] for item in canonical["evidence"]}
    all_rules = {item["id"] for item in canonical["rules"]}
    all_atoms = set(canonical["atoms"])
    return {
        "control_id": target,
        "control_identity_id": control_map[target],
        "literals": sorted(seen_literals),
        "atoms": sorted(relevant_atoms),
        "evidence_sources": sorted(relevant_evidence),
        "evidence_identity_ids": [evidence_map[item] for item in sorted(relevant_evidence)],
        "rules": sorted(relevant_rules),
        "rule_identity_ids": [rule_map[item] for item in sorted(relevant_rules)],
        "excluded_atoms": sorted(all_atoms - relevant_atoms),
        "excluded_evidence_sources": sorted(all_evidence - relevant_evidence),
        "excluded_rules": sorted(all_rules - relevant_rules),
    }


def witness_source_structure(canonical: Dict[str, Any], target: str, evidence_ids: Set[str], rule_ids: Set[str]) -> Dict[str, Any]:
    controls_by_id = {item["id"]: item for item in canonical["controls"]}
    evidence = [json.loads(json.dumps(item)) for item in canonical["evidence"] if item["id"] in evidence_ids]
    rules = [json.loads(json.dumps(item)) for item in canonical["rules"] if item["id"] in rule_ids]
    control = json.loads(json.dumps(controls_by_id[target]))
    atom_set: Set[str] = set(control["require"].keys())
    for item in evidence:
        atom_set.update(item["claims"].keys())
    for item in rules:
        atom_set.update(item["if_all"].keys())
        atom_set.update(item["then"].keys())
    return {
        "schema": INPUT_SCHEMA,
        "atoms": sorted(atom_set),
        "targets": [target],
        "evidence": evidence,
        "rules": rules,
        "controls": [control],
    }


def restricted_target_result(canonical: Dict[str, Any], target: str, evidence_ids: Set[str], rule_ids: Set[str]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    source = witness_source_structure(canonical, target, evidence_ids, rule_ids)
    restricted = normalize_structure(source)
    closure = derive_closure(restricted)
    resolution = build_resolution(restricted, closure)
    return restricted, resolution["targets"][target]


def witness_choice_key(item: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        item["source_count"],
        item["evidence_count"],
        item["rule_count"],
        tuple(item["evidence_sources"]),
        tuple(item["rules"]),
        canonical_json(item.get("derivation_paths", {})),
    )


def materialize_witness(canonical: Dict[str, Any], target: str, verdict: str, evidence_ids: Set[str], rule_ids: Set[str], derivation_paths: Dict[str, Any], decisive_literals: List[str]) -> Optional[Dict[str, Any]]:
    restricted, target_result = restricted_target_result(canonical, target, evidence_ids, rule_ids)
    if target_result["verdict"] != verdict:
        return None
    evidence_map, rule_map, control_map = identity_maps(canonical)
    evidence_sources = sorted(evidence_ids)
    rules = sorted(rule_ids)
    core = {
        "semantics": "DECLARED_STRUCTURE_ONLY",
        "optimization_metric": "MIN_EVIDENCE_PLUS_RULE_COUNT_THEN_CANONICAL",
        "target": target,
        "control_identity_id": control_map[target],
        "verdict": verdict,
        "decisive_literals": sorted(decisive_literals),
        "evidence_sources": evidence_sources,
        "evidence_identity_ids": [evidence_map[item] for item in evidence_sources],
        "rules": rules,
        "rule_identity_ids": [rule_map[item] for item in rules],
        "evidence_count": len(evidence_sources),
        "rule_count": len(rules),
        "source_count": len(evidence_sources) + len(rules),
        "derivation_paths": derivation_paths,
        "witness_structure_id": restricted["canonical_structure_id"],
        "reproduced_verdict": target_result["verdict"],
    }
    witness = dict(core)
    witness["witness_id"] = identity("slang_audit_minimal_witness_sha256", core)
    return witness


def literal_path(candidate: Tuple[frozenset, frozenset]) -> Dict[str, Any]:
    evidence, rules = candidate
    return {"evidence_sources": sorted(evidence), "rules": sorted(rules)}


def minimal_target_witness(canonical: Dict[str, Any], closure: Dict[str, Any], target: str, target_result: Dict[str, Any], proof_candidates: Dict[str, List[Tuple[frozenset, frozenset]]]) -> Optional[Dict[str, Any]]:
    controls_by_id = {item["id"]: item for item in canonical["controls"]}
    control = controls_by_id[target]
    verdict = target_result["verdict"]
    choices: List[Dict[str, Any]] = []
    combinations_examined = 0

    if verdict == VERDICT_PASS:
        requirements = [literal_key(atom, value) for atom, value in control["require"].items()]
        candidate_lists = [proof_candidates.get(key, []) for key in requirements]
        if any(not item for item in candidate_lists):
            raise StructuralError(STATE_UNSUPPORTED, "PASS_WITNESS_UNAVAILABLE", "$.controls." + target)
        combinations: List[Tuple[frozenset, frozenset, Dict[str, Any]]] = [(frozenset(), frozenset(), {})]
        for requirement, candidate_list in zip(requirements, candidate_lists):
            next_combinations: List[Tuple[frozenset, frozenset, Dict[str, Any]]] = []
            seen: Set[str] = set()
            for base_evidence, base_rules, base_paths in combinations:
                for candidate in candidate_list:
                    combinations_examined += 1
                    if combinations_examined > MAX_WITNESS_COMBINATIONS:
                        raise StructuralError(STATE_UNSUPPORTED, "WITNESS_COMBINATION_LIMIT", "$.controls." + target)
                    evidence, rules = candidate
                    paths = dict(base_paths)
                    paths[requirement] = literal_path(candidate)
                    combined_evidence = base_evidence | evidence
                    combined_rules = base_rules | rules
                    key = canonical_json({"e": sorted(combined_evidence), "r": sorted(combined_rules), "p": paths})
                    if key in seen:
                        continue
                    seen.add(key)
                    next_combinations.append((combined_evidence, combined_rules, paths))
            combinations = next_combinations
        for evidence, rules, paths in combinations:
            witness = materialize_witness(canonical, target, verdict, set(evidence), set(rules), paths, requirements)
            if witness is not None:
                choices.append(witness)

    elif verdict == VERDICT_VIOLATED:
        for atom, value in control["require"].items():
            opposing = literal_key(atom, opposite(value))
            for candidate in proof_candidates.get(opposing, []):
                combinations_examined += 1
                if combinations_examined > MAX_WITNESS_COMBINATIONS:
                    raise StructuralError(STATE_UNSUPPORTED, "WITNESS_COMBINATION_LIMIT", "$.controls." + target)
                evidence, rules = candidate
                witness = materialize_witness(
                    canonical,
                    target,
                    verdict,
                    set(evidence),
                    set(rules),
                    {opposing: literal_path(candidate)},
                    [opposing],
                )
                if witness is not None:
                    choices.append(witness)

    elif verdict == VERDICT_ABSTAIN:
        for atom, value in control["require"].items():
            required = literal_key(atom, value)
            opposing = literal_key(atom, opposite(value))
            for required_candidate in proof_candidates.get(required, []):
                for opposing_candidate in proof_candidates.get(opposing, []):
                    combinations_examined += 1
                    if combinations_examined > MAX_WITNESS_COMBINATIONS:
                        raise StructuralError(STATE_UNSUPPORTED, "WITNESS_COMBINATION_LIMIT", "$.controls." + target)
                    evidence = set(required_candidate[0] | opposing_candidate[0])
                    rules = set(required_candidate[1] | opposing_candidate[1])
                    paths = {
                        required: literal_path(required_candidate),
                        opposing: literal_path(opposing_candidate),
                    }
                    witness = materialize_witness(canonical, target, verdict, evidence, rules, paths, [required, opposing])
                    if witness is not None:
                        choices.append(witness)

    if verdict == VERDICT_INCOMPLETE:
        return None
    if not choices:
        raise StructuralError(STATE_UNSUPPORTED, "MINIMAL_WITNESS_UNAVAILABLE", "$.controls." + target)
    choices.sort(key=witness_choice_key)
    return choices[0]


def target_goal_literals(canonical: Dict[str, Any], target: str) -> List[str]:
    controls_by_id = {item["id"]: item for item in canonical["controls"]}
    control = controls_by_id[target]
    rules_by_conclusion: Dict[str, List[Dict[str, Any]]] = {}
    for rule in canonical["rules"]:
        conclusion_atom, conclusion_value = next(iter(rule["then"].items()))
        rules_by_conclusion.setdefault(literal_key(conclusion_atom, conclusion_value), []).append(rule)
    queued = [literal_key(atom, value) for atom, value in control["require"].items()]
    seen: Set[str] = set()
    index = 0
    while index < len(queued):
        key = queued[index]
        index += 1
        if key in seen:
            continue
        seen.add(key)
        for rule in rules_by_conclusion.get(key, []):
            for atom, value in rule["if_all"].items():
                queued.append(literal_key(atom, value))
    return sorted(seen)


def parse_literal_key(key: str) -> Tuple[str, bool]:
    atom, raw = key.rsplit("=", 1)
    return atom, raw == "true"


def counterfactual_source(canonical: Dict[str, Any], target: str, removed_sources: Set[str], added_literals: Set[str]) -> Dict[str, Any]:
    source = canonical_to_source(canonical)
    removed_evidence = {item.split(":", 1)[1] for item in removed_sources if item.startswith("evidence:")}
    removed_rules = {item.split(":", 1)[1] for item in removed_sources if item.startswith("rule:")}
    source["targets"] = [target]
    source["controls"] = [item for item in source["controls"] if item["id"] == target]
    source["evidence"] = [item for item in source["evidence"] if item["id"] not in removed_evidence]
    source["rules"] = [item for item in source["rules"] if item["id"] not in removed_rules]
    existing_ids = {item["id"] for item in source["evidence"]}
    for index, key in enumerate(sorted(added_literals)):
        atom, value = parse_literal_key(key)
        seed = "counterfactual_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        evidence_id = seed
        suffix = 0
        while evidence_id in existing_ids:
            suffix += 1
            evidence_id = seed + "_" + str(suffix)
        existing_ids.add(evidence_id)
        source["evidence"].append({"id": evidence_id, "claims": {atom: value}, "commitment": None})
    return source


def counterfactual_target_result(canonical: Dict[str, Any], target: str, removed_sources: Set[str], added_literals: Set[str]) -> Tuple[str, str]:
    restricted = normalize_structure(counterfactual_source(canonical, target, removed_sources, added_literals))
    closure = derive_closure(restricted)
    resolution = build_resolution(restricted, closure)
    return resolution["targets"][target]["verdict"], restricted["canonical_structure_id"]


def counterfactual_source_candidates(canonical: Dict[str, Any], target: str) -> List[str]:
    cone = target_dependency_cone(canonical, target)
    sources = ["evidence:" + item for item in cone["evidence_sources"]]
    sources.extend("rule:" + item for item in cone["rules"])
    return sorted(sources)


def available_goal_additions(canonical: Dict[str, Any], closure: Dict[str, Any], target: str) -> List[str]:
    support = closure["support"]
    output = [key for key in target_goal_literals(canonical, target) if key not in support]
    return sorted(output)


def removal_parts(items: Sequence[str]) -> Tuple[List[str], List[str]]:
    evidence = sorted(item.split(":", 1)[1] for item in items if item.startswith("evidence:"))
    rules = sorted(item.split(":", 1)[1] for item in items if item.startswith("rule:"))
    return evidence, rules


def cut_choice_key(item: Dict[str, Any]) -> Tuple[Any, ...]:
    tagged = ["evidence:" + value for value in item["removed_evidence_sources"]]
    tagged.extend("rule:" + value for value in item["removed_rules"])
    return (
        item["change_count"],
        tuple(sorted(tagged)),
        item["counterfactual_verdict"],
    )


def repair_choice_key(item: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        item["change_count"],
        item["removed_source_count"],
        item["added_literal_count"],
        tuple(item["removed_evidence_sources"]),
        tuple(item["removed_rules"]),
        tuple(item["added_literals"]),
    )


def minimal_verdict_cut(canonical: Dict[str, Any], target: str, baseline_verdict: str) -> Dict[str, Any]:
    sources = counterfactual_source_candidates(canonical, target)
    if not sources:
        return {"status": "NO_DECLARED_SOURCE_CUT_AVAILABLE", "baseline_verdict": baseline_verdict}
    if len(sources) > MAX_COUNTERFACTUAL_CANDIDATE_SOURCES:
        return {"status": "RESOURCE_LIMIT", "baseline_verdict": baseline_verdict, "candidate_source_count": len(sources)}
    evaluations = 0
    for size in range(1, len(sources) + 1):
        matches: List[Dict[str, Any]] = []
        level_complete = True
        for combo in itertools.combinations(sources, size):
            evaluations += 1
            if evaluations > MAX_COUNTERFACTUAL_EVALUATIONS:
                level_complete = False
                break
            verdict, structure_id = counterfactual_target_result(canonical, target, set(combo), set())
            if verdict != baseline_verdict:
                evidence, rules = removal_parts(combo)
                core = {
                    "semantics": "DECLARED_STRUCTURE_SOURCE_REMOVAL_ONLY",
                    "target": target,
                    "baseline_verdict": baseline_verdict,
                    "counterfactual_verdict": verdict,
                    "removed_evidence_sources": evidence,
                    "removed_rules": rules,
                    "removed_evidence_count": len(evidence),
                    "removed_rule_count": len(rules),
                    "change_count": len(combo),
                    "counterfactual_structure_id": structure_id,
                }
                item = dict(core)
                id_core = dict(core)
                id_core.pop("counterfactual_structure_id")
                item["cut_id"] = identity("slang_audit_minimal_cut_sha256", id_core)
                matches.append(item)
        if not level_complete:
            return {"status": "RESOURCE_LIMIT", "baseline_verdict": baseline_verdict, "evaluations": evaluations}
        if matches:
            matches.sort(key=cut_choice_key)
            selected = matches[0]
            return {
                "status": "AVAILABLE",
                "exact_within_declared_resource_bounds": True,
                "minimal_change_count": size,
                "minimal_cut_count": len(matches),
                "selected": selected,
                "evaluations": evaluations,
            }
    return {"status": "NO_DECLARED_SOURCE_CUT_AVAILABLE", "baseline_verdict": baseline_verdict, "evaluations": evaluations}


def minimal_completion_frontier(canonical: Dict[str, Any], closure: Dict[str, Any], target: str, baseline_verdict: str) -> Dict[str, Any]:
    if baseline_verdict != VERDICT_INCOMPLETE:
        return {"status": "NOT_APPLICABLE", "baseline_verdict": baseline_verdict}
    additions = available_goal_additions(canonical, closure, target)
    if not additions:
        return {"status": "NO_LITERAL_COMPLETION_AVAILABLE", "baseline_verdict": baseline_verdict}
    if len(additions) > MAX_COUNTERFACTUAL_CANDIDATE_LITERALS:
        return {"status": "RESOURCE_LIMIT", "baseline_verdict": baseline_verdict, "candidate_literal_count": len(additions)}
    evaluations = 0
    for size in range(1, len(additions) + 1):
        matches: List[Dict[str, Any]] = []
        level_complete = True
        for combo in itertools.combinations(additions, size):
            evaluations += 1
            if evaluations > MAX_COUNTERFACTUAL_EVALUATIONS:
                level_complete = False
                break
            verdict, structure_id = counterfactual_target_result(canonical, target, set(), set(combo))
            if verdict == VERDICT_PASS:
                core = {
                    "semantics": "HYPOTHETICAL_DECLARED_LITERAL_ADDITION_ONLY",
                    "target": target,
                    "baseline_verdict": baseline_verdict,
                    "counterfactual_verdict": verdict,
                    "added_literals": sorted(combo),
                    "change_count": len(combo),
                    "counterfactual_structure_id": structure_id,
                }
                item = dict(core)
                id_core = dict(core)
                id_core.pop("counterfactual_structure_id")
                item["completion_id"] = identity("slang_audit_completion_frontier_sha256", id_core)
                matches.append(item)
        if not level_complete:
            return {"status": "RESOURCE_LIMIT", "baseline_verdict": baseline_verdict, "evaluations": evaluations}
        if matches:
            matches.sort(key=lambda item: (item["change_count"], tuple(item["added_literals"])))
            return {
                "status": "AVAILABLE",
                "exact_within_declared_resource_bounds": True,
                "minimal_change_count": size,
                "minimal_completion_count": len(matches),
                "selected": matches[0],
                "evaluations": evaluations,
            }
    return {"status": "NO_LITERAL_COMPLETION_AVAILABLE", "baseline_verdict": baseline_verdict, "evaluations": evaluations}


def minimal_repair_to_pass(canonical: Dict[str, Any], closure: Dict[str, Any], target: str, baseline_verdict: str) -> Dict[str, Any]:
    if baseline_verdict == VERDICT_PASS:
        return {"status": "NOT_APPLICABLE_ALREADY_PASS", "baseline_verdict": baseline_verdict}
    sources = counterfactual_source_candidates(canonical, target)
    additions = available_goal_additions(canonical, closure, target)
    if len(sources) > MAX_COUNTERFACTUAL_CANDIDATE_SOURCES or len(additions) > MAX_COUNTERFACTUAL_CANDIDATE_LITERALS:
        return {
            "status": "RESOURCE_LIMIT",
            "baseline_verdict": baseline_verdict,
            "candidate_source_count": len(sources),
            "candidate_literal_count": len(additions),
        }
    evaluations = 0
    max_changes = len(sources) + len(additions)
    for total in range(1, max_changes + 1):
        matches: List[Dict[str, Any]] = []
        level_complete = True
        min_remove = max(0, total - len(additions))
        max_remove = min(total, len(sources))
        for remove_count in range(min_remove, max_remove + 1):
            add_count = total - remove_count
            for removed in itertools.combinations(sources, remove_count):
                for added in itertools.combinations(additions, add_count):
                    evaluations += 1
                    if evaluations > MAX_COUNTERFACTUAL_EVALUATIONS:
                        level_complete = False
                        break
                    verdict, structure_id = counterfactual_target_result(canonical, target, set(removed), set(added))
                    if verdict == VERDICT_PASS:
                        evidence, rules = removal_parts(removed)
                        core = {
                            "semantics": "DECLARED_SOURCE_REMOVAL_PLUS_HYPOTHETICAL_LITERAL_ADDITION",
                            "target": target,
                            "baseline_verdict": baseline_verdict,
                            "counterfactual_verdict": verdict,
                            "removed_evidence_sources": evidence,
                            "removed_rules": rules,
                            "added_literals": sorted(added),
                            "removed_source_count": len(removed),
                            "added_literal_count": len(added),
                            "change_count": total,
                            "counterfactual_structure_id": structure_id,
                        }
                        item = dict(core)
                        id_core = dict(core)
                        id_core.pop("counterfactual_structure_id")
                        item["repair_id"] = identity("slang_audit_minimal_repair_sha256", id_core)
                        matches.append(item)
                if not level_complete:
                    break
            if not level_complete:
                break
        if not level_complete:
            return {"status": "RESOURCE_LIMIT", "baseline_verdict": baseline_verdict, "evaluations": evaluations}
        if matches:
            matches.sort(key=repair_choice_key)
            return {
                "status": "AVAILABLE",
                "exact_within_declared_resource_bounds": True,
                "minimal_change_count": total,
                "minimal_repair_count": len(matches),
                "selected": matches[0],
                "evaluations": evaluations,
            }
    return {"status": "NO_REPAIR_TO_PASS_AVAILABLE", "baseline_verdict": baseline_verdict, "evaluations": evaluations}


def build_counterfactual_analysis(canonical: Dict[str, Any], closure: Dict[str, Any], target: str, target_result: Dict[str, Any], witness: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    verdict = target_result["verdict"]
    cut = minimal_verdict_cut(canonical, target, verdict)
    completion = minimal_completion_frontier(canonical, closure, target, verdict)
    repair = minimal_repair_to_pass(canonical, closure, target, verdict)
    return {
        "semantics": "TARGET_SPECIFIC_DECLARED_STRUCTURE_COUNTERFACTUAL_ONLY",
        "baseline_verdict": verdict,
        "minimal_verdict_cut": cut,
        "completion_frontier": completion,
        "minimal_repair_to_pass": repair,
        "decisive_witness_id": None if witness is None else witness["witness_id"],
    }


def build_target_analysis_item(canonical: Dict[str, Any], closure: Dict[str, Any], target: str, target_result: Dict[str, Any], proof_candidates: Dict[str, List[Tuple[frozenset, frozenset]]]) -> Dict[str, Any]:
    witness = minimal_target_witness(canonical, closure, target, target_result, proof_candidates)
    return {
        "dependency_cone": target_dependency_cone(canonical, target),
        "minimal_sufficient_witness": witness,
        "witness_status": "AVAILABLE" if witness is not None else "NOT_APPLICABLE_INCOMPLETE_TARGET",
        "counterfactual_analysis": build_counterfactual_analysis(canonical, closure, target, target_result, witness),
    }


def build_target_analysis(canonical: Dict[str, Any], closure: Dict[str, Any], resolution: Dict[str, Any]) -> Dict[str, Any]:
    proof_candidates = derive_proof_candidates(canonical, closure)
    analysis: Dict[str, Any] = {}
    for target in canonical["targets"]:
        analysis[target] = build_target_analysis_item(canonical, closure, target, resolution["targets"][target], proof_candidates)
    return {key: analysis[key] for key in sorted(analysis.keys())}


def target_proof_projection(target: str, target_result: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
    cone = analysis["dependency_cone"]
    cone_projection = {
        "control_id": cone["control_id"],
        "control_identity_id": cone["control_identity_id"],
        "atoms": cone["atoms"],
        "literals": cone["literals"],
        "evidence_sources": cone["evidence_sources"],
        "evidence_identity_ids": cone["evidence_identity_ids"],
        "rules": cone["rules"],
        "rule_identity_ids": cone["rule_identity_ids"],
    }
    witness = analysis["minimal_sufficient_witness"]
    counterfactual = analysis["counterfactual_analysis"]

    def action_projection(value: Dict[str, Any], identity_key: str) -> Dict[str, Any]:
        output = {"status": value.get("status"), "baseline_verdict": value.get("baseline_verdict")}
        for key in ("minimal_change_count", "minimal_cut_count", "minimal_completion_count", "minimal_repair_count"):
            if key in value:
                output[key] = value[key]
        selected = value.get("selected")
        if isinstance(selected, dict):
            output["selected_id"] = selected.get(identity_key)
            output["counterfactual_verdict"] = selected.get("counterfactual_verdict")
        return output

    return {
        "target": target,
        "target_result": target_result,
        "dependency_cone": cone_projection,
        "witness_status": analysis["witness_status"],
        "minimal_witness_id": None if witness is None else witness["witness_id"],
        "minimal_verdict_cut": action_projection(counterfactual["minimal_verdict_cut"], "cut_id"),
        "completion_frontier": action_projection(counterfactual["completion_frontier"], "completion_id"),
        "minimal_repair_to_pass": action_projection(counterfactual["minimal_repair_to_pass"], "repair_id"),
    }


def build_target_proof_ids(resolution: Dict[str, Any], target_analysis: Dict[str, Any]) -> Dict[str, str]:
    output: Dict[str, str] = {}
    for target in sorted(target_analysis.keys()):
        projection = target_proof_projection(target, resolution["targets"][target], target_analysis[target])
        output[target] = identity("slang_audit_target_proof_sha256", projection)
    return output


def certificate_from_canonical(canonical: Dict[str, Any]) -> Dict[str, Any]:
    closure = derive_closure(canonical)
    resolution = build_resolution(canonical, closure)
    target_analysis = build_target_analysis(canonical, closure, resolution)
    target_proof_ids = build_target_proof_ids(resolution, target_analysis)
    proof = {
        "schema": PROOF_SCHEMA,
        "declared_evidence_only": True,
        "external_truth_verified": False,
        "external_source_provenance_verified": False,
        "replay_performed": False,
        "reconciliation_performed": False,
        "closure": closure,
        "target_analysis": target_analysis,
        "target_proof_ids": target_proof_ids,
        "target_proof_semantics": "TARGET_LOCAL_IDENTITY_EXCLUDES_UNRELATED_DECLARED_STRUCTURE",
        "minimal_witness_semantics": "TARGET_SPECIFIC_DECLARED_STRUCTURE_ONLY",
        "minimal_witness_search": {
            "exact_within_declared_resource_bounds": True,
            "candidate_limit_per_literal": MAX_PROOF_CANDIDATES_PER_LITERAL,
            "combination_limit_per_target": MAX_WITNESS_COMBINATIONS,
            "silent_truncation": False,
        },
        "counterfactual_semantics": "DECLARED_STRUCTURE_ONLY_NO_REAL_WORLD_AUDIT_AUTHORITY",
        "counterfactual_search": {
            "exact_when_status_available": True,
            "candidate_source_limit": MAX_COUNTERFACTUAL_CANDIDATE_SOURCES,
            "candidate_literal_limit": MAX_COUNTERFACTUAL_CANDIDATE_LITERALS,
            "evaluation_limit_per_analysis": MAX_COUNTERFACTUAL_EVALUATIONS,
            "silent_truncation": False,
        },
        "evidence_commitments": {
            "declared_evidence_count": len(canonical["evidence"]),
            "committed_evidence_count": sum(1 for item in canonical["evidence"] if item.get("commitment") is not None),
            "all_evidence_committed": bool(canonical["evidence"]) and all(item.get("commitment") is not None for item in canonical["evidence"]),
            "commitment_semantics": "IDENTITY_BINDING_ONLY",
        },
    }
    certificate_core = {
        "schema": CERTIFICATE_SCHEMA,
        "version": VERSION,
        "profile_id": PROFILE_ID,
        "canonical_structure_id": canonical["canonical_structure_id"],
        "state": resolution["state"],
        "reason_codes": resolution["reason_codes"],
        "resolution": resolution,
        "proof": proof,
        "authority": "NONE",
    }
    certificate = dict(certificate_core)
    certificate["certificate_id"] = identity("slang_audit_certificate_sha256", certificate_core)
    return certificate


def make_error_bundle(raw: Any, error: StructuralError) -> Dict[str, Any]:
    input_identity = identity("slang_audit_rejected_input_sha256", raw)
    certificate_core = {
        "schema": CERTIFICATE_SCHEMA,
        "version": VERSION,
        "profile_id": PROFILE_ID,
        "canonical_structure_id": None,
        "state": error.state,
        "reason_codes": [error.code],
        "resolution": {"state": error.state, "path": error.path, "verdicts": {}, "targets": {}},
        "proof": {
            "schema": PROOF_SCHEMA,
            "declared_evidence_only": True,
            "external_truth_verified": False,
            "external_source_provenance_verified": False,
            "replay_performed": False,
            "reconciliation_performed": False,
            "rejected_input_id": input_identity,
        },
        "authority": "NONE",
    }
    certificate = dict(certificate_core)
    certificate["certificate_id"] = identity("slang_audit_certificate_sha256", certificate_core)
    bundle_core = {
        "schema": BUNDLE_SCHEMA,
        "version": VERSION,
        "canonical_structure": None,
        "certificate": certificate,
    }
    bundle = dict(bundle_core)
    bundle["bundle_id"] = identity("slang_audit_bundle_sha256", bundle_core)
    return bundle


def resolve_structure(raw: Any) -> Dict[str, Any]:
    try:
        canonical = normalize_structure(raw)
        certificate = certificate_from_canonical(canonical)
        bundle_core = {
            "schema": BUNDLE_SCHEMA,
            "version": VERSION,
            "canonical_structure": canonical,
            "certificate": certificate,
        }
        bundle = dict(bundle_core)
        bundle["bundle_id"] = identity("slang_audit_bundle_sha256", bundle_core)
        return bundle
    except StructuralError as error:
        return make_error_bundle(raw, error)


def canonical_to_source(canonical: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema": canonical["source_schema"],
        "atoms": list(canonical["atoms"]),
        "targets": list(canonical["targets"]),
        "evidence": json.loads(json.dumps(canonical["evidence"])),
        "rules": json.loads(json.dumps(canonical["rules"])),
        "controls": json.loads(json.dumps(canonical["controls"])),
    }


def verify_bundle(bundle: Any) -> Tuple[bool, str]:
    if not isinstance(bundle, dict):
        return False, "INVALID_BUNDLE_TYPE"
    expected_keys = {"schema", "version", "canonical_structure", "certificate", "bundle_id"}
    if set(bundle.keys()) != expected_keys:
        return False, "INVALID_BUNDLE_FIELDS"
    if bundle.get("schema") != BUNDLE_SCHEMA:
        return False, "INVALID_BUNDLE_SCHEMA"
    if bundle.get("version") != VERSION:
        return False, "INVALID_BUNDLE_VERSION"

    bundle_core = dict(bundle)
    supplied_bundle_id = bundle_core.pop("bundle_id", None)
    if supplied_bundle_id != identity("slang_audit_bundle_sha256", bundle_core):
        return False, "BUNDLE_ID_MISMATCH"

    certificate = bundle.get("certificate")
    if not isinstance(certificate, dict):
        return False, "INVALID_CERTIFICATE_TYPE"
    certificate_core = dict(certificate)
    supplied_certificate_id = certificate_core.pop("certificate_id", None)
    if supplied_certificate_id != identity("slang_audit_certificate_sha256", certificate_core):
        return False, "CERTIFICATE_ID_MISMATCH"

    canonical = bundle.get("canonical_structure")
    if canonical is None:
        if certificate.get("state") not in {STATE_FORBIDDEN, STATE_UNSUPPORTED}:
            return False, "MISSING_CANONICAL_STRUCTURE"
        return True, "PASS"
    if not isinstance(canonical, dict):
        return False, "INVALID_CANONICAL_STRUCTURE_TYPE"

    expected_canonical_keys = {
        "schema",
        "source_schema",
        "profile_id",
        "canonicalization_id",
        "atoms",
        "targets",
        "evidence",
        "rules",
        "controls",
        "evidence_ids",
        "rule_ids",
        "control_ids",
        "canonical_structure_id",
    }
    if set(canonical.keys()) != expected_canonical_keys:
        return False, "INVALID_CANONICAL_STRUCTURE_FIELDS"
    if canonical.get("schema") != CANONICAL_SCHEMA:
        return False, "INVALID_CANONICAL_SCHEMA"
    if canonical.get("source_schema") != INPUT_SCHEMA:
        return False, "INVALID_SOURCE_SCHEMA"
    if canonical.get("profile_id") != PROFILE_ID:
        return False, "INVALID_PROFILE_ID"
    if canonical.get("canonicalization_id") != CANONICALIZATION_ID:
        return False, "INVALID_CANONICALIZATION_ID"

    structure_core = dict(canonical)
    supplied_structure_id = structure_core.pop("canonical_structure_id", None)
    if supplied_structure_id != identity("slang_audit_structure_sha256", structure_core):
        return False, "STRUCTURE_ID_MISMATCH"
    if certificate.get("canonical_structure_id") != supplied_structure_id:
        return False, "CERTIFICATE_STRUCTURE_BINDING_MISMATCH"

    try:
        renormalized = normalize_structure(canonical_to_source(canonical))
    except StructuralError:
        return False, "CANONICAL_RENORMALIZATION_FAILED"
    if renormalized != canonical:
        return False, "CANONICAL_STRUCTURE_MISMATCH"

    expected_evidence_ids = [identity("slang_audit_evidence_sha256", item) for item in canonical["evidence"]]
    expected_rule_ids = [identity("slang_audit_rule_sha256", item) for item in canonical["rules"]]
    expected_control_ids = [identity("slang_audit_control_sha256", item) for item in canonical["controls"]]
    if canonical["evidence_ids"] != expected_evidence_ids:
        return False, "EVIDENCE_ID_MISMATCH"
    if canonical["rule_ids"] != expected_rule_ids:
        return False, "RULE_ID_MISMATCH"
    if canonical["control_ids"] != expected_control_ids:
        return False, "CONTROL_ID_MISMATCH"

    try:
        expected_certificate = certificate_from_canonical(canonical)
    except StructuralError:
        return False, "CERTIFICATE_RECOMPUTATION_FAILED"
    if expected_certificate != certificate:
        return False, "CERTIFICATE_RECOMPUTATION_MISMATCH"
    return True, "PASS"


def normalize_delta(raw: Any, base_bundle: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise StructuralError(STATE_UNSUPPORTED, "INVALID_DELTA_TYPE", "$")
    allowed = {"schema", "base_bundle_id", "remove_evidence", "upsert_evidence", "remove_rules", "upsert_rules", "delta_id"}
    unknown = sorted(set(raw.keys()) - allowed)
    if unknown:
        raise StructuralError(STATE_UNSUPPORTED, "UNKNOWN_DELTA_FIELD", "$." + unknown[0])
    if raw.get("schema") != DELTA_SCHEMA:
        raise StructuralError(STATE_UNSUPPORTED, "UNSUPPORTED_DELTA_SCHEMA", "$.schema")
    if raw.get("base_bundle_id") != base_bundle.get("bundle_id"):
        raise StructuralError(STATE_FORBIDDEN, "DELTA_BASE_BINDING_MISMATCH", "$.base_bundle_id")
    canonical = base_bundle["canonical_structure"]
    atom_set = set(canonical["atoms"])

    def id_list(name: str, maximum: int) -> List[str]:
        value = raw.get(name, [])
        if not isinstance(value, list) or len(value) > maximum:
            raise StructuralError(STATE_UNSUPPORTED, "INVALID_DELTA_OPERATION_LIST", "$." + name)
        output = [parse_identifier(item, "$." + name) for item in value]
        if len(output) != len(set(output)):
            raise StructuralError(STATE_UNSUPPORTED, "DUPLICATE_DELTA_OPERATION", "$." + name)
        return sorted(output)

    remove_evidence = id_list("remove_evidence", MAX_DELTA_EVIDENCE_OPERATIONS)
    remove_rules = id_list("remove_rules", MAX_DELTA_RULE_OPERATIONS)
    base_evidence_ids = {item["id"] for item in canonical["evidence"]}
    base_rule_ids = {item["id"] for item in canonical["rules"]}
    if any(item not in base_evidence_ids for item in remove_evidence):
        raise StructuralError(STATE_UNSUPPORTED, "REMOVE_UNKNOWN_EVIDENCE", "$.remove_evidence")
    if any(item not in base_rule_ids for item in remove_rules):
        raise StructuralError(STATE_UNSUPPORTED, "REMOVE_UNKNOWN_RULE", "$.remove_rules")

    upsert_evidence_raw = raw.get("upsert_evidence", [])
    if not isinstance(upsert_evidence_raw, list) or len(upsert_evidence_raw) > MAX_DELTA_EVIDENCE_OPERATIONS:
        raise StructuralError(STATE_UNSUPPORTED, "INVALID_DELTA_EVIDENCE", "$.upsert_evidence")
    upsert_evidence: List[Dict[str, Any]] = []
    seen_evidence: Set[str] = set()
    for index, item in enumerate(upsert_evidence_raw):
        path = "$.upsert_evidence[{}]".format(index)
        if not isinstance(item, dict) or set(item.keys()) - EVIDENCE_KEYS or "id" not in item or "claims" not in item:
            raise StructuralError(STATE_UNSUPPORTED, "INVALID_DELTA_EVIDENCE_ITEM", path)
        item_id = parse_identifier(item["id"], path + ".id")
        if item_id in seen_evidence:
            raise StructuralError(STATE_UNSUPPORTED, "DUPLICATE_DELTA_EVIDENCE_ID", path + ".id")
        seen_evidence.add(item_id)
        claims = parse_literal_map(item["claims"], path + ".claims", MAX_CLAIMS_PER_EVIDENCE, False)
        if set(claims.keys()) - atom_set:
            raise StructuralError(STATE_UNSUPPORTED, "UNDECLARED_ATOM", path + ".claims")
        commitment = parse_commitment(item.get("commitment"), path + ".commitment")
        upsert_evidence.append({"id": item_id, "claims": claims, "commitment": commitment})
    upsert_evidence.sort(key=lambda item: item["id"])

    upsert_rules_raw = raw.get("upsert_rules", [])
    if not isinstance(upsert_rules_raw, list) or len(upsert_rules_raw) > MAX_DELTA_RULE_OPERATIONS:
        raise StructuralError(STATE_UNSUPPORTED, "INVALID_DELTA_RULES", "$.upsert_rules")
    upsert_rules: List[Dict[str, Any]] = []
    seen_rules: Set[str] = set()
    for index, item in enumerate(upsert_rules_raw):
        path = "$.upsert_rules[{}]".format(index)
        if not isinstance(item, dict) or set(item.keys()) != RULE_KEYS:
            raise StructuralError(STATE_UNSUPPORTED, "INVALID_DELTA_RULE_ITEM", path)
        item_id = parse_identifier(item["id"], path + ".id")
        if item_id in seen_rules:
            raise StructuralError(STATE_UNSUPPORTED, "DUPLICATE_DELTA_RULE_ID", path + ".id")
        seen_rules.add(item_id)
        premises = parse_literal_map(item["if_all"], path + ".if_all", MAX_PREMISES_PER_RULE, False)
        conclusion = parse_literal_map(item["then"], path + ".then", 1, False)
        if (set(premises.keys()) | set(conclusion.keys())) - atom_set:
            raise StructuralError(STATE_UNSUPPORTED, "UNDECLARED_ATOM", path)
        conclusion_atom = next(iter(conclusion.keys()))
        if conclusion_atom in premises and premises[conclusion_atom] == conclusion[conclusion_atom]:
            raise StructuralError(STATE_UNSUPPORTED, "SELF_CONFIRMING_RULE", path)
        upsert_rules.append({"id": item_id, "if_all": premises, "then": conclusion})
    upsert_rules.sort(key=lambda item: item["id"])

    if set(remove_evidence) & seen_evidence:
        raise StructuralError(STATE_UNSUPPORTED, "DELTA_REMOVE_UPSERT_EVIDENCE_CONFLICT", "$.upsert_evidence")
    if set(remove_rules) & seen_rules:
        raise StructuralError(STATE_UNSUPPORTED, "DELTA_REMOVE_UPSERT_RULE_CONFLICT", "$.upsert_rules")

    core = {
        "schema": DELTA_SCHEMA,
        "base_bundle_id": base_bundle["bundle_id"],
        "remove_evidence": remove_evidence,
        "upsert_evidence": upsert_evidence,
        "remove_rules": remove_rules,
        "upsert_rules": upsert_rules,
    }
    output = dict(core)
    computed_delta_id = identity("slang_audit_delta_sha256", core)
    if raw.get("delta_id") is not None and raw.get("delta_id") != computed_delta_id:
        raise StructuralError(STATE_FORBIDDEN, "DELTA_ID_MISMATCH", "$.delta_id")
    output["delta_id"] = computed_delta_id
    return output


def apply_normalized_delta(base_canonical: Dict[str, Any], delta: Dict[str, Any]) -> Dict[str, Any]:
    source = canonical_to_source(base_canonical)
    evidence = {item["id"]: item for item in source["evidence"]}
    rules = {item["id"]: item for item in source["rules"]}
    for item_id in delta["remove_evidence"]:
        evidence.pop(item_id)
    for item in delta["upsert_evidence"]:
        evidence[item["id"]] = json.loads(json.dumps(item))
    for item_id in delta["remove_rules"]:
        rules.pop(item_id)
    for item in delta["upsert_rules"]:
        rules[item["id"]] = json.loads(json.dumps(item))
    source["evidence"] = [evidence[key] for key in sorted(evidence.keys())]
    source["rules"] = [rules[key] for key in sorted(rules.keys())]
    return source


def changed_atoms_and_dependency_targets(old: Dict[str, Any], new: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    changed: Set[str] = set()
    old_evidence = {item["id"]: item for item in old["evidence"]}
    new_evidence = {item["id"]: item for item in new["evidence"]}
    for item_id in sorted(set(old_evidence.keys()) | set(new_evidence.keys())):
        before = old_evidence.get(item_id)
        after = new_evidence.get(item_id)
        if before != after:
            if before is not None:
                changed.update(before["claims"].keys())
            if after is not None:
                changed.update(after["claims"].keys())
    old_rules = {item["id"]: item for item in old["rules"]}
    new_rules = {item["id"]: item for item in new["rules"]}
    for item_id in sorted(set(old_rules.keys()) | set(new_rules.keys())):
        before = old_rules.get(item_id)
        after = new_rules.get(item_id)
        if before != after:
            if before is not None:
                changed.update(before["then"].keys())
            if after is not None:
                changed.update(after["then"].keys())
    union_rules: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for item in old["rules"] + new["rules"]:
        key = canonical_json(item)
        if key not in seen:
            seen.add(key)
            union_rules.append(item)
    progress = True
    while progress:
        progress = False
        for rule in union_rules:
            if changed.intersection(rule["if_all"].keys()):
                conclusion = next(iter(rule["then"].keys()))
                if conclusion not in changed:
                    changed.add(conclusion)
                    progress = True
    controls = {item["id"]: item for item in new["controls"]}
    targets = [target for target in new["targets"] if changed.intersection(controls[target]["require"].keys())]
    return sorted(changed), sorted(targets)


def build_incremental_bundle(base_bundle: Any, raw_delta: Any) -> Dict[str, Any]:
    ok, reason = verify_bundle(base_bundle)
    if not ok:
        raise StructuralError(STATE_FORBIDDEN, "INVALID_BASE_BUNDLE_" + reason, "$.base_bundle")
    delta = normalize_delta(raw_delta, base_bundle)
    updated_source = apply_normalized_delta(base_bundle["canonical_structure"], delta)
    updated_bundle = resolve_structure(updated_source)
    ok_updated, reason_updated = verify_bundle(updated_bundle)
    if not ok_updated:
        raise StructuralError(STATE_FORBIDDEN, "UPDATED_BUNDLE_VERIFY_" + reason_updated, "$.updated_bundle")

    old_canonical = base_bundle["canonical_structure"]
    new_canonical = updated_bundle["canonical_structure"]
    affected_atoms, dependency_impacted_targets = changed_atoms_and_dependency_targets(old_canonical, new_canonical)
    old_ids = base_bundle["certificate"]["proof"]["target_proof_ids"]
    new_ids = updated_bundle["certificate"]["proof"]["target_proof_ids"]
    proof_changed_targets = sorted(target for target in new_canonical["targets"] if old_ids[target] != new_ids[target])
    preserved_targets = sorted(target for target in new_canonical["targets"] if old_ids[target] == new_ids[target])
    if any(target not in dependency_impacted_targets for target in proof_changed_targets):
        raise StructuralError(STATE_FORBIDDEN, "DEPENDENCY_IMPACT_UNDERSPECIFIED", "$.delta")

    new_closure = derive_closure(new_canonical)
    new_resolution = build_resolution(new_canonical, new_closure)
    proof_candidates = derive_proof_candidates(new_canonical, new_closure)
    incremental_recomputed: Dict[str, str] = {}
    for target in dependency_impacted_targets:
        item = build_target_analysis_item(new_canonical, new_closure, target, new_resolution["targets"][target], proof_candidates)
        projection = target_proof_projection(target, new_resolution["targets"][target], item)
        incremental_recomputed[target] = identity("slang_audit_target_proof_sha256", projection)
    if any(incremental_recomputed[target] != new_ids[target] for target in dependency_impacted_targets):
        raise StructuralError(STATE_FORBIDDEN, "INCREMENTAL_FULL_RECOMPUTATION_MISMATCH", "$.delta")

    transitions = {}
    for target in dependency_impacted_targets:
        transitions[target] = {
            "from": base_bundle["certificate"]["resolution"]["targets"][target]["verdict"],
            "to": updated_bundle["certificate"]["resolution"]["targets"][target]["verdict"],
            "proof_changed": old_ids[target] != new_ids[target],
        }
    delta_certificate_core = {
        "schema": DELTA_CERTIFICATE_SCHEMA,
        "version": VERSION,
        "base_bundle_id": base_bundle["bundle_id"],
        "base_structure_id": old_canonical["canonical_structure_id"],
        "delta_id": delta["delta_id"],
        "updated_bundle_id": updated_bundle["bundle_id"],
        "updated_structure_id": new_canonical["canonical_structure_id"],
        "affected_atoms": affected_atoms,
        "dependency_impacted_targets": dependency_impacted_targets,
        "proof_changed_targets": proof_changed_targets,
        "preserved_targets": preserved_targets,
        "transitions": transitions,
        "recomputed_target_proof_ids": {target: new_ids[target] for target in dependency_impacted_targets},
        "preserved_target_proof_ids": {target: old_ids[target] for target in preserved_targets},
        "incremental_semantics": "DEPENDENCY_SCOPED_TARGET_PROOF_RECOMPUTATION_WITH_FULL_EQUIVALENCE_GUARD",
        "full_recomputation_equivalence": True,
        "external_truth_verified": False,
        "external_source_provenance_verified": False,
        "audit_opinion_authority": "NONE",
    }
    delta_certificate = dict(delta_certificate_core)
    delta_certificate["delta_certificate_id"] = identity("slang_audit_delta_certificate_sha256", delta_certificate_core)
    bundle_core = {
        "schema": INCREMENTAL_BUNDLE_SCHEMA,
        "version": VERSION,
        "base_bundle": base_bundle,
        "delta": delta,
        "delta_certificate": delta_certificate,
        "updated_bundle": updated_bundle,
    }
    output = dict(bundle_core)
    output["incremental_bundle_id"] = identity("slang_audit_incremental_bundle_sha256", bundle_core)
    return output


def verify_incremental_bundle(value: Any) -> Tuple[bool, str]:
    if not isinstance(value, dict):
        return False, "INVALID_INCREMENTAL_BUNDLE_TYPE"
    expected = {"schema", "version", "base_bundle", "delta", "delta_certificate", "updated_bundle", "incremental_bundle_id"}
    if set(value.keys()) != expected:
        return False, "INVALID_INCREMENTAL_BUNDLE_FIELDS"
    if value.get("schema") != INCREMENTAL_BUNDLE_SCHEMA or value.get("version") != VERSION:
        return False, "INVALID_INCREMENTAL_BUNDLE_SCHEMA_VERSION"
    core = dict(value)
    supplied = core.pop("incremental_bundle_id", None)
    if supplied != identity("slang_audit_incremental_bundle_sha256", core):
        return False, "INCREMENTAL_BUNDLE_ID_MISMATCH"
    try:
        expected_value = build_incremental_bundle(value["base_bundle"], value["delta"])
    except StructuralError as error:
        return False, "INCREMENTAL_RECOMPUTATION_FAILED_" + error.code
    if expected_value != value:
        return False, "INCREMENTAL_RECOMPUTATION_MISMATCH"
    return True, "PASS"


def incremental_demo_delta(base_bundle: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema": DELTA_SCHEMA,
        "base_bundle_id": base_bundle["bundle_id"],
        "remove_evidence": ["contracts_ledger"],
        "upsert_evidence": [],
        "remove_rules": [],
        "upsert_rules": [],
    }


def normalize_ledger_delta_sequence(raw: Any, genesis_bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(raw, dict):
        raise StructuralError(STATE_UNSUPPORTED, "INVALID_LEDGER_DELTA_SEQUENCE_TYPE", "$")
    allowed = {"schema", "genesis_bundle_id", "deltas"}
    unknown = sorted(set(raw.keys()) - allowed)
    if unknown:
        raise StructuralError(STATE_UNSUPPORTED, "UNKNOWN_LEDGER_DELTA_SEQUENCE_FIELD", "$." + unknown[0])
    if raw.get("schema") != LEDGER_DELTA_SEQUENCE_SCHEMA:
        raise StructuralError(STATE_UNSUPPORTED, "UNSUPPORTED_LEDGER_DELTA_SEQUENCE_SCHEMA", "$.schema")
    if raw.get("genesis_bundle_id") != genesis_bundle.get("bundle_id"):
        raise StructuralError(STATE_FORBIDDEN, "LEDGER_GENESIS_BINDING_MISMATCH", "$.genesis_bundle_id")
    deltas = raw.get("deltas")
    if not isinstance(deltas, list) or len(deltas) > MAX_LEDGER_ENTRIES:
        raise StructuralError(STATE_UNSUPPORTED, "LEDGER_ENTRY_LIMIT", "$.deltas")
    return json.loads(json.dumps(deltas))


def build_proof_ledger(genesis_bundle: Any, raw_deltas: Any) -> Dict[str, Any]:
    ok, reason = verify_bundle(genesis_bundle)
    if not ok:
        raise StructuralError(STATE_FORBIDDEN, "INVALID_LEDGER_GENESIS_" + reason, "$.genesis_bundle")
    if not isinstance(raw_deltas, list) or len(raw_deltas) > MAX_LEDGER_ENTRIES:
        raise StructuralError(STATE_UNSUPPORTED, "INVALID_LEDGER_DELTAS", "$.deltas")

    current = genesis_bundle
    entries: List[Dict[str, Any]] = []
    predecessor_entry_id: Optional[str] = None
    for offset, raw_delta in enumerate(raw_deltas):
        incremental = build_incremental_bundle(current, raw_delta)
        delta = incremental["delta"]
        delta_certificate = incremental["delta_certificate"]
        updated = incremental["updated_bundle"]
        entry_core = {
            "index": offset + 1,
            "predecessor_entry_id": predecessor_entry_id,
            "base_bundle_id": current["bundle_id"],
            "base_structure_id": current["canonical_structure"]["canonical_structure_id"],
            "delta": delta,
            "delta_id": delta["delta_id"],
            "delta_certificate_id": delta_certificate["delta_certificate_id"],
            "incremental_bundle_id": incremental["incremental_bundle_id"],
            "updated_bundle_id": updated["bundle_id"],
            "updated_structure_id": updated["canonical_structure"]["canonical_structure_id"],
            "dependency_impacted_targets": delta_certificate["dependency_impacted_targets"],
            "proof_changed_targets": delta_certificate["proof_changed_targets"],
            "preserved_targets": delta_certificate["preserved_targets"],
            "transitions": delta_certificate["transitions"],
        }
        entry = dict(entry_core)
        entry["entry_id"] = identity("slang_audit_ledger_entry_sha256", entry_core)
        entries.append(entry)
        predecessor_entry_id = entry["entry_id"]
        current = updated

    entry_ids = [item["entry_id"] for item in entries]
    lineage_root_id = identity(
        "slang_audit_lineage_root_sha256",
        {"genesis_bundle_id": genesis_bundle["bundle_id"], "entry_ids": entry_ids},
    )
    checkpoint_core = {
        "schema": LEDGER_CHECKPOINT_SCHEMA,
        "version": VERSION,
        "genesis_bundle_id": genesis_bundle["bundle_id"],
        "genesis_structure_id": genesis_bundle["canonical_structure"]["canonical_structure_id"],
        "entry_count": len(entries),
        "lineage_root_id": lineage_root_id,
        "last_entry_id": None if not entries else entries[-1]["entry_id"],
        "terminal_bundle_id": current["bundle_id"],
        "terminal_structure_id": current["canonical_structure"]["canonical_structure_id"],
        "terminal_certificate_id": current["certificate"]["certificate_id"],
        "terminal_target_proof_ids": current["certificate"]["proof"]["target_proof_ids"],
        "checkpoint_semantics": "PINNED_LINEAGE_IDENTITY_REQUIRED_TO_DETECT_REBUILT_ALTERNATIVE_HISTORY",
        "external_truth_verified": False,
        "external_source_provenance_verified": False,
        "audit_opinion_authority": "NONE",
    }
    checkpoint = dict(checkpoint_core)
    checkpoint["checkpoint_id"] = identity("slang_audit_ledger_checkpoint_sha256", checkpoint_core)
    ledger_core = {
        "schema": LEDGER_SCHEMA,
        "version": VERSION,
        "genesis_bundle": genesis_bundle,
        "entries": entries,
        "terminal_bundle": current,
        "checkpoint": checkpoint,
        "lineage_semantics": "ORDERED_PREDECESSOR_BOUND_DECLARED_AUDIT_STATE_EVOLUTION",
        "external_truth_verified": False,
        "external_source_provenance_verified": False,
        "audit_opinion_authority": "NONE",
    }
    ledger = dict(ledger_core)
    ledger["ledger_id"] = identity("slang_audit_proof_ledger_sha256", ledger_core)
    return ledger


def build_proof_ledger_from_sequence(genesis_bundle: Any, raw_sequence: Any) -> Dict[str, Any]:
    deltas = normalize_ledger_delta_sequence(raw_sequence, genesis_bundle)
    return build_proof_ledger(genesis_bundle, deltas)


def verify_ledger_checkpoint_object(checkpoint: Any) -> Tuple[bool, str]:
    if not isinstance(checkpoint, dict):
        return False, "INVALID_LEDGER_CHECKPOINT_TYPE"
    expected = {
        "schema", "version", "genesis_bundle_id", "genesis_structure_id", "entry_count",
        "lineage_root_id", "last_entry_id", "terminal_bundle_id", "terminal_structure_id",
        "terminal_certificate_id", "terminal_target_proof_ids", "checkpoint_semantics",
        "external_truth_verified", "external_source_provenance_verified", "audit_opinion_authority",
        "checkpoint_id",
    }
    if set(checkpoint.keys()) != expected:
        return False, "INVALID_LEDGER_CHECKPOINT_FIELDS"
    if checkpoint.get("schema") != LEDGER_CHECKPOINT_SCHEMA or checkpoint.get("version") != VERSION:
        return False, "INVALID_LEDGER_CHECKPOINT_SCHEMA_VERSION"
    core = dict(checkpoint)
    supplied = core.pop("checkpoint_id", None)
    if supplied != identity("slang_audit_ledger_checkpoint_sha256", core):
        return False, "LEDGER_CHECKPOINT_ID_MISMATCH"
    return True, "PASS"


def verify_proof_ledger(value: Any) -> Tuple[bool, str]:
    if not isinstance(value, dict):
        return False, "INVALID_LEDGER_TYPE"
    expected = {
        "schema", "version", "genesis_bundle", "entries", "terminal_bundle", "checkpoint",
        "lineage_semantics", "external_truth_verified", "external_source_provenance_verified",
        "audit_opinion_authority", "ledger_id",
    }
    if set(value.keys()) != expected:
        return False, "INVALID_LEDGER_FIELDS"
    if value.get("schema") != LEDGER_SCHEMA or value.get("version") != VERSION:
        return False, "INVALID_LEDGER_SCHEMA_VERSION"
    core = dict(value)
    supplied = core.pop("ledger_id", None)
    if supplied != identity("slang_audit_proof_ledger_sha256", core):
        return False, "LEDGER_ID_MISMATCH"
    entries = value.get("entries")
    if not isinstance(entries, list) or len(entries) > MAX_LEDGER_ENTRIES:
        return False, "INVALID_LEDGER_ENTRIES"
    raw_deltas = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or "delta" not in entry:
            return False, "INVALID_LEDGER_ENTRY_{}".format(index + 1)
        raw_deltas.append(entry["delta"])
    try:
        expected_value = build_proof_ledger(value["genesis_bundle"], raw_deltas)
    except StructuralError as error:
        return False, "LEDGER_RECOMPUTATION_FAILED_" + error.code
    if expected_value != value:
        return False, "LEDGER_RECOMPUTATION_MISMATCH"
    return True, "PASS"


def verify_proof_ledger_against_checkpoint(value: Any, checkpoint: Any) -> Tuple[bool, str]:
    ok, reason = verify_proof_ledger(value)
    if not ok:
        return False, reason
    ok_checkpoint, reason_checkpoint = verify_ledger_checkpoint_object(checkpoint)
    if not ok_checkpoint:
        return False, reason_checkpoint
    if value["checkpoint"] != checkpoint:
        return False, "PINNED_CHECKPOINT_MISMATCH"
    return True, "PASS"


def compare_proof_ledgers(left: Any, right: Any) -> Dict[str, Any]:
    ok_left, reason_left = verify_proof_ledger(left)
    ok_right, reason_right = verify_proof_ledger(right)
    if not ok_left or not ok_right:
        core = {
            "schema": LEDGER_BRANCH_COMPARISON_SCHEMA,
            "version": VERSION,
            "status": "INVALID_LEDGER_INPUT",
            "left_verification": reason_left,
            "right_verification": reason_right,
        }
        output = dict(core)
        output["comparison_id"] = identity("slang_audit_ledger_branch_comparison_sha256", core)
        return output

    left_genesis = left["genesis_bundle"]["bundle_id"]
    right_genesis = right["genesis_bundle"]["bundle_id"]
    left_ids = [item["entry_id"] for item in left["entries"]]
    right_ids = [item["entry_id"] for item in right["entries"]]
    common = 0
    for a, b in zip(left_ids, right_ids):
        if a != b:
            break
        common += 1
    if left["ledger_id"] == right["ledger_id"]:
        status = "SAME_LINEAGE"
    elif left_genesis != right_genesis:
        status = "DIFFERENT_GENESIS"
    elif common == min(len(left_ids), len(right_ids)):
        status = "PREFIX_EXTENSION"
    else:
        status = "BRANCH_DETECTED"
    branch_point_bundle_id = None
    if left_genesis == right_genesis:
        branch_point_bundle_id = left_genesis if common == 0 else left["entries"][common - 1]["updated_bundle_id"]
    core = {
        "schema": LEDGER_BRANCH_COMPARISON_SCHEMA,
        "version": VERSION,
        "status": status,
        "left_ledger_id": left["ledger_id"],
        "right_ledger_id": right["ledger_id"],
        "common_prefix_entries": common,
        "branch_point_bundle_id": branch_point_bundle_id,
        "left_entry_count": len(left_ids),
        "right_entry_count": len(right_ids),
        "left_terminal_bundle_id": left["terminal_bundle"]["bundle_id"],
        "right_terminal_bundle_id": right["terminal_bundle"]["bundle_id"],
    }
    output = dict(core)
    output["comparison_id"] = identity("slang_audit_ledger_branch_comparison_sha256", core)
    return output


def bind_delta(base_bundle: Dict[str, Any], remove_evidence: Optional[List[str]] = None, upsert_evidence: Optional[List[Dict[str, Any]]] = None, remove_rules: Optional[List[str]] = None, upsert_rules: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    return {
        "schema": DELTA_SCHEMA,
        "base_bundle_id": base_bundle["bundle_id"],
        "remove_evidence": [] if remove_evidence is None else remove_evidence,
        "upsert_evidence": [] if upsert_evidence is None else upsert_evidence,
        "remove_rules": [] if remove_rules is None else remove_rules,
        "upsert_rules": [] if upsert_rules is None else upsert_rules,
    }


def demo_ledger_components() -> Tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
    genesis = resolve_structure(demo_structure())
    deltas: List[Dict[str, Any]] = []
    current = genesis

    d1 = bind_delta(current, remove_evidence=["contracts_ledger"])
    i1 = build_incremental_bundle(current, d1)
    deltas.append(i1["delta"])
    current = i1["updated_bundle"]

    d2 = bind_delta(current, upsert_evidence=[{"id": "contracts_replacement", "claims": {"contracts_supported": True}, "commitment": "sha256:" + "5" * 64}])
    i2 = build_incremental_bundle(current, d2)
    deltas.append(i2["delta"])
    current = i2["updated_bundle"]

    d3 = bind_delta(current, upsert_evidence=[{"id": "counterstatement", "claims": {"reported_profit_supported": False}, "commitment": "sha256:" + "6" * 64}])
    i3 = build_incremental_bundle(current, d3)
    deltas.append(i3["delta"])
    current = i3["updated_bundle"]

    d4 = bind_delta(current, remove_evidence=["counterstatement"])
    i4 = build_incremental_bundle(current, d4)
    deltas.append(i4["delta"])
    current = i4["updated_bundle"]

    sequence = {
        "schema": LEDGER_DELTA_SEQUENCE_SCHEMA,
        "genesis_bundle_id": genesis["bundle_id"],
        "deltas": deltas,
    }
    return genesis, deltas, sequence


def demo_proof_ledger() -> Dict[str, Any]:
    genesis, deltas, _ = demo_ledger_components()
    return build_proof_ledger(genesis, deltas)


def demo_structure() -> Dict[str, Any]:
    return {
        "schema": INPUT_SCHEMA,
        "atoms": [
            "contracts_supported",
            "costs_supported",
            "revenue_supported",
            "expense_supported",
            "profit_bridge_supported",
            "reported_profit_supported",
        ],
        "targets": ["profit_recognition", "reported_profit_alignment"],
        "evidence": [
            {"id": "contracts_ledger", "claims": {"contracts_supported": True}, "commitment": "sha256:" + "1" * 64},
            {"id": "cost_ledger", "claims": {"costs_supported": True}, "commitment": "sha256:" + "2" * 64},
            {"id": "reported_statement", "claims": {"reported_profit_supported": True}, "commitment": "sha256:" + "3" * 64},
            {"id": "profit_bridge", "claims": {"profit_bridge_supported": True}, "commitment": "sha256:" + "4" * 64},
        ],
        "rules": [
            {"id": "derive_revenue_support", "if_all": {"contracts_supported": True}, "then": {"revenue_supported": True}},
            {"id": "derive_expense_support", "if_all": {"costs_supported": True}, "then": {"expense_supported": True}},
        ],
        "controls": [
            {"id": "profit_recognition", "require": {"revenue_supported": True, "expense_supported": True}},
            {"id": "reported_profit_alignment", "require": {"profit_bridge_supported": True, "reported_profit_supported": True}},
        ],
    }


def incomplete_structure() -> Dict[str, Any]:
    raw = demo_structure()
    raw["evidence"] = [item for item in raw["evidence"] if item["id"] != "cost_ledger"]
    return raw


def violated_structure() -> Dict[str, Any]:
    raw = demo_structure()
    for item in raw["evidence"]:
        if item["id"] == "profit_bridge":
            item["claims"] = {"profit_bridge_supported": False}
    return raw


def contradiction_structure() -> Dict[str, Any]:
    raw = demo_structure()
    raw["evidence"].append({"id": "counterstatement", "claims": {"reported_profit_supported": False}, "commitment": None})
    return raw


def irrelevant_contradiction_structure() -> Dict[str, Any]:
    raw = demo_structure()
    raw["atoms"].append("unrelated_flag")
    raw["evidence"].append({"id": "unrelated_a", "claims": {"unrelated_flag": True}, "commitment": None})
    raw["evidence"].append({"id": "unrelated_b", "claims": {"unrelated_flag": False}, "commitment": None})
    return raw


class SelfTest:
    def __init__(self) -> None:
        self.total = 0
        self.passed = 0

    def check(self, condition: bool, name: str) -> None:
        self.total += 1
        if not condition:
            raise AssertionError(name)
        self.passed += 1

    def verify(self, bundle: Dict[str, Any], name: str) -> None:
        ok, reason = verify_bundle(bundle)
        self.check(ok, name + ":" + reason)


def run_self_test() -> int:
    test = SelfTest()

    baseline = resolve_structure(demo_structure())
    test.check(baseline["certificate"]["state"] == STATE_RESOLVED, "baseline_state")
    test.check(
        baseline["certificate"]["resolution"]["verdicts"]
        == {"profit_recognition": VERDICT_PASS, "reported_profit_alignment": VERDICT_PASS},
        "baseline_verdicts",
    )
    test.check(baseline["certificate"]["proof"]["external_truth_verified"] is False, "truth_boundary")
    test.check(baseline["certificate"]["proof"]["replay_performed"] is False, "replay_boundary")
    test.verify(baseline, "baseline_verify")
    test.check(baseline["certificate"]["proof"]["evidence_commitments"]["all_evidence_committed"] is True, "baseline_all_evidence_committed")

    commitment_mutation = demo_structure()
    commitment_mutation["evidence"][0]["commitment"] = "sha256:" + "9" * 64
    commitment_mutation_bundle = resolve_structure(commitment_mutation)
    test.check(commitment_mutation_bundle["certificate"]["resolution"]["verdicts"] == baseline["certificate"]["resolution"]["verdicts"], "commitment_does_not_change_logic")
    test.check(commitment_mutation_bundle["canonical_structure"]["canonical_structure_id"] != baseline["canonical_structure"]["canonical_structure_id"], "commitment_binds_identity")
    test.verify(commitment_mutation_bundle, "commitment_mutation_verify")

    invalid_commitment = demo_structure()
    invalid_commitment["evidence"][0]["commitment"] = "sha256:xyz"
    invalid_commitment_bundle = resolve_structure(invalid_commitment)
    test.check(invalid_commitment_bundle["certificate"]["state"] == STATE_UNSUPPORTED, "invalid_commitment_state")
    test.verify(invalid_commitment_bundle, "invalid_commitment_verify")

    incomplete = resolve_structure(incomplete_structure())
    test.check(incomplete["certificate"]["state"] == STATE_INCOMPLETE, "incomplete_state")
    test.check(incomplete["certificate"]["resolution"]["verdicts"]["profit_recognition"] == VERDICT_INCOMPLETE, "incomplete_target")
    test.verify(incomplete, "incomplete_verify")

    violated = resolve_structure(violated_structure())
    test.check(violated["certificate"]["state"] == STATE_RESOLVED, "violated_resolved_state")
    test.check(violated["certificate"]["resolution"]["verdicts"]["reported_profit_alignment"] == VERDICT_VIOLATED, "violated_target")
    test.verify(violated, "violated_verify")

    contradiction = resolve_structure(contradiction_structure())
    test.check(contradiction["certificate"]["state"] == STATE_ABSTAIN, "contradiction_state")
    test.check(contradiction["certificate"]["resolution"]["verdicts"]["reported_profit_alignment"] == VERDICT_ABSTAIN, "contradiction_target")
    test.verify(contradiction, "contradiction_verify")

    irrelevant = resolve_structure(irrelevant_contradiction_structure())
    test.check(irrelevant["certificate"]["state"] == STATE_RESOLVED, "irrelevant_contradiction_target_specific")
    test.check("unrelated_flag" in irrelevant["certificate"]["proof"]["closure"]["contradictory_atoms"], "irrelevant_contradiction_reported")
    test.verify(irrelevant, "irrelevant_verify")

    reordered = demo_structure()
    reordered["atoms"] = list(reversed(reordered["atoms"]))
    reordered["targets"] = list(reversed(reordered["targets"]))
    reordered["evidence"] = list(reversed(reordered["evidence"]))
    reordered["rules"] = list(reversed(reordered["rules"]))
    reordered["controls"] = list(reversed(reordered["controls"]))
    reordered_bundle = resolve_structure(reordered)
    test.check(reordered_bundle == baseline, "order_independence")

    deterministic_again = resolve_structure(demo_structure())
    test.check(deterministic_again == baseline, "deterministic_repeat")

    cyclic = {
        "schema": INPUT_SCHEMA,
        "atoms": ["a", "b"],
        "targets": ["c1"],
        "evidence": [],
        "rules": [
            {"id": "r1", "if_all": {"a": True}, "then": {"b": True}},
            {"id": "r2", "if_all": {"b": True}, "then": {"a": True}},
        ],
        "controls": [{"id": "c1", "require": {"a": True}}],
    }
    cyclic_bundle = resolve_structure(cyclic)
    test.check(cyclic_bundle["certificate"]["state"] == STATE_INCOMPLETE, "cycle_does_not_self_start")
    test.verify(cyclic_bundle, "cycle_verify")

    derived_conflict = {
        "schema": INPUT_SCHEMA,
        "atoms": ["a", "b", "x"],
        "targets": ["c1"],
        "evidence": [
            {"id": "e1", "claims": {"a": True}, "commitment": None},
            {"id": "e2", "claims": {"b": True}, "commitment": None},
        ],
        "rules": [
            {"id": "r1", "if_all": {"a": True}, "then": {"x": True}},
            {"id": "r2", "if_all": {"b": True}, "then": {"x": False}},
        ],
        "controls": [{"id": "c1", "require": {"x": True}}],
    }
    derived_conflict_bundle = resolve_structure(derived_conflict)
    test.check(derived_conflict_bundle["certificate"]["state"] == STATE_ABSTAIN, "derived_conflict_state")
    test.verify(derived_conflict_bundle, "derived_conflict_verify")

    conflicting_premise = {
        "schema": INPUT_SCHEMA,
        "atoms": ["a", "x"],
        "targets": ["c1"],
        "evidence": [
            {"id": "e1", "claims": {"a": True}, "commitment": None},
            {"id": "e2", "claims": {"a": False}, "commitment": None},
        ],
        "rules": [{"id": "r1", "if_all": {"a": True}, "then": {"x": True}}],
        "controls": [{"id": "c1", "require": {"x": True}}],
    }
    conflicting_premise_bundle = resolve_structure(conflicting_premise)
    test.check(conflicting_premise_bundle["certificate"]["state"] == STATE_INCOMPLETE, "conflicted_premise_does_not_fire")
    test.check("r1" not in [item["rule_id"] for item in conflicting_premise_bundle["certificate"]["proof"]["closure"]["rule_firings"]], "conflicted_premise_no_firing")
    test.verify(conflicting_premise_bundle, "conflicted_premise_verify")

    forbidden = demo_structure()
    forbidden["result"] = {"profit_recognition": "PASS"}
    forbidden_bundle = resolve_structure(forbidden)
    test.check(forbidden_bundle["certificate"]["state"] == STATE_FORBIDDEN, "forbidden_state")
    test.check(forbidden_bundle["certificate"]["reason_codes"] == ["FORBIDDEN_DERIVED_FIELD"], "forbidden_reason")
    test.verify(forbidden_bundle, "forbidden_verify")

    unknown = demo_structure()
    unknown["extra"] = 1
    unknown_bundle = resolve_structure(unknown)
    test.check(unknown_bundle["certificate"]["state"] == STATE_UNSUPPORTED, "unknown_field_state")
    test.verify(unknown_bundle, "unknown_field_verify")

    undeclared_atom = demo_structure()
    undeclared_atom["evidence"][0]["claims"]["ghost"] = True
    undeclared_atom_bundle = resolve_structure(undeclared_atom)
    test.check(undeclared_atom_bundle["certificate"]["state"] == STATE_UNSUPPORTED, "undeclared_atom_state")
    test.verify(undeclared_atom_bundle, "undeclared_atom_verify")

    missing_target = demo_structure()
    missing_target["targets"] = ["ghost_control"]
    missing_target_bundle = resolve_structure(missing_target)
    test.check(missing_target_bundle["certificate"]["state"] == STATE_UNSUPPORTED, "undeclared_target_state")
    test.verify(missing_target_bundle, "undeclared_target_verify")

    bad_boolean = demo_structure()
    bad_boolean["evidence"][0]["claims"]["contracts_supported"] = "true"
    bad_boolean_bundle = resolve_structure(bad_boolean)
    test.check(bad_boolean_bundle["certificate"]["state"] == STATE_UNSUPPORTED, "strict_boolean_state")
    test.verify(bad_boolean_bundle, "strict_boolean_verify")

    duplicate_rule = demo_structure()
    duplicate_rule["rules"].append(json.loads(json.dumps(duplicate_rule["rules"][0])))
    duplicate_rule_bundle = resolve_structure(duplicate_rule)
    test.check(duplicate_rule_bundle["certificate"]["state"] == STATE_UNSUPPORTED, "duplicate_rule_state")
    test.verify(duplicate_rule_bundle, "duplicate_rule_verify")

    self_confirming = demo_structure()
    self_confirming["rules"].append({"id": "bad", "if_all": {"contracts_supported": True}, "then": {"contracts_supported": True}})
    self_confirming_bundle = resolve_structure(self_confirming)
    test.check(self_confirming_bundle["certificate"]["state"] == STATE_UNSUPPORTED, "self_confirming_rule_state")
    test.verify(self_confirming_bundle, "self_confirming_rule_verify")

    tampered_verdict = json.loads(json.dumps(baseline))
    tampered_verdict["certificate"]["resolution"]["verdicts"]["profit_recognition"] = VERDICT_VIOLATED
    ok, _ = verify_bundle(tampered_verdict)
    test.check(not ok, "tampered_verdict_rejected")

    tampered_verdict_rehashed = json.loads(json.dumps(baseline))
    tampered_verdict_rehashed["certificate"]["resolution"]["verdicts"]["profit_recognition"] = VERDICT_VIOLATED
    cert_core = dict(tampered_verdict_rehashed["certificate"])
    cert_core.pop("certificate_id")
    tampered_verdict_rehashed["certificate"]["certificate_id"] = identity("slang_audit_certificate_sha256", cert_core)
    bundle_core = dict(tampered_verdict_rehashed)
    bundle_core.pop("bundle_id")
    tampered_verdict_rehashed["bundle_id"] = identity("slang_audit_bundle_sha256", bundle_core)
    ok, _ = verify_bundle(tampered_verdict_rehashed)
    test.check(not ok, "rehashed_verdict_forgery_rejected")

    tampered_structure = json.loads(json.dumps(baseline))
    tampered_structure["canonical_structure"]["atoms"][0] = "mutated_atom"
    structure_core = dict(tampered_structure["canonical_structure"])
    structure_core.pop("canonical_structure_id")
    tampered_structure["canonical_structure"]["canonical_structure_id"] = identity("slang_audit_structure_sha256", structure_core)
    tampered_structure["certificate"]["canonical_structure_id"] = tampered_structure["canonical_structure"]["canonical_structure_id"]
    cert_core = dict(tampered_structure["certificate"])
    cert_core.pop("certificate_id")
    tampered_structure["certificate"]["certificate_id"] = identity("slang_audit_certificate_sha256", cert_core)
    bundle_core = dict(tampered_structure)
    bundle_core.pop("bundle_id")
    tampered_structure["bundle_id"] = identity("slang_audit_bundle_sha256", bundle_core)
    ok, _ = verify_bundle(tampered_structure)
    test.check(not ok, "rehashed_structure_forgery_rejected")

    transplanted = json.loads(json.dumps(baseline))
    transplanted["certificate"] = json.loads(json.dumps(violated["certificate"]))
    bundle_core = dict(transplanted)
    bundle_core.pop("bundle_id")
    transplanted["bundle_id"] = identity("slang_audit_bundle_sha256", bundle_core)
    ok, _ = verify_bundle(transplanted)
    test.check(not ok, "certificate_transplant_rejected")

    try:
        strict_json_load_text('{"schema":"x","schema":"y"}')
        duplicate_json_rejected = False
    except ValueError:
        duplicate_json_rejected = True
    test.check(duplicate_json_rejected, "duplicate_json_key_rejected")

    try:
        strict_json_load_text('{"x":1.25}')
        float_rejected = False
    except ValueError:
        float_rejected = True
    test.check(float_rejected, "strict_float_rejected")

    baseline_analysis = baseline["certificate"]["proof"]["target_analysis"]
    profit_witness = baseline_analysis["profit_recognition"]["minimal_sufficient_witness"]
    test.check(profit_witness is not None, "profit_witness_available")
    test.check(profit_witness["evidence_sources"] == ["contracts_ledger", "cost_ledger"], "profit_witness_evidence_minimal")
    test.check(profit_witness["rules"] == ["derive_expense_support", "derive_revenue_support"], "profit_witness_rules_minimal")
    test.check(profit_witness["source_count"] == 4, "profit_witness_source_count")
    test.check(profit_witness["reproduced_verdict"] == VERDICT_PASS, "profit_witness_reproduces")
    test.check("profit_bridge" in baseline_analysis["profit_recognition"]["dependency_cone"]["excluded_evidence_sources"], "profit_dependency_excludes_irrelevant_evidence")
    test.check("reported_statement" in baseline_analysis["profit_recognition"]["dependency_cone"]["excluded_evidence_sources"], "profit_dependency_excludes_other_target_evidence")

    irrelevant_added = demo_structure()
    irrelevant_added["atoms"].append("irrelevant_extra")
    irrelevant_added["evidence"].append({"id": "irrelevant_extra_source", "claims": {"irrelevant_extra": True}, "commitment": "sha256:" + "8" * 64})
    irrelevant_added["rules"].append({"id": "irrelevant_extra_rule", "if_all": {"irrelevant_extra": True}, "then": {"irrelevant_extra": False}})
    irrelevant_added_bundle = resolve_structure(irrelevant_added)
    test.check(irrelevant_added_bundle["certificate"]["resolution"]["verdicts"]["profit_recognition"] == VERDICT_PASS, "irrelevant_addition_verdict_invariant")
    added_witness = irrelevant_added_bundle["certificate"]["proof"]["target_analysis"]["profit_recognition"]["minimal_sufficient_witness"]
    test.check(added_witness["witness_id"] == profit_witness["witness_id"], "irrelevant_addition_witness_invariant")
    test.check(added_witness["witness_structure_id"] == profit_witness["witness_structure_id"], "irrelevant_addition_witness_structure_invariant")
    test.verify(irrelevant_added_bundle, "irrelevant_addition_verify")

    necessary_removed = demo_structure()
    necessary_removed["evidence"] = [item for item in necessary_removed["evidence"] if item["id"] != "contracts_ledger"]
    necessary_removed_bundle = resolve_structure(necessary_removed)
    test.check(necessary_removed_bundle["certificate"]["resolution"]["verdicts"]["profit_recognition"] == VERDICT_INCOMPLETE, "necessary_removal_changes_target")
    test.check(necessary_removed_bundle["certificate"]["proof"]["target_analysis"]["profit_recognition"]["minimal_sufficient_witness"] is None, "incomplete_has_no_sufficient_witness")
    test.verify(necessary_removed_bundle, "necessary_removal_verify")

    outside_conflict = demo_structure()
    outside_conflict["atoms"].append("outside_flag")
    outside_conflict["evidence"].append({"id": "outside_true", "claims": {"outside_flag": True}, "commitment": None})
    outside_conflict["evidence"].append({"id": "outside_false", "claims": {"outside_flag": False}, "commitment": None})
    outside_conflict_bundle = resolve_structure(outside_conflict)
    outside_witness = outside_conflict_bundle["certificate"]["proof"]["target_analysis"]["profit_recognition"]["minimal_sufficient_witness"]
    test.check(outside_conflict_bundle["certificate"]["resolution"]["verdicts"]["profit_recognition"] == VERDICT_PASS, "outside_conflict_verdict_isolated")
    test.check(outside_witness["witness_id"] == profit_witness["witness_id"], "outside_conflict_witness_isolated")
    test.verify(outside_conflict_bundle, "outside_conflict_verify")

    inside_conflict = demo_structure()
    inside_conflict["evidence"].append({"id": "contracts_counter", "claims": {"contracts_supported": False}, "commitment": None})
    inside_conflict_bundle = resolve_structure(inside_conflict)
    test.check(inside_conflict_bundle["certificate"]["resolution"]["verdicts"]["profit_recognition"] == VERDICT_INCOMPLETE, "inside_premise_conflict_blocks_derivation")
    test.check(inside_conflict_bundle["certificate"]["proof"]["target_analysis"]["profit_recognition"]["minimal_sufficient_witness"] is None, "inside_premise_conflict_no_pass_witness")
    test.verify(inside_conflict_bundle, "inside_premise_conflict_verify")

    direct_target_conflict = demo_structure()
    direct_target_conflict["evidence"].append({"id": "revenue_counter", "claims": {"revenue_supported": False}, "commitment": None})
    direct_target_conflict_bundle = resolve_structure(direct_target_conflict)
    conflict_witness = direct_target_conflict_bundle["certificate"]["proof"]["target_analysis"]["profit_recognition"]["minimal_sufficient_witness"]
    test.check(direct_target_conflict_bundle["certificate"]["resolution"]["verdicts"]["profit_recognition"] == VERDICT_ABSTAIN, "inside_target_conflict_abstains")
    test.check(conflict_witness is not None and conflict_witness["reproduced_verdict"] == VERDICT_ABSTAIN, "abstain_witness_reproduces")
    test.verify(direct_target_conflict_bundle, "inside_target_conflict_verify")

    alternative_paths = {
        "schema": INPUT_SCHEMA,
        "atoms": ["a", "b", "x"],
        "targets": ["c1"],
        "evidence": [
            {"id": "e_a", "claims": {"a": True}, "commitment": None},
            {"id": "e_b", "claims": {"b": True}, "commitment": None},
        ],
        "rules": [
            {"id": "r_a", "if_all": {"a": True}, "then": {"x": True}},
            {"id": "r_b", "if_all": {"b": True}, "then": {"x": True}},
        ],
        "controls": [{"id": "c1", "require": {"x": True}}],
    }
    alternative_bundle = resolve_structure(alternative_paths)
    alternative_witness = alternative_bundle["certificate"]["proof"]["target_analysis"]["c1"]["minimal_sufficient_witness"]
    test.check(alternative_witness["evidence_sources"] == ["e_a"], "alternative_path_canonical_evidence")
    test.check(alternative_witness["rules"] == ["r_a"], "alternative_path_canonical_rule")
    test.check(alternative_witness["source_count"] == 2, "alternative_path_minimal_count")
    test.verify(alternative_bundle, "alternative_path_verify")

    alternative_reordered = json.loads(json.dumps(alternative_paths))
    alternative_reordered["evidence"] = list(reversed(alternative_reordered["evidence"]))
    alternative_reordered["rules"] = list(reversed(alternative_reordered["rules"]))
    alternative_reordered_bundle = resolve_structure(alternative_reordered)
    alternative_reordered_witness = alternative_reordered_bundle["certificate"]["proof"]["target_analysis"]["c1"]["minimal_sufficient_witness"]
    test.check(alternative_reordered_witness["witness_id"] == alternative_witness["witness_id"], "alternative_path_order_independent")
    test.verify(alternative_reordered_bundle, "alternative_reordered_verify")

    direct_beats_derived = json.loads(json.dumps(alternative_paths))
    direct_beats_derived["evidence"].append({"id": "e_direct", "claims": {"x": True}, "commitment": None})
    direct_bundle = resolve_structure(direct_beats_derived)
    direct_witness = direct_bundle["certificate"]["proof"]["target_analysis"]["c1"]["minimal_sufficient_witness"]
    test.check(direct_witness["evidence_sources"] == ["e_direct"], "direct_path_beats_derived")
    test.check(direct_witness["rules"] == [], "direct_path_no_rule")
    test.check(direct_witness["source_count"] == 1, "direct_path_minimal_count")
    test.verify(direct_bundle, "direct_path_verify")

    shared_source = {
        "schema": INPUT_SCHEMA,
        "atoms": ["p", "q"],
        "targets": ["c1"],
        "evidence": [
            {"id": "e_p", "claims": {"p": True}, "commitment": None},
            {"id": "e_q", "claims": {"q": True}, "commitment": None},
            {"id": "e_shared", "claims": {"p": True, "q": True}, "commitment": None},
        ],
        "rules": [],
        "controls": [{"id": "c1", "require": {"p": True, "q": True}}],
    }
    shared_bundle = resolve_structure(shared_source)
    shared_witness = shared_bundle["certificate"]["proof"]["target_analysis"]["c1"]["minimal_sufficient_witness"]
    test.check(shared_witness["evidence_sources"] == ["e_shared"], "shared_source_union_minimality")
    test.check(shared_witness["source_count"] == 1, "shared_source_count")
    test.verify(shared_bundle, "shared_source_verify")

    violated_witness = violated["certificate"]["proof"]["target_analysis"]["reported_profit_alignment"]["minimal_sufficient_witness"]
    test.check(violated_witness is not None and violated_witness["verdict"] == VERDICT_VIOLATED, "violated_witness_available")
    test.check(violated_witness["evidence_sources"] == ["profit_bridge"], "violated_witness_minimal")

    contradiction_witness = contradiction["certificate"]["proof"]["target_analysis"]["reported_profit_alignment"]["minimal_sufficient_witness"]
    test.check(contradiction_witness is not None and contradiction_witness["verdict"] == VERDICT_ABSTAIN, "contradiction_witness_available")
    test.check(set(contradiction_witness["evidence_sources"]) == {"counterstatement", "reported_statement"}, "contradiction_witness_minimal_pair")


    baseline_cf = baseline["certificate"]["proof"]["target_analysis"]["profit_recognition"]["counterfactual_analysis"]
    baseline_cut = baseline_cf["minimal_verdict_cut"]
    test.check(baseline_cut["status"] == "AVAILABLE", "baseline_cut_available")
    test.check(baseline_cut["minimal_change_count"] == 1, "baseline_cut_size_one")
    test.check(baseline_cut["selected"]["counterfactual_verdict"] == VERDICT_INCOMPLETE, "baseline_cut_changes_to_incomplete")
    test.check(baseline_cut["selected"]["removed_evidence_sources"] == ["contracts_ledger"], "baseline_cut_canonical_contracts")
    test.check(baseline_cf["minimal_repair_to_pass"]["status"] == "NOT_APPLICABLE_ALREADY_PASS", "baseline_repair_not_applicable")

    incomplete_cf = incomplete["certificate"]["proof"]["target_analysis"]["profit_recognition"]["counterfactual_analysis"]
    completion = incomplete_cf["completion_frontier"]
    test.check(completion["status"] == "AVAILABLE", "incomplete_completion_available")
    test.check(completion["minimal_change_count"] == 1, "incomplete_completion_one_literal")
    test.check(completion["selected"]["counterfactual_verdict"] == VERDICT_PASS, "incomplete_completion_reaches_pass")
    test.check(completion["selected"]["added_literals"] == ["costs_supported=true"], "incomplete_completion_canonical_literal")
    test.check(incomplete_cf["minimal_repair_to_pass"]["status"] == "AVAILABLE", "incomplete_repair_available")
    test.check(incomplete_cf["minimal_repair_to_pass"]["minimal_change_count"] == 1, "incomplete_repair_one_change")

    violated_cf = violated["certificate"]["proof"]["target_analysis"]["reported_profit_alignment"]["counterfactual_analysis"]
    test.check(violated_cf["minimal_verdict_cut"]["status"] == "AVAILABLE", "violated_cut_available")
    test.check(violated_cf["minimal_verdict_cut"]["selected"]["removed_evidence_sources"] == ["profit_bridge"], "violated_blocker_cut")
    test.check(violated_cf["minimal_verdict_cut"]["selected"]["counterfactual_verdict"] == VERDICT_INCOMPLETE, "violated_cut_to_incomplete")
    violated_repair = violated_cf["minimal_repair_to_pass"]
    test.check(violated_repair["status"] == "AVAILABLE", "violated_repair_available")
    test.check(violated_repair["minimal_change_count"] == 2, "violated_repair_two_changes")
    test.check(violated_repair["selected"]["removed_evidence_sources"] == ["profit_bridge"], "violated_repair_removes_blocker")
    test.check(violated_repair["selected"]["added_literals"] == ["profit_bridge_supported=true"], "violated_repair_adds_required")
    test.check(violated_repair["selected"]["counterfactual_verdict"] == VERDICT_PASS, "violated_repair_reaches_pass")

    contradiction_cf = contradiction["certificate"]["proof"]["target_analysis"]["reported_profit_alignment"]["counterfactual_analysis"]
    test.check(contradiction_cf["minimal_verdict_cut"]["status"] == "AVAILABLE", "abstain_cut_available")
    test.check(contradiction_cf["minimal_verdict_cut"]["minimal_change_count"] == 1, "abstain_cut_one_change")
    abstain_repair = contradiction_cf["minimal_repair_to_pass"]
    test.check(abstain_repair["status"] == "AVAILABLE", "abstain_repair_available")
    test.check(abstain_repair["minimal_change_count"] == 1, "abstain_repair_one_change")
    test.check(abstain_repair["selected"]["removed_evidence_sources"] == ["counterstatement"], "abstain_repair_removes_counterstatement")
    test.check(abstain_repair["selected"]["added_literals"] == [], "abstain_repair_no_addition")
    test.check(abstain_repair["selected"]["counterfactual_verdict"] == VERDICT_PASS, "abstain_repair_reaches_pass")

    irrelevant_cf = irrelevant["certificate"]["proof"]["target_analysis"]["profit_recognition"]["counterfactual_analysis"]
    test.check(irrelevant_cf["minimal_verdict_cut"]["selected"]["cut_id"] == baseline_cut["selected"]["cut_id"], "irrelevant_conflict_cut_invariant")

    reordered_cf = reordered_bundle["certificate"]["proof"]["target_analysis"]["profit_recognition"]["counterfactual_analysis"]
    test.check(reordered_cf == baseline_cf, "counterfactual_order_independence")

    tampered_counterfactual = json.loads(json.dumps(baseline))
    tampered_counterfactual["certificate"]["proof"]["target_analysis"]["profit_recognition"]["counterfactual_analysis"]["minimal_verdict_cut"]["selected"]["removed_evidence_sources"] = ["profit_bridge"]
    cert_core = dict(tampered_counterfactual["certificate"])
    cert_core.pop("certificate_id")
    tampered_counterfactual["certificate"]["certificate_id"] = identity("slang_audit_certificate_sha256", cert_core)
    bundle_core = dict(tampered_counterfactual)
    bundle_core.pop("bundle_id")
    tampered_counterfactual["bundle_id"] = identity("slang_audit_bundle_sha256", bundle_core)
    ok, _ = verify_bundle(tampered_counterfactual)
    test.check(not ok, "rehashed_counterfactual_forgery_rejected")

    tampered_witness = json.loads(json.dumps(baseline))
    tampered_witness["certificate"]["proof"]["target_analysis"]["profit_recognition"]["minimal_sufficient_witness"]["evidence_sources"] = ["profit_bridge"]
    cert_core = dict(tampered_witness["certificate"])
    cert_core.pop("certificate_id")
    tampered_witness["certificate"]["certificate_id"] = identity("slang_audit_certificate_sha256", cert_core)
    bundle_core = dict(tampered_witness)
    bundle_core.pop("bundle_id")
    tampered_witness["bundle_id"] = identity("slang_audit_bundle_sha256", bundle_core)
    ok, _ = verify_bundle(tampered_witness)
    test.check(not ok, "rehashed_witness_forgery_rejected")

    incremental_delta = incremental_demo_delta(baseline)
    incremental = build_incremental_bundle(baseline, incremental_delta)
    ok_incremental, reason_incremental = verify_incremental_bundle(incremental)
    test.check(ok_incremental, "incremental_verify:" + reason_incremental)
    delta_certificate = incremental["delta_certificate"]
    test.check(delta_certificate["dependency_impacted_targets"] == ["profit_recognition"], "incremental_impacted_target")
    test.check(delta_certificate["proof_changed_targets"] == ["profit_recognition"], "incremental_changed_proof_target")
    test.check(delta_certificate["preserved_targets"] == ["reported_profit_alignment"], "incremental_preserved_target")
    test.check(delta_certificate["transitions"]["profit_recognition"]["from"] == VERDICT_PASS, "incremental_transition_from_pass")
    test.check(delta_certificate["transitions"]["profit_recognition"]["to"] == VERDICT_INCOMPLETE, "incremental_transition_to_incomplete")
    test.check(delta_certificate["preserved_target_proof_ids"]["reported_profit_alignment"] == baseline["certificate"]["proof"]["target_proof_ids"]["reported_profit_alignment"], "incremental_preserved_proof_id")
    test.check(incremental["updated_bundle"]["certificate"]["resolution"]["verdicts"]["profit_recognition"] == VERDICT_INCOMPLETE, "incremental_updated_bundle_verdict")
    test.check(delta_certificate["full_recomputation_equivalence"] is True, "incremental_full_equivalence")

    unrelated_delta = {
        "schema": DELTA_SCHEMA,
        "base_bundle_id": baseline["bundle_id"],
        "remove_evidence": [],
        "upsert_evidence": [{"id": "reported_statement_2", "claims": {"reported_profit_supported": True}, "commitment": None}],
        "remove_rules": [],
        "upsert_rules": [],
    }
    unrelated_incremental = build_incremental_bundle(baseline, unrelated_delta)
    unrelated_dc = unrelated_incremental["delta_certificate"]
    test.check(unrelated_dc["dependency_impacted_targets"] == ["reported_profit_alignment"], "unrelated_delta_impacted_other_target")
    test.check("profit_recognition" in unrelated_dc["preserved_targets"], "unrelated_delta_preserves_profit_target")
    test.check(unrelated_dc["preserved_target_proof_ids"]["profit_recognition"] == baseline["certificate"]["proof"]["target_proof_ids"]["profit_recognition"], "unrelated_delta_profit_proof_identity")
    ok_unrelated, _ = verify_incremental_bundle(unrelated_incremental)
    test.check(ok_unrelated, "unrelated_incremental_verify")

    commitment_delta = {
        "schema": DELTA_SCHEMA,
        "base_bundle_id": baseline["bundle_id"],
        "remove_evidence": [],
        "upsert_evidence": [{"id": "contracts_ledger", "claims": {"contracts_supported": True}, "commitment": "sha256:" + "9" * 64}],
        "remove_rules": [],
        "upsert_rules": [],
    }
    commitment_incremental = build_incremental_bundle(baseline, commitment_delta)
    test.check(commitment_incremental["delta_certificate"]["dependency_impacted_targets"] == ["profit_recognition"], "commitment_delta_dependency_scope")
    test.check(commitment_incremental["delta_certificate"]["transitions"]["profit_recognition"]["to"] == VERDICT_PASS, "commitment_delta_logic_stable")
    test.check(commitment_incremental["delta_certificate"]["transitions"]["profit_recognition"]["proof_changed"] is True, "commitment_delta_proof_changes")
    ok_commitment_inc, _ = verify_incremental_bundle(commitment_incremental)
    test.check(ok_commitment_inc, "commitment_incremental_verify")

    rule_delta = {
        "schema": DELTA_SCHEMA,
        "base_bundle_id": baseline["bundle_id"],
        "remove_evidence": [],
        "upsert_evidence": [],
        "remove_rules": ["derive_revenue_support"],
        "upsert_rules": [],
    }
    rule_incremental = build_incremental_bundle(baseline, rule_delta)
    test.check(rule_incremental["delta_certificate"]["dependency_impacted_targets"] == ["profit_recognition"], "rule_delta_scope")
    test.check(rule_incremental["delta_certificate"]["transitions"]["profit_recognition"]["to"] == VERDICT_INCOMPLETE, "rule_delta_transition")
    ok_rule_inc, _ = verify_incremental_bundle(rule_incremental)
    test.check(ok_rule_inc, "rule_incremental_verify")

    bad_binding = dict(incremental_delta)
    bad_binding["base_bundle_id"] = "slang_audit_bundle_sha256:" + "0" * 64
    try:
        build_incremental_bundle(baseline, bad_binding)
        bad_binding_rejected = False
    except StructuralError:
        bad_binding_rejected = True
    test.check(bad_binding_rejected, "delta_base_binding_rejected")

    tampered_incremental = json.loads(json.dumps(incremental))
    tampered_incremental["delta_certificate"]["preserved_targets"] = ["profit_recognition", "reported_profit_alignment"]
    dc_core = dict(tampered_incremental["delta_certificate"])
    dc_core.pop("delta_certificate_id")
    tampered_incremental["delta_certificate"]["delta_certificate_id"] = identity("slang_audit_delta_certificate_sha256", dc_core)
    ib_core = dict(tampered_incremental)
    ib_core.pop("incremental_bundle_id")
    tampered_incremental["incremental_bundle_id"] = identity("slang_audit_incremental_bundle_sha256", ib_core)
    ok_tampered_incremental, _ = verify_incremental_bundle(tampered_incremental)
    test.check(not ok_tampered_incremental, "rehashed_incremental_forgery_rejected")

    ledger = demo_proof_ledger()
    ok_ledger, reason_ledger = verify_proof_ledger(ledger)
    test.check(ok_ledger, "ledger_verify:" + reason_ledger)
    test.check(len(ledger["entries"]) == 4, "ledger_entry_count")
    test.check(ledger["entries"][0]["predecessor_entry_id"] is None, "ledger_genesis_predecessor")
    test.check(ledger["entries"][1]["predecessor_entry_id"] == ledger["entries"][0]["entry_id"], "ledger_predecessor_binding")
    test.check(ledger["entries"][0]["transitions"]["profit_recognition"]["to"] == VERDICT_INCOMPLETE, "ledger_transition_1")
    test.check(ledger["entries"][1]["transitions"]["profit_recognition"]["to"] == VERDICT_PASS, "ledger_transition_2")
    test.check(ledger["entries"][2]["transitions"]["reported_profit_alignment"]["to"] == VERDICT_ABSTAIN, "ledger_transition_3")
    test.check(ledger["entries"][3]["transitions"]["reported_profit_alignment"]["to"] == VERDICT_PASS, "ledger_transition_4")
    test.check(ledger["terminal_bundle"]["certificate"]["resolution"]["verdicts"] == {"profit_recognition": VERDICT_PASS, "reported_profit_alignment": VERDICT_PASS}, "ledger_terminal_verdicts")
    ok_checkpoint, reason_checkpoint = verify_proof_ledger_against_checkpoint(ledger, ledger["checkpoint"])
    test.check(ok_checkpoint, "ledger_checkpoint_verify:" + reason_checkpoint)

    deleted = json.loads(json.dumps(ledger))
    deleted["entries"].pop(1)
    deleted_core = dict(deleted)
    deleted_core.pop("ledger_id")
    deleted["ledger_id"] = identity("slang_audit_proof_ledger_sha256", deleted_core)
    ok_deleted, _ = verify_proof_ledger(deleted)
    test.check(not ok_deleted, "ledger_deletion_rejected")

    reordered_ledger = json.loads(json.dumps(ledger))
    reordered_ledger["entries"][1], reordered_ledger["entries"][2] = reordered_ledger["entries"][2], reordered_ledger["entries"][1]
    reordered_core = dict(reordered_ledger)
    reordered_core.pop("ledger_id")
    reordered_ledger["ledger_id"] = identity("slang_audit_proof_ledger_sha256", reordered_core)
    ok_reordered_ledger, _ = verify_proof_ledger(reordered_ledger)
    test.check(not ok_reordered_ledger, "ledger_reorder_rejected")

    tampered_entry = json.loads(json.dumps(ledger))
    tampered_entry["entries"][0]["preserved_targets"] = []
    entry_core = dict(tampered_entry["entries"][0])
    entry_core.pop("entry_id")
    tampered_entry["entries"][0]["entry_id"] = identity("slang_audit_ledger_entry_sha256", entry_core)
    tampered_core = dict(tampered_entry)
    tampered_core.pop("ledger_id")
    tampered_entry["ledger_id"] = identity("slang_audit_proof_ledger_sha256", tampered_core)
    ok_tampered_entry, _ = verify_proof_ledger(tampered_entry)
    test.check(not ok_tampered_entry, "ledger_rehashed_entry_forgery_rejected")

    genesis, _, _ = demo_ledger_components()
    current = genesis
    alt_deltas: List[Dict[str, Any]] = []
    a1 = bind_delta(current, remove_evidence=["contracts_ledger"], upsert_evidence=[{"id": "contracts_replacement", "claims": {"contracts_supported": True}, "commitment": "sha256:" + "5" * 64}])
    ai1 = build_incremental_bundle(current, a1)
    alt_deltas.append(ai1["delta"])
    current = ai1["updated_bundle"]
    a2 = bind_delta(current, upsert_evidence=[{"id": "counterstatement", "claims": {"reported_profit_supported": False}, "commitment": "sha256:" + "6" * 64}])
    ai2 = build_incremental_bundle(current, a2)
    alt_deltas.append(ai2["delta"])
    current = ai2["updated_bundle"]
    a3 = bind_delta(current, remove_evidence=["counterstatement"])
    ai3 = build_incremental_bundle(current, a3)
    alt_deltas.append(ai3["delta"])
    alternative = build_proof_ledger(genesis, alt_deltas)
    ok_alt, _ = verify_proof_ledger(alternative)
    test.check(ok_alt, "alternative_history_internally_valid")
    test.check(alternative["terminal_bundle"]["bundle_id"] == ledger["terminal_bundle"]["bundle_id"], "alternative_history_same_terminal")
    test.check(alternative["checkpoint"]["checkpoint_id"] != ledger["checkpoint"]["checkpoint_id"], "alternative_history_checkpoint_differs")
    ok_alt_checkpoint, _ = verify_proof_ledger_against_checkpoint(alternative, ledger["checkpoint"])
    test.check(not ok_alt_checkpoint, "alternative_history_rejected_by_pinned_checkpoint")
    comparison = compare_proof_ledgers(ledger, alternative)
    test.check(comparison["status"] == "BRANCH_DETECTED", "alternative_history_branch_detected")

    prefix = build_proof_ledger(genesis, [ledger["entries"][0]["delta"], ledger["entries"][1]["delta"]])
    prefix_comparison = compare_proof_ledgers(prefix, ledger)
    test.check(prefix_comparison["status"] == "PREFIX_EXTENSION", "ledger_prefix_extension")

    branch_current = ledger["genesis_bundle"]
    b1 = build_incremental_bundle(branch_current, ledger["entries"][0]["delta"])
    branch_current = b1["updated_bundle"]
    b2 = bind_delta(branch_current, upsert_evidence=[{"id": "contracts_branch", "claims": {"contracts_supported": True}, "commitment": "sha256:" + "7" * 64}])
    b2i = build_incremental_bundle(branch_current, b2)
    branch = build_proof_ledger(genesis, [b1["delta"], b2i["delta"]])
    branch_comparison = compare_proof_ledgers(ledger, branch)
    test.check(branch_comparison["status"] == "BRANCH_DETECTED", "ledger_common_prefix_branch_detected")
    test.check(branch_comparison["common_prefix_entries"] == 1, "ledger_common_prefix_count")

    print("SLANG-Audit v{} self-test".format(VERSION))
    print("TOTAL {}/{} {}".format(test.passed, test.total, "PASS" if test.passed == test.total else "FAIL"))
    return 0 if test.passed == test.total else 1


def run_demo() -> int:
    bundle = resolve_structure(demo_structure())
    ok, reason = verify_bundle(bundle)
    certificate = bundle["certificate"]
    print("SLANG-Audit v{}".format(VERSION))
    print("scope:DECLARED_STRUCTURE_ONLY_NOT_AUDIT_OPINION")
    print("Core relation:")
    print("declared audit evidence + structural rules + controls -> deterministic closure -> bounded control verdicts -> portable certificate")
    print()
    print("state:" + certificate["state"])
    print("verdicts:" + canonical_json(certificate["resolution"]["verdicts"]))
    print("canonical_structure_id:" + bundle["canonical_structure"]["canonical_structure_id"])
    print("certificate_id:" + certificate["certificate_id"])
    print("bundle_id:" + bundle["bundle_id"])
    print("verification:" + ("PASS" if ok else "FAIL:" + reason))
    primary_target = sorted(certificate["resolution"]["targets"].keys())[0]
    primary_witness = certificate["proof"]["target_analysis"][primary_target]["minimal_sufficient_witness"]
    if primary_witness is not None:
        print("minimal_witness_target:" + primary_target)
        print("minimal_witness_sources:" + canonical_json({"evidence": primary_witness["evidence_sources"], "rules": primary_witness["rules"]}))
        print("minimal_witness_structure_id:" + primary_witness["witness_structure_id"])
        print("minimal_witness_id:" + primary_witness["witness_id"])
    primary_counterfactual = certificate["proof"]["target_analysis"][primary_target]["counterfactual_analysis"]
    cut = primary_counterfactual["minimal_verdict_cut"]
    if cut.get("status") == "AVAILABLE":
        print("minimal_verdict_cut:" + canonical_json(cut["selected"]))
    repair = primary_counterfactual["minimal_repair_to_pass"]
    print("minimal_repair_to_pass_status:" + repair["status"])
    ledger = demo_proof_ledger()
    ok_ledger, reason_ledger = verify_proof_ledger(ledger)
    ok_checkpoint, reason_checkpoint = verify_proof_ledger_against_checkpoint(ledger, ledger["checkpoint"])
    print("proof_ledger_entries:" + str(len(ledger["entries"])))
    print("proof_ledger_id:" + ledger["ledger_id"])
    print("proof_ledger_checkpoint_id:" + ledger["checkpoint"]["checkpoint_id"])
    print("proof_ledger_verification:" + ("PASS" if ok_ledger else "FAIL:" + reason_ledger))
    print("checkpoint_verification:" + ("PASS" if ok_checkpoint else "FAIL:" + reason_checkpoint))
    print("external_truth_verified:false")
    print("external_source_provenance_verified:false")
    print("replay_performed:false")
    print("reconciliation_performed:false")
    print("audit_opinion_authority:NONE")
    return 0 if ok else 1


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SLANG-Audit proof-carrying declared-evidence structural audit resolver")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--demo", action="store_true")
    group.add_argument("--self-test", action="store_true")
    group.add_argument("--resolve", metavar="INPUT_JSON")
    group.add_argument("--verify", metavar="BUNDLE_JSON")
    group.add_argument("--incremental", nargs=2, metavar=("BASE_BUNDLE_JSON", "DELTA_JSON"))
    group.add_argument("--verify-incremental", metavar="INCREMENTAL_BUNDLE_JSON")
    group.add_argument("--ledger", nargs=2, metavar=("GENESIS_BUNDLE_JSON", "DELTA_SEQUENCE_JSON"))
    group.add_argument("--verify-ledger", metavar="LEDGER_JSON")
    group.add_argument("--verify-ledger-checkpoint", nargs=2, metavar=("LEDGER_JSON", "CHECKPOINT_JSON"))
    group.add_argument("--compare-ledgers", nargs=2, metavar=("LEFT_LEDGER_JSON", "RIGHT_LEDGER_JSON"))
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def print_json(value: Any, pretty: bool) -> None:
    if pretty:
        print(json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False))
    else:
        print(canonical_json(value))


def main(argv: Optional[Sequence[str]] = None) -> int:
    if sys.version_info < MINIMUM_PYTHON_VERSION:
        print("Python 3.9 or newer is required.", file=sys.stderr)
        return 2
    args = parse_args(argv)
    if args.self_test:
        return run_self_test()
    if args.resolve:
        print("NOTE: structural resolution only - not an audit opinion", file=sys.stderr)
        try:
            raw = load_json_file(args.resolve)
        except (OSError, ValueError) as error:
            print("INPUT_ERROR:" + str(error), file=sys.stderr)
            return 2
        print_json(resolve_structure(raw), args.pretty)
        return 0
    if args.verify:
        try:
            bundle = load_json_file(args.verify)
        except (OSError, ValueError) as error:
            print("INPUT_ERROR:" + str(error), file=sys.stderr)
            return 2
        ok, reason = verify_bundle(bundle)
        print("PASS" if ok else "FAIL:" + reason)
        return 0 if ok else 1
    if args.incremental:
        try:
            base_bundle = load_json_file(args.incremental[0])
            delta = load_json_file(args.incremental[1])
            output = build_incremental_bundle(base_bundle, delta)
        except (OSError, ValueError, StructuralError) as error:
            code = error.code if isinstance(error, StructuralError) else str(error)
            print("INPUT_ERROR:" + code, file=sys.stderr)
            return 2
        print_json(output, args.pretty)
        return 0
    if args.verify_incremental:
        try:
            value = load_json_file(args.verify_incremental)
        except (OSError, ValueError) as error:
            print("INPUT_ERROR:" + str(error), file=sys.stderr)
            return 2
        ok, reason = verify_incremental_bundle(value)
        print("PASS" if ok else "FAIL:" + reason)
        return 0 if ok else 1
    if args.ledger:
        try:
            genesis_bundle = load_json_file(args.ledger[0])
            sequence = load_json_file(args.ledger[1])
            output = build_proof_ledger_from_sequence(genesis_bundle, sequence)
        except (OSError, ValueError, StructuralError) as error:
            code = error.code if isinstance(error, StructuralError) else str(error)
            print("INPUT_ERROR:" + code, file=sys.stderr)
            return 2
        print_json(output, args.pretty)
        return 0
    if args.verify_ledger:
        try:
            ledger = load_json_file(args.verify_ledger)
        except (OSError, ValueError) as error:
            print("INPUT_ERROR:" + str(error), file=sys.stderr)
            return 2
        ok, reason = verify_proof_ledger(ledger)
        print("PASS" if ok else "FAIL:" + reason)
        return 0 if ok else 1
    if args.verify_ledger_checkpoint:
        try:
            ledger = load_json_file(args.verify_ledger_checkpoint[0])
            checkpoint = load_json_file(args.verify_ledger_checkpoint[1])
        except (OSError, ValueError) as error:
            print("INPUT_ERROR:" + str(error), file=sys.stderr)
            return 2
        ok, reason = verify_proof_ledger_against_checkpoint(ledger, checkpoint)
        print("PASS" if ok else "FAIL:" + reason)
        return 0 if ok else 1
    if args.compare_ledgers:
        try:
            left = load_json_file(args.compare_ledgers[0])
            right = load_json_file(args.compare_ledgers[1])
        except (OSError, ValueError) as error:
            print("INPUT_ERROR:" + str(error), file=sys.stderr)
            return 2
        print_json(compare_proof_ledgers(left, right), args.pretty)
        return 0
    return run_demo()


if __name__ == "__main__":
    raise SystemExit(main())

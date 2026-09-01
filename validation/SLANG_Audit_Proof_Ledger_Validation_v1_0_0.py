#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Shunyaya Framework contributors.

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

VERSION = "1.0.0"
RESOLVER_FILENAME = "../core/SLANG_Audit_Reference_Resolver_v2_4_0.py"
RESOLVER_VERSION = "2.4.0"
RESOLVER_SHA256 = "a3376eb81b7e9ca625f4839fefc4cfbeda227f515109c80450c6a6bd7d7edf98"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_resolver():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), RESOLVER_FILENAME)
    if not os.path.exists(path):
        raise RuntimeError("RESOLVER_NOT_FOUND")
    if sha256_file(path) != RESOLVER_SHA256:
        raise RuntimeError("RESOLVER_SHA256_MISMATCH")
    spec = importlib.util.spec_from_file_location("slang_audit_v240", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("RESOLVER_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.VERSION != RESOLVER_VERSION:
        raise RuntimeError("RESOLVER_VERSION_MISMATCH")
    return module


class Test:
    def __init__(self) -> None:
        self.total = 0
        self.passed = 0

    def check(self, condition: bool, name: str) -> None:
        self.total += 1
        if not condition:
            raise AssertionError(name)
        self.passed += 1


def build_alternative_same_terminal(r, genesis: Dict[str, Any]) -> Dict[str, Any]:
    current = genesis
    deltas: List[Dict[str, Any]] = []
    d1 = r.bind_delta(
        current,
        remove_evidence=["contracts_ledger"],
        upsert_evidence=[{"id": "contracts_replacement", "claims": {"contracts_supported": True}, "commitment": "sha256:" + "5" * 64}],
    )
    i1 = r.build_incremental_bundle(current, d1)
    deltas.append(i1["delta"])
    current = i1["updated_bundle"]
    d2 = r.bind_delta(current, upsert_evidence=[{"id": "counterstatement", "claims": {"reported_profit_supported": False}, "commitment": "sha256:" + "6" * 64}])
    i2 = r.build_incremental_bundle(current, d2)
    deltas.append(i2["delta"])
    current = i2["updated_bundle"]
    d3 = r.bind_delta(current, remove_evidence=["counterstatement"])
    i3 = r.build_incremental_bundle(current, d3)
    deltas.append(i3["delta"])
    return r.build_proof_ledger(genesis, deltas)


def build_common_prefix_branch(r, ledger: Dict[str, Any]) -> Dict[str, Any]:
    genesis = ledger["genesis_bundle"]
    first = r.build_incremental_bundle(genesis, ledger["entries"][0]["delta"])
    current = first["updated_bundle"]
    branch_delta = r.bind_delta(current, upsert_evidence=[{"id": "contracts_branch", "claims": {"contracts_supported": True}, "commitment": "sha256:" + "7" * 64}])
    second = r.build_incremental_bundle(current, branch_delta)
    return r.build_proof_ledger(genesis, [first["delta"], second["delta"]])


def rehash_ledger(r, ledger: Dict[str, Any]) -> None:
    core = dict(ledger)
    core.pop("ledger_id", None)
    ledger["ledger_id"] = r.identity("slang_audit_proof_ledger_sha256", core)


def run_checks(r) -> Tuple[Test, Dict[str, Any]]:
    test = Test()
    ledger = r.demo_proof_ledger()
    genesis = ledger["genesis_bundle"]
    checkpoint = ledger["checkpoint"]

    ok, reason = r.verify_proof_ledger(ledger)
    test.check(ok, "valid_ledger:" + reason)
    ok_cp, reason_cp = r.verify_proof_ledger_against_checkpoint(ledger, checkpoint)
    test.check(ok_cp, "valid_checkpoint:" + reason_cp)
    test.check(len(ledger["entries"]) == 4, "entry_count")
    test.check(ledger["checkpoint"]["entry_count"] == 4, "checkpoint_entry_count")
    test.check(ledger["checkpoint"]["last_entry_id"] == ledger["entries"][-1]["entry_id"], "checkpoint_last_entry")
    test.check(ledger["checkpoint"]["terminal_bundle_id"] == ledger["terminal_bundle"]["bundle_id"], "checkpoint_terminal_binding")
    test.check(ledger["entries"][0]["predecessor_entry_id"] is None, "first_predecessor")
    test.check(ledger["entries"][1]["predecessor_entry_id"] == ledger["entries"][0]["entry_id"], "second_predecessor")
    test.check(ledger["entries"][2]["predecessor_entry_id"] == ledger["entries"][1]["entry_id"], "third_predecessor")
    test.check(ledger["entries"][3]["predecessor_entry_id"] == ledger["entries"][2]["entry_id"], "fourth_predecessor")

    transitions = [
        ("profit_recognition", "PASS", "INCOMPLETE"),
        ("profit_recognition", "INCOMPLETE", "PASS"),
        ("reported_profit_alignment", "PASS", "ABSTAIN"),
        ("reported_profit_alignment", "ABSTAIN", "PASS"),
    ]
    for index, (target, before, after) in enumerate(transitions):
        item = ledger["entries"][index]["transitions"][target]
        test.check(item["from"] == before, "transition_{}_from".format(index + 1))
        test.check(item["to"] == after, "transition_{}_to".format(index + 1))

    current = genesis
    for index, entry in enumerate(ledger["entries"]):
        inc = r.build_incremental_bundle(current, entry["delta"])
        test.check(inc["updated_bundle"]["bundle_id"] == entry["updated_bundle_id"], "fresh_step_{}_bundle".format(index + 1))
        current = inc["updated_bundle"]
    test.check(current == ledger["terminal_bundle"], "terminal_full_recomputation_equality")

    deleted = json.loads(json.dumps(ledger))
    deleted["entries"].pop(1)
    rehash_ledger(r, deleted)
    ok_deleted, _ = r.verify_proof_ledger(deleted)
    test.check(not ok_deleted, "deletion_rejected")

    reordered = json.loads(json.dumps(ledger))
    reordered["entries"][1], reordered["entries"][2] = reordered["entries"][2], reordered["entries"][1]
    rehash_ledger(r, reordered)
    ok_reordered, _ = r.verify_proof_ledger(reordered)
    test.check(not ok_reordered, "reordering_rejected")

    substituted = json.loads(json.dumps(ledger))
    branch = build_common_prefix_branch(r, ledger)
    substituted["entries"][1]["delta"] = branch["entries"][1]["delta"]
    entry_core = dict(substituted["entries"][1])
    entry_core.pop("entry_id", None)
    substituted["entries"][1]["entry_id"] = r.identity("slang_audit_ledger_entry_sha256", entry_core)
    rehash_ledger(r, substituted)
    ok_substituted, _ = r.verify_proof_ledger(substituted)
    test.check(not ok_substituted, "substitution_rejected")

    tampered = json.loads(json.dumps(ledger))
    tampered["entries"][0]["transitions"]["profit_recognition"]["to"] = "PASS"
    entry_core = dict(tampered["entries"][0])
    entry_core.pop("entry_id", None)
    tampered["entries"][0]["entry_id"] = r.identity("slang_audit_ledger_entry_sha256", entry_core)
    rehash_ledger(r, tampered)
    ok_tampered, _ = r.verify_proof_ledger(tampered)
    test.check(not ok_tampered, "rehashed_transition_forgery_rejected")

    tampered_terminal = json.loads(json.dumps(ledger))
    tampered_terminal["terminal_bundle"]["certificate"]["reason_codes"] = ["TARGETS_STRUCTURALLY_RESOLVED", "FORGED"]
    cert_core = dict(tampered_terminal["terminal_bundle"]["certificate"])
    cert_core.pop("certificate_id", None)
    tampered_terminal["terminal_bundle"]["certificate"]["certificate_id"] = r.identity("slang_audit_certificate_sha256", cert_core)
    bundle_core = dict(tampered_terminal["terminal_bundle"])
    bundle_core.pop("bundle_id", None)
    tampered_terminal["terminal_bundle"]["bundle_id"] = r.identity("slang_audit_bundle_sha256", bundle_core)
    rehash_ledger(r, tampered_terminal)
    ok_tampered_terminal, _ = r.verify_proof_ledger(tampered_terminal)
    test.check(not ok_tampered_terminal, "historical_terminal_tamper_rejected")

    alt = build_alternative_same_terminal(r, genesis)
    ok_alt, reason_alt = r.verify_proof_ledger(alt)
    test.check(ok_alt, "alternative_history_valid:" + reason_alt)
    test.check(alt["terminal_bundle"] == ledger["terminal_bundle"], "alternative_same_terminal_exact")
    test.check(alt["ledger_id"] != ledger["ledger_id"], "alternative_ledger_identity_differs")
    test.check(alt["checkpoint"]["lineage_root_id"] != ledger["checkpoint"]["lineage_root_id"], "alternative_lineage_root_differs")
    test.check(alt["checkpoint"]["checkpoint_id"] != checkpoint["checkpoint_id"], "alternative_checkpoint_differs")
    ok_alt_cp, reason_alt_cp = r.verify_proof_ledger_against_checkpoint(alt, checkpoint)
    test.check(not ok_alt_cp and reason_alt_cp == "PINNED_CHECKPOINT_MISMATCH", "alternative_rejected_by_original_checkpoint")
    comparison_alt = r.compare_proof_ledgers(ledger, alt)
    test.check(comparison_alt["status"] == "BRANCH_DETECTED", "alternative_branch_detected")
    test.check(comparison_alt["common_prefix_entries"] == 0, "alternative_branch_at_genesis")

    ok_branch, reason_branch = r.verify_proof_ledger(branch)
    test.check(ok_branch, "common_prefix_branch_valid:" + reason_branch)
    comparison_branch = r.compare_proof_ledgers(ledger, branch)
    test.check(comparison_branch["status"] == "BRANCH_DETECTED", "common_prefix_branch_status")
    test.check(comparison_branch["common_prefix_entries"] == 1, "common_prefix_branch_count")
    test.check(comparison_branch["branch_point_bundle_id"] == ledger["entries"][0]["updated_bundle_id"], "common_prefix_branch_point")

    prefix = r.build_proof_ledger(genesis, [ledger["entries"][0]["delta"], ledger["entries"][1]["delta"]])
    comparison_prefix = r.compare_proof_ledgers(prefix, ledger)
    test.check(comparison_prefix["status"] == "PREFIX_EXTENSION", "prefix_extension_status")
    test.check(comparison_prefix["common_prefix_entries"] == 2, "prefix_extension_count")

    same = r.compare_proof_ledgers(ledger, ledger)
    test.check(same["status"] == "SAME_LINEAGE", "same_lineage")

    other_genesis_source = r.demo_structure()
    other_genesis_source["evidence"][0]["commitment"] = "sha256:" + "9" * 64
    other_genesis = r.resolve_structure(other_genesis_source)
    other_ledger = r.build_proof_ledger(other_genesis, [])
    different = r.compare_proof_ledgers(ledger, other_ledger)
    test.check(different["status"] == "DIFFERENT_GENESIS", "different_genesis")

    forged_checkpoint = json.loads(json.dumps(checkpoint))
    forged_checkpoint["entry_count"] = 3
    cp_core = dict(forged_checkpoint)
    cp_core.pop("checkpoint_id", None)
    forged_checkpoint["checkpoint_id"] = r.identity("slang_audit_ledger_checkpoint_sha256", cp_core)
    ok_forged_cp_obj, _ = r.verify_ledger_checkpoint_object(forged_checkpoint)
    test.check(ok_forged_cp_obj, "forged_checkpoint_self_hash_valid")
    ok_forged_cp, reason_forged_cp = r.verify_proof_ledger_against_checkpoint(ledger, forged_checkpoint)
    test.check(not ok_forged_cp and reason_forged_cp == "PINNED_CHECKPOINT_MISMATCH", "forged_checkpoint_not_original")

    test.check(ledger["external_truth_verified"] is False, "truth_boundary")
    test.check(ledger["external_source_provenance_verified"] is False, "provenance_boundary")
    test.check(ledger["audit_opinion_authority"] == "NONE", "authority_boundary")
    test.check(checkpoint["checkpoint_semantics"] == "PINNED_LINEAGE_IDENTITY_REQUIRED_TO_DETECT_REBUILT_ALTERNATIVE_HISTORY", "checkpoint_semantics")

    report = {
        "schema": "SLANG-AUDIT-PROOF-LEDGER-VALIDATION-REPORT-1",
        "version": VERSION,
        "frozen_resolver_version": RESOLVER_VERSION,
        "frozen_resolver_sha256": RESOLVER_SHA256,
        "ledger_id": ledger["ledger_id"],
        "checkpoint_id": checkpoint["checkpoint_id"],
        "lineage_root_id": checkpoint["lineage_root_id"],
        "entry_count": len(ledger["entries"]),
        "terminal_bundle_id": ledger["terminal_bundle"]["bundle_id"],
        "transitions": [
            {"index": item["index"], "transitions": item["transitions"], "entry_id": item["entry_id"]}
            for item in ledger["entries"]
        ],
        "valid_ledger_verification": "PASS",
        "checkpoint_verification": "PASS",
        "deletion_rejected": True,
        "reordering_rejected": True,
        "substitution_rejected": True,
        "rehashed_transition_forgery_rejected": True,
        "terminal_tamper_rejected": True,
        "alternative_history_internally_valid": True,
        "alternative_history_same_terminal": alt["terminal_bundle"] == ledger["terminal_bundle"],
        "alternative_history_original_checkpoint_rejected": True,
        "branch_detection": {
            "same_terminal_rewrite": comparison_alt,
            "common_prefix_branch": comparison_branch,
            "prefix_extension": comparison_prefix,
        },
        "external_truth_verified": False,
        "external_source_provenance_verified": False,
        "audit_opinion_authority": "NONE",
        "checks_passed": test.passed,
        "checks_total": test.total,
        "result": "PASS" if test.passed == test.total else "FAIL",
    }
    return test, report


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SLANG-Audit Proof Ledger Validation")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test", action="store_true")
    group.add_argument("--run", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        r = load_resolver()
        test, report = run_checks(r)
    except Exception as error:
        print("ERROR:" + str(error), file=sys.stderr)
        return 2
    if args.self_test:
        print("SLANG-Audit Proof Ledger Validation v{} self-test".format(VERSION))
        print("frozen_resolver_version:" + RESOLVER_VERSION)
        print("frozen_resolver_sha256:" + RESOLVER_SHA256)
        print("entries:" + str(report["entry_count"]))
        print("TOTAL {}/{} {}".format(test.passed, test.total, "PASS" if test.passed == test.total else "FAIL"))
        return 0 if test.passed == test.total else 1
    print("SLANG-Audit Proof Ledger Validation v{}".format(VERSION))
    print("Core relation:")
    print("certified audit state + ordered predecessor-bound deltas -> tamper-evident declared audit lineage -> pinned checkpoint")
    print()
    print("frozen_resolver_version:" + RESOLVER_VERSION)
    print("frozen_resolver_sha256:" + RESOLVER_SHA256)
    print("entries:" + str(report["entry_count"]))
    print("ledger_id:" + report["ledger_id"])
    print("checkpoint_id:" + report["checkpoint_id"])
    print("lineage_root_id:" + report["lineage_root_id"])
    print("valid_ledger_verification:PASS")
    print("checkpoint_verification:PASS")
    print("deletion_rejected:true")
    print("reordering_rejected:true")
    print("substitution_rejected:true")
    print("rehashed_transition_forgery_rejected:true")
    print("terminal_tamper_rejected:true")
    print("alternative_history_same_terminal:true")
    print("alternative_history_original_checkpoint_rejected:true")
    print("same_terminal_rewrite_status:" + report["branch_detection"]["same_terminal_rewrite"]["status"])
    print("common_prefix_branch_status:" + report["branch_detection"]["common_prefix_branch"]["status"])
    print("prefix_comparison_status:" + report["branch_detection"]["prefix_extension"]["status"])
    print("external_truth_verified:false")
    print("external_source_provenance_verified:false")
    print("audit_opinion_authority:NONE")
    print("proof_ledger_test:" + report["result"])
    if args.pretty:
        print(json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

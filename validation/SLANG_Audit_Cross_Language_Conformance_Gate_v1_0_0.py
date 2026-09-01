#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Shunyaya Framework contributors.

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
RESOLVER = ROOT / "core" / "SLANG_Audit_Reference_Resolver_v2_4_0.py"
JS_VERIFIER = ROOT / "validation" / "SLANG_Audit_Standalone_Verifier_v1_0_0.js"
VECTORS = ROOT / "validation" / "conformance" / "SLANG_Audit_Cross_Language_Conformance_Vectors_v1_0_0.json"
LEDGER = ROOT / "validation" / "SLANG_Audit_Proof_Ledger_Demo_v1_0_0.json"
CHECKPOINT = ROOT / "validation" / "SLANG_Audit_Proof_Ledger_Demo_Checkpoint_v1_0_0.json"


class Checks:
    def __init__(self) -> None:
        self.total = 0
        self.passed = 0
        self.failed: List[str] = []

    def check(self, condition: bool, name: str) -> None:
        self.total += 1
        if condition:
            self.passed += 1
        else:
            self.failed.append(name)


def run(args: Sequence[str]) -> Tuple[int, str, str]:
    proc = subprocess.run(args, cwd=str(ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def self_test() -> Checks:
    c = Checks()
    c.check(RESOLVER.is_file(), "resolver_exists")
    c.check(JS_VERIFIER.is_file(), "javascript_verifier_exists")
    c.check(VECTORS.is_file(), "vectors_exist")
    c.check(LEDGER.is_file(), "ledger_exists")
    c.check(CHECKPOINT.is_file(), "checkpoint_exists")
    c.check(shutil.which("node") is not None, "node_available")
    try:
        data = json.loads(VECTORS.read_text(encoding="utf-8"))
        c.check(data.get("expected_genuine_count") == 10 and len(data.get("genuine_vectors", [])) == 10, "genuine_vector_count")
        c.check(data.get("expected_mutation_count") == 6 and len(data.get("rehashed_semantic_mutations", [])) == 6, "mutation_vector_count")
    except Exception:
        c.check(False, "genuine_vector_count")
        c.check(False, "mutation_vector_count")
    return c


def conformance() -> Checks:
    c = Checks()
    data = json.loads(VECTORS.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        for item in data["genuine_vectors"]:
            path = td / (item["id"] + ".json")
            write_json(path, item["bundle"])
            py = run([sys.executable, "-B", str(RESOLVER), "--verify", str(path)])
            js = run(["node", str(JS_VERIFIER), "--verify-bundle", str(path)])
            c.check(py[0] == 0 and py[1] == "PASS", "python_accept:" + item["id"])
            c.check(js[0] == 0 and js[1] == "PASS", "javascript_accept:" + item["id"])
        for item in data["rehashed_semantic_mutations"]:
            path = td / (item["id"] + ".json")
            write_json(path, item["bundle"])
            py = run([sys.executable, "-B", str(RESOLVER), "--verify", str(path)])
            js = run(["node", str(JS_VERIFIER), "--verify-bundle", str(path)])
            c.check(py[0] != 0 and py[1].startswith("FAIL:"), "python_reject:" + item["id"])
            c.check(js[0] != 0 and js[1].startswith("FAIL:"), "javascript_reject:" + item["id"])
        inc = td / "incremental.json"
        write_json(inc, data["incremental_vector"])
        py = run([sys.executable, "-B", str(RESOLVER), "--verify-incremental", str(inc)])
        js = run(["node", str(JS_VERIFIER), "--verify-incremental", str(inc)])
        c.check(py[0] == 0 and py[1] == "PASS", "python_incremental_accept")
        c.check(js[0] == 0 and js[1] == "PASS", "javascript_incremental_accept")
    py = run([sys.executable, "-B", str(RESOLVER), "--verify-ledger", str(LEDGER)])
    js = run(["node", str(JS_VERIFIER), "--verify-ledger", str(LEDGER)])
    c.check(py[0] == 0 and py[1] == "PASS", "python_ledger_accept")
    c.check(js[0] == 0 and js[1] == "PASS", "javascript_ledger_accept")
    py = run([sys.executable, "-B", str(RESOLVER), "--verify-ledger-checkpoint", str(LEDGER), str(CHECKPOINT)])
    js = run(["node", str(JS_VERIFIER), "--verify-ledger-checkpoint", str(LEDGER), str(CHECKPOINT)])
    c.check(py[0] == 0 and py[1] == "PASS", "python_checkpoint_accept")
    c.check(js[0] == 0 and js[1] == "PASS", "javascript_checkpoint_accept")
    js_self = run(["node", str(JS_VERIFIER), "--self-test"])
    c.check(js_self[0] == 0 and "TOTAL 4/4 PASS" in js_self[1], "javascript_self_test")
    return c


def report(title: str, checks: Checks) -> int:
    print(title)
    print("TOTAL {}/{} {}".format(checks.passed, checks.total, "PASS" if not checks.failed else "FAIL"))
    for item in checks.failed:
        print("FAIL:" + item)
    return 0 if not checks.failed else 1


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SLANG-Audit cross-language conformance gate")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test", action="store_true")
    group.add_argument("--run", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        return report("SLANG-Audit Cross-Language Conformance Gate v1.0.0 self-test", self_test())
    return report("SLANG-Audit Cross-Language Conformance Gate v1.0.0", conformance())


if __name__ == "__main__":
    raise SystemExit(main())

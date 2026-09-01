#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Shunyaya Framework contributors.

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

VERSION = "2.4.0"
ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "validation" / "FROZEN_ARTIFACT_SHA256SUMS_v2_4_0.txt"

PROTECTED = {
    "core/SLANG_Audit_Reference_Resolver_v2_4_0.py",
    "validation/SLANG_Audit_Proof_Ledger_Validation_v1_0_0.py",
    "validation/SLANG_Audit_Standalone_Verifier_v1_0_0.js",
    "validation/SLANG_Audit_Cross_Language_Conformance_Gate_v1_0_0.py",
    "validation/SLANG_Audit_Evidence_Content_Binding_Verifier_v1_0_0.py",
    "validation/SLANG_Audit_Package_Verifier_v2_4_0.py",
    "validation/conformance/SLANG_Audit_Cross_Language_Conformance_Vectors_v1_0_0.json",
    "validation/SLANG_Audit_Demo_Bundle_v2_4_0.json",
    "validation/SLANG_Audit_Proof_Ledger_Demo_Genesis_Bundle_v2_4_0.json",
    "validation/SLANG_Audit_Proof_Ledger_Demo_Delta_Sequence_v1_0_0.json",
    "validation/SLANG_Audit_Proof_Ledger_Demo_Checkpoint_v1_0_0.json",
    "validation/SLANG_Audit_Proof_Ledger_Demo_v1_0_0.json",
    "validation/SLANG_Audit_Proof_Ledger_Validation_Report_v1_0_0.json",
}

REQUIRED_EDITABLE = {
    "README.md",
    "LICENSE",
    "COPYRIGHT_NOTICE.txt",
    "THIRD_PARTY_NOTICES.txt",
    "CLAIM_BOUNDARIES.txt",
    "REPRODUCIBILITY_SCOPE.txt",
    "TECHNICAL_STATUS.txt",
    "VERSION",
    "requirements.txt",
    ".gitignore",
    ".github/workflows/verify.yml",
    "docs/Architecture.md",
    "docs/Quickstart.md",
    "docs/Input-Contract.md",
    "docs/Structural-Model.md",
    "docs/Certificate-and-Verification.md",
    "docs/Portable-Certificate-and-Ledger-Specification.md",
    "docs/Cross-Language-Verification.md",
    "docs/Evidence-Content-Binding.md",
    "docs/External-Checkpoint-Anchoring.md",
    "docs/SLANG-Audit-Diagram.png",
    "docs/Minimal-Witness-and-Criticality.md",
    "docs/Incremental-Proof-Deltas.md",
    "docs/Proof-Ledger-and-Checkpoints.md",
    "docs/Integrity-Scope.md",
    "docs/Scientific-and-Operational-Boundaries.md",
    "docs/FAQ.md",
    "examples/README.md",
    "examples/SLANG_Audit_Demo_Input_v2_4_0.json",
    "examples/SLANG_Audit_Profit_Recognition_Minimal_Witness_Input_v2_4_0.json",
    "examples/SLANG_Audit_Incomplete_Example_v2_4_0.json",
    "examples/SLANG_Audit_Violated_Example_v2_4_0.json",
    "examples/SLANG_Audit_Abstain_Example_v2_4_0.json",
    "validation/Validation-Evidence.md",
    "validation/VERIFICATION_RESULT.txt",
}

HEX64 = re.compile(r"[0-9a-f]{64}\Z")


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


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_manifest_text(text: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2:
            raise ValueError("MANIFEST_FORMAT")
        digest, rel = parts
        if not HEX64.fullmatch(digest):
            raise ValueError("MANIFEST_DIGEST")
        if rel.startswith("/") or "\\" in rel or rel.startswith("../") or "/../" in rel or rel in result:
            raise ValueError("MANIFEST_PATH")
        result[rel] = digest
    return result


def run_command(args: Sequence[str]) -> Tuple[int, str, str]:
    proc = subprocess.run(args, cwd=str(ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def self_test() -> Checks:
    c = Checks()
    c.check(hashlib.sha256(b"abc").hexdigest() == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", "sha256")
    parsed = parse_manifest_text("" + "0" * 64 + "  core/x.py\n")
    c.check(parsed == {"core/x.py": "0" * 64}, "manifest_parse")
    try:
        parse_manifest_text("0" * 64 + "  ../x\n")
        path_rejected = False
    except ValueError:
        path_rejected = True
    c.check(path_rejected, "manifest_traversal_rejected")
    try:
        parse_manifest_text("0" * 64 + "  x\n" + "1" * 64 + "  x\n")
        duplicate_rejected = False
    except ValueError:
        duplicate_rejected = True
    c.check(duplicate_rejected, "manifest_duplicate_rejected")
    code, out, _ = run_command([sys.executable, "-c", "print('OK')"])
    c.check(code == 0 and out.strip() == "OK", "subprocess")
    return c


def verify_package() -> Checks:
    c = Checks()
    c.check(sys.version_info >= (3, 9), "python_version")
    c.check(shutil.which("node") is not None, "node_available")
    c.check(MANIFEST.is_file(), "manifest_exists")
    try:
        manifest = parse_manifest_text(MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        manifest = {}
    c.check(set(manifest) == PROTECTED, "manifest_exact_scope")
    for rel in sorted(PROTECTED):
        path = ROOT / rel
        c.check(path.is_file(), "protected_exists:" + rel)
        c.check(path.is_file() and manifest.get(rel) == sha256_file(path), "protected_hash:" + rel)
    c.check(PROTECTED.isdisjoint(REQUIRED_EDITABLE), "editable_unhashed_scope")
    for rel in sorted(REQUIRED_EDITABLE):
        c.check((ROOT / rel).is_file(), "editable_exists:" + rel)
    bad_metadata = []
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if rel.parts and rel.parts[0] == ".git":
            continue
        if any(part in {"__pycache__", ".git", "__MACOSX"} for part in rel.parts) or path.name in {".DS_Store", "Thumbs.db"} or path.name.endswith(":Zone.Identifier"):
            bad_metadata.append(str(path))
    c.check(not bad_metadata, "metadata_clean")

    resolver = "core/SLANG_Audit_Reference_Resolver_v2_4_0.py"
    validation = "validation/SLANG_Audit_Proof_Ledger_Validation_v1_0_0.py"

    code, out, err = run_command([sys.executable, "-B", resolver, "--self-test"])
    c.check(code == 0 and not err, "core_self_test_exit")
    c.check("TOTAL 166/166 PASS" in out, "core_self_test_result")

    code, out, err = run_command([sys.executable, "-B", resolver, "--demo"])
    c.check(code == 0 and not err, "demo_exit")
    c.check("scope:DECLARED_STRUCTURE_ONLY_NOT_AUDIT_OPINION" in out, "demo_scope_banner")
    c.check("verification:PASS" in out, "demo_bundle_verification")
    c.check("proof_ledger_verification:PASS" in out, "demo_ledger_verification")
    c.check("checkpoint_verification:PASS" in out, "demo_checkpoint_verification")
    c.check("external_truth_verified:false" in out and "external_source_provenance_verified:false" in out and "audit_opinion_authority:NONE" in out, "demo_authority_boundary")

    code, out, err = run_command([sys.executable, "-B", validation, "--self-test"])
    c.check(code == 0 and not err, "ledger_validation_self_test_exit")
    c.check("TOTAL 50/50 PASS" in out, "ledger_validation_self_test_result")

    code, out, err = run_command([sys.executable, "-B", validation, "--run"])
    c.check(code == 0 and not err, "ledger_validation_run_exit")
    c.check("proof_ledger_test:PASS" in out, "ledger_validation_run_result")
    c.check("alternative_history_same_terminal:true" in out and "alternative_history_original_checkpoint_rejected:true" in out, "same_terminal_rewrite_gate")
    c.check("same_terminal_rewrite_status:BRANCH_DETECTED" in out and "prefix_comparison_status:PREFIX_EXTENSION" in out, "lineage_comparison_gate")

    js_verifier = "validation/SLANG_Audit_Standalone_Verifier_v1_0_0.js"
    cross_gate = "validation/SLANG_Audit_Cross_Language_Conformance_Gate_v1_0_0.py"
    content_verifier = "validation/SLANG_Audit_Evidence_Content_Binding_Verifier_v1_0_0.py"

    code, out, err = run_command(["node", js_verifier, "--self-test"])
    c.check(code == 0 and not err, "javascript_self_test_exit")
    c.check("TOTAL 4/4 PASS" in out, "javascript_self_test_result")

    code, out, err = run_command([sys.executable, "-B", cross_gate, "--self-test"])
    c.check(code == 0 and not err, "cross_language_self_test_exit")
    c.check("TOTAL 8/8 PASS" in out, "cross_language_self_test_result")
    code, out, err = run_command([sys.executable, "-B", cross_gate, "--run"])
    c.check(code == 0 and not err, "cross_language_run_exit")
    c.check("TOTAL 39/39 PASS" in out, "cross_language_run_result")

    code, out, err = run_command([sys.executable, "-B", content_verifier, "--self-test"])
    c.check(code == 0 and not err, "content_binding_self_test_exit")
    c.check("TOTAL 5/5 PASS" in out, "content_binding_self_test_result")

    demo_bundle = "validation/SLANG_Audit_Demo_Bundle_v2_4_0.json"
    code, out, _ = run_command([sys.executable, "-B", resolver, "--verify", demo_bundle])
    c.check(code == 0 and out.strip() == "PASS", "frozen_demo_bundle_verify")
    code, out, _ = run_command(["node", js_verifier, "--verify-bundle", demo_bundle])
    c.check(code == 0 and out.strip() == "PASS", "frozen_demo_bundle_javascript_verify")

    ledger = "validation/SLANG_Audit_Proof_Ledger_Demo_v1_0_0.json"
    checkpoint = "validation/SLANG_Audit_Proof_Ledger_Demo_Checkpoint_v1_0_0.json"
    code, out, _ = run_command([sys.executable, "-B", resolver, "--verify-ledger", ledger])
    c.check(code == 0 and out.strip() == "PASS", "frozen_ledger_verify")
    code, out, _ = run_command(["node", js_verifier, "--verify-ledger", ledger])
    c.check(code == 0 and out.strip() == "PASS", "frozen_ledger_javascript_verify")
    code, out, _ = run_command([sys.executable, "-B", resolver, "--verify-ledger-checkpoint", ledger, checkpoint])
    c.check(code == 0 and out.strip() == "PASS", "frozen_checkpoint_verify")
    code, out, _ = run_command(["node", js_verifier, "--verify-ledger-checkpoint", ledger, checkpoint])
    c.check(code == 0 and out.strip() == "PASS", "frozen_checkpoint_javascript_verify")

    with tempfile.TemporaryDirectory() as tmp:
        resolved = Path(tmp) / "resolved_bundle.json"
        code, out, err = run_command([sys.executable, "-B", resolver, "--resolve", "examples/SLANG_Audit_Demo_Input_v2_4_0.json", "--pretty"])
        c.check(code == 0, "readme_resolve_exit")
        c.check("NOTE: structural resolution only - not an audit opinion" in err, "resolve_scope_stderr")
        resolved.write_bytes(out.encode("utf-8"))
        code, vout, _ = run_command([sys.executable, "-B", resolver, "--verify", str(resolved)])
        c.check(code == 0 and vout.strip() == "PASS", "readme_resolve_python_verify")
        code, vout, _ = run_command(["node", js_verifier, "--verify-bundle", str(resolved)])
        c.check(code == 0 and vout.strip() == "PASS", "readme_resolve_javascript_verify")

        generated = Path(tmp) / "ledger.json"
        code, out, err = run_command([
            sys.executable,
            "-B",
            resolver,
            "--ledger",
            "validation/SLANG_Audit_Proof_Ledger_Demo_Genesis_Bundle_v2_4_0.json",
            "validation/SLANG_Audit_Proof_Ledger_Demo_Delta_Sequence_v1_0_0.json",
            "--pretty",
        ])
        c.check(code == 0 and not err, "ledger_rebuild_exit")
        generated.write_bytes(out.encode("utf-8"))
        c.check(generated.read_bytes() == (ROOT / ledger).read_bytes(), "ledger_rebuild_exact")
        code, vout, _ = run_command([sys.executable, "-B", resolver, "--verify-ledger", str(generated)])
        c.check(code == 0 and vout.strip() == "PASS", "rebuilt_ledger_verify")
        code, vout, _ = run_command(["node", js_verifier, "--verify-ledger", str(generated)])
        c.check(code == 0 and vout.strip() == "PASS", "rebuilt_ledger_javascript_verify")
        code, vout, _ = run_command(["node", js_verifier, "--verify-ledger-checkpoint", str(generated), checkpoint])
        c.check(code == 0 and vout.strip() == "PASS", "rebuilt_checkpoint_javascript_verify")

    return c


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SLANG-Audit v2.4.0 package verifier")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test", action="store_true")
    group.add_argument("--verify", action="store_true")
    return parser.parse_args(argv)


def report(title: str, checks: Checks) -> int:
    print(title)
    print("TOTAL {}/{} {}".format(checks.passed, checks.total, "PASS" if not checks.failed else "FAIL"))
    if checks.failed:
        for name in checks.failed:
            print("FAIL:" + name)
        return 1
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        return report("SLANG-Audit v2.4.0 package verifier self-test", self_test())
    return report("SLANG-Audit v2.4.0 package verification", verify_package())


if __name__ == "__main__":
    raise SystemExit(main())

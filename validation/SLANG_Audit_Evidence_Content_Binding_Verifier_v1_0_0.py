#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Shunyaya Framework contributors.

import argparse
import hashlib
import re
import tempfile
from pathlib import Path
from typing import Optional, Sequence

COMMITMENT = re.compile(r"sha256:[0-9a-f]{64}\Z")


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def verify(path: Path, commitment: str) -> bool:
    if not COMMITMENT.fullmatch(commitment):
        raise ValueError("INVALID_COMMITMENT")
    return digest_file(path) == commitment


def self_test() -> int:
    total = 5
    passed = 0
    if hashlib.sha256(b"abc").hexdigest() == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad":
        passed += 1
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "evidence.bin"
        path.write_bytes(b"declared evidence bytes\n")
        commitment = digest_file(path)
        if verify(path, commitment):
            passed += 1
        if not verify(path, "sha256:" + "0" * 64):
            passed += 1
        path.write_bytes(b"changed evidence bytes\n")
        if not verify(path, commitment):
            passed += 1
        try:
            verify(path, "sha256:xyz")
            rejected = False
        except ValueError:
            rejected = True
        if rejected:
            passed += 1
    print("SLANG-Audit Evidence Content-Binding Verifier v1.0.0 self-test")
    print("TOTAL {}/{} {}".format(passed, total, "PASS" if passed == total else "FAIL"))
    return 0 if passed == total else 1


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SLANG-Audit optional evidence byte-to-commitment verifier")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test", action="store_true")
    group.add_argument("--file", metavar="PATH")
    parser.add_argument("--commitment", metavar="SHA256_COMMITMENT")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        return self_test()
    if args.commitment is None:
        print("INPUT_ERROR:--commitment is required with --file")
        return 2
    try:
        ok = verify(Path(args.file), args.commitment)
    except (OSError, ValueError) as error:
        print("INPUT_ERROR:" + str(error))
        return 2
    print("CONTENT_BINDING_" + ("PASS" if ok else "FAIL"))
    print("external_truth_verified:false")
    print("external_source_provenance_verified:false")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

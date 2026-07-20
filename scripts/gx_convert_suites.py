#!/usr/bin/env python3
"""Convert inline-gate suite JSONs to GX canonical format.

Reads `data-platform/governance/expectations/{table}_cdc_suite.json` (the
format the inline gate in `quality.py` reads) and writes the corresponding
`data-platform/governance/gx-runtime/expectations/{table}_cdc_suite.json`
(the format GX 0.18 expects to load via `context.get_expectation_suite`).

Deterministic: re-running against unchanged inputs produces byte-identical
output (sorted keys, LF line endings, trailing newline).

Supported expectation kinds (superset of what the inline gate enforces;
GX-proper understands all of these — the inline gate silently ignores the
kinds it does not implement):

  - expect_column_to_exist
  - expect_column_values_to_not_be_null
  - expect_column_values_to_be_in_set
  - expect_column_values_to_be_between
  - expect_column_value_lengths_to_be_between
  - expect_column_values_to_be_of_type
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

GX_VERSION = "0.18.19"

SUPPORTED = {
    "expect_column_to_exist",
    "expect_column_values_to_not_be_null",
    "expect_column_values_to_be_in_set",
    "expect_column_values_to_be_between",
    "expect_column_value_lengths_to_be_between",
    "expect_column_values_to_be_of_type",
}


def convert(inline: dict, source_path: Path) -> dict:
    suite_name = inline.get("expectation_suite_name")
    if not suite_name:
        raise ValueError(f"{source_path}: missing 'expectation_suite_name'")

    expectations = []
    for exp in inline.get("expectations", []):
        etype = exp.get("expectation_type")
        if etype not in SUPPORTED:
            print(
                f"WARN: {source_path}: skipping unsupported expectation "
                f"'{etype}'",
                file=sys.stderr,
            )
            continue
        kwargs = dict(exp.get("kwargs", {}))
        meta = kwargs.pop("meta", None)
        entry = {
            "expectation_type": etype,
            "kwargs": kwargs,
            "meta": meta or {},
        }
        expectations.append(entry)

    return {
        "expectation_suite_name": suite_name,
        "data_asset_type": None,
        "meta": {
            "great_expectations_version": GX_VERSION,
            **(inline.get("meta") or {}),
        },
        "expectations": expectations,
        "ge_cloud_id": None,
    }


def convert_file(src: Path, dst: Path) -> bool:
    with src.open() as f:
        inline = json.load(f)
    canonical = convert(inline, src)
    payload = json.dumps(canonical, indent=2, sort_keys=True) + "\n"

    if dst.exists():
        existing = dst.read_text()
        if existing == payload:
            return False

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(payload)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--src-dir",
        type=Path,
        default=Path("data-platform/governance/expectations"),
    )
    parser.add_argument(
        "--dst-dir",
        type=Path,
        default=Path("data-platform/governance/gx-runtime/expectations"),
    )
    args = parser.parse_args()

    if not args.src_dir.is_dir():
        print(f"error: source dir not found: {args.src_dir}", file=sys.stderr)
        return 2

    sources = sorted(args.src_dir.glob("*_suite.json"))
    if not sources:
        print(f"error: no suite files at {args.src_dir}", file=sys.stderr)
        return 2

    changed = 0
    for src in sources:
        dst = args.dst_dir / src.name
        if convert_file(src, dst):
            print(f"wrote  {dst}")
            changed += 1
        else:
            print(f"unchanged  {dst}")

    print(f"done: {changed} file(s) changed of {len(sources)} suite(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Write QA config filtering results to GITHUB_OUTPUT for GitHub Actions.

Replaces the inline Python config-loading blocks in notebook-qa.yml.
Uses qa_config.py as a library to filter notebooks per check and write
the results as GitHub Actions step outputs.

Usage (lint job — all checks + extras):
    python write_gha_config.py \
        --checks linter formatter pynblint links figures \
                 metadata accessibility license changelog \
        --config .github/notebook-qa.yml \
        --extras

Usage (execute job — execution check + performance-test thresholds):
    python3 write_gha_config.py \
        --checks execute \
        --config .github/notebook-qa.yml \
        --performance-tests

Reads the notebook list from the ALL_NOTEBOOKS environment variable
(newline-separated paths).
"""

import argparse
import os
import sys

from qa_config import (
    get_filtered_notebooks_for_check,
    get_performance_test_thresholds,
    get_pynblint_exclude,
    load_config,
)


def parse_notebook_list(raw: str) -> list[str]:
    """Parse notebook list from newline-separated (or space-separated) string."""
    nbs = [nb.strip() for nb in raw.splitlines() if nb.strip()] if "\n" in raw else raw.split()
    return [nb.removeprefix("./") for nb in nbs]


def write_multiline_output(fh, key: str, lines: list[str]) -> None:
    """Write a value to GITHUB_OUTPUT, using multiline syntax when needed."""
    if not lines:
        fh.write(f"{key}=\n")
        return
    fh.write(f"{key}<<__NB_EOF__\n")
    for line in lines:
        fh.write(f"{line}\n")
    fh.write("__NB_EOF__\n")


def main():
    parser = argparse.ArgumentParser(description="Write QA config outputs for GitHub Actions")
    parser.add_argument("--checks", nargs="+", required=True, help="Check IDs to produce output for")
    parser.add_argument("--config", default=".github/notebook-qa.yml", help="Path to QA config file")
    parser.add_argument("--extras", action="store_true", help="Also write pynblint config")
    parser.add_argument(
        "--performance-tests",
        action="store_true",
        help="Also write performance-test threshold outputs",
    )
    args = parser.parse_args()

    raw_notebooks = os.environ.get("ALL_NOTEBOOKS", "")
    notebooks = parse_notebook_list(raw_notebooks)
    config = load_config(args.config)

    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        print("Error: GITHUB_OUTPUT environment variable not set", file=sys.stderr)
        sys.exit(1)

    with open(output_path, "a") as out:
        for check in args.checks:
            skip, filtered = get_filtered_notebooks_for_check(config, check, notebooks)
            out.write(f"skip_{check}={'true' if skip else 'false'}\n")
            write_multiline_output(out, f"notebooks_{check}", filtered)

        if args.extras:
            pynblint_exclude = get_pynblint_exclude(config)
            out.write(f"pynblint_exclude={pynblint_exclude}\n")

        if args.performance_tests:
            try:
                thresholds = get_performance_test_thresholds(config)
            except ValueError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                sys.exit(1)

            for key, value in thresholds.items():
                out.write(f"{key}={'' if value is None else value}\n")


if __name__ == "__main__":
    main()

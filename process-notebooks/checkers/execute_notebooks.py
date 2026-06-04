#!/usr/bin/env python3
"""Execute notebooks with Ploomber and enforce performance-test thresholds."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ploomber_engine import execute_notebook
from ploomber_engine.profiling import get_profiling_data

WARNING_ANNOTATION_LIMIT = 20
THRESHOLD_ENV_VARS = {
    "max_cell_memory_mb_warning": "MAX_CELL_MEMORY_MB_WARNING",
    "max_cell_memory_mb_fail": "MAX_CELL_MEMORY_MB_FAIL",
    "max_cell_runtime_seconds_warning": "MAX_CELL_RUNTIME_SECONDS_WARNING",
    "max_cell_runtime_seconds_fail": "MAX_CELL_RUNTIME_SECONDS_FAIL",
}
CSV_FIELDS = [
    "notebook",
    "execution_status",
    "code_cell",
    "notebook_cell",
    "memory_mb",
    "runtime_seconds",
    "memory_status",
    "runtime_status",
]


@dataclass
class Thresholds:
    max_cell_memory_mb_warning: float | None
    max_cell_memory_mb_fail: float | None
    max_cell_runtime_seconds_warning: float | None
    max_cell_runtime_seconds_fail: float | None


@dataclass
class NotebookResult:
    notebook: str
    execution_failed: bool
    profiling_available: bool
    max_memory_mb: float | None
    max_runtime_seconds: float | None
    rows: list[dict[str, str]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute notebooks, save profiling artifacts, and enforce performance limits"
    )
    parser.add_argument("notebooks", nargs="+", help="Notebook paths to execute")
    parser.add_argument("--output-dir", default="qa_outputs", help="Directory for QA artifacts")
    return parser.parse_args()


def parse_threshold(name: str, env_var: str) -> float | None:
    raw = os.environ.get(env_var, "").strip()
    if raw == "":
        return None
    try:
        value = float(raw)
    except ValueError:
        print(f"::error::Invalid {name}: {raw!r} is not a number")
        sys.exit(1)
    if value <= 0:
        print(f"::error::Invalid {name}: value must be positive")
        sys.exit(1)
    return value


def load_thresholds() -> Thresholds:
    values = {key: parse_threshold(key, env_var) for key, env_var in THRESHOLD_ENV_VARS.items()}
    return Thresholds(**values)


def relative_artifact_path(notebook: str) -> Path:
    path = Path(notebook)
    if path.is_absolute():
        try:
            path = path.relative_to(Path.cwd())
        except ValueError:
            path = Path(path.name)
    normalized = Path(os.path.normpath(str(path)))
    safe_parts = [part for part in normalized.parts if part not in (".", "..", os.sep)]
    return Path(*safe_parts) if safe_parts else Path(normalized.name)


def code_cell_positions(notebook: str) -> list[int]:
    try:
        with open(notebook, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        warning(f"Could not inspect notebook cells for {notebook}: {exc}")
        return []

    positions = []
    for index, cell in enumerate(data.get("cells", []), start=1):
        if cell.get("cell_type") == "code":
            positions.append(index)
    return positions


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def format_value(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}".rstrip("0").rstrip(".")


def metric_status(value: float | None, warning_threshold: float | None, fail_threshold: float | None) -> str:
    if value is None:
        return "N/A"
    if fail_threshold is not None and value > fail_threshold:
        return "fail"
    if warning_threshold is not None and value > warning_threshold:
        return "warning"
    return "ok"


def gha_escape(message: str) -> str:
    return message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def warning(message: str) -> None:
    print(f"::warning::{gha_escape(message)}")


def error(message: str) -> None:
    print(f"::error::{gha_escape(message)}")


def rows_for_failed_execution(notebook: str) -> list[dict[str, str]]:
    return [
        {
            "notebook": notebook,
            "execution_status": "failed",
            "code_cell": "N/A",
            "notebook_cell": "N/A",
            "memory_mb": "N/A",
            "runtime_seconds": "N/A",
            "memory_status": "N/A",
            "runtime_status": "N/A",
        }
    ]


def rows_from_profiling(
    notebook: str,
    data: dict[str, Any],
    positions: list[int],
    thresholds: Thresholds,
) -> tuple[list[dict[str, str]], bool, float | None, float | None]:
    memory_values = [to_float(value) for value in data.get("memory") or []]
    runtime_values = [to_float(value) for value in data.get("runtime") or []]
    row_count = max(len(memory_values), len(runtime_values), len(positions))

    if row_count == 0:
        return (rows_for_missing_profiling(notebook), False, None, None)

    rows = []
    for index in range(row_count):
        memory = memory_values[index] if index < len(memory_values) else None
        runtime = runtime_values[index] if index < len(runtime_values) else None
        notebook_cell = positions[index] if index < len(positions) else None
        rows.append(
            {
                "notebook": notebook,
                "execution_status": "success",
                "code_cell": str(index + 1),
                "notebook_cell": str(notebook_cell) if notebook_cell is not None else "N/A",
                "memory_mb": format_value(memory),
                "runtime_seconds": format_value(runtime),
                "memory_status": metric_status(
                    memory,
                    thresholds.max_cell_memory_mb_warning,
                    thresholds.max_cell_memory_mb_fail,
                ),
                "runtime_status": metric_status(
                    runtime,
                    thresholds.max_cell_runtime_seconds_warning,
                    thresholds.max_cell_runtime_seconds_fail,
                ),
            }
        )

    max_memory = max((value for value in memory_values if value is not None), default=None)
    max_runtime = max((value for value in runtime_values if value is not None), default=None)
    profiling_available = any(value is not None for value in memory_values + runtime_values)
    return rows, profiling_available, max_memory, max_runtime


def rows_for_missing_profiling(notebook: str) -> list[dict[str, str]]:
    return [
        {
            "notebook": notebook,
            "execution_status": "success",
            "code_cell": "N/A",
            "notebook_cell": "N/A",
            "memory_mb": "N/A",
            "runtime_seconds": "N/A",
            "memory_status": "N/A",
            "runtime_status": "N/A",
        }
    ]


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def execute_one(notebook: str, output_dir: Path, thresholds: Thresholds) -> NotebookResult:
    rel_path = relative_artifact_path(notebook)
    executed_path = output_dir / "executed-notebooks" / rel_path
    profiling_path = output_dir / "profiling" / rel_path.with_name(f"{rel_path.stem}-profiling.csv")
    executed_path.parent.mkdir(parents=True, exist_ok=True)
    profiling_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"Executing: {notebook}")
    print("=" * 60)

    positions = code_cell_positions(notebook)
    try:
        result = execute_notebook(
            notebook,
            output_path=str(executed_path),
            profile_memory=True,
            profile_runtime=True,
            progress_bar=False,
        )
    except Exception as exc:
        error(f"{notebook} failed to execute: {exc}")
        rows = rows_for_failed_execution(notebook)
        write_csv(profiling_path, rows)
        return NotebookResult(notebook, True, False, None, None, rows)

    data = get_profiling_data(result) or {}
    rows, profiling_available, max_memory, max_runtime = rows_from_profiling(
        notebook, data, positions, thresholds
    )
    write_csv(profiling_path, rows)

    if not profiling_available:
        warning(f"No profiling data returned for {notebook}; performance data marked N/A")
    else:
        memory_values_available = any(row["memory_status"] != "N/A" for row in rows)
        runtime_values_available = any(row["runtime_status"] != "N/A" for row in rows)
        if not memory_values_available:
            warning(f"No memory profiling data returned for {notebook}; memory marked N/A")
        if not runtime_values_available:
            warning(f"No runtime profiling data returned for {notebook}; runtime marked N/A")

    print(f"✅ {notebook} executed successfully")
    return NotebookResult(notebook, False, profiling_available, max_memory, max_runtime, rows)


def threshold_message(row: dict[str, str], metric: str) -> str:
    value_key = "memory_mb" if metric == "memory" else "runtime_seconds"
    unit = "MB" if metric == "memory" else "seconds"
    return (
        f"{row['notebook']} code cell {row['code_cell']} "
        f"(notebook cell {row['notebook_cell']}) {metric} "
        f"{row[value_key]} {unit} exceeded performance-test threshold"
    )


def emit_threshold_annotations(rows: list[dict[str, str]]) -> tuple[int, int]:
    failures = 0
    warnings = 0
    warning_annotations = 0

    for row in rows:
        for metric in ("memory", "runtime"):
            status = row[f"{metric}_status"]
            if status == "fail":
                failures += 1
                error(threshold_message(row, metric))
            elif status == "warning":
                warnings += 1
                if warning_annotations < WARNING_ANNOTATION_LIMIT:
                    warning(threshold_message(row, metric))
                    warning_annotations += 1

    if warnings > warning_annotations:
        warning(
            f"Suppressed {warnings - warning_annotations} additional performance-test "
            "warning annotation(s); see uploaded CSV artifacts for full details"
        )

    return failures, warnings


def row_metric_status(row: dict[str, str]) -> str:
    statuses = {row["memory_status"], row["runtime_status"]}
    if "fail" in statuses:
        return "fail"
    if "warning" in statuses:
        return "warning"
    if "N/A" in statuses:
        return "N/A"
    return "ok"


def notebook_status(result: NotebookResult) -> str:
    if result.execution_failed:
        return "execution failed"
    statuses = [row_metric_status(row) for row in result.rows]
    if "fail" in statuses:
        return "fail"
    if "warning" in statuses:
        return "warning"
    if "N/A" in statuses:
        return "N/A"
    return "ok"


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def build_summary(
    results: list[NotebookResult],
    all_rows: list[dict[str, str]],
    thresholds: Thresholds,
    threshold_failures: int,
    threshold_warnings: int,
) -> str:
    selected = len(results)
    executed = sum(not result.execution_failed for result in results)
    profiling_available = sum(result.profiling_available for result in results)
    coverage_rows = [row for row in all_rows if row["execution_status"] == "success"]
    covered_cells = sum(
        row["memory_status"] != "N/A" and row["runtime_status"] != "N/A" for row in coverage_rows
    )
    total_cells = sum(row["code_cell"] != "N/A" for row in coverage_rows)
    execution_failures = sum(result.execution_failed for result in results)

    lines = ["## Notebook performance tests", ""]
    lines.extend(
        [
            f"- Notebooks selected: **{selected}**",
            f"- Notebooks executed successfully: **{executed}/{selected}**",
            f"- Performance tests available: **{profiling_available}/{selected}** notebooks",
            f"- Performance tests coverage: **{covered_cells}/{total_cells}** profiled code "
            "cells had memory and runtime data",
            f"- Threshold failures: **{threshold_failures}**",
            f"- Threshold warnings: **{threshold_warnings}**",
            f"- Execution failures: **{execution_failures}**",
            "",
            "### Thresholds",
            "",
        ]
    )
    lines.append(
        markdown_table(
            ["Limit", "Value"],
            [
                ["Memory warning", format_value(thresholds.max_cell_memory_mb_warning) + " MB"],
                ["Memory fail", format_value(thresholds.max_cell_memory_mb_fail) + " MB"],
                [
                    "Runtime warning",
                    format_value(thresholds.max_cell_runtime_seconds_warning) + " s",
                ],
                ["Runtime fail", format_value(thresholds.max_cell_runtime_seconds_fail) + " s"],
            ],
        )
    )

    lines.extend(["", "### Notebook maxima", ""])
    lines.append(
        markdown_table(
            ["Notebook", "Max memory MB", "Max runtime s", "Status"],
            [
                [
                    result.notebook,
                    format_value(result.max_memory_mb),
                    format_value(result.max_runtime_seconds),
                    notebook_status(result),
                ]
                for result in results
            ],
        )
    )

    notable_rows = [
        row
        for row in all_rows
        if row_metric_status(row) in {"fail", "warning", "N/A"} or row["execution_status"] == "failed"
    ]
    lines.extend(["", "### Notable cells", ""])
    if notable_rows:
        display_rows = notable_rows[:100]
        lines.append(
            markdown_table(
                [
                    "Notebook",
                    "Code cell",
                    "Notebook cell",
                    "Memory MB",
                    "Runtime s",
                    "Memory status",
                    "Runtime status",
                    "Execution",
                ],
                [
                    [
                        row["notebook"],
                        row["code_cell"],
                        row["notebook_cell"],
                        row["memory_mb"],
                        row["runtime_seconds"],
                        row["memory_status"],
                        row["runtime_status"],
                        row["execution_status"],
                    ]
                    for row in display_rows
                ],
            )
        )
        if len(notable_rows) > len(display_rows):
            lines.append(
                f"\nShowing {len(display_rows)} of {len(notable_rows)} notable rows. "
                "See `performance-summary.csv` for full details."
            )
    else:
        lines.append("No warnings, failures, or N/A profiling values.")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    thresholds = load_thresholds()

    results = [execute_one(notebook, output_dir, thresholds) for notebook in args.notebooks]
    all_rows = [row for result in results for row in result.rows]

    write_csv(output_dir / "performance-summary.csv", all_rows)
    threshold_failures, threshold_warnings = emit_threshold_annotations(all_rows)

    summary = build_summary(results, all_rows, thresholds, threshold_failures, threshold_warnings)
    (output_dir / "performance-summary.md").write_text(summary, encoding="utf-8")
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as fh:
            fh.write(summary)

    execution_failures = sum(result.execution_failed for result in results)
    if execution_failures or threshold_failures:
        print(
            f"❌ Notebook execution/performance tests failed: "
            f"{execution_failures} execution failure(s), "
            f"{threshold_failures} threshold failure(s)"
        )
        sys.exit(1)

    print("✅ Notebook execution/performance tests passed")


if __name__ == "__main__":
    main()

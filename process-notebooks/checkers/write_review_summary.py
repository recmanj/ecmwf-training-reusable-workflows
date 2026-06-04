#!/usr/bin/env python3

"""Generate the notebook QA markdown summary table for GitHub Actions."""

from __future__ import annotations

import os
from pathlib import Path


def format_status(result: str) -> str:
    mapping = {
        "success": "Pass",
        "failure": "Fail",
        "cancelled": "Cancelled",
        "skipped": "Skipped",
    }
    return mapping.get(result, "N/A")


def check_status(step_result: str, job_result: str) -> str:
    if not step_result and job_result != "success":
        step_result = job_result
    return format_status(step_result)


def aggregate_status(results: list[str], lint_job_result: str) -> str:
    has_success = False
    has_skipped = False
    has_cancelled = False

    for result in results:
        if result == "failure":
            return "Fail"
        if result == "cancelled":
            has_cancelled = True
        elif result == "success":
            has_success = True
        elif result == "skipped":
            has_skipped = True

    if has_cancelled:
        return "Cancelled"
    if has_success:
        return "Pass"
    if has_skipped:
        return "Skipped"
    if lint_job_result != "success":
        return format_status(lint_job_result)
    return "N/A"


def clean_error(text: str) -> str:
    """Sanitise captured error output for inclusion in a markdown table cell."""
    text = text.strip()
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("|", "\\|")
    return text.replace("\n", "<br>")


def resolve_run_url(env) -> str:
    """Resolve the fallback URL to the GitHub Actions run page."""
    url = env.get("LOGS_URL", "").strip()
    if url:
        return url
    server = env.get("GITHUB_SERVER_URL", "https://github.com")
    repo = env.get("GITHUB_REPOSITORY", "")
    run_id = env.get("GITHUB_RUN_ID", "")
    if repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return ""


def result_cell(status: str, error: str, logs_url: str = "") -> str:
    """Render the Automated Result cell with a bold status and optional error detail."""
    cell = f"**{status}**"
    if status != "Fail":
        return cell
    if error:
        cell += "<br>" + error
    elif logs_url:
        cell += (
            "<br>Unable to gather error message please see full github logs: "
            f"[GitHub Actions logs]({logs_url})"
        )
    else:
        cell += "<br>Unable to gather error message please see full github logs."
    return cell


def append_row(
    rows: list[str],
    include_all: bool,
    criterion: str,
    ref: str,
    status: str,
    error: str = "",
    comment: str = "",
    logs_url: str = "",
) -> None:
    """Record a table row, filtering to failures unless include_all is set."""
    if include_all or status == "Fail":
        cells = [criterion, ref, result_cell(status, error, logs_url), comment]
        rows.append("| " + " | ".join(cells) + " |")


def main() -> int:
    env = os.environ

    run_url = resolve_run_url(env)
    lint_logs_url = env.get("LINT_LOGS_URL", "").strip() or run_url
    execute_logs_url = env.get("EXECUTE_LOGS_URL", "").strip() or run_url

    lint_job_result = env.get("LINT_JOB_RESULT", "")
    execute_job_result = env.get("EXECUTE_JOB_RESULT", "")

    links_status = check_status(env.get("LINK_RESULT", ""), lint_job_result)
    license_status = check_status(env.get("LICENSE_RESULT", ""), lint_job_result)
    metadata_status = check_status(env.get("METADATA_RESULT", ""), lint_job_result)
    data_source_status = check_status(env.get("DATA_SOURCE_RESULT", ""), lint_job_result)
    execute_status = check_status(env.get("EXECUTE_RESULT", ""), execute_job_result)
    code_style_status = aggregate_status(
        [
            env.get("LINTER_RESULT", ""),
            env.get("FORMATTER_RESULT", ""),
            env.get("PYNBLINT_RESULT", ""),
        ],
        lint_job_result,
    )
    figure_status = check_status(env.get("FIGURE_RESULT", ""), lint_job_result)
    accessibility_status = check_status(env.get("ACCESSIBILITY_RESULT", ""), lint_job_result)
    changelog_status = check_status(env.get("CHANGELOG_RESULT", ""), lint_job_result)

    links_error = clean_error(env.get("LINK_ERROR", ""))
    license_error = clean_error(env.get("LICENSE_ERROR", ""))
    metadata_error = clean_error(env.get("METADATA_ERROR", ""))
    data_source_error = clean_error(env.get("DATA_SOURCE_ERROR", ""))
    execute_error = clean_error(env.get("EXECUTE_ERROR", ""))
    figure_error = clean_error(env.get("FIGURE_ERROR", ""))
    accessibility_error = clean_error(env.get("ACCESSIBILITY_ERROR", ""))
    changelog_error = clean_error(env.get("CHANGELOG_ERROR", ""))
    code_style_error = clean_error(
        "\n".join(
            part
            for part in (
                env.get("LINTER_ERROR", ""),
                env.get("FORMATTER_ERROR", ""),
                env.get("PYNBLINT_ERROR", ""),
            )
            if part.strip()
        )
    )

    summary_file = env.get("SUMMARY_FILE")
    if not summary_file:
        summary_file = str(Path(env.get("RUNNER_TEMP", "/tmp")) / "notebook-qa-summary.md")

    include_all = env.get("SUMMARISE_ALL_CHECKS", "").strip().lower() in ("true", "1", "yes")

    rows: list[str] = []

    append_row(
        rows,
        include_all,
        "All links in the learning resource must work.",
        "1.2.3",
        links_status,
        links_error,
        logs_url=lint_logs_url,
    )
    append_row(
        rows,
        include_all,
        "All licences applicable to the learning resource must be provided.",
        "1.2.4",
        license_status,
        license_error,
        logs_url=lint_logs_url,
    )
    append_row(
        rows,
        include_all,
        "The date of the most recent version of the learning resource must be stated.",
        "1.2.6",
        metadata_status,
        metadata_error,
        logs_url=lint_logs_url,
    )
    append_row(
        rows,
        include_all,
        "The date of the most recent execution of the learning resource code must be stated.",
        "1.2.7",
        "N/A",
        "",
    )
    append_row(
        rows,
        include_all,
        "All datasets used in the learning resource must be available.",
        "1.2.8",
        data_source_status,
        data_source_error,
        logs_url=lint_logs_url,
    )
    append_row(
        rows,
        include_all,
        "All code cells must be able to run sequentially without errors.",
        "2.2.1",
        execute_status,
        execute_error,
        logs_url=execute_logs_url,
    )
    append_row(
        rows,
        include_all,
        "All Python code must adhere to the Black style.",
        "2.2.3",
        code_style_status,
        code_style_error,
        logs_url=lint_logs_url,
    )
    append_row(
        rows,
        include_all,
        "All installation/execute instructions must be functional across current devices "
        "and operating systems.",
        "2.2.4",
        execute_status,
        execute_error,
        logs_url=execute_logs_url,
    )
    append_row(
        rows,
        include_all,
        "All installation/execute instructions must be functional across current internet browsers.",
        "2.2.5",
        "N/A",
        "",
    )
    append_row(
        rows,
        include_all,
        "The learning resource must be functional using the supplied dependencies and/or environment.",
        "2.3.1",
        execute_status,
        execute_error,
        logs_url=execute_logs_url,
    )
    append_row(
        rows,
        include_all,
        "All dependencies of the source code must be stable and reliable.",
        "2.2.8",
        "N/A",
        "",
    )
    append_row(
        rows,
        include_all,
        "All dependencies of the source code must be regularly security checked.",
        "2.2.7",
        "N/A",
        "",
    )
    append_row(
        rows,
        include_all,
        "The learning resource must come with a set of tests for evaluating its performance.",
        "2.3.1",
        execute_status,
        execute_error,
        logs_url=execute_logs_url,
    )
    append_row(
        rows,
        include_all,
        "Performance tests must pass with X% coverage.",
        "2.3.2",
        execute_status,
        execute_error,
        logs_url=execute_logs_url,
    )
    append_row(
        rows,
        include_all,
        "Key text-based information must be compatible with text to audio software.",
        "3.1.3",
        accessibility_status,
        accessibility_error,
        logs_url=lint_logs_url,
    )
    append_row(
        rows,
        include_all,
        "Graphs and figures must be properly labelled and include source information.",
        "3.3.2",
        figure_status,
        figure_error,
        logs_url=lint_logs_url,
    )
    append_row(
        rows,
        include_all,
        "Underlying sources, datasets, and publications must be referenced.",
        "4.1.1",
        "N/A",
        "",
    )
    append_row(
        rows,
        include_all,
        "All figures, tables, and datasets must be accompanied by appropriate attribution and explanations.",
        "4.1.2",
        "N/A",
        "",
    )
    append_row(
        rows,
        include_all,
        "A record of all revisions and updates must be available in the documentation.",
        "4.2.3",
        changelog_status,
        changelog_error,
        logs_url=lint_logs_url,
    )
    append_row(rows, include_all, "In expert reviews only", "N/A", "N/A", comment="N/A")

    lines: list[str] = [
        "## AUTOMATED REVIEW",
        "",
        (
            "The table below summarises the results of the automated checks performed on learning resource. "
            "It should be copied to the 'Automated Review' section of the review checklist. "
        ),
        (
            "The 'Automated Result' column is populated from the results of the GitHub Actions "
            "workflow, and the 'Technical Officer Comment' column is for any additional comments from the "
            "technical officer."
        ),
    ]
    if rows:
        lines.append("| Criterion | Ref no. | Automated Result | Technical Officer Comment |")
        lines.append("| --- | --- | --- | --- |")
        lines.extend(rows)
    else:
        lines.append("All automated checks passed. No failures to report.")

    Path(summary_file).write_text("\n".join(lines) + "\n", encoding="utf-8")

    github_output = env.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.write(f"summary_file={summary_file}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

## reusable workflows

This repository contains reusable GitHub Actions workflows for C3S projects. There is currently one CI workflow for Jupyter Notebook QA automation.


### notebook-qa

This workflow implements QA automation for Jupyter Notebooks. The checks below run automatically — all checks that are not skipped or disabled must pass for the workflow to succeed.

On pull requests, only notebooks changed relative to the PR base are checked. On pushes and manual `workflow_dispatch` runs, all `*.ipynb` files are checked (unless a specific list is supplied via the `notebooks` input).

Checks are split across three jobs: a fast `lint` job for static checks, an `execute` job for end-to-end notebook execution (on a configurable runner), and a `summary` job that renders the automated review table.

#### Checks

**Code linting** (`linter`) — Runs `ruff check` on all code cells. No Python lint violations allowed.

**Code formatting** (`formatter`) — Runs `ruff format --check` on code cells. Code cells must conform to `ruff` formatting rules.

**Notebook linting** (`pynblint`) — Runs `pynblint` on each notebook. Checks notebook-level quality issues such as non-linear execution order, empty cells, or untitled notebooks.

**Link availability** (`links`) — Runs `lychee` against all notebooks. Every URL in markdown and code cells must be reachable.

**Notebook execution** (`execute`) — Executes each notebook end-to-end with `ploomber-engine` inside a Conda environment built from the consuming repository's `environment.yml`. The notebook must run without errors. Memory usage and runtime are profiled per cell, checked against performance-test thresholds, and uploaded as artifacts. The runner and timeout are configurable via the `execution_runner` and `execution_timeout` inputs.

**Data source availability** (`data_source`) — Warning-only check. Inspects code cells for how data is sourced. If data is fetched but not via approved sources (`cdsapi`, `earthkit`, or the CDS/ADS APIs), it emits a warning annotation. This check never fails the workflow.

**Version metadata** (`metadata`) — Looks for `**Last updated:** YYYY-MM-DD` (e.g. `**Last updated:** 2025-01-15`) in the first markdown cell(s) before any code cell. Falls back to a `README.md` in the same directory if not found in the notebook.


**Accessibility** (`accessibility`) — Runs WCAG compliance checks on notebooks using `jupyterlab-a11y-checker`.

**Figure attribution** (`figures`) — Every figure output (PNG/JPEG) in code cells must have source attribution in a nearby markdown cell (within 2 cells). Recognized attribution patterns include `source:`, `credit:`, `data from:`, `attribution:`, `reference:`, `dataset:`, a DOI, or a URL.

**License file** (`license`) — A non-empty `LICENSE` file must exist in the repository root.

**Changelog file** (`changelog`) — A non-empty `CHANGELOG.md` file must exist in the repository root.

#### How to use `notebook-qa.yml` workflow

Configure the target repository which you want to run the QA check against using this format:

```
.github/workflows/qa.yml

------------------------

name: Notebook QA

on:
  push:
    branches:
      - develop
  pull_request:
    branches:
      - develop
  workflow_dispatch:
    inputs:
      notebooks:
        description: "Space-separated list of notebook paths to check (default: all *.ipynb)"
        required: false
        type: string
        default: ""

permissions:
  contents: read
  pull-requests: write

jobs:
  notebook-qa:
    uses: ecmwf-training/reusable-workflows/.github/workflows/notebook-qa.yml@main
    with:
      notebooks: ${{ inputs.notebooks || '' }}
      pr_comment_summary: true
    secrets: inherit
```

This sets up automated checks on new pull requests and merges/pushes into `develop` branch. It also allows manual Action runs in the GitHub Actions UI.

The workflow writes the automated review table to the GitHub Actions job summary and, by default, updates a single managed comment on pull requests. Set `pr_comment_summary: false` to disable PR comments. The caller workflow must grant `pull-requests: write` for PR comments to work; reusable workflows cannot elevate the caller's `GITHUB_TOKEN` permissions. Pull requests from forks may still receive read-only tokens depending on the target repository settings.

By default the summary table only lists checks that failed. Set `summarise_all_checks: true` to include every check (passed, skipped, and failed) in the table.

#### Workflow inputs

All inputs are optional.

| Input | Default | Description |
|-------|---------|-------------|
| `notebooks` | `""` | Space-separated list of notebook paths to check. Empty checks all `*.ipynb` (or changed notebooks on PRs). |
| `execution_runner` | `ubuntu-latest` | Runner for the notebook execution job. Supports self-hosted runners. |
| `execution_timeout` | `60` | Timeout in minutes for the notebook execution job. |
| `qa_tools_repo` | `ecmwf-training/reusable-workflows` | Repository containing the QA checker tools. |
| `qa_tools_ref` | `""` | Git ref (branch, tag, or SHA) of the QA tools repository to check out. When empty, defaults to the reusable workflow's own commit so the checker tools always match the workflow version. |
| `pr_comment_summary` | `true` | Post/update the automated review summary as a pull request comment. |
| `summarise_all_checks` | `false` | Include all checks in the summary table instead of only failed checks. |

#### Workflow secrets

All secrets are optional and can be passed via `secrets: inherit` or explicitly.

| Secret | Description |
|--------|-------------|
| `CDSAPI_KEY` | API key used to configure `cdsapi` for the notebook execution check. |


#### Configuration

You can customize check behavior by adding a `.github/notebook-qa.yml` config file in the consuming repository:

```yaml
# Globally disable specific checks
disabled_checks:
  - linter
  - formatter

# Notebooks to skip entirely (all checks), supports glob patterns
skip_notebooks:
  - "draft.ipynb"
  - "notebooks/draft.ipynb"
  - "notebooks/experimental/**"

# Per-notebook check configuration
notebooks:
  "notebooks/example.ipynb":
    skip:
      - figures

# Performance-test thresholds used during notebook execution.
# Defaults are strict for learner-suitable notebooks. Set any value to null to disable it.
performance_tests:
  max_cell_memory_mb_warning: 512
  max_cell_memory_mb_fail: 1024
  max_cell_runtime_seconds_warning: 60
  max_cell_runtime_seconds_fail: 180

# Pynblint rule configuration
pynblint:
  exclude:                    # Additional rules to suppress (extends baseline)
    - untitled-notebook
  exclude_mode: extend        # "extend" (default) or "override"
```

The baseline pynblint exclusion list suppresses `missing-h1-MD-heading` (MyST notebooks use YAML frontmatter for titles) and `imports-beyond-first-cell`. In `extend` mode (default), your `exclude` list is merged with the baseline. In `override` mode, your list fully replaces the baseline.

Available pynblint rule slugs: `non-linear-execution`, `notebook-too-long`, `untitled-notebook`, `non-portable-chars-in-nb-name`, `notebook-name-too-long`, `imports-beyond-first-cell`, `missing-h1-MD-heading`, `missing-opening-MD-text`, `missing-closing-MD-text`, `too-few-MD-cells`, `duplicate-notebook-not-renamed`, `invalid-python-syntax`, `non-executed-notebook`, `non-executed-cells`, `empty-cells`, `long-multiline-python-comment`, `cell-too-long`

Valid check IDs: `linter`, `formatter`, `pynblint`, `links`, `figures`, `metadata`, `data_source`, `accessibility`, `license`, `changelog`, `execute`


#### QA criteria reference

| ID    | Description               | Tool / Check           |
|-------|---------------------------|------------------------|
| 1.2.3 | Link availability         | lychee                 |
| 1.2.4 | License file              | LICENSE existence       |
| 1.2.6 | Version metadata          | metadata_checker.py    |
| 1.2.8 | Data source availability  | data_source_checker.py |
| 2.2.1 | Code execution            | ploomber-engine        |
| 2.2.3 | Code style                | ruff, pynblint         |
| 2.2.4 | Execution profiling       | ploomber-engine        |
| 2.2.6 | Memory profiling          | ploomber-engine        |
| 2.3.1 | Performance tests available | ploomber-engine profiling |
| 2.3.2 | Performance tests coverage | resource threshold checks |
| 3.1.3 | Accessibility             | jupyterlab-a11y-checker|
| 3.3.2 | Figure attribution        | figure_checker.py      |
| 4.2.3 | Changelog                 | CHANGELOG.md existence |


### Notebook execution environment

The notebook execution check builds a Conda environment from an `environment.yml` file in the consuming repository root. Ensure this file exists and declares all dependencies required to run the notebooks. Execution tooling (`ploomber-engine`, `psutil`, `matplotlib`) is installed automatically on top of this environment.


### How to configure access to cdsapi for notebook execution check

The action responsible for notebook execution allows setting a `cdsapi` key via `CDSAPI_KEY` secret set either on repository or organisation level.


### How to setup reusable-workflows repository in GitHub organisation

1. Fork this repository into your organisation
2. Leave the fork network in the newly forked repository settings

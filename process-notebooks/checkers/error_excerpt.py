#!/usr/bin/env python3
"""Print a short, bounded excerpt of a QA check log for the review summary.

Check errors travel from the lint/execute jobs to the summary job as step outputs and end up
as environment variables there. Linux caps a single environment variable at 128 KiB, and logs
with progress bars (tqdm rewrites its line with ``\\r`` thousands of times) or long diffs blow
past that, so the summary job fails with "Argument list too long". This script renders the log
the way a terminal would, drops noise, and caps the result.

Usage: error_excerpt.py LOG_FILE   (``-`` reads stdin). Always exits 0.
"""

from __future__ import annotations

import argparse
import re
import sys

MAX_LINES = 20
MAX_LINE_CHARS = 400
MAX_CHARS = 2000
TRUNCATED_MARKER = "… (earlier output truncated, see job logs)"

# Full CSI escape sequence (colours, cursor movement, ?25l, ...)
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
# tqdm progress bar, e.g. " 45%|████▌     | 9/20 [00:01<00:02, 4.50it/s]"
PROGRESS_RE = re.compile(r"\d{1,3}%\|.*\|\s*\S+/\S+\s*\[")
# GitHub workflow commands carrying a message, e.g. "::error file=x.ipynb::message"
COMMAND_RE = re.compile(r"^::(error|warning|notice)[^:]*::")


def terminal_line(raw: str) -> str:
    """Return what a terminal shows for one physical line: the text after the last carriage return."""
    return ANSI_RE.sub("", raw.rstrip("\r").rsplit("\r", 1)[-1]).rstrip()


def expand_command(line: str) -> list[str]:
    """Decode ``::error::``/``::warning::``/``::notice::`` escapes into real lines."""
    match = COMMAND_RE.match(line)
    if not match:
        return [line]
    body = line[match.end() :].replace("%0D", "").replace("%0A", "\n").replace("%25", "%")
    return f"{match.group(1).capitalize()}: {body}".split("\n")


def shorten(line: str, limit: int) -> str:
    """Cut the middle out of an overlong line, keeping its start and (most of) its end."""
    if len(line) <= limit:
        return line
    head = limit // 3
    return line[:head] + " … " + line[-(limit - head - 3) :]


def excerpt(
    text: str,
    max_lines: int = MAX_LINES,
    max_line_chars: int = MAX_LINE_CHARS,
    max_chars: int = MAX_CHARS,
) -> str:
    """Return the last meaningful lines of ``text``, at most ``max_chars`` characters in total."""
    lines: list[str] = []
    for raw in text.split("\n"):
        for line in expand_command(terminal_line(raw)):
            line = line.rstrip()
            if not line.strip() or PROGRESS_RE.search(line):
                continue
            lines.append(shorten(line, max_line_chars))
    lines = lines[-max_lines:] if max_lines > 0 else []

    def size(kept: list[str], marker: bool) -> int:
        return len("\n".join(([TRUNCATED_MARKER] if marker else []) + kept))

    if size(lines, marker=False) <= max_chars:
        return "\n".join(lines)
    # Drop the oldest lines until the remaining lines plus the marker fit
    while lines and size(lines, marker=True) > max_chars:
        lines.pop(0)
    if not lines:
        # A single line longer than the cap (only possible with max_line_chars > max_chars)
        return TRUNCATED_MARKER[:max_chars]
    return "\n".join([TRUNCATED_MARKER, *lines])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", help="log file to excerpt, or - for stdin")
    parser.add_argument("--max-lines", type=int, default=MAX_LINES)
    parser.add_argument("--max-line-chars", type=int, default=MAX_LINE_CHARS)
    parser.add_argument("--max-chars", type=int, default=MAX_CHARS)
    args = parser.parse_args(argv)
    try:
        if args.path == "-":
            data = sys.stdin.buffer.read()
        else:
            with open(args.path, "rb") as fh:
                data = fh.read()
    except OSError as exc:
        print(f"error_excerpt: cannot read {args.path}: {exc}", file=sys.stderr)
        return 0
    out = excerpt(
        data.decode("utf-8", errors="replace"),
        max_lines=args.max_lines,
        max_line_chars=args.max_line_chars,
        max_chars=args.max_chars,
    )
    if out:
        # Write UTF-8 regardless of the runner's locale (the marker and ✅/❌ are non-ASCII)
        sys.stdout.buffer.write((out + "\n").encode("utf-8"))
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

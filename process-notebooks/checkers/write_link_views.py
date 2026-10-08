#!/usr/bin/env python3
"""
Write link-check views of Jupyter notebooks for lychee (Criterion 1.2.3).

A view contains everything a reader can click: markdown and code cell sources plus
rendered (text/html, text/markdown) outputs. Text outputs (text/plain, stream) are
left out because library reprs truncate long values ("http://nco.sf....") into
URLs that never existed.

Usage:
    python write_link_views.py --output-dir DIR notebook1.ipynb notebook2.ipynb ...

Views are plain text (.txt), so lychee extracts absolute URLs only, as it does from a raw
.ipynb; a markdown view would also resolve relative links against DIR and report them missing.

Prints the path of each view, one per line.
"""

import argparse
import os
from pathlib import Path

from utils import extract_cell_source, read_notebook

RENDERED_OUTPUT_TYPES = ("text/html", "text/markdown")


def render_view(nb_data: dict) -> str:
    """Render the linkable content of a notebook as one text document."""
    parts = []
    for cell_idx, cell in enumerate(nb_data.get("cells", [])):
        parts.append(f"<!-- cell {cell_idx} ({cell.get('cell_type')}) -->")
        parts.append(extract_cell_source(cell))
        for output in cell.get("outputs", []):
            data = output.get("data", {})
            for mime in RENDERED_OUTPUT_TYPES:
                if mime in data:
                    parts.append(f"<!-- cell {cell_idx} output ({mime}) -->")
                    parts.append(extract_cell_source({"source": data[mime]}))
        parts.append("")
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Write link-check views of Jupyter notebooks")
    parser.add_argument("notebooks", nargs="+", help="Notebook files to render")
    parser.add_argument("--output-dir", required=True, help="Directory to write the views into")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    for notebook in args.notebooks:
        target = output_dir / f"{os.path.normpath(notebook)}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_view(read_notebook(notebook)), encoding="utf-8")
        print(target)


if __name__ == "__main__":
    main()

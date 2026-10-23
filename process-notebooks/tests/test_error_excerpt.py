import io
import sys

import error_excerpt
import pytest
from error_excerpt import MAX_CHARS, TRUNCATED_MARKER, excerpt


def test_carriage_returns_keep_last_update():
    text = "start\rDownloading  10%\rDownloading 100%\r\nnext line\r\n"
    assert excerpt(text) == "Downloading 100%\nnext line"


def test_ansi_sequences_are_stripped():
    text = "\x1b[1m\x1b[31mError\x1b[0m: boom\x1b[?25l\n\x1b[1Aafter\x1b[K\n"
    assert excerpt(text) == "Error: boom\nafter"


def test_tqdm_progress_lines_are_dropped():
    bar = " 45%|████▌     | 9/20 [00:01<00:02, 4.50it/s]"
    text = "\r".join([bar] * 2000) + "\nTraceback: real error\n"
    assert excerpt(text) == "Traceback: real error"


def test_workflow_command_escapes_are_decoded():
    text = "::error file=nb.ipynb,line=3::nb.ipynb failed to execute:%0AValueError: 100%25 bad%0D%0Ahint\n"
    assert excerpt(text).splitlines() == [
        "Error: nb.ipynb failed to execute:",
        "ValueError: 100% bad",
        "hint",
    ]


def test_keeps_last_lines_and_status_icons():
    text = "\n".join(f"line {i}" for i in range(100)) + "\n✅ ok\n❌ broken\n"
    lines = excerpt(text).splitlines()
    assert len(lines) == 20
    assert lines[-2:] == ["✅ ok", "❌ broken"]
    assert lines[0] == "line 82"


def test_long_line_is_shortened_in_the_middle():
    line = "HEAD" + "x" * 10_000 + "TAIL"
    out = excerpt(line)
    assert len(out) == 400
    assert out.startswith("HEAD")
    assert out.endswith("TAIL")
    assert " … " in out


@pytest.mark.parametrize(
    "text",
    [
        "\n".join("y" * 399 for _ in range(50)),
        "z" * 1_000_000,
        "\n".join(f"short {i}" for i in range(10_000)),
    ],
)
def test_output_never_exceeds_cap(text):
    assert len(excerpt(text)) <= MAX_CHARS


def test_marker_counts_towards_cap():
    five = "\n".join("a" * 399 for _ in range(5))  # 1999 chars: fits without a marker
    assert excerpt(five) == five
    out = excerpt("\n".join("a" * 399 for _ in range(6)))  # with the marker only 4 lines fit
    lines = out.splitlines()
    assert lines[0] == TRUNCATED_MARKER
    assert len(lines) == 5
    assert len(out) <= MAX_CHARS


@pytest.mark.parametrize("text", ["", "\r\r\r", "   \n\t\n \r\n"])
def test_empty_or_blank_input(text):
    assert excerpt(text) == ""


def _run_main(monkeypatch, argv, stdin_bytes=b""):
    out = io.BytesIO()
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(stdin_bytes)))
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(out))
    rc = error_excerpt.main(argv)
    sys.stdout.flush()
    return rc, out.getvalue()


def test_main_reads_stdin(monkeypatch):
    assert _run_main(monkeypatch, ["-"], b"one\r\ntwo\r\n") == (0, b"one\ntwo\n")


def test_main_handles_invalid_utf8(monkeypatch, tmp_path):
    log = tmp_path / "log.txt"
    log.write_bytes(b"bad \xff\xfe bytes\n\xe2\x9d\x8c failed\n")
    rc, out = _run_main(monkeypatch, [str(log)])
    assert rc == 0
    assert out.decode("utf-8") == "bad �� bytes\n❌ failed\n"


def test_main_empty_file_prints_nothing(monkeypatch, tmp_path):
    log = tmp_path / "empty.log"
    log.write_bytes(b"")
    assert _run_main(monkeypatch, [str(log)]) == (0, b"")


def test_main_missing_file_exits_zero(monkeypatch, tmp_path):
    assert _run_main(monkeypatch, [str(tmp_path / "missing.log")]) == (0, b"")

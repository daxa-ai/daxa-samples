"""Reusable spreadsheet -> plain-text parsing helpers (no Streamlit dependency).

Framework-agnostic on purpose: any caller (Streamlit app, CLI script, API
endpoint) can pass raw bytes in and get an LLM-friendly text blob out.
"""
import io
import zipfile
from typing import List

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

MAX_CHARS = 8000
MAX_ROWS_PER_SHEET = 500


class FileParsingError(Exception):
    """Raised when input bytes cannot be parsed as a supported spreadsheet."""


def parse_xlsx_to_text(file_bytes: bytes, filename: str = "", max_chars: int = MAX_CHARS) -> str:
    """Parse .xlsx bytes into a plain-text, LLM-friendly representation.

    One "Sheet: <name>" section per worksheet, followed by its rows (cell
    values joined with " | "), one row per line. Result is truncated to
    `max_chars`.

    Args:
        file_bytes: Raw bytes of an .xlsx/.xlsm file.
        filename: Original filename, used only to make error messages clearer.
        max_chars: Hard cap on the returned string's length.

    Returns:
        Plain-text description of every sheet's contents (never None; an
        empty or all-blank workbook returns descriptive placeholder text
        rather than raising).

    Raises:
        FileParsingError: if file_bytes is not a readable Excel workbook
            (wrong format, corrupt file, etc.).
    """
    try:
        workbook = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except (InvalidFileException, KeyError, OSError, zipfile.BadZipFile) as exc:
        raise FileParsingError(
            f"Could not read '{filename or 'uploaded file'}' as an Excel (.xlsx) file: {exc}"
        ) from exc

    sections: List[str] = []
    for sheet_name in workbook.sheetnames:
        ws = workbook[sheet_name]
        lines = [f"Sheet: {sheet_name}"]
        row_count = 0
        for row in ws.iter_rows(values_only=True):
            if row_count >= MAX_ROWS_PER_SHEET:
                lines.append("...[remaining rows truncated]")
                break
            cells = [str(c) if c is not None else "" for c in row]
            if any(cells):  # skip fully-empty rows
                lines.append(" | ".join(cells))
            row_count += 1
        if row_count == 0:
            lines.append("(empty sheet)")
        sections.append("\n".join(lines))

    text = "\n\n".join(sections) if sections else "(workbook has no sheets)"
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...[truncated]"
    return text

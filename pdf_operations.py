"""Page-level PDF operations that preserve the original page content."""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

import pikepdf


def get_page_count(source_path: str | Path) -> int:
    """Return the number of pages in an unencrypted PDF."""
    with _open_pdf(source_path) as source_pdf:
        return len(source_pdf.pages)


def pages_for_selection(page_count: int, selection: str) -> tuple[int, ...]:
    """Return zero-based page indices for an all, odd, or even page selection."""
    if page_count < 1:
        raise ValueError("The PDF must contain at least one page.")
    if selection == "all":
        return tuple(range(page_count))
    if selection == "odd":
        return tuple(range(0, page_count, 2))
    if selection == "even":
        return tuple(range(1, page_count, 2))
    raise ValueError("Selection must be 'all', 'odd', or 'even'.")


def split_pages(
    source_path: str | Path,
    output_folder: str | Path,
    page_indices: Iterable[int],
) -> list[Path]:
    """Write each selected source page to its own PDF in the output folder."""
    source = Path(source_path).resolve()
    folder = Path(output_folder).resolve()
    indices = tuple(page_indices)
    if not folder.is_dir():
        raise ValueError("The output folder does not exist.")
    if not indices:
        raise ValueError("Select at least one page.")
    if any(not isinstance(index, int) or isinstance(index, bool) for index in indices):
        raise ValueError("Page indices must be integers.")
    if len(set(indices)) != len(indices):
        raise ValueError("A page can only be split once.")

    outputs = [
        folder / f"{source.stem}_page_{index + 1:04d}.pdf"
        for index in indices
    ]
    with _open_pdf(source) as source_pdf:
        _validate_pages(source_pdf, indices)
        for index, target in zip(indices, outputs):
            _write_subset(source_pdf, target, (index,))
    return outputs


def write_pages(
    source_path: str | Path,
    output_path: str | Path,
    page_indices: Iterable[int],
) -> int:
    """Write the selected zero-based pages to a new PDF without rasterizing them."""
    source = Path(source_path).resolve()
    target = Path(output_path).resolve()
    indices = tuple(page_indices)

    if source == target:
        raise ValueError("The output file must be different from the source file.")
    if not target.parent.is_dir():
        raise ValueError("The output folder does not exist.")
    if not indices:
        raise ValueError("Select at least one page.")
    if any(not isinstance(index, int) or isinstance(index, bool) for index in indices):
        raise ValueError("Page indices must be integers.")

    with _open_pdf(source) as source_pdf:
        _validate_pages(source_pdf, indices)
        _write_subset(source_pdf, target, indices)

    return len(indices)


@contextmanager
def _open_pdf(source_path: str | Path) -> Iterator[pikepdf.Pdf]:
    try:
        pdf = pikepdf.open(source_path)
    except pikepdf.PasswordError as error:
        raise ValueError("Password-protected PDFs are not supported.") from error

    with pdf:
        if pdf.is_encrypted:
            raise ValueError("Password-protected PDFs are not supported.")
        yield pdf


def _validate_pages(source_pdf: pikepdf.Pdf, indices: tuple[int, ...]) -> None:
    page_count = len(source_pdf.pages)
    if any(index < 0 or index >= page_count for index in indices):
        raise ValueError("A selected page is outside the source document.")


def _write_subset(
    source_pdf: pikepdf.Pdf,
    target: Path,
    indices: tuple[int, ...],
) -> None:
    output_pdf = pikepdf.new()
    try:
        for index in indices:
            output_pdf.pages.append(source_pdf.pages[index])
        _save_atomically(output_pdf, target)
    finally:
        output_pdf.close()


def _save_atomically(pdf: pikepdf.Pdf, target: Path) -> None:
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.stem}_",
        suffix=".tmp.pdf",
        dir=target.parent,
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)

    try:
        pdf.save(temporary_path)
        os.replace(temporary_path, target)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pikepdf

from pdf_operations import get_page_count, pages_for_selection, split_pages, write_pages


class PdfOperationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "source.pdf"
        self._create_source()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _create_source(self) -> None:
        pdf = pikepdf.new()
        for page_number, page_size in enumerate(
            ((200, 300), (320, 240), (400, 500)),
            start=1,
        ):
            page = pdf.add_blank_page(page_size=page_size)
            page.obj.Contents = pdf.make_stream(
                f"q {page_number / 10} gs 0 0 100 100 re f Q".encode()
            )
            graphics_state = pdf.make_indirect(
                pikepdf.Dictionary(Type=pikepdf.Name.ExtGState, ca=page_number / 10)
            )
            page.obj.Resources = pikepdf.Dictionary(
                ExtGState=pikepdf.Dictionary(GS1=graphics_state)
            )
        pdf.save(self.source)
        pdf.close()

    def test_split_copy_preserves_page_box_stream_and_transparency_resource(self) -> None:
        output = self.root / "page-2.pdf"

        self.assertEqual(write_pages(self.source, output, (1,)), 1)

        with pikepdf.open(self.source) as original, pikepdf.open(output) as copied:
            self.assertEqual(len(copied.pages), 1)
            self.assertEqual(list(copied.pages[0].mediabox), list(original.pages[1].mediabox))
            self.assertEqual(
                copied.pages[0].obj.Contents.read_bytes(),
                original.pages[1].obj.Contents.read_bytes(),
            )
            copied_state = copied.pages[0].obj.Resources.ExtGState.GS1
            original_state = original.pages[1].obj.Resources.ExtGState.GS1
            self.assertEqual(float(copied_state.ca), float(original_state.ca))

    def test_write_pages_preserves_requested_order(self) -> None:
        output = self.root / "reordered.pdf"

        self.assertEqual(write_pages(self.source, output, (2, 0)), 2)

        with pikepdf.open(output) as copied:
            self.assertEqual(len(copied.pages), 2)
            self.assertEqual(list(copied.pages[0].mediabox), [0, 0, 400, 500])
            self.assertEqual(list(copied.pages[1].mediabox), [0, 0, 200, 300])

    def test_page_count(self) -> None:
        self.assertEqual(get_page_count(self.source), 3)

    def test_all_odd_and_even_page_selections(self) -> None:
        self.assertEqual(pages_for_selection(5, "all"), (0, 1, 2, 3, 4))
        self.assertEqual(pages_for_selection(5, "odd"), (0, 2, 4))
        self.assertEqual(pages_for_selection(5, "even"), (1, 3))
        self.assertEqual(pages_for_selection(1, "even"), ())

    def test_split_pages_creates_one_output_per_requested_page(self) -> None:
        outputs = split_pages(self.source, self.root, (0, 2))

        self.assertEqual(
            [path.name for path in outputs],
            ["source_page_0001.pdf", "source_page_0003.pdf"],
        )
        self.assertTrue(all(path.is_file() for path in outputs))

    def test_rejects_empty_or_out_of_range_selection(self) -> None:
        with self.assertRaises(ValueError):
            write_pages(self.source, self.root / "empty.pdf", ())
        with self.assertRaises(ValueError):
            write_pages(self.source, self.root / "invalid.pdf", (3,))

    def test_refuses_to_overwrite_source(self) -> None:
        with self.assertRaises(ValueError):
            write_pages(self.source, self.source, (0,))

    def test_reports_password_protected_pdf_as_unsupported(self) -> None:
        protected = self.root / "protected.pdf"
        with pikepdf.new() as pdf:
            pdf.add_blank_page()
            pdf.save(
                protected,
                encryption=pikepdf.Encryption(owner="owner", user="user", R=6),
            )

        with self.assertRaisesRegex(ValueError, "Password-protected"):
            get_page_count(protected)


if __name__ == "__main__":
    unittest.main()

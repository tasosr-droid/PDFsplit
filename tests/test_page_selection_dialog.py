from __future__ import annotations

import os
import gc
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pikepdf
from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel
from unittest.mock import patch

from pdf_splitter import (
    PageSelectionDialog,
    PdfSplitterWindow,
    stylesheet_for_theme,
)


class PageSelectionDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.source = Path(self.temp_dir.name) / "preview.pdf"
        with pikepdf.new() as pdf:
            pdf.add_blank_page(page_size=(200, 300))
            pdf.add_blank_page(page_size=(320, 240))
            pdf.add_blank_page(page_size=(400, 500))
            pdf.save(self.source)
        self.dialogs: list[PageSelectionDialog] = []
        self.windows: list[PdfSplitterWindow] = []

    def tearDown(self) -> None:
        for dialog in self.dialogs:
            dialog.reject()
            dialog.deleteLater()
        for window in self.windows:
            window.close()
            window.deleteLater()
        self.application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.application.processEvents()
        self.dialogs.clear()
        self.windows.clear()
        gc.collect()
        self.temp_dir.cleanup()

    def _make_dialog(
        self,
        *,
        multi_select: bool,
        selected_pages: set[int],
    ) -> PageSelectionDialog:
        dialog = PageSelectionDialog(
            self.source,
            3,
            multi_select=multi_select,
            selected_pages=selected_pages,
            parent=None,
        )
        dialog.render_timer.stop()
        self.dialogs.append(dialog)
        return dialog

    def _make_window(self) -> PdfSplitterWindow:
        window = PdfSplitterWindow()
        self.windows.append(window)
        return window

    def test_window_uses_split_icon(self) -> None:
        window = self._make_window()

        self.assertFalse(window.windowIcon().isNull())
        self.assertEqual(window.windowTitle(), "PDF Split! v0.3 by Tasos Rizopoulos 2026")
        title_icon = window.findChild(QLabel, "appIcon")
        self.assertIsNotNone(title_icon)
        self.assertFalse(title_icon.pixmap().isNull())

    def test_stylesheets_include_light_and_dark_palettes(self) -> None:
        light_stylesheet = stylesheet_for_theme(dark=False)
        dark_stylesheet = stylesheet_for_theme(dark=True)

        self.assertIn("background: #f5f7fb;", light_stylesheet)
        self.assertIn("background: #171a21;", dark_stylesheet)
        self.assertIn("color: #e6eaf2;", dark_stylesheet)
        self.assertNotIn("@", light_stylesheet)
        self.assertNotIn("@", dark_stylesheet)

    def _render_all_pages(self, dialog: PageSelectionDialog) -> None:
        for _ in range(dialog.page_grid.count() + 1):
            dialog._render_next_thumbnail()

    def _click_page(self, dialog: PageSelectionDialog, page_index: int) -> None:
        dialog.show()
        self.application.processEvents()
        position = dialog.page_grid.visualItemRect(dialog.page_grid.item(page_index)).center()
        QTest.mouseClick(
            dialog.page_grid.viewport(),
            Qt.MouseButton.LeftButton,
            pos=position,
        )
        self.application.processEvents()

    def test_extract_picker_shows_green_tint_and_enforces_single_selection(self) -> None:
        dialog = self._make_dialog(multi_select=False, selected_pages={0})

        self._render_all_pages(dialog)
        self.assertTrue(all(
            not dialog.page_grid.item(index).icon().isNull()
            for index in range(dialog.page_grid.count())
        ))
        self.assertEqual(dialog.selected_pages, {0})
        selected_image = dialog.page_grid.item(0).icon().pixmap(150, 200).toImage()
        self.assertGreater(
            selected_image.pixelColor(75, 100).green(),
            selected_image.pixelColor(75, 100).red(),
        )

        self._click_page(dialog, 1)
        self._click_page(dialog, 2)
        self.assertEqual(dialog.selected_pages, {2})
        selected_image = dialog.page_grid.item(2).icon().pixmap(150, 200).toImage()
        self.assertGreater(
            selected_image.pixelColor(75, 100).green(),
            selected_image.pixelColor(75, 100).red(),
        )
        for index in (0, 1):
            image = dialog.page_grid.item(index).icon().pixmap(150, 200).toImage()
            self.assertEqual(
                image.pixelColor(75, 100),
                dialog._base_thumbnails[index].toImage().pixelColor(75, 100),
            )

    def test_delete_picker_toggles_red_tint_on_thumbnail_click(self) -> None:
        dialog = self._make_dialog(multi_select=True, selected_pages=set())
        self._render_all_pages(dialog)

        self._click_page(dialog, 1)
        self.assertEqual(dialog.selected_pages, {1})
        selected_image = dialog.page_grid.item(1).icon().pixmap(150, 200).toImage()
        self.assertGreater(
            selected_image.pixelColor(75, 100).red(),
            selected_image.pixelColor(75, 100).green(),
        )

        self._click_page(dialog, 1)
        self.assertEqual(dialog.selected_pages, set())
        unselected_image = dialog.page_grid.item(1).icon().pixmap(150, 200).toImage()
        self.assertEqual(
            unselected_image.pixelColor(75, 100),
            dialog._base_thumbnails[1].toImage().pixelColor(75, 100),
        )

    def test_multi_page_picker_keeps_multiple_selections_and_supports_select_all(self) -> None:
        dialog = self._make_dialog(multi_select=True, selected_pages={1})

        self._click_page(dialog, 0)
        self.assertEqual(dialog.selected_pages, {0, 1})

        dialog._set_all_checked(True)
        self.assertEqual(dialog.selected_pages, {0, 1, 2})
        dialog._set_all_checked(False)
        self.assertEqual(dialog.selected_pages, set())

    def test_extract_ok_copies_selected_page_number_to_page_box(self) -> None:
        window = self._make_window()
        window.source_path = self.source
        window.page_count = 3
        window.extract_spin.setMaximum(3)
        window.extract_spin.setValue(1)

        def accept_second_page(dialog: PageSelectionDialog) -> QDialog.DialogCode:
            self.dialogs.append(dialog)
            dialog._toggle_page_selection(dialog.page_grid.item(1))
            dialog.accept()
            return QDialog.DialogCode.Accepted

        with patch.object(PageSelectionDialog, "exec", accept_second_page):
            window.choose_extract_page()
        self.assertEqual(window.extract_spin.value(), 2)

    def test_delete_ok_runs_the_selected_delete_action(self) -> None:
        window = self._make_window()
        window.source_path = self.source
        window.page_count = 3
        window.target_folder = self.source.parent
        window.action_buttons[2].setChecked(True)

        def accept_third_page(dialog: PageSelectionDialog) -> QDialog.DialogCode:
            self.dialogs.append(dialog)
            dialog.page_grid.item(2).setData(Qt.ItemDataRole.UserRole, True)
            dialog.accept()
            return QDialog.DialogCode.Accepted

        with (
            patch.object(PageSelectionDialog, "exec", accept_third_page),
            patch.object(window, "_confirm_replacements", return_value=True),
            patch.object(window, "_show_success"),
        ):
            window.choose_delete_pages()
        output = self.source.with_name("preview_without_selected_pages.pdf")
        self.assertTrue(output.is_file())
        self.assertEqual(window.selected_delete_pages, set())
        with pikepdf.open(output) as updated, pikepdf.open(self.source) as original:
            self.assertEqual(len(updated.pages), 2)
            self.assertEqual(len(original.pages), 3)


if __name__ == "__main__":
    unittest.main()

"""A simple desktop PDF splitter and page extractor by Tasos Rizopoulos 2026."""

from __future__ import annotations

import sys
from pathlib import Path

import pikepdf
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pdf_operations import get_page_count, pages_for_selection, split_pages, write_pages


APP_ICON_PATH = Path(__file__).resolve().with_name("split.png")


STYLESHEET_TEMPLATE = """
QMainWindow, QWidget {
    background: @background;
    color: @foreground;
    font-family: "Segoe UI";
    font-size: 10pt;
}
QLabel#eyebrow {
    color: @eyebrow;
    font-size: 9pt;
    font-weight: 600;
}
QLabel#title {
    color: @foreground;
    font-size: 25pt;
    font-weight: 700;
}
QLabel#subtitle, QLabel#muted {
    color: @muted;
}
QFrame#dropZone {
    background: @surface;
    border: 2px dashed @drop-border;
    border-radius: 14px;
}
QFrame#dropZone[dragging="true"] {
    border-color: @accent;
    background: @drag-background;
}
QFrame#panel, QFrame#fileCard {
    background: @surface;
    border: 1px solid @border;
    border-radius: 12px;
}
QToolButton {
    background: @button-background;
    border: 1px solid @button-border;
    border-radius: 9px;
    padding: 11px;
    font-weight: 600;
}
QToolButton:checked {
    color: @checked-foreground;
    background: @checked-background;
    border: 1px solid @checked-border;
}
QPushButton {
    background: @button-background;
    border: 1px solid @button-border;
    border-radius: 8px;
    padding: 9px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background: @button-hover;
}
QPushButton#primary {
    color: #ffffff;
    background: @accent;
    border: 1px solid @accent;
    padding: 11px 20px;
}
QPushButton#primary:hover {
    background: @accent-hover;
}
QLineEdit, QSpinBox, QListWidget {
    background: @input-background;
    border: 1px solid @input-border;
    border-radius: 7px;
    padding: 7px;
}
QListWidget::item {
    padding: 6px;
}
QListWidget::item:selected {
    background: @checked-background;
    color: @foreground;
}
QRadioButton, QCheckBox {
    spacing: 8px;
}
"""

THEME_COLORS = {
    "light": {
        "background": "#f5f7fb",
        "foreground": "#172033",
        "eyebrow": "#52617a",
        "muted": "#69768c",
        "surface": "#ffffff",
        "border": "#e1e6ef",
        "drop-border": "#c7d1e1",
        "drag-background": "#f0f5ff",
        "accent": "#315fce",
        "accent-hover": "#254fb3",
        "button-background": "#ffffff",
        "button-border": "#d4dce8",
        "button-hover": "#f3f6fb",
        "checked-foreground": "#2456c7",
        "checked-background": "#edf3ff",
        "checked-border": "#8ba9ee",
        "input-background": "#ffffff",
        "input-border": "#d8e0eb",
    },
    "dark": {
        "background": "#171a21",
        "foreground": "#e6eaf2",
        "eyebrow": "#a9b4c6",
        "muted": "#a0aaba",
        "surface": "#202630",
        "border": "#343d4b",
        "drop-border": "#586474",
        "drag-background": "#27334a",
        "accent": "#547fe0",
        "accent-hover": "#426dce",
        "button-background": "#252c37",
        "button-border": "#3b4656",
        "button-hover": "#303a48",
        "checked-foreground": "#a9c2ff",
        "checked-background": "#293754",
        "checked-border": "#6684c7",
        "input-background": "#191e26",
        "input-border": "#414b5b",
    },
}


def is_windows_dark_mode() -> bool:
    if sys.platform != "win32":
        return False

    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            uses_light_theme, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
    except OSError:
        return False
    return uses_light_theme == 0


def stylesheet_for_theme(dark: bool) -> str:
    palette = THEME_COLORS["dark" if dark else "light"]
    stylesheet = STYLESHEET_TEMPLATE
    for name, color in palette.items():
        stylesheet = stylesheet.replace(f"@{name}", color)
    return stylesheet


class PageSelectionDialog(QDialog):
    def __init__(
        self,
        source_path: Path,
        page_count: int,
        *,
        multi_select: bool,
        selected_pages: set[int],
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose pages")
        self.resize(780, 620)
        self.multi_select = multi_select
        self._next_page_to_render = 0
        self._base_thumbnails: dict[int, QPixmap] = {}

        root = QVBoxLayout(self)
        heading = QLabel("Choose pages to delete" if multi_select else "Choose a page to extract")
        heading.setStyleSheet("font-size: 16pt; font-weight: 650;")
        root.addWidget(heading)
        instructions = QLabel(
            "Click each page you want to remove. Click it again to deselect."
            if multi_select
            else "Click the page you want to extract."
        )
        instructions.setObjectName("muted")
        root.addWidget(instructions)

        self.page_grid = QListWidget()
        self.page_grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.page_grid.setFlow(QListWidget.Flow.LeftToRight)
        self.page_grid.setWrapping(True)
        self.page_grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.page_grid.setMovement(QListWidget.Movement.Static)
        self.page_grid.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.page_grid.setIconSize(QSize(150, 200))
        self.page_grid.setGridSize(QSize(174, 240))
        self.page_grid.setSpacing(8)
        self.page_grid.itemClicked.connect(self._toggle_page_selection)
        root.addWidget(self.page_grid, 1)

        controls = QHBoxLayout()
        self.selection_status = QLabel()
        self.selection_status.setObjectName("muted")
        controls.addWidget(self.selection_status, 1)
        if multi_select:
            select_all_button = QPushButton("Select all")
            select_all_button.clicked.connect(lambda: self._set_all_checked(True))
            clear_button = QPushButton("Clear")
            clear_button.clicked.connect(lambda: self._set_all_checked(False))
            controls.addWidget(select_all_button)
            controls.addWidget(clear_button)
        root.addLayout(controls)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)
        self.ok_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setEnabled(False)

        self.document = QPdfDocument(self)
        load_error = self.document.load(str(source_path))
        if load_error != QPdfDocument.Error.None_:
            raise ValueError(f"Could not load PDF previews: {load_error.name}.")
        if self.document.pageCount() != page_count:
            raise ValueError("The PDF changed while previews were being prepared.")

        self._initial_pages = set(selected_pages)
        self._populate_pages(page_count)
        self._update_selection_status()

        self.render_timer = QTimer(self)
        self.render_timer.setInterval(0)
        self.render_timer.timeout.connect(self._render_next_thumbnail)
        self.render_timer.start()
        self.finished.connect(self._close_document)

    @property
    def selected_pages(self) -> set[int]:
        return {
            index
            for index in range(self.page_grid.count())
            if self.page_grid.item(index).data(Qt.ItemDataRole.UserRole)
        }

    def _populate_pages(self, page_count: int) -> None:
        for page_index in range(page_count):
            item = QListWidgetItem(f"Page {page_index + 1}")
            item.setData(Qt.ItemDataRole.UserRole, page_index in self._initial_pages)
            item.setSizeHint(QSize(174, 240))
            self.page_grid.addItem(item)

    def _render_next_thumbnail(self) -> None:
        if self._next_page_to_render >= self.page_grid.count():
            self.render_timer.stop()
            self.selection_status.setText(self._selection_summary(ready=True))
            self.ok_button.setEnabled(True)
            return

        page_index = self._next_page_to_render
        self._next_page_to_render += 1
        try:
            image = self._render_page(page_index)
        except RuntimeError as error:
            self.render_timer.stop()
            QMessageBox.critical(self, "Preview unavailable", str(error))
            self.reject()
            return

        self._base_thumbnails[page_index] = image
        self._update_thumbnail_visual(page_index)
        self.selection_status.setText(
            f"Preparing previews… {self._next_page_to_render}/{self.page_grid.count()}"
        )

    def _render_page(self, page_index: int) -> QPixmap:
        page_size = self.document.pagePointSize(page_index)
        if page_size.width() <= 0 or page_size.height() <= 0:
            raise RuntimeError(f"Could not read the dimensions of page {page_index + 1}.")

        scale = min(140 / page_size.width(), 186 / page_size.height())
        render_size = QSize(
            max(1, round(page_size.width() * scale)),
            max(1, round(page_size.height() * scale)),
        )
        page_image = self.document.render(page_index, render_size)
        if page_image.isNull():
            raise RuntimeError(f"Could not render page {page_index + 1}.")

        thumbnail = QPixmap(150, 200)
        thumbnail.fill(Qt.GlobalColor.white)
        painter = QPainter(thumbnail)
        x = (thumbnail.width() - page_image.width()) // 2
        y = (thumbnail.height() - page_image.height()) // 2
        painter.drawImage(x, y, page_image)
        painter.setPen(QPen(Qt.GlobalColor.lightGray))
        painter.drawRect(0, 0, thumbnail.width() - 1, thumbnail.height() - 1)
        painter.end()
        return thumbnail

    def _toggle_page_selection(self, item: QListWidgetItem) -> None:
        page_index = self.page_grid.row(item)
        selected = not bool(item.data(Qt.ItemDataRole.UserRole))
        if not self.multi_select and selected:
            for index in range(self.page_grid.count()):
                other = self.page_grid.item(index)
                if other is not item:
                    other.setData(Qt.ItemDataRole.UserRole, False)
                    self._update_thumbnail_visual(index)
        item.setData(Qt.ItemDataRole.UserRole, selected)
        self._update_thumbnail_visual(page_index)
        self._update_selection_status()

    def _set_all_checked(self, checked: bool) -> None:
        for index in range(self.page_grid.count()):
            self.page_grid.item(index).setData(Qt.ItemDataRole.UserRole, checked)
            self._update_thumbnail_visual(index)
        self._update_selection_status()

    def _update_thumbnail_visual(self, page_index: int) -> None:
        thumbnail = self._base_thumbnails.get(page_index)
        if thumbnail is None:
            return

        selected = bool(
            self.page_grid.item(page_index).data(Qt.ItemDataRole.UserRole)
        )
        tinted = thumbnail.copy()
        if selected:
            color = QColor("#e53935" if self.multi_select else "#34a853")
            painter = QPainter(tinted)
            painter.fillRect(tinted.rect(), QColor(color.red(), color.green(), color.blue(), 88))
            painter.setPen(QPen(color, 5))
            painter.drawRect(2, 2, tinted.width() - 5, tinted.height() - 5)

            badge_center_x = tinted.width() - 17
            badge_center_y = 17
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(badge_center_x - 12, badge_center_y - 12, 24, 24)
            painter.setPen(QPen(Qt.GlobalColor.white, 2))
            painter.drawLine(
                badge_center_x - 5,
                badge_center_y,
                badge_center_x - 1,
                badge_center_y + 4,
            )
            painter.drawLine(
                badge_center_x - 1,
                badge_center_y + 4,
                badge_center_x + 6,
                badge_center_y - 5,
            )
            painter.end()

        self.page_grid.item(page_index).setIcon(QIcon(tinted))

    def _selection_summary(self, *, ready: bool) -> str:
        count = len(self.selected_pages)
        noun = "page" if count == 1 else "pages"
        prefix = "Previews ready" if ready else "Preparing previews"
        return f"{prefix} · {count} {noun} selected"

    def _update_selection_status(self) -> None:
        ready = self._next_page_to_render >= self.page_grid.count()
        self.selection_status.setText(self._selection_summary(ready=ready))

    def _close_document(self) -> None:
        self.render_timer.stop()
        self.document.close()
        self.document.deleteLater()


class PdfSplitterWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PDF Split! v0.3 by Tasos Rizopoulos 2026")
        self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.resize(760, 790)
        self.setAcceptDrops(True)
        self.source_path: Path | None = None
        self.page_count = 0
        self.target_folder: Path | None = None
        self.selected_delete_pages: set[int] = set()

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(34, 28, 34, 26)
        root.setSpacing(16)

        eyebrow = QLabel("PDF TOOLS  /  LOCAL & PRIVATE")
        eyebrow.setObjectName("eyebrow")
        root.addWidget(eyebrow)

        title_row = QHBoxLayout()
        title_icon = QLabel()
        title_icon.setObjectName("appIcon")
        title_icon.setPixmap(QIcon(str(APP_ICON_PATH)).pixmap(QSize(52, 52)))
        title_icon.setFixedSize(52, 52)
        title_row.addWidget(title_icon)
        title = QLabel("PDF splitter")
        title.setObjectName("title")
        title_row.addWidget(title)
        title_row.addStretch(1)
        root.addLayout(title_row)

        subtitle = QLabel("Split, extract, or remove pages without rasterizing your PDF.")
        subtitle.setObjectName("subtitle")
        root.addWidget(subtitle)

        self.drop_zone = QFrame()
        self.drop_zone.setObjectName("dropZone")
        drop_layout = QHBoxLayout(self.drop_zone)
        drop_layout.setContentsMargins(20, 16, 20, 16)
        drop_text_layout = QVBoxLayout()
        self.drop_title = QLabel("Drop a PDF here")
        self.drop_title.setStyleSheet("font-size: 12pt; font-weight: 650;")
        drop_hint = QLabel("or choose a file from your computer")
        drop_hint.setObjectName("muted")
        drop_text_layout.addWidget(self.drop_title)
        drop_text_layout.addWidget(drop_hint)
        drop_layout.addLayout(drop_text_layout, 1)
        self.open_button = QPushButton("Choose PDF")
        self.open_button.clicked.connect(self.choose_pdf)
        drop_layout.addWidget(self.open_button)
        root.addWidget(self.drop_zone)

        self.file_card = QFrame()
        self.file_card.setObjectName("fileCard")
        file_layout = QHBoxLayout(self.file_card)
        file_layout.setContentsMargins(14, 10, 14, 10)
        self.file_label = QLabel("No PDF loaded")
        self.file_label.setObjectName("muted")
        file_layout.addWidget(self.file_label, 1)
        self.clear_button = QPushButton("Remove")
        self.clear_button.clicked.connect(self.clear_pdf)
        file_layout.addWidget(self.clear_button)
        self.file_card.hide()
        root.addWidget(self.file_card)

        section_label = QLabel("Choose an action")
        section_label.setStyleSheet("font-weight: 650;")
        root.addWidget(section_label)

        self.action_group = QButtonGroup(self)
        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        self.action_buttons: list[QToolButton] = []
        for index, text in enumerate(("Split pages", "Extract one", "Delete pages")):
            button = QToolButton()
            button.setText(text)
            button.setCheckable(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            self.action_group.addButton(button, index)
            self.action_buttons.append(button)
            action_row.addWidget(button)
        self.action_buttons[0].setChecked(True)
        self.action_group.idClicked.connect(self._select_action)
        root.addLayout(action_row)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._make_split_panel())
        self.pages.addWidget(self._make_extract_panel())
        self.pages.addWidget(self._make_delete_panel())
        root.addWidget(self.pages, 1)

        footer = QHBoxLayout()
        self.status_label = QLabel("Load a PDF to get started.")
        self.status_label.setObjectName("muted")
        footer.addWidget(self.status_label, 1)
        self.run_button = QPushButton("Split into PDFs")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self.run_action)
        self.run_button.setEnabled(False)
        footer.addWidget(self.run_button)
        root.addLayout(footer)

        self._select_action(0)

    def _make_split_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        heading = QLabel("Create a separate PDF for each selected page")
        heading.setStyleSheet("font-weight: 650;")
        layout.addWidget(heading)

        self.split_all = QRadioButton("All pages")
        self.split_odd = QRadioButton("Odd pages")
        self.split_even = QRadioButton("Even pages")
        self.split_all.setChecked(True)
        radio_row = QHBoxLayout()
        for radio in (self.split_all, self.split_odd, self.split_even):
            radio_row.addWidget(radio)
        radio_row.addStretch(1)
        layout.addLayout(radio_row)

        self.split_folder_label = self._add_folder_picker(layout, "Output folder")
        layout.addStretch(1)
        return panel

    def _make_extract_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        heading = QLabel("Extract one page to its own PDF")
        heading.setStyleSheet("font-weight: 650;")
        layout.addWidget(heading)

        page_row = QHBoxLayout()
        page_row.addWidget(QLabel("Page number"))
        self.extract_spin = QSpinBox()
        self.extract_spin.setMinimum(1)
        self.extract_spin.setMaximum(1)
        self.extract_spin.setEnabled(False)
        page_row.addWidget(self.extract_spin)
        self.extract_preview_button = QPushButton("Choose with previews…")
        self.extract_preview_button.clicked.connect(self.choose_extract_page)
        self.extract_preview_button.setEnabled(False)
        page_row.addWidget(self.extract_preview_button)
        page_row.addStretch(1)
        layout.addLayout(page_row)

        self.extract_folder_label = self._add_folder_picker(layout, "Output folder")
        layout.addStretch(1)
        return panel

    def _make_delete_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        heading = QLabel("Choose pages to remove")
        heading.setStyleSheet("font-weight: 650;")
        layout.addWidget(heading)
        hint = QLabel("Review page thumbnails and select one or more pages in the preview window.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.delete_preview_button = QPushButton("Choose pages with previews…")
        self.delete_preview_button.clicked.connect(self.choose_delete_pages)
        self.delete_preview_button.setEnabled(False)
        layout.addWidget(self.delete_preview_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.delete_selection_label = QLabel("No pages selected")
        self.delete_selection_label.setObjectName("muted")
        self.delete_selection_label.setWordWrap(True)
        layout.addWidget(self.delete_selection_label)
        layout.addStretch(1)

        self.delete_folder_label = self._add_folder_picker(layout, "Save updated PDF in")
        return panel

    def _add_folder_picker(self, layout: QVBoxLayout, title: str) -> QLabel:
        layout.addWidget(QLabel(title))
        row = QHBoxLayout()
        folder_label = QLabel("Choose a target folder")
        folder_label.setObjectName("muted")
        folder_label.setWordWrap(True)
        row.addWidget(folder_label, 1)
        button = QPushButton("Browse…")
        button.clicked.connect(self.choose_folder)
        row.addWidget(button)
        layout.addLayout(row)
        return folder_label

    def _select_action(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        labels = ("Split into PDFs", "Extract page", "Delete selected pages")
        self.run_button.setText(labels[index])

    def choose_pdf(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Choose a PDF",
            "",
            "PDF files (*.pdf)",
        )
        if filename:
            self.load_pdf(Path(filename))

    def load_pdf(self, path: Path) -> None:
        try:
            count = get_page_count(path)
        except ValueError as error:
            QMessageBox.warning(self, "Cannot open PDF", str(error))
            return
        except (OSError, pikepdf.PdfError) as error:
            QMessageBox.critical(self, "Cannot open PDF", str(error))
            return

        if count < 1:
            QMessageBox.warning(self, "Cannot open PDF", "This PDF has no pages.")
            return

        self.source_path = path
        self.page_count = count
        self.target_folder = path.parent
        self.file_label.setText(f"{path.name}  ·  {count} page{'s' if count != 1 else ''}")
        self.drop_title.setText("PDF loaded — drop another one to replace it")
        self.file_card.show()
        self.run_button.setEnabled(True)
        self.extract_spin.setMaximum(count)
        self.extract_spin.setEnabled(True)
        self.extract_preview_button.setEnabled(True)
        self.delete_preview_button.setEnabled(True)
        self.selected_delete_pages.clear()
        self._update_delete_selection_label()
        self._update_folder_labels()
        self.status_label.setText(f"Ready to work with {count} pages.")

    def clear_pdf(self) -> None:
        self.source_path = None
        self.page_count = 0
        self.target_folder = None
        self.file_card.hide()
        self.drop_title.setText("Drop a PDF here")
        self.run_button.setEnabled(False)
        self.extract_spin.setEnabled(False)
        self.extract_preview_button.setEnabled(False)
        self.delete_preview_button.setEnabled(False)
        self.selected_delete_pages.clear()
        self._update_delete_selection_label()
        for label in (
            self.split_folder_label,
            self.extract_folder_label,
            self.delete_folder_label,
        ):
            label.setText("Choose a target folder")
        self.status_label.setText("Load a PDF to get started.")

    def choose_extract_page(self) -> None:
        if self.source_path is None:
            return
        try:
            dialog = PageSelectionDialog(
                self.source_path,
                self.page_count,
                multi_select=False,
                selected_pages={self.extract_spin.value() - 1},
                parent=self,
            )
        except ValueError as error:
            QMessageBox.critical(self, "Page previews unavailable", str(error))
            return
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_pages:
            self.extract_spin.setValue(min(dialog.selected_pages) + 1)

    def choose_delete_pages(self) -> None:
        if self.source_path is None:
            return
        try:
            dialog = PageSelectionDialog(
                self.source_path,
                self.page_count,
                multi_select=True,
                selected_pages=self.selected_delete_pages,
                parent=self,
            )
        except ValueError as error:
            QMessageBox.critical(self, "Page previews unavailable", str(error))
            return
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.selected_delete_pages = dialog.selected_pages
            self._update_delete_selection_label()
            if self.selected_delete_pages:
                self.run_action()
            else:
                QMessageBox.information(
                    self,
                    "No pages selected",
                    "Select the pages you want to remove.",
                )

    def _update_delete_selection_label(self) -> None:
        page_numbers = sorted(page + 1 for page in self.selected_delete_pages)
        if not page_numbers:
            self.delete_selection_label.setText("No pages selected")
            return
        shown = ", ".join(str(page) for page in page_numbers[:8])
        remaining = len(page_numbers) - 8
        suffix = f", and {remaining} more" if remaining > 0 else ""
        noun = "page" if len(page_numbers) == 1 else "pages"
        self.delete_selection_label.setText(
            f"{len(page_numbers)} {noun} selected: {shown}{suffix}"
        )

    def choose_folder(self) -> None:
        start = str(self.target_folder) if self.target_folder else ""
        folder = QFileDialog.getExistingDirectory(self, "Choose an output folder", start)
        if folder:
            self.target_folder = Path(folder)
            self._update_folder_labels()

    def _update_folder_labels(self) -> None:
        text = str(self.target_folder) if self.target_folder else "Choose a target folder"
        for label in (
            self.split_folder_label,
            self.extract_folder_label,
            self.delete_folder_label,
        ):
            label.setText(text)

    def run_action(self) -> None:
        if self.source_path is None:
            return
        if self.target_folder is None or not self.target_folder.is_dir():
            QMessageBox.warning(self, "Choose a folder", "Choose an existing output folder first.")
            return

        action = self.action_group.checkedId()
        try:
            if action == 0:
                self._split_pages()
            elif action == 1:
                self._extract_page()
            else:
                if not self.selected_delete_pages:
                    self.choose_delete_pages()
                else:
                    self._delete_pages()
        except (OSError, ValueError, pikepdf.PdfError) as error:
            QMessageBox.critical(self, "Could not create PDF", str(error))
            self.status_label.setText("The operation failed.")

    def _split_pages(self) -> None:
        if self.split_odd.isChecked():
            selection = "odd"
        elif self.split_even.isChecked():
            selection = "even"
        else:
            selection = "all"
        page_indices = pages_for_selection(self.page_count, selection)
        if not page_indices:
            QMessageBox.information(
                self,
                "No matching pages",
                f"There are no {selection} pages in this PDF.",
            )
            return
        outputs = [
            self.target_folder / f"{self.source_path.stem}_page_{index + 1:04d}.pdf"
            for index in page_indices
        ]
        if not self._confirm_replacements(outputs):
            return

        split_pages(self.source_path, self.target_folder, page_indices)
        self._show_success(f"Created {len(outputs)} single-page PDFs in {self.target_folder}.")

    def _extract_page(self) -> None:
        page_number = self.extract_spin.value()
        output = self.target_folder / f"{self.source_path.stem}_page_{page_number:04d}.pdf"
        if not self._confirm_replacements([output]):
            return
        write_pages(self.source_path, output, (page_number - 1,))
        self._show_success(f"Extracted page {page_number} to {output.name}.")

    def _delete_pages(self) -> None:
        selected = sorted(self.selected_delete_pages)
        if not selected:
            QMessageBox.information(self, "No pages selected", "Check the pages you want to remove.")
            return
        selected_set = set(selected)
        remaining = [
            index for index in range(self.page_count) if index not in selected_set
        ]
        if not remaining:
            QMessageBox.warning(
                self,
                "Keep at least one page",
                "A PDF must contain at least one page. Leave one page unchecked.",
            )
            return

        output = self.target_folder / f"{self.source_path.stem}_without_selected_pages.pdf"
        if not self._confirm_replacements([output]):
            return
        write_pages(self.source_path, output, remaining)
        self.selected_delete_pages.clear()
        self._update_delete_selection_label()
        self._show_success(f"Saved the updated PDF as {output.name}. The source was not changed.")

    def _confirm_replacements(self, outputs: list[Path]) -> bool:
        existing = [output.name for output in outputs if output.exists()]
        if not existing:
            return True

        names = "\n".join(existing[:5])
        remainder = len(existing) - 5
        if remainder > 0:
            names += f"\n…and {remainder} more"
        answer = QMessageBox.question(
            self,
            "Replace existing files?",
            f"The following output file(s) already exist and will be replaced:\n\n{names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _show_success(self, message: str) -> None:
        self.status_label.setText(message)
        QMessageBox.information(self, "Done", message)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls() and any(
            url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf")
            for url in event.mimeData().urls()
        ):
            self.drop_zone.setProperty("dragging", True)
            self.drop_zone.style().unpolish(self.drop_zone)
            self.drop_zone.style().polish(self.drop_zone)
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self.drop_zone.setProperty("dragging", False)
        self.drop_zone.style().unpolish(self.drop_zone)
        self.drop_zone.style().polish(self.drop_zone)
        event.accept()

    def dropEvent(self, event) -> None:
        self.drop_zone.setProperty("dragging", False)
        self.drop_zone.style().unpolish(self.drop_zone)
        self.drop_zone.style().polish(self.drop_zone)
        for url in event.mimeData().urls():
            if url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf"):
                self.load_pdf(Path(url.toLocalFile()))
                event.acceptProposedAction()
                return
        event.ignore()


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    dark_mode = is_windows_dark_mode()
    app.setStyleSheet(stylesheet_for_theme(dark_mode))

    theme_timer = QTimer(app)
    theme_timer.setInterval(2000)

    def refresh_theme() -> None:
        nonlocal dark_mode
        updated_dark_mode = is_windows_dark_mode()
        if updated_dark_mode != dark_mode:
            dark_mode = updated_dark_mode
            app.setStyleSheet(stylesheet_for_theme(dark_mode))

    theme_timer.timeout.connect(refresh_theme)
    theme_timer.start()

    window = PdfSplitterWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

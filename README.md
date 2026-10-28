# PDF Splitter

A small Windows desktop app for splitting a PDF into single-page files, extracting one page, or removing selected pages.

## Run

Requires Python 3.10 or later.

```powershell
python -m pip install -r requirements.txt
python pdf_splitter.py
```

## Build a Windows executable

Install PyInstaller in the same Python environment, then build the windowed distributable folder with the multi-resolution Windows icon:

```powershell
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean PDFSplitter.spec
```

The distributable is written to `dist\PDFSplitter\`. Run `dist\PDFSplitter\PDFSplitter.exe` and keep the entire folder together when moving or sharing the app. This folder-based build avoids the repeated extraction performed by a one-file executable, so it should open faster.

Drag a PDF into the window or use **Choose PDF**. Select an action, choose the pages and output folder, then run it. In the extraction preview, the selected page is tinted green and **OK** copies its number into the page field. In the deletion preview, click thumbnails to toggle a red tint; **OK** immediately creates the updated PDF. The split action defaults to **All pages** and also supports odd-only and even-only output.

The UI follows the Windows app-mode setting (light or dark) and updates automatically if that setting changes while the app is open.

The app works locally. It copies PDF page objects rather than rendering pages to images, preserving vector content and page-level resources such as transparency. The source PDF is never modified; removing pages creates a separate output file. Existing output files are replaced only after confirmation. Password-protected PDFs are not supported.

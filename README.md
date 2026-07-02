# PDF Guide

[![GitHub repo](https://img.shields.io/badge/GitHub-Flinterpop%2FPDF__Guide-181717?logo=github)](https://github.com/Flinterpop/PDF_Guide)
![Platform](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)
![GUI](https://img.shields.io/badge/GUI-Tkinter-FFD43B)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A small desktop app (Tkinter) that lets you browse PDFs by topic.

- **Left pane** — lists every PDF in a subfolder (default `./pdfs`).
- **Middle pane** — when you select a PDF, shows the topics and page numbers from
  its companion metadata file (same base name, `.toc` or `.json`).
- **Right pane** — an embedded viewer. Click a topic and the PDF jumps to that page.
- **Drag & drop** — drop a PDF anywhere on the window to file it into an
  `inbox` subfolder with an auto-generated topics file.

## Install

```
pip install -r requirements.txt
```

(That pulls in **PyMuPDF** for rendering and **Pillow** for displaying pages.)

## Run

```
python app.py            # uses the ./pdfs subfolder
python app.py C:\docs    # or point it at any folder
```

You can also switch folders at runtime with the **Choose folder…** button.

## Standalone build & installer (Windows)

Build the one-file exe, then compile the installer:

```
python -m PyInstaller PDFGuide.spec        # -> dist\PDFGuide.exe
iscc installer.iss                         # -> installer\PDFGuide-Setup.exe
```

`PDFGuide-Setup.exe` is a per-user installer (no admin rights needed): it
installs the app, adds Start-Menu (and optional desktop) shortcuts, and
registers an uninstaller. Point the app at your own PDF folder with
**Choose folder…** after installing.

## Metadata files

Each PDF gets a companion file with the **same base name** and a different
extension. `.toc` is checked first, then `.json`.

`mybook.pdf` → `mybook.toc`:

```
# comments start with '#'
Introduction: 1
Chapter 1 - Setup: 5
Advanced Topics: 42
```

The page is the trailing number, so topics may contain colons and dashes
(`Chapter 1 - Setup: 5` works fine).

Or `mybook.json`:

```json
[
  {"topic": "Introduction", "page": 1},
  {"topic": "Chapter 1 - Setup", "page": 5}
]
```

Page numbers are **1-based** (page 1 = the first page).

## Notes

- PDFs are grouped by subfolder under the top-level folder. Subfolders **start
  collapsed**, and the app **remembers which folders you left open/closed** for
  next time. (While a search filter is active, folders open automatically to
  reveal matches.)
- **Search box** above the list filters PDFs by filename as you type (`✕`
  clears it).
- **Right-click** a PDF for **Open PDF** / **Reveal in Explorer**; right-click a
  folder to open it in Explorer.
- The app remembers the **last page you were on in each PDF** and returns there
  when you reopen it.
- A PDF without a metadata file is still listed (marked `(no metadata)`) and
  viewable — you just won't get the topic list. **Refresh** (button or `F5`)
  offers to **auto-build topic lists** for any PDFs that don't have one, using
  each PDF's bookmarks — or its text headings when there are no bookmarks.
- **Drop PDFs onto the window** (from Explorer, Outlook attachments saved to
  disk, etc.) and they are **copied into an `inbox` subfolder** of the current
  folder, a **`.toc` topics file is auto-generated** for each (bookmarks first,
  text headings as a fallback), and the last one dropped is selected and
  opened. Dropping a PDF whose name is already in the inbox asks before
  replacing it, and an existing (hand-edited) `.toc` is never overwritten.
- Viewer controls: **Prev/Next**, **+/−** zoom, **Fit width**, **Full page**,
  and mouse-wheel scrolling. Your **Fit width / Full page** choice is remembered
  and re-applied to every PDF you open — and it persists across app runs
  (saved to `%APPDATA%\PDFGuide\config.json`). Manual **+/−** zoom is a temporary
  override that doesn't change the saved preference.
- The app also remembers your **window size/position** and **re-opens the last
  PDF** you were viewing on the next launch (same config file).
- The mouse wheel scrolls within the page and **flips to the next/previous page
  when you scroll past the bottom/top edge**.

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `←` / `Page Up` | Previous page |
| `→` / `Page Down` / `Space` | Next page |
| `Home` / `End` | First / last page |
| `+` / `=` / `−` | Zoom in / out |
| `W` | Fit width |
| `P` | Full page |
| `F5` | Refresh PDF list |

Arrow, space, and page keys defer to the PDF/topic lists while one of them has
keyboard focus, so you can still navigate the lists with the keyboard.

## License

Released under the [MIT License](LICENSE).

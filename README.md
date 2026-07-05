# PDF Sherpa

[![GitHub repo](https://img.shields.io/badge/GitHub-Flinterpop%2FPDF__Sherpa-181717?logo=github)](https://github.com/Flinterpop/PDF_Sherpa)
![Platform](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)
![GUI](https://img.shields.io/badge/GUI-Tkinter-FFD43B)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A small desktop app (Tkinter) that lets you browse PDFs by topic.

- **Left pane** — lists every PDF in a subfolder (default `./pdfs`).
- **Middle pane** — when you select a PDF, shows the topics and page numbers from
  its companion metadata file (same base name, `.toc` or `.json`).
- **Right pane** — an embedded viewer. Click a topic and the PDF jumps to that page.
- **Search everywhere** — filter the PDF list by name, filter the topic list,
  and full-text search inside the open PDF with highlighted matches.
- **Highlight text** — drag-select words on the page and save them as real PDF
  highlight annotations, into the original or an `(ann)` copy.
- **Drag & drop** — drop a PDF anywhere on the window to file it into an
  `inbox` subfolder with an auto-generated topics file.

## Screenshot
<img width="1427" height="1209" alt="image" src="https://github.com/user-attachments/assets/63af4bb8-e27c-4956-ace1-ff0c47cd110b" />


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

## Installing (Windows)

Download `PDFSherpa-Setup.exe` from the
[latest release](https://github.com/Flinterpop/PDF_Sherpa/releases/latest).
It is a per-user installer (no admin rights needed): it installs the app, adds
Start-Menu (and optional desktop) shortcuts, and registers an uninstaller.
Point the app at your own PDF folder with **Choose folder…** after installing.

## Standalone build & installer (Windows)

Build the one-file exe, then compile the installer:

```
python -m PyInstaller PDFSherpa.spec       # -> dist\PDFSherpa.exe
iscc installer.iss                         # -> installer\PDFSherpa-Setup.exe
```

The compiled installer is not committed to the repo -- publish it as a GitHub
Release asset:

```
gh release create v<version> installer\PDFSherpa-Setup.exe
```

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
- **Search boxes** in every pane (`✕` clears): the PDF list filters by
  filename, the Topics pane filters the topic list, and the viewer's box
  searches the **text of the open PDF** — matches highlight in yellow with a
  live `2 / 17` counter, `Enter`/`F3` steps forward, `Shift+Enter`/`Shift+F3`
  back, `Ctrl+F` focuses the box. The scan runs in background chunks, so even
  a 9000-page document stays responsive while it searches.
- **Highlight text**: drag across text in the viewer (words shade blue), then
  click **Highlight** or right-click → *Highlight selection*. **Save**
  (`Ctrl+S`) offers an annotated copy — `manual.pdf` → `manual(ann).pdf`, with
  the topics file copied along — or writes into the original file. Right-click
  an existing highlight to remove it. Highlights are standard PDF annotations,
  visible in any viewer.
- **PDFs / Topics** toolbar toggles collapse the left and middle panes — hide
  both for a full-width reading view. The choice persists across runs.
- **Full page** fits the whole page and resizes the window to hug it; dragging
  a window edge or corner then zooms the page to follow. Selecting a different
  PDF never moves the window.
- The **title bar** shows the app version and the current folder; the **Help**
  button opens the rendered user guide, and hovering the less obvious buttons
  shows a tooltip.
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
| `Ctrl+F` | Focus the content search box |
| `Ctrl+S` | Save highlights to the PDF |
| `F3` / `Shift+F3` | Next / previous search match |
| `Enter` / `Shift+Enter` (in search box) | Next / previous search match |
| `F5` | Refresh PDF list |

Arrow, space, and page keys defer to the PDF/topic lists while one of them has
keyboard focus, so you can still navigate the lists with the keyboard.

## License

Released under the [MIT License](LICENSE).

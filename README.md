# PDF Sherpa

[![GitHub repo](https://img.shields.io/badge/GitHub-Flinterpop%2FPDF__Sherpa-181717?logo=github)](https://github.com/Flinterpop/PDF_Sherpa)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-0078D6)
![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white)
![GUI](https://img.shields.io/badge/GUI-Tkinter-FFD43B)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A small desktop app (Tkinter) that lets you browse PDFs by topic.

- **Left pane** — lists every PDF in a folder (the last folder you chose, or
  a `./pdfs` subfolder by default).
- **Middle pane** — when you select a PDF, shows the topics and page numbers from
  its companion metadata file (same base name, `.toc` or `.json`), with your
  own bookmarks in a resizable list above them.
- **Right pane** — an embedded viewer. Click a topic and the PDF jumps to that page.
- **Search everywhere** — filter the PDF list by name, filter the topic list,
  and full-text search inside the open PDF with highlighted matches.
- **Highlight text** — drag-select words on the page and save them as real PDF
  highlight annotations, into the original or an `(ann)` copy.
- **Bookmarks** — mark pages with your own names (`Ctrl+B`); they show in
  their own list above the Topics and are saved beside the PDF in
  `name.bookmarks.json`. PDFs that have bookmarks are shown in **blue** in the
  list, so you can spot them at a glance.
- **Drag & drop** (Windows) — drop a PDF anywhere on the window to file it into
  an `inbox` subfolder with an auto-generated topics file. On Linux/macOS, copy
  PDFs into the folder and press Refresh instead.

## Screenshot
<img width="1427" height="1209" alt="image" src="https://github.com/user-attachments/assets/63af4bb8-e27c-4956-ace1-ff0c47cd110b" />


## Install

```
pip install -r requirements.txt
```

(That pulls in **PyMuPDF** for rendering and **Pillow** for displaying pages.)

## Run

```
python app.py            # last chosen folder (or the ./pdfs subfolder)
python app.py C:\docs    # or point it at any folder
```

You can also switch folders at runtime with the **Choose folder…** button —
the chosen folder is remembered and reopened on the next launch (a
command-line folder overrides it).

## Installing (Windows)

Grab either flavor from the
[latest release](https://github.com/Flinterpop/PDF_Sherpa/releases/latest):

- **`PDFSherpa-Setup.exe`** — a per-user installer (no admin rights needed):
  it installs the app, adds Start-Menu (and optional desktop) shortcuts, and
  registers an uninstaller.
- **`PDFSherpa-Portable.zip`** — no install at all: unzip `PDFSherpa.exe`
  anywhere (a folder, a USB stick) and run it. Settings still live in
  `%APPDATA%\PDFGuide\config.json`.

Point the app at your own PDF folder with **Choose folder…** after installing.

The app **checks for updates at launch** (quietly, in the background) and
offers to download and apply a newer release in place — the installed copy
re-runs the installer silently, the portable copy swaps its own exe — or to
skip that version (`"skip_version"` in the config file). A manual **Check for
updates** button lives at the bottom of the Help window. To disable the launch
check, add `"check_updates": false` to `%APPDATA%\PDFGuide\config.json`.

## Installing (Linux)

The easiest way — grab the **`PDFSherpa-x86_64.AppImage`** from the
[latest release](https://github.com/Flinterpop/PDF_Sherpa/releases/latest).
It bundles Python, Tcl/Tk, PyMuPDF and Pillow, so there's nothing to install:

```
chmod +x PDFSherpa-x86_64.AppImage
./PDFSherpa-x86_64.AppImage
```

It needs a 64-bit desktop with FUSE 3 (standard on Ubuntu 22.04+, Fedora,
etc.) and a glibc at least as new as the build host's.

The AppImage **updates itself**: on launch it checks the releases and, when a
newer version is available, offers to download it and replace the running
AppImage in place, then relaunch. Update information is embedded and a
companion `.zsync` is published, so external tools (AppImageUpdate, appimaged)
can update it too.

To add it to your application menu, from a clone of this repo run:

```
./install-linux.sh --appimage                 # auto-finds the AppImage in
                                              #   ./dist or ~/Applications
./install-linux.sh --appimage ~/Downloads/PDFSherpa-x86_64.AppImage
```

This copies the AppImage into `~/Applications/` (behind a version-independent
`PDFSherpa.AppImage` symlink), installs the icon, and writes the `.desktop`
entry; `./install-linux.sh --remove` takes it back out. Alternatively, open the
AppImage once with [Gear Lever](https://flathub.org/apps/it.mijorus.gearlever)
or AppImageLauncher, which also handle menu integration and updates.

## Running from source (Linux / macOS)

PDF Sherpa is a Tkinter app and also runs from source on Linux and macOS. A
helper script sets everything up on first launch:

```
./run.sh                 # last-used folder (or ./pdfs)
./run.sh ~/Documents     # open a specific folder
```

On its first run `run.sh` creates a local `.venv`, installs **PyMuPDF** and
**Pillow** into it, and then launches the app; later runs just launch. You need
Python 3.9+ with Tkinter — Tkinter ships separately on many distros:

- Debian/Ubuntu: `sudo apt install python3-tk`
- Fedora: `sudo dnf install python3-tkinter`
- Arch: `sudo pacman -S tk`

To add PDF Sherpa to your application menu (a per-user `.desktop` entry, no
root needed) that launches this source checkout via `run.sh`:

```
./install-linux.sh            # menu entry that runs from source
./install-linux.sh --appimage # ...or one that runs the bundled AppImage
./install-linux.sh --remove   # remove it
```

Settings live in `~/.config/PDFGuide/config.json` (following the XDG spec).
Platform notes: **Open in default viewer** uses `xdg-open` (Linux) / `open`
(macOS), and **Show in file manager** selects the file via the freedesktop
FileManager1 D-Bus interface, falling back to opening its folder. Drag-and-drop
from the file manager is Windows-only; use **Choose folder…** or drop files
into the folder directly. A source run doesn't self-update — `git pull` to
upgrade — but the **AppImage build updates itself** (see below).

## Building the AppImage (Linux)

To produce the bundled `PDFSherpa-x86_64.AppImage` yourself:

```
./build-appimage.sh        # -> dist/PDFSherpa-x86_64.AppImage (+ .zsync)
```

It freezes the app with PyInstaller (pulling in Tcl/Tk, PyMuPDF and Pillow),
assembles an AppDir, and packs it with `appimagetool` using the statically
linked type2 runtime (so the result runs on FUSE-3-only systems). It also
embeds AppImage update information and writes a companion `.zsync`, so the
built AppImage self-updates from the GitHub `latest` release (and
AppImageUpdate / appimaged can update it too). The output name is
**version-less** on purpose so `latest` always carries that exact asset —
upload both `PDFSherpa-x86_64.AppImage` and its `.zsync` to the release. Build
tooling and downloads are cached under `build/`; both `build/` and `dist/`
stay out of git. Build on the oldest glibc you want to support — the AppImage
requires a glibc at least as new as the build host's.

## Standalone build & installer (Windows)

To cut a full release in one step (bump versions, build everything, commit,
push, publish the GitHub release, reinstall locally):

```
.\release.ps1 1.3.8                     # notes auto-generated from commits
.\release.ps1 1.3.8 -NotesFile notes.md # or hand-written notes
```

Or do the steps by hand — build the one-file exe, then compile the installer
and zip the portable variant:

```
python -m PyInstaller PDFSherpa.spec       # -> dist\PDFSherpa.exe
iscc installer.iss                         # -> installer\PDFSherpa-Setup.exe
powershell Compress-Archive -Force dist\PDFSherpa.exe installer\PDFSherpa-Portable.zip
```

The compiled artifacts are not committed to the repo -- publish them as GitHub
Release assets (both names are what the in-app updater looks for, so keep
them exact):

```
gh release create v<version> installer\PDFSherpa-Setup.exe installer\PDFSherpa-Portable.zip
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
  the topics and bookmarks files copied along — or writes into the original
  file. Right-click
  an existing highlight to remove it. Highlights are standard PDF annotations,
  visible in any viewer.
- **Bookmarks**: press `Ctrl+B` (or the **🔖** button, or right-click the page)
  to bookmark the current page under a name of your choice. Bookmarks get
  their own list above the Topics (shown only when the PDF has bookmarks; it
  starts at a quarter of the pane and the divider is draggable, with the
  position remembered across runs) — click to jump, right-click to rename or
  delete. They live in a `name.bookmarks.json` sidecar next to the PDF, so
  they travel with the folder and can be hand-edited; an `(ann)` copy gets the
  sidecar copied along too. PDFs that have bookmarks show their name in **blue**
  in the PDF list (the colour updates live as you add the first bookmark or
  delete the last one).
- **PDFs / Topics and Bookmarks** toolbar toggles collapse the left and middle
  panes — hide both for a full-width reading view. The choice persists across
  runs.
- **Full page** fits the whole page and resizes the window to hug it; dragging
  a window edge or corner then zooms the page to follow. Selecting a different
  PDF never moves the window.
- The **title bar** shows the app version and the current folder; the **Help**
  button opens the rendered user guide, and hovering the less obvious buttons
  shows a tooltip.
- **Right-click** a PDF for **Open PDF** / **Show in file manager** (*Reveal in
  Explorer* on Windows, *Reveal in Finder* on macOS); right-click a folder to
  open it in your file manager.
- The app remembers the **last page you were on in each PDF** and returns there
  when you reopen it (positions are kept for the 200 most recently viewed
  PDFs, so the settings file never grows without bound).
- A PDF without a metadata file is still listed (marked `(no metadata)`) and
  viewable — you just won't get the topic list. **Refresh** (button or `F5`)
  offers to **auto-build topic lists** for any PDFs that don't have one, using
  each PDF's built-in outline bookmarks — or its text headings when there are
  none. (These built-in bookmarks are separate from your own `Ctrl+B`
  bookmarks.)
- **Drop PDFs onto the window** (Windows only — from Explorer, Outlook
  attachments saved to disk, etc.) and they are **copied into an `inbox`
  subfolder** of the current folder, a **`.toc` topics file is auto-generated**
  for each (bookmarks first, text headings as a fallback), and the last one
  dropped is selected and opened. Dropping a PDF whose name is already in the
  inbox asks before replacing it, and an existing (hand-edited) `.toc` is never
  overwritten. On Linux/macOS, copy PDFs into the folder and press **Refresh**
  to get the same auto-generated topics.
- Viewer controls: **Prev/Next**, **+/−** zoom, **Fit width**, **Full page**,
  and mouse-wheel scrolling. Your **Fit width / Full page** choice is remembered
  and re-applied to every PDF you open — and it persists across app runs
  (saved to the config file). Manual **+/−** zoom is a temporary
  override that doesn't change the saved preference.
- The app also remembers your **window size/position**, the **folder you
  chose**, the **bookmarks divider position**, and **re-opens the last PDF**
  you were viewing on the next launch (same config file).
- The mouse wheel scrolls within the page and **flips to the next/previous page
  when you scroll past the bottom/top edge**.

## Settings file

Everything the app remembers lives in one JSON file —
`%APPDATA%\PDFGuide\config.json` on Windows, `~/.config/PDFGuide/config.json`
on Linux/macOS (the folder keeps the app's former name so settings saved
before the rename survive). It is safe to edit while the app is closed, or to
delete for a fresh start.

| Key | Meaning |
|-----|---------|
| `folder` | Last folder chosen with **Choose folder…** |
| `geometry` | Window size and position |
| `last_pdf` | PDF re-opened on the next launch |
| `last_pages` | Last-viewed page per PDF (200 most recent) |
| `favorites` | Pinned PDFs above the search box (10 max, stored relative to the folder root) |
| `expanded_folders` | Subfolders left open in the PDF list |
| `fit_pref` | Viewer fit preference: `"width"` or `"page"` |
| `bm_sash` | Bookmarks/Topics divider position |
| `show_pdf_list`, `show_topics` | Pane visibility toggles |
| `check_updates` | `false` disables the launch update check |
| `skip_version` | Release the update prompt should not re-offer |

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `←` / `Page Up` | Previous page |
| `→` / `Page Down` / `Space` | Next page |
| `Home` / `End` | First / last page |
| `+` / `=` / `−` | Zoom in / out |
| `W` | Fit width |
| `P` | Full page |
| `Ctrl+B` | Bookmark the current page |
| `Ctrl+F` | Focus the content search box |
| `Ctrl+S` | Save highlights to the PDF |
| `F3` / `Shift+F3` | Next / previous search match |
| `Enter` / `Shift+Enter` (in search box) | Next / previous search match |
| `F5` | Refresh PDF list |

Arrow, space, and page keys defer to the PDF/topic lists while one of them has
keyboard focus, so you can still navigate the lists with the keyboard.

## License

Released under the [MIT License](LICENSE).

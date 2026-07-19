# PDF Sherpa — Help

Vibe Coded with Claude Code using Fable 5 

B. Graham - July 2026

PDF Sherpa lets you browse a folder of PDFs **by topic** and read them in a built-in viewer.

## The three panes

- **PDFs** (left) — every PDF found under the current folder, grouped by subfolder. Click one to open it. The search box filters the list as you type.
  Right-click a PDF for **Open PDF** (in your default viewer), **Show in file manager** (labelled *Reveal in Explorer* on Windows / *Reveal in Finder* on macOS), or **Add to favorites**; right-click a folder to open it in your file manager.
  A **Favorites** list sits above the search box: up to 10 pinned PDFs (newest first) that you can open in one click. Each row shows the PDF's path
  relative to the current folder, and favorites are stored that way — so they follow the folder if you move or rename it, and re-point when you switch
  to a different root folder (PDFs outside the current folder are kept as absolute paths). Right-click a
  favorite to open it, reveal it, or remove it. Favorites are remembered across runs, and a favorite that also has bookmarks shows in blue. The **⋯**
  button beside the *Favorites* heading lets you **clear** the list, or **export** it to / **import** it from a JSON file (handy for moving your
  favorites to another machine); importing can either merge with or replace your current list.
- **Topics** (middle) — the selected PDF's topic list. Click a topic to jump straight to that page. The search box filters the topics as you type. If the
  PDF has bookmarks, they appear in their own list above the topics (see **Bookmarks** below).
- **Viewer** (right) — the embedded page view, with a search box that finds text inside the open PDF (see **Searching** below).

The **PDFs** and **Topics** buttons in the toolbar collapse and restore the left and middle panes — turn both off for a full-width reading view. Your
choice is remembered across runs, and hidden panes keep their state (selection, search text) while collapsed.

## Adding PDFs

**Drag and drop** one or more PDF files anywhere onto the window (Windows only). Each is copied into an `inbox` subfolder of the current folder, a topics file is
generated automatically, and the last one is selected and opened for you.

On Linux and macOS, drag-and-drop isn't available — instead copy the PDFs into your folder (or an `inbox` subfolder) directly, or point Sherpa at their
folder with **Choose folder…**, then press **Refresh** (`F5`) to build any missing topics files.

## Topic (.toc) files

Every PDF can have a companion topics file with the same base name — for example `manual.pdf` pairs with `manual.toc`. If a PDF has none, it shows as
`(no metadata)`. Press **Refresh** (or `F5`) and choose to build topic lists:
Sherpa reads each PDF's built-in outline bookmarks (not your own `Ctrl+B` bookmarks), or falls back to detecting headings from the text when there are
none.

A `.toc` is a plain text file you can edit by hand — the page is the trailing number, so topics may contain colons and dashes:

```
# comments start with '#'
Introduction: 1
Chapter 1 - Setup: 5
Advanced Topics: 42
```

Page numbers are **1-based** (page 1 is the first page).

## Bookmarks

Mark your own places in a PDF: press `Ctrl+B` (or the **🔖** button, or right-click the page and choose **Bookmark this page**) to bookmark the page
you're reading. Name it whatever you like — the suggested name is just `Page N`.

Your bookmarks appear in their own **Bookmarks** list above the Topics. Click a bookmark to jump to its page; right-click one to **Rename** or
**Delete** it. The list only appears when the PDF has bookmarks — otherwise the Topics take the full height — and you can drag the divider between
the two lists to resize them (the divider position is remembered across runs). PDFs that have bookmarks are shown in **blue** in the PDF list, so you
can spot them at a glance. These are separate from a PDF's built-in bookmarks, which feed the topic list.

Bookmarks are saved next to the PDF — `manual.pdf` gets `manual.bookmarks.json` — so they travel with the folder and are easy to edit
by hand. Deleting the last bookmark removes the file, and saving highlights as an `(ann)` copy carries the bookmarks along.

## Choosing a folder

Use **Choose folder…** to point Sherpa at any folder of PDFs. Your choice is remembered — the next launch opens the same folder — along with which
subfolders you left open, your window size, and the last PDF you were reading, returning you to the page you left off on. Reading positions are kept
for the 200 PDFs you opened most recently. (Starting the app with a folder on the command line overrides the remembered folder.)

## Searching

Each pane has its own search box:

- **PDFs** — filters the file list by name as you type; folders with no matches are hidden.
- **Topics** — filters the current PDF's topic list as you type.
- **Viewer** — searches the **text of the open PDF**. Matches are highlighted in yellow on the page, with the current match outlined in orange, and the
  counter shows where you are (for example `2 / 17`). Use the **▲ / ▼** buttons — or `Enter` / `Shift+Enter` in the box, or `F3` / `Shift+F3`
  anywhere — to step between matches; stepping wraps around at the end. `Ctrl+F` focuses the box. Searches are case-insensitive.

Press the **✕** button to clear a search. Filters stay applied when you switch PDFs — a content search re-runs against the new document but stays on your
page until you step to a match.

## Highlighting text

Drag across text in the viewer to select it (selected words shade blue), then click **Highlight** in the toolbar — or right-click and choose **Highlight
selection**. Highlights are standard PDF annotations, so they show up in any PDF viewer.

Changes are kept in memory until you save. The **Save** button (or `Ctrl+S`) asks where to put them: **Yes** saves an annotated copy alongside the
original — `manual.pdf` becomes `manual(ann).pdf`, with the topics and bookmarks files copied too — while **No** writes into the original file. Saving while
viewing an `(ann)` copy just updates it, no questions asked. If you switch PDFs or close the app with unsaved highlights, Sherpa asks whether to save
them. To remove a highlight, right-click it and choose **Remove highlight**, then save.

Notes: scanned PDFs without a text layer have nothing to select, and saving highlights into a digitally signed PDF may invalidate its signature (Sherpa
warns first).

## Viewer controls

- **Prev / Next** buttons, or the arrow keys, to page through the document.
- **+ / −** to zoom; **Fit width** and **Full page** to fit the page. Your fit choice is remembered and re-applied when you resize the window.
- The mouse wheel scrolls the page and flips to the next or previous page when you scroll past the bottom or top edge.

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| Left / Page Up | Previous page |
| Right / Page Down / Space | Next page |
| Home / End | First / last page |
| + / = / - | Zoom in / out |
| W | Fit width |
| P | Full page |
| Ctrl+B | Bookmark the current page |
| Ctrl+F | Focus the content search box |
| Ctrl+S | Save highlights to the PDF |
| F3 / Shift+F3 | Next / previous search match |
| Enter / Shift+Enter (in search box) | Next / previous search match |
| F5 | Refresh PDF list |

Arrow, space, and page keys defer to the PDF and topic lists while one of them has keyboard focus, so you can still navigate the lists from the keyboard.

## Updates

A couple of seconds after launch Sherpa quietly checks GitHub for a newer release (it never interrupts you when you're up to date or
offline). When one is found you get three choices: **Yes** downloads the update and applies it in place — the app restarts on the new version by itself;
**No** skips that version for good (you'll be asked again for the next one); **Cancel** just reminds you on the next launch. On **Windows** this works for both the
installed copy (it re-runs the installer silently) and the portable copy (it swaps the exe where it sits, even on a USB stick). The **Linux AppImage**
downloads the new AppImage, replaces its own file in place, and relaunches.

You can also check on demand with the **Check for updates** button at the bottom of this Help window — it always answers, including "You're up to
date", and still offers a version you previously skipped.

Running **from source** (or on **macOS**) there's nothing to self-replace, so the automatic check is off there — to upgrade, `git pull`, or download the
newest AppImage from the releases page. The **Check for updates** button still tells you whether a newer release exists.

To turn the launch check off entirely, add `"check_updates": false` to your config file — `%APPDATA%\PDFGuide\config.json` on Windows,
`~/.config/PDFGuide/config.json` on Linux/macOS.

## More

Project page: [github.com/Flinterpop/PDF_Sherpa](https://github.com/Flinterpop/PDF_Sherpa)

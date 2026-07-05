# PDF Sherpa — Help

Vibe Coded with Claude Code using Fable 5 
B. Graham - July 2026

PDF Sherpa lets you browse a folder of PDFs **by topic** and read them in a
built-in viewer.

## The three panes

- **PDFs** (left) — every PDF found under the current folder, grouped by
  subfolder. Click one to open it. The search box filters the list as you type.
- **Topics** (middle) — the selected PDF's topic list. Click a topic to jump
  straight to that page. The search box filters the topics as you type. If the
  PDF has bookmarks, they appear in their own list above the topics (see
  **Bookmarks** below).
- **Viewer** (right) — the embedded page view, with a search box that finds
  text inside the open PDF (see **Searching** below).

The **PDFs** and **Topics** buttons in the toolbar collapse and restore the
left and middle panes — turn both off for a full-width reading view. Your
choice is remembered across runs, and hidden panes keep their state (selection,
search text) while collapsed.

## Adding PDFs

**Drag and drop** one or more PDF files anywhere onto the window. Each is
copied into an `inbox` subfolder of the current folder, a topics file is
generated automatically, and the last one is selected and opened for you.

## Topic (.toc) files

Every PDF can have a companion topics file with the same base name — for
example `manual.pdf` pairs with `manual.toc`. If a PDF has none, it shows as
`(no metadata)`. Press **Refresh** (or `F5`) and choose to build topic lists:
Sherpa reads each PDF's bookmarks, or falls back to detecting headings from the
text when there are no bookmarks.

A `.toc` is a plain text file you can edit by hand — the page is the trailing
number, so topics may contain colons and dashes:

```
# comments start with '#'
Introduction: 1
Chapter 1 - Setup: 5
Advanced Topics: 42
```

Page numbers are **1-based** (page 1 is the first page).

## Bookmarks

Mark your own places in a PDF: press `Ctrl+B` (or the **🔖** button, or
right-click the page and choose **Bookmark this page**) to bookmark the page
you're reading. Name it whatever you like — the suggested name is just
`Page N`. Your bookmarks appear in their own **Bookmarks** list above the
Topics — it only shows when the PDF has bookmarks, and you can drag the
divider between the two lists to resize it. Click a bookmark to jump to its
page, right-click one to **Rename** or **Delete** it. (These are separate from
a PDF's built-in bookmarks, which feed the topic list.)

Bookmarks are saved next to the PDF — `manual.pdf` gets
`manual.bookmarks.json` — so they travel with the folder and are easy to edit
by hand. Deleting the last bookmark removes the file.

## Choosing a folder

Use **Choose folder…** to point Sherpa at any folder of PDFs. It remembers
which subfolders you left open, your window size, and the last PDF you were
reading — and returns you to the page you left off on.

## Searching

Each pane has its own search box:

- **PDFs** — filters the file list by name as you type; folders with no
  matches are hidden.
- **Topics** — filters the current PDF's topic list as you type.
- **Viewer** — searches the **text of the open PDF**. Matches are highlighted
  in yellow on the page, with the current match outlined in orange, and the
  counter shows where you are (for example `2 / 17`). Use the **▲ / ▼**
  buttons — or `Enter` / `Shift+Enter` in the box, or `F3` / `Shift+F3`
  anywhere — to step between matches; stepping wraps around at the end.
  `Ctrl+F` focuses the box. Searches are case-insensitive.

Press the **✕** button to clear a search. Filters stay applied when you switch
PDFs — a content search re-runs against the new document but stays on your
page until you step to a match.

## Highlighting text

Drag across text in the viewer to select it (selected words shade blue), then
click **Highlight** in the toolbar — or right-click and choose **Highlight
selection**. Highlights are standard PDF annotations, so they show up in any
PDF viewer.

Changes are kept in memory until you save. The **Save** button (or `Ctrl+S`)
asks where to put them: **Yes** saves an annotated copy alongside the
original — `manual.pdf` becomes `manual(ann).pdf`, with the topics file
copied too — while **No** writes into the original file. Saving while
viewing an `(ann)` copy just updates it, no questions asked. If you switch
PDFs or close the app with unsaved highlights, Sherpa asks whether to save
them. To remove a highlight, right-click it and choose **Remove highlight**,
then save.

Notes: scanned PDFs without a text layer have nothing to select, and saving
highlights into a digitally signed PDF may invalidate its signature (Sherpa
warns first).

## Viewer controls

- **Prev / Next** buttons, or the arrow keys, to page through the document.
- **+ / −** to zoom; **Fit width** and **Full page** to fit the page. Your fit
  choice is remembered and re-applied when you resize the window.
- The mouse wheel scrolls the page and flips to the next or previous page when
  you scroll past the bottom or top edge.

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

Arrow, space, and page keys defer to the PDF and topic lists while one of them
has keyboard focus, so you can still navigate the lists from the keyboard.

## More

Project page: [github.com/Flinterpop/PDF_Sherpa](https://github.com/Flinterpop/PDF_Sherpa)

"""
PDF Sherpa
==========

A small desktop app that:

1. Lists every PDF found in a subfolder (default: ./pdfs).
2. When a PDF is selected, loads its companion metadata file -- same base
   filename, different extension (.toc or .json) -- and shows the list of
   topics with their page numbers.
3. Clicking a topic/page opens the PDF (embedded viewer) at that page.
4. Drop a PDF anywhere on the window to copy it into an 'inbox' subfolder
   of the current folder and auto-generate its .toc topics file.
5. Bookmark pages (Ctrl+B) with your own names; bookmarks show in their own
   list above the Topics and are saved next to the PDF (name.bookmarks.json).

Metadata file formats (auto-detected by extension, .toc preferred):

  book.toc  (simple text, one entry per line -- easiest to hand-edit)
  ---------------------------------------------------------------
      # lines starting with '#' are comments
      Introduction: 1
      Chapter 1 - Setup: 5
      Advanced Topics: 42

  book.json (structured)
  ---------------------------------------------------------------
      [
        {"topic": "Introduction", "page": 1},
        {"topic": "Chapter 1 - Setup", "page": 5}
      ]

Requirements:  pip install pymupdf pillow
Run:           python app.py  [optional_folder]
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

import tocgen

# ---- Optional heavy deps: fail with a friendly message rather than a crash ---
try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None

try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover
    Image = None
    ImageTk = None


# Shown in the window title; keep in sync with AppVersion in installer.iss.
APP_VERSION = "1.3.1"

# Metadata extensions we look for, in order of preference.
METADATA_EXTENSIONS = (".toc", ".json")

# Zoom limits for the embedded viewer.
MIN_ZOOM = 0.25
MAX_ZOOM = 4.0
ZOOM_STEP = 1.25


def _add_tooltip(widget, text: str, delay_ms: int = 500) -> None:
    """Attach a hover tooltip to a widget (Tk has none built in).  Works on
    disabled widgets too -- they still receive Enter/Leave events."""
    state = {"after": None, "tip": None}

    def show():
        state["after"] = None
        tip = tk.Toplevel(widget)
        tip.wm_overrideredirect(True)     # no title bar / border
        tip.wm_geometry(f"+{widget.winfo_rootx() + 10}"
                        f"+{widget.winfo_rooty() + widget.winfo_height() + 4}")
        tk.Label(tip, text=text, justify="left", background="#ffffe0",
                 relief="solid", borderwidth=1, padx=6, pady=4).pack()
        state["tip"] = tip

    def enter(_event):
        state["after"] = widget.after(delay_ms, show)

    def leave(_event):
        if state["after"] is not None:
            widget.after_cancel(state["after"])
            state["after"] = None
        if state["tip"] is not None:
            state["tip"].destroy()
            state["tip"] = None

    widget.bind("<Enter>", enter, add="+")
    widget.bind("<Leave>", leave, add="+")
    widget.bind("<ButtonPress>", leave, add="+")


# ----------------------------------------------------------------------------
# Metadata loading
# ----------------------------------------------------------------------------
def find_metadata_path(pdf_path: str) -> str | None:
    """Return the companion metadata file for a PDF, or None if none exists."""
    base, _ = os.path.splitext(pdf_path)
    for ext in METADATA_EXTENSIONS:
        candidate = base + ext
        if os.path.isfile(candidate):
            return candidate
    return None


def _parse_toc_text(text: str) -> list[tuple[str, int]]:
    """Parse the simple '.toc' text format into (topic, page) tuples.

    Each non-comment, non-blank line must end with a page number.  The page is
    taken from the trailing integer (after the last ':' if present, otherwise
    after the last run of whitespace), so topics may themselves contain colons
    and spaces, e.g. "Chapter 1 - Setup: 5".
    """
    entries: list[tuple[str, int]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        if ":" in line:
            topic, _, page_part = line.rpartition(":")
        else:
            topic, _, page_part = line.rpartition(" ")

        topic = topic.strip()
        match = re.search(r"\d+", page_part)
        if not topic or not match:
            raise ValueError(
                f"Line {lineno}: expected 'Topic: page', got {raw!r}"
            )
        entries.append((topic, int(match.group())))
    return entries


def _parse_json_metadata(text: str) -> list[tuple[str, int]]:
    """Parse the '.json' metadata format into (topic, page) tuples."""
    data = json.loads(text)
    entries: list[tuple[str, int]] = []
    for item in data:
        topic = str(item["topic"]).strip()
        page = int(item["page"])
        entries.append((topic, page))
    return entries


def load_metadata(metadata_path: str) -> list[tuple[str, int]]:
    """Load a metadata file and return a list of (topic, page) tuples."""
    with open(metadata_path, "r", encoding="utf-8") as fh:
        text = fh.read()
    if metadata_path.lower().endswith(".json"):
        return _parse_json_metadata(text)
    return _parse_toc_text(text)


# ----------------------------------------------------------------------------
# Bookmarks (per-PDF sidecar: name.bookmarks.json next to the PDF)
# ----------------------------------------------------------------------------
def bookmarks_path(pdf_path: str) -> str:
    """Return the bookmarks sidecar path for a PDF (manual.pdf ->
    manual.bookmarks.json).  The double extension keeps it clear of the
    .toc/.json metadata lookup in find_metadata_path."""
    return os.path.splitext(pdf_path)[0] + ".bookmarks.json"


def load_bookmarks(pdf_path: str) -> list[dict]:
    """Load a PDF's bookmarks: a list of {"page": int, "title": str} dicts,
    sorted by page.  Missing sidecar is the normal case -> []."""
    path = bookmarks_path(pdf_path)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        bookmarks = []
        for item in data:
            page = int(item["page"])
            title = str(item["title"]).strip()
            if page >= 1 and title:
                bookmarks.append({"page": page, "title": title})
        bookmarks.sort(key=lambda b: b["page"])
        return bookmarks
    except Exception as exc:  # corrupt/unreadable; next save overwrites it
        messagebox.showwarning(
            "Bookmarks",
            f"Could not read {os.path.basename(path)}:\n\n{exc}\n\n"
            "Starting with no bookmarks for this PDF.")
        return []


def save_bookmarks(pdf_path: str, bookmarks: list[dict]) -> bool:
    """Write a PDF's bookmarks sidecar; an empty list deletes the file
    (no file = no bookmarks).  Returns False if the write failed."""
    path = bookmarks_path(pdf_path)
    try:
        if not bookmarks:
            if os.path.isfile(path):
                os.remove(path)
            return True
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(bookmarks, fh, indent=2)
        return True
    except OSError as exc:
        messagebox.showwarning(
            "Bookmarks",
            f"Could not write {path}:\n\n{exc}\n\n"
            "Bookmarks will be kept for this session only.")
        return False


# ----------------------------------------------------------------------------
# GUI
# ----------------------------------------------------------------------------
class PDFSherpaApp(ttk.Frame):
    def __init__(self, master: tk.Tk, folder: str):
        super().__init__(master, padding=6)
        self.master = master
        self.folder = folder

        # Viewer state
        self.doc = None                 # fitz.Document currently open
        self.current_pdf_path: str | None = None
        self.current_page = 0           # 0-based
        self.zoom = 1.0
        # Fit preference persists across PDFs and app runs; fit_mode is the
        # currently-applied fit (may be None after a manual +/- zoom).
        pref = load_config().get("fit_pref", "width")
        self.fit_pref = pref if pref in ("width", "page") else "width"
        self.fit_mode: str | None = self.fit_pref  # "width" | "page" | None
        self._photo = None              # keep a ref so Tk doesn't GC the image
        self.filter_text = ""           # current PDF-list search filter
        self.topic_filter_text = ""     # current topic-list search filter
        self._topic_entries: list[tuple[str, int]] = []  # current PDF's topics
        self._topic_placeholder: str | None = None  # shown instead of topics
        # Current PDF's bookmarks ({"page", "title"} dicts, page-sorted) and
        # the list index targeted by the tree's right-click menu.
        self._bookmarks: list[dict] = []
        self._bm_menu_index: int | None = None
        # Where the user last dragged the bookmarks/topics sash (pixels).
        # Persisted across runs; None means "use the default 25%".
        saved_sash = load_config().get("bm_sash")
        self._bm_sash: int | None = (
            saved_sash if isinstance(saved_sash, int) and saved_sash > 0
            else None)
        # Content search over the open PDF: (page_index, fitz.Rect) per hit.
        # The scan runs in chunks on the Tk event loop so big documents don't
        # freeze the UI; matches/label fill in progressively.
        self.content_matches: list[tuple[int, object]] = []
        self.content_match_idx = -1     # index into content_matches (-1 = none)
        self._content_search_after: str | None = None  # debounce timer id
        self._content_scan_after: str | None = None    # next-chunk timer id
        self._content_scan_active = False
        self._content_scan_needle = ""
        self._content_scan_page = 0     # next page the scan will read
        self._content_scan_jump = False  # jump to the first hit when found
        # Text selection / highlight annotations on the open PDF.
        self._select_anchor: tuple[float, float] | None = None  # canvas px
        self._select_drag: tuple[float, float] | None = None
        self._selected_rects: list = []  # word boxes (PDF points) selected
        self._annots_dirty = False       # highlights not yet saved to disk
        self._canvas_menu_pt: tuple[float, float] | None = None  # PDF points
        # Re-fit the page when a window resize settles (debounced).
        self._resize_after: str | None = None
        self._snap_after: str | None = None   # full-page window-snap pass
        # Full-page fit: which canvas dimension drives the zoom during a
        # user resize ("w"/"h"), and the canvas size of the last fit.
        self._fit_master: str | None = None
        self._fitted_canvas_size: tuple[int, int] | None = None
        self._saved_sashes: list[int] | None = None  # pane widths pre-snap
        self._last_pix: tuple[int, int] | None = None  # last rendered size
        self._last_canvas_size = (0, 0)
        # Remembered open folders (relative paths); folders start closed unless
        # listed here.  Persisted across runs.
        saved = load_config().get("expanded_folders", [])
        self._expanded = set(saved) if isinstance(saved, list) else set()

        self.pack(fill="both", expand=True)
        self._build_ui()
        self._bind_shortcuts()
        self._enable_file_drop()
        self.refresh_pdf_list()
        self._restore_session()

    # -- Layout ---------------------------------------------------------------
    def _build_ui(self) -> None:
        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(side="top", fill="x", pady=(0, 6))

        ttk.Button(toolbar, text="Choose folder…",
                   command=self.choose_folder).pack(side="left")
        refresh_btn = ttk.Button(toolbar, text="Refresh",
                                 command=self.on_refresh_clicked)
        refresh_btn.pack(side="left", padx=(4, 0))
        _add_tooltip(refresh_btn,
                     "Rescan the folder for PDFs (F5) and offer to build\n"
                     "topic lists for any PDFs that don't have one yet.")
        ttk.Button(toolbar, text="Help",
                   command=self.show_help).pack(side="right")

        # Pane visibility toggles (pressed = shown); with both off only the
        # viewer remains.  Persisted across runs.
        cfg = load_config()
        self.show_pdfs_var = tk.BooleanVar(
            value=bool(cfg.get("show_pdf_list", True)))
        self.show_topics_var = tk.BooleanVar(
            value=bool(cfg.get("show_topics", True)))
        pdfs_toggle = ttk.Checkbutton(toolbar, text="PDFs",
                                      style="Toolbutton",
                                      variable=self.show_pdfs_var,
                                      command=self._apply_pane_visibility)
        pdfs_toggle.pack(side="left", padx=(12, 0))
        _add_tooltip(pdfs_toggle,
                     "Show or hide the PDF list pane.\n"
                     "Hide both panes for a full-width reading view.")
        topics_toggle = ttk.Checkbutton(toolbar, text="Topics",
                                        style="Toolbutton",
                                        variable=self.show_topics_var,
                                        command=self._apply_pane_visibility)
        topics_toggle.pack(side="left", padx=(2, 0))
        _add_tooltip(topics_toggle,
                     "Show or hide the Topics pane.\n"
                     "Hide both panes for a full-width reading view.")


        # Three resizable panes: PDFs | topics | viewer
        panes = self.panes = ttk.PanedWindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True)

        # 1. PDF list (grouped by subfolder under the top-level folder)
        left = ttk.Frame(panes)
        ttk.Label(left, text="PDFs").pack(anchor="w")

        # Search / filter box
        search = ttk.Frame(left)
        search.pack(side="top", fill="x", pady=(0, 4))
        ttk.Label(search, text="🔍").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search_changed)
        search_entry = ttk.Entry(search, textvariable=self.search_var)
        search_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))
        ttk.Button(search, text="✕", width=2,
                   command=lambda: self.search_var.set("")).pack(side="left")

        tree_wrap = ttk.Frame(left)
        tree_wrap.pack(side="top", fill="both", expand=True)
        self.pdf_tree = ttk.Treeview(tree_wrap, show="tree",
                                     selectmode="browse")
        self.pdf_tree.column("#0", width=240, anchor="w")
        self.pdf_tree.tag_configure("folder", foreground="#333")
        self.pdf_tree.tag_configure("nometa", foreground="#999")
        self.pdf_tree.pack(side="left", fill="both", expand=True)
        pdf_sb = ttk.Scrollbar(tree_wrap, orient="vertical",
                               command=self.pdf_tree.yview)
        pdf_sb.pack(side="right", fill="y")
        self.pdf_tree.config(yscrollcommand=pdf_sb.set)
        self.pdf_tree.bind("<<TreeviewSelect>>", self.on_pdf_selected)
        self.pdf_tree.bind("<Button-3>", self._on_pdf_right_click)
        self.pdf_tree.bind("<<TreeviewOpen>>",
                           lambda e: self._on_folder_toggle(True))
        self.pdf_tree.bind("<<TreeviewClose>>",
                           lambda e: self._on_folder_toggle(False))

        # Right-click context menu for the PDF list
        self.pdf_menu = tk.Menu(self, tearoff=0)
        self.pdf_menu.add_command(label="Open in default viewer",
                                  command=self._ctx_open)
        self.pdf_menu.add_command(label="Reveal in Explorer",
                                  command=self._ctx_reveal)
        self._ctx_path: str | None = None
        self._left_pane = left
        panes.add(left, weight=1)

        # 2. Topics
        mid = ttk.Frame(panes)
        # Vertical split: Bookmarks over Topics, with a draggable sash.  The
        # Bookmarks pane is only attached while the PDF has bookmarks (it
        # starts at 25% of the height); otherwise Topics takes it all.
        self._mid_split = ttk.PanedWindow(mid, orient="vertical")
        self._mid_split.pack(fill="both", expand=True)

        self._bm_frame = ttk.Frame(self._mid_split)
        # Not added to the split here -- _populate_bookmark_tree attaches and
        # detaches it as bookmarks come and go.
        ttk.Label(self._bm_frame, text="Bookmarks").pack(anchor="w")
        bm_wrap = ttk.Frame(self._bm_frame)
        bm_wrap.pack(side="top", fill="both", expand=True)
        self.bm_tree = ttk.Treeview(bm_wrap, columns=("page",),
                                    show="tree headings",
                                    selectmode="browse", height=3)
        self.bm_tree.heading("#0", text="Bookmark")
        self.bm_tree.heading("page", text="Page")
        self.bm_tree.column("#0", width=200, anchor="w")
        self.bm_tree.column("page", width=50, anchor="center", stretch=False)
        self.bm_tree.pack(side="left", fill="both", expand=True)
        bm_sb = ttk.Scrollbar(bm_wrap, orient="vertical",
                              command=self.bm_tree.yview)
        bm_sb.pack(side="right", fill="y")
        self.bm_tree.config(yscrollcommand=bm_sb.set)
        self.bm_tree.bind("<<TreeviewSelect>>", self.on_bookmark_selected)
        self.bm_tree.bind("<Button-3>", self._on_bm_right_click)

        topics = ttk.Frame(self._mid_split)
        self._mid_split.add(topics, weight=3)
        ttk.Label(topics, text="Topics").pack(anchor="w")

        # Search / filter box (filters the current PDF's topics only)
        topic_search = ttk.Frame(topics)
        topic_search.pack(side="top", fill="x", pady=(0, 4))
        ttk.Label(topic_search, text="🔍").pack(side="left")
        self.topic_search_var = tk.StringVar()
        self.topic_search_var.trace_add("write", self._on_topic_search_changed)
        topic_entry = ttk.Entry(topic_search,
                                textvariable=self.topic_search_var)
        topic_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))
        ttk.Button(topic_search, text="✕", width=2,
                   command=lambda: self.topic_search_var.set("")
                   ).pack(side="left")

        topic_wrap = ttk.Frame(topics)
        topic_wrap.pack(side="top", fill="both", expand=True)
        self.topic_tree = ttk.Treeview(topic_wrap, columns=("page",),
                                       show="tree headings",
                                       selectmode="browse")
        self.topic_tree.heading("#0", text="Topic")
        self.topic_tree.heading("page", text="Page")
        self.topic_tree.column("#0", width=200, anchor="w")
        self.topic_tree.column("page", width=50, anchor="center", stretch=False)
        self.topic_tree.pack(side="left", fill="both", expand=True)
        topic_sb = ttk.Scrollbar(topic_wrap, orient="vertical",
                                 command=self.topic_tree.yview)
        topic_sb.pack(side="right", fill="y")
        self.topic_tree.config(yscrollcommand=topic_sb.set)
        self.topic_tree.bind("<<TreeviewSelect>>", self.on_topic_selected)

        # Right-click context menu for rows in the bookmark list
        self.bookmark_menu = tk.Menu(self, tearoff=0)
        self.bookmark_menu.add_command(label="Rename",
                                       command=self._rename_bookmark)
        self.bookmark_menu.add_command(label="Delete",
                                       command=self._delete_bookmark)
        self._mid_pane = mid
        panes.add(mid, weight=1)

        # 3. Embedded viewer
        right = ttk.Frame(panes)

        # Search / find box (searches the text of the currently open PDF)
        content_search = ttk.Frame(right)
        content_search.pack(side="top", fill="x", pady=(0, 4))
        ttk.Label(content_search, text="🔍").pack(side="left")
        self.content_search_var = tk.StringVar()
        self.content_search_var.trace_add("write",
                                          self._on_content_search_changed)
        self.content_search_entry = ttk.Entry(
            content_search, textvariable=self.content_search_var)
        self.content_search_entry.pack(side="left", fill="x", expand=True,
                                       padx=(4, 0))
        self.content_search_entry.bind("<Return>", self._on_content_return)
        self.content_search_entry.bind("<Shift-Return>",
                                       lambda e: self.prev_match() or "break")
        prev_btn = ttk.Button(content_search, text="▲", width=2,
                              command=self.prev_match)
        prev_btn.pack(side="left", padx=(4, 0))
        _add_tooltip(prev_btn, "Previous search match (Shift+F3)")
        next_btn = ttk.Button(content_search, text="▼", width=2,
                              command=self.next_match)
        next_btn.pack(side="left")
        _add_tooltip(next_btn, "Next search match (F3)")
        self.match_var = tk.StringVar()
        ttk.Label(content_search, textvariable=self.match_var,
                  width=10, anchor="center").pack(side="left")
        ttk.Button(content_search, text="✕", width=2,
                   command=lambda: self.content_search_var.set("")
                   ).pack(side="left")

        nav = ttk.Frame(right)
        nav.pack(side="top", fill="x")
        ttk.Button(nav, text="◀ Prev",
                   command=self.prev_page).pack(side="left")
        ttk.Button(nav, text="Next ▶",
                   command=self.next_page).pack(side="left", padx=(4, 8))
        self.page_var = tk.StringVar(value="—")
        ttk.Label(nav, textvariable=self.page_var).pack(side="left")
        self.highlight_btn = ttk.Button(nav, text="Highlight",
                                        state="disabled",
                                        command=self.highlight_selection)
        self.highlight_btn.pack(side="left", padx=(12, 0))
        _add_tooltip(self.highlight_btn,
                     "Hold the left mouse button and drag across text on\n"
                     "the page — selected words shade blue — then click\n"
                     "Highlight. Save writes the highlights into the PDF.")
        self.save_btn = ttk.Button(nav, text="Save", state="disabled",
                                   command=self.save_annotations)
        self.save_btn.pack(side="left", padx=(4, 0))
        _add_tooltip(self.save_btn,
                     "Write highlights to disk (Ctrl+S): choose between an\n"
                     "annotated copy — name(ann).pdf — or the original file.")
        bookmark_btn = ttk.Button(nav, text="🔖", width=3,
                                  command=self.add_bookmark)
        bookmark_btn.pack(side="left", padx=(4, 0))
        _add_tooltip(bookmark_btn,
                     "Bookmark the current page (Ctrl+B). Bookmarks appear\n"
                     "in their own list above the Topics; right-click one\n"
                     "there to rename or delete it.")
        ttk.Button(nav, text="−",
                   command=lambda: self.change_zoom(1 / ZOOM_STEP)
                   ).pack(side="right")
        ttk.Button(nav, text="+",
                   command=lambda: self.change_zoom(ZOOM_STEP)
                   ).pack(side="right", padx=(0, 4))
        full_btn = ttk.Button(nav, text="Full page", command=self.fit_page)
        full_btn.pack(side="right", padx=(0, 4))
        _add_tooltip(full_btn,
                     "Fit the whole page in the viewer and resize the\n"
                     "window to match it (P). Dragging a window edge then\n"
                     "zooms the page to follow.")
        fit_btn = ttk.Button(nav, text="Fit width", command=self.fit_width)
        fit_btn.pack(side="right", padx=4)
        _add_tooltip(fit_btn, "Scale the page to the viewer width (W)")

        canvas_wrap = ttk.Frame(right)
        canvas_wrap.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(canvas_wrap, background="#3a3a3a",
                                highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        v_sb = ttk.Scrollbar(canvas_wrap, orient="vertical",
                             command=self.canvas.yview)
        v_sb.grid(row=0, column=1, sticky="ns")
        h_sb = ttk.Scrollbar(canvas_wrap, orient="horizontal",
                             command=self.canvas.xview)
        h_sb.grid(row=1, column=0, sticky="ew")
        self.canvas.config(yscrollcommand=v_sb.set, xscrollcommand=h_sb.set)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<ButtonPress-1>", self._on_select_start)
        self.canvas.bind("<B1-Motion>", self._on_select_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_select_end)
        self.canvas.bind("<Button-3>", self._on_canvas_right_click)

        # Right-click context menu for the viewer
        self.canvas_menu = tk.Menu(self, tearoff=0)
        self.canvas_menu.add_command(label="Highlight selection",
                                     command=self.highlight_selection)
        self.canvas_menu.add_command(label="Remove highlight",
                                     command=self._remove_highlight_here)
        self.canvas_menu.add_separator()
        self.canvas_menu.add_command(label="Bookmark this page",
                                     command=self.add_bookmark)
        canvas_wrap.rowconfigure(0, weight=1)
        canvas_wrap.columnconfigure(0, weight=1)
        panes.add(right, weight=3)

        self._apply_pane_visibility(persist=False)   # restore saved toggles

    # -- Pane visibility -------------------------------------------------------
    def _apply_pane_visibility(self, persist: bool = True) -> None:
        """Add/remove the PDF-list and Topics panes to match the toolbar
        toggles.  Removing a pane keeps its widgets (and state) intact, so
        re-showing it is instant."""
        show_left = self.show_pdfs_var.get()
        show_mid = self.show_topics_var.get()

        def present(widget) -> bool:
            return str(widget) in self.panes.panes()

        if show_left and not present(self._left_pane):
            self.panes.insert(0, self._left_pane, weight=1)
        elif not show_left and present(self._left_pane):
            self.panes.forget(self._left_pane)

        if show_mid and not present(self._mid_pane):
            self.panes.insert(1 if show_left else 0, self._mid_pane, weight=1)
        elif not show_mid and present(self._mid_pane):
            self.panes.forget(self._mid_pane)

        if persist:
            update_config({"show_pdf_list": show_left,
                           "show_topics": show_mid})

    # -- Keyboard shortcuts ---------------------------------------------------
    def _bind_shortcuts(self) -> None:
        """Global viewer shortcuts. Arrow/space/page keys defer to a focused
        tree so list navigation still works; the rest are viewer-only keys."""
        top = self.winfo_toplevel()

        # Paging (guarded -- let a focused tree keep its own navigation).
        for seq in ("<Left>", "<Prior>"):          # Prior = Page Up
            top.bind(seq, self._key_guarded(self.prev_page))
        for seq in ("<Right>", "<Next>", "<space>"):  # Next = Page Down
            top.bind(seq, self._key_guarded(self.next_page))
        top.bind("<Home>", self._key_guarded(lambda: self.goto_page(0)))
        top.bind("<End>", self._key_guarded(
            lambda: self.goto_page((self.doc.page_count - 1) if self.doc else 0)))

        # Zoom (ignored while typing in the search box).
        for seq in ("<plus>", "<KP_Add>", "<equal>"):
            top.bind(seq, self._viewer_key(lambda: self.change_zoom(ZOOM_STEP)))
        for seq in ("<minus>", "<KP_Subtract>"):
            top.bind(seq, self._viewer_key(
                lambda: self.change_zoom(1 / ZOOM_STEP)))

        # Fit modes.
        top.bind("<Key-w>", self._viewer_key(self.fit_width))
        top.bind("<Key-W>", self._viewer_key(self.fit_width))
        top.bind("<Key-p>", self._viewer_key(self.fit_page))
        top.bind("<Key-P>", self._viewer_key(self.fit_page))

        # Refresh the PDF list (offers to build missing topic lists).
        top.bind("<F5>", lambda e: self.on_refresh_clicked())

        # Save highlight annotations.
        top.bind("<Control-s>",
                 lambda e: (self.save_annotations(), "break")[1])

        # Bookmark the current page.  _viewer_key (not a bare bind): entries
        # have a default emacs Control-b binding we must not shadow.
        top.bind("<Control-b>", self._viewer_key(self.add_bookmark))

        # Content search: Ctrl+F focuses the box, F3 / Shift+F3 step matches.
        top.bind("<Control-f>",
                 lambda e: (self.content_search_entry.focus_set(), "break")[1])
        top.bind("<F3>", lambda e: (self.next_match(), "break")[1])
        top.bind("<Shift-F3>", lambda e: (self.prev_match(), "break")[1])

        # Mouse wheel over the viewer scrolls the page and flips at the edges.
        top.bind_all("<MouseWheel>", self._on_mousewheel)

    def _key_guarded(self, action):
        """Return a key handler that runs `action` unless a tree or text entry
        has focus (so arrows/space/page keys still drive the lists and let you
        type in the search box)."""
        def handler(event):
            if isinstance(self.focus_get(), (ttk.Treeview, ttk.Entry, tk.Entry)):
                return None          # let the widget handle it
            action()
            return "break"
        return handler

    def _viewer_key(self, action):
        """Key handler for viewer-only keys; ignored while typing in an entry."""
        def handler(event):
            if isinstance(self.focus_get(), (ttk.Entry, tk.Entry)):
                return None
            action()
            return "break"
        return handler

    # -- Drag & drop (Windows) -------------------------------------------------
    def _enable_file_drop(self) -> None:
        """Accept files dropped from Explorer anywhere on the window.

        Uses the classic Win32 WM_DROPFILES route: register the toplevel's
        client window with DragAcceptFiles, then subclass its window procedure
        to catch the drop message.  Drops over child widgets bubble up to the
        nearest ancestor that accepts files, so one hook covers the whole UI.

        The window procedure only *queues* the dropped paths -- it must not call
        into Tk/Tcl, because it runs reentrantly inside Tcl's own event dispatch
        and doing so crashes the interpreter.  A periodic poller (started here in
        the normal main-loop context) drains the queue and does the real work.
        """
        if sys.platform != "win32":
            return
        import ctypes
        from ctypes import wintypes

        self._drop_queue: list[str] = []

        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32

        WM_DROPFILES = 0x0233
        GWLP_WNDPROC = -4
        LRESULT = ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                                     wintypes.WPARAM, wintypes.LPARAM)

        shell32.DragAcceptFiles.argtypes = (wintypes.HWND, wintypes.BOOL)
        shell32.DragQueryFileW.argtypes = (wintypes.WPARAM, wintypes.UINT,
                                           ctypes.c_wchar_p, wintypes.UINT)
        shell32.DragFinish.argtypes = (wintypes.WPARAM,)
        set_wndproc = getattr(user32, "SetWindowLongPtrW",
                              user32.SetWindowLongW)
        set_wndproc.restype = LRESULT
        set_wndproc.argtypes = (wintypes.HWND, ctypes.c_int, WNDPROC)
        user32.CallWindowProcW.restype = LRESULT
        user32.CallWindowProcW.argtypes = (LRESULT, wintypes.HWND,
                                           wintypes.UINT, wintypes.WPARAM,
                                           wintypes.LPARAM)

        def wndproc(hwnd, msg, wparam, lparam):
            if msg == WM_DROPFILES:
                count = shell32.DragQueryFileW(wparam, 0xFFFFFFFF, None, 0)
                for i in range(count):
                    n = shell32.DragQueryFileW(wparam, i, None, 0) + 1
                    buf = ctypes.create_unicode_buffer(n)
                    shell32.DragQueryFileW(wparam, i, buf, n)
                    self._drop_queue.append(buf.value)
                shell32.DragFinish(wparam)
                # NOTE: no Tk calls here -- the poller handles the queue.
                return 0
            return user32.CallWindowProcW(self._orig_wndproc, hwnd, msg,
                                          wparam, lparam)

        hwnd = self.winfo_toplevel().winfo_id()
        shell32.DragAcceptFiles(hwnd, True)
        self._wndproc_ref = WNDPROC(wndproc)   # keep alive or the hook crashes
        self._orig_wndproc = set_wndproc(hwnd, GWLP_WNDPROC, self._wndproc_ref)
        self.after(200, self._poll_drop_queue)

    def _poll_drop_queue(self) -> None:
        """Drain paths queued by the drop window procedure (main-loop context)."""
        if self._drop_queue:
            batch, self._drop_queue = self._drop_queue, []
            self._on_files_dropped(batch)
        self.after(200, self._poll_drop_queue)

    def _on_files_dropped(self, paths: list[str]) -> None:
        """Copy dropped PDFs into <folder>/inbox and build missing .toc files."""
        pdfs = [p for p in paths
                if p.lower().endswith(".pdf") and os.path.isfile(p)]
        if not pdfs:
            messagebox.showinfo(
                "Drop PDFs",
                "Drop one or more .pdf files to add them to the inbox.")
            return

        inbox = os.path.join(self.folder, "inbox")
        try:
            os.makedirs(inbox, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Drop PDFs",
                                 f"Could not create {inbox}:\n\n{exc}")
            return

        added: list[str] = []
        failed: list[str] = []
        for src in pdfs:
            name = os.path.basename(src)
            dest = os.path.join(inbox, name)
            try:
                if os.path.exists(dest):
                    if os.path.samefile(src, dest):
                        added.append(dest)   # already in the inbox
                        continue
                    if not messagebox.askyesno(
                            "Replace PDF?",
                            f"{name} is already in the inbox.\nReplace it?"):
                        continue
                shutil.copy2(src, dest)
            except OSError as exc:
                failed.append(f"{name}: {exc}")
                continue
            added.append(dest)
            # Keep an existing (possibly hand-edited) topics file; only
            # generate one when the PDF has no metadata yet.
            if find_metadata_path(dest) is None:
                try:
                    tocgen.write_toc(dest)
                except Exception as exc:
                    failed.append(f"{name}: added, but no topics built ({exc})")

        if added:
            # Show the inbox folder open so the new files are visible.
            self._expanded.add("inbox")
            update_config({"expanded_folders": sorted(self._expanded)})
            if self.filter_text:
                self.search_var.set("")   # clears filter and refreshes
            else:
                self.refresh_pdf_list()
            self._select_pdf(added[-1])

        if failed:
            messagebox.showwarning(
                "Drop PDFs",
                f"Added {len(added)} PDF{'s' if len(added) != 1 else ''} "
                "to the inbox.\n\nProblems:\n" + "\n".join(failed[:10]))

    # -- Help -----------------------------------------------------------------
    def show_help(self) -> None:
        """Open a window that renders the bundled HELP.md."""
        existing = getattr(self, "_help_win", None)
        if existing is not None and existing.winfo_exists():
            existing.deiconify()
            existing.lift()
            existing.focus_set()
            return

        try:
            with open(_resource_path("HELP.md"), "r", encoding="utf-8") as fh:
                md = fh.read()
        except OSError:
            md = ("# Help\n\nThe help file (HELP.md) could not be found.\n\n"
                  "See the project page for documentation.")

        win = tk.Toplevel(self)
        self._help_win = win
        win.title("PDF Sherpa — Help")
        # Open centered over the main window (clamped to the screen).
        w, h = 660, 740
        top = self.winfo_toplevel()
        x = top.winfo_rootx() + (top.winfo_width() - w) // 2
        y = top.winfo_rooty() + (top.winfo_height() - h) // 2
        x = max(0, min(x, win.winfo_screenwidth() - w))
        y = max(0, min(y, win.winfo_screenheight() - h))
        win.geometry(f"{w}x{h}+{x}+{y}")
        icon = _resource_path("sherpaicon.ico")
        if os.path.isfile(icon):
            try:
                win.iconbitmap(icon)
            except tk.TclError:
                pass

        wrap = ttk.Frame(win)
        wrap.pack(fill="both", expand=True)
        text = tk.Text(wrap, wrap="word", padx=16, pady=12, borderwidth=0,
                       background="#ffffff", foreground="#1a1a1a",
                       font=("Segoe UI", 11), cursor="arrow", spacing3=2)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=text.yview)
        text.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)

        _render_markdown(text, md)
        text.config(state="disabled")

        win.bind("<Escape>", lambda e: win.destroy())

    # -- PDF list -------------------------------------------------------------
    def choose_folder(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.folder,
                                         title="Choose folder containing PDFs")
        if chosen:
            self.folder = chosen
            self.refresh_pdf_list()

    def refresh_pdf_list(self) -> None:
        self.winfo_toplevel().title(
            f"PDF Sherpa - V{APP_VERSION} - {os.path.abspath(self.folder)}")
        self.pdf_tree.delete(*self.pdf_tree.get_children())
        self._pdf_by_iid: dict[str, str] = {}   # tree item id -> pdf path
        self._folder_rel_by_iid: dict[str, str] = {}   # folder iid -> rel path

        if not os.path.isdir(self.folder):
            self.pdf_tree.insert("", "end", text="(folder not found)")
            return

        # While filtering, force folders open so matches are visible; otherwise
        # honour the remembered open/closed state (closed by default).
        filtering = bool(self.filter_text)

        # Map each subfolder's relative path to its tree node, creating parent
        # nodes on demand.  "" is the root (the top-level folder itself).
        folder_nodes: dict[str, str] = {"": ""}

        def ensure_folder(rel: str) -> str:
            if rel in folder_nodes:
                return folder_nodes[rel]
            parent_rel, _, name = rel.rpartition(os.sep)
            parent = ensure_folder(parent_rel)
            is_open = filtering or rel in self._expanded
            node = self.pdf_tree.insert(parent, "end", text=name,
                                        open=is_open, tags=("folder",))
            folder_nodes[rel] = node
            self._folder_rel_by_iid[node] = rel
            return node

        needle = self.filter_text.lower()
        count = 0
        for dirpath, dirnames, filenames in os.walk(self.folder):
            dirnames.sort(key=str.lower)
            rel = os.path.relpath(dirpath, self.folder)
            rel = "" if rel == "." else rel
            pdfs = sorted((f for f in filenames if f.lower().endswith(".pdf")),
                          key=str.lower)
            if needle:   # filter by filename substring (folders follow content)
                pdfs = [f for f in pdfs if needle in f.lower()]
            if not pdfs:
                continue
            parent = ensure_folder(rel)
            for name in pdfs:
                path = os.path.join(dirpath, name)
                has_meta = find_metadata_path(path) is not None
                text = name if has_meta else name + "   (no metadata)"
                iid = self.pdf_tree.insert(
                    parent, "end", text=text,
                    tags=() if has_meta else ("nometa",))
                self._pdf_by_iid[iid] = path
                count += 1

        if count == 0:
            msg = "(no matches)" if needle else "(no PDFs found)"
            self.pdf_tree.insert("", "end", text=msg)

    def on_pdf_selected(self, _event=None) -> None:
        selection = self.pdf_tree.selection()
        if not selection:
            return
        path = self._pdf_by_iid.get(selection[0])
        if path is None:
            return  # a folder node or placeholder row, not a PDF
        self.load_pdf(path)
        self.load_topics(path)

    # -- Search / filter ------------------------------------------------------
    def _on_search_changed(self, *_args) -> None:
        self.filter_text = self.search_var.get().strip()
        self.refresh_pdf_list()

    # -- Remember folder open/closed state ------------------------------------
    def _on_folder_toggle(self, is_open: bool) -> None:
        if self.filter_text:
            return   # filter forces folders open -- don't persist that
        rel = self._folder_rel_by_iid.get(self.pdf_tree.focus())
        if rel is None:
            return
        if is_open:
            self._expanded.add(rel)
        else:
            self._expanded.discard(rel)
        update_config({"expanded_folders": sorted(self._expanded)})

    # -- Refresh (with optional TOC generation) -------------------------------
    def on_refresh_clicked(self) -> None:
        self.refresh_pdf_list()
        missing = self._pdfs_without_metadata()
        if not missing:
            return
        n = len(missing)
        if not messagebox.askyesno(
                "Build topic lists?",
                f"{n} PDF{'s' if n > 1 else ''} in this folder "
                f"{'have' if n > 1 else 'has'} no topics (.toc) file.\n\n"
                "Generate topic lists now from each PDF's bookmarks, or from "
                "its text when there are no bookmarks?"):
            return

        made, failed = 0, []
        for pdf in missing:
            try:
                tocgen.write_toc(pdf)
                made += 1
            except Exception as exc:          # keep going on a bad PDF
                failed.append(f"{os.path.basename(pdf)}: {exc}")

        self.refresh_pdf_list()               # pick up the new .toc files
        summary = f"Created {made} topics file{'s' if made != 1 else ''}."
        if failed:
            summary += "\n\nCould not process:\n" + "\n".join(failed[:10])
            if len(failed) > 10:
                summary += f"\n…and {len(failed) - 10} more."
        messagebox.showinfo("Topic lists", summary)

    def _pdfs_without_metadata(self) -> list[str]:
        """All PDFs under the folder that have no companion .toc/.json."""
        out: list[str] = []
        if not os.path.isdir(self.folder):
            return out
        for dirpath, _dirs, filenames in os.walk(self.folder):
            for name in sorted(filenames, key=str.lower):
                if name.lower().endswith(".pdf"):
                    path = os.path.join(dirpath, name)
                    if find_metadata_path(path) is None:
                        out.append(path)
        return out

    # -- Right-click context menu ---------------------------------------------
    def _on_pdf_right_click(self, event) -> None:
        iid = self.pdf_tree.identify_row(event.y)
        if not iid:
            return
        self.pdf_tree.selection_set(iid)
        self.pdf_tree.focus(iid)
        # A PDF row maps to a file; a folder row maps to its directory.
        path = self._pdf_by_iid.get(iid)
        if path is not None:
            self._ctx_path = path
            self.pdf_menu.entryconfigure(0, state="normal", label="Open PDF")
        else:
            self._ctx_path = self._folder_path_for(iid)
            self.pdf_menu.entryconfigure(0, state="disabled", label="Open")
        if self._ctx_path:
            self.pdf_menu.tk_popup(event.x_root, event.y_root)

    def _folder_path_for(self, iid: str) -> str:
        """Reconstruct the on-disk path of a folder node from the tree."""
        parts = []
        node = iid
        while node:
            parts.append(self.pdf_tree.item(node, "text"))
            node = self.pdf_tree.parent(node)
        return os.path.join(self.folder, *reversed(parts))

    def _ctx_open(self) -> None:
        if self._ctx_path and os.path.exists(self._ctx_path):
            try:
                os.startfile(self._ctx_path)      # Windows default handler
            except OSError as exc:
                messagebox.showerror("Open", str(exc))

    def _ctx_reveal(self) -> None:
        path = self._ctx_path
        if not path or not os.path.exists(path):
            return
        try:
            if os.path.isdir(path):
                os.startfile(path)                # open the folder itself
            else:
                # explorer's /select wants the path as one quoted token.
                subprocess.run(f'explorer /select,"{os.path.normpath(path)}"')
        except OSError as exc:
            messagebox.showerror("Reveal in Explorer", str(exc))

    # -- Session (window size + last PDF) -------------------------------------
    def _restore_session(self) -> None:
        cfg = load_config()
        top = self.winfo_toplevel()

        geom = cfg.get("geometry")
        if isinstance(geom, str) and "x" in geom:
            try:
                top.geometry(geom)
            except tk.TclError:
                pass

        last = cfg.get("last_pdf")
        if last and os.path.isfile(last):
            self._select_pdf(last)

        top.protocol("WM_DELETE_WINDOW", self._on_close)

    def _select_pdf(self, pdf_path: str) -> None:
        """Select pdf_path in the tree if listed (selection fires the load)."""
        want = os.path.normcase(os.path.abspath(pdf_path))
        for iid, path in self._pdf_by_iid.items():
            if os.path.normcase(os.path.abspath(path)) == want:
                self.pdf_tree.selection_set(iid)
                self.pdf_tree.see(iid)
                self.pdf_tree.focus(iid)
                break

    def _on_close(self) -> None:
        self._maybe_save_annots()
        if str(self._bm_frame) in self._mid_split.panes():
            self._bm_sash = self._mid_split.sashpos(0)
        updates = {"geometry": self.winfo_toplevel().geometry()}
        if self._bm_sash is not None:
            updates["bm_sash"] = self._bm_sash
        update_config(updates)
        self.winfo_toplevel().destroy()

    # -- Topics ---------------------------------------------------------------
    def load_topics(self, pdf_path: str) -> None:
        self._topic_entries = []
        self._topic_placeholder = None
        self._bookmarks = load_bookmarks(pdf_path)
        self._populate_bookmark_tree()
        metadata_path = find_metadata_path(pdf_path)
        if metadata_path is None:
            self._topic_placeholder = "(no metadata file found)"
            self._populate_topic_tree()
            return
        try:
            entries = load_metadata(metadata_path)
        except Exception as exc:  # bad format, unreadable, etc.
            self._topic_placeholder = (
                f"(error reading {os.path.basename(metadata_path)})")
            self._populate_topic_tree()
            messagebox.showerror("Metadata error",
                                 f"Could not read {metadata_path}:\n\n{exc}")
            return

        if not entries:
            self._topic_placeholder = (
                f"(no topics in {os.path.basename(metadata_path)})")
            self._populate_topic_tree()
            return

        self._topic_entries = entries
        self._populate_topic_tree()

    def _populate_topic_tree(self) -> None:
        """Fill the topic tree from the loaded entries, honouring the topic
        search filter (substring match on the topic text only)."""
        self.topic_tree.delete(*self.topic_tree.get_children())
        if self._topic_placeholder is not None:
            self.topic_tree.insert(
                "", "end", text=self._topic_placeholder, values=("",))
            return

        needle = self.topic_filter_text.lower()
        count = 0
        for topic, page in self._topic_entries:
            if needle and needle not in topic.lower():
                continue
            # page is read back from the row's values on click; let Tk assign
            # the iid (topics/pages may repeat, so we can't use them as ids).
            self.topic_tree.insert("", "end", text=topic, values=(page,))
            count += 1

        if count == 0 and needle:
            self.topic_tree.insert("", "end", text="(no matches)", values=("",))

    def _populate_bookmark_tree(self) -> None:
        """Fill the bookmark list and attach/detach its pane: while the PDF
        has bookmarks it sits above the topics behind a draggable sash;
        without any, Topics takes the full height."""
        self.bm_tree.delete(*self.bm_tree.get_children())
        for i, bm in enumerate(self._bookmarks):
            # The list index rides in the iid so the right-click menu knows
            # which bookmark it targets.
            self.bm_tree.insert("", "end", iid=f"bm-{i}",
                                text=bm["title"], values=(bm["page"],))
        shown = str(self._bm_frame) in self._mid_split.panes()
        if self._bookmarks and not shown:
            self._mid_split.insert(0, self._bm_frame, weight=1)
            self.after_idle(self._place_bm_sash)
        elif not self._bookmarks and shown:
            self._bm_sash = self._mid_split.sashpos(0)  # keep the dragged spot
            self._mid_split.forget(self._bm_frame)

    def _place_bm_sash(self) -> None:
        """Put the bookmarks/topics sash where the user last dragged it, or
        at 25% of the split's height the first time the pane appears."""
        if str(self._bm_frame) not in self._mid_split.panes():
            return
        height = self._mid_split.winfo_height()
        if height <= 1:                   # split not laid out yet; retry
            self.after(50, self._place_bm_sash)
            return
        pos = self._bm_sash if self._bm_sash is not None else height // 4
        self._mid_split.sashpos(0, max(40, min(pos, height - 80)))

    def _on_topic_search_changed(self, *_args) -> None:
        self.topic_filter_text = self.topic_search_var.get().strip()
        self._populate_topic_tree()

    # -- Bookmarks -------------------------------------------------------------
    def add_bookmark(self) -> None:
        """Bookmark the current page under a user-chosen name."""
        if self.doc is None or self.current_pdf_path is None:
            return
        page = self.current_page + 1
        default = f"Page {page}"
        title = simpledialog.askstring("Add bookmark", "Bookmark name:",
                                       initialvalue=default, parent=self)
        if title is None:               # cancelled
            return
        title = title.strip() or default
        bookmark = {"page": page, "title": title}
        self._bookmarks.append(bookmark)
        self._bookmarks.sort(key=lambda b: b["page"])
        save_bookmarks(self.current_pdf_path, self._bookmarks)
        self._populate_bookmark_tree()
        self._select_bookmark_row(self._bookmarks.index(bookmark))

    def _select_bookmark_row(self, index: int) -> None:
        """Highlight a bookmark's row so the user sees where it landed."""
        iid = f"bm-{index}"
        if self.bm_tree.exists(iid):
            self.bm_tree.selection_set(iid)
            self.bm_tree.see(iid)

    def on_bookmark_selected(self, _event=None) -> None:
        selection = self.bm_tree.selection()
        if not selection:
            return
        values = self.bm_tree.item(selection[0], "values")
        if not values or values[0] in ("", None):
            return
        try:
            page = int(values[0])
        except (ValueError, TypeError):
            return
        self.goto_page(page - 1)        # bookmark pages are 1-based

    def _on_bm_right_click(self, event) -> None:
        iid = self.bm_tree.identify_row(event.y)
        if not iid.startswith("bm-"):
            return
        self._bm_menu_index = int(iid.split("-", 1)[1])
        self.bm_tree.selection_set(iid)
        self.bookmark_menu.tk_popup(event.x_root, event.y_root)

    def _rename_bookmark(self) -> None:
        i = self._bm_menu_index
        if i is None or not 0 <= i < len(self._bookmarks):
            return
        title = simpledialog.askstring("Rename bookmark", "Bookmark name:",
                                       initialvalue=self._bookmarks[i]["title"],
                                       parent=self)
        if title is None or not title.strip():
            return
        self._bookmarks[i]["title"] = title.strip()
        save_bookmarks(self.current_pdf_path, self._bookmarks)
        self._populate_bookmark_tree()
        self._select_bookmark_row(i)

    def _delete_bookmark(self) -> None:
        i = self._bm_menu_index
        if i is None or not 0 <= i < len(self._bookmarks):
            return
        del self._bookmarks[i]
        save_bookmarks(self.current_pdf_path, self._bookmarks)
        self._populate_bookmark_tree()

    # -- Content search (text of the open PDF) --------------------------------
    def _on_content_search_changed(self, *_args) -> None:
        # Debounce: searching every page on each keystroke would stutter.
        if self._content_search_after is not None:
            self.after_cancel(self._content_search_after)
        self._content_search_after = self.after(300, self._run_content_search)

    def _on_content_return(self, _event=None) -> str:
        """Enter runs a pending search immediately, otherwise steps to the
        next match."""
        if self._content_search_after is not None:
            self.after_cancel(self._content_search_after)
            self._content_search_after = None
            self._run_content_search()
        else:
            self.next_match()
        return "break"

    def _run_content_search(self, jump: bool = True) -> None:
        self._content_search_after = None
        self._cancel_content_scan()
        self.content_matches = []
        self.content_match_idx = -1
        needle = self.content_search_var.get().strip()
        if self.doc is None or not needle:
            self._update_match_label()
            if self.doc is not None:
                self.render_page()   # drop any old highlights
            return
        self._content_scan_active = True
        self._content_scan_needle = needle
        self._content_scan_page = 0
        self._content_scan_jump = jump
        self._update_match_label()
        self.render_page()           # drop highlights from the old query
        self._content_scan_chunk()

    def _cancel_content_scan(self) -> None:
        if self._content_scan_after is not None:
            self.after_cancel(self._content_scan_after)
            self._content_scan_after = None
        self._content_scan_active = False

    def _content_scan_chunk(self, pages_per_chunk: int = 50) -> None:
        """Scan the next slice of pages for the current needle, then yield to
        the event loop and reschedule -- keeps the UI live on huge PDFs."""
        self._content_scan_after = None
        if self.doc is None or not self._content_scan_active:
            return
        end = min(self._content_scan_page + pages_per_chunk,
                  self.doc.page_count)
        found_on_current = False
        for pno in range(self._content_scan_page, end):
            for rect in self.doc[pno].search_for(self._content_scan_needle):
                self.content_matches.append((pno, rect))
                found_on_current |= pno == self.current_page
        self._content_scan_page = end
        done = end >= self.doc.page_count

        if self._content_scan_jump:
            # Jump once we know the first hit on/after the page we started
            # on; if the whole scan ends without one, wrap to the first hit.
            idx = next((i for i, (p, _) in enumerate(self.content_matches)
                        if p >= self.current_page), None)
            if idx is None and done and self.content_matches:
                idx = 0
            if idx is not None:
                self._content_scan_jump = False
                if done:
                    self._content_scan_active = False
                self._select_match(idx)
        elif found_on_current:
            self.render_page()       # paint new highlights on the shown page

        if done:
            self._content_scan_active = False
            self._update_match_label()
        else:
            self._update_match_label()
            self._content_scan_after = self.after(1, self._content_scan_chunk)

    def next_match(self) -> None:
        self._step_match(1)

    def prev_match(self) -> None:
        self._step_match(-1)

    def _step_match(self, delta: int) -> None:
        if not self.content_matches:
            return
        if self.content_match_idx == -1:
            # First jump goes to the nearest hit on/after the current page.
            idx = next((i for i, (p, _) in enumerate(self.content_matches)
                        if p >= self.current_page), 0)
            if delta < 0:
                idx = (idx - 1) % len(self.content_matches)
        else:
            idx = (self.content_match_idx + delta) % len(self.content_matches)
        self._select_match(idx)

    def _select_match(self, idx: int) -> None:
        self.content_match_idx = idx
        pno, rect = self.content_matches[idx]
        self.goto_page(pno)          # re-renders, drawing the highlights
        self._update_match_label()
        self._scroll_match_into_view(rect)

    def _update_match_label(self) -> None:
        if not self.content_search_var.get().strip():
            self.match_var.set("")
            return
        n = len(self.content_matches)
        if not self._content_scan_active:
            pos = self.content_match_idx + 1 if self.content_match_idx >= 0 \
                else ("–" if n else 0)
            self.match_var.set(f"{pos} / {n}")
        elif n == 0:
            self.match_var.set("…")   # scan under way, nothing found yet
        else:
            pos = "–" if self.content_match_idx < 0 \
                else self.content_match_idx + 1
            self.match_var.set(f"{pos} / {n}…")

    def _scroll_match_into_view(self, rect) -> None:
        """Scroll the canvas so the match sits about a third of the way down
        the view (render_page resets the scroll to the top)."""
        if self.doc is None:
            return
        page = self.doc[self.current_page]
        page_w = (page.rect.width or 1) * self.zoom
        page_h = (page.rect.height or 1) * self.zoom
        view_w = self.canvas.winfo_width() or 1
        view_h = self.canvas.winfo_height() or 1
        if page_h > view_h:
            frac = (rect.y0 * self.zoom - view_h / 3) / page_h
            self.canvas.yview_moveto(max(0.0, min(1.0, frac)))
        if page_w > view_w:
            frac = (rect.x0 * self.zoom - view_w / 3) / page_w
            self.canvas.xview_moveto(max(0.0, min(1.0, frac)))

    def _draw_match_highlights(self) -> None:
        """Overlay match rectangles on the rendered page (canvas coordinates
        are PDF points scaled by the current zoom)."""
        z = self.zoom
        for i, (pno, rect) in enumerate(self.content_matches):
            if pno != self.current_page:
                continue
            current = i == self.content_match_idx
            self.canvas.create_rectangle(
                rect.x0 * z, rect.y0 * z, rect.x1 * z, rect.y1 * z,
                outline="#e07000" if current else "#c8a800",
                width=2 if current else 1,
                fill="#ffd000", stipple="gray25")

    # -- Text selection & highlight annotations --------------------------------
    def _on_select_start(self, event) -> None:
        if self.doc is None:
            return
        self._select_anchor = (self.canvas.canvasx(event.x),
                               self.canvas.canvasy(event.y))
        self._select_drag = None
        if self._selected_rects:          # a plain click clears the selection
            self._selected_rects = []
            self.canvas.delete("selection")
            self._update_annot_buttons()

    def _on_select_drag(self, event) -> None:
        if self.doc is None or self._select_anchor is None:
            return
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        self._select_drag = (x, y)
        ax, ay = self._select_anchor
        self.canvas.delete("selband")     # rubber-band the drag area
        self.canvas.create_rectangle(ax, ay, x, y, outline="#3b78d8",
                                     dash=(3, 2), tags="selband")

    def _on_select_end(self, _event) -> None:
        self.canvas.delete("selband")
        anchor, self._select_anchor = self._select_anchor, None
        drag, self._select_drag = self._select_drag, None
        if self.doc is None or anchor is None or drag is None:
            return
        z = self.zoom
        x0, x1 = sorted((anchor[0], drag[0]))
        y0, y1 = sorted((anchor[1], drag[1]))
        sel = fitz.Rect(x0 / z, y0 / z, x1 / z, y1 / z)
        words = self.doc[self.current_page].get_text("words")
        self._selected_rects = [fitz.Rect(w[:4]) for w in words
                                if fitz.Rect(w[:4]).intersects(sel)]
        self._draw_selection()
        self._update_annot_buttons()

    def _draw_selection(self) -> None:
        self.canvas.delete("selection")
        z = self.zoom
        for r in self._selected_rects:
            self.canvas.create_rectangle(
                r.x0 * z, r.y0 * z, r.x1 * z, r.y1 * z,
                outline="", fill="#3b78d8", stipple="gray50",
                tags="selection")

    def _update_annot_buttons(self) -> None:
        self.highlight_btn.config(
            state="normal" if self._selected_rects else "disabled")
        self.save_btn.config(
            state="normal" if self._annots_dirty else "disabled")

    def highlight_selection(self) -> None:
        if self.doc is None or not self._selected_rects:
            return
        page = self.doc[self.current_page]
        annot = page.add_highlight_annot(self._selected_rects)
        annot.update()
        self._selected_rects = []
        self._annots_dirty = True
        self._update_annot_buttons()
        self.render_page()                # annotation shows on the repaint

    @staticmethod
    def _find_highlight(page, pt: tuple[float, float]):
        """The highlight annotation under a PDF-space point, or None.

        The caller must keep `page` alive while using the returned annot --
        a PyMuPDF Annot dies with its owning Page object."""
        for annot in page.annots(types=(fitz.PDF_ANNOT_HIGHLIGHT,)):
            if annot.rect.contains(fitz.Point(*pt)):
                return annot
        return None

    def _on_canvas_right_click(self, event) -> None:
        if self.doc is None:
            return
        self._canvas_menu_pt = (self.canvas.canvasx(event.x) / self.zoom,
                                self.canvas.canvasy(event.y) / self.zoom)
        page = self.doc[self.current_page]
        self.canvas_menu.entryconfig(
            0, state="normal" if self._selected_rects else "disabled")
        self.canvas_menu.entryconfig(
            1, state="normal"
            if self._find_highlight(page, self._canvas_menu_pt) else "disabled")
        self.canvas_menu.tk_popup(event.x_root, event.y_root)

    def _remove_highlight_here(self) -> None:
        if self.doc is None or self._canvas_menu_pt is None:
            return
        page = self.doc[self.current_page]
        annot = self._find_highlight(page, self._canvas_menu_pt)
        if annot is None:
            return
        page.delete_annot(annot)
        self._annots_dirty = True
        self._update_annot_buttons()
        self.render_page()

    def save_annotations(self) -> None:
        if self.doc is None or not self._annots_dirty:
            return
        src = self.current_pdf_path or ""
        base, ext = os.path.splitext(src)
        ann_path = base + "(ann)" + ext
        save_copy = False
        # An "(ann)" copy is already the annotated file -- save it in place
        # without asking (avoids piling up "(ann)(ann)" names).
        if not base.endswith("(ann)"):
            choice = messagebox.askyesnocancel(
                "Save highlights",
                "Save highlights as a separate copy?\n\n"
                f"Yes  –  save as {os.path.basename(ann_path)}\n"
                f"No  –  save into {os.path.basename(src)}")
            if choice is None:
                return                    # cancelled; keep changes pending
            save_copy = choice

        if save_copy:
            try:
                self.doc.save(ann_path)   # full write to the new file
            except Exception as exc:
                messagebox.showerror(
                    "Save failed",
                    f"Could not save\n{ann_path}:\n\n{exc}")
                return
            # Give the copy the same topics file so it lists cleanly.
            meta = find_metadata_path(src)
            if meta is not None:
                ann_meta = base + "(ann)" + os.path.splitext(meta)[1]
                if not os.path.exists(ann_meta):
                    try:
                        shutil.copyfile(meta, ann_meta)
                    except OSError:
                        pass              # copy still saved; just no topics
            # ...and the same bookmarks sidecar, if any.
            bm = bookmarks_path(src)
            if os.path.isfile(bm):
                ann_bm = bookmarks_path(ann_path)
                if not os.path.exists(ann_bm):
                    try:
                        shutil.copyfile(bm, ann_bm)
                    except OSError:
                        pass              # copy still saved; just no bookmarks
            self.refresh_pdf_list()       # show the new (ann) file
        else:
            try:
                signed = (self.doc.get_sigflags() or 0) > 0
            except Exception:
                signed = False
            if signed and not messagebox.askyesno(
                    "Signed PDF",
                    "This PDF is digitally signed; saving highlights may "
                    "invalidate the signature.\n\nSave anyway?"):
                return
            try:
                self.doc.saveIncr()       # append-only update, fast
            except Exception as exc:
                messagebox.showerror(
                    "Save failed",
                    f"Could not save highlights to\n{src}:\n\n{exc}")
                return
        self._annots_dirty = False
        self._update_annot_buttons()

    def _maybe_save_annots(self) -> None:
        """Offer to keep unsaved highlights before the document goes away."""
        if self.doc is None or not self._annots_dirty:
            return
        name = os.path.basename(self.current_pdf_path or "this document")
        if messagebox.askyesno(
                "Unsaved highlights",
                f"{name} has unsaved highlights.\n\nSave them?"):
            self.save_annotations()
        self._annots_dirty = False        # saved or deliberately discarded
        self._update_annot_buttons()

    def on_topic_selected(self, _event=None) -> None:
        selection = self.topic_tree.selection()
        if not selection:
            return
        values = self.topic_tree.item(selection[0], "values")
        if not values or values[0] in ("", None):
            return
        try:
            page = int(values[0])
        except (ValueError, TypeError):
            return
        self.goto_page(page - 1)  # metadata pages are 1-based

    # -- Viewer ---------------------------------------------------------------
    def load_pdf(self, pdf_path: str) -> None:
        if fitz is None:
            self._render_message("PyMuPDF not installed.\n"
                                 "Run:  pip install pymupdf pillow")
            return
        if Image is None:
            self._render_message("Pillow not installed.\n"
                                 "Run:  pip install pymupdf pillow")
            return
        if pdf_path == self.current_pdf_path:
            return
        # Stop any in-flight content scan before the document goes away, and
        # offer to keep unsaved highlights.
        self._cancel_content_scan()
        self._maybe_save_annots()
        self._selected_rects = []
        try:
            if self.doc is not None:
                self.doc.close()
            self.doc = fitz.open(pdf_path)
        except Exception as exc:
            self.doc = None
            self._render_message(f"Could not open PDF:\n{exc}")
            return
        self.current_pdf_path = pdf_path
        # Restore the page we were last on for this PDF (clamped to range).
        saved_page = load_config().get("last_pages", {}).get(_page_key(pdf_path))
        self.current_page = 0
        if isinstance(saved_page, int):
            self.current_page = max(0, min(saved_page, self.doc.page_count - 1))
        self.fit_mode = self.fit_pref   # open in the last-used fit preference
        self.render_page()
        update_config({"last_pdf": pdf_path})
        # Re-run an active content search against the new document, but stay
        # on the restored page (matches highlight; ▼/Enter jumps to one).
        if self.content_search_var.get().strip():
            self._run_content_search(jump=False)
        elif self.content_matches:
            self.content_matches = []      # drop hits from the previous PDF
            self.content_match_idx = -1
            self._update_match_label()

    def goto_page(self, page_index: int) -> None:
        if self.doc is None:
            return
        page_index = max(0, min(page_index, self.doc.page_count - 1))
        changed = page_index != self.current_page
        self.current_page = page_index
        if changed and self._selected_rects:
            self._selected_rects = []     # selection was on the old page
            self._update_annot_buttons()
        self.render_page()
        self._maybe_snap()
        if changed and self.current_pdf_path:
            self._save_last_page(self.current_pdf_path, page_index)

    def _save_last_page(self, pdf_path: str, page_index: int) -> None:
        cfg = load_config()
        pages = cfg.get("last_pages", {})
        if not isinstance(pages, dict):
            pages = {}
        pages[_page_key(pdf_path)] = page_index
        update_config({"last_pages": pages})

    def prev_page(self) -> None:
        self.goto_page(self.current_page - 1)

    def next_page(self) -> None:
        self.goto_page(self.current_page + 1)

    def change_zoom(self, factor: float) -> None:
        self.fit_mode = None   # manual zoom overrides any active fit
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, self.zoom * factor))
        self.render_page()

    def fit_width(self) -> None:
        self._set_fit_pref("width")

    def fit_page(self) -> None:
        self._set_fit_pref("page")

    def _set_fit_pref(self, mode: str) -> None:
        """Apply a fit mode, remember it, and persist it for future runs."""
        self.fit_mode = self.fit_pref = mode
        update_config({"fit_pref": mode})
        self.render_page()
        self._maybe_snap()

    def _on_canvas_configure(self, event) -> None:
        """Re-apply the active fit once a window/pane resize has settled.

        <Configure> fires continuously while dragging, so debounce: reschedule
        a one-shot render and only run it after the size stops changing.  A
        manual (+/-) zoom has no fit mode and is left untouched."""
        size = (event.width, event.height)
        if size == self._last_canvas_size:
            return
        self._last_canvas_size = size
        if self.doc is None or not self.fit_mode:
            return
        if self._resize_after is not None:
            self.after_cancel(self._resize_after)
        self._resize_after = self.after(150, self._refit_after_resize)

    def _refit_after_resize(self) -> None:
        self._resize_after = None
        if self.doc is None or not self.fit_mode:
            return
        if self.fit_mode == "page" and self._fitted_canvas_size:
            # The dimension the user dragged drives the zoom; the window
            # snap then re-fits the other dimension to the page.
            self.canvas.update_idletasks()
            ow, oh = self._fitted_canvas_size
            dw = self.canvas.winfo_width() - ow
            dh = self.canvas.winfo_height() - oh
            self._fit_master = "w" if abs(dw) >= abs(dh) else "h"
        try:
            self.render_page()   # _apply_fit recomputes zoom for the new size
            self._maybe_snap()
        finally:
            self._fit_master = None

    def _apply_fit(self) -> None:
        """When a fit mode is active, recompute self.zoom from the current
        canvas size and page dimensions (keeps fit across page changes)."""
        if self.doc is None or not self.fit_mode:
            return
        self.canvas.update_idletasks()   # ensure the canvas has been laid out
        page = self.doc[self.current_page]
        pad = 8
        canvas_w = self.canvas.winfo_width() or 600
        page_w = page.rect.width or 1
        zoom = (canvas_w - pad) / page_w
        if self.fit_mode == "page":
            canvas_h = self.canvas.winfo_height() or 800
            page_h = page.rect.height or 1
            zoom_h = (canvas_h - pad) / page_h
            if self._fit_master == "h":
                zoom = zoom_h            # user dragged height: height rules
            elif self._fit_master != "w":
                zoom = min(zoom, zoom_h)  # no drag in play: whole page fits
            self._fitted_canvas_size = (canvas_w, canvas_h)
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))

    def render_page(self) -> None:
        if self.doc is None:
            return
        self._apply_fit()
        page = self.doc[self.current_page]
        matrix = fitz.Matrix(self.zoom, self.zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        self._photo = ImageTk.PhotoImage(image)

        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self._draw_match_highlights()
        self._draw_selection()
        self.canvas.config(scrollregion=(0, 0, pix.width, pix.height))
        self.canvas.yview_moveto(0)
        self.page_var.set(
            f"Page {self.current_page + 1} / {self.doc.page_count}")
        self._last_pix = (pix.width, pix.height)

    def _maybe_snap(self) -> None:
        """Snap the window to the page in full-page mode.  Called from the
        actions that should resize the window (Full page button, page turns,
        user window resizes) -- deliberately NOT from every render, so e.g.
        selecting a different PDF never moves the window."""
        if self.fit_mode == "page" and self.doc is not None and self._last_pix:
            self._snap_window_to_page(*self._last_pix)

    def _snap_window_to_page(self, page_w: int, page_h: int) -> None:
        """Full-page mode: resize the toplevel so the canvas hugs the rendered
        page instead of leaving gray slack around it.

        Targets page size plus the fit padding so _apply_fit recomputes the
        same zoom afterwards (otherwise each snap would shrink the page by the
        pad).  The geometry change fires the debounced refit, which renders
        and snaps again -- so any part of the resize absorbed by the other
        panes is corrected over a few quick passes."""
        top = self.winfo_toplevel()
        if top.state() != "normal":
            return                      # don't fight a maximized window
        self.canvas.update_idletasks()
        pad = 8                         # keep in sync with _apply_fit
        dw = (page_w + pad) - self.canvas.winfo_width()
        dh = (page_h + pad) - self.canvas.winfo_height()
        if abs(dw) <= 2 and abs(dh) <= 2:
            return                      # close enough -- avoid resize loops
        new_w = max(480, min(top.winfo_width() + dw, top.winfo_screenwidth()))
        new_h = max(360, min(top.winfo_height() + dh,
                             top.winfo_screenheight()))
        if (new_w, new_h) != (top.winfo_width(), top.winfo_height()):
            # The WM resize redistributes width across all panes (by weight),
            # so the canvas only receives part of the change.  Remember the
            # sash positions; the follow-up pass restores them, putting the
            # whole change on the viewer so it lands in one correction.
            n_sashes = len(self.panes.panes()) - 1
            self._saved_sashes = [self.panes.sashpos(i)
                                  for i in range(n_sashes)]
            top.geometry(f"{new_w}x{new_h}")
            if self._snap_after is not None:
                self.after_cancel(self._snap_after)
            self._snap_after = self.after(180, self._snap_again)

    def _snap_again(self) -> None:
        self._snap_after = None
        if self.doc is None or self.fit_mode != "page":
            self._saved_sashes = None
            return
        for i, pos in enumerate(self._saved_sashes or []):
            try:
                self.panes.sashpos(i, pos)
            except tk.TclError:
                pass
        self._saved_sashes = None
        self.render_page()       # re-fits to the new size...
        self._maybe_snap()       # ...and snaps again if still off

    def _render_message(self, message: str) -> None:
        self.canvas.delete("all")
        self.canvas.create_text(
            20, 20, anchor="nw", fill="white", text=message,
            font=("Segoe UI", 11))
        self.page_var.set("—")

    def _on_mousewheel(self, event) -> None:
        # Only handle the wheel when the pointer is over the viewer canvas;
        # otherwise let the PDF/topic trees keep their own wheel scrolling.
        if self.winfo_containing(event.x_root, event.y_root) is not self.canvas:
            return None
        if self.doc is None:
            return "break"

        down = event.delta < 0                       # wheel down = go forward
        top, bottom = self.canvas.yview()
        if down and bottom >= 0.999:                 # at bottom -> next page
            if self.current_page < self.doc.page_count - 1:
                self.goto_page(self.current_page + 1)   # lands at page top
            return "break"
        if not down and top <= 0.001:                # at top -> previous page
            if self.current_page > 0:
                self.goto_page(self.current_page - 1)
                self.canvas.update_idletasks()
                self.canvas.yview_moveto(1.0)           # show its bottom
            return "break"

        self.canvas.yview_scroll(-3 if not down else 3, "units")
        return "break"


# ----------------------------------------------------------------------------
# Minimal Markdown -> Tk Text renderer (for the Help window)
# ----------------------------------------------------------------------------
# Kept dependency-free on purpose: handles headings, bold/italic/inline-code,
# links, bullet/numbered lists, fenced code blocks, horizontal rules, and
# simple pipe tables. Anything fancier is rendered as plain text.

_MD_INLINE = re.compile(
    r"(?P<code>`[^`]+`)"
    r"|(?P<bold>\*\*[^*]+\*\*)"
    r"|(?P<italic>\*[^*\s][^*]*\*)"
    r"|(?P<link>\[[^\]]+\]\([^)]+\))")
_MD_TABLE_SEP = re.compile(r"^\s*:?-{2,}:?\s*$")


def _configure_help_tags(text: "tk.Text") -> None:
    base = "Segoe UI"
    text.tag_configure("h1", font=(base, 18, "bold"), spacing1=10, spacing3=6)
    text.tag_configure("h2", font=(base, 14, "bold"), spacing1=10, spacing3=4)
    text.tag_configure("h3", font=(base, 12, "bold"), spacing1=8, spacing3=3)
    text.tag_configure("bold", font=(base, 11, "bold"))
    text.tag_configure("italic", font=(base, 11, "italic"))
    text.tag_configure("code", font=("Consolas", 10), background="#f0f0f0")
    text.tag_configure("codeblock", font=("Consolas", 10),
                       background="#f5f5f5", lmargin1=24, lmargin2=24,
                       spacing1=1, spacing3=1)
    text.tag_configure("bullet", lmargin1=20, lmargin2=36)
    text.tag_configure("rule", foreground="#bbbbbb", spacing1=4, spacing3=6)
    text.tag_configure("link", foreground="#0a58ca", underline=True)


def _md_inline(text: "tk.Text", line: str, base_tags: tuple) -> None:
    """Insert one line, applying inline bold/italic/code/link formatting."""
    pos = 0
    for m in _MD_INLINE.finditer(line):
        if m.start() > pos:
            text.insert("end", line[pos:m.start()], base_tags)
        if m.group("code"):
            text.insert("end", m.group()[1:-1], base_tags + ("code",))
        elif m.group("bold"):
            text.insert("end", m.group()[2:-2], base_tags + ("bold",))
        elif m.group("italic"):
            text.insert("end", m.group()[1:-1], base_tags + ("italic",))
        elif m.group("link"):
            label, url = re.match(r"\[([^\]]+)\]\(([^)]+)\)", m.group()).groups()
            tag = f"link-{id(m)}-{m.start()}"
            text.insert("end", label, base_tags + ("link", tag))
            text.tag_bind(tag, "<Button-1>",
                          lambda e, u=url: webbrowser.open(u))
            text.tag_bind(tag, "<Enter>",
                          lambda e: text.config(cursor="hand2"))
            text.tag_bind(tag, "<Leave>",
                          lambda e: text.config(cursor="arrow"))
        pos = m.end()
    if pos < len(line):
        text.insert("end", line[pos:], base_tags)
    text.insert("end", "\n")


def _md_table(text: "tk.Text", rows: list[str]) -> None:
    """Render a block of pipe-table lines as aligned monospace text."""
    parsed = []
    for row in rows:
        cells = [c.strip().replace("`", "")
                 for c in row.strip().strip("|").split("|")]
        if all(_MD_TABLE_SEP.match(c) or not c for c in cells):
            continue  # the |---|---| separator row
        parsed.append(cells)
    if not parsed:
        return
    ncol = max(len(r) for r in parsed)
    widths = [0] * ncol
    for r in parsed:
        for j, c in enumerate(r):
            widths[j] = max(widths[j], len(c))
    for r in parsed:
        padded = "  ".join(c.ljust(widths[j]) for j, c in enumerate(r))
        text.insert("end", padded + "\n", ("codeblock",))
    text.insert("end", "\n")


def _md_is_block_start(line: str) -> bool:
    """True if `line` begins a new block (so it can't be lazy continuation)."""
    s = line.strip()
    return (not s or s.startswith("```") or s.startswith("#")
            or s in ("---", "***", "___") or "|" in line
            or re.match(r"^\s*[-*]\s+", line) is not None
            or re.match(r"^\s*\d+\.\s+", line) is not None)


def _render_markdown(text: "tk.Text", md: str) -> None:
    _configure_help_tags(text)
    lines = md.split("\n")
    i, n = 0, len(md.split("\n"))

    def gather_continuation(start: int) -> tuple:
        """Join following non-blank, non-block-start lines (lazy wrapping)."""
        parts, j = [], start
        while j < n and lines[j].strip() and not _md_is_block_start(lines[j]):
            parts.append(lines[j].strip())
            j += 1
        return " ".join(parts), j

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):                 # fenced code block
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                text.insert("end", lines[i] + "\n", ("codeblock",))
                i += 1
            i += 1                                      # skip closing fence
            continue
        if not stripped:
            text.insert("end", "\n")
            i += 1
            continue
        if stripped in ("---", "***", "___"):
            text.insert("end", "─" * 50 + "\n", ("rule",))
            i += 1
            continue
        if stripped.startswith("### "):
            _md_inline(text, stripped[4:], ("h3",))
            i += 1
            continue
        if stripped.startswith("## "):
            _md_inline(text, stripped[3:], ("h2",))
            i += 1
            continue
        if stripped.startswith("# "):
            _md_inline(text, stripped[2:], ("h1",))
            i += 1
            continue
        if "|" in line:                                 # table block
            block = []
            while i < len(lines) and "|" in lines[i]:
                block.append(lines[i])
                i += 1
            _md_table(text, block)
            continue
        bullet = re.match(r"^\s*[-*]\s+(.*)", line)
        if bullet:
            rest, i = gather_continuation(i + 1)
            content = bullet.group(1) + ((" " + rest) if rest else "")
            text.insert("end", "•  ", ("bullet",))
            _md_inline(text, content, ("bullet",))
            continue
        numbered = re.match(r"^\s*(\d+\.)\s+(.*)", line)
        if numbered:
            rest, i = gather_continuation(i + 1)
            content = numbered.group(2) + ((" " + rest) if rest else "")
            text.insert("end", numbered.group(1) + "  ", ("bullet",))
            _md_inline(text, content, ("bullet",))
            continue
        rest, i = gather_continuation(i + 1)             # paragraph
        para = stripped + ((" " + rest) if rest else "")
        _md_inline(text, para, ())


def _page_key(pdf_path: str) -> str:
    """Stable per-PDF key for the last-page map (case/relpath insensitive)."""
    return os.path.normcase(os.path.abspath(pdf_path))


def _config_path() -> str:
    """Per-user settings file (persists across runs, incl. the frozen exe).

    The folder stays "PDFGuide" (the app's former name) so settings saved
    before the rename to PDF Sherpa keep working."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "PDFGuide", "config.json")


def load_config() -> dict:
    try:
        with open(_config_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(settings: dict) -> None:
    try:
        path = _config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(settings, fh)
    except OSError:
        pass  # settings are a convenience -- never crash on a write failure


def update_config(updates: dict) -> None:
    """Merge `updates` into the saved settings (preserves other keys)."""
    cfg = load_config()
    cfg.update(updates)
    save_config(cfg)


def _resource_path(name: str) -> str:
    """Locate a bundled resource, whether running from source or frozen."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def _default_folder() -> str:
    """Default to a 'pdfs' folder next to the app (works when frozen too)."""
    if getattr(sys, "frozen", False):          # bundled by PyInstaller
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "pdfs")


def main() -> None:
    folder = sys.argv[1] if len(sys.argv) > 1 else _default_folder()

    root = tk.Tk()
    root.title(f"PDF Sherpa - V{APP_VERSION}")
    root.geometry("1100x720")

    icon = _resource_path("sherpaicon.ico")
    if os.path.isfile(icon):
        try:
            root.iconbitmap(icon)
        except tk.TclError:
            pass  # non-Windows or unreadable icon -- not fatal

    if fitz is None or Image is None:
        messagebox.showwarning(
            "Missing dependencies",
            "The embedded viewer needs PyMuPDF and Pillow.\n\n"
            "Install them with:\n    pip install pymupdf pillow\n\n"
            "The app will still list PDFs and topics.")

    PDFSherpaApp(root, folder)
    root.mainloop()


if __name__ == "__main__":
    main()

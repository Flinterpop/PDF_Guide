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
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

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


# Metadata extensions we look for, in order of preference.
METADATA_EXTENSIONS = (".toc", ".json")

# Zoom limits for the embedded viewer.
MIN_ZOOM = 0.25
MAX_ZOOM = 4.0
ZOOM_STEP = 1.25


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
        # Re-fit the page when a window resize settles (debounced).
        self._resize_after: str | None = None
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
        ttk.Button(toolbar, text="Refresh",
                   command=self.on_refresh_clicked).pack(side="left", padx=(4, 0))

        self.folder_var = tk.StringVar()
        ttk.Label(toolbar, textvariable=self.folder_var,
                  foreground="#555").pack(side="left", padx=10)

        # Three resizable panes: PDFs | topics | viewer
        panes = ttk.PanedWindow(self, orient="horizontal")
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
        panes.add(left, weight=1)

        # 2. Topics
        mid = ttk.Frame(panes)
        ttk.Label(mid, text="Topics").pack(anchor="w")
        self.topic_tree = ttk.Treeview(mid, columns=("page",),
                                       show="tree headings",
                                       selectmode="browse")
        self.topic_tree.heading("#0", text="Topic")
        self.topic_tree.heading("page", text="Page")
        self.topic_tree.column("#0", width=200, anchor="w")
        self.topic_tree.column("page", width=50, anchor="center", stretch=False)
        self.topic_tree.pack(side="left", fill="both", expand=True)
        topic_sb = ttk.Scrollbar(mid, orient="vertical",
                                 command=self.topic_tree.yview)
        topic_sb.pack(side="right", fill="y")
        self.topic_tree.config(yscrollcommand=topic_sb.set)
        self.topic_tree.bind("<<TreeviewSelect>>", self.on_topic_selected)
        panes.add(mid, weight=1)

        # 3. Embedded viewer
        right = ttk.Frame(panes)
        nav = ttk.Frame(right)
        nav.pack(side="top", fill="x")
        ttk.Button(nav, text="◀ Prev",
                   command=self.prev_page).pack(side="left")
        ttk.Button(nav, text="Next ▶",
                   command=self.next_page).pack(side="left", padx=(4, 8))
        self.page_var = tk.StringVar(value="—")
        ttk.Label(nav, textvariable=self.page_var).pack(side="left")
        ttk.Button(nav, text="−",
                   command=lambda: self.change_zoom(1 / ZOOM_STEP)
                   ).pack(side="right")
        ttk.Button(nav, text="+",
                   command=lambda: self.change_zoom(ZOOM_STEP)
                   ).pack(side="right", padx=(0, 4))
        ttk.Button(nav, text="Full page",
                   command=self.fit_page).pack(side="right", padx=(0, 4))
        ttk.Button(nav, text="Fit width",
                   command=self.fit_width).pack(side="right", padx=4)

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
        canvas_wrap.rowconfigure(0, weight=1)
        canvas_wrap.columnconfigure(0, weight=1)
        panes.add(right, weight=3)

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

    # -- PDF list -------------------------------------------------------------
    def choose_folder(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.folder,
                                         title="Choose folder containing PDFs")
        if chosen:
            self.folder = chosen
            self.refresh_pdf_list()

    def refresh_pdf_list(self) -> None:
        self.folder_var.set(os.path.abspath(self.folder))
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
        update_config({"geometry": self.winfo_toplevel().geometry()})
        self.winfo_toplevel().destroy()

    # -- Topics ---------------------------------------------------------------
    def load_topics(self, pdf_path: str) -> None:
        self.topic_tree.delete(*self.topic_tree.get_children())
        metadata_path = find_metadata_path(pdf_path)
        if metadata_path is None:
            self.topic_tree.insert(
                "", "end", text="(no metadata file found)", values=("",))
            return
        try:
            entries = load_metadata(metadata_path)
        except Exception as exc:  # bad format, unreadable, etc.
            self.topic_tree.insert(
                "", "end",
                text=f"(error reading {os.path.basename(metadata_path)})",
                values=("",))
            messagebox.showerror("Metadata error",
                                 f"Could not read {metadata_path}:\n\n{exc}")
            return

        if not entries:
            self.topic_tree.insert(
                "", "end",
                text=f"(no topics in {os.path.basename(metadata_path)})",
                values=("",))
            return

        for topic, page in entries:
            # page is read back from the row's values on click; let Tk assign
            # the iid (topics/pages may repeat, so we can't use them as ids).
            self.topic_tree.insert("", "end", text=topic, values=(page,))

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

    def goto_page(self, page_index: int) -> None:
        if self.doc is None:
            return
        page_index = max(0, min(page_index, self.doc.page_count - 1))
        changed = page_index != self.current_page
        self.current_page = page_index
        self.render_page()
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
        if self.doc is not None and self.fit_mode:
            self.render_page()   # _apply_fit recomputes zoom for the new size

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
            zoom = min(zoom, (canvas_h - pad) / page_h)
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
        self.canvas.config(scrollregion=(0, 0, pix.width, pix.height))
        self.canvas.yview_moveto(0)
        self.page_var.set(
            f"Page {self.current_page + 1} / {self.doc.page_count}")

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
    root.title("PDF Sherpa")
    root.geometry("1100x720")

    icon = _resource_path("bookicon.ico")
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

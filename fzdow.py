#!/usr/bin/env python3
"""fzdow window. Mode prompt, then the fuzzy card. House look, coral accent.

The window only reads and asks; fzbuf (zig) owns the buffer: ingest, list, keep.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tkinter as tk
from pathlib import Path

W, H = 420, 560

BG = "#050509"
VOID = "#0a0a10"
PANEL = "#101018"
LINE = "#272739"
INK = "#e7e7f2"
INK_STRONG = "#f4f4fb"
INK_SOFT = "#a7a7bd"
INK_MUTE = "#6c6c83"
CORAL = "#ff8f7c"
CORAL_DEEP = "#6e3a33"
SEL = "#2a1614"
SEL_DIM = "#141018"

MONO = ("DejaVu Sans Mono", 10)
MONO_SM = ("DejaVu Sans Mono", 8)
MONO_B = ("DejaVu Sans Mono", 11, "bold")

FZBUF = os.environ.get("FZBUF") or str(Path(__file__).resolve().parent / "buf" / "zig-out" / "bin" / "fzbuf")
ROWS = 18
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def fzbuf(*args: str) -> tuple[int, str]:
    p = subprocess.run([FZBUF, *args], capture_output=True, text=True)
    return p.returncode, (p.stdout if p.returncode == 0 else p.stderr).strip()


def parse_index(text: str) -> list[dict[str, str]]:
    keys = ("id", "state", "session", "mode", "ts", "edits", "src", "buf")
    rows = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) == len(keys):
            rows.append(dict(zip(keys, parts)))
    rows.sort(key=lambda r: r["ts"], reverse=True)
    return rows


def fuzzy(q: str, s: str) -> tuple[int, list[int]] | None:
    if not q:
        return 0, []
    lq, ls = q.lower(), s.lower()
    hits: list[int] = []
    j = score = 0
    prev = -2
    for i, ch in enumerate(ls):
        if j < len(lq) and ch == lq[j]:
            hits.append(i)
            score += 16 if i == prev + 1 else 8
            if i == 0 or ls[i - 1] in "/._- ":
                score += 10
            if prev >= 0 and i != prev + 1:
                score -= 3
            prev = i
            j += 1
    if j < len(lq):
        return None
    return score - len(s) // 8, hits


def words(s: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", s.lower()) if w and not w.isdigit()]


def suggest_name(row: dict[str, str]) -> str:
    """Five words: project · file · mode · weekday · revision.
    Stand-in until the house naming method is written down."""
    src = Path(row["src"])
    project = (words(src.parent.name) or ["home"])[0]
    stem = (words(src.stem) or ["file"])[0]
    mode = "versioned" if row["mode"] == "versioned" else "last"
    try:
        y, m, d = (int(x) for x in row["ts"][:10].split("-"))
        import datetime
        day = DAYS[datetime.date(y, m, d).weekday()]
    except ValueError:
        day = "someday"
    rev = "r" + row["id"].rsplit(":", 2)[-2] if row["mode"] == "versioned" else "final"
    return "-".join([project, stem, mode, day, rev])


class Window:
    def __init__(self, transcript: Path) -> None:
        self.transcript = transcript
        self.session = transcript.stem
        self.root = tk.Tk()
        self.root.title("fzdow")
        self.root.geometry(f"{W}x{H}")
        self.root.minsize(W, H)
        self.root.configure(bg=BG)
        self.frame: tk.Frame | None = None
        self.rows: list[dict[str, str]] = []
        self.col = 1
        self.sel = [0, 0]
        self.show_prompt()

    # ---- screen 1: the ui prompt ------------------------------------------
    def clear(self) -> tk.Frame:
        if self.frame is not None:
            self.frame.destroy()
        self.frame = tk.Frame(self.root, bg=VOID, highlightthickness=1, highlightbackground=CORAL_DEEP)
        self.frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        return self.frame

    def show_prompt(self) -> None:
        f = self.clear()
        tk.Label(f, text=f"⬡  fzdow  /  {self.session[:8]}", bg=VOID, fg=CORAL, font=MONO_SM, anchor="w").pack(fill=tk.X, padx=12, pady=(12, 18))
        self.choice = 0
        self.stubs: list[tk.Label] = []
        for i, (label, sub) in enumerate((("versioned  out", "every revision, one file each"),
                                          ("authoritative  last in", "only the final state counts"))):
            box = tk.Frame(f, bg=VOID, highlightthickness=1, highlightbackground=LINE)
            box.pack(fill=tk.X, padx=12, pady=(0, 10))
            top = tk.Label(box, text=f"{i + 1}  {label}", bg=VOID, fg=INK, font=MONO_B, anchor="w")
            top.pack(fill=tk.X, padx=10, pady=(10, 2))
            tk.Label(box, text=sub, bg=VOID, fg=INK_MUTE, font=MONO_SM, anchor="w").pack(fill=tk.X, padx=10, pady=(0, 10))
            for w in (box, top):
                w.bind("<Button-1>", lambda _e, n=i: self.pick_mode(n))
            self.stubs.append(box)
        self.status = tk.Label(f, text="", bg=VOID, fg=CORAL, font=MONO_SM, anchor="w")
        self.status.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=12)
        self.paint_stubs()
        self.root.bind("<Key>", self.prompt_key)

    def paint_stubs(self) -> None:
        for i, b in enumerate(self.stubs):
            b.configure(highlightbackground=CORAL if i == self.choice else LINE)

    def prompt_key(self, e: tk.Event) -> None:
        if e.keysym in ("1", "2"):
            self.pick_mode(int(e.keysym) - 1)
        elif e.keysym in ("Up", "Down", "Tab"):
            self.choice = 1 - self.choice
            self.paint_stubs()
        elif e.keysym == "Return":
            self.pick_mode(self.choice)
        elif e.keysym == "Escape":
            self.root.destroy()

    def pick_mode(self, n: int) -> None:
        mode = ("versioned", "last")[n]
        self.status.configure(text="buffering…")
        self.root.update_idletasks()
        code, out = fzbuf("ingest", mode, str(self.transcript))
        if code != 0:
            self.status.configure(text=out or "fzbuf failed")
            return
        self.mode = mode
        self.show_card()

    # ---- screen 2: the fuzzy card -------------------------------------------
    def load(self) -> None:
        code, out = fzbuf("list")
        rows = parse_index(out) if code == 0 else []
        self.rows = [r for r in rows if r["session"] == self.session and r["mode"] == self.mode and r["state"] == "buffered"]

    def show_card(self) -> None:
        self.root.unbind("<Key>")
        f = self.clear()
        top = tk.Frame(f, bg=VOID)
        top.pack(fill=tk.X, padx=10, pady=(8, 4))
        tk.Label(top, text="root", bg=VOID, fg=INK_MUTE, font=MONO_SM).pack(side=tk.LEFT)
        self.root_var = tk.StringVar(value="~")
        self.root_entry = tk.Entry(top, textvariable=self.root_var, bg=VOID, fg=INK_SOFT, insertbackground=CORAL,
                                   relief="flat", highlightthickness=0, font=MONO)
        self.root_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        self.count = tk.Label(top, text="", bg=VOID, fg=INK_MUTE, font=MONO_SM)
        self.count.pack(side=tk.RIGHT)

        cols = tk.Frame(f, bg=VOID)
        cols.pack(fill=tk.BOTH, expand=True, padx=10)
        cols.columnconfigure(0, weight=1, uniform="c")
        cols.columnconfigure(1, weight=1, uniform="c")
        self.lists: list[tk.Listbox] = []
        self.bars: list[tk.Frame] = []
        for i in range(2):
            wrap = tk.Frame(cols, bg=VOID)
            wrap.grid(row=0, column=i, sticky="nsew", padx=(0, 4) if i == 0 else (4, 0))
            bar = tk.Frame(wrap, height=1, bg=LINE)
            bar.pack(fill=tk.X)
            lb = tk.Listbox(wrap, bg=VOID, fg=INK_SOFT, selectbackground=SEL, selectforeground=INK_STRONG,
                            highlightthickness=0, relief="flat", activestyle="none", font=MONO, height=ROWS,
                            exportselection=False)
            lb.pack(fill=tk.BOTH, expand=True)
            lb.bind("<<ListboxSelect>>", lambda _e, c=i: self.clicked(c))
            self.lists.append(lb)
            self.bars.append(bar)

        # the card's back: header + five-word name
        self.back = tk.Frame(f, bg=VOID, highlightthickness=1, highlightbackground=CORAL)
        self.back_title = tk.Label(self.back, text="", bg=VOID, fg=CORAL, font=MONO_B, anchor="w")
        self.back_title.pack(fill=tk.X, padx=10, pady=(8, 2))
        self.back_meta = tk.Label(self.back, text="", bg=VOID, fg=INK_MUTE, font=MONO_SM, anchor="w", justify="left")
        self.back_meta.pack(fill=tk.X, padx=10)
        self.name_var = tk.StringVar()
        self.name_entry = tk.Entry(self.back, textvariable=self.name_var, bg=PANEL, fg=INK_STRONG, insertbackground=CORAL,
                                   relief="flat", highlightthickness=1, highlightbackground=LINE, highlightcolor=CORAL, font=MONO)
        self.name_entry.pack(fill=tk.X, padx=10, pady=8)
        self.name_entry.bind("<Return>", lambda _e: self.keep())
        self.name_entry.bind("<Escape>", lambda _e: self.unflip())
        self.flipped = False

        bottom = tk.Frame(f, bg=VOID, highlightthickness=0)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(4, 8))
        tk.Frame(f, height=1, bg=LINE).pack(side=tk.BOTTOM, fill=tk.X, padx=10)
        tk.Label(bottom, text="›", bg=VOID, fg=CORAL, font=MONO_B).pack(side=tk.LEFT)
        self.query_var = tk.StringVar()
        self.query = tk.Entry(bottom, textvariable=self.query_var, bg=VOID, fg=INK_STRONG, insertbackground=CORAL,
                              relief="flat", highlightthickness=0, font=MONO)
        self.query.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        self.msg = tk.Label(bottom, text="", bg=VOID, fg=CORAL, font=MONO_SM)
        self.msg.pack(side=tk.RIGHT)

        for e in (self.query, self.root_entry):
            e.bind("<Key>", self.card_key)
        self.root_var.trace_add("write", lambda *_: self.refresh(reset=True))
        self.query_var.trace_add("write", lambda *_: self.refresh(reset=True))
        self.load()
        self.refresh(reset=True)
        self.query.focus_set()

    def filtered(self) -> list[list[dict]]:
        base = self.root_var.get().strip().rstrip("/") or "~"
        home = str(Path.home())
        pre = home if base == "~" else base.replace("~", home, 1)
        q = self.query_var.get()
        dirs: dict[str, dict] = {}
        files = []
        for r in self.rows:
            if not (r["src"] == pre or r["src"].startswith(pre + "/")):
                continue
            d = str(Path(r["src"]).parent)
            dirs.setdefault(d, {"label": d.replace(home, "~", 1) + "/", "row": r, "dir": d})
            label = Path(r["src"]).name + (f"  ·{r['id'].rsplit(':', 2)[-2]}" if r["mode"] == "versioned" else "")
            files.append({"label": label, "row": r})
        out = []
        for items in (list(dirs.values()), files):
            scored = [(m, it) for it in items if (m := fuzzy(q, it["label"])) is not None]
            if q:
                scored.sort(key=lambda t: -t[0][0])
            out.append([it for _, it in scored])
        return out

    def refresh(self, reset: bool = False) -> None:
        self.view = self.filtered()
        if reset:
            self.sel = [0, 0]
            if not self.view[self.col] and self.view[1 - self.col]:
                self.col = 1 - self.col
        for i, lb in enumerate(self.lists):
            lb.delete(0, tk.END)
            for it in self.view[i]:
                lb.insert(tk.END, it["label"])
            if self.view[i]:
                self.sel[i] = min(self.sel[i], len(self.view[i]) - 1)
                lb.selection_set(self.sel[i])
                lb.see(self.sel[i])
                lb.itemconfigure(self.sel[i], selectbackground=SEL if i == self.col else SEL_DIM)
            self.bars[i].configure(bg=CORAL if i == self.col else LINE)
        self.count.configure(text=f"{len(self.view[0])} · {len(self.view[1])}")

    def clicked(self, c: int) -> None:
        cur = self.lists[c].curselection()
        if cur:
            self.col, self.sel[c] = c, cur[0]
            self.refresh()

    def card_key(self, e: tk.Event) -> str | None:
        k, ctrl = e.keysym, bool(e.state & 0x4)
        if k == "Down" or (ctrl and k in ("n", "j")):
            self.move(1)
        elif k == "Up" or (ctrl and k in ("p", "k")):
            self.move(-1)
        elif k == "Left" or (ctrl and k == "h"):
            self.switch(0)
        elif k == "Right" or (ctrl and k == "l"):
            self.switch(1)
        elif k == "Return" and e.widget is self.root_entry:
            self.query.focus_set()
        elif k in ("Return", "Tab"):
            self.flip()
        elif k == "Escape":
            var = self.root_var if e.widget is self.root_entry else self.query_var
            if var.get() in ("", "~"):
                self.root.destroy()
            else:
                var.set("~" if e.widget is self.root_entry else "")
        else:
            return None
        return "break"

    def move(self, d: int) -> None:
        n = len(self.view[self.col])
        if n:
            self.sel[self.col] = max(0, min(n - 1, self.sel[self.col] + d))
            self.refresh()

    def switch(self, c: int) -> None:
        if self.view[c]:
            self.col = c
            self.refresh()

    def current(self) -> dict | None:
        items = self.view[self.col]
        return items[self.sel[self.col]] if items else None

    def flip(self) -> None:
        it = self.current()
        if it is None:
            return
        if self.col == 0:  # a directory: make it the root
            self.root_var.set(it["label"].rstrip("/"))
            self.switch(1)
            return
        r = it["row"]
        self.back_title.configure(text=Path(r["src"]).name)
        self.back_meta.configure(text=f"{r['ts'].replace('T', ' ')[:19]}  ·  edits {r['edits']}\n{r['src'].replace(str(Path.home()), '~', 1)}")
        self.name_var.set(suggest_name(r))
        self.back.place(relx=0, rely=0.25, relwidth=1, x=0)
        self.back.lift()
        self.flipped = True
        self.name_entry.focus_set()
        self.name_entry.icursor(tk.END)

    def unflip(self) -> str:
        self.back.place_forget()
        self.flipped = False
        self.query.focus_set()
        return "break"

    def keep(self) -> str:
        it = self.current()
        name = re.sub(r"[^a-z0-9]+", "-", self.name_var.get().lower()).strip("-")
        if it is None:
            return "break"
        if len(name.split("-")) != 5:
            self.msg.configure(text="five words")
            return "break"
        code, out = fzbuf("keep", it["row"]["id"], name)
        self.msg.configure(text=("kept " + name) if code == 0 else (out or "keep failed"))
        if code == 0:
            self.load()
            self.unflip()
            self.refresh()
        return "break"

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_file():
        print("usage: fzdow.py <session.jsonl>", file=sys.stderr)
        return 2
    Window(Path(sys.argv[1])).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

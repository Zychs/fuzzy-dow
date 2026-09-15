#!/usr/bin/env python3
"""Clump the work under a root. Stem, place, time, mentions -> clumps.

Each item becomes a small vector: stem tokens, parent-path tokens, mtime.
Clumps are seeded by each item's most telling token, then settled on centroids; each clump gets a centroid; every
item's offset is its distance from that centroid. An item closer to another
clump's centroid (by MARGIN) is remapped there. Your lines in clumps.tsv
(source "you") are pinned and never moved.
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

HOME = Path.home()
TSV = HOME / ".sesefus" / "clumps.tsv"
REPORT = HOME / ".sesefus" / "clump-report.json"

MAX_DEPTH = 3
SKIP = {
    "node_modules", "venv", ".venv", "__pycache__", ".git", ".cache", ".zig-cache",
    "zig-out", "build", ".gradle", ".pytest_cache", "site-packages", "Music", "Videos",
    "Pictures", "Public", "Templates",
}
ALIAS = {"sesephus": "sesefus", "seseph": "sesefus", "circadian": "circadia", "neuria": "neurialab"}
STOP = {"md", "txt", "py", "sh", "json", "the", "and", "to", "of", "map", "publish", "tar", "gz",
        "xz", "deb", "x86", "64", "amd64", "linux", "dev", "main", "src", "app", "readme", "file"}
VERSION = re.compile(r"\d+(\.\d+)+|\d{4}-\d{2}-\d{2}|\b\d+\b")

W_STEM, W_PLACE, W_TIME = 0.6, 0.25, 0.15
TIME_SCALE = 3 * 86400  # three days apart ≈ unrelated in time
LINK = 0.34             # how near a loose item must sit to join a clump
MARGIN = 0.08           # remap only when clearly nearer another centroid


def tokens(name: str) -> list[str]:
    s = VERSION.sub(" ", name.lower())
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
    out = []
    for t in re.split(r"[^a-z0-9]+", s):
        t = ALIAS.get(t, t)
        if len(t) > 1 and t not in STOP and not t.isdigit():
            out.append(t)
    return out


def vendored(n: str) -> bool:
    return n.startswith("zig-x86") or n.startswith("zig-linux") or n in {"android-dev", "espeak-ng-data", "piper"}


def scan(root: Path) -> list[dict]:
    items = []
    base = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        d = Path(dirpath)
        depth = len(d.parts) - base
        dirnames[:] = [n for n in dirnames if n not in SKIP and not n.startswith(".") and not vendored(n)]
        if depth >= MAX_DEPTH:
            dirnames[:] = []
        for n in dirnames + [f for f in filenames if not f.startswith(".")]:
            p = d / n
            try:
                st = p.lstat()
            except OSError:
                continue
            rel = p.relative_to(root)
            stem = tokens(n)
            place = [t for part in rel.parts[:-1] for t in tokens(part)]
            if not stem and not place:
                continue
            items.append({
                "path": "~/" + str(rel) if root == HOME else str(p),
                "name": n, "dir": p.is_dir(), "mtime": st.st_mtime,
                "stem": stem, "place": place,
            })
    return items


def jacc(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    inter = sum((a & b).values())
    union = sum((a | b).values())
    return inter / union if union else 0.0


def sim(a: dict, b: dict) -> float:
    s = jacc(a["S"], b["S"])
    p = jacc(a["P"], b["P"])
    t = math.exp(-abs(a["mtime"] - b["mtime"]) / TIME_SCALE)
    return W_STEM * s + W_PLACE * p + W_TIME * t


def vec(it: dict) -> dict:
    return {"S": Counter(it["stem"] + it["place"][-1:]), "P": Counter(it["place"]), "mtime": it["mtime"]}


def centroid(members: list[dict]) -> dict:
    S, P = Counter(), Counter()
    for m in members:
        S.update(m["v"]["S"]); P.update(m["v"]["P"])
    n = len(members)
    # keep tokens shared by at least a third of the clump — the clump's "name"
    keep = lambda c: Counter({k: 1 for k, v in c.items() if v / n >= 0.34})
    return {"S": keep(S) or S, "P": keep(P), "mtime": sum(m["mtime"] for m in members) / n}


def group(items: list[dict]) -> list[list[dict]]:
    """Seed by the dominant token, then settle on centroids. Linear in items x clumps."""
    df = Counter(t for it in items for t in set(it["stem"] + it["place"]))
    seeds: dict[str, list[dict]] = {}
    for it in items:
        # the rarest-but-shared token names the work; ubiquitous tokens don't
        cand = [t for t in it["place"][:1] + it["stem"] if 1 < df[t] < len(items) * 0.3]
        key = min(cand, key=lambda t: df[t]) if it["place"][:1] == [] and cand else (it["place"][:1] or cand or ["~"])[0]
        seeds.setdefault(key, []).append(it)
    clumps = list(seeds.values())
    for _ in range(4):
        cents = [centroid(c) for c in clumps]
        nxt: list[list[dict]] = [[] for _ in clumps]
        for it in items:
            i = max(range(len(cents)), key=lambda i: sim(it["v"], cents[i]))
            nxt[i].append(it)
        clumps = [c for c in nxt if c]
    return clumps


def label(c: dict, used: set[str]) -> str:
    top = [k for k, _ in c["S"].most_common(2)] or ["loose"]
    name = "@" + "·".join(top)
    while name in used:
        name += "'"
    used.add(name)
    return name


def load_pins() -> dict[str, str]:
    pins = {}
    if TSV.is_file():
        for line in TSV.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) == 3 and parts[2] == "you":
                pins[parts[0]] = parts[1]
    return pins


def main() -> int:
    root = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else HOME
    items = scan(root)
    for it in items:
        it["v"] = vec(it)
    pins = load_pins()
    free = [it for it in items if it["path"] not in pins]

    raw = group(free)
    solo = [m for c in raw if len(c) < 3 for m in c]
    clumps = [c for c in raw if len(c) >= 3]

    used: set[str] = set()
    named = [{"members": c, "c": centroid(c)} for c in clumps]
    for k in named:
        k["name"] = label(k["c"], used)

    # centroidal remap: each item goes to its nearest centroid if clearly nearer
    moved = []
    for k in named:
        for m in list(k["members"]):
            own = sim(m["v"], k["c"])
            best = max(named, key=lambda o: sim(m["v"], o["c"]))
            if best is not k and sim(m["v"], best["c"]) - own > MARGIN:
                k["members"].remove(m); best["members"].append(m)
                moved.append({"path": m["path"], "from": k["name"], "to": best["name"],
                              "gain": round(sim(m["v"], best["c"]) - own, 3)})
    # loose items join a clump only if they sit near its centroid
    loose = []
    for m in solo:
        best = max(named, key=lambda o: sim(m["v"], o["c"]), default=None)
        if best and sim(m["v"], best["c"]) >= LINK:
            best["members"].append(m)
        else:
            loose.append(m)

    out, rows = [], []
    for k in sorted(named, key=lambda k: -len(k["members"])):
        if not k["members"]:
            continue
        k["c"] = centroid(k["members"])
        mem = sorted(({"path": m["path"], "dir": m["dir"],
                       "offset": round(1 - sim(m["v"], k["c"]), 3)} for m in k["members"]),
                     key=lambda m: m["offset"])
        spread = sum(m["offset"] for m in mem) / len(mem)
        out.append({"name": k["name"], "n": len(mem), "spread": round(spread, 3),
                    "last": time.strftime("%Y-%m-%d", time.localtime(k["c"]["mtime"])),
                    "members": mem})
        rows += [f"{m['path']}\t{k['name']}\tauto" for m in mem]
    rows += [f"{p}\t{c}\tyou" for p, c in pins.items()]

    TSV.parent.mkdir(parents=True, exist_ok=True)
    TSV.write_text("\n".join(rows) + "\n", encoding="utf-8")
    report = {"root": str(root), "at": time.strftime("%Y-%m-%d %H:%M"), "items": len(items),
              "pinned": len(pins), "clumps": out, "moved": moved,
              "loose": [m["path"] for m in loose]}
    REPORT.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(f"{len(items)} items -> {len(out)} clumps, {len(moved)} remapped, "
          f"{len(loose)} loose, {len(pins)} pinned  ·  {TSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

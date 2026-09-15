# fuzzy DOW (`fzdow`)

A small desktop window for collecting the files an AI coding session edited.
It reads one Claude Code session transcript, rebuilds every file that
session's **Write** and **Edit** tool calls touched, holds them in a buffer,
and lets you fuzzy-find one and keep it under a five-word name. The look
follows journal-clip's dark palette, with a coral accent.

## What works now

- **Session scope.** `fzdow` opens on the session it was run from:
  `$CLAUDE_CODE_SESSION_ID` when it's set (for example with `! fzdow` inside
  Claude Code), otherwise the newest transcript for the current directory
  under `~/.claude/projects/`.
- **Mode prompt** (the first screen):
  - `1  versioned out` buffers every revision of each file.
  - `2  authoritative last in` buffers only each file's final state.
- **Buffer** (`fzbuf`, written in Zig):
  - Writes files to `~/test-buffer/<session>/`.
  - Each file starts with a header line: creation time, edit count and a
    tally, like `# fzdow · created … · edits 7  ||||/ ||`.
  - The header goes below a `#!` or `<!doctype` first line, and JSON and
    unknown file types get no header.
  - The index (`index.tsv`) is replaced atomically, and running ingest again
    adds nothing twice.
- **Fuzzy card** (420×560, the same size as the prompt):
  - Root field on top, query at the bottom.
  - Directories column on the left, files column on the right, newest first.
  - Matching letters must appear in order, gaps allowed.
- **Keep.** Enter on a file flips to its details, with a suggested
  five-word name. Enter again moves the file to
  `~/test-buffer/kept/<name>.<ext>`. Names that aren't exactly five words,
  names already taken, and files already kept are refused.
- **`clump.py`** is a separate tool, not used by the window. It groups the
  folders under `~` into related clumps and writes `~/.sesefus/clumps.tsv`
  and `~/.sesefus/clump-report.json`.

## Requirements

- Linux with an X display (`DISPLAY`; the launcher defaults to `:0`).
- Python 3 with Tk: `sudo apt install python3-tk`. No pip packages.
- Zig `0.17.0-dev.813+2153f8143`. The buffer uses the 0.17 `std.Io` API, so
  older releases won't build it.
- Claude Code session transcripts in `~/.claude/projects/`.

## Install and start

```sh
git clone https://github.com/Zychs/fuzzy-dow.git ~/fuzzyDOW
cd ~/fuzzyDOW/buf && zig build --release=safe   # builds buf/zig-out/bin/fzbuf
cd ~/fuzzyDOW && ./fzdow                          # opens the window
```

To start it as `fzdow` from anywhere, add an alias:

```sh
echo 'alias fzdow="$HOME/fuzzyDOW/fzdow"' >> ~/.bashrc
```

Environment overrides:

- `FZBUF` sets the path to the `fzbuf` binary.
- `FZBUF_ROOT` sets the buffer folder (default `~/test-buffer`).

## Keys

Mode prompt:

| Key | Action |
|---|---|
| `1` / `2` | Pick versioned / authoritative |
| `↑` `↓` `Tab` | Move between the two choices |
| `Enter` | Confirm the highlighted choice |
| `Esc` | Quit |

Card:

| Key | Action |
|---|---|
| `↓` / `Ctrl-n` / `Ctrl-j` | Next row |
| `↑` / `Ctrl-p` / `Ctrl-k` | Previous row |
| `←` / `Ctrl-h` · `→` / `Ctrl-l` | Directories column · files column |
| `Enter` in root | Jump to the query |
| `Enter` / `Tab` on a directory | Make it the root |
| `Enter` / `Tab` on a file | Flip to its details and name |
| `Enter` on the details | Keep the file under the name |
| `Esc` | On the details: go back. Otherwise: clear the field, or quit if it's already empty |

Clicking a row selects it.

## Buffer CLI

```sh
fzbuf ingest versioned|last <session.jsonl>
fzbuf list                          # index.tsv: id state session mode ts edits src buf
fzbuf keep <id> <five-word-name>
```

## Layout

```
fzdow            launcher: picks the session, opens the window
fzdow.py         Tk window: mode prompt + fuzzy card (standard library only)
buf/             fzbuf, the Zig buffer manager
  build.zig
  build.zig.zon
  src/main.zig   ingest / list / keep, plus unit tests
clump.py         separate tool that groups folders under ~ into clumps
```

## Known limitations

- Only edits made through Claude Code's Write and Edit tools are captured.
  Files changed by shell commands or scripts during a session don't appear.
- The five-word name suggestion (project, file, mode, weekday, revision) is
  a stand-in for the owner's own naming method.
- The flip is a panel shown over the card, not an animation.
- The buffer only grows. Nothing is deleted, and kept files are moved out of
  the buffer, not copied.

## Proposals, not built yet

- Tracking shell-made edits by comparing file modification times on disk.
- Sessions from other tools (Codex and others).
- Syncing kept files to a remote host.
- Pinning and merging clumps from inside the window.

## Checks

```sh
cd buf && zig build test
```

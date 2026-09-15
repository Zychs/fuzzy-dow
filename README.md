# fuzzy DOW (`fzdow`)
dedicated finder ; unlike macintosh os
## Install and start

unreleased
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

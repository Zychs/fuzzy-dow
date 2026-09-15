//! fzbuf — the fzdow buffer. One session transcript in, standalone files out.
//!
//!   fzbuf ingest versioned|last <session.jsonl>   rebuild edited files into the buffer
//!   fzbuf list                                    print index.tsv
//!   fzbuf keep <id> <five-word-name>              move a buffered file to kept/
//!
//! Buffer root: $FZBUF_ROOT, else ~/test-buffer. Nothing outside it is written.
//! index.tsv: id state session mode ts edits src buf — replaced atomically.

const std = @import("std");

const Event = struct {
    path: []const u8,
    ts: []const u8,
    content: []const u8,
};

const Row = struct {
    id: []const u8,
    state: []const u8,
    session: []const u8,
    mode: []const u8,
    ts: []const u8,
    edits: []const u8,
    src: []const u8,
    buf: []const u8,
};

fn usage() void {
    std.debug.print(
        \\fzbuf ingest versioned|last <session.jsonl>
        \\fzbuf list
        \\fzbuf keep <id> <five-word-name>
        \\
    , .{});
}

// ---- files -------------------------------------------------------------------

fn readAll(a: std.mem.Allocator, io: std.Io, path: []const u8) ![]u8 {
    const file = try std.Io.Dir.openFileAbsolute(io, path, .{ .mode = .read_only });
    defer file.close(io);
    var rbuf: [64 * 1024]u8 = undefined;
    var r = file.reader(io, &rbuf);
    return r.interface.allocRemaining(a, .unlimited);
}

fn readOrEmpty(a: std.mem.Allocator, io: std.Io, path: []const u8) []u8 {
    return readAll(a, io, path) catch a.dupe(u8, "") catch &.{};
}

fn exists(io: std.Io, path: []const u8) bool {
    std.Io.Dir.cwd().access(io, path, .{}) catch return false;
    return true;
}

/// Write to a sibling temp file, then rename over the target: a reader never sees half a file.
fn writeAtomic(a: std.mem.Allocator, io: std.Io, path: []const u8, parts: []const []const u8) !void {
    const tmp = try std.fmt.allocPrint(a, "{s}.tmp", .{path});
    {
        const f = try std.Io.Dir.createFileAbsolute(io, tmp, .{ .truncate = true });
        defer f.close(io);
        var wbuf: [64 * 1024]u8 = undefined;
        var w = f.writer(io, &wbuf);
        for (parts) |p| try w.interface.writeAll(p);
        try w.flush();
    }
    try std.Io.Dir.renameAbsolute(tmp, path, io);
}

// ---- transcript ----------------------------------------------------------------

fn str(obj: std.json.ObjectMap, key: []const u8) ?[]const u8 {
    const v = obj.get(key) orelse return null;
    return switch (v) {
        .string => |s| s,
        else => null,
    };
}

/// The file as it stood right after one Write or Edit, from the tool result alone.
fn eventFromLine(a: std.mem.Allocator, line: []const u8) ?Event {
    if (std.mem.indexOf(u8, line, "\"toolUseResult\":{") == null) return null;
    if (std.mem.indexOf(u8, line, "\"filePath\"") == null) return null;
    const v = std.json.parseFromSliceLeaky(std.json.Value, a, line, .{}) catch return null;
    if (v != .object) return null;
    const ts = str(v.object, "timestamp") orelse return null;
    const tur_v = v.object.get("toolUseResult") orelse return null;
    if (tur_v != .object) return null;
    const tur = tur_v.object;
    const path = str(tur, "filePath") orelse return null;

    if (str(tur, "oldString")) |old| {
        const new = str(tur, "newString") orelse return null;
        const orig = str(tur, "originalFile") orelse return null;
        const all = if (tur.get("replaceAll")) |r| (r == .bool and r.bool) else false;
        const content = if (all)
            std.mem.replaceOwned(u8, a, orig, old, new) catch return null
        else blk: {
            const at = std.mem.indexOf(u8, orig, old) orelse return null;
            break :blk std.mem.concat(a, u8, &.{ orig[0..at], new, orig[at + old.len ..] }) catch return null;
        };
        return .{ .path = path, .ts = ts, .content = content };
    }
    if (str(tur, "content")) |c| {
        // Write results carry the whole file; Read results also have "content" but a "file" type
        const kind = str(tur, "type") orelse "";
        if (!std.mem.eql(u8, kind, "create") and !std.mem.eql(u8, kind, "update")) return null;
        return .{ .path = path, .ts = ts, .content = c };
    }
    return null;
}

// ---- header ---------------------------------------------------------------------

const Comment = struct { open: []const u8, close: []const u8 };

fn commentFor(name: []const u8) ?Comment {
    const ext = std.fs.path.extension(name);
    const hash = [_][]const u8{ ".py", ".sh", ".bash", ".toml", ".yaml", ".yml", ".rb", ".conf", ".service", ".txt", ".tsv", ".ini", ".cfg" };
    const slash = [_][]const u8{ ".zig", ".js", ".ts", ".jsx", ".tsx", ".c", ".h", ".cpp", ".go", ".rs", ".kt", ".kts", ".java", ".swift" };
    const angle = [_][]const u8{ ".md", ".html", ".htm", ".xml", ".svg" };
    for (hash) |e| if (std.ascii.eqlIgnoreCase(ext, e)) return .{ .open = "# ", .close = "" };
    for (slash) |e| if (std.ascii.eqlIgnoreCase(ext, e)) return .{ .open = "// ", .close = "" };
    for (angle) |e| if (std.ascii.eqlIgnoreCase(ext, e)) return .{ .open = "<!-- ", .close = " -->" };
    if (std.ascii.eqlIgnoreCase(ext, ".css")) return .{ .open = "/* ", .close = " */" };
    return null; // json, lockfiles, unknown: a header would break it
}

/// Tally marks in fives: 7 -> "||||/ ||". Hard to misread, hard to forget.
fn tally(a: std.mem.Allocator, n: usize) ![]u8 {
    var out: std.ArrayList(u8) = .empty;
    const shown = @min(n, 40);
    var i: usize = 0;
    while (i < shown) : (i += 1) {
        if (i > 0 and i % 5 == 0) try out.append(a, ' ');
        try out.append(a, if (i % 5 == 4) '/' else '|');
    }
    if (n > shown) try out.appendSlice(a, " +");
    return out.toOwnedSlice(a);
}

/// Header goes first, except after a shebang or a doctype, which must stay line one.
fn withHeader(a: std.mem.Allocator, name: []const u8, content: []const u8, ts: []const u8, edits: usize) ![]const u8 {
    const c = commentFor(name) orelse return content;
    const marks = try tally(a, edits);
    const line = try std.fmt.allocPrint(a, "{s}fzdow · created {s} · edits {d}  {s}{s}\n", .{ c.open, ts, edits, marks, c.close });
    var split: usize = 0;
    const lower_head = try std.ascii.allocLowerString(a, content[0..@min(content.len, 16)]);
    if (std.mem.startsWith(u8, content, "#!") or std.mem.startsWith(u8, lower_head, "<!doctype")) {
        split = if (std.mem.indexOfScalar(u8, content, '\n')) |nl| nl + 1 else content.len;
    }
    return std.mem.concat(a, u8, &.{ content[0..split], line, content[split..] });
}

// ---- index ------------------------------------------------------------------------

fn parseIndex(a: std.mem.Allocator, body: []const u8) ![]Row {
    var rows: std.ArrayList(Row) = .empty;
    var it = std.mem.splitScalar(u8, body, '\n');
    while (it.next()) |line| {
        if (line.len == 0) continue;
        var f: [8][]const u8 = undefined;
        var cols = std.mem.splitScalar(u8, line, '\t');
        var n: usize = 0;
        while (cols.next()) |col| : (n += 1) {
            if (n == 8) break;
            f[n] = col;
        }
        if (n != 8) continue;
        try rows.append(a, .{ .id = f[0], .state = f[1], .session = f[2], .mode = f[3], .ts = f[4], .edits = f[5], .src = f[6], .buf = f[7] });
    }
    return rows.toOwnedSlice(a);
}

fn clean(a: std.mem.Allocator, s: []const u8) ![]u8 {
    const out = try a.dupe(u8, s);
    for (out) |*ch| if (ch.* == '\t' or ch.* == '\n' or ch.* == '\r') {
        ch.* = ' ';
    };
    return out;
}

fn rowLine(a: std.mem.Allocator, r: Row) ![]u8 {
    return std.fmt.allocPrint(a, "{s}\t{s}\t{s}\t{s}\t{s}\t{s}\t{s}\t{s}\n", .{
        r.id, r.state, r.session, r.mode, r.ts, r.edits, try clean(a, r.src), try clean(a, r.buf),
    });
}

fn writeIndex(a: std.mem.Allocator, io: std.Io, path: []const u8, rows: []const Row) !void {
    var lines: std.ArrayList([]const u8) = .empty;
    for (rows) |r| try lines.append(a, try rowLine(a, r));
    try writeAtomic(a, io, path, lines.items);
}

// ---- commands ------------------------------------------------------------------------

fn ingest(a: std.mem.Allocator, io: std.Io, root: []const u8, mode: []const u8, transcript: []const u8) !void {
    const versioned = std.mem.eql(u8, mode, "versioned");
    if (!versioned and !std.mem.eql(u8, mode, "last")) return error.BadMode;

    const body = try readAll(a, io, transcript);
    const base = std.fs.path.basename(transcript);
    const session = if (std.mem.endsWith(u8, base, ".jsonl")) base[0 .. base.len - 6] else base;
    const sess8 = session[0..@min(session.len, 8)];

    var events: std.ArrayList(Event) = .empty;
    var lines = std.mem.splitScalar(u8, body, '\n');
    while (lines.next()) |line| {
        if (eventFromLine(a, line)) |e| try events.append(a, e);
    }

    // edits per path, in turn order
    var total: std.StringHashMapUnmanaged(usize) = .empty;
    for (events.items) |e| {
        const g = try total.getOrPut(a, e.path);
        g.value_ptr.* = if (g.found_existing) g.value_ptr.* + 1 else 1;
    }

    const index_path = try std.fs.path.join(a, &.{ root, "index.tsv" });
    const dir = try std.fs.path.join(a, &.{ root, sess8 });
    try std.Io.Dir.cwd().createDirPath(io, dir);

    var rows: std.ArrayList(Row) = .empty;
    try rows.appendSlice(a, try parseIndex(a, readOrEmpty(a, io, index_path)));
    var known: std.StringHashMapUnmanaged(void) = .empty;
    for (rows.items) |r| try known.put(a, r.id, {});

    var seen: std.StringHashMapUnmanaged(usize) = .empty;
    var added: usize = 0;
    for (events.items) |e| {
        const g = try seen.getOrPut(a, e.path);
        g.value_ptr.* = if (g.found_existing) g.value_ptr.* + 1 else 1;
        const rev = g.value_ptr.*;
        const all = total.get(e.path).?;
        if (!versioned and rev != all) continue; // authoritative: only the last one in

        const h: u32 = @truncate(std.hash.Wyhash.hash(0, e.path));
        const rev_s = if (versioned) try std.fmt.allocPrint(a, "{d}", .{rev}) else "last";
        const id = try std.fmt.allocPrint(a, "{s}:{s}:{s}:{x:0>8}", .{ sess8, mode, rev_s, h });
        if (known.contains(id)) continue;

        const name = std.fs.path.basename(e.path);
        const fname = try std.fmt.allocPrint(a, "{x:0>8}-{s}-{s}", .{ h, rev_s, name });
        const out = try std.fs.path.join(a, &.{ dir, fname });
        const edits = if (versioned) rev else all;
        try writeAtomic(a, io, out, &.{try withHeader(a, name, e.content, e.ts, edits)});

        try rows.append(a, .{
            .id = id, .state = "buffered", .session = session, .mode = mode, .ts = e.ts,
            .edits = try std.fmt.allocPrint(a, "{d}", .{edits}), .src = e.path, .buf = out,
        });
        try known.put(a, id, {});
        added += 1;
    }
    try writeIndex(a, io, index_path, rows.items);
    std.debug.print("{d} buffered · {d} edits in session\n", .{ added, events.items.len });
}

fn fiveWords(name: []const u8) bool {
    var n: usize = 0;
    var it = std.mem.splitScalar(u8, name, '-');
    while (it.next()) |w| {
        if (w.len == 0) return false;
        for (w) |ch| if (!std.ascii.isLower(ch) and !std.ascii.isDigit(ch)) return false;
        n += 1;
    }
    return n == 5;
}

fn keep(a: std.mem.Allocator, io: std.Io, root: []const u8, id: []const u8, name: []const u8) !void {
    if (!fiveWords(name)) return error.NotFiveWords;
    const index_path = try std.fs.path.join(a, &.{ root, "index.tsv" });
    const rows = try parseIndex(a, readOrEmpty(a, io, index_path));
    for (rows) |*r| {
        if (!std.mem.eql(u8, r.id, id)) continue;
        if (!std.mem.eql(u8, r.state, "buffered")) return error.AlreadyKept;
        const kept_dir = try std.fs.path.join(a, &.{ root, "kept" });
        try std.Io.Dir.cwd().createDirPath(io, kept_dir);
        const ext = std.fs.path.extension(std.fs.path.basename(r.src));
        const dest = try std.fmt.allocPrint(a, "{s}/{s}{s}", .{ kept_dir, name, ext });
        if (exists(io, dest)) return error.NameTaken;
        try std.Io.Dir.renameAbsolute(r.buf, dest, io);
        r.state = "kept";
        r.buf = dest;
        try writeIndex(a, io, index_path, rows);
        std.debug.print("kept {s}\n", .{dest});
        return;
    }
    return error.NoSuchId;
}

fn list(a: std.mem.Allocator, io: std.Io, root: []const u8) !void {
    const index_path = try std.fs.path.join(a, &.{ root, "index.tsv" });
    const body = readOrEmpty(a, io, index_path);
    var wbuf: [64 * 1024]u8 = undefined;
    var w = std.Io.File.stdout().writer(io, &wbuf);
    try w.interface.writeAll(body);
    try w.flush();
}

pub fn main(init: std.process.Init) !void {
    var arena_state = std.heap.ArenaAllocator.init(init.gpa);
    defer arena_state.deinit();
    const a = arena_state.allocator();
    const io = init.io;
    const env = init.environ_map;
    const args = try init.minimal.args.toSlice(a);

    const root = if (env.get("FZBUF_ROOT")) |r| r else blk: {
        const home = env.get("HOME") orelse return error.NoHome;
        break :blk try std.fs.path.join(a, &.{ home, "test-buffer" });
    };
    try std.Io.Dir.cwd().createDirPath(io, root);

    if (args.len < 2) return usage();
    const cmd = args[1];
    const run: anyerror!void = if (std.mem.eql(u8, cmd, "ingest") and args.len == 4)
        ingest(a, io, root, args[2], args[3])
    else if (std.mem.eql(u8, cmd, "list") and args.len == 2)
        list(a, io, root)
    else if (std.mem.eql(u8, cmd, "keep") and args.len == 4)
        keep(a, io, root, args[2], args[3])
    else {
        usage();
        std.process.exit(2);
    };
    run catch |err| {
        std.debug.print("fzbuf: {s}\n", .{@errorName(err)});
        std.process.exit(1);
    };
}

// ---- tests -----------------------------------------------------------------------------

test "tally groups in fives" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    try std.testing.expectEqualStrings("||||/ ||", try tally(arena.allocator(), 7));
    try std.testing.expectEqualStrings("|", try tally(arena.allocator(), 1));
}

test "header respects shebang, doctype and json" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const a = arena.allocator();
    const sh = try withHeader(a, "x.sh", "#!/bin/sh\necho\n", "T", 2);
    try std.testing.expect(std.mem.startsWith(u8, sh, "#!/bin/sh\n# fzdow · created T · edits 2"));
    const html = try withHeader(a, "p.html", "<!DOCTYPE html>\n<p>\n", "T", 1);
    try std.testing.expect(std.mem.startsWith(u8, html, "<!DOCTYPE html>\n<!-- fzdow"));
    try std.testing.expectEqualStrings("{}", try withHeader(a, "a.json", "{}", "T", 1));
}

test "edit rebuilds the file from the original" {
    var arena = std.heap.ArenaAllocator.init(std.testing.allocator);
    defer arena.deinit();
    const line =
        \\{"timestamp":"T1","toolUseResult":{"filePath":"/x/a.py","oldString":"b","newString":"c","originalFile":"abab","replaceAll":false}}
    ;
    const e = eventFromLine(arena.allocator(), line).?;
    try std.testing.expectEqualStrings("acab", e.content);
}

test "five words" {
    try std.testing.expect(fiveWords("one-two-three-four-five"));
    try std.testing.expect(!fiveWords("one-two-three-four"));
    try std.testing.expect(!fiveWords("One-two-three-four-five"));
}

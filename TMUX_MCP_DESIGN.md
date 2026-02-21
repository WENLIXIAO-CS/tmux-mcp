# tmux-mcp Design Document

## Architecture Overview

**Stack**: Python 3.10+, FastMCP (`mcp[cli]`), async subprocess, stdio transport.

All tools live in a single `server.py` module. Each tool is an `async def` decorated with `@mcp.tool()` that shells out via `run_tmux()` — a thin wrapper around `asyncio.create_subprocess_exec("tmux", ...)`. The server runs over stdio transport, launched by the MCP host:

```
claude mcp add tmux-mcp -- uv run --directory /path/to/tmux_mcp tmux-mcp
```

### Core helper

```python
async def run_tmux(*args: str) -> tuple[str, str, int]:
    proc = await asyncio.create_subprocess_exec(
        "tmux", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return stdout.decode(), stderr.decode(), proc.returncode
```

All tools use this helper and follow the same error pattern: check `rc != 0`, return `f"Error: {err.strip()}"` on failure.

---

## tmux ID System

tmux uses three namespaces for unique IDs:

| Object  | ID format | Example | Assigned by |
|---------|-----------|---------|-------------|
| Session | `$N`      | `$0`    | tmux server |
| Window  | `@N`      | `@1`    | tmux server |
| Pane    | `%N`      | `%3`    | tmux server |

These IDs are **globally unique** and **stable** (never reused in a server lifetime). They are the preferred way to address targets programmatically, vs. names which can be ambiguous or change.

### Target syntax

tmux targets use colon-dot notation: `session:window.pane`

Each part can be a name, index, or ID:
- `mysession` — session by name
- `$0` — session by ID
- `mysession:0` — window 0 in mysession
- `mysession:@1` — window by ID
- `mysession:0.0` — pane 0 of window 0
- `%5` — pane by global ID (no session/window needed)

---

## Complete Tool Inventory

### Session tools
| Tool | Status | Description |
|------|--------|-------------|
| `tmux_list_sessions` | existing (keep) | List all sessions |
| `tmux_create_session` | existing (**improve**) | Create session, return IDs |
| `tmux_rename_session` | existing (keep) | Rename a session |
| `tmux_kill` | existing (keep) | Kill session/window/pane |

### Window tools
| Tool | Status | Description |
|------|--------|-------------|
| `tmux_list_windows` | existing (**improve**) | List windows, add pane count |
| `tmux_create_window` | existing (**improve**) | Create window, return IDs |
| `tmux_select_window` | existing (keep) | Switch to a window |
| `tmux_rename_window` | existing (keep) | Rename a window |

### Pane tools
| Tool | Status | Description |
|------|--------|-------------|
| `tmux_list_panes` | **new** | List panes with IDs, dimensions |
| `tmux_split_window` | **new** | Split to create a pane, return pane ID |
| `tmux_select_pane` | **new** | Focus a specific pane |
| `tmux_resize_pane` | **new** | Resize a pane |

### I/O tools
| Tool | Status | Description |
|------|--------|-------------|
| `tmux_send_keys` | existing (keep) | Send keys to a pane |
| `tmux_read_pane` | existing (keep) | Capture pane content |

**Total: 14 tools** (10 existing + 4 new)

---

## Detailed Tool Specs

### Existing tools to improve

#### `tmux_create_session` — return session ID

**Current**: returns `"Session 'name' created."` (no IDs).

**Improved**: use `-P -F` to print the created session/window/pane info.

```python
@mcp.tool()
async def tmux_create_session(name: str, command: str | None = None, window_name: str | None = None) -> str:
    """Create a new tmux session.

    Args:
        name: Name for the new session.
        command: Optional command to run in the initial window.
        window_name: Optional name for the first window.
    """
    fmt = "#{session_id}\t#{window_id}\t#{pane_id}"
    args = ["new-session", "-d", "-s", name, "-P", "-F", fmt]
    if window_name:
        args.extend(["-n", window_name])
    if command:
        args.append(command)
    out, err, rc = await run_tmux(*args)
    if rc != 0:
        return f"Error: {err.strip()}"
    parts = out.strip().split("\t")
    return f"Session '{name}' created. session_id={parts[0]} window_id={parts[1]} pane_id={parts[2]}"
```

**tmux command**: `tmux new-session -d -s <name> -P -F '#{session_id}\t#{window_id}\t#{pane_id}' [-n window_name] [command]`

**Return**: `Session 'work' created. session_id=$0 window_id=@0 pane_id=%0`

---

#### `tmux_create_window` — return window & pane ID

**Current**: returns `"Window created in session 'session'."` (no IDs).

**Improved**: use `-P -F` to print window/pane info.

```python
@mcp.tool()
async def tmux_create_window(session: str, name: str | None = None, command: str | None = None) -> str:
    """Create a new window in an existing tmux session.

    Args:
        session: Target session name or ID.
        name: Optional name for the new window.
        command: Optional command to run in the new window.
    """
    fmt = "#{session_id}\t#{window_id}\t#{window_index}\t#{pane_id}"
    args = ["new-window", "-t", session, "-P", "-F", fmt]
    if name:
        args.extend(["-n", name])
    if command:
        args.append(command)
    out, err, rc = await run_tmux(*args)
    if rc != 0:
        return f"Error: {err.strip()}"
    parts = out.strip().split("\t")
    return f"Window created in session '{session}'. window_id={parts[1]} window_index={parts[2]} pane_id={parts[3]}"
```

**tmux command**: `tmux new-window -t <session> -P -F '#{session_id}\t#{window_id}\t#{window_index}\t#{pane_id}' [-n name] [command]`

**Return**: `Window created in session 'work'. window_id=@2 window_index=1 pane_id=%3`

---

#### `tmux_list_windows` — add pane count

**Current format**: `session_name \t window_index \t window_id \t window_name \t window_active \t pane_id`

**Improved**: add `#{window_panes}` to show how many panes each window has.

```python
@mcp.tool()
async def tmux_list_windows(session: str | None = None) -> str:
    """List all tmux windows. Optionally filter by session name or ID.

    Args:
        session: Session name or ID to filter by. If omitted, lists windows from all sessions.
    """
    fmt = "#{session_name}\t#{window_index}\t#{window_id}\t#{window_name}\t#{window_active}\t#{window_panes} panes\t#{pane_id}"
    if session:
        out, err, rc = await run_tmux("list-windows", "-t", session, "-F", fmt)
    else:
        out, err, rc = await run_tmux("list-windows", "-a", "-F", fmt)
    if rc != 0:
        return f"Error: {err.strip()}"
    return out.strip() or "No windows found."
```

**tmux command**: `tmux list-windows [-t session | -a] -F '#{session_name}\t#{window_index}\t#{window_id}\t#{window_name}\t#{window_active}\t#{window_panes} panes\t#{pane_id}'`

**Return** (one line per window):
```
work	0	@0	bash	1	2 panes	%0
work	1	@1	vim	0	1 panes	%2
```

---

### New tools

#### `tmux_list_panes`

List panes in a target window/session with IDs, dimensions, active status, and current command.

```python
@mcp.tool()
async def tmux_list_panes(target: str | None = None) -> str:
    """List tmux panes with their IDs, dimensions, and status.

    Args:
        target: Session or window target (e.g. "mysession", "mysession:0"). If omitted, lists panes in the current session.
    """
    fmt = "#{session_name}\t#{window_index}\t#{pane_id}\t#{pane_index}\t#{pane_width}x#{pane_height}\t#{pane_active}\t#{pane_current_command}"
    if target:
        out, err, rc = await run_tmux("list-panes", "-t", target, "-F", fmt)
    else:
        out, err, rc = await run_tmux("list-panes", "-a", "-F", fmt)
    if rc != 0:
        return f"Error: {err.strip()}"
    return out.strip() or "No panes found."
```

**tmux command**: `tmux list-panes [-t target | -a] -F '#{session_name}\t#{window_index}\t#{pane_id}\t#{pane_index}\t#{pane_width}x#{pane_height}\t#{pane_active}\t#{pane_current_command}'`

**Return** (one line per pane):
```
work	0	%0	0	80x24	1	bash
work	0	%1	1	80x24	0	python
```

**Notes**:
- Without `-t`, use `-a` to list all panes across all sessions.
- With `-t session`, lists panes in all windows of that session. With `-t session:window`, lists panes in that specific window.

---

#### `tmux_split_window`

Split an existing pane to create a new pane. Returns the new pane's ID.

```python
@mcp.tool()
async def tmux_split_window(
    target: str,
    horizontal: bool = False,
    size: str | None = None,
    command: str | None = None,
) -> str:
    """Split a window/pane to create a new pane.

    Args:
        target: Target window or pane to split (e.g. "session:window", "session:window.pane", or "%3").
        horizontal: If true, split horizontally (top/bottom). Default is vertical (left/right).
        size: Size of new pane — percentage (e.g. "50%") or line/column count (e.g. "20").
        command: Optional command to run in the new pane.
    """
    fmt = "#{pane_id}"
    args = ["split-window", "-t", target, "-P", "-F", fmt]
    if horizontal:
        args.append("-v")  # -v = vertical split = horizontal layout (top/bottom)
    else:
        args.append("-h")  # -h = horizontal split = vertical layout (left/right)
    if size:
        args.extend(["-l", size])
    if command:
        args.append(command)
    out, err, rc = await run_tmux(*args)
    if rc != 0:
        return f"Error: {err.strip()}"
    pane_id = out.strip()
    return f"Pane created. pane_id={pane_id}"
```

**tmux command**: `tmux split-window -t <target> -P -F '#{pane_id}' [-h|-v] [-l size] [command]`

**Return**: `Pane created. pane_id=%4`

**Notes on tmux's -h/-v semantics** (counterintuitive):
- `-h` = "horizontal split" = the divider is vertical, panes are side-by-side (left/right)
- `-v` = "vertical split" = the divider is horizontal, panes are stacked (top/bottom)

The tool parameter `horizontal=True` means "I want a horizontal divider (top/bottom stacking)", which maps to `-v`. This matches the user's mental model, not tmux's internal naming.

---

#### `tmux_select_pane`

Focus a specific pane.

```python
@mcp.tool()
async def tmux_select_pane(target: str) -> str:
    """Select/focus a specific tmux pane.

    Args:
        target: Pane target (e.g. "session:window.pane", "%3").
    """
    out, err, rc = await run_tmux("select-pane", "-t", target)
    if rc != 0:
        return f"Error: {err.strip()}"
    return f"Selected pane '{target}'."
```

**tmux command**: `tmux select-pane -t <target>`

**Return**: `Selected pane '%3'.`

---

#### `tmux_resize_pane`

Resize a pane by direction+amount or by absolute size.

```python
@mcp.tool()
async def tmux_resize_pane(
    target: str,
    direction: str | None = None,
    amount: int = 5,
    width: int | None = None,
    height: int | None = None,
) -> str:
    """Resize a tmux pane.

    Use direction+amount for relative resize, or width/height for absolute resize.

    Args:
        target: Pane target (e.g. "%3", "session:window.pane").
        direction: Direction to grow: "up", "down", "left", or "right".
        amount: Number of cells to resize by (default 5). Used with direction.
        width: Absolute width in columns. Overrides direction/amount.
        height: Absolute height in rows. Overrides direction/amount.
    """
    args = ["resize-pane", "-t", target]
    if width is not None:
        args.extend(["-x", str(width)])
    if height is not None:
        args.extend(["-y", str(height)])
    if width is None and height is None:
        direction_flags = {"up": "-U", "down": "-D", "left": "-L", "right": "-R"}
        if direction not in direction_flags:
            return "Error: direction must be 'up', 'down', 'left', or 'right'."
        args.append(direction_flags[direction])
        args.append(str(amount))
    out, err, rc = await run_tmux(*args)
    if rc != 0:
        return f"Error: {err.strip()}"
    return f"Pane '{target}' resized."
```

**tmux command**:
- Relative: `tmux resize-pane -t <target> -U|-D|-L|-R <amount>`
- Absolute: `tmux resize-pane -t <target> [-x width] [-y height]`

**Return**: `Pane '%3' resized.`

---

### Existing tools (unchanged)

These tools require no changes:

| Tool | tmux command | Signature |
|------|-------------|-----------|
| `tmux_list_sessions` | `list-sessions -F <fmt>` | `() -> str` |
| `tmux_send_keys` | `send-keys -t <target> [-l] <keys>` | `(target, keys, literal=False) -> str` |
| `tmux_read_pane` | `capture-pane -t <target> -p [-S start] [-E end]` | `(target, line_count=None, start_line=None) -> str` |
| `tmux_rename_session` | `rename-session -t <old> <new>` | `(old_name, new_name) -> str` |
| `tmux_rename_window` | `rename-window -t <target> <new>` | `(target, new_name) -> str` |
| `tmux_select_window` | `select-window -t <target>` | `(target) -> str` |
| `tmux_kill` | `kill-{type} -t <target>` | `(target, type="pane") -> str` |

---

## Key Design Decisions

### 1. Return IDs from creation operations

**Problem**: `tmux_create_session` and `tmux_create_window` returned only human-readable strings with no IDs. The caller had to immediately `list_sessions`/`list_windows` to find what was created.

**Solution**: Use tmux's `-P -F` flags on `new-session`, `new-window`, and `split-window`. These print the newly created object using a format string, giving us stable IDs in the same call.

### 2. Format strings over parsed JSON

tmux's `-F` flag with tab-separated fields is simpler and more reliable than trying to produce JSON. The LLM consumer can parse tab-separated lines trivially. No extra dependencies needed.

### 3. Error handling pattern

All tools follow the same pattern:
```python
out, err, rc = await run_tmux(...)
if rc != 0:
    return f"Error: {err.strip()}"
```
Errors are returned as strings (not exceptions) because MCP tool results are always strings. The `"Error: "` prefix makes failures easy to detect.

### 4. Target syntax as a string

Rather than having separate `session`, `window`, `pane` parameters, tools that operate on targets accept a single `target: str` using tmux's native colon-dot syntax (`session:window.pane`). This:
- Avoids parameter explosion
- Lets users pass IDs directly (`%3`, `@1`)
- Matches tmux documentation

### 5. split_window horizontal/vertical semantics

tmux's `-h` and `-v` flags are notoriously confusing. The tool exposes a `horizontal: bool` parameter where `True` = "horizontal divider, panes stacked top/bottom" (maps to tmux `-v`). This matches the user's spatial mental model.

### 6. Unified kill tool

A single `tmux_kill(target, type)` handles sessions, windows, and panes rather than three separate tools. The `type` parameter maps directly to `kill-session`, `kill-window`, or `kill-pane`.

### 7. list_panes defaults to all

When `target` is omitted, `tmux_list_panes` uses `-a` to list all panes across all sessions, consistent with how `tmux_list_windows` behaves.

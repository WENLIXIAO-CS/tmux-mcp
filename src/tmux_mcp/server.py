import argparse
import asyncio
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("tmux-mcp")


async def run_tmux(*args: str) -> tuple[str, str, int]:
    proc = await asyncio.create_subprocess_exec(
        "tmux", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return stdout.decode(), stderr.decode(), proc.returncode


@mcp.tool()
async def tmux_list_sessions() -> str:
    """List all tmux sessions with their names, IDs, window count, and status."""
    fmt = "#{session_id}\t#{session_name}\t#{session_windows} windows\t#{session_attached} attached\t#{session_created}"
    out, err, rc = await run_tmux("list-sessions", "-F", fmt)
    if rc != 0:
        return f"Error: {err.strip() or 'no tmux server running'}"
    return out.strip() or "No sessions found."


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


@mcp.tool()
async def tmux_send_keys(target: str, keys: str, literal: bool = False) -> str:
    """Send keys or commands to a tmux pane.

    Args:
        target: Tmux target (e.g. "session:window.pane", "session:window", "session").
        keys: Keys to send. Use special key names like "Enter", "C-c", "Escape", "Tab", "Space", etc.
        literal: If true, send keys literally (the -l flag) without special key lookup.
    """
    args = ["send-keys", "-t", target]
    if literal:
        args.append("-l")
    args.append(keys)
    out, err, rc = await run_tmux(*args)
    if rc != 0:
        return f"Error: {err.strip()}"
    return "Keys sent."


@mcp.tool()
async def tmux_read_pane(target: str, line_count: int | None = None, start_line: int | None = None) -> str:
    """Read/capture content from a tmux pane.

    Args:
        target: Tmux target (e.g. "session:window.pane").
        line_count: Number of lines to capture. If omitted, captures entire visible pane.
        start_line: Start line for history capture (negative = lines before visible area, e.g. -100).
    """
    args = ["capture-pane", "-t", target, "-p"]
    if start_line is not None:
        args.extend(["-S", str(start_line)])
    if line_count is not None:
        end_line = (start_line or 0) + line_count
        args.extend(["-E", str(end_line)])
    out, err, rc = await run_tmux(*args)
    if rc != 0:
        return f"Error: {err.strip()}"
    return out if out else "(empty pane)"


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


@mcp.tool()
async def tmux_rename_session(old_name: str, new_name: str) -> str:
    """Rename a tmux session.

    Args:
        old_name: Current session name or ID.
        new_name: New name for the session.
    """
    out, err, rc = await run_tmux("rename-session", "-t", old_name, new_name)
    if rc != 0:
        return f"Error: {err.strip()}"
    return f"Session renamed to '{new_name}'."


@mcp.tool()
async def tmux_rename_window(target: str, new_name: str) -> str:
    """Rename a tmux window.

    Args:
        target: Tmux target for the window (e.g. "session:window").
        new_name: New name for the window.
    """
    out, err, rc = await run_tmux("rename-window", "-t", target, new_name)
    if rc != 0:
        return f"Error: {err.strip()}"
    return f"Window renamed to '{new_name}'."


@mcp.tool()
async def tmux_select_window(target: str) -> str:
    """Navigate/switch to a specific tmux window.

    Args:
        target: Tmux target (e.g. "session:window").
    """
    out, err, rc = await run_tmux("select-window", "-t", target)
    if rc != 0:
        return f"Error: {err.strip()}"
    return f"Switched to '{target}'."


@mcp.tool()
async def tmux_list_panes(target: str | None = None) -> str:
    """List tmux panes with their IDs, dimensions, and status.

    Args:
        target: Session or window target (e.g. "mysession", "mysession:0"). If omitted, lists panes from all sessions.
    """
    fmt = "#{session_name}\t#{window_index}\t#{pane_id}\t#{pane_index}\t#{pane_width}x#{pane_height}\t#{pane_active}\t#{pane_current_command}"
    if target:
        out, err, rc = await run_tmux("list-panes", "-t", target, "-F", fmt)
    else:
        out, err, rc = await run_tmux("list-panes", "-a", "-F", fmt)
    if rc != 0:
        return f"Error: {err.strip()}"
    return out.strip() or "No panes found."


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
        args.append("-v")
    else:
        args.append("-h")
    if size:
        args.extend(["-l", size])
    if command:
        args.append(command)
    out, err, rc = await run_tmux(*args)
    if rc != 0:
        return f"Error: {err.strip()}"
    pane_id = out.strip()
    return f"Pane created. pane_id={pane_id}"


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


@mcp.tool()
async def tmux_kill(target: str, type: str = "pane") -> str:
    """Kill a tmux session, window, or pane.

    Args:
        target: Tmux target to kill.
        type: What to kill - "session", "window", or "pane".
    """
    if type not in ("session", "window", "pane"):
        return "Error: type must be 'session', 'window', or 'pane'."
    out, err, rc = await run_tmux(f"kill-{type}", "-t", target)
    if rc != 0:
        return f"Error: {err.strip()}"
    return f"{type.capitalize()} '{target}' killed."


def main():
    parser = argparse.ArgumentParser(description="MCP server for controlling tmux sessions")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8888, help="Port to listen on (default: 8888)")
    args = parser.parse_args()

    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()

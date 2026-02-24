import argparse
import asyncio
import logging
import re
import sys
import time

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("tmux-mcp")
logger = logging.getLogger("tmux-mcp")

_ANSI_RE = re.compile(r"\x1b(?:\[[0-9;]*[a-zA-Z]|\].*?\x07|\(B)")


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


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return _ANSI_RE.sub("", text)


def _get_bottom_lines(pane_text: str, n: int = 20) -> list[str]:
    """Return the last *n* non-empty lines from captured pane text."""
    return [l for l in pane_text.split("\n") if l.strip()][-n:]


def _detect_cc_state(lines: list[str]) -> tuple[str, str]:
    """Detect the current state of a Claude Code session.

    Examines the bottom portion of a captured tmux pane and returns
    ``(state, detail)`` where *state* is one of:

    * ``"permission"`` – CC is showing a numbered-option approval prompt
    * ``"processing"`` – CC is actively working (spinner / status line)
    * ``"idle"``       – CC is waiting for the next user prompt
    """
    if not lines:
        return "unknown", "empty pane"

    bottom_text = "\n".join(lines)

    # --- 1. Permission prompt ---
    # Claude Code shows numbered options like "1. Yes  2. Yes, don't ask again  3. No"
    numbered = [l.strip() for l in lines if re.match(r"\s*\d+[\.\)]\s+\S", l)]
    if len(numbered) >= 2:
        return "permission", " | ".join(numbered)

    for line in lines:
        if re.search(r"Do you want to|Allow |approve|\(y/n\)|\(Y/n\)", line, re.IGNORECASE):
            return "permission", line.strip()

    # --- 2. Processing indicators ---
    # Token counter in status line: "· ↓ 3.1k tokens"
    m = re.search(r"·\s*↓\s*[\d.,]+k?\s*tokens", bottom_text)
    if m:
        return "processing", m.group(0).strip()

    # Tool running status
    if re.search(r"Running…|Running\.\.\.", bottom_text):
        return "processing", "Running…"

    # Time counter: "(3m 45s ·" or "(45s ·"
    m = re.search(r"\(\d+[ms]?\s+\d+s\s*·", bottom_text)
    if m:
        return "processing", m.group(0).strip()

    # Braille spinner characters (Claude Code progress spinners)
    if re.search(r"[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏⠐✽]", bottom_text):
        return "processing", "spinner detected"

    # Activity word with ellipsis
    for line in lines[-10:]:
        m = re.search(r"\b\w+ing[…\.]{1,3}", line)
        if m:
            return "processing", m.group(0)

    # Bare "ing…" or "ing..." anywhere in bottom text
    if re.search(r"ing…|ing\.\.\.", bottom_text):
        return "processing", "ing… detected"

    # --- 3. Default: idle ---
    return "idle", "no activity indicators"


@mcp.tool()
async def tmux_read_cc_pane(
    target: str,
    timeout: float = 300.0,
    poll_interval: float = 0.5,
    last_n_lines: int = 20,
) -> str:
    """Monitor a tmux pane running Claude Code, auto-waiting and auto-approving.

    Polls the pane in a loop:
    - While Claude Code is processing (spinners, "Running…", activity text):
      logs the status and sleeps.
    - When Claude Code asks for permission (numbered options):
      sends "1" to approve and continues monitoring.
    - When Claude Code is idle (waiting for next prompt):
      returns the captured pane content.

    Args:
        target: Tmux target pane (e.g. "session:window.pane", "%3").
        timeout: Max seconds to wait before returning (default 300).
        poll_interval: Seconds between polls (default 0.5).
        last_n_lines: Number of trailing non-empty lines to analyze (default 20).
    """
    log_entries: list[str] = []
    t0 = time.monotonic()

    def _log(msg: str):
        elapsed = time.monotonic() - t0
        entry = f"[{elapsed:6.1f}s] {msg}"
        log_entries.append(entry)
        logger.info(msg)

    _log(f"Monitoring Claude Code pane '{target}'")

    while True:
        elapsed = time.monotonic() - t0
        if elapsed > timeout:
            _log(f"Timeout after {timeout:.0f}s")
            break

        # Capture the visible pane
        out, err, rc = await run_tmux("capture-pane", "-t", target, "-p")
        if rc != 0:
            _log(f"Error reading pane: {err.strip()}")
            return f"Error: {err.strip()}\n\n--- Log ---\n" + "\n".join(log_entries)

        clean = _strip_ansi(out)
        bottom = _get_bottom_lines(clean, last_n_lines)

        if not bottom:
            _log("Empty pane, waiting…")
            await asyncio.sleep(poll_interval)
            continue

        state, detail = _detect_cc_state(bottom)

        if state == "processing":
            _log(f"Processing: {detail}")
            await asyncio.sleep(poll_interval)
        elif state == "permission":
            _log(f"Permission requested: {detail} → sending '1'")
            await run_tmux("send-keys", "-t", target, "1")
            await asyncio.sleep(poll_interval)
        elif state == "idle":
            _log(f"Idle: {detail}")
            break
        else:
            _log(f"Unknown state ({detail}), waiting…")
            await asyncio.sleep(poll_interval)

    # Final capture with scrollback for context
    out, err, rc = await run_tmux(
        "capture-pane", "-t", target, "-p", "-S", "-200"
    )
    if rc != 0:
        content = "(error capturing final pane content)"
    else:
        content = _strip_ansi(out).rstrip()

    log_block = "\n".join(log_entries)
    return f"{content}\n\n--- Monitor Log ---\n{log_block}"


def main():
    parser = argparse.ArgumentParser(description="MCP server for controlling tmux sessions")
    sub = parser.add_subparsers(dest="command")

    # --- serve (default) ---
    serve_p = sub.add_parser("serve", help="Start the MCP server (default)")
    serve_p.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    serve_p.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    serve_p.add_argument("--port", type=int, default=8888, help="Port to listen on (default: 8888)")

    # --- read-cc-pane ---
    cc_p = sub.add_parser(
        "read-cc-pane",
        help="Monitor a Claude Code tmux pane (standalone, no MCP server)",
    )
    cc_p.add_argument("target", help="Tmux target pane (e.g. 'session', '%%3')")
    cc_p.add_argument("--timeout", type=float, default=300.0, help="Max seconds to wait (default: 300)")
    cc_p.add_argument("--poll-interval", type=float, default=0.5, help="Seconds between polls (default: 0.5)")
    cc_p.add_argument("--lines", type=int, default=20, help="Trailing lines to analyze (default: 20)")

    args = parser.parse_args()

    # Default to serve when no subcommand given
    if args.command is None or args.command == "serve":
        serve_args = args if args.command == "serve" else parser.parse_args(["serve"])
        mcp.settings.host = serve_args.host
        mcp.settings.port = serve_args.port
        mcp.run(transport=serve_args.transport)
    elif args.command == "read-cc-pane":
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)s] %(message)s",
            stream=sys.stderr,
        )
        result = asyncio.run(
            tmux_read_cc_pane(
                target=args.target,
                timeout=args.timeout,
                poll_interval=args.poll_interval,
                last_n_lines=args.lines,
            )
        )
        print(result)


if __name__ == "__main__":
    main()

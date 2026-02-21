# tmux-mcp

An [MCP](https://modelcontextprotocol.io/) server for controlling tmux sessions. Allows AI assistants to create, manage, and interact with tmux sessions, windows, and panes programmatically.

## Prerequisites

- Python 3.10+
- [tmux](https://github.com/tmux/tmux) installed and available on `PATH`

## Installation

### With Claude Code (stdio)

```bash
# From PyPI
claude mcp add tmux-mcp -- uvx tmux-mcp

# From GitHub (no PyPI needed)
claude mcp add tmux-mcp -- uvx --from git+https://github.com/WENLIXIAO-CS/tmux-mcp tmux-mcp
```

### With Claude Code (HTTP)

Start the server:

```bash
tmux-mcp --transport streamable-http --port 8888
```

Then add it as an HTTP MCP server:

```bash
claude mcp add --transport http tmux-mcp http://localhost:8888/mcp
```

### With pip

```bash
pip install tmux-mcp
```

Then run the server:

```bash
# stdio (default)
tmux-mcp

# HTTP
tmux-mcp --transport streamable-http --port 8888
```

## Available Tools

### Sessions
| Tool | Description |
|------|-------------|
| `tmux_list_sessions` | List all tmux sessions with names, IDs, window count, and attached status |
| `tmux_create_session` | Create a new detached session (returns session/window/pane IDs) |
| `tmux_rename_session` | Rename an existing session |

### Windows
| Tool | Description |
|------|-------------|
| `tmux_list_windows` | List windows, optionally filtered by session (includes pane count) |
| `tmux_create_window` | Create a new window in a session (returns window/pane IDs) |
| `tmux_select_window` | Switch to a specific window |
| `tmux_rename_window` | Rename a window |

### Panes
| Tool | Description |
|------|-------------|
| `tmux_list_panes` | List panes with IDs, dimensions, active status, and running command |
| `tmux_split_window` | Split a window/pane horizontally or vertically (returns new pane ID) |
| `tmux_select_pane` | Focus a specific pane |
| `tmux_resize_pane` | Resize a pane by direction+amount or absolute width/height |

### I/O
| Tool | Description |
|------|-------------|
| `tmux_send_keys` | Send keys or commands to a pane (supports special keys like Enter, C-c, Tab) |
| `tmux_read_pane` | Capture visible content from a pane (supports scrollback history) |

### Lifecycle
| Tool | Description |
|------|-------------|
| `tmux_kill` | Kill a session, window, or pane by target |

## Usage Examples

Create a session and run a command:

```
> Create a tmux session called "dev" and run "python server.py" in it

Tool call: tmux_create_session(name="dev")
-> Session 'dev' created. session_id=$1 window_id=@1 pane_id=%1

Tool call: tmux_send_keys(target="dev", keys="python server.py Enter")
-> Keys sent.
```

Read output from a pane:

```
> What's the output in the dev session?

Tool call: tmux_read_pane(target="dev")
-> $ python server.py
   Server running on port 8080
```

Split a window and run a second process:

```
> Split the dev window and start a log tail

Tool call: tmux_split_window(target="dev:0")
-> Pane created. pane_id=%2

Tool call: tmux_send_keys(target="%2", keys="tail -f app.log Enter")
-> Keys sent.
```

## Usage with Claude Code

Add the tmux-mcp server to Claude Code:

```bash
# stdio (managed by Claude Code)
claude mcp add tmux-mcp -- uvx tmux-mcp

# HTTP (run server separately, then add)
claude mcp add --transport http tmux-mcp http://localhost:8888/mcp

# Local development
claude mcp add tmux-mcp -- uv run --directory /path/to/tmux-mcp tmux-mcp
```

Once added, Claude Code can use all tmux tools directly in conversation.

## Development

Clone the repository and set up a development environment:

```bash
git clone https://github.com/WENLIXIAO-CS/tmux-mcp.git
cd tmux-mcp
uv sync
```

Run the server locally:

```bash
uv run tmux-mcp
```

## License

MIT

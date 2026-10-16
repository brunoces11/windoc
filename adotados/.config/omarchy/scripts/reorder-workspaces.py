#!/usr/bin/env python3
import json
import subprocess
import sys

def main():
    if len(sys.argv) < 3:
        print("Usage: reorder-workspaces.py <from_workspace_id> <to_workspace_id>", file=sys.stderr)
        sys.exit(1)

    try:
        from_ws = int(sys.argv[1])
        to_ws = int(sys.argv[2])
    except ValueError:
        print("Error: workspace IDs must be integers", file=sys.stderr)
        sys.exit(1)

    if from_ws == to_ws:
        return

    mapping = {}
    if from_ws > to_ws:
        # Dragged right-to-left: from_ws becomes to_ws; intermediate shift right (+1)
        mapping[from_ws] = to_ws
        for i in range(to_ws, from_ws):
            mapping[i] = i + 1
    else:
        # Dragged left-to-right: from_ws becomes to_ws; intermediate shift left (-1)
        mapping[from_ws] = to_ws
        for i in range(from_ws + 1, to_ws + 1):
            mapping[i] = i - 1

    try:
        clients_raw = subprocess.check_output(["hyprctl", "clients", "-j"], timeout=3)
        clients = json.loads(clients_raw)
    except Exception as e:
        print(f"Error querying clients: {e}", file=sys.stderr)
        sys.exit(1)

    affected = []
    for c in clients:
        if c.get("pinned", False):
            continue
        ws_id = c.get("workspace", {}).get("id")
        if ws_id in mapping:
            affected.append({
                "address": c["address"],
                "from_ws": ws_id,
                "temp_ws": 9000 + ws_id,
                "to_ws": mapping[ws_id]
            })

    # The user just dropped the workspace at to_ws, so make to_ws the focused workspace
    target_active = to_ws

    lua_lines = []
    # Phase 1: move affected windows to collision-free temporary workspaces
    for item in affected:
        lua_lines.append(
            f'hl.dispatch(hl.dsp.window.move({{ window = "{item["address"]}", workspace = "{item["temp_ws"]}", follow = false }}))'
        )

    # Phase 2: move from temporary workspaces to their final target workspaces
    for item in affected:
        lua_lines.append(
            f'hl.dispatch(hl.dsp.window.move({{ window = "{item["address"]}", workspace = "{item["to_ws"]}", follow = false }}))'
        )

    # Phase 3: focus the newly placed target workspace
    if target_active is not None:
        lua_lines.append(f'hl.dispatch(hl.dsp.focus({{ workspace = "{target_active}" }}))')

    if lua_lines:
        lua_script = "\n".join(lua_lines) + "\n"
        subprocess.run(["hyprctl", "repl"], input=lua_script, text=True, capture_output=True, timeout=5)

if __name__ == "__main__":
    main()

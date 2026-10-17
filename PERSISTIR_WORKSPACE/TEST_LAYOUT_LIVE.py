"""Isolated real Hyprland/Kitty round trip; never closes pre-existing windows."""
import json
import shlex
import tempfile
import time
from pathlib import Path

import WORKSPACE1 as api


def main():
    workspace = 85
    identities = ["c741187f0b294c769e5c000" + str(i) for i in range(1, 5)]
    assert not any(c["workspace"]["id"] == workspace for c in api.clients()), "Workspace de teste ocupado"
    before = {c["address"] for c in api.workspace_clients()}
    original_focus = next((c["address"] for c in api.clients() if c.get("focusHistoryID") == 0), None)
    with tempfile.TemporaryDirectory(prefix="test-bsp-", dir=api.STATE_DIR) as tmp:
        api.STATE_DIR = Path(tmp)
        for key, name in [("STATE_FILE", "WORKSPACE1.json"), ("CAPTURE_FILE", "LATEST_CAPTURE.json"),
                          ("RESTORE_STATUS_FILE", "RESTORE_STATUS.json"), ("AGENT_IDS_FILE", "AGENT_IDS.json")]:
            setattr(api, key, Path(tmp) / name)
        api.WORKSPACE_ID = workspace
        def wait_empty():
            deadline = time.monotonic() + 8
            while api.workspace_clients() and time.monotonic() < deadline:
                time.sleep(.2)
            assert not api.workspace_clients()
        def close_test():
            for c in api.clients():
                if api.window_identity(c) in identities:
                    api.dispatch('hl.dsp.window.close({window=' + api.layout.selector(c["address"]) + '})')
            wait_empty()
        try:
            one = api.stored_session("new_tab\nlayout tall\nlaunch --cwd=/tmp\n")
            two = api.stored_session("new_tab\nlayout tall\nlaunch --cwd=/tmp\nnew_tab\nlayout tall\nlaunch --cwd=/tmp\nfocus_tab 1\n")
            for index, identity in enumerate(identities):
                command = shlex.join(["env", "WINDOC_WORKSPACE_WINDOW_ID=" + identity, "kitty", "--session", str(api.STATE_DIR / (two if index == 0 else one))])
                api.dispatch('hl.dsp.exec_cmd(' + json.dumps(command) + ',{workspace="85 silent",float=true,group="barred"})')
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                clients = {api.window_identity(c): c for c in api.workspace_clients()}
                if len(clients) == 4:
                    break
                time.sleep(.2)
            assert set(clients) == set(identities)
            a, extra, b, c = [api.layout.selector(clients[i]["address"]) for i in identities]
            api.layout.lua(api, f'local a=hl.get_window({a});hl.dispatch(hl.dsp.group.toggle({{window=a}}));a.group:add(hl.get_window({extra}));')
            for window in (b, c):
                api.dispatch(f'hl.dsp.group.toggle({{window={window}}})')
            api.dispatch(f'hl.dsp.window.float({{window={a},action="disable"}})')
            api.dispatch(f'hl.dsp.focus({{window={a}}})')
            api.dispatch('hl.dsp.layout("preselect r")')
            api.dispatch(f'hl.dsp.window.float({{window={b},action="disable"}})')
            api.dispatch(f'hl.dsp.focus({{window={b}}})')
            api.dispatch('hl.dsp.layout("preselect d")')
            api.dispatch(f'hl.dsp.window.float({{window={c},action="disable"}})')
            api.dispatch(f'hl.dsp.focus({{window={a}}})')
            api.dispatch('hl.dsp.layout("splitratio 1.2 exact")')
            api.dispatch(f'hl.dsp.focus({{window={b}}})')
            api.dispatch('hl.dsp.layout("splitratio 1.1 exact")')
            api.dispatch(f'hl.dsp.group.active({{window={a},index=2}})')
            captured = api.snapshot()
            assert api.scene_counts(captured) == (4, 5, 5)
            assert len(captured["groups"]) == 3
            close_test()
            results = api.restore(captured, verify_seconds=8)
            if not all(r["status"] == "verificado" for r in results):
                print(api.RESTORE_STATUS_FILE.read_text())
                print("grid salvo:", json.dumps({"grid": captured.get("grid"), "tree": captured.get("tile_tree"),
                                                   "groups": captured.get("groups")}, indent=2))
                print([(api.window_identity(w), w["at"], w["size"]) for w in api.workspace_clients()])
            assert all(r["status"] == "verificado" for r in results), results
            print("OK: 4 janelas, 3 grupos, 5 abas e divisões horizontal/vertical restaurados com geometria e foco conferidos")
        finally:
            close_test()
            if original_focus and any(c["address"] == original_focus for c in api.clients()):
                api.dispatch('hl.dsp.focus({window=' + api.layout.selector(original_focus) + '})')
            assert {c["address"] for c in api.clients() if c["workspace"]["id"] == 1} == before
            print("OK: janelas originais preservadas e teste isolado encerrado")


if __name__ == "__main__":
    main()

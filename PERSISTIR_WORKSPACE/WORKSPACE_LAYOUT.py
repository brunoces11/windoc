"""Native Hyprland groups and Dwindle geometry. No persistent compositor overrides."""
from __future__ import annotations

import hashlib
import json
import subprocess


def lua(api, code, *, query=False):
    result = api.run(["hyprctl", "repl" if query else "eval", code])
    if result.stdout.lstrip().startswith("error:"):
        raise RuntimeError(result.stdout.strip())
    return result.stdout.strip()


def selector(address):
    return json.dumps("address:" + address)


def metadata(api, clients):
    """One small Lua query for native group current/lock and workspace algorithm."""
    addresses = ",".join(json.dumps(c["address"]) for c in clients)
    code = ('local r={};for _,a in ipairs({' + addresses + '}) do '
            'local w=hl.get_window("address:"..a);if w then '
            'local g=w.group;r[#r+1]=table.concat({a,g and g.current.address or "",'
            'tostring(g and g.locked or false),w.layout and w.layout.name or ""},"|") end end;'
            'return table.concat(r,"\\n")')
    result = {}
    for line in lua(api, code, query=True).splitlines():
        parts = line.split("|")
        if len(parts) == 4:
            result[parts[0]] = dict(active=parts[1], locked=parts[2] == "true", layout=parts[3])
    return result


def monitor_area(monitor):
    scale = monitor.get("scale") or 1
    width, height = monitor["width"], monitor["height"]
    if monitor.get("transform", 0) % 2:
        width, height = height, width
    left, top, right, bottom = monitor.get("reserved", [0, 0, 0, 0])
    return [monitor.get("x", 0) + left, monitor.get("y", 0) + top,
            width / scale - left - right, height / scale - top - bottom]


def monitor_records(monitors):
    keys = ("id", "name", "description", "width", "height", "scale", "transform", "x", "y", "reserved")
    return sorted([{k: m[k] for k in keys if k in m} for m in monitors], key=lambda m: m["name"])


def groups(windows, monitors=()):
    by_address = {w.get("address"): w["restore_id"] for w in windows}
    by_id = {w["restore_id"]: w for w in windows}
    result, seen = [], set()
    for window in windows:
        members = window.get("group_members")
        if members is None:
            members = [by_address[a] for a in window.get("grouped", []) if a in by_address]
        members = list(dict.fromkeys(members or [window["restore_id"]]))
        members = [m for m in members if m in by_id]
        key = tuple(members)
        if key in seen:
            continue
        seen.add(key)
        source = by_id[members[0]]
        monitor = next((m for m in monitors if m.get("id") == source.get("monitor")), None)
        result.append({"id": hashlib.sha256("|".join(members).encode()).hexdigest()[:24],
                       "members": members, "is_group": bool(window.get("grouped")),
                       "active": window.get("group_active") or members[0],
                       "locked": window.get("group_locked", False),
                       "at": source.get("at"), "size": source.get("size"),
                       "tile_at": source.get("normal_at") or source.get("at"),
                       "tile_size": source.get("normal_size") or source.get("size"),
                       "floating": source.get("floating", False), "fullscreen": source.get("fullscreen", 0),
                       "monitor_name": source.get("monitor_name") or (monitor or {}).get("name"),
                       "monitor_area": source.get("monitor_area") or (monitor_area(monitor) if monitor else None),
                       "layout": source.get("layout_name", "dwindle")})
    return result


def rect(group):
    return [*group["at"], *group["size"]]


def infer_tree(items):
    """Recover a slicing tree from non-overlapping logical rectangles, per tile/group."""
    if not items:
        return None
    if len(items) == 1:
        return {"group": items[0]["id"]}
    def tile_rect(group):
        return [*(group.get("tile_at") or group["at"]), *(group.get("tile_size") or group["size"])]
    for axis in (0, 1):
        ordered = sorted(items, key=lambda g: tile_rect(g)[axis])
        for i in range(1, len(ordered)):
            a, b = ordered[:i], ordered[i:]
            end = max(tile_rect(g)[axis] + tile_rect(g)[axis + 2] for g in a)
            start = min(tile_rect(g)[axis] for g in b)
            if end > start + 2:
                continue
            low = min(tile_rect(g)[axis] for g in ordered)
            high = max(tile_rect(g)[axis] + tile_rect(g)[axis + 2] for g in ordered)
            left, right = infer_tree(a), infer_tree(b)
            if left and right and high > low:
                return {"axis": axis, "ratio": ((end + start) / 2 - low) / (high - low),
                        "left": left, "right": right}
    raise ValueError("As divisões observadas não formam uma árvore Dwindle reconstruível")


def _native_tree(node, identities, groups_by_id):
    if not isinstance(node, dict):
        raise ValueError("A árvore nativa contém um nó inválido")
    if node.get("kind") == "split":
        first = _native_tree(node.get("first"), identities, groups_by_id)
        second = _native_tree(node.get("second"), identities, groups_by_id)
        ratio = float(node["split_ratio"])
        if node.get("axis") not in (0, 1) or not 0.1 <= ratio <= 1.9:
            raise ValueError("A árvore nativa contém um corte fora dos limites válidos")
        return {"axis": node["axis"], "ratio": ratio / 2,
                "native_split_ratio": ratio, "split_top": bool(node.get("split_top")),
                "box": node.get("box"), "left": first, "right": second}
    if node.get("kind") != "tile":
        raise ValueError("A árvore nativa contém um tipo de nó desconhecido")
    addresses = node.get("windows")
    members = [identities[address] for address in addresses if address in identities]
    if not members or len(members) != len(addresses) or len(set(members)) != len(members):
        raise ValueError("A folha nativa não corresponde a janelas únicas do workspace")
    group_id = hashlib.sha256("|".join(members).encode()).hexdigest()[:24]
    if group_id not in groups_by_id:
        raise ValueError("A folha nativa não possui grupo persistível")
    return {"group": group_id, "box": node.get("box")}


def apply_native_grid(state, grid):
    """Map the live Dwindle BSP tree and ordered groups to persistent window IDs."""
    if not isinstance(grid, dict) or grid.get("layout") != "dwindle":
        raise ValueError("O exportador não retornou uma árvore Dwindle válida")

    by_address = {w.get("address"): w for w in state["windows"] if w.get("address")}
    identities = {address: row["restore_id"] for address, row in by_address.items()}
    if grid.get("tree") is None:
        if any(not w.get("floating") for w in state["windows"]):
            raise ValueError("O exportador não encontrou a árvore que deveria conter janelas tiled")
        state["groups"] = groups(state["windows"], state.get("monitors", []))
        state["tile_tree"] = None
        state["grid"] = {"source": "hyprland-native", "layout": "dwindle",
                          "build_id": grid.get("build_id"), "work_area": grid.get("work_area"),
                          "tiled_leaves": 0, "split_nodes": 0}
        state["layout_snapshot"] = True
        return state
    if not isinstance(grid.get("tree"), dict):
        raise ValueError("O exportador retornou uma árvore Dwindle inválida")
    leaves = []
    leaf_addresses = []

    def collect(node):
        if node.get("kind") == "split":
            collect(node["first"])
            collect(node["second"])
            return
        if node.get("kind") != "tile":
            raise ValueError("A árvore nativa contém um nó desconhecido")
        addresses = node.get("windows")
        if not isinstance(addresses, list) or not addresses:
            raise ValueError("A árvore nativa contém uma folha sem janela")
        if any(address not in by_address or by_address[address].get("floating") for address in addresses):
            raise ValueError("A folha nativa contém uma janela ausente ou flutuante")
        if any(address in leaf_addresses for address in addresses):
            raise ValueError("Uma janela aparece em mais de uma folha Dwindle")
        leaf_addresses.extend(addresses)
        members = [identities[address] for address in addresses]
        group_id = hashlib.sha256("|".join(members).encode()).hexdigest()[:24]
        source = by_address[addresses[0]]
        active_address = node.get("active")
        group = {"id": group_id, "members": members, "is_group": bool(node.get("is_group", len(members) > 1)),
                 "active": identities.get(active_address, members[0]), "locked": bool(node.get("locked")),
                 "at": source.get("at"), "size": source.get("size"),
                 "tile_at": source.get("normal_at") or source.get("at"),
                 "tile_size": source.get("normal_size") or source.get("size"),
                 "floating": False, "fullscreen": source.get("fullscreen", 0),
                 "monitor_name": source.get("monitor_name"), "monitor_area": source.get("monitor_area"),
                 "layout": "dwindle", "native_box": node.get("box")}
        leaves.append((node, group))

    collect(grid["tree"])
    tiled_addresses = {w.get("address") for w in state["windows"] if w.get("address") and not w.get("floating")}
    if set(leaf_addresses) != tiled_addresses:
        raise ValueError("A árvore nativa não cobre exatamente todas as janelas tiled do workspace")

    for node, group in leaves:
        for address in node["windows"]:
            row = by_address[address]
            row["group_members"] = list(group["members"])
            row["group_active"] = group["active"]
            row["group_locked"] = group["locked"]
            row["layout_name"] = "dwindle"

    floating = [g for g in groups(state["windows"], state.get("monitors", [])) if g["floating"]]
    state["groups"] = [group for _, group in leaves] + floating
    groups_by_id = {group["id"]: group for group in state["groups"]}
    state["tile_tree"] = _native_tree(grid["tree"], identities, groups_by_id)
    state["grid"] = {"source": "hyprland-native", "layout": "dwindle",
                      "build_id": grid.get("build_id"), "work_area": grid.get("work_area"),
                      "tiled_leaves": len(leaves), "split_nodes": max(0, len(leaves) - 1)}
    state["layout_snapshot"] = True
    return state


def prune_tree(node, allowed_groups):
    """Remove unavailable leaves from a saved tree without changing surviving cuts."""
    if not isinstance(node, dict):
        return None
    if "group" in node:
        return dict(node) if node["group"] in allowed_groups else None
    left = prune_tree(node.get("left"), allowed_groups)
    right = prune_tree(node.get("right"), allowed_groups)
    if left and right:
        return {**node, "left": left, "right": right}
    return left or right


def enrich(state, native=None, grid=None):
    native = native or {}
    identities = {w.get("address"): w["restore_id"] for w in state["windows"]}
    for window in state["windows"]:
        m = native.get(window.get("address"), {})
        window["group_members"] = [identities[a] for a in window.get("grouped", []) if a in identities]
        window["group_active"] = identities.get(m.get("active"))
        window["group_locked"] = m.get("locked", False)
        window["layout_name"] = m.get("layout") or window.get("layout_name") or "dwindle"
        monitor = next((x for x in state.get("monitors", []) if x.get("id") == window.get("monitor")), {})
        window["monitor_name"] = monitor.get("name")
        window["monitor_area"] = monitor_area(monitor) if monitor else None
    state["groups"] = groups(state["windows"], state.get("monitors", []))
    state["layout_snapshot"] = True
    if grid:
        try:
            return apply_native_grid(state, grid)
        except (KeyError, TypeError, ValueError) as error:
            state["warnings"].append(f"Captura nativa do grid inválida: {error}")
    else:
        state["warnings"].append("Árvore nativa do Hyprland indisponível; grid inferido apenas pela geometria")
    state["complete"] = False
    try:
        state["tile_tree"] = infer_tree([g for g in state["groups"] if not g["floating"]])
        state["grid"] = {"source": "geometry-inferred", "layout": "dwindle",
                         "tiled_leaves": sum(not g["floating"] for g in state["groups"]),
                         "split_nodes": max(0, sum(not g["floating"] for g in state["groups"]) - 1)}
    except (ValueError, TypeError, KeyError) as error:
        state["tile_tree"] = None
        state["warnings"].append(str(error))
        state["complete"] = False
    return state


def target_rect(group, monitors, *, normal=False):
    box = ([*(group.get("tile_at") or group["at"]), *(group.get("tile_size") or group["size"])]
           if normal else rect(group))
    source = group.get("monitor_area")
    monitor = next((m for m in monitors if m.get("name") == group.get("monitor_name")), None)
    if not monitor:
        monitor = next(iter(monitors), None)
    if source and monitor:
        dest = monitor_area(monitor)
        box = [dest[0] + (box[0] - source[0]) * dest[2] / source[2],
               dest[1] + (box[1] - source[1]) * dest[3] / source[3],
               box[2] * dest[2] / source[2], box[3] * dest[3] / source[3]]
    return [round(x) for x in box]


def matches(item, actual, state, observed, tolerance=4):
    group = next((g for g in state.get("groups", []) if item["restore_id"] in g["members"]), None)
    if not group:
        return True  # Legacy snapshots without geometry remain readable.
    expected = target_rect(group, observed.get("monitors", []))
    got = [*(actual.get("at") or []), *(actual.get("size") or [])]
    if len(got) != 4 or any(abs(x-y) > tolerance for x, y in zip(expected, got)):
        return False
    return (bool(item.get("floating")) == bool(actual.get("floating"))
            and item.get("fullscreen", 0) == actual.get("fullscreen", 0))


def restore(api, state):
    """Rebuild native groups and BSP splits; leave unrelated windows alone."""
    desired = state.get("groups") or groups(state["windows"], state.get("monitors", []))
    if not desired or any(not g.get("at") or not g.get("size") for g in desired):
        return {}
    live = api.clients()
    associations = {w["restore_id"]: api.associated_client(w, live, str(state.get("boot_id"))) for w in state["windows"]}
    known = {c["address"] for c in associations.values() if c}
    extras = [c for c in live if c.get("workspace", {}).get("id") == api.WORKSPACE_ID and c["address"] not in known and not c.get("floating")]
    if extras:
        return {"error": "Layout preservado: há janelas adicionais não pertencentes à restauração"}
    active = next((c for c in live if c.get("focusHistoryID") == 0), None)
    available = []
    for group in desired:
        members = [m for m in group["members"] if associations.get(m)]
        if members:
            available.append(dict(group, members=members))
    if any(g.get("layout", "dwindle") != "dwindle" for g in available if not g["floating"]):
        return {"error": "O layout nativo salvo não é Dwindle; reconstrução automática pendente"}
    tiles = [g for g in available if not g["floating"]]
    saved_tree = state.get("tile_tree")
    grid_metadata = state.get("grid") if isinstance(state.get("grid"), dict) else {}
    if saved_tree:
        tree = prune_tree(saved_tree, {g["id"] for g in tiles})
    elif tiles and grid_metadata.get("source") == "hyprland-native":
        return {"error": "O snapshot nativo declara tiled windows, mas não contém a árvore salva"}
    else:
        try:
            tree = infer_tree(tiles)
        except (ValueError, TypeError, KeyError) as error:
            return {"error": str(error)}  # Validate before changing any live window.
    tree_groups = set()
    def collect_groups(node):
        if not node:
            return
        if "group" in node:
            tree_groups.add(node["group"])
            return
        collect_groups(node.get("left"))
        collect_groups(node.get("right"))
    collect_groups(tree)
    if tree_groups != {g["id"] for g in tiles}:
        return {"error": "A árvore salva não corresponde exatamente aos grupos tiled disponíveis"}
    monitors = api.hypr_json("monitors")
    wanted_monitor = next((m for m in monitors if any(g.get("monitor_name") == m.get("name") for g in available)), None)
    try:
        if wanted_monitor:
            api.dispatch(f'hl.dsp.workspace.move({{workspace="{api.WORKSPACE_ID}",monitor={json.dumps(wanted_monitor["name"])}}})')
        # Detach only managed windows and stage them floating before building splits.
        for client in associations.values():
            if not client:
                continue
            s = selector(client["address"])
            lua(api, f'local w=hl.get_window({s});if w.group then w.group:remove(w) end;'
                f'hl.dispatch(hl.dsp.window.fullscreen_state({{window=w,internal=0,client=0}}));'
                f'hl.dispatch(hl.dsp.window.float({{window=w,action="enable"}}))')
        leaders = {}
        for group in available:
            leader = associations[group["members"][0]]
            leaders[group["id"]] = leader
            s = selector(leader["address"])
            if group["is_group"]:
                code = f'local w=hl.get_window({s});if not w.group then hl.dispatch(hl.dsp.group.toggle({{window=w}})) end;'
                for member in group["members"][1:]:
                    code += f'w.group:add(hl.get_window({selector(associations[member]["address"])}));'
                lua(api, code)
            box = target_rect(group, monitors, normal=True)
            api.dispatch(f'hl.dsp.window.resize({{window={s},x={box[2]},y={box[3]},relative=false}})')
            api.dispatch(f'hl.dsp.window.move({{window={s},x={box[0]},y={box[1]},relative=false}})')
        def seed(node):
            return node["group"] if "group" in node else seed(node["left"])
        def tile(group_id):
            api.dispatch(f'hl.dsp.window.float({{window={selector(leaders[group_id]["address"])},action="disable"}})')
        def branch(node):
            if "group" in node:
                return
            left, right = seed(node["left"]), seed(node["right"])
            api.dispatch(f'hl.dsp.focus({{window={selector(leaders[left]["address"])}}})')
            api.dispatch('hl.dsp.layout(' + json.dumps("preselect " + ("r" if node["axis"] == 0 else "d")) + ')')
            tile(right)
            api.dispatch(f'hl.dsp.focus({{window={selector(leaders[left]["address"])}}})')
            ratio = max(.1, min(1.9, node["ratio"] * 2))
            api.dispatch('hl.dsp.layout(' + json.dumps(f"splitratio {ratio:.8f} exact") + ')')
            branch(node["left"])
            branch(node["right"])
        if tree:
            tile(seed(tree))
            branch(tree)
        # Group selection and fullscreen are applied after the tiling tree exists.
        for group in available:
            leader = leaders[group["id"]]
            s = selector(leader["address"])
            if group["is_group"]:
                index = group["members"].index(group["active"]) + 1 if group["active"] in group["members"] else 1
                api.dispatch(f'hl.dsp.group.active({{window={s},index={index}}})')
                action = "enable" if group["locked"] else "disable"
                api.dispatch(f'hl.dsp.group.lock({{window={s},action="{action}"}})')
            if group["fullscreen"]:
                api.dispatch(f'hl.dsp.window.fullscreen_state({{window={s},internal={group["fullscreen"]},client={group["fullscreen"]}}})')
        focus = min(state["windows"], key=lambda w: w.get("focus_order") if isinstance(w.get("focus_order"), int) else 999)
        focus_client = associations.get(focus["restore_id"])
        if focus_client:
            api.dispatch(f'hl.dsp.focus({{window={selector(focus_client["address"])}}})')
        return {"groups": len(available), "algorithm": "dwindle", "adapted": state.get("monitors", []) != monitor_records(monitors)}
    except Exception as error:
        # A dispatcher can fail after staging windows as floats. Re-enable tiling
        # for every managed saved tile so a partial replay never strands the grid.
        tiled_ids = {member for group in available if not group["floating"] for member in group["members"]}
        for identity in tiled_ids:
            client = associations.get(identity)
            if not client:
                continue
            try:
                api.dispatch(f'hl.dsp.window.float({{window={selector(client["address"])},action="disable"}})')
            except Exception:
                pass
        return {"error": str(error)}
    finally:
        # A manual restore/test must not strand the user on its temporary workspace.
        if active and active["address"] not in known:
            try:
                api.dispatch(f'hl.dsp.focus({{window={selector(active["address"])}}})')
            except (OSError, RuntimeError):
                pass

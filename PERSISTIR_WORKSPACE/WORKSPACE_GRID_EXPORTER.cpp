#include <plugins/PluginAPI.hpp>
#include <state/WorkspaceState.hpp>
#include <desktop/Workspace.hpp>
#include <desktop/view/Window.hpp>
#include <desktop/view/Group.hpp>
#include <layout/space/Space.hpp>
#include <layout/target/Target.hpp>
#include <layout/algorithm/Algorithm.hpp>
#include <layout/algorithm/tiled/dwindle/DwindleAlgorithm.hpp>

#include <cstdint>
#include <format>
#include <string>

#ifndef WINDOC_HYPRLAND_HASH
#error "The exact Hyprland build hash must be supplied at compile time"
#endif

#ifndef WINDOC_EXPORTER_BUILD_ID
#error "The exporter build ID must be supplied at compile time"
#endif

namespace {
using Layout::Tiled::CDwindleAlgorithm;
using Layout::Tiled::SDwindleNodeData;

std::string windowAddress(PHLWINDOW window) {
    return window ? std::format("0x{:x}", reinterpret_cast<uintptr_t>(window.get())) : "";
}

std::string boxJson(const CBox& box) {
    return std::format("[{}, {}, {}, {}]", box.x, box.y, box.w, box.h);
}

std::string treeJson(SP<SDwindleNodeData> node) {
    if (!node)
        return "null";

    if (node->isNode) {
        const auto FIRST  = node->children[0].lock();
        const auto SECOND = node->children[1].lock();
        if (!FIRST || !SECOND)
            return "null";

        return std::format(
            "{{\"kind\":\"split\",\"axis\":{},\"split_top\":{},\"split_ratio\":{},\"box\":{},\"first\":{},\"second\":{}}}",
            node->splitTop ? 1 : 0, node->splitTop ? "true" : "false", node->splitRatio, boxJson(node->box), treeJson(FIRST), treeJson(SECOND));
    }

    const auto TARGET = node->pTarget.lock();
    const auto WINDOW = TARGET ? TARGET->window() : nullptr;
    if (!WINDOW)
        return "null";

    std::string members = "[";
    std::string active;
    bool        locked = false;
    const bool  isGroup = static_cast<bool>(WINDOW->m_group);
    if (WINDOW->m_group) {
        bool first = true;
        for (const auto& reference : WINDOW->m_group->windows()) {
            const auto member = reference.lock();
            if (!member)
                continue;
            if (!first)
                members += ",";
            first = false;
            members += std::format("\"{}\"", windowAddress(member));
        }
        active = windowAddress(WINDOW->m_group->current());
        locked = WINDOW->m_group->locked();
    } else {
        members += std::format("\"{}\"", windowAddress(WINDOW));
        active = windowAddress(WINDOW);
    }
    members += "]";

    return std::format("{{\"kind\":\"tile\",\"box\":{},\"windows\":{},\"active\":\"{}\",\"locked\":{},\"is_group\":{}}}",
                       boxJson(node->box), members, active, locked ? "true" : "false", isGroup ? "true" : "false");
}

std::string exportWorkspace(int id) {
    const auto failure = [id](const std::string& error) {
        return std::format("{{\"workspace_id\":{},\"build_id\":\"{}\",\"error\":\"{}\"}}", id, WINDOC_EXPORTER_BUILD_ID, error);
    };
    for (const auto& workspace : State::workspaceState()->workspacesCopy()) {
        if (!workspace || workspace->m_id != id || !workspace->m_space)
            continue;

        const auto ALGORITHM = workspace->m_space->algorithm();
        const auto DWINDLE = ALGORITHM ? dynamic_cast<CDwindleAlgorithm*>(ALGORITHM->tiledAlgo().get()) : nullptr;
        if (!DWINDLE)
            return failure("workspace layout is not Dwindle");

        SP<SDwindleNodeData> root;
        size_t              tiledTargets = 0;
        for (const auto& weakTarget : workspace->m_space->targets()) {
            const auto target = weakTarget.lock();
            if (!target || target->floating())
                continue;
            ++tiledTargets;

            const auto leaf = DWINDLE->getNodeFromWindow(target->window());
            if (!leaf)
                continue;

            auto current = leaf;
            while (const auto parent = current->pParent.lock())
                current = parent;
            root = current;
            break;
        }

        if (!root) {
            if (tiledTargets == 0)
                return std::format("{{\"workspace_id\":{},\"layout\":\"dwindle\",\"build_id\":\"{}\",\"work_area\":{},\"tree\":null}}",
                                   id, WINDOC_EXPORTER_BUILD_ID, boxJson(workspace->m_space->workArea()));
            return failure("workspace has tiled targets but no Dwindle root");
        }

        return std::format("{{\"workspace_id\":{},\"layout\":\"dwindle\",\"build_id\":\"{}\",\"work_area\":{},\"tree\":{}}}",
                           id, WINDOC_EXPORTER_BUILD_ID, boxJson(workspace->m_space->workArea()), treeJson(root));
    }

    return failure("workspace not found");
}
} // namespace

APICALL EXPORT std::string PLUGIN_API_VERSION() {
    return HYPRLAND_API_VERSION;
}

APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE handle) {
    const auto VERSION = HyprlandAPI::getHyprlandVersion(handle);
    if (VERSION.hash != WINDOC_HYPRLAND_HASH)
        return {"windoc-grid-exporter", "Disabled: Hyprland build hash mismatch", "WinDoc", "1"};

    HyprlandAPI::registerHyprCtlCommand(handle, SHyprCtlCommand{
        "windoc-layout", false,
        [](eHyprCtlOutputFormat, std::string request) {
            int id = 1;
            try {
                const auto separator = request.find_first_of(' ');
                if (separator != std::string::npos)
                    id = std::stoi(request.substr(separator + 1));
            } catch (...) {
                return std::string("{\"error\":\"invalid workspace id\"}");
            }
            return exportWorkspace(id);
        }});

    return {"windoc-grid-exporter", "Read-only Dwindle tree exporter", "WinDoc", "1"};
}

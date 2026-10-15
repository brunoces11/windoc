import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Services.Pipewire
import Quickshell.Services.UPower
import qs.Commons
import qs.Ui
import "DockModel.js" as DockModel
import "DockSettings.js" as DockSettings
import "components"

Item {
    id: root

    // Properties injected by Omarchy Shell host
    property string omarchyPath: Quickshell.env("OMARCHY_PATH")
    property var shell: null
    property var manifest: null
    property var pluginRegistry: null
    // Omarchy 4.0.3 scopes pluginRegistry to this plugin's own manifest, so
    // getWidgetSource() can no longer resolve another plugin's entry point.
    // Declaring this makes the host inject the widget-catalogue facade, whose
    // snapshot still carries every registered widget's Component.
    property var barWidgetRegistry: null
    readonly property int widgetRegistryRevision: barWidgetRegistry ? barWidgetRegistry.revision : 0

    // Dock state & Multi-source Live Bar Position Tracking
    property bool opened: true
    property bool pluginEnabled: true
    property string shellConfigPath: Quickshell.env("HOME") + "/.config/omarchy/shell.json"
    property string detectedBarPosition: {
        if (shell && shell.barConfig && shell.barConfig.position) return shell.barConfig.position
        return "top"
    }
    property bool detectedBarTransparent: {
        if (shell && shell.barConfig && typeof shell.barConfig.transparent === "boolean") {
            return shell.barConfig.transparent
        }
        return false
    }

    // Live bar position (only used to position the dock on the opposite side of the screen)
    property string barPosition: {
        if (shell && shell.bar && shell.bar.position) return shell.bar.position
        return detectedBarPosition
    }
    readonly property bool isVertical: barPosition === "left" || barPosition === "right"

    // Live dock edge on screen (opposite to system status bar)
    readonly property string dockScreenPosition: {
        if (root.barPosition === "top") return "bottom"
        if (root.barPosition === "bottom") return "top"
        if (root.barPosition === "left") return "right"
        if (root.barPosition === "right") return "left"
        return "bottom"
    }

    // Live Bar & Tray Transparency Tracking (Auto-syncs dock with bar & tray glassmorphism)
    readonly property bool isBarTransparent: {
        if (shell && shell.bar && typeof shell.bar.transparent === "boolean") return shell.bar.transparent
        return detectedBarTransparent
    }

    // Static Standard Dock Geometry (Strictly stable, no jumping/twitching on window state)
    readonly property real slotSize: 42
    readonly property real iconBaseSize: 24
    // Shared anchor line for the right-side tooltip and tray popups. The
    // tooltip's lower edge is at local y=12 in the dock window.
    readonly property real systemTrayPopupAnchorY: 12
    readonly property real systemTrayPopupGap: root.dockScreenPosition === "top"
        ? root.systemTrayPopupAnchorY - (root.slotSize + 8)
        : -root.systemTrayPopupAnchorY
    property real currentTrayAnchorGap: root.systemTrayPopupGap
    property real currentTrayAnchorMargin: 0
    property real systemTrayAnchorX: -1
    property real systemTrayAnchorY: -1
    property var systemTrayChevronAnchorItem: null
    property real systemTrayChevronAnchorX: -1

    // Live 1D Rail Displacement for Main Dock Bar
    property int dockDragActiveIndex: -1
    property int dockDragTargetIndex: -1
    property int currentMergeTargetIndex: -1

    function getDockVisualSlot(itemIdx, dragIdx, targetIdx) {
        if (dragIdx < 0 || targetIdx < 0 || dragIdx === targetIdx) return itemIdx;
        if (itemIdx === dragIdx) return dragIdx;
        if (dragIdx < targetIdx) {
            if (itemIdx > dragIdx && itemIdx <= targetIdx) return itemIdx - 1;
        } else {
            if (itemIdx >= targetIdx && itemIdx < dragIdx) return itemIdx + 1;
        }
        return itemIdx;
    }

    // Live 2D Rail Displacement inside Folder Grid
    property int folderDragActiveIndex: -1
    property int folderDragTargetIndex: -1

    function getFolderVisualSlot(itemIdx, dragIdx, targetIdx) {
        if (dragIdx < 0 || targetIdx < 0 || dragIdx === targetIdx) return itemIdx;
        if (itemIdx === dragIdx) return dragIdx;
        if (dragIdx < targetIdx) {
            if (itemIdx > dragIdx && itemIdx <= targetIdx) return itemIdx - 1;
        } else {
            if (itemIdx >= targetIdx && itemIdx < dragIdx) return itemIdx + 1;
        }
        return itemIdx;
    }

    // Direct IPC handler for rosakodu.dock target
    IpcHandler {
        target: "rosakodu.dock"
        function open(): string { root.open(""); return "ok" }
        function close(): string { root.close(); return "ok" }
        function toggle(): string { root.toggle(); return "ok" }
        function refresh(): string { return root.refresh() }
        function openWidgetPicker(): string {
            root.openWidgetPicker()
            return "ok"
        }
        function addWidget(widgetId: string): string { root.addDockWidget(widgetId); return "ok" }
        function removeWidget(widgetId: string): string { root.removeDockWidget(widgetId, ""); return "ok" }
        function setShowAppMenu(val: string): string { root.setShowAppMenu(val === "true" || val === "1"); return "ok" }
        function setAppMenuPosition(pos: string): string { root.setAppMenuPosition(pos); return "ok" }
        function setWidgetsEnabled(val: string): string { root.setWidgetsEnabled(val === "true" || val === "1"); return "ok" }
        function setWidgetPosition(pos: string): string { root.setWidgetPosition(pos); return "ok" }
        function setEditMode(val: string): string { root.isEditMode = (val === "true" || val === "1"); return "ok" }
        function setDockEnabled(val: string): string { root.dockEnabled = (val === "true" || val === "1"); root.saveSettings(); return "ok" }
        function setAutohide(val: string): string { root.setAutohide(val === "true" || val === "1"); return "ok" }
        function setVisibilityMode(mode: string): string { root.setVisibilityMode(mode); return "ok" }
        function setVisibleWorkspace(workspace: string): string { root.setVisibleWorkspace(workspace); return "ok" }
        function toggleReveal(): string { return root.toggleReveal() }
        function setAutohideEdgeDepth(val: string): string { var n = parseInt(val, 10); if (!isNaN(n) && n >= 1 && n <= 64) { root.autohideEdgeDepth = n; root.saveSettings(); } return "ok" }
        function setShowFolderTitles(val: string): string { root.showFolderTitles = (val === "true" || val === "1"); root.saveSettings(); return "ok" }
        function setShowBadges(val: string): string { root.showBadges = (val === "true" || val === "1"); root.saveSettings(); return "ok" }
        function setOverlayMode(val: string): string { root.overlayMode = (val === "true" || val === "1"); root.saveSettings(); return "ok" }
        function toggleTray(): string { root.toggleTrayOverflow(); return "ok" }
        function openTraySettings(): string { root.openSystemTraySettings(); return "ok" }
        function ping(): string { return "ok" }
    }

    function openWidgetPicker() {
        root.opened = true
        root.widgetPickerRevealOwned = false
        root.widgetPickerPreviousVisibilityOverride = root.visibilityOverride
        if (!root.dockRevealed) {
            var result = root.toggleReveal("internal")
            if (result !== "shown") return
            root.widgetPickerRevealOwned = true
        }
        if (widgetPicker) {
            widgetPicker.opened = true
            autohideLeaveTimer.stop()
        }
    }

    // Methods called by shell.summon / shell.hide / shell.toggle
    function open(payloadJson) {
        root.opened = true
        if (payloadJson) {
            try {
                var p = (typeof payloadJson === "string") ? JSON.parse(payloadJson) : payloadJson
                if (p && p.action === "openWidgetPicker") {
                    if (widgetPicker) widgetPicker.opened = true
                } else if (p && p.action === "closeWidgetPicker") {
                    if (widgetPicker) widgetPicker.opened = false
                }
            } catch(e) {}
        }
    }

    function close() {
        root.opened = false
        root.activeMenuItem = null
        root.activeStackItem = null
        root.dockDragActiveIndex = -1
        root.dockDragTargetIndex = -1
        root.currentMergeTargetIndex = -1
        root.folderDragActiveIndex = -1
        root.folderDragTargetIndex = -1
    }

    function toggle() {
        root.opened = !root.opened
        root.activeMenuItem = null
        root.activeStackItem = null
        root.dockDragActiveIndex = -1
        root.dockDragTargetIndex = -1
        root.currentMergeTargetIndex = -1
        root.folderDragActiveIndex = -1
        root.folderDragTargetIndex = -1
    }

    function toggleStack(item, index) {
        root.activeMenuItem = null
        if (!item) {
            root.activeStackItem = null
            return
        }
        var itemId = item.id || item.appId || ""
        if (root.activeStackItem && (root.activeStackItem.id === itemId || root.activeStackItem.appId === itemId || root.activeStackItemIndex === index)) {
            root.activeStackItem = null
        } else {
            root.activeStackItemIndex = index
            if (item.isStack) {
                root.activeStackItem = item
            }
        }
    }

    // Persistent stable chronological window registry (never reordered on focus or workspace switch)
    property var knownWindows: []
    property string pendingFocusAppId: ""
    property double pendingFocusTimestamp: 0

    function requestFocusOnLaunch(appId) {
        var clean = DockModel.stripDesktop(appId || "").toLowerCase()
        if (!clean) return
        root.pendingFocusAppId = clean
        root.pendingFocusTimestamp = Date.now()
    }

    function syncKnownWindows() {
        var live = ToplevelManager.toplevels ? ToplevelManager.toplevels.values : []
        var nextKnown = []
        // 1. Preserve existing known windows in their original creation order if still alive
        for (var i = 0; i < root.knownWindows.length; i++) {
            var k = root.knownWindows[i]
            for (var j = 0; j < live.length; j++) {
                if (live[j] === k) {
                    nextKnown.push(k)
                    break
                }
            }
        }
        // 2. Append newly opened windows to the end
        for (var l = 0; l < live.length; l++) {
            var cand = live[l]
            if (cand && nextKnown.indexOf(cand) === -1) {
                nextKnown.push(cand)
            }
        }

        var unchanged = nextKnown.length === root.knownWindows.length
        if (unchanged) {
            for (var m = 0; m < nextKnown.length; m++) {
                if (nextKnown[m] !== root.knownWindows[m]) {
                    unchanged = false
                    break
                }
            }
        }
        if (!unchanged) {
            root.knownWindows = nextKnown
        }
        return root.knownWindows
    }

    function activateAppWindow(appId, winIndex) {
        root.syncKnownWindows()
        var tops = root.knownWindows
        var matched = []
        for (var i = 0; i < tops.length; i++) {
            var t = tops[i]
            if (t && DockModel.matchToplevel(t, appId, null)) {
                matched.push(t)
            }
        }
        if (winIndex >= 0 && winIndex < matched.length && matched[winIndex] && matched[winIndex].activate) {
            matched[winIndex].activate()
        }
    }

    // Deterministic Right-Click Menu Toggle (Only for Folders / Stacks icon selection)
    function toggleMenu(item, index, fromFolder) {
        if (!item || !item.isStack) {
            root.activeMenuItem = null
            root.isMenuFromFolder = false
            return
        }
        var appId = item.appId || item.id || ""
        if (root.activeMenuItem && root.activeMenuItem.appId === appId) {
            root.activeMenuItem = null
            root.isMenuFromFolder = false
        } else {
            root.activeStackItem = null
            root.isMenuFromFolder = !!fromFolder
            root.activeMenuItemIndex = index
            root.activeMenuItem = item
        }
    }

    // Standalone plugin lifecycle: enabled by default, disabled ONLY if in disabledPlugins
    function updatePluginEnabled() {
        var reg = root.pluginRegistry || (shell ? shell.pluginRegistry : null)
        if (reg && typeof reg.isEnabled === "function") {
            root.pluginEnabled = reg.isEnabled("rosakodu.dock")
            return
        }
        try {
            var raw = shellConfigFile.text()
            if (raw && raw.length > 0) {
                var cfg = JSON.parse(raw)
                if (cfg) {
                    if (Array.isArray(cfg.disabledPlugins) && cfg.disabledPlugins.indexOf("rosakodu.dock") !== -1) {
                        root.pluginEnabled = false
                        return
                    }
                    if (Array.isArray(cfg.plugins)) {
                        for (var p = 0; p < cfg.plugins.length; p++) {
                            if (cfg.plugins[p] && (cfg.plugins[p].id === "rosakodu.dock" || cfg.plugins[p] === "rosakodu.dock")) {
                                root.pluginEnabled = true
                                return
                            }
                        }
                    }
                    if (cfg.bar && cfg.bar.layout) {
                        for (var s in cfg.bar.layout) {
                            var arr = cfg.bar.layout[s] || []
                            for (var k = 0; k < arr.length; k++) {
                                var entry = arr[k]
                                if (entry && (entry.id === "rosakodu.dock" || entry === "rosakodu.dock")) {
                                    root.pluginEnabled = true
                                    return
                                }
                            }
                        }
                    }
                }
            }
        } catch(e) {}
        root.pluginEnabled = true
    }

    function parseShellConfigFile() {
        root.updatePluginEnabled()
        try {
            var raw = shellConfigFile.text()
            if (raw && raw.length > 0) {
                var cfg = JSON.parse(raw)
                if (cfg && cfg.bar) {
                    if (cfg.bar.position && root.detectedBarPosition !== cfg.bar.position) {
                        root.detectedBarPosition = cfg.bar.position
                    }
                    if (cfg.bar.transparent !== undefined && root.detectedBarTransparent !== (cfg.bar.transparent === true)) {
                        root.detectedBarTransparent = (cfg.bar.transparent === true)
                    }
                }
            }
        } catch(e) {}
    }

    FileView {
        id: shellConfigFile
        path: root.shellConfigPath
        watchChanges: true
        atomicWrites: true
        printErrors: false
        onLoaded: root.parseShellConfigFile()
        onFileChanged: reload()
    }

    // Omarchy's default coding agent, to give its org.omarchy.agent window the agent's icon
    property string defaultAgent: ""
    readonly property string defaultAgentAssetPath: root.defaultAgent.length > 0
        ? Quickshell.shellDir + "/plugins/agents/assets/" + root.defaultAgent + ".svg"
        : ""

    function applyDefaultAgent(assetFound) {
        DockModel.setDefaultAgent(root.defaultAgent, assetFound ? "file://" + root.defaultAgentAssetPath : "")
        root.iconRevision++
        root.updateDockItems()
    }

    FileView {
        path: Quickshell.env("HOME") + "/.config/omarchy/defaults/agent"
        watchChanges: true
        printErrors: false
        onLoaded: root.defaultAgent = text().trim().toLowerCase()
        onLoadFailed: root.defaultAgent = ""
        onFileChanged: reload()
    }

    FileView {
        path: root.defaultAgentAssetPath
        printErrors: false
        onLoaded: root.applyDefaultAgent(true)
        onLoadFailed: root.applyDefaultAgent(false)
    }

    // Dock visibility, placement, and folder settings
    property string settingsPath: Quickshell.env("HOME") + "/.config/omarchy/dock-settings.json"
    property bool dockEnabled: true
    property string visibilityMode: "always"
    property string preferredVisibilityMode: "hover"
    readonly property bool autohide: root.visibilityMode !== "always"
    property bool overlayMode: false
    property int visibilityOverride: DockSettings.VISIBILITY_OVERRIDE_FOLLOW
    property string keyboardTargetWorkspace: ""
    property string keyboardTargetMonitorName: ""
    // Which screen triggered the current reveal (edge-hover screen, or the
    // focused screen for a keyboard toggle). "" means no specific trigger is
    // recorded, in which case screenRevealTarget() falls back to the focused
    // monitor.
    property string revealMonitorName: ""
    property string baseDockMonitorName: ""
    property bool widgetPickerRevealOwned: false
    property int widgetPickerPreviousVisibilityOverride: DockSettings.VISIBILITY_OVERRIDE_FOLLOW
    property string visibleWorkspace: "all"
    property int autohideEdgeDepth: 1  // pixels from screen edge that trigger dock reveal
    readonly property int effectiveAutohideEdgeDepth: Math.max(4, Math.min(64, root.autohideEdgeDepth))
    property bool showFolderTitles: true
    property bool showBadges: true
    property bool glassmorphism: false
    property real blurOpacity: 0.68
    property bool windowsTaskbarMode: true
    property string taskbarAppAlignment: "center"
    readonly property bool showAppMenu: root.widgetsEnabled && root.dockWidgets && (root.dockWidgets.indexOf("omarchy.apps") !== -1)
    property string appMenuPosition: "left"
    property bool widgetsEnabled: true
    property string widgetPosition: "right"
    property var dockWidgets: []
    property var widgetSavedPositions: ({})
    property bool isDockHovered: false
    // The pointer is over an app's hover window list, which lives outside the dock surface.
    property bool isWindowListHovered: false
    property bool isStackHovered: false
    property bool isMenuHovered: false
    property bool isWidgetPanelHovered: false

    function workspaceForSelector(selector) {
        var normalized = DockSettings.normalizeVisibleWorkspace(selector)
        if (normalized === "all") return null
        var workspaces = Hyprland.workspaces && Hyprland.workspaces.values ? Hyprland.workspaces.values : []
        for (var i = 0; i < workspaces.length; i++) {
            var workspace = workspaces[i]
            if (workspace && DockSettings.workspaceMatches(normalized, workspace.id, workspace.name)) {
                return workspace
            }
        }
        return null
    }

    function screenForMonitorName(monitorName) {
        var name = String(monitorName || "")
        if (name === "") return null
        var screens = Quickshell.screens || []
        for (var i = 0; i < screens.length; i++) {
            if (screens[i] && String(screens[i].name || "") === name) return screens[i]
        }
        return null
    }

    function screenForMonitor(monitor) {
        return monitor ? root.screenForMonitorName(monitor.name) : null
    }

    function screenShowsDock(screen) {
        if (!screen) return false
        var target = DockSettings.dockScreenTarget(
            root.visibleWorkspace,
            root.visibilityMode,
            root.visibilityOverride
        )
        var configuredName = (root.configuredWorkspace && root.configuredWorkspace.monitor)
            ? String(root.configuredWorkspace.monitor.name || "")
            : ""
        var focusedName = Hyprland.focusedMonitor ? String(Hyprland.focusedMonitor.name || "") : ""
        return DockSettings.screenShowsDock(
            target,
            screen.name,
            configuredName,
            root.keyboardTargetMonitorName,
            focusedName
        )
    }

    function anyDockSurfaceHovered() {
        var instances = dockVariants.instances
        if (!instances) return false
        for (var i = 0; i < instances.length; i++) {
            var handler = instances[i] ? instances[i].hoverHandler : null
            if (handler && handler.hovered) return true
        }
        return false
    }

    function focusedWorkspaceForKeyboardToggle() {
        var monitorWorkspace = Hyprland.focusedMonitor
            ? Hyprland.focusedMonitor.activeWorkspace
            : null
        var toplevelWorkspace = Hyprland.activeToplevel
            ? Hyprland.activeToplevel.workspace
            : null
        return DockSettings.keyboardToggleWorkspace(
            monitorWorkspace,
            Hyprland.focusedWorkspace,
            toplevelWorkspace
        )
    }

    readonly property bool hasExplicitWorkspace: root.visibleWorkspace !== "all"
    readonly property var configuredWorkspace: root.hasExplicitWorkspace
        ? root.workspaceForSelector(root.visibleWorkspace)
        : null
    readonly property var keyboardTargetWorkspaceObject: root.keyboardTargetWorkspace !== ""
        ? root.workspaceForSelector(root.keyboardTargetWorkspace)
        : null
    readonly property var effectiveDockScreen: {
        var target = DockSettings.dockScreenTarget(
            root.visibleWorkspace,
            root.visibilityMode,
            root.visibilityOverride
        )
        if (target === "configured" && root.configuredWorkspace && root.configuredWorkspace.monitor) {
            var configuredScreen = root.screenForMonitor(root.configuredWorkspace.monitor)
            if (configuredScreen) return configuredScreen
        }
        if (target === "captured") {
            var keyboardScreen = root.screenForMonitorName(root.keyboardTargetMonitorName)
            if (keyboardScreen) return keyboardScreen
        }
        if (target === "all") {
            var focusedForAll = root.screenForMonitor(Hyprland.focusedMonitor)
            if (focusedForAll) return focusedForAll
        }
        if (target === "focused") {
            var focusedScreen = root.screenForMonitor(Hyprland.focusedMonitor)
            if (focusedScreen) return focusedScreen
        }
        var baseScreen = root.screenForMonitorName(root.baseDockMonitorName)
        if (baseScreen) return baseScreen
        return Quickshell.screens && Quickshell.screens.length > 0 ? Quickshell.screens[0] : null
    }

    readonly property var currentDockWorkspace: {
        if (root.hasExplicitWorkspace) return root.configuredWorkspace
        if (root.visibilityOverride === DockSettings.VISIBILITY_OVERRIDE_SHOWN && root.keyboardTargetWorkspaceObject) {
            return root.keyboardTargetWorkspaceObject
        }
        var screen = root.effectiveDockScreen
        var monitor = screen ? Hyprland.monitorFor(screen) : Hyprland.focusedMonitor
        if (monitor && monitor.activeWorkspace) return monitor.activeWorkspace
        return Hyprland.focusedWorkspace
    }

    readonly property bool workspaceAllowed: {
        if (!root.hasExplicitWorkspace) return true
        var workspace = root.currentDockWorkspace
        return workspace !== null
    }

    readonly property bool dockAvailable: root.opened
        && root.pluginEnabled
        && root.dockEnabled
        && root.workspaceAllowed
        && root.isPinnedLoaded
    readonly property bool dockMapped: root.dockAvailable && !remapTimer.running
    readonly property bool dockRevealed: root.dockAvailable && !root.shouldSlideOut

    property var loadedWidgetItems: []

    property string currentMinuteString: Qt.formatDateTime(new Date(), "dddd HH:mm")
    property string currentHourString: Qt.formatDateTime(new Date(), "HH")
    property string currentMinutePart: Qt.formatDateTime(new Date(), "mm")

    Timer {
        id: clockTimer
        interval: 1000
        repeat: true
        running: root.hasClockWidget
        onTriggered: {
            var now = new Date()
            var minStr = Qt.formatDateTime(now, "dddd HH:mm")
            if (root.currentMinuteString !== minStr) {
                root.currentMinuteString = minStr
                root.currentHourString = Qt.formatDateTime(now, "HH")
                root.currentMinutePart = Qt.formatDateTime(now, "mm")
            }
        }
    }

    function checkWidgetPanelsOpen() {
        if (widgetPicker && widgetPicker.opened) return true
        if (root.loadedWidgetItems) {
            for (var i = 0; i < root.loadedWidgetItems.length; i++) {
                var w = root.loadedWidgetItems[i]
                if (w) {
                    if (w.opened === true) return true
                    if (w.panelLoader && w.panelLoader.item && w.panelLoader.item.opened === true) return true
                    if (w.panel && w.panel.open === true) return true
                }
            }
        }
        if (root.shell && root.shell.openPanelIds) {
            // openPanelIds is a set the shell adds to on summon and removes
            // from on hide, so a panel that closes itself can leave its id
            // behind. The shell's own isPluginOpen() knows this and prefers
            // the panel's live `opened` property, falling back to the set only
            // when there is nothing live to ask. Trusting the raw set instead
            // pins the dock open for the rest of the session.
            var askShell = typeof root.shell.isPluginOpen === "function"
            for (var k in root.shell.openPanelIds) {
                if (root.shell.openPanelIds[k] !== true) continue
                if (!askShell || root.shell.isPluginOpen(k)) return true
            }
        }
        return false
    }

    function closeAllWidgetPanels() {
        if (widgetPicker && widgetPicker.opened) widgetPicker.close()
        if (root.shell && typeof root.shell.closeAllPanels === "function") {
            root.shell.closeAllPanels()
        }
        if (root.loadedWidgetItems) {
            for (var i = 0; i < root.loadedWidgetItems.length; i++) {
                var w = root.loadedWidgetItems[i]
                if (w) {
                    if (typeof w.close === "function") {
                        w.close()
                    }
                    if (w.panelLoader && w.panelLoader.item && typeof w.panelLoader.item.close === "function") {
                        w.panelLoader.item.close()
                    }
                    if (w.panel && typeof w.panel.close === "function") {
                        w.panel.close()
                    }
                }
            }
        }
    }

    function evaluateHoverState() {
        if (!root.autohide) return
        var anyOpenWidget = checkWidgetPanelsOpen()
        var isDockWinHovered = !root.shouldSlideOut && root.anyDockSurfaceHovered()
        var anyPopupsActive = root.isStackOpen || root.isMenuOpen || root.isEditingFolderTitle || root.isEditMode || (root.widgetPicker && root.widgetPicker.opened)
        var anyHover = isDockWinHovered || root.isStackHovered || root.isMenuHovered || root.isWindowListHovered || root.isWidgetPanelHovered || anyOpenWidget || anyPopupsActive
        if (anyHover) {
            autohideLeaveTimer.stop()
            root.isDockHovered = true
        } else {
            autohideLeaveTimer.restart()
        }
    }

    Timer {
        id: autohideLeaveTimer
        interval: 1500
        repeat: false
        onTriggered: {
            if (!root.autohide) return
            var anyOpenWidget = root.checkWidgetPanelsOpen()
            var anyPopupsActive = root.isStackOpen || root.isMenuOpen || root.isEditingFolderTitle || root.isEditMode || (root.widgetPicker && root.widgetPicker.opened)
            var anyHover = root.anyDockSurfaceHovered() || root.isStackHovered || root.isMenuHovered || root.isWindowListHovered || root.isWidgetPanelHovered || anyOpenWidget || anyPopupsActive
            if (!anyHover) {
                root.isDockHovered = false
                if (DockSettings.shouldAutoDismissKeyboardReveal(root.visibilityMode, root.visibilityOverride)) {
                    root.visibilityOverride = DockSettings.VISIBILITY_OVERRIDE_FOLLOW
                }
            }
        }
    }

    function getActiveWorkspaceWindowCount() {
        var workspace = root.currentDockWorkspace
        if (workspace && workspace.toplevels && workspace.toplevels.values) {
            return workspace.toplevels.values.length
        }
        return 0
    }

    property int activeWorkspaceWindowCount: root.getActiveWorkspaceWindowCount()

    function refreshActiveWorkspaceWindowCount() {
        root.activeWorkspaceWindowCount = root.getActiveWorkspaceWindowCount()
    }

    onCurrentDockWorkspaceChanged: root.refreshActiveWorkspaceWindowCount()

    Connections {
        target: (typeof Hyprland !== "undefined") ? Hyprland : null
        function onFocusedWorkspaceChanged() {
            root.refreshActiveWorkspaceWindowCount()
            workspaceSyncTimer.restart()
        }
        function onRawEvent(event) {
            if (!event) return
            var name = String(event.name || "")
            if (name === "openwindow" || name === "closewindow" ||
                name === "movewindow" || name === "movewindowv2" ||
                name === "workspace" || name === "workspacev2" ||
                name === "focusedmon" || name === "changefloatingmode" ||
                name === "activewindow" || name === "activewindowv2" ||
                name === "fullscreen") {
                root.refreshActiveWorkspaceWindowCount()
                workspaceSyncTimer.restart()
            }
        }
    }

    Connections {
        target: (typeof Hyprland !== "undefined" && Hyprland.workspaces) ? Hyprland.workspaces : null
        function onValuesChanged() {
            root.refreshActiveWorkspaceWindowCount()
            workspaceSyncTimer.restart()
        }
    }

    Connections {
        target: (typeof ToplevelManager !== "undefined" && ToplevelManager.toplevels) ? ToplevelManager.toplevels : null
        function onValuesChanged() {
            root.refreshActiveWorkspaceWindowCount()
        }
    }

    Timer {
        id: workspaceSyncTimer
        interval: 80
        repeat: false
        onTriggered: {
            if (typeof Hyprland !== "undefined" && typeof Hyprland.refreshToplevels === "function") {
                Hyprland.refreshToplevels()
            }
            root.refreshActiveWorkspaceWindowCount()
        }
    }

    readonly property bool isWorkspaceEmpty: root.activeWorkspaceWindowCount === 0
    readonly property bool isDockActive: root.isDockHovered
        || root.isStackHovered
        || root.isMenuHovered
        || root.isWidgetPanelHovered
        || root.isStackOpen
        || root.isMenuOpen
        || root.isEditingFolderTitle
        || root.isEditMode
        || (root.widgetPicker && root.widgetPicker.opened)
        || root.checkWidgetPanelsOpen()
        || (root.dockDragActiveIndex >= 0)
    readonly property bool shouldSlideOut: DockSettings.shouldSlideOut(
        root.visibilityMode,
        root.visibilityOverride,
        root.isDockActive,
        root.isWorkspaceEmpty
    )

    // The screen whose dock should slide in for the current reveal, or "" if
    // every screen's dock should (always mode, or an explicit visibleWorkspace
    // selector).
    readonly property string revealTargetMonitorName: DockSettings.screenRevealTarget(
        root.visibilityMode,
        root.visibleWorkspace,
        root.revealMonitorName,
        Hyprland.focusedMonitor ? String(Hyprland.focusedMonitor.name || "") : ""
    )

    function screenSlidesOut(screen) {
        return DockSettings.screenSlidesOut(
            root.shouldSlideOut,
            root.revealTargetMonitorName,
            screen ? screen.name : ""
        )
    }

    function closeDockPopups() {
        root.closePopups()
    }

    property double lastToggleRevealTime: 0

    function toggleReveal(revealSource) {
        if (!root.opened || !root.dockEnabled || !root.pluginEnabled || !root.isPinnedLoaded) return "unavailable"
        var source = revealSource === "internal" ? "internal" : "keyboard"
        if (!DockSettings.revealRequestAllowed(root.visibilityMode, source)) return "inactive"

        var now = Date.now()
        if (now - root.lastToggleRevealTime < 300) {
            return root.dockRevealed ? "shown" : "hidden"
        }
        root.lastToggleRevealTime = now

        if (root.dockRevealed) {
            autohideLeaveTimer.stop()
            root.visibilityOverride = DockSettings.VISIBILITY_OVERRIDE_HIDDEN
            root.isDockHovered = false
            root.closeDockPopups()
            return "hidden"
        } else {
            autohideLeaveTimer.stop()
            root.revealMonitorName = Hyprland.focusedMonitor ? String(Hyprland.focusedMonitor.name || "") : ""
            root.visibilityOverride = DockSettings.VISIBILITY_OVERRIDE_SHOWN
            root.isDockHovered = true
            return "shown"
        }
    }

    function handleWidgetPickerOpenedChanged(opened) {
        if (opened) {
            autohideLeaveTimer.stop()
            return
        }

        root.visibilityOverride = DockSettings.releaseInteractionVisibilityOverride(
            root.widgetPickerRevealOwned,
            root.widgetPickerPreviousVisibilityOverride,
            root.visibilityOverride
        )
        root.widgetPickerRevealOwned = false
        root.isDockHovered = false
        root.evaluateHoverState()
    }

    onDockRevealedChanged: {
        if (!dockRevealed) {
            root.closeDockPopups()
            root.revealMonitorName = ""
        }
    }

    onVisibilityModeChanged: {
        root.widgetPickerRevealOwned = false
        root.visibilityOverride = DockSettings.VISIBILITY_OVERRIDE_FOLLOW
        root.keyboardTargetWorkspace = ""
        root.keyboardTargetMonitorName = ""
        root.revealMonitorName = ""
        root.isDockHovered = false
        autohideLeaveTimer.stop()
    }

    onWorkspaceAllowedChanged: {
        if (!workspaceAllowed && root.visibilityOverride === DockSettings.VISIBILITY_OVERRIDE_SHOWN) {
            root.visibilityOverride = DockSettings.VISIBILITY_OVERRIDE_HIDDEN
            root.closeDockPopups()
        }
    }

    onVisibleWorkspaceChanged: {
        root.visibilityOverride = DockSettings.VISIBILITY_OVERRIDE_FOLLOW
        root.keyboardTargetWorkspace = ""
        root.keyboardTargetMonitorName = ""
        root.revealMonitorName = ""
    }

    property var lastRemapScreen: null
    onEffectiveDockScreenChanged: {
        if (root.lastRemapScreen !== root.effectiveDockScreen) {
            root.lastRemapScreen = root.effectiveDockScreen
            var target = DockSettings.dockScreenTarget(
                root.visibleWorkspace,
                root.visibilityMode,
                root.visibilityOverride
            )
            if (target !== "all") remapTimer.restart()
        }
    }

    readonly property var widgetLayout: DockModel.getDockWidgetLayout(root.showAppMenu, root.appMenuPosition, root.widgetsEnabled, root.dockWidgets, root.widgetPosition)
    readonly property var leftWidgetsList: widgetLayout.leftWidgets || []
    readonly property var allSystemTrayWidgets: [
        { id: "omarchy.audio", name: "Volume e Áudio", icon: "󰕾", desc: "Dispositivos de áudio e controle de volume" },
        { id: "omarchy.network", name: "Rede e Conexões", icon: "󰖩", desc: "Wi-Fi, Ethernet e configurações de rede" },
        { id: "brunoma.agents", name: "Agentes de IA", icon: "󰚩", desc: "Consumo de créditos e limites dos modelos de IA" },
        { id: "omarchy.weather", name: "Previsão do Tempo", icon: "󰖐", desc: "Clima e previsão meteorológica atual" },
        { id: "omarchy.monitor", name: "Telas e Display", icon: "󰍹", desc: "Brilho, escala e configurações dos monitores" }
    ]
    readonly property var allSystemTrayWidgetIds: ["omarchy.audio", "omarchy.network", "brunoma.agents", "omarchy.weather", "omarchy.monitor"]
    property string activeTrayPanelId: ""
    property string pendingTrayPanelId: ""
    property bool pendingFloatingSettings: false
    property var systemTrayAnchorItem: null

    property bool systemTrayEnabled: true
    property var systemTrayPinnedWidgets: []
    property bool showDesktopButtonEnabled: true

    function isTrayWidget(widgetId) {
        return widgetId === "taskbar.tray"
    }

    function isDesktopWidget(widgetId) {
        return widgetId === "taskbar.desktop"
    }

    readonly property real desktopSlotWidth: 10
    readonly property real traySlotWidth: {
        var pinned = (root.systemTrayPinnedWidgets && Array.isArray(root.systemTrayPinnedWidgets)) ? root.systemTrayPinnedWidgets : []
        if (pinned.length === 0) return 24
        return 24 + (pinned.length * 26) + (pinned.length * 2)
    }

    readonly property bool trayOverflowOpened: (typeof trayOverflowPopup !== "undefined" && trayOverflowPopup) ? trayOverflowPopup.opened : false
    property var trayOverflowProxyTargets: []

    onTrayOverflowOpenedChanged: {
        Qt.callLater(root.updateTrayOverflowProxyTargets)
    }

    function updateTrayOverflowProxyTargets() {
        var targets = []
        if (root.trayOverflowOpened && root.dockWindow && root.dockWindow.proxyRepeater) {
            var rep = root.dockWindow.proxyRepeater
            for (var i = 0; i < rep.count; i++) {
                var it = rep.itemAt(i)
                if (it) targets.push(it)
            }
        }
        root.trayOverflowProxyTargets = targets
    }

    function toggleTrayOverflow(anchorItem) {
        if (typeof trayOverflowPopup !== "undefined" && trayOverflowPopup) {
            var chevron = anchorItem || root.systemTrayChevronAnchorItem || root.systemTrayAnchorItem
            root.setSystemTrayAnchor(chevron)
            if (root.systemTrayAnchorX > 0) {
                root.systemTrayChevronAnchorX = root.systemTrayAnchorX
            }
            trayOverflowPopup.mouseHasBeenNear = true
            trayOverflowPopup.opened = !trayOverflowPopup.opened
            console.log("WinDoc: toggleTrayOverflow() called -> opened is now", trayOverflowPopup.opened)
        }
    }

    function handleExternalClick(screenX, screenY, button) {
        var btn = button || Qt.LeftButton
        var isTop = root.dockScreenPosition === "top"
        var activeDock = root.dockWindow
        var dockH = (activeDock && activeDock.contentItem) ? activeDock.height : (root.slotSize + 8)
        var screenH = (activeDock && activeDock.screen) ? activeDock.screen.height : 864
        var dockScreenTop = isTop ? 0 : (screenH - dockH)

        var localX = screenX
        var localY = isTop ? screenY : (screenY - dockScreenTop)

        // 1. Right Widgets (Tray, Desktop button, Clock, etc.)
        if (root.hasRightWidgets) {
            var rBase = root.windowsTaskbarMode && !root.isVertical
                ? (activeDock ? activeDock.width : 1920) - root.rightWidgetsWidth
                : ((root.hasLeftWidgets ? (root.leftWidgetsWidth + root.leftSeparatorSize) : 0) + root.itemsWidth + root.rightSeparatorSize)
            if (localX >= rBase && localX <= rBase + root.rightWidgetsWidth) {
                var relRight = localX - rBase
                for (var i = 0; i < root.rightWidgetsList.length; i++) {
                    var wId = root.rightWidgetsList[i]
                    var wOffset = root.getRightWidgetOffset(i)
                    var wDim = root.getRightWidgetDimension(wId)
                    if (relRight >= wOffset && relRight <= wOffset + wDim) {
                        if (root.isTrayWidget(wId)) {
                            var trayRel = relRight - wOffset
                            if (trayRel < 24) {
                                root.toggleTrayOverflow()
                            } else {
                                var pinned = root.systemTrayPinnedWidgets || []
                                var pIdx = Math.floor((trayRel - 24) / 28)
                                if (pIdx >= 0 && pIdx < pinned.length) {
                                    var pId = pinned[pIdx]
                                    if (btn === Qt.RightButton && pId === "omarchy.audio") {
                                        Util.execDetached("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle")
                                    } else {
                                        root.toggleTrayWidget(pId, null, btn)
                                    }
                                }
                            }
                        } else if (root.isDesktopWidget(wId)) {
                            Util.execDetached("hyprctl dispatch workspace previous")
                        } else {
                            root.activateWidget(wId, null, null, { button: btn })
                        }
                        return true
                    }
                }
            }
        }

        // 2. Left Widgets (Start Menu, Left Clock, etc.)
        if (root.hasLeftWidgets) {
            for (var j = 0; j < root.leftWidgetsList.length; j++) {
                var lwId = root.leftWidgetsList[j]
                var lwOffset = root.getLeftWidgetOffset(j)
                var lwDim = (root.isClockWidget(lwId) && !root.isVertical) ? root.clockSlotWidth : root.slotSize
                if (localX >= lwOffset && localX <= lwOffset + lwDim) {
                    root.activateWidget(lwId, null, null, { button: btn })
                    return true
                }
            }
        }

        // 3. Applications / Pinned Apps
        var leftMin = root.hasLeftWidgets ? (root.leftWidgetsWidth + root.leftSeparatorSize) : 0
        var appOffset = leftMin
        if (root.windowsTaskbarMode && !root.isVertical) {
            if (root.taskbarAppAlignment === "left") {
                appOffset = leftMin
            } else if (root.taskbarAppAlignment === "right") {
                appOffset = Math.max(leftMin, (activeDock ? activeDock.width : 1920) - root.rightWidgetsWidth - root.rightSeparatorSize - root.itemsWidth)
            } else {
                appOffset = Math.max(leftMin, ((activeDock ? activeDock.width : 1920) - root.itemsWidth) / 2)
            }
        }

        if (localX >= appOffset && localX < appOffset + root.itemsWidth) {
            var slot = Math.floor((localX - appOffset) / root.slotSize)
            if (slot >= 0 && slot < root.dockItems.length) {
                var item = root.dockItems[slot]
                if (item) {
                    if (btn === Qt.RightButton) {
                        root.minimizeItem(item)
                    } else if (item.isStack) {
                        root.toggleStack(item, slot)
                    } else {
                        root.restoreOrLaunchItem(item, -1)
                    }
                    return true
                }
            }
        }

        return false
    }

    function setSystemTrayAnchor(anchorItem) {
        if (!anchorItem) return
        var activeDock = root.dockWindow
        var win = anchorItem.QsWindow ? anchorItem.QsWindow.window : activeDock
        var dockH = (activeDock && activeDock.contentItem) ? activeDock.height : (root.slotSize + 8)
        var screenH = (activeDock && activeDock.screen) ? activeDock.screen.height : 864
        var isTop = root.dockScreenPosition === "top"
        var dockScreenTop = isTop ? 0 : (screenH - dockH)

        var screenX = 0
        var screenY = 0
        var itemW = anchorItem.width || 24
        var itemH = anchorItem.height || 24
        var isInsideOverflow = (win && win.namespace === "omarchy-dock-tray-overflow") || (anchorItem && anchorItem.slotScreenX !== undefined)

        if (anchorItem && anchorItem.slotScreenX !== undefined && anchorItem.slotScreenY !== undefined) {
            screenX = anchorItem.slotScreenX
            screenY = anchorItem.slotScreenY
            isInsideOverflow = true
        } else if (isInsideOverflow) {
            var pt = anchorItem.mapToItem(win.contentItem, 0, 0)
            screenX = pt.x
            screenY = pt.y
        } else if (win && win.contentItem) {
            var pt = win.contentItem.mapFromItem(anchorItem, 0, 0)
            screenX = pt.x
            screenY = dockScreenTop + pt.y
        }

        root.systemTrayAnchorX = screenX + itemW / 2
        root.systemTrayAnchorY = screenY

        if (!isInsideOverflow && (anchorItem === root.systemTrayChevronAnchorItem || (root.systemTrayChevronAnchorItem && anchorItem === root.systemTrayChevronAnchorItem))) {
            root.systemTrayChevronAnchorX = screenX + itemW / 2
        }

        if (isInsideOverflow) {
            // Relative standard spacing for items inside the overflow popup:
            // Aligns with itemTooltip (anchors.bottom: parent.top; margin: 6).
            var targetBaselineY = isTop ? (screenY + itemH + 6) : (screenY - 6)
            root.currentTrayAnchorGap = isTop ? (targetBaselineY - dockH) : (dockScreenTop - targetBaselineY)
            root.currentTrayAnchorMargin = isTop
                ? (targetBaselineY - (screenY + itemH))
                : (screenY - targetBaselineY)

            if (activeDock && activeDock.dynamicTrayAnchorProxy) {
                var proxy = activeDock.dynamicTrayAnchorProxy
                proxy.x = screenX
                proxy.y = isTop ? screenY : (screenY - dockScreenTop)
                proxy.width = itemW
                proxy.height = itemH
                root.systemTrayAnchorItem = proxy
            } else {
                root.systemTrayAnchorItem = anchorItem
            }
        } else {
            root.currentTrayAnchorGap = isTop ? (root.systemTrayPopupAnchorY - dockH) : -root.systemTrayPopupAnchorY
            var targetBaselineY = dockScreenTop + root.systemTrayPopupAnchorY
            root.currentTrayAnchorMargin = isTop
                ? (targetBaselineY - (screenY + itemH))
                : (screenY - targetBaselineY)
            root.systemTrayAnchorItem = anchorItem
        }
    }

    function closeActiveTrayPanel() {
        var item = systemTrayPanelLoader.item
        if (!item) return
        if (typeof item.close === "function") item.close()
        else if (item.panel && typeof item.panel.close === "function") item.panel.close()
    }

    function toggleTrayWidget(widgetId, anchorItem, button) {
        if (widgetId === "io.github.rawritude.floating-mode") {
            if (button === Qt.RightButton) {
                root.setSystemTrayAnchor(anchorItem || root.systemTrayAnchorItem)
                root.pendingFloatingSettings = true
                floatingModeTrayLoader.active = true
                floatingModeTrayLoader.source = root.getWidgetSource(widgetId)
                if (floatingModeTrayLoader.item) {
                    root.configureHostedWidget(floatingModeTrayLoader.item, widgetId, root.systemTrayAnchorItem, true)
                    floatingModeTrayLoader.item.settingsOpen = true
                    root.pendingFloatingSettings = false
                }
                return true
            }
            Util.execDetached(Quickshell.env("HOME") + "/.config/omarchy/plugins/io.github.rawritude.floating-mode/bin/floating-mode toggle")
            return true
        }
        if (!widgetId || widgetId === "tray.settings") return false
        var anchor = anchorItem || root.systemTrayAnchorItem
        if (anchor) root.setSystemTrayAnchor(anchor)
        if (root.activeTrayPanelId === widgetId && systemTrayPanelLoader.item) {
            root.activateWidget(widgetId, systemTrayPanelLoader.item, anchor, { button: button || Qt.LeftButton }, true)
            return true
        }
        root.closeActiveTrayPanel()
        root.activeTrayPanelId = ""
        root.pendingTrayPanelId = widgetId
        var comp = root.getWidgetComponent(widgetId)
        if (comp) {
            systemTrayPanelLoader.source = ""
            systemTrayPanelLoader.sourceComponent = comp
        } else {
            systemTrayPanelLoader.sourceComponent = null
            systemTrayPanelLoader.source = root.getWidgetSource(widgetId)
        }
        systemTrayPanelLoader.active = true
        return true
    }

    function activatePendingTrayPanel() {
        var item = systemTrayPanelLoader.item
        var widgetId = root.pendingTrayPanelId
        if (!item || !widgetId) return
        root.activeTrayPanelId = widgetId
        root.pendingTrayPanelId = ""
        root.activateWidget(widgetId, item, root.systemTrayAnchorItem, { button: Qt.LeftButton }, true)
    }

    function toggleSystemTrayPin(widgetId) {
        if (!widgetId || root.allSystemTrayWidgetIds.indexOf(widgetId) === -1) return
        var current = (root.systemTrayPinnedWidgets || []).slice()
        var idx = current.indexOf(widgetId)
        if (idx !== -1) {
            current.splice(idx, 1)
        } else {
            current.push(widgetId)
        }
        root.systemTrayPinnedWidgets = current
        root.saveSettings()
    }

    function openSystemTraySettings() {
        root.closeActiveTrayPanel()
        if (typeof systemTraySettingsModal !== "undefined" && systemTraySettingsModal) {
            systemTraySettingsModal.opened = true
        }
    }

    readonly property var rightWidgetsList: {
        var rawWidgets = (widgetLayout.rightWidgets || []).slice()
        var widgets = []
        var trayManaged = (root.windowsTaskbarMode && root.systemTrayEnabled) ? root.allSystemTrayWidgetIds : []
        for (var i = 0; i < rawWidgets.length; i++) {
            var wid = rawWidgets[i]
            if (trayManaged.indexOf(wid) === -1 && wid !== "taskbar.clock" && wid !== "taskbar.tray" && wid !== "taskbar.desktop") {
                widgets.push(wid)
            }
        }
        if (root.windowsTaskbarMode && !root.isVertical) {
            if (root.systemTrayEnabled && widgets.indexOf("taskbar.tray") === -1) {
                widgets.push("taskbar.tray")
            }
            if (widgets.indexOf("taskbar.clock") === -1) {
                widgets.push("taskbar.clock")
            }
            if (root.showDesktopButtonEnabled && widgets.indexOf("taskbar.desktop") === -1) {
                widgets.push("taskbar.desktop")
            }
        }
        return widgets
    }
    readonly property bool hasLeftWidgets: leftWidgetsList.length > 0
    readonly property bool hasRightWidgets: rightWidgetsList.length > 0
    readonly property bool hasWidgets: hasLeftWidgets || hasRightWidgets

    function isClockWidget(widgetId) {
        return widgetId === "omarchy.clock" || widgetId === "taskbar.clock"
    }

    readonly property bool hasClockOnLeft: hasLeftWidgets && (leftWidgetsList.indexOf("omarchy.clock") !== -1 || leftWidgetsList.indexOf("taskbar.clock") !== -1)
    readonly property bool hasClockOnRight: hasRightWidgets && (rightWidgetsList.indexOf("omarchy.clock") !== -1 || rightWidgetsList.indexOf("taskbar.clock") !== -1)
    readonly property bool hasClockWidget: hasClockOnLeft || hasClockOnRight

    property string clockDisplayText: ""

    TextMetrics {
        id: clockMetrics
        font.family: Style.font.family
        font.pixelSize: 12
        font.weight: Font.Medium
        text: root.clockDisplayText !== "" ? root.clockDisplayText : root.currentMinuteString
    }

    readonly property real clockSlotWidth: (hasClockWidget && !root.isVertical)
        ? Math.max(root.slotSize, clockMetrics.advanceWidth + 24)
        : root.slotSize

    function getRightWidgetDimension(id) {
        if (!root.isVertical) {
            if (root.isClockWidget(id)) return root.clockSlotWidth
            if (root.isTrayWidget(id)) return root.traySlotWidth
            if (root.isDesktopWidget(id)) return root.desktopSlotWidth
        }
        return root.slotSize
    }

    function getLeftWidgetOffset(index) {
        var offset = 0
        for (var i = 0; i < index; i++) {
            var id = root.leftWidgetsList[i]
            var dim = (root.isClockWidget(id) && !root.isVertical) ? root.clockSlotWidth : root.slotSize
            offset += dim
        }
        return offset
    }

    function getRightWidgetOffset(index) {
        var offset = 0
        for (var i = 0; i < index; i++) {
            var id = root.rightWidgetsList[i]
            offset += root.getRightWidgetDimension(id)
        }
        return offset
    }

    readonly property real leftWidgetsWidth: {
        if (!hasLeftWidgets) return 0
        var total = 0
        for (var i = 0; i < leftWidgetsList.length; i++) {
            var id = leftWidgetsList[i]
            total += (root.isClockWidget(id) && !root.isVertical) ? root.clockSlotWidth : root.slotSize
        }
        return total
    }

    readonly property real rightWidgetsWidth: {
        if (!hasRightWidgets) return 0
        var total = 0
        for (var i = 0; i < rightWidgetsList.length; i++) {
            var id = rightWidgetsList[i]
            total += root.getRightWidgetDimension(id)
        }
        return total
    }

    readonly property real leftSeparatorSize: hasLeftWidgets ? 8 : 0
    readonly property real rightSeparatorSize: hasRightWidgets ? 8 : 0
    readonly property real itemsWidth: (root.dockItems.length * root.slotSize)

    // Dynamic max items limit for dock bar based on logical screen dimensions & scale (15 items on 1080p @ 1.6x, scales dynamically for Ultrawide 21:9 / 32:9)
    readonly property var activeScreen: {
        var focused = root.screenForMonitor(Hyprland.focusedMonitor)
        if (focused) return focused
        return (Quickshell.screens && Quickshell.screens.length > 0) ? Quickshell.screens[0] : null
    }
    readonly property real logicalScreenWidth: (activeScreen && activeScreen.width > 0) ? activeScreen.width : 1200
    readonly property real logicalScreenHeight: (activeScreen && activeScreen.height > 0) ? activeScreen.height : 675
    readonly property int maxDockItems: {
        if (root.isVertical) {
            // Vertical: limit by screen height minus widget slots
            var usedV = (hasLeftWidgets ? (leftWidgetsWidth + leftSeparatorSize) : 0)
                      + (hasRightWidgets ? (rightSeparatorSize + rightWidgetsWidth) : 0)
            var availableH = Math.max(0, logicalScreenHeight - usedV)
            return Math.max(3, Math.floor(availableH / root.slotSize))
        } else {
            // Horizontal: limit by screen width minus widget slots
            var usedH = (hasLeftWidgets ? (leftWidgetsWidth + leftSeparatorSize) : 0)
                      + (hasRightWidgets ? (rightSeparatorSize + rightWidgetsWidth) : 0)
            var availableW = Math.max(0, logicalScreenWidth - usedH)
            return Math.max(3, Math.floor(availableW / root.slotSize))
        }
    }

    readonly property real totalDockDimension: Math.max(root.slotSize,
        (hasLeftWidgets ? (leftWidgetsWidth + leftSeparatorSize) : 0) +
        itemsWidth +
        (hasRightWidgets ? (rightSeparatorSize + rightWidgetsWidth) : 0))

    onDockEnabledChanged: {
        if (!dockEnabled) {
            root.activeStackItem = null
            root.activeMenuItem = null
            root.isEditMode = false
        }
    }

    property bool isSavingSettings: false

    FileView {
        id: settingsFile
        path: root.settingsPath
        watchChanges: true
        atomicWrites: true
        printErrors: false
        onLoaded: root.readSettings()
        onFileChanged: {
            if (!root.isSavingSettings) {
                reload()
                root.readSettings()
            }
        }
    }

    Timer {
        id: saveSettingsTimer
        interval: 300
        repeat: false
        onTriggered: root.isSavingSettings = false
    }

    function readSettings() {
        if (root.isSavingSettings) return
        try {
            var txt = settingsFile.text()
            if (txt && txt.trim().length > 0) {
                var s = JSON.parse(txt)
                if (!s || typeof s !== "object") return
                var normalized = DockSettings.normalize(s)
                root.visibilityMode = normalized.visibilityMode
                if (s.preferredVisibilityMode !== undefined) {
                    var pvm = String(s.preferredVisibilityMode).trim().toLowerCase()
                    if (pvm === "hover" || pvm === "keybind") root.preferredVisibilityMode = pvm
                } else if (normalized.visibilityMode === "hover" || normalized.visibilityMode === "keybind") {
                    root.preferredVisibilityMode = normalized.visibilityMode
                }
                root.overlayMode = normalized.overlayMode
                root.visibleWorkspace = normalized.visibleWorkspace
                if (s.windowsTaskbarMode !== undefined) {
                    root.windowsTaskbarMode = (s.windowsTaskbarMode === true)
                }
                if (s.taskbarAppAlignment !== undefined) {
                    var alignment = String(s.taskbarAppAlignment).trim().toLowerCase()
                    if (["left", "center", "right"].indexOf(alignment) !== -1) {
                        root.taskbarAppAlignment = alignment
                    }
                }
                if (s.dockEnabled !== undefined) {
                    root.dockEnabled = (s.dockEnabled === true || s.dockEnabled === "true" || s.dockEnabled === 1 || s.dockEnabled === "1")
                } else {
                    root.dockEnabled = true
                }
                if (s.autohideEdgeDepth !== undefined) {
                    var depth = parseInt(s.autohideEdgeDepth, 10)
                    if (!isNaN(depth) && depth >= 1 && depth <= 64) root.autohideEdgeDepth = depth
                }
                root.showFolderTitles = true
                if (s.showBadges !== undefined) {
                    root.showBadges = (s.showBadges === true)
                }
                if (s.glassmorphism !== undefined) {
                    root.glassmorphism = (s.glassmorphism === true)
                }
                if (s.blurOpacity !== undefined) {
                    var bo = Number(s.blurOpacity)
                    if (isFinite(bo) && bo >= 0.1 && bo <= 1.0) root.blurOpacity = bo
                }
                if (s.appMenuPosition !== undefined) {
                    root.appMenuPosition = s.appMenuPosition
                }
                if (s.widgetPosition !== undefined) {
                    root.widgetPosition = s.widgetPosition
                }
                if (s.widgetsEnabled !== undefined) {
                    root.widgetsEnabled = (s.widgetsEnabled === true)
                }
                if (s.dockWidgets !== undefined && Array.isArray(s.dockWidgets)) {
                    if (!root.widgetsEnabled) {
                        root.dockWidgets = []
                    } else {
                        var newDockWidgets = s.dockWidgets.slice()
                        var oldDockWidgets = Array.isArray(root.dockWidgets) ? root.dockWidgets.slice() : []
                        var removedWidgets = []
                        for (var owi = 0; owi < oldDockWidgets.length; owi++) {
                            var ow = oldDockWidgets[owi]
                            if (ow && ow !== "omarchy.apps" && newDockWidgets.indexOf(ow) === -1) {
                                removedWidgets.push(ow)
                            }
                        }
                        if (removedWidgets.length > 0 && !root.windowsTaskbarMode) {
                            root.widgetSavedPositions = DockModel.switchDockWidgetInBar(root.shell, "", removedWidgets, root.widgetSavedPositions || {}, shellConfigFile)
                        }
                        for (var nwi = 0; nwi < newDockWidgets.length; nwi++) {
                            var nw = newDockWidgets[nwi]
                            if (nw && nw !== "omarchy.apps" && !root.windowsTaskbarMode) {
                                root.widgetSavedPositions = DockModel.switchDockWidgetInBar(root.shell, nw, [], root.widgetSavedPositions || {}, shellConfigFile)
                            }
                        }
                        root.dockWidgets = newDockWidgets
                    }
                } else if (root.widgetsEnabled) {
                    root.dockWidgets = ["omarchy.apps"]
                }
                if (s.systemTray !== undefined && typeof s.systemTray === "object") {
                    if (s.systemTray.enabled !== undefined) root.systemTrayEnabled = (s.systemTray.enabled === true)
                    if (s.systemTray.pinnedWidgets !== undefined && Array.isArray(s.systemTray.pinnedWidgets)) {
                        var rawPinned = s.systemTray.pinnedWidgets.slice()
                        var validPinned = []
                        var seenPinned = {}
                        for (var p = 0; p < rawPinned.length; p++) {
                            var pid = rawPinned[p]
                            if (pid && root.allSystemTrayWidgetIds.indexOf(pid) !== -1 && !seenPinned[pid]) {
                                seenPinned[pid] = true
                                validPinned.push(pid)
                            }
                        }
                        root.systemTrayPinnedWidgets = validPinned
                    }
                    if (s.systemTray.showDesktopButton !== undefined) {
                        root.showDesktopButtonEnabled = (s.systemTray.showDesktopButton === true)
                    }
                }
                if (s.widgetSavedPositions !== undefined && typeof s.widgetSavedPositions === "object") {
                    root.widgetSavedPositions = s.widgetSavedPositions
                }
            }
        } catch(e) {}
    }

    function saveSettings() {
        root.isSavingSettings = true
        saveSettingsTimer.restart()
        var jsonStr = JSON.stringify({
            dockEnabled: root.dockEnabled,
            visibilityMode: root.visibilityMode,
            preferredVisibilityMode: root.preferredVisibilityMode,
            autohide: DockSettings.legacyAutohide(root.visibilityMode),
            overlayMode: root.overlayMode,
            visibleWorkspace: root.visibleWorkspace,
            autohideEdgeDepth: root.autohideEdgeDepth,
            showFolderTitles: root.showFolderTitles,
            showBadges: root.showBadges,
            glassmorphism: root.glassmorphism,
            blurOpacity: root.blurOpacity,
            windowsTaskbarMode: root.windowsTaskbarMode,
            taskbarAppAlignment: root.taskbarAppAlignment,
            widgetsEnabled: root.widgetsEnabled,
            appMenuPosition: root.appMenuPosition || "left",
            widgetPosition: root.widgetPosition || "right",
            dockWidgets: (root.widgetsEnabled && root.dockWidgets) ? root.dockWidgets.slice() : [],
            systemTray: {
                enabled: root.systemTrayEnabled,
                pinnedWidgets: root.systemTrayPinnedWidgets || ["omarchy.network", "omarchy.audio"],
                showDesktopButton: root.showDesktopButtonEnabled
            },
            widgetSavedPositions: root.widgetSavedPositions || {}
        }, null, 2)
        settingsFile.setText(jsonStr + "\n")
    }

    function setDockEnabled(val) {
        root.dockEnabled = (val === true || val === "true" || val === 1 || val === "1")
        saveSettings()
    }

    function setAutohide(val) {
        if (val) {
            if (!root.dockEnabled) {
                root.dockEnabled = true
            }
            root.visibilityMode = root.preferredVisibilityMode || "hover"
        } else {
            if (root.visibilityMode === "hover" || root.visibilityMode === "keybind") {
                root.preferredVisibilityMode = root.visibilityMode
            }
            root.visibilityMode = "always"
        }
        saveSettings()
    }

    function setVisibilityMode(mode) {
        var norm = DockSettings.normalizeVisibilityMode(mode, false)
        if (norm === "hover" || norm === "keybind") {
            root.preferredVisibilityMode = norm
        }
        root.visibilityMode = norm
        saveSettings()
    }

    function setVisibleWorkspace(workspace) {
        root.visibleWorkspace = DockSettings.normalizeVisibleWorkspace(workspace)
        saveSettings()
    }

    function setOverlayMode(val) {
        root.overlayMode = (val === true || val === "true")
        root.saveSettings()
    }

    function setShowAppMenu(val) {
        if (val) {
            root.addDockWidget("omarchy.apps")
        } else {
            root.removeDockWidget("omarchy.apps", "")
        }
    }

    function setWidgetsEnabled(val) {
        root.widgetsEnabled = val
        saveSettings()
    }

    function setAppMenuPosition(pos) {
        root.appMenuPosition = (pos === "right") ? "right" : "left"
        saveSettings()
    }

    function setWidgetPosition(pos) {
        root.widgetPosition = (pos === "left") ? "left" : "right"
        saveSettings()
    }

    function addDockWidget(widgetId) {
        root.widgetsEnabled = true
        var currentSaved = JSON.parse(JSON.stringify(root.widgetSavedPositions || {}))

        if (widgetId !== "omarchy.apps" && !root.windowsTaskbarMode) {
            var prevIds = []
            if (root.dockWidgets && root.dockWidgets.length > 0) {
                for (var i = 0; i < root.dockWidgets.length; i++) {
                    var prevId = root.dockWidgets[i]
                    if (prevId && prevId !== "omarchy.apps" && prevId !== widgetId) {
                        prevIds.push(prevId)
                    }
                }
            }
            currentSaved = DockModel.switchDockWidgetInBar(root.shell, widgetId, prevIds, currentSaved, shellConfigFile)
        }

        root.dockWidgets = DockModel.addWidgetToDockList(root.dockWidgets, widgetId)
        root.widgetSavedPositions = currentSaved
        saveSettings()
    }

    function removeDockWidget(widgetId, targetRegion) {
        var next = DockModel.removeWidgetFromDockList(root.dockWidgets, widgetId)
        root.dockWidgets = next.slice()
        if (widgetId !== "omarchy.apps" && !root.windowsTaskbarMode) {
            var currentSaved = JSON.parse(JSON.stringify(root.widgetSavedPositions || {}))
            currentSaved = DockModel.switchDockWidgetInBar(root.shell, "", [widgetId], currentSaved, shellConfigFile)
            root.widgetSavedPositions = currentSaved
        }
        saveSettings()
    }

    // Preferred route since Omarchy 4.0.3: the widget-catalogue facade hands out
    // the live Component for anything the host has registered, which is every
    // enabled bar-widget plugin. Returns null when the widget is not registered,
    // leaving getWidgetSource() to cover the hardcoded first-party panels.
    function getWidgetComponent(widgetId) {
        if (!widgetId || widgetId === "omarchy.apps" || root.isClockWidget(widgetId) || widgetId === "omarchy.weather") return null
        if (!root.barWidgetRegistry) return null
        var widgets = root.barWidgetRegistry.widgets || {}
        var entry = widgets[widgetId]
        return entry && entry.component ? entry.component : null
    }

    function getWidgetSource(widgetId) {
        if (!widgetId || widgetId === "omarchy.apps") return ""
        if (root.isClockWidget(widgetId)) {
            return "file:///usr/share/omarchy/shell/plugins/panels/clock/Panel.qml"
        }
        if (widgetId === "omarchy.weather") {
            return "file:///usr/share/omarchy/shell/plugins/panels/weather/Panel.qml"
        }
        if (widgetId === "brunoma.agents") {
            return "file://" + Quickshell.env("HOME") + "/.config/omarchy/plugins/brunoma.agents/Panel.qml"
        }
        if (widgetId === "io.github.rawritude.floating-mode") {
            return "file://" + Quickshell.env("HOME") + "/.config/omarchy/plugins/io.github.rawritude.floating-mode/BarWidget.qml"
        }
        var manifest = (root.shell && root.shell.pluginRegistry && root.shell.pluginRegistry.installedPlugins) ? root.shell.pluginRegistry.installedPlugins[widgetId] : null
        if (manifest && root.shell && root.shell.pluginRegistry) {
            var ep = root.shell.pluginRegistry.entryPointUrl(manifest, "barWidget")
            if (ep && ep.length > 0) return ep
        }
        var parts = widgetId.split(".")
        var name = parts.length > 1 ? parts[1] : parts[0]

        // 1. Built-in bar widgets in plugins/bar/widgets/
        if (name === "indicators") return "file:///usr/share/omarchy/shell/plugins/bar/widgets/Indicators.qml"
        if (name === "keyboard-layout") return "file:///usr/share/omarchy/shell/plugins/bar/widgets/KeyboardLayout.qml"
        if (name === "microphone") return "file:///usr/share/omarchy/shell/plugins/bar/widgets/Microphone.qml"

        // 2. Services bar widgets
        if (name === "media") return "file:///usr/share/omarchy/shell/plugins/services/media/BarWidget.qml"

        // 3. Root plugin bar widgets / panels
        if (name === "agents") return "file:///usr/share/omarchy/shell/plugins/agents/Panel.qml"
        if (name === "menu") return "file:///usr/share/omarchy/shell/plugins/menu/BarWidget.qml"

        // 4. Panel widgets using Panel.qml
        if (name === "clock" || name === "audio" || name === "bluetooth" || name === "network" ||
            name === "power" || name === "monitor" || name === "tailscale" ||
            name === "dropbox" || name === "speedtest" || name === "disk-speedtest" ||
            name === "wifiqr") {
            return "file:///usr/share/omarchy/shell/plugins/panels/" + name + "/Panel.qml"
        }

        // 5. Panel widgets using BarWidget.qml
        if (name === "weather") {
            return "file:///usr/share/omarchy/shell/plugins/panels/" + name + "/BarWidget.qml"
        }

        if (manifest && (!manifest.entryPoints || !manifest.entryPoints.barWidget)) {
            return ""
        }
        return "file:///usr/share/omarchy/shell/plugins/panels/" + name + "/BarWidget.qml"
    }

    function configureHostedWidget(item, widgetId, anchorItem, trayHosted) {
        if (!item) return
        if (root.loadedWidgetItems.indexOf(item) === -1) root.loadedWidgetItems.push(item)
        if ("bar" in item) item.bar = dockBarContext
        if ("shell" in item) item.shell = root.shell
        if ("widgetId" in item) item.widgetId = widgetId
        if ("moduleName" in item) item.moduleName = widgetId

        function applyToPanel(p) {
            if (!p) return
            if ("centerOnBar" in p) {
                p.centerOnBar = false
            }
            if ("bar" in p) {
                p.bar = dockBarContext
            }
            if ("anchorItem" in p) {
                p.anchorItem = anchorItem || (root.dockWindow ? root.dockWindow.contentItem : null)
            }
            if (trayHosted) {
                if ("gap" in p) p.gap = root.currentTrayAnchorGap
                else if ("margin" in p) p.margin = root.currentTrayAnchorMargin
            }
            if ("opened" in p && p.openedChanged) {
                p.openedChanged.connect(function() {
                    root.evaluateHoverState()
                })
            }
            if ("open" in p && p.openChanged) {
                p.openChanged.connect(function() {
                    root.evaluateHoverState()
                })
            }
        }

        function scan(obj, depth) {
            if (!obj || (depth !== undefined && depth > 3)) return
            var d = depth || 0
            applyToPanel(obj)
            if (obj.panel) {
                applyToPanel(obj.panel)
                scan(obj.panel, d + 1)
            }
            if (obj.data) {
                for (var i = 0; i < obj.data.length; i++) {
                    var child = obj.data[i]
                    if (child) {
                        applyToPanel(child)
                        if (child.panel) applyToPanel(child.panel)
                        scan(child, d + 1)
                    }
                }
            }
            if (obj.children) {
                for (var j = 0; j < obj.children.length; j++) {
                    var c = obj.children[j]
                    if (c) {
                        applyToPanel(c)
                        if (c.panel) applyToPanel(c.panel)
                        scan(c, d + 1)
                    }
                }
            }
        }

        scan(item)

        if (item) {
            if ("iconChanged" in item && item.iconChanged && typeof item.iconChanged.connect === "function") {
                item.iconChanged.connect(function() { root.widgetIconRevision++ })
            }
            if ("labelChanged" in item && item.labelChanged && typeof item.labelChanged.connect === "function") {
                item.labelChanged.connect(function() { root.widgetIconRevision++ })
            }
            if ("displayTextChanged" in item && item.displayTextChanged && typeof item.displayTextChanged.connect === "function") {
                item.displayTextChanged.connect(function() { root.widgetIconRevision++ })
            }
            if ("playIconChanged" in item && item.playIconChanged && typeof item.playIconChanged.connect === "function") {
                item.playIconChanged.connect(function() { root.widgetIconRevision++ })
            }
            if ("updateAvailableChanged" in item && item.updateAvailableChanged && typeof item.updateAvailableChanged.connect === "function") {
                item.updateAvailableChanged.connect(function() { root.widgetIconRevision++ })
            }
            if ("activeChanged" in item && item.activeChanged && typeof item.activeChanged.connect === "function") {
                item.activeChanged.connect(function() { root.widgetIconRevision++ })
            }
            if ("mutedChanged" in item && item.mutedChanged && typeof item.mutedChanged.connect === "function") {
                item.mutedChanged.connect(function() { root.widgetIconRevision++ })
            }
        }

        if (item.panelLoader) {
            var handlePanelLoader = function() {
                if (item.panelLoader && item.panelLoader.item) {
                    scan(item.panelLoader.item)
                }
            }
            handlePanelLoader()
            item.panelLoader.loaded.connect(handlePanelLoader)
        }
    }

    // Proxy Bar context for hosted widgets
    QtObject {
        id: dockBarContext
        property bool vertical: root.isVertical
        property int barSize: (root.trayOverflowOpened && trayOverflowPopup && trayOverflowPopup.opened) ? 2000 : (root.slotSize + 8)
        property int barH: root.slotSize + 8
        property int barW: root.slotSize + 8
        property string position: root.dockScreenPosition
        property var screen: (root.dockWindow && root.dockWindow.screen) ? root.dockWindow.screen : null
        property var shell: root.shell
        property color foreground: Color.composed("bar.text", "bar.text-alpha", Color.text, 0.9)
        property color barForeground: Color.composed("bar.text", "bar.text-alpha", Color.text, 0.9)
        property color urgent: Color.urgent
        property color muted: Color.muted
        property color accent: Color.accent
        property bool foregroundAnimationEnabled: true
        property string fontFamily: Style.font.family
        property var activePopout: null
        property var clickTargets: (root.trayOverflowOpened && trayOverflowPopup && trayOverflowPopup.opened) ? root.trayOverflowProxyTargets : []
        function targetBelongsToWindow(target, win) { return true }
        function showTooltip(item, text) {}
        function hideTooltip(item) {}
        function requestPopout(key) {
            if (activePopout === key) return
            if (activePopout) {
                if ("closeForPopoutSwitch" in activePopout) activePopout.closeForPopoutSwitch()
                else if ("close" in activePopout) activePopout.close()
            }
            activePopout = key
        }
        function releasePopout(key) { if (activePopout === key) activePopout = null }
        function isBarWidgetOpen(id) { return false }
        function switchPanelFrom(panel, dir) { return false }
        function run(cmd) { Util.execDetached(cmd) }
    }

    // Reactive tracking for hardware and system states
    property int widgetIconRevision: 0

    PwObjectTracker {
        objects: [Pipewire.defaultAudioSink, Pipewire.defaultAudioSource]
    }

    readonly property var pipewireDefaultSinkAudio: (Pipewire.defaultAudioSink && Pipewire.defaultAudioSink.audio) ? Pipewire.defaultAudioSink.audio : null
    readonly property real pipewireSinkVolume: pipewireDefaultSinkAudio ? pipewireDefaultSinkAudio.volume : 1.0
    readonly property bool pipewireSinkMuted: pipewireDefaultSinkAudio ? pipewireDefaultSinkAudio.muted : false

    readonly property var pipewireDefaultSourceAudio: (Pipewire.defaultAudioSource && Pipewire.defaultAudioSource.audio) ? Pipewire.defaultAudioSource.audio : null
    readonly property bool pipewireSourceMuted: pipewireDefaultSourceAudio ? pipewireDefaultSourceAudio.muted : true

    readonly property var upowerDisplayDev: UPower.displayDevice
    readonly property real upowerBatteryPercentage: (upowerDisplayDev && upowerDisplayDev.isPresent) ? upowerDisplayDev.percentage : 100.0
    readonly property int upowerBatteryState: (upowerDisplayDev && upowerDisplayDev.isPresent) ? upowerDisplayDev.state : 0
    readonly property bool upowerBatteryPresent: (upowerDisplayDev && upowerDisplayDev.isPresent) ? true : false

    readonly property int screenCount: Quickshell.screens ? Quickshell.screens.length : 1

    function getWidgetIcon(widgetId, item) {
        var _rev = root.widgetIconRevision
        if (!widgetId) return "󰒓"
        if (widgetId === "omarchy.apps") return "󰀻"
        if (widgetId === "omarchy.monitor") {
            return (root.screenCount > 1) ? "󰍺" : "󰍹"
        }
        if (widgetId === "omarchy.clock") return "󰥔"
        if (widgetId === "omarchy.tailscale") {
            if (item && item.icon) return item.icon
            return "󰖂"
        }
        if (widgetId === "omarchy.network") {
            if (item && item.icon) return item.icon
            return "󰖩"
        }
        if (widgetId === "omarchy.bluetooth") {
            if (item && item.icon) return item.icon
            return "󰂯"
        }
        if (widgetId === "omarchy.weather") {
            if (item && item.label && item.label !== "") return item.label
            if (item && item.icon) return item.icon
            return "󰖐"
        }
        if (widgetId === "omarchy.system-update") return "󰚰"
        if (widgetId === "omarchy.microphone") {
            if (item && item.muted !== undefined) return item.muted ? "󰍭" : "󰍬"
            return root.pipewireSourceMuted ? "󰍭" : "󰍬"
        }
        if (widgetId === "omarchy.media") {
            if (item && item.playIcon) return item.playIcon
            return "󰐊"
        }
        if (widgetId === "omarchy.keyboard-layout" || widgetId === "nomarkoo.keyboard-layout" || widgetId === "glafeara.languages") {
            if (item && item.icon) return item.icon
            if (item && item.displayText) return item.displayText
            return "󰌌"
        }
        if (widgetId === "omarchy.tray") return "󰇙"
        if (widgetId === "omarchy.agents" || widgetId === "brunoma.agents") return "󰚩"
        if (widgetId === "io.github.rawritude.floating-mode") {
            if (item && item.floatingMode !== undefined) return item.floatingMode ? "󰖲" : "󰍹"
            return "󰍹"
        }
        if (widgetId === "omarchy.indicators") return "󰂚"
        if (widgetId === "silvaio.gamemode") return "󰊴"
        if (widgetId === "lgse.sandman") return "󰒲"
        if (widgetId === "omarchy.clipboard") return "󰅌"
        if (widgetId === "omarchy.emojis") return "󰞅"
        if (widgetId === "omarchy.reminders") return "󰔢"
        if (widgetId === "omarchy.speedtest") return "󰓅"
        if (widgetId === "omarchy.disk-speedtest") return "󰋊"
        if (widgetId === "omarchy.dropbox") return "󰇣"
        if (widgetId === "omarchy.wifiqr") return "󰒍"
        if (widgetId === "icons") return "󰀻"
        if (widgetId === "omaplug") return "󰏖"
        if (widgetId === "omarchy.audio") {
            if (item && typeof item.outputIcon === "function") {
                try {
                    var out = item.outputIcon()
                    if (out) return out
                } catch(e) {}
            }
            if (root.pipewireSinkMuted || root.pipewireSinkVolume <= 0.01) return "󰝟"
            if (root.pipewireSinkVolume < 0.33) return "󰕿"
            if (root.pipewireSinkVolume < 0.66) return "󰖀"
            return "󰕾"
        }
        if (widgetId === "omarchy.power") {
            if (item && typeof item.batteryIcon === "function") {
                try {
                    var bIcon = item.batteryIcon()
                    if (bIcon) return bIcon
                } catch(e) {}
            }
            if (!root.upowerBatteryPresent) return "󰚥"
            if (root.upowerBatteryState === UPowerDeviceState.Charging) return "󰂄"
            var frac = root.upowerBatteryPercentage / 100.0
            if (frac < 0.15) return "󰁺"
            if (frac < 0.30) return "󰁻"
            if (frac < 0.50) return "󰁽"
            if (frac < 0.70) return "󰁾"
            if (frac < 0.90) return "󰁿"
            return "󰁹"
        }
        if (item) {
            if (item.icon) return item.icon
            if (item.text) return item.text
            if (item.glyph) return item.glyph
            if (item.displayText) return item.displayText
        }
        var manifest = (root.shell && root.shell.pluginRegistry && root.shell.pluginRegistry.installedPlugins) ? root.shell.pluginRegistry.installedPlugins[widgetId] : null
        if (manifest) {
            if (manifest.icon) return manifest.icon
            if (manifest.barWidget && manifest.barWidget.icon) return manifest.barWidget.icon
        }
        return "󰒓"
    }

    function handleWidgetSlotClick(widgetId, mouse) {
        if (root.isEditMode) {
            if (mouse && mouse.button === Qt.RightButton) {
                root.isEditMode = false
            }
            return
        }
        if (widgetId === "omarchy.apps") {
            if (mouse && mouse.button === Qt.RightButton) {
                Util.execDetached("omarchy-menu toggle root")
            } else {
                Util.execDetached("omarchy-menu toggle apps")
            }
            return
        }
        if (root.isClockWidget(widgetId)) {
            if (mouse && (mouse.button === Qt.RightButton || mouse.button === Qt.MiddleButton)) {
                Util.execDetached("omarchy-menu-timezone")
                return
            }
            calendarPopup.refresh()
            calendarPopup.opened = !calendarPopup.opened
            return
        }
        if (widgetId === "omarchy.microphone") {
            if (mouse && mouse.button === Qt.MiddleButton) {
                Util.execDetached("omarchy-shell shell toggle omarchy.audio")
                return
            }
            if (mouse && mouse.button === Qt.LeftButton) {
                if (root.pipewireDefaultSourceAudio) {
                    root.pipewireDefaultSourceAudio.muted = !root.pipewireDefaultSourceAudio.muted
                } else {
                    Util.execDetached("wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle")
                }
                return
            }
        }
        if (widgetId === "omarchy.keyboard-layout") {
            Util.execDetached("hyprctl switchxkblayout all next")
            return
        }
        if (widgetId === "omarchy.system-update") {
            Util.execDetached("omarchy-launch-floating-terminal-with-presentation omarchy-update")
            return
        }

        // Reliable toggle for all other plugins and overlays:
        Util.execDetached("omarchy-shell shell toggle " + widgetId)
    }

    function activateWidget(widgetId, target, slotRoot, mouse, trayHosted) {
        if (root.isEditMode) {
            if (mouse && mouse.button === Qt.RightButton) {
                root.isEditMode = false
            }
            return
        }
        if (widgetId === "omarchy.apps") {
            if (mouse && mouse.button === Qt.RightButton) {
                Util.execDetached("omarchy-menu toggle root")
            } else {
                Util.execDetached("omarchy-menu toggle apps")
            }
            return
        }
        if (widgetId === "omarchy.system-update") {
            Util.execDetached("omarchy-launch-floating-terminal-with-presentation omarchy-update")
            return
        }
        if (root.isClockWidget(widgetId)) {
            if (mouse && (mouse.button === Qt.RightButton || mouse.button === Qt.MiddleButton)) {
                Util.execDetached("omarchy-menu-timezone")
                return
            }
            calendarPopup.refresh()
            calendarPopup.opened = !calendarPopup.opened
            return
        }

        if (target) {
            root.configureHostedWidget(target, widgetId, slotRoot, trayHosted === true)
            if (mouse && mouse.button === Qt.RightButton) {
                if (widgetId === "omarchy.weather") {
                    Util.execDetached("omarchy-notification-send \"$(omarchy-weather-status)\"")
                    return
                } else if (typeof target.cycleFormat === "function") {
                    target.cycleFormat()
                    return
                } else if (typeof target.toggleAllMuted === "function") {
                    target.toggleAllMuted()
                    return
                } else if (typeof target.toggleBluetooth === "function") {
                    target.toggleBluetooth()
                    return
                }
            } else if (mouse && mouse.button === Qt.MiddleButton) {
                if (widgetId === "omarchy.weather") {
                    if (target && typeof target.refresh === "function") target.refresh()
                    return
                } else if (widgetId === "omarchy.microphone") {
                    Util.execDetached("omarchy-shell shell toggle omarchy.audio")
                    return
                } else if (target.bar && typeof target.bar.run === "function") {
                    target.bar.run("omarchy-menu-timezone")
                    return
                } else {
                    Util.execDetached("omarchy-menu-timezone")
                    return
                }
            } else {
                // Left click handling
                if (typeof target.cycleLayout === "function") {
                    target.cycleLayout()
                    return
                } else if (typeof target.runUpdate === "function") {
                    target.runUpdate()
                    return
                } else if (typeof target.toggleMute === "function") {
                    target.toggleMute()
                    return
                } else if (typeof target.togglePanel === "function") {
                    target.togglePanel()
                    return
                } else if (typeof target.toggle === "function") {
                    target.toggle()
                    return
                } else if (target.panel && typeof target.panel.toggle === "function") {
                    target.panel.toggle()
                    return
                } else if (typeof target.open === "function") {
                    if (target.opened) target.close()
                    else target.open()
                    return
                } else if (target.panel && typeof target.panel.open === "function") {
                    if (target.panel.opened) target.panel.close()
                    else target.panel.open()
                    return
                } else if ("opened" in target) {
                    target.opened = !target.opened
                    return
                }
            }
        }

        root.handleWidgetSlotClick(widgetId, mouse)
    }

    Connections {
        target: root.pluginRegistry || (shell && shell.pluginRegistry) || null
        ignoreUnknownSignals: true
        function onPluginsChanged() { root.updatePluginEnabled() }
    }

    // Safe compositor unmap-remap sequence on orientation shift
    Timer {
        id: remapTimer
        interval: 100
        repeat: false
        // The remap builds fresh surfaces whose HoverHandlers start out
        // unhovered and therefore emit no onHoveredChanged. Re-derive the
        // hover state by hand, or a dock that was hovered before the remap
        // would stay revealed with nothing left to ever clear the flag.
        onTriggered: root.evaluateHoverState()
    }

    property string lastRemapBarPosition: ""
    onBarPositionChanged: {
        if (root.lastRemapBarPosition !== root.barPosition) {
            root.lastRemapBarPosition = root.barPosition
            // Drop the sticky hover flag before the surfaces are rebuilt: the
            // pointer cannot be over a dock that does not exist yet, and the
            // edge trigger re-reveals the dock the moment it really is.
            root.isDockHovered = false
            remapTimer.restart()
        }
    }

    // Periodic sync timer for guaranteed real-time layer alignment
    Timer {
        id: syncPollTimer
        interval: 15000
        repeat: true
        running: true
        onTriggered: {
            root.refreshLayers()
            root.refreshHyprlandOptions()
        }
    }

    // Real-time Bar Position detection via Hyprland layer shell
    Process {
        id: layersProc
        running: true
        command: ["hyprctl", "layers", "-j"]
        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                try {
                    var data = JSON.parse(text)
                    for (var mon in data) {
                        var levels = data[mon].levels || {}
                        for (var lvl in levels) {
                            var layers = levels[lvl] || []
                            for (var i = 0; i < layers.length; i++) {
                                var l = layers[i]
                                if (l.namespace === "omarchy-bar") {
                                    var newPos = (l.w < l.h) ? (l.x === 0 ? "left" : "right") : (l.y === 0 ? "top" : "bottom")
                                    if (root.detectedBarPosition !== newPos) {
                                        root.detectedBarPosition = newPos
                                    }
                                    return
                                }
                            }
                        }
                    }
                } catch(e) {}
            }
        }
    }

    function refreshLayers() {
        if (!layersProc.running) layersProc.running = true
    }

    // Dynamic system tiling border size, rounding & active gradient border
    property int systemBorderSize: 2
    property int systemRounding: Style.cornerRadius >= 0 ? Style.cornerRadius : 12
    property string hyprlandActiveBorderRaw: ""

    function parseHyprlandColor(str) {
        var s = String(str || "").trim()
        var m8 = s.match(/^(?:0x|#|rgba\()?([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})\)?$/)
        if (m8) {
            var a = parseInt(m8[1], 16) / 255
            var r = parseInt(m8[2], 16)
            var g = parseInt(m8[3], 16)
            var b = parseInt(m8[4], 16)
            return Qt.rgba(r / 255, g / 255, b / 255, a)
        }
        var m6 = s.match(/^(?:0x|#|rgb\()?([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})\)?$/)
        if (m6) {
            var r = parseInt(m6[1], 16)
            var g = parseInt(m6[2], 16)
            var b = parseInt(m6[3], 16)
            return Qt.rgba(r / 255, g / 255, b / 255, 1.0)
        }
        return s
    }

    function parseHyprlandGradient(raw, fallbackColor) {
        var s = String(raw || "").trim()
        if (!s) return { colors: [fallbackColor], angle: 0, enabled: false }
        var parts = s.split(/\s+/)
        var colors = []
        var angle = 0
        for (var i = 0; i < parts.length; i++) {
            var p = parts[i]
            if (p.match(/^-?\d+(?:\.\d+)?deg$/)) {
                angle = Number(p.replace(/deg$/, ""))
            } else {
                var c = root.parseHyprlandColor(p)
                if (c) colors.push(c)
            }
        }
        if (colors.length === 0) colors.push(fallbackColor)
        return {
            colors: colors,
            angle: angle,
            enabled: colors.length > 1
        }
    }

    property var dockBorderSpec: {
        if (root.isBarTransparent || root.systemBorderSize <= 0) {
            return Border.none()
        }
        var raw = root.hyprlandActiveBorderRaw
        if (raw && raw.length > 0) {
            var grad = root.parseHyprlandGradient(raw, Color.accent)
            return {
                color: grad.colors[0],
                widths: { top: root.systemBorderSize, right: root.systemBorderSize, bottom: root.systemBorderSize, left: root.systemBorderSize },
                gradient: grad
            }
        }
        return Border.hyprlandActiveSpec(Color.accent, root.systemBorderSize)
    }

    Process {
        id: roundingProc
        command: ["hyprctl", "-j", "getoption", "decoration:rounding"]
        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                try {
                    var json = JSON.parse(text || "{}")
                    var n = Number(json.int)
                    if (isFinite(n) && n >= 0) {
                        if (root.systemRounding !== n) {
                            root.systemRounding = n
                        }
                    }
                } catch(e) {}
            }
        }
    }

    Process {
        id: borderSizeProc
        command: ["hyprctl", "-j", "getoption", "general:border_size"]
        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                try {
                    var json = JSON.parse(text || "{}")
                    var n = Number(json.int)
                    if (isFinite(n) && n >= 0) {
                        if (root.systemBorderSize !== n) {
                            root.systemBorderSize = n
                        }
                    }
                } catch(e) {}
            }
        }
    }

    Process {
        id: activeBorderProc
        command: ["hyprctl", "-j", "getoption", "general:col.active_border"]
        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                try {
                    var json = JSON.parse(text || "{}")
                    var grad = String(json.gradient || json.str || "").trim()
                    if (grad.length > 0) {
                        if (root.hyprlandActiveBorderRaw !== grad) {
                            root.hyprlandActiveBorderRaw = grad
                        }
                    }
                } catch(e) {}
            }
        }
    }

    property bool borderAngleAnimationEnabled: true
    property real borderAngleAnimationDuration: 6000

    Process {
        id: animationsProc
        command: ["hyprctl", "animations"]
        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                try {
                    var str = text || ""
                    var match = str.match(/name:\s*borderangle[\s\S]*?enabled:\s*([0-9-]+)[\s\S]*?speed:\s*([0-9.]+)/)
                    if (match) {
                        var en = Number(match[1])
                        var sp = Number(match[2])
                        root.borderAngleAnimationEnabled = (en === 1)
                        if (isFinite(sp) && sp > 0) {
                            root.borderAngleAnimationDuration = Math.max(1000, sp * 200)
                        }
                    }
                } catch(e) {}
            }
        }
    }

    Timer {
        id: hyprlandRefreshDebounceTimer
        interval: 150
        repeat: false
        onTriggered: root.doRefreshHyprlandOptions()
    }

    function refreshHyprlandOptions() {
        hyprlandRefreshDebounceTimer.restart()
    }

    function doRefreshHyprlandOptions() {
        if (!roundingProc.running) roundingProc.running = true
        if (!borderSizeProc.running) borderSizeProc.running = true
        if (!activeBorderProc.running) activeBorderProc.running = true
        if (!animationsProc.running) animationsProc.running = true
    }

    Connections {
        target: Hyprland
        function onRawEvent(event) {
            if (event && event.name === "configreloaded") {
                root.refreshHyprlandOptions()
            }
        }
    }

    Connections {
        target: Style
        function onCornerRadiusChanged() {
            if (Style.cornerRadius >= 0) root.systemRounding = Style.cornerRadius
        }
        function onNormalBorderWidthChanged() {
            if (Style.normalBorderWidth >= 0) root.systemBorderSize = Style.normalBorderWidth
        }
    }

    FileView {
        path: Quickshell.env("HOME") + "/.config/hypr/looknfeel.lua"
        watchChanges: true
        printErrors: false
        onFileChanged: root.refreshHyprlandOptions()
        onLoaded: root.refreshHyprlandOptions()
    }

    FileView {
        path: Quickshell.env("HOME") + "/.config/hypr/hyprland.conf"
        watchChanges: true
        printErrors: false
        onFileChanged: root.refreshHyprlandOptions()
    }

    FileView {
        path: Quickshell.env("HOME") + "/.local/state/omarchy/toggles/hypr/window-no-gaps.lua"
        watchChanges: true
        printErrors: false
        onFileChanged: root.refreshHyprlandOptions()
    }

    // Unified Edit Mode State (Jiggle Mode across dock and open folders)
    property bool isEditMode: false

    function closeAppWindows(appIdOrItem) {
        if (!appIdOrItem) return
        var toplevels = []
        if (typeof appIdOrItem === "string") {
            for (var i = 0; i < root.dockItems.length; i++) {
                if (root.dockItems[i].appId === appIdOrItem && root.dockItems[i].toplevels) {
                    toplevels = root.dockItems[i].toplevels
                    break
                }
            }
        } else if (appIdOrItem.toplevels) {
            toplevels = appIdOrItem.toplevels
        }
        for (var t = 0; t < toplevels.length; t++) {
            if (toplevels[t].close) toplevels[t].close()
        }
    }

    // Which window the helper script should act on, as a Hyprland address.
    // The script resolves a bare --index against Hyprland's client list, which
    // is ordered independently of the dock's own window order, so the two agree
    // only until Hyprland reshuffles. Name the window instead, and fall back to
    // the position only when the address cannot be resolved.
    function targetWindowArg(itemData, targetIndex) {
        if (!itemData) return ""
        if (typeof targetIndex === "string" && targetIndex.indexOf("0x") === 0) {
            return targetIndex
        }
        if (typeof targetIndex !== "number" || targetIndex < 0) return ""
        var tops = itemData.toplevels || []
        if (targetIndex >= tops.length) return ""
        var hyprTops = (typeof Hyprland !== "undefined" && Hyprland.toplevels && Hyprland.toplevels.values)
            ? Hyprland.toplevels.values
            : []
        return DockModel.hyprAddressFor(tops[targetIndex], hyprTops)
    }

    function minimizeItem(itemData, targetIndex) {
        if (!itemData) return
        var args = ["minimize-instance"]
        if (itemData.appId) args.push(itemData.appId)
        if (itemData.desktopId && itemData.desktopId !== itemData.appId) args.push(itemData.desktopId)
        if (itemData.exec) args.push(itemData.exec)
        if (itemData.appClass && itemData.appClass !== itemData.appId && itemData.appClass !== itemData.desktopId) args.push(itemData.appClass)
        if (itemData.toplevels && typeof targetIndex === "number" && targetIndex >= 0 && targetIndex < itemData.toplevels.length) {
            var topAppMin = itemData.toplevels[targetIndex].appId || ""
            if (topAppMin && topAppMin !== itemData.appId && topAppMin !== itemData.desktopId && topAppMin !== itemData.appClass) {
                args.push(topAppMin)
            }
        }
        var targetArg = root.targetWindowArg(itemData, targetIndex)
        if (targetArg) {
            args.push(targetArg)
        } else if (typeof targetIndex === "number" && targetIndex >= 0) {
            args.push("--index=" + targetIndex)
        }
        var scriptPath = Qt.resolvedUrl("scripts/dock-minimize.py").toString().replace(/^file:\/\//, "")
        if (typeof Util !== "undefined" && typeof Util.execArgv === "function") {
            Util.execArgv(["python3", scriptPath].concat(args))
        } else {
            var cmd = "python3 " + (typeof Util !== "undefined" && Util.shellQuote ? Util.shellQuote(scriptPath) : ("\"" + scriptPath + "\""))
            for (var i = 0; i < args.length; i++) {
                var a = String(args[i])
                cmd += " " + (typeof Util !== "undefined" && Util.shellQuote ? Util.shellQuote(a) : ("\"" + a.replace(/"/g, "\\\"") + "\""))
            }
            Util.execDetached(cmd)
        }
        root.updateDockItems()
        minimizeRefreshTimer.restart()
    }

    function restoreOrLaunchItem(itemData, targetIndex) {
        if (!itemData) return
        var args = ["activate-instance"]
        if (itemData.appId) args.push(itemData.appId)
        if (itemData.desktopId && itemData.desktopId !== itemData.appId) args.push(itemData.desktopId)
        if (itemData.exec) args.push(itemData.exec)
        if (itemData.appClass && itemData.appClass !== itemData.appId && itemData.appClass !== itemData.desktopId) args.push(itemData.appClass)
        if (itemData.toplevels && typeof targetIndex === "number" && targetIndex >= 0 && targetIndex < itemData.toplevels.length) {
            var topAppAct = itemData.toplevels[targetIndex].appId || ""
            if (topAppAct && topAppAct !== itemData.appId && topAppAct !== itemData.desktopId && topAppAct !== itemData.appClass) {
                args.push(topAppAct)
            }
        }
        var targetArg = root.targetWindowArg(itemData, targetIndex)
        if (targetArg) {
            args.push(targetArg)
        } else if (typeof targetIndex === "number" && targetIndex >= 0) {
            args.push("--index=" + targetIndex)
        }
        var scriptPath = Qt.resolvedUrl("scripts/dock-minimize.py").toString().replace(/^file:\/\//, "")
        var launchId = itemData.desktopId || itemData.appId || ""
        root.requestFocusOnLaunch(launchId)
        DockModel.setPendingCliHint(itemData.appId || itemData.desktopId || "", root.knownWindows)
        if (typeof Util !== "undefined" && typeof Util.execArgv === "function") {
            Util.execArgv(["python3", scriptPath].concat(args))
        } else {
            var cmd = "python3 " + (typeof Util !== "undefined" && Util.shellQuote ? Util.shellQuote(scriptPath) : ("\"" + scriptPath + "\""))
            for (var i = 0; i < args.length; i++) {
                var a = String(args[i])
                cmd += " " + (typeof Util !== "undefined" && Util.shellQuote ? Util.shellQuote(a) : ("\"" + a.replace(/"/g, "\\\"") + "\""))
            }
            Util.execDetached(cmd)
        }
        root.updateDockItems()
        minimizeRefreshTimer.restart()
    }

    // Right-Click Menu State
    property var activeMenuItem: null
    property int activeMenuItemIndex: 0
    property bool isMenuFromFolder: false
    property int activeMenuItemFolderIndex: 0
    readonly property bool isMenuOpen: activeMenuItem !== null

    property var activeStackItem: null
    property int activeStackItemIndex: 0
    property bool isEditingFolderTitle: false
    readonly property bool isStackOpen: activeStackItem !== null

    onActiveStackItemChanged: {
        if (activeStackItem) {
            if (stackWindow && stackWindow.stackCard) stackWindow.stackCard.forceActiveFocus()
        } else {
            root.isEditingFolderTitle = false
        }
    }

    // Pinned apps persistence
    property string userPinnedPath: Quickshell.env("HOME") + "/.config/omarchy/dock-pinned.json"
    property int iconRevision: 0
    property var pinnedIds: []
    property var dockItems: []
    property var appRows: (shell && shell.appLibrary) ? shell.appLibrary.sortedEntries("") : []

    // Curated available symbols for folder icon personalization (Clean monochrome vector glyphs)
    readonly property var availableFolderIcons: ["󰉋", "󰒓", "󰞷", "󰝚", "󰊴", "󰏘", "󰭹", "󰖟", "󰕧", "󰈔", "󰍹", "󰖩", "󰌾", "♥"]

    function resolveIcon(itemObj) {
        if (!itemObj) return Quickshell.iconPath("application-x-executable", true)
        var raw = (typeof itemObj === "string") ? itemObj : (itemObj.rawIcon || itemObj.icon || itemObj.appId || itemObj.id || "")
        if (!raw) return Quickshell.iconPath("application-x-executable", true)
        if (raw.indexOf("://") >= 0) return raw
        if (raw.indexOf("/") === 0) return "file://" + raw

        var cands = (typeof itemObj === "string")
            ? DockModel.getCandidates(itemObj, itemObj, itemObj)
            : DockModel.getCandidates(itemObj.rawIcon, itemObj.icon, itemObj.appId || itemObj.id)

        for (var i = 0; i < cands.length; i++) {
            var c = cands[i]
            if (c.indexOf("://") >= 0) return c
            if (c.indexOf("/") === 0) return "file://" + c
            var diskHit = DockModel.getDiskIcon(c)
            if (diskHit) return diskHit
            var diskHitLow = DockModel.getDiskIcon(c.toLowerCase())
            if (diskHitLow) return diskHitLow
            if (shell && shell.appLibrary && typeof shell.appLibrary.iconSource === "function") {
                var src = shell.appLibrary.iconSource(c)
                if (src && src.length > 0 && src.indexOf("application-x-executable") === -1) {
                    return src
                }
                var cLow = c.toLowerCase()
                if (cLow !== c) {
                    var srcLow = shell.appLibrary.iconSource(cLow)
                    if (srcLow && srcLow.length > 0 && srcLow.indexOf("application-x-executable") === -1) {
                        return srcLow
                    }
                }
            }
            var qs = Quickshell.iconPath(c, true)
            if (qs && qs.length > 0 && qs.indexOf("application-x-executable") === -1) {
                return qs
            }
            var qsLow = Quickshell.iconPath(c.toLowerCase(), true)
            if (qsLow && qsLow.length > 0 && qsLow.indexOf("application-x-executable") === -1) {
                return qsLow
            }
        }

        return Quickshell.iconPath("application-x-executable", true)
    }

    // Exact Geometric Horizontal Center for Stack Popup Card (100% centered over folder icon in dock)
    readonly property real calculatedStackLeft: {
        var screenW = (dockWindow && dockWindow.screen) ? dockWindow.screen.width : 1920
        var dockW = root.isVertical ? (root.slotSize + 4) : (root.totalDockDimension + 8)
        var dockLeft = (screenW - dockW) / 2
        var appBaseOffset = (root.widgetPosition === "left" && root.hasWidgets) ? (root.widgetsWidth + root.separatorSize) : 0
        var iconCenterX = dockLeft + 4 + appBaseOffset + root.activeStackItemIndex * root.slotSize + (root.slotSize / 2)
        var cardW = (stackWindow && stackWindow.stackCard) ? stackWindow.stackCard.width : 180
        return Math.round(Math.max(6, Math.min(screenW - cardW - 6, iconCenterX - cardW / 2)))
    }

    readonly property real calculatedStackTop: {
        var screenH = (dockWindow && dockWindow.screen) ? dockWindow.screen.height : 1080
        var dockH = root.isVertical ? (root.totalDockDimension + 8) : (root.slotSize + 4)
        var dockTop = (screenH - dockH) / 2
        var appBaseOffset = (root.widgetPosition === "left" && root.hasWidgets) ? (root.widgetsWidth + root.separatorSize) : 0
        var iconCenterY = dockTop + 4 + appBaseOffset + root.activeStackItemIndex * root.slotSize + (root.slotSize / 2)
        var cardH = (stackWindow && stackWindow.stackCard) ? stackWindow.stackCard.height : 180
        return Math.round(Math.max(6, Math.min(screenH - cardH - 6, iconCenterY - cardH / 2)))
    }

    function closePopups() {
        root.activeStackItem = null
        root.activeMenuItem = null
        root.isEditMode = false
        root.isEditingFolderTitle = false
        root.folderDragActiveIndex = -1
        root.folderDragTargetIndex = -1
        root.currentMergeTargetIndex = -1
        if (widgetPicker) widgetPicker.opened = false
        root.closeAllWidgetPanels()
        root.evaluateHoverState()
    }

    // Auto-dismiss open folders, folder icon editor, widget panels and edit mode when system notifications / OSD appear
    readonly property var notifService: (root.shell && typeof root.shell.serviceFor === "function") ? root.shell.serviceFor("omarchy.notifications") : null
    readonly property var notifPopupModel: (root.notifService && root.notifService.popupModel) ? root.notifService.popupModel : null
    readonly property int notifPopupCount: notifPopupModel ? notifPopupModel.count : 0

    onNotifPopupCountChanged: {
        if (notifPopupCount > 0) {
            root.closePopups()
        }
    }

    Connections {
        target: root.notifPopupModel ? root.notifPopupModel : null
        ignoreUnknownSignals: true
        function onRowsInserted() {
            root.closePopups()
        }
        function onCountChanged() {
            if (root.notifPopupCount > 0) {
                root.closePopups()
            }
        }
    }

    readonly property bool isOsdOpen: {
        if (!root.shell) return false
        if (root.shell.openPanelIds && root.shell.openPanelIds["omarchy.osd"]) return true
        if (root.shell.appLibrary && root.shell.appLibrary.launchOsdOpen) return true
        if (typeof root.shell.isPluginOpen === "function" && root.shell.isPluginOpen("omarchy.osd")) return true
        return false
    }

    onIsOsdOpenChanged: {
        if (isOsdOpen) {
            root.closePopups()
        }
    }

    readonly property var osdLoader: (root.shell && root.shell.panelLoaders) ? root.shell.panelLoaders["omarchy.osd"] : null
    readonly property var osdItem: (osdLoader && osdLoader.item) ? osdLoader.item : null
    readonly property bool osdItemOpened: (osdItem && osdItem.opened !== undefined) ? osdItem.opened : false

    onOsdItemOpenedChanged: {
        if (osdItemOpened) {
            root.closePopups()
        }
    }

    Connections {
        target: root.shell ? root.shell : null
        // Omarchy's scoped plugin shell (third-party installs) has no openPanelIds
        ignoreUnknownSignals: true
        function onOpenPanelIdsChanged() {
            if (root.shell && root.shell.openPanelIds) {
                if (root.shell.openPanelIds["omarchy.osd"] || root.shell.openPanelIds["omarchy.notifications"]) {
                    root.closePopups()
                }
            }
        }
    }

    Connections {
        target: (root.shell && root.shell.appLibrary) ? root.shell.appLibrary : null
        function onLaunchOsdOpenChanged() {
            if (root.shell && root.shell.appLibrary && root.shell.appLibrary.launchOsdOpen) {
                root.closePopups()
            }
        }
    }

    function refresh() {
        root.pinnedIds = DockModel.parsePinned(userPinnedFile.text() || "")
        root.refreshLayers()
        root.updatePluginEnabled()
        iconScanDebounceTimer.restart()
        root.updateDockItems()
        return "ok"
    }

    // Coalescing debounce timer to prevent signal storm while keeping UI instantaneous
    Timer {
        id: batchUpdateTimer
        interval: 16
        repeat: false
        onTriggered: root.doUpdateDockItems()
    }

    function updateDockItems() {
        batchUpdateTimer.restart()
    }

    NotificationTracker {
        id: notifTracker
        shell: root.shell
        knownWindows: root.knownWindows
        onBadgeChanged: root.doUpdateDockItems()
    }

    // Clearing a badge rebuilds dockItems, and the Repeater below then destroys
    // the very delegate whose click is still running. Every statement after the
    // call — the rest of onItemLeftClicked, and DockItem's own handler, which
    // has not yet asked for the window — would execute in a dead context and
    // throw "root is not defined", swallowing the click. Defer the clear so the
    // click finishes before the delegates are replaced.
    function clearBadge(itemData) {
        if (!notifTracker) return
        Qt.callLater(function() {
            if (notifTracker) notifTracker.clearBadge(itemData)
        })
    }

    function getMinimizedToplevels() {
        var minTops = []
        if (typeof Hyprland !== "undefined" && Hyprland.workspaces && Hyprland.workspaces.values) {
            var wsArr = Hyprland.workspaces.values
            for (var w = 0; w < wsArr.length; w++) {
                var ws = wsArr[w]
                if (ws && String(ws.name || "").indexOf("special:") === 0) {
                    if (ws.toplevels && ws.toplevels.values) {
                        var tops = ws.toplevels.values
                        for (var wt = 0; wt < tops.length; wt++) {
                            var ht = tops[wt]
                            if (ht) {
                                if (ht.wayland) minTops.push(ht.wayland)
                                minTops.push(ht)
                            }
                        }
                    }
                }
            }
        }
        return minTops
    }

    function doUpdateDockItems() {
        root.syncKnownWindows()
        var toplevels = root.knownWindows
        var minTops = root.getMinimizedToplevels()
        var active = ToplevelManager.activeToplevel
        if (active) {
            if (minTops.indexOf(active) !== -1) {
                active = null
            } else if (typeof Hyprland !== "undefined" && Hyprland.activeToplevel && Hyprland.activeToplevel.workspace) {
                var aWs = String(Hyprland.activeToplevel.workspace.name || "")
                if (aWs.indexOf("special:") === 0) {
                    active = null
                }
            }
        }
        var lib = root.shell ? root.shell.appLibrary : null
        var allEntries = (typeof DesktopEntries !== "undefined" && DesktopEntries.applications && DesktopEntries.applications.values && DesktopEntries.applications.values.length > 0)
            ? DesktopEntries.applications.values
            : (lib && typeof lib.sortedEntries === "function" ? lib.sortedEntries("") : root.appRows)
        root.dockItems = DockModel.buildDockItems(root.pinnedIds, toplevels, active, allEntries, lib, notifTracker.canonicalCounts, notifTracker.canonicalUrgent, root.maxDockItems, minTops)

        // Refresh active stack item contents if open
        if (root.activeStackItem) {
            var found = false
            for (var i = 0; i < root.dockItems.length; i++) {
                var it = root.dockItems[i]
                if (it && (it.id === root.activeStackItem.id || it.appId === root.activeStackItem.appId)) {
                    if (it.isStack && it.subApps && it.subApps.length >= 2) {
                        root.activeStackItem = it
                        root.activeStackItemIndex = i
                        found = true
                    }
                    break
                }
            }
            if (!found) {
                root.activeStackItem = null
                root.folderDragActiveIndex = -1
                root.folderDragTargetIndex = -1
            }
        }

        // Refresh active menu item (multi-window menu) if open
        if (root.activeMenuItem && !root.activeMenuItem.isStack && root.activeMenuItem.windows) {
            var mAppId = root.activeMenuItem.appId
            var mWinList = []
            for (var mw = 0; mw < toplevels.length; mw++) {
                var mTop = toplevels[mw]
                if (mTop && DockModel.matchToplevel(mTop, mAppId, null)) {
                    var mActive = (active && mTop === active)
                    mWinList.push({
                        index: mWinList.length,
                        title: mTop.title || root.activeMenuItem.name || "",
                        isActive: !!mActive
                    })
                }
            }
            if (mWinList.length === 0) {
                root.activeMenuItem = null
            } else {
                root.activeMenuItem = {
                    id: root.activeMenuItem.id,
                    appId: root.activeMenuItem.appId,
                    name: root.activeMenuItem.name,
                    icon: root.activeMenuItem.icon,
                    rawIcon: root.activeMenuItem.rawIcon,
                    isStack: false,
                    windows: mWinList
                }
            }
        }
    }

    onPinnedIdsChanged: updateDockItems()
    onAppRowsChanged: updateDockItems()
    onShellChanged: {
        root.appRows = (shell && shell.appLibrary) ? shell.appLibrary.sortedEntries("") : []
        root.updateDockItems()
    }

    Connections {
        target: ToplevelManager.toplevels
        function onValuesChanged() {
            var live = ToplevelManager.toplevels ? ToplevelManager.toplevels.values : []
            var hasNewTerm = false
            for (var i = 0; i < live.length; i++) {
                var t = live[i]
                if (t && (t.appId === "foot" || t.appId === "ghostty" || t.appId === "kitty" || t.appId === "alacritty" || t.appId === "wezterm")) {
                    if (root.knownWindows.indexOf(t) === -1) {
                        hasNewTerm = true
                        break
                    }
                }
            }
            if (hasNewTerm) {
                root.lastTerminalOpenTime = Date.now()
                cliScannerProc.running = true
                terminalSettleTimer.restart()
            } else if (Date.now() - root.lastTerminalOpenTime < 150) {
                terminalSettleTimer.restart()
            } else {
                root.updateDockItems()
            }
        }
    }

    Connections {
        target: ToplevelManager
        function onActiveToplevelChanged() {
            if (Date.now() - root.lastTerminalOpenTime < 150) {
                terminalSettleTimer.restart()
            } else {
                root.updateDockItems()
            }
        }
    }

    property double lastWindowOpenTime: 0
    property double lastTerminalOpenTime: 0

    Process {
        id: cliScannerProc
        running: false
        command: ["python3", Qt.resolvedUrl("scripts/dock-minimize.py").toString().replace(/^file:\/\//, ""), "scan-cli"]
        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                try {
                    var apps = JSON.parse(text)
                    if (Array.isArray(apps)) {
                        DockModel.setDetectedCliApps(apps)
                        root.updateDockItems()
                    }
                } catch(e) {}
            }
        }
    }

    Process {
        id: iconScannerProc
        running: false
        command: ["python3", Qt.resolvedUrl("scripts/dock-minimize.py").toString().replace(/^file:\/\//, ""), "scan-icons"]
        stdout: StdioCollector {
            waitForEnd: true
            onStreamFinished: {
                try {
                    var icons = JSON.parse(text)
                    if (icons && typeof icons === "object") {
                        DockModel.setDiskIcons(icons)
                        root.iconRevision++
                        root.updateDockItems()
                    }
                } catch(e) {}
            }
        }
    }

    Timer {
        id: iconScanDebounceTimer
        interval: 200
        repeat: false
        onTriggered: {
            if (!iconScannerProc.running) {
                iconScannerProc.running = true
            }
        }
    }

    Timer {
        id: terminalSettleTimer
        interval: 100
        repeat: false
        onTriggered: {
            if (Date.now() - root.lastTerminalOpenTime < 2000) {
                cliScannerProc.running = true
            }
            root.updateDockItems()
        }
    }

    Timer {
        id: titleChangeDebounceTimer
        interval: 250
        repeat: false
        onTriggered: root.updateDockItems()
    }

    Timer {
        id: minimizeRefreshTimer
        interval: 65
        repeat: false
        onTriggered: root.updateDockItems()
    }

    Connections {
        target: (typeof Hyprland !== "undefined") ? Hyprland : null
        function onActiveToplevelChanged() {
            if (Date.now() - root.lastTerminalOpenTime < 150) {
                terminalSettleTimer.restart()
            } else {
                root.updateDockItems()
            }
        }
        function onRawEvent(event) {
            if (!event) return
            var name = String(event.name || "")
            if (name === "windowtitle" || name === "windowtitlev2") {
                if (Date.now() - root.lastWindowOpenTime < 2000) {
                    root.updateDockItems()
                } else {
                    titleChangeDebounceTimer.restart()
                }
                return
            }
            if (name === "movewindow" || name === "movewindowv2" || name === "activewindow" || name === "activewindowv2" || name === "closewindow" || name === "workspace" || name === "workspacev2" || name === "focusedmon") {
                root.updateDockItems()
                return
            }
            if (name === "openwindow") {
                root.lastWindowOpenTime = Date.now()
                iconScanDebounceTimer.restart()
                var openArgs = String(event.args || "")
                var openParts = openArgs.split(",")
                var openClass = openParts.length >= 3 ? openParts[2].trim().toLowerCase() : ""
                var isTerm = (openClass === "foot" || openClass === "ghostty" || openClass === "kitty" || openClass === "alacritty" || openClass === "wezterm")

                if (isTerm) {
                    root.lastTerminalOpenTime = Date.now()
                    cliScannerProc.running = true
                    terminalSettleTimer.restart()
                } else {
                    root.updateDockItems()
                }

                if (root.pendingFocusAppId) {
                    if (Date.now() - root.pendingFocusTimestamp > 8000) {
                        root.pendingFocusAppId = ""
                        return
                    }
                    if (openParts.length >= 3) {
                        var addr = openParts[0].trim()
                        var winClass = openParts[2].trim().toLowerCase()
                        var pending = root.pendingFocusAppId.toLowerCase()
                        var normClass = winClass.replace(/[^a-z0-9]/g, "")
                        var normPending = pending.replace(/[^a-z0-9]/g, "")
                        if (winClass === pending || (normPending.length > 0 && (normClass.indexOf(normPending) !== -1 || normPending.indexOf(normClass) !== -1))) {
                            root.pendingFocusAppId = ""
                            var cleanAddr = (addr.indexOf("0x") === 0) ? addr : ("0x" + addr)
                            Util.execDetached("hyprctl dispatch focuswindow address:" + cleanAddr)
                        }
                    }
                }
            }
        }
    }

    Connections {
        target: Color
        function onAccentChanged() {
            if (shell && shell.appLibrary && typeof shell.appLibrary.refreshIcons === "function") {
                shell.appLibrary.refreshIcons()
            }
            root.appRows = (shell && shell.appLibrary) ? shell.appLibrary.sortedEntries("") : []
            root.doUpdateDockItems()
        }
        function onForegroundChanged() { root.doUpdateDockItems() }
        function onBackgroundChanged() { root.doUpdateDockItems() }
    }

    Connections {
        target: Style
        function onCornerRadiusChanged() {
            root.systemRounding = Style.cornerRadius >= 0 ? Style.cornerRadius : 12
            root.doUpdateDockItems()
        }
    }

    Connections {
        target: DesktopEntries.applications
        function onValuesChanged() {
            root.appRows = (shell && shell.appLibrary) ? shell.appLibrary.sortedEntries("") : (DesktopEntries.applications.values || [])
            iconScanDebounceTimer.restart()
            root.iconRevision++
            root.updateDockItems()
        }
    }

    Connections {
        target: shell ? shell.appLibrary : null
        enabled: target !== null
        function onAppsChanged() {
            root.appRows = shell.appLibrary.sortedEntries("")
            root.iconRevision++
            root.updateDockItems()
        }
        function onIconIndexChanged() {
            root.iconRevision++
            root.doUpdateDockItems()
        }
    }

    FileView {
        id: themeWatcher
        path: Quickshell.env("HOME") + "/.local/state/omarchy/current/theme.name"
        watchChanges: true
        printErrors: false
        onFileChanged: {
            if (shell && shell.appLibrary && typeof shell.appLibrary.refreshIcons === "function") {
                shell.appLibrary.refreshIcons()
            }
            iconScanDebounceTimer.restart()
            root.appRows = (shell && shell.appLibrary) ? shell.appLibrary.sortedEntries("") : []
            root.iconRevision++
            root.doUpdateDockItems()
        }
    }

    property bool isGtkSettingsLoaded: false

    FileView {
        id: gtkSettingsFile
        path: Quickshell.env("HOME") + "/.config/gtk-3.0/settings.ini"
        watchChanges: true
        printErrors: false
        onLoaded: {
            root.isGtkSettingsLoaded = true
            root.triggerThemeRefresh()
        }
        onFileChanged: {
            reload()
            root.isGtkSettingsLoaded = true
            root.triggerThemeRefresh()
        }
    }

    readonly property string configuredIconTheme: {
        var txt = gtkSettingsFile.text()
        if (!txt) return ""
        var m = txt.match(/gtk-icon-theme-name\s*=\s*([^\r\n]+)/)
        return m ? m[1].trim() : ""
    }

    readonly property bool hasCustomIconTheme: {
        var t = root.configuredIconTheme.toLowerCase()
        return t.length > 0 && t !== "hicolor" && t !== "adwaita" && t !== "gnome"
    }

    property bool isPinnedLoaded: false
    property bool iconsReady: false
    property bool isDockVisualReady: false

    function triggerThemeRefresh() {
        themeChangeDebounceTimer.restart()
    }

    Timer {
        id: themeChangeDebounceTimer
        interval: 100
        repeat: false
        onTriggered: {
            if (shell && shell.appLibrary && typeof shell.appLibrary.refreshIcons === "function") {
                shell.appLibrary.refreshIcons()
            }
        }
    }

    Timer {
        id: iconIndexApplyTimer
        interval: 20
        repeat: false
        onTriggered: {
            root.iconRevision++
            root.doUpdateDockItems()
            var hasIndex = (shell && shell.appLibrary && shell.appLibrary.iconIndex && Object.keys(shell.appLibrary.iconIndex).length > 0)
            if (hasIndex) {
                root.iconsReady = true
            }
        }
    }

    FileView {
        id: omarchyIconThemeFile
        path: Quickshell.env("HOME") + "/.local/state/omarchy/current/theme/icons.theme"
        watchChanges: true
        printErrors: false
        onFileChanged: root.triggerThemeRefresh()
        onLoaded: root.triggerThemeRefresh()
    }

    FileView {
        id: gtk4SettingsFile
        path: Quickshell.env("HOME") + "/.config/gtk-4.0/settings.ini"
        watchChanges: true
        printErrors: false
        onFileChanged: root.triggerThemeRefresh()
        onLoaded: root.triggerThemeRefresh()
    }

    // Защитный таймер: если фоновый поиск темы затянулся, показываем доступные иконки
    Timer {
        id: iconsSafetyTimer
        interval: 1500
        running: !root.iconsReady
        repeat: false
        onTriggered: {
            if (!root.iconsReady) {
                root.iconRevision++
                root.doUpdateDockItems()
                root.iconsReady = true
            }
        }
    }

    // Задержка показа дока после поднятия плитки окон Hyprland (250мс на анимацию тайлинга и готовность иконок)
    Timer {
        id: dockVisualAppearTimer
        interval: 250
        running: root.iconsReady && !root.isDockVisualReady
        repeat: false
        onTriggered: {
            root.isDockVisualReady = true
        }
    }

    Connections {
        target: (shell && shell.appLibrary) ? shell.appLibrary : null
        function onIconIndexChanged() {
            iconIndexApplyTimer.restart()
        }
        function onAppsChanged() {
            iconIndexApplyTimer.restart()
        }
    }

    Component.onCompleted: {
        if (Hyprland.focusedMonitor) {
            root.baseDockMonitorName = String(Hyprland.focusedMonitor.name || "")
        }
        root.parseShellConfigFile()
        try {
            var txt = userPinnedFile.text()
            if (txt && txt.trim().length > 0) {
                var parsed = DockModel.parsePinned(txt)
                if (parsed && parsed.length > 0) {
                    root.pinnedIds = parsed
                    root.isPinnedLoaded = true
                }
            }
        } catch(e) {}
        root.readSettings()
        root.refreshHyprlandOptions()
        if (shell && shell.appLibrary && typeof shell.appLibrary.refreshIcons === "function") {
            shell.appLibrary.refreshIcons()
        }
        if (shell && shell.appLibrary && typeof shell.appLibrary.launch === "function" && !shell.appLibrary._dockLaunchHooked) {
            shell.appLibrary._dockLaunchHooked = true
            var origAppLibLaunch = shell.appLibrary.launch
            shell.appLibrary.launch = function(appId, appName) {
                root.requestFocusOnLaunch(appId)
                DockModel.setPendingCliHint(appId, root.knownWindows)
                return origAppLibLaunch.apply(this, arguments)
            }
        }
        iconScanDebounceTimer.restart()
        root.doUpdateDockItems()
    }

    FileView {
        id: userPinnedFile
        path: root.userPinnedPath
        watchChanges: true
        atomicWrites: true
        printErrors: false
        onLoaded: {
            var txt = text()
            if (txt && txt.trim().length > 0) {
                var parsed = DockModel.parsePinned(txt)
                root.pinnedIds = parsed
                root.isPinnedLoaded = true
                root.doUpdateDockItems()
            } else {
                root.isPinnedLoaded = true
            }
        }
        onLoadFailed: {
            root.isPinnedLoaded = true
            root.doUpdateDockItems()
        }
        onFileChanged: userPinnedFile.reload()
    }

    function savePinned() {
        var json = DockModel.serializePinned(root.pinnedIds)
        userPinnedFile.setText(json + "\n")
    }

    function setPinned(next) {
        root.pinnedIds = next
        root.savePinned()
        root.doUpdateDockItems()
    }

    readonly property var activeToplevel: ToplevelManager.activeToplevel

    // 1. Outside-click dismissal for Context Menu (closes ONLY the menu)
    HyprlandFocusGrab {
        id: menuGrab
        active: root.isMenuOpen
        windows: [menuWindow]
        onCleared: {
            root.activeMenuItem = null
        }
    }

    // 3. Outside-click & Escape dismissal for Edit Mode
    HyprlandFocusGrab {
        id: editGrab
        active: root.isEditMode && !root.isStackOpen && !root.isMenuOpen
        windows: dockVariants.instances
        onCleared: {
            root.isEditMode = false
        }
    }

    onIsEditModeChanged: {
        if (isEditMode) {
            var win = root.dockWindow
            if (win && win.surface) win.surface.forceActiveFocus()
        }
        root.evaluateHoverState()
    }

    onIsStackOpenChanged: {
        if (isStackOpen) {
            if (stackWindow && stackWindow.stackCard) stackWindow.stackCard.forceActiveFocus()
        }
        root.evaluateHoverState()
    }

    onIsMenuOpenChanged: {
        if (isMenuOpen) {
            if (menuWindow && menuWindow.menuCard) {
                menuWindow.menuCard.forceActiveFocus()
                if (root.activeMenuItem && root.activeMenuItem.isStack) {
                    var curIcon = root.activeMenuItem.icon || "grid"
                    var foundIdx = root.availableFolderIcons.indexOf(curIcon)
                    menuWindow.menuCard.selectedIndex = (foundIdx >= 0) ? foundIdx : 0
                } else {
                    menuWindow.menuCard.selectedIndex = -1
                }
            }
        }
        root.evaluateHoverState()
    }

    property var activeRightTooltipTarget: null
    property string activeRightTooltipText: ""

    function showRightTooltip(item, text) {
        if (!item || !text) {
            hideRightTooltip(item)
            return
        }
        activeRightTooltipTarget = item
        activeRightTooltipText = text
    }

    function hideRightTooltip(item) {
        if (activeRightTooltipTarget === item || !item) {
            activeRightTooltipTarget = null
            activeRightTooltipText = ""
        }
    }

    readonly property var dockWindow: {
        var instances = dockVariants.instances
        var count = instances ? instances.length : 0
        // When a reveal is targeting a specific (possibly non-focused) screen,
        // popups should attach to that revealed instance instead of whichever
        // screen has keyboard focus.
        var targetName = root.revealTargetMonitorName !== "" ? root.revealTargetMonitorName : ""
        if (targetName !== "") {
            for (var t = 0; t < count; t++) {
                var targetWin = instances[t]
                if (targetWin && targetWin.screen && String(targetWin.screen.name || "") === targetName)
                    return targetWin
            }
        }
        var focusedName = Hyprland.focusedMonitor ? String(Hyprland.focusedMonitor.name || "") : ""
        for (var i = 0; i < count; i++) {
            var win = instances[i]
            if (win && win.screen && String(win.screen.name || "") === focusedName)
                return win
        }
        return count > 0 ? instances[0] : null
    }

    // 1. The Main Solid Dock Window (One layer surface per output, matching Omarchy bar)
    Variants {
        id: dockVariants
        model: Quickshell.screens

        delegate: Component {
            PanelWindow {
                id: dockLayer
                required property var modelData
                property alias surface: dockSurface
                property alias hoverHandler: dockHoverHandler
                // Per-screen slide state: this screen's own reveal state,
                // unless another screen is the current reveal target (in
                // which case this one stays/goes slid out even while
                // root.shouldSlideOut is false).
                readonly property bool slidOut: root.screenSlidesOut(modelData)
                screen: modelData
                visible: root.dockMapped && root.screenShowsDock(modelData) && !remapGuard.remapping

                ScreenMoveRemap {
                    id: remapGuard
                    window: dockLayer
                }

                WlrLayershell.namespace: "omarchy-dock"
                // Fullscreen windows stack above the Top layer, which would
                // leave an autohidden dock unreachable exactly when it is
                // summoned. Overlay keeps it callable there. In "always" mode
                // the dock is permanently on screen, so it stays on Top and
                // lets fullscreen content win.
                WlrLayershell.layer: root.autohide ? WlrLayer.Overlay : WlrLayer.Top
                WlrLayershell.keyboardFocus: root.isEditMode ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None
                exclusionMode: root.dockRevealed && !dockLayer.slidOut && !root.overlayMode ? ExclusionMode.Auto : ExclusionMode.Ignore
                color: "transparent"
                surfaceFormat.opaque: false

                // Input region. While the dock is slid out its card is
                // translated off the window and the HoverHandler below is
                // disabled, so claiming the whole window there only swallows
                // the outer edge of whatever is underneath -- a fullscreen
                // client, since autohide puts this window on the Overlay layer
                // -- for a dock that cannot be hovered anyway. Revealing it is
                // the separate edge trigger's job. Hand the strip back.
                mask: Region {
                    width: dockLayer.slidOut ? 0 : dockLayer.width
                    height: dockLayer.slidOut ? 0 : dockLayer.height
                }

                anchors {
                    top: root.barPosition === "bottom"
                    bottom: root.barPosition === "top"
                    left: root.windowsTaskbarMode && !root.isVertical ? true : root.barPosition === "right"
                    right: root.windowsTaskbarMode && !root.isVertical ? true : root.barPosition === "left"
                }

                margins {
                    bottom: root.windowsTaskbarMode && !root.isVertical ? 0 : ((!root.isVertical && root.barPosition === "top") ? (Style.gapsOut || 5) : 0)
                    top: root.windowsTaskbarMode && !root.isVertical ? 0 : ((!root.isVertical && root.barPosition === "bottom") ? (Style.gapsOut || 5) : 0)
                    right: root.windowsTaskbarMode && !root.isVertical ? 0 : ((root.isVertical && root.barPosition === "left") ? (Style.gapsOut || 5) : 0)
                    left: root.windowsTaskbarMode && !root.isVertical ? 0 : ((root.isVertical && root.barPosition === "right") ? (Style.gapsOut || 5) : 0)
                }

                implicitWidth: root.windowsTaskbarMode && !root.isVertical
                    ? 0
                    : (root.isVertical ? (root.slotSize + 8) : Math.max(root.slotSize + 8, root.totalDockDimension + 14))
                implicitHeight: root.isVertical ? Math.max(root.slotSize + 8, root.totalDockDimension + 14) : (root.slotSize + 8)

                Item {
                    id: dynamicTrayAnchorProxy
                    objectName: "dynamicTrayAnchorProxy"
                    visible: false
                    x: 0
                    y: 0
                    width: 24
                    height: 24
                }
                property alias dynamicTrayAnchorProxy: dynamicTrayAnchorProxy

                Item {
                    id: trayOverflowProxiesContainer
                    objectName: "trayOverflowProxiesContainer"
                    visible: root.trayOverflowOpened && trayOverflowPopup && trayOverflowPopup.opened

                    Repeater {
                        id: proxyRepeater
                        model: (root.trayOverflowOpened && trayOverflowPopup && trayOverflowPopup.opened)
                            ? trayOverflowPopup.trayItems : []

                        Item {
                            id: proxySlot
                            required property var modelData
                            required property int index
                            property var mapToItem: true

                            readonly property real slotSpan: (trayOverflowPopup ? trayOverflowPopup.itemSlotSize : 40) + (trayOverflowPopup ? trayOverflowPopup.itemSpacing : 2)
                            readonly property int col: (trayOverflowPopup && trayOverflowPopup.gridCols > 0) ? (index % trayOverflowPopup.gridCols) : 0
                            readonly property int row: (trayOverflowPopup && trayOverflowPopup.gridCols > 0) ? Math.floor(index / trayOverflowPopup.gridCols) : 0

                            readonly property real slotScreenX: (trayOverflowPopup ? trayOverflowPopup.cardX : 0) + (trayOverflowPopup ? trayOverflowPopup.gridPadding : 7) + col * slotSpan
                            readonly property real slotScreenY: (trayOverflowPopup ? trayOverflowPopup.cardY : 0) + (trayOverflowPopup ? trayOverflowPopup.gridPadding : 7) + row * slotSpan

                            readonly property real screenW: dockLayer.screen ? dockLayer.screen.width : 1920
                            readonly property real screenH: dockLayer.screen ? dockLayer.screen.height : 864
                            readonly property real dockW: dockLayer.width
                            readonly property real dockH: dockLayer.height

                            x: (root.dockScreenPosition === "right") ? (slotScreenX - screenW + dockW) : slotScreenX
                            y: (root.dockScreenPosition === "bottom") ? (slotScreenY - screenH + dockH) : slotScreenY
                            width: trayOverflowPopup ? trayOverflowPopup.itemSlotSize : 40
                            height: trayOverflowPopup ? trayOverflowPopup.itemSlotSize : 40
                            visible: true
                            opacity: 1

                            function triggerPress(button) {
                                var itemSlot = (trayOverflowPopup && typeof trayOverflowPopup.getItemSlot === "function")
                                    ? trayOverflowPopup.getItemSlot(index)
                                    : null
                                var anchor = itemSlot || proxySlot
                                if (button === Qt.RightButton && typeof modelData.rightAction === "function") {
                                    modelData.rightAction(anchor)
                                } else if (typeof modelData.action === "function") {
                                    modelData.action(anchor)
                                }
                            }
                        }

                        onCountChanged: root.updateTrayOverflowProxyTargets()
                    }
                }
                property alias proxyRepeater: proxyRepeater

                HoverHandler {
                    id: dockHoverHandler
                    enabled: root.autohide && !dockLayer.slidOut
                    onHoveredChanged: {
                        root.evaluateHoverState()
                    }
                }

                // Main Visual Dock Card
        Rectangle {
            id: dockSurface
            anchors.centerIn: parent
            width: root.windowsTaskbarMode && !root.isVertical
                ? parent.width
                : (root.isVertical ? (root.slotSize + 4) : Math.max(root.slotSize + 4, root.totalDockDimension + 8))
            height: root.windowsTaskbarMode && !root.isVertical
                ? parent.height
                : (root.isVertical ? Math.max(root.slotSize + 4, root.totalDockDimension + 8) : (root.slotSize + 4))
            visible: root.dockMapped
            opacity: root.isDockVisualReady ? 1.0 : 0.0
            Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
            focus: root.isEditMode

            Keys.onEscapePressed: function(event) {
                event.accepted = true
                if (root.isEditingFolderTitle) {
                    root.isEditingFolderTitle = false
                    return
                }
                if (root.isStackOpen) {
                    root.activeStackItem = null
                }
                root.isEditMode = false
            }

            color: root.isBarTransparent
                ? Util.alpha(Color.bar.background, 0.25)
                : Color.bar.background
            border.width: (!root.windowsTaskbarMode && Border.canUseNative(root.dockBorderSpec) && !root.isBarTransparent) ? Border.uniformWidth(root.dockBorderSpec) : 0
            border.color: (!root.windowsTaskbarMode && Border.canUseNative(root.dockBorderSpec) && !root.isBarTransparent) ? Border.color(root.dockBorderSpec) : "transparent"
            radius: root.windowsTaskbarMode ? 0 : root.systemRounding
            antialiasing: true
            smooth: true

            Loader {
                anchors.fill: parent
                active: !root.windowsTaskbarMode && !root.isBarTransparent && Border.needsOverlay(root.dockBorderSpec)
                sourceComponent: DockBorderOverlay {
                    anchors.fill: parent
                    radius: root.systemRounding
                    borderSpec: root.dockBorderSpec
                    animated: root.borderAngleAnimationEnabled
                    animationDuration: root.borderAngleAnimationDuration
                }
            }

            Behavior on color { ColorAnimation { duration: 300; easing.type: Easing.InOutCubic } }
            Behavior on border.color { ColorAnimation { duration: 300; easing.type: Easing.InOutCubic } }
            Behavior on border.width { NumberAnimation { duration: 250; easing.type: Easing.InOutCubic } }

            MouseArea {
                anchors.fill: parent
                z: -1
                acceptedButtons: Qt.LeftButton | Qt.RightButton
                cursorShape: (root.dockDragActiveIndex >= 0) ? Qt.BlankCursor : (root.isEditMode ? Qt.PointingHandCursor : Qt.ArrowCursor)
                onClicked: {
                    root.isEditMode = false
                    root.activeMenuItem = null
                    root.activeStackItem = null
                }
            }

            transform: Translate {
                id: autohideTranslate
                x: {
                    if (!dockLayer.slidOut) return 0
                    if (root.barPosition === "right") return -56
                    if (root.barPosition === "left") return 56
                    return 0
                }
                y: {
                    if (!dockLayer.slidOut) return 0
                    if (root.barPosition === "top") return 56
                    if (root.barPosition === "bottom") return -56
                    return 0
                }
                Behavior on x { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }
                Behavior on y { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }
            }

            Behavior on radius { NumberAnimation { duration: 200 } }

            Item {
                id: dockContent
                anchors.centerIn: parent
                width: root.windowsTaskbarMode && !root.isVertical ? parent.width : (root.isVertical ? root.slotSize : root.totalDockDimension)
                height: root.isVertical ? root.totalDockDimension : root.slotSize

                // 1. Left Dock Active Bar/Tray Widgets
                Repeater {
                    model: root.leftWidgetsList

                    Item {
                        id: leftWidgetSlotRoot
                        required property string modelData
                        required property int index

                        readonly property real widgetSlotDimension: (root.isClockWidget(modelData) && !root.isVertical) ? root.clockSlotWidth : root.slotSize
                        readonly property real widgetPos: root.getLeftWidgetOffset(index)
                        x: root.isVertical ? 0 : widgetPos
                        y: root.isVertical ? widgetPos : 0
                        width: root.isVertical ? root.slotSize : widgetSlotDimension
                        height: root.isVertical ? widgetSlotDimension : root.slotSize
                        z: 1

                        Item {
                            id: leftWidgetWrapper
                            anchors.centerIn: parent
                            width: (root.isClockWidget(modelData) && !root.isVertical) ? (leftWidgetSlotRoot.width - 10) : root.iconBaseSize
                            height: (root.isClockWidget(modelData) && root.isVertical) ? (root.slotSize - 8) : root.iconBaseSize
                            scale: root.isEditMode ? 0.82 : 1.0
                            Behavior on scale { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

                            Text {
                                id: leftClockHorizontalLabel
                                visible: root.isClockWidget(modelData) && !root.isVertical
                                anchors.centerIn: parent
                                text: (leftWidgetLoader.item && leftWidgetLoader.item.displayText) ? leftWidgetLoader.item.displayText : (root.clockDisplayText !== "" ? root.clockDisplayText : root.currentMinuteString)
                                textFormat: Text.PlainText
                                font.family: Style.font.family
                                font.pixelSize: 12
                                font.weight: Font.Medium
                                color: leftWidgetSlotMouse.containsMouse ? Color.accent : Color.composed("popups.text", "popups.text-alpha", Color.text, 0.95)
                                renderType: Text.CurveRendering
                                font.hintingPreference: Font.PreferNoHinting
                                Behavior on color { ColorAnimation { duration: 120 } }
                            }

                            Column {
                                id: leftClockVerticalCol
                                visible: root.isClockWidget(modelData) && root.isVertical
                                anchors.centerIn: parent
                                spacing: 1

                                Repeater {
                                    model: [root.currentHourString, root.currentMinutePart]

                                    Text {
                                        required property string modelData
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        text: modelData
                                        textFormat: Text.PlainText
                                        font.family: Style.font.family
                                        font.pixelSize: modelData.length > 3 ? 9 : 10
                                        font.weight: Font.Medium
                                        color: leftWidgetSlotMouse.containsMouse ? Color.accent : Color.composed("popups.text", "popups.text-alpha", Color.text, 0.95)
                                        renderType: Text.CurveRendering
                                        font.hintingPreference: Font.PreferNoHinting
                                    }
                                }
                            }

                            DockGlyph {
                                id: leftWidgetGlyph
                                visible: !root.isClockWidget(modelData)
                                anchors.centerIn: parent
                                width: root.iconBaseSize
                                height: root.iconBaseSize
                                text: {
                                    var _rev = root.widgetIconRevision
                                    var _v = root.pipewireSinkVolume
                                    var _m = root.pipewireSinkMuted
                                    var _sm = root.pipewireSourceMuted
                                    var _bp = root.upowerBatteryPercentage
                                    var _bs = root.upowerBatteryState
                                    var it = leftWidgetLoader.item
                                    var _ic = it ? (it.icon || it.displayText || it.playIcon || "") : ""
                                    return root.getWidgetIcon(modelData, it)
                                }
                                fontFamily: (leftWidgetLoader.item && leftWidgetLoader.item.fontFamily) ? leftWidgetLoader.item.fontFamily : ((leftWidgetLoader.item && leftWidgetLoader.item.font && leftWidgetLoader.item.font.family) ? leftWidgetLoader.item.font.family : Style.font.family)
                                fontSize: 22
                                color: leftWidgetSlotMouse.containsMouse ? Color.accent : Color.composed("popups.text", "popups.text-alpha", Color.text, 0.95)
                                Behavior on color { ColorAnimation { duration: 120 } }
                            }

                            Loader {
                                id: leftWidgetLoader
                                anchors.fill: parent
                                opacity: 0.0
                                // source and sourceComponent clear one another, so pick one
                                // imperatively instead of binding both. This runs on every
                                // registry revision (dozens during shell start-up); re-assigning
                                // an unchanged source would still tear the item down, so it
                                // returns early when nothing changed.
                                function applyWidgetSource() {
                                    var comp = root.getWidgetComponent(modelData)
                                    if (comp) {
                                        if (sourceComponent === comp) return
                                        source = ""
                                        sourceComponent = comp
                                        return
                                    }
                                    var url = root.getWidgetSource(modelData)
                                    if (url !== "" && String(source) === url) return
                                    sourceComponent = null
                                    source = url
                                }
                                Component.onCompleted: applyWidgetSource()
                                Connections {
                                    target: root
                                    function onWidgetRegistryRevisionChanged() { leftWidgetLoader.applyWidgetSource() }
                                }
                                onLoaded: {
                                    if (item) {
                                        root.configureHostedWidget(item, modelData, leftWidgetSlotRoot)
                                        if (root.isClockWidget(modelData)) {
                                            if (item.displayText !== undefined) root.clockDisplayText = item.displayText
                                            if (item.displayTextChanged) {
                                                item.displayTextChanged.connect(function() {
                                                    root.clockDisplayText = item.displayText
                                                })
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        MouseArea {
                            id: leftWidgetSlotMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
                            cursorShape: root.isEditMode ? Qt.ArrowCursor : Qt.PointingHandCursor
                            onClicked: function(mouse) {
                                root.activateWidget(modelData, leftWidgetLoader.item, leftWidgetSlotRoot, mouse)
                            }
                        }
                    }
                }

                // 2. Left Sleek Separator between Left Widgets and Apps
                Item {
                    id: leftDockSeparator
                    visible: root.hasLeftWidgets && (!root.windowsTaskbarMode || root.taskbarAppAlignment === "left")
                    opacity: root.hasLeftWidgets ? 1.0 : 0.0
                    x: root.isVertical ? 0 : root.leftWidgetsWidth
                    y: root.isVertical ? root.leftWidgetsWidth : 0
                    width: root.isVertical ? root.slotSize : root.leftSeparatorSize
                    height: root.isVertical ? root.leftSeparatorSize : root.slotSize
                    z: 0

                    Rectangle {
                        anchors.centerIn: parent
                        width: root.isVertical ? (root.slotSize - 18) : 1.5
                        height: root.isVertical ? 1.5 : (root.slotSize - 18)
                        radius: 0.75
                        color: Color.composed("popups.border", "popups.border-alpha", Color.border, 0.45)
                    }
                }

                // 3. Applications & Folders
                Repeater {
                    model: root.dockItems

                    DockItem {
                        itemData: modelData
                        itemIndex: index
                        totalCount: root.dockItems.length
                        barPosition: root.barPosition
                        shell: root.shell
                        slotSize: root.slotSize
                        iconBaseSize: root.iconBaseSize
                        iconRevision: root.iconRevision
                        iconsReady: root.iconsReady
                        systemBorderSize: root.systemBorderSize
                        systemRounding: root.systemRounding
                        isSelected: (!root.isMenuFromFolder && root.activeMenuItem && (root.activeMenuItem.appId === modelData.appId || root.activeMenuItem.id === modelData.id)) || (root.activeStackItem && (root.activeStackItem.id === modelData.id || root.activeStackItem.appId === modelData.appId))
                        isMergeTarget: (root.currentMergeTargetIndex === index)

                        // 1D Live Rail Displacement (with Left Widget offset)
                        readonly property real appBaseOffset: {
                            var leftMinimum = root.hasLeftWidgets ? (root.leftWidgetsWidth + root.leftSeparatorSize) : 0
                            if (!root.windowsTaskbarMode || root.isVertical) return leftMinimum
                            if (root.taskbarAppAlignment === "left") return leftMinimum
                            if (root.taskbarAppAlignment === "right") {
                                return Math.max(leftMinimum, dockContent.width - root.rightWidgetsWidth - root.rightSeparatorSize - root.itemsWidth)
                            }
                            return Math.max(leftMinimum, (dockContent.width - root.itemsWidth) / 2)
                        }
                        readonly property int visualSlot: (root.dockDragActiveIndex === index) ? index : root.getDockVisualSlot(index, root.dockDragActiveIndex, root.dockDragTargetIndex)
                        x: root.isVertical ? 0 : (appBaseOffset + visualSlot * root.slotSize)
                        y: root.isVertical ? (appBaseOffset + visualSlot * root.slotSize) : 0

                        Behavior on x { enabled: root.dockDragActiveIndex >= 0; NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }
                        Behavior on y { enabled: root.dockDragActiveIndex >= 0; NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }

                        isEditMode: root.isEditMode
                        showBadges: root.showBadges
                        dockDragActiveIndex: root.dockDragActiveIndex

                        onEditModeRequested: {
                            root.isEditMode = true
                            root.activeMenuItem = null
                        }

                        onEditModeExitRequested: {
                            root.isEditMode = false
                        }

                        onTogglePinRequested: function(appId) {
                            root.setPinned(DockModel.togglePinned(root.pinnedIds, appId, root.maxDockItems))
                        }

                        onOriginalAppLaunched: function(appId) {
                            root.requestFocusOnLaunch(appId)
                        }

                        onRestoreOrLaunchRequested: function(item, targetIndex) {
                            root.restoreOrLaunchItem(item, targetIndex)
                        }

                        onMinimizeRequested: function(item, targetIndex) {
                            root.minimizeItem(item, targetIndex)
                        }

                        onWindowListHoverChanged: function(hovered) {
                            root.isWindowListHovered = hovered
                            root.evaluateHoverState()
                        }

                        onDissolveRequested: function(stackId) {
                            root.setPinned(DockModel.dissolveStack(root.pinnedIds, stackId))
                            root.isEditMode = false
                        }

                        onItemLeftClicked: function(item) {
                            if (item && !item.isStack) {
                                root.clearBadge(item)
                            }
                            if (item && item.isStack) {
                                root.toggleStack(item, index)
                            } else {
                                root.activeStackItem = null
                                root.activeMenuItem = null
                                if (root.isEditMode) return
                            }
                        }

                        onItemRightClicked: function(item, targetItem) {
                            if (root.isEditMode) {
                                root.isEditMode = false
                                return
                            }
                            if (item && item.isStack) {
                                root.toggleMenu(item, index, false)
                                return
                            }
                            if (item) {
                                root.minimizeItem(item)
                            }
                        }

                        onDragStarted: function(fromIdx) {
                            root.dockDragActiveIndex = fromIdx
                        }

                        onDragHoverChanged: function(fromIdx, targetIdx, isMergeIntent) {
                            if (fromIdx < 0) {
                                root.dockDragActiveIndex = -1
                                root.dockDragTargetIndex = -1
                                root.currentMergeTargetIndex = -1
                                return
                            }
                            root.dockDragActiveIndex = fromIdx
                            root.dockDragTargetIndex = (targetIdx >= 0 && !isMergeIntent) ? targetIdx : -1
                            root.currentMergeTargetIndex = (targetIdx >= 0 && isMergeIntent) ? targetIdx : -1
                        }

                        onDragEnded: function() {
                            root.dockDragActiveIndex = -1
                            root.dockDragTargetIndex = -1
                            root.currentMergeTargetIndex = -1
                        }

                        onMoveRequested: function(fromIdx, toIdx) {
                            root.dockDragActiveIndex = -1
                            root.dockDragTargetIndex = -1
                            root.currentMergeTargetIndex = -1
                            root.setPinned(DockModel.reorderPinned(root.pinnedIds, root.dockItems, fromIdx, toIdx))
                        }

                        onMergeRequested: function(fromIdx, targetIdx) {
                            root.dockDragActiveIndex = -1
                            root.dockDragTargetIndex = -1
                            root.currentMergeTargetIndex = -1
                            root.setPinned(DockModel.mergeIntoStack(root.pinnedIds, root.dockItems, fromIdx, targetIdx, root.appRows))
                        }
                    }
                }

                // 4. Right Sleek Separator between Apps and Right Widgets
                Item {
                    id: rightDockSeparator
                    visible: root.hasRightWidgets
                    opacity: root.hasRightWidgets ? 1.0 : 0.0
                    readonly property real rSepOffset: root.windowsTaskbarMode && !root.isVertical
                        ? dockContent.width - root.rightWidgetsWidth - root.rightSeparatorSize
                        : ((root.hasLeftWidgets ? (root.leftWidgetsWidth + root.leftSeparatorSize) : 0) + root.itemsWidth)
                    x: root.isVertical ? 0 : rSepOffset
                    y: root.isVertical ? rSepOffset : 0
                    width: root.isVertical ? root.slotSize : root.rightSeparatorSize
                    height: root.isVertical ? root.rightSeparatorSize : root.slotSize
                    z: 0

                    Rectangle {
                        anchors.centerIn: parent
                        width: root.isVertical ? (root.slotSize - 18) : 1.5
                        height: root.isVertical ? 1.5 : (root.slotSize - 18)
                        radius: 0.75
                        color: Color.composed("popups.border", "popups.border-alpha", Color.border, 0.45)
                    }
                }

                // 5. Right Dock Active Bar/Tray Widgets
                Repeater {
                    model: root.rightWidgetsList

                    Item {
                        id: rightWidgetSlotRoot
                        required property string modelData
                        required property int index

                        readonly property real rWidgetBaseOffset: root.windowsTaskbarMode && !root.isVertical
                            ? dockContent.width - root.rightWidgetsWidth
                            : ((root.hasLeftWidgets ? (root.leftWidgetsWidth + root.leftSeparatorSize) : 0) + root.itemsWidth + root.rightSeparatorSize)
                        readonly property real rWidgetSlotDimension: root.getRightWidgetDimension(modelData)
                        readonly property real rWidgetPos: rWidgetBaseOffset + root.getRightWidgetOffset(index)
                        x: root.isVertical ? 0 : rWidgetPos
                        y: root.isVertical ? rWidgetPos : 0
                        width: root.isVertical ? root.slotSize : rWidgetSlotDimension
                        height: root.isVertical ? rWidgetSlotDimension : root.slotSize
                        z: 1

                        // 1. System Icon Tray (Windows Notification Area & Chevron Flyout)
                        SystemIconTray {
                            id: systemIconTrayItem
                            visible: root.isTrayWidget(modelData)
                            anchors.fill: parent
                            dockPanel: root
                            dockWindow: root ? root.dockWindow : null
                        }

                        // 2. Windows Show Desktop Button (Far Right Corner Sliver)
                        Item {
                            id: showDesktopItem
                            visible: root.isDesktopWidget(modelData)
                            anchors.fill: parent

                            Rectangle {
                                width: 1
                                anchors.top: parent.top
                                anchors.bottom: parent.bottom
                                anchors.margins: 10
                                anchors.left: parent.left
                                color: Color.composed("popups.border", "popups.border-alpha", Color.outline, 0.3)
                            }

                            Rectangle {
                                anchors.fill: parent
                                anchors.leftMargin: 2
                                color: desktopMouse.containsMouse
                                    ? Color.composed("popups.hover", "popups.hover-alpha", Color.outline, 0.25)
                                    : "transparent"
                                Behavior on color { ColorAnimation { duration: 120 } }
                            }

                            MouseArea {
                                id: desktopMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onEntered: {
                                    root.showRightTooltip(desktopMouse, "Mostrar área de trabalho")
                                }
                                onExited: {
                                    root.hideRightTooltip(desktopMouse)
                                }
                                onClicked: {
                                    root.hideRightTooltip(desktopMouse)
                                    Util.execDetached("hyprctl dispatch 'hl.dsp.workspace.toggle_special()'")
                                }
                            }
                        }

                        // 3. Standard Widget Wrapper (Clock & Other Individual Widgets)
                        Item {
                            id: rightWidgetWrapper
                            visible: !root.isTrayWidget(modelData) && !root.isDesktopWidget(modelData)
                            anchors.centerIn: parent
                            width: (root.isClockWidget(modelData) && !root.isVertical) ? (rightWidgetSlotRoot.width - 10) : root.iconBaseSize
                            height: (root.isClockWidget(modelData) && root.isVertical) ? (root.slotSize - 8) : root.iconBaseSize
                            scale: root.isEditMode ? 0.82 : 1.0
                            Behavior on scale { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

                            Text {
                                id: rightClockHorizontalLabel
                                visible: root.isClockWidget(modelData) && !root.isVertical
                                anchors.centerIn: parent
                                text: (rightWidgetLoader.item && rightWidgetLoader.item.displayText) ? rightWidgetLoader.item.displayText : (root.clockDisplayText !== "" ? root.clockDisplayText : root.currentMinuteString)
                                textFormat: Text.PlainText
                                font.family: Style.font.family
                                font.pixelSize: 12
                                font.weight: Font.Medium
                                color: rightWidgetSlotMouse.containsMouse ? Color.accent : Color.composed("popups.text", "popups.text-alpha", Color.text, 0.95)
                                renderType: Text.CurveRendering
                                font.hintingPreference: Font.PreferNoHinting
                                Behavior on color { ColorAnimation { duration: 120 } }
                            }

                            Column {
                                id: rightClockVerticalCol
                                visible: root.isClockWidget(modelData) && root.isVertical
                                anchors.centerIn: parent
                                spacing: 1

                                Repeater {
                                    model: [root.currentHourString, root.currentMinutePart]

                                    Text {
                                        required property string modelData
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        text: modelData
                                        textFormat: Text.PlainText
                                        font.family: Style.font.family
                                        font.pixelSize: modelData.length > 3 ? 9 : 10
                                        font.weight: Font.Medium
                                        color: rightWidgetSlotMouse.containsMouse ? Color.accent : Color.composed("popups.text", "popups.text-alpha", Color.text, 0.95)
                                        renderType: Text.CurveRendering
                                        font.hintingPreference: Font.PreferNoHinting
                                    }
                                }
                            }

                            DockGlyph {
                                id: rightWidgetGlyph
                                visible: !root.isClockWidget(modelData) && !root.isTrayWidget(modelData) && !root.isDesktopWidget(modelData)
                                anchors.centerIn: parent
                                width: root.iconBaseSize
                                height: root.iconBaseSize
                                text: {
                                    var _rev = root.widgetIconRevision
                                    var _v = root.pipewireSinkVolume
                                    var _m = root.pipewireSinkMuted
                                    var _sm = root.pipewireSourceMuted
                                    var _bp = root.upowerBatteryPercentage
                                    var _bs = root.upowerBatteryState
                                    var it = rightWidgetLoader.item
                                    var _ic = it ? (it.icon || it.displayText || it.playIcon || "") : ""
                                    return root.getWidgetIcon(modelData, it)
                                }
                                fontFamily: (rightWidgetLoader.item && rightWidgetLoader.item.fontFamily) ? rightWidgetLoader.item.fontFamily : ((rightWidgetLoader.item && rightWidgetLoader.item.font && rightWidgetLoader.item.font.family) ? rightWidgetLoader.item.font.family : Style.font.family)
                                fontSize: 22
                                color: rightWidgetSlotMouse.containsMouse ? Color.accent : Color.composed("popups.text", "popups.text-alpha", Color.text, 0.95)
                                Behavior on color { ColorAnimation { duration: 120 } }
                            }

                            Loader {
                                id: rightWidgetLoader
                                anchors.fill: parent
                                opacity: 0.0
                                function applyWidgetSource() {
                                    if (root.isTrayWidget(modelData) || root.isDesktopWidget(modelData)) return
                                    var comp = root.getWidgetComponent(modelData)
                                    if (comp) {
                                        if (sourceComponent === comp) return
                                        source = ""
                                        sourceComponent = comp
                                        return
                                    }
                                    var url = root.getWidgetSource(modelData)
                                    if (url !== "" && String(source) === url) return
                                    sourceComponent = null
                                    source = url
                                }
                                Component.onCompleted: applyWidgetSource()
                                Connections {
                                    target: root
                                    function onWidgetRegistryRevisionChanged() { rightWidgetLoader.applyWidgetSource() }
                                }
                                onLoaded: {
                                    if (item) {
                                        root.configureHostedWidget(item, modelData, rightWidgetSlotRoot)
                                        if (root.isClockWidget(modelData)) {
                                            if (item.displayText !== undefined) root.clockDisplayText = item.displayText
                                            if (item.displayTextChanged) {
                                                item.displayTextChanged.connect(function() {
                                                    root.clockDisplayText = item.displayText
                                                })
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        MouseArea {
                            id: rightWidgetSlotMouse
                            visible: !root.isTrayWidget(modelData) && !root.isDesktopWidget(modelData)
                            anchors.fill: parent
                            hoverEnabled: true
                            acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
                            cursorShape: root.isEditMode ? Qt.ArrowCursor : Qt.PointingHandCursor
                            onEntered: {
                                var txt = root.isClockWidget(modelData)
                                    ? Qt.formatDate(new Date(), "dddd, d 'de' MMMM 'de' yyyy")
                                    : (rightWidgetLoader.item && rightWidgetLoader.item.tooltipText ? rightWidgetLoader.item.tooltipText : modelData)
                                root.showRightTooltip(rightWidgetSlotMouse, txt)
                            }
                            onExited: {
                                root.hideRightTooltip(rightWidgetSlotMouse)
                            }
                            onClicked: function(mouse) {
                                root.hideRightTooltip(rightWidgetSlotMouse)
                                root.activateWidget(modelData, rightWidgetLoader.item, rightWidgetSlotRoot, mouse)
                            }
                        }
                    }
                }
            }
        }

                PopupWindow {
                    id: rightTooltipPopup
                    visible: root.activeRightTooltipTarget !== null && root.activeRightTooltipText !== "" && !root.trayOverflowOpened && !calendarPopup.opened
                    color: "transparent"
                    implicitWidth: Math.ceil(bubble.implicitWidth)
                    implicitHeight: Math.ceil(bubble.implicitHeight)

                    function updatePosition() {
                        var target = root.activeRightTooltipTarget
                        if (!target || !dockLayer || !dockLayer.contentItem) return
                        var popupW = rightTooltipPopup.implicitWidth
                        var targetPt = dockLayer.contentItem.mapFromItem(target, 0, 0)
                        var targetCenterX = targetPt.x + (target.width / 2)
                        var rx = targetCenterX - (popupW / 2)
                        if (rx + popupW > dockLayer.width - 6) rx = dockLayer.width - popupW - 6
                        if (rx < 6) rx = 6
                        rightTooltipAnchor.rect.x = Math.round(rx)
                        rightTooltipAnchor.rect.y = root.systemTrayPopupAnchorY
                    }

                    Connections {
                        target: root
                        function onActiveRightTooltipTargetChanged() {
                            rightTooltipPopup.updatePosition()
                        }
                        function onActiveRightTooltipTextChanged() {
                            rightTooltipPopup.updatePosition()
                        }
                    }

                    anchor {
                        id: rightTooltipAnchor
                        window: dockLayer
                        adjustment: PopupAdjustment.None
                        edges: Edges.Top | Edges.Left
                        gravity: Edges.Top | Edges.Right
                        rect.width: 1
                        rect.height: 1

                        onAnchoring: {
                            rightTooltipPopup.updatePosition()
                        }
                    }

                    Rectangle {
                        id: bubble
                        anchors.top: parent.top
                        anchors.horizontalCenter: parent.horizontalCenter
                        implicitWidth: bubbleLabel.implicitWidth + 12
                        implicitHeight: bubbleLabel.implicitHeight + 8
                        radius: 4
                        color: Util.alpha(Color.popups.background, 0.90)
                        border.width: 1
                        border.color: Color.composed("popups.border", "popups.border-alpha", Color.outline, 0.40)

                        Text {
                            id: bubbleLabel
                            anchors.centerIn: parent
                            textFormat: Text.PlainText
                            text: root.activeRightTooltipText
                            font.family: Style.font.family
                            font.pixelSize: 10
                            color: Color.composed("popups.text", "popups.text-alpha", Color.text, 0.95)
                        }
                    }
                }
            }
        }
    }

    // 2. The Isolated Action Card Popup Overlay Window (Folder Icon Picker)
    FolderMenu {
        id: menuWindow
        root: root
        dockWindow: root.dockWindow
        stackWindow: stackWindow
    }

    // 3. macOS Stacks Folder Grid Overlay Window (Folder Contents Popup)
    FolderPopup {
        id: stackWindow
        root: root
        dockWindow: root.dockWindow
    }

    // 4. Widget Picker Popup Menu
    WidgetPickerPopup {
        id: widgetPicker
        root: root
        dockWindow: root.dockWindow
        shell: root.shell
    }

    // 5. Windows Taskbar Clock Calendar Popup
    DockCalendarPopup {
        id: calendarPopup
        root: root
        dockWindow: root.dockWindow
    }

    // 6. Windows Taskbar System Tray Settings Modal
    SystemTraySettingsModal {
        id: systemTraySettingsModal
        root: root
        dockWindow: root ? root.dockWindow : null
    }

    // 7. Windows Taskbar System Tray Overflow Popup
    TrayOverflowPopup {
        id: trayOverflowPopup
        dockPanel: root
        dockWindow: root ? root.dockWindow : null
    }

    Loader {
        id: systemTrayPanelLoader
        active: false
        onLoaded: root.activatePendingTrayPanel()
    }

    Loader {
        id: floatingModeTrayLoader
        active: false
        opacity: 0
        x: root.systemTrayAnchorItem ? root.systemTrayAnchorItem.mapToItem(root, 0, 0).x : 0
        y: root.systemTrayAnchorItem ? root.systemTrayAnchorItem.mapToItem(root, 0, 0).y : 0
        width: root.systemTrayAnchorItem ? root.systemTrayAnchorItem.width : root.slotSize
        height: root.systemTrayAnchorItem ? root.systemTrayAnchorItem.height : root.slotSize
        onLoaded: {
            if (!item) return
            root.configureHostedWidget(item, "io.github.rawritude.floating-mode", root.systemTrayAnchorItem, true)
            if (root.pendingFloatingSettings && "settingsOpen" in item) item.settingsOpen = true
            root.pendingFloatingSettings = false
        }
    }

    // 5. Autohide Edge Trigger — thin invisible strip at screen edge, activates dock reveal
    //    Recreate its input handler after each reveal so stale hover state cannot block re-arming.
    Variants {
        id: edgeVariants
        model: Quickshell.screens

        delegate: Component {
            PanelWindow {
                id: edgeTriggerWindow
                required property var modelData
                screen: modelData
                visible: root.dockAvailable
                         && (root.visibilityMode === "hover" || root.visibilityMode === "hybrid")
                         && root.screenSlidesOut(modelData)
                         && root.screenShowsDock(modelData)

                WlrLayershell.namespace: "omarchy-dock-edge"
                // The reveal trigger only exists while autohide is on, and it
                // has to catch the pointer over a fullscreen window.
                WlrLayershell.layer: WlrLayer.Overlay
                WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
                exclusionMode: ExclusionMode.Ignore
                color: "transparent"
                mask: Region { item: edgeTriggerLoader }

                // Anchor to the same edge as the dock, no margins — hug the screen edge
                anchors {
                    top:    root.dockScreenPosition === "top"
                    bottom: root.dockScreenPosition === "bottom"
                    left:   root.dockScreenPosition === "left"
                    right:  root.dockScreenPosition === "right"
                }

                margins {
                    top: 0
                    bottom: 0
                    left: 0
                    right: 0
                }

                implicitWidth:  root.isVertical ? root.effectiveAutohideEdgeDepth : Math.max(root.slotSize + 8, root.totalDockDimension + 14)
                implicitHeight: root.isVertical ? Math.max(root.slotSize + 8, root.totalDockDimension + 14) : root.effectiveAutohideEdgeDepth

                Loader {
                    id: edgeTriggerLoader
                    anchors.fill: parent
                    active: edgeTriggerWindow.visible

                    sourceComponent: Component {
                        MouseArea {
                            anchors.fill: parent
                            hoverEnabled: true
                            acceptedButtons: Qt.NoButton
                            onEntered: {
                                // Cursor reached the screen edge — reset keyboard override and show dock
                                if (root.visibilityOverride === DockSettings.VISIBILITY_OVERRIDE_HIDDEN) {
                                    root.visibilityOverride = DockSettings.VISIBILITY_OVERRIDE_FOLLOW
                                }
                                root.revealMonitorName = edgeTriggerWindow.modelData ? String(edgeTriggerWindow.modelData.name || "") : ""
                                root.isDockHovered = true
                                autohideLeaveTimer.restart()
                            }
                        }
                    }
                }
            }
        }
    }
}

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import qs.Commons
import qs.Ui
import ".."

PanelWindow {
    id: overflowWindow

    property var dockPanel: null
    property var dockWindow: null
    property bool opened: false

    screen: overflowWindow.dockWindow ? overflowWindow.dockWindow.screen : (Quickshell.screens && Quickshell.screens.length > 0 ? Quickshell.screens[0] : null)
    visible: opened

    readonly property real cardX: card ? card.x : 0
    readonly property real cardY: card ? card.y : 0
    readonly property real cardWidth: card ? card.width : 0
    readonly property real cardHeight: card ? card.height : 0
    readonly property var cardItem: card

    onOpenedChanged: {
        console.log("WinDoc TrayOverflowPopup: opened ->", opened, "visible ->", visible)
        if (opened) {
            card.forceActiveFocus()
            mouseHasBeenNear = false
            var cx = dockPanel ? (dockPanel.systemTrayChevronAnchorX > 0 ? dockPanel.systemTrayChevronAnchorX : dockPanel.systemTrayAnchorX) : -1
            if (cx > 0) fixedCenterX = cx
            if (dockPanel && typeof dockPanel.updateTrayOverflowProxyTargets === "function") {
                Qt.callLater(dockPanel.updateTrayOverflowProxyTargets)
            }
        } else {
            mouseHasBeenNear = false
            fixedCenterX = -1
            if (dockPanel && typeof dockPanel.updateTrayOverflowProxyTargets === "function") {
                Qt.callLater(dockPanel.updateTrayOverflowProxyTargets)
            }
        }
    }

    WlrLayershell.namespace: "omarchy-dock-tray-overflow"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: overflowWindow.opened ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    color: "transparent"

    anchors {
        top: true
        bottom: true
        left: true
        right: true
    }

    readonly property bool isOverlay: dockPanel ? (dockPanel.overlayMode === true) : false
    readonly property int dockHeight: (dockPanel && dockPanel.windowsTaskbarMode && !dockPanel.isVertical && overflowWindow.dockWindow)
        ? overflowWindow.dockWindow.height
        : (dockPanel ? (dockPanel.slotSize + 8) : 50)
    readonly property real popupAnchorY: dockPanel ? dockPanel.systemTrayPopupAnchorY : 12
    readonly property bool dockAtTop: dockPanel ? dockPanel.dockScreenPosition === "top" : false

    property bool mouseHasBeenNear: false
    property real fixedCenterX: -1

    function transferClick(clickX, clickY, clickBtn) {
        var btn = clickBtn || Qt.LeftButton
        var isTop = dockPanel ? (dockPanel.dockScreenPosition === "top") : false
        var screenH = overflowWindow.height
        var dockH = overflowWindow.dockHeight

        var inDock = isTop ? (clickY <= dockH) : (clickY >= (screenH - dockH))

        if (inDock && dockPanel) {
            if (typeof dockPanel.handleExternalClick === "function") {
                dockPanel.handleExternalClick(clickX, clickY, btn)
            }
            return
        }

        var toplevels = (typeof Hyprland !== "undefined" && Hyprland.toplevels && Hyprland.toplevels.values)
            ? Hyprland.toplevels.values
            : []
        var currentWsId = (typeof Hyprland !== "undefined" && Hyprland.focusedWorkspace)
            ? Hyprland.focusedWorkspace.id
            : -1

        var candidate = null
        for (var i = 0; i < toplevels.length; i++) {
            var top = toplevels[i]
            if (!top) continue
            var ipc = top.lastIpcObject
            if (!ipc || ipc.hidden === true || ipc.mapped === false) continue
            if (ipc.workspace && currentWsId !== -1 && ipc.workspace.id !== currentWsId) continue

            var at = ipc.at
            var size = ipc.size
            if (at && size && at.length >= 2 && size.length >= 2) {
                var wx = at[0]
                var wy = at[1]
                var ww = size[0]
                var wh = size[1]
                if (clickX >= wx && clickX <= wx + ww && clickY >= wy && clickY <= wy + wh) {
                    if (!candidate) {
                        candidate = top
                    } else if (ipc.floating === true && (!candidate.lastIpcObject || candidate.lastIpcObject.floating !== true)) {
                        candidate = top
                    }
                }
            }
        }

        if (candidate) {
            if (candidate.wayland && typeof candidate.wayland.activate === "function") {
                try { candidate.wayland.activate() } catch (e) {}
            } else if (typeof candidate.activate === "function") {
                try { candidate.activate() } catch (e) {}
            }
            if (candidate.address) {
                var addr = String(candidate.address)
                if (addr.indexOf("0x") !== 0) addr = "0x" + addr
                Util.execDetached("hyprctl dispatch focuswindow address:" + addr)
            }
        }
    }

    function isInsideCard(screenX, screenY) {
        if (!opened || !card) return false
        return screenX >= card.x && screenX <= (card.x + card.width) &&
               screenY >= card.y && screenY <= (card.y + card.height)
    }

    function handleCardClick(screenX, screenY, button) {
        if (!isInsideCard(screenX, screenY)) return false

        var relX = screenX - card.x
        var relY = screenY - card.y

        var gridX = (card.width - grid.width) / 2
        var gridY = (card.height - grid.height) / 2

        var localX = relX - gridX
        var localY = relY - gridY

        if (localX < 0 || localX > grid.width || localY < 0 || localY > grid.height) {
            return true
        }

        var slotSpan = overflowWindow.itemSlotSize + overflowWindow.itemSpacing
        var col = Math.floor(localX / slotSpan)
        var row = Math.floor(localY / slotSpan)

        if (col < 0) col = 0
        if (col >= overflowWindow.gridCols) col = overflowWindow.gridCols - 1
        if (row < 0) row = 0
        if (row >= overflowWindow.gridRows) row = overflowWindow.gridRows - 1

        var idx = row * overflowWindow.gridCols + col
        if (idx >= 0 && idx < overflowWindow.trayItems.length) {
            var item = overflowWindow.trayItems[idx]
            if (item) {
                var itemSlot = (itemRepeater && itemRepeater.count > idx) ? itemRepeater.itemAt(idx) : null
                if (button === Qt.RightButton && typeof item.rightAction === "function") {
                    item.rightAction(itemSlot)
                } else if (typeof item.action === "function") {
                    item.action(itemSlot)
                }
                return true
            }
        }
        return true
    }

    // Dismissal Area:
    // 1. Closes automatically if cursor moves >= 100px away from card in any direction.
    // 2. Closes and forwards/transfers the click if user clicks anywhere outside card.
    MouseArea {
        id: dismissArea
        anchors.fill: parent
        z: 0
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton

        onPositionChanged: function(mouse) {
            var dx = 0
            if (mouse.x < card.x) {
                dx = card.x - mouse.x
            } else if (mouse.x > card.x + card.width) {
                dx = mouse.x - (card.x + card.width)
            }

            var dy = 0
            if (mouse.y < card.y) {
                dy = card.y - mouse.y
            } else if (mouse.y > card.y + card.height) {
                dy = mouse.y - (card.y + card.height)
            }

            var isNear = (dx < 100 && dy < 100)
            if (isNear) {
                overflowWindow.mouseHasBeenNear = true
            }

            if (overflowWindow.mouseHasBeenNear && (dx >= 100 || dy >= 100)) {
                overflowWindow.opened = false
            }
        }

        onClicked: function(mouse) {
            overflowWindow.opened = false
            overflowWindow.transferClick(mouse.x, mouse.y, mouse.button)
        }
    }

    readonly property var pinnedWidgets: (dockPanel && dockPanel.systemTrayPinnedWidgets && Array.isArray(dockPanel.systemTrayPinnedWidgets))
        ? dockPanel.systemTrayPinnedWidgets
        : []

    // Full catalog of available tray items (Display widget is omarchy.monitor; settings is tray.settings)
    readonly property var allTrayItems: [
        {
            id: "omarchy.audio",
            name: "Volume e Áudio",
            icon: "󰕾",
            action: function(anchorItem) {
                if (dockPanel && typeof dockPanel.toggleTrayWidget === "function") {
                    dockPanel.toggleTrayWidget("omarchy.audio", anchorItem || dockPanel.systemTrayAnchorItem, Qt.LeftButton)
                } else {
                    Util.execDetached("omarchy-shell shell toggle omarchy.audio")
                }
            },
            rightAction: function(anchorItem) {
                Util.execDetached("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle")
            },
            scrollAction: function(delta) {
                if (delta > 0) Util.execDetached("wpctl set-volume @DEFAULT_AUDIO_SINK@ 2%+")
                else if (delta < 0) Util.execDetached("wpctl set-volume @DEFAULT_AUDIO_SINK@ 2%-")
            }
        },
        {
            id: "omarchy.network",
            name: "Rede e Conexões",
            icon: "󰖩",
            action: function(anchorItem) {
                if (dockPanel && typeof dockPanel.toggleTrayWidget === "function") {
                    dockPanel.toggleTrayWidget("omarchy.network", anchorItem || dockPanel.systemTrayAnchorItem, Qt.LeftButton)
                } else {
                    Util.execDetached("omarchy-shell shell toggle omarchy.network")
                }
            },
            rightAction: function(anchorItem) {
                Util.execDetached("omarchy-launch-floating-terminal-with-presentation nmtui")
            }
        },
        {
            id: "brunoma.agents",
            name: "Consumo de Agentes IA",
            icon: "󰚩",
            action: function(anchorItem) {
                if (dockPanel && typeof dockPanel.toggleTrayWidget === "function") {
                    dockPanel.toggleTrayWidget("brunoma.agents", anchorItem || dockPanel.systemTrayAnchorItem, Qt.LeftButton)
                } else {
                    Util.execDetached("omarchy-shell shell toggle brunoma.agents")
                }
            }
        },
        {
            id: "omarchy.weather",
            name: "Previsão do Tempo",
            icon: "󰖐",
            action: function(anchorItem) {
                if (dockPanel && typeof dockPanel.toggleTrayWidget === "function") {
                    dockPanel.toggleTrayWidget("omarchy.weather", anchorItem || dockPanel.systemTrayAnchorItem, Qt.LeftButton)
                }
            },
            rightAction: function(anchorItem) {
                Util.execDetached("omarchy-notification-send \"$(omarchy-weather-status)\"")
            }
        },
        {
            id: "omarchy.monitor",
            name: "Telas e Display",
            icon: "󰍹",
            action: function(anchorItem) {
                if (dockPanel && typeof dockPanel.toggleTrayWidget === "function")
                    dockPanel.toggleTrayWidget("omarchy.monitor", anchorItem || dockPanel.systemTrayAnchorItem, Qt.LeftButton)
            }
        },
        {
            id: "tray.settings",
            name: "Configurações da Bandeja",
            icon: "󰒓",
            action: function(anchorItem) {
                if (dockPanel && typeof dockPanel.openSystemTraySettings === "function") {
                    dockPanel.openSystemTraySettings()
                }
            }
        }
    ]

    // Mutual Exclusion & Deduplication Rule:
    // Any widget pinned/visible on the taskbar is strictly excluded from the overflow popup.
    // In addition, duplicate item IDs are deterministically ignored.
    readonly property var trayItems: {
        var list = []
        var seen = {}
        var pinned = pinnedWidgets || []
        for (var i = 0; i < allTrayItems.length; i++) {
            var item = allTrayItems[i]
            if (!item || !item.id) continue
            if (seen[item.id]) continue
            seen[item.id] = true
            if (item.id !== "tray.settings" && pinned.indexOf(item.id) !== -1) {
                continue
            }
            list.push(item)
        }
        return list
    }

    readonly property int totalItems: trayItems.length
    readonly property int gridCols: Math.max(1, Math.min(totalItems, 5))
    readonly property int gridRows: Math.max(1, Math.ceil(totalItems / gridCols))

    // Spacing and sizing tokens
    // Standard tray icon size matches pinned taskbar glyphs (17px)
    readonly property real iconPixelSize: 17
    // Spacing between icons matches taskbar slot spacing (2px)
    readonly property real itemSpacing: 2
    // Padding inside the card/grid reduced to 7px (total 14px) for a compact 10% smaller pop-up
    readonly property real gridPadding: 7
    // Slot size reduced by 10% (44px -> 40px)
    readonly property real itemSlotSize: 40

    // The Floating Acrylic Popup Card
    Rectangle {
        id: card
        z: 1
        focus: true
        Keys.onEscapePressed: function(event) {
            event.accepted = true
            overflowWindow.opened = false
        }
        anchors.top: overflowWindow.dockAtTop ? parent.top : undefined
        anchors.bottom: overflowWindow.dockAtTop ? undefined : parent.bottom
        anchors.topMargin: overflowWindow.dockAtTop ? overflowWindow.popupAnchorY : 0
        anchors.bottomMargin: overflowWindow.dockAtTop ? 0 : Math.max(0, overflowWindow.dockHeight - overflowWindow.popupAnchorY)
        x: {
            var centerX = overflowWindow.fixedCenterX > 0
                ? overflowWindow.fixedCenterX
                : (dockPanel ? (dockPanel.systemTrayChevronAnchorX > 0 ? dockPanel.systemTrayChevronAnchorX : dockPanel.systemTrayAnchorX) : -1)
            if (centerX < 0) centerX = parent.width - width / 2 - 8
            return Math.round(Math.max(6, Math.min(centerX - width / 2, parent.width - width - 6)))
        }

        width: Math.round((overflowWindow.gridCols * overflowWindow.itemSlotSize) + ((overflowWindow.gridCols - 1) * overflowWindow.itemSpacing) + (overflowWindow.gridPadding * 2))
        height: Math.round((overflowWindow.gridRows * overflowWindow.itemSlotSize) + ((overflowWindow.gridRows - 1) * overflowWindow.itemSpacing) + (overflowWindow.gridPadding * 2))
        radius: 10
        color: Color.popups.background
        border.width: 1
        border.color: Color.composed("popups.border", "popups.border-alpha", Color.outline, 0.28)

        // Drop shadow feel via subtle inner glow
        Rectangle {
            anchors.fill: parent
            radius: 10
            color: "transparent"
            border.width: 1
            border.color: Color.composed("popups.highlight", "popups.highlight-alpha", Color.text, 0.08)
        }

        // Catch clicks inside card so they don't dismiss the window
        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            onEntered: {
                overflowWindow.mouseHasBeenNear = true
            }
            onClicked: {}
        }

        Grid {
            id: grid
            anchors.centerIn: parent
            columns: overflowWindow.gridCols
            rowSpacing: overflowWindow.itemSpacing
            columnSpacing: overflowWindow.itemSpacing

            Repeater {
                id: itemRepeater
                model: overflowWindow.trayItems

                Rectangle {
                    id: itemSlot
                    required property var modelData
                    required property int index

                    z: itemMouse.containsMouse ? 100 : 1
                    width: overflowWindow.itemSlotSize
                    height: overflowWindow.itemSlotSize
                    radius: 6
                    color: itemMouse.containsMouse
                        ? Color.composed("popups.hover", "popups.hover-alpha", Color.outline, 0.2)
                        : "transparent"
                    Behavior on color { ColorAnimation { duration: 120 } }

                    Text {
                        id: glyph
                        anchors.centerIn: parent
                        textFormat: Text.PlainText
                        text: {
                            if (modelData.id === "omarchy.audio") {
                                if (dockPanel && dockPanel.pipewireSinkMuted) return "󰝟"
                                var vol = dockPanel ? dockPanel.pipewireSinkVolume : 0.5
                                if (vol <= 0.01) return "󰝟"
                                if (vol < 0.33) return "󰕿"
                                if (vol < 0.66) return "󰖀"
                                return "󰕾"
                            }
                            return modelData.icon || "󰒓"
                        }
                        font.pixelSize: overflowWindow.iconPixelSize
                        font.family: Style.font.family
                        color: itemMouse.containsMouse
                            ? Color.accent
                            : Color.composed("popups.text", "popups.text-alpha", Color.text, 0.95)
                        Behavior on color { ColorAnimation { duration: 120 } }
                    }

                    MouseArea {
                        id: itemMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        acceptedButtons: Qt.LeftButton | Qt.RightButton
                        cursorShape: Qt.PointingHandCursor
                        onClicked: function(mouse) {
                            if (mouse.button === Qt.RightButton && typeof modelData.rightAction === "function") {
                                modelData.rightAction(itemSlot)
                            } else if (typeof modelData.action === "function") {
                                modelData.action(itemSlot)
                            }
                        }
                        onWheel: function(wheel) {
                            if (typeof modelData.scrollAction === "function") {
                                modelData.scrollAction(wheel.angleDelta.y)
                            }
                        }
                    }

                    Rectangle {
                        id: itemTooltip
                        visible: itemMouse.containsMouse
                        z: 9999
                        anchors.bottom: parent.top
                        anchors.bottomMargin: 6
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: tipLabel.implicitWidth + 11
                        height: tipLabel.implicitHeight + 6
                        radius: 4
                        color: Util.alpha(Color.popups.background, 0.90)
                        border.width: 1
                        border.color: Color.composed("popups.border", "popups.border-alpha", Color.outline, 0.40)

                        Text {
                            id: tipLabel
                            anchors.centerIn: parent
                            textFormat: Text.PlainText
                            text: modelData.name
                            font.family: Style.font.family
                            font.pixelSize: 10
                            color: Color.composed("popups.text", "popups.text-alpha", Color.text, 0.95)
                        }
                    }
                }
            }
        }
    }
}

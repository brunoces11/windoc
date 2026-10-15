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

    onOpenedChanged: {
        console.log("WinDoc TrayOverflowPopup: opened ->", opened, "visible ->", visible)
        if (opened) card.forceActiveFocus()
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

    // Close when clicking anywhere outside the card
    MouseArea {
        anchors.fill: parent
        z: 0
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onClicked: {
            overflowWindow.opened = false
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
                overflowWindow.opened = false
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
                overflowWindow.opened = false
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
                overflowWindow.opened = false
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
                overflowWindow.opened = false
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
                overflowWindow.opened = false
            }
        },
        {
            id: "tray.settings",
            name: "Configurações da Bandeja",
            icon: "󰒓",
            action: function(anchorItem) {
                overflowWindow.opened = false
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
            var centerX = dockPanel ? dockPanel.systemTrayAnchorX : -1
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
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            onClicked: {}
        }

        Grid {
            id: grid
            anchors.centerIn: parent
            columns: overflowWindow.gridCols
            rowSpacing: overflowWindow.itemSpacing
            columnSpacing: overflowWindow.itemSpacing

            Repeater {
                model: overflowWindow.trayItems

                Rectangle {
                    id: itemSlot
                    required property var modelData
                    required property int index
                    readonly property real slotSpan: overflowWindow.itemSlotSize + overflowWindow.itemSpacing
                    readonly property int slotColumn: index % overflowWindow.gridCols
                    readonly property int slotRow: Math.floor(index / overflowWindow.gridCols)
                    // Absolute coordinates within the full-screen overflow surface.
                    // Passing these explicitly avoids cross-window mapToItem() ambiguity
                    // when a widget panel is anchored back to the dock surface.
                    readonly property real slotScreenX: card.x + overflowWindow.gridPadding + slotColumn * slotSpan
                    readonly property real slotScreenY: card.y + overflowWindow.gridPadding + slotRow * slotSpan

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

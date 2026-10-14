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
    readonly property int dockGap: (Style.gapsOut || 5)
    readonly property int dockOffset: isOverlay ? (dockGap + dockHeight + dockGap) : (dockHeight + dockGap)

    // Close when clicking anywhere outside the card
    MouseArea {
        anchors.fill: parent
        z: 0
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onClicked: {
            overflowWindow.opened = false
        }
    }

    // List of Tray Items: All available system widgets + Settings Gear
    readonly property var trayItems: [
        {
            id: "omarchy.audio",
            name: "Volume e Áudio",
            icon: "󰕾",
            action: function() {
                overflowWindow.opened = false
                if (dockPanel && typeof dockPanel.toggleTrayWidget === "function") {
                    dockPanel.toggleTrayWidget("omarchy.audio")
                } else {
                    Util.execDetached("omarchy-shell shell toggle omarchy.audio")
                }
            },
            rightAction: function() {
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
            action: function() {
                overflowWindow.opened = false
                if (dockPanel && typeof dockPanel.toggleTrayWidget === "function") {
                    dockPanel.toggleTrayWidget("omarchy.network")
                } else {
                    Util.execDetached("omarchy-shell shell toggle omarchy.network")
                }
            },
            rightAction: function() {
                Util.execDetached("omarchy-launch-floating-terminal-with-presentation nmtui")
            }
        },
        {
            id: "brunoma.agents",
            name: "Consumo de Agentes IA",
            icon: "󰚩",
            action: function() {
                overflowWindow.opened = false
                if (dockPanel && typeof dockPanel.toggleTrayWidget === "function") {
                    dockPanel.toggleTrayWidget("brunoma.agents")
                } else {
                    Util.execDetached("omarchy-shell shell toggle brunoma.agents")
                }
            }
        },
        {
            id: "io.github.rawritude.floating-mode",
            name: "Modo Janela / Desktop",
            icon: "󰍹",
            action: function() {
                overflowWindow.opened = false
                if (dockPanel && typeof dockPanel.toggleTrayWidget === "function") {
                    dockPanel.toggleTrayWidget("io.github.rawritude.floating-mode")
                } else {
                    Util.execDetached(Quickshell.env("HOME") + "/.config/omarchy/plugins/io.github.rawritude.floating-mode/bin/floating-mode toggle")
                }
            }
        },
        {
            id: "omarchy.weather",
            name: "Previsão do Tempo",
            icon: "󰖐",
            action: function() {
                overflowWindow.opened = false
                if (dockPanel && typeof dockPanel.toggleTrayWidget === "function") {
                    dockPanel.toggleTrayWidget("omarchy.weather")
                } else {
                    Util.execDetached("omarchy-notification-weather")
                }
            },
            rightAction: function() {
                Util.execDetached("omarchy-notification-send \"$(omarchy-weather-status)\"")
            }
        },
        {
            id: "tray.settings",
            name: "Configurações da Bandeja",
            icon: "󰒓",
            action: function() {
                overflowWindow.opened = false
                if (dockPanel && typeof dockPanel.openSystemTraySettings === "function") {
                    dockPanel.openSystemTraySettings()
                }
            }
        }
    ]

    readonly property int totalItems: trayItems.length
    readonly property int gridCols: Math.min(totalItems, 5)
    readonly property int gridRows: Math.ceil(totalItems / 5)

    // The Floating Acrylic Popup Card
    Rectangle {
        id: card
        z: 1
        focus: true
        Keys.onEscapePressed: function(event) {
            event.accepted = true
            overflowWindow.opened = false
        }
        anchors.bottom: parent.bottom
        anchors.bottomMargin: overflowWindow.dockOffset + 2
        anchors.right: parent.right
        anchors.rightMargin: {
            var clockW = (dockPanel && dockPanel.clockSlotWidth) ? dockPanel.clockSlotWidth : 76
            var deskW = (dockPanel && dockPanel.showDesktopButtonEnabled && dockPanel.desktopSlotWidth) ? dockPanel.desktopSlotWidth : 10
            return clockW + deskW + (Style.gapsOut || 5)
        }

        width: (overflowWindow.gridCols * 44) + ((overflowWindow.gridCols - 1) * 6) + 20
        height: (overflowWindow.gridRows * 44) + ((overflowWindow.gridRows - 1) * 6) + 20
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
            rowSpacing: 6
            columnSpacing: 6

            Repeater {
                model: overflowWindow.trayItems

                Rectangle {
                    id: itemSlot
                    required property var modelData
                    required property int index

                    width: 44
                    height: 44
                    radius: 7
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
                        font.pixelSize: 20
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
                        acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
                        cursorShape: Qt.PointingHandCursor
                        onClicked: function(mouse) {
                            if (mouse.button === Qt.RightButton && typeof modelData.rightAction === "function") {
                                modelData.rightAction()
                            } else if (typeof modelData.action === "function") {
                                modelData.action()
                            }
                        }
                        onWheel: function(wheel) {
                            if (typeof modelData.scrollAction === "function") {
                                modelData.scrollAction(wheel.angleDelta.y)
                            }
                        }
                    }

                    PanelToolTip {
                        visible: itemMouse.containsMouse
                        text: modelData.name
                        fontFamily: Style.font.family
                        y: -implicitHeight - 12
                        x: Math.round((parent.width - implicitWidth) / 2)
                    }
                }
            }
        }
    }
}

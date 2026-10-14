import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import qs.Commons
import qs.Ui
import ".."

Item {
    id: trayRoot

    property var root: null
    property var dockWindow: null

    readonly property var pinnedWidgets: (root && root.systemTrayPinnedWidgets && Array.isArray(root.systemTrayPinnedWidgets))
        ? root.systemTrayPinnedWidgets
        : []

    readonly property real baseIconSize: root ? root.iconBaseSize : 22
    readonly property real chevronWidth: 22
    readonly property real itemSlotWidth: 26
    readonly property real slotSpacing: 2

    implicitWidth: chevronWidth + (pinnedWidgets.length * itemSlotWidth) + (pinnedWidgets.length > 0 ? (pinnedWidgets.length * slotSpacing) : 0)
    implicitHeight: parent ? parent.height : (root ? root.slotSize : 32)

    Row {
        anchors.right: parent.right
        anchors.rightMargin: 1
        anchors.verticalCenter: parent.verticalCenter
        spacing: trayRoot.slotSpacing

        // 1. Chevron expand button (^) — on the left
        Rectangle {
            id: chevronBtn
            width: trayRoot.chevronWidth
            height: trayRoot.baseIconSize + 6
            anchors.verticalCenter: parent.verticalCenter
            radius: 4
            color: chevronMouse.containsMouse || (root && root.trayOverflowOpened)
                ? Color.composed("popups.hover", "popups.hover-alpha", Color.outline, 0.18)
                : "transparent"
            Behavior on color { ColorAnimation { duration: 120 } }

            Text {
                anchors.centerIn: parent
                textFormat: Text.PlainText
                text: (root && root.trayOverflowOpened) ? "󰅀" : "󰅃"
                font.pixelSize: 14
                font.family: Style.font.family
                color: chevronMouse.containsMouse || (root && root.trayOverflowOpened)
                    ? Color.accent
                    : Color.composed("popups.text", "popups.text-alpha", Color.text, 0.88)
                Behavior on color { ColorAnimation { duration: 120 } }
            }

            MouseArea {
                id: chevronMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    if (root && typeof root.toggleTrayOverflow === "function") {
                        root.toggleTrayOverflow()
                    }
                }
            }

            PanelToolTip {
                visible: chevronMouse.containsMouse && !(root && root.trayOverflowOpened)
                text: "Mostrar ícones ocultos"
                fontFamily: Style.font.family
            }
        }

        // 2. Pinned Widgets (if any selected by user) — sit between chevron and clock
        Repeater {
            model: trayRoot.pinnedWidgets

            Item {
                id: pinnedSlot
                required property string modelData
                required property int index

                width: trayRoot.itemSlotWidth
                height: trayRoot.baseIconSize + 6
                anchors.verticalCenter: parent.verticalCenter

                Rectangle {
                    anchors.fill: parent
                    radius: 4
                    color: pinnedMouse.containsMouse
                        ? Color.composed("popups.hover", "popups.hover-alpha", Color.outline, 0.15)
                        : "transparent"
                    Behavior on color { ColorAnimation { duration: 120 } }

                    Text {
                        id: pinnedGlyph
                        anchors.centerIn: parent
                        textFormat: Text.PlainText
                        text: {
                            if (modelData === "omarchy.audio") {
                                if (root && root.pipewireSinkMuted) return "󰝟"
                                var vol = root ? root.pipewireSinkVolume : 0.5
                                if (vol <= 0.01) return "󰝟"
                                if (vol < 0.33) return "󰕿"
                                if (vol < 0.66) return "󰖀"
                                return "󰕾"
                            }
                            if (modelData === "omarchy.network") return "󰖩"
                            if (modelData === "brunoma.agents") return "󰚩"
                            if (modelData === "io.github.rawritude.floating-mode") return "󰍹"
                            if (modelData === "omarchy.weather") return "󰖐"
                            return root ? root.getWidgetIcon(modelData, null) : "󰒓"
                        }
                        font.pixelSize: 17
                        font.family: Style.font.family
                        color: pinnedMouse.containsMouse
                            ? Color.accent
                            : Color.composed("popups.text", "popups.text-alpha", Color.text, 0.95)
                        Behavior on color { ColorAnimation { duration: 120 } }
                    }

                    MouseArea {
                        id: pinnedMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
                        cursorShape: Qt.PointingHandCursor
                        onClicked: function(mouse) {
                            if (mouse.button === Qt.RightButton && modelData === "omarchy.audio") {
                                Util.execDetached("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle")
                                return
                            }
                            if (root && typeof root.toggleTrayWidget === "function") {
                                root.toggleTrayWidget(modelData)
                            } else {
                                Util.execDetached("omarchy-shell shell toggle " + modelData)
                            }
                        }
                        onWheel: function(wheel) {
                            if (modelData === "omarchy.audio") {
                                var delta = wheel.angleDelta.y
                                if (delta > 0) Util.execDetached("wpctl set-volume @DEFAULT_AUDIO_SINK@ 2%+")
                                else if (delta < 0) Util.execDetached("wpctl set-volume @DEFAULT_AUDIO_SINK@ 2%-")
                            }
                        }
                    }

                    PanelToolTip {
                        visible: pinnedMouse.containsMouse
                        text: {
                            if (modelData === "omarchy.audio") return "Volume e Áudio"
                            if (modelData === "omarchy.network") return "Rede e Conexões"
                            if (modelData === "brunoma.agents") return "Agentes de IA"
                            if (modelData === "io.github.rawritude.floating-mode") return "Modo Janela / Desktop"
                            if (modelData === "omarchy.weather") return "Previsão do Tempo"
                            return modelData
                        }
                        fontFamily: Style.font.family
                    }
                }
            }
        }
    }
}

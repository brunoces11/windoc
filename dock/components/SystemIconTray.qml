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

    readonly property var pinnedWidgets: (root && root.systemTrayPinnedWidgets) ? root.systemTrayPinnedWidgets : ["omarchy.network", "omarchy.audio"]
    readonly property var allWidgets: (root && root.allSystemTrayWidgets) ? root.allSystemTrayWidgets : []
    readonly property var overflowWidgets: {
        var res = []
        for (var i = 0; i < allWidgets.length; i++) {
            var item = allWidgets[i]
            if (pinnedWidgets.indexOf(item.id) === -1) {
                res.push(item)
            }
        }
        return res
    }

    readonly property real baseIconSize: root ? root.iconBaseSize : 22
    readonly property real itemSlotWidth: 28
    readonly property real chevronWidth: 20
    readonly property real slotSpacing: 2

    implicitWidth: chevronWidth + (pinnedWidgets.length * itemSlotWidth) + ((pinnedWidgets.length) * slotSpacing) + 4
    implicitHeight: parent ? parent.height : (root ? root.slotSize : 32)

    // 1. Live Bar Capsule
    Row {
        anchors.centerIn: parent
        spacing: trayRoot.slotSpacing

        // Chevron expand button (^)
        Rectangle {
            id: chevronBtn
            width: trayRoot.chevronWidth
            height: trayRoot.baseIconSize + 6
            anchors.verticalCenter: parent.verticalCenter
            radius: 4
            color: chevronMouse.containsMouse || overflowWindow.opened
                ? Color.composed("popups.hover", "popups.hover-alpha", Color.outline, 0.18)
                : "transparent"
            Behavior on color { ColorAnimation { duration: 120 } }

            DockGlyph {
                anchors.centerIn: parent
                text: overflowWindow.opened ? "󰅀" : "󰅃"
                fontSize: 15
                color: chevronMouse.containsMouse || overflowWindow.opened
                    ? Color.accent
                    : Color.composed("popups.text", "popups.text-alpha", Color.text, 0.85)
                Behavior on color { ColorAnimation { duration: 120 } }
            }

            MouseArea {
                id: chevronMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    overflowWindow.opened = !overflowWindow.opened
                }
            }
        }

        // Pinned Widgets
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

                    DockGlyph {
                        id: pinnedGlyph
                        anchors.centerIn: parent
                        width: trayRoot.baseIconSize
                        height: trayRoot.baseIconSize
                        text: {
                            var _rev = root ? root.widgetIconRevision : 0
                            var _v = root ? root.pipewireSinkVolume : 0
                            var _m = root ? root.pipewireSinkMuted : false
                            var it = pinnedLoader.item
                            return root ? root.getWidgetIcon(modelData, it) : ""
                        }
                        fontSize: 18
                        color: pinnedMouse.containsMouse
                            ? Color.accent
                            : Color.composed("popups.text", "popups.text-alpha", Color.text, 0.95)
                        Behavior on color { ColorAnimation { duration: 120 } }
                    }

                    Loader {
                        id: pinnedLoader
                        anchors.fill: parent
                        opacity: 0.0
                        asynchronous: false
                        source: root ? root.getWidgetSource(modelData) : ""
                        onLoaded: {
                            if (item && root) {
                                root.configureHostedWidget(item, modelData, pinnedSlot)
                            }
                        }
                    }

                    MouseArea {
                        id: pinnedMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
                        cursorShape: Qt.PointingHandCursor
                        onClicked: function(mouse) {
                            if (root) {
                                root.activateWidget(modelData, pinnedLoader.item, pinnedSlot, mouse)
                            }
                        }
                        onWheel: function(wheel) {
                            if (modelData === "omarchy.audio") {
                                var delta = wheel.angleDelta.y
                                if (delta > 0) {
                                    Util.execDetached("wpctl set-volume @DEFAULT_AUDIO_SINK@ 2%+")
                                } else if (delta < 0) {
                                    Util.execDetached("wpctl set-volume @DEFAULT_AUDIO_SINK@ 2%-")
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // 2. Expandable Overflow Pop-up
    PanelWindow {
        id: overflowWindow
        property bool opened: false

        screen: trayRoot.dockWindow ? trayRoot.dockWindow.screen : (Quickshell.screens && Quickshell.screens.length > 0 ? Quickshell.screens[0] : null)
        visible: opened && root && root.dockRevealed

        WlrLayershell.namespace: "omarchy-dock-tray-overflow"
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        exclusionMode: ExclusionMode.Ignore
        color: "transparent"

        anchors {
            top: true
            bottom: true
            left: true
            right: true
        }

        // Click outside to dismiss
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            onClicked: overflowWindow.opened = false
        }

        readonly property int totalItems: trayRoot.overflowWidgets.length + 1
        readonly property int gridCols: Math.min(totalItems, 5)

        // Overflow Card
        Rectangle {
            id: overflowCard
            anchors.bottom: parent.bottom
            anchors.bottomMargin: {
                var dockH = (root && root.windowsTaskbarMode && !root.isVertical && trayRoot.dockWindow)
                    ? trayRoot.dockWindow.height
                    : ((root ? root.slotSize : 42) + 8)
                return dockH + (Style.gapsOut || 5) + 4
            }
            anchors.right: parent.right
            anchors.rightMargin: {
                var cWidth = (root && root.clockSlotWidth) ? root.clockSlotWidth : 80
                var dWidth = (root && root.showDesktopButtonEnabled && root.desktopSlotWidth) ? root.desktopSlotWidth : 10
                return cWidth + dWidth + (Style.gapsOut || 5) + 6
            }

            width: (overflowWindow.gridCols * 40) + ((overflowWindow.gridCols - 1) * 6) + 20
            height: (Math.ceil(overflowWindow.totalItems / 5) * 40) + ((Math.ceil(overflowWindow.totalItems / 5) - 1) * 6) + 20
            radius: 10
            color: Color.popups.background
            border.width: 1
            border.color: Color.composed("popups.border", "popups.border-alpha", Color.outline, 0.28)

            Behavior on opacity { NumberAnimation { duration: 140 } }
            Behavior on scale { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }

            // Consume clicks inside card
            MouseArea {
                anchors.fill: parent
                onClicked: {}
            }

            Grid {
                id: overflowGrid
                anchors.centerIn: parent
                columns: overflowWindow.gridCols
                spacing: 6

                // Overflow item icons
                Repeater {
                    model: trayRoot.overflowWidgets

                    Rectangle {
                        id: overSlot
                        required property var modelData
                        required property int index

                        width: 40
                        height: 40
                        radius: 6
                        color: overMouse.containsMouse
                            ? Color.composed("popups.hover", "popups.hover-alpha", Color.outline, 0.2)
                            : "transparent"
                        Behavior on color { ColorAnimation { duration: 120 } }

                        DockGlyph {
                            id: overGlyph
                            anchors.centerIn: parent
                            text: {
                                var _rev = root ? root.widgetIconRevision : 0
                                var it = overLoader.item
                                return root ? root.getWidgetIcon(modelData.id, it) : ""
                            }
                            fontSize: 20
                            color: overMouse.containsMouse
                                ? Color.accent
                                : Color.composed("popups.text", "popups.text-alpha", Color.text, 0.95)
                            Behavior on color { ColorAnimation { duration: 120 } }
                        }

                        Loader {
                            id: overLoader
                            anchors.fill: parent
                            opacity: 0.0
                            asynchronous: false
                            source: root ? root.getWidgetSource(modelData.id) : ""
                            onLoaded: {
                                if (item && root) {
                                    root.configureHostedWidget(item, modelData.id, overSlot)
                                }
                            }
                        }

                        MouseArea {
                            id: overMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
                            cursorShape: Qt.PointingHandCursor
                            onClicked: function(mouse) {
                                overflowWindow.opened = false
                                if (root) {
                                    root.activateWidget(modelData.id, overLoader.item, overSlot, mouse)
                                }
                            }
                        }
                    }
                }

                // Dedicated Settings Gear (⚙) Button
                Rectangle {
                    id: settingsSlot
                    width: 40
                    height: 40
                    radius: 6
                    color: settingsMouse.containsMouse
                        ? Color.composed("popups.hover", "popups.hover-alpha", Color.outline, 0.2)
                        : "transparent"
                    Behavior on color { ColorAnimation { duration: 120 } }

                    DockGlyph {
                        anchors.centerIn: parent
                        text: "󰒓"
                        fontSize: 20
                        color: settingsMouse.containsMouse
                            ? Color.accent
                            : Color.composed("popups.text", "popups.text-alpha", Color.text, 0.85)
                        Behavior on color { ColorAnimation { duration: 120 } }
                    }

                    MouseArea {
                        id: settingsMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            overflowWindow.opened = false
                            if (root && typeof root.openSystemTraySettings === "function") {
                                root.openSystemTraySettings()
                            }
                        }
                    }
                }
            }
        }
    }
}

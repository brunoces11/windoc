import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import qs.Commons
import qs.Ui
import ".."

PanelWindow {
    id: modalWindow

    property var root: null
    property var dockWindow: null
    property bool opened: false

    screen: modalWindow.dockWindow ? modalWindow.dockWindow.screen : (Quickshell.screens && Quickshell.screens.length > 0 ? Quickshell.screens[0] : null)
    visible: opened

    WlrLayershell.namespace: "omarchy-dock-tray-settings"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: modalWindow.opened ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    color: "transparent"

    anchors {
        top: true
        bottom: true
        left: true
        right: true
    }

    onOpenedChanged: {
        if (opened) {
            modalCard.forceActiveFocus()
        }
    }

    // Semi-transparent backdrop overlay
    Rectangle {
        anchors.fill: parent
        color: Qt.rgba(0, 0, 0, 0.55)
        opacity: modalWindow.opened ? 1.0 : 0.0
        Behavior on opacity { NumberAnimation { duration: 150 } }

        MouseArea {
            anchors.fill: parent
            onClicked: modalWindow.opened = false
        }
    }

    // Modal Card
    Rectangle {
        id: modalCard
        anchors.centerIn: parent
        width: Math.min(500, parent.width - 40)
        height: contentColumn.implicitHeight + 40
        radius: 12
        color: Color.popups.background
        border.width: 1
        border.color: Color.composed("popups.border", "popups.border-alpha", Color.outline, 0.3)

        // Consume clicks inside card
        MouseArea {
            anchors.fill: parent
            onClicked: {}
        }

        Keys.onEscapePressed: {
            modalWindow.opened = false
        }

        Column {
            id: contentColumn
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: 20
            spacing: 16

            // Header Row
            RowLayout {
                width: parent.width
                spacing: 12

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4

                    Text {
                        text: "Ícones da Área de Notificação"
                        font.family: Style.font.family
                        font.pixelSize: 17
                        font.weight: Font.DemiBold
                        color: Color.composed("popups.text", "popups.text-alpha", Color.text, 0.95)
                    }

                    Text {
                        text: "Selecione quais ícones devem aparecer fixados na barra de tarefas. Os demais ficam acessíveis pelo menu (^)."
                        font.family: Style.font.family
                        font.pixelSize: 12
                        color: Color.composed("popups.text-muted", "popups.text-muted-alpha", Color.text, 0.65)
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }

                // Close Button
                Rectangle {
                    width: 30
                    height: 30
                    radius: 15
                    color: closeMouse.containsMouse ? Color.composed("popups.hover", "popups.hover-alpha", Color.outline, 0.2) : "transparent"
                    Behavior on color { ColorAnimation { duration: 120 } }

                    Text {
                        anchors.centerIn: parent
                        textFormat: Text.PlainText
                        text: "󰅖"
                        font.pixelSize: 16
                        font.family: Style.font.family
                        color: closeMouse.containsMouse ? Color.accent : Color.composed("popups.text", "popups.text-alpha", Color.text, 0.8)
                    }

                    MouseArea {
                        id: closeMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: modalWindow.opened = false
                    }
                }
            }

            Rectangle {
                width: parent.width
                height: 1
                color: Color.composed("popups.border", "popups.border-alpha", Color.outline, 0.15)
            }

            // List of Widgets
            Column {
                width: parent.width
                spacing: 8

                Repeater {
                    model: modalWindow.root ? modalWindow.root.allSystemTrayWidgets : []

                    Rectangle {
                        required property var modelData
                        required property int index
                        width: parent.width
                        height: 52
                        radius: 8
                        color: itemMouse.containsMouse
                            ? Color.composed("popups.hover", "popups.hover-alpha", Color.outline, 0.12)
                            : "transparent"
                        Behavior on color { ColorAnimation { duration: 120 } }

                        readonly property bool isPinned: {
                            if (!modalWindow.root || !modalWindow.root.systemTrayPinnedWidgets) return false
                            return modalWindow.root.systemTrayPinnedWidgets.indexOf(modelData.id) !== -1
                        }

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            spacing: 14

                            // Widget Icon Box
                            Rectangle {
                                width: 34
                                height: 34
                                radius: 8
                                color: Color.composed("popups.icon-bg", "popups.icon-bg-alpha", Color.outline, 0.15)

                                Text {
                                    anchors.centerIn: parent
                                    textFormat: Text.PlainText
                                    text: modelData.icon || "󰒓"
                                    font.pixelSize: 18
                                    font.family: Style.font.family
                                    color: isPinned ? Color.accent : Color.composed("popups.text", "popups.text-alpha", Color.text, 0.85)
                                }
                            }

                            // Widget Info
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2

                                Text {
                                    text: modelData.name || modelData.id
                                    font.family: Style.font.family
                                    font.pixelSize: 13
                                    font.weight: Font.Medium
                                    color: Color.composed("popups.text", "popups.text-alpha", Color.text, 0.95)
                                }

                                Text {
                                    text: modelData.desc || ""
                                    font.family: Style.font.family
                                    font.pixelSize: 11
                                    color: Color.composed("popups.text-muted", "popups.text-muted-alpha", Color.text, 0.6)
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                            }

                            // Windows-style Toggle Switch
                            Rectangle {
                                width: 44
                                height: 24
                                radius: 12
                                color: isPinned ? Color.accent : Color.composed("popups.toggle-off", "popups.toggle-off-alpha", Color.outline, 0.3)
                                Behavior on color { ColorAnimation { duration: 160 } }

                                Rectangle {
                                    width: 18
                                    height: 18
                                    radius: 9
                                    anchors.verticalCenter: parent.verticalCenter
                                    x: isPinned ? (parent.width - width - 3) : 3
                                    color: isPinned ? Color.background : Color.composed("popups.text", "popups.text-alpha", Color.text, 0.9)
                                    Behavior on x { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
                                }
                            }
                        }

                        MouseArea {
                            id: itemMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (modalWindow.root && typeof modalWindow.root.toggleSystemTrayPin === "function") {
                                    modalWindow.root.toggleSystemTrayPin(modelData.id)
                                }
                            }
                        }
                    }
                }
            }

            Rectangle {
                width: parent.width
                height: 1
                color: Color.composed("popups.border", "popups.border-alpha", Color.outline, 0.15)
            }

            // Footer
            RowLayout {
                width: parent.width

                Text {
                    text: "Dica: Clique com botão direito nos ícones da barra para ações rápidas."
                    font.family: Style.font.family
                    font.pixelSize: 11
                    color: Color.composed("popups.text-muted", "popups.text-muted-alpha", Color.text, 0.5)
                    Layout.fillWidth: true
                }

                Rectangle {
                    width: 76
                    height: 28
                    radius: 6
                    color: doneMouse.containsMouse ? Color.composed("popups.hover", "popups.hover-alpha", Color.outline, 0.25) : Color.composed("popups.button", "popups.button-alpha", Color.outline, 0.15)

                    Text {
                        anchors.centerIn: parent
                        text: "Concluir"
                        font.family: Style.font.family
                        font.pixelSize: 12
                        font.weight: Font.Medium
                        color: Color.composed("popups.text", "popups.text-alpha", Color.text, 0.9)
                    }

                    MouseArea {
                        id: doneMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: modalWindow.opened = false
                    }
                }
            }
        }
    }
}

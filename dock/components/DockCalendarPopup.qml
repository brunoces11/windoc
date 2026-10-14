import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Hyprland
import Quickshell.Wayland
import qs.Commons
import qs.Ui
import "CalendarModel.js" as Model

PanelWindow {
    id: calendarWindow

    required property var root
    required property var dockWindow
    property bool opened: false

    screen: calendarWindow.dockWindow ? calendarWindow.dockWindow.screen : (Quickshell.screens && Quickshell.screens.length > 0 ? Quickshell.screens[0] : null)
    visible: opened && calendarWindow.root && calendarWindow.root.dockRevealed

    readonly property bool isOverlay: calendarWindow.root.overlayMode === true
    readonly property int dockHeight: calendarWindow.root.windowsTaskbarMode && !calendarWindow.root.isVertical
        ? (calendarWindow.dockWindow ? calendarWindow.dockWindow.height : 50)
        : (calendarWindow.root.slotSize + 8)
    readonly property int dockGap: (Style.gapsOut || 5)
    readonly property int dockOffset: isOverlay ? (dockGap + dockHeight + dockGap) : (dockHeight + dockGap)

    WlrLayershell.namespace: "omarchy-dock-calendar"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: calendarWindow.opened ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    color: "transparent"

    anchors {
        top: true
        bottom: true
        left: true
        right: true
    }

    // Calendar state
    property date today: new Date()
    readonly property string todayKey: Model.keyForDate(today)

    property int viewYear: today.getFullYear()
    property int viewMonth: today.getMonth()

    readonly property date viewDate: new Date(viewYear, viewMonth, 1)
    readonly property bool viewingCurrentMonth: viewYear === today.getFullYear() && viewMonth === today.getMonth()

    readonly property real yearDone: Model.yearProgress(today.getFullYear(), today.getMonth(), today.getDate())
    readonly property int yearDonePercent: Model.yearProgressPercent(today.getFullYear(), today.getMonth(), today.getDate())

    readonly property int weekStart: Model.normalizedWeekStart(null, Qt.locale().firstDayOfWeek)
    readonly property var labelLocale: Qt.locale()
    readonly property string nextWeekStartLabel: labelLocale.dayName(Model.toggledWeekStart(weekStart), Locale.LongFormat)
    readonly property var weekdays: Model.weekdayOrder(weekStart)
    readonly property var weeks: Model.monthGrid(viewYear, viewMonth, weekStart, todayKey)

    readonly property color contentForeground: Color.composed("popups.text", "popups.text-alpha", Color.text, 0.95)
    readonly property string contentFontFamily: Style.font.family

    readonly property int cellWidth: Style.space(48)
    readonly property int cellHeight: Style.space(32)
    readonly property int cellSpacing: Style.space(2)
    readonly property int weekColumnWidth: Style.space(28)
    readonly property int gutterWidth: Style.space(10)

    function refresh() {
        today = new Date()
        goToToday()
    }

    function goToToday() {
        viewYear = today.getFullYear()
        viewMonth = today.getMonth()
    }

    function moveMonth(delta) {
        var next = Model.stepMonth(viewYear, viewMonth, delta)
        viewYear = next.year
        viewMonth = next.month
    }

    function moveYear(delta) {
        moveMonth(delta * 12)
    }

    function weekdayLabel(weekday) {
        return String(labelLocale.dayName(weekday, Locale.ShortFormat)).toUpperCase()
    }

    onOpenedChanged: {
        if (opened) {
            refresh()
            calendarCard.forceActiveFocus()
        }
    }

    SystemClock {
        id: clock
        precision: SystemClock.Minutes
        onDateChanged: {
            if (Model.keyForDate(clock.date) === String(calendarWindow.todayKey)) return
            var followToday = calendarWindow.viewingCurrentMonth
            calendarWindow.today = clock.date
            if (followToday) calendarWindow.goToToday()
        }
    }

    // Dismissal MouseArea covering the area outside the card
    MouseArea {
        anchors.fill: parent
        z: 0
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onClicked: function() {
            calendarWindow.opened = false
        }
    }

    // Main Calendar Card
    Rectangle {
        id: calendarCard
        z: 1
        anchors.bottom: (!calendarWindow.root.isVertical && calendarWindow.root.barPosition === "top") ? parent.bottom : undefined
        anchors.top: (!calendarWindow.root.isVertical && calendarWindow.root.barPosition === "bottom") ? parent.top : undefined
        anchors.right: (calendarWindow.root.isVertical && calendarWindow.root.barPosition === "left") ? undefined : parent.right
        anchors.left: (calendarWindow.root.isVertical && calendarWindow.root.barPosition === "right") ? parent.left : undefined

        anchors.bottomMargin: (!calendarWindow.root.isVertical && calendarWindow.root.barPosition === "top") ? calendarWindow.dockOffset : 0
        anchors.topMargin: (!calendarWindow.root.isVertical && calendarWindow.root.barPosition === "bottom") ? calendarWindow.dockOffset : 0
        anchors.rightMargin: (calendarWindow.root.isVertical && calendarWindow.root.barPosition === "left") ? 0 : (Style.gapsOut || 5)
        anchors.leftMargin: (calendarWindow.root.isVertical && calendarWindow.root.barPosition === "right") ? calendarWindow.dockOffset : 0
        width: Style.space(480)
        height: calendarColumn.implicitHeight + Style.space(28)

        color: calendarWindow.root.isBarTransparent
            ? Util.alpha(Color.popups.background, 0.85)
            : Color.popups.background
        border.width: 1
        border.color: Color.popups.border
        radius: calendarWindow.root.systemRounding || Style.cornerRadius
        antialiasing: true
        smooth: true
        focus: true

        // Absorb clicks inside the card so dismissal MouseArea does not trigger
        MouseArea {
            anchors.fill: parent
            z: 0
            acceptedButtons: Qt.LeftButton | Qt.RightButton
        }

        Keys.onEscapePressed: function(event) {
            event.accepted = true
            calendarWindow.opened = false
        }

        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_BracketLeft) {
                event.accepted = true
                calendarWindow.moveMonth(-1)
            } else if (event.key === Qt.Key_BracketRight) {
                event.accepted = true
                calendarWindow.moveMonth(1)
            } else if (event.key === Qt.Key_T) {
                event.accepted = true
                calendarWindow.goToToday()
            }
        }

        Column {
            id: calendarColumn
            anchors.fill: parent
            anchors.margins: Style.space(14)
            spacing: Style.space(10)

            // 1. Hero Date Header
            Item {
                width: parent.width
                height: heroRow.height

                Row {
                    id: heroRow
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: Style.space(14)

                    Text {
                        anchors.baseline: heroDate.baseline
                        text: "󰃭"
                        color: heroMouse.containsMouse ? Color.accent : calendarWindow.contentForeground
                        font.family: calendarWindow.contentFontFamily
                        font.pixelSize: 38
                        Behavior on color { ColorAnimation { duration: 120 } }
                    }

                    Text {
                        id: heroDate
                        textFormat: Text.PlainText
                        anchors.verticalCenter: parent.verticalCenter
                        text: Qt.formatDate(calendarWindow.today, "dddd, d 'de' MMMM")
                        color: heroMouse.containsMouse ? Color.accent : calendarWindow.contentForeground
                        font.family: calendarWindow.contentFontFamily
                        font.pixelSize: 22
                        font.bold: true
                        Behavior on color { ColorAnimation { duration: 120 } }
                    }
                }

                MouseArea {
                    id: heroMouse
                    anchors.fill: heroRow
                    enabled: !calendarWindow.viewingCurrentMonth
                    hoverEnabled: enabled
                    cursorShape: Qt.PointingHandCursor
                    onClicked: calendarWindow.goToToday()

                    PanelToolTip {
                        visible: heroMouse.containsMouse
                        text: "Voltar para hoje"
                        fontFamily: calendarWindow.contentFontFamily
                    }
                }
            }

            // 2. Year Progress Bar
            Item {
                width: parent.width
                height: Style.space(14)

                Text {
                    id: yearLabel
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    text: calendarWindow.today.getFullYear()
                    color: Qt.darker(calendarWindow.contentForeground, 1.4)
                    font.family: calendarWindow.contentFontFamily
                    font.pixelSize: Style.font.caption
                    font.letterSpacing: 1
                    font.bold: true
                }

                Text {
                    id: yearPercent
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: calendarWindow.yearDonePercent + "% do ano decorrido"
                    color: Qt.darker(calendarWindow.contentForeground, 1.4)
                    font.family: calendarWindow.contentFontFamily
                    font.pixelSize: Style.font.caption
                }

                Rectangle {
                    anchors.left: yearLabel.right
                    anchors.right: yearPercent.left
                    anchors.leftMargin: Style.space(10)
                    anchors.rightMargin: Style.space(10)
                    anchors.verticalCenter: parent.verticalCenter
                    height: Style.space(5)
                    radius: height / 2
                    color: Qt.rgba(calendarWindow.contentForeground.r, calendarWindow.contentForeground.g, calendarWindow.contentForeground.b, 0.12)

                    Rectangle {
                        width: Math.round(parent.width * calendarWindow.yearDone)
                        height: parent.height
                        radius: parent.radius
                        color: Color.accent

                        Behavior on width { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
                    }
                }
            }

            // 3. Month Stepping / Navigation Bar
            Item {
                width: parent.width
                height: monthNav.height

                Row {
                    id: monthNav
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: Style.space(20)

                    PanelActionButton {
                        anchors.verticalCenter: parent.verticalCenter
                        iconText: "󰅁"
                        tooltipText: "Mês anterior"
                        foreground: calendarWindow.contentForeground
                        fontFamily: calendarWindow.contentFontFamily
                        onClicked: calendarWindow.moveMonth(-1)
                    }

                    Text {
                        id: monthLabel
                        textFormat: Text.PlainText
                        anchors.verticalCenter: parent.verticalCenter
                        width: Style.space(200)
                        horizontalAlignment: Text.AlignHCenter
                        text: Qt.formatDate(calendarWindow.viewDate, "MMMM yyyy").toUpperCase()
                        color: calendarWindow.contentForeground
                        font.family: calendarWindow.contentFontFamily
                        font.pixelSize: Style.font.body
                        font.letterSpacing: 1
                        font.bold: true
                    }

                    PanelActionButton {
                        anchors.verticalCenter: parent.verticalCenter
                        iconText: "󰅂"
                        tooltipText: "Próximo mês"
                        foreground: calendarWindow.contentForeground
                        fontFamily: calendarWindow.contentFontFamily
                        onClicked: calendarWindow.moveMonth(1)
                    }
                }
            }

            // 4. Calendar Month Grid
            Item {
                width: parent.width
                height: gridColumn.height

                WheelHandler {
                    onWheel: function(event) {
                        if (event.angleDelta.y === 0) return
                        calendarWindow.moveMonth(event.angleDelta.y > 0 ? -1 : 1)
                    }
                }

                Column {
                    id: gridColumn
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: Style.space(2)

                    // Weekday Header Row
                    Row {
                        id: headerRow
                        spacing: calendarWindow.cellSpacing

                        // Week column header
                        Rectangle {
                            width: calendarWindow.weekColumnWidth
                            height: Style.space(18)
                            radius: Style.cornerRadius
                            color: "transparent"

                            Text {
                                anchors.centerIn: parent
                                text: "S"
                                color: Qt.darker(calendarWindow.contentForeground, 1.8)
                                font.family: calendarWindow.contentFontFamily
                                font.pixelSize: Style.font.caption
                                font.letterSpacing: 1
                                font.bold: true
                            }
                        }

                        Item {
                            width: calendarWindow.gutterWidth
                            height: Style.space(18)
                        }

                        Repeater {
                            model: calendarWindow.weekdays

                            Text {
                                textFormat: Text.PlainText
                                required property var modelData
                                width: calendarWindow.cellWidth
                                height: Style.space(18)
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                text: calendarWindow.weekdayLabel(modelData)
                                color: Qt.darker(calendarWindow.contentForeground, 1.5)
                                font.family: calendarWindow.contentFontFamily
                                font.pixelSize: Style.font.caption
                                font.letterSpacing: 1
                                font.bold: true
                            }
                        }
                    }

                    // Week Rows
                    Repeater {
                        model: calendarWindow.weeks

                        Row {
                            required property var modelData
                            spacing: calendarWindow.cellSpacing

                            // ISO week number
                            Text {
                                textFormat: Text.PlainText
                                width: calendarWindow.weekColumnWidth
                                height: calendarWindow.cellHeight
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                text: modelData.week
                                color: Qt.darker(calendarWindow.contentForeground, 1.8)
                                font.family: calendarWindow.contentFontFamily
                                font.pixelSize: Style.font.caption
                            }

                            Item {
                                width: calendarWindow.gutterWidth
                                height: calendarWindow.cellHeight
                            }

                            Repeater {
                                model: modelData.days

                                Rectangle {
                                    required property var modelData

                                    width: calendarWindow.cellWidth
                                    height: calendarWindow.cellHeight
                                    radius: Style.cornerRadius
                                    color: modelData.today ? Util.alpha(Color.accent, 0.22) : "transparent"
                                    border.width: modelData.today ? 1.5 : 0
                                    border.color: Color.accent

                                    Text {
                                        textFormat: Text.PlainText
                                        anchors.centerIn: parent
                                        text: modelData.day
                                        color: modelData.today
                                            ? Color.accent
                                            : (modelData.inMonth
                                                ? (modelData.weekend ? Qt.darker(calendarWindow.contentForeground, 1.35) : calendarWindow.contentForeground)
                                                : Qt.darker(calendarWindow.contentForeground, 2.2))
                                        font.family: calendarWindow.contentFontFamily
                                        font.pixelSize: Style.font.body
                                        font.bold: modelData.today
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // 5. Footer with Timezone and Reset
            Item {
                width: parent.width
                height: Style.space(26)

                Row {
                    anchors.centerIn: parent
                    spacing: Style.space(16)

                    Rectangle {
                        width: tzText.implicitWidth + Style.space(16)
                        height: Style.space(24)
                        radius: Style.cornerRadius
                        color: tzMouse.containsMouse ? Util.alpha(Color.accent, 0.18) : "transparent"
                        border.width: 1
                        border.color: tzMouse.containsMouse ? Color.accent : Qt.rgba(calendarWindow.contentForeground.r, calendarWindow.contentForeground.g, calendarWindow.contentForeground.b, 0.15)

                        Text {
                            id: tzText
                            anchors.centerIn: parent
                            text: "󱑎 Fuso horário"
                            color: tzMouse.containsMouse ? Color.accent : calendarWindow.contentForeground
                            font.family: calendarWindow.contentFontFamily
                            font.pixelSize: Style.font.caption
                        }

                        MouseArea {
                            id: tzMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                calendarWindow.opened = false
                                Util.execDetached("omarchy-menu-timezone")
                            }
                        }
                    }

                    Rectangle {
                        width: todayBtnText.implicitWidth + Style.space(16)
                        height: Style.space(24)
                        radius: Style.cornerRadius
                        visible: !calendarWindow.viewingCurrentMonth
                        color: todayBtnMouse.containsMouse ? Util.alpha(Color.accent, 0.18) : "transparent"
                        border.width: 1
                        border.color: todayBtnMouse.containsMouse ? Color.accent : Qt.rgba(calendarWindow.contentForeground.r, calendarWindow.contentForeground.g, calendarWindow.contentForeground.b, 0.15)

                        Text {
                            id: todayBtnText
                            anchors.centerIn: parent
                            text: "󰁝 Mês atual"
                            color: todayBtnMouse.containsMouse ? Color.accent : calendarWindow.contentForeground
                            font.family: calendarWindow.contentFontFamily
                            font.pixelSize: Style.font.caption
                        }

                        MouseArea {
                            id: todayBtnMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: calendarWindow.goToToday()
                        }
                    }
                }
            }
        }
    }
}

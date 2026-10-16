import QtQuick
import Quickshell.Hyprland
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "omarchy.workspaces"

  // Make sure this widget is stacked above Bar.qml's modulePointer MouseArea
  // so that Alt+Drag and clicks are handled directly by workspace buttons
  onParentChanged: {
    if (root.parent) {
      root.parent.z = 100
    }
  }

  Component.onCompleted: {
    if (root.parent) {
      root.parent.z = 100
    }
  }

  function workspaceById(id) {
    var values = Hyprland.workspaces.values
    for (var i = 0; i < values.length; i++) {
      if (values[i].id === id) return values[i]
    }
    return null
  }

  function workspaceIds() {
    var ids = [1, 2, 3, 4, 5]
    var values = Hyprland.workspaces.values

    for (var i = 0; i < values.length; i++) {
      var id = values[i].id
      if (id > 0 && id <= 10 && ids.indexOf(id) === -1) ids.push(id)
    }

    ids.sort(function(left, right) { return left - right })
    return ids
  }

  function focusWorkspace(id) {
    if (!root.bar) return
    root.bar.run("hyprctl dispatch " + Util.shellQuote("hl.dsp.focus({ workspace = \"" + id + "\" })"))
  }

  function reorderWorkspaces(fromWs, toWs) {
    if (fromWs === toWs) return
    var script = "/home/brunoma/.config/omarchy/scripts/reorder-workspaces.py"
    var cmd = "python3 " + script + " " + fromWs + " " + toWs
    if (root.bar && typeof root.bar.run === "function") {
      root.bar.run(cmd)
    } else {
      Util.execDetached(cmd)
    }
  }

  readonly property var orderedIds: {
    var _hw = Hyprland.workspaces.values
    return root.workspaceIds()
  }
  readonly property int itemCount: orderedIds.length

  readonly property real trailingGap: root.vertical ? 0 : Style.spaceReal(1.5)
  readonly property real slotSpacing: root.vertical ? Style.space(2) : Style.space(1)
  
  readonly property real itemWidth: root.vertical ? root.barSize : Style.space(20)
  readonly property real itemHeight: root.barSize
  readonly property real slotStride: root.vertical ? (itemHeight + slotSpacing) : (itemWidth + slotSpacing)

  implicitWidth: root.vertical ? itemWidth : (itemCount * slotStride - slotSpacing + trailingGap)
  implicitHeight: root.vertical ? (itemCount * slotStride - slotSpacing) : itemHeight

  // Drag state
  property int dragFromIndex: -1
  property int dragTargetIndex: -1
  property real dragCurrentPos: 0
  property real dragStartPos: 0
  property bool isDragging: false

  Item {
    id: container
    anchors.fill: parent
    anchors.rightMargin: root.trailingGap

    Repeater {
      model: root.orderedIds

      WidgetButton {
        id: delegateItem
        required property int modelData
        required property int index

        readonly property var workspace: root.workspaceById(modelData)
        readonly property bool occupied: workspace !== null && workspace.toplevels.values.length > 0
        readonly property bool focused: Hyprland.focusedWorkspace !== null && Hyprland.focusedWorkspace.id === modelData
        
        // Dragging is only possible for the currently focused workspace (the red square)
        readonly property bool isBeingDragged: root.isDragging && root.dragFromIndex === index && focused

        bar: root.bar
        text: focused ? "\uDB85\uDCFB" : (modelData === 10 ? "0" : String(modelData))
        opacity: (occupied || focused || isBeingDragged) ? 1 : 0.5
        horizontalMargin: 6
        verticalPadding: 6
        fixedWidth: root.itemWidth
        fixedHeight: root.itemHeight

        // Bring the dragged item to front
        z: isBeingDragged ? 100 : (focused ? 2 : 1)
        scale: isBeingDragged ? 1.15 : 1.0

        // Visual displacement when another item is dragged over ("abrindo espaço")
        readonly property real shiftOffset: {
          if (!root.isDragging || root.dragFromIndex < 0 || root.dragTargetIndex < 0 || isBeingDragged) return 0
          if (root.dragFromIndex > root.dragTargetIndex) {
            // Dragged right-to-left
            if (index >= root.dragTargetIndex && index < root.dragFromIndex) return root.slotStride
          } else if (root.dragFromIndex < root.dragTargetIndex) {
            // Dragged left-to-right
            if (index > root.dragFromIndex && index <= root.dragTargetIndex) return -root.slotStride
          }
          return 0
        }

        readonly property real dragDelta: isBeingDragged ? (root.dragCurrentPos - root.dragStartPos) : 0

        x: root.vertical ? 0 : (index * root.slotStride + (isBeingDragged ? dragDelta : shiftOffset))
        y: root.vertical ? (index * root.slotStride + (isBeingDragged ? dragDelta : shiftOffset)) : 0

        Behavior on x {
          enabled: !delegateItem.isBeingDragged
          NumberAnimation { duration: 150; easing.type: Easing.OutCubic }
        }
        Behavior on y {
          enabled: !delegateItem.isBeingDragged
          NumberAnimation { duration: 150; easing.type: Easing.OutCubic }
        }
        Behavior on scale {
          NumberAnimation { duration: 150; easing.type: Easing.OutCubic }
        }

        onPressed: function() {
          // Fallback if MouseArea passes it through
          if (!root.isDragging) root.focusWorkspace(modelData)
        }

        MouseArea {
          id: dragArea
          anchors.fill: parent
          acceptedButtons: Qt.LeftButton
          propagateComposedEvents: true

          onPressed: function(mouse) {
            // Only allow dragging the active (focused) workspace indicator
            if (delegateItem.focused && (mouse.modifiers & Qt.AltModifier)) {
              mouse.accepted = true
              var containerPos = dragArea.mapToItem(container, mouse.x, mouse.y)
              var pos = root.vertical ? containerPos.y : containerPos.x
              root.dragStartPos = pos
              root.dragCurrentPos = pos
              root.isDragging = true
              root.dragFromIndex = index
              root.dragTargetIndex = index
            } else {
              mouse.accepted = false
            }
          }

          onPositionChanged: function(mouse) {
            if (!root.isDragging || root.dragFromIndex !== index) return
            var containerPos = dragArea.mapToItem(container, mouse.x, mouse.y)
            var pos = root.vertical ? containerPos.y : containerPos.x
            root.dragCurrentPos = pos

            var rawTarget = Math.floor(pos / root.slotStride)
            root.dragTargetIndex = Math.max(0, Math.min(root.itemCount - 1, rawTarget))
          }

          onReleased: function(mouse) {
            if (root.isDragging && root.dragFromIndex === index) {
              var fromIdx = root.dragFromIndex
              var toIdx = root.dragTargetIndex
              
              root.isDragging = false
              root.dragFromIndex = -1
              root.dragTargetIndex = -1

              if (fromIdx !== toIdx && fromIdx >= 0 && toIdx >= 0) {
                var fromWs = root.orderedIds[fromIdx]
                var toWs = root.orderedIds[toIdx]
                root.reorderWorkspaces(fromWs, toWs)
              }
            }
          }

          onCanceled: {
            if (root.dragFromIndex === index) {
              root.isDragging = false
              root.dragFromIndex = -1
              root.dragTargetIndex = -1
            }
          }
        }
      }
    }
  }
}

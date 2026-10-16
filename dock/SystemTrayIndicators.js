.pragma library

var items = [
    {
        id: "omarchy.indicator.screen-recording",
        name: "Screen Recording",
        icon: "󰻂",
        description: "Iniciar ou encerrar gravação de tela"
    },
    {
        id: "omarchy.indicator.reminder",
        name: "Set Reminder",
        icon: "󰢌",
        description: "Criar lembrete ou consultar os lembretes ativos"
    },
    {
        id: "omarchy.indicator.dictation",
        name: "Dictation (Voxtype)",
        icon: "󰍬",
        description: "Abrir as configurações da digitação por voz"
    },
    {
        id: "omarchy.indicator.idle",
        name: "Allow Idle Lock & Screensaver",
        icon: "󰅶",
        description: "Alternar o modo Stay Awake"
    },
    {
        id: "omarchy.indicator.notifications",
        name: "Allow Notifications",
        icon: "󰂛",
        description: "Alternar o silêncio de notificações"
    },
    {
        id: "omarchy.indicator.nightlight",
        name: "Daylight / Night Light",
        icon: "󰔎",
        description: "Alternar o filtro de luz noturna"
    }
]

function contains(id) {
    for (var i = 0; i < items.length; i++) {
        if (items[i].id === id) return true
    }
    return false
}

function itemForId(id) {
    for (var i = 0; i < items.length; i++) {
        if (items[i].id === id) return items[i]
    }
    return null
}

function overflowItems(dockPanel) {
    var result = []
    for (var i = 0; i < items.length; i++) {
        var entry = items[i]
        result.push({
            id: entry.id,
            name: entry.name,
            icon: entry.icon,
            action: (function(id) {
                return function() {
                    if (dockPanel && typeof dockPanel.runSystemTrayIndicator === "function") {
                        dockPanel.runSystemTrayIndicator(id)
                    }
                }
            })(entry.id)
        })
    }
    return result
}

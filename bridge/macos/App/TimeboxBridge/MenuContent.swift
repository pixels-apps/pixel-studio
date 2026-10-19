import SwiftUI
import TimeboxBridgeCore

/// Contenu du menu (style menu natif : chaque vue devient un élément de menu).
struct MenuContent: View {
    let model: BridgeModel
    @Environment(\.openWindow) private var openWindow
    @Environment(\.openSettings) private var openSettings

    var body: some View {
        Text(model.summary)
        if let hint = model.hint {
            Text(hint)
        }
        if model.bluetoothDenied {
            Button("Ouvrir les réglages de confidentialité…") { model.openBluetoothPrivacySettings() }
        }
        if model.isWaitingForPort {
            Button("Réessayer maintenant") { model.retryListening() }
        }
        if model.address != nil, model.startError == nil {
            Text(model.listenerLine)
            Text(model.channelLine)
            Text(model.clientLine)
            Text(model.bytesLine)
        }
        Divider()
        DeviceMenu(model: model)
        Button("Reconnecter") { model.reconnect() }
            .disabled(!model.canReconnect)
        Button("Journal…") {
            NSApp.activate()
            openWindow(id: LogWindow.id)
        }
        .keyboardShortcut("l")
        Button("Réglages…") {
            NSApp.activate()
            openSettings()
        }
        .keyboardShortcut(",")
        Divider()
        Button("Quitter Timebox Bridge") { model.quit() }
            .keyboardShortcut("q")
    }
}

/// Sous-menu « Appareil » : les Divoom appairés en tête, les autres dans « Tous les appareils ».
struct DeviceMenu: View {
    let model: BridgeModel

    var body: some View {
        let divoom = model.devices.filter(\.isDivoom)
        let others = model.devices.filter { !$0.isDivoom }
        Menu("Appareil : \(model.deviceName ?? model.address ?? "aucun")") {
            if let address = model.address, !model.devicePaired {
                Toggle(isOn: .constant(true)) {
                    Text("\(model.deviceName ?? address) (non appairé)")
                }
                .disabled(true)
            }
            if divoom.isEmpty {
                Text("Aucun appareil Divoom appairé")
            }
            ForEach(divoom, id: \.address) { device in
                item(device)
            }
            if !others.isEmpty {
                Menu("Tous les appareils") {
                    ForEach(others, id: \.address) { device in
                        item(device)
                    }
                }
            }
            Divider()
            Button("Actualiser la liste") { model.refreshDevices() }
        }
    }

    private func item(_ device: PairedDevice) -> some View {
        Toggle(isOn: Binding(
            get: { model.address?.caseInsensitiveCompare(device.address) == .orderedSame },
            set: { if $0 { model.select(device) } }
        )) {
            Text(device.isConnected ? "\(device.name) (connecté)" : device.name)
        }
    }
}

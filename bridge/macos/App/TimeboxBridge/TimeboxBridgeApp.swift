import SwiftUI
import TimeboxBridgeCore

/// Application de barre de menu : le relais timebox-bridge, sans fenêtre ni icône de Dock
/// (`LSUIElement`). L'état du relais se lit sur l'icône et dans le menu.
@main
struct TimeboxBridgeApp: App {
    @State private var model = BridgeModel()

    var body: some Scene {
        MenuBarExtra {
            MenuContent(model: model)
        } label: {
            Image(systemName: model.symbol)
                .accessibilityLabel("Timebox Bridge : \(model.summary)")
        }
    }
}

struct MenuContent: View {
    let model: BridgeModel

    var body: some View {
        Text(model.summary)
        if model.status == .noDevice {
            Text("Choix de l'appareil : bientôt dans ce menu")
        }
        Divider()
        Button("Quitter Timebox Bridge") { model.quit() }
            .keyboardShortcut("q")
    }
}

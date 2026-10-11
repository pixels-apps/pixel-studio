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
        Window("Journal de Timebox Bridge", id: LogWindow.id) {
            LogWindow(model: model)
        }
        .defaultSize(width: 720, height: 420)
        Settings {
            SettingsView(model: model)
        }
    }
}

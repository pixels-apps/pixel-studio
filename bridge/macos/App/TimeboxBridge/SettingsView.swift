import ServiceManagement
import SwiftUI
import TimeboxBridgeCore

/// Fenêtre « Réglages » : écoute du relais (appliquée par un redémarrage), journal verbeux et
/// lancement à l'ouverture de session (appliqués aussitôt).
struct SettingsView: View {
    let model: BridgeModel

    @State private var host = ""
    @State private var port = ""
    @State private var retries = 5
    @Environment(\.controlActiveState) private var activeState

    private var parsedPort: UInt16? { BridgeConfig.port(from: port) }
    private var hostIsValid: Bool { !host.trimmingCharacters(in: .whitespaces).isEmpty }
    private var isValid: Bool { parsedPort != nil && hostIsValid }
    private var isModified: Bool {
        let s = model.settings
        return host.trimmingCharacters(in: .whitespaces) != s.host || parsedPort != s.port || retries != s.retries
    }

    var body: some View {
        Form {
            Section {
                TextField("Hôte", text: $host, prompt: Text("127.0.0.1"))
                if !hostIsValid {
                    note("Indiquez une adresse, par exemple 127.0.0.1.", .red)
                } else if !BridgeConfig.isLoopback(host: host) {
                    note("Le relais sera accessible depuis le réseau : tout appareil connecté pourra piloter le Timebox.",
                         .orange)
                }
                TextField("Port", text: $port, prompt: Text("7777"))
                if parsedPort == nil {
                    note("Port de 1 à 65535.", .red)
                }
                Stepper("Essais d'ouverture du canal : \(retries)", value: $retries, in: 1...20)
                HStack {
                    Button("Valeurs par défaut") { load(BridgeConfig()) }
                    Spacer()
                    Button("Annuler") { load(model.settings) }
                        .disabled(!isModified)
                    Button("Appliquer") { model.apply(host: host, port: parsedPort!, retries: retries) }
                        .keyboardShortcut(.defaultAction)
                        .disabled(!isValid || !isModified)
                }
            } header: {
                Text("Relais")
            } footer: {
                Text("Appliquer redémarre le relais : le client connecté (pixel-studio) se reconnecte à sa prochaine requête.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("Journal") {
                Toggle("Journal verbeux (chaque octet échangé)", isOn: Binding(
                    get: { model.verbose }, set: { model.setVerbose($0) }))
            }

            Section("Démarrage") {
                Toggle("Lancer à l'ouverture de session", isOn: Binding(
                    get: { model.loginItemStatus == .enabled }, set: { model.setLaunchAtLogin($0) }))
                if model.loginItemStatus == .requiresApproval {
                    HStack {
                        note("À autoriser dans Réglages système → Général → Ouverture.", .orange)
                        Button("Ouvrir les réglages") { SMAppService.openSystemSettingsLoginItems() }
                    }
                }
                if let error = model.loginItemError {
                    note(error, .red)
                }
            }
        }
        .formStyle(.grouped)
        .frame(width: 460)
        .fixedSize(horizontal: false, vertical: true)
        .onAppear {
            load(model.settings)
            model.refreshLoginItem()
        }
        .onChange(of: activeState) {
            if activeState == .key { model.refreshLoginItem() }  // retour depuis Réglages système
        }
    }

    private func load(_ c: BridgeConfig) {
        host = c.host
        port = String(c.port)
        retries = c.retries
    }

    private func note(_ text: String, _ color: Color) -> some View {
        Text(text).font(.caption).foregroundStyle(color)
    }
}

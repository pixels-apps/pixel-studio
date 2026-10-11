import AppKit
import Observation
import TimeboxBridgeCore

/// État de l'application : possède le relais, relaie son état vers le menu, lit les réglages.
@Observable
@MainActor
final class BridgeModel {
    private(set) var state = BridgeState()
    /// Erreur au démarrage du relais (adresse invalide, écoute impossible à créer).
    private(set) var startError: String?
    private(set) var address: String?
    private(set) var deviceName: String?

    @ObservationIgnored let logBuffer = LogBuffer()
    @ObservationIgnored private var bridge: Bridge?
    @ObservationIgnored private let defaults = UserDefaults.standard

    init() {
        let buffer = logBuffer
        Log.shared.addSink { buffer.append($0) }
        Log.shared.verbose = defaults.bool(forKey: "verbose")
        start()
    }

    /// Configuration lue dans les réglages (`UserDefaults`) ; adresse absente = aucun appareil choisi.
    private func config() -> BridgeConfig? {
        guard let address = defaults.string(forKey: "address"), !address.isEmpty else { return nil }
        var c = BridgeConfig()
        c.address = address
        if let host = defaults.string(forKey: "host"), !host.isEmpty { c.host = host }
        if let port = UInt16(exactly: defaults.integer(forKey: "port")), port != 0 { c.port = port }
        if defaults.integer(forKey: "retries") > 0 { c.retries = defaults.integer(forKey: "retries") }
        return c
    }

    func start() {
        stop()
        startError = nil
        guard let config = config() else {
            address = nil
            deviceName = nil
            state = BridgeState()
            return
        }
        address = config.address
        do {
            let bridge = try Bridge(config: config)
            bridge.onStateChange = { [weak self] in self?.state = $0 }
            self.bridge = bridge
            deviceName = bridge.deviceName
            try bridge.start()
        } catch {
            startError = "\(error)"
            Log.shared.info("démarrage impossible : \(error)")
        }
    }

    func stop() {
        bridge?.stop()
        bridge = nil
        state = BridgeState()
    }

    func quit() {
        stop()
        NSApp.terminate(nil)
    }

    // MARK: Présentation

    enum Status {
        case noDevice, stopped, listening, opening, connected, error
    }

    var status: Status {
        if startError != nil { return .error }
        if address == nil { return .noDevice }
        switch (state.listener, state.channel) {
        case (.failed, _), (_, .gaveUp): return .error
        case (.stopped, _), (.starting, _): return .stopped
        case (_, .open): return .connected
        case (_, .opening): return .opening
        case (_, .closed): return .listening
        }
    }

    /// Symbole SF de la barre de menu.
    var symbol: String {
        switch status {
        case .noDevice, .stopped: "antenna.radiowaves.left.and.right.slash"
        case .listening: "antenna.radiowaves.left.and.right"
        case .opening: "arrow.triangle.2.circlepath"
        case .connected: "dot.radiowaves.left.and.right"
        case .error: "exclamationmark.triangle"
        }
    }

    var summary: String {
        if let startError { return "Erreur : \(startError)" }
        switch status {
        case .noDevice: return "Aucun appareil choisi"
        case .stopped: return "Relais arrêté"
        case .error:
            if case .failed(let message) = state.listener { return "Écoute impossible : \(message)" }
            if case .gaveUp(let reason) = state.channel { return "Bluetooth : échec (\(reason))" }
            return "Erreur"
        case .listening, .opening, .connected:
            return "Relais vers \(deviceName ?? address ?? "?")"
        }
    }
}

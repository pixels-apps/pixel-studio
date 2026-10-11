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
    /// Appareils appairés (actualisés au lancement, au choix d'un appareil et à la demande).
    private(set) var devices: [PairedDevice] = []
    /// Change à chaque nouveau message du journal (la fenêtre Journal relit `logBuffer`).
    private(set) var logRevision = 0

    @ObservationIgnored let logBuffer = LogBuffer()
    @ObservationIgnored private var bridge: Bridge?
    @ObservationIgnored private let defaults = UserDefaults.standard

    init() {
        let buffer = logBuffer
        Log.shared.addSink { [weak self] entry in
            buffer.append(entry)
            DispatchQueue.main.async { self?.logRevision += 1 }
        }
        Log.shared.verbose = defaults.bool(forKey: "verbose")
        refreshDevices()
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

    /// Choisit l'appareil à relayer (mémorisé) et redémarre le relais.
    func select(_ device: PairedDevice) {
        guard device.address.caseInsensitiveCompare(address ?? "") != .orderedSame else { return }
        Log.shared.info("appareil choisi : \(device.name) (\(device.address))")
        defaults.set(device.address, forKey: "address")
        start()
    }

    func refreshDevices() {
        devices = PairedDevice.paired().sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
    }

    func reconnect() {
        bridge?.reconnect()
    }

    var canReconnect: Bool { bridge != nil && state.listener != .stopped }

    func clearLog() {
        logBuffer.clear()
        logRevision += 1
    }

    func quit() {
        stop()
        NSApp.terminate(nil)
    }

    // MARK: Présentation

    var listenerLine: String {
        switch state.listener {
        case .stopped: "Écoute : arrêtée"
        case .starting: "Écoute : démarrage…"
        case .listening(let host, let port): "Écoute : \(host):\(port)"
        case .failed(let message): "Écoute impossible : \(message)"
        }
    }

    var channelLine: String {
        switch state.channel {
        case .closed: "Bluetooth : canal fermé (ouverture à la connexion d'un client)"
        case .opening(let attempt, let total): "Bluetooth : ouverture (essai \(attempt)/\(total))…"
        case .open(let mtu): "Bluetooth : canal ouvert (MTU \(mtu))"
        case .gaveUp(let reason): "Bluetooth : échec (\(reason)), nouvel essai au prochain envoi"
        }
    }

    var clientLine: String {
        state.client.map { "Client : \($0)" } ?? "Client : aucun"
    }

    var bytesLine: String {
        "Octets : \(state.bytesToDevice) envoyés · \(state.bytesFromDevice) reçus"
    }

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

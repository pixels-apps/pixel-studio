import AppKit
import CoreBluetooth
import Observation
import ServiceManagement
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
    /// Canal RFCOMM utilisé, et canal du port série détecté pour l'appareil choisi (`nil` si inconnu).
    private(set) var channel: UInt8?
    private(set) var detectedChannel: UInt8?
    /// Appareils appairés (actualisés au lancement, au choix d'un appareil et à la demande).
    private(set) var devices: [PairedDevice] = []
    /// L'appareil choisi est-il encore appairé ?
    private(set) var devicePaired = true
    /// Bluetooth du Mac activé ?
    private(set) var bluetoothOn = true
    /// Accès au Bluetooth refusé à l'application (Réglages système → Confidentialité).
    private(set) var bluetoothDenied = false
    /// Change à chaque nouveau message du journal (la fenêtre Journal relit `logBuffer`).
    private(set) var logRevision = 0
    /// Journal verbeux (chaque octet échangé).
    private(set) var verbose = false
    /// Lancement à l'ouverture de session (relu : l'utilisateur peut le changer dans Réglages système).
    private(set) var loginItemStatus = SMAppService.mainApp.status
    private(set) var loginItemError: String?

    /// Délai entre deux tentatives d'écoute quand le port est déjà utilisé.
    static let portRetryDelay: TimeInterval = 5

    @ObservationIgnored let logBuffer = LogBuffer()
    @ObservationIgnored private var bridge: Bridge?
    @ObservationIgnored private var portRetry: DispatchWorkItem?
    @ObservationIgnored private let defaults = UserDefaults.standard

    init() {
        let buffer = logBuffer
        Log.shared.addSink { [weak self] entry in
            buffer.append(entry)
            DispatchQueue.main.async { self?.logRevision += 1 }
        }
        verbose = defaults.bool(forKey: "verbose")
        Log.shared.verbose = verbose
        observeSleep()
        refreshDevices()
        start()
    }

    /// Configuration lue dans les réglages (`UserDefaults`) ; adresse absente = aucun appareil choisi.
    private func config() -> BridgeConfig? {
        guard let address = defaults.string(forKey: "address"), !address.isEmpty else { return nil }
        var c = settings
        c.address = address
        c.channel = channelOverride(for: address) ?? PairedDevice.serialChannel(address: address) ?? 1
        return c
    }

    /// Canal imposé dans les réglages pour cet appareil (`nil` = automatique).
    func channelOverride(for address: String) -> UInt8? {
        let channels = defaults.dictionary(forKey: "channels") as? [String: Int] ?? [:]
        return channels[address.lowercased()].flatMap(UInt8.init(exactly:))
    }

    /// Impose un canal pour l'appareil choisi (`nil` = automatique) et redémarre le relais.
    func setChannelOverride(_ channel: UInt8?) {
        guard let address else { return }
        var channels = defaults.dictionary(forKey: "channels") as? [String: Int] ?? [:]
        channels[address.lowercased()] = channel.map(Int.init)
        defaults.set(channels, forKey: "channels")
        Log.shared.info("canal RFCOMM : \(channel.map { "\($0) (imposé)" } ?? "automatique")")
        start()
    }

    /// Réglages du relais (hôte, port, tentatives), valeurs par défaut de la CLI si absents.
    var settings: BridgeConfig {
        var c = BridgeConfig()
        if let host = defaults.string(forKey: "host"), !host.isEmpty { c.host = host }
        if let port = UInt16(exactly: defaults.integer(forKey: "port")), port != 0 { c.port = port }
        if defaults.integer(forKey: "retries") > 0 { c.retries = defaults.integer(forKey: "retries") }
        return c
    }

    /// Enregistre les réglages du relais et le redémarre (le client connecté est déconnecté).
    func apply(host: String, port: UInt16, retries: Int) {
        let host = host.trimmingCharacters(in: .whitespaces)
        defaults.set(host, forKey: "host")
        defaults.set(Int(port), forKey: "port")
        defaults.set(retries, forKey: "retries")
        Log.shared.info("réglages : écoute \(host):\(port), \(retries) essais d'ouverture")
        start()
    }

    func setVerbose(_ on: Bool) {
        verbose = on
        defaults.set(on, forKey: "verbose")
        Log.shared.verbose = on
        Log.shared.info("journal verbeux : \(on ? "activé" : "désactivé")")
    }

    func refreshLoginItem() {
        loginItemStatus = SMAppService.mainApp.status
    }

    func setLaunchAtLogin(_ on: Bool) {
        loginItemError = nil
        do {
            if on { try SMAppService.mainApp.register() } else { try SMAppService.mainApp.unregister() }
        } catch {
            loginItemError = error.localizedDescription
        }
        refreshLoginItem()
        Log.shared.info("ouverture de session : \(loginItemStatus == .enabled ? "activée" : "désactivée")")
    }

    func start() {
        stop()
        startError = nil
        refreshBluetooth()
        guard let config = config() else {
            address = nil
            deviceName = nil
            channel = nil
            detectedChannel = nil
            state = BridgeState()
            return
        }
        address = config.address
        channel = config.channel
        detectedChannel = PairedDevice.serialChannel(address: config.address)
        devicePaired = PairedDevice.isPaired(address: config.address)
        if !devicePaired {
            Log.shared.info("l'appareil \(config.address) n'est plus appairé à ce Mac")
        }
        do {
            let bridge = try Bridge(config: config)
            bridge.onStateChange = { [weak self] in self?.stateChanged($0) }
            self.bridge = bridge
            deviceName = bridge.deviceName
            try bridge.start()
        } catch {
            startError = "\(error)"
            Log.shared.info("démarrage impossible : \(error)")
        }
    }

    func stop() {
        portRetry?.cancel()
        portRetry = nil
        bridge?.stop()
        bridge = nil
        state = BridgeState()
    }

    private func stateChanged(_ new: BridgeState) {
        state = new
        switch new.channel {
        case .gaveUp, .opening: refreshBluetooth()
        default: break
        }
        // Port déjà utilisé (souvent la CLI) : nouvel essai régulier de l'écoute, le relais prend la
        // place dès qu'elle se libère.
        if case .portInUse = new.listener, portRetry == nil {
            let work = DispatchWorkItem { [weak self] in
                MainActor.assumeIsolated {
                    guard let self else { return }
                    self.portRetry = nil
                    do { try self.bridge?.listen() } catch { self.start() }
                }
            }
            portRetry = work
            DispatchQueue.main.asyncAfter(deadline: .now() + Self.portRetryDelay, execute: work)
        }
    }

    /// Choisit l'appareil à relayer (mémorisé) et redémarre le relais.
    func select(_ device: PairedDevice) {
        guard device.address.caseInsensitiveCompare(address ?? "") != .orderedSame || !devicePaired else { return }
        Log.shared.info("appareil choisi : \(device.name) (\(device.address))")
        defaults.set(device.address, forKey: "address")
        start()
    }

    func refreshDevices() {
        devices = PairedDevice.paired().sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
        if let address { devicePaired = PairedDevice.isPaired(address: address) }
        refreshBluetooth()
    }

    func refreshBluetooth() {
        bluetoothOn = BluetoothHost.isPoweredOn
        bluetoothDenied = [.denied, .restricted].contains(CBManager.authorization)
    }

    func openBluetoothPrivacySettings() {
        NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Bluetooth")!)
    }

    func reconnect() {
        refreshBluetooth()
        bridge?.reconnect()
    }

    /// Nouvel essai d'écoute immédiat (port déjà utilisé).
    func retryListening() {
        portRetry?.cancel()
        portRetry = nil
        do { try bridge?.listen() } catch { start() }
    }

    var canReconnect: Bool {
        guard bridge != nil, case .listening = state.listener else { return false }
        return true
    }

    var isWaitingForPort: Bool {
        if case .portInUse = state.listener { return true }
        return false
    }

    /// Mise en veille : le canal Bluetooth ne survit pas ; on le ferme proprement et il sera rouvert
    /// au premier envoi après le réveil.
    private func observeSleep() {
        let center = NSWorkspace.shared.notificationCenter
        center.addObserver(forName: NSWorkspace.willSleepNotification, object: nil, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.bridge?.suspend() }
        }
        center.addObserver(forName: NSWorkspace.didWakeNotification, object: nil, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated {
                Log.shared.info("réveil du Mac")
                self?.refreshBluetooth()
            }
        }
    }

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
        case .portInUse(let port): "Écoute : port \(port) déjà utilisé, nouvel essai toutes les \(Int(Self.portRetryDelay)) s"
        case .failed(let message): "Écoute impossible : \(message)"
        }
    }

    var channelLine: String {
        let name = "Bluetooth, canal \(channel.map(String.init) ?? "?")"
        return switch state.channel {
        case .closed: "\(name) : fermé (ouverture à la connexion d'un client)"
        case .opening(let attempt, let total): "\(name) : ouverture (essai \(attempt)/\(total))…"
        case .open(let mtu): "\(name) : ouvert (MTU \(mtu))"
        case .gaveUp(let reason): "\(name) : échec (\(reason)), nouvel essai au prochain envoi"
        }
    }

    var clientLine: String {
        state.client.map { "Client : \($0)" } ?? "Client : aucun"
    }

    var bytesLine: String {
        "Octets : \(state.bytesToDevice) envoyés · \(state.bytesFromDevice) reçus"
    }

    /// Conseil affiché sous le résumé quand quelque chose bloque (sinon `nil`).
    var hint: String? {
        if bluetoothDenied { return "Autorisez Timebox Bridge dans Confidentialité et sécurité → Bluetooth." }
        if address != nil, !devicePaired { return "Appairez-le de nouveau ou choisissez un autre appareil." }
        if isWaitingForPort { return "Un autre relais (CLI ou application) tourne-t-il déjà ?" }
        if address != nil, !bluetoothOn { return "Activez le Bluetooth dans Réglages système." }
        if case .gaveUp = state.channel {
            return "Appareil éteint, hors de portée ou canal pris par l'appli Divoom du téléphone ?"
        }
        return nil
    }

    enum Status {
        case noDevice, stopped, listening, opening, connected, error
    }

    var status: Status {
        if startError != nil || bluetoothDenied { return .error }
        if address == nil { return .noDevice }
        if !devicePaired || !bluetoothOn { return .error }
        switch (state.listener, state.channel) {
        case (.failed, _), (.portInUse, _), (_, .gaveUp): return .error
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
        if bluetoothDenied { return "Accès au Bluetooth refusé" }
        if address == nil { return "Aucun appareil choisi" }
        if !devicePaired { return "\(deviceName ?? address ?? "L'appareil") n'est plus appairé" }
        if case .portInUse(let port) = state.listener { return "Port \(port) déjà utilisé" }
        if case .failed(let message) = state.listener { return "Écoute impossible : \(message)" }
        if !bluetoothOn { return "Bluetooth désactivé" }
        if case .gaveUp = state.channel { return "Appareil injoignable" }
        if status == .stopped { return "Relais arrêté" }
        return "Relais vers \(deviceName ?? address ?? "?")"
    }
}

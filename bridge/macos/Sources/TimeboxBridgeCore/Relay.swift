import Foundation

/// État du canal Bluetooth vu par le relais.
public enum ChannelState: Equatable, Sendable {
    case closed
    case opening(attempt: Int, of: Int)
    case open(mtu: Int)
    /// Abandon après le dernier essai ; nouvel essai au prochain envoi.
    case gaveUp(reason: String)
}

/// Cœur du relais, sans réseau : un client à la fois, octets relayés tels quels, ouverture du canal
/// à la connexion d'un client ou au premier envoi, avec plusieurs essais (le premier échoue souvent)
/// et un délai maximal par essai ; réouverture à la demande si l'appareil ferme le canal.
///
/// Le serveur TCP lui signale les clients et leurs octets ; il renvoie les octets de l'appareil et
/// les déconnexions par `sendToClient` et `disconnectClient`.
@MainActor
public final class Relay: BluetoothChannelDelegate {
    public typealias ClientID = Int

    public let config: BridgeConfig
    let device: BluetoothDevice
    let scheduler: Scheduler
    let log: Log

    public var sendToClient: (ClientID, Data) -> Void = { _, _ in }
    public var disconnectClient: (ClientID) -> Void = { _ in }
    public var onChange: () -> Void = {}

    public private(set) var channelState = ChannelState.closed { didSet { if channelState != oldValue { onChange() } } }
    public private(set) var client: ClientID? { didSet { if client != oldValue { onChange() } } }
    public private(set) var clientDescription: String?
    public private(set) var bytesToDevice = 0
    public private(set) var bytesFromDevice = 0

    private var channel: BluetoothChannel?
    private var openingChannel: BluetoothChannel?
    private var opening = false
    private var attempt = 0
    private var pending: [UInt8] = []  // octets du client en attente de l'ouverture du canal
    private var timeout: ScheduledWork?
    private var retry: ScheduledWork?

    public init(config: BridgeConfig, device: BluetoothDevice, scheduler: Scheduler = MainQueueScheduler(),
                log: Log = .shared) {
        self.config = config
        self.device = device
        self.scheduler = scheduler
        self.log = log
    }

    public var pendingCount: Int { pending.count }

    // MARK: Clients

    public func clientConnected(_ id: ClientID, description: String) {
        if let previous = client {
            log.info("nouveau client : l'ancien est déconnecté")
            disconnectClient(previous)
        }
        pending.removeAll()
        clientDescription = description
        client = id
        ensureChannel()
    }

    public func clientDisconnected(_ id: ClientID) {
        guard id == client else { return }
        pending.removeAll()
        clientDescription = nil
        client = nil
        log.info("client déconnecté")
    }

    public func received(_ data: Data, from id: ClientID) {
        guard id == client, !data.isEmpty else { return }
        log.debug("TCP → BT : \(hex(data))")
        pending.append(contentsOf: data)
        flush()
    }

    // MARK: Commandes

    /// Ferme le canal (ou abandonne l'ouverture en cours) et le rouvre après `retryDelay` : une
    /// réouverture immédiate reste sans réponse (constaté avec le Timebox Evo).
    public func reconnect() {
        log.info("reconnexion demandée (réouverture dans \(seconds(config.retryDelay)))")
        closeChannel()
        opening = true
        attempt = 0
        retry = scheduler.schedule(after: config.retryDelay) { [weak self] in self?.tryOpen() }
    }

    /// Ferme le canal (mise en veille du Mac) ; il sera rouvert au prochain envoi du client.
    public func suspend() {
        guard channel != nil || opening else { return }
        closeChannel()
        log.info("mise en veille : canal \(config.channel) fermé (réouverture au prochain envoi)")
    }

    /// Ferme le canal et déconnecte le client.
    public func stop() {
        closeChannel()
        pending.removeAll()
        if let client {
            disconnectClient(client)
            clientDescription = nil
            self.client = nil
        }
    }

    private func closeChannel() {
        timeout?.cancel()
        retry?.cancel()
        openingChannel?.close()
        openingChannel = nil
        opening = false
        channel?.close()
        channel = nil
        channelState = .closed
    }

    // MARK: Bluetooth

    func ensureChannel() {
        guard channel == nil, !opening else { return }
        opening = true
        attempt = 0
        tryOpen()
    }

    private func tryOpen() {
        attempt += 1
        log.info("ouverture du canal \(config.channel) (essai \(attempt)/\(config.retries))…")
        channelState = .opening(attempt: attempt, of: config.retries)
        let (ch, r) = device.openChannel(config.channel, delegate: self)
        guard r == 0 else { openFailed(describe(r)); return }
        openingChannel = ch
        timeout = scheduler.schedule(after: config.openTimeout) { [weak self] in self?.openTimedOut() }
        // sinon : channelOpenComplete sera appelé
    }

    private func openTimedOut() {
        guard let ch = openingChannel else { return }
        openingChannel = nil
        ch.close()
        log.info("pas de réponse après \(seconds(config.openTimeout)) (appareil éteint ou hors de portée, ou canal pris par un autre programme ?)")
        openFailed("délai dépassé")
    }

    private func openFailed(_ reason: String) {
        if attempt < config.retries {
            log.info("échec \(reason), nouvel essai dans \(seconds(config.retryDelay))")
            retry = scheduler.schedule(after: config.retryDelay) { [weak self] in self?.tryOpen() }
        } else {
            log.info("échec \(reason) : abandon après \(attempt) essais (nouvel essai au prochain envoi)")
            opening = false
            channelState = .gaveUp(reason: reason)
            if !pending.isEmpty {
                log.info("\(pending.count) octets en attente abandonnés")
                pending.removeAll()
            }
        }
    }

    public func channelOpenComplete(_ ch: BluetoothChannel, status: Int32) {
        guard ch === openingChannel else {
            // essai déjà abandonné (délai dépassé) : on referme le canal s'il s'est ouvert entre-temps
            if status == 0 { ch.close() }
            return
        }
        timeout?.cancel()
        openingChannel = nil
        guard status == 0 else { openFailed(describe(status)); return }
        channel = ch
        opening = false
        log.info("canal \(config.channel) ouvert (MTU \(ch.mtu))")
        channelState = .open(mtu: ch.mtu)
        flush()
    }

    func flush() {
        guard !pending.isEmpty else { return }
        guard let ch = channel, ch.isOpen else { ensureChannel(); return }
        let mtu = max(1, ch.mtu)
        while !pending.isEmpty {
            let chunk = Array(pending.prefix(mtu))
            let r = ch.write(chunk)
            if r != 0 {
                log.info("écriture Bluetooth en échec \(describe(r)), \(pending.count) octets conservés")
                return
            }
            pending.removeFirst(chunk.count)
            bytesToDevice += chunk.count
            onChange()
        }
    }

    public func channelReceived(_ ch: BluetoothChannel, data: Data) {
        log.debug("BT → TCP : \(hex(data))")
        bytesFromDevice += data.count
        onChange()
        guard let client else {
            log.debug("(aucun client, \(data.count) octets ignorés)")
            return
        }
        sendToClient(client, data)
    }

    public func channelClosed(_ ch: BluetoothChannel) {
        guard ch === channel else { return }
        channel = nil
        channelState = .closed
        log.info("canal \(config.channel) fermé (réouverture au prochain envoi)")
    }
}

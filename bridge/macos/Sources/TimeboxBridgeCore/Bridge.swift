import Foundation
import Network

// Contrat (v1, voir docs/architecture.md) :
//  - écoute TCP (défaut 127.0.0.1:7777), un seul client à la fois : un nouveau client remplace
//    l'ancien ;
//  - les octets sont relayés tels quels dans les deux sens, sans interprétation des trames ;
//  - le relais gère seul le Bluetooth (voir `Relay`).

/// État complet du relais, publié à chaque changement.
public struct BridgeState: Equatable, Sendable {
    public enum Listener: Equatable, Sendable {
        case stopped
        case starting
        case listening(host: String, port: UInt16)
        case failed(String)
    }

    public var listener = Listener.stopped
    public var channel = ChannelState.closed
    /// Adresse du client TCP connecté.
    public var client: String?
    public var bytesToDevice = 0
    public var bytesFromDevice = 0

    public init() {}
}

public enum BridgeError: Error, CustomStringConvertible {
    case invalidAddress(String)

    public var description: String {
        switch self {
        case .invalidAddress(let a): "adresse Bluetooth invalide : \(a)"
        }
    }
}

/// Relais complet : serveur TCP + `Relay`. Partagé par la ligne de commande et l'application.
@MainActor
public final class Bridge {
    public let config: BridgeConfig
    public private(set) var state = BridgeState() {
        didSet { if state != oldValue { onStateChange(state) } }
    }
    public var onStateChange: (BridgeState) -> Void = { _ in }

    /// Nom Bluetooth de l'appareil (ex. « TimeBox-Evo-audio »).
    public var deviceName: String? { device.name }

    let device: BluetoothDevice
    let relay: Relay
    let log: Log
    private var listener: NWListener?
    private var connections: [Relay.ClientID: NWConnection] = [:]
    private var nextClientID = 0

    /// `device` : appareil à utiliser (par défaut, l'appareil IOBluetooth de `config.address`).
    public init(config: BridgeConfig, device: BluetoothDevice? = nil, scheduler: Scheduler = MainQueueScheduler(),
                log: Log = .shared) throws {
        guard let device = device ?? IOBluetoothRFCOMMDevice(address: config.address) else {
            throw BridgeError.invalidAddress(config.address)
        }
        self.config = config
        self.device = device
        self.log = log
        relay = Relay(config: config, device: device, scheduler: scheduler, log: log)
        relay.sendToClient = { [weak self] id, data in self?.send(data, to: id) }
        relay.disconnectClient = { [weak self] id in self?.disconnect(id) }
        relay.onChange = { [weak self] in self?.refresh() }
    }

    // MARK: Commandes

    public func start() throws {
        let params = NWParameters.tcp
        params.allowLocalEndpointReuse = true
        params.requiredLocalEndpoint = .hostPort(host: .init(config.host), port: .init(rawValue: config.port)!)
        let listener = try NWListener(using: params)
        listener.stateUpdateHandler = { [weak self] st in
            MainActor.assumeIsolated { self?.listenerChanged(st) }
        }
        listener.newConnectionHandler = { [weak self] connection in
            MainActor.assumeIsolated { self?.accept(connection) }
        }
        state.listener = .starting
        listener.start(queue: .main)
        self.listener = listener
        log.info("relais vers \(device.name ?? config.address) (\(config.address)), canal RFCOMM \(config.channel)")
    }

    /// Arrête l'écoute, déconnecte le client et ferme le canal.
    public func stop() {
        log.info("arrêt")
        relay.stop()
        for connection in connections.values { connection.cancel() }
        connections.removeAll()
        listener?.cancel()
        listener = nil
        state.listener = .stopped
    }

    /// Ferme le canal Bluetooth et le rouvre.
    public func reconnect() {
        relay.reconnect()
    }

    // MARK: TCP

    private func listenerChanged(_ st: NWListener.State) {
        switch st {
        case .ready:
            log.info("écoute sur \(config.host):\(config.port)")
            state.listener = .listening(host: config.host, port: config.port)
        case .failed(let error):
            log.info("écoute impossible : \(error)")
            state.listener = .failed("\(error)")
            listener?.cancel()
            listener = nil
        default:
            break
        }
    }

    private func accept(_ connection: NWConnection) {
        nextClientID += 1
        let id = nextClientID
        connections[id] = connection
        connection.stateUpdateHandler = { [weak self] st in
            MainActor.assumeIsolated {
                switch st {
                case .ready: self?.log.info("client connecté : \(connection.endpoint)")
                case .failed(let error): self?.log.info("client en erreur : \(error)"); self?.drop(id)
                default: break
                }
            }
        }
        connection.start(queue: .main)
        receive(from: id)
        relay.clientConnected(id, description: "\(connection.endpoint)")
    }

    private func receive(from id: Relay.ClientID) {
        guard let connection = connections[id] else { return }
        connection.receive(minimumIncompleteLength: 1, maximumLength: 4096) { [weak self] data, _, isComplete, error in
            MainActor.assumeIsolated {
                guard let self, self.connections[id] != nil else { return }
                if let data { self.relay.received(data, from: id) }
                if isComplete || error != nil {
                    self.drop(id)
                } else {
                    self.receive(from: id)
                }
            }
        }
    }

    private func drop(_ id: Relay.ClientID) {
        guard let connection = connections.removeValue(forKey: id) else { return }
        connection.cancel()
        relay.clientDisconnected(id)
    }

    /// Déconnexion demandée par le relais (un nouveau client remplace l'ancien).
    private func disconnect(_ id: Relay.ClientID) {
        connections.removeValue(forKey: id)?.cancel()
    }

    private func send(_ data: Data, to id: Relay.ClientID) {
        connections[id]?.send(content: data, completion: .contentProcessed { [weak self] error in
            if let error { self?.log.info("envoi TCP en échec : \(error)") }
        })
    }

    private func refresh() {
        state.channel = relay.channelState
        state.client = relay.clientDescription
        state.bytesToDevice = relay.bytesToDevice
        state.bytesFromDevice = relay.bytesFromDevice
    }
}

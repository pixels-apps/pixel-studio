import Foundation
import IOBluetooth
import Network

// timebox-bridge : relais transparent TCP <-> RFCOMM pour le Divoom Timebox Evo (macOS).
//
// Contrat (v1, voir docs/architecture.md) :
//  - écoute TCP (défaut 127.0.0.1:7777), un seul client à la fois : un nouveau client remplace
//    l'ancien ;
//  - les octets sont relayés tels quels dans les deux sens, sans interprétation des trames ;
//  - le relais gère seul le Bluetooth : ouverture du canal à la connexion d'un client ou au premier
//    envoi, avec plusieurs tentatives (la première échoue souvent), réouverture à la demande si
//    l'appareil ferme le canal.
//
// Usage : timebox-bridge --address AA-BB-CC-DD-EE-FF [--channel 1] [--host 127.0.0.1]
//                        [--port 7777] [--retries 5] [--verbose]
//         timebox-bridge --list      (appareils appairés, pour trouver l'adresse)
// Équivalents en variables d'environnement : TIMEBOX_ADDRESS, TIMEBOX_CHANNEL, BRIDGE_HOST,
// BRIDGE_PORT, BRIDGE_RETRIES, BRIDGE_VERBOSE=1.

struct Config {
    var address = ""
    var channel: BluetoothRFCOMMChannelID = 1
    var host = "127.0.0.1"
    var port: UInt16 = 7777
    var retries = 5
    var verbose = false

    static func load() -> Config {
        var c = Config()
        let env = ProcessInfo.processInfo.environment
        if let v = env["TIMEBOX_ADDRESS"] { c.address = v }
        if let v = env["TIMEBOX_CHANNEL"].flatMap(UInt8.init) { c.channel = v }
        if let v = env["BRIDGE_HOST"] { c.host = v }
        if let v = env["BRIDGE_PORT"].flatMap(UInt16.init) { c.port = v }
        if let v = env["BRIDGE_RETRIES"].flatMap(Int.init) { c.retries = v }
        if env["BRIDGE_VERBOSE"] == "1" { c.verbose = true }

        var args = CommandLine.arguments.dropFirst().makeIterator()
        while let arg = args.next() {
            switch arg {
            case "--address": c.address = args.next() ?? c.address
            case "--channel": c.channel = args.next().flatMap(UInt8.init) ?? c.channel
            case "--host": c.host = args.next() ?? c.host
            case "--port": c.port = args.next().flatMap(UInt16.init) ?? c.port
            case "--retries": c.retries = args.next().flatMap(Int.init) ?? c.retries
            case "-v", "--verbose": c.verbose = true
            case "--list": listPairedDevices(); exit(0)
            case "-h", "--help":
                print("usage: timebox-bridge --address AA-BB-CC-DD-EE-FF [--channel 1] "
                    + "[--host 127.0.0.1] [--port 7777] [--retries 5] [--verbose]")
                print("       timebox-bridge --list    (appareils Bluetooth appairés)")
                exit(0)
            default:
                fputs("argument inconnu : \(arg)\n", stderr); exit(64)
            }
        }
        if c.address.isEmpty {
            fputs("adresse de l'appareil manquante : --address AA-BB-CC-DD-EE-FF (ou TIMEBOX_ADDRESS)\n"
                + "pour la trouver : timebox-bridge --list\n", stderr)
            exit(64)
        }
        return c
    }
}

/// Liste les appareils appairés ; les Divoom (nom contenant « timebox » ou « divoom ») sont signalés.
func listPairedDevices() {
    let devices = (IOBluetoothDevice.pairedDevices() ?? []).compactMap { $0 as? IOBluetoothDevice }
    if devices.isEmpty {
        print("aucun appareil appairé (Réglages système → Bluetooth)")
        return
    }
    for device in devices {
        let name = device.name ?? "?"
        let divoom = ["timebox", "divoom", "pixoo", "ditoo", "tivoo"].contains { name.lowercased().contains($0) }
        print("\(divoom ? "→" : " ") \(device.addressString ?? "?")  \(name)\(device.isConnected() ? "  (connecté)" : "")")
    }
}

let timestamp: DateFormatter = {
    let f = DateFormatter(); f.dateFormat = "HH:mm:ss.SSS"; return f
}()

func log(_ message: String) {
    print("\(timestamp.string(from: Date())) \(message)")
    fflush(stdout)
}

func hex(_ bytes: some Sequence<UInt8>) -> String {
    bytes.map { String(format: "%02x", $0) }.joined(separator: " ")
}

func describe(_ r: IOReturn) -> String {
    String(format: "0x%08X", UInt32(bitPattern: r))
}

final class Bridge: NSObject, IOBluetoothRFCOMMChannelDelegate {
    let config: Config
    let device: IOBluetoothDevice
    var listener: NWListener?
    var client: NWConnection?
    var channel: IOBluetoothRFCOMMChannel?
    var opening = false
    var attempt = 0
    var pending: [UInt8] = []  // octets TCP en attente de l'ouverture du canal

    init(config: Config) {
        guard let device = IOBluetoothDevice(addressString: config.address) else {
            fputs("adresse Bluetooth invalide : \(config.address)\n", stderr); exit(64)
        }
        self.config = config
        self.device = device
    }

    // MARK: TCP

    func start() throws {
        let params = NWParameters.tcp
        params.allowLocalEndpointReuse = true
        params.requiredLocalEndpoint = .hostPort(host: .init(config.host),
                                                 port: .init(rawValue: config.port)!)
        let listener = try NWListener(using: params)
        listener.stateUpdateHandler = { [config] state in
            switch state {
            case .ready: log("écoute sur \(config.host):\(config.port)")
            case .failed(let error): log("écoute impossible : \(error)"); exit(1)
            default: break
            }
        }
        listener.newConnectionHandler = { [weak self] connection in self?.accept(connection) }
        listener.start(queue: .main)
        self.listener = listener
        log("relais vers \(device.name ?? config.address) (\(config.address)), canal RFCOMM \(config.channel)")
    }

    func accept(_ connection: NWConnection) {
        if let previous = client {
            log("nouveau client : l'ancien est déconnecté")
            previous.cancel()
        }
        client = connection
        connection.stateUpdateHandler = { [weak self] state in
            switch state {
            case .ready: log("client connecté : \(connection.endpoint)")
            case .failed(let error): log("client en erreur : \(error)"); self?.drop(connection)
            default: break
            }
        }
        connection.start(queue: .main)
        receive(from: connection)
        ensureChannel()
    }

    func receive(from connection: NWConnection) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 4096) { [weak self] data, _, isComplete, error in
            guard let self, connection === self.client else { return }
            if let data, !data.isEmpty {
                if self.config.verbose { log("TCP → BT : \(hex(data))") }
                self.pending.append(contentsOf: data)
                self.flush()
            }
            if isComplete || error != nil {
                self.drop(connection)
            } else {
                self.receive(from: connection)
            }
        }
    }

    func drop(_ connection: NWConnection) {
        connection.cancel()
        if connection === client {
            client = nil
            pending.removeAll()
            log("client déconnecté")
        }
    }

    // MARK: Bluetooth

    func ensureChannel() {
        guard channel == nil, !opening else { return }
        opening = true
        attempt = 0
        tryOpen()
    }

    func tryOpen() {
        attempt += 1
        log("ouverture du canal \(config.channel) (essai \(attempt)/\(config.retries))…")
        var ch: IOBluetoothRFCOMMChannel? = nil
        let r = device.openRFCOMMChannelAsync(&ch, withChannelID: config.channel, delegate: self)
        if r != kIOReturnSuccess { openFailed(r) }
        // sinon : rfcommChannelOpenComplete sera appelé
    }

    func openFailed(_ r: IOReturn) {
        if attempt < config.retries {
            log("échec \(describe(r)), nouvel essai dans 1 s")
            DispatchQueue.main.asyncAfter(deadline: .now() + 1) { self.tryOpen() }
        } else {
            log("échec \(describe(r)) : abandon après \(attempt) essais (nouvel essai au prochain envoi)")
            opening = false
            if !pending.isEmpty {
                log("\(pending.count) octets en attente abandonnés")
                pending.removeAll()
            }
        }
    }

    func rfcommChannelOpenComplete(_ ch: IOBluetoothRFCOMMChannel!, status error: IOReturn) {
        guard error == kIOReturnSuccess, let ch else { openFailed(error); return }
        channel = ch
        opening = false
        log("canal \(config.channel) ouvert (MTU \(ch.getMTU()))")
        flush()
    }

    func flush() {
        guard !pending.isEmpty else { return }
        guard let ch = channel, ch.isOpen() else { ensureChannel(); return }
        let mtu = max(1, Int(ch.getMTU()))
        while !pending.isEmpty {
            var chunk = Array(pending.prefix(mtu))
            let r = ch.writeSync(&chunk, length: UInt16(chunk.count))
            if r != kIOReturnSuccess {
                log("écriture Bluetooth en échec \(describe(r)), \(pending.count) octets conservés")
                return
            }
            pending.removeFirst(chunk.count)
        }
    }

    func rfcommChannelData(_ ch: IOBluetoothRFCOMMChannel!, data: UnsafeMutableRawPointer!, length: Int) {
        let bytes = Data(bytes: data, count: length)
        if config.verbose { log("BT → TCP : \(hex(bytes))") }
        guard let client else {
            if config.verbose { log("(aucun client, \(length) octets ignorés)") }
            return
        }
        client.send(content: bytes, completion: .contentProcessed { error in
            if let error { log("envoi TCP en échec : \(error)") }
        })
    }

    func rfcommChannelClosed(_ ch: IOBluetoothRFCOMMChannel!) {
        guard ch === channel else { return }
        channel = nil
        log("canal \(config.channel) fermé (réouverture au prochain envoi)")
    }

    func shutdown() {
        log("arrêt")
        channel?.close()
        client?.cancel()
        listener?.cancel()
    }
}

let bridge = Bridge(config: Config.load())
do {
    try bridge.start()
} catch {
    fputs("démarrage impossible : \(error)\n", stderr); exit(1)
}

var signalSources: [DispatchSourceSignal] = []
for sig in [SIGINT, SIGTERM] {
    signal(sig, SIG_IGN)
    let source = DispatchSource.makeSignalSource(signal: sig, queue: .main)
    source.setEventHandler { bridge.shutdown(); exit(0) }
    source.resume()
    signalSources.append(source)
}

RunLoop.main.run()

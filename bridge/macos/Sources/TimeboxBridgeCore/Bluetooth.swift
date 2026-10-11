import Foundation
import IOBluetooth

// Le relais ne parle à IOBluetooth qu'à travers ces protocoles : les tests les remplacent par un
// faux appareil. Tous les rappels arrivent sur la file principale.

/// Canal RFCOMM ouvert (ou en cours d'ouverture).
@MainActor
public protocol BluetoothChannel: AnyObject {
    var mtu: Int { get }
    var isOpen: Bool { get }
    /// Écrit des octets (au plus `mtu`) ; renvoie un code `IOReturn` (0 = succès).
    func write(_ bytes: [UInt8]) -> Int32
    /// Ferme le canal sans rappel `channelClosed` (fermeture voulue par le relais).
    func close()
}

@MainActor
public protocol BluetoothChannelDelegate: AnyObject {
    func channelOpenComplete(_ channel: BluetoothChannel, status: Int32)
    func channelReceived(_ channel: BluetoothChannel, data: Data)
    /// Fermeture à l'initiative de l'appareil ou du système.
    func channelClosed(_ channel: BluetoothChannel)
}

@MainActor
public protocol BluetoothDevice: AnyObject {
    var name: String? { get }
    /// Lance l'ouverture asynchrone du canal ; le code renvoyé signale un échec immédiat (0 = ouverture
    /// en cours, fin signalée par `channelOpenComplete`).
    func openChannel(_ id: UInt8, delegate: BluetoothChannelDelegate) -> (BluetoothChannel, Int32)
}

// MARK: - IOBluetooth

/// Appareil réel, désigné par son adresse (`AA-BB-CC-DD-EE-FF`).
public final class IOBluetoothRFCOMMDevice: BluetoothDevice {
    let device: IOBluetoothDevice

    public init?(address: String) {
        guard let device = IOBluetoothDevice(addressString: address) else { return nil }
        self.device = device
    }

    public var name: String? { device.name }

    public func openChannel(_ id: UInt8, delegate: BluetoothChannelDelegate) -> (BluetoothChannel, Int32) {
        let adapter = IOBluetoothChannelAdapter(delegate: delegate)
        var ch: IOBluetoothRFCOMMChannel?
        let r = device.openRFCOMMChannelAsync(&ch, withChannelID: id, delegate: adapter)
        adapter.channel = ch
        if r == kIOReturnSuccess { adapter.retain() }
        return (adapter, r)
    }
}

/// Fait le lien entre le délégué IOBluetooth et `BluetoothChannelDelegate`. IOBluetooth ne retient
/// pas son délégué : l'adaptateur se retient lui-même tant que des rappels peuvent arriver.
final class IOBluetoothChannelAdapter: NSObject, BluetoothChannel, IOBluetoothRFCOMMChannelDelegate {
    private static var alive: Set<IOBluetoothChannelAdapter> = []

    weak var delegate: BluetoothChannelDelegate?
    var channel: IOBluetoothRFCOMMChannel?

    init(delegate: BluetoothChannelDelegate) {
        self.delegate = delegate
    }

    func retain() { Self.alive.insert(self) }
    private func release() { Self.alive.remove(self) }

    var mtu: Int { Int(channel?.getMTU() ?? 0) }
    var isOpen: Bool { channel?.isOpen() ?? false }

    func write(_ bytes: [UInt8]) -> Int32 {
        guard let channel else { return kIOReturnNotOpen }
        var chunk = bytes
        return channel.writeSync(&chunk, length: UInt16(chunk.count))
    }

    func close() {
        channel?.setDelegate(nil)
        channel?.close()
        release()
    }

    nonisolated func rfcommChannelOpenComplete(_ ch: IOBluetoothRFCOMMChannel!, status error: IOReturn) {
        MainActor.assumeIsolated {
            if let ch { channel = ch }
            if error != kIOReturnSuccess { release() }
            delegate?.channelOpenComplete(self, status: error)
        }
    }

    nonisolated func rfcommChannelData(_ ch: IOBluetoothRFCOMMChannel!, data: UnsafeMutableRawPointer!, length: Int) {
        let bytes = Data(bytes: data, count: length)
        MainActor.assumeIsolated { delegate?.channelReceived(self, data: bytes) }
    }

    nonisolated func rfcommChannelClosed(_ ch: IOBluetoothRFCOMMChannel!) {
        MainActor.assumeIsolated {
            release()
            delegate?.channelClosed(self)
        }
    }
}

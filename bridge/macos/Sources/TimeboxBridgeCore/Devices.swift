import IOBluetooth

/// Appareil Bluetooth appairé (pour choisir l'adresse de l'appareil Divoom).
public struct PairedDevice: Equatable, Sendable {
    public let address: String
    public let name: String
    public let isConnected: Bool

    public init(address: String, name: String, isConnected: Bool) {
        self.address = address
        self.name = name
        self.isConnected = isConnected
    }

    public var isDivoom: Bool { Self.isDivoom(name: name) }

    /// Repère les appareils Divoom à leur nom.
    public static func isDivoom(name: String) -> Bool {
        let lower = name.lowercased()
        return ["timebox", "divoom", "pixoo", "ditoo", "tivoo"].contains { lower.contains($0) }
    }

    /// Appareils appairés à ce Mac (Réglages système → Bluetooth).
    public static func paired() -> [PairedDevice] {
        (IOBluetoothDevice.pairedDevices() ?? []).compactMap { $0 as? IOBluetoothDevice }.map {
            PairedDevice(address: $0.addressString ?? "?", name: $0.name ?? "?", isConnected: $0.isConnected())
        }
    }
}

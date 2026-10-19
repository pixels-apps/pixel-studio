import IOBluetooth

/// Appareil Bluetooth appairé (pour choisir l'adresse de l'appareil Divoom).
public struct PairedDevice: Equatable, Sendable {
    public let address: String
    public let name: String
    public let isConnected: Bool
    /// Canal RFCOMM du port série, d'après les services relevés par macOS (`nil` si inconnu).
    public let serialChannel: UInt8?

    public init(address: String, name: String, isConnected: Bool, serialChannel: UInt8? = nil) {
        self.address = address
        self.name = name
        self.isConnected = isConnected
        self.serialChannel = serialChannel
    }

    public var isDivoom: Bool { Self.isDivoom(name: name) }

    /// Repère les appareils Divoom à leur nom.
    public static func isDivoom(name: String) -> Bool {
        let lower = name.lowercased()
        return ["timebox", "divoom", "pixoo", "ditoo", "tivoo"].contains { lower.contains($0) }
    }

    /// L'appareil de cette adresse est-il (encore) appairé à ce Mac ?
    public static func isPaired(address: String) -> Bool {
        IOBluetoothDevice(addressString: address)?.isPaired() ?? false
    }

    /// Canal RFCOMM du service « port série » (SPP, UUID 0x1101) de l'appareil, d'après les services
    /// que macOS a relevés à l'appairage ; `nil` si inconnu. Il varie selon le modèle : 1 pour le
    /// Timebox Evo, 2 pour le Pixoo.
    public static func serialChannel(address: String) -> UInt8? {
        IOBluetoothDevice(addressString: address).flatMap(serialChannel(of:))
    }

    static func serialChannel(of device: IOBluetoothDevice) -> UInt8? {
        guard let record = device.getServiceRecord(for: IOBluetoothSDPUUID(uuid16: 0x1101)) else { return nil }
        var channel: BluetoothRFCOMMChannelID = 0
        return record.getRFCOMMChannelID(&channel) == kIOReturnSuccess ? channel : nil
    }

    /// Appareils appairés à ce Mac (Réglages système → Bluetooth).
    public static func paired() -> [PairedDevice] {
        (IOBluetoothDevice.pairedDevices() ?? []).compactMap { $0 as? IOBluetoothDevice }.map {
            PairedDevice(address: $0.addressString ?? "?", name: $0.name ?? "?", isConnected: $0.isConnected(),
                         serialChannel: serialChannel(of: $0))
        }
    }
}

/// Contrôleur Bluetooth du Mac.
public enum BluetoothHost {
    /// Bluetooth activé (Réglages système → Bluetooth).
    public static var isPoweredOn: Bool {
        IOBluetoothHostController.default()?.powerState == kBluetoothHCIPowerStateON
    }
}

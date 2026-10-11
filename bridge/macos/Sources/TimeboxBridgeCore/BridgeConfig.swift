import Foundation

/// Réglages du relais. Les valeurs par défaut sont celles de la ligne de commande.
public struct BridgeConfig: Equatable, Sendable {
    public var address = ""
    public var channel: UInt8 = 1
    public var host = "127.0.0.1"
    public var port: UInt16 = 7777
    public var retries = 5
    public var verbose = false
    /// Délai maximal d'un essai d'ouverture : si le canal est déjà pris par un autre programme,
    /// IOBluetooth ne signale jamais la fin de l'ouverture.
    public var openTimeout: TimeInterval = 5
    /// Pause entre deux essais d'ouverture.
    public var retryDelay: TimeInterval = 1

    public init() {}

    /// Port saisi dans les réglages : entier de 1 à 65535 (espaces ignorés), sinon `nil`.
    public static func port(from text: String) -> UInt16? {
        guard let p = UInt16(text.trimmingCharacters(in: .whitespaces)), p > 0 else { return nil }
        return p
    }

    /// Hôte limité à cette machine : sinon, n'importe quel appareil du réseau peut piloter le Timebox.
    public static func isLoopback(host: String) -> Bool {
        let h = host.trimmingCharacters(in: .whitespaces).lowercased()
        return h == "localhost" || h == "::1" || h.hasPrefix("127.")
    }

    /// Ce que demande la ligne de commande.
    public enum Command: Equatable, Sendable {
        case run(BridgeConfig)
        case list
        case help
    }

    public struct ParseError: Error, Equatable, CustomStringConvertible {
        public let description: String
    }

    /// Analyse les arguments (sans le nom du programme) puis les variables d'environnement
    /// TIMEBOX_ADDRESS, TIMEBOX_CHANNEL, BRIDGE_HOST, BRIDGE_PORT, BRIDGE_RETRIES, BRIDGE_VERBOSE=1 ;
    /// les arguments l'emportent. Une valeur numérique invalide garde la valeur précédente.
    public static func parse(arguments: [String], environment: [String: String]) throws -> Command {
        var c = BridgeConfig()
        if let v = environment["TIMEBOX_ADDRESS"] { c.address = v }
        if let v = environment["TIMEBOX_CHANNEL"].flatMap(UInt8.init) { c.channel = v }
        if let v = environment["BRIDGE_HOST"] { c.host = v }
        if let v = environment["BRIDGE_PORT"].flatMap(UInt16.init) { c.port = v }
        if let v = environment["BRIDGE_RETRIES"].flatMap(Int.init) { c.retries = v }
        if environment["BRIDGE_VERBOSE"] == "1" { c.verbose = true }

        var args = arguments.makeIterator()
        while let arg = args.next() {
            switch arg {
            case "--address": c.address = args.next() ?? c.address
            case "--channel": c.channel = args.next().flatMap(UInt8.init) ?? c.channel
            case "--host": c.host = args.next() ?? c.host
            case "--port": c.port = args.next().flatMap(UInt16.init) ?? c.port
            case "--retries": c.retries = args.next().flatMap(Int.init) ?? c.retries
            case "-v", "--verbose": c.verbose = true
            case "--list": return .list
            case "-h", "--help": return .help
            default: throw ParseError(description: "argument inconnu : \(arg)")
            }
        }
        if c.address.isEmpty {
            throw ParseError(description:
                "adresse de l'appareil manquante : --address AA-BB-CC-DD-EE-FF (ou TIMEBOX_ADDRESS)\n"
                + "pour la trouver : timebox-bridge --list")
        }
        return .run(c)
    }
}

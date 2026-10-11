import Foundation
import os

/// Journal du relais : chaque message part vers le journal système (`os.Logger`) et vers les
/// destinations ajoutées (sortie standard pour la CLI, `LogBuffer` pour l'application).
public final class Log: @unchecked Sendable {
    public static let shared = Log()

    public struct Entry: Equatable, Sendable {
        public let date: Date
        public let message: String
    }

    private let lock = NSLock()
    private var sinks: [@Sendable (Entry) -> Void] = []
    private var _verbose = false
    private let logger: Logger?

    /// `systemLog` : écrire aussi dans le journal système (désactivé dans les tests).
    init(systemLog: Bool = true) {
        logger = systemLog
            ? Logger(subsystem: Bundle.main.bundleIdentifier ?? "calm.show.timebox-bridge", category: "bridge")
            : nil
    }

    /// Journal verbeux : chaque octet échangé est journalisé. Modifiable à chaud.
    public var verbose: Bool {
        get { lock.withLock { _verbose } }
        set { lock.withLock { _verbose = newValue } }
    }

    public func addSink(_ sink: @escaping @Sendable (Entry) -> Void) {
        lock.withLock { sinks.append(sink) }
    }

    public func info(_ message: String) {
        logger?.notice("\(message, privacy: .public)")
        let entry = Entry(date: Date(), message: message)
        for sink in lock.withLock({ sinks }) { sink(entry) }
    }

    /// Message journalisé seulement en mode verbeux (le texte n'est construit que dans ce cas).
    public func debug(_ message: @autoclosure () -> String) {
        if verbose { info(message()) }
    }

    /// Destination « sortie standard », au format historique de la CLI : `HH:mm:ss.SSS message`.
    public static let standardOutput: @Sendable (Entry) -> Void = { entry in
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss.SSS"
        print("\(f.string(from: entry.date)) \(entry.message)")
        fflush(stdout)
    }
}

/// Tampon circulaire des derniers messages (fenêtre « Journal » de l'application).
public final class LogBuffer: @unchecked Sendable {
    public let capacity: Int
    private let lock = NSLock()
    private var entries: [Log.Entry] = []

    public init(capacity: Int = 1000) {
        self.capacity = capacity
    }

    public func append(_ entry: Log.Entry) {
        lock.withLock {
            entries.append(entry)
            if entries.count > capacity { entries.removeFirst(entries.count - capacity) }
        }
    }

    public var all: [Log.Entry] { lock.withLock { entries } }

    public func clear() { lock.withLock { entries.removeAll() } }
}

func hex(_ bytes: some Sequence<UInt8>) -> String {
    bytes.map { String(format: "%02x", $0) }.joined(separator: " ")
}

func describe(_ r: Int32) -> String {
    String(format: "0x%08X", UInt32(bitPattern: r))
}

func seconds(_ t: TimeInterval) -> String {
    t == t.rounded() ? "\(Int(t)) s" : "\(t) s"
}

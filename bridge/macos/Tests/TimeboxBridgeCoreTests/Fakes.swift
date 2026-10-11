import Foundation
@testable import TimeboxBridgeCore

/// Faux canal : note les écritures, renvoie le code choisi.
@MainActor
final class FakeChannel: BluetoothChannel {
    var mtu: Int
    var isOpen = false
    var writeResult: Int32 = 0
    var writes: [[UInt8]] = []
    var closed = false

    init(mtu: Int) { self.mtu = mtu }

    func write(_ bytes: [UInt8]) -> Int32 {
        if writeResult == 0 { writes.append(bytes) }
        return writeResult
    }

    func close() {
        closed = true
        isOpen = false
    }
}

/// Faux appareil : chaque ouverture crée un `FakeChannel` ; le test décide de l'issue.
@MainActor
final class FakeDevice: BluetoothDevice {
    let name: String? = "Faux-Timebox"
    var mtu = 666
    /// Codes renvoyés immédiatement par les ouvertures successives (0 par défaut).
    var immediateResults: [Int32] = []
    private(set) var attempts: [FakeChannel] = []
    private weak var delegate: BluetoothChannelDelegate?

    func openChannel(_ id: UInt8, delegate: BluetoothChannelDelegate) -> (BluetoothChannel, Int32) {
        self.delegate = delegate
        let ch = FakeChannel(mtu: mtu)
        attempts.append(ch)
        let r = immediateResults.isEmpty ? 0 : immediateResults.removeFirst()
        return (ch, r)
    }

    var last: FakeChannel { attempts.last! }

    /// Termine l'ouverture du dernier essai (ou de `channel`).
    func complete(_ status: Int32 = 0, channel: FakeChannel? = nil) {
        let ch = channel ?? last
        if status == 0 { ch.isOpen = true }
        delegate?.channelOpenComplete(ch, status: status)
    }

    func receive(_ bytes: [UInt8]) {
        delegate?.channelReceived(last, data: Data(bytes))
    }

    func closeRemotely() {
        last.isOpen = false
        delegate?.channelClosed(last)
    }
}

/// Horloge manuelle : `advance` exécute les tâches arrivées à échéance.
@MainActor
final class ManualScheduler: Scheduler {
    final class Task: ScheduledWork {
        let due: TimeInterval
        let work: @MainActor () -> Void
        var cancelled = false
        init(due: TimeInterval, work: @escaping @MainActor () -> Void) { self.due = due; self.work = work }
        func cancel() { cancelled = true }
    }

    private(set) var now: TimeInterval = 0
    private var tasks: [Task] = []

    func schedule(after delay: TimeInterval, _ work: @escaping @MainActor () -> Void) -> ScheduledWork {
        let t = Task(due: now + delay, work: work)
        tasks.append(t)
        return t
    }

    func advance(by delta: TimeInterval) {
        let end = now + delta
        while let next = tasks.filter({ !$0.cancelled && $0.due <= end }).min(by: { $0.due < $1.due }) {
            tasks.removeAll { $0 === next }
            now = next.due
            next.work()
        }
        now = end
        tasks.removeAll { $0.cancelled }
    }
}

/// Journal de test : messages en mémoire, sans sortie standard.
func testLog() -> (Log, LogBuffer) {
    let log = Log()
    let buffer = LogBuffer()
    log.addSink { buffer.append($0) }
    return (log, buffer)
}

extension LogBuffer {
    var messages: [String] { all.map(\.message) }
}

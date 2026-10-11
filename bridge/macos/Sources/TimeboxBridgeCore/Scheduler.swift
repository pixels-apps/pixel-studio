import Foundation

/// Planification des nouveaux essais et des délais maximaux (remplacée par une horloge manuelle
/// dans les tests).
@MainActor
public protocol Scheduler {
    func schedule(after delay: TimeInterval, _ work: @escaping @MainActor () -> Void) -> ScheduledWork
}

@MainActor
public protocol ScheduledWork {
    func cancel()
}

/// Planification sur la file principale.
public struct MainQueueScheduler: Scheduler {
    nonisolated public init() {}

    public func schedule(after delay: TimeInterval, _ work: @escaping @MainActor () -> Void) -> ScheduledWork {
        let item = DispatchWorkItem { MainActor.assumeIsolated { work() } }
        DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: item)
        return Item(item: item)
    }

    struct Item: ScheduledWork {
        let item: DispatchWorkItem
        func cancel() { item.cancel() }
    }
}

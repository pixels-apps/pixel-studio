import AppKit
import SwiftUI
import TimeboxBridgeCore

/// Fenêtre « Journal » : derniers messages du relais, défilement automatique, Copier / Effacer.
struct LogWindow: View {
    static let id = "journal"

    let model: BridgeModel

    private static let time: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss.SSS"
        return f
    }()

    private var lines: [String] {
        _ = model.logRevision  // relit le tampon à chaque nouveau message
        return model.logBuffer.all.map { "\(Self.time.string(from: $0.date)) \($0.message)" }
    }

    var body: some View {
        let lines = lines
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 2) {
                        ForEach(Array(lines.enumerated()), id: \.offset) { index, line in
                            Text(line).id(index)
                        }
                    }
                    .font(.system(.callout, design: .monospaced))
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(10)
                }
                .onChange(of: lines.count, initial: true) {
                    if let last = lines.indices.last { proxy.scrollTo(last, anchor: .bottom) }
                }
            }
            Divider()
            HStack {
                Text("\(lines.count) messages")
                    .foregroundStyle(.secondary)
                Spacer()
                Button("Effacer") { model.clearLog() }
                Button("Copier") {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(lines.joined(separator: "\n"), forType: .string)
                }
                .keyboardShortcut("c", modifiers: [.command, .shift])
            }
            .padding(10)
        }
        .frame(minWidth: 480, minHeight: 240)
    }
}

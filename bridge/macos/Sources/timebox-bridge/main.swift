import Foundation
import TimeboxBridgeCore

// timebox-bridge : relais transparent TCP <-> RFCOMM pour le Divoom Timebox Evo (macOS).
// Le relais lui-même est dans TimeboxBridgeCore (partagé avec l'application de barre de menu).
//
// Usage : timebox-bridge --address AA-BB-CC-DD-EE-FF [--channel N] [--host 127.0.0.1]
//                        [--port 7777] [--retries 5] [--verbose]
//         timebox-bridge --list      (appareils appairés, pour trouver l'adresse)
// Équivalents en variables d'environnement : TIMEBOX_ADDRESS, TIMEBOX_CHANNEL, BRIDGE_HOST,
// BRIDGE_PORT, BRIDGE_RETRIES, BRIDGE_VERBOSE=1.

let command: BridgeConfig.Command
do {
    command = try BridgeConfig.parse(arguments: Array(CommandLine.arguments.dropFirst()),
                                     environment: ProcessInfo.processInfo.environment)
} catch {
    fputs("\(error)\n", stderr)
    exit(64)
}

let config: BridgeConfig
switch command {
case .help:
    print("usage: timebox-bridge --address AA-BB-CC-DD-EE-FF [--channel N] "
        + "[--host 127.0.0.1] [--port 7777] [--retries 5] [--verbose]")
    print("       timebox-bridge --list    (appareils Bluetooth appairés)")
    print("--channel : canal RFCOMM ; par défaut, celui du port série de l'appareil (sinon 1)")
    exit(0)
case .list:
    let devices = PairedDevice.paired()
    if devices.isEmpty { print("aucun appareil appairé (Réglages système → Bluetooth)") }
    for d in devices {
        let channel = d.serialChannel.map { "  [port série : canal \($0)]" } ?? ""
        print("\(d.isDivoom ? "→" : " ") \(d.address)  \(d.name)\(d.isConnected ? "  (connecté)" : "")\(channel)")
    }
    exit(0)
case .run(var c):
    if !c.channelIsExplicit {
        c.channel = PairedDevice.serialChannel(address: c.address) ?? 1
    }
    config = c
}

Log.shared.verbose = config.verbose
Log.shared.addSink(Log.standardOutput)
if !config.channelIsExplicit {
    Log.shared.info("canal RFCOMM \(config.channel) (port série de l'appareil, sinon 1 ; --channel pour l'imposer)")
}

// Le code de premier niveau tourne sur le fil principal, comme tout le relais.
let bridge: Bridge = MainActor.assumeIsolated {
    do {
        let bridge = try Bridge(config: config)
        bridge.onStateChange = { state in
            switch state.listener {
            case .failed, .portInUse: exit(1)
            default: break
            }
        }
        try bridge.start()
        return bridge
    } catch let error as BridgeError {
        fputs("\(error)\n", stderr); exit(64)
    } catch {
        fputs("démarrage impossible : \(error)\n", stderr); exit(1)
    }
}

var signalSources: [DispatchSourceSignal] = []
for sig in [SIGINT, SIGTERM] {
    signal(sig, SIG_IGN)
    let source = DispatchSource.makeSignalSource(signal: sig, queue: .main)
    source.setEventHandler {
        MainActor.assumeIsolated { bridge.stop() }
        exit(0)
    }
    source.resume()
    signalSources.append(source)
}

RunLoop.main.run()

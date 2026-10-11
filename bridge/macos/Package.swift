// swift-tools-version:6.0
import PackageDescription

// Relais TCP ↔ RFCOMM pour le Divoom Timebox Evo.
// TimeboxBridgeCore est partagé par la ligne de commande (ci-dessous) et l'application de barre de
// menu (App/, projet XcodeGen). Compilation de la CLI : ./build.sh ; tests : ./test.sh.
let package = Package(
    name: "TimeboxBridge",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "TimeboxBridgeCore", targets: ["TimeboxBridgeCore"]),
        .executable(name: "timebox-bridge", targets: ["timebox-bridge"]),
    ],
    targets: [
        .target(name: "TimeboxBridgeCore"),
        .executableTarget(
            name: "timebox-bridge",
            dependencies: ["TimeboxBridgeCore"],
            exclude: ["Info.plist"],
            // Info.plist intégré au binaire : macOS tue un outil qui utilise le Bluetooth sans
            // déclaration d'usage.
            linkerSettings: [.unsafeFlags([
                "-Xlinker", "-sectcreate", "-Xlinker", "__TEXT", "-Xlinker", "__info_plist",
                "-Xlinker", Context.packageDirectory + "/Sources/timebox-bridge/Info.plist",
            ])]
        ),
        .testTarget(name: "TimeboxBridgeCoreTests", dependencies: ["TimeboxBridgeCore"]),
    ],
    swiftLanguageModes: [.v5]
)

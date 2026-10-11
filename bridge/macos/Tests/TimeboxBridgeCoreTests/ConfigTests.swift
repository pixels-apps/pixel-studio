import Testing
@testable import TimeboxBridgeCore

struct ConfigTests {
    func run(_ args: [String], _ env: [String: String] = [:]) throws -> BridgeConfig {
        guard case .run(let c) = try BridgeConfig.parse(arguments: args, environment: env) else {
            Issue.record("commande inattendue")
            return BridgeConfig()
        }
        return c
    }

    @Test func valeursParDefaut() throws {
        let c = try run(["--address", "AA-BB-CC-DD-EE-FF"])
        #expect(c.address == "AA-BB-CC-DD-EE-FF")
        #expect(c.channel == 1 && c.host == "127.0.0.1" && c.port == 7777 && c.retries == 5 && !c.verbose)
    }

    @Test func toutesLesOptions() throws {
        let c = try run(["--address", "A", "--channel", "2", "--host", "0.0.0.0", "--port", "8000",
                         "--retries", "9", "-v"])
        #expect(c.channel == 2 && c.host == "0.0.0.0" && c.port == 8000 && c.retries == 9 && c.verbose)
    }

    @Test func variablesDEnvironnement() throws {
        let env = ["TIMEBOX_ADDRESS": "E", "TIMEBOX_CHANNEL": "3", "BRIDGE_HOST": "::1",
                   "BRIDGE_PORT": "7000", "BRIDGE_RETRIES": "2", "BRIDGE_VERBOSE": "1"]
        let c = try run([], env)
        #expect(c.address == "E" && c.channel == 3 && c.host == "::1" && c.port == 7000 && c.retries == 2 && c.verbose)
    }

    @Test func lesArgumentsLEmportent() throws {
        let c = try run(["--port", "7100", "--address", "A"], ["BRIDGE_PORT": "7000", "TIMEBOX_ADDRESS": "E"])
        #expect(c.port == 7100 && c.address == "A")
    }

    @Test func valeurNumeriqueInvalideIgnoree() throws {
        let c = try run(["--address", "A", "--port", "99999", "--channel", "x"])
        #expect(c.port == 7777 && c.channel == 1)
    }

    @Test func adresseManquante() {
        #expect(throws: BridgeConfig.ParseError.self) { try run([]) }
    }

    @Test func argumentInconnu() {
        #expect(throws: BridgeConfig.ParseError(description: "argument inconnu : --bof")) {
            try run(["--address", "A", "--bof"])
        }
    }

    @Test func listeEtAideSansAdresse() throws {
        #expect(try BridgeConfig.parse(arguments: ["--list"], environment: [:]) == .list)
        #expect(try BridgeConfig.parse(arguments: ["-h"], environment: [:]) == .help)
        #expect(try BridgeConfig.parse(arguments: ["--list", "--bof"], environment: [:]) == .list)
    }
}

struct DeviceAndLogTests {
    @Test(arguments: ["TimeBox-Evo-audio", "TimeBox-Evo-light", "Pixoo-64", "Ditoo-Pro", "DIVOOM x"])
    func appareilsDivoom(name: String) {
        #expect(PairedDevice.isDivoom(name: name))
    }

    @Test(arguments: ["AirPods Pro", "MX MCHNCL M", "Xbox Wireless Controller"])
    func autresAppareils(name: String) {
        #expect(!PairedDevice.isDivoom(name: name))
    }

    @Test func tamponCirculaire() {
        let buffer = LogBuffer(capacity: 3)
        let log = Log(systemLog: false)
        log.addSink { buffer.append($0) }
        for i in 1...5 { log.info("m\(i)") }
        #expect(buffer.messages == ["m3", "m4", "m5"])
        buffer.clear()
        #expect(buffer.all.isEmpty)
    }
}

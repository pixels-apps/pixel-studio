import Foundation
import Testing
@testable import TimeboxBridgeCore

@MainActor
struct RelayTests {
    let device = FakeDevice()
    let clock = ManualScheduler()
    let log: Log
    let messages: LogBuffer
    let relay: Relay

    init() {
        (log, messages) = testLog()
        var config = BridgeConfig()
        config.address = "11-22-33-44-55-66"
        config.retries = 3
        relay = Relay(config: config, device: device, scheduler: clock, log: log)
    }

    /// Relais avec un client connecté et un canal ouvert.
    func connected(mtu: Int = 666) -> Relay {
        device.mtu = mtu
        relay.clientConnected(1, description: "client")
        device.complete()
        return relay
    }

    @Test func ouvertureALaConnexionDuClient() {
        relay.clientConnected(1, description: "127.0.0.1:5000")
        #expect(device.attempts.count == 1)
        #expect(relay.channelState == .opening(attempt: 1, of: 3))
        device.complete()
        #expect(relay.channelState == .open(mtu: 666))
        #expect(messages.messages.contains("canal 1 ouvert (MTU 666)"))
    }

    @Test func premierEssaiEnEchecPuisSucces() {
        relay.clientConnected(1, description: "client")
        relay.received(Data([0x01, 0x02]), from: 1)
        device.complete(-536_870_212)  // 0xE00002BC, échec typique du 1er essai
        #expect(relay.channelState == .opening(attempt: 1, of: 3))
        #expect(messages.messages.last == "échec 0xE00002BC, nouvel essai dans 1 s")

        clock.advance(by: 1)
        #expect(device.attempts.count == 2)
        device.complete()
        #expect(relay.channelState == .open(mtu: 666))
        #expect(device.last.writes == [[0x01, 0x02]])  // octets en attente envoyés à l'ouverture
        #expect(relay.bytesToDevice == 2)
    }

    @Test func echecImmediatCompteCommeUnEssai() {
        device.immediateResults = [-1]
        relay.clientConnected(1, description: "client")
        #expect(relay.channelState == .opening(attempt: 1, of: 3))
        clock.advance(by: 1)
        #expect(device.attempts.count == 2)
    }

    @Test func abandonApresLeDernierEssai() {
        relay.clientConnected(1, description: "client")
        relay.received(Data([0xaa, 0xbb, 0xcc]), from: 1)
        for _ in 1...3 {
            device.complete(-1)
            clock.advance(by: 1)
        }
        #expect(device.attempts.count == 3)
        #expect(relay.channelState == .gaveUp(reason: "0xFFFFFFFF"))
        #expect(relay.pendingCount == 0)
        #expect(messages.messages.contains("3 octets en attente abandonnés"))

        // nouvel essai au prochain envoi
        relay.received(Data([0x01]), from: 1)
        #expect(device.attempts.count == 4)
        #expect(relay.channelState == .opening(attempt: 1, of: 3))
    }

    @Test func delaiMaximalParEssai() {
        relay.clientConnected(1, description: "client")
        let stale = device.last
        clock.advance(by: 4.9)
        #expect(device.attempts.count == 1)
        clock.advance(by: 0.1)  // 5 s sans réponse : essai abandonné
        #expect(stale.closed)
        #expect(messages.messages.contains("échec délai dépassé, nouvel essai dans 1 s"))
        clock.advance(by: 1)
        #expect(device.attempts.count == 2)

        // réponse tardive de l'essai abandonné : ignorée, canal refermé
        stale.closed = false
        device.complete(0, channel: stale)
        #expect(stale.closed)
        #expect(relay.channelState == .opening(attempt: 2, of: 3))

        device.complete()
        #expect(relay.channelState == .open(mtu: 666))
        clock.advance(by: 10)  // le délai de l'essai réussi est annulé
        #expect(relay.channelState == .open(mtu: 666))
    }

    @Test func decoupageSelonLeMTU() {
        let relay = connected(mtu: 4)
        relay.received(Data(0..<10), from: 1)
        #expect(device.last.writes == [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9]])
        #expect(relay.bytesToDevice == 10)
    }

    @Test func ecritureEnEchecConserveLesOctets() {
        let relay = connected()
        device.last.writeResult = -1
        relay.received(Data([1, 2, 3]), from: 1)
        #expect(relay.pendingCount == 3)
        device.last.writeResult = 0
        relay.received(Data([4]), from: 1)
        #expect(device.last.writes == [[1, 2, 3, 4]])
    }

    @Test func nouveauClientRemplaceLAncien() {
        var disconnected: [Relay.ClientID] = []
        relay.disconnectClient = { disconnected.append($0) }
        let relay = connected()
        relay.clientConnected(2, description: "nouveau")
        #expect(disconnected == [1])
        #expect(relay.client == 2)
        relay.received(Data([9]), from: 1)  // octets de l'ancien client ignorés
        #expect(device.last.writes.isEmpty)
        relay.clientDisconnected(1)  // déconnexion tardive de l'ancien : sans effet
        #expect(relay.client == 2)
    }

    @Test func octetsDeLAppareilVersLeClient() {
        var sent: [(Relay.ClientID, Data)] = []
        relay.sendToClient = { sent.append(($0, $1)) }
        let relay = connected()
        device.receive([0x04, 0x46, 0x55])
        #expect(sent.count == 1)
        #expect(sent.first?.0 == 1 && sent.first?.1 == Data([0x04, 0x46, 0x55]))
        #expect(relay.bytesFromDevice == 3)

        relay.clientDisconnected(1)
        device.receive([0x01])
        #expect(sent.count == 1)  // aucun client : octets ignorés
    }

    @Test func fermetureParLAppareilPuisReouverture() {
        let relay = connected()
        device.closeRemotely()
        #expect(relay.channelState == .closed)
        #expect(messages.messages.last == "canal 1 fermé (réouverture au prochain envoi)")
        relay.received(Data([0x01]), from: 1)
        #expect(device.attempts.count == 2)
        device.complete()
        #expect(device.last.writes == [[0x01]])
    }

    @Test func reconnecter() {
        let relay = connected()
        let first = device.last
        relay.reconnect()
        #expect(first.closed)
        #expect(device.attempts.count == 2)
        #expect(relay.channelState == .opening(attempt: 1, of: 3))
    }

    @Test func reconnecterPendantUneOuverture() {
        relay.clientConnected(1, description: "client")
        device.complete(-1)  // nouvel essai prévu dans 1 s
        relay.reconnect()
        #expect(device.attempts.count == 2)
        clock.advance(by: 1)  // l'ancien nouvel essai est annulé
        #expect(device.attempts.count == 2)
        clock.advance(by: 5)  // délai du nouvel essai (t = 5 s), puis essai suivant (t = 6 s)
        #expect(device.attempts.count == 3)
        #expect(relay.channelState == .opening(attempt: 2, of: 3))
    }

    @Test func arret() {
        var disconnected: [Relay.ClientID] = []
        relay.disconnectClient = { disconnected.append($0) }
        let relay = connected()
        relay.stop()
        #expect(device.last.closed)
        #expect(disconnected == [1])
        #expect(relay.client == nil)
        #expect(relay.channelState == .closed)
    }

    @Test func journalVerbeux() {
        let relay = connected()
        relay.received(Data([0xab]), from: 1)
        #expect(!messages.messages.contains("TCP → BT : ab"))
        log.verbose = true
        relay.received(Data([0xcd]), from: 1)
        #expect(messages.messages.contains("TCP → BT : cd"))
    }
}

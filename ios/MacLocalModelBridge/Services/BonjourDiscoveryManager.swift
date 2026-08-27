//
//  BonjourDiscoveryManager.swift
//  MacLocalModelBridge
//

import Foundation
import Network
import Combine

public struct DiscoveredBridge: Identifiable, Hashable {
    public let id: String
    public let name: String
    public let host: String
    public let port: Int
    public let txtRecord: [String: String]

    public var urlString: String {
        return "http://\(host):\(port)"
    }
}

public class BonjourDiscoveryManager: ObservableObject {
    @Published public var discoveredBridges: [DiscoveredBridge] = []
    @Published public var isBrowsing: Bool = false
    @Published public var lastDiscoveryStatus: String = "Idle"

    private var browsers: [NWBrowser] = []
    private var resolvers: [NWConnection] = []
    private let queue = DispatchQueue(label: "com.macmodelbridge.bonjour", qos: .utility)
    private let resolutionQueue = DispatchQueue(label: "com.macmodelbridge.bonjour.resolve", qos: .utility)
    private var resultsMap: [String: DiscoveredBridge] = [:]
    private var browseGeneration = 0

    private let scanTimeoutSeconds: TimeInterval = 12

    public init() {}

    public func startBrowsing() {
        guard !isBrowsing else { return }

        browseGeneration += 1
        let generation = browseGeneration

        let serviceTypes = ["_local-ai-gateway._tcp", "_local-ai-bridge._tcp"]
        let parameters = NWParameters()
        parameters.includePeerToPeer = true

        resultsMap.removeAll()
        browsers.removeAll()
        isBrowsing = true
        lastDiscoveryStatus = "Scanning local Wi-Fi for Mac AI Gateway & Bridge..."

        for serviceType in serviceTypes {
            let descriptor = NWBrowser.Descriptor.bonjour(type: serviceType, domain: "local.")
            let browser = NWBrowser(for: descriptor, using: parameters)

            browser.stateUpdateHandler = { [weak self] state in
                DispatchQueue.main.async {
                    guard let self = self else { return }
                    switch state {
                    case .ready:
                        if self.lastDiscoveryStatus == "Idle" || self.lastDiscoveryStatus.hasPrefix("Scanning") {
                            self.lastDiscoveryStatus = "Scanning local Wi-Fi for Mac AI Gateway..."
                        }
                    case .failed(let error):
                        if self.discoveredBridges.isEmpty {
                            self.lastDiscoveryStatus = "Discovery blocked. Grant Local Network permission for this app in iOS Settings to find your Mac."
                        } else {
                            self.lastDiscoveryStatus = "Discovery warning: \(error.localizedDescription)"
                        }
                    case .cancelled:
                        break
                    default:
                        break
                    }
                }
            }

            browser.browseResultsChangedHandler = { [weak self] results, _ in
                guard let self = self else { return }
                var newBridges: [String: DiscoveredBridge] = [:]

                for result in results {
                    switch result.endpoint {
                    case .service(let name, _, _, _):
                        var txtDict: [String: String] = [:]
                        if case .bonjour(let txtRecord) = result.metadata {
                            txtDict = txtRecord.dictionary
                        }

                        // The gateway advertises the same service under two types
                        // (_local-ai-bridge and _local-ai-gateway), so dedupe by name.
                        let uniqueId = name

                        // Fast path: gateway publishes its IP/port in the TXT record.
                        var resolvedHost = self.sanitizeHost(txtDict["ip"] ?? "")
                        if resolvedHost.isEmpty {
                            if let regex = try? NSRegularExpression(pattern: "\\(([0-9.]+)\\)"),
                               let match = regex.firstMatch(in: name, range: NSRange(name.startIndex..., in: name)),
                               let range = Range(match.range(at: 1), in: name) {
                                resolvedHost = self.sanitizeHost(String(name[range]))
                            }
                        }

                        let isLoopback = resolvedHost == "127.0.0.1"
                            || resolvedHost == "0.0.0.0"
                            || resolvedHost == "localhost"
                        if isLoopback { continue }

                        if !resolvedHost.isEmpty {
                            let bridge = DiscoveredBridge(
                                id: uniqueId,
                                name: name,
                                host: resolvedHost,
                                port: Int(txtDict["port"] ?? "") ?? 8080,
                                txtRecord: txtDict
                            )
                            newBridges[uniqueId] = bridge
                        } else {
                            // Slow path: TXT record has no IP, so resolve the mDNS
                            // service to a real address via a short-lived connection.
                            self.resolveServiceHost(
                                endpoint: result.endpoint,
                                name: name,
                                txtDict: txtDict
                            )
                        }
                    default:
                        break
                    }
                }

                DispatchQueue.main.async {
                    for (key, value) in newBridges {
                        self.resultsMap[key] = value
                    }
                    let list = Array(self.resultsMap.values).sorted(by: { $0.name < $1.name })
                    self.discoveredBridges = list
                    if !list.isEmpty {
                        self.lastDiscoveryStatus = "Found \(list.count) Mac Gateway/Bridge on Wi-Fi"
                    }
                }
            }

            browser.start(queue: queue)
            browsers.append(browser)
        }

        // Auto-stop guard: if nothing was found within the timeout, pause the
        // scan so the app doesn't search the Wi-Fi network forever.
        DispatchQueue.main.asyncAfter(deadline: .now() + scanTimeoutSeconds) { [weak self] in
            guard let self = self, self.browseGeneration == generation else { return }
            if self.isBrowsing && self.discoveredBridges.isEmpty {
                self.stopBrowsing()
                self.lastDiscoveryStatus = "No Mac AI Gateway found on Wi-Fi. Start the gateway on your Mac, then tap RESCAN, or enter the Mac's LAN IP below."
            }
        }
    }

    public func restartBrowsing() {
        stopBrowsing()
        DispatchQueue.main.async { [weak self] in
            self?.startBrowsing()
        }
    }

    private func sanitizeHost(_ raw: String) -> String {
        var cleaned = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        // Strip Network.framework interface scope suffixes like "%en0" (or "%ifname")
        // that are appended to host descriptions and are invalid inside a URL host.
        if let scopeIndex = cleaned.firstIndex(of: "%") {
            cleaned = String(cleaned[..<scopeIndex])
        }
        return cleaned
    }

    public func stopBrowsing() {
        for browser in browsers {
            browser.cancel()
        }
        browsers.removeAll()
        resolutionQueue.async { [weak self] in
            guard let self = self else { return }
            for resolver in self.resolvers {
                resolver.cancel()
            }
            self.resolvers.removeAll()
        }
        DispatchQueue.main.async {
            self.isBrowsing = false
            if self.discoveredBridges.isEmpty {
                self.lastDiscoveryStatus = "Scanning paused."
            }
        }
    }

    private func resolveServiceHost(endpoint: NWEndpoint, name: String, txtDict: [String: String]) {
        let port = Int(txtDict["port"] ?? "") ?? 8080
        let uniqueId = name

        let connection = NWConnection(to: endpoint, using: .tcp)
        // Avoid a retain cycle: the connection's state handler must not strongly
        // reference the connection itself.
        weak var weakConnection = connection

        connection.stateUpdateHandler = { [weak self] state in
            guard let self = self else { return }
            guard let connection = weakConnection else { return }
            switch state {
            case .ready:
                var resolvedHost: String? = nil
                if let remote = connection.currentPath?.remoteEndpoint {
                    switch remote {
                    case .hostPort(let host, _):
                        switch host {
                        case .ipv4(let addr):
                            resolvedHost = self.sanitizeHost("\(addr)")
                        case .ipv6:
                            resolvedHost = nil
                        case .name(let hostname, _):
                            resolvedHost = self.sanitizeHost(hostname)
                        @unknown default:
                            resolvedHost = self.sanitizeHost(host.debugDescription)
                        }
                    default:
                        resolvedHost = nil
                    }
                }

                if let host = resolvedHost, !host.isEmpty {
                    let bridge = DiscoveredBridge(
                        id: uniqueId,
                        name: name,
                        host: host,
                        port: port,
                        txtRecord: txtDict
                    )
                    DispatchQueue.main.async {
                        self.resultsMap[uniqueId] = bridge
                        let list = Array(self.resultsMap.values).sorted(by: { $0.name < $1.name })
                        self.discoveredBridges = list
                        if !list.isEmpty {
                            self.lastDiscoveryStatus = "Found \(list.count) Mac Gateway/Bridge on Wi-Fi"
                        }
                    }
                }
                connection.cancel()
            case .failed, .cancelled:
                connection.cancel()
            default:
                break
            }
        }

        // Track the resolver on its own serial queue to avoid data races with the
        // browser and the timeout below.
        resolutionQueue.async { [weak self] in
            self?.resolvers.append(connection)
        }
        connection.start(queue: resolutionQueue)

        resolutionQueue.asyncAfter(deadline: .now() + 6) { [weak self] in
            guard let self = self else { return }
            if let idx = self.resolvers.firstIndex(where: { $0 === connection }) {
                connection.cancel()
                self.resolvers.remove(at: idx)
            }
        }
    }
}

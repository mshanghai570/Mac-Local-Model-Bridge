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
    private let queue = DispatchQueue(label: "com.macmodelbridge.bonjour", qos: .utility)
    private var resultsMap: [String: DiscoveredBridge] = [:]

    public init() {}

    public func startBrowsing() {
        guard !isBrowsing else { return }

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
                    switch state {
                    case .ready:
                        self?.lastDiscoveryStatus = "Scanning local Wi-Fi for Mac AI Gateway..."
                    case .failed(let error):
                        self?.lastDiscoveryStatus = "Discovery warning: \(error.localizedDescription)"
                    case .cancelled:
                        break
                    default:
                        break
                    }
                }
            }

            browser.browseResultsChangedHandler = { [weak self] results, changes in
                guard let self = self else { return }
                
                for result in results {
                    switch result.endpoint {
                    case .service(let name, let type, let domain, _):
                        var txtDict: [String: String] = [:]
                        if case .bonjour(let txtRecord) = result.metadata {
                            txtDict = txtRecord.dictionary
                        }

                        // Extract IP/port from TXT record if provided by gateway, or fallback
                        var resolvedHost = txtDict["ip"] ?? ""
                        if resolvedHost.isEmpty {
                            if let regex = try? NSRegularExpression(pattern: "\\(([0-9.]+)\\)"),
                               let match = regex.firstMatch(in: name, range: NSRange(name.startIndex..., in: name)),
                               let range = Range(match.range(at: 1), in: name) {
                                resolvedHost = String(name[range])
                            } else {
                                resolvedHost = "\(name.components(separatedBy: " ").first ?? "localhost").local"
                            }
                        }

                        let resolvedPort = Int(txtDict["port"] ?? "") ?? 8080
                        let uniqueId = "\(name).\(type).\(domain)"
                        let bridge = DiscoveredBridge(
                            id: uniqueId,
                            name: name,
                            host: resolvedHost,
                            port: resolvedPort,
                            txtRecord: txtDict
                        )
                        self.resultsMap[uniqueId] = bridge
                    default:
                        break
                    }
                }

                DispatchQueue.main.async {
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
    }

    public func stopBrowsing() {
        for browser in browsers {
            browser.cancel()
        }
        browsers.removeAll()
        DispatchQueue.main.async {
            self.isBrowsing = false
            self.lastDiscoveryStatus = "Scanning paused."
        }
    }
}

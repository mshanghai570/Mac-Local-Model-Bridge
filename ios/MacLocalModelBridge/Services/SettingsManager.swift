//
//  SettingsManager.swift
//  MacLocalModelBridge
//

import Foundation
import Combine

public class SettingsManager: ObservableObject {
    public static let shared = SettingsManager()

    private let defaults = UserDefaults.standard

    @Published public var host: String {
        didSet { defaults.set(host, forKey: "bridge_host") }
    }

    @Published public var port: Int {
        didSet { defaults.set(port, forKey: "bridge_port") }
    }

    @Published public var serverPort: Int {
        didSet { defaults.set(serverPort, forKey: "phone_server_port") }
    }

    @Published public var apiKey: String {
        didSet { defaults.set(apiKey, forKey: "bridge_api_key") }
    }

    @Published public var defaultModel: String {
        didSet { defaults.set(defaultModel, forKey: "bridge_default_model") }
    }

    @Published public var temperature: Double {
        didSet { defaults.set(temperature, forKey: "bridge_temperature") }
    }

    @Published public var systemPrompt: String {
        didSet { defaults.set(systemPrompt, forKey: "bridge_system_prompt") }
    }

    @Published public var autoDiscover: Bool {
        didSet { defaults.set(autoDiscover, forKey: "bridge_auto_discover") }
    }

    public var baseUrlString: String {
        var trimmedHost = host.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "http://", with: "")
            .replacingOccurrences(of: "https://", with: "")
            .trimmingCharacters(in: CharacterSet(charactersIn: "/"))

        if let scopeIndex = trimmedHost.firstIndex(of: "%") {
            trimmedHost = String(trimmedHost[..<scopeIndex])
        }
        trimmedHost = trimmedHost.trimmingCharacters(in: .whitespacesAndNewlines)

        guard !trimmedHost.isEmpty else { return "" }

        let hostOnly: String
        if let separatorIndex = trimmedHost.firstIndex(of: ":") {
            hostOnly = String(trimmedHost[..<separatorIndex])
        } else {
            hostOnly = trimmedHost
        }

        guard !hostOnly.isEmpty else { return "" }
        return "http://\(hostOnly):\(port)"
    }

    public var phoneServerUrlString: String {
        guard let lanIp = PhoneHttpServer.shared.currentLanIP else { return "" }
        return "http://\(lanIp):\(serverPort)"
    }

    private init() {
        self.host = defaults.string(forKey: "bridge_host") ?? ""
        let savedPort = defaults.integer(forKey: "bridge_port")
        self.port = savedPort > 0 ? savedPort : 8080
        self.apiKey = defaults.string(forKey: "bridge_api_key") ?? ""
        self.defaultModel = defaults.string(forKey: "bridge_default_model") ?? "llama3.2:3b"
        let savedTemp = defaults.double(forKey: "bridge_temperature")
        self.temperature = savedTemp > 0 ? savedTemp : 0.7
        self.systemPrompt = defaults.string(forKey: "bridge_system_prompt") ?? "You are an ultra-fast local assistant on MacBook M-series."
        self.autoDiscover = defaults.object(forKey: "bridge_auto_discover") == nil ? true : defaults.bool(forKey: "bridge_auto_discover")
        let savedServerPort = defaults.integer(forKey: "phone_server_port")
        self.serverPort = savedServerPort > 0 ? savedServerPort : 9090
    }

    public func setEndpoint(host: String, port: Int) {
        self.host = host
        self.port = port
    }
}

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
        let cleanHost = host.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "http://", with: "")
            .replacingOccurrences(of: "https://", with: "")
            .trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard !cleanHost.isEmpty else { return "" }
        return "http://\(cleanHost):\(port)"
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
    }

    public func setEndpoint(host: String, port: Int) {
        self.host = host
        self.port = port
    }
}

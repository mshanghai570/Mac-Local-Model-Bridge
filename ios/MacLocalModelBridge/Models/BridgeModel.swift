//
//  BridgeModel.swift
//  MacLocalModelBridge
//

import Foundation

public struct BridgeModel: Identifiable, Codable, Hashable {
    public var id: String { name }
    public let name: String
    public let model: String?
    public let size: Int64?
    public let sizeFormatted: String?
    public let parameterSize: String?
    public let quantizationLevel: String?
    public let format: String?
    public let digest: String?
    public let modifiedAt: String?
    public let capabilities: [String]?

    enum CodingKeys: String, CodingKey {
        case name
        case model
        case size
        case sizeBytes = "size_bytes"
        case sizeFormatted = "size_formatted"
        case parameterSize = "parameter_size"
        case quantizationLevel = "quantization_level"
        case format
        case digest
        case modifiedAt = "modified_at"
        case capabilities
        case capabilitiesList = "capabilities_list"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.name = try container.decode(String.self, forKey: .name)
        self.model = try? container.decodeIfPresent(String.self, forKey: .model)
        
        // Handle size or size_bytes
        if let s = try? container.decodeIfPresent(Int64.self, forKey: .size) {
            self.size = s
        } else if let sb = try? container.decodeIfPresent(Int64.self, forKey: .sizeBytes) {
            self.size = sb
        } else {
            self.size = 0
        }

        self.sizeFormatted = try? container.decodeIfPresent(String.self, forKey: .sizeFormatted)
        self.parameterSize = try? container.decodeIfPresent(String.self, forKey: .parameterSize)
        self.quantizationLevel = try? container.decodeIfPresent(String.self, forKey: .quantizationLevel)
        self.format = try? container.decodeIfPresent(String.self, forKey: .format)
        self.digest = try? container.decodeIfPresent(String.self, forKey: .digest)
        self.modifiedAt = try? container.decodeIfPresent(String.self, forKey: .modifiedAt)

        // Handle capabilities as [String] or as Dictionary or capabilities_list
        if let list = try? container.decodeIfPresent([String].self, forKey: .capabilitiesList) {
            self.capabilities = list
        } else if let capsArray = try? container.decodeIfPresent([String].self, forKey: .capabilities) {
            self.capabilities = capsArray
        } else if let capsDict = try? container.decodeIfPresent([String: Bool].self, forKey: .capabilities) {
            var inferred: [String] = []
            if capsDict["text"] == true { inferred.append("chat") }
            if capsDict["vision"] == true { inferred.append("vision") }
            if capsDict["tools"] == true { inferred.append("tools") }
            if capsDict["embeddings"] == true { inferred.append("embeddings") }
            self.capabilities = inferred
        } else {
            self.capabilities = []
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(name, forKey: .name)
        try container.encodeIfPresent(model, forKey: .model)
        try container.encodeIfPresent(size, forKey: .size)
        try container.encodeIfPresent(sizeFormatted, forKey: .sizeFormatted)
        try container.encodeIfPresent(parameterSize, forKey: .parameterSize)
        try container.encodeIfPresent(quantizationLevel, forKey: .quantizationLevel)
        try container.encodeIfPresent(format, forKey: .format)
        try container.encodeIfPresent(digest, forKey: .digest)
        try container.encodeIfPresent(modifiedAt, forKey: .modifiedAt)
        try container.encodeIfPresent(capabilities, forKey: .capabilities)
    }
}

public struct ModelsListResponse: Codable {
    public let models: [BridgeModel]
}

public struct HealthResponse: Codable {
    public let status: String
    public let provider: String
    public let backendReachable: Bool
    public let backendUrl: String?
    public let modelsCount: Int
    public let message: String
    public let timestamp: Double?
    public let authRequired: Bool
    public let lanIp: String?
    public let port: Int?
    public let device: String?
    public let bridge: String?
    public let zed: Bool?
    public let accessibility: Bool?
    public let protocolVersion: String?

    enum CodingKeys: String, CodingKey {
        case status
        case provider
        case providerName = "provider_name"
        case backendReachable = "backend_reachable"
        case providerStatus = "provider_status"
        case backendUrl = "backend_url"
        case providerUrl = "provider_url"
        case modelsCount = "models_count"
        case availableModels = "available_models"
        case message
        case timestamp
        case authRequired = "auth_required"
        case authEnabled = "auth_enabled"
        case lanIp = "lan_ip"
        case lanAddress = "lan_address"
        case port
        case device
        case bridge
        case zed
        case accessibility
        case protocolVersion = "protocolVersion"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.status = (try? container.decodeIfPresent(String.self, forKey: .status)) ?? "ok"
        self.provider = (try? container.decodeIfPresent(String.self, forKey: .provider))
            ?? (try? container.decodeIfPresent(String.self, forKey: .providerName))
            ?? "ollama"

        if let reachable = try? container.decodeIfPresent(Bool.self, forKey: .backendReachable) {
            self.backendReachable = reachable
        } else if let pStatus = try? container.decodeIfPresent(String.self, forKey: .providerStatus) {
            self.backendReachable = (pStatus == "connected")
        } else {
            self.backendReachable = true
        }

        self.backendUrl = (try? container.decodeIfPresent(String.self, forKey: .backendUrl))
            ?? (try? container.decodeIfPresent(String.self, forKey: .providerUrl))

        self.modelsCount = (try? container.decodeIfPresent(Int.self, forKey: .modelsCount))
            ?? (try? container.decodeIfPresent(Int.self, forKey: .availableModels))
            ?? 0

        self.message = (try? container.decodeIfPresent(String.self, forKey: .message)) ?? ""
        self.timestamp = try? container.decodeIfPresent(Double.self, forKey: .timestamp)

        self.authRequired = (try? container.decodeIfPresent(Bool.self, forKey: .authRequired))
            ?? (try? container.decodeIfPresent(Bool.self, forKey: .authEnabled))
            ?? false

        self.lanIp = (try? container.decodeIfPresent(String.self, forKey: .lanIp))
            ?? (try? container.decodeIfPresent(String.self, forKey: .lanAddress))

        self.port = try? container.decodeIfPresent(Int.self, forKey: .port)

        self.device = try? container.decodeIfPresent(String.self, forKey: .device)
        self.bridge = try? container.decodeIfPresent(String.self, forKey: .bridge)
        self.zed = try? container.decodeIfPresent(Bool.self, forKey: .zed)
        self.accessibility = try? container.decodeIfPresent(Bool.self, forKey: .accessibility)
        self.protocolVersion = try? container.decodeIfPresent(String.self, forKey: .protocolVersion)
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(status, forKey: .status)
        try container.encode(provider, forKey: .provider)
        try container.encode(backendReachable, forKey: .backendReachable)
        try container.encodeIfPresent(backendUrl, forKey: .backendUrl)
        try container.encode(modelsCount, forKey: .modelsCount)
        try container.encode(message, forKey: .message)
        try container.encodeIfPresent(timestamp, forKey: .timestamp)
        try container.encode(authRequired, forKey: .authRequired)
        try container.encodeIfPresent(lanIp, forKey: .lanIp)
        try container.encodeIfPresent(port, forKey: .port)
        try container.encodeIfPresent(device, forKey: .device)
        try container.encodeIfPresent(bridge, forKey: .bridge)
        try container.encodeIfPresent(zed, forKey: .zed)
        try container.encodeIfPresent(accessibility, forKey: .accessibility)
        try container.encodeIfPresent(protocolVersion, forKey: .protocolVersion)
    }
}


public struct ChatMessagePayload: Codable {
    public let role: String
    public let content: String
    public let toolCalls: [OpenAIToolCall]?
    public let toolCallId: String?

    public init(role: String, content: String, toolCalls: [OpenAIToolCall]? = nil, toolCallId: String? = nil) {
        self.role = role
        self.content = content
        self.toolCalls = toolCalls
        self.toolCallId = toolCallId
    }
}

public struct OpenAIToolDefinition: Codable {
    public let type: String
    public let function: OpenAIFunction

    public init(type: String = "function", function: OpenAIFunction) {
        self.type = type
        self.function = function
    }
}

public struct OpenAIFunction: Codable {
    public let name: String
    public let description: String
    public let parameters: [String: Any]

    public init(name: String, description: String, parameters: [String: Any]) {
        self.name = name
        self.description = description
        self.parameters = parameters
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.name = try container.decode(String.self, forKey: .name)
        self.description = try container.decode(String.self, forKey: .description)
        let data = try container.decode(Data.self, forKey: .parameters)
        self.parameters = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(name, forKey: .name)
        try container.encode(description, forKey: .description)
        let data = try JSONSerialization.data(withJSONObject: parameters)
        try container.encode(data, forKey: .parameters)
    }

    enum CodingKeys: String, CodingKey {
        case name, description, parameters
    }
}

public struct OpenAIToolCall: Codable, Identifiable, Equatable {
    public let id: String
    public let type: String
    public let function: OpenAIFunctionCall

    public init(id: String, type: String = "function", function: OpenAIFunctionCall) {
        self.id = id
        self.type = type
        self.function = function
    }
}

public struct OpenAIFunctionCall: Codable, Equatable {
    public let name: String
    public let arguments: String

    public init(name: String, arguments: String) {
        self.name = name
        self.arguments = arguments
    }
}

public struct ChatRequestPayload: Codable {
    public let model: String
    public let messages: [ChatMessagePayload]
    public let stream: Bool
    public let temperature: Double?
    public let system: String?
    public let tools: [OpenAIToolDefinition]?

    public init(model: String, messages: [ChatMessagePayload], stream: Bool = false, temperature: Double? = nil, system: String? = nil, tools: [OpenAIToolDefinition]? = nil) {
        self.model = model
        self.messages = messages
        self.stream = stream
        self.temperature = temperature
        self.system = system
        self.tools = tools
    }
}

public struct ChatResponsePayload: Codable {
    public let content: String
    public let model: String
    public let totalDurationMs: Double?
    public let promptEvalCount: Int?
    public let evalCount: Int?
    public let toolCalls: [OpenAIToolCall]?

    enum CodingKeys: String, CodingKey {
        case content
        case model
        case totalDurationMs = "total_duration_ms"
        case promptEvalCount = "prompt_eval_count"
        case evalCount = "eval_count"
        case toolCalls = "tool_calls"
    }

    public init(content: String, model: String, totalDurationMs: Double? = nil, promptEvalCount: Int? = nil, evalCount: Int? = nil, toolCalls: [OpenAIToolCall]? = nil) {
        self.content = content
        self.model = model
        self.totalDurationMs = totalDurationMs
        self.promptEvalCount = promptEvalCount
        self.evalCount = evalCount
        self.toolCalls = toolCalls
    }
}

public struct StreamChunkPayload: Codable {
    public let content: String?
    public let done: Bool?
    public let model: String?
    public let toolCalls: [OpenAIToolCall]?

    enum CodingKeys: String, CodingKey {
        case content
        case done
        case model
        case toolCalls = "tool_calls"
    }
}

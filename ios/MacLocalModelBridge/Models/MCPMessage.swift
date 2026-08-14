//
//  MCPMessage.swift
//  MacLocalModelBridge
//

import Foundation

public struct JsonRpcRequest<T: Codable>: Codable {
    public let jsonrpc: String
    public let id: Int
    public let method: String
    public let params: T

    public init(id: Int = Int.random(in: 1000...9999), method: String, params: T) {
        self.jsonrpc = "2.0"
        self.id = id
        self.method = method
        self.params = params
    }
}

public struct MCPToolCallParams: Codable {
    public let name: String
    public let arguments: [String: AnyCodable]
    
    public init(name: String, arguments: [String: AnyCodable] = [:]) {
        self.name = name
        self.arguments = arguments
    }
}

public struct AnyCodable: Codable {
    public let value: Any

    public init(_ value: Any) {
        self.value = value
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let intVal = try? container.decode(Int.self) {
            self.value = intVal
        } else if let doubleVal = try? container.decode(Double.self) {
            self.value = doubleVal
        } else if let stringVal = try? container.decode(String.self) {
            self.value = stringVal
        } else if let boolVal = try? container.decode(Bool.self) {
            self.value = boolVal
        } else if let arrayVal = try? container.decode([AnyCodable].self) {
            self.value = arrayVal.map { $0.value }
        } else if let dictVal = try? container.decode([String: AnyCodable].self) {
            self.value = dictVal.mapValues { $0.value }
        } else {
            self.value = ()
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        if let intVal = value as? Int {
            try container.encode(intVal)
        } else if let doubleVal = value as? Double {
            try container.encode(doubleVal)
        } else if let stringVal = value as? String {
            try container.encode(stringVal)
        } else if let boolVal = value as? Bool {
            try container.encode(boolVal)
        } else if let arrayVal = value as? [Any] {
            let codableArray = arrayVal.map { AnyCodable($0) }
            try container.encode(codableArray)
        } else if let dictVal = value as? [String: Any] {
            let codableDict = dictVal.mapValues { AnyCodable($0) }
            try container.encode(codableDict)
        }
    }
}

public struct MCPContentItem: Codable {
    public let type: String
    public let text: String?
}

public struct MCPToolResult: Codable {
    public let content: [MCPContentItem]?
    public let isError: Bool?
}

public struct JsonRpcResponse<T: Codable>: Codable {
    public let jsonrpc: String
    public let id: Int
    public let result: T?
    public let error: JsonRpcError?
}

public struct JsonRpcError: Codable {
    public let code: Int
    public let message: String
}

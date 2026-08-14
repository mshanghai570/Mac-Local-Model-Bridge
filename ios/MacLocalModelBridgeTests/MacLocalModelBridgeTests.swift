//
//  MacLocalModelBridgeTests.swift
//  MacLocalModelBridgeTests
//

import XCTest
@testable import MacLocalModelBridge

final class MacLocalModelBridgeTests: XCTestCase {

    func testDecodingBridgeModel() throws {
        let json = """
        {
            "name": "llama3.2:3b",
            "model": "llama3.2:3b",
            "size": 2000000000,
            "size_formatted": "2.0 GB",
            "parameter_size": "3B",
            "quantization_level": "Q4_K_M",
            "format": "gguf",
            "digest": "abc12345",
            "modified_at": "2025-01-01T00:00:00Z",
            "capabilities": ["chat", "tools"]
        }
        """.data(using: .utf8)!

        let model = try JSONDecoder().decode(BridgeModel.self, data: json)
        XCTAssertEqual(model.name, "llama3.2:3b")
        XCTAssertEqual(model.parameterSize, "3B")
        XCTAssertEqual(model.sizeFormatted, "2.0 GB")
        XCTAssertEqual(model.capabilities?.count, 2)
    }

    func testSettingsManagerBaseUrlFormatting() {
        let settings = SettingsManager.shared
        settings.setEndpoint(host: "http://192.168.1.100", port: 8080)
        XCTAssertEqual(settings.baseUrlString, "http://192.168.1.100:8080")

        settings.setEndpoint(host: "10.0.0.45", port: 11434)
        XCTAssertEqual(settings.baseUrlString, "http://10.0.0.45:11434")
    }

    func testJsonRpcRequestFormatting() throws {
        let params = MCPToolCallParams(name: "list_models", arguments: [:])
        let request = JsonRpcRequest(id: 42, method: "tools/call", params: params)
        let data = try JSONEncoder().encode(request)
        let jsonString = String(data: data, encoding: .utf8)!

        XCTAssertTrue(jsonString.contains("\"jsonrpc\":\"2.0\""))
        XCTAssertTrue(jsonString.contains("\"method\":\"tools/call\""))
        XCTAssertTrue(jsonString.contains("\"id\":42"))
    }
}

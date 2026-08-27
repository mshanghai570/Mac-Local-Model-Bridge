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

        let model = try JSONDecoder().decode(BridgeModel.self, from: json)
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

    func testSettingsManagerStripsNetworkInterfaceScope() {
        let settings = SettingsManager.shared
        settings.setEndpoint(host: "192.168.68.102%en0", port: 8080)
        XCTAssertEqual(settings.baseUrlString, "http://192.168.68.102:8080")
        XCTAssertNotNil(URL(string: settings.baseUrlString))

        settings.setEndpoint(host: "192.168.68.102%en0:8080", port: 8080)
        XCTAssertEqual(settings.baseUrlString, "http://192.168.68.102:8080")
    }

    func testHealthResponseDecodesBridgeFields() throws {
        let json = """
        {
            "status": "ok",
            "device": "Mac",
            "bridge": "running",
            "zed": true,
            "accessibility": true,
            "protocolVersion": "1.0"
        }
        """.data(using: .utf8)!

        let health = try JSONDecoder().decode(HealthResponse.self, from: json)
        XCTAssertEqual(health.status, "ok")
        XCTAssertEqual(health.device, "Mac")
        XCTAssertEqual(health.bridge, "running")
        XCTAssertEqual(health.zed, true)
        XCTAssertEqual(health.accessibility, true)
        XCTAssertEqual(health.protocolVersion, "1.0")
    }

    func testHealthResponseBackwardsCompatible() throws {
        let legacyJson = """
        {
            "status": "healthy",
            "service": "local-ai-gateway",
            "uptime_seconds": 42
        }
        """.data(using: .utf8)!

        let health = try JSONDecoder().decode(HealthResponse.self, from: legacyJson)
        XCTAssertEqual(health.status, "healthy")
        XCTAssertNil(health.zed)
        XCTAssertNil(health.accessibility)
        XCTAssertNil(health.protocolVersion)
    }

    func testJsonRpcRequestFormatting() throws {
        let params = MCPToolCallParams(name: "list_models", arguments: [:])
        let request = JsonRpcRequest(id: 42, method: "tools/call", params: params)
        let data = try JSONEncoder().encode(request)

        let decoded = try JSONDecoder().decode(JsonRpcRequest<MCPToolCallParams>.self, from: data)
        XCTAssertEqual(decoded.jsonrpc, "2.0")
        XCTAssertEqual(decoded.method, "tools/call")
        XCTAssertEqual(decoded.id, 42)
        XCTAssertEqual(decoded.params.name, "list_models")
    }

    // MARK: - DeviceModelStore import tests

    func testIsInsideOurContainerRespectsPathBoundaries() {
        let store = DeviceModelStore.shared
        let docPath = store.documentsDirectory.resolvingSymlinksInPath().path

        // A path that merely shares a string prefix with "Documents" but is
        // NOT actually inside it (e.g. "DocumentsBackup/file.gguf").
        // The old hasPrefix(doc) check without a trailing "/" would return
        // true (false positive), routing to moveItem for a file outside our
        // sandbox — which fails with "the file couldn't be found because there
        // is no such file".
        let falsePositivePath = docPath + "Backup/test.gguf"
        let falsePositiveURL = URL(fileURLWithPath: falsePositivePath)

        XCTAssertFalse(store.isInsideOurContainer(falsePositiveURL),
            "A path sharing only a string prefix with Documents must NOT be treated as inside our container")

        // A genuine file inside Documents should return true
        let insideDocURL = store.documentsDirectory.appendingPathComponent("test.gguf")
        XCTAssertTrue(store.isInsideOurContainer(insideDocURL),
            "A file inside the Documents directory must be treated as inside our container")

        // A file inside tmp should return true
        let insideTmpURL = FileManager.default.temporaryDirectory.appendingPathComponent("test.gguf")
        XCTAssertTrue(store.isInsideOurContainer(insideTmpURL),
            "A file inside the temporary directory must be treated as inside our container")
    }

    func testDestinationURLDeduplication() throws {
        let store = DeviceModelStore.shared
        let fileName = "test-dedup-model.gguf"
        let baseURL = store.documentsDirectory.appendingPathComponent(fileName)

        // Clean slate
        try? FileManager.default.removeItem(at: baseURL)

        // No existing file → return the base URL
        let firstURL = store.destinationURL(for: fileName)
        XCTAssertEqual(firstURL.path, baseURL.path)

        // Create the file so the next call sees it exists
        try Data("gguf".utf8).write(to: baseURL)

        // Second call → should return a deduplicated name with a counter
        let secondURL = store.destinationURL(for: fileName)
        XCTAssertNotEqual(secondURL.path, baseURL.path,
            "destinationURL should return a different path when the base already exists")
        XCTAssertTrue(secondURL.lastPathComponent.hasPrefix("test-dedup-model ("),
            "Deduplicated filename should contain the base name with a counter")
        XCTAssertTrue(secondURL.lastPathComponent.hasSuffix(".gguf"),
            "Deduplicated filename should preserve the extension")

        // Clean up
        try? FileManager.default.removeItem(at: baseURL)
        try? FileManager.default.removeItem(at: secondURL)
    }
}

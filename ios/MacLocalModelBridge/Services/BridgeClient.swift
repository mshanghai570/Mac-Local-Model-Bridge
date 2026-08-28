//
//  BridgeClient.swift
//  MacLocalModelBridge
//

import Foundation
import Combine

public enum BridgeError: LocalizedError {
    case invalidUrl(String)
    case invalidResponse(Int, String)
    case authenticationFailed
    case decodingError(Error)
    case connectionFailed(String)
    case serverError(String)
    case cancelled

    public var errorDescription: String? {
        switch self {
        case .invalidUrl(let url):
            return "Bridge URL is not configured or invalid: '\(url)'. Open Settings and enter your Mac's LAN IP address (e.g. 192.168.1.xxx) or use Bonjour discovery."
        case .invalidResponse(let code, let msg):
            return "Server responded with HTTP \(code): \(msg). Is the gateway running on your Mac?"
        case .authenticationFailed:
            return "Authentication failed. Check your Bridge API Key in Settings, or disable auth on the Mac gateway."
        case .decodingError(let err):
            return "Failed to parse response from Mac Bridge: \(err.localizedDescription)"
        case .connectionFailed(let msg):
            return "Could not connect to Mac Bridge. Check: 1) Mac is on the same Wi-Fi, 2) Gateway is running ('local-ai-gateway serve'), 3) macOS Firewall allows incoming connections for Python on port 8080, 4) IP address in Settings is correct. (\(msg))"
        case .serverError(let msg):
            return "Mac Bridge error: \(msg)"
        case .cancelled:
            return "Inference cancelled by user."
        }
    }
}

public class BridgeClient: ObservableObject {
    private let urlSession: URLSession

    public init(urlSession: URLSession = .shared) {
        self.urlSession = urlSession
    }

    private func createRequest(path: String, method: String = "GET", body: Data? = nil) throws -> URLRequest {
        let settings = SettingsManager.shared
        let fullUrlStr = "\(settings.baseUrlString)\(path)"
        guard
            let url = URL(string: fullUrlStr),
            let scheme = url.scheme,
            !scheme.isEmpty,
            let host = url.host,
            !host.isEmpty
        else {
            throw BridgeError.invalidUrl(fullUrlStr)
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 60
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        if !settings.apiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            request.setValue("Bearer \(settings.apiKey)", forHTTPHeaderField: "Authorization")
            request.setValue(settings.apiKey, forHTTPHeaderField: "X-API-Key")
        }

        request.httpBody = body
        return request
    }

    // MARK: - Health Check
    public func checkHealth() async throws -> HealthResponse {
        var request = try createRequest(path: "/health")
        request.timeoutInterval = 10
        do {
            let (data, response) = try await urlSession.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                throw BridgeError.connectionFailed("No HTTP response received")
            }
            if httpResponse.statusCode == 401 || httpResponse.statusCode == 403 {
                throw BridgeError.authenticationFailed
            }
            guard httpResponse.statusCode == 200 else {
                let errText = String(data: data, encoding: .utf8) ?? "HTTP \(httpResponse.statusCode)"
                throw BridgeError.invalidResponse(httpResponse.statusCode, errText)
            }
            let decoder = JSONDecoder()
            return try decoder.decode(HealthResponse.self, from: data)
        } catch let error as BridgeError {
            throw error
        } catch {
            throw BridgeError.connectionFailed(error.localizedDescription)
        }
    }

    // MARK: - Fetch Local Models
    public func fetchModels() async throws -> [BridgeModel] {
        let request = try createRequest(path: "/models")
        do {
            let (data, response) = try await urlSession.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                throw BridgeError.connectionFailed("No HTTP response received")
            }
            if httpResponse.statusCode == 401 || httpResponse.statusCode == 403 {
                throw BridgeError.authenticationFailed
            }
            guard httpResponse.statusCode == 200 else {
                let errText = String(data: data, encoding: .utf8) ?? "HTTP \(httpResponse.statusCode)"
                throw BridgeError.invalidResponse(httpResponse.statusCode, errText)
            }
            let decoder = JSONDecoder()
            let listResponse = try decoder.decode(ModelsListResponse.self, from: data)
            return listResponse.models
        } catch let error as BridgeError {
            throw error
        } catch {
            throw BridgeError.connectionFailed(error.localizedDescription)
        }
    }

    // MARK: - Non-Streaming Chat Completion
    public func chat(
        messages: [ChatMessage],
        model: String,
        temperature: Double = 0.7,
        system: String? = nil,
        tools: [OpenAIToolDefinition]? = nil
    ) async throws -> ChatResponsePayload {
        let payloadMessages = messages.map {
            ChatMessagePayload(role: $0.role.rawValue, content: $0.content)
        }
        let payload = ChatRequestPayload(
            model: model,
            messages: payloadMessages,
            stream: false,
            temperature: temperature,
            system: system,
            tools: tools
        )

        let bodyData = try JSONEncoder().encode(payload)
        let request = try createRequest(path: "/chat", method: "POST", body: bodyData)

        do {
            let (data, response) = try await urlSession.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                throw BridgeError.connectionFailed("No response")
            }
            if httpResponse.statusCode == 401 || httpResponse.statusCode == 403 {
                throw BridgeError.authenticationFailed
            }
            guard httpResponse.statusCode == 200 else {
                let errText = String(data: data, encoding: .utf8) ?? "HTTP \(httpResponse.statusCode)"
                throw BridgeError.invalidResponse(httpResponse.statusCode, errText)
            }
            return try JSONDecoder().decode(ChatResponsePayload.self, from: data)
        } catch let error as BridgeError {
            throw error
        } catch {
            throw BridgeError.connectionFailed(error.localizedDescription)
        }
    }

    // MARK: - Real-Time Server-Sent Events (SSE) Streaming
    public struct ChatStreamChunk: Equatable {
        public let content: String?
        public let toolCalls: [OpenAIToolCall]?
        public let done: Bool?
        public let requestId: String?
    }

    public func streamChat(
        messages: [ChatMessage],
        model: String,
        temperature: Double = 0.7,
        system: String? = nil,
        tools: [OpenAIToolDefinition]? = nil,
        requestId: String? = nil
    ) -> AsyncThrowingStream<ChatStreamChunk, Error> {
        return AsyncThrowingStream { continuation in
            let task = Task.detached {
                do {
                    let payloadMessages = messages.map {
                        ChatMessagePayload(role: $0.role.rawValue, content: $0.content)
                    }
                    let payload = ChatRequestPayload(
                        model: model,
                        messages: payloadMessages,
                        stream: true,
                        temperature: temperature,
                        system: system,
                        tools: tools,
                        requestId: requestId
                    )

                    let bodyData = try JSONEncoder().encode(payload)
                    var request = try self.createRequest(path: "/chat", method: "POST", body: bodyData)
                    if let requestId, !requestId.isEmpty {
                        request.setValue(requestId, forHTTPHeaderField: "X-Request-ID")
                    }
                    request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    request.timeoutInterval = 60

                    let (bytes, response) = try await self.urlSession.bytes(for: request)
                    guard let httpResponse = response as? HTTPURLResponse else {
                        continuation.finish(throwing: BridgeError.connectionFailed("No HTTP response"))
                        return
                    }

                    if httpResponse.statusCode == 401 || httpResponse.statusCode == 403 {
                        continuation.finish(throwing: BridgeError.authenticationFailed)
                        return
                    }

                    guard httpResponse.statusCode == 200 else {
                        continuation.finish(throwing: BridgeError.invalidResponse(httpResponse.statusCode, "Streaming request failed"))
                        return
                    }

                    for try await line in bytes.lines {
                        if Task.isCancelled {
                            continuation.finish(throwing: BridgeError.cancelled)
                            return
                        }

                        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
                        guard trimmed.hasPrefix("data: ") else { continue }
                        let jsonString = String(trimmed.dropFirst(6))

                        if jsonString == "[DONE]" {
                            continuation.yield(ChatStreamChunk(content: nil, toolCalls: nil, done: true, requestId: requestId))
                            break
                        }

                        if let data = jsonString.data(using: .utf8),
                           let chunk = try? JSONDecoder().decode(StreamChunkPayload.self, from: data) {
                            let output = ChatStreamChunk(
                                content: chunk.content,
                                toolCalls: chunk.toolCalls,
                                done: chunk.done,
                                requestId: chunk.requestId
                            )
                            continuation.yield(output)
                        }
                    }

                    continuation.finish()
                } catch {
                    if Task.isCancelled {
                        continuation.finish(throwing: BridgeError.cancelled)
                    } else {
                        continuation.finish(throwing: error)
                    }
                }
            }

            continuation.onTermination = { @Sendable _ in
                task.cancel()
            }
        }
    }

    // MARK: - MCP Tool Execution
    public func callMcpTool(name: String, arguments: [String: AnyCodable] = [:]) async throws -> MCPToolResult {
        let params = MCPToolCallParams(name: name, arguments: arguments)
        let rpcRequest = JsonRpcRequest(method: "tools/call", params: params)
        let bodyData = try JSONEncoder().encode(rpcRequest)
        let request = try createRequest(path: "/mcp", method: "POST", body: bodyData)

        do {
            let (data, response) = try await urlSession.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
                throw BridgeError.serverError("MCP call failed")
            }
            let rpcResponse = try JSONDecoder().decode(JsonRpcResponse<MCPToolResult>.self, from: data)
            if let error = rpcResponse.error {
                throw BridgeError.serverError(error.message)
            }
            guard let result = rpcResponse.result else {
                throw BridgeError.serverError("Empty result from MCP tool")
            }
            return result
        } catch let error as BridgeError {
            throw error
        } catch {
            throw BridgeError.connectionFailed(error.localizedDescription)
        }
    }
}

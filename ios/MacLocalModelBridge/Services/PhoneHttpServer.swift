//
//  PhoneHttpServer.swift
//  MacLocalModelBridge
//
//  Lightweight HTTP server exposing /v1/chat/completions so a
//  Mac-side CLI can send prompts to the iPhone. The server can either:
//  1. Run inference directly on-device using LocalInferenceEngine (direct mode)
//  2. Proxy requests to a configured Mac bridge (legacy mode)
//
//  Uses Network.framework (NWListener / NWConnection) only - no
//  third-party dependencies.
//

import Foundation
import Network
import Combine

public enum PhoneServerError: LocalizedError, Equatable {
    case notRunning
    case invalidRequest(String)
    case upstreamError(String)
    case cancelled
    case inferenceError(String)
    case modelNotLoaded

    public var errorDescription: String? {
        switch self {
        case .notRunning:
            return "Phone HTTP server is not running."
        case .invalidRequest(let msg):
            return "Invalid request: \(msg)"
        case .upstreamError(let msg):
            return "Upstream error: \(msg)"
        case .cancelled:
            return "Request cancelled."
        case .inferenceError(let msg):
            return "Inference error: \(msg)"
        case .modelNotLoaded:
            return "No on-device model is loaded. Import a .gguf model in the Models tab, then load it."
        }
    }
}

public struct HttpRequest: Equatable {
    public let method: String
    public let path: String
    public let headers: [String: String]
    public let body: Data
}

public struct HttpResponse: Equatable {
    public let statusCode: Int
    public let headers: [String: String]
    public let body: Data
}

public class PhoneHttpServer: ObservableObject {
    public static let shared = PhoneHttpServer()

    @Published public private(set) var isRunning: Bool = false
    @Published public private(set) var currentLanIP: String?

    /// Mode: run inference directly on-device, or proxy to upstream Mac bridge
    public enum ServerMode {
        case directInference
        case proxyToUpstream
    }

    /// Current server mode - defaults to direct inference for on-device model serving
    public var mode: ServerMode = .directInference

    private var listener: NWListener?
    private let queue = DispatchQueue(label: "com.macmodelbridge.httpserver", qos: .utility)
    private var connections: [NWConnection] = []

    private init() {}

    public func start(port: Int = 9090) {
        guard !isRunning else { return }

        let parameters = NWParameters.tcp
        parameters.allowLocalEndpointReuse = true
        parameters.allowFastOpen = true

        guard let listener = try? NWListener(using: parameters, on: NWEndpoint.Port(rawValue: UInt16(port))!) else {
            return
        }

        self.listener = listener
        self.currentLanIP = currentLANIPv4()

        listener.stateUpdateHandler = { [weak self] state in
            DispatchQueue.main.async {
                switch state {
                case .ready:
                    self?.isRunning = true
                case .failed(let error):
                    self?.isRunning = false
                    print("[PhoneHttpServer] listener failed: \(error)")
                case .cancelled:
                    self?.isRunning = false
                default:
                    break
                }
            }
        }

        listener.newConnectionHandler = { [weak self] connection in
            self?.handleConnection(connection)
        }

        listener.start(queue: queue)
    }

    public func stop() {
        listener?.cancel()
        listener = nil
        for conn in connections {
            conn.cancel()
        }
        connections.removeAll()
        isRunning = false
    }

    private func handleConnection(_ connection: NWConnection) {
        connections.append(connection)
        connection.stateUpdateHandler = { [weak self] state in
            switch state {
            case .cancelled, .failed:
                self?.connections.removeAll { $0 === connection }
            default:
                break
            }
        }

        connection.start(queue: queue)
        receiveRequest(on: connection)
    }

    private func receiveRequest(on connection: NWConnection) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] (data, _, isComplete, receiveError) in
            guard let self = self else { return }

            if let receiveError = receiveError {
                connection.cancel()
                self.connections.removeAll { $0 === connection }
                return
            }

            guard let data = data, !data.isEmpty else {
                if isComplete {
                    connection.cancel()
                    self.connections.removeAll { $0 === connection }
                }
                return
            }

            do {
                let request = try self.parseHttpRequest(data)
                self.handleRequest(request, on: connection)
            } catch {
                let response = self.buildResponse(statusCode: 400, body: ["error": error.localizedDescription])
                self.sendResponse(response, on: connection, close: true)
            }
        }
    }

    private func parseHttpRequest(_ data: Data) throws -> HttpRequest {
        guard let rawString = String(data: data, encoding: .utf8) else {
            throw PhoneServerError.invalidRequest("Non-UTF8 request")
        }

        let lines = rawString.split(separator: "\r\n", omittingEmptySubsequences: false)
        guard let firstLine = lines.first else {
            throw PhoneServerError.invalidRequest("Empty request")
        }

        let components = firstLine.split(separator: " ", maxSplits: 2)
        guard components.count == 3 else {
            throw PhoneServerError.invalidRequest("Malformed request line")
        }

        let method = String(components[0])
        let path = String(components[1])

        var headers: [String: String] = [:]

        for i in 1..<lines.count {
            let line = String(lines[i])
            if line.isEmpty {
                break
            }
            if let colonRange = line.range(of: ":") {
                let key = String(line[..<colonRange.lowerBound]).trimmingCharacters(in: .whitespaces)
                let value = String(line[colonRange.upperBound...]).trimmingCharacters(in: .whitespaces)
                headers[key] = value
            }
        }

        let headerEndPattern = "\r\n\r\n"
        guard let headerEndRange = rawString.range(of: headerEndPattern) else {
            return HttpRequest(method: method, path: path, headers: headers, body: Data())
        }

        let bodyStart = rawString.utf8.distance(from: rawString.utf8.startIndex, to: headerEndRange.upperBound)
        let body = data.subdata(in: bodyStart..<data.count)

        return HttpRequest(method: method, path: path, headers: headers, body: body)
    }

    private func handleRequest(_ request: HttpRequest, on connection: NWConnection) {
        let path = request.path
        let method = request.method

        // Handle health endpoint
        if path == "/health" && method == "GET" {
            handleHealthRequest(on: connection)
            return
        }

        // Handle models endpoint
        if path == "/v1/models" && method == "GET" {
            handleModelsRequest(on: connection)
            return
        }

        // Handle chat completions endpoint
        if (path == "/v1/chat/completions" || path == "/chat") && method == "POST" {
            handleChatCompletionsRequest(request, on: connection)
            return
        }

        // Fallback to proxy mode for other endpoints if configured
        if mode == .proxyToUpstream {
            handleProxyRequest(request, on: connection)
            return
        }

        // Unknown endpoint
        let response = buildResponse(statusCode: 404, body: ["error": "Not found"])
        sendResponse(response, on: connection, close: true)
    }

    // MARK: - Direct Inference Handlers

    private func handleHealthRequest(on connection: NWConnection) {
        var status: [String: Any] = [
            "status": "ok",
            "device": "iPhone",
            "provider": "iphone-gguf",
            "service": "phone-http-server",
            "mode": mode == .directInference ? "direct" : "proxy"
        ]

        if let info = LocalInferenceEngine.shared.loadedModelInfo {
            status["model_loaded"] = true
            status["model_name"] = info.name
        } else {
            status["model_loaded"] = false
        }

        if let ip = currentLanIP {
            status["lan_ip"] = ip
        }

        status["models"] = DeviceModelStore.shared.installedModels().map { $0.name }

        let response = buildResponse(statusCode: 200, body: status)
        sendResponse(response, on: connection, close: true)
    }

    private func handleModelsRequest(on connection: NWConnection) {
        let models = DeviceModelStore.shared.installedModels()
        let modelList = models.map { model -> [String: Any] in
            var dict: [String: Any] = [
                "id": model.name,
                "name": model.name,
                "size_bytes": model.sizeBytes,
                "size_formatted": model.sizeFormatted
            ]

            if let info = LocalInferenceEngine.shared.loadedModelInfo, info.path == model.fileURL.path {
                dict["loaded"] = true
                if let paramCount = info.parameterCount {
                    dict["parameter_count"] = paramCount
                }
                if let ctxLen = info.contextLength {
                    dict["context_length"] = ctxLen
                }
                if let quant = info.quantization {
                    dict["quantization"] = quant
                }
            } else {
                dict["loaded"] = false
            }

            return dict
        }

        let responseBody: [String: Any] = [
            "object": "list",
            "data": modelList
        ]

        let response = buildResponse(statusCode: 200, body: responseBody)
        sendResponse(response, on: connection, close: true)
    }

    private func handleChatCompletionsRequest(_ request: HttpRequest, on connection: NWConnection) {
        let acceptHeader = request.headers["Accept"] ?? ""
        let wantsStream = acceptHeader.contains("text/event-stream")

        if wantsStream {
            handleStreamingChatRequest(request, on: connection)
        } else {
            handleNonStreamingChatRequest(request, on: connection)
        }
    }

    private func handleNonStreamingChatRequest(_ request: HttpRequest, on connection: NWConnection) {
        do {
            guard let bodyJson = try JSONSerialization.jsonObject(with: request.body, options: []) as? [String: Any] else {
                throw PhoneServerError.invalidRequest("Invalid JSON body")
            }

            let messages = bodyJson["messages"] as? [[String: Any]] ?? []
            let model = bodyJson["model"] as? String ?? "auto"
            let temperature = bodyJson["temperature"] as? Double ?? 0.7
            let system = bodyJson["system"] as? String
            let maxTokens = bodyJson["max_tokens"] as? Int ?? 512

            guard LocalInferenceEngine.shared.isLoaded else {
                throw PhoneServerError.modelNotLoaded
            }

            let chatMessages = convertToChatMessages(messages, system: system)
            let result = try runInferenceSync(messages: chatMessages, temperature: temperature, maxTokens: maxTokens)

            let responseBody: [String: Any] = [
                "id": generateRequestId(),
                "object": "chat.completion",
                "created": Int(Date().timeIntervalSince1970),
                "model": model,
                "choices": [
                    [
                        "index": 0,
                        "message": [
                            "role": "assistant",
                            "content": result.content
                        ],
                        "finish_reason": "stop"
                    ]
                ],
                "usage": [
                    "prompt_tokens": result.promptTokens,
                    "completion_tokens": result.completionTokens,
                    "total_tokens": result.promptTokens + result.completionTokens
                ]
            ]

            let response = buildResponse(statusCode: 200, body: responseBody)
            sendResponse(response, on: connection, close: true)

        } catch let error as PhoneServerError {
            let response = buildResponse(statusCode: error == .modelNotLoaded ? 400 : 500, body: ["error": error.localizedDescription])
            sendResponse(response, on: connection, close: true)
        } catch {
            let response = buildResponse(statusCode: 500, body: ["error": error.localizedDescription])
            sendResponse(response, on: connection, close: true)
        }
    }

    private func handleStreamingChatRequest(_ request: HttpRequest, on connection: NWConnection) {
        do {
            guard let bodyJson = try JSONSerialization.jsonObject(with: request.body, options: []) as? [String: Any] else {
                throw PhoneServerError.invalidRequest("Invalid JSON body")
            }

            let messages = bodyJson["messages"] as? [[String: Any]] ?? []
            let model = bodyJson["model"] as? String ?? "auto"
            let temperature = bodyJson["temperature"] as? Double ?? 0.7
            let system = bodyJson["system"] as? String
            let maxTokens = bodyJson["max_tokens"] as? Int ?? 512

            guard LocalInferenceEngine.shared.isLoaded else {
                throw PhoneServerError.modelNotLoaded
            }

            let chatMessages = convertToChatMessages(messages, system: system)
            let stream = LocalInferenceEngine.shared.generate(
                messages: chatMessages,
                system: system,
                temperature: temperature,
                maxTokens: maxTokens,
                stopSequences: LocalInferenceEngine.defaultStopSequences
            )

            let requestId = generateRequestId()
            let created = Int(Date().timeIntervalSince1970)

            // Send headers
            var headers = [
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive"
            ]

            let headerString = buildStreamHeaders(statusCode: 200, headers: headers)
            guard let headerData = headerString.data(using: .utf8) else { return }
            connection.send(content: headerData, completion: .contentProcessed { _ in })

            // Process the stream asynchronously
            let task = Task.detached {
                do {
                    var isFirstToken = true

                    for try await token in stream {
                        if isFirstToken {
                            // Send first chunk with role delta
                            let firstChunk: [String: Any] = [
                                "id": requestId,
                                "object": "chat.completion.chunk",
                                "created": created,
                                "model": model,
                                "choices": [
                                    [
                                        "index": 0,
                                        "delta": ["role": "assistant", "content": ""],
                                        "finish_reason": nil
                                    ]
                                ]
                            ]
                            if let chunkString = self.formatSSEChunk(firstChunk) {
                                if let chunkBytes = chunkString.data(using: .utf8) {
                                    connection.send(content: chunkBytes, completion: .contentProcessed { _ in })
                                }
                            }
                            isFirstToken = false
                        }

                        // Send token chunk
                        let tokenChunk: [String: Any] = [
                            "id": requestId,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": model,
                            "choices": [
                                [
                                    "index": 0,
                                    "delta": ["content": token],
                                    "finish_reason": nil
                                ]
                            ]
                        ]
                        if let chunkString = self.formatSSEChunk(tokenChunk) {
                            if let chunkBytes = chunkString.data(using: .utf8) {
                                connection.send(content: chunkBytes, completion: .contentProcessed { _ in })
                            }
                        }
                    }

                    // Send done chunk
                    let doneChunk: [String: Any] = [
                        "id": requestId,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [
                            [
                                "index": 0,
                                "delta": [:],
                                "finish_reason": "stop"
                            ]
                        ]
                    ]
                    if let doneString = self.formatSSEChunk(doneChunk) {
                        if let doneBytes = doneString.data(using: .utf8) {
                            connection.send(content: doneBytes, completion: .contentProcessed { _ in })
                        }
                    }

                    // Send [DONE] marker
                    let doneMarker = "data: [DONE]\n\n"
                    if let doneMarkerBytes = doneMarker.data(using: .utf8) {
                        connection.send(content: doneMarkerBytes, completion: .contentProcessed { error in
                            connection.cancel()
                            self.connections.removeAll { $0 === connection }
                        })
                    }

                } catch {
                    let errorChunk: [String: Any] = [
                        "id": requestId,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [
                            [
                                "index": 0,
                                "delta": ["content": "\n[ERROR: \(error.localizedDescription)]"],
                                "finish_reason": "error"
                            ]
                        ]
                    ]
                    if let errorString = self.formatSSEChunk(errorChunk) {
                        if let errorBytes = errorString.data(using: .utf8) {
                            connection.send(content: errorBytes, completion: .contentProcessed { _ in })
                        }
                    }
                    let doneMarker = "data: [DONE]\n\n"
                    if let doneMarkerBytes = doneMarker.data(using: .utf8) {
                        connection.send(content: doneMarkerBytes, completion: .contentProcessed { _ in })
                    }
                    connection.cancel()
                    self.connections.removeAll { $0 === connection }
                }
            }

        } catch let error as PhoneServerError {
            let response = buildResponse(statusCode: error == .modelNotLoaded ? 400 : 500, body: ["error": error.localizedDescription])
            sendResponse(response, on: connection, close: true)
        } catch {
            let response = buildResponse(statusCode: 500, body: ["error": error.localizedDescription])
            sendResponse(response, on: connection, close: true)
        }
    }

    private func formatSSEChunk(_ data: [String: Any]) -> String? {
        guard let jsonData = try? JSONSerialization.data(withJSONObject: data, options: []) else {
            return nil
        }
        let jsonString = String(data: jsonData, encoding: .utf8) ?? ""
        // Escape special characters for SSE
        let escaped = jsonString
            .replacingOccurrences(of: "\n", with: "\\n")
            .replacingOccurrences(of: "\r", with: "\\r")
        return "data: \(escaped)\n\n"
    }

    private func buildStreamHeaders(statusCode: Int, headers: [String: String]) -> String {
        let statusText = httpStatusText(for: statusCode)
        var headerLines = [
            "HTTP/1.1 \(statusCode) \(statusText)",
            "Content-Type: text/event-stream",
            "Cache-Control: no-cache",
            "Connection: keep-alive"
        ]

        for (key, value) in headers {
            headerLines.append("\(key): \(value)")
        }

        let headerString = headerLines.joined(separator: "\r\n") + "\r\n\r\n"
        return headerString
    }

    private struct InferenceResult {
        let content: String
        let promptTokens: Int
        let completionTokens: Int
    }

    private func runInferenceSync(messages: [ChatMessage], temperature: Double, maxTokens: Int) throws -> InferenceResult {
        let semaphore = DispatchSemaphore(value: 0)
        var resultContent = ""
        var capturedError: Error? = nil
        var completionTokenCount = 0

        let stream = LocalInferenceEngine.shared.generate(
            messages: messages,
            system: nil,
            temperature: temperature,
            maxTokens: maxTokens,
            stopSequences: LocalInferenceEngine.defaultStopSequences
        )

        Task.detached {
            do {
                for try await token in stream {
                    resultContent += token
                    completionTokenCount += 1
                }
                semaphore.signal()
            } catch let caughtError {
                capturedError = caughtError
                semaphore.signal()
            }
        }

        _ = semaphore.wait(timeout: .distantFuture)

        if let error = capturedError {
            throw error
        }

        // Estimate prompt tokens
        let avgCharsPerToken = 4
        var promptTokenCount = 0
        for message in messages {
            promptTokenCount += max(1, message.content.count / avgCharsPerToken)
        }

        return InferenceResult(
            content: resultContent,
            promptTokens: promptTokenCount,
            completionTokens: completionTokenCount
        )
    }

    private func convertToChatMessages(_ messageDicts: [[String: Any]], system: String?) -> [ChatMessage] {
        var chatMessages: [ChatMessage] = []

        // Add system message if provided
        if let system = system, !system.isEmpty {
            chatMessages.append(ChatMessage(role: .system, content: system))
        }

        for dict in messageDicts {
            guard let roleStr = dict["role"] as? String else { continue }
            let content = dict["content"] as? String ?? ""

            let role: MessageRole
            switch roleStr.lowercased() {
            case "user": role = .user
            case "assistant": role = .assistant
            case "system": role = .system
            default: role = .user
            }

            chatMessages.append(ChatMessage(role: role, content: content))
        }

        return chatMessages
    }

    private func generateRequestId() -> String {
        let uuid = UUID()
        return "chatcmpl-\(uuid.uuidString.prefix(24))"
    }

    // MARK: - Proxy Handlers (Legacy Mode)

    private func handleProxyRequest(_ request: HttpRequest, on connection: NWConnection) {
        guard let settings = SettingsManager.shared.upstream else {
            let response = buildResponse(statusCode: 500, body: ["error": "Upstream Mac bridge not configured"])
            sendResponse(response, on: connection, close: true)
            return
        }

        var urlRequest = URLRequest(url: settings.url)
        urlRequest.httpMethod = request.method
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.httpBody = request.body

        if !settings.apiKey.isEmpty {
            urlRequest.setValue("Bearer \(settings.apiKey)", forHTTPHeaderField: "Authorization")
        }

        let task = URLSession.shared.dataTask(with: urlRequest) { [weak self] data, response, error in
            guard let self = self else { return }

            if let error = error {
                let response = self.buildResponse(statusCode: 502, body: ["error": error.localizedDescription])
                self.sendResponse(response, on: connection, close: true)
                return
            }

            guard let httpResponse = response as? HTTPURLResponse else {
                let response = self.buildResponse(statusCode: 502, body: ["error": "No HTTP response"])
                self.sendResponse(response, on: connection, close: true)
                return
            }

            let responseBody = data ?? Data()
            var headers: [String: String] = [:]
            if let contentType = httpResponse.allHeaderFields["Content-Type"] as? String {
                headers["Content-Type"] = contentType
            }

            let response = HttpResponse(statusCode: httpResponse.statusCode, headers: headers, body: responseBody)

            // For SSE streaming from upstream, don't close the connection
            let shouldClose = !(httpResponse.statusCode == 200 &&
                headers["Content-Type"]?.contains("text/event-stream") == true)

            self.sendResponse(response, on: connection, close: shouldClose)
        }
        task.resume()
    }

    // MARK: - Response Helpers

    private func sendResponse(_ response: HttpResponse, on connection: NWConnection, close: Bool) {
        let statusText = httpStatusText(for: response.statusCode)
        var headerLines = [
            "HTTP/1.1 \(response.statusCode) \(statusText)",
            "Content-Length: \(response.body.count)"
        ]

        for (key, value) in response.headers {
            headerLines.append("\(key): \(value)")
        }

        if close {
            headerLines.append("Connection: close")
        }

        let headerString = headerLines.joined(separator: "\r\n") + "\r\n\r\n"
        guard let headerData = headerString.data(using: .utf8) else { return }

        var fullData = Data()
        fullData.append(headerData)
        fullData.append(response.body)

        connection.send(content: fullData, completion: .contentProcessed { [weak self] error in
            if close || error != nil {
                connection.cancel()
                self?.connections.removeAll { $0 === connection }
            }
        })
    }

    private func buildResponse(statusCode: Int, body: [String: Any]) -> HttpResponse {
        let jsonData = try? JSONSerialization.data(withJSONObject: body, options: [])
        return HttpResponse(
            statusCode: statusCode,
            headers: ["Content-Type": "application/json"],
            body: jsonData ?? Data()
        )
    }

    private func httpStatusText(for code: Int) -> String {
        switch code {
        case 200: return "OK"
        case 400: return "Bad Request"
        case 404: return "Not Found"
        case 500: return "Internal Server Error"
        case 502: return "Bad Gateway"
        default: return "Unknown"
        }
    }

    private func currentLANIPv4() -> String? {
        var addresses: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&addresses) == 0, let firstAddr = addresses else {
            return nil
        }
        defer { freeifaddrs(addresses) }

        var cursor = firstAddr
        while true {
            let ifa = cursor.pointee
            let name = String(cString: ifa.ifa_name)
            if name == "en0" || name == "en1" || name.hasPrefix("wlan") {
                let addr = ifa.ifa_addr.pointee
                if addr.sa_family == UInt8(AF_INET) {
                    var host = [CChar](repeating: 0, count: Int(NI_MAXHOST))
                    if getnameinfo(ifa.ifa_addr, socklen_t(addr.sa_len), &host, socklen_t(host.count), nil, 0, NI_NUMERICHOST) == 0 {
                        let ip = String(cString: host)
                        if ip != "127.0.0.1" && !ip.isEmpty {
                            return ip
                        }
                    }
                }
            }
            if ifa.ifa_next == nil {
                break
            }
            cursor = ifa.ifa_next
        }
        return nil
    }

    private func currentInterfaces() -> [NetworkInterface] {
        var interfaces: [NetworkInterface] = []
        let monitor = NWPathMonitor()
        let semaphore = DispatchSemaphore(value: 0)

        monitor.pathUpdateHandler = { path in
            for interface in path.availableInterfaces {
                let iface = NetworkInterface(interface)
                interfaces.append(iface)
            }
            semaphore.signal()
        }

        monitor.start(queue: DispatchQueue.global())
        semaphore.wait()
        monitor.cancel()

        return interfaces
    }
}

public enum NetworkInterfaceType {
    case wifi
    case wiredEthernet
    case cellular
    case loopback
    case other
}

public struct NetworkInterface: Equatable {
    public let name: String
    public let type: NetworkInterfaceType
    public let addresses: [NetworkInterfaceAddress]

    public init(_ interface: NWInterface) {
        self.name = interface.name
        switch interface.type {
        case .wifi:
            self.type = .wifi
        case .wiredEthernet:
            self.type = .wiredEthernet
        case .cellular:
            self.type = .cellular
        case .loopback:
            self.type = .loopback
        default:
            self.type = .other
        }
        self.addresses = []
    }
}

public enum NetworkInterfaceAddress: Equatable {
    case ipv4(String)
    case ipv6(String)
}

extension SettingsManager {
    fileprivate var upstream: (url: URL, apiKey: String)? {
        let trimmedHost = host.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "http://", with: "")
            .replacingOccurrences(of: "https://", with: "")
            .trimmingCharacters(in: CharacterSet(charactersIn: "/"))

        guard !trimmedHost.isEmpty else { return nil }

        let urlString = "http://\(trimmedHost):\(port)"
        guard let url = URL(string: urlString) else { return nil }
        return (url, apiKey)
    }
}

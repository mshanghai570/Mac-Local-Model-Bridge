//
//  MacRuntimeBridgeClient.swift
//  MacLocalModelBridge
//
//  Paired iPhone client for the Mac GGUF store and loopback llama.cpp runtime.
//

import Foundation
import CryptoKit
import UIKit

public enum MacRuntimeBridgeError: LocalizedError {
    case invalidURL
    case missingPairedToken
    case invalidResponse(Int, String)
    case malformedResponse
    case invalidModelFile
    case cancelled

    public var errorDescription: String? {
        switch self {
        case .invalidURL: return "The Mac bridge URL is invalid. Select a discovered Mac or set its LAN address first."
        case .missingPairedToken: return "This Mac requires explicit pairing. Enter its pairing code in Connection before transferring a model."
        case .invalidResponse(let status, let message): return "Mac bridge returned HTTP \(status): \(message)"
        case .malformedResponse: return "Mac bridge returned an unexpected response."
        case .invalidModelFile: return "The selected file is not a readable GGUF model."
        case .cancelled: return "The model transfer was cancelled."
        }
    }
}

public struct MacStoredModel: Codable, Identifiable, Equatable {
    public let filename: String
    public let storedFilename: String?
    public let sizeBytes: Int64
    public let sha256: String
    public let metadata: [String: JSONValue]?
    public let available: Bool
    public let active: Bool

    public var id: String { sha256 }
    public var sizeFormatted: String { ByteCountFormatter.string(fromByteCount: sizeBytes, countStyle: .file) }

    enum CodingKeys: String, CodingKey {
        case filename, sha256, metadata, available, active
        case storedFilename = "stored_filename"
        case sizeBytes = "size_bytes"
    }
}

public struct MacTransfer: Codable, Identifiable, Equatable {
    public let id: String
    public let filename: String
    public let sizeBytes: Int64
    public let sha256: String
    public let bytesReceived: Int64
    public let status: String
    public let progress: Double

    enum CodingKeys: String, CodingKey {
        case id, filename, sha256, status, progress
        case sizeBytes = "size_bytes"
        case bytesReceived = "bytes_received"
    }
}

public struct MacRuntimeStatus: Codable, Equatable {
    public let runtime: String
    public let baseURL: String
    public let running: Bool
    public let pid: Int?
    public let modelSHA256: String?
    public let memoryBytes: Int64?
    public let cpuFirst: Bool?
    public let lastError: String?

    enum CodingKeys: String, CodingKey {
        case runtime, running, pid
        case baseURL = "base_url"
        case modelSHA256 = "model_sha256"
        case memoryBytes = "memory_bytes"
        case cpuFirst = "cpu_first"
        case lastError = "last_error"
    }
}

public enum JSONValue: Codable, Equatable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() { self = .null }
        else if let value = try? container.decode(Bool.self) { self = .bool(value) }
        else if let value = try? container.decode(Double.self) { self = .number(value) }
        else if let value = try? container.decode(String.self) { self = .string(value) }
        else if let value = try? container.decode([String: JSONValue].self) { self = .object(value) }
        else if let value = try? container.decode([JSONValue].self) { self = .array(value) }
        else { throw MacRuntimeBridgeError.malformedResponse }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value): try container.encode(value)
        case .number(let value): try container.encode(value)
        case .bool(let value): try container.encode(value)
        case .object(let value): try container.encode(value)
        case .array(let value): try container.encode(value)
        case .null: try container.encodeNil()
        }
    }
}

public final class MacRuntimeBridgeClient {
    private let session: URLSession
    private let settings: SettingsManager
    private let chunkBytes = 4 * 1024 * 1024
    private let maxChunkAttempts = 3
    /// GGUF hashing and final integrity verification can legitimately exceed the
    /// generic API timeout on an older iPhone, slow Wi-Fi, or large model.
    private let transferRequestTimeout: TimeInterval = 10 * 60

    public init(session: URLSession = .shared, settings: SettingsManager = .shared) {
        self.session = session
        self.settings = settings
    }

    public func pair(code: String, deviceName: String = UIDevice.current.name) async throws {
        struct PairRequest: Encodable { let code: String; let device_name: String }
        struct PairResponse: Decodable { let device_token: String }
        let response: PairResponse = try await request(
            path: "/pair/exchange",
            method: "POST",
            payload: PairRequest(code: code, device_name: deviceName),
            requiresPairing: false
        )
        settings.apiKey = response.device_token
    }

    public func listModels() async throws -> [MacStoredModel] {
        struct Response: Decodable { let models: [MacStoredModel] }
        return try await request(path: "/bridge/v1/models", response: Response.self).models
    }

    public func lookupModel(sha256: String) async throws -> MacStoredModel? {
        struct Response: Decodable { let available: Bool; let model: MacStoredModel? }
        let response: Response = try await request(path: "/bridge/v1/models/lookup?sha256=\(sha256)", response: Response.self)
        return response.available ? response.model : nil
    }

    public func select(model: MacStoredModel) async throws -> MacStoredModel {
        struct Response: Decodable { let model: MacStoredModel }
        return try await request(path: "/bridge/v1/models/\(model.sha256)/select", method: "POST", response: Response.self).model
    }

    public func runtimeStatus() async throws -> MacRuntimeStatus {
        try await request(path: "/bridge/v1/runtime", response: MacRuntimeStatus.self)
    }

    public func start(model: MacStoredModel, contextSize: Int? = nil, threads: Int? = nil) async throws -> MacRuntimeStatus {
        struct StartRequest: Encodable { let model: String; let context_size: Int?; let threads: Int? }
        return try await request(
            path: "/bridge/v1/runtime/start",
            method: "POST",
            payload: StartRequest(model: model.sha256, context_size: contextSize, threads: threads),
            response: MacRuntimeStatus.self
        )
    }

    public func stop() async throws -> MacRuntimeStatus {
        try await request(path: "/bridge/v1/runtime/stop", method: "POST", response: MacRuntimeStatus.self)
    }

    /// Streams the model from its local file handle in bounded chunks. An interrupted invocation can be retried:
    /// the Mac reports its current byte offset and the next invocation continues from that offset.
    public func upload(
        model: DeviceModel,
        progress: @escaping @Sendable (Double) async -> Void,
        transferStarted: @escaping @Sendable (String) async -> Void = { _ in },
        stage: @escaping @Sendable (String) async -> Void = { _ in }
    ) async throws -> MacStoredModel {
        let sourceURL = model.fileURL
        let attributes = try FileManager.default.attributesOfItem(atPath: sourceURL.path)
        let size = (attributes[.size] as? NSNumber)?.int64Value ?? 0
        guard size > 0 else { throw MacRuntimeBridgeError.invalidModelFile }
        await stage("Preparing local GGUF…")
        // The original path performed a full multi-gigabyte SHA-256 scan before
        // the first network request while the row displayed only 0%. Keep that
        // work off the UI actor and expose it as a distinct transfer phase.
        await stage("Hashing local GGUF…")
        let digest = try await Task.detached(priority: .utility) {
            try MacRuntimeBridgeClient.sha256(of: sourceURL)
        }.value
        await stage("Starting resumable Mac transfer…")

        struct StartRequest: Encodable { let filename: String; let size_bytes: Int64; let sha256: String }
        struct StartResponse: Decodable { let status: String; let model: MacStoredModel?; let transfer: MacTransfer? }
        let started: StartResponse = try await request(
            path: "/bridge/v1/transfers",
            method: "POST",
            payload: StartRequest(filename: model.name, size_bytes: size, sha256: digest),
            response: StartResponse.self
        )
        if let existing = started.model, started.status == "already_available" {
            await progress(1.0)
            return existing
        }
        guard var transfer = started.transfer else { throw MacRuntimeBridgeError.malformedResponse }
        await transferStarted(transfer.id)
        await stage("Uploading to Mac…")
        var offset = transfer.bytesReceived
        await progress(Double(offset) / Double(size))

        let handle = try FileHandle(forReadingFrom: sourceURL)
        defer { try? handle.close() }
        try handle.seek(toOffset: UInt64(offset))

        do {
            while offset < size {
                if Task.isCancelled {
                    _ = try? await cancel(transferID: transfer.id)
                    throw MacRuntimeBridgeError.cancelled
                }
                let expected = min(Int64(chunkBytes), size - offset)
                guard let data = try handle.read(upToCount: Int(expected)), data.count == Int(expected) else {
                    throw MacRuntimeBridgeError.invalidModelFile
                }
                transfer = try await uploadChunk(transferID: transfer.id, offset: offset, data: data)
                offset = transfer.bytesReceived
                await progress(Double(offset) / Double(size))
            }
        } catch {
            // Keep the Mac-side .part file and report its offset; retrying upload resumes rather than duplicating it.
            throw error
        }

        await stage("Verifying GGUF on Mac…")
        struct CompleteResponse: Decodable { let model: MacStoredModel }
        let completed: CompleteResponse = try await request(
            path: "/bridge/v1/transfers/\(transfer.id)/complete",
            method: "POST",
            response: CompleteResponse.self,
            timeout: transferRequestTimeout
        )
        await progress(1.0)
        return completed.model
    }

    public func cancel(transferID: String) async throws -> MacTransfer {
        try await request(path: "/bridge/v1/transfers/\(transferID)/cancel", method: "POST", response: MacTransfer.self)
    }

    private func uploadChunk(transferID: String, offset: Int64, data: Data) async throws -> MacTransfer {
        var lastError: Error = MacRuntimeBridgeError.malformedResponse
        for attempt in 0..<maxChunkAttempts {
            do {
                let request = try makeRequest(path: "/bridge/v1/transfers/\(transferID)/chunk", method: "PUT", requiresPairing: true)
                var mutable = request
                mutable.timeoutInterval = transferRequestTimeout
                mutable.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
                mutable.setValue(String(offset), forHTTPHeaderField: "X-Upload-Offset")
                let (responseData, response) = try await session.upload(for: mutable, from: data)
                try validate(response: response, data: responseData)
                return try JSONDecoder().decode(MacTransfer.self, from: responseData)
            } catch {
                lastError = error
                if attempt + 1 < maxChunkAttempts {
                    try await Task.sleep(nanoseconds: UInt64(250_000_000 * (1 << attempt)))
                }
            }
        }
        throw lastError
    }

    private static func sha256(of fileURL: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: fileURL)
        defer { try? handle.close() }
        var hasher = SHA256()
        while true {
            guard let chunk = try handle.read(upToCount: chunkBytes), !chunk.isEmpty else { break }
            hasher.update(data: chunk)
        }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }

    private func request<Response: Decodable>(path: String, method: String = "GET", response: Response.Type, timeout: TimeInterval = 60) async throws -> Response {
        try await request(path: path, method: method, payload: Optional<String>.none, response: response, timeout: timeout)
    }

    private func request<Payload: Encodable, Response: Decodable>(
        path: String,
        method: String,
        payload: Payload,
        response: Response.Type,
        timeout: TimeInterval = 60
    ) async throws -> Response {
        try await request(path: path, method: method, payload: payload, requiresPairing: true, timeout: timeout)
    }

    private func request<Payload: Encodable, Response: Decodable>(
        path: String,
        method: String,
        payload: Payload,
        requiresPairing: Bool = true,
        timeout: TimeInterval = 60
    ) async throws -> Response {
        var request = try makeRequest(path: path, method: method, requiresPairing: requiresPairing)
        request.timeoutInterval = timeout
        request.httpBody = try JSONEncoder().encode(payload)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        do { return try JSONDecoder().decode(Response.self, from: data) }
        catch { throw MacRuntimeBridgeError.malformedResponse }
    }

    private func makeRequest(path: String, method: String, requiresPairing: Bool) throws -> URLRequest {
        guard let url = URL(string: settings.baseUrlString + path), !settings.baseUrlString.isEmpty else {
            throw MacRuntimeBridgeError.invalidURL
        }
        if requiresPairing && settings.apiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            throw MacRuntimeBridgeError.missingPairedToken
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 60
        if !settings.apiKey.isEmpty {
            request.setValue("Bearer \(settings.apiKey)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    private func validate(response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else { throw MacRuntimeBridgeError.malformedResponse }
        guard (200..<300).contains(http.statusCode) else {
            throw MacRuntimeBridgeError.invalidResponse(http.statusCode, String(data: data, encoding: .utf8) ?? "Unknown error")
        }
    }
}

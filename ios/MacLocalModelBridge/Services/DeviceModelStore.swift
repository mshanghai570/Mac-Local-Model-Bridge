//
//  DeviceModelStore.swift
//  MacLocalModelBridge
//

import Foundation
import OSLog

public extension Notification.Name {
    static let localModelImported = Notification.Name("com.localai.localModelImported")
    static let localModelImportFailed = Notification.Name("com.localai.localModelImportFailed")
}

public enum DeviceModelError: LocalizedError {
    case unsupportedFile(String)
    case importFailed(String)
    case corruptImport(name: String, presentBytes: Int64, requiredBytes: Int64)

    public var errorDescription: String? {
        switch self {
        case .unsupportedFile(let name):
            return "Unsupported file type: \(name). Only .gguf model files can be loaded on-device."
        case .importFailed(let msg):
            return "Failed to import model: \(msg)"
        case .corruptImport(let name, let present, let required):
            let p = ByteCountFormatter.string(fromByteCount: present, countStyle: .file)
            let r = ByteCountFormatter.string(fromByteCount: required, countStyle: .file)
            return "\(name) is incomplete: \(p) present but \(r) required. The file was not copied/downloaded fully. If it came from iCloud, wait until it finishes downloading, then try again. If downloaded in Safari, re-download it."
        }
    }
}

public struct DeviceModel: Identifiable, Equatable {
    public let id: String
    public let name: String
    public let fileURL: URL
    public let sizeBytes: Int64

    public var sizeFormatted: String {
        ByteCountFormatter.string(fromByteCount: sizeBytes, countStyle: .file)
    }
}

public final class DeviceModelStore: @unchecked Sendable {
    public static let shared = DeviceModelStore()

    private let logger = Logger(subsystem: "com.localai.MacLocalModelBridge", category: "DeviceModelStore")

    var documentsDirectory: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    }

    private var legacyModelsDirectory: URL {
        documentsDirectory.appendingPathComponent("Models", isDirectory: true)
    }

    private let importQueue = DispatchQueue(label: "com.localai.modelstore.import")

    private init() {
        try? FileManager.default.createDirectory(at: legacyModelsDirectory, withIntermediateDirectories: true)
    }

    // MARK: - Import

    @discardableResult
    public func importModel(from sourceURL: URL) async throws -> DeviceModel {
        try await withCheckedThrowingContinuation { continuation in
            importQueue.async {
                do {
                    let model = try self.importModelSync(from: sourceURL)
                    continuation.resume(returning: model)
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    /// Synchronous copy used by the `onOpenURL` path. Must run while the
    /// security-scoped extension handed to us at open time is still fresh, so
    /// the file is captured before any queue hop. Validation happens later via
    /// `completeImport`.
    public func stageImport(from sourceURL: URL) throws -> URL {
        let fileName = sourceURL.lastPathComponent
        guard fileName.lowercased().hasSuffix(".gguf") else {
            throw DeviceModelError.unsupportedFile(fileName)
        }

        let securityScoped = sourceURL.startAccessingSecurityScopedResource()
        defer {
            if securityScoped { sourceURL.stopAccessingSecurityScopedResource() }
        }

        waitForDownloadIfNeeded(sourceURL)

        let destinationURL = destinationURL(for: fileName)
        logger.debug("Staging import: source=\(sourceURL.path), destination=\(destinationURL.path)")
        guard FileManager.default.fileExists(atPath: sourceURL.path) else {
            throw DeviceModelError.importFailed(
                "Source file not found at \(sourceURL.path). The file may not have finished downloading, or was moved/deleted before the copy could complete. (source: \(sourceURL.lastPathComponent))"
            )
        }
        do {
            try FileManager.default.copyItem(at: sourceURL, to: destinationURL)
        } catch {
            throw DeviceModelError.importFailed(
                "\(error.localizedDescription) (source: \(sourceURL.lastPathComponent), destination: \(destinationURL.lastPathComponent))"
            )
        }
        return destinationURL
    }

    /// Validates and registers a file that was staged with `stageImport`.
    @discardableResult
    public func completeImport(at stagedURL: URL) async throws -> DeviceModel {
        try await withCheckedThrowingContinuation { continuation in
            importQueue.async {
                do {
                    let model = try self.completeImportSync(at: stagedURL)
                    continuation.resume(returning: model)
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    private func completeImportSync(at finalURL: URL) throws -> DeviceModel {
        let fileManager = FileManager.default
        do {
            let report = try GGUFValidator.validate(url: finalURL)
            guard report.isComplete else {
                try? fileManager.removeItem(at: finalURL)
                throw DeviceModelError.corruptImport(
                    name: finalURL.lastPathComponent,
                    presentBytes: report.presentBytes,
                    requiredBytes: report.requiredBytes
                )
            }
        } catch let error as DeviceModelError {
            throw error
        } catch {
            try? fileManager.removeItem(at: finalURL)
            throw DeviceModelError.importFailed(error.localizedDescription)
        }

        return DeviceModel(
            id: finalURL.lastPathComponent,
            name: finalURL.lastPathComponent,
            fileURL: finalURL,
            sizeBytes: fileSize(of: finalURL)
        )
    }

    private func importModelSync(from sourceURL: URL) throws -> DeviceModel {
        let fileName = sourceURL.lastPathComponent
        guard fileName.lowercased().hasSuffix(".gguf") else {
            throw DeviceModelError.unsupportedFile(fileName)
        }

        let securityScoped = sourceURL.startAccessingSecurityScopedResource()
        defer {
            if securityScoped { sourceURL.stopAccessingSecurityScopedResource() }
        }

        let fileManager = FileManager.default
        let destinationURL = destinationURL(for: fileName)

        if fileManager.fileExists(atPath: destinationURL.path)
            && fileManager.fileExists(atPath: sourceURL.path)
            && destinationURL.standardizedFileURL.path == sourceURL.standardizedFileURL.path {
            return DeviceModel(
                id: fileName,
                name: fileName,
                fileURL: destinationURL,
                sizeBytes: fileSize(of: destinationURL)
            )
        }

        waitForDownloadIfNeeded(sourceURL)

        guard fileManager.fileExists(atPath: sourceURL.path) else {
            throw DeviceModelError.importFailed(
                "Source file not found at \(sourceURL.path). The file may not have finished downloading, or was moved/deleted before the copy could complete. (source: \(sourceURL.lastPathComponent))"
            )
        }

        logger.debug("Importing model: source=\(sourceURL.path), destination=\(destinationURL.path), isInsideContainer=\(self.isInsideOurContainer(sourceURL))")

        do {
            if isInsideOurContainer(sourceURL) {
                // System picker's asCopy already staged a private copy in our
                // container (tmp/Inbox). Consume it with an instant rename.
                // moveItem requires write access to the source; if that fails
                // (e.g. read-only volume or unexpected sandbox boundary), fall
                // back to copyItem which only needs read access.
                do {
                    try fileManager.moveItem(at: sourceURL, to: destinationURL)
                } catch {
                    logger.debug("moveItem failed for \(sourceURL.lastPathComponent), falling back to copyItem")
                    try fileManager.copyItem(at: sourceURL, to: destinationURL)
                }
            } else {
                // Files.app / LocalSend / iCloud: never move the user's file out
                // of its original location - copy it.
                try fileManager.copyItem(at: sourceURL, to: destinationURL)
            }
        } catch {
            throw DeviceModelError.importFailed(
                "\(error.localizedDescription) (source: \(sourceURL.lastPathComponent), destination: \(destinationURL.lastPathComponent))"
            )
        }

        return try completeImportSync(at: destinationURL)
    }

    func destinationURL(for fileName: String) -> URL {
        let baseDestination = documentsDirectory.appendingPathComponent(fileName)
        guard FileManager.default.fileExists(atPath: baseDestination.path) else {
            return baseDestination
        }
        let baseName = (fileName as NSString).deletingPathExtension
        let ext = (fileName as NSString).pathExtension
        var counter = 1
        while true {
            let candidate = documentsDirectory.appendingPathComponent("\(baseName) (\(counter)).\(ext)")
            if !FileManager.default.fileExists(atPath: candidate.path) { return candidate }
            counter += 1
        }
    }

    func isInsideOurContainer(_ url: URL) -> Bool {
        let resolved = url.resolvingSymlinksInPath().path
        let doc = documentsDirectory.resolvingSymlinksInPath().path
        let tmp = FileManager.default.temporaryDirectory.resolvingSymlinksInPath().path
        // Append a path separator so that "DocumentsBackup" cannot falsely
        // match "Documents" — the comparison must respect directory boundaries.
        return resolved.hasPrefix(doc + "/") || resolved.hasPrefix(tmp + "/")
    }

    private func waitForDownloadIfNeeded(_ url: URL) {
        let fileManager = FileManager.default
        guard fileManager.isUbiquitousItem(at: url) else { return }
        let status = (try? url.resourceValues(forKeys: [.ubiquitousItemDownloadingStatusKey])
            .ubiquitousItemDownloadingStatus) ?? .current
        guard status != .current else { return }
        try? fileManager.startDownloadingUbiquitousItem(at: url)
        let deadline = Date().addingTimeInterval(90)
        while Date() < deadline {
            if fileManager.fileExists(atPath: url.path) {
                let now = (try? url.resourceValues(forKeys: [.ubiquitousItemDownloadingStatusKey])
                    .ubiquitousItemDownloadingStatus) ?? .current
                if now == .current { return }
            }
            Thread.sleep(forTimeInterval: 2)
        }
    }

    // MARK: - Listing / Deletion

    public func installedModels() -> [DeviceModel] {
        var urls: [URL] = []
        if let entries = try? FileManager.default.contentsOfDirectory(
            at: documentsDirectory,
            includingPropertiesForKeys: [.isRegularFileKey],
            options: [.skipsHiddenFiles]
        ) {
            urls.append(contentsOf: entries)
        }
        if let entries = try? FileManager.default.contentsOfDirectory(
            at: legacyModelsDirectory,
            includingPropertiesForKeys: [.isRegularFileKey],
            options: [.skipsHiddenFiles]
        ) {
            urls.append(contentsOf: entries)
        }

        var seen = Set<String>()
        return urls.compactMap { url -> DeviceModel? in
            guard url.pathExtension.lowercased() == "gguf" else { return nil }
            let name = url.lastPathComponent
            guard seen.insert(name).inserted else { return nil }
            return DeviceModel(id: name, name: name, fileURL: url, sizeBytes: fileSize(of: url))
        }
        .sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }

    public func url(for name: String) -> URL? {
        let root = documentsDirectory.appendingPathComponent(name)
        if FileManager.default.fileExists(atPath: root.path) { return root }
        let legacy = legacyModelsDirectory.appendingPathComponent(name)
        if FileManager.default.fileExists(atPath: legacy.path) { return legacy }
        return nil
    }

    public func deleteModel(named name: String) throws {
        if let url = url(for: name) {
            try FileManager.default.removeItem(at: url)
        }
    }

    private func fileSize(of url: URL) -> Int64 {
        (try? FileManager.default.attributesOfItem(atPath: url.path)[.size] as? NSNumber)?.int64Value ?? 0
    }
}

// MARK: - GGUF integrity validation

/// Walks the GGUF header (magic, metadata, tensor info) and computes the minimum
/// byte size a complete model must have, then compares it against the actual file
/// size. Detects truncated/corrupt imports before llama.cpp ever sees them.
enum GGUFValidator {
    struct Report {
        let presentBytes: Int64
        let requiredBytes: Int64
        var isComplete: Bool { requiredBytes <= presentBytes }
    }

    private static let typeLayout: [(size: Int64, block: Int64)] = [
        (4, 1), (2, 1), (18, 32), (20, 32), (16, 32), (18, 32), (22, 32), (24, 32),
        (34, 32), (36, 32), (20, 256), (44, 256), (144, 256), (176, 256), (212, 256), (292, 256),
        (18, 256), (22, 256), (28, 256), (18, 256), (34, 32), (34, 256), (22, 256), (34, 256),
        (1, 1), (2, 1), (4, 1), (8, 1), (8, 1), (22, 256), (36, 32), (72, 32), (136, 32)
    ]

    static func validate(url: URL) throws -> Report {
        let data = try Data(contentsOf: url, options: .mappedIfSafe)
        let presentBytes = Int64(data.count)

        var offset = 0
        func u32() throws -> UInt32 {
            guard offset + 4 <= data.count else { throw DeviceModelError.importFailed("GGUF header truncated.") }
            defer { offset += 4 }
            return data.subdata(in: offset..<offset + 4).withUnsafeBytes { $0.loadUnaligned(as: UInt32.self) }
        }
        func u64() throws -> UInt64 {
            guard offset + 8 <= data.count else { throw DeviceModelError.importFailed("GGUF header truncated.") }
            defer { offset += 8 }
            return data.subdata(in: offset..<offset + 8).withUnsafeBytes { $0.loadUnaligned(as: UInt64.self) }
        }
        func string() throws -> String {
            let length = Int(try u64())
            guard offset + length <= data.count else { throw DeviceModelError.importFailed("GGUF header truncated.") }
            let value = String(data: data.subdata(in: offset..<offset + length), encoding: .utf8) ?? ""
            offset += length
            return value
        }
        func skipValue(_ type: UInt32) throws {
            switch type {
            case 0, 1, 7: offset += 1
            case 2, 3: offset += 2
            case 4, 5, 6: offset += 4
            case 8: _ = try string()
            case 9:
                let elementType = try u32()
                let count = try u64()
                for _ in 0..<count {
                    if elementType == 8 { _ = try string() } else { try skipValue(elementType) }
                }
            case 10, 11, 12: offset += 8
            default: offset += 4
            }
        }

        let magic = try u32()
        guard magic == 0x46554747 else { // "GGUF"
            throw DeviceModelError.importFailed("Not a GGUF file (bad magic).")
        }
        _ = try u32() // version
        let tensorCount = try u64()
        let metadataCount = try u64()
        for _ in 0..<metadataCount {
            _ = try string()
            try skipValue(try u32())
        }

        var requiredBytes: Int64 = 0
        for _ in 0..<tensorCount {
            _ = try string()
            let dimensions = try u32()
            var elements: Int64 = 1
            for _ in 0..<dimensions {
                elements *= Int64(try u64())
            }
            let typeIndex = Int(try u32())
            let tensorOffset = Int64(try u64())
            guard typeIndex < typeLayout.count else {
                throw DeviceModelError.importFailed("Unsupported GGUF tensor type \(typeIndex).")
            }
            let (size, block) = typeLayout[typeIndex]
            let blocks = (elements + block - 1) / block
            requiredBytes = max(requiredBytes, tensorOffset + size * blocks)
        }

        return Report(presentBytes: presentBytes, requiredBytes: requiredBytes)
    }
}

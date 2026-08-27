//
//  ChatViewModel.swift
//  MacLocalModelBridge
//

import Foundation
import SwiftUI
import Combine

public enum ChatSource: String, CaseIterable, Identifiable {
    case mac = "MAC"
    case device = "ON-DEVICE"

    public var id: String { rawValue }
}

@MainActor
public class ChatViewModel: ObservableObject {
    @Published public var messages: [ChatMessage] = []
    @Published public var inputPrompt: String = ""
    @Published public var isGenerating: Bool = false
    @Published public var errorMessage: String? = nil
    @Published public var activeModel: String = "llama3.2:3b"

    // On-device source
    @Published public var source: ChatSource = .mac
    @Published public var deviceModels: [DeviceModel] = []
    @Published public var selectedDeviceModel: DeviceModel? = nil
    @Published public var isDeviceModelLoading: Bool = false
    @Published public var loadedDeviceModelInfo: DeviceModelInfo? = nil

    // Live Streaming Telemetry
    @Published public var liveTokensPerSecond: Double = 0.0
    @Published public var liveTimeToFirstTokenMs: Double = 0.0
    @Published public var liveTokenCount: Int = 0

    private let client: BridgeClient
    private var streamTask: Task<Void, Never>?

    /// Splits on-device generation output into answer vs. <think> channels.
    /// Nil for MAC-source requests (server output has no local think tags).
    private var reasoningParser: ReasoningStreamParser? = nil

    /// Token budget for on-device generation. Reasoning models spend hundreds
    /// to thousands of tokens inside <think>…</think> BEFORE the visible
    /// answer starts, so they need a much larger total budget; the default of
    /// 512 otherwise guillotines the answer mid-word once thinking exhausts it.
    public static let deviceMaxTokensDefault = 512
    public static let deviceMaxTokensReasoning = 4096

    public var deviceMaxTokens: Int {
        LocalInferenceEngine.shared.activeModelUsesReasoning
            ? ChatViewModel.deviceMaxTokensReasoning
            : ChatViewModel.deviceMaxTokensDefault
    }

    public init(client: BridgeClient = BridgeClient()) {
        self.client = client
        self.activeModel = SettingsManager.shared.defaultModel
        self.refreshDeviceModels()

        // Preload sample welcome message
        self.messages.append(
            ChatMessage(
                role: .assistant,
                content: "🍏 **Mac Local Model Bridge ready.** Open **Settings** and enter your Mac's LAN IP address, or wait for Bonjour auto-discovery. Tap **PING BUS** to verify the connection, then send a prompt to stream tokens over LAN.\n\nYou can also run models **fully on-device**: import a `.gguf` file in the **Models** tab, then switch the source to **ON-DEVICE**."
            )
        )
    }

    // MARK: - Sending

    public func sendMessage() {
        let trimmed = inputPrompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !isGenerating else { return }

        let userMsg = ChatMessage(role: .user, content: trimmed)
        messages.append(userMsg)
        inputPrompt = ""
        errorMessage = nil

        let assistantId = UUID()
        let assistantMsg = ChatMessage(
            id: assistantId,
            role: .assistant,
            content: "",
            isStreaming: true
        )
        messages.append(assistantMsg)
        isGenerating = true
        liveTokenCount = 0
        liveTokensPerSecond = 0.0
        liveTimeToFirstTokenMs = 0.0

        if source == .device {
            sendDeviceMessage(assistantId: assistantId)
        } else {
            sendMacMessage(assistantId: assistantId)
        }
    }

    private func sendMacMessage(assistantId: UUID) {
        let settings = SettingsManager.shared
        let startTime = CFAbsoluteTimeGetCurrent()
        var firstTokenTime: CFTimeInterval? = nil
        var tokenCount = 0

        let tools = Self.defaultTools()

        streamTask = Task {
            do {
                let stream = client.streamChat(
                    messages: messages.filter { $0.id != assistantId },
                    model: activeModel,
                    temperature: settings.temperature,
                    system: settings.systemPrompt,
                    tools: tools
                )

                var accumulatedToolCalls: [OpenAIToolCall] = []

                for try await chunk in stream {
                    if let content = chunk.content, !content.isEmpty {
                        self.accumulateToken(
                            content,
                            startTime: startTime,
                            firstTokenTime: &firstTokenTime,
                            tokenCount: &tokenCount,
                            assistantId: assistantId
                        )
                    }

                    if let toolCalls = chunk.toolCalls, !toolCalls.isEmpty {
                        accumulatedToolCalls.append(contentsOf: toolCalls)
                    }

                    if let done = chunk.done, done {
                        break
                    }
                }

                if !accumulatedToolCalls.isEmpty,
                   let idx = self.messages.firstIndex(where: { $0.id == assistantId }) {
                    self.messages[idx].toolCalls = accumulatedToolCalls
                }

                if let idx = self.messages.firstIndex(where: { $0.id == assistantId }) {
                    self.messages[idx].isStreaming = false
                }
            } catch {
                self.handleGenerationError(error, assistantId: assistantId)
            }

            self.isGenerating = false
            self.streamTask = nil
        }
    }

    public static func defaultTools() -> [OpenAIToolDefinition] {
        return [
            OpenAIToolDefinition(
                function: OpenAIFunction(
                    name: "read_file",
                    description: "Read the full text contents of a file at the given absolute path.",
                    parameters: [
                        "type": "object",
                        "properties": [
                            "path": [
                                "type": "string",
                                "description": "Absolute path to the file to read"
                            ]
                        ],
                        "required": ["path"]
                    ]
                )
            ),
            OpenAIToolDefinition(
                function: OpenAIFunction(
                    name: "list_directory",
                    description: "List files and subdirectories inside a directory at the given absolute path.",
                    parameters: [
                        "type": "object",
                        "properties": [
                            "path": [
                                "type": "string",
                                "description": "Absolute path to the directory to list"
                            ]
                        ],
                        "required": ["path"]
                    ]
                )
            )
        ]
    }

    private func sendDeviceMessage(assistantId: UUID) {
        guard let selected = selectedDeviceModel,
              let url = DeviceModelStore.shared.url(for: selected.name) else {
            if let idx = self.messages.firstIndex(where: { $0.id == assistantId }) {
                self.messages[idx].isStreaming = false
                self.messages[idx].content = "⚠️ *[No on-device model loaded. Import a `.gguf` file in the Models tab, then select it.]*"
            }
            self.isGenerating = false
            return
        }

        let settings = SettingsManager.shared
        let startTime = CFAbsoluteTimeGetCurrent()
        var firstTokenTime: CFTimeInterval? = nil
        var tokenCount = 0

        streamTask = Task {
            do {
                if !LocalInferenceEngine.shared.isLoaded
                    || LocalInferenceEngine.shared.loadedModelInfo?.name != selected.name {
                    self.isDeviceModelLoading = true
                    defer { self.isDeviceModelLoading = false }
                    let info = try await LocalInferenceEngine.shared.loadModel(at: url.path)
                    self.loadedDeviceModelInfo = info
                }

                self.reasoningParser = ReasoningStreamParser(
                    startsInsideThink: LocalInferenceEngine.shared.generationStartsInsideThink
                )

                let stream = LocalInferenceEngine.shared.generate(
                    messages: self.messages.filter { $0.id != assistantId },
                    system: settings.systemPrompt,
                    temperature: settings.temperature,
                    maxTokens: self.deviceMaxTokens
                )

                for try await token in stream {
                    if Task.isCancelled { break }
                    self.accumulateToken(
                        token,
                        startTime: startTime,
                        firstTokenTime: &firstTokenTime,
                        tokenCount: &tokenCount,
                        assistantId: assistantId
                    )
                }

                self.drainReasoningParser(assistantId: assistantId)
                self.normalizeStrayThinkCloser(assistantId: assistantId)

                if let idx = self.messages.firstIndex(where: { $0.id == assistantId }) {
                    self.messages[idx].isStreaming = false
                }
            } catch {
                self.drainReasoningParser(assistantId: assistantId)
                self.normalizeStrayThinkCloser(assistantId: assistantId)
                self.handleGenerationError(error, assistantId: assistantId)
            }

            self.isGenerating = false
            self.streamTask = nil
            self.reasoningParser = nil
        }
    }

    /// Flush any text the reasoning parser still holds back (a trailing
    /// partial tag or an unclosed <think> block) into the message fields.
    private func drainReasoningParser(assistantId: UUID) {
        guard var parser = reasoningParser else { return }
        applySegments(parser.finish(), assistantId: assistantId)
    }

    /// Some samples emit a closing </think> without ever opening a block
    /// (observed with DeepSeek-R1 distills). The streaming parser correctly
    /// passes that through as answer text; once the stream is done we
    /// reclassify: everything before the stray closer moves to the reasoning
    /// field so the bubble shows only the real answer.
    private func normalizeStrayThinkCloser(assistantId: UUID) {
        guard let idx = messages.firstIndex(where: { $0.id == assistantId }) else { return }
        guard let range = messages[idx].content.range(of: "</think>", options: .literal) else { return }

        let prefix = String(messages[idx].content[..<range.lowerBound])
        let remainder = String(messages[idx].content[range.upperBound...]).trimmingCharacters(in: .whitespacesAndNewlines)

        let existingReasoning = messages[idx].reasoningContent ?? ""
        messages[idx].reasoningContent = (existingReasoning + prefix).trimmingCharacters(in: .whitespacesAndNewlines)
        messages[idx].content = remainder
    }

    private func applySegments(
        _ segments: [ReasoningStreamParser.Segment],
        assistantId: UUID
    ) {
        guard !segments.isEmpty else { return }
        guard let idx = messages.firstIndex(where: { $0.id == assistantId }) else { return }
        for segment in segments {
            switch segment.channel {
            case .reasoning:
                if messages[idx].reasoningContent == nil { messages[idx].reasoningContent = "" }
                messages[idx].reasoningContent! += segment.text
                // Learned at runtime: this model reasons out loud, so future
                // requests get the larger thinking budget even if its chat
                // template didn't advertise it.
                LocalInferenceEngine.shared.noteReasoningOutputObserved()
            case .answer:
                messages[idx].content += segment.text
            }
        }
        messages[idx].tokensPerSecond = self.liveTokensPerSecond
        messages[idx].timeToFirstTokenMs = self.liveTimeToFirstTokenMs
        messages[idx].totalTokens = self.liveTokenCount
    }

    private func accumulateToken(
        _ token: String,
        startTime: CFTimeInterval,
        firstTokenTime: inout CFTimeInterval?,
        tokenCount: inout Int,
        assistantId: UUID
    ) {
        if firstTokenTime == nil {
            firstTokenTime = CFAbsoluteTimeGetCurrent()
            let ttft = (firstTokenTime! - startTime) * 1000.0
            self.liveTimeToFirstTokenMs = Double(round(ttft))
        }

        tokenCount += 1
        let elapsed = CFAbsoluteTimeGetCurrent() - startTime
        let tps = elapsed > 0 ? Double(tokenCount) / elapsed : 0.0
        self.liveTokensPerSecond = Double(round(tps * 10) / 10)
        self.liveTokenCount = tokenCount

        // Route through the reasoning parser when one is active (on-device
        // generation); otherwise append directly (MAC source).
        if reasoningParser != nil {
            var parser = reasoningParser!
            let segments = parser.consume(token)
            reasoningParser = parser
            applySegments(segments, assistantId: assistantId)
        } else {
            applySegments([(channel: .answer, text: token)], assistantId: assistantId)
        }
    }

    private func handleGenerationError(_ error: Error, assistantId: UUID) {
        if let idx = self.messages.firstIndex(where: { $0.id == assistantId }) {
            self.messages[idx].isStreaming = false
            if self.messages[idx].content.isEmpty {
                if (error as? InferenceError) == .cancelled {
                    self.messages[idx].content = "*[Stream cancelled]*"
                } else {
                    self.messages[idx].content = "⚠️ *[Error: \(error.localizedDescription)]*"
                }
            }
        }
        self.errorMessage = error.localizedDescription
    }

    // MARK: - Stop / Clear

    public func stopGeneration() {
        streamTask?.cancel()
        streamTask = nil
        LocalInferenceEngine.shared.stop()
        isGenerating = false

        if let lastIdx = messages.indices.last, messages[lastIdx].role == .assistant {
            messages[lastIdx].isStreaming = false
            if !messages[lastIdx].content.isEmpty {
                messages[lastIdx].content += "\n\n*[Stream cancelled]*"
            }
        }
    }

    public func clearChat() {
        messages.removeAll()
        let subject = source == .device ? (selectedDeviceModel?.name ?? "on-device model") : activeModel
        messages.append(
            ChatMessage(
                role: .assistant,
                content: "Chat cleared. Using **\(subject)**."
            )
        )
    }

    // MARK: - On-Device Model Management

    public func refreshDeviceModels() {
        deviceModels = DeviceModelStore.shared.installedModels()
        if let info = LocalInferenceEngine.shared.loadedModelInfo {
            loadedDeviceModelInfo = info
            selectedDeviceModel = deviceModels.first(where: { $0.name == info.name }) ?? deviceModels.first
        } else {
            loadedDeviceModelInfo = nil
            if let selected = selectedDeviceModel {
                selectedDeviceModel = deviceModels.first(where: { $0.id == selected.id }) ?? deviceModels.first
            } else {
                selectedDeviceModel = deviceModels.first
            }
        }
    }

    public func selectDeviceModel(_ model: DeviceModel) {
        selectedDeviceModel = model
        if LocalInferenceEngine.shared.loadedModelInfo?.name != model.name {
            loadedDeviceModelInfo = nil
        }
    }

    public func loadDeviceModel(_ model: DeviceModel) {
        guard let url = DeviceModelStore.shared.url(for: model.name) else { return }
        isDeviceModelLoading = true
        errorMessage = nil
        Task {
            do {
                let info = try await LocalInferenceEngine.shared.loadModel(at: url.path)
                self.selectedDeviceModel = model
                self.loadedDeviceModelInfo = info
            } catch {
                self.errorMessage = error.localizedDescription
            }
            self.isDeviceModelLoading = false
        }
    }

    public func deleteDeviceModel(_ model: DeviceModel) {
        if LocalInferenceEngine.shared.loadedModelInfo?.name == model.name {
            LocalInferenceEngine.shared.unloadModel()
            loadedDeviceModelInfo = nil
        }
        try? DeviceModelStore.shared.deleteModel(named: model.name)
        refreshDeviceModels()
    }
}

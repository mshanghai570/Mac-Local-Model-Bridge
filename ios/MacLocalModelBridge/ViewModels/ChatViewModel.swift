//
//  ChatViewModel.swift
//  MacLocalModelBridge
//

import Foundation
import SwiftUI
import Combine

@MainActor
public class ChatViewModel: ObservableObject {
    @Published public var messages: [ChatMessage] = []
    @Published public var inputPrompt: String = ""
    @Published public var isGenerating: Bool = false
    @Published public var errorMessage: String? = nil
    @Published public var activeModel: String = "llama3.2:3b"

    // Live Streaming Telemetry
    @Published public var liveTokensPerSecond: Double = 0.0
    @Published public var liveTimeToFirstTokenMs: Double = 0.0
    @Published public var liveTokenCount: Int = 0

    private let client: BridgeClient
    private var streamTask: Task<Void, Never>?

    public init(client: BridgeClient = BridgeClient()) {
        self.client = client
        self.activeModel = SettingsManager.shared.defaultModel

        // Preload sample welcome message
        self.messages.append(
            ChatMessage(
                role: .assistant,
                content: "🍏 **Mac Local Model Bridge Connected.** Ready to execute inference on Apple Silicon Neural Engine & Metal GPU. Send a prompt to stream tokens over LAN."
            )
        )
    }

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

        let settings = SettingsManager.shared
        let startTime = CFAbsoluteTimeGetCurrent()
        var firstTokenTime: CFAbsoluteTime? = nil
        var tokenCount = 0

        streamTask = Task {
            do {
                let stream = client.streamChat(
                    messages: messages.filter { $0.id != assistantId },
                    model: activeModel,
                    temperature: settings.temperature,
                    system: settings.systemPrompt
                )

                for try await token in stream {
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

                    if let idx = self.messages.firstIndex(where: { $0.id == assistantId }) {
                        self.messages[idx].content += token
                        self.messages[idx].tokensPerSecond = self.liveTokensPerSecond
                        self.messages[idx].timeToFirstTokenMs = self.liveTimeToFirstTokenMs
                        self.messages[idx].totalTokens = tokenCount
                    }
                }

                if let idx = self.messages.firstIndex(where: { $0.id == assistantId }) {
                    self.messages[idx].isStreaming = false
                }
            } catch {
                if let idx = self.messages.firstIndex(where: { $0.id == assistantId }) {
                    self.messages[idx].isStreaming = false
                    if self.messages[idx].content.isEmpty {
                        self.messages[idx].content = "⚠️ *[Error: \(error.localizedDescription)]*"
                    }
                }
                self.errorMessage = error.localizedDescription
            }

            self.isGenerating = false
            self.streamTask = nil
        }
    }

    public func stopGeneration() {
        streamTask?.cancel()
        streamTask = nil
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
        messages.append(
            ChatMessage(
                role: .assistant,
                content: "Chat cleared. Connected to Mac model **\(activeModel)**."
            )
        )
    }
}

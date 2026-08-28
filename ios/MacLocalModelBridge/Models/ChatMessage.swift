//
//  ChatMessage.swift
//  MacLocalModelBridge
//

import Foundation

public enum MessageRole: String, Codable {
    case user
    case assistant
    case system
}

public struct ChatMessage: Identifiable, Equatable {
    public let id: UUID
    public let role: MessageRole
    public var content: String
    public var reasoningContent: String?
    public let timestamp: Date
    public var isStreaming: Bool
    public var tokensPerSecond: Double?
    public var timeToFirstTokenMs: Double?
    public var totalTokens: Int?
    public var toolCalls: [OpenAIToolCall]?
    /// UI-only notices such as onboarding and local status must never become
    /// prior assistant turns in an inference request.
    public let includeInInferenceContext: Bool

    public init(
        id: UUID = UUID(),
        role: MessageRole,
        content: String,
        reasoningContent: String? = nil,
        timestamp: Date = Date(),
        isStreaming: Bool = false,
        tokensPerSecond: Double? = nil,
        timeToFirstTokenMs: Double? = nil,
        totalTokens: Int? = nil,
        toolCalls: [OpenAIToolCall]? = nil,
        includeInInferenceContext: Bool = true
    ) {
        self.id = id
        self.role = role
        self.content = content
        self.reasoningContent = reasoningContent
        self.timestamp = timestamp
        self.isStreaming = isStreaming
        self.tokensPerSecond = tokensPerSecond
        self.timeToFirstTokenMs = timeToFirstTokenMs
        self.totalTokens = totalTokens
        self.toolCalls = toolCalls
        self.includeInInferenceContext = includeInInferenceContext
    }
}

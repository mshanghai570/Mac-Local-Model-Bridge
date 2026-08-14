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
    public let timestamp: Date
    public var isStreaming: Bool
    public var tokensPerSecond: Double?
    public var timeToFirstTokenMs: Double?
    public var totalTokens: Int?

    public init(
        id: UUID = UUID(),
        role: MessageRole,
        content: String,
        timestamp: Date = Date(),
        isStreaming: Bool = false,
        tokensPerSecond: Double? = nil,
        timeToFirstTokenMs: Double? = nil,
        totalTokens: Int? = nil
    ) {
        self.id = id
        self.role = role
        self.content = content
        self.timestamp = timestamp
        self.isStreaming = isStreaming
        self.tokensPerSecond = tokensPerSecond
        self.timeToFirstTokenMs = timeToFirstTokenMs
        self.totalTokens = totalTokens
    }
}

//
//  MessageBubbleView.swift
//  MacLocalModelBridge
//

import SwiftUI

public struct MessageBubbleView: View {
    public let message: ChatMessage

    public var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
            if message.role == .assistant {
                Image(systemName: "cpu.fill")
                    .foregroundColor(Color.phosphorGreen)
                    .font(.system(size: 14))
                    .padding(6)
                    .background(Color.backgroundElevated)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
                    .overlay(
                        RoundedRectangle(cornerRadius: AppTheme.Radius.sm)
                            .stroke(Color.borderColor, lineWidth: 1)
                    )
            } else {
                Spacer()
            }

            VStack(alignment: message.role == .user ? .trailing : .leading, spacing: AppTheme.Spacing.xxs) {
                // Header line with role & timestamp
                HStack(spacing: AppTheme.Spacing.xs) {
                    Text(message.role == .user ? "YOU (IPHONE)" : "MAC // LOCAL GPU")
                        .font(AppTheme.Font.caption(.bold))
                        .foregroundColor(message.role == .user ? Color.electricBlue : Color.phosphorGreen)

                    if let tps = message.tokensPerSecond, tps > 0 {
                        Text("• \(String(format: "%.1f", tps)) t/s")
                            .font(AppTheme.Font.caption2(.medium))
                            .foregroundColor(Color.amber)
                    }

                    if let ttft = message.timeToFirstTokenMs, ttft > 0 {
                        Text("• TTFT: \(Int(ttft))ms")
                            .font(AppTheme.Font.caption2(.medium))
                            .foregroundColor(Color.textSecondary)
                    }
                }

                // Reasoning (💭…) block — collapsible, never silently
                // dropped. Auto-expanded while the model is thinking,
                // collapsed once the answer starts arriving.
                if let reasoning = message.reasoningContent, !reasoning.isEmpty {
                    ReasoningDisclosureView(
                        text: reasoning,
                        isActive: message.isStreaming && message.content.isEmpty
                    )
                    .padding(.bottom, AppTheme.Spacing.xs)
                }

                // Message Body
                VStack(alignment: .leading, spacing: 0) {
                    if !message.content.isEmpty {
                        Text(message.content)
                            .font(AppTheme.Font.body())
                            .foregroundColor(message.role == .user ? .textPrimary : Color.phosphorGreen)
                            .textSelection(.enabled)
                    }

                    if let toolCalls = message.toolCalls, !toolCalls.isEmpty {
                        ForEach(toolCalls) { toolCall in
                            VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
                                HStack(spacing: AppTheme.Spacing.xs) {
                                    Image(systemName: "wrench.fill")
                                        .font(.system(size: 10))
                                    Text("TOOL CALL")
                                        .font(AppTheme.Font.caption(.bold))
                                        .foregroundColor(Color.amber)
                                    Text(toolCall.function.name)
                                        .font(AppTheme.Font.caption2(.medium))
                                        .foregroundColor(.textPrimary)
                                }
                                .padding(6)
                                .background(Color.toolCallBackground)
                                .cornerRadius(AppTheme.Radius.xs)

                                Text(toolCall.function.arguments)
                                    .font(AppTheme.Font.caption2())
                                    .foregroundColor(Color.textTertiary)
                                    .textSelection(.enabled)
                                    .padding(6)
                                    .background(Color.toolCallArgBackground)
                                    .cornerRadius(AppTheme.Radius.xs)
                            }
                            .padding(.top, AppTheme.Spacing.xxs)
                        }
                    }

                    if message.isStreaming {
                        HStack(spacing: AppTheme.Spacing.xxs) {
                            Text("▋")
                                .font(.system(size: 14))
                                .foregroundColor(Color.phosphorGreen)
                                .opacity(0.4)
                            Text("")
                                .font(.system(size: 14))
                                .foregroundColor(Color.phosphorGreen)
                                .opacity(0.4)
                        }
                        .transition(.opacity)
                        .onAppear {
                            // Smooth pulse animation for the cursor
                        }
                        .animation(
                            Animation.easeInOut(duration: 0.9)
                                .repeatForever(autoreverses: true),
                            value: UUID()
                        )
                    }
                }
                .padding(AppTheme.Spacing.md)
                .background(
                    message.role == .user
                        ? Color.userBubbleBackground
                        : Color.assistantBubbleBackground
                )
                .cornerRadius(AppTheme.Radius.lg)
                .overlay(
                    RoundedRectangle(cornerRadius: AppTheme.Radius.lg)
                        .stroke(
                            message.role == .user
                                ? Color.borderStrong
                                : Color.borderColor,
                            lineWidth: 1
                        )
                )
            }

            if message.role == .user {
                Image(systemName: "iphone.gen3")
                    .foregroundColor(Color.electricBlue)
                    .font(.system(size: 14))
                    .padding(6)
                    .background(Color.backgroundElevated)
                    .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.sm))
                    .overlay(
                        RoundedRectangle(cornerRadius: AppTheme.Radius.sm)
                            .stroke(Color.borderColor, lineWidth: 1)
                    )
            } else {
                Spacer()
            }
        }
        .padding(.horizontal, AppTheme.Spacing.xs)
        .padding(.vertical, AppTheme.Spacing.xxs)
    }
}

/// Collapsible container for a model's 💭 output.
public struct ReasoningDisclosureView: View {
    public let text: String
    /// True while the model is still inside its thinking block.
    public let isActive: Bool
    @State private var isExpanded = true

    public var body: some View {
        DisclosureGroup(isExpanded: $isExpanded) {
            Text(text)
                .font(AppTheme.Font.caption2())
                .foregroundColor(Color.textDim)
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
                .padding(.top, AppTheme.Spacing.xs)
        } label: {
            HStack(spacing: AppTheme.Spacing.xs) {
                Image(systemName: isActive ? "brain.head.profile" : "brain")
                    .font(.system(size: 11))
                Text(isActive ? "THINKING…" : "REASONING")
                    .font(AppTheme.Font.caption(.bold))
                Spacer()
                Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundColor(Color.textDim)
            }
            .foregroundColor(Color.phosphorGreen.opacity(0.75))
        }
        .padding(AppTheme.Spacing.xs)
        .background(Color.reasoningBackground)
        .cornerRadius(AppTheme.Radius.sm)
        .overlay(
            RoundedRectangle(cornerRadius: AppTheme.Radius.sm)
                .stroke(Color.reasoningBorder, lineWidth: 1)
        )
        .onChange(of: isActive) { active in
            // Collapse once the answer starts; user can re-open freely.
            if !active { isExpanded = false }
        }
    }
}

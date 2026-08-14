//
//  MessageBubbleView.swift
//  MacLocalModelBridge
//

import SwiftUI

public struct MessageBubbleView: View {
    public let message: ChatMessage

    public var body: some View {
        HStack(alignment: .top, spacing: 10) {
            if message.role == .assistant {
                Image(systemName: "cpu.fill")
                    .foregroundColor(Color(red: 0.0, green: 1.0, blue: 0.25)) // #00FF41
                    .font(.system(size: 14))
                    .padding(6)
                    .background(Color(red: 0.11, green: 0.12, blue: 0.13)) // #1C1E22
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                    .overlay(
                        RoundedRectangle(cornerRadius: 6)
                            .stroke(Color(red: 0.16, green: 0.17, blue: 0.18), lineWidth: 1)
                    )
            } else {
                Spacer()
            }

            VStack(alignment: message.role == .user ? .trailing : .leading, spacing: 4) {
                // Header line with role & timestamp
                HStack(spacing: 6) {
                    Text(message.role == .user ? "YOU (IPHONE)" : "MAC // LOCAL GPU")
                        .font(.system(size: 9, weight: .bold, design: .monospaced))
                        .foregroundColor(message.role == .user ? Color.blue : Color(red: 0.0, green: 1.0, blue: 0.25))
                    
                    if let tps = message.tokensPerSecond, tps > 0 {
                        Text("• \(String(format: "%.1f", tps)) t/s")
                            .font(.system(size: 9, weight: .medium, design: .monospaced))
                            .foregroundColor(Color(red: 0.95, green: 0.49, blue: 0.15)) // #F27D26
                    }

                    if let ttft = message.timeToFirstTokenMs, ttft > 0 {
                        Text("• TTFT: \(Int(ttft))ms")
                            .font(.system(size: 9, weight: .medium, design: .monospaced))
                            .foregroundColor(Color.gray)
                    }
                }

                // Message Body
                VStack(alignment: .leading, spacing: 0) {
                    Text(message.content)
                        .font(.system(size: 14, design: .monospaced))
                        .foregroundColor(message.role == .user ? .white : Color(red: 0.0, green: 1.0, blue: 0.25))
                        .textSelection(.enabled)

                    if message.isStreaming {
                        Rectangle()
                            .fill(Color.white)
                            .frame(width: 8, height: 14)
                            .opacity(0.8)
                            .padding(.top, 2)
                    }
                }
                .padding(12)
                .background(
                    message.role == .user
                        ? Color(red: 0.11, green: 0.12, blue: 0.14)
                        : Color(red: 0.08, green: 0.09, blue: 0.10)
                )
                .cornerRadius(8)
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(
                            message.role == .user
                                ? Color(red: 0.2, green: 0.25, blue: 0.35)
                                : Color(red: 0.16, green: 0.17, blue: 0.18),
                            lineWidth: 1
                        )
                )
            }

            if message.role == .user {
                Image(systemName: "iphone.gen3")
                    .foregroundColor(.blue)
                    .font(.system(size: 14))
                    .padding(6)
                    .background(Color(red: 0.11, green: 0.12, blue: 0.13))
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                    .overlay(
                        RoundedRectangle(cornerRadius: 6)
                            .stroke(Color(red: 0.16, green: 0.17, blue: 0.18), lineWidth: 1)
                    )
            } else {
                Spacer()
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
    }
}

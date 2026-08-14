//
//  ChatView.swift
//  MacLocalModelBridge
//

import SwiftUI

public struct ChatView: View {
    @StateObject private var viewModel = ChatViewModel()
    @EnvironmentObject var settings: SettingsManager
    @FocusState private var isInputFocused: Bool

    public var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                // Top Telemetry Header
                TelemetryHeaderView(
                    activeModel: viewModel.activeModel,
                    isGenerating: viewModel.isGenerating,
                    tokensPerSecond: viewModel.liveTokensPerSecond,
                    tokenCount: viewModel.liveTokenCount
                )

                // Chat Messages Scroll List
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: 12) {
                            ForEach(viewModel.messages) { msg in
                                MessageBubbleView(message: msg)
                                    .id(msg.id)
                            }
                        }
                        .padding(.vertical, 12)
                    }
                    .onChange(of: viewModel.messages.last?.content) { _ in
                        if let lastId = viewModel.messages.last?.id {
                            withAnimation(.easeOut(duration: 0.15)) {
                                proxy.scrollTo(lastId, anchor: .bottom)
                            }
                        }
                    }
                }

                // Error Banner if present
                if let error = viewModel.errorMessage {
                    HStack {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.red)
                        Text(error)
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundColor(.white)
                        Spacer()
                    }
                    .padding(8)
                    .background(Color.red.opacity(0.2))
                    .border(Color.red, width: 1)
                }

                // Input Bar & Action Controls
                VStack(spacing: 8) {
                    HStack(spacing: 8) {
                        TextField("Send prompt to Mac GPU...", text: $viewModel.inputPrompt, axis: .vertical)
                            .font(.system(size: 13, design: .monospaced))
                            .foregroundColor(.white)
                            .padding(10)
                            .background(Color(red: 0.05, green: 0.05, blue: 0.06))
                            .cornerRadius(6)
                            .overlay(
                                RoundedRectangle(cornerRadius: 6)
                                    .stroke(Color(red: 0.16, green: 0.17, blue: 0.18), lineWidth: 1)
                            )
                            .focused($isInputFocused)
                            .disabled(viewModel.isGenerating)
                            .lineLimit(1...5)

                        if viewModel.isGenerating {
                            Button(action: {
                                viewModel.stopGeneration()
                            }) {
                                Image(systemName: "stop.fill")
                                    .foregroundColor(.white)
                                    .font(.system(size: 14, weight: .bold))
                                    .frame(width: 38, height: 38)
                                    .background(Color(red: 0.9, green: 0.2, blue: 0.2))
                                    .cornerRadius(6)
                            }
                        } else {
                            Button(action: {
                                isInputFocused = false
                                viewModel.sendMessage()
                            }) {
                                Image(systemName: "arrow.up")
                                    .foregroundColor(Color(red: 0.05, green: 0.05, blue: 0.06))
                                    .font(.system(size: 14, weight: .bold))
                                    .frame(width: 38, height: 38)
                                    .background(viewModel.inputPrompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? Color.gray : Color(red: 0.0, green: 1.0, blue: 0.25))
                                    .cornerRadius(6)
                            }
                            .disabled(viewModel.inputPrompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        }
                    }

                    // Model Selector Quick Switcher
                    HStack {
                        Menu {
                            Button("llama3.2:3b") { viewModel.activeModel = "llama3.2:3b" }
                            Button("llama3.2:1b") { viewModel.activeModel = "llama3.2:1b" }
                            Button("qwen2.5:7b") { viewModel.activeModel = "qwen2.5:7b" }
                            Button("mistral:7b") { viewModel.activeModel = "mistral:7b" }
                            Button("deepseek-r1:1.5b") { viewModel.activeModel = "deepseek-r1:1.5b" }
                            Button("phi3:mini") { viewModel.activeModel = "phi3:mini" }
                        } label: {
                            HStack(spacing: 4) {
                                Image(systemName: "cpu")
                                    .font(.system(size: 10))
                                Text(viewModel.activeModel)
                                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                                Image(systemName: "chevron.up.chevron.down")
                                    .font(.system(size: 8))
                            }
                            .foregroundColor(Color(red: 0.95, green: 0.49, blue: 0.15))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Color(red: 0.11, green: 0.12, blue: 0.13))
                            .cornerRadius(4)
                        }

                        Spacer()

                        Button(action: {
                            viewModel.clearChat()
                        }) {
                            HStack(spacing: 4) {
                                Image(systemName: "trash")
                                    .font(.system(size: 9))
                                Text("CLEAR")
                                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                            }
                            .foregroundColor(Color.gray)
                        }
                    }
                }
                .padding(12)
                .background(Color(red: 0.08, green: 0.09, blue: 0.10))
            }
            .background(Color(red: 0.05, green: 0.05, blue: 0.06).ignoresSafeArea())
            .navigationBarHidden(true)
        }
        .navigationViewStyle(StackNavigationViewStyle())
    }
}

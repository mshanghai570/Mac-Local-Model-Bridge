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
        NavigationStack {
            VStack(spacing: 0) {
                // Top Telemetry Header
                TelemetryHeaderView(
                    activeModel: viewModel.source == .device
                        ? (viewModel.loadedDeviceModelInfo?.name ?? viewModel.selectedDeviceModel?.name ?? "No on-device model")
                        : viewModel.activeModel,
                    isGenerating: viewModel.isGenerating,
                    tokensPerSecond: viewModel.liveTokensPerSecond,
                    tokenCount: viewModel.liveTokenCount
                )

                // Chat Messages Scroll List
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: AppTheme.Spacing.sm, content: {
                            ForEach(viewModel.messages) { msg in
                                MessageBubbleView(message: msg)
                                    .id(msg.id)
                                    .transition(.asymmetric(
                                        insertion: .opacity.combined(with: .move(edge: .bottom)),
                                        removal: .opacity
                                    ))
                            }
                        })
                        .padding(.vertical, AppTheme.Spacing.md)
                        .animation(AppTheme.Animation.standard, value: viewModel.messages)
                    }
                    .onTapGesture {
                        isInputFocused = false
                    }
                    .onChange(of: viewModel.messages.last?.content) { _ in
                        guard let lastId = viewModel.messages.last?.id else { return }
                        // Defer scrollTo to the next run-loop tick so the ForEach
                        // has a chance to render the new MessageBubbleView before we
                        // try to scroll to it.  On iOS 16+ calling scrollTo for an
                        // as-yet-unrendered view ID triggers an EXC_BAD_ACCESS crash.
                        DispatchQueue.main.async {
                            withAnimation(AppTheme.Animation.standard) {
                                proxy.scrollTo(lastId, anchor: .bottom)
                            }
                        }
                    }
                }

                // Error Banner if present
                if let error = viewModel.errorMessage {
                    HStack(spacing: AppTheme.Spacing.xs) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.errorRed)
                        Text(error)
                            .font(AppTheme.Font.caption2())
                            .foregroundColor(.textPrimary)
                        Spacer()
                        Button(action: {
                            withAnimation(AppTheme.Animation.fast) {
                                viewModel.errorMessage = nil
                            }
                        }) {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundColor(Color.textSecondary)
                        }
                    }
                    .padding(AppTheme.Spacing.xs)
                    .background(Color.errorRed.opacity(0.2))
                    .overlay(
                        RoundedRectangle(cornerRadius: AppTheme.Radius.sm)
                            .stroke(Color.errorRed, lineWidth: 1)
                    )
                    .cornerRadius(AppTheme.Radius.sm)
                    .padding(.horizontal, AppTheme.Spacing.lg)
                    .transition(.move(edge: .top).combined(with: .opacity))
                    .animation(AppTheme.Animation.standard, value: viewModel.errorMessage)
                }

                // Input Bar & Action Controls
                VStack(spacing: AppTheme.Spacing.xs) {
                    // Source selector: Mac bridge vs on-device
                    Picker("Source", selection: $viewModel.source) {
                        ForEach(ChatSource.allCases) { source in
                            Text(source.rawValue).tag(source)
                        }
                    }
                    .pickerStyle(.segmented)
                    .tint(Color.phosphorGreen)
                    .animation(AppTheme.Animation.standard, value: viewModel.source)

                    HStack(spacing: AppTheme.Spacing.xs) {
                        // Keyboard dismiss button (shows only while focused)
                        if isInputFocused {
                            Button(action: {
                                withAnimation(AppTheme.Animation.fast) {
                                    isInputFocused = false
                                }
                            }) {
                                Image(systemName: "keyboard.chevron.compact.down")
                                    .foregroundColor(Color.textSecondary)
                                    .font(.system(size: 16))
                                    .frame(width: 32, height: 38)
                            }
                            .transition(.opacity)
                        }

                        TextField(
                            viewModel.source == .device
                                ? "Send prompt to on-device model..."
                                : "Send prompt to Mac GPU...",
                            text: $viewModel.inputPrompt,
                            axis: .vertical
                        )
                        .font(AppTheme.Font.subheadline())
                        .foregroundColor(.textPrimary)
                        .padding(AppTheme.Spacing.sm)
                        .background(Color.backgroundElevated)
                        .cornerRadius(AppTheme.Radius.md)
                        .overlay(
                            RoundedRectangle(cornerRadius: AppTheme.Radius.md)
                                .stroke(Color.borderInput, lineWidth: 1)
                        )
                        .focused($isInputFocused)
                        .disabled(viewModel.isGenerating)
                        .lineLimit(1...5)
                        .toolbar {
                            ToolbarItemGroup(placement: .keyboard) {
                                Spacer()
                                Button("Done") {
                                    isInputFocused = false
                                }
                                .foregroundColor(Color.phosphorGreen)
                                .font(AppTheme.Font.footnote(.bold))
                            }
                        }

                        if viewModel.isGenerating {
                            Button(action: {
                                viewModel.stopGeneration()
                            }) {
                                Image(systemName: "stop.fill")
                                    .foregroundColor(.textPrimary)
                                    .font(.system(size: 14, weight: .bold))
                                    .frame(width: 38, height: 38)
                                    .background(Color.errorRed)
                                    .cornerRadius(AppTheme.Radius.md)
                            }
                            .transition(.opacity)
                        } else {
                            Button(action: {
                                isInputFocused = false
                                viewModel.sendMessage()
                            }) {
                                Image(systemName: "arrow.up")
                                    .foregroundColor(Color.backgroundPrimary)
                                    .font(.system(size: 14, weight: .bold))
                                    .frame(width: 38, height: 38)
                                    .background(
                                        Group {
                                            if viewModel.inputPrompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                                                Color.textSecondary.opacity(0.4)
                                            } else {
                                                Color.phosphorGreen
                                            }
                                        }
                                    )
                                    .cornerRadius(AppTheme.Radius.md)
                            }
                            .disabled(viewModel.inputPrompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        }
                    }
                    .animation(AppTheme.Animation.standard, value: viewModel.isGenerating)

                    // Model Selector Row
                    HStack {
                        if viewModel.source == .device {
                            deviceModelSelector
                                .transition(.asymmetric(insertion: .opacity.combined(with: .move(edge: .trailing)), removal: .opacity))
                        } else {
                            macModelSelector
                                .transition(.asymmetric(insertion: .opacity.combined(with: .move(edge: .trailing)), removal: .opacity))
                        }

                        Spacer()

                        Button(action: {
                            viewModel.clearChat()
                        }) {
                            HStack(spacing: AppTheme.Spacing.xxs) {
                                Image(systemName: "trash")
                                    .font(.system(size: 9))
                                Text("CLEAR")
                                    .font(AppTheme.Font.caption(.bold))
                            }
                            .foregroundColor(Color.textSecondary)
                        }
                    }
                    .animation(AppTheme.Animation.standard, value: viewModel.source)
                }
                .padding(AppTheme.Spacing.md)
                .background(Color.backgroundSurface)
            }
            .background(Color.backgroundPrimary.ignoresSafeArea())
            .toolbarBackground(.hidden, for: .navigationBar)
            .task {
                viewModel.refreshDeviceModels()
            }
        }
        .navigationViewStyle(StackNavigationViewStyle())
    }

    // MARK: - MAC Model Selector

    private var macModelSelector: some View {
        Menu {
            Button("llama3.2:3b") { withAnimation { viewModel.activeModel = "llama3.2:3b" } }
            Button("llama3.2:1b") { withAnimation { viewModel.activeModel = "llama3.2:1b" } }
            Button("qwen2.5:7b") { withAnimation { viewModel.activeModel = "qwen2.5:7b" } }
            Button("mistral:7b") { withAnimation { viewModel.activeModel = "mistral:7b" } }
            Button("deepseek-r1:1.5b") { withAnimation { viewModel.activeModel = "deepseek-r1:1.5b" } }
            Button("phi3:mini") { withAnimation { viewModel.activeModel = "phi3:mini" } }
        } label: {
            HStack(spacing: AppTheme.Spacing.xxs) {
                Image(systemName: "cpu")
                    .font(.system(size: 10))
                Text(viewModel.activeModel)
                    .font(AppTheme.Font.caption(.bold))
                    .lineLimit(1)
                Image(systemName: "chevron.up.chevron.down")
                    .font(.system(size: 8))
            }
            .foregroundColor(Color.amber)
            .padding(.horizontal, AppTheme.Spacing.xs)
            .padding(.vertical, 4)
            .background(Color.backgroundElevated)
            .cornerRadius(AppTheme.Radius.xs)
        }
    }

    // MARK: - Device Model Selector

    @ViewBuilder
    private var deviceModelSelector: some View {
        Group {
            if viewModel.isDeviceModelLoading {
                HStack(spacing: AppTheme.Spacing.xs) {
                    ProgressView()
                        .controlSize(.small)
                    Text("LOADING MODEL…")
                        .font(AppTheme.Font.caption(.bold))
                        .foregroundColor(Color.textSecondary)
                }
                .padding(.horizontal, AppTheme.Spacing.xs)
                .padding(.vertical, 4)
            } else {
                Menu {
                    if viewModel.deviceModels.isEmpty {
                        Button("No models — import a .gguf in Models tab") {}
                    }
                    ForEach(viewModel.deviceModels) { model in
                        Button(model.name) {
                            viewModel.selectDeviceModel(model)
                            viewModel.loadDeviceModel(model)
                        }
                    }
                } label: {
                    HStack(spacing: AppTheme.Spacing.xxs) {
                        Image(systemName: "memorychip")
                            .font(.system(size: 10))
                        Text(viewModel.loadedDeviceModelInfo?.name ?? viewModel.selectedDeviceModel?.name ?? "Import & load model")
                            .font(AppTheme.Font.caption(.bold))
                            .lineLimit(1)
                        if viewModel.loadedDeviceModelInfo != nil {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 10))
                                .foregroundColor(Color.phosphorGreen)
                        }
                        Image(systemName: "chevron.up.chevron.down")
                            .font(.system(size: 8))
                    }
                    .foregroundColor(Color.phosphorGreen)
                    .padding(.horizontal, AppTheme.Spacing.xs)
                    .padding(.vertical, 4)
                    .background(Color.backgroundElevated)
                    .cornerRadius(AppTheme.Radius.xs)
                }
            }
        }
        .animation(AppTheme.Animation.standard, value: viewModel.isDeviceModelLoading)
        .animation(AppTheme.Animation.standard, value: viewModel.loadedDeviceModelInfo?.name)
    }
}

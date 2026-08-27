//
//  McpInspectorView.swift
//  MacLocalModelBridge
//

import SwiftUI

public struct McpInspectorView: View {
    @StateObject private var viewModel = McpViewModel()
    @EnvironmentObject var settings: SettingsManager

    private let tools = ["chat", "generate", "list_models", "health", "model_info"]

    public var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Header
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("MCP PROTOCOL INSPECTOR")
                            .font(AppTheme.Font.caption(.bold))
                            .foregroundColor(.textPrimary)
                        Text("Executes tools/call over JSON-RPC 2.0 to local bridge")
                            .font(AppTheme.Font.caption2())
                            .foregroundColor(Color.textSecondary)
                    }
                    Spacer()
                    Text("MCP v1.0")
                        .font(AppTheme.Font.caption2(.bold))
                        .foregroundColor(Color.amber)
                        .padding(.horizontal, AppTheme.Spacing.xxs)
                        .padding(.vertical, 2)
                        .background(Color.amber.opacity(0.15))
                        .cornerRadius(AppTheme.Radius.xs)
                }
                .padding(AppTheme.Spacing.lg)
                .background(Color.backgroundSurface)
                .bottomSeparator()

                ScrollView {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                        // Tool Selector
                        VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                            Text("SELECT MCP TOOL")
                                .font(AppTheme.Font.caption2(.bold))
                                .foregroundColor(Color.textSecondary)

                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack(spacing: AppTheme.Spacing.xs) {
                                    ForEach(tools, id: \.self) { tool in
                                        Button(action: {
                                            withAnimation(AppTheme.Animation.standard) {
                                                viewModel.selectedTool = tool
                                            }
                                        }) {
                                            Text(tool)
                                                .font(AppTheme.Font.caption2(.bold))
                                                .foregroundColor(viewModel.selectedTool == tool
                                                    ? Color.backgroundPrimary
                                                    : Color.textPrimary)
                                                .padding(.horizontal, AppTheme.Spacing.sm)
                                                .padding(.vertical, AppTheme.Spacing.xxs)
                                                .background(viewModel.selectedTool == tool
                                                    ? Color.phosphorGreen
                                                    : Color.backgroundElevated)
                                                .cornerRadius(AppTheme.Radius.sm)
                                                .overlay(
                                                    RoundedRectangle(cornerRadius: AppTheme.Radius.sm)
                                                        .stroke(viewModel.selectedTool == tool
                                                            ? Color.phosphorGreen
                                                            : Color.borderColor, lineWidth: 1)
                                                )
                                        }
                                        .buttonStyle(.plain)
                                    }
                                }
                            }
                        }

                        // Arguments Input
                        if viewModel.selectedTool == "chat" || viewModel.selectedTool == "generate" || viewModel.selectedTool == "model_info" {
                            VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                                Text("MODEL ARGUMENT")
                                    .font(AppTheme.Font.caption2(.bold))
                                    .foregroundColor(Color.textSecondary)

                                TextField("Model", text: $viewModel.selectedModel)
                                    .font(AppTheme.Font.subheadline())
                                    .foregroundColor(.textPrimary)
                                    .padding(AppTheme.Spacing.xs)
                                    .background(Color.backgroundElevated)
                                    .cornerRadius(AppTheme.Radius.sm)
                                    .overlay(
                                        RoundedRectangle(cornerRadius: AppTheme.Radius.sm)
                                            .stroke(Color.borderInput, lineWidth: 1)
                                    )
                                    .transition(.opacity)
                            }
                        }

                        if viewModel.selectedTool == "chat" || viewModel.selectedTool == "generate" {
                            VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                                Text("PROMPT / MESSAGE ARGUMENT")
                                    .font(AppTheme.Font.caption2(.bold))
                                    .foregroundColor(Color.textSecondary)

                                TextEditor(text: $viewModel.promptArgument)
                                    .font(AppTheme.Font.subheadline())
                                    .foregroundColor(.textPrimary)
                                    .frame(minHeight: 70)
                                    .padding(AppTheme.Spacing.xs)
                                    .background(Color.backgroundElevated)
                                    .cornerRadius(AppTheme.Radius.sm)
                                    .overlay(
                                        RoundedRectangle(cornerRadius: AppTheme.Radius.sm)
                                            .stroke(Color.borderInput, lineWidth: 1)
                                    )
                            }
                        }

                        // Execute Button
                        Button(action: {
                            Task { await viewModel.executeTool() }
                        }) {
                            HStack {
                                if viewModel.isExecuting {
                                    ProgressView()
                                        .progressViewStyle(CircularProgressViewStyle(tint: Color.backgroundPrimary))
                                } else {
                                    Image(systemName: "play.fill")
                                }
                                Text(viewModel.isExecuting ? "EXECUTING RPC CALL…" : "INVOKE \(viewModel.selectedTool.uppercased())")
                                    .font(AppTheme.Font.caption2(.bold))
                            }
                            .foregroundColor(Color.backgroundPrimary)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, AppTheme.Spacing.sm)
                            .background(viewModel.isExecuting ? Color.textSecondary : Color.phosphorGreen)
                            .cornerRadius(AppTheme.Radius.md)
                        }
                        .disabled(viewModel.isExecuting)
                        .animation(AppTheme.Animation.standard, value: viewModel.isExecuting)
                        .transition(.opacity)

                        // Output Terminal Result
                        VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                            Text("MCP TOOL RESULT // CONTENT")
                                .font(AppTheme.Font.caption2(.bold))
                                .foregroundColor(Color.textSecondary)

                            ScrollView {
                                Text(viewModel.resultText.isEmpty ? "[NO EXECUTION RESULT]" : viewModel.resultText)
                                    .font(AppTheme.Font.caption2())
                                    .foregroundColor(viewModel.isError ? .errorRed : Color.phosphorGreen)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(AppTheme.Spacing.sm)
                                    .textSelection(.enabled)
                            }
                            .frame(minHeight: 140)
                            .background(Color.backgroundElevated)
                            .cornerRadius(AppTheme.Radius.md)
                            .overlay(
                                RoundedRectangle(cornerRadius: AppTheme.Radius.md)
                                    .stroke(Color.borderColor, lineWidth: 1)
                            )
                        }
                    }
                    .padding(AppTheme.Spacing.lg)
                }
            }
            .background(Color.backgroundPrimary.ignoresSafeArea())
            .toolbarBackground(.hidden, for: .navigationBar)
        }
        .navigationViewStyle(StackNavigationViewStyle())
    }
}

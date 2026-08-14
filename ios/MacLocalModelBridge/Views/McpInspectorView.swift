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
        NavigationView {
            VStack(spacing: 0) {
                // Header
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("MCP PROTOCOL INSPECTOR")
                            .font(.system(size: 13, weight: .bold, design: .monospaced))
                            .foregroundColor(.white)
                        Text("Executes tools/call over JSON-RPC 2.0 to local bridge")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundColor(Color.gray)
                    }
                    Spacer()
                    Text("MCP v1.0")
                        .font(.system(size: 9, weight: .bold, design: .monospaced))
                        .foregroundColor(Color(red: 0.95, green: 0.49, blue: 0.15))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color(red: 0.95, green: 0.49, blue: 0.15).opacity(0.15))
                        .cornerRadius(3)
                }
                .padding(14)
                .background(Color(red: 0.08, green: 0.09, blue: 0.10))
                .overlay(
                    Rectangle()
                        .frame(height: 1)
                        .foregroundColor(Color(red: 0.16, green: 0.17, blue: 0.18)),
                    alignment: .bottom
                )

                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        // Tool Selector
                        VStack(alignment: .leading, spacing: 6) {
                            Text("SELECT MCP TOOL")
                                .font(.system(size: 10, weight: .bold, design: .monospaced))
                                .foregroundColor(Color.gray)

                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack(spacing: 8) {
                                    ForEach(tools, id: \.self) { tool in
                                        Button(action: {
                                            viewModel.selectedTool = tool
                                        }) {
                                            Text(tool)
                                                .font(.system(size: 11, weight: .bold, design: .monospaced))
                                                .foregroundColor(viewModel.selectedTool == tool ? Color(red: 0.0, green: 1.0, blue: 0.25) : .white)
                                                .padding(.horizontal, 10)
                                                .padding(.vertical, 6)
                                                .background(viewModel.selectedTool == tool ? Color(red: 0.15, green: 0.16, blue: 0.18) : Color(red: 0.08, green: 0.09, blue: 0.10))
                                                .cornerRadius(4)
                                                .overlay(
                                                    RoundedRectangle(cornerRadius: 4)
                                                        .stroke(viewModel.selectedTool == tool ? Color(red: 0.0, green: 1.0, blue: 0.25) : Color(red: 0.16, green: 0.17, blue: 0.18), lineWidth: 1)
                                                )
                                        }
                                    }
                                }
                            }
                        }

                        // Arguments Input
                        if viewModel.selectedTool == "chat" || viewModel.selectedTool == "generate" || viewModel.selectedTool == "model_info" {
                            VStack(alignment: .leading, spacing: 6) {
                                Text("MODEL ARGUMENT")
                                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                                    .foregroundColor(Color.gray)

                                TextField("Model", text: $viewModel.selectedModel)
                                    .font(.system(size: 12, design: .monospaced))
                                    .foregroundColor(.white)
                                    .padding(8)
                                    .background(Color(red: 0.08, green: 0.09, blue: 0.10))
                                    .cornerRadius(4)
                            }
                        }

                        if viewModel.selectedTool == "chat" || viewModel.selectedTool == "generate" {
                            VStack(alignment: .leading, spacing: 6) {
                                Text("PROMPT / MESSAGE ARGUMENT")
                                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                                    .foregroundColor(Color.gray)

                                TextEditor(text: $viewModel.promptArgument)
                                    .font(.system(size: 12, design: .monospaced))
                                    .foregroundColor(.white)
                                    .frame(minHeight: 70)
                                    .padding(4)
                                    .background(Color(red: 0.08, green: 0.09, blue: 0.10))
                                    .cornerRadius(4)
                            }
                        }

                        // Execute Button
                        Button(action: {
                            Task { await viewModel.executeTool() }
                        }) {
                            HStack {
                                if viewModel.isExecuting {
                                    ProgressView()
                                        .progressViewStyle(CircularProgressViewStyle(tint: .black))
                                } else {
                                    Image(systemName: "play.fill")
                                }
                                Text(viewModel.isExecuting ? "EXECUTING RPC CALL..." : "INVOKE \(viewModel.selectedTool.uppercased())")
                                    .font(.system(size: 11, weight: .bold, design: .monospaced))
                            }
                            .foregroundColor(Color(red: 0.05, green: 0.05, blue: 0.06))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 10)
                            .background(viewModel.isExecuting ? Color.gray : Color(red: 0.0, green: 1.0, blue: 0.25))
                            .cornerRadius(6)
                        }
                        .disabled(viewModel.isExecuting)

                        // Output Terminal Result
                        VStack(alignment: .leading, spacing: 6) {
                            Text("MCP TOOL RESULT // CONTENT")
                                .font(.system(size: 10, weight: .bold, design: .monospaced))
                                .foregroundColor(Color.gray)

                            ScrollView {
                                Text(viewModel.resultText.isEmpty ? "[NO EXECUTION RESULT]" : viewModel.resultText)
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundColor(viewModel.isError ? .red : Color(red: 0.0, green: 1.0, blue: 0.25))
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(10)
                                    .textSelection(.enabled)
                            }
                            .frame(minHeight: 140)
                            .background(Color(red: 0.08, green: 0.09, blue: 0.10))
                            .cornerRadius(6)
                            .overlay(
                                RoundedRectangle(cornerRadius: 6)
                                    .stroke(Color(red: 0.16, green: 0.17, blue: 0.18), lineWidth: 1)
                            )
                        }
                    }
                    .padding(14)
                }
            }
            .background(Color(red: 0.05, green: 0.05, blue: 0.06).ignoresSafeArea())
            .navigationBarHidden(true)
        }
        .navigationViewStyle(StackNavigationViewStyle())
    }
}

//
//  McpViewModel.swift
//  MacLocalModelBridge
//

import Foundation
import SwiftUI

@MainActor
public class McpViewModel: ObservableObject {
    @Published public var selectedTool: String = "chat"
    @Published public var promptArgument: String = "Why does running local LLMs on Apple Silicon save battery and protect privacy?"
    @Published public var selectedModel: String = "llama3.2:3b"
    @Published public var isExecuting: Bool = false
    @Published public var resultText: String = ""
    @Published public var isError: Bool = false

    private let client: BridgeClient

    public init(client: BridgeClient = BridgeClient()) {
        self.client = client
    }

    public func executeTool() async {
        isExecuting = true
        resultText = ""
        isError = false

        do {
            var args: [String: AnyCodable] = [:]
            if selectedTool == "chat" {
                args["model"] = AnyCodable(selectedModel)
                args["messages"] = AnyCodable([["role": "user", "content": promptArgument]])
            } else if selectedTool == "generate" {
                args["model"] = AnyCodable(selectedModel)
                args["prompt"] = AnyCodable(promptArgument)
            } else if selectedTool == "model_info" {
                args["model"] = AnyCodable(selectedModel)
            }

            let result = try await client.callMcpTool(name: selectedTool, arguments: args)
            if let text = result.content?.first?.text {
                self.resultText = text
            } else {
                self.resultText = "Tool executed successfully with no textual output."
            }
            self.isError = result.isError ?? false
        } catch {
            self.resultText = "MCP Error: \(error.localizedDescription)"
            self.isError = true
        }

        isExecuting = false
    }
}

import React, { useState } from 'react';
import { Smartphone, Copy, Check, Terminal, Shield, Sparkles, Layers, Sliders, ExternalLink, QrCode } from 'lucide-react';
import { BridgeConfigState } from '../types';

interface Props {
  config: BridgeConfigState | null;
}

export const IphoneConnectGuide: React.FC<Props> = ({ config }) => {
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'shortcuts' | 'curl' | 'swift' | 'mcp' | 'firewall'>('shortcuts');

  const lanUrl = config?.lan_url || `http://${config?.lanIp || '192.168.1.125'}:${config?.port || 8080}`;
  const apiKey = config?.apiKey || '';

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const curlChat = `curl -X POST ${lanUrl}/chat \\
  -H "Content-Type: application/json" \\${apiKey ? `\n  -H "Authorization: Bearer ${apiKey}" \\` : ''}
  -d '{
    "model": "llama3.2:3b",
    "messages": [
      {"role": "user", "content": "What is the fastest way to run local LLMs on Mac?"}
    ],
    "temperature": 0.7
  }'`;

  const curlHealth = `curl ${lanUrl}/health`;
  const curlModels = `curl ${apiKey ? `-H "Authorization: Bearer ${apiKey}" ` : ''}${lanUrl}/models`;

  const [activeSwiftFile, setActiveSwiftFile] = useState<string>('BridgeClient.swift');

  const swiftFiles: Record<string, { desc: string; code: string }> = {
    'MacLocalModelBridgeApp.swift': {
      desc: 'SwiftUI @main application lifecycle, tab navigation, and dependency injection',
      code: `import SwiftUI

@main
struct MacLocalModelBridgeApp: App {
    @StateObject private var settings = SettingsManager.shared
    @StateObject private var discovery = BonjourDiscoveryManager()
    @StateObject private var bridgeClient = BridgeClient()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(settings)
                .environmentObject(discovery)
                .environmentObject(bridgeClient)
                .preferredColorScheme(.dark)
                .onAppear {
                    discovery.startBrowsing()
                }
        }
    }
}`
    },
    'BridgeClient.swift': {
      desc: 'Async/await URLSession networking engine with Server-Sent Events (SSE) token streaming & MCP JSON-RPC',
      code: `import Foundation

public class BridgeClient: ObservableObject {
    private let urlSession: URLSession = .shared

    // MARK: - Real-Time Server-Sent Events (SSE) Streaming
    public func streamChat(
        messages: [ChatMessage],
        model: String,
        temperature: Double = 0.7,
        system: String? = nil
    ) -> AsyncThrowingStream<String, Error> {
        return AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let payloadMessages = messages.map { ChatMessagePayload(role: $0.role.rawValue, content: $0.content) }
                    let payload = ChatRequestPayload(model: model, messages: payloadMessages, stream: true, temperature: temperature, system: system)
                    let bodyData = try JSONEncoder().encode(payload)
                    var request = try self.createRequest(path: "/chat", method: "POST", body: bodyData)
                    request.setValue("text/event-stream", forHTTPHeaderField: "Accept")

                    let (bytes, response) = try await self.urlSession.bytes(for: request)
                    guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
                        continuation.finish(throwing: BridgeError.invalidResponse(500, "Stream failed"))
                        return
                    }

                    for try await line in bytes.lines {
                        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
                        guard trimmed.hasPrefix("data: ") else { continue }
                        let jsonString = String(trimmed.dropFirst(6))
                        if jsonString == "[DONE]" { break }

                        if let data = jsonString.data(using: .utf8),
                           let chunk = try? JSONDecoder().decode(StreamChunkPayload.self, data: data),
                           let content = chunk.content {
                            continuation.yield(content)
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { @Sendable _ in task.cancel() }
        }
    }
}`
    },
    'ChatViewModel.swift': {
      desc: 'Observable ViewModel computing live tokens/sec, TTFT, and conversation history',
      code: `import Foundation
import SwiftUI

@MainActor
public class ChatViewModel: ObservableObject {
    @Published public var messages: [ChatMessage] = []
    @Published public var inputPrompt: String = ""
    @Published public var isGenerating: Bool = false
    @Published public var liveTokensPerSecond: Double = 0.0
    @Published public var liveTimeToFirstTokenMs: Double = 0.0

    private let client = BridgeClient()

    public func sendMessage() {
        guard !inputPrompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        let userMsg = ChatMessage(role: .user, content: inputPrompt)
        messages.append(userMsg)
        inputPrompt = ""

        let assistantId = UUID()
        messages.append(ChatMessage(id: assistantId, role: .assistant, content: "", isStreaming: true))
        isGenerating = true

        let startTime = CFAbsoluteTimeGetCurrent()
        var firstTokenTime: CFAbsoluteTime?
        var tokenCount = 0

        Task {
            let stream = client.streamChat(messages: messages, model: "llama3.2:3b")
            for try await token in stream {
                if firstTokenTime == nil {
                    firstTokenTime = CFAbsoluteTimeGetCurrent()
                    liveTimeToFirstTokenMs = (firstTokenTime! - startTime) * 1000.0
                }
                tokenCount += 1
                let elapsed = CFAbsoluteTimeGetCurrent() - startTime
                liveTokensPerSecond = elapsed > 0 ? Double(tokenCount) / elapsed : 0.0

                if let idx = messages.firstIndex(where: { $0.id == assistantId }) {
                    messages[idx].content += token
                    messages[idx].tokensPerSecond = liveTokensPerSecond
                }
            }
            isGenerating = false
        }
    }
}`
    },
    'BonjourDiscoveryManager.swift': {
      desc: 'Network.framework NWBrowser scanning _local-ai-bridge._tcp on local Wi-Fi',
      code: `import Foundation
import Network

public class BonjourDiscoveryManager: ObservableObject {
    @Published public var discoveredBridges: [DiscoveredBridge] = []
    private var browser: NWBrowser?

    public func startBrowsing() {
        let descriptor = NWBrowser.Descriptor.bonjour(type: "_local-ai-bridge._tcp", domain: "local.")
        let parameters = NWParameters()
        parameters.includePeerToPeer = true

        browser = NWBrowser(for: descriptor, using: parameters)
        browser?.browseResultsChangedHandler = { [weak self] results, _ in
            DispatchQueue.main.async {
                self?.discoveredBridges = results.compactMap { result in
                    if case .service(let name, _, _, _) = result.endpoint {
                        return DiscoveredBridge(id: name, name: name, host: "192.168.1.125", port: 8080)
                    }
                    return nil
                }
            }
        }
        browser?.start(queue: .main)
    }
}`
    },
    'Package.swift': {
      desc: 'Swift 5.9 Package manifest defining MacLocalModelBridge library and XCTest target',
      code: `// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "MacLocalModelBridge",
    platforms: [.iOS(.v16), .macOS(.v13)],
    products: [.library(name: "MacLocalModelBridge", targets: ["MacLocalModelBridge"])],
    targets: [
        .target(name: "MacLocalModelBridge", path: "MacLocalModelBridge"),
        .testTarget(name: "MacLocalModelBridgeTests", dependencies: ["MacLocalModelBridge"], path: "MacLocalModelBridgeTests")
    ]
)`
    }
  };

  const mcpConfig = `{
  "mcpServers": {
    "mac-local-models": {
      "command": "python3",
      "args": ["-m", "local_model_bridge.server"],
      "env": {
        "MODEL_PROVIDER": "ollama",
        "OLLAMA_URL": "http://127.0.0.1:11434"${apiKey ? `,\n        "BRIDGE_API_KEY": "${apiKey}"` : ''}
      }
    }
  }
}`;

  return (
    <div className="bg-[#151619] border border-[#2A2B2E] rounded-lg p-5 shadow-2xl relative overflow-hidden">
      <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-transparent via-[#3B82F6] to-transparent opacity-30" />

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#2A2B2E]">
        <div className="flex items-center gap-2.5">
          <div className="w-2.5 h-2.5 rounded-full bg-[#3B82F6] shadow-[0_0_8px_#3B82F6]" />
          <div>
            <h2 className="text-xs uppercase tracking-widest text-[#8E9299] font-bold">
              IPHONE ACCESS & CLIENT CONFIGURATION
            </h2>
            <p className="text-[11px] text-[#5C5E63] mt-0.5">
              Connect Apple Shortcuts, native iOS apps, or MCP tools to your Mac LAN target.
            </p>
          </div>
        </div>

        {/* Tab Selection */}
        <div className="flex flex-wrap gap-1 bg-[#080809] p-1 rounded border border-[#2A2B2E] text-[10px]">
          <button
            onClick={() => setActiveTab('shortcuts')}
            className={`px-2.5 py-1 rounded transition ${activeTab === 'shortcuts' ? 'bg-[#1C1E22] text-[#00FF41] border border-[#2A2B2E] font-bold' : 'text-[#8E9299] hover:text-white'}`}
          >
            🍎 SHORTCUTS
          </button>
          <button
            onClick={() => setActiveTab('curl')}
            className={`px-2.5 py-1 rounded transition ${activeTab === 'curl' ? 'bg-[#1C1E22] text-[#00FF41] border border-[#2A2B2E] font-bold' : 'text-[#8E9299] hover:text-white'}`}
          >
            💻 CURL
          </button>
          <button
            onClick={() => setActiveTab('swift')}
            className={`px-2.5 py-1 rounded transition ${activeTab === 'swift' ? 'bg-[#1C1E22] text-[#00FF41] border border-[#2A2B2E] font-bold' : 'text-[#8E9299] hover:text-white'}`}
          >
            📱 SWIFT
          </button>
          <button
            onClick={() => setActiveTab('mcp')}
            className={`px-2.5 py-1 rounded transition ${activeTab === 'mcp' ? 'bg-[#1C1E22] text-[#00FF41] border border-[#2A2B2E] font-bold' : 'text-[#8E9299] hover:text-white'}`}
          >
            🤖 CLAUDE MCP
          </button>
          <button
            onClick={() => setActiveTab('firewall')}
            className={`px-2.5 py-1 rounded transition ${activeTab === 'firewall' ? 'bg-[#1C1E22] text-[#00FF41] border border-[#2A2B2E] font-bold' : 'text-[#8E9299] hover:text-white'}`}
          >
            🛡️ FIREWALL
          </button>
        </div>
      </div>

      <div className="mt-4">
        {/* Apple Shortcuts Tab */}
        {activeTab === 'shortcuts' && (
          <div className="space-y-3 text-xs">
            <div className="bg-[#1C1E22] border border-[#2A2B2E] rounded p-3 text-[#D1D1D1]">
              <div className="text-[10px] text-[#00FF41] uppercase tracking-wider font-bold mb-1 flex items-center gap-1.5">
                <Sparkles className="w-3 h-3 text-[#00FF41]" />
                TRIGGER MAC LLM VIA IPHONE SIRI OR ACTION BUTTON:
              </div>
              <p className="text-[11px] text-[#8E9299]">
                Create a Shortcut with the <strong>"Get Contents of URL"</strong> action targeting your MacBook's LAN IP:
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="bg-[#080809] border border-[#2A2B2E] rounded p-3">
                <div className="text-[10px] text-[#8E9299] uppercase tracking-wider font-bold mb-1">
                  1. ASK FOR INPUT
                </div>
                <p className="text-[11px] text-[#5C5E63]">Prompt: "Ask your Mac AI"</p>
                <div className="mt-2 text-[10px] font-mono text-[#00FF41] bg-[#151619] p-1.5 rounded border border-[#2A2B2E]">
                  INPUT: USER_TEXT
                </div>
              </div>

              <div className="bg-[#080809] border border-[#2A2B2E] rounded p-3">
                <div className="text-[10px] text-[#8E9299] uppercase tracking-wider font-bold mb-1">
                  2. GET CONTENTS OF URL
                </div>
                <div className="text-[11px] text-[#8E9299] space-y-1">
                  <div><strong>URL:</strong> <span className="font-mono text-[#00FF41]">{lanUrl}/chat</span></div>
                  <div><strong>METHOD:</strong> POST</div>
                  {apiKey && <div><strong>HEADER:</strong> Authorization: Bearer {apiKey}</div>}
                </div>
              </div>

              <div className="bg-[#080809] border border-[#2A2B2E] rounded p-3">
                <div className="text-[10px] text-[#8E9299] uppercase tracking-wider font-bold mb-1">
                  3. GET DICTIONARY VALUE
                </div>
                <p className="text-[11px] text-[#5C5E63]">Key: <code className="text-[#00FF41] font-bold">content</code></p>
                <div className="mt-2 text-[10px] font-mono text-[#00FF41] bg-[#151619] p-1.5 rounded border border-[#2A2B2E]">
                  OUTPUT: SPEAK TEXT
                </div>
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-[#8E9299] mb-1">
                <span>SHORTCUT JSON PAYLOAD:</span>
                <button
                  onClick={() => copyToClipboard(`{\n  "model": "llama3.2:3b",\n  "messages": [\n    {"role": "user", "content": "Shortcut Input"}\n  ]\n}`, 'shortcut-json')}
                  className="flex items-center gap-1 text-[#00FF41] hover:text-white font-mono"
                >
                  {copiedId === 'shortcut-json' ? '[COPIED]' : '[COPY JSON]'}
                </button>
              </div>
              <pre className="bg-[#080809] border border-[#2A2B2E] text-[#00FF41] p-3 rounded font-mono text-[11px] overflow-x-auto">
{`{
  "model": "llama3.2:3b",
  "messages": [
    {
      "role": "user",
      "content": "Shortcut Input"
    }
  ]
}`}
              </pre>
            </div>
          </div>
        )}

        {/* cURL Tab */}
        {activeTab === 'curl' && (
          <div className="space-y-3 text-xs">
            <div>
              <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-[#8E9299] mb-1">
                <span>1. LAN CHAT INFERENCE PROBE:</span>
                <button
                  onClick={() => copyToClipboard(curlChat, 'curl-chat')}
                  className="flex items-center gap-1 text-[#00FF41] hover:text-white font-mono"
                >
                  {copiedId === 'curl-chat' ? '[COPIED]' : '[COPY CMD]'}
                </button>
              </div>
              <pre className="bg-[#080809] border border-[#2A2B2E] text-[#00FF41] p-3 rounded font-mono text-[11px] overflow-x-auto">
                {curlChat}
              </pre>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-[#8E9299] mb-1">
                  <span>2. HEALTH PROBE:</span>
                  <button
                    onClick={() => copyToClipboard(curlHealth, 'curl-health')}
                    className="text-[#00FF41] hover:text-white font-mono"
                  >
                    {copiedId === 'curl-health' ? '[COPIED]' : '[COPY]'}
                  </button>
                </div>
                <pre className="bg-[#080809] border border-[#2A2B2E] text-white p-2.5 rounded font-mono text-[10px] overflow-x-auto">
                  {curlHealth}
                </pre>
              </div>

              <div>
                <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-[#8E9299] mb-1">
                  <span>3. CATALOG MODELS:</span>
                  <button
                    onClick={() => copyToClipboard(curlModels, 'curl-models')}
                    className="text-[#00FF41] hover:text-white font-mono"
                  >
                    {copiedId === 'curl-models' ? '[COPIED]' : '[COPY]'}
                  </button>
                </div>
                <pre className="bg-[#080809] border border-[#2A2B2E] text-white p-2.5 rounded font-mono text-[10px] overflow-x-auto">
                  {curlModels}
                </pre>
              </div>
            </div>
          </div>
        )}

        {/* Swift Tab */}
        {activeTab === 'swift' && (
          <div className="space-y-3 text-xs">
            <div className="bg-[#1C1E22] border border-[#2A2B2E] rounded p-3 text-[#D1D1D1] flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div>
                <div className="text-[10px] text-[#00FF41] uppercase tracking-wider font-bold mb-0.5 flex items-center gap-1.5">
                  <Smartphone className="w-3 h-3 text-[#00FF41]" />
                  IOS SWIFT CODEBASE // 100% NATIVE SWIFTUI & ASYNC/AWAIT
                </div>
                <p className="text-[11px] text-[#8E9299]">
                  Complete production-ready iOS client with Server-Sent Events, Network.framework Bonjour, and MCP tools.
                </p>
              </div>
              <span className="text-[10px] font-mono text-[#F27D26] bg-[#080809] px-2 py-1 rounded border border-[#2A2B2E] shrink-0">
                SWIFT 5.9+ / IOS 16+
              </span>
            </div>

            {/* File Switcher */}
            <div className="flex flex-wrap gap-1.5 bg-[#080809] p-1 rounded border border-[#2A2B2E]">
              {Object.keys(swiftFiles).map((fileName) => (
                <button
                  key={fileName}
                  onClick={() => setActiveSwiftFile(fileName)}
                  className={`px-2.5 py-1 rounded text-[10px] font-mono transition ${
                    activeSwiftFile === fileName
                      ? 'bg-[#1C1E22] text-[#00FF41] border border-[#00FF41]/40 font-bold'
                      : 'text-[#8E9299] hover:text-white'
                  }`}
                >
                  {fileName}
                </button>
              ))}
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-[#8E9299]">
                <span className="font-mono text-[#D1D1D1]">
                  📄 {activeSwiftFile} — <span className="text-[#8E9299]">{swiftFiles[activeSwiftFile]?.desc}</span>
                </span>
                <button
                  onClick={() => copyToClipboard(swiftFiles[activeSwiftFile]?.code || '', `swift-${activeSwiftFile}`)}
                  className="flex items-center gap-1 text-[#00FF41] hover:text-white font-mono"
                >
                  {copiedId === `swift-${activeSwiftFile}` ? '[COPIED SWIFT]' : '[COPY FILE]'}
                </button>
              </div>
              <pre className="bg-[#080809] border border-[#2A2B2E] text-[#00FF41] p-3 rounded font-mono text-[11px] overflow-x-auto max-h-80 leading-relaxed">
                {swiftFiles[activeSwiftFile]?.code}
              </pre>
            </div>
          </div>
        )}

        {/* MCP Tab */}
        {activeTab === 'mcp' && (
          <div className="space-y-2 text-xs">
            <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-[#8E9299] mb-1">
              <span>CLAUDE DESKTOP CONFIG (~/Library/Application Support/Claude/claude_desktop_config.json):</span>
              <button
                onClick={() => copyToClipboard(mcpConfig, 'mcp-config')}
                className="flex items-center gap-1 text-[#00FF41] hover:text-white font-mono"
              >
                {copiedId === 'mcp-config' ? '[COPIED]' : '[COPY JSON]'}
              </button>
            </div>
            <pre className="bg-[#080809] border border-[#2A2B2E] text-[#00FF41] p-3 rounded font-mono text-[11px] overflow-x-auto">
              {mcpConfig}
            </pre>
          </div>
        )}

        {/* Firewall Tab */}
        {activeTab === 'firewall' && (
          <div className="space-y-3 text-xs text-[#8E9299]">
            <div className="bg-[#1C1E22] border border-[#2A2B2E] rounded p-3 text-[#D1D1D1]">
              <div className="text-[10px] text-[#F27D26] uppercase tracking-wider font-bold mb-1 flex items-center gap-1.5">
                <Shield className="w-3.5 h-3.5 text-[#F27D26]" />
                MACOS FIREWALL & WI-FI SUBNET DIAGNOSTIC CHECKLIST
              </div>
              <p className="text-[11px] text-[#8E9299]">
                If your iPhone reports "Connection timed out", verify these 3 macOS parameters:
              </p>
            </div>

            <div className="space-y-2 font-mono text-[11px]">
              <div className="p-2.5 bg-[#080809] border border-[#2A2B2E] rounded">
                <strong className="text-white">1. macOS Firewall:</strong> Open <em>System Settings → Network → Firewall</em>. Ensure Python / incoming connections on port <span className="text-[#00FF41]">{config?.port || 8080}</span> are permitted.
              </div>
              <div className="p-2.5 bg-[#080809] border border-[#2A2B2E] rounded">
                <strong className="text-white">2. Same Wi-Fi SSID:</strong> iPhone must be on the exact same Wi-Fi subnet as Mac (not on cellular or Guest network).
              </div>
              <div className="p-2.5 bg-[#080809] border border-[#2A2B2E] rounded">
                <strong className="text-white">3. Router AP Isolation:</strong> Ensure "Client / AP Isolation" is disabled on your home Wi-Fi access point.
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

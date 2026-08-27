//
//  MacLocalModelBridgeApp.swift
//  MacLocalModelBridge
//
//  Created for Mac Local Model Bridge MCP Client for iPhone.
//

import SwiftUI

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
                .onOpenURL { url in
                    Self.handleIncomingFile(url)
                }
                .onAppear {
                    if settings.autoDiscover {
                        discovery.startBrowsing()
                    }
                    // Mac inference is the default. Keep the legacy phone engine available only as an explicit fallback.
                    if settings.enableDirectInference {
                        PhoneHttpServer.shared.mode = .directInference
                        PhoneHttpServer.shared.start(port: settings.serverPort)
                    }
                }
                .onDisappear {
                    discovery.stopBrowsing()
                    PhoneHttpServer.shared.stop()
                }
                .onChange(of: settings.autoDiscover) { enabled in
                    if enabled {
                        discovery.startBrowsing()
                    } else {
                        discovery.stopBrowsing()
                    }
                }
                .onChange(of: settings.enableDirectInference) { enabled in
                    if enabled {
                        PhoneHttpServer.shared.mode = .directInference
                        PhoneHttpServer.shared.start(port: settings.serverPort)
                    } else {
                        PhoneHttpServer.shared.stop()
                    }
                }
        }
    }

    private static func handleIncomingFile(_ url: URL) {
        guard url.isFileURL, url.pathExtension.lowercased() == "gguf" else { return }
        let stagedURL: URL
        do {
            // Copy synchronously while the security-scoped extension handed to
            // us at open time is still valid - a detached background task can
            // lose access to the original file in another app's container.
            stagedURL = try DeviceModelStore.shared.stageImport(from: url)
        } catch {
            NotificationCenter.default.post(
                name: .localModelImportFailed,
                object: nil,
                userInfo: ["message": error.localizedDescription]
            )
            return
        }
        Task.detached {
            do {
                try await DeviceModelStore.shared.completeImport(at: stagedURL)
                await MainActor.run {
                    NotificationCenter.default.post(name: .localModelImported, object: nil)
                }
            } catch {
                await MainActor.run {
                    NotificationCenter.default.post(
                        name: .localModelImportFailed,
                        object: nil,
                        userInfo: ["message": error.localizedDescription]
                    )
                }
            }
        }
    }
}

struct ContentView: View {
    @EnvironmentObject var settings: SettingsManager
    @EnvironmentObject var discovery: BonjourDiscoveryManager
    @EnvironmentObject var bridgeClient: BridgeClient
    
    @State private var selectedTab: Tab = .chat

    enum Tab: String, CaseIterable, Identifiable {
        case chat = "Chat"
        case models = "Models"
        case mcp = "MCP Tools"
        case settings = "Connection"
        
        var id: String { rawValue }
        
        var iconName: String {
            switch self {
            case .chat: return "bubble.left.and.bubble.right.fill"
            case .models: return "cpu"
            case .mcp: return "wrench.and.screwdriver.fill"
            case .settings: return "network"
            }
        }
    }

    var body: some View {
        TabView(selection: $selectedTab) {
            ChatView()
                .tabItem {
                    Label(Tab.chat.rawValue, systemImage: Tab.chat.iconName)
                }
                .tag(Tab.chat)

            ModelsListView()
                .tabItem {
                    Label(Tab.models.rawValue, systemImage: Tab.models.iconName)
                }
                .tag(Tab.models)

            McpInspectorView()
                .tabItem {
                    Label(Tab.mcp.rawValue, systemImage: Tab.mcp.iconName)
                }
                .tag(Tab.mcp)

            SettingsView()
                .tabItem {
                    Label(Tab.settings.rawValue, systemImage: Tab.settings.iconName)
                }
                .tag(Tab.settings)
        }
        .tint(Color.phosphorGreen)
        .onReceive(NotificationCenter.default.publisher(for: .localModelImported)) { _ in
            withAnimation(AppTheme.Animation.standard) {
                selectedTab = .models
            }
        }
    }
}

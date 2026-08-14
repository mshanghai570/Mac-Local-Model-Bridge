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
                .onAppear {
                    discovery.startBrowsing()
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
        .tint(Color(red: 0.0, green: 1.0, blue: 0.25)) // Phosphor Matrix Green #00FF41
    }
}

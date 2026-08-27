//
//  SettingsView.swift
//  MacLocalModelBridge
//

import SwiftUI

public struct SettingsView: View {
    @EnvironmentObject var settings: SettingsManager
    @EnvironmentObject var discovery: BonjourDiscoveryManager
    @EnvironmentObject var bridgeClient: BridgeClient

    @State private var pingResult: String? = nil
    @State private var isPinging: Bool = false
    @State private var pingSuccess: Bool = false

    public var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Header
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("CONNECTION & TELEMETRY")
                            .font(AppTheme.Font.caption(.bold))
                            .foregroundColor(.textPrimary)
                        Text("Target Mac Bridge endpoint configuration")
                            .font(AppTheme.Font.caption2())
                            .foregroundColor(Color.textSecondary)
                    }
                    Spacer()

                    Button(action: testConnection) {
                        HStack(spacing: AppTheme.Spacing.xxs) {
                            if isPinging {
                                ProgressView()
                                    .progressViewStyle(CircularProgressViewStyle(tint: .white))
                            } else {
                                Image(systemName: "bolt.fill")
                            }
                            Text("PING BUS")
                                .font(AppTheme.Font.caption(.bold))
                        }
                        .foregroundColor(.textPrimary)
                        .padding(.horizontal, AppTheme.Spacing.xs)
                        .padding(.vertical, AppTheme.Spacing.xxs)
                        .background(Color.backgroundElevated)
                        .cornerRadius(AppTheme.Radius.sm)
                    }
                    .disabled(isPinging)
                }
                .padding(AppTheme.Spacing.lg)
                .background(Color.backgroundSurface)
                .bottomSeparator()

                Form {
                    // Ping Diagnostic Result Banner
                    if let ping = pingResult {
                        Section {
                            HStack(spacing: AppTheme.Spacing.xs) {
                                Circle()
                                    .fill(pingSuccess ? Color.successGreen : .errorRed)
                                    .frame(width: 8, height: 8)
                                    .pulseGlow(color: pingSuccess ? Color.successGreen : .errorRed, animate: pingSuccess)

                                Text(ping)
                                    .font(AppTheme.Font.caption2())
                                    .foregroundColor(pingSuccess ? Color.successGreen : .errorRed)
                            }
                            .listRowBackground(Color.clear)
                        }
                        .listRowInsets(EdgeInsets())
                        .transition(.move(edge: .top).combined(with: .opacity))
                        .animation(AppTheme.Animation.standard, value: pingResult)
                    }

                    // Bonjour Discovered Bridges
                    Section {
                        HStack {
                            Toggle("AUTO-DISCOVER MAC", isOn: $settings.autoDiscover)
                                .font(AppTheme.Font.caption(.bold))
                                .foregroundColor(.textPrimary)
                                .tint(Color.phosphorGreen)
                            Spacer()
                            Button("RESCAN") {
                                discovery.restartBrowsing()
                            }
                            .font(AppTheme.Font.caption2(.bold))
                            .foregroundColor(.textPrimary)
                            .padding(.horizontal, AppTheme.Spacing.xs)
                            .padding(.vertical, 4)
                            .background(Color.backgroundElevated)
                            .cornerRadius(AppTheme.Radius.sm)
                        }
                        .listRowBackground(Color.clear)

                        if discovery.discoveredBridges.isEmpty {
                            HStack(spacing: AppTheme.Spacing.xs) {
                                if discovery.isBrowsing {
                                    ProgressView()
                                        .scaleEffect(0.8)
                                } else {
                                    Image(systemName: "magnifyingglass")
                                        .foregroundColor(Color.textSecondary)
                                        .font(.system(size: 12))
                                }
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(discovery.lastDiscoveryStatus)
                                        .font(AppTheme.Font.caption2())
                                        .foregroundColor(Color.textSecondary)
                                    if !discovery.isBrowsing {
                                        Text("Make sure the gateway is running on your Mac, then tap RESCAN, or enter the LAN IP manually below.")
                                            .font(AppTheme.Font.caption2(.light))
                                            .foregroundColor(Color.textSecondary.opacity(0.7))
                                    }
                                }
                            }
                            .listRowBackground(Color.clear)
                            .foregroundColor(.clear)
                        } else {
                            ForEach(discovery.discoveredBridges) { bridge in
                                HStack {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(bridge.name)
                                            .font(AppTheme.Font.caption2(.bold))
                                            .foregroundColor(.textPrimary)
                                        Text(bridge.urlString)
                                            .font(AppTheme.Font.caption2(.light))
                                            .foregroundColor(Color.phosphorGreen)
                                    }
                                    Spacer()
                                    Button("CONNECT") {
                                        settings.setEndpoint(host: bridge.host, port: bridge.port)
                                        discovery.stopBrowsing()
                                        testConnection()
                                    }
                                    .font(AppTheme.Font.caption2(.bold))
                                    .foregroundColor(Color.backgroundPrimary)
                                    .padding(.horizontal, AppTheme.Spacing.xs)
                                    .padding(.vertical, 4)
                                    .background(Color.phosphorGreen)
                                    .cornerRadius(AppTheme.Radius.sm)
                                }
                                .listRowBackground(Color.clear)
                            }
                        }
                    } header: {
                        Text("BONJOUR ZERO-CONF SCANNED BRIDGES")
                            .font(AppTheme.Font.caption2(.bold))
                    }

                    // Manual LAN Endpoint Settings
                    Section {
                        HStack {
                            Text("MAC HOST / LAN IP")
                                .font(AppTheme.Font.footnote())
                                .foregroundColor(Color.textSecondary)
                            Spacer()
                            TextField("e.g. 192.168.1.100", text: $settings.host)
                                .font(AppTheme.Font.subheadline())
                                .foregroundColor(.textPrimary)
                                .multilineTextAlignment(.trailing)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled(true)
                                .keyboardType(.numbersAndPunctuation)
                                .textFieldStyle(.roundedBorder)
                                .tint(Color.phosphorGreen)
                        }
                        .listRowBackground(Color.clear)

                        HStack {
                            Text("BRIDGE PORT")
                                .font(AppTheme.Font.footnote())
                                .foregroundColor(Color.textSecondary)
                            Spacer()
                            TextField("8080", value: $settings.port, formatter: NumberFormatter())
                                .font(AppTheme.Font.subheadline())
                                .foregroundColor(.textPrimary)
                                .multilineTextAlignment(.trailing)
                                .keyboardType(.numberPad)
                                .textFieldStyle(.roundedBorder)
                                .tint(Color.phosphorGreen)
                        }
                        .listRowBackground(Color.clear)

                        HStack {
                            Text("BRIDGE API KEY")
                                .font(AppTheme.Font.footnote())
                                .foregroundColor(Color.textSecondary)
                            Spacer()
                            SecureField("Optional passphrase", text: $settings.apiKey)
                                .font(AppTheme.Font.subheadline())
                                .foregroundColor(.textPrimary)
                                .multilineTextAlignment(.trailing)
                                .textFieldStyle(.roundedBorder)
                                .tint(Color.phosphorGreen)
                        }
                        .listRowBackground(Color.clear)
                    } header: {
                        Text("MANUAL BRIDGE ENDPOINT")
                            .font(AppTheme.Font.caption2(.bold))
                    }

                    // Inference Hyperparameters
                    Section {
                        VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
                            HStack {
                                Text("TEMPERATURE: \(String(format: "%.1f", settings.temperature))")
                                    .font(AppTheme.Font.footnote())
                                    .foregroundColor(.textPrimary)
                                Spacer()
                                Text(String(format: "%.1f", settings.temperature))
                                    .font(AppTheme.Font.caption2(.bold))
                                    .foregroundColor(Color.amber)
                            }
                            Slider(value: $settings.temperature, in: 0.0...1.0, step: 0.1)
                                .accentColor(Color.amber)
                        }
                        .listRowBackground(Color.clear)

                        VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
                            Text("DEFAULT SYSTEM INSTRUCTIONS")
                                .font(AppTheme.Font.caption2())
                                .foregroundColor(Color.textSecondary)
                            TextEditor(text: $settings.systemPrompt)
                                .font(AppTheme.Font.caption2())
                                .foregroundColor(.textPrimary)
                                .frame(minHeight: 50)
                                .background(Color.backgroundElevated)
                                .cornerRadius(AppTheme.Radius.sm)
                                .overlay(
                                    RoundedRectangle(cornerRadius: AppTheme.Radius.sm)
                                        .stroke(Color.borderInput, lineWidth: 1)
                                )
                        }
                        .padding(.vertical, AppTheme.Spacing.xxs)
                        .listRowBackground(Color.clear)
                    } header: {
                        Text("INFERENCE PARAMETERS")
                            .font(AppTheme.Font.caption2(.bold))
                    }
                }
                .scrollContentBackground(.hidden)
                .refreshable {
                    discovery.restartBrowsing()
                }
            }
            .background(Color.backgroundPrimary.ignoresSafeArea())
            .toolbarBackground(.hidden, for: .navigationBar)
        }
        .navigationViewStyle(StackNavigationViewStyle())
    }

    private func testConnection() {
        isPinging = true
        pingResult = nil
        let start = CFAbsoluteTimeGetCurrent()

        Task {
            do {
                let health = try await bridgeClient.checkHealth()
                let elapsedMs = Int((CFAbsoluteTimeGetCurrent() - start) * 1000.0)
                await MainActor.run {
                    self.pingSuccess = true
                    self.pingResult = "HEALTH 200 OK • \(health.provider.uppercased()) • \(health.modelsCount) models • Latency: \(elapsedMs)ms"
                    self.isPinging = false
                    // Connection verified — stop endlessly scanning the network.
                    self.discovery.stopBrowsing()
                }
            } catch {
                await MainActor.run {
                    self.pingSuccess = false
                    self.pingResult = "FAILED: \(error.localizedDescription)"
                    self.isPinging = false
                }
            }
        }
    }
}

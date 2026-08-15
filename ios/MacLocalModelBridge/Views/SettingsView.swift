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
        NavigationView {
            VStack(spacing: 0) {
                // Header
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("CONNECTION & TELEMETRY")
                            .font(.system(size: 13, weight: .bold, design: .monospaced))
                            .foregroundColor(.white)
                        Text("Target Mac Bridge endpoint configuration")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundColor(Color.gray)
                    }
                    Spacer()
                    Button(action: {
                        testConnection()
                    }) {
                        HStack(spacing: 4) {
                            if isPinging {
                                ProgressView()
                                    .progressViewStyle(CircularProgressViewStyle(tint: .white))
                            } else {
                                Image(systemName: "bolt.fill")
                            }
                            Text("PING BUS")
                                .font(.system(size: 10, weight: .bold, design: .monospaced))
                        }
                        .foregroundColor(.white)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 5)
                        .background(Color(red: 0.15, green: 0.16, blue: 0.18))
                        .cornerRadius(4)
                    }
                }
                .padding(14)
                .background(Color(red: 0.08, green: 0.09, blue: 0.10))
                .overlay(
                    Rectangle()
                        .frame(height: 1)
                        .foregroundColor(Color(red: 0.16, green: 0.17, blue: 0.18)),
                    alignment: .bottom
                )

                Form {
                    // Ping Diagnostic Result Banner
                    if let ping = pingResult {
                        Section(header: Text("DIAGNOSTIC PROBE RESULT").font(.system(size: 10, design: .monospaced))) {
                            HStack {
                                Circle()
                                    .fill(pingSuccess ? Color(red: 0.0, green: 1.0, blue: 0.25) : Color.red)
                                    .frame(width: 8, height: 8)
                                Text(ping)
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundColor(pingSuccess ? Color(red: 0.0, green: 1.0, blue: 0.25) : Color.red)
                            }
                            .listRowBackground(Color(red: 0.08, green: 0.09, blue: 0.10))
                        }
                    }

                    // Bonjour Discovered Bridges
                    Section(header: Text("BONJOUR ZERO-CONF SCANNED BRIDGES").font(.system(size: 10, design: .monospaced))) {
                        if discovery.discoveredBridges.isEmpty {
                            HStack {
                                ProgressView()
                                    .scaleEffect(0.8)
                                Text(discovery.lastDiscoveryStatus)
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundColor(Color.gray)
                            }
                            .listRowBackground(Color(red: 0.08, green: 0.09, blue: 0.10))
                        } else {
                            ForEach(discovery.discoveredBridges) { bridge in
                                HStack {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(bridge.name)
                                            .font(.system(size: 12, weight: .bold, design: .monospaced))
                                            .foregroundColor(.white)
                                        Text(bridge.urlString)
                                            .font(.system(size: 10, design: .monospaced))
                                            .foregroundColor(Color(red: 0.0, green: 1.0, blue: 0.25))
                                    }
                                    Spacer()
                                    Button("CONNECT") {
                                        settings.setEndpoint(host: bridge.host, port: bridge.port)
                                        testConnection()
                                    }
                                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                                    .foregroundColor(Color(red: 0.05, green: 0.05, blue: 0.06))
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 4)
                                    .background(Color(red: 0.0, green: 1.0, blue: 0.25))
                                    .cornerRadius(4)
                                }
                                .listRowBackground(Color(red: 0.08, green: 0.09, blue: 0.10))
                            }
                        }
                    }

                    // Manual LAN Endpoint Settings
                    Section(header: Text("MANUAL BRIDGE ENDPOINT").font(.system(size: 10, design: .monospaced))) {
                        HStack {
                            Text("MAC HOST / LAN IP")
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundColor(Color.gray)
                            Spacer()
                            TextField("e.g. 192.168.1.100", text: $settings.host)
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundColor(.white)
                                .multilineTextAlignment(.trailing)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled(true)
                                .keyboardType(.numbersAndPunctuation)
                        }
                        .listRowBackground(Color(red: 0.08, green: 0.09, blue: 0.10))

                        HStack {
                            Text("BRIDGE PORT")
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundColor(Color.gray)
                            Spacer()
                            TextField("8080", value: $settings.port, formatter: NumberFormatter())
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundColor(.white)
                                .multilineTextAlignment(.trailing)
                                .keyboardType(.numberPad)
                        }
                        .listRowBackground(Color(red: 0.08, green: 0.09, blue: 0.10))

                        HStack {
                            Text("BRIDGE API KEY")
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundColor(Color.gray)
                            Spacer()
                            SecureField("Optional passphrase", text: $settings.apiKey)
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundColor(.white)
                                .multilineTextAlignment(.trailing)
                        }
                        .listRowBackground(Color(red: 0.08, green: 0.09, blue: 0.10))
                    }

                    // Inference Hyperparameters
                    Section(header: Text("INFERENCE PARAMETERS").font(.system(size: 10, design: .monospaced))) {
                        VStack(alignment: .leading, spacing: 6) {
                            HStack {
                                Text("TEMPERATURE: \(String(format: "%.1f", settings.temperature))")
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundColor(.white)
                                Spacer()
                            }
                            Slider(value: $settings.temperature, in: 0.0...1.0, step: 0.1)
                                .accentColor(Color(red: 0.95, green: 0.49, blue: 0.15))
                        }
                        .listRowBackground(Color(red: 0.08, green: 0.09, blue: 0.10))

                        VStack(alignment: .leading, spacing: 4) {
                            Text("DEFAULT SYSTEM INSTRUCTIONS")
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundColor(Color.gray)
                            TextEditor(text: $settings.systemPrompt)
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundColor(.white)
                                .frame(minHeight: 50)
                        }
                        .listRowBackground(Color(red: 0.08, green: 0.09, blue: 0.10))
                    }
                }
                .scrollContentBackground(.hidden)
            }
            .background(Color(red: 0.05, green: 0.05, blue: 0.06).ignoresSafeArea())
            .navigationBarHidden(true)
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
                DispatchQueue.main.async {
                    self.pingSuccess = true
                    self.pingResult = "HEALTH 200 OK • \(health.provider.uppercased()) • \(health.modelsCount) models • Latency: \(elapsedMs)ms"
                    self.isPinging = false
                }
            } catch {
                DispatchQueue.main.async {
                    self.pingSuccess = false
                    self.pingResult = "FAILED: \(error.localizedDescription)"
                    self.isPinging = false
                }
            }
        }
    }
}

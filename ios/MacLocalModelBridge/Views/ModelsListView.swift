//
//  ModelsListView.swift
//  MacLocalModelBridge
//

import SwiftUI

public struct ModelsListView: View {
    @StateObject private var viewModel = ModelsViewModel()
    @EnvironmentObject var settings: SettingsManager

    public var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                // Header
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("MAC MODEL CATALOG")
                            .font(.system(size: 13, weight: .bold, design: .monospaced))
                            .foregroundColor(.white)
                        Text("Retrieved via GET /models from Ollama / GGUF store")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundColor(Color.gray)
                    }
                    Spacer()
                    Button(action: {
                        Task { await viewModel.loadModels() }
                    }) {
                        Image(systemName: "arrow.clockwise")
                            .foregroundColor(Color(red: 0.0, green: 1.0, blue: 0.25))
                            .font(.system(size: 12, weight: .bold))
                            .padding(6)
                            .background(Color(red: 0.11, green: 0.12, blue: 0.13))
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

                if viewModel.isLoading {
                    Spacer()
                    ProgressView()
                        .progressViewStyle(CircularProgressViewStyle(tint: Color(red: 0.0, green: 1.0, blue: 0.25)))
                    Text("Fetching local models from Mac...")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundColor(Color.gray)
                        .padding(.top, 8)
                    Spacer()
                } else if let error = viewModel.errorMessage {
                    Spacer()
                    VStack(spacing: 8) {
                        Image(systemName: "exclamationmark.triangle")
                            .foregroundColor(.red)
                            .font(.system(size: 24))
                        Text(error)
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundColor(.white)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal)
                        Button("RETRY") {
                            Task { await viewModel.loadModels() }
                        }
                        .font(.system(size: 11, weight: .bold, design: .monospaced))
                        .foregroundColor(Color(red: 0.0, green: 1.0, blue: 0.25))
                        .padding(.horizontal, 16)
                        .padding(.vertical, 6)
                        .background(Color(red: 0.11, green: 0.12, blue: 0.13))
                        .cornerRadius(4)
                    }
                    Spacer()
                } else {
                    List {
                        ForEach(viewModel.models) { model in
                            VStack(alignment: .leading, spacing: 6) {
                                HStack {
                                    Text(model.name)
                                        .font(.system(size: 13, weight: .bold, design: .monospaced))
                                        .foregroundColor(.white)
                                    Spacer()
                                    if settings.defaultModel == model.name {
                                        Text("ACTIVE")
                                            .font(.system(size: 9, weight: .bold, design: .monospaced))
                                            .foregroundColor(Color(red: 0.0, green: 1.0, blue: 0.25))
                                            .padding(.horizontal, 6)
                                            .padding(.vertical, 2)
                                            .background(Color(red: 0.0, green: 1.0, blue: 0.25).opacity(0.15))
                                            .cornerRadius(3)
                                    }
                                }

                                HStack(spacing: 8) {
                                    Text(model.sizeFormatted ?? "N/A")
                                        .font(.system(size: 10, design: .monospaced))
                                        .foregroundColor(Color(red: 0.95, green: 0.49, blue: 0.15))

                                    Text("•")
                                        .foregroundColor(.gray)

                                    Text(model.quantizationLevel ?? "Q4_K_M")
                                        .font(.system(size: 10, design: .monospaced))
                                        .foregroundColor(.gray)

                                    if let param = model.parameterSize {
                                        Text("•")
                                            .foregroundColor(.gray)
                                        Text(param)
                                            .font(.system(size: 10, design: .monospaced))
                                            .foregroundColor(.blue)
                                    }
                                }

                                if let caps = model.capabilities, !caps.isEmpty {
                                    HStack(spacing: 4) {
                                        ForEach(caps, id: \.self) { cap in
                                            Text(cap.uppercased())
                                                .font(.system(size: 8, weight: .bold, design: .monospaced))
                                                .foregroundColor(.gray)
                                                .padding(.horizontal, 4)
                                                .padding(.vertical, 2)
                                                .background(Color(red: 0.05, green: 0.05, blue: 0.06))
                                                .cornerRadius(2)
                                        }
                                    }
                                }

                                Button(action: {
                                    settings.defaultModel = model.name
                                }) {
                                    Text("SET AS ACTIVE INFERENCE MODEL")
                                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                                        .foregroundColor(Color(red: 0.0, green: 1.0, blue: 0.25))
                                        .frame(maxWidth: .infinity)
                                        .padding(.vertical, 6)
                                        .background(Color(red: 0.11, green: 0.12, blue: 0.13))
                                        .cornerRadius(4)
                                }
                                .padding(.top, 4)
                            }
                            .padding(.vertical, 4)
                            .listRowBackground(Color(red: 0.08, green: 0.09, blue: 0.10))
                        }
                    }
                    .listStyle(PlainListStyle())
                }
            }
            .background(Color(red: 0.05, green: 0.05, blue: 0.06).ignoresSafeArea())
            .navigationBarHidden(true)
            .task {
                await viewModel.loadModels()
            }
        }
        .navigationViewStyle(StackNavigationViewStyle())
    }
}

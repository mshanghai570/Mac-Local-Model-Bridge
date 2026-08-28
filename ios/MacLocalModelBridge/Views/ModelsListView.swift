//
//  ModelsListView.swift
//  MacLocalModelBridge
//

import SwiftUI
import UniformTypeIdentifiers
import UIKit

public enum ModelsSection: String, CaseIterable, Identifiable {
    case mac = "MAC"
    case device = "ON-DEVICE"

    public var id: String { rawValue }
}

public struct ModelsListView: View {
    @StateObject private var viewModel = ModelsViewModel()
    @EnvironmentObject var settings: SettingsManager

    @State private var section: ModelsSection = .mac
    @State private var deviceModels: [DeviceModel] = []
    @State private var showImporter = false
    @State private var isImporting = false
    @State private var importError: String? = nil
    @State private var loadingModelName: String? = nil
    @State private var loadedModelName: String? = nil
    @State private var macModels: [MacStoredModel] = []
    @State private var macRuntime: MacRuntimeStatus? = nil
    @State private var isLoadingMacModels = false
    @State private var macError: String? = nil
    @State private var transferringModelName: String? = nil
    @State private var activeTransferID: String? = nil
    @State private var transferProgress: Double = 0
    @State private var transferStage: String = ""

    public var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Header
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(section == .mac ? "MAC MODEL CATALOG" : "ON-DEVICE GGUF MODELS")
                            .font(AppTheme.Font.caption(.bold))
                            .foregroundColor(.textPrimary)
                        Text(section == .mac
                             ? "Retrieved via GET /models from Ollama / GGUF store"
                             : "Imported .gguf files stored locally on this iPhone")
                            .font(AppTheme.Font.caption2())
                            .foregroundColor(Color.textSecondary)
                    }
                    Spacer()

                    if section == .mac {
                        Button(action: {
                            Task { await refreshMacModels() }
                        }) {
                            Image(systemName: "arrow.clockwise")
                                .foregroundColor(Color.phosphorGreen)
                                .font(.system(size: 12, weight: .bold))
                                .padding(AppTheme.Spacing.xs)
                                .background(Color.backgroundElevated)
                                .cornerRadius(AppTheme.Radius.sm)
                        }
                        .accessibilityLabel("Refresh")
                    } else {
                        Button(action: { showImporter = true }) {
                            Image(systemName: "square.and.arrow.down")
                                .foregroundColor(Color.phosphorGreen)
                                .font(.system(size: 12, weight: .bold))
                                .padding(AppTheme.Spacing.xs)
                                .background(Color.backgroundElevated)
                                .cornerRadius(AppTheme.Radius.sm)
                        }
                        .accessibilityLabel("Import model")
                    }
                }
                .padding(AppTheme.Spacing.lg)
                .background(Color.backgroundSurface)
                .bottomSeparator()

                // Section selector
                Picker("Section", selection: $section) {
                    ForEach(ModelsSection.allCases) { sec in
                        Text(sec.rawValue).tag(sec)
                    }
                }
                .pickerStyle(.segmented)
                .tint(Color.phosphorGreen)
                .padding(.horizontal, AppTheme.Spacing.lg)
                .padding(.vertical, AppTheme.Spacing.xs)
                .animation(AppTheme.Animation.standard, value: section)

                if section == .mac {
                    macModelsSection
                } else {
                    deviceModelsSection
                }
            }
            .background(Color.backgroundPrimary.ignoresSafeArea())
            .toolbarBackground(.hidden, for: .navigationBar)
                            .task {
                refreshDeviceModels()
                await refreshMacModels()
            }

            .onChange(of: section) { newSection in
                withAnimation(AppTheme.Animation.standard) {
                    if newSection == .mac {
                        Task { await refreshMacModels() }
                    } else {
                        refreshDeviceModels()
                    }
                }
            }
            .onReceive(NotificationCenter.default.publisher(for: .localModelImported)) { _ in
                withAnimation(AppTheme.Animation.standard) {
                    section = .device
                    importError = nil
                    refreshDeviceModels()
                }
            }
            .onReceive(NotificationCenter.default.publisher(for: .localModelImportFailed)) { note in
                withAnimation(AppTheme.Animation.standard) {
                    section = .device
                    importError = (note.userInfo?["message"] as? String) ?? "Failed to import model."
                    refreshDeviceModels()
                }
            }
            .sheet(isPresented: $showImporter) {
                DocumentPicker(allowedContentTypes: [.item, UTType(filenameExtension: "gguf") ?? .item]) { result in
                    handleImportResult(result)
                }
                .interactiveDismissDisabled(false)
            }
        }
        .navigationViewStyle(StackNavigationViewStyle())
    }

    // MARK: - Mac Models Section

    @ViewBuilder
    private var macModelsSection: some View {
        if isLoadingMacModels {
            Spacer()
            ProgressView()
                .progressViewStyle(CircularProgressViewStyle(tint: Color.phosphorGreen))
            Text("Fetching verified GGUF models from Mac…")
                .font(AppTheme.Font.caption2())
                .foregroundColor(Color.textSecondary)
                .padding(.top, AppTheme.Spacing.xs)
            Spacer()
        } else if let error = macError {
            Spacer()
            VStack(spacing: AppTheme.Spacing.xs) {
                Image(systemName: "exclamationmark.triangle")
                    .foregroundColor(.errorRed)
                    .font(.system(size: 24))
                Text(error)
                    .font(AppTheme.Font.caption2())
                    .foregroundColor(.textPrimary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)
                Button("RETRY") {
                    Task { await refreshMacModels() }
                }
                .font(AppTheme.Font.caption(.bold))
                .foregroundColor(Color.backgroundPrimary)
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, AppTheme.Spacing.xxs)
                .background(Color.phosphorGreen)
                .cornerRadius(AppTheme.Radius.sm)
            }
            .padding()
            .transition(.opacity)
            Spacer()
        } else if macModels.isEmpty {
            Spacer()
            VStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: "server.rack")
                    .font(.system(size: 28))
                    .foregroundColor(Color.phosphorGreen)
                Text("No verified Mac GGUF models")
                    .font(AppTheme.Font.body(.bold))
                    .foregroundColor(.textPrimary)
                Text("Pair this iPhone in Connection, then send an on-device GGUF model to your Mac.")
                    .font(AppTheme.Font.caption2())
                    .foregroundColor(Color.textSecondary)
                    .multilineTextAlignment(.center)
            }
            .padding()
            Spacer()
        } else {
            List {
                Section {
                    ForEach(macModels) { model in
                        MacStoredModelRowView(
                            model: model,
                            isRuntimeModel: macRuntime?.modelSHA256 == model.sha256,
                            runtimeRunning: macRuntime?.running == true,
                            onSelect: { selectMacModel(model) },
                            onStart: { startMacModel(model) },
                            onStop: { stopMacRuntime() }
                        )
                        .listRowBackground(Color.clear)
                    }
                } header: {
                    Text(macRuntime?.running == true ? "INTEL CPU RUNTIME RUNNING" : "INTEL CPU RUNTIME STOPPED")
                }
            }
            .listStyle(PlainListStyle())
            .refreshable { await refreshMacModels() }
            .scrollContentBackground(.hidden)
            .background(Color.backgroundSurface)
        }
    }

    // MARK: - On-Device Models Section

    @ViewBuilder
    private var deviceModelsSection: some View {
        if let error = importError {
            HStack(spacing: AppTheme.Spacing.xs) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundColor(.errorRed)
                Text(error)
                    .font(AppTheme.Font.caption2())
                    .foregroundColor(.textPrimary)
                Spacer()
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
            .animation(AppTheme.Animation.standard, value: importError)
        }

        if isImporting {
            Spacer()
            ProgressView()
                .progressViewStyle(CircularProgressViewStyle(tint: Color.phosphorGreen))
            Text("Importing model…")
                .font(AppTheme.Font.caption2())
                .foregroundColor(Color.textSecondary)
                .padding(.top, AppTheme.Spacing.xs)
            Spacer()
        } else if deviceModels.isEmpty {
            Spacer()
            VStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: "memorychip")
                    .font(.system(size: 28))
                    .foregroundColor(Color.phosphorGreen)
                Text("No on-device models yet")
                    .font(AppTheme.Font.body(.bold))
                    .foregroundColor(.textPrimary)
                Text("Tap the download icon above and pick a `.gguf` file\nfrom Files. Tip: on macOS, drop the file into\n`Files → On My iPhone → MacLocalModelBridge`\nafter AirDrop to avoid a long cloud download.")
                    .font(AppTheme.Font.caption2())
                    .foregroundColor(Color.textSecondary)
                    .multilineTextAlignment(.center)
                Button("IMPORT .GGUF") {
                    showImporter = true
                }
                .font(AppTheme.Font.caption(.bold))
                .foregroundColor(Color.backgroundPrimary)
                .padding(.horizontal, AppTheme.Spacing.xl)
                .padding(.vertical, AppTheme.Spacing.xs)
                .background(Color.phosphorGreen)
                .cornerRadius(AppTheme.Radius.sm)
                .transition(.scale.combined(with: .opacity))
            }
            .padding()
            Spacer()
        } else {
            List {
                ForEach(deviceModels) { model in
                    DeviceModelRowView(
                        model: model,
                        isLoading: loadingModelName == model.name,
                        isLoaded: loadedModelName == model.name,
                        isTransferring: transferringModelName == model.name,
                        transferProgress: transferProgress,
                        transferStage: transferStage,
                        onLoaded: { loadedModelName = $0 },
                        onLoadingStart: { loadingModelName = $0 },
                        onLoadingEnd: { _ in loadingModelName = nil },
                        onLoad: { loadDeviceModel(model) },
                        onTransfer: { transferDeviceModel(model) },
                        onCancelTransfer: { cancelActiveTransfer() },
                        onDelete: { deleteDeviceModel(model) }
                    )
                    .listRowBackground(Color.clear)
                }
            }
            .listStyle(PlainListStyle())
            .refreshable {
                refreshDeviceModels()
            }
            .scrollContentBackground(.hidden)
            .background(Color.backgroundSurface)
        }
    }

    // MARK: - Device Model Actions

    private func refreshMacModels() async {
        isLoadingMacModels = true
        macError = nil
        do {
            let client = MacRuntimeBridgeClient()
            let fetched = try await client.listModels()
            let status = try? await client.runtimeStatus()
            await MainActor.run {
                macModels = fetched
                macRuntime = status
                isLoadingMacModels = false
            }
        } catch {
            await MainActor.run {
                macError = error.localizedDescription
                isLoadingMacModels = false
            }
        }
    }

    private func transferDeviceModel(_ model: DeviceModel) {
        transferringModelName = model.name
        transferProgress = 0
        transferStage = "Preparing local GGUF…"
        importError = nil
        Task {
            do {
                let sent = try await MacRuntimeBridgeClient().upload(
                    model: model,
                    progress: { fraction in
                        await MainActor.run { transferProgress = fraction }
                    },
                    transferStarted: { transferID in
                        await MainActor.run { activeTransferID = transferID }
                    },
                    stage: { currentStage in
                        await MainActor.run { transferStage = currentStage }
                    }
                )
                await MainActor.run {
                    transferringModelName = nil
                    activeTransferID = nil
                    transferProgress = 1
                    transferStage = ""
                    section = .mac
                    macModels = (macModels.filter { $0.sha256 != sent.sha256 } + [sent])
                        .sorted { $0.filename.localizedCaseInsensitiveCompare($1.filename) == .orderedAscending }
                }
                await refreshMacModels()
            } catch {
                await MainActor.run {
                    importError = "Mac transfer failed: \(error.localizedDescription)"
                    transferringModelName = nil
                    activeTransferID = nil
                    transferStage = ""
                }
            }
        }
    }

    private func cancelActiveTransfer() {
        guard let transferID = activeTransferID else { return }
        Task {
            do {
                _ = try await MacRuntimeBridgeClient().cancel(transferID: transferID)
                await MainActor.run {
                    importError = "Mac transfer cancelled. Use SEND TO MAC again to resume from the saved offset."
                    transferringModelName = nil
                    activeTransferID = nil
                    transferStage = ""
                }
            } catch {
                await MainActor.run { importError = "Could not cancel Mac transfer: \(error.localizedDescription)" }
            }
        }
    }

    private func selectMacModel(_ model: MacStoredModel) {
        Task {
            do {
                _ = try await MacRuntimeBridgeClient().select(model: model)
                await MainActor.run { settings.defaultModel = model.filename }
                await refreshMacModels()
            } catch {
                await MainActor.run { macError = "Could not select Mac model: \(error.localizedDescription)" }
            }
        }
    }

    private func startMacModel(_ model: MacStoredModel) {
        Task {
            do {
                _ = try await MacRuntimeBridgeClient().start(model: model)
                await MainActor.run { settings.defaultModel = model.filename }
                await refreshMacModels()
            } catch {
                await MainActor.run { macError = "Could not start Intel runtime: \(error.localizedDescription)" }
            }
        }
    }

    private func stopMacRuntime() {
        Task {
            do {
                _ = try await MacRuntimeBridgeClient().stop()
                await refreshMacModels()
            } catch {
                await MainActor.run { macError = "Could not stop Intel runtime: \(error.localizedDescription)" }
            }
        }
    }

    private func refreshDeviceModels() {
        deviceModels = DeviceModelStore.shared.installedModels()
        loadedModelName = LocalInferenceEngine.shared.loadedModelInfo?.name
    }

    private func handleImportResult(_ result: Result<URL, Error>) {
        switch result {
        case .success(let url):
            withAnimation(AppTheme.Animation.standard) {
                isImporting = true
                importError = nil
            }
            Task {
                defer {
                    withAnimation(AppTheme.Animation.standard) {
                        isImporting = false
                    }
                }
                do {
                    _ = try await DeviceModelStore.shared.importModel(from: url)
                    refreshDeviceModels()
                } catch {
                    importError = error.localizedDescription
                }
            }
        case .failure(let error):
            if error is CancellationError { return }
            importError = error.localizedDescription
        }
    }

    private func loadDeviceModel(_ model: DeviceModel) {
        guard let url = DeviceModelStore.shared.url(for: model.name) else { return }
        loadingModelName = model.name
        importError = nil
        Task {
            defer { loadingModelName = nil }
            do {
                let report = try GGUFValidator.validate(url: url)
                guard report.isComplete else {
                    throw DeviceModelError.corruptImport(
                        name: model.name,
                        presentBytes: report.presentBytes,
                        requiredBytes: report.requiredBytes
                    )
                }
                _ = try await LocalInferenceEngine.shared.loadModel(at: url.path)
                loadedModelName = model.name
            } catch {
                importError = error.localizedDescription
            }
        }
    }

    private func deleteDeviceModel(_ model: DeviceModel) {
        if LocalInferenceEngine.shared.loadedModelInfo?.name == model.name {
            LocalInferenceEngine.shared.unloadModel()
            loadedModelName = nil
        }
        try? DeviceModelStore.shared.deleteModel(named: model.name)
        refreshDeviceModels()
    }
}

// MARK: - MAC Model Row

/// A reusable row for displaying a Mac-side model with an "SET AS ACTIVE" action.
struct ModelRowView: View {
    let model: BridgeModel
    let isActive: Bool
    let onSetActive: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
            HStack {
                Text(model.name)
                    .font(AppTheme.Font.body(.bold))
                    .foregroundColor(.textPrimary)
                Spacer()
                if isActive {
                    PillBadge(text: "ACTIVE")
                }
            }

            HStack(spacing: AppTheme.Spacing.xs) {
                Text(model.sizeFormatted ?? "N/A")
                    .font(AppTheme.Font.caption2())
                    .foregroundColor(Color.amber)

                Text("•")
                    .foregroundColor(Color.textSecondary)

                Text(model.quantizationLevel ?? "Q4_K_M")
                    .font(AppTheme.Font.caption2())
                    .foregroundColor(Color.textSecondary)

                if let param = model.parameterSize {
                    Text("•")
                        .foregroundColor(Color.textSecondary)
                    Text(param)
                        .font(AppTheme.Font.caption2())
                        .foregroundColor(Color.electricBlue)
                }
            }

            if let caps = model.capabilities, !caps.isEmpty {
                HStack(spacing: AppTheme.Spacing.xxs) {
                    ForEach(caps, id: \.self) { cap in
                        Text(cap.uppercased())
                            .font(AppTheme.Font.caption2(.bold))
                            .foregroundColor(Color.textSecondary)
                            .padding(.horizontal, AppTheme.Spacing.xxs)
                            .padding(.vertical, 2)
                            .background(Color.backgroundPrimary)
                            .cornerRadius(AppTheme.Radius.xs)
                    }
                }
            }

            Button(action: onSetActive) {
                Text("SET AS ACTIVE INFERENCE MODEL")
                    .font(AppTheme.Font.caption(.bold))
                    .foregroundColor(Color.phosphorGreen)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, AppTheme.Spacing.xxs)
                    .background(Color.backgroundElevated)
                    .cornerRadius(AppTheme.Radius.sm)
            }
            .buttonStyle(.plain)
            .padding(.top, AppTheme.Spacing.xxs)
        }
        .padding(.vertical, AppTheme.Spacing.xxs)
    }
}

// MARK: - Device Model Row

/// A reusable row for displaying an on-device GGUF model with load/delete actions.
struct DeviceModelRowView: View {
    let model: DeviceModel
    let isLoading: Bool
    let isLoaded: Bool
    let isTransferring: Bool
    let transferProgress: Double
    let transferStage: String
    let onLoaded: (String) -> Void
    let onLoadingStart: (String) -> Void
    let onLoadingEnd: (String) -> Void
    let onLoad: () -> Void
    let onTransfer: () -> Void
    let onCancelTransfer: () -> Void
    let onDelete: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
            HStack {
                Text(model.name)
                    .font(AppTheme.Font.body(.bold))
                    .foregroundColor(.textPrimary)
                Spacer()
                if isLoaded {
                    PillBadge(text: "LOADED")
                }
            }

            Text(model.sizeFormatted)
                .font(AppTheme.Font.caption2())
                .foregroundColor(Color.amber)

                        if isLoading || isTransferring {
                HStack(spacing: AppTheme.Spacing.xs) {
                    ProgressView()
                        .controlSize(.small)
                    Text(isTransferring
                         ? "\(transferStage.isEmpty ? "SENDING TO MAC" : transferStage)\(transferStage == "Uploading to Mac…" ? " \(Int(transferProgress * 100))%" : "")"
                         : "LOADING INTO MEMORY…")
                        .font(AppTheme.Font.caption2(.bold))
                        .foregroundColor(Color.textSecondary)
                    if isTransferring {
                        Button("CANCEL", action: onCancelTransfer)
                            .font(AppTheme.Font.caption2(.bold))
                            .foregroundColor(.errorRed)
                    }
                }
                .padding(.top, AppTheme.Spacing.xxs)
            } else {
                HStack(spacing: AppTheme.Spacing.xs) {
                    Button(action: onLoad) {
                        Text("LOAD")
                            .font(AppTheme.Font.caption(.bold))
                            .foregroundColor(Color.phosphorGreen)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, AppTheme.Spacing.xxs)
                            .background(Color.backgroundElevated)
                            .cornerRadius(AppTheme.Radius.sm)
                    }
                    .buttonStyle(.plain)

                    Button(action: onTransfer) {
                        Text("SEND TO MAC")
                            .font(AppTheme.Font.caption(.bold))
                            .foregroundColor(Color.electricBlue)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, AppTheme.Spacing.xxs)
                            .background(Color.backgroundElevated)
                            .cornerRadius(AppTheme.Radius.sm)
                    }
                    .buttonStyle(.plain)

                    Button(action: onDelete) {
                        Text("DELETE")
                            .font(AppTheme.Font.caption(.bold))
                            .foregroundColor(.errorRed)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, AppTheme.Spacing.xxs)
                            .background(Color.backgroundElevated)
                            .cornerRadius(AppTheme.Radius.sm)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.top, AppTheme.Spacing.xxs)
            }

        }
        .padding(.vertical, AppTheme.Spacing.xxs)
    }
}

// MARK: - Document Picker

struct DocumentPicker: UIViewControllerRepresentable {
    var allowedContentTypes: [UTType]
    var onPick: (Result<URL, Error>) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIViewController(context: Context) -> UIDocumentPickerViewController {
        let picker = UIDocumentPickerViewController(forOpeningContentTypes: allowedContentTypes, asCopy: true)
        picker.delegate = context.coordinator
        picker.allowsMultipleSelection = false
        return picker
    }

    func updateUIViewController(_ uiViewController: UIDocumentPickerViewController, context: Context) {}

    final class Coordinator: NSObject, UIDocumentPickerDelegate {
        let parent: DocumentPicker

        init(_ parent: DocumentPicker) { self.parent = parent }

        func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
            guard let url = urls.first else {
                parent.onPick(.failure(CancellationError()))
                return
            }
            parent.onPick(.success(url))
        }

        func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
            parent.onPick(.failure(CancellationError()))
        }
    }
}

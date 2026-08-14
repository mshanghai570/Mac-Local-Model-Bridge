//
//  ModelsViewModel.swift
//  MacLocalModelBridge
//

import Foundation
import SwiftUI

@MainActor
public class ModelsViewModel: ObservableObject {
    @Published public var models: [BridgeModel] = []
    @Published public var isLoading: Bool = false
    @Published public var errorMessage: String? = nil
    @Published public var selectedModel: BridgeModel? = nil

    private let client: BridgeClient

    public init(client: BridgeClient = BridgeClient()) {
        self.client = client
    }

    public func loadModels() async {
        isLoading = true
        errorMessage = nil
        do {
            let fetched = try await client.fetchModels()
            self.models = fetched
            if let first = fetched.first {
                self.selectedModel = first
            }
        } catch {
            self.errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}

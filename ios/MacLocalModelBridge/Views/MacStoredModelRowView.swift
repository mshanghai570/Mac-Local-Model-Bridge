//
//  MacStoredModelRowView.swift
//  MacLocalModelBridge
//

import SwiftUI

struct MacStoredModelRowView: View {
    let model: MacStoredModel
    let isRuntimeModel: Bool
    let runtimeRunning: Bool
    let onSelect: () -> Void
    let onStart: () -> Void
    let onStop: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
            HStack {
                Text(model.filename)
                    .font(AppTheme.Font.body(.bold))
                    .foregroundColor(.textPrimary)
                    .lineLimit(2)
                Spacer()
                if isRuntimeModel && runtimeRunning {
                    PillBadge(text: "RUNNING")
                } else if model.active {
                    PillBadge(text: "SELECTED")
                }
            }

            HStack(spacing: AppTheme.Spacing.xs) {
                Text(model.sizeFormatted)
                    .font(AppTheme.Font.caption2())
                    .foregroundColor(Color.amber)
                Text("•")
                    .foregroundColor(Color.textSecondary)
                Text("SHA-256 \(model.sha256.prefix(12))")
                    .font(AppTheme.Font.caption2())
                    .foregroundColor(Color.textSecondary)
                if let architecture = architecture {
                    Text("•")
                        .foregroundColor(Color.textSecondary)
                    Text(architecture.uppercased())
                        .font(AppTheme.Font.caption2())
                        .foregroundColor(Color.electricBlue)
                }
            }

            HStack(spacing: AppTheme.Spacing.xs) {
                Button("SELECT", action: onSelect)
                    .font(AppTheme.Font.caption(.bold))
                    .foregroundColor(Color.phosphorGreen)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, AppTheme.Spacing.xxs)
                    .background(Color.backgroundElevated)
                    .cornerRadius(AppTheme.Radius.sm)
                    .buttonStyle(.plain)

                if isRuntimeModel && runtimeRunning {
                    Button("STOP", action: onStop)
                        .font(AppTheme.Font.caption(.bold))
                        .foregroundColor(.errorRed)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, AppTheme.Spacing.xxs)
                        .background(Color.backgroundElevated)
                        .cornerRadius(AppTheme.Radius.sm)
                        .buttonStyle(.plain)
                } else {
                    Button("START ON MAC", action: onStart)
                        .font(AppTheme.Font.caption(.bold))
                        .foregroundColor(Color.electricBlue)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, AppTheme.Spacing.xxs)
                        .background(Color.backgroundElevated)
                        .cornerRadius(AppTheme.Radius.sm)
                        .buttonStyle(.plain)
                }
            }
        }
        .padding(.vertical, AppTheme.Spacing.xxs)
    }

    private var architecture: String? {
        guard case .string(let value)? = model.metadata?["architecture"] else { return nil }
        return value
    }
}

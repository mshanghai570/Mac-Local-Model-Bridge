//
//  TelemetryHeaderView.swift
//  MacLocalModelBridge
//

import SwiftUI

public struct TelemetryHeaderView: View {
    @EnvironmentObject var settings: SettingsManager
    let activeModel: String
    let isGenerating: Bool
    let tokensPerSecond: Double
    let tokenCount: Int

    public var body: some View {
        HStack {
            HStack(spacing: AppTheme.Spacing.xs) {
                StatusDot(color: isGenerating ? .errorRed : .successGreen, pulse: !isGenerating)

                VStack(alignment: .leading, spacing: 1) {
                    Text("LM-BRIDGE // \(activeModel.uppercased())")
                        .font(AppTheme.Font.caption(.bold))
                        .foregroundColor(.textPrimary)
                    Text("LAN: \(settings.host):\(settings.port)")
                        .font(AppTheme.Font.caption2())
                        .foregroundColor(Color.textSecondary)
                }
            }

            Spacer()

            if isGenerating {
                HStack(spacing: AppTheme.Spacing.xs) {
                    Text("\(String(format: "%.1f", tokensPerSecond)) t/s")
                        .font(AppTheme.Font.caption2(.bold))
                        .foregroundColor(Color.amber)

                    Text("•")
                        .foregroundColor(Color.textSecondary)

                    Text("\(tokenCount) tok")
                        .font(AppTheme.Font.caption2())
                        .foregroundColor(.textPrimary)
                }
                .padding(.horizontal, AppTheme.Spacing.xs)
                .padding(.vertical, 4)
                .background(Color.backgroundPrimary)
                .cornerRadius(AppTheme.Radius.sm)
                .overlay(
                    RoundedRectangle(cornerRadius: AppTheme.Radius.sm)
                        .stroke(Color.amber.opacity(0.5), lineWidth: 1)
                )
            } else {
                Text("READY")
                    .font(AppTheme.Font.caption(.bold))
                    .foregroundColor(.successGreen)
                    .padding(.horizontal, AppTheme.Spacing.xs)
                    .padding(.vertical, 3)
                    .background(Color.greenTint10)
                    .cornerRadius(AppTheme.Radius.sm)
                    .overlay(
                        RoundedRectangle(cornerRadius: AppTheme.Radius.sm)
                            .stroke(Color.phosphorGreen.opacity(0.3), lineWidth: 1)
                    )
            }
        }
        .padding(.horizontal, AppTheme.Spacing.lg)
        .padding(.vertical, AppTheme.Spacing.sm)
        .background(Color.backgroundSurface)
        .bottomSeparator()
        .animation(AppTheme.Animation.standard, value: isGenerating)
    }
}

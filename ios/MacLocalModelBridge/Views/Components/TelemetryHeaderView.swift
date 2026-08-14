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
            HStack(spacing: 6) {
                Circle()
                    .fill(Color(red: 0.0, green: 1.0, blue: 0.25)) // #00FF41
                    .frame(width: 8, height: 8)
                    .shadow(color: Color(red: 0.0, green: 1.0, blue: 0.25), radius: 4)

                VStack(alignment: .leading, spacing: 1) {
                    Text("LM-BRIDGE // \(activeModel.uppercased())")
                        .font(.system(size: 11, weight: .bold, design: .monospaced))
                        .foregroundColor(.white)
                    Text("LAN: \(settings.host):\(settings.port)")
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundColor(Color.gray)
                }
            }

            Spacer()

            if isGenerating {
                HStack(spacing: 8) {
                    Text("\(String(format: "%.1f", tokensPerSecond)) t/s")
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                        .foregroundColor(Color(red: 0.95, green: 0.49, blue: 0.15))
                    
                    Text("\(tokenCount) tok")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundColor(.white)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color(red: 0.05, green: 0.05, blue: 0.06))
                .cornerRadius(4)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Color(red: 0.95, green: 0.49, blue: 0.15), lineWidth: 1)
                )
            } else {
                Text("READY")
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundColor(Color(red: 0.0, green: 1.0, blue: 0.25))
                    .padding(.horizontal, 6)
                    .padding(.vertical, 3)
                    .background(Color(red: 0.0, green: 1.0, blue: 0.25).opacity(0.1))
                    .cornerRadius(4)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(Color(red: 0.08, green: 0.09, blue: 0.10)) // #151619
        .overlay(
            Rectangle()
                .frame(height: 1)
                .foregroundColor(Color(red: 0.16, green: 0.17, blue: 0.18)),
            alignment: .bottom
        )
    }
}

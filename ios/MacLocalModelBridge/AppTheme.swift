//
//  AppTheme.swift
//  MacLocalModelBridge
//
//  Centralized design system: color palette, spacing tokens, typography,
//  and reusable view modifiers that give every screen a consistent, smooth
//  cyberpunk aesthetic.
//

import SwiftUI

// MARK: - Color Palette

public extension Color {
    // ── Base backgrounds ──────────────────────────────────────────
    /// Deepest surface — app background / full-screen fills.
    static let backgroundPrimary = Color(red: 0.05, green: 0.05, blue: 0.06)   // #0D0D0E
    /// Slightly elevated card / header surface.
    static let backgroundSurface = Color(red: 0.08, green: 0.09, blue: 0.10)   // #141619
    /// Elevated interactive elements (buttons, input fields).
    static let backgroundElevated = Color(red: 0.11, green: 0.12, blue: 0.13)  // #1C1E22
    /// Distinct elevated surface for tool-call bubbles.
    static let backgroundElevatedAlt = Color(red: 0.12, green: 0.13, blue: 0.14)

    // ── Borders ───────────────────────────────────────────────────
    static let borderColor = Color(red: 0.16, green: 0.17, blue: 0.18)   // #28292A
    static let borderStrong = Color(red: 0.20, green: 0.25, blue: 0.35)  // user message outline
    static let borderInput = Color(red: 0.16, green: 0.17, blue: 0.18)

    // ── Accent colors ─────────────────────────────────────────────
    /// Phosphor Matrix Green — brand primary.
    static let phosphorGreen = Color(red: 0.0, green: 1.0, blue: 0.25)    // #00FF41
    /// Amber — warm secondary / metric labels.
    static let amber = Color(red: 0.95, green: 0.49, blue: 0.15)          // #F27D26
    /// Electric blue — user message icon / accent.
    static let electricBlue = Color(red: 0.0, green: 0.50, blue: 1.0)    // #007FFF
    /// Error / destructive.
    static let errorRed = Color(red: 0.9, green: 0.2, blue: 0.2)         // #E6333A

    // ── Text colors ───────────────────────────────────────────────
    static let textPrimary = Color.white
    static let textSecondary = Color.gray
    static let textDim = Color(red: 0.55, green: 0.60, blue: 0.55)         // reasoning text
    static let textTertiary = Color(red: 0.80, green: 0.85, blue: 0.80)    // tool-call args
    static let textPlaceholder = Color(red: 0.50, green: 0.52, blue: 0.53)

    // ── Semantic message bubble backgrounds ───────────────────────
    static let userBubbleBackground = Color(red: 0.11, green: 0.12, blue: 0.14)
    static let assistantBubbleBackground = Color(red: 0.08, green: 0.09, blue: 0.10)
    static let reasoningBackground = Color(red: 0.06, green: 0.07, blue: 0.08)
    static let toolCallBackground = Color(red: 0.12, green: 0.13, blue: 0.14)
    static let toolCallArgBackground = Color(red: 0.06, green: 0.07, blue: 0.08)

    // ── Reasoning block border ────────────────────────────────────
    static let reasoningBorder = Color(red: 0.13, green: 0.14, blue: 0.15)

    // ── Telemetry / status ────────────────────────────────────────
    static let telemetryBackground = Color(red: 0.08, green: 0.09, blue: 0.10)

    // ── Green tint overlays ───────────────────────────────────────
    static let greenTint15 = phosphorGreen.opacity(0.15)
    static let greenTint10 = phosphorGreen.opacity(0.10)

    // ── Convenience aliases ───────────────────────────────────────
    static let successGreen = phosphorGreen
    static let warningOrange = amber
}

// MARK: - Design Tokens

public enum AppTheme {
    public enum Radius {
        public static let xs: CGFloat = 3
        public static let sm: CGFloat = 4
        public static let md: CGFloat = 6
        public static let lg: CGFloat = 8
        public static let xl: CGFloat = 12
        public static let pill: CGFloat = 100
    }

    public enum Spacing {
        public static let xxxs: CGFloat = 2
        public static let xxs: CGFloat = 4
        public static let xs: CGFloat = 6
        public static let sm: CGFloat = 8
        public static let md: CGFloat = 12
        public static let lg: CGFloat = 14
        public static let xl: CGFloat = 18
        public static let xxl: CGFloat = 24
    }

    public enum Font {
        public static func caption(_ weight: SwiftUI.Font.Weight = .bold) -> SwiftUI.Font {
            .system(size: 9, weight: weight, design: .monospaced)
        }
        public static func caption2(_ weight: SwiftUI.Font.Weight = .regular) -> SwiftUI.Font {
            .system(size: 10, weight: weight, design: .monospaced)
        }
        public static func footnote(_ weight: SwiftUI.Font.Weight = .regular) -> SwiftUI.Font {
            .system(size: 11, weight: weight, design: .monospaced)
        }
        public static func subheadline(_ weight: SwiftUI.Font.Weight = .regular) -> SwiftUI.Font {
            .system(size: 12, weight: weight, design: .monospaced)
        }
        public static func body(_ weight: SwiftUI.Font.Weight = .regular) -> SwiftUI.Font {
            .system(size: 13, weight: weight, design: .monospaced)
        }
        public static func headline(_ weight: SwiftUI.Font.Weight = .regular) -> SwiftUI.Font {
            .system(size: 14, weight: weight, design: .monospaced)
        }
        public static func largeTitle(_ weight: SwiftUI.Font.Weight = .bold) -> SwiftUI.Font {
            .system(size: 16, weight: weight, design: .monospaced)
        }
    }

    public enum Animation {
        public static let standard = SwiftUI.Animation.interpolatingSpring(stiffness: 180, damping: 16)
        public static let smooth = SwiftUI.Animation.smooth(duration: 0.25)
        public static let fast = SwiftUI.Animation.easeOut(duration: 0.15)
    }

    public static let defaultShadow: [Any] = [
        // used as .shadow(color:radius:x:y:) — callers unpack
    ]
}

// MARK: - View Extensions

public extension View {
    /// Card background: elevated surface with rounded corners and a subtle
    /// border — the visual building block for buttons, input fields, and panels.
    func cardBackground(
        cornerRadius: CGFloat = AppTheme.Radius.md,
        borderColor: Color = Color.borderColor,
        backgroundColor: Color = Color.backgroundElevated
    ) -> some View {
        self
            .background(backgroundColor)
            .cornerRadius(cornerRadius)
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .stroke(borderColor, lineWidth: 1)
            )
    }

    /// Flat background for list rows and section surfaces.
    func flatSurface(
        cornerRadius: CGFloat = 0,
        backgroundColor: Color = Color.backgroundSurface
    ) -> some View {
        self
            .background(backgroundColor)
            .if(cornerRadius > 0) { view in
                view.cornerRadius(cornerRadius)
            }
    }

    /// A subtle separator line at the bottom of a header / toolbar.
    func bottomSeparator(
        color: Color = Color.borderColor,
        height: CGFloat = 1
    ) -> some View {
        self
            .overlay(
                Rectangle()
                    .frame(height: height)
                    .foregroundColor(color),
                alignment: .bottom
            )
    }

    /// Pulsing glow for status dots / active indicators.
    func pulseGlow(
        color: Color = Color.phosphorGreen,
        radius: CGFloat = 4,
        animate: Bool = true
    ) -> some View {
        self
            .shadow(color: color, radius: animate ? radius : 0)
            .animation(
                animate
                    ? .easeInOut(duration: 1.2).repeatForever(autoreverses: true)
                    : .none,
                value: animate
            )
    }

    /// Conditionally apply a modifier — SwiftUI's standard pattern.
    @ViewBuilder
    func `if`<Content: View>(_ condition: Bool, transform: (Self) -> Content) -> some View {
        if condition {
            transform(self)
        } else {
            self
        }
    }
}

// MARK: - Reusable Components

// MARK: - Reusable Components

/// A pill-shaped badge, used for ACTIVE / LOADED / MCP tags.
public struct PillBadge: View {
    let text: String
    let textColor: Color
    let backgroundColor: Color
    let borderColor: Color

    public init(
        text: String,
        textColor: Color = Color.phosphorGreen,
        backgroundColor: Color = Color.greenTint15,
        borderColor: Color = Color.phosphorGreen.opacity(0.3)
    ) {
        self.text = text
        self.textColor = textColor
        self.backgroundColor = backgroundColor
        self.borderColor = borderColor
    }

    public var body: some View {
        Text(text)
            .font(AppTheme.Font.caption(.bold))
            .foregroundColor(textColor)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(backgroundColor)
            .cornerRadius(AppTheme.Radius.xs)
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.xs)
                    .stroke(borderColor, lineWidth: 1)
            )
    }
}

/// A circular status dot with optional pulse.
public struct StatusDot: View {
    let color: Color
    let size: CGFloat
    let pulse: Bool

    public init(color: Color = Color.phosphorGreen, size: CGFloat = 8, pulse: Bool = true) {
        self.color = color
        self.size = size
        self.pulse = pulse
    }

    public var body: some View {
        Circle()
            .fill(color)
            .frame(width: size, height: size)
            .pulseGlow(color: color, radius: 4, animate: pulse)
    }
}

/// A label + value row used throughout Settings and Models.
public struct KeyValueRow: View {
    let label: String
    let value: String
    let labelColor: Color
    let valueColor: Color
    let alignment: HorizontalAlignment

    public init(
        label: String,
        value: String,
        labelColor: Color = Color.textSecondary,
        valueColor: Color = Color.textPrimary,
        alignment: HorizontalAlignment = .leading
    ) {
        self.label = label
        self.value = value
        self.labelColor = labelColor
        self.valueColor = valueColor
        self.alignment = alignment
    }

    public var body: some View {
        HStack {
            Text(label)
                .font(AppTheme.Font.footnote())
                .foregroundColor(labelColor)
            Spacer()
            Text(value)
                .font(AppTheme.Font.subheadline(.medium))
                .foregroundColor(valueColor)
                .multilineTextAlignment(.trailing)
        }
        .frame(maxWidth: .infinity, alignment: alignment == .trailing ? .trailing : .leading)
    }
}

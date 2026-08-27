//
//  ReasoningStreamParser.swift
//  MacLocalModelBridge
//

import Foundation

/// Splits incrementally-streamed generation output into two channels:
/// `.reasoning` (text between an open/close thinking-tag pair, e.g.
/// `<think>…</think>`) and `.answer` (everything else).
///
/// Generic across model families: DeepSeek-R1, Qwen3, Hunyuan and most
/// reasoning fine-tunes use `<think>`, some older tunes use `<thinking>`.
/// Nothing here is DeepSeek-specific; additional pairs can be supplied.
///
/// Streaming-safe: because tokens arrive in arbitrary-sized chunks, a tag can
/// straddle chunk boundaries ("<th" | "ink>"). The parser holds back at most
/// (longest tag length − 1) characters until the next chunk disambiguates,
/// then releases them on their correct channel.
public struct ReasoningStreamParser {

    public enum Channel: Equatable {
        case reasoning
        case answer
    }

    public typealias Segment = (channel: Channel, text: String)

    /// Tag pairs recognized by default. First match wins; order matters only
    /// for overlapping prefixes ("<think" vs "<thinking" share a prefix, and
    /// earliest-occurrence scanning resolves them correctly either way).
    public static let defaultTagPairs: [(open: String, close: String)] = [
        ("<think>", "</think>"),
        ("<thinking>", "</thinking>")
    ]

    private enum State {
        case ground
        case inside(closeTag: String)
    }

    private let tagPairs: [(open: String, close: String)]
    private var state: State = .ground
    private var pending: String = ""
    private var hasEmittedAnswer = false

    /// Longest tag we might be mid-way through seeing.
    private var maxTagLength: Int {
        let opens = tagPairs.map { $0.open.count }
        let closes = tagPairs.map { $0.close.count }
        return max(opens.max() ?? 0, closes.max() ?? 0)
    }

    public init(
        tagPairs: [(open: String, close: String)] = ReasoningStreamParser.defaultTagPairs,
        startsInsideThink: Bool = false
    ) {
        self.tagPairs = tagPairs.filter { !$0.open.isEmpty && !$0.close.isEmpty }
        if startsInsideThink {
            // Some chat templates (e.g. DeepSeek-R1 distills) pre-fill
            // "<think>" at the end of the assistant turn, so generated output
            // begins INSIDE the thinking block and its first explicit tag is
            // the closer. Start in reasoning mode accordingly.
            self.state = .inside(closeTag: "</think>")
        }
    }

    /// Consume one streamed chunk and return the segments that are now safe
    /// to surface, in order. Returned text never contains a partial or full
    /// thinking tag itself.
    public mutating func consume(_ text: String) -> [Segment] {
        pending += text
        return drain(matchLimit: maxTagLength - 1)
    }

    /// Flush everything still held back. Call when the stream finishes.
    /// If generation was cut off inside an unclosed `<think>` block, the held
    /// text correctly lands on the reasoning channel.
    public mutating func finish() -> [Segment] {
        let segments = drain(matchLimit: 0)
        return segments
    }

    // MARK: - Internals

    /// Repeatedly scan `pending` for the next relevant tag and release safe
    /// prefixes. `matchLimit` is how many trailing characters must stay
    /// buffered because they could still become a tag.
    private mutating func drain(matchLimit: Int) -> [Segment] {
        guard !tagPairs.isEmpty else {
            defer { pending.removeAll() }
            return pending.isEmpty ? [] : [makeSegment(channel: .answer, text: pending)]
        }

        var segments: [Segment] = []

        scanLoop: while true {
            // Earliest relevant tag in `pending`, given current state.
            var earliest: (range: Range<String.Index>, kind: TagKind)? = nil
            switch state {
            case .ground:
                for pair in tagPairs {
                    if let r = pending.range(of: pair.open, options: .literal),
                       earliest == nil || r.lowerBound < earliest!.range.lowerBound {
                        earliest = (r, .open(closeTag: pair.close))
                    }
                }
            case .inside(let closeTag):
                if let r = pending.range(of: closeTag, options: .literal) {
                    earliest = (r, .close)
                }
            }

            if let match = earliest {
                let headCount = pending.distance(from: pending.startIndex, to: match.range.lowerBound)
                if headCount > 0 {
                    segments.append(makeSegment(channel: currentChannel, text: String(pending.prefix(headCount))))
                }
                pending.removeSubrange(pending.startIndex..<match.range.upperBound)

                switch match.kind {
                case .open(let closeTag):
                    state = .inside(closeTag: closeTag)
                case .close:
                    state = .ground
                }
                continue scanLoop
            }

            // No complete tag: release everything except a possible partial
            // tag tail, then stop scanning.
            let holdBack = min(pending.count, matchLimit)
            let emitCount = pending.count - holdBack
            if emitCount > 0 {
                let released = String(pending.prefix(emitCount))
                pending = String(pending.suffix(holdBack))
                segments.append(makeSegment(channel: currentChannel, text: released))
            }
            break scanLoop
        }

        return segments
    }

    private var currentChannel: Channel {
        if case .inside = state { return .reasoning }
        return .answer
    }

    private mutating func makeSegment(channel: Channel, text: String) -> Segment {
        var trimmed = text
        if channel == .answer && !hasEmittedAnswer {
            // Drop blank lines the model emits right after </think>.
            let stripped = trimmed.drop(while: { $0 == "\n" || $0 == " " || $0 == "\t" })
            trimmed = String(stripped)
        }
        if !trimmed.isEmpty {
            if channel == .answer { hasEmittedAnswer = true }
        }
        return (channel, trimmed)
    }

    private enum TagKind {
        case open(closeTag: String)
        case close
    }
}

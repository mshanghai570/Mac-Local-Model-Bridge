//
//  LocalInferenceEngine.swift
//  MacLocalModelBridge
//
//  Runs .gguf models fully on-device via llama.swift (llama.cpp b10446).
//

import Foundation
import Darwin
import LlamaSwift

public struct DeviceModelInfo: Equatable {
    public let name: String
    public let path: String
    public let fileSizeBytes: Int64
    public let parameterCount: UInt64?
    public let contextLength: Int32?
    public let quantization: String?
    public let hasChatTemplate: Bool

    public var parameterCountFormatted: String? {
        guard let count = parameterCount else { return nil }
        if count >= 1_000_000_000 {
            return String(format: "%.1fB", Double(count) / 1_000_000_000)
        }
        if count >= 1_000_000 {
            return String(format: "%.1fM", Double(count) / 1_000_000)
        }
        return "\(count)"
    }
}

public enum InferenceError: LocalizedError, Equatable {
    case notLoaded
    case loadFailed(String)
    case contextCreationFailed
    case tokenizationFailed
    case detokenizationFailed
    case decodeFailed(Int32)
    case samplingFailed(String)
    case invalidToken(llama_token)
    case promptTooLong(Int)
    case cancelled

    public var errorDescription: String? {
        switch self {
        case .notLoaded:
            return "No on-device model is loaded. Import a .gguf model in the Models tab, then load it."
        case .loadFailed(let msg):
            return "Failed to load model: \(msg)"
        case .contextCreationFailed:
            return "Failed to create the inference context for this model."
        case .tokenizationFailed:
            return "Failed to tokenize the prompt."
        case .detokenizationFailed:
            return "Failed to decode model output."
        case .decodeFailed(let code):
            return "Inference failed (llama_decode error \(code))."
        case .samplingFailed(let msg):
            return "Sampling failed: \(msg)"
        case .invalidToken(let token):
            return "Received invalid token (id: \(token)) from the sampler."
        case .promptTooLong(let n):
            return "Prompt is too long (\(n) tokens) for this model's context window."
        case .cancelled:
            return "Inference cancelled by user."
        }
    }
}
public final class LocalInferenceEngine: @unchecked Sendable {

    public static let shared = LocalInferenceEngine()

    /// Textual fallback stops used alongside llama_vocab_is_eog.
    ///
    /// Some GGUF conversions mistag special tokens (<｜User｜>, <｜Assistant｜>,
    /// <｜end｜>, …) so they are neither flagged control nor EOG. Without a
    /// string-based check, generation then runs to maxTokens while the model
    /// hallucinates a fake back-and-forth conversation with itself. Callers can
    /// pass a custom list; these defaults cover the commonly mistagged tags
    /// plus the naive-prompt role markers.
    public static let defaultStopSequences: [String] = [
        "<｜User｜>",
        "<｜Assistant｜>",
        "<｜end｜>",
        "<｜end▁of▁sentence｜>",
        "\nUser:",
        "\nAssistant:",
        // ASCII ChatML / Llama-style tags — some Qwen & Mistral GGUF
        // conversions emit these literally instead of as EOG tokens.
        "<|im_end|>",
        "<|im_start|>",
        "</s>"
    ]

    // MARK: - Device Memory Budgeting
    //
    // Full GPU offload of large models exhausts Metal compute-buffer headroom
    // on 6–8 GB iPhones: llama_decode then fails (rc < 0, commonly -3) and in
    // the worst cases stresses the Metal driver hard enough to corrupt the
    // display until force-quit. iOS caps per-app memory well below physical
    // RAM, and the true footprint is weights + KV cache + compute buffers +
    // driver headroom, so the thresholds below are deliberately conservative
    // and keyed off the GGUF file size (≈ weight bytes).

    /// Models up to this size get full offload (n_gpu_layers = 99).
    public static let fullOffloadMaxBytes: Int64 = 3_221_225_472 // 3 GiB

    /// Above this size, GPU offload is disabled entirely (n_gpu_layers = 0);
    /// between the two thresholds we attempt a partial offload. 4 GiB keeps
    /// typical 7B Q4_K_M files (~4.7 GB decimal ≈ 4.4 GiB) safely CPU-only.
    public static let cpuOnlyAboveBytes: Int64 = 4_294_967_296 // 4 GiB

    /// Offload plan for a model of the given file size. Pure function so it
    /// can be exercised without loading anything.
    public static func plannedOffloadLayers(fileSizeBytes: Int64) -> Int32 {
        if fileSizeBytes >= cpuOnlyAboveBytes { return 0 }
        if fileSizeBytes >= fullOffloadMaxBytes { return 16 }
        return 99
    }

    /// Context/batch plan scaled to model size: KV cache grows linearly with
    /// n_ctx and prompt-processing buffers with n_batch, so large models get
    /// tighter budgets regardless of their trained context length.
    public static func contextPlan(
        fileSizeBytes: Int64,
        trainedContextLength: Int
    ) -> (nCtx: Int, nBatch: UInt32, nUBatch: UInt32) {
        let trained = trainedContextLength > 0 ? trainedContextLength : 2048
        if fileSizeBytes >= cpuOnlyAboveBytes {
            return (min(max(trained, 1024), 2048), 256, 256)
        }
        if fileSizeBytes >= fullOffloadMaxBytes {
            return (min(max(trained, 2048), 4096), 512, 256)
        }
        return (min(max(trained, 2048), 8192), 2048, 512)
    }

    private let queue = DispatchQueue(label: "com.localai.llama.inference")

    private var model: OpaquePointer?
    private var context: OpaquePointer?
    private var vocab: OpaquePointer?
    private var chatTemplate: String?
    private var nCtx: Int = 2048

    /// GPU layers actually applied to the currently loaded model (0 when the
    /// model runs CPU-only). Used to decide whether a decode failure is a
    /// Metal/GPU problem worth marking. Int32 matches llama_model_params.
    private var currentGpuLayers: Int32 = 0

    /// Models that hit llama_decode failures while running with GPU layers
    /// offloaded. They are reloaded CPU-only on the next request instead of
    /// failing again. Accessed only on `queue`.
    private var gpuOffloadUnsafePaths = Set<String>()

    /// Models known to emit <think>-style reasoning blocks: detected from the
    /// GGUF chat template at load time, or learned at runtime when a response
    /// actually contains a thinking tag. Used to raise the token budget.
    /// Guarded by `reasoningLock` because reads come from the main actor.
    private var reasoningModelPaths = Set<String>()
    private let reasoningLock = NSLock()

    private let stateLock = NSLock()
    private var _isLoaded = false
    private var _modelInfo: DeviceModelInfo?

    private let cancelLock = NSLock()
    private var _isCancelled = false

    private static let backendInitialized: Void = {
        llama_backend_init()
    }()

    private static func loadModel(path: String, params: llama_model_params, allowCpuFallback: Bool) -> OpaquePointer? {
        var result = llama_model_load_from_file(path, params)
        if allowCpuFallback && result == nil && params.n_gpu_layers > 0 {
            logBuffer.append("[engine] GPU offload failed, retrying with CPU only (n_gpu_layers = 0)")
            var cpuParams = params
            cpuParams.n_gpu_layers = 0
            result = llama_model_load_from_file(path, cpuParams)
        }
        return result
    }

    private final class LogBuffer {
        private let lock = NSLock()
        private var lines: [String] = []

        func append(_ line: String) {
            lock.lock()
            defer { lock.unlock() }
            lines.append(line)
            if lines.count > 200 { lines.removeFirst(lines.count - 200) }
        }

        func tail(_ count: Int = 40) -> String {
            lock.lock()
            defer { lock.unlock() }
            return lines.suffix(count).joined(separator: "\n")
        }

        func clear() {
            lock.lock()
            defer { lock.unlock() }
            lines.removeAll()
        }
    }

    private static let logBuffer = LogBuffer()

    private init() {
        let context = Unmanaged.passUnretained(Self.logBuffer).toOpaque()
        llama_log_set({ _, text, userData in
            guard let text, let userData else { return }
            Unmanaged<LogBuffer>.fromOpaque(userData).takeUnretainedValue().append(String(cString: text))
        }, context)
    }

    public var isLoaded: Bool {
        stateLock.lock()
        defer { stateLock.unlock() }
        return _isLoaded
    }

    public var loadedModelInfo: DeviceModelInfo? {
        stateLock.lock()
        defer { stateLock.unlock() }
        return _modelInfo
    }

    /// Recent llama.cpp/engine log lines, for on-device diagnostics of load
    /// and decode failures (e.g. Metal buffer exhaustion with large models).
    public func diagnosticLogTail(lines: Int = 24) -> String {
        Self.logBuffer.tail(lines)
    }

    /// True when the currently loaded model is known to emit <think>-style
    /// reasoning blocks (chat-template hint or runtime observation). Callers
    /// use this to size the generation budget.
    public var activeModelUsesReasoning: Bool {
        reasoningLock.lock()
        defer { reasoningLock.unlock() }
        guard let info = _modelInfo else { return false }
        return reasoningModelPaths.contains(info.path)
    }

    /// True when the applied chat template pre-fills "<think>" at the end of
    /// the assistant turn (DeepSeek-R1 style), meaning generation starts
    /// inside the thinking block. Callers use this to seed the reasoning
    /// parser's initial state.
    public var generationStartsInsideThink: Bool {
        reasoningLock.lock()
        defer { reasoningLock.unlock() }
        guard let template = chatTemplate else { return false }
        return Self.templatePreopensThink(template)
    }

    /// Heuristic: a template leaves generation inside a think block when it
    /// contains more openers than closers (typical R1-style templates end the
    /// assistant turn with a bare "<think>").
    private static func templatePreopensThink(_ template: String) -> Bool {
        func count(_ s: String, of needle: String) -> Int {
            guard !needle.isEmpty else { return 0 }
            var n = 0
            var searchRange = s.startIndex..<s.endIndex
            while let found = s.range(of: needle, options: .literal, range: searchRange) {
                n += 1
                searchRange = found.upperBound..<s.endIndex
            }
            return n
        }
        let opens = count(template, of: "<think>") + count(template, of: "<thinking>")
        let closes = count(template, of: "</think>") + count(template, of: "</thinking>")
        return opens > closes
    }

    /// Record that the active model produced a thinking block at runtime.
    public func noteReasoningOutputObserved() {
        reasoningLock.lock()
        defer { reasoningLock.unlock() }
        guard let info = _modelInfo else { return }
        reasoningModelPaths.insert(info.path)
    }

    // MARK: - Loading / Unloading

    public func loadModel(at path: String) async throws -> DeviceModelInfo {
        try await withCheckedThrowingContinuation { continuation in
            queue.async { [weak self] in
                guard let self else {
                    continuation.resume(throwing: InferenceError.notLoaded)
                    return
                }
                do {
                    let info = try self.loadModelSync(at: path)
                    continuation.resume(returning: info)
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    private func loadModelSync(at path: String) throws -> DeviceModelInfo {
        _ = Self.backendInitialized

        // Same model already loaded AND not flagged as GPU-unsafe → reuse it.
        // A GPU-unsafe flag forces the reload below so the next request
        // succeeds on CPU instead of repeating the decode failure.
        if let current = loadedModelInfo, current.path == path,
           !gpuOffloadUnsafePaths.contains(path) {
            return current
        }

        unloadSync()

        let fileURL = URL(fileURLWithPath: path)
        // Read the size up front: it drives the offload and context plans.
        let fileSizeBytes = (try? FileManager.default.attributesOfItem(atPath: path)[.size] as? NSNumber)?.int64Value ?? 0

        // Validate GGUF header before passing the file to llama.cpp. This
        // avoids feeding truncated or corrupt files into the native loader,
        // which can crash the process.
        do {
            let report = try GGUFValidator.validate(url: fileURL)
            if !report.isComplete {
                throw InferenceError.loadFailed("\(fileURL.lastPathComponent) is incomplete: \(ByteCountFormatter.string(fromByteCount: report.presentBytes, countStyle: .file)) present of \(ByteCountFormatter.string(fromByteCount: report.requiredBytes, countStyle: .file)) required")
            }
        } catch let err as InferenceError {
            throw err
        } catch let devErr as DeviceModelError {
            throw InferenceError.loadFailed(devErr.localizedDescription)
        } catch {
            throw InferenceError.loadFailed(error.localizedDescription)
        }

        Self.logBuffer.clear()

#if targetEnvironment(simulator)
        let allowGpu = false
#else
        let allowGpu = true
#endif

        var plannedLayers: Int32 = Self.plannedOffloadLayers(fileSizeBytes: fileSizeBytes)
        if allowGpu, gpuOffloadUnsafePaths.contains(path) {
            Self.logBuffer.append("[engine] \(fileURL.lastPathComponent) previously failed decode with GPU offload; forcing CPU-only (n_gpu_layers = 0)")
            plannedLayers = 0
        }

        var modelParams = llama_model_default_params()
        modelParams.n_gpu_layers = allowGpu ? plannedLayers : 0
        currentGpuLayers = allowGpu ? modelParams.n_gpu_layers : 0

        guard let loaded = Self.loadModel(path: path, params: modelParams, allowCpuFallback: allowGpu) else {
            let logTail = Self.logBuffer.tail()
            if !logTail.isEmpty {
                let logURL = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
                    .appendingPathComponent("llama_log.txt")
                try? logTail.write(to: logURL, atomically: true, encoding: .utf8)
            }
            let detail = logTail.isEmpty ? "" : "\n\nllama.cpp log:\n\(logTail)"
            throw InferenceError.loadFailed("llama_model_load_from_file returned nil. The file may be corrupt or incompatible.\(detail)")
        }
        model = loaded

        guard let loadedVocab = llama_model_get_vocab(loaded) else {
            llama_model_free(loaded)
            model = nil
            throw InferenceError.loadFailed("Model vocabulary unavailable.")
        }
        vocab = loadedVocab

        var contextParams = llama_context_default_params()
        let trainCtx = llama_model_n_ctx_train(loaded)
        let plan = Self.contextPlan(fileSizeBytes: fileSizeBytes, trainedContextLength: Int(trainCtx))
        nCtx = plan.nCtx
        contextParams.n_ctx = UInt32(nCtx)
        contextParams.n_batch = plan.nBatch
        contextParams.n_ubatch = plan.nUBatch
        contextParams.n_threads = 4
        contextParams.n_threads_batch = 4
        contextParams.no_perf = true

        guard let loadedContext = llama_init_from_model(loaded, contextParams) else {
            llama_model_free(loaded)
            model = nil
            vocab = nil
            throw InferenceError.contextCreationFailed
        }
        context = loadedContext
        llama_set_n_threads(loadedContext, 4, 4)

        if let template = llama_model_chat_template(loaded, nil) {
            chatTemplate = String(cString: template)
        } else {
            chatTemplate = nil
        }

        // Reasoning-model detection: most reasoning GGUFs (DeepSeek-R1,
        // Qwen3, …) declare a chat template containing the thinking tag. This
        // is a hint, not gospel — runtime observation via
        // noteReasoningOutputObserved() covers templates without the tag.
        if chatTemplate?.range(of: "<think", options: .literal) != nil {
            reasoningModelPaths.insert(path)
        } else {
            reasoningModelPaths.remove(path)
        }

        let ftype = llama_model_ftype(loaded)
        let info = DeviceModelInfo(
            name: (path as NSString).lastPathComponent,
            path: path,
            fileSizeBytes: fileSizeBytes,
            parameterCount: llama_model_n_params(loaded),
            contextLength: trainCtx,
            quantization: llama_ftype_name(ftype).map { String(cString: $0) },
            hasChatTemplate: chatTemplate != nil
        )

        stateLock.lock()
        _isLoaded = true
        _modelInfo = info
        stateLock.unlock()

        return info
    }

    public func unloadModel() {
        queue.async { [weak self] in
            guard let self else { return }
            self.unloadSync()
        }
    }

    private func unloadSync() {
        setCancelled(true)

        if let context {
            llama_free(context)
        }
        if let model {
            llama_model_free(model)
        }
        context = nil
        model = nil
        vocab = nil
        chatTemplate = nil

        stateLock.lock()
        _isLoaded = false
        _modelInfo = nil
        stateLock.unlock()
    }

    /// Called when llama_decode returns a negative code while a model with
    /// GPU layers offloaded is loaded. This is the decode-time analogue of the
    /// load-time CPU fallback: Metal compute-buffer exhaustion typically loads
    /// fine and only fails during generation, and retrying with full GPU
    /// offload would fail (or stress the driver) identically every time.
    ///
    /// The current request still fails gracefully via InferenceError; this
    /// marks the model so `loadModelSync` reloads it with n_gpu_layers = 0 on
    /// the NEXT request automatically.
    private func handleDecodeFailure(rc: Int32) {
        guard let info = loadedModelInfo, currentGpuLayers > 0 else { return }
        guard !gpuOffloadUnsafePaths.contains(info.path) else { return }
        gpuOffloadUnsafePaths.insert(info.path)
        Self.logBuffer.append("[engine] llama_decode returned \(rc); marking \(info.name) as GPU-offload unsafe. It will reload CPU-only on the next request.")
    }

    // MARK: - Cancellation

    public func stop() {
        setCancelled(true)
    }

    private func setCancelled(_ value: Bool) {
        cancelLock.lock()
        _isCancelled = value
        cancelLock.unlock()
    }

    private func isCancellationRequested() -> Bool {
        cancelLock.lock()
        defer { cancelLock.unlock() }
        return _isCancelled
    }

    // MARK: - Generation

    public func generate(
        messages: [ChatMessage],
        system: String?,
        temperature: Double,
        maxTokens: Int,
        stopSequences: [String] = LocalInferenceEngine.defaultStopSequences
    ) -> AsyncThrowingStream<String, Error> {
        AsyncThrowingStream { continuation in
            queue.async { [weak self] in
                guard let self else {
                    continuation.finish(throwing: InferenceError.notLoaded)
                    return
                }
                do {
                    self.setCancelled(false)
                    try self.generateInternal(
                        messages: messages,
                        system: system,
                        temperature: temperature,
                        maxTokens: maxTokens,
                        stopSequences: stopSequences,
                        yield: { continuation.yield($0) }
                    )
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    private func generateInternal(
        messages: [ChatMessage],
        system: String?,
        temperature: Double,
        maxTokens: Int,
        stopSequences: [String],
        yield: (String) -> Void
    ) throws {
        guard let ctx = context, let loadedVocab = vocab else {
            throw InferenceError.notLoaded
        }

        let prompt = buildPrompt(messages: messages, system: system)
        var tokens = try tokenize(prompt, vocab: loadedVocab)

        // Guard: an empty token array yields a nil baseAddress from
        // withUnsafeMutableBufferPointer, which causes llama_batch_get_one
        // to dereference nil and crash with EXC_BAD_ACCESS on arm64.
        guard !tokens.isEmpty else {
            throw InferenceError.tokenizationFailed
        }

        guard tokens.count < nCtx else {
            throw InferenceError.promptTooLong(tokens.count)
        }

        let limit = maxTokens > 0 ? maxTokens : 256

        // Decode the full prompt. With logits == NULL (set by llama_batch_get_one),
        // llama.cpp outputs logits for only the last token, which is exactly what
        // we sample from.
        let promptRC: Int32 = tokens.withUnsafeMutableBufferPointer { buf in
            let batch = llama_batch_get_one(buf.baseAddress, Int32(buf.count))
            return llama_decode(ctx, batch)
        }
        guard promptRC == 0 else {
            handleDecodeFailure(rc: promptRC)
            throw InferenceError.decodeFailed(promptRC)
        }

        // Per-request sampler chain: top_k -> top_p -> temp -> dist.
        let chainParams = llama_sampler_chain_default_params()
        guard let sampler = llama_sampler_chain_init(chainParams) else {
            throw InferenceError.contextCreationFailed
        }
        llama_sampler_chain_add(sampler, llama_sampler_init_top_k(40))
        llama_sampler_chain_add(sampler, llama_sampler_init_top_p(0.95, 1))
        llama_sampler_chain_add(sampler, llama_sampler_init_temp(Float(min(max(temperature, 0.0), 2.0))))
        llama_sampler_chain_add(sampler, llama_sampler_init_dist(LLAMA_DEFAULT_SEED))
        defer { llama_sampler_free(sampler) }

        var generated = 0
        var carry: [UInt8] = []

        // MARK: Stop-sequence safety net (see defaultStopSequences).
        //
        // llama_vocab_is_eog above remains the primary stop condition; this is
        // purely a fallback for mistagged GGUFs. Streaming mechanics:
        // decoded text is held back in `pending` (at most maxStopLength - 1
        // characters) so a stop sequence that straddles token boundaries can
        // be trimmed BEFORE it reaches the UI. `emittedTail` keeps the last
        // few characters of already-streamed text so matches can span the
        // holdback boundary. The raw-byte UTF-8 `carry` handling inside
        // decodePiece is untouched.
        let maxStopLength = stopSequences.map { $0.count }.max() ?? 0
        let rollingWindowLimit = max(40, maxStopLength * 2)
        var emittedTail = ""
        var pending = ""
        var stoppedBySequence = false

        while generated < limit {
            if isCancellationRequested() {
                throw InferenceError.cancelled
            }

            let newToken = llama_sampler_sample(sampler, ctx, -1)

            // llama_sampler_sample returns LLAMA_TOKEN_NULL (-1) when it
            // could not produce a token — e.g. when the context has no
            // backend sampler attached AND llama_get_logits_ith returns
            // nullptr (which happens if n_outputs is 0 after decode).
            // Passing -1 to llama_vocab_is_control triggers an out-of-bounds
            // array access (id_to_token[-1]) in llama.cpp, causing
            // EXC_BAD_ACCESS on arm64. Guard against this here.
            if newToken == LLAMA_TOKEN_NULL {
                throw InferenceError.samplingFailed("llama_sampler_sample returned LLAMA_TOKEN_NULL")
            }

            if llama_vocab_is_eog(loadedVocab, newToken) {
                break
            }

            if !llama_vocab_is_control(loadedVocab, newToken) {
                let piece = try pieceBytes(for: newToken, vocab: loadedVocab)
                let text = decodePiece(piece, carry: &carry)
                if !text.isEmpty {
                    generated += 1

                    pending += text

                    if maxStopLength > 0 {
                        let window = emittedTail + pending
                        if let match = Self.firstStopSequenceRange(in: window, stopSequences: stopSequences) {
                            // Emit only the text that precedes the earliest
                            // match, then stop cleanly. This is a normal,
                            // expected stop condition — not an error.
                            let matchOffset = window.distance(from: window.startIndex, to: match.lowerBound)
                            let safeFromPending = matchOffset - emittedTail.count
                            if safeFromPending > 0 {
                                yield(String(pending.prefix(safeFromPending)))
                            }
                            stoppedBySequence = true
                            break
                        }

                        // Hold back the last maxStopLength - 1 characters so a
                        // split stop sequence can never reach the caller.
                        let holdBack = min(pending.count, maxStopLength - 1)
                        let emitCount = pending.count - holdBack
                        if emitCount > 0 {
                            let chunk = String(pending.prefix(emitCount))
                            yield(chunk)
                            emittedTail = String((emittedTail + chunk).suffix(rollingWindowLimit))
                            pending = String(pending.suffix(holdBack))
                        }
                    } else {
                        yield(pending)
                        pending = ""
                    }
                }
            }

            // Decode the sampled token to advance the KV cache.
            var one = [newToken]
            let rc: Int32 = one.withUnsafeMutableBufferPointer { buf in
                let batch = llama_batch_get_one(buf.baseAddress, 1)
                return llama_decode(ctx, batch)
            }
            if rc != 0 {
                handleDecodeFailure(rc: rc)
                throw InferenceError.decodeFailed(rc)
            }
        }

        // Flush text held back by the stop-sequence window. Only when the loop
        // ended normally (EOG / token limit / cancellation-free exit). On a
        // stop-sequence break the held-back region belongs to the trimmed
        // match and is intentionally discarded, along with any partial bytes
        // left in `carry`.
        if !stoppedBySequence {
            if !pending.isEmpty {
                yield(pending)
            }
            if !carry.isEmpty, let tail = String(bytes: carry, encoding: .utf8) {
                yield(tail)
            }
        }
    }

    /// Earliest occurrence of any stop sequence in `text`, or nil when none
    /// of them appear. Uses literal comparison so multibyte tags such as
    /// <｜end▁of▁sentence｜> match byte-for-byte without grapheme-cluster
    /// canonicalization surprises.
    private static func firstStopSequenceRange(
        in text: String,
        stopSequences: [String]
    ) -> Range<String.Index>? {
        var earliest: Range<String.Index>? = nil
        for sequence in stopSequences where !sequence.isEmpty {
            if let range = text.range(of: sequence, options: .literal) {
                if earliest == nil || range.lowerBound < earliest!.lowerBound {
                    earliest = range
                }
            }
        }
        return earliest
    }

    // MARK: - Prompt Building

    public func buildPrompt(messages: [ChatMessage], system: String?) -> String {
        if let templateApplied = applyChatTemplate(messages: messages, system: system) {
            return templateApplied
        }
        return naivePrompt(messages: messages, system: system)
    }

    private func applyChatTemplate(messages: [ChatMessage], system: String?, addAssistant: Bool = true) -> String? {
        guard let template = chatTemplate else { return nil }

        var chatMessages: [llama_chat_message] = []
        var heldPointers: [UnsafeMutablePointer<CChar>] = []
        defer {
            for pointer in heldPointers {
                free(UnsafeMutableRawPointer(pointer))
            }
        }

        func appendMessage(role: String, content: String) {
            guard !content.isEmpty else { return }
            guard let roleC = strdup(role), let contentC = strdup(content) else { return }
            heldPointers.append(roleC)
            heldPointers.append(contentC)
            var message = llama_chat_message()
            message.role = UnsafePointer(roleC)
            message.content = UnsafePointer(contentC)
            chatMessages.append(message)
        }

        if let system, !system.isEmpty {
            appendMessage(role: "system", content: system)
        }
        for message in messages {
            appendMessage(role: message.role.rawValue, content: message.content)
        }
        guard !chatMessages.isEmpty else { return nil }

        var capacity = 256
        for message in chatMessages {
            let roleLength = message.role.map { strlen($0) } ?? 0
            let contentLength = message.content.map { strlen($0) } ?? 0
            capacity += Int(roleLength) + Int(contentLength) + 64
        }

        var buffer = [CChar](repeating: 0, count: capacity * 2)
        var resultLength = llama_chat_apply_template(
            template,
            &chatMessages,
            chatMessages.count,
            addAssistant,
            &buffer,
            Int32(buffer.count)
        )
        if resultLength < 0 {
            let required = Int(-resultLength)
            buffer = [CChar](repeating: 0, count: required)
            resultLength = llama_chat_apply_template(
                template,
                &chatMessages,
                chatMessages.count,
                addAssistant,
                &buffer,
                Int32(buffer.count)
            )
        }
        guard resultLength >= 0 else { return nil }
        return String(cString: buffer)
    }

    private func naivePrompt(messages: [ChatMessage], system: String?) -> String {
        var parts: [String] = []
        if let system, !system.isEmpty {
            parts.append("System: \(system)")
        }
        for message in messages where !message.content.isEmpty {
            switch message.role {
            case .user:
                parts.append("User: \(message.content)")
            case .assistant:
                parts.append("Assistant: \(message.content)")
            case .system:
                parts.append("System: \(message.content)")
            }
        }
        parts.append("Assistant:")
        return parts.joined(separator: "\n\n")
    }

    // MARK: - Tokenizer / Detokenizer Helpers

    private func tokenize(_ text: String, vocab: OpaquePointer) throws -> [llama_token] {
        let byteLength = text.utf8.count

        var capacity = max(byteLength / 2, 64) + 16
        var tokens = [llama_token](repeating: 0, count: capacity)
        var count = llama_tokenize(vocab, text, Int32(byteLength), &tokens, Int32(capacity), true, false)

        if count < 0 {
            capacity = Int(-count)
            tokens = [llama_token](repeating: 0, count: capacity)
            count = llama_tokenize(vocab, text, Int32(byteLength), &tokens, Int32(capacity), true, false)
        }
        guard count >= 0 else { throw InferenceError.tokenizationFailed }
        return Array(tokens.prefix(Int(count)))
    }

    private func pieceBytes(for token: llama_token, vocab: OpaquePointer) throws -> [UInt8] {
        // Defence-in-depth: LLAMA_TOKEN_NULL (-1) would cause an out-of-bounds
        // lookup in llama.cpp's vocab tables (EXC_BAD_ACCESS on arm64).
        guard token != LLAMA_TOKEN_NULL && token >= 0 else {
            throw InferenceError.invalidToken(token)
        }
        var buffer = [CChar](repeating: 0, count: 64)
        var length = llama_token_to_piece(vocab, token, &buffer, Int32(buffer.count), 0, false)

        if length < 0 {
            let required = Int(-length)
            buffer = [CChar](repeating: 0, count: required)
            length = llama_token_to_piece(vocab, token, &buffer, Int32(buffer.count), 0, false)
        }
        guard length >= 0 else { throw InferenceError.detokenizationFailed }
        return buffer.prefix(Int(length)).map { UInt8(bitPattern: $0) }
    }

    private func decodePiece(_ bytes: [UInt8], carry: inout [UInt8]) -> String {
        var combined = carry
        combined.append(contentsOf: bytes)

        let validLength = validUTF8PrefixLength(combined)
        // Use suffix(from:) instead of [validLength...] — the closed range subscript
        // crashes with "Index out of range" when validLength == combined.count,
        // which happens whenever all bytes form valid UTF-8 (the common case).
        carry = Array(combined.suffix(from: validLength))

        guard validLength > 0 else { return "" }
        return String(bytes: combined[0..<validLength], encoding: .utf8) ?? ""
    }

    private func validUTF8PrefixLength(_ bytes: [UInt8]) -> Int {
        var index = 0
        let count = bytes.count

        while index < count {
            let byte = bytes[index]
            let expected: Int
            if byte < 0x80 {
                expected = 0
            } else if byte >= 0xC0 && byte < 0xE0 {
                expected = 1
            } else if byte >= 0xE0 && byte < 0xF0 {
                expected = 2
            } else if byte >= 0xF0 && byte < 0xF8 {
                expected = 3
            } else {
                index += 1
                continue
            }

            // expected == 0 for plain ASCII: there are no continuation bytes,
            // so the sequence is trivially complete. Skipping the loop below is
            // required — `(index + 1)...(index + 0)` is an empty-backwards range
            // and raises "Range requires lowerBound <= upperBound" (crash).
            if expected == 0 {
                index += 1
                continue
            }

            if index + expected + 1 > count {
                return index
            }

            var validSequence = true
            for j in (index + 1)...(index + expected) {
                if bytes[j] & 0xC0 != 0x80 {
                    validSequence = false
                    break
                }
            }
            if !validSequence {
                index += 1
                continue
            }
            index += expected + 1
        }
        return count
    }
}

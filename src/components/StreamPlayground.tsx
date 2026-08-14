import React, { useState, useRef } from 'react';
import { Send, Zap, Square, Gauge, Clock, Sparkles, Terminal, Activity } from 'lucide-react';
import { BridgeModel, StreamMetric } from '../types';

interface Props {
  models: BridgeModel[];
  lanUrl: string;
  apiKey: string;
}

export const StreamPlayground: React.FC<Props> = ({ models, lanUrl, apiKey }) => {
  const [selectedModel, setSelectedModel] = useState<string>(models[0]?.name || 'llama3.2:3b');
  const [inputMessage, setInputMessage] = useState<string>('Write 3 bullet points on why Apple Silicon runs local LLMs efficiently.');
  const [temperature, setTemperature] = useState<number>(0.7);
  const [systemPrompt, setSystemPrompt] = useState<string>('You are an ultra-fast local assistant on MacBook M-series.');
  const [streaming, setStreaming] = useState<boolean>(false);
  const [outputStream, setOutputStream] = useState<string>('');
  const [metrics, setMetrics] = useState<StreamMetric | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);

  const startStreaming = async () => {
    if (!inputMessage.trim() || streaming) return;

    setStreaming(true);
    setOutputStream('');
    setMetrics(null);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    const startTime = performance.now();
    let firstTokenTime: number | null = null;
    let tokenCount = 0;

    try {
      const response = await fetch('/api/bridge/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
        },
        body: JSON.stringify({
          model: selectedModel,
          messages: [{ role: 'user', content: inputMessage }],
          temperature,
          system: systemPrompt,
          stream: true,
        }),
        signal: controller.signal,
      });

      if (!response.body) throw new Error('ReadableStream not supported in response');

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data: ')) continue;
          const dataStr = trimmed.slice(6);
          if (dataStr === '[DONE]') break;

          try {
            const chunk = JSON.parse(dataStr);
            if (chunk.content) {
              if (firstTokenTime === null) {
                firstTokenTime = performance.now();
              }
              tokenCount++;
              setOutputStream((prev) => prev + chunk.content);

              const currentElapsed = performance.now() - startTime;
              const ttft = firstTokenTime ? firstTokenTime - startTime : 0;
              const tps = currentElapsed > 0 ? (tokenCount / (currentElapsed / 1000)) : 0;

              setMetrics({
                tokenCount,
                durationMs: Math.round(currentElapsed),
                tokensPerSec: Math.round(tps * 10) / 10,
                firstTokenMs: Math.round(ttft),
              });
            }
          } catch {
            // ignore non-json line
          }
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        setOutputStream((prev) => prev + `\n\n[Stream error: ${err.message}]`);
      }
    } finally {
      setStreaming(false);
      abortControllerRef.current = null;
    }
  };

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setStreaming(false);
      setOutputStream((prev) => prev + '\n\n[Generation cancelled by user]');
    }
  };

  return (
    <div className="bg-[#151619] border border-[#2A2B2E] rounded-lg p-5 shadow-2xl relative overflow-hidden">
      <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-transparent via-[#00FF41] to-transparent opacity-30" />

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#2A2B2E]">
        <div className="flex items-center gap-2.5">
          <div className="w-2.5 h-2.5 rounded-full bg-[#00FF41] shadow-[0_0_8px_#00FF41]" />
          <div>
            <h2 className="text-xs uppercase tracking-widest text-[#8E9299] font-bold">
              REAL-TIME TOKEN STREAMING // SSE PROTOCOL
            </h2>
            <p className="text-[11px] text-[#5C5E63] mt-0.5">
              Live token-by-token emission from MacBook Metal GPU to iPhone simulation over Server-Sent Events.
            </p>
          </div>
        </div>

        {/* Live Metrics Readout */}
        <div className="flex items-center gap-3 bg-[#080809] border border-[#2A2B2E] px-3 py-1 rounded text-[11px] font-mono">
          <div className="flex items-center gap-1.5">
            <span className="text-[#5C5E63]">THROUGHPUT:</span>
            <span className="text-[#00FF41] font-bold">{metrics ? `${metrics.tokensPerSec} t/s` : '0.0 t/s'}</span>
          </div>
          <span className="text-[#2A2B2E]">|</span>
          <div className="flex items-center gap-1.5">
            <span className="text-[#5C5E63]">TTFT:</span>
            <span className="text-[#F27D26] font-bold">{metrics ? `${metrics.firstTokenMs}ms` : '--'}</span>
          </div>
          <span className="text-[#2A2B2E]">|</span>
          <div className="flex items-center gap-1.5">
            <span className="text-[#5C5E63]">TOKENS:</span>
            <span className="text-white font-bold">{metrics ? metrics.tokenCount : '0'}</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 mt-4">
        {/* Left Column: Hardware Controls */}
        <div className="lg:col-span-5 space-y-3.5 text-xs">
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-[#8E9299] mb-1">
              TARGET_MODEL:
            </label>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              disabled={streaming}
              className="w-full text-xs font-mono bg-[#080809] border border-[#2A2B2E] rounded p-2 text-white focus:outline-none focus:border-[#00FF41]"
            >
              {models.map((m) => (
                <option key={m.name} value={m.name} className="bg-[#151619] text-white">
                  {m.name} [{m.parameter_size || '3B'} // {m.quantization_level || 'Q4'}]
                </option>
              ))}
            </select>
          </div>

          <div>
            <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-[#8E9299] mb-1">
              <span>TEMPERATURE: {temperature}</span>
              <span className="text-[#5C5E63]">0.0 (PRECISE) → 1.0 (CREATIVE)</span>
            </div>
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={temperature}
              onChange={(e) => setTemperature(parseFloat(e.target.value))}
              disabled={streaming}
              className="w-full accent-[#F27D26] cursor-pointer bg-[#080809]"
            />
          </div>

          <div>
            <label className="block text-[10px] uppercase tracking-wider text-[#8E9299] mb-1">
              SYSTEM_INSTRUCTIONS:
            </label>
            <input
              type="text"
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              disabled={streaming}
              className="w-full text-xs font-mono bg-[#080809] border border-[#2A2B2E] rounded p-2 text-white placeholder-[#5C5E63] focus:outline-none focus:border-[#00FF41]"
              placeholder="e.g. You are a concise code helper"
            />
          </div>

          <div>
            <label className="block text-[10px] uppercase tracking-wider text-[#8E9299] mb-1">
              USER_PROMPT:
            </label>
            <textarea
              rows={3}
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              disabled={streaming}
              className="w-full text-xs font-mono bg-[#080809] border border-[#2A2B2E] rounded p-2.5 text-white placeholder-[#5C5E63] focus:outline-none focus:border-[#00FF41] resize-none"
              placeholder="Enter prompt to execute on local Mac GPU..."
            />
          </div>

          <div className="flex gap-2 pt-1">
            {!streaming ? (
              <button
                onClick={startStreaming}
                disabled={!inputMessage.trim()}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-[#1C1E22] hover:bg-[#2A2B2E] text-[#00FF41] border border-[#2A2B2E] hover:border-[#00FF41] rounded text-xs font-bold uppercase tracking-wider transition disabled:opacity-50"
              >
                <Zap className="w-3.5 h-3.5 text-[#00FF41]" />
                STREAM TOKENS FROM MAC
              </button>
            ) : (
              <button
                onClick={handleStop}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-[#FF4444]/10 hover:bg-[#FF4444]/20 border border-[#FF4444] text-[#FF4444] rounded text-xs font-bold uppercase tracking-wider transition"
              >
                <Square className="w-3.5 h-3.5" />
                STOP INFERENCE [CANCEL]
              </button>
            )}
          </div>
        </div>

        {/* Right Column: Live Stream Terminal Output */}
        <div className="lg:col-span-7 flex flex-col bg-[#080809] border border-[#2A2B2E] rounded overflow-hidden">
          <div className="p-2.5 border-b border-[#2A2B2E] bg-[#151619] flex justify-between items-center text-[10px]">
            <span className="text-[#00FF41] flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${streaming ? 'bg-[#00FF41] animate-ping' : 'bg-[#5C5E63]'}`} />
              ● LIVE TRAFFIC MONITOR // SSE CHAT BUS
            </span>
            <span className="text-[#5C5E63] font-mono">POST /chat [stream: true]</span>
          </div>

          <div className="flex-1 min-h-[240px] max-h-[320px] overflow-y-auto p-4 font-mono text-[11px] leading-relaxed text-[#D1D1D1]">
            {outputStream ? (
              <div className="whitespace-pre-wrap">
                <span className="text-[#5C5E63] select-none">&gt; </span>
                <span className="text-[#00FF41]">{outputStream}</span>
                {streaming && <span className="text-white animate-pulse"> _</span>}
              </div>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-[#5C5E63] text-center gap-2 py-8">
                <Terminal className="w-8 h-8 text-[#2A2B2E]" />
                <p className="text-[11px] uppercase tracking-wider">
                  [READY] Click "STREAM TOKENS FROM MAC" to initialize inference bus.
                </p>
                <p className="text-[10px] text-[#5C5E63]">
                  Tokens are synthesized on Apple Silicon Neural Engine & Metal GPU.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

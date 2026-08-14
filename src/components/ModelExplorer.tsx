import React from 'react';
import { HardDrive, Cpu, Tag, Sparkles, Check, FileText } from 'lucide-react';
import { BridgeModel } from '../types';

interface Props {
  models: BridgeModel[];
  onSelectModel: (name: string) => void;
}

export const ModelExplorer: React.FC<Props> = ({ models, onSelectModel }) => {
  return (
    <div className="bg-[#151619] border border-[#2A2B2E] rounded-lg p-5 shadow-2xl relative overflow-hidden flex flex-col h-full">
      <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-transparent via-[#F27D26] to-transparent opacity-30" />

      <div className="flex items-center justify-between pb-4 border-b border-[#2A2B2E]">
        <div className="flex items-center gap-2.5">
          <div className="w-2.5 h-2.5 rounded-full bg-[#F27D26] shadow-[0_0_8px_#F27D26]" />
          <div>
            <h2 className="text-xs uppercase tracking-widest text-[#8E9299] font-bold">
              AVAILABLE MODELS // GGUF STORAGE
            </h2>
            <p className="text-[11px] text-[#5C5E63] mt-0.5">
              Synced from local Ollama weights on Mac SSD.
            </p>
          </div>
        </div>
        <span className="text-[10px] font-mono px-2 py-0.5 bg-[#080809] text-[#00FF41] border border-[#2A2B2E] rounded">
          {models.length} LOADED
        </span>
      </div>

      <div className="flex-1 overflow-y-auto space-y-2.5 mt-4 max-h-[420px] pr-1">
        {models.map((m, idx) => (
          <div
            key={m.name}
            className={`p-3 bg-[#1C1E22] border-l-2 rounded-r transition flex flex-col justify-between ${
              idx === 0 ? 'border-[#F27D26]' : 'border-[#5C5E63] opacity-80 hover:opacity-100'
            }`}
          >
            <div>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="font-mono font-bold text-white text-xs flex items-center gap-2">
                    <span>{m.name}</span>
                    {idx === 0 && (
                      <span className="text-[9px] px-1 bg-[#F27D26]/20 text-[#F27D26] border border-[#F27D26]/40 rounded font-normal">
                        DEFAULT
                      </span>
                    )}
                  </div>
                  <div className="text-[10px] text-[#5C5E63] flex items-center gap-2 mt-0.5 font-mono">
                    <span>{m.size_formatted}</span>
                    <span>•</span>
                    <span>{m.format || 'GGUF'}</span>
                    <span>•</span>
                    <span>{m.quantization_level || 'Q4_K_M'}</span>
                  </div>
                </div>
                {m.parameter_size && (
                  <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-[#080809] text-[#8E9299] border border-[#2A2B2E]">
                    {m.parameter_size}
                  </span>
                )}
              </div>

              {/* Capabilities Chips */}
              <div className="flex flex-wrap gap-1 mt-2">
                {m.capabilities?.map((cap) => (
                  <span
                    key={cap}
                    className="px-1.5 py-0.2 rounded text-[8px] font-mono bg-[#080809] text-[#8E9299] border border-[#2A2B2E] uppercase"
                  >
                    {cap}
                  </span>
                ))}
              </div>
            </div>

            <div className="mt-3 pt-2 border-t border-[#2A2B2E] flex items-center justify-between text-[10px] font-mono">
              <span className="text-[#5C5E63] text-[9px] truncate max-w-[120px]">
                {m.digest?.slice(0, 10)}...
              </span>
              <button
                onClick={() => onSelectModel(m.name)}
                className="px-2.5 py-1 bg-[#080809] hover:bg-[#2A2B2E] text-[#00FF41] hover:text-white rounded border border-[#2A2B2E] hover:border-[#00FF41] transition text-[10px]"
              >
                SELECT IN MCP
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

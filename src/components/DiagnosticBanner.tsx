import React from 'react';
import { ShieldCheck, ShieldAlert, Wifi, Server, Cpu, CheckCircle2, AlertCircle, RefreshCw, Smartphone, Activity } from 'lucide-react';
import { BridgeHealth, BridgeConfigState } from '../types';

interface Props {
  health: BridgeHealth | null;
  config: BridgeConfigState | null;
  loading: boolean;
  onRefresh: () => void;
}

export const DiagnosticBanner: React.FC<Props> = ({ health, config, loading, onRefresh }) => {
  const isHealthy = health?.status === 'ok' && health?.backend_reachable;

  return (
    <div className="bg-[#151619] border border-[#2A2B2E] rounded-lg p-5 text-[#D1D1D1] shadow-2xl relative overflow-hidden">
      {/* Laser accent line */}
      <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-transparent via-[#00FF41] to-transparent opacity-30" />

      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 pb-4 border-b border-[#2A2B2E]">
        <div className="flex items-center gap-3">
          <div className={`w-3 h-3 rounded-full ${isHealthy ? 'bg-[#00FF41] shadow-[0_0_8px_#00FF41]' : 'bg-[#FF4444] shadow-[0_0_8px_#FF4444]'} animate-pulse`} />
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-xs uppercase tracking-widest text-[#8E9299] font-bold">
                SYSTEM TELEMETRY & HARDWARE BRIDGE STATUS
              </h2>
              <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-[#1C1E22] border border-[#2A2B2E] text-[#00FF41]">
                LIVE BUS
              </span>
            </div>
            <div className="text-[11px] text-[#5C5E63] mt-0.5">
              Zero-cloud local inference bridge streaming directly from Apple Silicon Metal GPU to iPhone client over LAN.
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={onRefresh}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-1.5 text-[11px] font-mono bg-[#1C1E22] hover:bg-[#2A2B2E] text-[#D1D1D1] hover:text-white rounded border border-[#2A2B2E] transition disabled:opacity-50"
          >
            <RefreshCw className={`w-3 h-3 text-[#F27D26] ${loading ? 'animate-spin' : ''}`} />
            {loading ? '[PROBING...]' : 'PROBE BUS'}
          </button>

          <div className={`flex items-center gap-2 px-3 py-1.5 rounded border text-[11px] font-mono ${
            isHealthy
              ? 'bg-[#080809] border-[#00FF41]/40 text-[#00FF41]'
              : 'bg-[#080809] border-[#FF4444]/40 text-[#FF4444]'
          }`}>
            <span className={`w-2 h-2 rounded-full ${isHealthy ? 'bg-[#00FF41]' : 'bg-[#FF4444]'}`} />
            {isHealthy ? 'BUS STATUS: ONLINE' : 'BUS STATUS: DEGRADED'}
          </div>
        </div>
      </div>

      {/* Grid of Key Diagnostics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mt-4 text-xs">
        {/* LAN Address */}
        <div className="bg-[#1C1E22] border border-[#2A2B2E] rounded p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-[#8E9299] text-[10px] uppercase tracking-wider mb-1">
            <span className="flex items-center gap-1.5">
              <Wifi className="w-3 h-3 text-[#3B82F6]" />
              IPHONE_LAN_TARGET
            </span>
            <span className="text-[#3B82F6] font-mono">0.0.0.0:{config?.port || 8080}</span>
          </div>
          <div className="font-mono text-sm font-bold text-white truncate my-1">
            {config?.lan_url || `http://${config?.lanIp || '192.168.1.125'}:${config?.port || 8080}`}
          </div>
          <div className="text-[10px] text-[#5C5E63]">
            INTERFACE: <span className="text-[#D1D1D1]">{config?.lanIp || '192.168.1.125'}</span>
          </div>
        </div>

        {/* Inference Backend */}
        <div className="bg-[#1C1E22] border border-[#2A2B2E] rounded p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-[#8E9299] text-[10px] uppercase tracking-wider mb-1">
            <span className="flex items-center gap-1.5">
              <Cpu className="w-3 h-3 text-[#F27D26]" />
              INFERENCE_ENGINE
            </span>
            <span className="text-[#F27D26] uppercase font-mono">{config?.provider || 'ollama'}</span>
          </div>
          <div className="font-mono text-sm font-bold text-white truncate flex items-center gap-1.5 my-1">
            <span className={`w-2 h-2 rounded-full shrink-0 ${health?.backend_reachable ? 'bg-[#00FF41]' : 'bg-[#FF4444]'}`} />
            {health?.backend_url || 'http://127.0.0.1:11434'}
          </div>
          <div className="text-[10px] text-[#5C5E63] truncate">
            {health?.message || 'Ready for inference'}
          </div>
        </div>

        {/* Security / Auth Guard */}
        <div className="bg-[#1C1E22] border border-[#2A2B2E] rounded p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-[#8E9299] text-[10px] uppercase tracking-wider mb-1">
            <span className="flex items-center gap-1.5">
              {config?.apiKey ? <ShieldCheck className="w-3 h-3 text-[#00FF41]" /> : <ShieldAlert className="w-3 h-3 text-[#5C5E63]" />}
              AUTH_GUARD
            </span>
            <span className={`text-[10px] font-mono ${config?.apiKey ? 'text-[#00FF41]' : 'text-[#8E9299]'}`}>
              {config?.apiKey ? 'ENFORCED' : 'OPEN_LAN'}
            </span>
          </div>
          <div className="font-mono text-sm font-bold text-white truncate my-1">
            {config?.apiKey ? `BEARER ${config.apiKey.slice(0, 3)}***` : 'NO TOKEN REQ'}
          </div>
          <div className="text-[10px] text-[#5C5E63]">
            {config?.apiKey ? 'Constant-time HMAC token check' : 'Open Wi-Fi subnet access'}
          </div>
        </div>

        {/* Bonjour Discovery */}
        <div className="bg-[#1C1E22] border border-[#2A2B2E] rounded p-3 flex flex-col justify-between">
          <div className="flex items-center justify-between text-[#8E9299] text-[10px] uppercase tracking-wider mb-1">
            <span className="flex items-center gap-1.5">
              <Smartphone className="w-3 h-3 text-[#00FF41]" />
              MDNS_DISCOVERY
            </span>
            <span className="text-[#00FF41] font-mono">BROADCASTING</span>
          </div>
          <div className="font-mono text-xs font-bold text-[#00FF41] truncate my-1">
            _local-ai-bridge._tcp
          </div>
          <div className="text-[10px] text-[#5C5E63]">
            Auto-discovered by iOS Bonjour
          </div>
        </div>
      </div>
    </div>
  );
};

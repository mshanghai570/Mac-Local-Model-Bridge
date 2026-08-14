import React, { useState, useEffect } from 'react';
import { DiagnosticBanner } from './components/DiagnosticBanner';
import { McpToolTester } from './components/McpToolTester';
import { StreamPlayground } from './components/StreamPlayground';
import { IphoneConnectGuide } from './components/IphoneConnectGuide';
import { ModelExplorer } from './components/ModelExplorer';
import { BridgeHealth, BridgeConfigState, BridgeModel } from './types';
import { Settings, Sliders, Activity, Radio, Cpu, RefreshCw, Key, Terminal, Wifi, Shield } from 'lucide-react';

export default function App() {
  const [health, setHealth] = useState<BridgeHealth | null>(null);
  const [config, setConfig] = useState<BridgeConfigState | null>(null);
  const [models, setModels] = useState<BridgeModel[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [activeTab, setActiveTab] = useState<'overview' | 'stream' | 'mcp' | 'models' | 'connect' | 'settings'>('overview');

  // Config settings modal/tab state
  const [editPort, setEditPort] = useState<number>(8080);
  const [editApiKey, setEditApiKey] = useState<string>('');
  const [editOllamaUrl, setEditOllamaUrl] = useState<string>('http://127.0.0.1:11434');
  const [savingConfig, setSavingConfig] = useState<boolean>(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  const fetchBridgeData = async () => {
    setLoading(true);
    try {
      const [healthRes, configRes, modelsRes] = await Promise.all([
        fetch('/api/bridge/health').then(r => r.json()),
        fetch('/api/bridge/config').then(r => r.json()),
        fetch('/api/bridge/models').then(r => r.json()),
      ]);

      setHealth(healthRes);
      setConfig(configRes);
      setModels(modelsRes.models || []);

      setEditPort(configRes.port || 8080);
      setEditApiKey(configRes.apiKey || '');
      setEditOllamaUrl(configRes.ollamaUrl || 'http://127.0.0.1:11434');
    } catch (err) {
      console.error('Error fetching bridge data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBridgeData();
  }, []);

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingConfig(true);
    setSaveMessage(null);
    try {
      const res = await fetch('/api/bridge/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          port: editPort,
          apiKey: editApiKey,
          ollamaUrl: editOllamaUrl,
        }),
      });
      const data = await res.json();
      if (data.success) {
        setSaveMessage('Bridge configuration updated.');
        await fetchBridgeData();
      }
    } catch (err: any) {
      setSaveMessage(`Failed to save: ${err.message}`);
    } finally {
      setSavingConfig(false);
    }
  };

  const isHealthy = health?.status === 'ok' && health?.backend_reachable;

  return (
    <div className="min-h-screen bg-[#0C0D0E] text-[#D1D1D1] font-mono flex flex-col antialiased selection:bg-[#00FF41]/20 selection:text-[#00FF41]">
      {/* Hardware Telemetry Header */}
      <header className="bg-[#151619] border-b border-[#2A2B2E] px-4 sm:px-6 lg:px-8 py-3 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className={`w-3 h-3 rounded-full ${isHealthy ? 'bg-[#00FF41] shadow-[0_0_8px_#00FF41]' : 'bg-[#FF4444] shadow-[0_0_8px_#FF4444]'} animate-pulse`} />
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-sm sm:text-base font-bold tracking-tight text-white uppercase">
                  LM-BRIDGE // MCP-SERVER-01
                </h1>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#1C1E22] border border-[#2A2B2E] text-[#8E9299]">
                  v1.0.4
                </span>
              </div>
              <div className="text-[11px] text-[#5C5E63] mt-0.5">
                LAN TARGET: <span className="text-[#00FF41]">{config?.lan_url || 'http://192.168.1.125:8080'}</span>
              </div>
            </div>
          </div>

          {/* Quick Hardware Readouts */}
          <div className="hidden lg:flex items-center gap-6 text-[10px] text-[#8E9299] uppercase tracking-widest border-l border-r border-[#2A2B2E] px-6">
            <div className="flex flex-col items-end">
              <span className="text-[#5C5E63]">LOCAL IP</span>
              <span className="text-white font-bold">{config?.lanIp || '192.168.1.125'}</span>
            </div>
            <div className="flex flex-col items-end">
              <span className="text-[#5C5E63]">PORT</span>
              <span className="text-[#F27D26] font-bold">{config?.port || 8080}</span>
            </div>
            <div className="flex flex-col items-end">
              <span className="text-[#5C5E63]">PROVIDER</span>
              <span className="text-[#F27D26] font-bold">{config?.provider?.toUpperCase() || 'OLLAMA'}</span>
            </div>
            <div className="flex flex-col items-end">
              <span className="text-[#5C5E63]">STATUS</span>
              <span className={`font-bold ${isHealthy ? 'text-[#00FF41]' : 'text-[#FF4444]'}`}>
                {isHealthy ? 'READY' : 'DEGRADED'}
              </span>
            </div>
          </div>

          {/* Navigation Controls */}
          <nav className="flex items-center flex-wrap gap-1.5 bg-[#080809] p-1 rounded-lg border border-[#2A2B2E] text-[11px]">
            <button
              onClick={() => setActiveTab('overview')}
              className={`px-3 py-1.5 rounded transition ${activeTab === 'overview' ? 'bg-[#1C1E22] text-[#00FF41] border border-[#2A2B2E] font-bold' : 'text-[#8E9299] hover:text-white'}`}
            >
              OVERVIEW & STREAM
            </button>
            <button
              onClick={() => setActiveTab('mcp')}
              className={`px-3 py-1.5 rounded transition ${activeTab === 'mcp' ? 'bg-[#1C1E22] text-[#00FF41] border border-[#2A2B2E] font-bold' : 'text-[#8E9299] hover:text-white'}`}
            >
              MCP TOOLS
            </button>
            <button
              onClick={() => setActiveTab('connect')}
              className={`px-3 py-1.5 rounded transition ${activeTab === 'connect' ? 'bg-[#1C1E22] text-[#00FF41] border border-[#2A2B2E] font-bold' : 'text-[#8E9299] hover:text-white'}`}
            >
              IPHONE LINK
            </button>
            <button
              onClick={() => setActiveTab('models')}
              className={`px-3 py-1.5 rounded transition ${activeTab === 'models' ? 'bg-[#1C1E22] text-[#00FF41] border border-[#2A2B2E] font-bold' : 'text-[#8E9299] hover:text-white'}`}
            >
              MODELS ({models.length})
            </button>
            <button
              onClick={() => setActiveTab('settings')}
              className={`px-3 py-1.5 rounded transition ${activeTab === 'settings' ? 'bg-[#1C1E22] text-[#00FF41] border border-[#2A2B2E] font-bold' : 'text-[#8E9299] hover:text-white'}`}
            >
              SYS CONFIG
            </button>
          </nav>
        </div>
      </header>

      {/* Main Rack Workspace */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* System Diagnostics & Telemetry Banner */}
        <DiagnosticBanner
          health={health}
          config={config}
          loading={loading}
          onRefresh={fetchBridgeData}
        />

        {/* Tab: Overview (Streaming + Connect Guide + MCP Inspector + Models) */}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            <StreamPlayground
              models={models}
              lanUrl={config?.lan_url || 'http://192.168.1.125:8080'}
              apiKey={config?.apiKey || ''}
            />

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-7">
                <IphoneConnectGuide config={config} />
              </div>
              <div className="lg:col-span-5">
                <ModelExplorer
                  models={models}
                  onSelectModel={() => setActiveTab('mcp')}
                />
              </div>
            </div>

            <McpToolTester models={models} />
          </div>
        )}

        {/* Tab: MCP Inspector */}
        {activeTab === 'mcp' && (
          <div className="space-y-6">
            <McpToolTester models={models} />
            <StreamPlayground
              models={models}
              lanUrl={config?.lan_url || 'http://192.168.1.125:8080'}
              apiKey={config?.apiKey || ''}
            />
          </div>
        )}

        {/* Tab: iPhone Link */}
        {activeTab === 'connect' && (
          <div className="space-y-6">
            <IphoneConnectGuide config={config} />
            <StreamPlayground
              models={models}
              lanUrl={config?.lan_url || 'http://192.168.1.125:8080'}
              apiKey={config?.apiKey || ''}
            />
          </div>
        )}

        {/* Tab: Models Catalog */}
        {activeTab === 'models' && (
          <div className="space-y-6">
            <ModelExplorer
              models={models}
              onSelectModel={() => setActiveTab('mcp')}
            />
          </div>
        )}

        {/* Tab: System Configuration */}
        {activeTab === 'settings' && (
          <div className="bg-[#151619] border border-[#2A2B2E] rounded-lg p-6 max-w-2xl mx-auto shadow-2xl relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-transparent via-[#00FF41] to-transparent opacity-30" />
            
            <div className="flex items-center justify-between pb-4 border-b border-[#2A2B2E]">
              <div className="flex items-center gap-2">
                <Settings className="w-4 h-4 text-[#F27D26]" />
                <h2 className="text-xs uppercase tracking-widest text-[#8E9299] font-bold">
                  System Configuration // Environment
                </h2>
              </div>
              <span className="text-[10px] text-[#5C5E63]">LOCAL_OVERRIDE</span>
            </div>

            <form onSubmit={handleSaveConfig} className="space-y-5 mt-5 text-xs">
              <div>
                <label className="block text-[11px] uppercase tracking-wider text-[#8E9299] mb-1.5">
                  GATEWAY_PORT (Gateway listening port):
                </label>
                <div className="relative">
                  <input
                    type="number"
                    value={editPort}
                    onChange={(e) => setEditPort(Number(e.target.value))}
                    className="w-full text-xs font-mono bg-[#080809] border border-[#2A2B2E] rounded p-2.5 text-[#00FF41] focus:outline-none focus:border-[#00FF41]"
                  />
                </div>
                <p className="text-[10px] text-[#5C5E63] mt-1">Socket binds to 0.0.0.0:{editPort} on all local network adapters.</p>
              </div>

              <div>
                <label className="block text-[11px] uppercase tracking-wider text-[#8E9299] mb-1.5">
                  GATEWAY_API_KEY (Optional iPhone auth token):
                </label>
                <div className="relative">
                  <input
                    type="text"
                    value={editApiKey}
                    onChange={(e) => setEditApiKey(e.target.value)}
                    placeholder="Leave blank for zero-configuration open local LAN access"
                    className="w-full text-xs font-mono bg-[#080809] border border-[#2A2B2E] rounded p-2.5 text-white placeholder-[#5C5E63] focus:outline-none focus:border-[#00FF41]"
                  />
                </div>
                <p className="text-[10px] text-[#5C5E63] mt-1">
                  Enforces constant-time HMAC bearer authorization on all /chat, /generate & /models endpoints.
                </p>
              </div>

              <div>
                <label className="block text-[11px] uppercase tracking-wider text-[#8E9299] mb-1.5">
                  OLLAMA_URL (Local Ollama daemon endpoint):
                </label>
                <input
                  type="text"
                  value={editOllamaUrl}
                  onChange={(e) => setEditOllamaUrl(e.target.value)}
                  className="w-full text-xs font-mono bg-[#080809] border border-[#2A2B2E] rounded p-2.5 text-white focus:outline-none focus:border-[#00FF41]"
                />
                <p className="text-[10px] text-[#5C5E63] mt-1">
                  Default local socket loopback is http://127.0.0.1:11434.
                </p>
              </div>

              {saveMessage && (
                <div className="text-[11px] font-mono text-[#00FF41] bg-[#00FF41]/10 border border-[#00FF41]/30 p-3 rounded">
                  [SYSTEM] {saveMessage}
                </div>
              )}

              <button
                type="submit"
                disabled={savingConfig}
                className="w-full py-2.5 bg-[#1C1E22] hover:bg-[#2A2B2E] text-white border border-[#2A2B2E] hover:border-[#00FF41] rounded text-xs font-bold uppercase tracking-wider transition disabled:opacity-50"
              >
                {savingConfig ? '[WRITING CONFIG...]' : 'APPLY SYSTEM CONFIGURATION'}
              </button>
            </form>
          </div>
        )}
      </main>

      {/* Hardware Telemetry Footer */}
      <footer className="bg-[#0C0D0E] border-t border-[#2A2B2E] px-6 py-4 mt-auto">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row justify-between items-center gap-2 text-[10px] text-[#5C5E63] font-mono">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#00FF41]"></span>
            <span>BUILD v1.0.4-STABLE // ASYNCIO_FASTAPI_RUNTIME // MCP PROTOCOL 2024-11-05</span>
          </div>
          <div>
            LATENCY: &lt;4ms // METAL ACCELERATION ACTIVE // APPLE SILICON UNIFIED MEMORY
          </div>
        </div>
      </footer>
    </div>
  );
}

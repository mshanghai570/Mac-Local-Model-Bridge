import React, { useState } from 'react';
import { Play, Code, CheckCircle, Terminal, RefreshCw, Layers } from 'lucide-react';
import { BridgeModel } from '../types';

interface Props {
  models: BridgeModel[];
}

export const McpToolTester: React.FC<Props> = ({ models }) => {
  const [selectedTool, setSelectedTool] = useState<string>('chat');
  const [selectedModel, setSelectedModel] = useState<string>(models[0]?.name || 'llama3.2:3b');
  const [promptInput, setPromptInput] = useState<string>('Why is running local AI on a Mac better for privacy?');
  const [systemPrompt, setSystemPrompt] = useState<string>('You are an expert AI assistant on Apple Silicon.');
  const [taskIdInput, setTaskIdInput] = useState<string>('task-001');
  const [loading, setLoading] = useState<boolean>(false);
  const [jsonRpcResponse, setJsonRpcResponse] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<'preview' | 'json'>('preview');

  const tools = [
    { id: 'list_models', label: 'list_models', desc: 'Query installed GGUF models' },
    { id: 'health', label: 'health', desc: 'Probe bridge & socket reachability' },
    { id: 'model_info', label: 'model_info', desc: 'Inspect parameters & context window' },
    { id: 'chat', label: 'chat', desc: 'Send multi-turn message payload' },
    { id: 'generate', label: 'generate', desc: 'Send raw text prompt for completion' },
    { id: 'stop', label: 'stop', desc: 'Cancel active task generation' },
  ];

  const executeMcpTool = async () => {
    setLoading(true);
    setJsonRpcResponse(null);

    let params: any = { name: selectedTool, arguments: {} };

    if (selectedTool === 'model_info') {
      params.arguments = { model: selectedModel };
    } else if (selectedTool === 'chat') {
      params.arguments = {
        model: selectedModel,
        messages: [{ role: 'user', content: promptInput }],
        system: systemPrompt,
      };
    } else if (selectedTool === 'generate') {
      params.arguments = {
        model: selectedModel,
        prompt: promptInput,
        system: systemPrompt,
      };
    } else if (selectedTool === 'stop') {
      params.arguments = { task_id: taskIdInput };
    }

    const payload = {
      jsonrpc: '2.0',
      id: Math.floor(Math.random() * 10000),
      method: 'tools/call',
      params,
    };

    try {
      const res = await fetch('/api/bridge/mcp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      setJsonRpcResponse(data);
    } catch (err: any) {
      setJsonRpcResponse({
        jsonrpc: '2.0',
        id: payload.id,
        error: { code: -32000, message: err.message },
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-[#151619] border border-[#2A2B2E] rounded-lg p-5 shadow-2xl relative overflow-hidden">
      <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-transparent via-[#F27D26] to-transparent opacity-30" />

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#2A2B2E]">
        <div className="flex items-center gap-2.5">
          <div className="w-2.5 h-2.5 rounded-full bg-[#F27D26] shadow-[0_0_8px_#F27D26]" />
          <div>
            <h2 className="text-xs uppercase tracking-widest text-[#8E9299] font-bold">
              MCP PROTOCOL INSPECTOR // TOOLS/CALL
            </h2>
            <p className="text-[11px] text-[#5C5E63] mt-0.5">
              Direct JSON-RPC 2.0 interface exposing MacBook inference tools to Claude Desktop & iOS clients.
            </p>
          </div>
        </div>
        <span className="text-[10px] text-[#5C5E63] uppercase tracking-wider font-mono">
          METHOD: tools/call
        </span>
      </div>

      {/* Tool Selector Buttons */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 mt-4">
        {tools.map((t) => (
          <button
            key={t.id}
            onClick={() => {
              setSelectedTool(t.id);
              setJsonRpcResponse(null);
            }}
            className={`p-2.5 rounded border text-left text-xs font-mono transition flex flex-col justify-between ${
              selectedTool === t.id
                ? 'bg-[#1C1E22] border-[#F27D26] text-white border-l-4'
                : 'bg-[#080809] border-[#2A2B2E] text-[#8E9299] hover:text-white hover:border-[#5C5E63]'
            }`}
          >
            <span className="font-bold text-[#F27D26]">{t.label}</span>
            <span className="text-[9px] text-[#5C5E63] mt-1 line-clamp-1">{t.desc}</span>
          </button>
        ))}
      </div>

      {/* Tool Argument Form */}
      <div className="bg-[#1C1E22] border border-[#2A2B2E] rounded p-4 mt-4 space-y-3 text-xs">
        {/* Model Selection */}
        {(selectedTool === 'chat' || selectedTool === 'generate' || selectedTool === 'model_info') && (
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-[#8E9299] mb-1">
              MODEL_PARAMETER:
            </label>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="w-full text-xs font-mono bg-[#080809] border border-[#2A2B2E] rounded p-2 text-white focus:outline-none focus:border-[#F27D26]"
            >
              {models.map((m) => (
                <option key={m.name} value={m.name} className="bg-[#151619] text-white">
                  {m.name} [{m.size_formatted} // {m.parameter_size || '3B'}]
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Prompt Input */}
        {(selectedTool === 'chat' || selectedTool === 'generate') && (
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-[#8E9299] mb-1">
              PROMPT_ARGUMENT:
            </label>
            <textarea
              rows={2}
              value={promptInput}
              onChange={(e) => setPromptInput(e.target.value)}
              className="w-full text-xs font-mono bg-[#080809] border border-[#2A2B2E] rounded p-2 text-white placeholder-[#5C5E63] focus:outline-none focus:border-[#F27D26] resize-none"
              placeholder="Type prompt payload..."
            />
          </div>
        )}

        {/* System Prompt */}
        {(selectedTool === 'chat' || selectedTool === 'generate') && (
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-[#8E9299] mb-1">
              SYSTEM_INSTRUCTIONS:
            </label>
            <input
              type="text"
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              className="w-full text-xs font-mono bg-[#080809] border border-[#2A2B2E] rounded p-2 text-white placeholder-[#5C5E63] focus:outline-none focus:border-[#F27D26]"
              placeholder="e.g. You are a fast on-device assistant"
            />
          </div>
        )}

        {/* Task ID for stop */}
        {selectedTool === 'stop' && (
          <div>
            <label className="block text-[10px] uppercase tracking-wider text-[#8E9299] mb-1">
              TASK_ID_ARGUMENT:
            </label>
            <input
              type="text"
              value={taskIdInput}
              onChange={(e) => setTaskIdInput(e.target.value)}
              className="w-full text-xs font-mono bg-[#080809] border border-[#2A2B2E] rounded p-2 text-white focus:outline-none focus:border-[#F27D26]"
            />
          </div>
        )}

        <div className="flex items-center justify-between pt-2">
          <span className="text-[10px] text-[#5C5E63]">
            DISPATCHES JSON-RPC 2.0 TO LOCAL MCP ROUTER
          </span>
          <button
            onClick={executeMcpTool}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-[#080809] hover:bg-[#2A2B2E] text-[#00FF41] border border-[#2A2B2E] hover:border-[#00FF41] rounded text-xs font-bold uppercase tracking-wider transition disabled:opacity-50"
          >
            {loading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
            {loading ? 'EXECUTING ON MAC...' : `INVOKE ${selectedTool.toUpperCase()}`}
          </button>
        </div>
      </div>

      {/* Response Panel */}
      {jsonRpcResponse && (
        <div className="mt-4 border border-[#2A2B2E] rounded overflow-hidden">
          <div className="flex items-center justify-between bg-[#151619] px-3 py-2 text-[10px] border-b border-[#2A2B2E]">
            <div className="flex items-center gap-2 text-[#00FF41]">
              <Terminal className="w-3.5 h-3.5" />
              <span>MCP RPC RESPONSE // ID: {jsonRpcResponse.id}</span>
            </div>
            <div className="flex items-center gap-1 bg-[#080809] p-0.5 rounded border border-[#2A2B2E]">
              <button
                onClick={() => setActiveTab('preview')}
                className={`px-2 py-0.5 rounded transition ${activeTab === 'preview' ? 'bg-[#1C1E22] text-white' : 'text-[#8E9299] hover:text-white'}`}
              >
                TEXT
              </button>
              <button
                onClick={() => setActiveTab('json')}
                className={`px-2 py-0.5 rounded transition ${activeTab === 'json' ? 'bg-[#1C1E22] text-[#00FF41]' : 'text-[#8E9299] hover:text-white'}`}
              >
                RAW JSON
              </button>
            </div>
          </div>

          <div className="p-4 bg-[#080809] text-[#D1D1D1] font-mono text-xs overflow-x-auto max-h-72 leading-relaxed">
            {activeTab === 'preview' ? (
              <pre className="whitespace-pre-wrap font-mono text-[11px] text-[#00FF41]">
                {jsonRpcResponse?.result?.content?.[0]?.text ||
                 jsonRpcResponse?.error?.message ||
                 JSON.stringify(jsonRpcResponse, null, 2)}
              </pre>
            ) : (
              <pre className="whitespace-pre-wrap font-mono text-[11px] text-[#00FF41]">
                {JSON.stringify(jsonRpcResponse, null, 2)}
              </pre>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

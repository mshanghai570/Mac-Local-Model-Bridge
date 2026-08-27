import express, { Request, Response } from 'express';
import path from 'path';
import { createServer as createViteServer } from 'vite';
import os from 'os';

async function startServer() {
  const app = express();
  const PORT = 3000;

  app.use(express.json({ limit: '10mb' }));

  // Helper to detect LAN IP
  function getLanIp(): string {
    const interfaces = os.networkInterfaces();
    for (const name of Object.keys(interfaces)) {
      for (const net of interfaces[name] || []) {
        if (net.family === 'IPv4' && !net.internal) {
          return net.address;
        }
      }
    }
    return '192.168.1.125';
  }

  // Simulated & Connected Bridge State for Interactive Control Panel
  let bridgeConfig = {
    host: '0.0.0.0',
    port: 8080,
    apiKey: '',
    provider: 'ollama',
    ollamaUrl: 'http://127.0.0.1:11434',
    lanIp: getLanIp(),
  };

  // Mock / Live models in the catalog
  let localModels = [
    {
      name: 'llama3.2:3b',
      size_bytes: 2019393189,
      size_formatted: '1.88 GB',
      modified_at: new Date(Date.now() - 3600000 * 24).toISOString(),
      digest: 'a80c4f172edd',
      format: 'gguf',
      family: 'llama',
      families: ['llama'],
      parameter_size: '3.2B',
      quantization_level: 'Q4_K_M',
      capabilities: ['chat', 'completion', 'tools'],
      details: { format: 'gguf', family: 'llama', parameter_size: '3.2B', quantization_level: 'Q4_K_M' }
    },
    {
      name: 'qwen2.5:7b',
      size_bytes: 4684534016,
      size_formatted: '4.36 GB',
      modified_at: new Date(Date.now() - 3600000 * 48).toISOString(),
      digest: 'b39e24a10c99',
      format: 'gguf',
      family: 'qwen2',
      families: ['qwen2'],
      parameter_size: '7.6B',
      quantization_level: 'Q4_K_M',
      capabilities: ['chat', 'completion', 'coding', 'tools'],
      details: { format: 'gguf', family: 'qwen2', parameter_size: '7.6B', quantization_level: 'Q4_K_M' }
    },
    {
      name: 'deepseek-r1:8b',
      size_bytes: 4920000000,
      size_formatted: '4.58 GB',
      modified_at: new Date(Date.now() - 3600000 * 12).toISOString(),
      digest: 'e17621aa90ff',
      format: 'gguf',
      family: 'deepseek',
      families: ['deepseek'],
      parameter_size: '8.0B',
      quantization_level: 'Q4_K_M',
      capabilities: ['chat', 'reasoning', 'coding'],
      details: { format: 'gguf', family: 'deepseek', parameter_size: '8.0B', quantization_level: 'Q4_K_M' }
    },
    {
      name: 'moondream:1.8b',
      size_bytes: 1800000000,
      size_formatted: '1.68 GB',
      modified_at: new Date(Date.now() - 3600000 * 72).toISOString(),
      digest: 'f72381bc5211',
      format: 'gguf',
      family: 'moondream',
      families: ['moondream', 'clip'],
      parameter_size: '1.8B',
      quantization_level: 'Q4_K_M',
      capabilities: ['chat', 'vision'],
      details: { format: 'gguf', family: 'moondream', parameter_size: '1.8B', quantization_level: 'Q4_K_M' }
    }
  ];

  // API Routes
  // 1. Health check
  app.get('/api/bridge/health', (req: Request, res: Response) => {
    res.json({
      status: 'ok',
      inference_backend_status: 'connected',
      backend_url: bridgeConfig.ollamaUrl,
      lan_ip: bridgeConfig.lanIp,
      port: bridgeConfig.port,
      bridge_url: `http://${bridgeConfig.lanIp}:${bridgeConfig.port}`,
      configured_provider: bridgeConfig.provider,
      backend_reachable: true,
      auth_enabled: !!bridgeConfig.apiKey,
      version: '1.0.0',
      message: 'Ollama v0.3.14 connected and ready (Apple Silicon M-series accelerated)'
    });
  });

  // 2. Get Config
  app.get('/api/bridge/config', (req: Request, res: Response) => {
    res.json({
      ...bridgeConfig,
      lan_url: `http://${bridgeConfig.lanIp}:${bridgeConfig.port}`
    });
  });

  // 3. Update Config
  app.post('/api/bridge/config', (req: Request, res: Response) => {
    const { host, port, apiKey, provider, ollamaUrl } = req.body;
    if (host !== undefined) bridgeConfig.host = host;
    if (port !== undefined) bridgeConfig.port = Number(port);
    if (apiKey !== undefined) bridgeConfig.apiKey = apiKey;
    if (provider !== undefined) bridgeConfig.provider = provider;
    if (ollamaUrl !== undefined) bridgeConfig.ollamaUrl = ollamaUrl;
    res.json({ success: true, config: bridgeConfig });
  });

  // 4. List Models
  app.get('/api/bridge/models', (req: Request, res: Response) => {
    res.json({ models: localModels, count: localModels.length });
  });

  // 5. Model Info
  app.get('/api/bridge/models/:name', (req: Request, res: Response) => {
    const name = decodeURIComponent(req.params.name);
    const model = localModels.find(m => m.name.toLowerCase() === name.toLowerCase());
    if (!model) {
      return res.status(404).json({ error: `Model '${name}' not found in local Ollama library.` });
    }
    res.json({
      name: model.name,
      modelfile: `FROM ${model.name}\nPARAMETER stop "<|eot_id|>"\nPARAMETER temperature 0.7`,
      parameters: 'stop <|eot_id|>\ntemperature 0.7\nnum_ctx 8192',
      template: '{{ if .System }}<|start_header_id|>system<|end_header_id|>\n\n{{ .System }}<|eot_id|>{{ end }}{{ if .Prompt }}<|start_header_id|>user<|end_header_id|>\n\n{{ .Prompt }}<|eot_id|>{{ end }}<|start_header_id|>assistant<|end_header_id|>\n\n',
      details: model.details,
      capabilities: model.capabilities
    });
  });

  // 6. Chat Endpoint with optional SSE Streaming
  app.post('/api/bridge/chat', async (req: Request, res: Response) => {
    const { model = 'llama3.2:3b', messages = [], temperature = 0.7, stream = false, tools = [] } = req.body;
    const userMsg = messages[messages.length - 1]?.content || 'Hello';

    if (stream || req.headers.accept === 'text/event-stream') {
      res.setHeader('Content-Type', 'text/event-stream');
      res.setHeader('Cache-Control', 'no-cache');
      res.setHeader('Connection', 'keep-alive');
      res.flushHeaders();

      const hasTools = Array.isArray(tools) && tools.length > 0;
      const lowerPrompt = userMsg.toLowerCase();
      const wantsFile = hasTools && (lowerPrompt.includes('read') || lowerPrompt.includes('file') || lowerPrompt.includes('list') || lowerPrompt.includes('directory'));

      if (hasTools && wantsFile) {
        const toolCallId = 'call_' + Math.random().toString(36).slice(2, 10);
        const toolName = lowerPrompt.includes('list') ? 'list_directory' : 'read_file';
        const fakePath = lowerPrompt.includes('project') || lowerPrompt.includes('code')
          ? '/Users/michaelshingara/Documents/remix-mac-local-ai-gateway-for-iphone'
          : '/tmp';

        const toolCallChunk = {
          model,
          role: 'assistant',
          content: null,
          tool_calls: [
            {
              id: toolCallId,
              type: 'function',
              function: {
                name: toolName,
                arguments: JSON.stringify({ path: fakePath })
              }
            }
          ],
          done: true,
          finish_reason: 'tool_calls'
        };

        res.write(`data: ${JSON.stringify(toolCallChunk)}\n\n`);
        res.write('data: [DONE]\n\n');
        res.end();
        return;
      }

      const sampleResponse = `[Mac Local Model: ${model}] Response streamed from local Ollama runtime to iPhone via Bridge:

Based on your prompt: "${userMsg.slice(0, 80)}..."

1. Local Inference on Mac: Zero network latency to external clouds, fully private.
2. Token Stream: Tokens delivered to iPhone via Server-Sent Events over Wi-Fi.
3. Memory & Hardware: Executing on Apple Silicon Unified Memory with Metal GPU acceleration.`;

      const words = sampleResponse.split(' ');
      for (let i = 0; i < words.length; i++) {
        const chunk = {
          model,
          role: 'assistant',
          content: words[i] + (i === words.length - 1 ? '' : ' '),
          done: i === words.length - 1,
          eval_count: i + 1,
          eval_duration: 15000000
        };
        res.write(`data: ${JSON.stringify(chunk)}\n\n`);
        await new Promise(resolve => setTimeout(resolve, 45));
      }
      res.write('data: [DONE]\n\n');
      res.end();
    } else {
      const hasTools = Array.isArray(tools) && tools.length > 0;
      const lowerPrompt = userMsg.toLowerCase();
      const wantsFile = hasTools && (lowerPrompt.includes('read') || lowerPrompt.includes('file') || lowerPrompt.includes('list') || lowerPrompt.includes('directory'));

      const response: any = {
        model,
        role: 'assistant',
        content: `[Mac Local Model: ${model}] Computed securely on your MacBook and returned over local Wi-Fi to your iPhone.`,
        done: true,
        total_duration: 420000000,
        eval_count: 32,
        eval_duration: 380000000
      };

      if (hasTools && wantsFile) {
        response.tool_calls = [
          {
            id: 'call_' + Math.random().toString(36).slice(2, 10),
            type: 'function',
            function: {
              name: lowerPrompt.includes('list') ? 'list_directory' : 'read_file',
              arguments: JSON.stringify({ path: '/tmp' })
            }
          }
        ];
        response.finish_reason = 'tool_calls';
        response.content = null;
      }

      res.json(response);
    }
  });

  // 6b. OpenAI-compatible /v1/chat/completions
  app.post('/v1/chat/completions', async (req: Request, res: Response) => {
    const { model = 'auto', messages = [], stream = false, tools = [] } = req.body;
    const userMsg = messages[messages.length - 1]?.content || 'Hello';

    if (stream) {
      res.setHeader('Content-Type', 'text/event-stream');
      res.setHeader('Cache-Control', 'no-cache');
      res.setHeader('Connection', 'keep-alive');
      res.flushHeaders();

      const hasTools = Array.isArray(tools) && tools.length > 0;
      const lowerPrompt = userMsg.toLowerCase();
      const wantsFile = hasTools && (lowerPrompt.includes('read') || lowerPrompt.includes('file') || lowerPrompt.includes('list') || lowerPrompt.includes('directory'));

      if (hasTools && wantsFile) {
        const toolCallId = 'call_' + Math.random().toString(36).slice(2, 10);
        const toolName = lowerPrompt.includes('list') ? 'list_directory' : 'read_file';
        const fakePath = lowerPrompt.includes('project') || lowerPrompt.includes('code')
          ? '/Users/michaelshingara/Documents/remix-mac-local-ai-gateway-for-iphone'
          : '/tmp';

        const chunk = {
          id: 'chatcmpl-' + Math.random().toString(36).slice(2, 14),
          object: 'chat.completion.chunk',
          created: Math.floor(Date.now() / 1000),
          model,
          choices: [
            {
              index: 0,
              delta: {
                role: 'assistant',
                content: null,
                tool_calls: [
                  {
                    id: toolCallId,
                    type: 'function',
                    function: {
                      name: toolName,
                      arguments: JSON.stringify({ path: fakePath })
                    }
                  }
                ]
              },
              finish_reason: 'tool_calls'
            }
          ]
        };

        res.write(`data: ${JSON.stringify(chunk)}\n\n`);
        res.write('data: [DONE]\n\n');
        res.end();
        return;
      }

      const sampleResponse = `Response from ${model}: ${userMsg.slice(0, 60)}...`;
      const words = sampleResponse.split(' ');
      const chunkId = 'chatcmpl-' + Math.random().toString(36).slice(2, 14);
      const created = Math.floor(Date.now() / 1000);

      res.write(`data: ${JSON.stringify({
        id: chunkId,
        object: 'chat.completion.chunk',
        created,
        model,
        choices: [{ index: 0, delta: { role: 'assistant', content: '' }, finish_reason: null }]
      })}\n\n`);

      for (let i = 0; i < words.length; i++) {
        const piece = words[i] + (i === words.length - 1 ? '' : ' ');
        res.write(`data: ${JSON.stringify({
          id: chunkId,
          object: 'chat.completion.chunk',
          created,
          model,
          choices: [{ index: 0, delta: { content: piece }, finish_reason: null }]
        })}\n\n`);
        await new Promise(resolve => setTimeout(resolve, 40));
      }

      res.write(`data: ${JSON.stringify({
        id: chunkId,
        object: 'chat.completion.chunk',
        created,
        model,
        choices: [{ index: 0, delta: {}, finish_reason: 'stop' }]
      })}\n\n`);
      res.write('data: [DONE]\n\n');
      res.end();
    } else {
      const hasTools = Array.isArray(tools) && tools.length > 0;
      const lowerPrompt = userMsg.toLowerCase();
      const wantsFile = hasTools && (lowerPrompt.includes('read') || lowerPrompt.includes('file') || lowerPrompt.includes('list') || lowerPrompt.includes('directory'));

      const response: any = {
        id: 'chatcmpl-' + Math.random().toString(36).slice(2, 14),
        object: 'chat.completion',
        created: Math.floor(Date.now() / 1000),
        model,
        choices: [
          {
            index: 0,
            message: {
              role: 'assistant',
              content: `[Mock] Response from ${model}: ${userMsg.slice(0, 80)}...`
            },
            finish_reason: 'stop'
          }
        ],
        usage: {
          prompt_tokens: userMsg.split(' ').length,
          completion_tokens: 32,
          total_tokens: userMsg.split(' ').length + 32
        }
      };

      if (hasTools && wantsFile) {
        response.choices[0].message = {
          role: 'assistant',
          content: null,
          tool_calls: [
            {
              id: 'call_' + Math.random().toString(36).slice(2, 10),
              type: 'function',
              function: {
                name: lowerPrompt.includes('list') ? 'list_directory' : 'read_file',
                arguments: JSON.stringify({ path: '/tmp' })
              }
            }
          ]
        };
        response.choices[0].finish_reason = 'tool_calls';
      }

      res.json(response);
    }
  });

  // 7. MCP JSON-RPC Handler
  app.post('/api/bridge/mcp', (req: Request, res: Response) => {
    const { id = 1, method, params = {} } = req.body;

    if (method === 'tools/list') {
      return res.json({
        jsonrpc: '2.0',
        id,
        result: {
          tools: [
            { name: 'list_models', description: 'List all AI models locally installed and running on the Mac inference backend (Ollama).', inputSchema: { type: 'object', properties: {} } },
            { name: 'health', description: 'Get bridge and inference backend health, LAN address, and network reachability.', inputSchema: { type: 'object', properties: {} } },
            { name: 'model_info', description: 'Get detailed metadata, parameter specifications, and template for a local model.', inputSchema: { type: 'object', properties: { model: { type: 'string' } }, required: ['model'] } },
            { name: 'chat', description: 'Send a conversational chat prompt to a local model running on Mac.', inputSchema: { type: 'object', properties: { model: { type: 'string' }, messages: { type: 'array' } }, required: ['model', 'messages'] } },
            { name: 'generate', description: 'Send a raw completion prompt to a local model on Mac.', inputSchema: { type: 'object', properties: { model: { type: 'string' }, prompt: { type: 'string' } }, required: ['model', 'prompt'] } },
            { name: 'stop', description: 'Cancel an active generation on the Mac backend.', inputSchema: { type: 'object', properties: { task_id: { type: 'string' } } } }
          ]
        }
      });
    }

    if (method === 'tools/call') {
      const toolName = params.name;
      const args = params.arguments || {};

      if (toolName === 'list_models') {
        return res.json({
          jsonrpc: '2.0',
          id,
          result: {
            content: [{ type: 'text', text: JSON.stringify({ models: localModels, count: localModels.length }, null, 2) }]
          }
        });
      }
      if (toolName === 'health') {
        return res.json({
          jsonrpc: '2.0',
          id,
          result: {
            content: [{
              type: 'text',
              text: JSON.stringify({
                status: 'ok',
                inference_backend_status: 'connected',
                backend_url: bridgeConfig.ollamaUrl,
                lan_ip: bridgeConfig.lanIp,
                port: bridgeConfig.port,
                bridge_url: `http://${bridgeConfig.lanIp}:${bridgeConfig.port}`,
                backend_reachable: true
              }, null, 2)
            }]
          }
        });
      }
      if (toolName === 'model_info') {
        const model = localModels.find(m => m.name === args.model) || localModels[0];
        return res.json({
          jsonrpc: '2.0',
          id,
          result: {
            content: [{ type: 'text', text: JSON.stringify(model, null, 2) }]
          }
        });
      }
      if (toolName === 'chat') {
        return res.json({
          jsonrpc: '2.0',
          id,
          result: {
            content: [{ type: 'text', text: `[MCP Chat Result from ${args.model || 'llama3.2:3b'}] Hello from your MacBook inference bridge!` }],
            meta: { model: args.model, eval_count: 18 }
          }
        });
      }
      if (toolName === 'generate') {
        return res.json({
          jsonrpc: '2.0',
          id,
          result: {
            content: [{ type: 'text', text: `[Raw Completion Result]: ${args.prompt || ''} -> Processed on Mac GPU.` }]
          }
        });
      }
      if (toolName === 'stop') {
        return res.json({
          jsonrpc: '2.0',
          id,
          result: {
            content: [{ type: 'text', text: JSON.stringify({ status: 'cancelled', task_id: args.task_id || 'active-task-1' }, null, 2) }]
          }
        });
      }

      return res.json({
        jsonrpc: '2.0',
        id,
        error: { code: -32601, message: `Tool '${toolName}' not recognized.` }
      });
    }

    res.json({
      jsonrpc: '2.0',
      id,
      result: { status: 'Mac Local Model Bridge MCP JSON-RPC Server 1.0.0' }
    });
  });

  // Vite middleware
  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Bridge Web Console running on http://0.0.0.0:${PORT}`);
  });
}

startServer();

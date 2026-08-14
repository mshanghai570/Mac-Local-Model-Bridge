"""
Embedded HTML/JS Web Dashboard for Local AI Gateway.
Zero-dependency, fast, mobile-friendly interface for testing local models from Safari on iPhone or Mac.
"""

def get_dashboard_html(lan_url: str, port: int, has_auth: bool = False, default_model: str = "llama3.2:3b", pairing_code: str = "------") -> str:
    auth_badge_class = "bg-emerald-100 text-emerald-800 border-emerald-300" if has_auth else "bg-amber-100 text-amber-900 border-amber-300"
    auth_status_text = "Bearer Auth Required" if has_auth else "Auth Disabled (Open Local LAN)"
    auth_hint_text = "Requests require Bearer token header" if has_auth else "Zero-configuration mode active. Set GATEWAY_API_KEY to enforce token authentication."

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Local AI Gateway</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%232563eb'><path d='M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5'/></svg>">
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/qrcode@1.5.3/build/qrcode.min.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
        body {{ font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif; }}
        code, pre {{ font-family: 'JetBrains Mono', monospace; }}
        .chat-bubble {{ max-width: 85%; word-break: break-word; }}
        ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
        ::-webkit-scrollbar-track {{ background: transparent; }}
        ::-webkit-scrollbar-thumb {{ background: #cbd5e1; border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: #94a3b8; }}
    </style>
</head>
<body class="bg-slate-50 text-slate-900 min-h-screen flex flex-col antialiased">
    <!-- Top Header -->
    <header class="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-xs">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <div class="flex items-center gap-3">
                <div class="w-9 h-9 rounded-xl bg-blue-600 flex items-center justify-center text-white shadow-sm font-bold text-lg">
                    ⚡
                </div>
                <div>
                    <div class="flex items-center gap-2">
                        <h1 class="font-bold text-slate-900 leading-tight">Local AI Gateway</h1>
                        <span id="health-badge" class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800">
                            <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1.5 animate-pulse"></span>
                            Online
                        </span>
                    </div>
                    <p class="text-xs text-slate-500 hidden sm:block">Apple Silicon Bridge for iPhone & Claude</p>
                </div>
            </div>

            <div class="flex items-center gap-2 sm:gap-3">
                <span class="hidden md:inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-medium border {auth_badge_class}" title="{auth_hint_text}">
                    🛡️ {auth_status_text}
                </span>
                <button onclick="openPairingModal()" class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs sm:text-sm font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 active:bg-slate-300 rounded-lg transition-colors">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0h.01M5 8h2a1 1 0 001-1V5a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1zm12 0h2a1 1 0 001-1V5a1 1 0 00-1-1h-2a1 1 0 00-1 1v2a1 1 0 001 1zM5 20h2a1 1 0 001-1v-2a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1z"/></svg>
                    <span>Pair iPhone</span>
                </button>
                <button onclick="refreshData()" class="p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors" title="Refresh Models & Metrics">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
                </button>
            </div>
        </div>
    </header>

    <!-- Main Workspace -->
    <main class="max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 flex-1 grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        <!-- Left Column: Chat Playground (7 cols) -->
        <section class="lg:col-span-7 flex flex-col bg-white border border-slate-200 rounded-2xl shadow-xs overflow-hidden h-[750px] max-h-[85vh]">
            <!-- Chat Header -->
            <div class="px-4 py-3 border-b border-slate-200 bg-slate-50 flex items-center justify-between gap-2">
                <div class="flex items-center gap-2 flex-1 min-w-0">
                    <label class="text-xs font-semibold text-slate-500 uppercase tracking-wider">Model:</label>
                    <select id="model-select" onchange="onModelChange()" class="bg-white border border-slate-300 text-slate-800 text-xs sm:text-sm rounded-lg px-2.5 py-1 font-medium focus:ring-2 focus:ring-blue-500 focus:outline-none truncate max-w-[220px]">
                        <option value="auto">auto (Adaptive Task Routing)</option>
                    </select>
                </div>
                <div class="flex items-center gap-2">
                    <button onclick="clearChat()" class="text-xs text-slate-500 hover:text-red-600 font-medium px-2 py-1 rounded transition-colors">
                        Clear Chat
                    </button>
                </div>
            </div>

            <!-- Messages Stream Area -->
            <div id="chat-messages" class="flex-1 p-4 overflow-y-auto space-y-4 bg-slate-50/50">
                <div class="flex items-start gap-3">
                    <div class="w-7 h-7 rounded-lg bg-blue-600 text-white flex items-center justify-center text-xs font-bold shrink-0">AI</div>
                    <div class="chat-bubble bg-white border border-slate-200 text-slate-800 rounded-2xl px-4 py-3 text-sm shadow-2xs">
                        <p class="font-medium text-slate-900 mb-1">Local AI Gateway is ready.</p>
                        <p class="text-slate-600 text-xs leading-relaxed">
                            Type a prompt below to stream responses directly from your Apple Silicon Mac with unified memory speed. Zero cloud transit, zero latency fees.
                        </p>
                    </div>
                </div>
            </div>

            <!-- Live Telemetry Status Bar -->
            <div id="telemetry-bar" class="px-4 py-1.5 bg-slate-100 border-t border-slate-200 text-xs text-slate-500 flex items-center justify-between font-mono">
                <span id="telemetry-ttft">TTFT: --</span>
                <span id="telemetry-tps">Speed: -- tok/s</span>
                <span id="telemetry-total">Tokens: 0</span>
            </div>

            <!-- Input Bar -->
            <div class="p-3 bg-white border-t border-slate-200">
                <form id="chat-form" onsubmit="handleSend(event)" class="flex gap-2">
                    <input type="text" id="chat-input" placeholder="Type a message (e.g. 'Write a Swift struct for a User model')..." class="flex-1 bg-slate-50 border border-slate-300 rounded-xl px-4 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:bg-white focus:ring-2 focus:ring-blue-500 focus:outline-none transition-all">
                    <button type="submit" id="send-btn" class="bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white font-semibold px-4 py-2.5 rounded-xl text-sm transition-colors flex items-center gap-1.5 shadow-xs">
                        <span>Send</span>
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"/></svg>
                    </button>
                    <button type="button" id="cancel-btn" onclick="cancelCurrentStream()" class="hidden bg-rose-600 hover:bg-rose-700 text-white font-semibold px-3 py-2.5 rounded-xl text-sm transition-colors">
                        Stop
                    </button>
                </form>
            </div>
        </section>

        <!-- Right Column: System Specs, Endpoints & Health (5 cols) -->
        <section class="lg:col-span-5 space-y-6">
            
            <!-- Connection & LAN Details Card -->
            <div class="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs space-y-4">
                <div class="flex items-center justify-between">
                    <h2 class="font-bold text-slate-900 text-sm">Connection Endpoints</h2>
                    <span class="text-xs font-mono bg-slate-100 text-slate-600 px-2 py-0.5 rounded">Port {port}</span>
                </div>
                
                <div class="space-y-2.5 text-xs font-mono">
                    <div>
                        <span class="text-slate-400 block mb-0.5 font-sans">LAN Gateway URL:</span>
                        <div class="flex items-center justify-between bg-slate-50 p-2 rounded-lg border border-slate-200">
                            <span class="text-blue-700 select-all font-semibold" id="lan-url-display">{lan_url}</span>
                            <button onclick="copyText('{lan_url}')" class="text-slate-400 hover:text-slate-600 text-xs uppercase font-sans font-semibold">Copy</button>
                        </div>
                    </div>
                    <div>
                        <span class="text-slate-400 block mb-0.5 font-sans">OpenAI v1 Endpoint:</span>
                        <div class="flex items-center justify-between bg-slate-50 p-2 rounded-lg border border-slate-200">
                            <span class="text-slate-700 select-all">{lan_url}/v1</span>
                            <button onclick="copyText('{lan_url}/v1')" class="text-slate-400 hover:text-slate-600 text-xs uppercase font-sans font-semibold">Copy</button>
                        </div>
                    </div>
                </div>

                <div class="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
                    <span>Authentication:</span>
                    <span class="font-semibold { 'text-emerald-600' if has_auth else 'text-amber-600' }">{ 'Enabled' if has_auth else 'Disabled (Open Local LAN)' }</span>
                </div>
                <div class="border-t border-slate-100 pt-2 flex items-center justify-between text-xs text-slate-500">
                    <span>Bonjour Discovery:</span>
                    <span class="font-semibold text-emerald-600">_local-ai-bridge._tcp</span>
                </div>
            </div>

            <!-- Installed Models Card -->
            <div class="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs space-y-4">
                <div class="flex items-center justify-between">
                    <h2 class="font-bold text-slate-900 text-sm">Installed Models</h2>
                    <span id="model-count-badge" class="text-xs font-bold bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full">0 Models</span>
                </div>

                <div id="models-list-container" class="space-y-2 max-h-52 overflow-y-auto pr-1">
                    <p class="text-xs text-slate-400 italic">Scanning local models...</p>
                </div>
            </div>

            <!-- Live Performance & Telemetry Card -->
            <div class="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs space-y-3">
                <h2 class="font-bold text-slate-900 text-sm">Gateway Performance</h2>
                <div class="grid grid-cols-2 gap-3 text-center">
                    <div class="bg-slate-50 border border-slate-200/80 rounded-xl p-2.5">
                        <span class="text-xs text-slate-500 block">Avg Generation Speed</span>
                        <span id="metric-avg-tps" class="text-base font-bold text-slate-900">-- tok/s</span>
                    </div>
                    <div class="bg-slate-50 border border-slate-200/80 rounded-xl p-2.5">
                        <span class="text-xs text-slate-500 block">Avg First Token (TTFT)</span>
                        <span id="metric-avg-ttft" class="text-base font-bold text-slate-900">-- ms</span>
                    </div>
                    <div class="bg-slate-50 border border-slate-200/80 rounded-xl p-2.5">
                        <span class="text-xs text-slate-500 block">Total Requests</span>
                        <span id="metric-total-reqs" class="text-base font-bold text-slate-900">0</span>
                    </div>
                    <div class="bg-slate-50 border border-slate-200/80 rounded-xl p-2.5">
                        <span class="text-xs text-slate-500 block">Active Concurrency</span>
                        <span id="metric-active-reqs" class="text-base font-bold text-slate-900">0 / 1</span>
                    </div>
                </div>
            </div>

        </section>
    </main>

    <!-- Pairing QR Modal -->
    <div id="pairing-modal" class="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4 hidden">
        <div class="bg-white rounded-3xl max-w-sm w-full p-6 shadow-2xl space-y-5 text-center">
            <div class="w-12 h-12 rounded-2xl bg-blue-100 text-blue-600 flex items-center justify-center mx-auto text-2xl">
                📱
            </div>
            <div>
                <h3 class="text-lg font-bold text-slate-900">Pair iPhone</h3>
                <p class="text-xs text-slate-500 mt-1">Scan this QR code with your iPhone camera to connect to the local inference gateway.</p>
            </div>

            <div class="bg-slate-50 p-4 rounded-2xl border border-slate-200 inline-block mx-auto shadow-inner">
                <div id="qrcode-canvas" class="flex justify-center"></div>
            </div>

            <div class="bg-blue-50 border border-blue-100 rounded-xl p-3 text-left space-y-1">
                <span class="text-xs font-bold text-blue-900 block">Pairing Code:</span>
                <span id="pairing-code-display" class="font-mono text-base font-bold text-blue-700 tracking-wider">{pairing_code}</span>
            </div>

            <div class="flex gap-2">
                <button onclick="closePairingModal()" class="flex-1 bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold py-2.5 rounded-xl text-sm transition-colors">
                    Done
                </button>
            </div>
        </div>
    </div>

    <!-- Client Script -->
    <script>
        let currentAbortController = null;
        let currentRequestId = null;

        async function init() {{
            await refreshData();
            setInterval(refreshMetrics, 3000);
        }}

        async function refreshData() {{
            await Promise.all([loadModels(), refreshMetrics()]);
        }}

        async function loadModels() {{
            try {{
                const res = await fetch('/models');
                const data = await res.json();
                const select = document.getElementById('model-select');
                const listContainer = document.getElementById('models-list-container');
                const countBadge = document.getElementById('model-count-badge');
                
                select.innerHTML = '<option value="auto">auto (Adaptive Task Routing)</option>';
                listContainer.innerHTML = '';

                if (data.models && data.models.length > 0) {{
                    countBadge.textContent = `${{data.models.length}} Models`;
                    data.models.forEach(m => {{
                        const opt = document.createElement('option');
                        opt.value = m.name;
                        opt.textContent = `${{m.name}} (${{m.size_formatted}})`;
                        if (m.name === '{default_model}') opt.selected = true;
                        select.appendChild(opt);

                        const card = document.createElement('div');
                        card.className = 'p-2.5 rounded-xl border border-slate-200 bg-slate-50/70 hover:bg-white transition-colors flex items-center justify-between text-xs';
                        card.innerHTML = `
                            <div>
                                <span class="font-bold text-slate-800 block">${{m.name}}</span>
                                <span class="text-slate-500 font-mono text-[11px]">${{m.parameter_size || m.family || 'Model'}} • ${{m.size_formatted}}</span>
                            </div>
                            <div class="flex gap-1">
                                ${{m.capabilities && m.capabilities.vision ? '<span class="px-1.5 py-0.5 rounded bg-purple-100 text-purple-700 font-bold text-[10px]">Vision</span>' : ''}}
                                ${{m.capabilities && m.capabilities.tools ? '<span class="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 font-bold text-[10px]">Tools</span>' : ''}}
                            </div>
                        `;
                        listContainer.appendChild(card);
                    }});
                }} else {{
                    countBadge.textContent = '0 Models';
                    listContainer.innerHTML = '<p class="text-xs text-amber-600">No models detected. Run "ollama pull {default_model}" on your Mac.</p>';
                }}
            }} catch (e) {{
                console.error('Error loading models:', e);
            }}
        }}

        async function refreshMetrics() {{
            try {{
                const res = await fetch('/metrics');
                if (!res.ok) return;
                const data = await res.json();
                document.getElementById('metric-avg-tps').textContent = `${{data.avg_tokens_per_sec || 0}} tok/s`;
                document.getElementById('metric-avg-ttft').textContent = `${{data.avg_ttft_ms || 0}} ms`;
                document.getElementById('metric-total-reqs').textContent = data.total_requests || 0;
                document.getElementById('metric-active-reqs').textContent = `${{data.active_requests || 0}} / ${{data.max_concurrent_limit || 1}}`;
            }} catch (e) {{}}
        }}

        async function handleSend(e) {{
            e.preventDefault();
            const input = document.getElementById('chat-input');
            const prompt = input.value.trim();
            if (!prompt) return;

            input.value = '';
            appendMessage('user', prompt);

            const model = document.getElementById('model-select').value;
            const assistantBubble = appendMessage('assistant', '<span class="text-slate-400 italic">Thinking...</span>');
            
            document.getElementById('send-btn').classList.add('hidden');
            document.getElementById('cancel-btn').classList.remove('hidden');

            currentAbortController = new AbortController();
            currentRequestId = 'req_' + Math.random().toString(36).substring(2, 10);

            const startTime = performance.now();
            let firstTokenTime = null;
            let tokenCount = 0;
            let fullText = '';

            try {{
                const res = await fetch('/chat', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        model: model,
                        messages: [{{ role: 'user', content: prompt }}],
                        stream: true,
                        request_id: currentRequestId
                    }}),
                    signal: currentAbortController.signal
                }});

                const reader = res.body.getReader();
                const decoder = new TextDecoder('utf-8');
                let buffer = '';

                while (true) {{
                    const {{ value, done }} = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, {{ stream: true }});
                    const lines = buffer.split('\\n');
                    buffer = lines.pop();

                    for (const line of lines) {{
                        if (line.startsWith('data: ')) {{
                            const payloadStr = line.slice(6).trim();
                            if (payloadStr === '[DONE]') continue;
                            try {{
                                const chunk = JSON.parse(payloadStr);
                                if (chunk.content) {{
                                    if (!firstTokenTime) {{
                                        firstTokenTime = performance.now();
                                        const ttft = (firstTokenTime - startTime).toFixed(0);
                                        document.getElementById('telemetry-ttft').textContent = `TTFT: ${{ttft}}ms`;
                                        assistantBubble.innerHTML = '';
                                    }}
                                    tokenCount++;
                                    fullText += chunk.content;
                                    assistantBubble.textContent = fullText;

                                    const elapsed = (performance.now() - startTime) / 1000;
                                    const tps = (tokenCount / Math.max(0.1, elapsed)).toFixed(1);
                                    document.getElementById('telemetry-tps').textContent = `Speed: ${{tps}} tok/s`;
                                    document.getElementById('telemetry-total').textContent = `Tokens: ${{tokenCount}}`;
                                }}
                            }} catch (err) {{}}
                        }}
                    }}
                }}
            }} catch (err) {{
                if (err.name !== 'AbortError') {{
                    assistantBubble.innerHTML = `<span class="text-rose-600">Error: ${{err.message}}</span>`;
                }}
            }} finally {{
                document.getElementById('send-btn').classList.remove('hidden');
                document.getElementById('cancel-btn').classList.add('hidden');
                currentAbortController = null;
                refreshMetrics();
            }}
        }}

        function cancelCurrentStream() {{
            if (currentAbortController) {{
                currentAbortController.abort();
            }}
            if (currentRequestId) {{
                fetch('/cancel', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ request_id: currentRequestId }})
                }}).catch(() => {{}});
            }}
        }}

        function appendMessage(role, htmlContent) {{
            const chatContainer = document.getElementById('chat-messages');
            const row = document.createElement('div');
            row.className = `flex items-start gap-3 ${{role === 'user' ? 'justify-end' : ''}}`;

            if (role === 'assistant') {{
                row.innerHTML = `
                    <div class="w-7 h-7 rounded-lg bg-blue-600 text-white flex items-center justify-center text-xs font-bold shrink-0">AI</div>
                    <div class="chat-bubble bg-white border border-slate-200 text-slate-800 rounded-2xl px-4 py-3 text-sm shadow-2xs">
                        <div class="message-content whitespace-pre-wrap">${{htmlContent}}</div>
                    </div>
                `;
            }} else {{
                row.innerHTML = `
                    <div class="chat-bubble bg-blue-600 text-white rounded-2xl px-4 py-2.5 text-sm shadow-2xs">
                        <div class="message-content whitespace-pre-wrap">${{htmlContent}}</div>
                    </div>
                    <div class="w-7 h-7 rounded-lg bg-slate-200 text-slate-700 flex items-center justify-center text-xs font-bold shrink-0">ME</div>
                `;
            }}
            chatContainer.appendChild(row);
            chatContainer.scrollTop = chatContainer.scrollHeight;
            return row.querySelector('.message-content');
        }}

        function clearChat() {{
            document.getElementById('chat-messages').innerHTML = '';
        }}

        async function openPairingModal() {{
            const modal = document.getElementById('pairing-modal');
            modal.classList.remove('hidden');
            try {{
                const res = await fetch('/pair');
                const data = await res.json();
                document.getElementById('pairing-code-display').textContent = data.pairing_code;
                
                const qrContainer = document.getElementById('qrcode-canvas');
                qrContainer.innerHTML = '';
                if (window.QRCode) {{
                    const qrUrl = `${{data.lan_url}}/?code=${{data.pairing_code}}`;
                    QRCode.toCanvas(qrUrl, {{ width: 180, margin: 1 }}, function (err, canvas) {{
                        if (!err) qrContainer.appendChild(canvas);
                    }});
                }}
            }} catch (e) {{}}
        }}

        function closePairingModal() {{
            document.getElementById('pairing-modal').classList.add('hidden');
        }}

        function copyText(text) {{
            navigator.clipboard.writeText(text);
        }}

        function onModelChange() {{}}

        window.onload = init;
    </script>
</body>
</html>"""

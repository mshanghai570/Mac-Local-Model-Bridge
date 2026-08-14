export interface BridgeModel {
  name: string;
  size_bytes: number;
  size_formatted: string;
  modified_at: string;
  digest: string;
  format?: string;
  family?: string;
  families?: string[];
  parameter_size?: string;
  quantization_level?: string;
  capabilities: string[];
  details?: Record<string, any>;
}

export interface BridgeHealth {
  status: string;
  inference_backend_status: string;
  backend_url: string;
  lan_ip: string;
  port: number;
  bridge_url: string;
  configured_provider: string;
  backend_reachable: boolean;
  auth_enabled: boolean;
  version: string;
  message?: string;
}

export interface BridgeConfigState {
  host: string;
  port: number;
  apiKey: string;
  provider: string;
  ollamaUrl: string;
  lanIp: string;
  lan_url?: string;
}

export interface StreamMetric {
  tokenCount: number;
  durationMs: number;
  tokensPerSec: number;
  firstTokenMs: number;
}

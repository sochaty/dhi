/**
 * DhiClient — single point of entry for all HTTP calls to the Dhi server.
 *
 * Architecture rule (see ARCHITECTURE.md):
 *   Providers and panels MUST NOT call fetch() directly.
 *   All HTTP goes through this class.
 *
 * DhiClient has no VS Code dependency — it is a plain HTTP client. The caller
 * (extension.ts) is responsible for reading the serverUrl from VS Code config
 * and passing it as a getter so the value is always fresh.
 */

export interface CompleteRequest {
  file_path: string;
  prefix: string;
  suffix: string;
  language: string;
}

export interface CompleteResponse {
  completion: string;
}

export interface IndexRequest {
  file_path: string;
  content: string;
  language: string;
}

export interface IndexResponse {
  indexed: number;
}

export interface HealthResponse {
  status: string;
}

export class DhiClient {
  constructor(
    private readonly getServerUrl: () => string = () => 'http://localhost:8000',
  ) {}

  private get baseUrl(): string {
    return this.getServerUrl();
  }

  async health(): Promise<HealthResponse> {
    return this._get<HealthResponse>('/health');
  }

  async complete(req: CompleteRequest, signal?: AbortSignal): Promise<CompleteResponse> {
    return this._post<CompleteResponse>('/complete', req, signal);
  }

  async index(req: IndexRequest): Promise<IndexResponse> {
    return this._post<IndexResponse>('/index', req);
  }

  private async _get<T>(path: string): Promise<T> {
    const resp = await fetch(`${this.baseUrl}${path}`);
    if (!resp.ok) {
      const body = await resp.text();
      throw new Error(`Dhi server ${resp.status}: ${body}`);
    }
    return resp.json() as Promise<T>;
  }

  private async _post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
    const resp = await fetch(`${this.baseUrl}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`Dhi server ${resp.status}: ${text}`);
    }
    return resp.json() as Promise<T>;
  }
}

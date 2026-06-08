/**
 * DhiClient — single point of entry for all HTTP calls to the Dhi server.
 *
 * Architecture rule (see ARCHITECTURE.md):
 *   Providers and panels MUST NOT call fetch() directly.
 *   All HTTP goes through this class.
 */

import * as vscode from 'vscode';

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
}

export interface IndexResponse {
  indexed: number;
}

export interface HealthResponse {
  status: string;
}

export class DhiClient {
  private get baseUrl(): string {
    return vscode.workspace
      .getConfiguration('dhi')
      .get<string>('serverUrl', 'http://localhost:8000');
  }

  async health(): Promise<HealthResponse> {
    return this._get<HealthResponse>('/health');
  }

  async complete(req: CompleteRequest): Promise<CompleteResponse> {
    return this._post<CompleteResponse>('/complete', req);
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

  private async _post<T>(path: string, body: unknown): Promise<T> {
    const resp = await fetch(`${this.baseUrl}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`Dhi server ${resp.status}: ${text}`);
    }
    return resp.json() as Promise<T>;
  }
}

/**
 * Unit tests for DhiClient.
 *
 * DhiClient has no VS Code dependency — it is a pure HTTP client that accepts
 * a URL getter. These tests run under plain Mocha with no extension host and
 * no vscode mock required.
 */

import * as assert from 'assert';
import * as sinon from 'sinon';
import { DhiClient } from './index';

// ── Helpers ───────────────────────────────────────────────────────────────────

function mockFetch(response: { ok: boolean; status?: number; json?: () => unknown; text?: string }) {
  return sinon.stub(global, 'fetch').resolves({
    ok: response.ok,
    status: response.status ?? (response.ok ? 200 : 500),
    json: response.json ? sinon.stub().resolves(response.json()) : sinon.stub().resolves({}),
    text: sinon.stub().resolves(response.text ?? ''),
  } as unknown as Response);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('DhiClient', () => {
  const client = new DhiClient(() => 'http://localhost:9999');

  afterEach(() => sinon.restore());

  describe('health()', () => {
    it('calls GET /health and returns parsed JSON', async () => {
      const stub = mockFetch({ ok: true, json: () => ({ status: 'ok' }) });
      const result = await client.health();
      assert.deepStrictEqual(result, { status: 'ok' });
      sinon.assert.calledOnce(stub);
      const url = stub.firstCall.args[0] as string;
      assert.ok(url.endsWith('/health'), `expected /health, got ${url}`);
    });

    it('throws on non-ok response', async () => {
      mockFetch({ ok: false, status: 503, text: 'service unavailable' });
      await assert.rejects(client.health(), /503/);
    });
  });

  describe('complete()', () => {
    const req = {
      file_path: '/repo/foo.py',
      prefix: 'def foo():\n    ',
      suffix: '\n    return x',
      language: 'python',
    };

    it('sends POST /complete with JSON body', async () => {
      const stub = mockFetch({ ok: true, json: () => ({ completion: '    x = 1' }) });
      const result = await client.complete(req);
      assert.strictEqual(result.completion, '    x = 1');
      const url = stub.firstCall.args[0] as string;
      assert.ok(url.endsWith('/complete'));
      const init = stub.firstCall.args[1] as RequestInit;
      assert.strictEqual(init.method, 'POST');
      assert.deepStrictEqual(JSON.parse(init.body as string), req);
    });

    it('throws when server returns 500', async () => {
      mockFetch({ ok: false, status: 500, text: 'internal error' });
      await assert.rejects(client.complete(req), /500/);
    });
  });

  describe('index()', () => {
    it('sends POST /index and returns indexed count', async () => {
      mockFetch({ ok: true, json: () => ({ indexed: 4 }) });
      const result = await client.index({ file_path: '/repo/module.py', content: 'def f(): pass', language: 'python' });
      assert.strictEqual(result.indexed, 4);
    });

    it('throws on 404 response', async () => {
      mockFetch({ ok: false, status: 404, text: 'not found' });
      await assert.rejects(client.index({ file_path: '/missing.py', content: '', language: 'python' }), /404/);
    });
  });

  describe('chat()', () => {
    function mockStream(lines: string[]): sinon.SinonStub {
      const encoder = new TextEncoder();
      const chunks = lines.map(l => encoder.encode(l));
      let i = 0;
      const reader = {
        read: async () => i < chunks.length
          ? { done: false, value: chunks[i++] }
          : { done: true, value: undefined },
        releaseLock: () => {},
      };
      return sinon.stub(global, 'fetch').resolves({
        ok: true,
        status: 200,
        body: { getReader: () => reader },
      } as unknown as Response);
    }

    it('yields tokens from SSE stream', async () => {
      mockStream([
        'data: {"token": "Hello"}\n\n',
        'data: {"token": " world"}\n\n',
        'data: [DONE]\n\n',
      ]);
      const tokens: string[] = [];
      for await (const t of client.chat({ message: 'hi' })) {
        tokens.push(t);
      }
      assert.deepStrictEqual(tokens, ['Hello', ' world']);
    });

    it('stops iteration on [DONE] sentinel', async () => {
      mockStream([
        'data: {"token": "A"}\n\ndata: [DONE]\n\ndata: {"token": "B"}\n\n',
      ]);
      const tokens: string[] = [];
      for await (const t of client.chat({ message: 'hi' })) {
        tokens.push(t);
      }
      assert.deepStrictEqual(tokens, ['A']);
    });

    it('throws when server returns non-ok response', async () => {
      sinon.stub(global, 'fetch').resolves({
        ok: false,
        status: 503,
        body: null,
        text: async () => 'busy',
      } as unknown as Response);
      await assert.rejects(async () => {
        for await (const _ of client.chat({ message: 'hi' })) { /* drain */ }
      }, /503/);
    });

    it('sends POST /chat with correct body', async () => {
      const stub = mockStream(['data: [DONE]\n\n']);
      for await (const _ of client.chat({ message: 'explain', file_path: '/a.py' })) { /* drain */ }
      const init = stub.firstCall.args[1] as RequestInit;
      const body = JSON.parse(init.body as string) as { message: string; file_path: string };
      assert.strictEqual(body.message, 'explain');
      assert.strictEqual(body.file_path, '/a.py');
    });
  });
});

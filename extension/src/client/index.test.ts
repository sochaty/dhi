/**
 * Unit tests for DhiClient.
 *
 * The VS Code API is stubbed out — these tests run under plain Mocha
 * without an actual extension host.
 */

import * as assert from 'assert';
import * as sinon from 'sinon';

// ── VS Code stub ──────────────────────────────────────────────────────────────
// DhiClient reads workspace configuration at call time. We stub vscode before
// importing the module under test so the require cache sees the stub.

const vscodeStub = {
  workspace: {
    getConfiguration: sinon.stub().returns({
      get: sinon.stub().callsFake((key: string, def: unknown) => {
        if (key === 'serverUrl') return 'http://localhost:9999';
        return def;
      }),
    }),
  },
};

// Replace the real vscode module with our stub in the require cache.
require.cache['vscode'] = { id: 'vscode', filename: 'vscode', loaded: true, exports: vscodeStub } as NodeJS.Module;

import { DhiClient } from './index';

// ── Helpers ───────────────────────────────────────────────────────────────────

function mockFetch(response: { ok: boolean; status?: number; json?: () => unknown; text?: string }) {
  const stub = sinon.stub(global, 'fetch').resolves({
    ok: response.ok,
    status: response.status ?? (response.ok ? 200 : 500),
    json: response.json ? sinon.stub().resolves(response.json()) : sinon.stub().resolves({}),
    text: sinon.stub().resolves(response.text ?? ''),
  } as unknown as Response);
  return stub;
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('DhiClient', () => {
  afterEach(() => sinon.restore());

  describe('health()', () => {
    it('calls GET /health and returns parsed JSON', async () => {
      const stub = mockFetch({ ok: true, json: () => ({ status: 'ok' }) });
      const client = new DhiClient();
      const result = await client.health();
      assert.deepStrictEqual(result, { status: 'ok' });
      sinon.assert.calledOnce(stub);
      const url = stub.firstCall.args[0] as string;
      assert.ok(url.endsWith('/health'), `expected /health, got ${url}`);
    });

    it('throws on non-ok response', async () => {
      mockFetch({ ok: false, status: 503, text: 'service unavailable' });
      const client = new DhiClient();
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
      const client = new DhiClient();
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
      const client = new DhiClient();
      await assert.rejects(client.complete(req), /500/);
    });
  });

  describe('index()', () => {
    it('sends POST /index and returns indexed count', async () => {
      mockFetch({ ok: true, json: () => ({ indexed: 4 }) });
      const client = new DhiClient();
      const result = await client.index({ file_path: '/repo/module.py' });
      assert.strictEqual(result.indexed, 4);
    });

    it('throws on 404 response', async () => {
      mockFetch({ ok: false, status: 404, text: 'not found' });
      const client = new DhiClient();
      await assert.rejects(client.index({ file_path: '/missing.py' }), /404/);
    });
  });
});

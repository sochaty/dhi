/**
 * Unit tests for FIMCompletionProvider.
 *
 * The VS Code API is provided by the global mock installed in
 * test/vscode-stub.cjs via Mocha's --require flag (runs before ts-node).
 * workspace.getConfiguration is overridden per-test through the configValues
 * map so debounce=0 and completionEnabled can be toggled without timers.
 */

import * as assert from 'assert';
import * as sinon from 'sinon';
import * as vscode from 'vscode'; // resolves to the global mock from test/vscode-stub.cjs
import { FIMCompletionProvider } from './provider';

// vscode.workspace is typed as a namespace in @types/vscode, but at test
// runtime it is our plain mock object — cast once here to allow reassignment.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ws = vscode.workspace as any;

// Controls what workspace.getConfiguration().get() returns for each test.
// completionDebounceMs=0 prevents real 150 ms timer waits.
const configValues: Record<string, unknown> = {
  completionDebounceMs: 0,
  completionEnabled: true,
};

let origGetConfig: unknown;

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeDocument(languageId: string, text: string) {
  return {
    languageId,
    uri: { fsPath: '/repo/foo.py' },
    getText: sinon.stub().callsFake((range?: unknown) => {
      if (!range) return text;
      const r = range as { start: { line: number; character: number } };
      if (r.start.line === 0 && r.start.character === 0) {
        return text.split('\n')[0] + '\n';
      }
      return text.split('\n').slice(1).join('\n');
    }),
    positionAt: sinon.stub().returns(new vscode.Position(99, 0)),
  };
}

function makeCancelToken(cancelled = false) {
  return {
    isCancellationRequested: cancelled,
    onCancellationRequested: (listener: () => void) => {
      // If already cancelled, fire the listener immediately so the debounce
      // Promise resolves(false) before the setTimeout fires.
      if (cancelled) listener();
      return { dispose: () => {} };
    },
  };
}

function makeClient(completion: string | null) {
  const stub: { complete: sinon.SinonStub } = { complete: sinon.stub() };
  if (completion === null) {
    stub.complete.rejects(new Error('network error'));
  } else {
    stub.complete.resolves({ completion });
  }
  return stub;
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('FIMCompletionProvider', () => {
  beforeEach(() => {
    configValues['completionEnabled'] = true;
    origGetConfig = ws.getConfiguration;
    ws.getConfiguration = () => ({
      get: (key: string, def: unknown) =>
        key in configValues ? configValues[key] : def,
    });
  });

  afterEach(() => {
    ws.getConfiguration = origGetConfig;
    sinon.restore();
  });

  it('returns completion item for supported language', async () => {
    const client = makeClient('    x = 1');
    const provider = new FIMCompletionProvider(client as never);
    const doc = makeDocument('python', 'def foo():\n    return x\n');
    const pos = new vscode.Position(1, 0);

    const result = await provider.provideInlineCompletionItems(
      doc as never,
      pos as never,
      {} as never,
      makeCancelToken() as never,
    );

    assert.ok(result != null && 'items' in result);
    const list = result as { items: Array<{ insertText: string }> };
    assert.strictEqual(list.items[0].insertText, '    x = 1');
  });

  it('returns null for unsupported language', async () => {
    const client = makeClient('irrelevant');
    const provider = new FIMCompletionProvider(client as never);
    const doc = makeDocument('json', '{}');
    const pos = new vscode.Position(0, 0);

    const result = await provider.provideInlineCompletionItems(
      doc as never,
      pos as never,
      {} as never,
      makeCancelToken() as never,
    );

    assert.strictEqual(result, null);
    sinon.assert.notCalled(client.complete);
  });

  it('returns null when completionEnabled is false', async () => {
    configValues['completionEnabled'] = false;
    const client = makeClient('whatever');
    const provider = new FIMCompletionProvider(client as never);
    const doc = makeDocument('python', 'x = 1');
    const pos = new vscode.Position(0, 5);

    const result = await provider.provideInlineCompletionItems(
      doc as never,
      pos as never,
      {} as never,
      makeCancelToken() as never,
    );

    assert.strictEqual(result, null);
  });

  it('returns null when cancellation is requested', async () => {
    const client = makeClient('x');
    const provider = new FIMCompletionProvider(client as never);
    const doc = makeDocument('typescript', 'const x = ');
    const pos = new vscode.Position(0, 10);

    const result = await provider.provideInlineCompletionItems(
      doc as never,
      pos as never,
      {} as never,
      makeCancelToken(true) as never,
    );

    assert.strictEqual(result, null);
  });

  it('returns null on client network error', async () => {
    const client = makeClient(null);
    const provider = new FIMCompletionProvider(client as never);
    const doc = makeDocument('python', 'import os\n');
    const pos = new vscode.Position(1, 0);

    const result = await provider.provideInlineCompletionItems(
      doc as never,
      pos as never,
      {} as never,
      makeCancelToken() as never,
    );

    assert.strictEqual(result, null);
  });

  it('returns null when completion is whitespace-only', async () => {
    const client = makeClient('   \n  ');
    const provider = new FIMCompletionProvider(client as never);
    const doc = makeDocument('python', 'x = ');
    const pos = new vscode.Position(0, 4);

    const result = await provider.provideInlineCompletionItems(
      doc as never,
      pos as never,
      {} as never,
      makeCancelToken() as never,
    );

    assert.strictEqual(result, null);
  });

  it('calls client.complete with correct arguments', async () => {
    const client = makeClient('1');
    const provider = new FIMCompletionProvider(client as never);
    const doc = makeDocument('typescript', 'const x = 1;\n');
    doc.uri = { fsPath: '/project/index.ts' } as never;
    const pos = new vscode.Position(1, 0);

    await provider.provideInlineCompletionItems(
      doc as never,
      pos as never,
      {} as never,
      makeCancelToken() as never,
    );

    sinon.assert.calledOnce(client.complete);
    const args = client.complete.firstCall.args[0];
    assert.strictEqual(args.file_path, '/project/index.ts');
    assert.strictEqual(args.language, 'typescript');
  });
});

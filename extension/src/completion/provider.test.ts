/**
 * Unit tests for FIMCompletionProvider.
 *
 * The VS Code API and DhiClient are stubbed — no extension host needed.
 */

import * as assert from 'assert';
import * as sinon from 'sinon';

// ── VS Code stub ──────────────────────────────────────────────────────────────

class FakePosition {
  constructor(public line: number, public character: number) {}
}

class FakeRange {
  constructor(public start: FakePosition, public end: FakePosition) {}
}

class FakeInlineCompletionItem {
  constructor(public insertText: string, public range: FakeRange) {}
}

class FakeInlineCompletionList {
  constructor(public items: FakeInlineCompletionItem[]) {}
}

const configValues: Record<string, unknown> = {
  completionDebounceMs: 0, // 0 ms so tests don't need real timers
  completionEnabled: true,
  serverUrl: 'http://localhost:9999',
};

const vscodeStub = {
  workspace: {
    getConfiguration: sinon.stub().returns({
      get: sinon.stub().callsFake((key: string, def: unknown) =>
        key in configValues ? configValues[key] : def,
      ),
    }),
  },
  InlineCompletionList: FakeInlineCompletionList,
  InlineCompletionItem: FakeInlineCompletionItem,
  Range: FakeRange,
  Position: FakePosition,
  languages: {
    registerInlineCompletionItemProvider: sinon.stub(),
  },
};

require.cache['vscode'] = {
  id: 'vscode',
  filename: 'vscode',
  loaded: true,
  exports: vscodeStub,
} as NodeJS.Module;

import { FIMCompletionProvider } from './provider';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeDocument(languageId: string, text: string) {
  return {
    languageId,
    uri: { fsPath: '/repo/foo.py' },
    getText: sinon.stub().callsFake((range?: FakeRange) => {
      if (!range) return text;
      if (range.start.line === 0 && range.start.character === 0) {
        return text.split('\n')[0] + '\n';
      }
      return text.split('\n').slice(1).join('\n');
    }),
    positionAt: sinon.stub().returns(new FakePosition(99, 0)),
  };
}

function makeCancelToken(cancelled = false) {
  return { isCancellationRequested: cancelled };
}

function makeClient(completion: string | null) {
  const stub: { complete: sinon.SinonStub; health?: sinon.SinonStub; index?: sinon.SinonStub } = {
    complete: sinon.stub(),
  };
  if (completion === null) {
    stub.complete.rejects(new Error('network error'));
  } else {
    stub.complete.resolves({ completion });
  }
  return stub;
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('FIMCompletionProvider', () => {
  afterEach(() => sinon.restore());

  it('returns completion item for supported language', async () => {
    const client = makeClient('    x = 1');
    const provider = new FIMCompletionProvider(client as never);
    const doc = makeDocument('python', 'def foo():\n    return x\n');
    const pos = new FakePosition(1, 0);

    const result = await provider.provideInlineCompletionItems(
      doc as never,
      pos as never,
      {} as never,
      makeCancelToken() as never,
    );

    assert.ok(result instanceof FakeInlineCompletionList);
    assert.strictEqual((result as FakeInlineCompletionList).items[0].insertText, '    x = 1');
  });

  it('returns null for unsupported language', async () => {
    const client = makeClient('irrelevant');
    const provider = new FIMCompletionProvider(client as never);
    const doc = makeDocument('json', '{}');
    const pos = new FakePosition(0, 0);

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
    const pos = new FakePosition(0, 5);

    try {
      const result = await provider.provideInlineCompletionItems(
        doc as never,
        pos as never,
        {} as never,
        makeCancelToken() as never,
      );
      assert.strictEqual(result, null);
    } finally {
      configValues['completionEnabled'] = true;
    }
  });

  it('returns null when cancellation is requested', async () => {
    const client = makeClient('x');
    const provider = new FIMCompletionProvider(client as never);
    const doc = makeDocument('typescript', 'const x = ');
    const pos = new FakePosition(0, 10);

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
    const pos = new FakePosition(1, 0);

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
    const pos = new FakePosition(0, 4);

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
    const pos = new FakePosition(1, 0);

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

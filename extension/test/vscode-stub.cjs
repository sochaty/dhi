/**
 * Mocha setup file — loaded via --require BEFORE ts-node processes any test file.
 *
 * Patches Module._resolveFilename so that require('vscode') resolves to the
 * string 'vscode' (instead of throwing MODULE_NOT_FOUND), then installs a
 * comprehensive stub into require.cache['vscode'].
 *
 * Tests that need specific behaviour can use sinon to stub individual methods
 * on the exported mock object.
 */

'use strict';

const Module = require('module');
const origResolve = Module._resolveFilename;

// Make 'vscode' resolvable without it being in node_modules
Module._resolveFilename = function (request, parent, isMain, options) {
  if (request === 'vscode') return 'vscode';
  return origResolve.call(this, request, parent, isMain, options);
};

class FakePosition {
  constructor(line, character) {
    this.line = line;
    this.character = character;
  }
}

class FakeRange {
  constructor(start, end) {
    this.start = start;
    this.end = end;
  }
}

class FakeInlineCompletionItem {
  constructor(insertText, range) {
    this.insertText = insertText;
    this.range = range;
  }
}

class FakeInlineCompletionList {
  constructor(items) {
    this.items = items;
  }
}

class FakeThemeColor {
  constructor(id) {
    this.id = id;
  }
}

const vscodeExports = {
  workspace: {
    getConfiguration: () => ({ get: (_key, defaultValue) => defaultValue }),
    workspaceFolders: [],
    findFiles: async () => [],
    onDidChangeConfiguration: () => ({ dispose: () => {} }),
  },
  window: {
    createOutputChannel: (_name) => ({
      appendLine: () => {},
      append: () => {},
      show: () => {},
      hide: () => {},
      clear: () => {},
      dispose: () => {},
    }),
    createStatusBarItem: () => ({
      text: '',
      tooltip: '',
      backgroundColor: undefined,
      show: () => {},
      dispose: () => {},
    }),
    showInformationMessage: () => Promise.resolve(),
    showWarningMessage: () => Promise.resolve(),
    withProgress: async (_opts, fn) => fn({ report: () => {} }),
    createWebviewPanel: () => ({
      webview: { html: '' },
      onDidDispose: (_cb) => {},
      reveal: () => {},
    }),
  },
  commands: {
    registerCommand: () => ({ dispose: () => {} }),
  },
  languages: {
    registerInlineCompletionItemProvider: () => ({ dispose: () => {} }),
  },
  // Enums
  StatusBarAlignment: { Left: 1, Right: 2 },
  ProgressLocation: { Notification: 15, Window: 10, SourceControl: 1 },
  ViewColumn: { Active: -1, Beside: -2, One: 1 },
  // Classes
  ThemeColor: FakeThemeColor,
  Position: FakePosition,
  Range: FakeRange,
  InlineCompletionItem: FakeInlineCompletionItem,
  InlineCompletionList: FakeInlineCompletionList,
  Uri: {
    file: (p) => ({ fsPath: p, scheme: 'file' }),
    parse: (s) => ({ fsPath: s, scheme: 'file' }),
  },
  EventEmitter: class EventEmitter {
    constructor() { this.event = () => {}; }
    fire() {}
    dispose() {}
  },
};

require.cache['vscode'] = {
  id: 'vscode',
  filename: 'vscode',
  loaded: true,
  exports: vscodeExports,
  children: [],
  paths: [],
};

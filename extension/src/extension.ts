/**
 * VS Code extension entry point for Dhi.
 *
 * Registers:
 *  - FIM InlineCompletionItemProvider (all supported languages)
 *  - Command: dhi.openChat
 *  - Command: dhi.indexWorkspace
 *  - Status bar item (server connectivity indicator)
 */

import * as vscode from 'vscode';
import { DhiClient } from './client';
import { FIMCompletionProvider } from './completion/provider';
import { ChatPanel } from './chat/panel';

let statusBar: vscode.StatusBarItem;

export function activate(context: vscode.ExtensionContext): void {
  const client = new DhiClient(() =>
    vscode.workspace.getConfiguration('dhi').get<string>('serverUrl', 'http://localhost:8000'),
  );

  // ── Status bar ────────────────────────────────────────────────────────────
  statusBar = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Right,
    100,
  );
  statusBar.text = '$(loading~spin) Dhi';
  statusBar.tooltip = 'Dhi — checking server connection…';
  statusBar.show();
  context.subscriptions.push(statusBar);

  _pingServer(client);

  // ── Inline completion provider ────────────────────────────────────────────
  const provider = new FIMCompletionProvider(client);
  const providerDisposable = vscode.languages.registerInlineCompletionItemProvider(
    { pattern: '**' },
    provider,
  );
  context.subscriptions.push(providerDisposable);

  // ── Commands ──────────────────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('dhi.openChat', () => {
      ChatPanel.show(context, client);
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('dhi.indexWorkspace', async () => {
      const folders = vscode.workspace.workspaceFolders;
      if (!folders?.length) {
        vscode.window.showWarningMessage('Dhi: No workspace folder open.');
        return;
      }

      let total = 0;
      await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: 'Dhi: Indexing workspace…' },
        async (progress) => {
          const files = await vscode.workspace.findFiles(
            '**/*.{py,ts,tsx,js,jsx,go,rs,java}',
            '**/node_modules/**',
          );
          for (const file of files) {
            try {
              const result = await client.index({ file_path: file.fsPath });
              total += result.indexed;
              progress.report({ message: `${file.fsPath} (${result.indexed} chunks)` });
            } catch {
              // Skip files that fail to index (binary, too large, etc.)
            }
          }
        },
      );

      vscode.window.showInformationMessage(`Dhi: Indexed ${total} chunks.`);
    }),
  );
}

export function deactivate(): void {
  statusBar?.dispose();
}

async function _pingServer(client: DhiClient): Promise<void> {
  try {
    await client.health();
    statusBar.text = '$(check) Dhi';
    statusBar.tooltip = 'Dhi — server connected';
    statusBar.backgroundColor = undefined;
  } catch {
    statusBar.text = '$(warning) Dhi offline';
    statusBar.tooltip = 'Dhi — cannot reach server. Check dhi.serverUrl in settings.';
    statusBar.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
  }
}

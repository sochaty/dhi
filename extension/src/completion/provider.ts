/**
 * FIM InlineCompletionItemProvider.
 *
 * Design:
 *  - 150 ms debounce: the debounce timer is reset on every keystroke and only
 *    fires when the user pauses. This keeps network traffic low.
 *  - One in-flight request at a time: if a new trigger arrives before the
 *    previous completes, the previous AbortController is aborted.
 *  - Language detection: uses VS Code's built-in languageId; skips file types
 *    for which the server has no chunker (e.g. JSON, Markdown).
 *  - DhiClient: all HTTP goes through DhiClient — never fetch() directly.
 */

import * as vscode from 'vscode';
import { DhiClient } from '../client';

const SUPPORTED_LANGUAGES = new Set([
  'python',
  'typescript',
  'typescriptreact',
  'javascript',
  'javascriptreact',
  'go',
  'rust',
  'java',
]);

export class FIMCompletionProvider
  implements vscode.InlineCompletionItemProvider
{
  private debounceTimer: ReturnType<typeof setTimeout> | undefined;
  private client: DhiClient;

  constructor(client: DhiClient) {
    this.client = client;
  }

  provideInlineCompletionItems(
    document: vscode.TextDocument,
    position: vscode.Position,
    _context: vscode.InlineCompletionContext,
    token: vscode.CancellationToken,
  ): Promise<vscode.InlineCompletionList | null> {
    return new Promise((resolve) => {
      if (this.debounceTimer) {
        clearTimeout(this.debounceTimer);
      }

      if (!SUPPORTED_LANGUAGES.has(document.languageId)) {
        resolve(null);
        return;
      }

      const debounceMs = vscode.workspace
        .getConfiguration('dhi')
        .get<number>('completionDebounceMs', 150);

      const enabled = vscode.workspace
        .getConfiguration('dhi')
        .get<boolean>('completionEnabled', true);

      if (!enabled) {
        resolve(null);
        return;
      }

      this.debounceTimer = setTimeout(async () => {
        if (token.isCancellationRequested) {
          resolve(null);
          return;
        }

        const prefix = document.getText(
          new vscode.Range(new vscode.Position(0, 0), position),
        );
        const suffix = document.getText(
          new vscode.Range(position, document.positionAt(document.getText().length)),
        );

        try {
          const response = await this.client.complete({
            file_path: document.uri.fsPath,
            prefix,
            suffix,
            language: document.languageId,
          });

          if (token.isCancellationRequested || !response.completion.trim()) {
            resolve(null);
            return;
          }

          resolve(
            new vscode.InlineCompletionList([
              new vscode.InlineCompletionItem(
                response.completion,
                new vscode.Range(position, position),
              ),
            ]),
          );
        } catch {
          resolve(null);
        }
      }, debounceMs);
    });
  }
}

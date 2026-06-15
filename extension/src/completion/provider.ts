/**
 * FIM InlineCompletionItemProvider — async / CancellationToken pattern.
 *
 * VS Code cancels the previous call's token on every keystroke, so we use
 * that token as our debounce mechanism: wait 150 ms inside the Promise; if
 * the token is cancelled first (user typed again), bail immediately.  No
 * cache, no inlineSuggest.trigger, no in-flight flag needed.
 */

import * as vscode from 'vscode';
import { DhiClient } from '../client';
import { log } from '../extension';

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
  private client: DhiClient;

  constructor(client: DhiClient) {
    this.client = client;
  }

  async provideInlineCompletionItems(
    document: vscode.TextDocument,
    position: vscode.Position,
    _context: vscode.InlineCompletionContext,
    token: vscode.CancellationToken,
  ): Promise<vscode.InlineCompletionList | null> {
    if (!SUPPORTED_LANGUAGES.has(document.languageId)) {
      return null;
    }

    const cfg = vscode.workspace.getConfiguration('dhi');
    if (!cfg.get<boolean>('completionEnabled', true)) {
      return null;
    }

    log.appendLine(
      `[provider] pos=${position.line}:${position.character} lang=${document.languageId}`,
    );

    // Debounce via CancellationToken.
    // VS Code cancels the previous call's token each time the user types,
    // so this timer is automatically cleared without any extra bookkeeping.
    const debounceMs = cfg.get<number>('completionDebounceMs', 150);
    const debounced = await new Promise<boolean>((resolve) => {
      const t = setTimeout(() => resolve(true), debounceMs);
      token.onCancellationRequested(() => {
        clearTimeout(t);
        resolve(false);
      });
    });

    if (!debounced || token.isCancellationRequested) {
      return null;
    }

    log.appendLine(`[fetch] starting at ${position.line}:${position.character}`);

    // Tie an AbortController to the token so the HTTP request is cancelled
    // when the user starts typing again.
    const controller = new AbortController();
    const disposable = token.onCancellationRequested(() => controller.abort());

    try {
      const prefix = document.getText(
        new vscode.Range(new vscode.Position(0, 0), position),
      );
      const suffix = document.getText(
        new vscode.Range(
          position,
          document.positionAt(document.getText().length),
        ),
      );

      log.appendLine(
        `[fetch] prefix tail: "${prefix.slice(-40).replace(/\n/g, '\\n')}"`,
      );

      const response = await this.client.complete(
        {
          file_path: document.uri.fsPath,
          prefix,
          suffix,
          language: document.languageId,
        },
        controller.signal,
      );

      if (token.isCancellationRequested) {
        log.appendLine('[fetch] cancelled after response — discarding');
        return null;
      }

      log.appendLine(`[fetch] response: "${response.completion}"`);

      if (!response.completion.trim()) {
        return null;
      }

      return new vscode.InlineCompletionList([
        new vscode.InlineCompletionItem(
          response.completion,
          new vscode.Range(position, position),
        ),
      ]);
    } catch (err: unknown) {
      const isAbort =
        (err as { name?: string })?.name === 'AbortError' ||
        token.isCancellationRequested;
      if (isAbort) {
        log.appendLine('[fetch] aborted');
        return null;
      }
      log.appendLine(`[fetch] error: ${err}`);
      return null;
    } finally {
      disposable.dispose();
    }
  }
}

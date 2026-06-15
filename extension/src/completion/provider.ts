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

    // Only fetch at semantically meaningful positions — not mid-word.
    // A fetch at position 10:1 (user typed "d" in "def") would grab the Ollama
    // lock for ~7 seconds, making every subsequent fetch return "".
    const prefix = document.getText(
      new vscode.Range(new vscode.Position(0, 0), position),
    );
    const lastChar = prefix[prefix.length - 1] ?? '';
    const triggerChars = new Set([' ', '\t', '\n', '{', ':', '.']);
    if (lastChar !== '' && !triggerChars.has(lastChar)) {
      return null;
    }

    log.appendLine(
      `[provider] pos=${position.line}:${position.character} lang=${document.languageId}`,
    );

    // Debounce via CancellationToken.
    // VS Code cancels the previous call's token each time the user types,
    // so this timer is automatically cleared without any extra bookkeeping.
    // 400 ms prevents firing during bursts of keystrokes (e.g. typing a
    // function signature); still short enough to feel responsive on a pause.
    const debounceMs = cfg.get<number>('completionDebounceMs', 400);
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
      const suffix = document.getText(
        new vscode.Range(
          position,
          document.positionAt(document.getText().length),
        ),
      );

      log.appendLine(
        `[fetch] prefix tail: "${prefix.slice(-40).replace(/\n/g, '\\n')}"`,
      );

      const reqBody = {
        file_path: document.uri.fsPath,
        prefix,
        suffix,
        language: document.languageId,
      };

      // Fetch, with a single retry when the server is busy (503).
      // The lock on the server is held while Ollama generates; an early fetch
      // (fired mid-typing) can hold it for several seconds.  Waiting 2 s and
      // retrying once lets the lock release before we give up.
      let response = await this.client.complete(reqBody, controller.signal).catch(
        async (firstErr: unknown) => {
          const isBusy = String((firstErr as { message?: string }).message ?? '').includes('503');
          if (!isBusy) throw firstErr;

          log.appendLine('[fetch] server busy — retrying in 2 s');
          const waited = await new Promise<boolean>((resolve) => {
            const t = setTimeout(() => resolve(true), 2000);
            token.onCancellationRequested(() => { clearTimeout(t); resolve(false); });
          });
          if (!waited || token.isCancellationRequested) return null;
          return this.client.complete(reqBody, controller.signal);
        },
      );

      if (token.isCancellationRequested) {
        log.appendLine('[fetch] cancelled after response — discarding');
        return null;
      }

      if (!response || !response.completion.trim()) {
        log.appendLine(`[fetch] response: "${response?.completion ?? '(null)'}"`);
        return null;
      }

      log.appendLine(`[fetch] response: "${response.completion}"`);

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

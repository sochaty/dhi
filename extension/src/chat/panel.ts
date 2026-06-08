/**
 * Chat panel stub — implemented in Post 3 of the Dhi series.
 *
 * Post 3 title: "Building the Chat Panel: Context Assembly, Token Slots,
 * and Streaming Code Diff Preview"
 */

import * as vscode from 'vscode';
import { DhiClient } from '../client';

export class ChatPanel {
  private static instance: ChatPanel | undefined;

  static show(context: vscode.ExtensionContext, client: DhiClient): void {
    if (!ChatPanel.instance) {
      ChatPanel.instance = new ChatPanel(context, client);
    }
    ChatPanel.instance.panel.reveal();
  }

  private readonly panel: vscode.WebviewPanel;

  private constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly _client: DhiClient,
  ) {
    this.panel = vscode.window.createWebviewPanel(
      'dhiChat',
      'Dhi Chat',
      vscode.ViewColumn.Beside,
      { enableScripts: false },
    );
    this.panel.webview.html = this._placeholder();
    this.panel.onDidDispose(() => {
      ChatPanel.instance = undefined;
    });
  }

  private _placeholder(): string {
    return `<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;padding:2rem;color:#ccc;">
  <h2>Dhi Chat</h2>
  <p>Coming in Post 3 of the Dhi series.</p>
</body>
</html>`;
  }
}

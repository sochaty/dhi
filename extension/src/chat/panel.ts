/**
 * Dhi Chat Panel — VS Code Webview with SSE streaming.
 *
 * Architecture (see ARCHITECTURE.md):
 *   All HTTP goes through DhiClient (extension host), never from the webview.
 *   The webview sends `{type:'chat.send', data:{message}}` to the host.
 *   The host streams tokens back as `{type:'chat.token', data:token}`.
 *   The host signals completion with `{type:'chat.done'}`.
 */

import * as crypto from 'crypto';
import * as vscode from 'vscode';
import { type ChatMessage, DhiClient } from '../client';

const MAX_HISTORY_MESSAGES = 8; // 4 turns × 2 messages

export class ChatPanel {
  private static instance: ChatPanel | undefined;

  static show(context: vscode.ExtensionContext, client: DhiClient): void {
    if (ChatPanel.instance) {
      ChatPanel.instance._panel.reveal();
      return;
    }
    ChatPanel.instance = new ChatPanel(context, client);
  }

  private readonly _panel: vscode.WebviewPanel;
  private readonly _client: DhiClient;
  private _history: ChatMessage[] = [];
  private _abortController: AbortController | undefined;
  // activeTextEditor becomes undefined when a webview gains focus;
  // track the last real editor so file context is always available.
  private _lastEditor: vscode.TextEditor | undefined;

  private constructor(context: vscode.ExtensionContext, client: DhiClient) {
    this._client = client;
    this._lastEditor = vscode.window.activeTextEditor;
    vscode.window.onDidChangeActiveTextEditor(
      (editor) => { if (editor) this._lastEditor = editor; },
      undefined,
      context.subscriptions,
    );
    this._panel = vscode.window.createWebviewPanel(
      'dhiChat',
      'Dhi Chat',
      vscode.ViewColumn.Beside,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
      },
    );

    const nonce = crypto.randomBytes(16).toString('hex');
    this._panel.webview.html = this._buildHtml(nonce);

    this._panel.webview.onDidReceiveMessage(
      (msg: { type: string; data?: { message: string } }) => {
        if (msg.type === 'chat.send' && msg.data?.message) {
          void this._handleMessage(msg.data.message);
        } else if (msg.type === 'chat.clear') {
          this._abortController?.abort();
          this._history = [];
          void this._panel.webview.postMessage({ type: 'chat.cleared' });
        }
      },
      undefined,
      context.subscriptions,
    );

    this._panel.onDidDispose(() => {
      this._abortController?.abort();
      ChatPanel.instance = undefined;
    });
  }

  private async _handleMessage(message: string): Promise<void> {
    this._abortController?.abort();
    this._abortController = new AbortController();

    const editor = this._lastEditor;
    const req = {
      message,
      file_path: editor?.document.uri.fsPath ?? '',
      language: editor?.document.languageId ?? '',
      file_content: editor?.document.getText() ?? '',
      history: this._history.slice(-MAX_HISTORY_MESSAGES),
    };

    let fullResponse = '';
    try {
      for await (const token of this._client.chat(req, this._abortController.signal)) {
        fullResponse += token;
        void this._panel.webview.postMessage({ type: 'chat.token', data: token });
      }
      this._history.push(
        { role: 'user', content: message },
        { role: 'assistant', content: fullResponse },
      );
      void this._panel.webview.postMessage({ type: 'chat.done' });
    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        void this._panel.webview.postMessage({ type: 'chat.error', data: err.message });
      }
    }
  }

  private _buildHtml(nonce: string): string {
    return /* html */ `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy"
    content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
  <title>Dhi Chat</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{
      font-family:var(--vscode-font-family,sans-serif);
      font-size:var(--vscode-font-size,13px);
      color:var(--vscode-editor-foreground);
      background:var(--vscode-editor-background);
      display:flex;flex-direction:column;height:100vh;overflow:hidden
    }
    #messages{
      flex:1;overflow-y:auto;padding:12px;
      display:flex;flex-direction:column;gap:10px
    }
    .msg{
      max-width:94%;padding:8px 12px;border-radius:6px;
      line-height:1.6;word-break:break-word
    }
    .msg.user{
      align-self:flex-end;
      background:var(--vscode-button-background);
      color:var(--vscode-button-foreground);
      white-space:pre-wrap
    }
    .msg.assistant{
      align-self:flex-start;
      background:var(--vscode-textBlockQuote-background,rgba(127,127,127,0.1));
      border-left:3px solid var(--vscode-textLink-foreground)
    }
    .msg.assistant p{margin:4px 0}
    .msg.assistant pre{
      background:var(--vscode-textCodeBlock-background,rgba(0,0,0,0.25));
      padding:10px;border-radius:4px;overflow-x:auto;margin:6px 0;
      font-family:var(--vscode-editor-font-family,monospace);font-size:0.9em
    }
    .msg.assistant code{
      font-family:var(--vscode-editor-font-family,monospace);
      background:var(--vscode-textCodeBlock-background,rgba(0,0,0,0.2));
      padding:1px 4px;border-radius:3px;font-size:0.9em
    }
    .msg.assistant pre code{background:none;padding:0}
    .msg.assistant strong{font-weight:600}
    .cursor{
      display:inline-block;width:2px;height:1em;
      background:var(--vscode-editor-foreground);
      animation:blink 1s step-end infinite;vertical-align:text-bottom;margin-left:1px
    }
    @keyframes blink{50%{opacity:0}}
    #empty{
      flex:1;display:flex;flex-direction:column;
      align-items:center;justify-content:center;
      opacity:0.45;gap:6px;text-align:center;padding:24px
    }
    #empty p{font-size:0.9em}
    #input-area{
      padding:8px;
      border-top:1px solid var(--vscode-panel-border,rgba(127,127,127,0.3));
      display:flex;gap:6px
    }
    #input{
      flex:1;
      background:var(--vscode-input-background);
      color:var(--vscode-input-foreground);
      border:1px solid var(--vscode-input-border,transparent);
      border-radius:4px;padding:6px 8px;
      font-family:inherit;font-size:inherit;resize:none;outline:none
    }
    #input:focus{border-color:var(--vscode-focusBorder)}
    #send{
      background:var(--vscode-button-background);
      color:var(--vscode-button-foreground);
      border:none;border-radius:4px;padding:6px 14px;
      cursor:pointer;font-family:inherit;font-size:inherit;align-self:flex-end
    }
    #send:hover{background:var(--vscode-button-hoverBackground)}
    #send:disabled{opacity:0.45;cursor:not-allowed}
    #toolbar{
      display:flex;justify-content:flex-end;padding:4px 8px;
      border-bottom:1px solid var(--vscode-panel-border,rgba(127,127,127,0.3))
    }
    #clear{
      background:none;border:none;
      color:var(--vscode-descriptionForeground);
      font-family:inherit;font-size:0.85em;
      cursor:pointer;padding:2px 6px;border-radius:3px;opacity:0.7
    }
    #clear:hover{opacity:1;background:var(--vscode-toolbar-hoverBackground)}
  </style>
</head>
<body>
  <div id="toolbar">
    <button id="clear">New Chat</button>
  </div>
  <div id="messages">
    <div id="empty">
      <p><strong>Dhi Chat</strong></p>
      <p>Ask about your code. The active editor file is sent automatically as context.</p>
      <p>Enter to send · Shift+Enter for a new line.</p>
    </div>
  </div>
  <div id="input-area">
    <textarea id="input" rows="3" placeholder="Ask about your code…"></textarea>
    <button id="send">Send</button>
  </div>
  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    const messagesEl = document.getElementById('messages');
    const inputEl    = document.getElementById('input');
    const sendBtn    = document.getElementById('send');
    const emptyEl    = document.getElementById('empty');
    const clearBtn   = document.getElementById('clear');

    let currentEl  = null;   // the streaming assistant bubble
    let rawContent = '';     // accumulated text for the current response
    let busy       = false;

    // ── Markdown renderer (subset) ────────────────────────────────────────────
    function escape(s) {
      return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }
    function renderMd(text) {
      // fenced code blocks
      text = text.replace(/\`\`\`(\\w*)\\n([\\s\\S]*?)\`\`\`/g, (_, lang, code) =>
        '<pre><code>' + escape(code.trimEnd()) + '</code></pre>'
      );
      // inline code
      text = text.replace(/\`([^\`\\n]+)\`/g, (_, c) => '<code>' + escape(c) + '</code>');
      // bold
      text = text.replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>');
      // paragraphs
      return text.split(/\\n\\n+/).map(p => '<p>' + p.replace(/\\n/g,'<br>') + '</p>').join('');
    }

    // ── DOM helpers ───────────────────────────────────────────────────────────
    function addUserBubble(text) {
      emptyEl.style.display = 'none';
      const el = document.createElement('div');
      el.className = 'msg user';
      el.textContent = text;
      messagesEl.appendChild(el);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function startAssistantBubble() {
      emptyEl.style.display = 'none';
      currentEl  = document.createElement('div');
      currentEl.className = 'msg assistant';
      currentEl.innerHTML = '<span class="cursor"></span>';
      rawContent = '';
      messagesEl.appendChild(currentEl);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function appendToken(token) {
      if (!currentEl) return;
      rawContent += token;
      currentEl.innerHTML = renderMd(rawContent) + '<span class="cursor"></span>';
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function finishResponse() {
      if (currentEl) {
        currentEl.innerHTML = renderMd(rawContent);
        currentEl = null;
      }
      busy = false;
      sendBtn.disabled = false;
      inputEl.focus();
    }

    function showError(msg) {
      if (currentEl) {
        currentEl.innerHTML = '<span style="color:var(--vscode-errorForeground)">Error: ' + escape(msg) + '</span>';
        currentEl = null;
      }
      busy = false;
      sendBtn.disabled = false;
    }

    // ── Send ──────────────────────────────────────────────────────────────────
    function send() {
      const text = inputEl.value.trim();
      if (!text || busy) return;
      busy = true;
      sendBtn.disabled = true;
      addUserBubble(text);
      startAssistantBubble();
      inputEl.value = '';
      vscode.postMessage({ type: 'chat.send', data: { message: text } });
    }

    sendBtn.addEventListener('click', send);
    inputEl.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    });
    clearBtn.addEventListener('click', () => {
      vscode.postMessage({ type: 'chat.clear' });
    });

    // ── Messages from host ────────────────────────────────────────────────────
    window.addEventListener('message', e => {
      const m = e.data;
      if (m.type === 'chat.token') appendToken(m.data);
      else if (m.type === 'chat.done')    finishResponse();
      else if (m.type === 'chat.error')   showError(m.data);
      else if (m.type === 'chat.cleared') {
        // Remove all bubbles, restore empty state, reset streaming state
        while (messagesEl.firstChild) messagesEl.removeChild(messagesEl.firstChild);
        messagesEl.appendChild(emptyEl);
        emptyEl.style.display = '';
        currentEl  = null;
        rawContent = '';
        busy       = false;
        sendBtn.disabled = false;
        inputEl.focus();
      }
    });

    inputEl.focus();
  </script>
</body>
</html>`;
  }
}

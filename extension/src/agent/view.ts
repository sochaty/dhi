/**
 * Multi-file agent diff view stub — implemented in Post 4 of the Dhi series.
 *
 * Post 4 title: "Multi-File Agent Editing with LangGraph:
 * Plan → Act → Observe → Verify in Dhi"
 */

import * as vscode from 'vscode';
import { DhiClient } from '../client';

export class AgentView {
  static show(context: vscode.ExtensionContext, client: DhiClient): void {
    vscode.window.showInformationMessage(
      'Dhi: Agent mode is coming in Post 4 of the series.',
    );
  }
}

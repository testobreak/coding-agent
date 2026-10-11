import * as vscode from 'vscode';
import { AgentClient } from './agentClient';
import { getEditorContext } from './selection';
import { getWorkspaceDiagnostics } from './diagnostics';
import { InlineEditManager } from './inlineEdit';

export function activate(context: vscode.ExtensionContext) {
    console.log('[CursorAgent] Extension activated');

    // Command: Cmd+K / Inline Chat
    const inlineChatCmd = vscode.commands.registerCommand('cursor-agent.inlineChat', async () => {
        const query = await vscode.window.showInputBox({
            prompt: 'Enter instructions for the agent (e.g. "optimize this", "add log")',
            placeHolder: 'e.g. Add logging to approveLeave method'
        });

        if (!query || query.trim() === '') {
            return;
        }

        // Get rich editor state
        const editorContext = getEditorContext();
        // Load active problems/diagnostics
        editorContext.diagnostics = getWorkspaceDiagnostics();

        vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: 'Agent starting...',
            cancellable: false
        }, async (progress) => {
            try {
                const response = await AgentClient.modifyStream(query, editorContext, (update) => {
                    if (update.type === 'status') {
                        progress.report({ message: update.content });
                    }
                });
                if (response && response.status === 'success' && response.patch && response.file_path) {
                    await InlineEditManager.showDiffPreview(response.file_path, response.patch);
                } else {
                    vscode.window.showInformationMessage(`Agent completed: no patches to apply.`);
                }
            } catch (e: any) {
                vscode.window.showErrorMessage(`Agent failed: ${e.message}`);
            }
        });
    });

    // Command: Fix Errors
    const fixErrorsCmd = vscode.commands.registerCommand('cursor-agent.fixErrors', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showWarningMessage('No active editor open.');
            return;
        }

        const editorContext = getEditorContext();
        const diagnostics = getWorkspaceDiagnostics().filter(d => d.file === editorContext.active_file);
        
        if (diagnostics.length === 0) {
            vscode.window.showInformationMessage('No active compiler or lint errors detected in this file.');
            return;
        }

        editorContext.diagnostics = diagnostics;
        const query = `Fix compilation and lint errors in ${pathBasename(editorContext.active_file)}`;

        vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: 'Agent starting...',
            cancellable: false
        }, async (progress) => {
            try {
                const response = await AgentClient.modifyStream(query, editorContext, (update) => {
                    if (update.type === 'status') {
                        progress.report({ message: update.content });
                    }
                });
                if (response && response.status === 'success' && response.patch && response.file_path) {
                    await InlineEditManager.showDiffPreview(response.file_path, response.patch);
                } else {
                    vscode.window.showInformationMessage(`Agent completed: no patches needed.`);
                }
            } catch (e: any) {
                vscode.window.showErrorMessage(`Agent failed to repair: ${e.message}`);
            }
        });
    });

    // Accept and Reject workspace commands
    const acceptCmd = vscode.commands.registerCommand('cursor-agent.acceptProposal', () => {
        const editor = vscode.window.activeTextEditor;
        if (editor) {
            InlineEditManager.acceptProposal(editor.document.uri.fsPath);
        }
    });

    const rejectCmd = vscode.commands.registerCommand('cursor-agent.rejectProposal', () => {
        const editor = vscode.window.activeTextEditor;
        if (editor) {
            InlineEditManager.rejectProposal(editor.document.uri.fsPath);
        }
    });

    context.subscriptions.push(inlineChatCmd);
    context.subscriptions.push(fixErrorsCmd);
    context.subscriptions.push(acceptCmd);
    context.subscriptions.push(rejectCmd);

    // Real-time state syncing subscriptions
    context.subscriptions.push(
        vscode.window.onDidChangeTextEditorSelection(pushState),
        vscode.workspace.onDidChangeTextDocument(pushState),
        vscode.window.onDidChangeActiveTextEditor(pushState)
    );

    // Initial sync
    pushState();
}

async function pushState() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) { return; }

    const doc = editor.document;
    const selection = editor.selection;

    const diagnostics = vscode.languages.getDiagnostics(doc.uri).map(d => ({
        severity: vscode.DiagnosticSeverity[d.severity].toLowerCase(),
        message: d.message,
        line: d.range.start.line + 1, // Shift 0-indexed to 1-indexed
        column: d.range.start.character,
        source: d.source || 'vscode'
    }));

    const payload = {
        workspace_root: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || "",
        active_file: doc.fileName,
        cursor_line: selection.active.line + 1, // Shift 0-indexed to 1-indexed
        cursor_column: selection.active.character,
        selected_text: doc.getText(selection),
        unsaved_buffer: doc.getText(),
        diagnostics: diagnostics,
        client: "vscode"
    };

    try {
        await AgentClient.sendState(payload);
    } catch (e: any) {
        console.error(`Problem pushing editor state to local Cursor agent: ${e.message}`);
    }
}

function pathBasename(filePath?: string): string {
    if (!filePath) { return 'file'; }
    const parts = filePath.split(/[/\\]/);
    return parts[parts.length - 1];
}

export function deactivate() {
    console.log('[CursorAgent] Extension deactivated');
}

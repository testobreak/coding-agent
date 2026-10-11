"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || function (mod) {
    if (mod && mod.__esModule) return mod;
    var result = {};
    if (mod != null) for (var k in mod) if (k !== "default" && Object.prototype.hasOwnProperty.call(mod, k)) __createBinding(result, mod, k);
    __setModuleDefault(result, mod);
    return result;
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.deactivate = exports.activate = void 0;
const vscode = __importStar(require("vscode"));
const agentClient_1 = require("./agentClient");
const selection_1 = require("./selection");
const diagnostics_1 = require("./diagnostics");
const inlineEdit_1 = require("./inlineEdit");
function activate(context) {
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
        const editorContext = (0, selection_1.getEditorContext)();
        // Load active problems/diagnostics
        editorContext.diagnostics = (0, diagnostics_1.getWorkspaceDiagnostics)();
        vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: 'Agent starting...',
            cancellable: false
        }, async (progress) => {
            try {
                const response = await agentClient_1.AgentClient.modifyStream(query, editorContext, (update) => {
                    if (update.type === 'status') {
                        progress.report({ message: update.content });
                    }
                });
                if (response && response.status === 'success' && response.patch && response.file_path) {
                    await inlineEdit_1.InlineEditManager.showDiffPreview(response.file_path, response.patch);
                }
                else {
                    vscode.window.showInformationMessage(`Agent completed: no patches to apply.`);
                }
            }
            catch (e) {
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
        const editorContext = (0, selection_1.getEditorContext)();
        const diagnostics = (0, diagnostics_1.getWorkspaceDiagnostics)().filter(d => d.file === editorContext.active_file);
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
                const response = await agentClient_1.AgentClient.modifyStream(query, editorContext, (update) => {
                    if (update.type === 'status') {
                        progress.report({ message: update.content });
                    }
                });
                if (response && response.status === 'success' && response.patch && response.file_path) {
                    await inlineEdit_1.InlineEditManager.showDiffPreview(response.file_path, response.patch);
                }
                else {
                    vscode.window.showInformationMessage(`Agent completed: no patches needed.`);
                }
            }
            catch (e) {
                vscode.window.showErrorMessage(`Agent failed to repair: ${e.message}`);
            }
        });
    });
    // Accept and Reject workspace commands
    const acceptCmd = vscode.commands.registerCommand('cursor-agent.acceptProposal', () => {
        const editor = vscode.window.activeTextEditor;
        if (editor) {
            inlineEdit_1.InlineEditManager.acceptProposal(editor.document.uri.fsPath);
        }
    });
    const rejectCmd = vscode.commands.registerCommand('cursor-agent.rejectProposal', () => {
        const editor = vscode.window.activeTextEditor;
        if (editor) {
            inlineEdit_1.InlineEditManager.rejectProposal(editor.document.uri.fsPath);
        }
    });
    context.subscriptions.push(inlineChatCmd);
    context.subscriptions.push(fixErrorsCmd);
    context.subscriptions.push(acceptCmd);
    context.subscriptions.push(rejectCmd);
    // Real-time state syncing subscriptions
    context.subscriptions.push(vscode.window.onDidChangeTextEditorSelection(pushState), vscode.workspace.onDidChangeTextDocument(pushState), vscode.window.onDidChangeActiveTextEditor(pushState));
    // Initial sync
    pushState();
}
exports.activate = activate;
async function pushState() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        return;
    }
    const doc = editor.document;
    const selection = editor.selection;
    const diagnostics = vscode.languages.getDiagnostics(doc.uri).map(d => ({
        severity: vscode.DiagnosticSeverity[d.severity].toLowerCase(),
        message: d.message,
        line: d.range.start.line + 1,
        column: d.range.start.character,
        source: d.source || 'vscode'
    }));
    const payload = {
        workspace_root: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || "",
        active_file: doc.fileName,
        cursor_line: selection.active.line + 1,
        cursor_column: selection.active.character,
        selected_text: doc.getText(selection),
        unsaved_buffer: doc.getText(),
        diagnostics: diagnostics,
        client: "vscode"
    };
    try {
        await agentClient_1.AgentClient.sendState(payload);
    }
    catch (e) {
        console.error(`Problem pushing editor state to local Cursor agent: ${e.message}`);
    }
}
function pathBasename(filePath) {
    if (!filePath) {
        return 'file';
    }
    const parts = filePath.split(/[/\\]/);
    return parts[parts.length - 1];
}
function deactivate() {
    console.log('[CursorAgent] Extension deactivated');
}
exports.deactivate = deactivate;
//# sourceMappingURL=extension.js.map
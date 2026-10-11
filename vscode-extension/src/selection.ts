import * as vscode from 'vscode';
import { EditorContext } from './agentClient';

export function getEditorContext(): EditorContext {
    const editor = vscode.window.activeTextEditor;
    const openTabs: string[] = [];
    
    try {
        for (const group of vscode.window.tabGroups.all) {
            for (const tab of group.tabs) {
                if (tab.input && tab.input instanceof vscode.TabInputText) {
                    openTabs.push(tab.input.uri.fsPath);
                }
            }
        }
    } catch (e) {
        // Fallback for group/tabs APIs in older versions
    }

    if (!editor) {
        return { open_tabs: openTabs, diagnostics: [] };
    }

    const doc = editor.document;
    const selection = editor.selection;
    const activeFile = doc.uri.fsPath;
    
    const context: EditorContext = {
        active_file: activeFile,
        cursor_line: selection.active.line + 1, // 1-indexed for backend
        cursor_column: selection.active.character,
        open_tabs: openTabs,
        diagnostics: []
    };

    if (!selection.isEmpty) {
        context.selection = doc.getText(selection);
        context.selection_range = [
            [selection.start.line + 1, selection.start.character],
            [selection.end.line + 1, selection.end.character]
        ];
    }

    if (editor.visibleRanges && editor.visibleRanges.length > 0) {
        const vr = editor.visibleRanges[0];
        context.visible_range = [vr.start.line + 1, vr.end.line + 1];
    }

    if (doc.isDirty) {
        context.unsaved_buffer = doc.getText();
    }

    return context;
}

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
exports.getEditorContext = void 0;
const vscode = __importStar(require("vscode"));
function getEditorContext() {
    const editor = vscode.window.activeTextEditor;
    const openTabs = [];
    try {
        for (const group of vscode.window.tabGroups.all) {
            for (const tab of group.tabs) {
                if (tab.input && tab.input instanceof vscode.TabInputText) {
                    openTabs.push(tab.input.uri.fsPath);
                }
            }
        }
    }
    catch (e) {
        // Fallback for group/tabs APIs in older versions
    }
    if (!editor) {
        return { open_tabs: openTabs, diagnostics: [] };
    }
    const doc = editor.document;
    const selection = editor.selection;
    const activeFile = doc.uri.fsPath;
    const context = {
        active_file: activeFile,
        cursor_line: selection.active.line + 1,
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
exports.getEditorContext = getEditorContext;
//# sourceMappingURL=selection.js.map
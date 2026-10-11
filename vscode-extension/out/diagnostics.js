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
exports.getWorkspaceDiagnostics = void 0;
const vscode = __importStar(require("vscode"));
function getWorkspaceDiagnostics() {
    const diagList = [];
    const allDiagnostics = vscode.languages.getDiagnostics();
    for (const [uri, diags] of allDiagnostics) {
        for (const diag of diags) {
            diagList.push({
                file: uri.fsPath,
                line: diag.range.start.line + 1,
                severity: vscode.DiagnosticSeverity[diag.severity].toLowerCase(),
                message: diag.message,
                source: diag.source || 'unknown'
            });
        }
    }
    // Return up to 50 active diagnostics to prevent bloating context
    return diagList.slice(0, 50);
}
exports.getWorkspaceDiagnostics = getWorkspaceDiagnostics;
//# sourceMappingURL=diagnostics.js.map
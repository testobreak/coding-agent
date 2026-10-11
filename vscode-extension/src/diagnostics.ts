import * as vscode from 'vscode';

export function getWorkspaceDiagnostics(): any[] {
    const diagList: any[] = [];
    const allDiagnostics = vscode.languages.getDiagnostics();
    
    for (const [uri, diags] of allDiagnostics) {
        for (const diag of diags) {
            diagList.push({
                file: uri.fsPath,
                line: diag.range.start.line + 1, // 1-indexed for backend compatibility
                severity: vscode.DiagnosticSeverity[diag.severity].toLowerCase(),
                message: diag.message,
                source: diag.source || 'unknown'
            });
        }
    }
    // Return up to 50 active diagnostics to prevent bloating context
    return diagList.slice(0, 50);
}

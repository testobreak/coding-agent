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
exports.InlineEditManager = void 0;
const vscode = __importStar(require("vscode"));
const path = __importStar(require("path"));
const fs = __importStar(require("fs"));
const os = __importStar(require("os"));
const agentClient_1 = require("./agentClient");
class InlineEditManager {
    static async showDiffPreview(originalFilePath, patch) {
        const originalUri = vscode.Uri.file(originalFilePath);
        try {
            const originalContent = fs.readFileSync(originalFilePath, 'utf8');
            // Create a temp file to hold the proposed content
            const tempDir = os.tmpdir();
            const ext = path.extname(originalFilePath);
            const tempFilePath = path.join(tempDir, `agent_proposal_${Date.now()}${ext}`);
            const tempUri = vscode.Uri.file(tempFilePath);
            // Write original content to temp, then apply patch to it
            fs.writeFileSync(tempFilePath, originalContent, 'utf8');
            await agentClient_1.AgentClient.applyPatch(tempFilePath, patch);
            const proposedContent = fs.readFileSync(tempFilePath, 'utf8');
            // Store active proposal
            this.activeProposals.set(originalFilePath, {
                originalUri,
                tempUri,
                content: proposedContent
            });
            // Open native VS Code diff comparison
            await vscode.commands.executeCommand('vscode.diff', originalUri, tempUri, `Agent Proposed Changes: ${path.basename(originalFilePath)}`);
            // Show options to Accept or Reject
            vscode.window.showInformationMessage(`Agent proposed changes. Do you want to accept or reject them?`, 'Accept', 'Reject').then(selection => {
                if (selection === 'Accept') {
                    this.acceptProposal(originalFilePath);
                }
                else if (selection === 'Reject') {
                    this.rejectProposal(originalFilePath);
                }
            });
        }
        catch (e) {
            vscode.window.showErrorMessage(`Failed to generate diff preview: ${e}`);
        }
    }
    static acceptProposal(originalFilePath) {
        const proposal = this.activeProposals.get(originalFilePath);
        if (!proposal) {
            vscode.window.showWarningMessage(`No active proposal found for ${originalFilePath}`);
            return;
        }
        try {
            fs.writeFileSync(originalFilePath, proposal.content, 'utf8');
            vscode.window.showInformationMessage(`Successfully applied changes to ${path.basename(originalFilePath)}`);
            this.cleanup(originalFilePath, proposal.tempUri);
        }
        catch (e) {
            vscode.window.showErrorMessage(`Failed to apply changes: ${e}`);
        }
    }
    static rejectProposal(originalFilePath) {
        const proposal = this.activeProposals.get(originalFilePath);
        if (!proposal) {
            return;
        }
        vscode.window.showInformationMessage(`Discarded changes for ${path.basename(originalFilePath)}`);
        this.cleanup(originalFilePath, proposal.tempUri);
    }
    static cleanup(filePath, tempUri) {
        this.activeProposals.delete(filePath);
        try {
            if (fs.existsSync(tempUri.fsPath)) {
                fs.unlinkSync(tempUri.fsPath);
            }
        }
        catch (e) { }
        // Close the active diff tab
        vscode.commands.executeCommand('workbench.action.closeActiveEditor');
    }
}
exports.InlineEditManager = InlineEditManager;
InlineEditManager.activeProposals = new Map();
//# sourceMappingURL=inlineEdit.js.map
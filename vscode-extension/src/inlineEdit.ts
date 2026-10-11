import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import * as os from 'os';
import { AgentClient } from './agentClient';

export class InlineEditManager {
    private static activeProposals = new Map<string, { originalUri: vscode.Uri, tempUri: vscode.Uri, content: string }>();

    public static async showDiffPreview(originalFilePath: string, patch: string) {
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
            
            await AgentClient.applyPatch(tempFilePath, patch);
            
            const proposedContent = fs.readFileSync(tempFilePath, 'utf8');
            
            // Store active proposal
            this.activeProposals.set(originalFilePath, {
                originalUri,
                tempUri,
                content: proposedContent
            });

            // Open native VS Code diff comparison
            await vscode.commands.executeCommand(
                'vscode.diff',
                originalUri,
                tempUri,
                `Agent Proposed Changes: ${path.basename(originalFilePath)}`
            );

            // Show options to Accept or Reject
            vscode.window.showInformationMessage(
                `Agent proposed changes. Do you want to accept or reject them?`,
                'Accept', 'Reject'
            ).then(selection => {
                if (selection === 'Accept') {
                    this.acceptProposal(originalFilePath);
                } else if (selection === 'Reject') {
                    this.rejectProposal(originalFilePath);
                }
            });

        } catch (e) {
            vscode.window.showErrorMessage(`Failed to generate diff preview: ${e}`);
        }
    }

    public static acceptProposal(originalFilePath: string) {
        const proposal = this.activeProposals.get(originalFilePath);
        if (!proposal) {
            vscode.window.showWarningMessage(`No active proposal found for ${originalFilePath}`);
            return;
        }

        try {
            fs.writeFileSync(originalFilePath, proposal.content, 'utf8');
            vscode.window.showInformationMessage(`Successfully applied changes to ${path.basename(originalFilePath)}`);
            this.cleanup(originalFilePath, proposal.tempUri);
        } catch (e) {
            vscode.window.showErrorMessage(`Failed to apply changes: ${e}`);
        }
    }

    public static rejectProposal(originalFilePath: string) {
        const proposal = this.activeProposals.get(originalFilePath);
        if (!proposal) {
            return;
        }
        vscode.window.showInformationMessage(`Discarded changes for ${path.basename(originalFilePath)}`);
        this.cleanup(originalFilePath, proposal.tempUri);
    }

    private static cleanup(filePath: string, tempUri: vscode.Uri) {
        this.activeProposals.delete(filePath);
        try {
            if (fs.existsSync(tempUri.fsPath)) {
                fs.unlinkSync(tempUri.fsPath);
            }
        } catch (e) {}
        
        // Close the active diff tab
        vscode.commands.executeCommand('workbench.action.closeActiveEditor');
    }
}

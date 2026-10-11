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
exports.AgentClient = void 0;
const http = __importStar(require("http"));
class AgentClient {
    static post(path, data) {
        return new Promise((resolve, reject) => {
            const payload = JSON.stringify(data);
            const url = new URL(this.baseUrl + path);
            const options = {
                hostname: url.hostname,
                port: url.port,
                path: url.pathname,
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Content-Length': Buffer.byteLength(payload)
                }
            };
            const req = http.request(options, (res) => {
                let body = '';
                res.setEncoding('utf8');
                res.on('data', (chunk) => {
                    body += chunk;
                });
                res.on('end', () => {
                    try {
                        const parsed = JSON.parse(body);
                        if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
                            resolve(parsed);
                        }
                        else {
                            reject(new Error(parsed.error || `Request failed with code ${res.statusCode}`));
                        }
                    }
                    catch (e) {
                        reject(new Error(`Failed to parse response: ${e}`));
                    }
                });
            });
            req.on('error', (e) => {
                reject(new Error(`Connection to local agent failed: ${e.message}`));
            });
            req.write(payload);
            req.end();
        });
    }
    static streamPost(path, data, onProgress) {
        return new Promise((resolve, reject) => {
            const payload = JSON.stringify(data);
            const url = new URL(this.baseUrl + path);
            const options = {
                hostname: url.hostname,
                port: url.port,
                path: url.pathname,
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Content-Length': Buffer.byteLength(payload)
                }
            };
            const req = http.request(options, (res) => {
                let buffer = '';
                res.setEncoding('utf8');
                res.on('data', (chunk) => {
                    buffer += chunk;
                    const lines = buffer.split('\n\n');
                    buffer = lines.pop() || '';
                    for (const line of lines) {
                        if (line.trim().startsWith('data:')) {
                            const dataText = line.replace(/^\s*data:\s*/, '').trim();
                            if (dataText) {
                                try {
                                    const parsed = JSON.parse(dataText);
                                    if (parsed.type === 'done') {
                                        resolve(parsed.content);
                                    }
                                    else if (parsed.type === 'error') {
                                        reject(new Error(parsed.content));
                                    }
                                    else {
                                        onProgress(parsed);
                                    }
                                }
                                catch (e) {
                                    console.error('Failed to parse SSE data:', e);
                                }
                            }
                        }
                    }
                });
                res.on('end', () => {
                    if (buffer.trim().startsWith('data:')) {
                        const dataText = buffer.replace(/^\s*data:\s*/, '').trim();
                        if (dataText) {
                            try {
                                const parsed = JSON.parse(dataText);
                                if (parsed.type === 'done') {
                                    resolve(parsed.content);
                                }
                                else if (parsed.type === 'error') {
                                    reject(new Error(parsed.content));
                                }
                                else {
                                    onProgress(parsed);
                                }
                            }
                            catch (e) {
                                // Ignore
                            }
                        }
                    }
                });
            });
            req.on('error', (e) => {
                reject(new Error(`Connection to local agent failed: ${e.message}`));
            });
            req.write(payload);
            req.end();
        });
    }
    static chat(query, context) {
        return this.post('/chat', { query, editor_context: context });
    }
    static chatStream(query, context, onProgress) {
        return this.streamPost('/chat', { query, editor_context: context }, onProgress);
    }
    static retrieve(query, context) {
        return this.post('/retrieve', { query, editor_context: context });
    }
    static modify(query, context) {
        return this.post('/modify', { query, editor_context: context });
    }
    static modifyStream(query, context, onProgress) {
        return this.streamPost('/modify', { query, editor_context: context }, onProgress);
    }
    static applyPatch(filePath, patch) {
        return this.post('/apply_patch', { file_path: filePath, patch });
    }
    static sendDiagnostics(diagnostics) {
        return this.post('/diagnostics', { diagnostics });
    }
    static sendState(state) {
        return this.post('/editor/state', state);
    }
}
exports.AgentClient = AgentClient;
AgentClient.baseUrl = 'http://localhost:8000';
//# sourceMappingURL=agentClient.js.map
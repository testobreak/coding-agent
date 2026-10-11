import * as http from 'http';

export interface EditorContext {
    active_file?: string;
    cursor_line?: number;
    cursor_column?: number;
    selection?: string;
    selection_range?: [[number, number], [number, number]];
    open_tabs: string[];
    diagnostics: any[];
    visible_range?: [number, number];
    unsaved_buffer?: string;
}

export class AgentClient {
    private static baseUrl = 'http://localhost:8000';

    private static post(path: string, data: any): Promise<any> {
        return new Promise((resolve, reject) => {
            const payload = JSON.stringify(data);
            const url = new URL(this.baseUrl + path);
            
            const options: http.RequestOptions = {
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
                        } else {
                            reject(new Error(parsed.error || `Request failed with code ${res.statusCode}`));
                        }
                    } catch (e) {
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

    private static streamPost(
        path: string,
        data: any,
        onProgress: (data: { type: string; content: any }) => void
    ): Promise<any> {
        return new Promise((resolve, reject) => {
            const payload = JSON.stringify(data);
            const url = new URL(this.baseUrl + path);
            
            const options: http.RequestOptions = {
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
                                    } else if (parsed.type === 'error') {
                                        reject(new Error(parsed.content));
                                    } else {
                                        onProgress(parsed);
                                    }
                                } catch (e) {
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
                                } else if (parsed.type === 'error') {
                                    reject(new Error(parsed.content));
                                } else {
                                    onProgress(parsed);
                                }
                            } catch (e) {
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

    public static chat(query: string, context: EditorContext): Promise<any> {
        return this.post('/chat', { query, editor_context: context });
    }

    public static chatStream(query: string, context: EditorContext, onProgress: (data: { type: string; content: any }) => void): Promise<any> {
        return this.streamPost('/chat', { query, editor_context: context }, onProgress);
    }

    public static retrieve(query: string, context: EditorContext): Promise<any> {
        return this.post('/retrieve', { query, editor_context: context });
    }

    public static modify(query: string, context: EditorContext): Promise<any> {
        return this.post('/modify', { query, editor_context: context });
    }

    public static modifyStream(query: string, context: EditorContext, onProgress: (data: { type: string; content: any }) => void): Promise<any> {
        return this.streamPost('/modify', { query, editor_context: context }, onProgress);
    }

    public static applyPatch(filePath: string, patch: string): Promise<any> {
        return this.post('/apply_patch', { file_path: filePath, patch });
    }

    public static sendDiagnostics(diagnostics: any[]): Promise<any> {
        return this.post('/diagnostics', { diagnostics });
    }

    public static sendState(state: any): Promise<any> {
        return this.post('/editor/state', state);
    }
}

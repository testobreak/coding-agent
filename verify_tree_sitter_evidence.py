# verify_tree_sitter_evidence.py
"""
Standalone smoke tests for Tree-Sitter AST evidence extraction.
Validates:
1. Java method, constructor, and HTTP/API call-site extraction.
2. TypeScript HTTP and streaming callback extraction.
3. Real repository files: vscode-extension/src/extension.ts and agentClient.ts.
4. Source line integrity and EvidenceSpan contract compliance.
"""

import sys
import os
from pathlib import Path

# Setup agent path
agent_dir = Path(__file__).resolve().parent / ".agent"
if str(agent_dir) not in sys.path:
    sys.path.insert(0, str(agent_dir))

from retrieval.tree_sitter_evidence_selector import TreeSitterEvidenceSelector
from retrieval.ast_evidence_selector import EvidenceSpan


def test_java_evidence():
    print("============================================================")
    print("  TEST 1: JAVA AST EVIDENCE EXTRACTION")
    print("============================================================")
    selector = TreeSitterEvidenceSelector()

    java_source = '''package com.example.service;

import java.net.HttpURLConnection;
import java.net.URL;

public class OrderServiceClient {
    private final String apiBaseUrl;

    public OrderServiceClient(String apiBaseUrl) {
        this.apiBaseUrl = apiBaseUrl;
    }

    public void submitOrder(
        String orderId,
        String customerId,
        String orderPayload,
        OrderCallback callback
    ) {
        try {
            URL url = new URL(apiBaseUrl + "/api/v1/orders/" + orderId);
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setDoOutput(true);

            java.io.OutputStream os = conn.getOutputStream();
            os.write(orderPayload.getBytes());
            os.flush();

            java.io.InputStream in = conn.getInputStream();
            byte[] buffer = new byte[1024];
            int read;
            while ((read = in.read(buffer)) != -1) {
                callback.onProgress(new String(buffer, 0, read));
            }
            callback.onSuccess(conn.getResponseCode());
        } catch (Exception e) {
            callback.onError(e);
        }
    }
}
'''
    query = "Where is the HTTP endpoint called and how is callback progress streamed?"
    spans = selector.select(
        file_path="src/main/java/OrderServiceClient.java",
        source=java_source,
        query=query,
        max_spans=3,
        max_lines=25,
    )

    print(f"Java extracted {len(spans)} spans:")
    for s in spans:
        print(f"  [{s.evidence_type}] {s.symbol_name} L{s.start_line}-{s.end_line} score={s.score:.1f}")
        assert s.content.strip(), "Evidence content must not be empty"
        assert s.start_line <= s.end_line, f"Invalid range: {s.start_line}-{s.end_line}"

    assert len(spans) > 0, "No spans extracted from Java source"
    types = {s.evidence_type for s in spans}
    assert "signature" in types or "method" in types, "Missing method/signature in Java evidence"
    assert "endpoint" in types or "callback" in types, "Missing endpoint or callback in Java evidence"

    # Verify line overlap
    for i in range(len(spans)):
        for j in range(i + 1, len(spans)):
            overlap = not (spans[i].end_line < spans[j].start_line or spans[j].end_line < spans[i].start_line)
            assert not overlap, f"Java spans overlap: L{spans[i].start_line}-{spans[i].end_line} and L{spans[j].start_line}-{spans[j].end_line}"

    print("  [OK] Java evidence extraction passed.")


def test_typescript_evidence():
    print("\n============================================================")
    print("  TEST 2: TYPESCRIPT HTTP & STREAMING EVIDENCE")
    print("============================================================")
    selector = TreeSitterEvidenceSelector()

    ts_source = '''import { RequestOptions } from 'http';

export class ApiGateway {
    private endpointUrl: string = 'http://localhost:8080';

    public async streamRequest(payload: any, onChunk: (data: string) => void): Promise<any> {
        const response = await fetch(this.endpointUrl + '/api/stream', {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        const reader = response.body?.getReader();
        while (reader) {
            const { done, value } = await reader.read();
            if (done) break;
            onChunk(new TextDecoder().decode(value));
        }
        return response.status;
    }
}
'''
    query = "Where is fetch called for /api/stream and how is chunk streaming handled?"
    spans = selector.select(
        file_path="src/gateway.ts",
        source=ts_source,
        query=query,
        max_spans=3,
        max_lines=25,
    )

    print(f"TypeScript extracted {len(spans)} spans:")
    for s in spans:
        print(f"  [{s.evidence_type}] {s.symbol_name} L{s.start_line}-{s.end_line} score={s.score:.1f}")
        assert s.content.strip(), "Evidence content must not be empty"

    assert len(spans) > 0, "No spans extracted from TypeScript source"
    types = {s.evidence_type for s in spans}
    assert "endpoint" in types or "method" in types, "Missing endpoint or method in TS evidence"

    # Verify line overlap
    for i in range(len(spans)):
        for j in range(i + 1, len(spans)):
            overlap = not (spans[i].end_line < spans[j].start_line or spans[j].end_line < spans[i].start_line)
            assert not overlap, f"TS spans overlap: L{spans[i].start_line}-{spans[i].end_line} and L{spans[j].start_line}-{spans[j].end_line}"

    print("  [OK] TypeScript evidence extraction passed.")


def test_real_typescript_files():
    print("\n============================================================")
    print("  TEST 3: REAL REPOSITORY TYPESCRIPT FILES")
    print("============================================================")
    selector = TreeSitterEvidenceSelector()

    ext_file = Path("vscode-extension/src/extension.ts")
    client_file = Path("vscode-extension/src/agentClient.ts")

    query = "Trace extension.ts through agentClient.ts to the Python HTTP server"

    if ext_file.exists():
        ext_src = ext_file.read_text(encoding="utf-8")
        spans_ext = selector.select(
            file_path=str(ext_file),
            source=ext_src,
            query=query,
            max_spans=3,
            max_lines=25,
        )
        print(f"extension.ts extracted {len(spans_ext)} spans:")
        for s in spans_ext:
            print(f"  [{s.evidence_type}] {s.symbol_name} L{s.start_line}-{s.end_line} score={s.score:.1f}")
            assert s.content.strip(), "Evidence content must not be empty"
        assert len(spans_ext) > 0, "Expected evidence from extension.ts"
        print("  [OK] extension.ts extraction passed.")
    else:
        print("  [SKIP] extension.ts not present.")

    if client_file.exists():
        client_src = client_file.read_text(encoding="utf-8")
        spans_client = selector.select(
            file_path=str(client_file),
            source=client_src,
            query=query,
            max_spans=3,
            max_lines=25,
        )
        print(f"\nagentClient.ts extracted {len(spans_client)} spans:")
        for s in spans_client:
            print(f"  [{s.evidence_type}] {s.symbol_name} L{s.start_line}-{s.end_line} score={s.score:.1f}")
            assert s.content.strip(), "Evidence content must not be empty"
        assert len(spans_client) > 0, "Expected evidence from agentClient.ts"
        print("  [OK] agentClient.ts extraction passed.")
    else:
        print("  [SKIP] agentClient.ts not present.")


if __name__ == "__main__":
    test_java_evidence()
    test_typescript_evidence()
    test_real_typescript_files()
    print("\n============================================================")
    print("  ALL TREE-SITTER EVIDENCE TESTS PASSED! [100% GREEN]")
    print("============================================================\n")

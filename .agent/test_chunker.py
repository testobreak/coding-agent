from retrieval.chunker.repo_chunker import (
    RepoChunker
)

chunker = RepoChunker()

chunks = chunker.build_chunks(".")

print(f"\nTotal chunks: {len(chunks)}\n")

for chunk in chunks[:5]:

    print("=" * 80)

    print(
        chunk.get(
            "name",
            "NO_NAME"
        )
    )

    print(
        chunk.get(
            "type",
            "NO_TYPE"
        )
    )

    print(
        f"{chunk.get('file')} "
        f"({chunk.get('start_line')}-"
        f"{chunk.get('end_line')})"
    )

    print()

    print(
        chunk.get(
            "code",
            "NO_CODE"
        )[:500]
    )

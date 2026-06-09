from retrieval.retriever import (
    CodeRetriever
)

from retrieval.retrieval_pipeline import (
    RetrievalPipeline
)


print("\n[TEST] Starting retriever...\n")

retriever = CodeRetriever(
    repo_root=".."
)

pipeline = RetrievalPipeline(
    retriever
)

print(
    f"\n[TEST] Total indexed vectors: "
    f"{retriever.vector_store.total_vectors()}"
)

print("\n[TEST] Ready for queries\n")


while True:

    try:

        query = input(
            "\nSearch Query > "
        ).strip()

        if not query:
            continue

        if query.lower() in {
            "exit",
            "quit",
            "q"
        }:
            break

        results = pipeline.retrieve_relevant_chunks(
            query=query,
            top_k=8,
            expand_context=True
        )

        print("\nRESULTS\n")

        if not results:

            print("No results found.")
            continue

        for i, item in enumerate(results[:5]):

            chunk = item["chunk"]

            print("=" * 80)

            print(
                f"Result #{i+1}"
            )

            print(
                f"Score: "
                f"{item['score']:.4f}"
            )

            print(
                f"Name: "
                f"{chunk['name']}"
            )

            print(
                f"Type: "
                f"{chunk['type']}"
            )

            print(
                f"File: "
                f"{chunk['file']}"
            )

            print(
                f"Lines: "
                f"{chunk['start_line']}"
                f"-{chunk['end_line']}"
            )

            print(
                f"Chunk: "
                f"{chunk.get('chunk_index', 0)+1}/"
                f"{chunk.get('total_chunks', 1)}"
            )

            if chunk.get("docstring"):

                print(
                    f"Docstring: "
                    f"{chunk['docstring'][:200]}"
                )

            if chunk.get("imports"):

                imports_preview = (
                    ", ".join(
                        chunk["imports"][:5]
                    )
                )

                print(
                    f"Imports: "
                    f"{imports_preview}"
                )

            print("\nCODE\n")

            print(
                chunk['code'][:1200]
            )

            print()

    except KeyboardInterrupt:

        print("\n[TEST] Exiting...")
        break

    except Exception as e:

        print(
            f"\n[ERROR] {e}"
        )

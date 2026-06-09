import argparse

from repository_intelligence.services.repository_service import (
    RepositoryService
)


def main():

    parser = argparse.ArgumentParser(
        description="Repository Intelligence indexing"
    )
    parser.add_argument(
        "repository_root",
        nargs="?",
        default=r"D:\HRMS"
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run symbols, relationships, and embeddings after file indexing."
    )
    args = parser.parse_args()

    service = RepositoryService()

    if args.full:
        result = service.scan_repository(
            args.repository_root
        )
    else:
        result = service.index_repository_files(
            args.repository_root
        )

    print(result)


if __name__ == "__main__":
    main()

"""
query.py -- run one context request against the index and print cited passages.

NEVER imports streamlit. This is the command-line face of retrieval.py, and it
is also how a retrieval change gets checked against a real evaluation question
without going through the app.

    python query.py "checkout throwing 503s, where do i start?" --service payment-service

The `--service` flag stands in for the detector. In the finished system nobody
types it: the Week 1 evidence gate produces a verdict naming the elevated
endpoint x backend slice, and that verdict becomes the ContextRequest. The flag
exists so retrieval can be exercised before that wiring is built.
"""

from __future__ import annotations

import argparse
import sys
import time

import embedding
import retrieval


def build_request(args) -> retrieval.ContextRequest:
    return retrieval.ContextRequest(
        question=args.question,
        service=args.service,
        statuses=("current", "superseded") if args.include_superseded else ("current",),
        access_level="restricted" if args.privileged else "operations",
        top_k=args.top_k,
        max_chunks_per_document=args.per_document,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--service", default=None,
                        help="scope to one backend service (the detector supplies this)")
    parser.add_argument("--top-k", type=int, default=6)
    parser.add_argument("--per-document", type=int, default=2,
                        help="max chunks any one document may contribute")
    parser.add_argument("--include-superseded", action="store_true",
                        help="let superseded documents compete, demoted rather than excluded")
    parser.add_argument("--privileged", action="store_true",
                        help="caller may read access_level: restricted documents")
    args = parser.parse_args(argv)

    try:
        index = embedding.load_index()
    except embedding.EmbeddingError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    started = time.perf_counter()
    retriever = retrieval.Retriever(index)
    built = time.perf_counter()

    request = build_request(args)
    result = retriever.retrieve(request)
    finished = time.perf_counter()

    print(f'Question: "{request.question}"')
    print()
    print(retrieval.describe_filter(result))
    print()
    print(retrieval.format_citations(result))
    print()
    print(f"Documents cited: {', '.join(result.cited_documents) or 'none'}")
    print(f"Timing: index+BM25 build {built - started:.2f}s · "
          f"retrieval {finished - built:.2f}s · total {finished - started:.2f}s")
    spent = embedding.total_spend()
    print(f"Query cost: {result.query_tokens} tokens · "
          f"session total {spent['tokens']:,} tokens, ${spent['usd']:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

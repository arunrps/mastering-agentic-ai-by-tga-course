"""
evaluation.py -- run the golden question set against retrieval and report.

NEVER imports streamlit.

This is the retrieval half of the measurement. It answers: for each of the 24
questions, which passages came back, did the expected document surface, and at
what rank. It does NOT generate answers -- generation.py does that, and it is
gated by the verdict this module's scores calibrate.

Run:  python evaluation.py            (retrieval only, free after first run)
      python evaluation.py --scores   (adds the score distribution used to
                                       calibrate the retrieval-sufficiency gate)
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import embedding
import ingestion
import retrieval

GOLDEN_FILE = ingestion.WEEK_02 / "golden_questions.json"


@dataclass
class QuestionResult:
    """One golden question, run."""

    question: dict
    result: object

    @property
    def qid(self) -> str:
        return self.question["id"]

    @property
    def expected(self) -> list:
        return list(self.question.get("expected_documents") or [])

    @property
    def retrieved(self) -> list:
        return self.result.cited_documents

    def rank_of(self, document_id: str) -> Optional[int]:
        """1-based rank of the first passage from a document, or None."""
        for position, scored in enumerate(self.result.results, start=1):
            if scored.document_id == document_id:
                return position
        return None

    @property
    def expected_found(self) -> dict:
        return {doc: self.rank_of(doc) for doc in self.expected}

    @property
    def hit_count(self) -> int:
        return sum(1 for rank in self.expected_found.values() if rank is not None)

    @property
    def top_score(self) -> float:
        return self.result.results[0].dense_score if self.result.results else 0.0

    @property
    def top_fused(self) -> float:
        return self.result.results[0].fused_score if self.result.results else 0.0


def load_golden(path: Optional[Path] = None) -> list:
    data = json.loads(Path(path or GOLDEN_FILE).read_text(encoding="utf-8"))
    return data["questions"]


def run_all(retriever, questions: Sequence, top_k: int = 6) -> list:
    """Retrieve for every question. Query vectors are cached, so re-runs are free."""
    results = []
    for question in questions:
        request = retrieval.ContextRequest(
            question=question["text"],
            service=question.get("service"),
            top_k=top_k,
        )
        results.append(QuestionResult(question=question, result=retriever.retrieve(request)))
    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_report(results: Sequence) -> None:
    rule = "-" * 96
    print("TriageLens Week 2 -- retrieval evaluation, 24 golden questions")
    print(rule)

    by_class = {}
    for item in results:
        by_class.setdefault(item.question["expected_class"], []).append(item)

    for expected_class in ("answered", "partial", "restricted", "not_in_corpus"):
        items = by_class.get(expected_class, [])
        if not items:
            continue
        print(f"\n{'=' * 96}\nEXPECTED CLASS: {expected_class.upper()}  ({len(items)} questions)")
        for item in items:
            print(f"\n{item.qid} \"{item.question['text']}\"")
            scope = item.question.get("service") or "no service scope"
            print(f"   scope: {scope} · {item.result.candidates_considered}"
                  f"/{item.result.corpus_size} chunks passed the pre-filter")

            if item.expected:
                marks = []
                for doc, rank in item.expected_found.items():
                    marks.append(f"{doc}@{rank}" if rank else f"{doc}=MISS")
                print(f"   expected: {'  '.join(marks)}"
                      f"   ({item.hit_count}/{len(item.expected)} found)")
            else:
                print("   expected: nothing should be needed (refusal set)")

            if item.result.results:
                print(f"   retrieved: {', '.join(item.retrieved)}")
                print(f"   top dense {item.top_score:.3f} · top fused {item.top_fused:.4f}")
            else:
                print("   retrieved: NOTHING")

            if item.result.excluded_restricted:
                print(f"   withheld as restricted: "
                      f"{', '.join(item.result.excluded_restricted)}")

    # --- aggregate ---
    print(f"\n{rule}\nAGGREGATE")
    with_expected = [r for r in results if r.expected]
    total_expected = sum(len(r.expected) for r in with_expected)
    total_found = sum(r.hit_count for r in with_expected)
    full = sum(1 for r in with_expected if r.hit_count == len(r.expected))
    any_hit = sum(1 for r in with_expected if r.hit_count > 0)

    print(f"  questions with an expected document: {len(with_expected)}")
    print(f"  expected documents found: {total_found}/{total_expected} "
          f"({total_found / total_expected * 100:.0f}%)")
    print(f"  questions where ALL expected documents surfaced: {full}/{len(with_expected)}")
    print(f"  questions where AT LEAST ONE surfaced: {any_hit}/{len(with_expected)}")

    ranks = [rank for r in with_expected for rank in r.expected_found.values() if rank]
    if ranks:
        print(f"  rank of found documents: median {int(statistics.median(ranks))}, "
              f"best {min(ranks)}, worst {max(ranks)}")
        print(f"  found at rank 1: {sum(1 for r in ranks if r == 1)}/{len(ranks)}")


def print_score_distribution(results: Sequence) -> None:
    """The separation the retrieval-sufficiency gate is calibrated against.

    The question is whether a question the corpus CAN answer produces visibly
    higher similarity than one it cannot. If the two distributions overlap
    completely, no threshold can separate them and the gate has to be built on
    something other than score.
    """
    print(f"\n{'-' * 96}\nSCORE DISTRIBUTION BY EXPECTED CLASS")
    print("  (top dense cosine per question -- the signal a score-based gate would use)")

    groups = {}
    for item in results:
        groups.setdefault(item.question["expected_class"], []).append(item)

    answerable = []
    unanswerable = []
    for expected_class in ("answered", "partial", "restricted", "not_in_corpus"):
        items = groups.get(expected_class, [])
        if not items:
            continue
        scores = sorted(item.top_score for item in items)
        print(f"\n  {expected_class:<16} n={len(scores)}  "
              f"min {scores[0]:.3f}  median {statistics.median(scores):.3f}  "
              f"max {scores[-1]:.3f}")
        for item in sorted(items, key=lambda i: -i.top_score):
            print(f"      {item.top_score:.3f}  {item.qid:<5} {item.question['text'][:62]}")
        if expected_class in ("answered",):
            answerable.extend(scores)
        if expected_class == "not_in_corpus":
            unanswerable.extend(scores)

    if answerable and unanswerable:
        print(f"\n  answerable floor:     {min(answerable):.3f}")
        print(f"  not-in-corpus ceiling: {max(unanswerable):.3f}")
        if min(answerable) > max(unanswerable):
            print("  --> the two classes SEPARATE; a score threshold between them works")
        else:
            print("  --> the two classes OVERLAP. A score threshold alone cannot")
            print("      distinguish them, and a gate built on one would be guessing.")


def run_generation(retriever, documents, questions: Sequence, top_k: int = 6) -> list:
    """Generate an answer for every question. THIS SPENDS CREDIT."""
    import generation

    rows = []
    for question in questions:
        request = retrieval.ContextRequest(
            question=question["text"], service=question.get("service"), top_k=top_k
        )
        answer, result = generation.answer_question(retriever, documents, request)
        rows.append((question, answer, result))
    return rows


def print_generation_report(rows: Sequence) -> None:
    """Per question: what outcome the system produced against what was expected."""
    import generation

    rule = "-" * 96
    print(f"\n{rule}\nGENERATION -- four-outcome classification across 24 questions\n{rule}")

    agree = 0
    confusion = {}
    for question, answer, result in rows:
        expected = question["expected_class"]
        produced = answer.outcome
        match = "OK " if expected == produced else "DIFF"
        if expected == produced:
            agree += 1
        confusion.setdefault((expected, produced), []).append(question["id"])

        print(f"\n[{match}] {question['id']}  expected={expected}  produced={produced}")
        print(f"   \"{question['text']}\"")
        text = " ".join((answer.text or "").split())
        print(f"   answer: {text[:220]}{'...' if len(text) > 220 else ''}")
        if answer.citations:
            print(f"   cites: {', '.join(answer.cited_documents)}")
        if answer.not_covered:
            covered = " ".join(answer.not_covered.split())
            print(f"   not covered: {covered[:160]}")
        if answer.restricted_documents:
            print(f"   RESTRICTED would have ranked: "
                  f"{', '.join(answer.restricted_documents)}")
        if answer.invalid_citations:
            print(f"   !! INVALID CITATIONS REJECTED: "
                  f"{', '.join(answer.invalid_citations)}")

    print(f"\n{rule}\nOUTCOME AGREEMENT: {agree}/{len(rows)}")
    print("\n  expected -> produced")
    for (expected, produced), qids in sorted(confusion.items()):
        flag = "   " if expected == produced else " * "
        print(f"  {flag}{expected:<14} -> {produced:<14} {len(qids):>2}  {', '.join(qids)}")

    invalid = [q["id"] for q, a, _ in rows if a.invalid_citations]
    print(f"\n  answers citing a document they were not given: "
          f"{len(invalid)}/{len(rows)}"
          + (f"  ({', '.join(invalid)})" if invalid else "  -- none"))

    tokens_in = sum(a.input_tokens for _, a, _ in rows)
    tokens_out = sum(a.output_tokens for _, a, _ in rows)
    print(f"  tokens: {tokens_in:,} in + {tokens_out:,} out = {tokens_in + tokens_out:,}")


def main(argv=None) -> int:
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    index = embedding.load_index()
    retriever = retrieval.Retriever(index)
    questions = load_golden()

    before = embedding.total_spend()
    results = run_all(retriever, questions)
    after = embedding.total_spend()

    print_report(results)
    if "--scores" in argv:
        print_score_distribution(results)
    if "--generate" in argv:
        documents = ingestion.load_corpus()
        print_generation_report(run_generation(retriever, documents, questions))
        after = embedding.total_spend()

    spent = after["tokens"] - before["tokens"]
    print(f"\nquery tokens spent this run: {spent} "
          f"({'cache hits, no API calls' if spent == 0 else 'cache misses'})")
    print(f"session total: {after['tokens']:,} tokens, ${after['usd']:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

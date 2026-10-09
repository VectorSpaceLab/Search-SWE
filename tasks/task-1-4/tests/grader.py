#!/usr/bin/env python3
"""Validate Task-1-4 evidence locations and compute macro Recall@5."""

from __future__ import annotations

import json
import math
import os
import unicodedata
from pathlib import Path
from typing import Any, Iterator

import pypdfium2 as pdfium


CORPUS_DIR = Path("/tmp/task-1-4-eval/corpus")
QUERIES_PATH = Path("/tests/data/queries.jsonl")
GROUND_TRUTH_PATH = Path("/tests/data/golden_answers.jsonl")
RESULTS_DIR = Path(
    os.environ.get("SEARCH_SWE_RESULTS_DIR", "/logs/verifier/task-1-4-eval")
)
PREDICTIONS_PATH = RESULTS_DIR / "results.jsonl"
REPORT_PATH = RESULTS_DIR / "evaluation.json"
EXECUTION_PATH = RESULTS_DIR / "query_execution.json"
EXECUTION_ERROR = os.environ.get("SEARCH_SWE_EXECUTION_ERROR", "")
TOP_K = 5
MAX_EVIDENCE_CHARS = 100_000


class VerificationError(RuntimeError):
    """Raised when verifier inputs or submission output are invalid."""


def iter_jsonl(path: Path) -> Iterator[tuple[int, Any]]:
    try:
        handle = path.open(encoding="utf-8")
    except OSError as error:
        raise VerificationError(f"cannot open {path}: {error}") from error

    with handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise VerificationError(
                    f"invalid JSON in {path}:{line_number}: {error}"
                ) from error
            yield line_number, value


def canonical_text(value: str) -> str:
    """Normalize text across common PDF extractors for page membership checks."""

    normalized = unicodedata.normalize("NFKD", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


class PdfCorpus:
    def __init__(self, root: Path) -> None:
        if not root.is_dir() or root.is_symlink():
            raise VerificationError(f"corpus directory is missing or invalid: {root}")
        self.paths: dict[str, Path] = {}
        for path in sorted(root.glob("*.pdf")):
            if not path.is_file() or path.is_symlink():
                raise VerificationError(f"invalid PDF corpus entry: {path}")
            if path.stem in self.paths:
                raise VerificationError(f"duplicate PDF target {path.stem!r}")
            self.paths[path.stem] = path
        if len(self.paths) != 1:
            raise VerificationError("corpus must contain exactly one PDF file")
        self.target = next(iter(self.paths))
        self.documents: dict[str, Any] = {}
        self.page_cache: dict[tuple[str, int], str] = {}

    def document(self, target: str) -> Any:
        if target not in self.paths:
            raise VerificationError(f"unknown target PDF {target!r}")
        if target not in self.documents:
            try:
                self.documents[target] = pdfium.PdfDocument(str(self.paths[target]))
            except Exception as error:
                raise VerificationError(
                    f"cannot open target PDF {target!r}: {error}"
                ) from error
        return self.documents[target]

    def page_count(self, target: str) -> int:
        return len(self.document(target))

    def canonical_page_text(self, target: str, page_number: int) -> str:
        key = (target, page_number)
        if key in self.page_cache:
            return self.page_cache[key]
        document = self.document(target)
        if not 1 <= page_number <= len(document):
            raise VerificationError(
                f"page {page_number} is outside target PDF {target!r}"
            )
        page = document[page_number - 1]
        text_page = None
        try:
            text_page = page.get_textpage()
            extracted = text_page.get_text_range()
        except Exception as error:
            raise VerificationError(
                f"cannot extract target {target!r} page {page_number}: {error}"
            ) from error
        finally:
            if text_page is not None:
                text_page.close()
            page.close()
        canonical = canonical_text(extracted)
        self.page_cache[key] = canonical
        return canonical

    def close(self) -> None:
        for document in self.documents.values():
            document.close()
        self.documents.clear()


def load_reference_data(
    corpus: PdfCorpus,
) -> tuple[list[dict[str, str]], dict[str, set[int]]]:
    queries: list[dict[str, str]] = []
    query_ids: set[str] = set()
    for line_number, record in iter_jsonl(QUERIES_PATH):
        if not isinstance(record, dict):
            raise VerificationError(f"invalid query object at line {line_number}")
        query_id = record.get("query_id")
        target = corpus.target
        query_text = record.get("query")
        if (
            not isinstance(query_id, str)
            or not query_id
            or query_id in query_ids
            or not isinstance(query_text, str)
            or not query_text.strip()
        ):
            raise VerificationError(f"invalid or duplicate query at line {line_number}")
        query_ids.add(query_id)
        queries.append(
            {"query_id": query_id, "target": target, "query": query_text.strip()}
        )
    if not queries:
        raise VerificationError("queries file is empty")

    relevant_pages: dict[str, set[int]] = {}
    for line_number, record in iter_jsonl(GROUND_TRUTH_PATH):
        if not isinstance(record, dict):
            raise VerificationError(
                f"invalid ground-truth object at line {line_number}"
            )
        query_id = record.get("query_id")
        target = corpus.target
        raw_pages = record.get("relevant_pages")
        if (
            not isinstance(query_id, str)
            or query_id not in query_ids
            or query_id in relevant_pages
            or not isinstance(raw_pages, list)
            or not raw_pages
        ):
            raise VerificationError(
                f"invalid or duplicate ground truth at line {line_number}"
            )

        page_numbers: set[int] = set()
        page_count = corpus.page_count(target)
        for item in raw_pages:
            if not isinstance(item, dict):
                raise VerificationError(
                    f"ground truth for {query_id!r} contains a non-object page"
                )
            page = item.get("page")
            evidence = item.get("evidence")
            if (
                isinstance(page, bool)
                or not isinstance(page, int)
                or not 1 <= page <= page_count
                or page in page_numbers
            ):
                raise VerificationError(
                    f"ground truth for {query_id!r} has invalid page {page!r}"
                )
            if (
                not isinstance(evidence, list)
                or not evidence
                or any(not isinstance(text, str) or not text.strip() for text in evidence)
            ):
                raise VerificationError(
                    f"ground truth for {query_id!r}, page {page} has invalid evidence"
                )
            page_text = corpus.canonical_page_text(target, page)
            if any(not canonical_text(text) or canonical_text(text) not in page_text
                   for text in evidence):
                raise VerificationError(
                    f"ground truth for {query_id!r}, page {page} has evidence "
                    "not found on that physical page"
                )
            page_numbers.add(page)
        relevant_pages[query_id] = page_numbers

    if set(relevant_pages) != query_ids:
        missing = sorted(query_ids - set(relevant_pages))
        extra = sorted(set(relevant_pages) - query_ids)
        raise VerificationError(
            f"queries and ground truth differ: missing={missing}, extra={extra}"
        )
    return queries, relevant_pages


def validate_prediction(
    corpus: PdfCorpus, query: dict[str, str], record: dict[str, Any],
) -> list[int]:
    query_id = query["query_id"]
    results = record.get("results")
    if not isinstance(results, list) or len(results) != TOP_K:
        raise VerificationError(
            f"query {query_id!r} must contain exactly {TOP_K} results"
        )
    target = query["target"]
    page_count = corpus.page_count(target)
    pages: list[int] = []
    previous_score: float | None = None
    previous_page: int | None = None
    for position, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            raise VerificationError(
                f"query {query_id!r}, result {position} is not an object"
            )
        page = item.get("page")
        evidence = item.get("evidence")
        raw_score = item.get("score")
        if (
            isinstance(page, bool)
            or not isinstance(page, int)
            or not 1 <= page <= page_count
        ):
            raise VerificationError(
                f"query {query_id!r}, result {position} has invalid page {page!r}"
            )
        if page in pages:
            raise VerificationError(
                f"query {query_id!r} contains duplicate page {page}"
            )
        if (
            not isinstance(evidence, str)
            or not evidence.strip()
            or len(evidence) > MAX_EVIDENCE_CHARS
        ):
            raise VerificationError(
                f"query {query_id!r}, result {position} has invalid evidence"
            )
        canonical_evidence = canonical_text(evidence)
        canonical_page = corpus.canonical_page_text(target, page)
        if not canonical_evidence or canonical_evidence not in canonical_page:
            raise VerificationError(
                f"query {query_id!r}, result {position} evidence is not text "
                f"from target {target!r} page {page}"
            )
        if (
            isinstance(raw_score, bool)
            or not isinstance(raw_score, (int, float))
        ):
            raise VerificationError(
                f"query {query_id!r}, result {position} has a non-numeric score"
            )
        score = float(raw_score)
        if not math.isfinite(score):
            raise VerificationError(
                f"query {query_id!r}, result {position} has a non-finite score"
            )
        if previous_score is not None:
            if score > previous_score:
                raise VerificationError(
                    f"query {query_id!r} scores are not in descending order"
                )
            if (
                score == previous_score
                and previous_page is not None
                and page < previous_page
            ):
                raise VerificationError(
                    f"query {query_id!r} does not use ascending page order "
                    "for equal scores"
                )
        pages.append(page)
        previous_score = score
        previous_page = page
    return pages


def load_predictions(
    corpus: PdfCorpus, queries: list[dict[str, str]],
) -> tuple[dict[str, list[int]], dict[str, str], list[str]]:
    expected = {row["query_id"]: row for row in queries}
    predictions: dict[str, list[int]] = {}
    errors: dict[str, str] = {}
    output_errors: list[str] = []
    seen: set[str] = set()
    try:
        lines = PREDICTIONS_PATH.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        return {}, {qid: f"cannot read predictions: {error}" for qid in expected}, []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            output_errors.append(f"invalid JSON at output line {line_number}")
            continue
        query_id = record.get("query_id") if isinstance(record, dict) else None
        if not isinstance(query_id, str) or query_id not in expected:
            output_errors.append(f"unknown or invalid query_id at output line {line_number}")
            continue
        if query_id in seen:
            errors[query_id] = "duplicate output query_id"
            predictions.pop(query_id, None)
            continue
        seen.add(query_id)
        try:
            predictions[query_id] = validate_prediction(corpus, expected[query_id], record)
        except (VerificationError, ValueError, OverflowError) as error:
            errors[query_id] = str(error)
    for query_id in expected.keys() - seen:
        errors[query_id] = "missing output for query"
    return predictions, errors, output_errors


def load_execution_errors(queries: list[dict[str, str]]) -> dict[str, str]:
    # Standalone output checks may omit the runner's private execution manifest.
    # test.sh requires it for an actual verifier run.
    if not EXECUTION_PATH.exists():
        return {}
    try:
        manifest = json.loads(EXECUTION_PATH.read_text(encoding="utf-8"))
        rows = manifest["queries"]
        expected = {row["query_id"] for row in queries}
        if (not isinstance(rows, list) or len(rows) != len(expected)
                or any(not isinstance(row, dict) for row in rows)
                or {row["query_id"] for row in rows} != expected):
            raise ValueError("execution/query IDs do not match")
        errors = {}
        for row in rows:
            error = row.get("error")
            if error is not None:
                if not isinstance(error, str) or not error:
                    raise ValueError("invalid query execution error")
                errors[row["query_id"]] = error
        return errors
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise VerificationError(f"invalid private execution manifest: {error}") from error


def write_report(report: dict[str, Any]) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    REPORT_PATH.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


def invalid_report(error: Exception) -> dict[str, Any]:
    return {
        "task_id": "task-1-4",
        "valid": False,
        "score": 0.0,
        "query_count": 0,
        "primary_metric": {"name": "Recall@5", "value": 0.0},
        "errors": [str(error)],
    }


def main() -> int:
    corpus: PdfCorpus | None = None
    try:
        corpus = PdfCorpus(CORPUS_DIR)
        queries, relevant_pages = load_reference_data(corpus)
        if EXECUTION_ERROR:
            raise VerificationError(EXECUTION_ERROR)
        predictions, query_errors, output_errors = load_predictions(corpus, queries)
        query_errors.update(load_execution_errors(queries))

        per_query: list[dict[str, Any]] = []
        recall_sum = 0.0
        for row in queries:
            query_id = row["query_id"]
            relevant = relevant_pages[query_id]
            error = query_errors.get(query_id)
            retrieved = predictions.get(query_id, []) if error is None else []
            hit_count = len(set(retrieved) & relevant)
            recall = hit_count / len(relevant)
            recall_sum += recall
            per_query.append(
                {
                    "query_id": query_id,
                    "valid": error is None,
                    "error": error,
                    "retrieved_pages": retrieved,
                    "relevant_page_count": len(relevant),
                    "hit_count": hit_count,
                    "recall_at_5": recall,
                }
            )

        mean_recall = recall_sum / len(queries)
        report = {
            "task_id": "task-1-4",
            "valid": True,
            "score": 100.0 * mean_recall,
            "query_count": len(queries),
            "invalid_query_count": len(query_errors),
            "primary_metric": {"name": "Recall@5", "value": mean_recall},
            "per_query_metrics": per_query,
            "errors": output_errors,
            "scoring_rule": (
                "macro average of |top-5 predicted pages intersect relevant pages| "
                "/ |relevant pages| over all queries; failed or invalid queries score zero"
            ),
        }
        write_report(report)
        return 0
    except Exception as error:
        write_report(invalid_report(error))
        return 1
    finally:
        if corpus is not None:
            corpus.close()


if __name__ == "__main__":
    raise SystemExit(main())

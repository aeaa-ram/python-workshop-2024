"""Similarity engine for duplicate detection.

MVP implementation is dependency-free: TF-IDF cosine similarity over the
tool documents plus a fuzzy title ratio. The ``EmbeddingBackend`` protocol
is the seam where a real LLM embedding service (e.g. an internal endpoint,
or Claude/OpenAI embeddings) plugs in later — the gatekeeper only talks to
``combined_score``.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Iterable, Protocol

_TOKEN = re.compile(r"[a-z0-9_]+")

# Words too generic to signal similarity between engineering tools.
_STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "to", "for", "in", "with",
    "calculation", "calc", "check", "design", "sheet", "tool",
}


def tokenize(text: str) -> list[str]:
    return [
        t for t in _TOKEN.findall(text.lower())
        if t not in _STOPWORDS and len(t) > 1
    ]


def tfidf_cosine(doc_a: str, doc_b: str, corpus: Iterable[str]) -> float:
    """Cosine similarity of two documents, weighted by corpus IDF."""
    docs = [tokenize(d) for d in corpus]
    tokens_a, tokens_b = tokenize(doc_a), tokenize(doc_b)
    n_docs = max(len(docs), 1)
    df: Counter = Counter()
    for doc in docs:
        df.update(set(doc))

    def vector(tokens: list[str]) -> dict[str, float]:
        tf = Counter(tokens)
        # +1 smoothing (sklearn-style) so terms present in every corpus
        # document still contribute — without it, two identical docs in a
        # tiny corpus score 0.
        return {
            t: (count / len(tokens))
            * (math.log((n_docs + 1) / (df.get(t, 0) + 1)) + 1.0)
            for t, count in tf.items()
        } if tokens else {}

    va, vb = vector(tokens_a), vector(tokens_b)
    dot = sum(va[t] * vb.get(t, 0.0) for t in va)
    norm = math.sqrt(sum(x * x for x in va.values())) * math.sqrt(
        sum(x * x for x in vb.values())
    )
    return dot / norm if norm else 0.0


def title_ratio(title_a: str, title_b: str) -> float:
    return SequenceMatcher(
        None, title_a.lower().strip(), title_b.lower().strip()
    ).ratio()


def variable_overlap(vars_a: set[str], vars_b: set[str]) -> float:
    if not vars_a or not vars_b:
        return 0.0
    return len(vars_a & vars_b) / len(vars_a | vars_b)


def combined_score(
    doc_a: str,
    doc_b: str,
    title_a: str,
    title_b: str,
    vars_a: set[str],
    vars_b: set[str],
    corpus: Iterable[str],
) -> float:
    """Weighted blend used by the gatekeeper (0..1).

    Two signals are combined with max(): the full blend (body + title +
    variables), and a title-dominated blend so that a near-identical
    title flags on its own — a hypothetical request or a from-scratch
    rewrite has few/no variables and formulas to match on, but its title
    is usually the giveaway.
    """
    tfidf = tfidf_cosine(doc_a, doc_b, corpus)
    title = title_ratio(title_a, title_b)
    variables = variable_overlap(vars_a, vars_b)
    full_blend = 0.45 * tfidf + 0.30 * title + 0.25 * variables
    title_blend = 0.75 * title + 0.25 * tfidf
    return max(full_blend, title_blend)


class EmbeddingBackend(Protocol):
    """Future LLM-powered semantic search plugs in here."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class LLMEmbeddingBackend:
    """Placeholder for a real embedding service (not yet wired up).

    Intended flow: embed every tool document at index time, store vectors
    in the index file (or a pgvector/Chroma store once the corpus grows),
    then rank candidate duplicates by cosine similarity of embeddings and
    ask an LLM to adjudicate borderline pairs with a structured verdict.
    """

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError(
            "Wire this to an embedding API (set KG_EMBEDDING_ENDPOINT / "
            "KG_EMBEDDING_API_KEY in the environment) — see docs/ARCHITECTURE.md."
        )

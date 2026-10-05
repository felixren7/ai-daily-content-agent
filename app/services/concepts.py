"""Seed and select frontier AI concepts."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Concept
from app.schemas import CandidateTopic

CONCEPT_SEEDS = [
    (
        "Agentic AI",
        (
            "AI systems that plan multi-step work, use tools, observe results, and adapt "
            "toward a goal."
        ),
        "agents",
    ),
    (
        "Model Context Protocol",
        (
            "An open protocol that standardizes how AI applications discover and connect "
            "to tools and data."
        ),
        "agents",
    ),
    (
        "Retrieval-Augmented Generation",
        (
            "A method that retrieves relevant external evidence and supplies it to a model "
            "before generation."
        ),
        "retrieval",
    ),
    (
        "GraphRAG",
        (
            "A retrieval approach using graph-structured entities and relationships to "
            "assemble model context."
        ),
        "retrieval",
    ),
    (
        "Vector Database",
        (
            "A database designed to store embeddings and retrieve records by numeric "
            "vector similarity."
        ),
        "infrastructure",
    ),
    (
        "Embeddings",
        (
            "Numeric representations learned so related text, images, or inputs occupy "
            "nearby vector space."
        ),
        "foundations",
    ),
    (
        "Mixture of Experts",
        (
            "A sparse architecture routing each token through only a selected subset of "
            "expert networks."
        ),
        "models",
    ),
    (
        "KV Cache",
        (
            "Stored attention keys and values that avoid recomputing earlier autoregressive "
            "token states."
        ),
        "inference",
    ),
    (
        "Quantization",
        (
            "Reducing model numeric precision to lower memory and compute costs while "
            "measuring accuracy loss."
        ),
        "inference",
    ),
    (
        "Distillation",
        (
            "Training a smaller student model to reproduce useful behavior from a stronger "
            "teacher model."
        ),
        "training",
    ),
    (
        "DPO",
        "A preference method that learns directly from paired chosen and rejected model responses.",
        "alignment",
    ),
    (
        "Test-Time Compute",
        (
            "Allocating extra inference computation for search, sampling, or verification "
            "to improve answers."
        ),
        "reasoning",
    ),
    (
        "Vision-Language-Action Models",
        (
            "Models combining visual and language input to predict actions for robots or "
            "embodied systems."
        ),
        "robotics",
    ),
    (
        "Context Engineering",
        "Designing which instructions, evidence, tools, and memory reach a model at each step.",
        "agents",
    ),
    (
        "Agent Memory",
        (
            "Mechanisms that let agents persist, select, and retrieve information from "
            "earlier interactions."
        ),
        "agents",
    ),
    (
        "Synthetic Data",
        (
            "Artificially generated examples for training or evaluating models against "
            "measured real requirements."
        ),
        "training",
    ),
]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def seed_concepts(session: Session) -> int:
    existing = {concept.slug: concept for concept in session.scalars(select(Concept)).all()}
    added = 0
    for term, description, category in CONCEPT_SEEDS:
        slug = _slug(term)
        if slug in existing:
            existing[slug].description = description
            existing[slug].category = category
            continue
        session.add(
            Concept(
                term=term,
                slug=slug,
                description=description,
                category=category,
                importance=0.75,
                novelty=0.8,
            )
        )
        added += 1
    session.flush()
    return added


def select_concept(session: Session, now: datetime | None = None) -> CandidateTopic | None:
    now = now or datetime.now(UTC)
    concepts = list(session.scalars(select(Concept).where(Concept.active.is_(True))).all())
    if not concepts:
        return None

    def score(concept: Concept) -> float:
        if concept.last_published_at is None:
            staleness = 1.0
        else:
            last = concept.last_published_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=UTC)
            days = max(0, (now - last).days)
            staleness = min(1.0, days / 90)
        repetition_penalty = min(0.8, concept.times_published * 0.2)
        return (
            100
            * (0.45 * concept.importance + 0.35 * concept.novelty + 0.20 * staleness)
            * (1 - repetition_penalty)
        )

    selected = max(concepts, key=score)
    return CandidateTopic(
        mode="concept",
        title=selected.term,
        concept_id=selected.id,
        summary=selected.description,
        score=round(score(selected), 2),
        score_breakdown={
            "importance": selected.importance * 100,
            "novelty": selected.novelty * 100,
        },
    )

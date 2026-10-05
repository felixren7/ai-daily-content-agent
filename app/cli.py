"""Operational command line interface."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select

from app.config import get_settings
from app.database import SessionLocal, init_db
from app.models import Article, GeneratedPost, RunHistory
from app.schemas import NormalizedArticle
from app.services.pipeline import ContentPipeline
from app.services.publisher import PublisherService
from app.utils.logging import configure_logging


def _pipeline() -> ContentPipeline:
    settings = get_settings()
    return ContentPipeline(settings, SessionLocal, progress=print)


async def command_fetch() -> int:
    pipeline = _pipeline()
    print("Fetching AI sources...")
    articles, errors = await pipeline.fetch_articles()
    with SessionLocal() as session:
        pipeline.persist_articles(session, articles)
    print(f"Found {len(articles)} articles; source errors: {len(errors)}")
    for error in errors:
        print(f"WARN {error['source']}: {error['error']}", file=sys.stderr)
    return 0


def _load_recent_articles() -> list[NormalizedArticle]:
    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(hours=settings.article_max_age_hours)
    with SessionLocal() as session:
        records = session.scalars(
            select(Article)
            .where(Article.published_at >= cutoff)
            .order_by(desc(Article.published_at))
        ).all()
        return [
            NormalizedArticle(
                source_name=record.source.name,
                source_url=record.source.url,
                source_quality=record.source.credibility,
                external_id=record.external_id,
                title=record.title,
                url=record.url,
                canonical_url=record.canonical_url,
                summary=record.summary,
                content=record.raw_content,
                author=record.author,
                published_at=record.published_at,
                metadata=record.extra_metadata,
            )
            for record in records
        ]


def command_rank() -> int:
    pipeline = _pipeline()
    with SessionLocal() as session:
        ranked, duplicates = pipeline.rank_articles(session, _load_recent_articles())
    print(f"Removed {duplicates} duplicates; ranked {len(ranked)} topics")
    for index, item in enumerate(ranked[:20], 1):
        print(f"{index:2d}. {item.score:6.2f}  {item.title}")
    return 0


async def command_run(args: argparse.Namespace) -> int:
    result = await _pipeline().run(dry_run=args.dry_run, mode=args.mode)
    if result.content:
        print("\n" + "=" * 72)
        print(result.content)
        print("=" * 72)
    return 0 if result.status == "done" else 1


def command_list_posts(pending_only: bool = False) -> int:
    with SessionLocal() as session:
        statement = select(GeneratedPost).order_by(desc(GeneratedPost.created_at))
        if pending_only:
            statement = statement.where(GeneratedPost.status == "pending_review")
        posts = session.scalars(statement.limit(100)).all()
        for post in posts:
            print(
                f"{post.id:4d}  {post.status:20s}  quality={post.quality_score:3d}  "
                f"confidence={post.confidence_score:.2f}  {post.title}"
            )
    return 0


def command_approve(post_id: int) -> int:
    with SessionLocal() as session:
        post = session.get(GeneratedPost, post_id)
        if post is None:
            print(f"Post {post_id} not found", file=sys.stderr)
            return 1
        if post.status not in {"pending_review", "quality_rejected"}:
            print(f"Post {post_id} cannot be approved from status {post.status}", file=sys.stderr)
            return 1
        post.status = "approved"
        post.approved_at = datetime.now(UTC)
        session.commit()
        print(f"Approved post {post_id}")
    return 0


async def command_publish(post_id: int) -> int:
    settings = get_settings()
    with SessionLocal() as session:
        post = session.get(GeneratedPost, post_id)
        if post is None:
            print(f"Post {post_id} not found", file=sys.stderr)
            return 1
        if post.status != "approved":
            print("Post must be approved before manual publication", file=sys.stderr)
            return 1
        if settings.dry_run:
            print("DRY RUN — publication skipped.")
            return 0
        results = await PublisherService(settings).publish(session, post, ignore_auto_publish=True)
        session.commit()
        print(json.dumps([item.model_dump() for item in results], ensure_ascii=False, indent=2))
        return 0 if results and all(item.success for item in results) else 1


def command_status() -> int:
    settings = get_settings()
    with SessionLocal() as session:
        run = session.scalar(select(RunHistory).order_by(desc(RunHistory.started_at)).limit(1))
        pending = len(
            session.scalars(
                select(GeneratedPost).where(GeneratedPost.status == "pending_review")
            ).all()
        )
    print(f"scheduler_enabled={settings.scheduler_enabled}")
    print(f"schedule={settings.post_time} {settings.timezone}")
    print(
        f"mode={settings.content_mode} auto_publish={settings.auto_publish} "
        f"dry_run={settings.dry_run}"
    )
    print(f"pending_review={pending}")
    if run:
        print(f"last_run={run.run_id} status={run.status} step={run.current_step}")
    else:
        print("last_run=none")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="AI Daily Content Agent")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("fetch", help="Fetch and persist current source items")
    subcommands.add_parser("rank", help="Rank recently persisted articles")
    run = subcommands.add_parser("run", help="Execute the complete pipeline")
    run.add_argument("--dry-run", action="store_true", default=None)
    run.add_argument("--mode", choices=["news", "concept", "mixed"])
    generate = subcommands.add_parser("generate", help="Generate from a complete dry-run pipeline")
    generate.add_argument("--mode", choices=["news", "concept", "mixed"])
    subcommands.add_parser("list-posts", help="List generated posts")
    subcommands.add_parser("list-pending", help="List posts awaiting review")
    approve = subcommands.add_parser("approve", help="Approve a post")
    approve.add_argument("post_id", type=int)
    publish = subcommands.add_parser("publish", help="Publish an approved post")
    publish.add_argument("post_id", type=int)
    subcommands.add_parser("status", help="Show scheduler and latest-run status")
    return parser


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    init_db()
    args = build_parser().parse_args()
    if args.command == "fetch":
        return asyncio.run(command_fetch())
    if args.command == "rank":
        return command_rank()
    if args.command == "run":
        return asyncio.run(command_run(args))
    if args.command == "generate":
        args.dry_run = True
        return asyncio.run(command_run(args))
    if args.command == "list-posts":
        return command_list_posts()
    if args.command == "list-pending":
        return command_list_posts(True)
    if args.command == "approve":
        return command_approve(args.post_id)
    if args.command == "publish":
        return asyncio.run(command_publish(args.post_id))
    if args.command == "status":
        return command_status()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

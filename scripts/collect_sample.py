"""Collect a sample corpus from public sources.

Examples:
    python scripts/collect_sample.py --source play_store --app indmoney --limit 100
    python scripts/collect_sample.py --source reddit --max-queries 2 --limit 30
    python scripts/collect_sample.py --source all --quick
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from src.collectors.app_store import AppStoreCollector
from src.collectors.base import get_or_create_source, save_documents
from src.collectors.forums import DiscourseCollector
from src.collectors.play_store import PlayStoreCollector
from src.collectors.reddit import RedditCollector
from src.collectors.youtube import YouTubeCollector
from src.config import settings
from src.db import get_session, init_db
from src.models import Document


def collect_play_store(session, cfg, only_app: str | None, limit: int | None) -> None:
    ps = cfg["play_store"]
    collector = PlayStoreCollector(
        country=ps.get("country", "in"),
        languages=tuple(ps.get("languages", ["en"])),
        count=ps.get("reviews_per_app", 600),
    )
    for key, app in ps["apps"].items():
        if only_app and key != only_app:
            continue
        docs = collector.collect(app["app_id"], app["name"])
        if limit:
            docs = docs[:limit]
        source = get_or_create_source(
            session,
            f"play_store:{app['name']}",
            "play_store",
            f"https://play.google.com/store/apps/details?id={app['app_id']}",
        )
        inserted, skipped = save_documents(session, source, docs)
        print(f"play_store:{app['name']}: fetched={len(docs)} inserted={inserted} skipped={skipped}")


def collect_app_store(session, cfg, only_app: str | None, limit: int | None) -> None:
    app_cfg = cfg["app_store"]
    collector = AppStoreCollector(
        country=app_cfg.get("country", "in"),
        pages=app_cfg.get("pages", 5),
    )
    for key, app in app_cfg["apps"].items():
        if only_app and key != only_app:
            continue
        docs = collector.collect(str(app["app_id"]), app["name"])
        if limit:
            docs = docs[:limit]
        source = get_or_create_source(
            session,
            f"app_store:{app['name']}",
            "app_store",
            f"https://apps.apple.com/in/app/id{app['app_id']}",
        )
        inserted, skipped = save_documents(session, source, docs)
        print(f"app_store:{app['name']}: fetched={len(docs)} inserted={inserted} skipped={skipped}")


def collect_reddit(session, cfg, limit: int | None, max_queries: int | None) -> None:
    reddit_cfg = cfg["reddit"]
    collector = RedditCollector()
    source = get_or_create_source(session, "reddit", "reddit", "https://old.reddit.com")
    queries = reddit_cfg["queries"]
    if max_queries:
        queries = queries[:max_queries]

    for subreddit in reddit_cfg["subreddits"]:
        for query in queries:
            docs = collector.search(subreddit, query, limit=reddit_cfg.get("limit_per_query", 50))
            if limit:
                docs = docs[:limit]
            inserted, skipped = save_documents(session, source, docs)
            print(
                f"reddit:r/{subreddit} q={query!r}: "
                f"fetched={len(docs)} inserted={inserted} skipped={skipped}"
            )


def collect_youtube(session, cfg, limit: int | None, max_queries: int | None) -> None:
    yt_cfg = cfg["youtube"]
    collector = YouTubeCollector(
        max_videos=yt_cfg.get("max_videos_per_query", 2),
        max_comments=yt_cfg.get("max_comments_per_video", 300),
    )
    source = get_or_create_source(session, "youtube", "youtube", "https://www.youtube.com")
    queries = yt_cfg["queries"]
    if max_queries:
        queries = queries[:max_queries]

    for query in queries:
        docs = collector.collect(query)
        if limit:
            docs = docs[:limit]
        inserted, skipped = save_documents(session, source, docs)
        print(f"youtube q={query!r}: fetched={len(docs)} inserted={inserted} skipped={skipped}")


def collect_forums(session, cfg, limit: int | None, max_queries: int | None) -> None:
    for name, forum_cfg in cfg["forums"].items():
        collector = DiscourseCollector(
            base_url=forum_cfg["base_url"],
            name=name,
            max_topics=forum_cfg.get("max_topics", 15),
        )
        source = get_or_create_source(
            session,
            f"forum:{name}",
            "forum",
            forum_cfg["base_url"],
        )
        queries = forum_cfg["queries"]
        if max_queries:
            queries = queries[:max_queries]
        for query in queries:
            docs = collector.collect(query)
            if limit:
                docs = docs[:limit]
            inserted, skipped = save_documents(session, source, docs)
            print(
                f"forum:{name} q={query!r}: "
                f"fetched={len(docs)} inserted={inserted} skipped={skipped}"
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        choices=["all", "play_store", "app_store", "reddit", "youtube", "forums"],
        default="all",
    )
    parser.add_argument("--app", default=None, help="Limit Play/App Store collection to one app key.")
    parser.add_argument("--limit", type=int, default=None, help="Max documents per app/query.")
    parser.add_argument("--max-queries", type=int, default=None, help="Limit queries per source.")
    parser.add_argument("--quick", action="store_true", help="Small smoke-test collection.")
    args = parser.parse_args()

    cfg = settings()["sources"]
    if args.quick:
        args.limit = args.limit or 100
        args.max_queries = args.max_queries or 1
        cfg = dict(cfg)
        cfg["youtube"] = dict(cfg["youtube"])
        cfg["youtube"]["max_videos_per_query"] = 1
        cfg["youtube"]["max_comments_per_video"] = 100

    init_db()
    with get_session() as session:
        if args.source in ("all", "play_store"):
            collect_play_store(session, cfg, args.app, args.limit)
        if args.source in ("all", "app_store"):
            collect_app_store(session, cfg, args.app, args.limit)
        if args.source in ("all", "reddit"):
            collect_reddit(session, cfg, args.limit, args.max_queries)
        if args.source in ("all", "youtube"):
            collect_youtube(session, cfg, args.limit, args.max_queries)
        if args.source in ("all", "forums"):
            collect_forums(session, cfg, args.limit, args.max_queries)

        total = session.scalar(select(func.count()).select_from(Document))
        print(f"\nTotal documents in database: {total}")


if __name__ == "__main__":
    main()

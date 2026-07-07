#!/usr/bin/env python3
"""
Train a neural Transformer Hawkes checkpoint for GDELT daily event sequences.

Usage from Docker:
  docker compose exec backend python db_scripts/train_thp_model.py --epochs 80
  docker compose exec backend python db_scripts/train_thp_model.py --dry-run

For exact country and event-root dimensions, run:
  Get-Content db_scripts\thp_training_precompute.sql | docker exec -i gdelt_mysql mysql -uroot -prootpassword gdelt

The script writes a checkpoint to models/thp_gdelt.pt by default. The FastAPI
backend loads that file automatically through THP_CHECKPOINT_PATH.
"""

from __future__ import annotations

import argparse
import copy
import itertools
import json
import os
import random
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import mysql.connector
import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.thp_neural import (  # noqa: E402
    FEATURE_SIZE,
    NeuralTransformerHawkesModel,
    build_feature_vector,
    series_group_key,
)
from backend.services.actor_normalization import normalize_actor_name  # noqa: E402


EVENT_TYPES = ("all", "conflict", "cooperation", "protest")
DEFAULT_TOP_COUNTRIES = 50
DEFAULT_TOP_ACTORS = 50
DEFAULT_TOP_COUNTRY_PAIRS = 30
DEFAULT_TOP_EVENT_ROOTS = 20
DEFAULT_TOP_EVENT_CODES = 50
DEFAULT_TOP_ACTOR_PAIRS = 30


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train neural THP checkpoint")
    parser.add_argument("--output", default="models/thp_gdelt.pt")
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--seq-len", type=int, default=30)
    parser.add_argument("--forecast-horizon", type=int, default=7)
    parser.add_argument("--d-model", type=int, default=48)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--heads", type=int, default=4)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--amp", action="store_true", help="Use mixed precision on CUDA.")
    parser.add_argument("--compile", action="store_true", help="Use torch.compile when available.")
    parser.add_argument("--val-fraction", type=float, default=0.15)
    parser.add_argument("--count-loss-weight", type=float, default=0.15)
    parser.add_argument("--early-stopping-patience", type=int, default=12)
    parser.add_argument("--early-stopping-min-delta", type=float, default=1e-4)
    parser.add_argument("--early-stop-metric", choices=("mae", "rmse", "hybrid", "val_loss"), default="mae")
    parser.add_argument("--poisson-loss-weight", type=float, default=0.02)
    parser.add_argument("--negative-binomial-loss-weight", type=float, default=0.01)
    parser.add_argument("--negative-binomial-theta", type=float, default=20.0)
    parser.add_argument("--training-log", default="models/training_logs/thp_training_log.jsonl")
    parser.add_argument("--search", action="store_true", help="Run a bounded hyperparameter search.")
    parser.add_argument("--search-epochs", type=int, default=20)
    parser.add_argument("--search-max-trials", type=int, default=8)
    parser.add_argument("--search-seq-lens", default="14,30,60")
    parser.add_argument("--search-d-models", default="48,96")
    parser.add_argument("--search-lrs", default="0.001,0.0005")
    parser.add_argument("--search-batch-sizes", default="512,1024")
    parser.add_argument("--dataset-cache", default="models/thp_training_dataset.npz")
    parser.add_argument("--rebuild-dataset-cache", action="store_true")
    parser.add_argument("--top-countries", type=int, default=DEFAULT_TOP_COUNTRIES)
    parser.add_argument("--top-actors", type=int, default=DEFAULT_TOP_ACTORS)
    parser.add_argument("--top-country-pairs", type=int, default=DEFAULT_TOP_COUNTRY_PAIRS)
    parser.add_argument("--top-event-roots", type=int, default=DEFAULT_TOP_EVENT_ROOTS)
    parser.add_argument("--top-event-codes", type=int, default=DEFAULT_TOP_EVENT_CODES)
    parser.add_argument("--top-actor-pairs", type=int, default=DEFAULT_TOP_ACTOR_PAIRS)
    parser.add_argument("--sweep", action="store_true", help="Run top actor / batch size / compile smoke sweep.")
    parser.add_argument("--sweep-top-actors", default="50,100,200")
    parser.add_argument("--sweep-batch-sizes", default="512,1024,2048")
    parser.add_argument("--sweep-epochs", type=int, default=2)
    parser.add_argument("--min-series-events", type=int, default=10)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the expanded training dataset and print stats without training.",
    )
    return parser.parse_args()


def connect_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3307")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "rootpassword"),
        database=os.getenv("DB_NAME", "gdelt"),
    )


def resolve_device(device_name: str) -> torch.device:
    if device_name == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested, but torch.cuda.is_available() is false.")
    if device_name in ("auto", "cuda") and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def placeholders(values: Sequence[Any]) -> str:
    return ",".join(["%s"] * len(values))


def metrics_sql() -> str:
    return """
            COUNT(*) AS total_events,
            SUM(CASE WHEN GoldsteinScale < 0 THEN 1 ELSE 0 END) AS conflict_events,
            SUM(CASE WHEN GoldsteinScale > 0 THEN 1 ELSE 0 END) AS cooperation_events,
            SUM(CASE WHEN EventRootCode = '14' THEN 1 ELSE 0 END) AS protest_events,
            AVG(GoldsteinScale) AS avg_goldstein,
            AVG(AvgTone) AS avg_tone,
            SUM(NumArticles) AS total_articles
    """


def fetch_all(cur, sql: str, params: Sequence[Any] = ()) -> List[Dict]:
    cur.execute(sql, tuple(params))
    return list(cur.fetchall())


def table_exists(cur, table_name: str) -> bool:
    rows = fetch_all(
        cur,
        """
        SELECT COUNT(*) AS table_count
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        """,
        (table_name,),
    )
    return bool(rows and rows[0]["table_count"])


def parse_json_payload(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return None


def fetch_scalar_list(cur, sql: str, limit: int, column: str) -> List[str]:
    if limit <= 0:
        return []
    rows = fetch_all(cur, sql, (int(limit),))
    return [str(row[column]) for row in rows if row.get(column)]


def fetch_top_countries(cur, limit: int) -> List[str]:
    if table_exists(cur, "thp_country_daily_summary"):
        return fetch_scalar_list(
            cur,
            """
            SELECT country AS value, SUM(total_events) AS event_count
            FROM thp_country_daily_summary
            GROUP BY country
            ORDER BY event_count DESC
            LIMIT %s
            """,
            limit,
            "value",
        )

    return fetch_scalar_list(
        cur,
        """
        SELECT location_name AS value, SUM(location_count) AS event_count
        FROM daily_summary,
             JSON_TABLE(
                top_locations,
                '$[*]' COLUMNS (
                    location_name VARCHAR(255) PATH '$.name',
                    location_count INT PATH '$.count'
                )
             ) AS location_items
        WHERE location_name IS NOT NULL
          AND location_name <> ''
        GROUP BY location_name
        ORDER BY event_count DESC
        LIMIT %s
        """,
        limit,
        "value",
    )


def fetch_top_event_roots(cur, limit: int) -> List[str]:
    if table_exists(cur, "thp_event_root_daily_summary"):
        return fetch_scalar_list(
            cur,
            """
            SELECT event_root AS value, SUM(total_events) AS event_count
            FROM thp_event_root_daily_summary
            GROUP BY event_root
            ORDER BY event_count DESC
            LIMIT %s
            """,
            limit,
            "value",
        )

    if limit <= 0:
        return []
    rows = fetch_all(
        cur,
        "SELECT event_type_distribution FROM daily_summary",
    )
    totals: Dict[str, float] = {}
    for row in rows:
        payload = parse_json_payload(row.get("event_type_distribution")) or {}
        if not isinstance(payload, dict):
            continue
        for name, count in payload.items():
            totals[str(name)] = totals.get(str(name), 0.0) + float(count or 0)
    return [
        name
        for name, _ in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
    ]

def fetch_top_event_roots_raw(cur, limit: int) -> List[str]:
    return fetch_scalar_list(
        cur,
        """
        SELECT EventRootCode AS value, COUNT(*) AS event_count
        FROM events_table
        WHERE EventRootCode IS NOT NULL
          AND EventRootCode <> ''
        GROUP BY EventRootCode
        ORDER BY event_count DESC
        LIMIT %s
        """,
        limit,
        "value",
    )


def fetch_top_event_codes(cur, limit: int) -> List[str]:
    if limit <= 0:
        return []
    if table_exists(cur, "thp_event_code_daily_summary"):
        return fetch_scalar_list(
            cur,
            """
            SELECT event_code AS value, SUM(total_events) AS event_count
            FROM thp_event_code_daily_summary
            GROUP BY event_code
            ORDER BY event_count DESC
            LIMIT %s
            """,
            limit,
            "value",
        )
    return fetch_scalar_list(
        cur,
        """
        SELECT EventCode AS value, COUNT(*) AS event_count
        FROM events_table
        WHERE EventCode IS NOT NULL
          AND EventCode <> ''
        GROUP BY EventCode
        ORDER BY event_count DESC
        LIMIT %s
        """,
        limit,
        "value",
    )


def fetch_top_actors(cur, limit: int) -> List[str]:
    if limit <= 0:
        return []
    if table_exists(cur, "thp_actor_daily_summary"):
        raw_actors = fetch_scalar_list(
            cur,
            """
            SELECT actor_name AS value, SUM(total_events) AS event_count
            FROM thp_actor_daily_summary
            GROUP BY actor_name
            ORDER BY event_count DESC
            LIMIT %s
            """,
            limit,
            "value",
        )
        normalized = []
        seen = set()
        for actor in raw_actors:
            actor_name = normalize_actor_name(actor)
            if actor_name and actor_name not in seen:
                normalized.append(actor_name)
                seen.add(actor_name)
        return normalized

    rows = fetch_all(
        cur,
        """
        SELECT actor_name AS value, SUM(actor_count) AS total_events
        FROM daily_summary,
             JSON_TABLE(
                top_actors,
                '$[*]' COLUMNS (
                    actor_name VARCHAR(255) PATH '$.name',
                    actor_count INT PATH '$.count'
                )
             ) AS actor_items
        WHERE actor_name IS NOT NULL
          AND actor_name <> ''
        GROUP BY actor_name
        ORDER BY total_events DESC
        LIMIT %s
        """,
        (int(limit),),
    )
    return [normalize_actor_name(str(row["value"])) for row in rows if row.get("value")]


def fetch_top_country_pairs(cur, limit: int) -> List[str]:
    if limit <= 0:
        return []
    if table_exists(cur, "thp_country_pair_daily_summary"):
        return fetch_scalar_list(
            cur,
            """
            SELECT country_pair AS value, SUM(total_events) AS event_count
            FROM thp_country_pair_daily_summary
            GROUP BY country_pair
            ORDER BY event_count DESC
            LIMIT %s
            """,
            limit,
            "value",
        )
    return []


def fetch_top_actor_pairs(cur, limit: int) -> List[str]:
    if limit <= 0:
        return []
    if table_exists(cur, "thp_actor_pair_daily_summary"):
        return fetch_scalar_list(
            cur,
            """
            SELECT actor_pair AS value, SUM(total_events) AS event_count
            FROM thp_actor_pair_daily_summary
            GROUP BY actor_pair
            ORDER BY event_count DESC
            LIMIT %s
            """,
            limit,
            "value",
        )
    return []


def fetch_global_rows(cur) -> List[Dict]:
    return fetch_all(
        cur,
        """
        SELECT
            'global:ALL' AS series_id,
            date AS event_date,
            total_events,
            conflict_events,
            cooperation_events,
            0 AS protest_events,
            avg_goldstein,
            avg_tone,
            total_events AS total_articles
        FROM daily_summary
        """,
    )


def fetch_country_rows(cur, countries: Sequence[str]) -> List[Dict]:
    if not countries:
        return []
    if table_exists(cur, "thp_country_daily_summary"):
        return fetch_all(
            cur,
            f"""
            SELECT
                CONCAT('country:', country) AS series_id,
                event_date,
                total_events,
                conflict_events,
                cooperation_events,
                protest_events,
                avg_goldstein,
                avg_tone,
                total_articles
            FROM thp_country_daily_summary
            WHERE country IN ({placeholders(countries)})
            """,
            countries,
        )

    return fetch_all(
        cur,
        f"""
        SELECT
            CONCAT('country:', location_name) AS series_id,
            date AS event_date,
            SUM(location_count) AS total_events,
            SUM(location_count * conflict_events / GREATEST(total_events, 1)) AS conflict_events,
            SUM(location_count * cooperation_events / GREATEST(total_events, 1)) AS cooperation_events,
            0 AS protest_events,
            AVG(avg_goldstein) AS avg_goldstein,
            AVG(avg_tone) AS avg_tone,
            SUM(location_count) AS total_articles
        FROM daily_summary,
             JSON_TABLE(
                top_locations,
                '$[*]' COLUMNS (
                    location_name VARCHAR(255) PATH '$.name',
                    location_count INT PATH '$.count'
                )
             ) AS location_items
        WHERE location_name IN ({placeholders(countries)})
        GROUP BY location_name, date
        """,
        countries,
    )


def fetch_country_pair_rows(cur, country_pairs: Sequence[str]) -> List[Dict]:
    if not country_pairs:
        return []
    if table_exists(cur, "thp_country_pair_daily_summary"):
        return fetch_all(
            cur,
            f"""
            SELECT
                CONCAT('country_pair:', country_pair) AS series_id,
                event_date,
                total_events,
                conflict_events,
                cooperation_events,
                protest_events,
                avg_goldstein,
                avg_tone,
                total_articles
            FROM thp_country_pair_daily_summary
            WHERE country_pair IN ({placeholders(country_pairs)})
            """,
            country_pairs,
        )

    pair_expr = """
        CONCAT(
            LEAST(Actor1CountryCode, Actor2CountryCode),
            '-',
            GREATEST(Actor1CountryCode, Actor2CountryCode)
        )
    """
    return fetch_all(
        cur,
        f"""
        SELECT
            CONCAT('country_pair:', {pair_expr}) AS series_id,
            SQLDATE AS event_date,
            {metrics_sql()}
        FROM events_table
        WHERE Actor1CountryCode IS NOT NULL
          AND Actor2CountryCode IS NOT NULL
          AND Actor1CountryCode <> ''
          AND Actor2CountryCode <> ''
          AND Actor1CountryCode <> Actor2CountryCode
          AND {pair_expr} IN ({placeholders(country_pairs)})
        GROUP BY {pair_expr}, SQLDATE
        """,
        country_pairs,
    )


def fetch_actor_pair_rows(cur, actor_pairs: Sequence[str]) -> List[Dict]:
    if not actor_pairs:
        return []
    if table_exists(cur, "thp_actor_pair_daily_summary"):
        return fetch_all(
            cur,
            f"""
            SELECT
                CONCAT('actor_pair:', actor_pair) AS series_id,
                event_date,
                total_events,
                conflict_events,
                cooperation_events,
                protest_events,
                avg_goldstein,
                avg_tone,
                total_articles
            FROM thp_actor_pair_daily_summary
            WHERE actor_pair IN ({placeholders(actor_pairs)})
            """,
            actor_pairs,
        )
    return []


def fetch_actor_rows(cur, actors: Sequence[str]) -> List[Dict]:
    if not actors:
        return []
    if table_exists(cur, "thp_actor_daily_summary"):
        return fetch_all(
            cur,
            f"""
            SELECT
                CONCAT('actor:', actor_name) AS series_id,
                event_date,
                total_events,
                conflict_events,
                cooperation_events,
                protest_events,
                avg_goldstein,
                avg_tone,
                total_articles
            FROM thp_actor_daily_summary
            WHERE actor_name IN ({placeholders(actors)})
            """,
            actors,
        )

    actor_filter = placeholders(actors)
    return fetch_all(
        cur,
        f"""
        SELECT
            CONCAT('actor:', actor_name) AS series_id,
            date AS event_date,
            SUM(actor_count) AS total_events,
            0 AS conflict_events,
            0 AS cooperation_events,
            0 AS protest_events,
            0 AS avg_goldstein,
            0 AS avg_tone,
            SUM(actor_count) AS total_articles
        FROM daily_summary,
             JSON_TABLE(
                top_actors,
                '$[*]' COLUMNS (
                    actor_name VARCHAR(255) PATH '$.name',
                    actor_count INT PATH '$.count'
                )
             ) AS actor_items
        WHERE actor_name IN ({actor_filter})
        GROUP BY actor_name, date
        """,
        actors,
    )


def fetch_event_root_rows(cur, event_roots: Sequence[str]) -> List[Dict]:
    if not event_roots:
        return []
    if table_exists(cur, "thp_event_root_daily_summary"):
        return fetch_all(
            cur,
            f"""
            SELECT
                CONCAT('event_root:', event_root) AS series_id,
                event_date,
                total_events,
                conflict_events,
                cooperation_events,
                protest_events,
                avg_goldstein,
                avg_tone,
                total_articles
            FROM thp_event_root_daily_summary
            WHERE event_root IN ({placeholders(event_roots)})
            """,
            event_roots,
        )

    rows = fetch_all(
        cur,
        """
        SELECT
            date AS event_date,
            total_events,
            conflict_events,
            cooperation_events,
            avg_goldstein,
            avg_tone,
            event_type_distribution
        FROM daily_summary
        """,
    )
    selected = set(event_roots)
    result: List[Dict] = []
    for row in rows:
        payload = parse_json_payload(row.get("event_type_distribution")) or {}
        if not isinstance(payload, dict):
            continue
        for name, count in payload.items():
            if name not in selected:
                continue
            total = float(row.get("total_events") or 0)
            item_count = float(count or 0)
            result.append({
                "series_id": f"event_category:{name}",
                "event_date": row["event_date"],
                "total_events": item_count,
                "conflict_events": item_count * float(row.get("conflict_events") or 0) / max(total, 1.0),
                "cooperation_events": item_count * float(row.get("cooperation_events") or 0) / max(total, 1.0),
                "protest_events": 0,
                "avg_goldstein": row.get("avg_goldstein") or 0,
                "avg_tone": row.get("avg_tone") or 0,
                "total_articles": item_count,
            })
    return result


def fetch_event_root_rows_raw(cur, event_roots: Sequence[str]) -> List[Dict]:
    if not event_roots:
        return []
    return fetch_all(
        cur,
        f"""
        SELECT
            CONCAT('event_root:', EventRootCode) AS series_id,
            SQLDATE AS event_date,
            {metrics_sql()}
        FROM events_table
        WHERE EventRootCode IN ({placeholders(event_roots)})
        GROUP BY EventRootCode, SQLDATE
        """,
        event_roots,
    )


def fetch_event_code_rows(cur, event_codes: Sequence[str]) -> List[Dict]:
    if not event_codes:
        return []
    if table_exists(cur, "thp_event_code_daily_summary"):
        return fetch_all(
            cur,
            f"""
            SELECT
                CONCAT('event_code:', event_code) AS series_id,
                event_date,
                total_events,
                conflict_events,
                cooperation_events,
                protest_events,
                avg_goldstein,
                avg_tone,
                total_articles
            FROM thp_event_code_daily_summary
            WHERE event_code IN ({placeholders(event_codes)})
            """,
            event_codes,
        )

    return fetch_all(
        cur,
        f"""
        SELECT
            CONCAT('event_code:', EventCode) AS series_id,
            SQLDATE AS event_date,
            {metrics_sql()}
        FROM events_table
        WHERE EventCode IN ({placeholders(event_codes)})
        GROUP BY EventCode, SQLDATE
        """,
        event_codes,
    )


def fetch_rows(args: argparse.Namespace) -> Tuple[List[Dict], Dict[str, Any]]:
    conn = connect_db()
    try:
        cur = conn.cursor(dictionary=True)
        countries = fetch_top_countries(cur, args.top_countries)
        actors = fetch_top_actors(cur, args.top_actors)
        country_pairs = fetch_top_country_pairs(cur, args.top_country_pairs)
        actor_pairs = fetch_top_actor_pairs(cur, args.top_actor_pairs)
        event_roots = fetch_top_event_roots(cur, args.top_event_roots)
        event_codes = fetch_top_event_codes(cur, args.top_event_codes)

        rows: List[Dict] = []
        fetch_plan = [
            ("global", ["ALL"], fetch_global_rows(cur)),
            ("countries", countries, fetch_country_rows(cur, countries)),
            ("actors", actors, fetch_actor_rows(cur, actors)),
            ("country_pairs", country_pairs, fetch_country_pair_rows(cur, country_pairs)),
            ("actor_pairs", actor_pairs, fetch_actor_pair_rows(cur, actor_pairs)),
            ("event_roots", event_roots, fetch_event_root_rows(cur, event_roots)),
            ("event_codes", event_codes, fetch_event_code_rows(cur, event_codes)),
        ]
        for _, _, group_rows in fetch_plan:
            rows.extend(group_rows)

        summary = {
            "global_series": 1,
            "top_countries": countries,
            "top_actors": actors,
            "top_country_pairs": country_pairs,
            "top_actor_pairs": actor_pairs,
            "top_event_roots": event_roots,
            "top_event_codes": event_codes,
            "daily_group_rows": {
                name: len(group_rows)
                for name, _, group_rows in fetch_plan
            },
        }
        return rows, summary
    finally:
        conn.close()


def daterange(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def event_count_for(row: Dict, event_type: str) -> float:
    if event_type == "conflict":
        return float(row.get("conflict_events") or 0)
    if event_type == "cooperation":
        return float(row.get("cooperation_events") or 0)
    if event_type == "protest":
        return float(row.get("protest_events") or 0)
    return float(row.get("total_events") or 0)


def build_series(rows: List[Dict], min_series_events: int) -> Dict[Tuple[str, str], List[List[float]]]:
    by_series_date: Dict[Tuple[str, date], Dict] = {}
    series_totals: Dict[str, float] = {}
    min_date = None
    max_date = None
    series_ids = set()

    for row in rows:
        series_id = row["series_id"]
        event_date = row["event_date"]
        if isinstance(event_date, datetime):
            event_date = event_date.date()
        by_series_date[(series_id, event_date)] = row
        series_totals[series_id] = series_totals.get(series_id, 0.0) + float(row.get("total_events") or 0)
        series_ids.add(series_id)
        min_date = event_date if min_date is None else min(min_date, event_date)
        max_date = event_date if max_date is None else max(max_date, event_date)

    if min_date is None or max_date is None:
        raise RuntimeError("No training rows returned from database")

    series = {}
    for series_id in sorted(series_ids):
        if series_totals.get(series_id, 0.0) < min_series_events:
            continue
        for event_type in EVENT_TYPES:
            values = []
            counts_so_far: List[float] = []
            for day in daterange(min_date, max_date):
                row = by_series_date.get((series_id, day), {})
                event_count = event_count_for(row, event_type)
                conflict = event_count if event_type == "conflict" else float(row.get("conflict_events") or 0)
                cooperation = event_count if event_type == "cooperation" else float(row.get("cooperation_events") or 0)
                counts_so_far.append(event_count)
                values.append(build_feature_vector(
                    event_count=event_count,
                    conflict_events=conflict,
                    cooperation_events=cooperation,
                    avg_goldstein=float(row.get("avg_goldstein") or 0),
                    avg_tone=float(row.get("avg_tone") or 0),
                    total_articles=float(row.get("total_articles") or 0),
                    event_date=day,
                    rolling_counts=counts_so_far,
                ))
            series[(series_id, event_type)] = values
    return series


def linear_slope(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    x_axis = np.arange(len(values), dtype=np.float32)
    y_axis = np.asarray(values, dtype=np.float32)
    x_mean = float(x_axis.mean())
    y_mean = float(y_axis.mean())
    denominator = float(((x_axis - x_mean) ** 2).sum())
    if denominator <= 0:
        return 0.0
    return float(((x_axis - x_mean) * (y_axis - y_mean)).sum() / denominator)


def lag_autocorrelation(values: Sequence[float]) -> float:
    if len(values) < 3:
        return 0.25
    arr = np.asarray(values, dtype=np.float32)
    mean_value = float(arr.mean())
    numerator = float(((arr[:-1] - mean_value) * (arr[1:] - mean_value)).sum())
    denominator = float(((arr[:-1] - mean_value) ** 2).sum())
    if denominator <= 0:
        return 0.25
    return max(0.05, min(0.85, numerator / denominator))


def empirical_hawkes_baseline(history: Sequence[float], horizon: int) -> List[float]:
    history_arr = np.asarray(history, dtype=np.float32)
    historical_mean = float(history_arr.mean()) if len(history_arr) else 0.0
    historical_median = float(np.median(history_arr)) if len(history_arr) else 0.0
    recent_mean = float(history_arr[-7:].mean()) if len(history_arr) else 0.0
    baseline = max(0.0, 0.65 * historical_mean + 0.35 * historical_median)
    trend = linear_slope(history_arr[-min(21, len(history_arr)):])
    alpha = lag_autocorrelation(history_arr)
    beta = np.log(2.0) / 7.0
    excitation = max(0.0, recent_mean - baseline) * alpha

    predictions = []
    for step in range(1, horizon + 1):
        decayed_excitation = excitation * float(np.exp(-beta * step))
        damped_trend = trend * step * float(np.exp(-step / 21.0))
        predictions.append(max(0.0, baseline + decayed_excitation + damped_trend))
    return predictions


def make_dataset(series: Dict[Tuple[str, str], List[List[float]]], seq_len: int, horizon: int):
    xs = []
    ys_log = []
    ys_count = []
    labels = []
    target_positions = []
    baselines = {
        "naive_last": [],
        "moving_avg_7": [],
        "empirical_hawkes": [],
    }
    total_days = 0

    for label, values in series.items():
        total_days = max(total_days, len(values))
        counts = [np.expm1(v[0]) for v in values]
        max_start = len(values) - seq_len - horizon + 1
        for start in range(max_start):
            x = values[start:start + seq_len]
            history = counts[start:start + seq_len]
            y_count = [max(counts[start + seq_len + h], 0.0) for h in range(horizon)]
            y_log = [np.log1p(value) for value in y_count]
            xs.append(x)
            ys_log.append(y_log)
            ys_count.append(y_count)
            labels.append(label)
            target_positions.append(start + seq_len)

            last_value = max(history[-1], 0.0)
            moving_avg = max(float(np.mean(history[-min(7, len(history)):])), 0.0)
            baselines["naive_last"].append([last_value] * horizon)
            baselines["moving_avg_7"].append([moving_avg] * horizon)
            baselines["empirical_hawkes"].append(empirical_hawkes_baseline(history, horizon))

    if not xs:
        raise RuntimeError("Not enough data to build training windows")

    return (
        np.asarray(xs, dtype=np.float32),
        np.asarray(ys_log, dtype=np.float32),
        np.asarray(ys_count, dtype=np.float32),
        labels,
        np.asarray(target_positions, dtype=np.int32),
        {name: np.asarray(values, dtype=np.float32) for name, values in baselines.items()},
        total_days,
    )


def build_training_arrays(args: argparse.Namespace):
    cache_path = Path(args.dataset_cache)
    if not cache_path.is_absolute():
        cache_path = PROJECT_ROOT / cache_path
    cache_meta = {
        "seq_len": int(args.seq_len),
        "forecast_horizon": int(args.forecast_horizon),
        "top_countries": int(args.top_countries),
        "top_actors": int(args.top_actors),
        "top_country_pairs": int(args.top_country_pairs),
        "top_actor_pairs": int(args.top_actor_pairs),
        "top_event_roots": int(args.top_event_roots),
        "top_event_codes": int(args.top_event_codes),
        "min_series_events": int(args.min_series_events),
    }
    if cache_path.exists() and not args.rebuild_dataset_cache:
        payload = np.load(cache_path, allow_pickle=False)
        cached_meta = json.loads(str(payload["cache_meta_json"]))
        if cached_meta == cache_meta:
            labels = [tuple(item.split("||", 1)) for item in payload["labels"].tolist()]
            baselines = {
                "naive_last": payload["baseline_naive_last"],
                "moving_avg_7": payload["baseline_moving_avg_7"],
                "empirical_hawkes": payload["baseline_empirical_hawkes"],
            }
            series = {label: [] for label in sorted(set(labels))}
            dimension_summary = json.loads(str(payload["dimension_summary_json"]))
            return (
                payload["x"],
                payload["y_log"],
                payload["y_count"],
                labels,
                payload["target_positions"],
                baselines,
                int(payload["total_days"]),
                series,
                dimension_summary,
            )

    rows, dimension_summary = fetch_rows(args)
    series = build_series(rows, args.min_series_events)
    dataset = make_dataset(series, args.seq_len, args.forecast_horizon)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    labels = dataset[3]
    baselines = dataset[5]
    np.savez_compressed(
        cache_path,
        x=dataset[0],
        y_log=dataset[1],
        y_count=dataset[2],
        labels=np.asarray([f"{series_id}||{event_type}" for series_id, event_type in labels]),
        target_positions=dataset[4],
        baseline_naive_last=baselines["naive_last"],
        baseline_moving_avg_7=baselines["moving_avg_7"],
        baseline_empirical_hawkes=baselines["empirical_hawkes"],
        total_days=np.asarray(dataset[6], dtype=np.int32),
        dimension_summary_json=np.asarray(json.dumps(dimension_summary)),
        cache_meta_json=np.asarray(json.dumps(cache_meta)),
    )
    return (*dataset, series, dimension_summary)


def encode_label_ids(
    labels: List[Tuple[str, str]]
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict[str, int], Dict[str, int], Dict[str, int]]:
    series_labels = sorted({series_id for series_id, _ in labels})
    event_labels = sorted({event_type for _, event_type in labels})
    group_labels = sorted({series_group_key(series_id) for series_id, _ in labels})
    series_to_id = {series_id: idx for idx, series_id in enumerate(series_labels)}
    event_type_to_id = {event_type: idx for idx, event_type in enumerate(event_labels)}
    series_group_to_id = {group_key: idx for idx, group_key in enumerate(group_labels)}
    series_ids = np.asarray([series_to_id[series_id] for series_id, _ in labels], dtype=np.int64)
    event_type_ids = np.asarray([event_type_to_id[event_type] for _, event_type in labels], dtype=np.int64)
    series_group_ids = np.asarray(
        [series_group_to_id[series_group_key(series_id)] for series_id, _ in labels],
        dtype=np.int64,
    )
    return (
        series_ids,
        event_type_ids,
        series_group_ids,
        series_to_id,
        event_type_to_id,
        series_group_to_id,
    )


def time_based_split(target_positions: np.ndarray, total_days: int, val_fraction: float) -> Tuple[np.ndarray, np.ndarray, int]:
    safe_fraction = min(max(float(val_fraction), 0.05), 0.5)
    split_position = int(total_days * (1.0 - safe_fraction))
    train_idx = np.where(target_positions < split_position)[0]
    val_idx = np.where(target_positions >= split_position)[0]
    if len(train_idx) == 0 or len(val_idx) == 0:
        raise RuntimeError(
            "Time-based validation split produced an empty train or validation set. "
            "Use a smaller validation fraction or shorter sequence length."
        )
    return train_idx, val_idx, split_position


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    true_values = np.asarray(y_true, dtype=np.float32)
    pred_values = np.asarray(y_pred, dtype=np.float32)
    errors = pred_values - true_values
    denominator = np.maximum(np.abs(true_values), 1.0)
    return {
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors ** 2))),
        "mape": float(np.mean(np.abs(errors) / denominator) * 100.0),
    }


def evaluate_by_category(
    labels: List[Tuple[str, str]],
    val_idx: np.ndarray,
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> Dict[str, Dict[str, Any]]:
    categories: Dict[str, List[int]] = {}
    val_positions = val_idx.tolist()
    for local_idx, global_idx in enumerate(val_positions):
        series_id, _ = labels[global_idx]
        category = series_id.split(":", 1)[0] if ":" in series_id else "global"
        categories.setdefault(category, []).append(local_idx)

    result: Dict[str, Dict[str, Any]] = {}
    for category, positions in sorted(categories.items()):
        if not positions:
            continue
        category_true = y_true[positions]
        category_pred = y_pred[positions]
        result[category] = {
            **regression_metrics(category_true, category_pred),
            "samples": len(positions),
        }
    return result


def baseline_improvement(evaluation: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    model_mae = float(evaluation.get("neural_thp", {}).get("mae", 0.0) or 0.0)
    improvements: Dict[str, Dict[str, float]] = {}
    for name, metrics in evaluation.get("baselines", {}).items():
        baseline_mae = float(metrics.get("mae", 0.0) or 0.0)
        if baseline_mae <= 0:
            continue
        improvements[name] = {
            "baseline_mae": baseline_mae,
            "model_mae": model_mae,
            "mae_improvement_pct": (baseline_mae - model_mae) * 100.0 / baseline_mae,
        }
    return improvements


def residual_calibration(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, Any]:
    residuals = np.asarray(y_true, dtype=np.float32) - np.asarray(y_pred, dtype=np.float32)
    abs_errors = np.abs(residuals)
    horizons = []
    for idx in range(residuals.shape[1]):
        h_residual = residuals[:, idx]
        h_abs = abs_errors[:, idx]
        horizons.append({
            "horizon": idx + 1,
            "residual_q10": float(np.quantile(h_residual, 0.10)),
            "residual_q50": float(np.quantile(h_residual, 0.50)),
            "residual_q90": float(np.quantile(h_residual, 0.90)),
            "absolute_error_q80": float(np.quantile(h_abs, 0.80)),
            "absolute_error_q90": float(np.quantile(h_abs, 0.90)),
        })
    return {
        "method": "validation_residual_quantiles",
        "coverage": "central_80_percent",
        "horizons": horizons,
    }


def backtest_by_origin(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    target_positions: np.ndarray,
    val_idx: np.ndarray,
    buckets: int = 3,
) -> List[Dict[str, Any]]:
    positions = target_positions[val_idx]
    if len(positions) == 0:
        return []
    min_pos = int(positions.min())
    max_pos = int(positions.max())
    edges = np.linspace(min_pos, max_pos + 1, buckets + 1)
    results = []
    for bucket in range(buckets):
        mask = (positions >= edges[bucket]) & (positions < edges[bucket + 1])
        if not np.any(mask):
            continue
        metrics = regression_metrics(y_true[mask], y_pred[mask])
        results.append({
            "origin_bucket": bucket + 1,
            "target_day_start": int(edges[bucket]),
            "target_day_end": int(edges[bucket + 1] - 1),
            "samples": int(mask.sum()),
            "metrics": metrics,
        })
    return results


def hybrid_loss(
    pred_norm: torch.Tensor,
    target_norm: torch.Tensor,
    target_count: torch.Tensor,
    target_mean: float,
    target_std: float,
    count_scale: float,
    count_loss_weight: float,
    poisson_loss_weight: float,
    negative_binomial_loss_weight: float,
    negative_binomial_theta: float,
) -> torch.Tensor:
    log_mse = torch.nn.functional.mse_loss(pred_norm, target_norm)
    pred_log = pred_norm * target_std + target_mean
    pred_count = torch.expm1(pred_log).clamp_min(0.0)
    count_mae = torch.nn.functional.l1_loss(pred_count / count_scale, target_count / count_scale)
    poisson = torch.nn.functional.poisson_nll_loss(
        pred_log.clamp(min=-20.0, max=20.0),
        target_count,
        log_input=True,
        full=False,
        reduction="mean",
    ) / count_scale
    theta = torch.tensor(
        max(float(negative_binomial_theta), 1e-3),
        dtype=pred_count.dtype,
        device=pred_count.device,
    )
    mu = pred_count.clamp_min(1e-6)
    nb_log_prob = (
        torch.lgamma(target_count + theta)
        - torch.lgamma(theta)
        - torch.lgamma(target_count + 1.0)
        + theta * (torch.log(theta) - torch.log(theta + mu))
        + target_count * (torch.log(mu) - torch.log(theta + mu))
    )
    negative_binomial = -nb_log_prob.mean() / count_scale
    return (
        log_mse
        + count_loss_weight * count_mae
        + poisson_loss_weight * poisson
        + negative_binomial_loss_weight * negative_binomial
    )


def monitor_score(
    metric_name: str,
    val_loss: float,
    val_metrics: Dict[str, float],
    count_loss_weight: float,
) -> float:
    if metric_name == "mae":
        return val_metrics["mae"]
    if metric_name == "rmse":
        return val_metrics["rmse"]
    if metric_name == "hybrid":
        return val_loss + count_loss_weight * (val_metrics["mae"] / max(val_metrics.get("mean_count", 1.0), 1.0))
    return val_loss


def predict_counts(
    model: nn.Module,
    x_norm: np.ndarray,
    series_ids: np.ndarray,
    event_type_ids: np.ndarray,
    series_group_ids: np.ndarray,
    batch_size: int,
    horizons: torch.Tensor,
    target_mean: float,
    target_std: float,
    device: torch.device,
) -> np.ndarray:
    loader = DataLoader(
        TensorDataset(
            torch.tensor(x_norm),
            torch.tensor(series_ids),
            torch.tensor(event_type_ids),
            torch.tensor(series_group_ids),
        ),
        batch_size=batch_size,
        shuffle=False,
    )
    predictions = []
    model.eval()
    with torch.no_grad():
        for batch_x, batch_series, batch_event, batch_group in loader:
            pred_norm, _ = model(
                batch_x.float().to(device),
                horizons,
                batch_series.long().to(device),
                batch_event.long().to(device),
                batch_group.long().to(device),
            )
            pred_log = pred_norm.cpu().numpy() * target_std + target_mean
            predictions.append(np.maximum(0.0, np.expm1(pred_log)))
    return np.vstack(predictions).astype(np.float32)


def print_dataset_summary(
    x: np.ndarray,
    labels: List[Tuple[str, str]],
    series: Dict[Tuple[str, str], List[List[float]]],
    dimension_summary: Dict[str, Any],
) -> None:
    group_count = len({label[0] for label in labels})
    print(f"windows={len(x)} series={len(series)} dimension_groups={group_count}")
    print(f"global_daily_rows={dimension_summary['daily_group_rows']['global']}")
    print(f"country_count={len(dimension_summary['top_countries'])}")
    print(f"actor_count={len(dimension_summary['top_actors'])}")
    print(f"country_pair_count={len(dimension_summary['top_country_pairs'])}")
    print(f"actor_pair_count={len(dimension_summary['top_actor_pairs'])}")
    print(f"event_root_count={len(dimension_summary['top_event_roots'])}")
    print(f"event_code_count={len(dimension_summary['top_event_codes'])}")
    print(f"series_preview={[f'{group}:{event_type}' for group, event_type in sorted(series.keys())[:8]]}")


def parse_int_list(value: str) -> List[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def parse_float_list(value: str) -> List[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def resolve_project_path(path: str) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = PROJECT_ROOT / resolved
    return resolved


def append_training_log(path: str, record: Dict[str, Any]) -> None:
    if not path:
        return
    log_path = resolve_project_path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str) + "\n")


def write_epoch_csv(jsonl_path: str) -> None:
    if not jsonl_path:
        return
    log_path = resolve_project_path(jsonl_path)
    if not log_path.exists():
        return
    csv_path = log_path.with_suffix(".csv")
    rows = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if "epoch" in item:
            rows.append(item)
    if not rows:
        return
    columns = [
        "run_id",
        "epoch",
        "train_loss",
        "val_loss",
        "val_mae",
        "val_rmse",
        "monitor_metric",
        "monitor_score",
        "best_epoch",
    ]
    with csv_path.open("w", encoding="utf-8") as handle:
        handle.write(",".join(columns) + "\n")
        for row in rows:
            handle.write(",".join(str(row.get(column, "")) for column in columns) + "\n")


def train(args: argparse.Namespace) -> Dict[str, Any]:
    run_id = datetime.utcnow().strftime("thp_%Y%m%dT%H%M%SZ")
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = resolve_device(args.device)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(args.seed)
        torch.set_float32_matmul_precision("high")
    print(f"device={device}")
    if device.type == "cuda":
        print(f"cuda_device={torch.cuda.get_device_name(0)}")

    (
        x,
        y_log,
        y_count,
        labels,
        target_positions,
        baselines,
        total_days,
        series,
        dimension_summary,
    ) = build_training_arrays(args)
    print_dataset_summary(x, labels, series, dimension_summary)
    (
        series_ids,
        event_type_ids,
        series_group_ids,
        series_to_id,
        event_type_to_id,
        series_group_to_id,
    ) = encode_label_ids(labels)
    train_idx, val_idx, split_position = time_based_split(
        target_positions,
        total_days,
        args.val_fraction,
    )
    print(
        "split_strategy=time_based "
        f"split_day_index={split_position} train_samples={len(train_idx)} val_samples={len(val_idx)}"
    )
    append_training_log(args.training_log, {
        "run_id": run_id,
        "event": "start",
        "output": args.output,
        "seq_len": args.seq_len,
        "d_model": args.d_model,
        "batch_size": args.batch_size,
        "top_actors": args.top_actors,
        "device": str(device),
        "amp": bool(args.amp and device.type == "cuda"),
        "torch_compile": bool(args.compile),
        "train_samples": int(len(train_idx)),
        "val_samples": int(len(val_idx)),
        "dimension_summary": dimension_summary,
    })

    feature_mean = x[train_idx].reshape(-1, FEATURE_SIZE).mean(axis=0)
    feature_std = x[train_idx].reshape(-1, FEATURE_SIZE).std(axis=0)
    feature_std = np.where(feature_std < 1e-6, 1.0, feature_std)
    target_mean = float(y_log[train_idx].mean())
    train_target_std = float(y_log[train_idx].std())
    target_std = float(train_target_std if train_target_std > 1e-6 else 1.0)
    count_scale = float(max(np.mean(y_count[train_idx]), 1.0))

    x_norm = (x - feature_mean) / feature_std
    y_norm = (y_log - target_mean) / target_std

    train_loader = DataLoader(
        TensorDataset(
            torch.tensor(x_norm[train_idx]),
            torch.tensor(series_ids[train_idx]),
            torch.tensor(event_type_ids[train_idx]),
            torch.tensor(series_group_ids[train_idx]),
            torch.tensor(y_norm[train_idx]),
            torch.tensor(y_count[train_idx]),
        ),
        batch_size=args.batch_size,
        shuffle=True,
        pin_memory=device.type == "cuda",
    )
    val_loader = DataLoader(
        TensorDataset(
            torch.tensor(x_norm[val_idx]),
            torch.tensor(series_ids[val_idx]),
            torch.tensor(event_type_ids[val_idx]),
            torch.tensor(series_group_ids[val_idx]),
            torch.tensor(y_norm[val_idx]),
            torch.tensor(y_count[val_idx]),
        ),
        batch_size=args.batch_size,
        shuffle=False,
        pin_memory=device.type == "cuda",
    )

    model = NeuralTransformerHawkesModel(
        input_size=FEATURE_SIZE,
        seq_len=args.seq_len,
        d_model=args.d_model,
        nhead=args.heads,
        num_layers=args.layers,
        num_series=len(series_to_id),
        num_event_types=len(event_type_to_id),
        num_series_groups=len(series_group_to_id),
    ).to(device)
    if args.compile and hasattr(torch, "compile"):
        model = torch.compile(model)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    horizons = torch.arange(1, args.forecast_horizon + 1, dtype=torch.float32, device=device)
    use_amp = bool(args.amp and device.type == "cuda")
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    best_score = float("inf")
    best_val = float("inf")
    best_epoch = 0
    stale_epochs = 0
    best_state = None
    for epoch in range(1, args.epochs + 1):
        model.train()
        train_loss = 0.0
        for batch_x, batch_series, batch_event, batch_group, batch_y, batch_count in train_loader:
            optimizer.zero_grad()
            with torch.amp.autocast("cuda", enabled=use_amp):
                pred, _ = model(
                    batch_x.float().to(device),
                    horizons,
                    batch_series.long().to(device),
                    batch_event.long().to(device),
                    batch_group.long().to(device),
                )
                loss = hybrid_loss(
                    pred_norm=pred,
                    target_norm=batch_y.float().to(device),
                    target_count=batch_count.float().to(device),
                    target_mean=target_mean,
                    target_std=target_std,
                    count_scale=count_scale,
                    count_loss_weight=args.count_loss_weight,
                    poisson_loss_weight=args.poisson_loss_weight,
                    negative_binomial_loss_weight=args.negative_binomial_loss_weight,
                    negative_binomial_theta=args.negative_binomial_theta,
                )
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(optimizer)
            scaler.update()
            train_loss += loss.item() * len(batch_x)
        train_loss /= len(train_idx)

        model.eval()
        val_loss = 0.0
        val_pred_batches = []
        val_true_batches = []
        with torch.no_grad():
            for batch_x, batch_series, batch_event, batch_group, batch_y, batch_count in val_loader:
                pred, _ = model(
                    batch_x.float().to(device),
                    horizons,
                    batch_series.long().to(device),
                    batch_event.long().to(device),
                    batch_group.long().to(device),
                )
                batch_count_device = batch_count.float().to(device)
                loss = hybrid_loss(
                    pred_norm=pred,
                    target_norm=batch_y.float().to(device),
                    target_count=batch_count_device,
                    target_mean=target_mean,
                    target_std=target_std,
                    count_scale=count_scale,
                    count_loss_weight=args.count_loss_weight,
                    poisson_loss_weight=args.poisson_loss_weight,
                    negative_binomial_loss_weight=args.negative_binomial_loss_weight,
                    negative_binomial_theta=args.negative_binomial_theta,
                )
                val_loss += loss.item() * len(batch_x)
                pred_log = pred * target_std + target_mean
                val_pred_batches.append(torch.expm1(pred_log).clamp_min(0.0).cpu().numpy())
                val_true_batches.append(batch_count.numpy())
        val_loss /= max(1, len(val_idx))
        val_pred_counts = np.vstack(val_pred_batches)
        val_true_counts = np.vstack(val_true_batches)
        val_metrics = regression_metrics(val_true_counts, val_pred_counts)
        val_metrics["mean_count"] = float(np.mean(val_true_counts))
        current_score = monitor_score(
            args.early_stop_metric,
            val_loss,
            val_metrics,
            args.count_loss_weight,
        )

        if current_score < best_score - args.early_stopping_min_delta:
            best_score = current_score
            best_val = val_loss
            best_epoch = epoch
            stale_epochs = 0
            state_model = getattr(model, "_orig_mod", model)
            best_state = {k: v.cpu().clone() for k, v in state_model.state_dict().items()}
        else:
            stale_epochs += 1

        append_training_log(args.training_log, {
            "run_id": run_id,
            "event": "epoch",
            "epoch": int(epoch),
            "train_loss": float(train_loss),
            "val_loss": float(val_loss),
            "val_mae": float(val_metrics["mae"]),
            "val_rmse": float(val_metrics["rmse"]),
            "val_mape": float(val_metrics["mape"]),
            "monitor_metric": args.early_stop_metric,
            "monitor_score": float(current_score),
            "best_epoch": int(best_epoch),
        })

        if epoch == 1 or epoch % 10 == 0 or epoch == args.epochs:
            print(
                f"epoch={epoch:03d} "
                f"train_loss={train_loss:.5f} "
                f"val_loss={val_loss:.5f} "
                f"val_mae={val_metrics['mae']:.3f} "
                f"val_rmse={val_metrics['rmse']:.3f} "
                f"monitor_{args.early_stop_metric}={current_score:.5f}"
            )

        if args.early_stopping_patience > 0 and stale_epochs >= args.early_stopping_patience:
            print(
                f"early_stopped epoch={epoch:03d} "
                f"best_epoch={best_epoch:03d} "
                f"best_{args.early_stop_metric}={best_score:.5f}"
            )
            break

    write_epoch_csv(args.training_log)

    if best_state is not None:
        state_model = getattr(model, "_orig_mod", model)
        state_model.load_state_dict(best_state)

    model_val_predictions = predict_counts(
        model=model,
        x_norm=x_norm[val_idx],
        series_ids=series_ids[val_idx],
        event_type_ids=event_type_ids[val_idx],
        series_group_ids=series_group_ids[val_idx],
        batch_size=args.batch_size,
        horizons=horizons,
        target_mean=target_mean,
        target_std=target_std,
        device=device,
    )
    evaluation = {
        "split_strategy": "time_based",
        "split_day_index": int(split_position),
        "validation_fraction": float(args.val_fraction),
        "neural_thp": regression_metrics(y_count[val_idx], model_val_predictions),
        "baselines": {
            name: regression_metrics(y_count[val_idx], values[val_idx])
            for name, values in baselines.items()
        },
    }
    evaluation["per_category"] = evaluate_by_category(
        labels=labels,
        val_idx=val_idx,
        y_true=y_count[val_idx],
        y_pred=model_val_predictions,
    )
    evaluation["baseline_improvement"] = baseline_improvement(evaluation)
    evaluation["residual_calibration"] = residual_calibration(y_count[val_idx], model_val_predictions)
    evaluation["rolling_origin_backtest"] = backtest_by_origin(
        y_true=y_count[val_idx],
        y_pred=model_val_predictions,
        target_positions=target_positions,
        val_idx=val_idx,
        buckets=3,
    )
    model_metrics = evaluation["neural_thp"]
    print(
        "metrics neural_thp "
        f"mae={model_metrics['mae']:.3f} "
        f"rmse={model_metrics['rmse']:.3f} "
        f"mape={model_metrics['mape']:.3f}"
    )
    for name, metrics in evaluation["baselines"].items():
        print(
            f"metrics {name} "
            f"mae={metrics['mae']:.3f} "
            f"rmse={metrics['rmse']:.3f} "
            f"mape={metrics['mape']:.3f}"
        )

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    checkpoint = {
        "model_state": getattr(model, "_orig_mod", model).state_dict(),
        "config": {
            "input_size": FEATURE_SIZE,
            "seq_len": args.seq_len,
            "d_model": args.d_model,
            "nhead": args.heads,
            "num_layers": args.layers,
            "dropout": 0.1,
            "num_series": len(series_to_id),
            "num_event_types": len(event_type_to_id),
            "num_series_groups": len(series_group_to_id),
        },
        "feature_mean": feature_mean.tolist(),
        "feature_std": feature_std.tolist(),
            "target_mean": target_mean,
            "target_std": target_std,
            "count_scale": count_scale,
            "series_to_id": series_to_id,
            "event_type_to_id": event_type_to_id,
            "series_group_to_id": series_group_to_id,
            "metadata": {
            "train_samples": int(len(train_idx)),
            "val_samples": int(len(val_idx)),
            "best_val_loss": float(best_val),
            "best_epoch": int(best_epoch),
            "best_monitor_metric": args.early_stop_metric,
            "best_monitor_score": float(best_score),
            "epochs": args.epochs,
            "completed_epochs": int(epoch),
            "forecast_horizon": args.forecast_horizon,
            "series_count": len(series),
            "training_strategy": "expanded_daily_aggregate_time_split_multitask_embeddings",
            "event_types": list(EVENT_TYPES),
            "model_version": "thp_v4_hierarchy_nb_intervals",
            "uses_series_embedding": True,
            "uses_event_type_embedding": True,
            "uses_time_features": True,
            "uses_rolling_features": True,
            "uses_attention_pooling": True,
            "uses_direct_multi_horizon_head": True,
            "uses_poisson_count_likelihood": True,
            "uses_negative_binomial_likelihood": True,
            "uses_cameo_hierarchy_embedding": True,
            "multi_task_event_types": True,
            "loss": {
                "name": "log_mse_plus_count_mae_plus_poisson_and_negative_binomial_nll",
                "count_loss_weight": float(args.count_loss_weight),
                "poisson_loss_weight": float(args.poisson_loss_weight),
                "negative_binomial_loss_weight": float(args.negative_binomial_loss_weight),
                "negative_binomial_theta": float(args.negative_binomial_theta),
                "count_scale": float(count_scale),
            },
            "early_stopping": {
                "patience": int(args.early_stopping_patience),
                "min_delta": float(args.early_stopping_min_delta),
                "metric": args.early_stop_metric,
            },
            "device": str(device),
            "amp": bool(use_amp),
            "torch_compile": bool(args.compile),
            "evaluation": evaluation,
            "dimension_summary": dimension_summary,
            "series_label_count": len(series),
            "series_group_count": len(series_group_to_id),
            "series_group_to_id": series_group_to_id,
            "series_label_preview": [
                f"{series_id}:{event_type}"
                for series_id, event_type in sorted(series.keys())[:40]
            ],
        },
    }
    torch.save(checkpoint, output_path)
    append_training_log(args.training_log, {
        "run_id": run_id,
        "event": "finish",
        "output_path": str(output_path),
        "best_val_loss": float(best_val),
        "best_epoch": int(best_epoch),
        "best_monitor_score": float(best_score),
        "evaluation": evaluation,
    })
    write_epoch_csv(args.training_log)
    print(f"saved_checkpoint={output_path}")
    print(f"best_val_loss={best_val:.5f}")
    print(f"best_epoch={best_epoch}")
    print(f"best_{args.early_stop_metric}={best_score:.5f}")
    print(f"samples={len(x)} series={len(series)}")
    print(f"label_preview={labels[:3]}")
    return {
        "output_path": output_path,
        "best_val_loss": best_val,
        "best_epoch": best_epoch,
        "best_monitor_score": best_score,
        "monitor_metric": args.early_stop_metric,
        "evaluation": evaluation,
        "completed_epochs": epoch,
    }


def run_hyperparameter_search(args: argparse.Namespace) -> Dict[str, Any]:
    seq_lens = parse_int_list(args.search_seq_lens)
    d_models = parse_int_list(args.search_d_models)
    learning_rates = parse_float_list(args.search_lrs)
    batch_sizes = parse_int_list(args.search_batch_sizes)
    grid = list(itertools.product(seq_lens, d_models, learning_rates, batch_sizes))
    if args.search_max_trials > 0:
        grid = grid[:args.search_max_trials]
    if not grid:
        raise RuntimeError("Hyperparameter search grid is empty.")

    final_output = Path(args.output)
    if not final_output.is_absolute():
        final_output = PROJECT_ROOT / final_output
    search_dir = final_output.parent / "search"
    search_dir.mkdir(parents=True, exist_ok=True)

    results = []
    best_result = None
    print(f"search_trials={len(grid)}")
    for trial_index, (seq_len, d_model, lr, batch_size) in enumerate(grid, start=1):
        trial_args = copy.deepcopy(args)
        trial_args.search = False
        trial_args.epochs = args.search_epochs
        trial_args.seq_len = seq_len
        trial_args.d_model = d_model
        trial_args.lr = lr
        trial_args.batch_size = batch_size
        trial_args.output = str(search_dir / f"trial_{trial_index:02d}_seq{seq_len}_d{d_model}_lr{lr}_bs{batch_size}.pt")
        trial_args.dataset_cache = str(search_dir / f"dataset_seq{seq_len}_h{args.forecast_horizon}.npz")
        trial_args.training_log = str(search_dir / f"training_trial_{trial_index:02d}.jsonl")
        print(
            f"search_trial={trial_index} "
            f"seq_len={seq_len} d_model={d_model} lr={lr} batch_size={batch_size}"
        )
        result = train(trial_args)
        metrics = result["evaluation"]["neural_thp"]
        record = {
            "trial": trial_index,
            "seq_len": seq_len,
            "d_model": d_model,
            "lr": lr,
            "batch_size": batch_size,
            "best_epoch": result["best_epoch"],
            "completed_epochs": result["completed_epochs"],
            "best_monitor_score": result["best_monitor_score"],
            "best_val_loss": result["best_val_loss"],
            "mae": metrics["mae"],
            "rmse": metrics["rmse"],
            "mape": metrics["mape"],
            "output_path": str(result["output_path"]),
        }
        results.append(record)
        if best_result is None or record["mae"] < best_result["mae"]:
            best_result = record

    assert best_result is not None
    shutil.copyfile(best_result["output_path"], final_output)
    summary = {
        "best_trial": best_result,
        "trials": results,
        "selected_checkpoint": str(final_output),
        "selection_metric": "mae",
    }
    summary_path = search_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"search_summary={summary_path}")
    print(f"selected_checkpoint={final_output}")
    print(
        f"best_trial={best_result['trial']} "
        f"mae={best_result['mae']:.3f} "
        f"rmse={best_result['rmse']:.3f} "
        f"mape={best_result['mape']:.3f}"
    )
    return summary


def run_capacity_sweep(args: argparse.Namespace) -> Dict[str, Any]:
    top_actor_values = parse_int_list(args.sweep_top_actors)
    batch_sizes = parse_int_list(args.sweep_batch_sizes)
    compile_options = [False, True]
    sweep_dir = PROJECT_ROOT / "models" / "sweep"
    sweep_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for trial_index, (top_actors, batch_size, use_compile) in enumerate(
        itertools.product(top_actor_values, batch_sizes, compile_options),
        start=1,
    ):
        trial_args = copy.deepcopy(args)
        trial_args.sweep = False
        trial_args.search = False
        trial_args.epochs = args.sweep_epochs
        trial_args.top_actors = top_actors
        trial_args.batch_size = batch_size
        trial_args.compile = use_compile
        trial_args.output = str(
            sweep_dir / f"trial_{trial_index:02d}_actors{top_actors}_bs{batch_size}_compile{int(use_compile)}.pt"
        )
        trial_args.dataset_cache = str(
            sweep_dir / f"dataset_actors{top_actors}_seq{args.seq_len}_h{args.forecast_horizon}.npz"
        )
        trial_args.training_log = str(
            sweep_dir / f"training_actors{top_actors}_bs{batch_size}_compile{int(use_compile)}.jsonl"
        )
        print(
            f"sweep_trial={trial_index} "
            f"top_actors={top_actors} batch_size={batch_size} compile={use_compile}"
        )
        try:
            result = train(trial_args)
            metrics = result["evaluation"]["neural_thp"]
            records.append({
                "trial": trial_index,
                "top_actors": top_actors,
                "batch_size": batch_size,
                "compile": use_compile,
                "status": "ok",
                "mae": metrics["mae"],
                "rmse": metrics["rmse"],
                "mape": metrics["mape"],
                "completed_epochs": result["completed_epochs"],
                "output_path": str(result["output_path"]),
            })
        except RuntimeError as exc:
            if "out of memory" in str(exc).lower() and torch.cuda.is_available():
                torch.cuda.empty_cache()
            records.append({
                "trial": trial_index,
                "top_actors": top_actors,
                "batch_size": batch_size,
                "compile": use_compile,
                "status": "failed",
                "error": str(exc),
            })

    ok_records = [record for record in records if record["status"] == "ok"]
    best = min(ok_records, key=lambda record: record["mae"]) if ok_records else None
    summary = {
        "purpose": "top_actor_batch_compile_capacity_sweep",
        "best_trial": best,
        "trials": records,
    }
    summary_path = sweep_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"sweep_summary={summary_path}")
    if best:
        print(
            f"best_sweep_trial={best['trial']} "
            f"top_actors={best['top_actors']} batch_size={best['batch_size']} "
            f"compile={best['compile']} mae={best['mae']:.3f}"
        )
    return summary


if __name__ == "__main__":
    cli_args = parse_args()
    if cli_args.dry_run:
        arrays = build_training_arrays(cli_args)
        print_dataset_summary(arrays[0], arrays[3], arrays[7], arrays[8])
        train_idx, val_idx, split_position = time_based_split(
            arrays[4],
            arrays[6],
            cli_args.val_fraction,
        )
        print(
            "split_strategy=time_based "
            f"split_day_index={split_position} train_samples={len(train_idx)} val_samples={len(val_idx)}"
        )
    elif cli_args.sweep:
        run_capacity_sweep(cli_args)
    elif cli_args.search:
        run_hyperparameter_search(cli_args)
    else:
        train(cli_args)

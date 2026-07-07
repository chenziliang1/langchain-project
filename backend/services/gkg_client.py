"""
GKG BigQuery Client — Cost-controlled GDELT GKG data access.

CRITICAL: All queries MUST use _PARTITIONTIME filtering.
Without partition filters, a single query can scan 3.6TB (~$18).

This module enforces:
- Mandatory _PARTITIONTIME filters (query rejected otherwise)
- Dry-run cost estimation before execution
- Per-query byte limit (default 1GB)
- Daily quota limit (default 10GB)
- Result caching (1 hour TTL)
- Query logging for audit

Environment variables:
    GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
    BIGQUERY_PROJECT_ID=your-gcp-project-id
    BIGQUERY_DAILY_GB_LIMIT=10
    BIGQUERY_QUERY_TIMEOUT_SEC=30
    GKG_CACHE_TTL_SEC=3600
"""

import os
import time
import hashlib
import json
import asyncio
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# Optional: aiohttp for Ollama entity mapping
aiohttp = None
try:
    import aiohttp
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GKG_TABLE = "gdelt-bq.gdeltv2.gkg_partitioned"
GKG_PARTITIONED_TABLE = "gdelt-bq.gdeltv2.gkg_partitioned"

DEFAULT_MAX_BYTES_PER_QUERY = 1_000_000_000  # 1 GB
DEFAULT_DAILY_GB_LIMIT = 10
DEFAULT_QUERY_TIMEOUT_SEC = 30
DEFAULT_CACHE_TTL_SEC = 3600

COST_PER_GB = 0.005  # $5/TB = $0.005/GB (on-demand pricing)


# ---------------------------------------------------------------------------
# Cost Tracking
# ---------------------------------------------------------------------------

@dataclass
class _DailyQuota:
    """Thread-safe daily quota tracker (per-process)."""
    bytes_used: int = 0
    date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    query_count: int = 0

    def _check_date(self) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self.date:
            self.date = today
            self.bytes_used = 0
            self.query_count = 0

    def can_use(self, bytes_needed: int, daily_limit_bytes: int) -> Tuple[bool, str]:
        self._check_date()
        if self.bytes_used + bytes_needed > daily_limit_bytes:
            remaining = (daily_limit_bytes - self.bytes_used) / 1e9
            needed = bytes_needed / 1e9
            return False, (
                f"Daily quota exceeded: used {self.bytes_used/1e9:.2f}GB, "
                f"need {needed:.2f}GB, remaining {remaining:.2f}GB"
            )
        return True, ""

    def record(self, bytes_used: int) -> None:
        self._check_date()
        self.bytes_used += bytes_used
        self.query_count += 1

    def stats(self) -> Dict[str, Any]:
        self._check_date()
        return {
            "date": self.date,
            "bytes_used": self.bytes_used,
            "gb_used": round(self.bytes_used / 1e9, 4),
            "estimated_cost_usd": round(self.bytes_used / 1e9 * COST_PER_GB, 4),
            "query_count": self.query_count,
            "daily_limit_gb": DEFAULT_DAILY_GB_LIMIT,
        }


# Global quota tracker
_daily_quota = _DailyQuota()


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

@dataclass
class _GKGCacheEntry:
    result: Any
    cached_at: float


class _GKGCache:
    """In-memory cache for GKG query results."""

    def __init__(self, ttl: float = DEFAULT_CACHE_TTL_SEC):
        self._store: Dict[str, _GKGCacheEntry] = {}
        self._ttl = ttl

    def _key(self, query: str, params: Tuple) -> str:
        return hashlib.md5(f"{query}:{params}".encode()).hexdigest()

    def get(self, query: str, params: Tuple) -> Optional[Any]:
        key = self._key(query, params)
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.time() - entry.cached_at > self._ttl:
            del self._store[key]
            return None
        return entry.result

    def set(self, query: str, params: Tuple, result: Any) -> None:
        self._store[self._key(query, params)] = _GKGCacheEntry(result, time.time())

    def clear(self) -> None:
        self._store.clear()

    def stats(self) -> Dict[str, Any]:
        now = time.time()
        valid = sum(1 for e in self._store.values() if now - e.cached_at <= self._ttl)
        return {"total": len(self._store), "valid": valid, "ttl_seconds": self._ttl}


_gkg_cache = _GKGCache()


# ---------------------------------------------------------------------------
# Query Validation
# ---------------------------------------------------------------------------

_PARTITIONTIME_PATTERN = "_PARTITIONTIME"


def _validate_partition_filter(query: str) -> Tuple[bool, str]:
    """Ensure query contains _PARTITIONTIME filter."""
    if _PARTITIONTIME_PATTERN not in query.upper():
        return False, (
            "Query REJECTED: missing mandatory _PARTITIONTIME filter. "
            "All GKG queries must partition by date to control cost. "
            "Example: WHERE _PARTITIONTIME >= TIMESTAMP('2024-01-01')"
        )
    return True, ""


def _sanitize_columns(columns: List[str]) -> List[str]:
    """Validate column names to prevent injection."""
    allowed = {
        "GKGRECORDID", "DATE", "SourceCollectionIdentifier", "SourceCommonName",
        "DocumentIdentifier", "V1Themes", "V2Themes", "V1Locations", "V2Locations",
        "V1Persons", "V2Persons", "V1Orgs", "V2Orgs", "V1_5Tone", "V2Tone",
        "V2_1Themes", "V2_2Themes", "V2_3Themes", "V2_4Themes", "V2_5Themes",
        "V2_6Themes", "V2_7Themes", "V2_8Themes", "V2_9Themes", "V2_10Themes",
        "V2_11Themes", "V2_12Themes", "V2_13Themes", "V2_14Themes", "V2_15Themes",
        "V2_16Themes", "V2_17Themes", "V2_18Themes", "V2_19Themes", "V2_20Themes",
        "V2EnhancedThemes", "V2GCAM", "V2_1Counts", "V2_2Counts", "V2_3Counts",
        "V2_4Counts", "V2_5Counts", "V2_6Counts", "V2_7Counts", "V2_8Counts",
        "V2_9Counts", "V2_10Counts", "V2_11Counts", "V2_12Counts", "V2_13Counts",
        "V2_14Counts", "V2_15Counts", "V2_16Counts", "V2_17Counts", "V2_18Counts",
        "V2_19Counts", "V2_20Counts", "V2_21Counts", "V2_22Counts", "V2_23Counts",
        "V2_24Counts", "V2_25Counts", "V2_26Counts", "V2_27Counts", "V2_28Counts",
        "V2_29Counts", "V2_30Counts", "V2_31Counts", "V2_32Counts", "V2_33Counts",
        "V2_34Counts", "V2_35Counts", "V2_36Counts", "V2_37Counts", "V2_38Counts",
        "V2_39Counts", "V2_40Counts", "V2_41Counts", "V2_42Counts", "V2_43Counts",
        "V2_44Counts", "V2_45Counts", "V2_46Counts", "V2_47Counts", "V2_48Counts",
        "V2_49Counts", "V2_50Counts", "V2_51Counts", "V2_52Counts", "V2_53Counts",
        "V2_54Counts", "V2_55Counts", "V2_56Counts", "V2_57Counts", "V2_58Counts",
        "V2_59Counts", "V2_60Counts", "V2_61Counts", "V2_62Counts", "V2_63Counts",
        "V2_64Counts", "V2_65Counts", "V2_66Counts", "V2_67Counts", "V2_68Counts",
        "V2_69Counts", "V2_70Counts", "V2_71Counts", "V2_72Counts", "V2_73Counts",
        "V2_74Counts", "V2_75Counts", "V2_76Counts", "V2_77Counts", "V2_78Counts",
        "V2_79Counts", "V2_80Counts", "V2_81Counts", "V2_82Counts", "V2_83Counts",
        "V2_84Counts", "V2_85Counts", "V2_86Counts", "V2_87Counts", "V2_88Counts",
        "V2_89Counts", "V2_90Counts", "V2_91Counts", "V2_92Counts", "V2_93Counts",
        "V2_94Counts", "V2_95Counts", "V2_96Counts", "V2_97Counts", "V2_98Counts",
        "V2_99Counts", "V2_100Counts", "V2_1Locations", "V2_2Locations", "V2_3Locations",
        "V2_4Locations", "V2_5Locations", "V2_6Locations", "V2_7Locations", "V2_8Locations",
        "V2_9Locations", "V2_10Locations", "V2_11Locations", "V2_12Locations",
        "V2_13Locations", "V2_14Locations", "V2_15Locations", "V2_16Locations",
        "V2_17Locations", "V2_18Locations", "V2_19Locations", "V2_20Locations",
        "V2_21Locations", "V2_22Locations", "V2_23Locations", "V2_24Locations",
        "V2_25Locations", "V2_26Locations", "V2_27Locations", "V2_28Locations",
        "V2_29Locations", "V2_30Locations", "V2_31Locations", "V2_32Locations",
        "V2_33Locations", "V2_34Locations", "V2_35Locations", "V2_36Locations",
        "V2_37Locations", "V2_38Locations", "V2_39Locations", "V2_40Locations",
        "V2_41Locations", "V2_42Locations", "V2_43Locations", "V2_44Locations",
        "V2_45Locations", "V2_46Locations", "V2_47Locations", "V2_48Locations",
        "V2_49Locations", "V2_50Locations", "V2_51Locations", "V2_52Locations",
        "V2_53Locations", "V2_54Locations", "V2_55Locations", "V2_56Locations",
        "V2_57Locations", "V2_58Locations", "V2_59Locations", "V2_60Locations",
        "V2_61Locations", "V2_62Locations", "V2_63Locations", "V2_64Locations",
        "V2_65Locations", "V2_66Locations", "V2_67Locations", "V2_68Locations",
        "V2_69Locations", "V2_70Locations", "V2_71Locations", "V2_72Locations",
        "V2_73Locations", "V2_74Locations", "V2_75Locations", "V2_76Locations",
        "V2_77Locations", "V2_78Locations", "V2_79Locations", "V2_80Locations",
        "V2_81Locations", "V2_82Locations", "V2_83Locations", "V2_84Locations",
        "V2_85Locations", "V2_86Locations", "V2_87Locations", "V2_88Locations",
        "V2_89Locations", "V2_90Locations", "V2_91Locations", "V2_92Locations",
        "V2_93Locations", "V2_94Locations", "V2_95Locations", "V2_96Locations",
        "V2_97Locations", "V2_98Locations", "V2_99Locations", "V2_100Locations",
        "V2_1Persons", "V2_2Persons", "V2_3Persons", "V2_4Persons", "V2_5Persons",
        "V2_6Persons", "V2_7Persons", "V2_8Persons", "V2_9Persons", "V2_10Persons",
        "V2_11Persons", "V2_12Persons", "V2_13Persons", "V2_14Persons", "V2_15Persons",
        "V2_16Persons", "V2_17Persons", "V2_18Persons", "V2_19Persons", "V2_20Persons",
        "V2_21Persons", "V2_22Persons", "V2_23Persons", "V2_24Persons", "V2_25Persons",
        "V2_26Persons", "V2_27Persons", "V2_28Persons", "V2_29Persons", "V2_30Persons",
        "V2_31Persons", "V2_32Persons", "V2_33Persons", "V2_34Persons", "V2_35Persons",
        "V2_36Persons", "V2_37Persons", "V2_38Persons", "V2_39Persons", "V2_40Persons",
        "V2_41Persons", "V2_42Persons", "V2_43Persons", "V2_44Persons", "V2_45Persons",
        "V2_46Persons", "V2_47Persons", "V2_48Persons", "V2_49Persons", "V2_50Persons",
        "V2_51Persons", "V2_52Persons", "V2_53Persons", "V2_54Persons", "V2_55Persons",
        "V2_56Persons", "V2_57Persons", "V2_58Persons", "V2_59Persons", "V2_60Persons",
        "V2_61Persons", "V2_62Persons", "V2_63Persons", "V2_64Persons", "V2_65Persons",
        "V2_66Persons", "V2_67Persons", "V2_68Persons", "V2_69Persons", "V2_70Persons",
        "V2_71Persons", "V2_72Persons", "V2_73Persons", "V2_74Persons", "V2_75Persons",
        "V2_76Persons", "V2_77Persons", "V2_78Persons", "V2_79Persons", "V2_80Persons",
        "V2_81Persons", "V2_82Persons", "V2_83Persons", "V2_84Persons", "V2_85Persons",
        "V2_86Persons", "V2_87Persons", "V2_88Persons", "V2_89Persons", "V2_90Persons",
        "V2_91Persons", "V2_92Persons", "V2_93Persons", "V2_94Persons", "V2_95Persons",
        "V2_96Persons", "V2_97Persons", "V2_98Persons", "V2_99Persons", "V2_100Persons",
        "V2_1Orgs", "V2_2Orgs", "V2_3Orgs", "V2_4Orgs", "V2_5Orgs", "V2_6Orgs",
        "V2_7Orgs", "V2_8Orgs", "V2_9Orgs", "V2_10Orgs", "V2_11Orgs", "V2_12Orgs",
        "V2_13Orgs", "V2_14Orgs", "V2_15Orgs", "V2_16Orgs", "V2_17Orgs", "V2_18Orgs",
        "V2_19Orgs", "V2_20Orgs", "V2_21Orgs", "V2_22Orgs", "V2_23Orgs", "V2_24Orgs",
        "V2_25Orgs", "V2_26Orgs", "V2_27Orgs", "V2_28Orgs", "V2_29Orgs", "V2_30Orgs",
        "V2_31Orgs", "V2_32Orgs", "V2_33Orgs", "V2_34Orgs", "V2_35Orgs", "V2_36Orgs",
        "V2_37Orgs", "V2_38Orgs", "V2_39Orgs", "V2_40Orgs", "V2_41Orgs", "V2_42Orgs",
        "V2_43Orgs", "V2_44Orgs", "V2_45Orgs", "V2_46Orgs", "V2_47Orgs", "V2_48Orgs",
        "V2_49Orgs", "V2_50Orgs", "V2_51Orgs", "V2_52Orgs", "V2_53Orgs", "V2_54Orgs",
        "V2_55Orgs", "V2_56Orgs", "V2_57Orgs", "V2_58Orgs", "V2_59Orgs", "V2_60Orgs",
        "V2_61Orgs", "V2_62Orgs", "V2_63Orgs", "V2_64Orgs", "V2_65Orgs", "V2_66Orgs",
        "V2_67Orgs", "V2_68Orgs", "V2_69Orgs", "V2_70Orgs", "V2_71Orgs", "V2_72Orgs",
        "V2_73Orgs", "V2_74Orgs", "V2_75Orgs", "V2_76Orgs", "V2_77Orgs", "V2_78Orgs",
        "V2_79Orgs", "V2_80Orgs", "V2_81Orgs", "V2_82Orgs", "V2_83Orgs", "V2_84Orgs",
        "V2_85Orgs", "V2_86Orgs", "V2_87Orgs", "V2_88Orgs", "V2_89Orgs", "V2_90Orgs",
        "V2_91Orgs", "V2_92Orgs", "V2_93Orgs", "V2_94Orgs", "V2_95Orgs", "V2_96Orgs",
        "V2_97Orgs", "V2_98Orgs", "V2_99Orgs", "V2_100Orgs",
    }
    safe = []
    for c in columns:
        c_clean = c.strip()
        if c_clean in allowed or c_clean.upper().startswith("COUNT(") or c_clean.upper().startswith("SUM("):
            safe.append(c_clean)
        else:
            raise ValueError(f"Disallowed column name: {c_clean}")
    return safe


# ---------------------------------------------------------------------------
# GKG Client
# ---------------------------------------------------------------------------

class GKGClient:
    """Cost-controlled GDELT GKG BigQuery client.

    Usage:
        client = GKGClient()
        result = await client.get_entity_themes("Biden", ("2024-01-01", "2024-01-07"))
    """

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        project_id: Optional[str] = None,
        max_bytes_per_query: int = DEFAULT_MAX_BYTES_PER_QUERY,
        daily_gb_limit: int = DEFAULT_DAILY_GB_LIMIT,
        query_timeout_sec: int = DEFAULT_QUERY_TIMEOUT_SEC,
    ):
        self._credentials_path = credentials_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        self._project_id = project_id or os.getenv("BIGQUERY_PROJECT_ID")
        self._max_bytes = max_bytes_per_query
        self._daily_limit_bytes = daily_gb_limit * 1_000_000_000
        self._timeout = query_timeout_sec
        self._client = None
        self._available = False
        self._init_error = None

    def _get_client(self):
        """Lazy initialization of BigQuery client."""
        if self._client is not None:
            return self._client

        try:
            from google.cloud import bigquery
            from google.oauth2 import service_account

            if self._credentials_path and os.path.exists(self._credentials_path):
                credentials = service_account.Credentials.from_service_account_file(
                    self._credentials_path
                )
                self._client = bigquery.Client(
                    project=self._project_id,
                    credentials=credentials,
                )
            else:
                # Use Application Default Credentials
                self._client = bigquery.Client(project=self._project_id)

            self._available = True
            print(f"[GKGClient] BigQuery client initialized (project={self._project_id})", flush=True)
            return self._client

        except Exception as e:
            self._available = False
            self._init_error = str(e)
            print(f"[GKGClient] Failed to initialize: {e}", flush=True)
            return None

    @property
    def available(self) -> bool:
        return self._get_client() is not None

    @property
    def init_error(self) -> Optional[str]:
        return self._init_error

    # -- Core query execution with cost guard --

    async def query(
        self,
        sql: str,
        params: Optional[Tuple] = None,
        max_bytes: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Execute a GKG query with full cost protection.

        Steps:
        1. Validate _PARTITIONTIME filter is present
        2. Check cache
        3. Dry-run to estimate bytes
        4. Check daily quota
        5. Execute query
        6. Record cost and cache result
        """
        max_bytes = max_bytes or self._max_bytes
        params = params or ()

        # 1. Validate partition filter
        ok, msg = _validate_partition_filter(sql)
        if not ok:
            return {"error": "VALIDATION_FAILED", "message": msg, "query": sql}

        # 2. Check cache
        cached = _gkg_cache.get(sql, params)
        if cached is not None:
            return {
                "cached": True,
                "data": cached,
                "query": sql,
                "bytes_processed": 0,
                "cost_usd": 0,
            }

        # 3. Get client
        client = self._get_client()
        if client is None:
            return {
                "error": "CLIENT_NOT_AVAILABLE",
                "message": self._init_error or "BigQuery client not initialized",
                "query": sql,
            }

        # 4. Dry-run to estimate cost
        try:
            from google.cloud import bigquery

            job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=True)
            dry_job = client.query(sql, job_config=job_config)
            estimated_bytes = dry_job.total_bytes_processed or 0

            if estimated_bytes > max_bytes:
                return {
                    "error": "COST_LIMIT",
                    "message": (
                        f"Query would process {estimated_bytes / 1e9:.2f}GB, "
                        f"exceeds limit of {max_bytes / 1e9:.2f}GB. "
                        f"Narrow your date range or add more filters."
                    ),
                    "estimated_bytes": estimated_bytes,
                    "query": sql,
                }

            # 5. Check daily quota
            ok, msg = _daily_quota.can_use(estimated_bytes, self._daily_limit_bytes)
            if not ok:
                return {
                    "error": "DAILY_QUOTA_EXCEEDED",
                    "message": msg,
                    "query": sql,
                }

        except Exception as e:
            return {
                "error": "DRY_RUN_FAILED",
                "message": str(e),
                "query": sql,
            }

        # 6. Execute actual query with timeout
        try:
            loop = asyncio.get_event_loop()
            job_config = bigquery.QueryJobConfig(use_query_cache=True)

            def _run_query():
                return client.query(sql, job_config=job_config).result()

            result = await asyncio.wait_for(
                loop.run_in_executor(None, _run_query),
                timeout=self._timeout,
            )

            # Convert to list of dicts
            rows = []
            for row in result:
                row_dict = {}
                for key, value in row.items():
                    # Handle date/timestamp types
                    if hasattr(value, "isoformat"):
                        row_dict[key] = value.isoformat()
                    else:
                        row_dict[key] = value
                rows.append(row_dict)

            actual_bytes = result.total_bytes_processed or estimated_bytes
            cost_usd = actual_bytes / 1e9 * COST_PER_GB

            # Record usage
            _daily_quota.record(actual_bytes)

            # Cache result
            _gkg_cache.set(sql, params, rows)

            print(
                f"[GKGClient] Query OK: {len(rows)} rows, "
                f"{actual_bytes / 1e6:.2f}MB processed, ${cost_usd:.4f}",
                flush=True,
            )

            return {
                "data": rows,
                "row_count": len(rows),
                "bytes_processed": actual_bytes,
                "cost_usd": round(cost_usd, 6),
                "query": sql,
                "cached": False,
            }

        except asyncio.TimeoutError:
            return {
                "error": "TIMEOUT",
                "message": f"Query timed out after {self._timeout}s",
                "query": sql,
            }
        except Exception as e:
            return {
                "error": "QUERY_FAILED",
                "message": str(e),
                "query": sql,
            }

    # -- High-level GKG query methods --

    async def get_event_gkg_records(
        self, date: str, event_id: Optional[int] = None, limit: int = 10
    ) -> Dict[str, Any]:
        """Query GKG records for a specific date (and optionally event-related docs).

        Args:
            date: YYYY-MM-DD format
            event_id: Optional GlobalEventID to filter by (not directly in GKG, but we can search by theme)
            limit: Max rows to return
        """
        next_day = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

        columns = ["DocumentIdentifier", "V2Themes", "V2Persons", "V2Orgs", "V2Tone", "SourceCommonName"]

        sql = f"""
        SELECT {', '.join(columns)}
        FROM `{GKG_PARTITIONED_TABLE}`
        WHERE _PARTITIONTIME >= TIMESTAMP('{date}')
          AND _PARTITIONTIME < TIMESTAMP('{next_day}')
        LIMIT {limit}
        """

        return await self.query(sql, max_bytes=500_000_000)  # 500MB limit for single-day

    async def get_entity_themes(
        self, entity_name: str, date_range: Tuple[str, str], limit: int = 100
    ) -> Dict[str, Any]:
        """Get theme evolution for an entity over a date range.

        Parses V2Themes (semicolon-delimited, comma-scored) to extract top themes.
        """
        start, end = date_range
        # Add one day to end for exclusive upper bound
        end_dt = datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1)
        end_exclusive = end_dt.strftime("%Y-%m-%d")

        # Limit date range to control cost
        days = (end_dt - datetime.strptime(start, "%Y-%m-%d")).days
        if days > 7:
            return {
                "error": "DATE_RANGE_TOO_LARGE",
                "message": f"Date range {days} days exceeds 7-day limit for theme queries. Please narrow.",
            }

        search_condition = await _build_entity_search_condition(entity_name)
        sql = f"""
        SELECT
          DATE(_PARTITIONTIME) as date,
          V2Themes,
          V2Tone
        FROM `{GKG_PARTITIONED_TABLE}`
        WHERE _PARTITIONTIME >= TIMESTAMP('{start}')
          AND _PARTITIONTIME < TIMESTAMP('{end_exclusive}')
          AND ({search_condition})
        LIMIT {limit}
        """

        result = await self.query(sql, max_bytes=1_000_000_000)
        if result.get("error"):
            return result

        # Parse themes from results
        rows = result.get("data", [])
        parsed = _parse_gkg_themes(rows)
        result["parsed_themes"] = parsed
        return result

    async def get_cooccurring_entities(
        self, entity_name: str, date: str, limit: int = 50
    ) -> Dict[str, Any]:
        """Find entities that co-occur with the given entity on a specific date.

        Returns person and organization co-occurrence counts.
        """
        next_day = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

        search_condition = await _build_entity_search_condition(entity_name)
        sql = f"""
        SELECT
          V2Persons,
          V2Organizations,
          V2Themes
        FROM `{GKG_PARTITIONED_TABLE}`
        WHERE _PARTITIONTIME >= TIMESTAMP('{date}')
          AND _PARTITIONTIME < TIMESTAMP('{next_day}')
          AND ({search_condition})
        LIMIT {limit}
        """

        result = await self.query(sql, max_bytes=500_000_000)
        if result.get("error"):
            return result

        # Parse co-occurring entities
        rows = result.get("data", [])
        entity_variants = await _normalize_actor_name(entity_name)
        cooccurring = _parse_cooccurring_entities(rows, entity_name, entity_variants)
        result["cooccurring_entities"] = cooccurring
        return result

    async def get_tone_timeline(
        self, entity_name: str, date_range: Tuple[str, str]
    ) -> Dict[str, Any]:
        """Get average tone over time for an entity.

        V2Tone format: comma-separated values: tone, polarity, ...
        We extract the first value (average tone).
        """
        start, end = date_range
        end_dt = datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1)
        end_exclusive = end_dt.strftime("%Y-%m-%d")

        days = (end_dt - datetime.strptime(start, "%Y-%m-%d")).days
        if days > 14:
            return {
                "error": "DATE_RANGE_TOO_LARGE",
                "message": f"Date range {days} days exceeds 14-day limit for tone queries.",
            }

        search_condition = await _build_entity_search_condition(entity_name)
        sql = f"""
        SELECT
          DATE(_PARTITIONTIME) as date,
          AVG(SAFE_CAST(SPLIT(V2Tone, ',')[OFFSET(0)] AS FLOAT64)) as avg_tone,
          COUNT(*) as mention_count
        FROM `{GKG_PARTITIONED_TABLE}`
        WHERE _PARTITIONTIME >= TIMESTAMP('{start}')
          AND _PARTITIONTIME < TIMESTAMP('{end_exclusive}')
          AND ({search_condition})
        GROUP BY date
        ORDER BY date
        """

        return await self.query(sql, max_bytes=1_000_000_000)

    # -- Storyline Precision: GKG Theme Overlap --

    async def score_events_by_theme_overlap(
        self,
        seed_actor: str,
        seed_date: str,
        candidate_events: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Attach theme_overlap score to each candidate event (soft scoring, no filtering).
        
        Unlike filter_events_by_theme_overlap, this keeps ALL events and just
        attaches a score for downstream ranking.
        """
        if not self.available or not candidate_events:
            return candidate_events
        
        # 1. Get seed themes
        seed_themes_result = await self.get_entity_themes(
            seed_actor, (seed_date, seed_date), limit=100
        )
        if seed_themes_result.get("error"):
            print(f"[GKG] Seed theme query failed: {seed_themes_result.get('message')}", flush=True)
            return candidate_events
        
        seed_themes = set()
        for t in seed_themes_result.get("parsed_themes", {}).get("top_themes", []):
            seed_themes.add(t["theme"])
        
        if not seed_themes:
            return candidate_events
        
        # 2. Batch candidates by date to minimize queries
        from collections import defaultdict
        date_to_events = defaultdict(list)
        for evt in candidate_events:
            date_to_events[evt.get("SQLDATE")].append(evt)
        
        # 3. Query themes for each unique date
        date_themes = {}
        for date_str in date_to_events:
            result = await self.get_entity_themes(
                seed_actor, (date_str, date_str), limit=100
            )
            if not result.get("error"):
                themes = set()
                for t in result.get("parsed_themes", {}).get("top_themes", []):
                    themes.add(t["theme"])
                date_themes[date_str] = themes
        
        # 4. Attach overlap score to ALL events (no filtering)
        for evt in candidate_events:
            evt_themes = date_themes.get(evt.get("SQLDATE"), set())
            if evt_themes:
                intersection = seed_themes & evt_themes
                union = seed_themes | evt_themes
                overlap = len(intersection) / len(union) if union else 0
                evt["theme_overlap"] = round(overlap, 3)
                evt["shared_themes"] = list(intersection)[:5]
            else:
                evt["theme_overlap"] = 0.0
                evt["shared_themes"] = []
        
        return candidate_events

    # -- Legacy filter (kept for backward compat) --

    async def filter_events_by_theme_overlap(
        self,
        seed_actor: str,
        seed_date: str,
        candidate_events: List[Dict[str, Any]],
        min_overlap_ratio: float = 0.15,
    ) -> List[Dict[str, Any]]:
        """Legacy: hard-filter by theme overlap. Use score_events_by_theme_overlap for ranking."""
        scored = await self.score_events_by_theme_overlap(seed_actor, seed_date, candidate_events)
        return [e for e in scored if e.get("theme_overlap", 0) >= min_overlap_ratio]

    # -- Storyline Precision: Mentions Shared-Articles (same article) --

    async def get_shared_mention_articles(
        self,
        seed_event_id: int,
        candidate_event_ids: List[int],
        date_range: Tuple[str, str],
    ) -> Dict[int, Dict[str, Any]]:
        """Find shared ARTICLES (not just sources) between seed and each candidate.
        
        This is much more precise than shared-source: two events appearing in the
        exact same article are almost certainly part of the same story.
        
        Returns per-candidate:
            - shared_articles: count of exact article matches
            - shared_article_urls: list of shared MentionIdentifiers (URLs)
            - shared_sources: count of distinct source names
        """
        if not self.available or not candidate_event_ids:
            return {}
        
        start, end = date_range
        end_dt = datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1)
        end_exclusive = end_dt.strftime("%Y-%m-%d")
        
        id_list = ','.join(str(gid) for gid in candidate_event_ids)
        
        sql = f"""
        WITH seed_articles AS (
          SELECT MentionSourceName, MentionIdentifier
          FROM `gdelt-bq.gdeltv2.eventmentions_partitioned`
          WHERE _PARTITIONTIME >= TIMESTAMP('{start}')
            AND _PARTITIONTIME < TIMESTAMP('{end_exclusive}')
            AND GLOBALEVENTID = {seed_event_id}
        )
        SELECT
          c.GLOBALEVENTID as event_id,
          COUNT(*) as shared_articles,
          COUNT(DISTINCT c.MentionSourceName) as shared_sources,
          ARRAY_AGG(DISTINCT c.MentionIdentifier LIMIT 5) as sample_urls
        FROM `gdelt-bq.gdeltv2.eventmentions_partitioned` c
        JOIN seed_articles s
          ON c.MentionSourceName = s.MentionSourceName
          AND c.MentionIdentifier = s.MentionIdentifier
        WHERE c._PARTITIONTIME >= TIMESTAMP('{start}')
          AND c._PARTITIONTIME < TIMESTAMP('{end_exclusive}')
          AND c.GLOBALEVENTID IN ({id_list})
          AND c.GLOBALEVENTID != {seed_event_id}
        GROUP BY c.GLOBALEVENTID
        """
        
        result = await self.query(sql, max_bytes=500_000_000)
        if result.get("error"):
            print(f"[GKG] Shared-articles query failed: {result.get('message')}", flush=True)
            return {}
        
        shared = {}
        for row in result.get("data", []):
            evt_id = int(row["event_id"])
            shared[evt_id] = {
                "shared_articles": int(row["shared_articles"]),
                "shared_sources": int(row["shared_sources"]),
                "sample_urls": row.get("sample_urls", []),
            }
        
        print(
            f"[GKG] Shared articles: seed={seed_event_id}, "
            f"found matches for {len(shared)}/{len(candidate_event_ids)} candidates",
            flush=True,
        )
        return shared

    # -- Legacy: shared sources only (kept for backward compat) --

    async def get_shared_mention_sources(
        self,
        seed_event_id: int,
        candidate_event_ids: List[int],
        date_range: Tuple[str, str],
    ) -> Dict[int, int]:
        """Legacy: returns only shared source counts."""
        result = await self.get_shared_mention_articles(
            seed_event_id, candidate_event_ids, date_range
        )
        return {k: v["shared_sources"] for k, v in result.items()}

    # -- Stats --

    def get_cost_stats(self) -> Dict[str, Any]:
        """Return current cost usage statistics."""
        return {
            "quota": _daily_quota.stats(),
            "cache": _gkg_cache.stats(),
            "client_available": self.available,
            "client_error": self.init_error,
        }

    @staticmethod
    def clear_cache() -> None:
        _gkg_cache.clear()


# ---------------------------------------------------------------------------
# GKG Data Parsers
# ---------------------------------------------------------------------------

def _parse_gkg_themes(rows: List[Dict]) -> Dict[str, Any]:
    """Parse V2Themes from GKG rows into structured theme data.

    V2Themes format: "THEME1,score1;THEME2,score2;..."
    """
    from collections import Counter

    all_themes = Counter()
    themes_by_date: Dict[str, Counter] = {}

    for row in rows:
        date = row.get("date", "unknown")
        themes_str = row.get("V2Themes", "")
        if not themes_str:
            continue

        day_themes = themes_by_date.setdefault(date, Counter())

        for theme_entry in themes_str.split(";"):
            if not theme_entry:
                continue
            parts = theme_entry.split(",")
            theme_name = parts[0].strip()
            if theme_name:
                all_themes[theme_name] += 1
                day_themes[theme_name] += 1

    # Top themes overall
    top_themes = [
        {"theme": name, "count": count}
        for name, count in all_themes.most_common(20)
    ]

    # Themes by date (top 5 per day)
    themes_over_time = []
    for date in sorted(themes_by_date.keys()):
        day_counter = themes_by_date[date]
        themes_over_time.append({
            "date": date,
            "top_themes": [
                {"theme": name, "count": count}
                for name, count in day_counter.most_common(5)
            ],
        })

    return {
        "total_records": len(rows),
        "unique_themes": len(all_themes),
        "top_themes": top_themes,
        "themes_over_time": themes_over_time,
    }


async def _normalize_actor_name(actor_name: str) -> List[str]:
    """Normalize GDELT Events actor name to GKG entity search terms via Ollama LLM.
    
    Uses qwen2.5:3b to dynamically map any actor code to natural language
    entity names. Falls back to basic heuristics if Ollama is unavailable.
    
    Examples:
        ISRAELI -> ["Israel", "Israeli", "Army Israeli", "Israel Defense Forces"]
        BIDEN -> ["Biden", "Joe Biden", "Joseph Biden"]
        REGIME -> ["Regime", "Government", "Administration"]
        GOV -> ["Government", "Administration", "State"]
    """
    if not actor_name:
        return []
    
    name = actor_name.strip()
    upper = name.upper()
    
    # Check cache first
    cache_key = f"entity_map:{upper}"
    cached = _gkg_cache.get(cache_key, ())
    if cached is not None:
        return cached
    
    # Build Ollama prompt
    prompt = (
        "You are a GDELT entity translator. Convert actor codes to natural language names.\n"
        "Output ONLY a JSON array of strings. No explanation.\n\n"
        'ISRAELI -> ["Israel","Israeli","Army Israeli","Israel Defense Forces"]\n'
        'BIDEN -> ["Biden","Joe Biden","Joseph Biden"]\n'
        'GOV -> ["Government","Administration","State"]\n'
        'REGIME -> ["Regime","Government","Administration"]\n'
        'TALIBAN -> ["Taliban","Afghan Taliban","Islamic Emirate"]\n'
        'POLICE -> ["Police","Law Enforcement","Security Forces"]\n'
        'USA -> ["United States","America","American","US"]\n'
        'CHINESE -> ["China","Chinese","People Republic Of China"]\n'
        f"{name} ->"
    )
    
    # Call Ollama
    ollama_url = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{ollama_url}/api/generate",
                json={
                    "model": "qwen2.5:3b",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.05, "num_predict": 80, "top_p": 0.9},
                },
                timeout=aiohttp.ClientTimeout(total=3.0),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    text = data.get("response", "").strip()
                    start = text.find("[")
                    end = text.rfind("]")
                    if start >= 0 and end > start:
                        try:
                            variants = json.loads(text[start:end+1])
                            if isinstance(variants, list):
                                result = [str(v).strip() for v in variants if v]
                                result = list(dict.fromkeys(result + [name, name.title()]))
                                _gkg_cache.set(cache_key, (), result)
                                return result
                        except json.JSONDecodeError:
                            pass
    except Exception:
        pass
    
    # Fallback: basic heuristics
    variants = {name, name.title()}
    if upper.endswith("AN") and len(upper) > 4:
        root = name[:-2]
        variants.add(root + "a")
    if upper.endswith("ISH") and len(upper) > 5:
        root = name[:-3]
        variants.add(root + "ain")
    if upper.endswith("ESE") and len(upper) > 5:
        variants.add(name[:-3])
    if upper.endswith("IAN") and len(upper) > 5:
        variants.add(name[:-3] + "a")
    if upper.endswith("I") and len(upper) > 3:
        variants.add(name[:-1])
    
    result = list(variants)
    _gkg_cache.set(cache_key, (), result)
    return result


async def _build_entity_search_condition(entity_name: str) -> str:
    """Build SQL LIKE conditions for entity search with multiple variants."""
    variants = await _normalize_actor_name(entity_name)
    if not variants:
        return "1=0"  # Always false
    
    conditions = []
    for v in variants:
        # Escape single quotes
        safe = v.replace("'", "\\'")
        conditions.append(f"V2Persons LIKE '%{safe}%'")
        conditions.append(f"V2Organizations LIKE '%{safe}%'")
    
    return " OR ".join(conditions)


def _parse_cooccurring_entities(rows: List[Dict], target_entity: str, entity_variants: Optional[List[str]] = None) -> Dict[str, Any]:
    """Parse V2Persons and V2Organizations to find co-occurring entities."""
    from collections import Counter

    persons = Counter()
    orgs = Counter()
    themes = Counter()

    target_lower = target_entity.lower()
    # Use provided variants or just the entity name itself
    target_variants = {v.lower() for v in (entity_variants or [target_entity])}
    target_variants.add(target_lower)

    for row in rows:
        # Parse persons
        persons_str = row.get("V2Persons", "")
        if persons_str:
            for entry in persons_str.split(";"):
                if not entry:
                    continue
                name = entry.split(",")[0].strip()
                if name:
                    name_lower = name.lower()
                    # Skip if name contains any target variant
                    if not any(tv in name_lower for tv in target_variants):
                        persons[name] += 1

        # Parse organizations
        orgs_str = row.get("V2Organizations", "")
        if orgs_str:
            for entry in orgs_str.split(";"):
                if not entry:
                    continue
                name = entry.split(",")[0].strip()
                if name:
                    name_lower = name.lower()
                    if not any(tv in name_lower for tv in target_variants):
                        orgs[name] += 1

        # Parse themes
        themes_str = row.get("V2Themes", "")
        if themes_str:
            for entry in themes_str.split(";"):
                if not entry:
                    continue
                theme = entry.split(",")[0].strip()
                if theme:
                    themes[theme] += 1

    return {
        "total_records": len(rows),
        "top_persons": [{"name": n, "count": c} for n, c in persons.most_common(15)],
        "top_organizations": [{"name": n, "count": c} for n, c in orgs.most_common(15)],
        "top_themes": [{"theme": t, "count": c} for t, c in themes.most_common(15)],
    }


# Singleton
gkg_client = GKGClient()

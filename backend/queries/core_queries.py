"""
Core Queries — Shared SQL layer for FastAPI DataService and internal services.

All data-fetching logic lives here. Callers handle formatting only.
"""

import asyncio
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from .query_utils import parse_time_hint, parse_region_input, sanitize_text


# ============================================================================
# Location condition builder (uses parse_region_input for smart matching)
# ============================================================================

def _build_smart_location_condition(location_hint: Optional[str], location_exact: Optional[str]) -> tuple[str, list]:
    """Build location SQL using parse_region_input for alias support and prefix indexing."""
    if location_exact:
        if len(location_exact) <= 3 and location_exact.isalpha():
            return " AND ActionGeo_CountryCode = %s", [location_exact.upper()[:3]]
        return " AND ActionGeo_FullName = %s", [location_exact]
    
    if not location_hint:
        return "", []
    
    terms = parse_region_input(location_hint)
    conditions = []
    params = []
    
    for term in terms:
        if not term or len(term) < 2:
            continue
        # Prefix match on full location name (index-friendly)
        conditions.append("ActionGeo_FullName LIKE %s")
        params.append(f"{term}%")
        # Match city/state within comma-separated location
        conditions.append("ActionGeo_FullName LIKE %s")
        params.append(f"%, {term}%")
        # Country code exact match for short alpha terms
        if len(term) <= 3 and term.isalpha():
            conditions.append("ActionGeo_CountryCode = %s")
            params.append(term.upper()[:3])
    
    if not conditions:
        return "", []
    
    return f" AND ({' OR '.join(conditions)})", params


def _build_actor_condition(actor: Optional[str], actor_exact: Optional[str]) -> tuple[str, list]:
    """Build actor SQL condition. Exact match uses index; fuzzy uses LIKE."""
    if actor_exact:
        return " AND (Actor1Name = %s OR Actor2Name = %s)", [actor_exact, actor_exact]
    if actor:
        return " AND (Actor1Name LIKE %s OR Actor2Name LIKE %s)", [f"%{actor}%", f"%{actor}%"]
    return "", []


async def query_suggest_actors(pool, prefix: str, limit: int = 10) -> List[str]:
    """Return actor names matching prefix using indexed LIKE prefix search.
    Results ordered by frequency (hot actors first)."""
    prefix_up = prefix.upper()
    rows = await pool.fetchall(
        f"""SELECT Actor1Name as name, COUNT(*) as cnt FROM {DEFAULT_TABLE}
            WHERE Actor1Name LIKE %s
            GROUP BY name
            ORDER BY cnt DESC
            LIMIT %s""",
        (f"{prefix_up}%", limit)
    )
    return [r['name'] for r in rows if r['name']]


# State abbreviation / name -> canonical location mapping for fast suggestion
_us_state_suggestions: dict[str, str] = {
    # Abbreviations
    'AL': 'Alabama, United States', 'AK': 'Alaska, United States', 'AZ': 'Arizona, United States',
    'AR': 'Arkansas, United States', 'CA': 'California, United States', 'CO': 'Colorado, United States',
    'CT': 'Connecticut, United States', 'DE': 'Delaware, United States', 'FL': 'Florida, United States',
    'GA': 'Georgia, United States', 'HI': 'Hawaii, United States', 'ID': 'Idaho, United States',
    'IL': 'Illinois, United States', 'IN': 'Indiana, United States', 'IA': 'Iowa, United States',
    'KS': 'Kansas, United States', 'KY': 'Kentucky, United States', 'LA': 'Louisiana, United States',
    'ME': 'Maine, United States', 'MD': 'Maryland, United States', 'MA': 'Massachusetts, United States',
    'MI': 'Michigan, United States', 'MN': 'Minnesota, United States', 'MS': 'Mississippi, United States',
    'MO': 'Missouri, United States', 'MT': 'Montana, United States', 'NE': 'Nebraska, United States',
    'NV': 'Nevada, United States', 'NH': 'New Hampshire, United States', 'NJ': 'New Jersey, United States',
    'NM': 'New Mexico, United States', 'NY': 'New York, United States', 'NC': 'North Carolina, United States',
    'ND': 'North Dakota, United States', 'OH': 'Ohio, United States', 'OK': 'Oklahoma, United States',
    'OR': 'Oregon, United States', 'PA': 'Pennsylvania, United States', 'RI': 'Rhode Island, United States',
    'SC': 'South Carolina, United States', 'SD': 'South Dakota, United States', 'TN': 'Tennessee, United States',
    'TX': 'Texas, United States', 'UT': 'Utah, United States', 'VT': 'Vermont, United States',
    'VA': 'Virginia, United States', 'WA': 'Washington, United States', 'WV': 'West Virginia, United States',
    'WI': 'Wisconsin, United States', 'WY': 'Wyoming, United States', 'DC': 'Washington, District of Columbia, United States',
}

# Build reverse lookup by state name (lowercase) -> canonical location
_us_state_by_name: dict[str, str] = {}
for _abbr, _loc in _us_state_suggestions.items():
    # Extract state name from "State, United States"
    _state_name = _loc.split(',')[0].strip().lower()
    _us_state_by_name[_state_name] = _loc
    # Also add abbreviation
    _us_state_by_name[_abbr.lower()] = _loc

# Add multi-word states
_us_state_by_name.update({
    'new york': 'New York, United States',
    'north carolina': 'North Carolina, United States',
    'south carolina': 'South Carolina, United States',
    'north dakota': 'North Dakota, United States',
    'south dakota': 'South Dakota, United States',
    'west virginia': 'West Virginia, United States',
    'new hampshire': 'New Hampshire, United States',
    'new jersey': 'New Jersey, United States',
    'new mexico': 'New Mexico, United States',
    'rhode island': 'Rhode Island, United States',
    'district of columbia': 'Washington, District of Columbia, United States',
})


async def query_suggest_locations(pool, prefix: str, limit: int = 10) -> List[str]:
    """Return location names matching prefix or alias using indexed LIKE prefix search.
    
    Collects results from all parsed terms (e.g. TX -> Texas) so abbreviations
    show full-name matches in suggestions. State full names are prioritized first.
    """
    terms = parse_region_input(prefix)
    state_matches: list[str] = []
    other_results: set[str] = set()
    
    # Fast-path: state abbreviations OR full state names -> canonical location
    for term in terms:
        term_up = term.upper()
        if term_up in _us_state_suggestions:
            state_name = _us_state_suggestions[term_up]
            if state_name not in state_matches:
                state_matches.append(state_name)
        # Also check by full state name (e.g. "Texas" -> "Texas, United States")
        term_lower = term.strip().lower()
        if term_lower in _us_state_by_name:
            state_name = _us_state_by_name[term_lower]
            if state_name not in state_matches:
                state_matches.append(state_name)
    
    for term in terms:
        if not term or len(term) < 2:
            continue
        rows = await pool.fetchall(
            f"""SELECT DISTINCT ActionGeo_FullName as name FROM {DEFAULT_TABLE}
                WHERE ActionGeo_FullName LIKE %s
                LIMIT %s""",
            (f"{term}%", limit)
        )
        for r in rows:
            name = r['name']
            if name and name not in state_matches:
                other_results.add(name)
    
    # State names first, then others sorted alphabetically
    combined = state_matches + sorted(other_results)
    return combined[:limit]


# ============================================================================
# Optimized search SQL builder
# ============================================================================

def _build_optimized_search_sql(
    start_date: str,
    end_date: str,
    location_hint: Optional[str],
    location_exact: Optional[str],
    event_type: Optional[str],
    actor: Optional[str],
    actor_exact: Optional[str],
    query_text: Optional[str] = None,
    max_results: int = 20,
) -> tuple[str, list]:
    """Build optimized search SQL. Uses subquery + FORCE INDEX for exact matches.
    
    Keyword search: When query_text is provided, we search event_fingerprints.headline/summary
    via a separate subquery and UNION with the main results. This avoids full-table scans on
    the large events_table while still supporting text search on the smaller fingerprint table.
    """
    
    loc_cond, loc_params = _build_smart_location_condition(location_hint, location_exact)
    act_cond, act_params = _build_actor_condition(actor, actor_exact)
    
    # Determine best index hint for the inner query
    force_index = ""
    if actor_exact and not location_exact:
        force_index = "FORCE INDEX (idx_date_actor)"
    elif location_exact and not actor_exact:
        force_index = "FORCE INDEX (idx_date_geo)"
    
    # Event type condition
    type_sql = ""
    if event_type and event_type != "any":
        type_conditions = {
            "conflict": "GoldsteinScale < -5",
            "cooperation": "GoldsteinScale > 5",
            "protest": "EventRootCode = '14'",
        }
        if event_type in type_conditions:
            type_sql = f" AND {type_conditions[event_type]}"
    
    # Build inner WHERE for subquery
    inner_where = f"SQLDATE BETWEEN %s AND %s"
    inner_params = [start_date, end_date]
    
    if actor_exact:
        inner_where += " AND Actor1Name = %s"
        inner_params.append(actor_exact)
    elif actor:
        inner_where += " AND (Actor1Name LIKE %s OR Actor2Name LIKE %s)"
        inner_params.extend([f"%{actor}%", f"%{actor}%"])
    
    if location_exact:
        if len(location_exact) <= 3 and location_exact.isalpha():
            inner_where += " AND ActionGeo_CountryCode = %s"
            inner_params.append(location_exact.upper()[:3])
        else:
            inner_where += " AND ActionGeo_FullName = %s"
            inner_params.append(location_exact)
    elif location_hint:
        # For inner query with hint, use simplified location condition
        hint_terms = parse_region_input(location_hint)
        loc_conds = []
        for term in hint_terms:
            if not term or len(term) < 2:
                continue
            loc_conds.append("ActionGeo_FullName LIKE %s")
            inner_params.append(f"{term}%")
            if len(term) <= 3 and term.isalpha():
                loc_conds.append("ActionGeo_CountryCode = %s")
                inner_params.append(term.upper()[:3])
        if loc_conds:
            inner_where += f" AND ({' OR '.join(loc_conds)})"
    
    inner_where += type_sql
    
    # Keyword search via event_fingerprints (smaller table, has headline/summary)
    keyword_sql = ""
    keyword_params = []
    if query_text and query_text.strip():
        kw = query_text.strip()
        # Search headline and summary in event_fingerprints, then join back to events_table
        keyword_sql = f"""
        SELECT
            e.GlobalEventID, CAST(e.SQLDATE AS CHAR) as SQLDATE,
            e.Actor1Name, e.Actor2Name,
            e.EventCode, e.GoldsteinScale, e.AvgTone, e.NumArticles,
            e.ActionGeo_FullName, e.ActionGeo_CountryCode,
            e.ActionGeo_Lat, e.ActionGeo_Long,
            f.fingerprint, f.headline, f.summary, f.event_type_label, f.severity_score
        FROM event_fingerprints f
        JOIN {DEFAULT_TABLE} e ON e.GlobalEventID = f.global_event_id
        WHERE e.SQLDATE BETWEEN %s AND %s
          AND (f.headline LIKE %s OR f.summary LIKE %s)
        """
        keyword_params = [start_date, end_date, f"%{kw}%", f"%{kw}%"]
        
        # Add event_type filter to keyword query if present
        if event_type and event_type != "any":
            type_conditions = {
                "conflict": "GoldsteinScale < -5",
                "cooperation": "GoldsteinScale > 5",
                "protest": "EventRootCode = '14'",
            }
            if event_type in type_conditions:
                keyword_sql += f" AND e.{type_conditions[event_type]}"
        
        # NOTE: No ORDER BY/LIMIT in keyword_sql — applied at UNION level or final
    
    # Main filter-based query (location, actor, etc.)
    has_structured_filters = actor_exact or location_exact or location_hint or actor
    
    if has_structured_filters or not keyword_sql:
        main_sql = f"""
        SELECT
            e.GlobalEventID, CAST(e.SQLDATE AS CHAR) as SQLDATE,
            e.Actor1Name, e.Actor2Name,
            e.EventCode, e.GoldsteinScale, e.AvgTone, e.NumArticles,
            e.ActionGeo_FullName, e.ActionGeo_CountryCode,
            e.ActionGeo_Lat, e.ActionGeo_Long,
            f.fingerprint, f.headline, f.summary, f.event_type_label, f.severity_score
        FROM (
            SELECT GlobalEventID FROM {DEFAULT_TABLE} {force_index}
            WHERE {inner_where}
            ORDER BY NumArticles DESC
            LIMIT %s
        ) ids
        JOIN {DEFAULT_TABLE} e ON e.GlobalEventID = ids.GlobalEventID
        LEFT JOIN event_fingerprints f ON e.GlobalEventID = f.global_event_id
        """
        main_params = inner_params + [max_results]
    else:
        # No structured filters, only keyword — use simpler query
        main_sql = f"""
        SELECT
            e.GlobalEventID, CAST(e.SQLDATE AS CHAR) as SQLDATE,
            e.Actor1Name, e.Actor2Name,
            e.EventCode, e.GoldsteinScale, e.AvgTone, e.NumArticles,
            e.ActionGeo_FullName, e.ActionGeo_CountryCode,
            e.ActionGeo_Lat, e.ActionGeo_Long,
            f.fingerprint, f.headline, f.summary, f.event_type_label, f.severity_score
        FROM {DEFAULT_TABLE} e
        LEFT JOIN event_fingerprints f ON e.GlobalEventID = f.global_event_id
        WHERE e.SQLDATE BETWEEN %s AND %s
        """
        main_params = [start_date, end_date]
        
        main_sql += type_sql.replace("GoldsteinScale", "e.GoldsteinScale").replace("EventRootCode", "e.EventRootCode")
        
        main_sql += " ORDER BY e.NumArticles DESC LIMIT %s"
        main_params.append(max_results)
    


    # If both keyword and structured filters exist, UNION them
    if keyword_sql and has_structured_filters:
        # MySQL requires parentheses around subqueries with ORDER BY in UNION
        sql = f"""( {main_sql} )
        UNION
        ( {keyword_sql} )
        ORDER BY NumArticles DESC
        LIMIT %s"""
        params = main_params + keyword_params + [max_results]
    elif keyword_sql and not has_structured_filters:
        # Only keyword, no structured filters
        sql = keyword_sql + " ORDER BY e.NumArticles DESC LIMIT %s"
        params = keyword_params + [max_results]
    else:
        # Only structured filters, no keyword
        sql = main_sql
        params = main_params
    
    return sql, params


async def query_search_events(
    pool,
    query_text: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    time_hint: Optional[str] = None,
    location_hint: Optional[str] = None,
    location_exact: Optional[str] = None,
    event_type: Optional[str] = None,
    actor: Optional[str] = None,
    actor_exact: Optional[str] = None,
    max_results: int = 20,
) -> List[Dict[str, Any]]:
    if start_date and end_date:
        date_start, date_end = start_date, end_date
    elif time_hint:
        date_start, date_end = parse_time_hint(time_hint)
    else:
        end = datetime.now().date()
        start = end - timedelta(days=30)
        date_start = start.strftime("%Y-%m-%d")
        date_end = end.strftime("%Y-%m-%d")

    sql, params = _build_optimized_search_sql(
        date_start, date_end,
        location_hint, location_exact,
        event_type, actor, actor_exact,
        query_text=query_text,
        max_results=min(max_results, 50),
    )
    return await pool.fetchall(sql, tuple(params))


async def query_geo_events(
    pool,
    start_date: str,
    end_date: str,
    location_hint: Optional[str] = None,
    location_exact: Optional[str] = None,
    event_type: Optional[str] = None,
    actor: Optional[str] = None,
    actor_exact: Optional[str] = None,
    max_results: int = 100,
) -> List[Dict[str, Any]]:
    """Return individual event points with coordinates for map display.
    
    NOTE: No JOIN with event_fingerprints for speed. Headline/summary not included.
    """
    loc_cond, loc_params = _build_smart_location_condition(location_hint, location_exact)
    act_cond, act_params = _build_actor_condition(actor, actor_exact)
    
    force_index = ""
    if actor_exact and not location_exact:
        force_index = "FORCE INDEX (idx_date_actor)"
    elif location_exact and not actor_exact:
        force_index = "FORCE INDEX (idx_date_geo)"
    
    type_sql = ""
    if event_type and event_type != "any":
        type_conditions = {
            "conflict": "GoldsteinScale < -5",
            "cooperation": "GoldsteinScale > 5",
            "protest": "EventRootCode = '14'",
        }
        if event_type in type_conditions:
            type_sql = f" AND {type_conditions[event_type]}"
    
    if actor_exact or location_exact:
        inner_where = f"SQLDATE BETWEEN %s AND %s"
        inner_params = [start_date, end_date]
        
        if actor_exact:
            inner_where += " AND Actor1Name = %s"
            inner_params.append(actor_exact)
        elif actor:
            inner_where += " AND (Actor1Name LIKE %s OR Actor2Name LIKE %s)"
            inner_params.extend([f"%{actor}%", f"%{actor}%"])
        
        if location_exact:
            if len(location_exact) <= 3 and location_exact.isalpha():
                inner_where += " AND ActionGeo_CountryCode = %s"
                inner_params.append(location_exact.upper()[:3])
            else:
                inner_where += " AND ActionGeo_FullName = %s"
                inner_params.append(location_exact)
        elif location_hint:
            hint_terms = parse_region_input(location_hint)
            loc_conds = []
            for term in hint_terms:
                if not term or len(term) < 2:
                    continue
                loc_conds.append("ActionGeo_FullName LIKE %s")
                inner_params.append(f"{term}%")
                if len(term) <= 3 and term.isalpha():
                    loc_conds.append("ActionGeo_CountryCode = %s")
                    inner_params.append(term.upper()[:3])
            if loc_conds:
                inner_where += f" AND ({' OR '.join(loc_conds)})"
        
        inner_where += type_sql
        
        sql = f"""
        SELECT
            e.GlobalEventID,
            CAST(e.SQLDATE AS CHAR) as SQLDATE,
            e.Actor1Name,
            e.Actor2Name,
            e.EventCode,
            e.GoldsteinScale,
            e.AvgTone,
            e.NumArticles,
            e.ActionGeo_FullName,
            e.ActionGeo_CountryCode,
            e.ActionGeo_Lat as lat,
            e.ActionGeo_Long as lng
        FROM (
            SELECT GlobalEventID FROM {DEFAULT_TABLE} {force_index}
            WHERE {inner_where}
              AND ActionGeo_Lat IS NOT NULL
              AND ActionGeo_Long IS NOT NULL
            ORDER BY NumArticles DESC
            LIMIT %s
        ) ids
        JOIN {DEFAULT_TABLE} e ON e.GlobalEventID = ids.GlobalEventID
        """
        params = inner_params + [min(max_results, 100)]
    else:
        sql = f"""
        SELECT
            e.GlobalEventID,
            CAST(e.SQLDATE AS CHAR) as SQLDATE,
            e.Actor1Name,
            e.Actor2Name,
            e.EventCode,
            e.GoldsteinScale,
            e.AvgTone,
            e.NumArticles,
            e.ActionGeo_FullName,
            e.ActionGeo_CountryCode,
            e.ActionGeo_Lat as lat,
            e.ActionGeo_Long as lng
        FROM {DEFAULT_TABLE} e
        WHERE e.SQLDATE BETWEEN %s AND %s
          AND e.ActionGeo_Lat IS NOT NULL
          AND e.ActionGeo_Long IS NOT NULL
        """
        params = [start_date, end_date]
        
        if location_hint:
            loc_sql, loc_p = _build_smart_location_condition(location_hint, None)
            sql += loc_sql.replace("ActionGeo", "e.ActionGeo")
            params.extend(loc_p)
        
        sql += type_sql.replace("GoldsteinScale", "e.GoldsteinScale").replace("EventRootCode", "e.EventRootCode")
        
        if actor:
            sql += " AND (e.Actor1Name LIKE %s OR e.Actor2Name LIKE %s)"
            params.extend([f"%{actor}%", f"%{actor}%"])
        
        sql += """
        ORDER BY e.NumArticles DESC
        LIMIT %s
        """
        params.append(min(max_results, 100))

    rows = await pool.fetchall(sql, tuple(params))
    result = []
    for r in rows:
        d = dict(r)
        d['lat'] = float(d['lat']) if d['lat'] is not None else None
        d['lng'] = float(d['lng']) if d['lng'] is not None else None
        result.append(d)
    return result

DEFAULT_TABLE = "events_table"


# ============================================================================
# Dashboard (parallel 5-query)
# ============================================================================

async def query_dashboard(pool, start_date: str, end_date: str) -> Dict[str, Any]:
    """Return raw dashboard data: daily_trend, top_actors, geo_distribution, event_types, summary_stats."""
    # firsttryuseprecomputetabledaily_summary
    ds_rows = await pool.fetchall(
        "SELECT CAST(date AS CHAR) as date, total_events, conflict_events, "
        "avg_goldstein, avg_tone, top_actors, top_locations, event_type_distribution "
        "FROM daily_summary WHERE date BETWEEN %s AND %s ORDER BY date",
        (start_date, end_date)
    )
    if ds_rows and len(ds_rows) >= 10:
        import json
        daily_trend = []
        all_actors = {}
        all_countries = {}
        all_event_types = {}
        total_events = 0
        total_articles = 0
        goldstein_sum = 0
        tone_sum = 0
        unique_actors_set = set()
        for r in ds_rows:
            daily_trend.append({
                'SQLDATE': r['date'],
                'cnt': r['total_events'],
                'goldstein': r['avg_goldstein'],
                'conflict': r['conflict_events'],
            })
            total_events += r['total_events']
            goldstein_sum += (r['avg_goldstein'] or 0) * r['total_events']
            tone_sum += (r['avg_tone'] or 0) * r['total_events']
            # mergeactors
            for a in json.loads(r['top_actors'] or '[]'):
                all_actors[a['name']] = all_actors.get(a['name'], 0) + a['count']
                unique_actors_set.add(a['name'])
            # mergecountries
            for loc in json.loads(r['top_locations'] or '[]'):
                all_countries[loc['name']] = all_countries.get(loc['name'], 0) + loc['count']
            # mergeeventtypes
            for et, ec in json.loads(r['event_type_distribution'] or '{}').items():
                all_event_types[et] = all_event_types.get(et, 0) + ec
        top_actors = sorted([{'actor': k, 'event_count': v} for k, v in all_actors.items()], key=lambda x: x['event_count'], reverse=True)[:10]
        geo_distribution = sorted([{'country_code': k, 'event_count': v} for k, v in all_countries.items()], key=lambda x: x['event_count'], reverse=True)[:10]
        event_types = sorted([{'event_type': k, 'event_count': v} for k, v in all_event_types.items()], key=lambda x: x['event_count'], reverse=True)
        # extraquerytotal_articles（daily_summaryNo.storethisfield）
        articles_result = await pool.fetchone(
            f"SELECT SUM(NumArticles) as total_articles FROM {DEFAULT_TABLE} WHERE SQLDATE BETWEEN %s AND %s",
            (start_date, end_date)
        )
        total_articles = articles_result['total_articles'] if articles_result else None
        return {
            'daily_trend': {'data': daily_trend},
            'top_actors': {'data': top_actors},
            'geo_distribution': {'data': geo_distribution},
            'event_types': {'data': event_types},
            'summary_stats': {'data': [{
                'total_events': total_events,
                'unique_actors': len(unique_actors_set),
                'avg_goldstein': round(goldstein_sum / total_events, 2) if total_events else 0,
                'avg_tone': round(tone_sum / total_events, 2) if total_events else 0,
                'total_articles': total_articles,
            }]}
        }

    # fallbackto originalparallelquery
    queries = [
        ("daily_trend", f"""
            SELECT CAST(SQLDATE AS CHAR) as SQLDATE, COUNT(*) as cnt,
                   AVG(GoldsteinScale) as goldstein,
                   SUM(CASE WHEN GoldsteinScale < 0 THEN 1 ELSE 0 END) as conflict
            FROM {DEFAULT_TABLE}
            WHERE SQLDATE BETWEEN %s AND %s
            GROUP BY SQLDATE ORDER BY SQLDATE
        """, (start_date, end_date)),

        ("top_actors", f"""
            SELECT Actor1Name as actor, COUNT(*) as event_count
            FROM {DEFAULT_TABLE}
            WHERE SQLDATE BETWEEN %s AND %s AND Actor1Name IS NOT NULL
            GROUP BY Actor1Name ORDER BY event_count DESC LIMIT 10
        """, (start_date, end_date)),

        ("geo_distribution", f"""
            SELECT ActionGeo_CountryCode as country_code, COUNT(*) as event_count
            FROM {DEFAULT_TABLE}
            WHERE SQLDATE BETWEEN %s AND %s
              AND ActionGeo_CountryCode IS NOT NULL
            GROUP BY ActionGeo_CountryCode ORDER BY event_count DESC LIMIT 10
        """, (start_date, end_date)),

        ("event_types", f"""
            SELECT
                CASE
                    WHEN EventRootCode BETWEEN 1 AND 9 THEN 'Public Statement'
                    WHEN EventRootCode BETWEEN 10 AND 19 THEN 'Yield'
                    WHEN EventRootCode BETWEEN 20 AND 29 THEN 'Investigate'
                    WHEN EventRootCode BETWEEN 30 AND 39 THEN 'Demand'
                    WHEN EventRootCode BETWEEN 40 AND 49 THEN 'Disapprove'
                    WHEN EventRootCode BETWEEN 50 AND 59 THEN 'Reject'
                    WHEN EventRootCode BETWEEN 60 AND 69 THEN 'Threaten'
                    WHEN EventRootCode BETWEEN 70 AND 79 THEN 'Protest'
                    ELSE 'Other'
                END as event_type,
                COUNT(*) as event_count
            FROM {DEFAULT_TABLE}
            WHERE SQLDATE BETWEEN %s AND %s
            GROUP BY event_type ORDER BY event_count DESC
        """, (start_date, end_date)),

        ("summary_stats", f"""
            SELECT
                COUNT(*) as total_events,
                COUNT(DISTINCT Actor1Name) as unique_actors,
                AVG(GoldsteinScale) as avg_goldstein,
                AVG(AvgTone) as avg_tone,
                SUM(NumArticles) as total_articles
            FROM {DEFAULT_TABLE}
            WHERE SQLDATE BETWEEN %s AND %s
        """, (start_date, end_date)),
    ]

    async def _run_one(name: str, sql: str, params: tuple):
        import time
        t0 = time.time()
        rows = await pool.fetchall(sql, params)
        elapsed_ms = round((time.time() - t0) * 1000, 2)
        return name, {"data": rows, "count": len(rows), "elapsed_ms": elapsed_ms}

    results = await asyncio.gather(*[_run_one(n, s, p) for n, s, p in queries])
    return {name: data for name, data in results}


# ============================================================================
# Time Series
# ============================================================================

async def query_time_series(pool, start_date: str, end_date: str, granularity: str = "day") -> List[Dict[str, Any]]:
    # firsttryuseprecomputetabledaily_summary（ifETLalreadyran）
    ds_rows = await pool.fetchall(
        "SELECT CAST(date AS CHAR) as period, total_events as event_count, conflict_events, cooperation_events, "
        "avg_goldstein, avg_tone FROM daily_summary WHERE date BETWEEN %s AND %s ORDER BY date",
        (start_date, end_date)
    )
    if ds_rows and len(ds_rows) >= 20:
        result = []
        for r in ds_rows:
            total = r['event_count'] or 1
            result.append({
                'period': r['period'],
                'event_count': r['event_count'],
                'conflict_pct': round(r['conflict_events'] * 100.0 / total, 2) if r['conflict_events'] else 0,
                'cooperation_pct': round(r['cooperation_events'] * 100.0 / total, 2) if r['cooperation_events'] else 0,
                'avg_goldstein': r['avg_goldstein'],
                'std_goldstein': None,
                'avg_tone': r['avg_tone'],
                'std_tone': None,
                'top_actors_json': None,
            })
        return result

    # fallbackto originalSQL（forweek/monthorlackdaily_summary）
    if granularity == "week":
        period_expr = "STR_TO_DATE(CONCAT(YEARWEEK(SQLDATE), ' Sunday'), '%%X%%V %%W')"
    elif granularity == "month":
        period_expr = "DATE_FORMAT(SQLDATE, '%%Y-%%m-01')"
    else:
        period_expr = "SQLDATE"

    sql = f"""
    SELECT
        CAST({period_expr} AS CHAR) as period,
        COUNT(*) as event_count,
        ROUND(SUM(CASE WHEN GoldsteinScale < -5 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as conflict_pct,
        ROUND(SUM(CASE WHEN GoldsteinScale > 5 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as cooperation_pct,
        ROUND(AVG(GoldsteinScale), 2) as avg_goldstein,
        ROUND(STDDEV(GoldsteinScale), 2) as std_goldstein,
        ROUND(AVG(AvgTone), 2) as avg_tone,
        ROUND(STDDEV(AvgTone), 2) as std_tone,
        NULL as top_actors_json
    FROM {DEFAULT_TABLE}
    WHERE SQLDATE BETWEEN %s AND %s
    GROUP BY {period_expr}
    ORDER BY {period_expr}
    """
    return await pool.fetchall(sql, (start_date, end_date))


# ============================================================================
# Geo Heatmap
# ============================================================================

async def query_geo_heatmap(pool, start_date: str, end_date: str, precision: int = 2) -> List[Dict[str, Any]]:
    precision = max(1, min(4, int(precision)))
    # firsttryuseprecomputetablegeo_heatmap_grid
    gh_rows = await pool.fetchall(
        f"SELECT ROUND(lat_grid, {precision}) as lat, ROUND(lng_grid, {precision}) as lng, "
        f"SUM(event_count) as intensity, AVG(avg_goldstein) as avg_conflict "
        f"FROM geo_heatmap_grid WHERE date BETWEEN %s AND %s "
        f"GROUP BY ROUND(lat_grid, {precision}), ROUND(lng_grid, {precision}) "
        f"HAVING intensity >= 5 ORDER BY intensity DESC LIMIT 1000",
        (start_date, end_date)
    )
    if gh_rows and len(gh_rows) >= 10:
        return [{**r, 'sample_location': None} for r in gh_rows]

    # fallbackto originalSQL
    sql = f"""
    SELECT
        ROUND(ActionGeo_Lat, {precision}) as lat,
        ROUND(ActionGeo_Long, {precision}) as lng,
        COUNT(*) as intensity,
        AVG(GoldsteinScale) as avg_conflict,
        ANY_VALUE(ActionGeo_FullName) as sample_location
    FROM {DEFAULT_TABLE}
    WHERE SQLDATE BETWEEN %s AND %s
      AND ActionGeo_Lat IS NOT NULL
      AND ActionGeo_Long IS NOT NULL
    GROUP BY ROUND(ActionGeo_Lat, {precision}), ROUND(ActionGeo_Long, {precision})
    HAVING intensity >= 5
    ORDER BY intensity DESC
    LIMIT 1000
    """
    return await pool.fetchall(sql, (start_date, end_date))


# ============================================================================
# Event Search
# ============================================================================

# ============================================================================
# Suggestion helpers
# ============================================================================

async def query_suggest_actors(pool, prefix: str, limit: int = 10) -> List[str]:
    """Return actor names matching prefix using indexed LIKE prefix search."""
    prefix_up = prefix.upper()
    rows = await pool.fetchall(
        f"""SELECT DISTINCT Actor1Name as name FROM {DEFAULT_TABLE}
            WHERE Actor1Name LIKE %s
            LIMIT %s""",
        (f"{prefix_up}%", limit)
    )
    return [r['name'] for r in rows if r['name']]



# ============================================================================
# Event Detail
# ============================================================================

async def query_event_detail(pool, fingerprint: str) -> Optional[Dict[str, Any]]:
    """Return raw event detail data or None if not found.
    
    Supports three formats:
      - EVT-YYYY-MM-DD-ID: Extract numeric ID from EVT format
      - Pure numeric ID (9-12 digits): Direct GlobalEventID lookup
      - US-YYYYMMDD-LOC-TYPE-NUM: Custom fingerprint lookup in event_fingerprints
    """
    gid = None
    
    # Format 1: EVT-YYYY-MM-DD-ID
    if fingerprint.startswith('EVT-'):
        parts = fingerprint.split('-')
        if len(parts) >= 4:
            try:
                gid = int(parts[-1])
            except ValueError:
                return None
        else:
            return None
    
    # Format 2: Pure numeric ID (9-12 digits)
    elif fingerprint.isdigit() and 9 <= len(fingerprint) <= 12:
        gid = int(fingerprint)
    
    # Format 3: Custom fingerprint (US-... or any other string)
    else:
        row = await pool.fetchone("""
            SELECT global_event_id, fingerprint, headline, summary,
                   key_actors, event_type_label, severity_score,
                   location_name, location_country
            FROM event_fingerprints
            WHERE fingerprint = %s
        """, (fingerprint,))
        if not row:
            return None

        gid = int(row['global_event_id']) if row['global_event_id'] else None
        if not gid:
            return None

        event_row = await pool.fetchone(f"SELECT * FROM {DEFAULT_TABLE} WHERE GlobalEventID = %s", (gid,))
        event_data = dict(event_row) if event_row else {}
        for k, v in list(event_data.items()):
            if isinstance(v, bytes):
                event_data[k] = v.hex()
        return {
            "fingerprint": row['fingerprint'],
            "headline": row['headline'],
            "summary": row['summary'],
            "key_actors": row['key_actors'],
            "event_type_label": row['event_type_label'],
            "severity_score": row['severity_score'],
            "location_name": row['location_name'],
            "location_country": row['location_country'],
            "event_data": event_data,
        }
    
    # Direct GlobalEventID lookup (for EVT- and pure numeric formats)
    if gid:
        row = await pool.fetchone(f"SELECT * FROM {DEFAULT_TABLE} WHERE GlobalEventID = %s", (gid,))
        if row:
            event_data = dict(row)
            for k, v in list(event_data.items()):
                if isinstance(v, bytes):
                    event_data[k] = v.hex()
            return {
                "fingerprint": fingerprint,
                "headline": f"{event_data.get('Actor1Name', 'Unknown')} vs {event_data.get('Actor2Name', 'Unknown')}",
                "summary": event_data.get('ActionGeo_FullName', ''),
                "key_actors": str([event_data.get('Actor1Name'), event_data.get('Actor2Name')]),
                "event_type_label": None,
                "severity_score": abs(event_data.get('GoldsteinScale', 0)),
                "location_name": event_data.get('ActionGeo_FullName'),
                "location_country": event_data.get('ActionGeo_CountryCode'),
                "event_data": event_data,
            }
    return None


# ============================================================================
# Regional Overview
# ============================================================================

async def query_regional_overview(
    pool, region: str, time_range: str = "week",
    start_date: Optional[str] = None, end_date: Optional[str] = None
) -> Dict[str, Any]:
    if start_date and end_date:
        start = start_date
        end = end_date
    else:
        end_dt = datetime.now().date()
        days_map = {'day': 1, 'week': 7, 'month': 30, 'quarter': 90, 'year': 365}
        start_dt = end_dt - timedelta(days=days_map.get(time_range, 7))
        start = start_dt.strftime('%Y-%m-%d')
        end = end_dt.strftime('%Y-%m-%d')

    # Try pre-computed stats first
    stats_rows = await pool.fetchall("""
        SELECT * FROM region_daily_stats
        WHERE region_code = %s AND date BETWEEN %s AND %s
        ORDER BY date DESC LIMIT 7
    """, (region.upper(), start, end))

    if stats_rows:
        return {"source": "precomputed", "rows": [dict(r) for r in stats_rows], "region": region, "start": start, "end": end}

    # Fallback: real-time query
    row = await pool.fetchone(f"""
        SELECT
            COUNT(*) as total,
            AVG(GoldsteinScale) as avg_goldstein,
            AVG(AvgTone) as avg_tone,
            SUM(CASE WHEN GoldsteinScale < -5 THEN 1 ELSE 0 END) as conflicts,
            SUM(CASE WHEN GoldsteinScale > 5 THEN 1 ELSE 0 END) as cooperation
        FROM {DEFAULT_TABLE}
        WHERE SQLDATE BETWEEN %s AND %s
          AND (ActionGeo_CountryCode = %s OR ActionGeo_FullName LIKE %s)
    """, (start, end, region.upper(), f'%{region}%'))

    hot_events = await pool.fetchall(f"""
        SELECT Actor1Name, Actor2Name, EventCode, GoldsteinScale,
               NumArticles, ActionGeo_FullName, SQLDATE
        FROM {DEFAULT_TABLE}
        WHERE SQLDATE BETWEEN %s AND %s
          AND (ActionGeo_CountryCode = %s OR ActionGeo_FullName LIKE %s)
        ORDER BY NumArticles DESC
        LIMIT 5
    """, (start, end, region.upper(), f'%{region}%'))

    return {
        "source": "realtime",
        "summary": dict(row) if row else {},
        "hot_events": [dict(r) for r in hot_events],
        "region": region,
        "start": start,
        "end": end,
    }


# ============================================================================
# Hot Events
# ============================================================================

async def query_hot_events(
    pool, query_date: Optional[str] = None, region_filter: Optional[str] = None, top_n: int = 5
) -> List[Dict[str, Any]]:
    query_date = query_date or (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    # Try pre-computed
    result = await pool.fetchone("""
        SELECT hot_event_fingerprints, top_actors, top_locations
        FROM daily_summary
        WHERE date = %s
    """, (query_date,))

    if result and result['hot_event_fingerprints']:
        import json
        hot_fingerprints = json.loads(result['hot_event_fingerprints']) if isinstance(result['hot_event_fingerprints'], str) else result['hot_event_fingerprints']
        events = []
        for fp in hot_fingerprints[:top_n]:
            row = await pool.fetchone("""
                SELECT f.fingerprint, f.headline, f.summary, f.severity_score,
                       f.location_name, CAST(e.SQLDATE AS CHAR) as SQLDATE,
                       e.GoldsteinScale, e.NumArticles,
                       e.GlobalEventID, 'standard' as fp_type
                FROM event_fingerprints f
                JOIN events_table e ON f.global_event_id = e.GlobalEventID
                WHERE f.fingerprint = %s
            """, (fp,))
            if row:
                events.append(dict(row))
        return events

    # Fallback: real-time query
    region_condition = ""
    params = [query_date]
    if region_filter:
        region_condition = "AND (e.ActionGeo_CountryCode = %s OR e.ActionGeo_FullName LIKE %s)"
        params.extend([region_filter.upper(), f'%{region_filter}%'])

    sql = f"""
        SELECT
            COALESCE(f.fingerprint, CONCAT('EVT-', e.SQLDATE, '-', CAST(e.GlobalEventID AS CHAR))) as fingerprint,
            COALESCE(f.headline, CONCAT(COALESCE(NULLIF(e.Actor1Name, ''), '一方'), ' vs ', COALESCE(NULLIF(e.Actor2Name, ''), '另一方'))) as headline,
            COALESCE(f.summary, e.ActionGeo_FullName) as summary,
            COALESCE(f.severity_score, ABS(e.GoldsteinScale)) as severity_score,
            COALESCE(f.location_name, e.ActionGeo_FullName) as location_name,
            CAST(e.SQLDATE AS CHAR) as SQLDATE,
            e.GoldsteinScale,
            e.NumArticles,
            e.GlobalEventID,
            CASE WHEN f.fingerprint IS NOT NULL THEN 'standard' ELSE 'temp' END as fp_type
        FROM {DEFAULT_TABLE} e
        LEFT JOIN event_fingerprints f ON e.GlobalEventID = f.global_event_id
        WHERE e.SQLDATE = %s {region_condition}
        ORDER BY e.NumArticles DESC
        LIMIT %s
    """
    params.append(top_n)
    return await pool.fetchall(sql, tuple(params))


# ============================================================================
# Top Events
# ============================================================================

async def query_top_events(
    pool, start_date: str, end_date: str,
    region_filter: Optional[str] = None, event_type: Optional[str] = None, top_n: int = 10
) -> List[Dict[str, Any]]:
    conditions = ["SQLDATE BETWEEN %s AND %s"]
    params = [start_date, end_date]

    if region_filter:
        parsed = parse_region_input(region_filter)
        region_conds = []
        for term in parsed:
            region_conds.append("ActionGeo_FullName LIKE %s")
            params.append(f'{term}%')
            region_conds.append("ActionGeo_FullName LIKE %s")
            params.append(f'%, {term}%')
            if len(term) <= 3 and term.isalpha():
                region_conds.append("ActionGeo_CountryCode = %s")
                params.append(term.upper()[:3])
        if region_conds:
            conditions.append(f"({' OR '.join(region_conds)})")

    if event_type == 'conflict':
        conditions.append("GoldsteinScale < -5")
    elif event_type == 'cooperation':
        conditions.append("GoldsteinScale > 5")
    elif event_type == 'protest':
        conditions.append("EventRootCode = '14'")

    where_clause = " AND ".join(conditions)

    # Use subquery for fast index usage + avoid filesort on full table
    sql = f"""
        SELECT
            e.GlobalEventID, CAST(e.SQLDATE AS CHAR) as SQLDATE,
            e.Actor1Name, e.Actor2Name,
            e.ActionGeo_FullName, e.ActionGeo_CountryCode,
            e.EventRootCode, e.GoldsteinScale, e.NumArticles,
            e.NumSources, e.AvgTone, e.SOURCEURL
        FROM (
            SELECT GlobalEventID FROM {DEFAULT_TABLE}
            WHERE {where_clause}
            ORDER BY NumArticles DESC
            LIMIT %s
        ) ids
        JOIN {DEFAULT_TABLE} e ON e.GlobalEventID = ids.GlobalEventID
    """
    params.append(top_n)
    return await pool.fetchall(sql, tuple(params))


# ============================================================================
# Daily Brief
# ============================================================================

async def query_daily_brief(pool, query_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    query_date = query_date or (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    brief = await pool.fetchone("SELECT * FROM daily_summary WHERE date = %s", (query_date,))
    if brief:
        return dict(brief)

    row = await pool.fetchone(f"""
        SELECT
            COUNT(*) as total_events,
            SUM(CASE WHEN GoldsteinScale < -5 THEN 1 ELSE 0 END) as conflict_events,
            SUM(CASE WHEN GoldsteinScale > 5 THEN 1 ELSE 0 END) as cooperation_events,
            AVG(GoldsteinScale) as avg_goldstein,
            AVG(AvgTone) as avg_tone
        FROM {DEFAULT_TABLE}
        WHERE SQLDATE = %s
    """, (query_date,))

    return dict(row) if row else None


# ============================================================================
# Stream Events
# ============================================================================

async def query_stream_events(
    pool, actor_name: str,
    start_date: Optional[str] = None, end_date: Optional[str] = None,
    max_results: int = 100
):
    """Generator-friendly streaming query."""
    from ..database.streaming import StreamingQuery

    streaming = StreamingQuery(pool, chunk_size=50)
    date_filter = ""
    params = [f"%{actor_name}%", f"%{actor_name}%"]

    if start_date and end_date:
        date_filter = "AND SQLDATE BETWEEN %s AND %s"
        params.extend([start_date, end_date])

    params.append(max_results)

    sql = f"""
        SELECT CAST(SQLDATE AS CHAR) as SQLDATE, Actor1Name, Actor2Name, EventCode,
               GoldsteinScale, AvgTone, ActionGeo_FullName,
               ActionGeo_Lat, ActionGeo_Long
        FROM {DEFAULT_TABLE}
        WHERE (Actor1Name LIKE %s OR Actor2Name LIKE %s)
        {date_filter}
        ORDER BY SQLDATE DESC
        LIMIT %s
    """

    async for row in streaming.stream(sql, tuple(params)):
        yield dict(row)


# ============================================================================
# Similar Events
# ============================================================================

async def query_similar_events(pool, seed_event_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Find events similar to a seed event.

    Uses a soft-preference approach: time window + actor/location preference
    in ORDER BY, not hard WHERE filters.  Returns a larger candidate pool
    for downstream soft scoring (_compute_storyline_relevance).
    """
    seed = await pool.fetchone(f"""
        SELECT GlobalEventID, Actor1Name, Actor2Name, ActionGeo_CountryCode,
               ActionGeo_FullName, EventRootCode, CAST(SQLDATE AS CHAR) as SQLDATE,
               NumArticles, GoldsteinScale
        FROM {DEFAULT_TABLE}
        WHERE GlobalEventID = %s
    """, (seed_event_id,))

    if not seed:
        return []

    a1, a2 = seed['Actor1Name'], seed['Actor2Name']
    loc = seed['ActionGeo_CountryCode'] or seed['ActionGeo_FullName']
    sd = seed['SQLDATE']
    seed_articles = seed.get('NumArticles', 0) or 0
    seed_goldstein = abs(seed.get('GoldsteinScale', 0) or 0)

    from datetime import datetime, timedelta
    sd_dt = datetime.strptime(sd, '%Y-%m-%d')
    window_start = (sd_dt - timedelta(days=30)).strftime('%Y-%m-%d')
    window_end = (sd_dt + timedelta(days=30)).strftime('%Y-%m-%d')

    # Build actor preference for ORDER BY
    actor_order = "0"
    params = [window_start, window_end, seed_event_id, sd]
    if a1 and a2:
        actor_order = (
            "CASE WHEN (e.Actor1Name = %s AND e.Actor2Name = %s) "
            "     OR (e.Actor1Name = %s AND e.Actor2Name = %s) THEN 2 "
            "     WHEN e.Actor1Name IN (%s, %s) OR e.Actor2Name IN (%s, %s) THEN 1 "
            "     ELSE 0 END"
        )
        params.extend([a1, a2, a2, a1, a1, a2, a1, a2])
    elif a1:
        actor_order = (
            "CASE WHEN e.Actor1Name = %s OR e.Actor2Name = %s THEN 1 ELSE 0 END"
        )
        params.extend([a1, a1])
    elif a2:
        actor_order = (
            "CASE WHEN e.Actor1Name = %s OR e.Actor2Name = %s THEN 1 ELSE 0 END"
        )
        params.extend([a2, a2])

    # Location preference
    loc_order = "0"
    if loc:
        loc_order = (
            "CASE WHEN e.ActionGeo_CountryCode = %s OR e.ActionGeo_FullName = %s THEN 1 ELSE 0 END"
        )
        params.extend([loc, loc])

    params.append(limit * 5)  # Larger pool for soft scoring

    rows = await pool.fetchall(f"""
        SELECT
            e.GlobalEventID,
            CAST(e.SQLDATE AS CHAR) as SQLDATE,
            e.Actor1Name, e.Actor2Name,
            e.EventCode, e.GoldsteinScale, e.AvgTone, e.NumArticles,
            e.ActionGeo_FullName, e.ActionGeo_CountryCode,
            e.SOURCEURL,
            f.fingerprint, f.headline, f.summary, f.event_type_label
        FROM {DEFAULT_TABLE} e
        LEFT JOIN event_fingerprints f ON e.GlobalEventID = f.global_event_id
        WHERE e.SQLDATE BETWEEN %s AND %s
          AND e.GlobalEventID != %s
          AND e.SQLDATE != %s
        ORDER BY {actor_order} DESC, {loc_order} DESC, e.NumArticles DESC
        LIMIT %s
    """, tuple(params))

    result = []
    for r in rows:
        d = dict(r)
        d['_seed_articles'] = seed_articles
        d['_seed_goldstein'] = seed_goldstein
        result.append(d)

    return result


# ============================================================================
# RAG / Vector Search (ChromaDB)
# ============================================================================

def get_chroma_db_path() -> str:
    """Get the ChromaDB persistent storage path."""
    # Navigate from backend/queries/ up to project root
    project_root = Path(__file__).resolve().parents[2]
    return str(project_root / 'chroma_db')


async def query_search_news_context(
    query: str,
    n_results: int = 5
) -> Dict[str, Any]:
    """
    Search news article content via ChromaDB vector semantic search.
    
    Args:
        query: Natural language search query
        n_results: Number of results to return (default 5, max 10)
    
    Returns:
        Dict with 'results' list and 'query' metadata
    """
    try:
        import chromadb
        from chromadb.utils import embedding_functions
        
        db_path = get_chroma_db_path()
        if not os.path.exists(db_path):
            return {
                "error": "Vector database not found",
                "db_path": db_path,
                "message": "Please build the knowledge base first"
            }
        
        client = chromadb.PersistentClient(path=db_path)
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        
        try:
            collection = client.get_collection(
                name="gdelt_news_collection",
                embedding_function=ef
            )
        except Exception:
            return {
                "error": "Collection not found",
                "message": "News collection 'gdelt_news_collection' not found. Please build the knowledge base first."
            }
        
        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, 10)
        )
        
        if not results['documents'] or not results['documents'][0]:
            return {
                "query": query,
                "results": [],
                "message": f"No related news found for '{query}'"
            }
        
        # Format results
        formatted_results = []
        for i in range(len(results['documents'][0])):
            formatted_results.append({
                "event_id": results['ids'][0][i],
                "date": results['metadatas'][0][i].get('date', 'Unknown'),
                "source_url": results['metadatas'][0][i].get('source_url', 'Unknown'),
                "content": results['documents'][0][i],
            })
        
        return {
            "query": query,
            "results": formatted_results,
            "count": len(formatted_results)
        }
        
    except ImportError:
        return {
            "error": "Missing dependencies",
            "message": "ChromaDB not installed. Run: pip install chromadb sentence-transformers"
        }
    except Exception as e:
        return {
            "error": "Search failed",
            "message": str(e)
        }


# ============================================================================
# Event Sequence for THP Forecasting
# ============================================================================

# ============================================================================
# Dashboard Insights (QuadClass, ActorTypes, Hot Headlines)
# ============================================================================

async def query_insights(
    pool, start_date: str, end_date: str
) -> Dict[str, Any]:
    """Return overview insights: top headlines and precomputed sentiment.
    
    NOTE: All heavy real-time GROUP BYs removed. Sentiment comes from daily_summary only.
    If daily_summary is not populated, sentiment returns empty.
    """
    
    # Sentiment summary — ONLY from precomputed daily_summary (fast PK range scan)
    ds_rows = await pool.fetchall(
        "SELECT total_events, conflict_events, cooperation_events, "
        "avg_goldstein, avg_tone FROM daily_summary WHERE date BETWEEN %s AND %s",
        (start_date, end_date)
    )
    if ds_rows:
        total_events = sum(r['total_events'] or 0 for r in ds_rows)
        conflict_count = sum(r['conflict_events'] or 0 for r in ds_rows)
        cooperation_count = sum(r['cooperation_events'] or 0 for r in ds_rows)
        goldstein_sum = sum((r['avg_goldstein'] or 0) * (r['total_events'] or 0) for r in ds_rows)
        tone_sum = sum((r['avg_tone'] or 0) * (r['total_events'] or 0) for r in ds_rows)
        sentiment = {
            "avg_tone": round(tone_sum / total_events, 2) if total_events else None,
            "avg_goldstein": round(goldstein_sum / total_events, 2) if total_events else None,
            "conflict_count": conflict_count,
            "cooperation_count": cooperation_count,
            "total_events": total_events,
        }
    else:
        sentiment = {}
    
    # Top headlines with fingerprints — use subquery for fast index path
    headline_rows = await pool.fetchall(
        f"""
        SELECT
            e.GlobalEventID,
            CAST(e.SQLDATE AS CHAR) as SQLDATE,
            e.Actor1Name, e.Actor2Name,
            e.GoldsteinScale, e.AvgTone, e.NumArticles,
            e.ActionGeo_FullName,
            f.headline, f.summary, f.event_type_label, f.severity_score
        FROM (
            SELECT GlobalEventID FROM {DEFAULT_TABLE}
            WHERE SQLDATE BETWEEN %s AND %s
            ORDER BY NumArticles DESC
            LIMIT 5
        ) ids
        JOIN {DEFAULT_TABLE} e ON e.GlobalEventID = ids.GlobalEventID
        LEFT JOIN event_fingerprints f ON e.GlobalEventID = f.global_event_id
        """,
        (start_date, end_date)
    )
    
    return {
        "quad_class": {"data": []},
        "actor_types": {"data": []},
        "top_headlines": {"data": [dict(r) for r in headline_rows]},
        "sentiment": sentiment,
    }


async def query_event_sequence(
    pool,
    start_date: str,
    end_date: str,
    region: Optional[str] = None,
    actor: Optional[str] = None,
    event_type: str = "all",
) -> List[Dict[str, Any]]:
    """Return daily event sequence rows for THP-style forecasting."""
    event_type = (event_type or "all").lower()

    conditions = ["SQLDATE BETWEEN %s AND %s"]
    params: List[Any] = [start_date, end_date]

    if region:
        region_clean = region.strip().upper()
        if len(region_clean) <= 3 and region_clean.isalpha():
            conditions.append("ActionGeo_CountryCode = %s")
            params.append(region_clean)
        else:
            conditions.append("(ActionGeo_CountryCode = %s OR ActionGeo_FullName LIKE %s)")
            params.extend([region_clean, f"%{region}%"])

    if actor:
        actor_term = f"%{actor}%"
        conditions.append("(Actor1Name LIKE %s OR Actor2Name LIKE %s)")
        params.extend([actor_term, actor_term])

    type_condition = ""
    if event_type == "conflict":
        type_condition = "AND GoldsteinScale < 0"
    elif event_type == "cooperation":
        type_condition = "AND GoldsteinScale > 0"
    elif event_type == "protest":
        type_condition = "AND EventRootCode IN ('14', '15', '16')"

    where_clause = " AND ".join(conditions)

    rows = await pool.fetchall(
        f"""
        SELECT
            CAST(SQLDATE AS CHAR) as date,
            COUNT(*) as event_count,
            SUM(CASE WHEN GoldsteinScale < 0 THEN 1 ELSE 0 END) as conflict_events,
            SUM(CASE WHEN GoldsteinScale > 0 THEN 1 ELSE 0 END) as cooperation_events,
            AVG(GoldsteinScale) as avg_goldstein,
            AVG(AvgTone) as avg_tone,
            SUM(NumArticles) as total_articles
        FROM events_table
        WHERE {where_clause} {type_condition}
        GROUP BY SQLDATE
        ORDER BY SQLDATE
        """,
        tuple(params),
    )
    return rows


# ============================================================================
# Actor Activity Overview — Daily aggregation for actor situation analysis
# ============================================================================

async def query_actor_activity_overview(
    pool,
    actor_name: str,
    center_date: str,
    days_before: int = 7,
    days_after: int = 7,
    min_articles: int = 1,
) -> List[Dict[str, Any]]:
    """Build daily activity overview for an actor (NOT a storyline).
    
    This aggregates ALL events for the actor per day — useful for seeing
    overall conflict/cooperation trends, but NOT for reading individual
    event stories (use query_event_storyline for that).
    
    Args:
        actor_name: Actor to track (e.g. 'ISRAELI')
        center_date: Center date YYYY-MM-DD
        days_before: Days to look back
        days_after: Days to look forward
        min_articles: Minimum NumArticles to filter noise
    
    Returns:
        Daily aggregated rows: events count, articles, avg goldstein/tone,
        severe conflict/cooperation counts, top CAMEO code.
    """
    from datetime import datetime, timedelta
    
    center = datetime.strptime(center_date, "%Y-%m-%d")
    start = (center - timedelta(days=days_before)).strftime("%Y-%m-%d")
    end = (center + timedelta(days=days_after)).strftime("%Y-%m-%d")
    
    rows = await pool.fetchall(
        f"""
        SELECT
            CAST(SQLDATE AS CHAR) as date,
            COUNT(*) as total_events,
            SUM(NumArticles) as total_articles,
            AVG(GoldsteinScale) as avg_goldstein,
            AVG(AvgTone) as avg_tone,
            SUM(CASE WHEN GoldsteinScale < -5 THEN 1 ELSE 0 END) as severe_conflict,
            SUM(CASE WHEN GoldsteinScale > 5 THEN 1 ELSE 0 END) as severe_cooperation,
            -- Top CAMEO event code of the day (most articles)
            (SELECT EventCode FROM {DEFAULT_TABLE} AS sub
             WHERE sub.SQLDATE = e.SQLDATE
               AND (sub.Actor1Name = %s OR sub.Actor2Name = %s)
               AND sub.NumArticles >= %s
             ORDER BY sub.NumArticles DESC
             LIMIT 1) as top_event_code
        FROM {DEFAULT_TABLE} AS e
        WHERE e.SQLDATE BETWEEN %s AND %s
          AND (e.Actor1Name = %s OR e.Actor2Name = %s)
          AND e.NumArticles >= %s
        GROUP BY SQLDATE
        ORDER BY SQLDATE
        """,
        (
            actor_name, actor_name, min_articles,
            start, end,
            actor_name, actor_name, min_articles,
        ),
    )
    
    return [dict(r) for r in rows]


# ============================================================================
# Event Storyline — True chronological event chain around a specific event
# ============================================================================

async def query_event_storyline(
    pool,
    seed_event_id: int,
    days_before: int = 7,
    days_after: int = 7,
    max_events_per_phase: int = 10,
) -> Dict[str, Any]:
    """Build a true event storyline: preceding → seed → following events.
    
    Unlike query_similar_events (which finds similar events by actor/type),
    this finds events that are part of the SAME conflict narrative:
    - Preceding: Same actor pair, same location, earlier dates
    - Seed: The event itself
    - Following: Same actor pair, same location, later dates  
    - Reactions: Other actors responding to the seed event
    
    Args:
        seed_event_id: GlobalEventID of the central event
        days_before: How many days to look back for preceding events
        days_after: How many days to look forward for following events
        max_events_per_phase: Max events per phase (preceding/following/reactions)
    
    Returns:
        Dict with keys: seed, preceding, following, reactions
    """
    from datetime import datetime, timedelta
    
    # --- Step 1: Get seed event details ---
    seed_row = await pool.fetchone(f"""
        SELECT
            e.GlobalEventID,
            CAST(e.SQLDATE AS CHAR) as SQLDATE,
            e.Actor1Name, e.Actor2Name,
            e.EventCode, e.EventRootCode,
            e.GoldsteinScale, e.AvgTone, e.NumArticles,
            e.ActionGeo_FullName, e.ActionGeo_CountryCode,
            e.SOURCEURL,
            f.fingerprint, f.headline, f.summary, f.event_type_label
        FROM {DEFAULT_TABLE} e
        LEFT JOIN event_fingerprints f ON e.GlobalEventID = f.global_event_id
        WHERE e.GlobalEventID = %s
    """, (seed_event_id,))
    
    if not seed_row:
        return {"seed": None, "preceding": [], "following": [], "reactions": []}
    
    seed = dict(seed_row)
    seed_date = seed['SQLDATE']
    a1, a2 = seed['Actor1Name'], seed['Actor2Name']
    location = seed['ActionGeo_CountryCode'] or seed['ActionGeo_FullName']
    root_code = seed['EventRootCode']
    seed_quad = seed.get('QuadClass')
    
    center_dt = datetime.strptime(seed_date, '%Y-%m-%d')
    pre_start = (center_dt - timedelta(days=days_before)).strftime('%Y-%m-%d')
    fol_end = (center_dt + timedelta(days=days_after)).strftime('%Y-%m-%d')
    
    # --- Step 2: Preceding events (time window + soft actor/location preference) ---
    # Hard filter: only time window.  Actor/location/QuadClass/CAMEO are
    # evaluated by _compute_storyline_relevance in Python layer.
    preceding = []
    params = [pre_start, seed_date, seed_event_id, seed_date]
    
    # Build actor preference for ORDER BY (not WHERE)
    actor_order = "0"
    if a1 and a2:
        actor_order = (
            "CASE WHEN (e.Actor1Name = %s AND e.Actor2Name = %s) "
            "     OR (e.Actor1Name = %s AND e.Actor2Name = %s) THEN 2 "
            "     WHEN e.Actor1Name IN (%s, %s) OR e.Actor2Name IN (%s, %s) THEN 1 "
            "     ELSE 0 END"
        )
        params.extend([a1, a2, a2, a1, a1, a2, a1, a2])
    elif a1:
        actor_order = (
            "CASE WHEN e.Actor1Name = %s OR e.Actor2Name = %s THEN 1 ELSE 0 END"
        )
        params.extend([a1, a1])
    elif a2:
        actor_order = (
            "CASE WHEN e.Actor1Name = %s OR e.Actor2Name = %s THEN 1 ELSE 0 END"
        )
        params.extend([a2, a2])
    
    # Location preference for ORDER BY
    loc_order = "0"
    if location:
        loc_order = (
            "CASE WHEN e.ActionGeo_CountryCode = %s OR e.ActionGeo_FullName = %s THEN 1 ELSE 0 END"
        )
        params.extend([location, location])
    
    params.append(max_events_per_phase * 3)  # Larger pool for soft scoring
    
    pre_rows = await pool.fetchall(f"""
        SELECT
            e.GlobalEventID,
            CAST(e.SQLDATE AS CHAR) as SQLDATE,
            e.Actor1Name, e.Actor2Name,
            e.EventCode, e.EventRootCode,
            e.GoldsteinScale, e.AvgTone, e.NumArticles,
            e.ActionGeo_FullName, e.ActionGeo_CountryCode,
            e.SOURCEURL,
            f.headline, f.summary, f.event_type_label
        FROM {DEFAULT_TABLE} e
        LEFT JOIN event_fingerprints f ON e.GlobalEventID = f.global_event_id
        WHERE e.SQLDATE BETWEEN %s AND %s
          AND e.GlobalEventID != %s
          AND e.SQLDATE != %s
        ORDER BY e.NumArticles DESC, e.SQLDATE DESC
        LIMIT %s
    """, tuple(params))
    
    preceding = [dict(r) for r in pre_rows]
    # Already ordered by SQLDATE DESC, so reverse to get oldest first
    
    # --- Step 3: Following events (time window + soft actor/location preference) ---
    following = []
    params = [seed_date, fol_end, seed_event_id, seed_date]
    
    actor_order = "0"
    if a1 and a2:
        actor_order = (
            "CASE WHEN (e.Actor1Name = %s AND e.Actor2Name = %s) "
            "     OR (e.Actor1Name = %s AND e.Actor2Name = %s) THEN 2 "
            "     WHEN e.Actor1Name IN (%s, %s) OR e.Actor2Name IN (%s, %s) THEN 1 "
            "     ELSE 0 END"
        )
        params.extend([a1, a2, a2, a1, a1, a2, a1, a2])
    elif a1:
        actor_order = (
            "CASE WHEN e.Actor1Name = %s OR e.Actor2Name = %s THEN 1 ELSE 0 END"
        )
        params.extend([a1, a1])
    elif a2:
        actor_order = (
            "CASE WHEN e.Actor1Name = %s OR e.Actor2Name = %s THEN 1 ELSE 0 END"
        )
        params.extend([a2, a2])
    
    loc_order = "0"
    if location:
        loc_order = (
            "CASE WHEN e.ActionGeo_CountryCode = %s OR e.ActionGeo_FullName = %s THEN 1 ELSE 0 END"
        )
        params.extend([location, location])
    
    params.append(max_events_per_phase * 3)
    
    fol_rows = await pool.fetchall(f"""
        SELECT
            e.GlobalEventID,
            CAST(e.SQLDATE AS CHAR) as SQLDATE,
            e.Actor1Name, e.Actor2Name,
            e.EventCode, e.EventRootCode,
            e.GoldsteinScale, e.AvgTone, e.NumArticles,
            e.ActionGeo_FullName, e.ActionGeo_CountryCode,
            e.SOURCEURL,
            f.headline, f.summary, f.event_type_label
        FROM {DEFAULT_TABLE} e
        LEFT JOIN event_fingerprints f ON e.GlobalEventID = f.global_event_id
        WHERE e.SQLDATE BETWEEN %s AND %s
          AND e.GlobalEventID != %s
          AND e.SQLDATE != %s
        ORDER BY e.NumArticles DESC, e.SQLDATE ASC
        LIMIT %s
    """, tuple(params))
    
    following = [dict(r) for r in fol_rows]
    # Already ordered by SQLDATE ASC (earliest first)
    
    # --- Step 4: Reactions (soft actor preference, not hard filter) ---
    # Look for events where other actors act toward a1 or a2,
    # but also include events that mention a1/a2 in any position.
    reactions = []
    params = [seed_date, fol_end, seed_event_id, seed_date]
    
    actor_order = "0"
    if a1 and a2:
        actor_order = (
            "CASE WHEN e.Actor2Name = %s AND e.Actor1Name NOT IN (%s, %s) THEN 2 "
            "     WHEN e.Actor2Name = %s AND e.Actor1Name NOT IN (%s, %s) THEN 1 "
            "     WHEN e.Actor1Name IN (%s, %s) OR e.Actor2Name IN (%s, %s) THEN 0.5 "
            "     ELSE 0 END"
        )
        params.extend([a1, a1, a2, a2, a1, a2, a1, a2, a1, a2])
    elif a1:
        actor_order = (
            "CASE WHEN e.Actor2Name = %s AND e.Actor1Name != %s THEN 1 "
            "     WHEN e.Actor1Name = %s OR e.Actor2Name = %s THEN 0.5 "
            "     ELSE 0 END"
        )
        params.extend([a1, a1, a1, a1])
    elif a2:
        actor_order = (
            "CASE WHEN e.Actor2Name = %s AND e.Actor1Name != %s THEN 1 "
            "     WHEN e.Actor1Name = %s OR e.Actor2Name = %s THEN 0.5 "
            "     ELSE 0 END"
        )
        params.extend([a2, a2, a2, a2])
    
    params.append(max_events_per_phase * 3)
    
    reac_rows = await pool.fetchall(f"""
        SELECT
            e.GlobalEventID,
            CAST(e.SQLDATE AS CHAR) as SQLDATE,
            e.Actor1Name, e.Actor2Name,
            e.EventCode, e.EventRootCode,
            e.GoldsteinScale, e.AvgTone, e.NumArticles,
            e.ActionGeo_FullName, e.ActionGeo_CountryCode,
            e.SOURCEURL,
            f.headline, f.summary, f.event_type_label
        FROM {DEFAULT_TABLE} e
        LEFT JOIN event_fingerprints f ON e.GlobalEventID = f.global_event_id
        WHERE e.SQLDATE BETWEEN %s AND %s
          AND e.GlobalEventID != %s
          AND e.SQLDATE != %s
        ORDER BY e.NumArticles DESC, e.SQLDATE ASC
        LIMIT %s
    """, tuple(params))
    reactions = [dict(r) for r in reac_rows]
    
    return {
        "seed": seed,
        "preceding": preceding,
        "following": following,
        "reactions": reactions,
    }


# CAMEO Event Code descriptions (simplified)
CAMEO_CODE_MAP = {
    "010": "Make statement",
    "011": "Decline comment",
    "012": "Make pessimistic comment",
    "013": "Make optimistic comment",
    "014": "Consider policy option",
    "015": "Engage in material cooperation",
    "016": "Engage in diplomatic cooperation",
    "017": "Engage in material conflict",
    "018": "Engage in diplomatic conflict",
    "019": "Make public statement",
    "020": "Yield",
    "021": "Ease administrative sanctions",
    "022": "Ease military blockade",
    "023": "Accede to demands for change in leadership",
    "024": "Return, release",
    "025": "Ease military alert",
    "026": "Ease political dissent",
    "027": "Yield",
    "028": "Yield",
    "030": "Disapprove",
    "031": "Criticize or denounce",
    "032": "Accuse",
    "033": "Rally opposition",
    "034": "Complain officially",
    "035": "Bring lawsuit against",
    "036": "Investigate",
    "037": "Threaten",
    "038": "Reject",
    "039": "Threaten",
    "040": "Reject",
    "041": "Reject accusation",
    "042": "Reject proposal to meet, discuss, or negotiate",
    "043": "Reject plan, agreement to settle dispute",
    "044": "Reject request for military aid",
    "045": "Reject request for economic aid",
    "046": "Reject request for humanitarian aid",
    "047": "Reject request for military protection",
    "048": "Reject request for change in leadership",
    "049": "Reject request for change in policy",
    "050": "Threaten",
    "051": "Threaten non-force",
    "052": "Threaten with administrative sanctions",
    "053": "Threaten with political dissent",
    "054": "Threaten to halt negotiations",
    "055": "Threaten to halt mediation",
    "056": "Threaten to impose blockade, restrict movement",
    "057": "Threaten with military force",
    "058": "Threaten to use unconventional mass violence",
    "060": "Protest",
    "061": "Demonstrate or rally",
    "062": "Conduct hunger strike",
    "063": "Conduct strike or boycott",
    "064": "Obstruct passage, block",
    "065": "Protest violently, riot",
    "066": "Engage in violent protest",
    "067": "Engage in political dissent",
    "068": "Engage in violent protest",
    "070": "Coerce",
    "071": "Seize or damage property",
    "072": "Impose administrative sanctions",
    "073": "Impose military blockade",
    "074": "Arrest or detain",
    "075": "Use force to restore order",
    "076": "Impose state of emergency or martial law",
    "077": "Violate ceasefire",
    "078": "Escalate military engagement",
    "080": "Assault",
    "081": "Assault with weapons",
    "082": "Sexually assault",
    "083": "Kill by physical assault",
    "084": "Kill",
    "085": "Use unconventional mass violence",
    "086": "Use biological weapons",
    "087": "Use chemical weapons",
    "088": "Use radiological weapons",
    "090": "Use force",
    "091": "Use military force",
    "092": "Employ aerial weapons",
    "093": "Employ artillery and tanks",
    "094": "Use small arms and light weapons",
    "095": "Use conventional military force",
    "096": "Use unconventional mass violence",
    "097": "Use biological weapons",
    "098": "Use radiological weapons",
    "100": "Use chemical weapons",
    "101": "Use biological weapons",
    "102": "Use radiological weapons",
    "103": "Use nuclear weapons",
    "104": "Use force",
    "105": "Use force",
    "106": "Use force",
    "107": "Use force",
    "108": "Use force",
    "110": "Demonstrate force",
    "111": "Demonstrate military force",
    "112": "Demonstrate crowd control",
    "113": "Demonstrate riot control",
    "114": "Demonstrate military force",
    "115": "Demonstrate military force",
    "116": "Demonstrate military force",
    "120": "Use force",
    "121": "Use force",
    "122": "Use force",
    "123": "Use force",
    "124": "Use unconventional mass violence",
    "125": "Use biological weapons",
    "126": "Use chemical weapons",
    "127": "Use radiological weapons",
    "128": "Use nuclear weapons",
    "129": "Use force",
    "130": "Threaten",
    "131": "Threaten",
    "132": "Threaten",
    "133": "Threaten",
    "134": "Threaten",
    "135": "Threaten",
    "136": "Threaten",
    "137": "Threaten",
    "138": "Threaten",
    "139": "Threaten",
    "140": "Coerce",
    "141": "Coerce",
    "142": "Coerce",
    "143": "Coerce",
    "144": "Coerce",
    "145": "Coerce",
    "146": "Coerce",
    "150": "Engage in material cooperation",
    "151": "Engage in economic cooperation",
    "152": "Engage in military cooperation",
    "153": "Engage in judicial cooperation",
    "154": "Engage in intelligence cooperation",
    "155": "Engage in diplomatic cooperation",
    "160": "Engage in diplomatic cooperation",
    "161": "Engage in diplomatic cooperation",
    "162": "Engage in diplomatic cooperation",
    "163": "Engage in diplomatic cooperation",
    "164": "Engage in diplomatic cooperation",
    "165": "Engage in diplomatic cooperation",
    "166": "Engage in diplomatic cooperation",
    "170": "Yield",
    "171": "Ease administrative sanctions",
    "172": "Ease military blockade",
    "173": "Accede to demands for change in leadership",
    "174": "Return, release",
    "175": "Ease military alert",
    "180": "Yield",
    "181": "Ease administrative sanctions",
    "182": "Ease military blockade",
    "183": "Accede to demands for change in leadership",
    "184": "Return, release",
    "185": "Ease military alert",
    "186": "Yield",
    "190": "Use unconventional mass violence",
    "191": "Use biological weapons",
    "192": "Use chemical weapons",
    "193": "Use radiological weapons",
    "194": "Use nuclear weapons",
    "195": "Use force",
    "196": "Use unconventional mass violence",
}


def get_cameo_description(code: Optional[str]) -> str:
    """Get human-readable description for CAMEO event code."""
    if not code:
        return "Unknown event"
    return CAMEO_CODE_MAP.get(code, f"Event type {code}")

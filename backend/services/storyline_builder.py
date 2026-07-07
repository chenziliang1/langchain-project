"""
Storyline Builder — Construct event narrative arcs from event sequences + GKG data.

Builds three core story dimensions:
1. Timeline: chronological event sequence with significance scoring
2. Entity Evolution: how actors, locations, organizations change over time
3. Theme Evolution: how media themes shift (requires GKG data)
"""

from typing import Dict, Any, List, Optional
from collections import defaultdict
from datetime import datetime


# ---------------------------------------------------------------------------
# Timeline Builder
# ---------------------------------------------------------------------------

def build_timeline(
    events: List[Dict[str, Any]],
    gkg_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a chronological timeline from a list of related events.

    Args:
        events: List of event dicts (from query_similar_events or query_search_events)
        gkg_data: Optional GKG data to enrich timeline entries

    Returns:
        Dict with timeline events, period info, and key milestones.
    """
    if not events:
        return {
            "events": [],
            "period": {"start": None, "end": None, "duration_days": 0},
            "key_milestones": [],
        }

    # Sort by date
    sorted_events = sorted(events, key=lambda e: e.get("SQLDATE") or e.get("date") or "")

    timeline_events = []
    for i, evt in enumerate(sorted_events):
        ed = evt.get("event_data") or evt
        date = evt.get("SQLDATE") or evt.get("date") or ed.get("SQLDATE", "")

        # Build title
        headline = evt.get("headline")
        if not headline:
            a1 = ed.get("Actor1Name") or evt.get("actor1_name", "")
            a2 = ed.get("Actor2Name") or evt.get("actor2_name", "")
            headline = f"{a1 or 'Unknown'} vs {a2 or 'Unknown'}"

        # Build description
        location = (
            evt.get("location_name")
            or ed.get("ActionGeo_FullName")
            or ed.get("location_name", "")
        )
        summary = evt.get("summary", "")
        event_type = evt.get("event_type_label") or evt.get("event_type", "")

        # Significance score (0-10)
        significance = _calculate_significance(evt, ed)

        # Actors list
        actors = []
        for a in (ed.get("Actor1Name"), ed.get("Actor2Name")):
            if a:
                actors.append(a)

        timeline_events.append({
            "index": i,
            "event_id": ed.get("GlobalEventID") or evt.get("global_event_id"),
            "date": date,
            "title": headline,
            "description": summary or f"Event in {location}" if location else "Event",
            "actors": actors,
            "location": location,
            "event_type": event_type,
            "significance_score": significance,
            "goldstein_scale": ed.get("GoldsteinScale") or evt.get("goldstein_scale"),
            "num_articles": ed.get("NumArticles") or evt.get("num_articles", 0),
            "avg_tone": ed.get("AvgTone") or evt.get("avg_tone"),
            "source_url": ed.get("SOURCEURL") or evt.get("source_url"),
        })

    # Identify key milestones (top 3 by significance)
    milestones = sorted(timeline_events, key=lambda x: x["significance_score"], reverse=True)[:3]
    key_milestones = [
        {
            "date": m["date"],
            "title": m["title"],
            "significance_score": m["significance_score"],
            "reason": _milestone_reason(m),
        }
        for m in milestones
    ]

    # Period
    dates = [e["date"] for e in timeline_events if e["date"]]
    start_date = min(dates) if dates else None
    end_date = max(dates) if dates else None
    duration_days = 0
    if start_date and end_date:
        try:
            duration_days = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days
        except ValueError:
            pass

    return {
        "events": timeline_events,
        "period": {
            "start": start_date,
            "end": end_date,
            "duration_days": duration_days,
        },
        "key_milestones": key_milestones,
        "total_events": len(timeline_events),
    }


def _calculate_significance(event: Dict, event_data: Dict) -> float:
    """Calculate event significance score (0-10)."""
    score = 0.0

    # Articles (media coverage)
    articles = event_data.get("NumArticles") or event.get("num_articles", 0)
    if articles:
        score += min(articles / 50, 4.0)  # Max 4 points

    # Goldstein intensity
    goldstein = event_data.get("GoldsteinScale") or event.get("goldstein_scale")
    if goldstein is not None:
        score += min(abs(goldstein) / 2, 3.0)  # Max 3 points

    # Severity score from fingerprint
    severity = event.get("severity_score")
    if severity is not None:
        score += severity  # Already 0-10, scale down

    # Has summary/headline (indicates fingerprint quality)
    if event.get("headline") and event.get("summary"):
        score += 1.0

    return min(round(score, 1), 10.0)


def _milestone_reason(milestone: Dict) -> str:
    """Generate a human-readable reason for why this is a milestone."""
    reasons = []
    if milestone.get("num_articles", 0) > 50:
        reasons.append("high media coverage")
    gs = milestone.get("goldstein_scale")
    if gs is not None and abs(gs) > 5:
        reasons.append("significant conflict/cooperation intensity")
    if milestone.get("significance_score", 0) > 7:
        reasons.append("major event")
    return ", ".join(reasons) if reasons else "notable event"


# ---------------------------------------------------------------------------
# Entity Evolution Builder
# ---------------------------------------------------------------------------

def build_entity_evolution(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Track how entities (actors, locations, organizations) evolve over time.

    Returns:
        Dict with actors, locations, and organizations tracking.
    """
    actors = defaultdict(lambda: {"first_seen": None, "last_seen": None, "event_count": 0, "locations": set(), "coactors": set(), "goldstein_values": []})
    locations = defaultdict(lambda: {"first_seen": None, "last_seen": None, "event_count": 0, "actors": set(), "event_types": set()})

    for evt in events:
        ed = evt.get("event_data") or evt
        date = evt.get("SQLDATE") or evt.get("date") or ed.get("SQLDATE", "")

        # Process actors
        for actor_key in ("Actor1Name", "Actor2Name"):
            actor = ed.get(actor_key)
            if not actor:
                continue

            a = actors[actor]
            a["event_count"] += 1
            if a["first_seen"] is None or date < a["first_seen"]:
                a["first_seen"] = date
            if a["last_seen"] is None or date > a["last_seen"]:
                a["last_seen"] = date

            # Location
            loc = ed.get("ActionGeo_FullName") or evt.get("location_name", "")
            if loc:
                a["locations"].add(loc)

            # Co-actors
            other = ed.get("Actor2Name") if actor_key == "Actor1Name" else ed.get("Actor1Name")
            if other and other != actor:
                a["coactors"].add(other)

            # Goldstein
            gs = ed.get("GoldsteinScale")
            if gs is not None:
                a["goldstein_values"].append(gs)

        # Process locations
        loc = ed.get("ActionGeo_FullName") or evt.get("location_name", "")
        if loc:
            l = locations[loc]
            l["event_count"] += 1
            if l["first_seen"] is None or date < l["first_seen"]:
                l["first_seen"] = date
            if l["last_seen"] is None or date > l["last_seen"]:
                l["last_seen"] = date

            for ak in ("Actor1Name", "Actor2Name"):
                a = ed.get(ak)
                if a:
                    l["actors"].add(a)

            et = evt.get("event_type_label") or evt.get("event_type", "")
            if et:
                l["event_types"].add(et)

    # Convert to sorted lists
    actor_list = []
    for name, data in sorted(actors.items(), key=lambda x: x[1]["event_count"], reverse=True):
        avg_goldstein = sum(data["goldstein_values"]) / len(data["goldstein_values"]) if data["goldstein_values"] else None
        actor_list.append({
            "name": name,
            "first_seen": data["first_seen"],
            "last_seen": data["last_seen"],
            "event_count": data["event_count"],
            "locations": sorted(data["locations"]),
            "coactors": sorted(data["coactors"])[:10],  # Top 10
            "avg_goldstein": round(avg_goldstein, 2) if avg_goldstein is not None else None,
            "role": _infer_actor_role(name, data),
        })

    location_list = []
    for name, data in sorted(locations.items(), key=lambda x: x[1]["event_count"], reverse=True):
        location_list.append({
            "name": name,
            "first_seen": data["first_seen"],
            "last_seen": data["last_seen"],
            "event_count": data["event_count"],
            "actors": sorted(data["actors"])[:10],
            "event_types": sorted(data["event_types"]),
        })

    return {
        "actors": actor_list[:20],  # Top 20
        "locations": location_list[:15],  # Top 15
        "total_actors": len(actor_list),
        "total_locations": len(location_list),
    }


def _infer_actor_role(actor_name: str, data: Dict) -> str:
    """Infer actor's role based on their events."""
    goldstein_values = data.get("goldstein_values", [])
    if not goldstein_values:
        return "unknown"

    avg_gs = sum(goldstein_values) / len(goldstein_values)
    if avg_gs < -3:
        return "antagonist"
    elif avg_gs > 3:
        return "cooperator"
    else:
        return "neutral"


# ---------------------------------------------------------------------------
# Theme Evolution Builder
# ---------------------------------------------------------------------------

def build_theme_evolution(gkg_themes: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Build theme evolution from GKG parsed theme data.

    Args:
        gkg_themes: Output from GKGClient._parse_gkg_themes()

    Returns:
        Dict with theme trends, emerging/declining themes.
    """
    if not gkg_themes or "themes_over_time" not in gkg_themes:
        return {
            "themes_over_time": [],
            "emerging_themes": [],
            "declining_themes": [],
            "dominant_themes": [],
        }

    themes_over_time = gkg_themes.get("themes_over_time", [])
    top_themes = gkg_themes.get("top_themes", [])

    # If we have time-series data, find emerging/declining
    emerging = []
    declining = []

    if len(themes_over_time) >= 2:
        first_day = themes_over_time[0]
        last_day = themes_over_time[-1]

        first_themes = {t["theme"]: t["count"] for t in first_day.get("top_themes", [])}
        last_themes = {t["theme"]: t["count"] for t in last_day.get("top_themes", [])}

        # Emerging: appeared or grew significantly
        for theme, count in last_themes.items():
            first_count = first_themes.get(theme, 0)
            if count > first_count * 2 and count >= 3:
                emerging.append({
                    "theme": theme,
                    "first_count": first_count,
                    "last_count": count,
                    "growth_ratio": round(count / max(first_count, 1), 1),
                })

        # Declining: disappeared or dropped significantly
        for theme, count in first_themes.items():
            last_count = last_themes.get(theme, 0)
            if count > last_count * 2 and count >= 3:
                declining.append({
                    "theme": theme,
                    "first_count": count,
                    "last_count": last_count,
                    "decline_ratio": round(count / max(last_count, 1), 1),
                })

    # Sort by significance
    emerging = sorted(emerging, key=lambda x: x["growth_ratio"], reverse=True)[:10]
    declining = sorted(declining, key=lambda x: x["decline_ratio"], reverse=True)[:10]

    return {
        "themes_over_time": themes_over_time,
        "emerging_themes": emerging,
        "declining_themes": declining,
        "dominant_themes": top_themes[:10],
        "total_unique_themes": gkg_themes.get("unique_themes", 0),
    }


# ---------------------------------------------------------------------------
# Narrative Arc Builder
# ---------------------------------------------------------------------------

def build_narrative_arc(
    timeline: Dict[str, Any],
    entity_evolution: Dict[str, Any],
    theme_evolution: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate a narrative arc description for LLM prompt enrichment.

    This is a structured text summary that helps the LLM understand
    the story's progression before generating the final report.
    """
    parts = []

    # Period
    period = timeline.get("period", {})
    if period.get("start"):
        parts.append(
            f"Story Period: {period['start']} to {period['end']} "
            f"({period.get('duration_days', 0)} days)"
        )

    # Total events
    parts.append(f"Total Events: {timeline.get('total_events', 0)}")

    # Key milestones
    milestones = timeline.get("key_milestones", [])
    if milestones:
        parts.append("Key Milestones:")
        for m in milestones:
            parts.append(f"  - {m['date']}: {m['title']} (significance: {m['significance_score']}/10)")

    # Actor dynamics
    actors = entity_evolution.get("actors", [])
    if actors:
        parts.append("Key Actors:")
        for a in actors[:5]:
            gs_info = f", avg Goldstein: {a['avg_goldstein']}" if a.get("avg_goldstein") is not None else ""
            parts.append(
                f"  - {a['name']}: {a['event_count']} events, "
                f"role: {a['role']}, active {a['first_seen']} to {a['last_seen']}{gs_info}"
            )

    # Location hotspots
    locations = entity_evolution.get("locations", [])
    if locations:
        parts.append("Key Locations:")
        for loc in locations[:5]:
            parts.append(f"  - {loc['name']}: {loc['event_count']} events")

    # Theme evolution
    if theme_evolution:
        dominant = theme_evolution.get("dominant_themes", [])
        if dominant:
            parts.append("Dominant Themes:")
            for t in dominant[:5]:
                parts.append(f"  - {t['theme']}: {t['count']} mentions")

        emerging = theme_evolution.get("emerging_themes", [])
        if emerging:
            parts.append("Emerging Themes:")
            for t in emerging[:3]:
                parts.append(f"  - {t['theme']}: grew {t['growth_ratio']}x")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Convenience: Full Storyline Build
# ---------------------------------------------------------------------------

def build_event_context(
    events: List[Dict[str, Any]],
    gkg_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build event context analysis from events and optional GKG data.

    Returns entity evolution and theme evolution for the Context Analysis panel.
    Timeline and narrative arc are handled separately by the event storyline chain.
    """
    entity_evolution = build_entity_evolution(events)
    theme_evolution = build_theme_evolution(gkg_data)

    return {
        "entity_evolution": entity_evolution,
        "theme_evolution": theme_evolution,
    }

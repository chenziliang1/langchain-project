"""
Analyze Router — AI-driven data exploration and visualization API.

Two-stage design for responsiveness:
1. POST /analyze       → Planner + Executor (fast, no LLM report)
2. POST /analyze/report → Report Generator (async, delayed load)
3. POST /analyze/event-report → Enhanced Report (storyline + news + GKG)
4. POST /analyze/storyline → Storyline data only
"""

import time
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException

from backend.services.data_service import data_service
from backend.agents.planner import Planner, ReportGenerator, QueryPlan
from backend.agents.enhanced_reporter import get_enhanced_reporter
from backend.services.executor import run_plan
from backend.services.storyline_builder import build_event_context
from backend.services.gkg_client import gkg_client
from backend.agents.enhanced_reporter import _compute_storyline_relevance
from backend.schemas.responses import (
    AnalyzeRequest,
    AnalyzeResponse,
    ReportRequest,
    QueryPlanOutput,
    ReportOutput,
    EventReportRequest,
    EventReportResponse,
    EnhancedReportOutput,
    StorylineRequest,
    StorylineResponse,
    StorylineData,
)

router = APIRouter(prefix="/analyze", tags=["analyze"])


@router.post("", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    """
    Stage 1: Planner + Executor only.
    Returns data + visualization plan immediately. NO report generation here.
    """
    total_start = time.time()
    llm_config = request.llm_config.model_dump() if request.llm_config else None

    try:
        # Step 1: Planner
        t0 = time.time()
        planner = Planner(config=llm_config)
        plan, planner_phases = await planner.plan(request.query)
        t_plan = round((time.time() - t0) * 1000, 1)
        print(f"[Analyze] Planner: {t_plan}ms | Intent: {plan.intent} | Steps: {len(plan.steps)}", flush=True)

        # Off-topic guard: skip database queries entirely
        if plan.intent == "off_topic":
            total_ms = round((time.time() - total_start) * 1000, 1)
            print(f"[Analyze] Off-topic detected, skipped execution in {total_ms}ms", flush=True)
            return AnalyzeResponse(
                query=request.query,
                plan=QueryPlanOutput(
                    intent=plan.intent,
                    time_range=None,
                    steps=[],
                    visualizations=[],
                ),
                data={},
                report=None,
                elapsed_ms=total_ms,
                phases=[
                    *planner_phases,
                    {"name": "Response Ready", "status": "completed", "detail": "No database queries needed for off-topic input.", "elapsed_ms": 0},
                ],
            )

        # Step 2: Executor
        t0 = time.time()
        results = await run_plan(data_service, plan)
        t_exec = round((time.time() - t0) * 1000, 1)
        print(f"[Analyze] Executor: {t_exec}ms | Keys: {list(results.keys())}", flush=True)

        total_ms = round((time.time() - total_start) * 1000, 1)
        print(f"[Analyze] TOTAL: {total_ms}ms (plan={t_plan}ms, exec={t_exec}ms)", flush=True)

        step_keys = list(results.keys())
        step_count = len(step_keys)
        step_names = ' → '.join(step_keys) if step_keys else 'none'

        return AnalyzeResponse(
            query=request.query,
            plan=QueryPlanOutput(
                intent=plan.intent,
                thinking=plan.thinking,
                time_range=plan.time_range,
                steps=[{"type": s.type, "params": s.params} for s in plan.steps],
                visualizations=plan.visualizations,
                report_prompt=plan.report_prompt,
                notice=plan.notice,
            ),
            data=results,
            report=None,  # Report is loaded separately
            elapsed_ms=total_ms,
            phases=[
                *planner_phases,
                {
                    "name": "Database Query",
                    "status": "completed",
                    "detail": f"Executed {step_count} query{'ies' if step_count != 1 else 'y'}: {step_names}",
                    "elapsed_ms": t_exec,
                },
                {"name": "Response Ready", "status": "completed", "detail": f"Total pipeline: {total_ms}ms", "elapsed_ms": 0},
            ],
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[Analyze] FAILED: {e}", flush=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")


@router.post("/report", response_model=ReportOutput)
async def generate_report(request: ReportRequest):
    """
    Stage 2: Report Generator (async delayed load).
    Frontend calls this AFTER receiving visualization data.
    """
    t0 = time.time()
    llm_config = request.llm_config.model_dump() if request.llm_config else None

    try:
        reporter = ReportGenerator(config=llm_config)
        report = await reporter.generate(request.data, request.prompt)
        t_report = round((time.time() - t0) * 1000, 1)
        print(f"[Analyze/Report] Generated in {t_report}ms", flush=True)
        return ReportOutput(
            summary=report.summary,
            key_findings=report.key_findings,
        )
    except Exception as e:
        print(f"[Analyze/Report] FAILED: {e}", flush=True)
        raise HTTPException(status_code=500, detail=f"Report generation failed: {e}")


@router.post("/event-report", response_model=EventReportResponse)
async def generate_event_report(request: EventReportRequest):
    """
    Enhanced event report with storyline, news coverage, and GKG insights.
    Single-call endpoint that returns complete report data.
    """
    t0 = time.time()
    llm_config = request.llm_config.model_dump() if request.llm_config else None

    try:
        reporter = get_enhanced_reporter(llm_config)
        config = request.config.model_dump() if request.config else None
        result = await reporter.generate_event_report(
            data=request.data,
            prompt=request.prompt,
            include_storyline=request.include_storyline,
            include_news=request.include_news,
            include_gkg=request.include_gkg,
            config=config,
        )

        t_report = round((time.time() - t0) * 1000, 1)
        print(f"[Analyze/EventReport] Generated in {t_report}ms", flush=True)

        return EventReportResponse(
            report=EnhancedReportOutput(
                summary=result.summary,
                key_findings=result.key_findings,
                event_context=result.event_context,
                news_coverage=result.news_coverage,
                gkg_insights=result.gkg_insights,
                actor_activity=result.actor_activity or [],
                event_storyline=result.event_storyline,
                generated_at=result.generated_at,
            ),
            elapsed_ms=t_report,
        )
    except Exception as e:
        print(f"[Analyze/EventReport] FAILED: {e}", flush=True)
        raise HTTPException(status_code=500, detail=f"Event report generation failed: {e}")


@router.post("/storyline", response_model=StorylineResponse)
async def get_storyline(request: StorylineRequest):
    """
    Get event storyline data (timeline + entities + themes) without LLM report.
    Can be called independently for visualization.
    """
    t0 = time.time()

    try:
        # Fetch event and related events
        events = []
        if request.fingerprint:
            event = await data_service.get_event_detail(request.fingerprint)
            if event:
                events.append(event)
                # Get similar events
                ed = event.get("event_data") or event
                gid = ed.get("GlobalEventID")
                if gid:
                    similar = await data_service.get_similar_events(gid, limit=10)
                    events.extend(similar)

        if not events and request.event_id:
            similar = await data_service.get_similar_events(request.event_id, limit=10)
            events.extend(similar)

        if not events:
            return StorylineResponse(
                storyline=None,
                elapsed_ms=round((time.time() - t0) * 1000, 1),
            )

        # --- Soft scoring: re-rank events by relevance to seed ---
        primary = events[0]
        ed = primary.get("event_data") or primary
        seed_date = ed.get("SQLDATE")
        seed_location = ed.get("ActionGeo_CountryCode") or ed.get("ActionGeo_FullName")
        seed_actor1 = ed.get("Actor1Name")
        seed_actor2 = ed.get("Actor2Name")
        seed_articles = ed.get("NumArticles", 0) or 0
        seed_goldstein = abs(ed.get("GoldsteinScale", 0) or 0)

        from datetime import datetime
        seed_dt = datetime.strptime(seed_date, "%Y-%m-%d") if seed_date else datetime.now()

        for evt in events:
            evt['_seed_articles'] = seed_articles
            evt['_seed_goldstein'] = seed_goldstein
            score = _compute_storyline_relevance(
                evt, seed_dt, seed_location,
                seed_actor1, seed_actor2,
                has_gkg=False, has_mentions=False,
            )
            evt['_relevance_score'] = round(score, 3)

        # Sort by relevance score DESC, then by date ASC
        events.sort(key=lambda e: (-e.get('_relevance_score', 0), e.get("SQLDATE", "")))

        # Optionally fetch GKG data
        gkg_themes = None
        if gkg_client.available and events:
            actor = ed.get("Actor1Name")
            if seed_date and actor:
                try:
                    gkg_result = await gkg_client.get_entity_themes(actor, (seed_date, seed_date), limit=50)
                    if not gkg_result.get("error"):
                        gkg_themes = gkg_result.get("parsed_themes")
                    else:
                        print(f"[Storyline] GKG themes: {gkg_result.get('message')}", flush=True)
                except Exception as e:
                    print(f"[Storyline] GKG fetch failed: {e}", flush=True)

        event_context = build_event_context(events, gkg_themes)

        t_total = round((time.time() - t0) * 1000, 1)
        print(f"[Analyze/Storyline] Built in {t_total}ms, {len(events)} events", flush=True)

        return StorylineResponse(
            storyline=StorylineData(
                timeline={"events": [], "period": {"start": None, "end": None, "duration_days": 0}, "key_milestones": []},
                entity_evolution=event_context["entity_evolution"],
                theme_evolution=event_context["theme_evolution"],
                narrative_arc="",
            ),
            elapsed_ms=t_total,
        )

    except Exception as e:
        print(f"[Analyze/Storyline] FAILED: {e}", flush=True)
        raise HTTPException(status_code=500, detail=f"Storyline generation failed: {e}")

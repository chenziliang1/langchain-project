"""
Planner Executor — Parallel query execution engine.

Receives a QueryPlan from the Planner, executes all steps in parallel
via DataService, and returns structured JSON results.
"""

import asyncio
from typing import Dict, Any, List

from backend.services.data_service import DataService
from backend.agents.planner import QueryPlan, QueryStep


class Executor:
    """Executes query plans by parallel DataService calls."""

    def __init__(self, data_service: DataService):
        self.ds = data_service

    async def execute(self, plan: QueryPlan) -> Dict[str, Any]:
        """
        Execute all steps in a query plan.
        Steps run sequentially to allow cross-step dependencies (e.g. similar_events
        needs the GlobalEventID from event_detail).

        Returns:
            dict mapping step index to result data
        """
        if not plan.steps:
            return {}

        output = {}
        for i, step in enumerate(plan.steps):
            # Resolve cross-step dependencies
            params = dict(step.params)
            if step.type == "similar_events":
                seed = params.get("seed_event_id")
                # If seed is missing or not a valid integer, try to extract from prior event_detail
                if seed is None or not isinstance(seed, int):
                    try:
                        seed = int(seed)
                        params["seed_event_id"] = seed
                    except (ValueError, TypeError):
                        for key, val in output.items():
                            if val.get("type") == "event_detail" and val.get("data"):
                                ed = val["data"]
                                gid = None
                                if isinstance(ed, dict):
                                    gid = ed.get("event_data", {}).get("GlobalEventID")
                                if gid:
                                    params["seed_event_id"] = int(gid)
                                    break

            resolved_step = QueryStep(type=step.type, params=params)
            result = await self._execute_step(i, resolved_step)

            key = f"{step.type}_{i}"
            if isinstance(result, Exception):
                print(f"[Executor] Step {i} ({step.type}) failed: {result}", flush=True)
                output[key] = {"error": str(result), "type": step.type}
            else:
                output[key] = {"type": step.type, "data": result}

        return output

    async def _execute_step(self, index: int, step: QueryStep) -> Any:
        """Execute a single query step via DataService."""
        p = step.params
        step_type = step.type

        if step_type == "events":
            return await self.ds.search_events(
                query_text=p.get("query", ""),
                start_date=p.get("start_date"),
                end_date=p.get("end_date"),
                time_hint=p.get("time_hint"),
                location_hint=p.get("location_hint"),
                event_type=p.get("event_type"),
                actor=p.get("actor"),
                max_results=p.get("limit", 20),
            )

        if step_type == "event_detail":
            return await self.ds.get_event_detail(p.get("fingerprint", ""))

        if step_type == "similar_events":
            seed_id = p.get("seed_event_id")
            if seed_id is None:
                return {"error": "seed_event_id not provided and no event_detail found"}
            return await self.ds.get_similar_events(int(seed_id), p.get("limit", 10))

        if step_type == "hot_events":
            return await self.ds.get_hot_events(
                query_date=p.get("query_date"),
                region_filter=p.get("region_filter"),
                top_n=p.get("top_n", 10),
            )

        if step_type == "top_events":
            return await self.ds.get_top_events(
                start_date=p.get("start_date"),
                end_date=p.get("end_date"),
                region_filter=p.get("region_filter"),
                event_type=p.get("event_type"),
                top_n=p.get("top_n", 10),
            )

        if step_type == "dashboard":
            return await self.ds.get_dashboard(
                start_date=p.get("start_date"),
                end_date=p.get("end_date"),
            )

        if step_type == "timeseries":
            return await self.ds.get_time_series(
                start_date=p.get("start_date"),
                end_date=p.get("end_date"),
                granularity=p.get("granularity", "day"),
            )

        if step_type == "geo":
            # Use geo_events if filters are present, otherwise geo_heatmap
            if p.get("location_hint") or p.get("location_exact") or p.get("event_type") or p.get("actor") or p.get("actor_exact"):
                return await self.ds.get_geo_events(
                    start_date=p.get("start_date"),
                    end_date=p.get("end_date"),
                    location_hint=p.get("location_hint"),
                    location_exact=p.get("location_exact"),
                    event_type=p.get("event_type"),
                    actor=p.get("actor"),
                    actor_exact=p.get("actor_exact"),
                    max_results=p.get("limit", 100),
                )
            return await self.ds.get_geo_heatmap(
                start_date=p.get("start_date"),
                end_date=p.get("end_date"),
                precision=p.get("precision", 2),
            )

        if step_type == "regional_overview":
            return await self.ds.get_regional_overview(
                region=p.get("region"),
                time_range=p.get("time_range", "week"),
                start_date=p.get("start_date"),
                end_date=p.get("end_date"),
            )

        if step_type == "daily_brief":
            return await self.ds.get_daily_brief(
                query_date=p.get("query_date"),
            )

        raise ValueError(f"Unknown step type: {step_type}")


async def run_plan(data_service: DataService, plan: QueryPlan) -> Dict[str, Any]:
    """Convenience function: execute a plan and return results."""
    executor = Executor(data_service)
    return await executor.execute(plan)

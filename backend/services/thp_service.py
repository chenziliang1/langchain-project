"""
Transformer Hawkes style event forecasting.

This module provides a fast, deterministic forecasting layer for GDELT event
sequences. It uses transformer-style temporal attention to estimate recent
context, then applies a Hawkes-style exponential decay to forecast short-term
event intensity.

The implementation is intentionally lightweight for production use in the
dashboard/chat path. A trained neural THP checkpoint can later replace the
forecast core while keeping the same service contract.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional

from backend.services.actor_normalization import (
    action_geo_country_code,
    actor_country_code,
    normalize_actor_name,
)
from backend.services.thp_neural import NeuralTHPCheckpoint, build_feature_vector


@dataclass
class SequencePoint:
    date: datetime
    event_count: float
    conflict_events: float
    cooperation_events: float
    avg_goldstein: float
    avg_tone: float
    total_articles: float


class TransformerHawkesForecaster:
    """Empirical THP-style forecaster for daily event intensity."""

    def __init__(self, lookback_days: int = 30, half_life_days: float = 7.0):
        self.lookback_days = lookback_days
        self.half_life_days = half_life_days
        checkpoint_path = os.getenv("THP_CHECKPOINT_PATH", "models/thp_gdelt.pt")
        self.neural_checkpoint = NeuralTHPCheckpoint(Path(checkpoint_path))
        self._feature_window_cache: Dict[str, List[List[float]]] = {}
        self._feature_window_cache_max = int(os.getenv("THP_FEATURE_WINDOW_CACHE_MAX", "64"))

    def forecast(
        self,
        rows: List[Dict[str, Any]],
        start_date: str,
        end_date: str,
        forecast_days: int = 14,
        region: Optional[str] = None,
        actor: Optional[str] = None,
        event_type: str = "conflict",
    ) -> Dict[str, Any]:
        points = self._complete_daily_sequence(rows, start_date, end_date)
        if len(points) < 7:
            return {
                "model": self._model_name(),
                "ok": False,
                "error": "At least 7 daily observations are required for forecasting.",
                "history_days": len(points),
            }

        neural_result = self._forecast_with_checkpoint(
            points=points,
            start_date=start_date,
            end_date=end_date,
            forecast_days=forecast_days,
            region=region,
            actor=actor,
            event_type=event_type,
        )
        if neural_result:
            return neural_result

        counts = [p.event_count for p in points]
        historical_mean = self._mean(counts)
        historical_median = median(counts)
        baseline = max(0.0, 0.65 * historical_mean + 0.35 * historical_median)
        recent_mean = self._mean(counts[-7:])
        trend = self._linear_slope(counts[-min(21, len(counts)):])
        alpha = self._estimate_excitation(counts)
        beta = math.log(2.0) / max(self.half_life_days, 1.0)
        context_intensity, attention = self._attention_context(points)
        excitation = max(0.0, context_intensity - baseline) * alpha

        forecast_points = []
        last_date = points[-1].date
        for horizon in range(1, max(1, min(forecast_days, 60)) + 1):
            decayed_excitation = excitation * math.exp(-beta * horizon)
            damped_trend = trend * horizon * math.exp(-horizon / 21.0)
            expected = max(0.0, baseline + decayed_excitation + damped_trend)
            risk_score = self._risk_score(expected, counts)
            interval = self._empirical_interval(expected, counts, horizon)
            forecast_points.append({
                "date": (last_date + timedelta(days=horizon)).strftime("%Y-%m-%d"),
                "expected_events": round(expected, 2),
                "low_events": round(interval["low"], 2),
                "median_events": round(expected, 2),
                "high_events": round(interval["high"], 2),
                "risk_score": round(risk_score, 1),
                "risk_level": self._risk_level(risk_score),
                "hawkes_excitation": round(decayed_excitation, 2),
            })

        peak = max(forecast_points, key=lambda p: p["risk_score"])
        recent_delta_pct = self._pct_change(recent_mean, historical_mean)
        confidence = self._confidence(points, counts)

        return {
            "model": self._model_name(),
            "ok": True,
            "target": {
                "region": region,
                "actor": actor,
                "event_type": event_type,
                "history_start": start_date,
                "history_end": end_date,
                "forecast_days": forecast_days,
            },
            "summary": {
                "risk_level": peak["risk_level"],
                "peak_risk_date": peak["date"],
                "peak_risk_score": peak["risk_score"],
                "expected_events_peak": peak["expected_events"],
                "historical_daily_mean": round(historical_mean, 2),
                "recent_7d_mean": round(recent_mean, 2),
                "recent_vs_history_pct": round(recent_delta_pct, 2),
                "baseline_intensity": round(baseline, 2),
                "excitation_strength": round(excitation, 2),
                "trend_slope_per_day": round(trend, 3),
                "confidence": confidence,
            },
            "forecast": forecast_points,
            "attention_context": attention,
            "checkpoint": {
                "available": self.neural_checkpoint.available,
                "error": self.neural_checkpoint.error,
            },
            "recent_history": [
                {
                    "date": p.date.strftime("%Y-%m-%d"),
                    "event_count": int(p.event_count),
                    "avg_goldstein": round(p.avg_goldstein, 3),
                    "avg_tone": round(p.avg_tone, 3),
                }
                for p in points[-14:]
            ],
        }

    def _forecast_with_checkpoint(
        self,
        points: List[SequencePoint],
        start_date: str,
        end_date: str,
        forecast_days: int,
        region: Optional[str],
        actor: Optional[str],
        event_type: str,
    ) -> Optional[Dict[str, Any]]:
        if not self.neural_checkpoint.available:
            return None

        feature_window = self._feature_window(points)
        predictions = self.neural_checkpoint.predict(
            feature_window=feature_window,
            forecast_days=max(1, min(forecast_days, 60)),
            series_key=self._series_key(region, actor),
            event_type=event_type,
        )
        if not predictions:
            return None

        counts = [p.event_count for p in points]
        historical_mean = self._mean(counts)
        recent_mean = self._mean(counts[-7:])
        baseline = max(0.0, 0.65 * historical_mean + 0.35 * median(counts))
        context_intensity, attention = self._attention_context(points)
        last_date = points[-1].date

        forecast_points = []
        for item in predictions:
            expected = item["expected_events"]
            risk_score = self._risk_score(expected, counts)
            horizon = int(item["horizon"])
            interval = self._prediction_interval(expected, horizon)
            forecast_points.append({
                "date": (last_date + timedelta(days=horizon)).strftime("%Y-%m-%d"),
                "expected_events": round(expected, 2),
                "low_events": round(interval["low"], 2),
                "median_events": round(expected, 2),
                "high_events": round(interval["high"], 2),
                "risk_score": round(risk_score, 1),
                "risk_level": self._risk_level(risk_score),
                "hawkes_excitation": round(max(0.0, expected - baseline), 2),
            })

        peak = max(forecast_points, key=lambda p: p["risk_score"])
        return {
            "model": "neural_transformer_hawkes_v1",
            "ok": True,
            "target": {
                "region": region,
                "actor": actor,
                "event_type": event_type,
                "history_start": start_date,
                "history_end": end_date,
                "forecast_days": forecast_days,
            },
            "summary": {
                "risk_level": peak["risk_level"],
                "peak_risk_date": peak["date"],
                "peak_risk_score": peak["risk_score"],
                "expected_events_peak": peak["expected_events"],
                "historical_daily_mean": round(historical_mean, 2),
                "recent_7d_mean": round(recent_mean, 2),
                "recent_vs_history_pct": round(self._pct_change(recent_mean, historical_mean), 2),
                "baseline_intensity": round(baseline, 2),
                "excitation_strength": round(max(0.0, context_intensity - baseline), 2),
                "trend_slope_per_day": round(self._linear_slope(counts[-min(21, len(counts)):]), 3),
                "confidence": self._confidence(points, counts),
            },
            "forecast": forecast_points,
            "attention_context": attention,
            "checkpoint": {
                "available": True,
                "path": str(self.neural_checkpoint.checkpoint_path),
                "metadata": self.neural_checkpoint.metadata,
                "series_key": self._series_key(region, actor),
                "baseline_comparison": self._baseline_comparison(),
            },
            "recent_history": [
                {
                    "date": p.date.strftime("%Y-%m-%d"),
                    "event_count": int(p.event_count),
                    "avg_goldstein": round(p.avg_goldstein, 3),
                    "avg_tone": round(p.avg_tone, 3),
                }
                for p in points[-14:]
            ],
        }

    def _model_name(self) -> str:
        if self.neural_checkpoint.available:
            return "neural_transformer_hawkes_v1"
        return "empirical_transformer_hawkes_v1"

    def _series_key(self, region: Optional[str], actor: Optional[str]) -> str:
        if actor:
            return f"actor:{normalize_actor_name(actor)}"
        if region:
            normalized = region.strip().upper()
            actor_pair = self._actor_pair_key(normalized)
            if actor_pair:
                return f"actor_pair:{actor_pair}"
            country_pair = self._country_pair_key(normalized)
            if country_pair:
                return f"country_pair:{country_pair}"
            country_code = action_geo_country_code(normalized) or normalized
            if len(country_code) in (2, 3):
                return f"country:{country_code}"
        return "global:ALL"

    def _actor_pair_key(self, normalized_region: str) -> Optional[str]:
        target = normalized_region
        force_actor_pair = False
        for prefix in ("ACTOR_PAIR:", "ACTORPAIR:", "ACTOR PAIR:"):
            if target.startswith(prefix):
                target = target[len(prefix):].strip()
                force_actor_pair = True
                break
        for prefix in ("COUNTRY_PAIR:", "COUNTRYPAIR:", "COUNTRY PAIR:"):
            if target.startswith(prefix):
                return None

        parts = self._split_pair_parts(target)
        if len(parts) != 2:
            return None

        left_country = actor_country_code(parts[0].strip())
        right_country = actor_country_code(parts[1].strip())
        if left_country and right_country and not force_actor_pair:
            return None

        left = normalize_actor_name(parts[0])
        right = normalize_actor_name(parts[1])
        if not left or not right or left == right:
            return None
        return " :: ".join(sorted((left, right)))

    def _country_pair_key(self, normalized_region: str) -> Optional[str]:
        target = normalized_region
        for prefix in ("COUNTRY_PAIR:", "COUNTRYPAIR:", "COUNTRY PAIR:"):
            if target.startswith(prefix):
                target = target[len(prefix):].strip()
                break
        for prefix in ("ACTOR_PAIR:", "ACTORPAIR:", "ACTOR PAIR:"):
            if target.startswith(prefix):
                return None

        parts = self._split_pair_parts(target)
        if len(parts) != 2:
            return None
        left = actor_country_code(parts[0].strip())
        right = actor_country_code(parts[1].strip())
        if not left or not right or left == right:
            return None
        return "-".join(sorted((left, right)))

    def _split_pair_parts(self, value: str) -> List[str]:
        separators = [" AND ", " VS ", " VERSUS ", "/", ","]
        if "-" in value and len(value) <= 15:
            return [part.strip() for part in value.split("-", 1)]
        for separator in separators:
            if separator in value:
                return [part.strip() for part in value.split(separator, 1)]
        return []

    def _prediction_interval(self, expected: float, horizon: int) -> Dict[str, float]:
        calibration = (
            self.neural_checkpoint.metadata
            .get("evaluation", {})
            .get("residual_calibration", {})
        )
        horizons = calibration.get("horizons", [])
        if 1 <= horizon <= len(horizons):
            item = horizons[horizon - 1]
            low = expected + float(item.get("residual_q10", 0.0))
            high = expected + float(item.get("residual_q90", 0.0))
            return {"low": max(0.0, low), "high": max(0.0, high)}
        spread = max(1.0, expected * 0.2)
        return {"low": max(0.0, expected - spread), "high": expected + spread}

    def _baseline_comparison(self) -> Dict[str, Any]:
        evaluation = self.neural_checkpoint.metadata.get("evaluation", {})
        improvements = evaluation.get("baseline_improvement") or {}
        moving_avg = improvements.get("moving_avg_7")
        if moving_avg:
            return {
                "best_baseline": "moving_avg_7",
                "mae_improvement_pct": round(float(moving_avg.get("mae_improvement_pct", 0.0)), 2),
                "model_mae": round(float(moving_avg.get("model_mae", 0.0)), 3),
                "baseline_mae": round(float(moving_avg.get("baseline_mae", 0.0)), 3),
            }
        model_mae = evaluation.get("neural_thp", {}).get("mae")
        baseline_mae = evaluation.get("baselines", {}).get("moving_avg_7", {}).get("mae")
        if model_mae is None or baseline_mae in (None, 0):
            return {}
        improvement = (float(baseline_mae) - float(model_mae)) * 100.0 / float(baseline_mae)
        return {
            "best_baseline": "moving_avg_7",
            "mae_improvement_pct": round(improvement, 2),
            "model_mae": round(float(model_mae), 3),
            "baseline_mae": round(float(baseline_mae), 3),
        }

    def _empirical_interval(self, expected: float, history: List[float], horizon: int) -> Dict[str, float]:
        if len(history) < 7:
            spread = max(1.0, expected * 0.25)
        else:
            recent = history[-min(30, len(history)):]
            mean_value = self._mean(recent)
            variance = self._mean([(value - mean_value) ** 2 for value in recent])
            spread = max(math.sqrt(max(variance, 0.0)), expected * 0.15) * math.sqrt(horizon / 7.0)
        return {"low": max(0.0, expected - spread), "high": expected + spread}

    def _complete_daily_sequence(
        self,
        rows: List[Dict[str, Any]],
        start_date: str,
        end_date: str,
    ) -> List[SequencePoint]:
        by_date = {str(r["date"]): r for r in rows}
        current = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        points: List[SequencePoint] = []

        while current <= end:
            date_key = current.strftime("%Y-%m-%d")
            row = by_date.get(date_key, {})
            points.append(SequencePoint(
                date=current,
                event_count=float(row.get("event_count") or 0),
                conflict_events=float(row.get("conflict_events") or 0),
                cooperation_events=float(row.get("cooperation_events") or 0),
                avg_goldstein=float(row.get("avg_goldstein") or 0),
                avg_tone=float(row.get("avg_tone") or 0),
                total_articles=float(row.get("total_articles") or 0),
            ))
            current += timedelta(days=1)

        return points

    def _attention_context(self, points: List[SequencePoint]) -> tuple[float, List[Dict[str, Any]]]:
        window = points[-min(self.lookback_days, len(points)):]
        query = self._feature_vector(window[-1])
        keys = [self._feature_vector(p) for p in window]
        scores = []

        for idx, key in enumerate(keys):
            lag = len(window) - idx - 1
            similarity = self._dot(query, key) / math.sqrt(len(query))
            recency_penalty = lag / max(self.half_life_days, 1.0)
            scores.append(similarity - recency_penalty)

        weights = self._softmax(scores)
        context = sum(w * p.event_count for w, p in zip(weights, window))
        top = sorted(
            [
                {
                    "date": p.date.strftime("%Y-%m-%d"),
                    "weight": round(w, 4),
                    "event_count": int(p.event_count),
                }
                for w, p in zip(weights, window)
            ],
            key=lambda item: item["weight"],
            reverse=True,
        )[:5]

        return context, top

    def _feature_vector(self, point: SequencePoint) -> List[float]:
        return build_feature_vector(
            event_count=point.event_count,
            conflict_events=point.conflict_events,
            cooperation_events=point.cooperation_events,
            avg_goldstein=point.avg_goldstein,
            avg_tone=point.avg_tone,
            total_articles=point.total_articles,
            event_date=point.date,
            rolling_counts=[point.event_count],
        )

    def _feature_window(self, points: List[SequencePoint]) -> List[List[float]]:
        cache_key = self._feature_window_cache_key(points)
        cached = self._feature_window_cache.get(cache_key)
        if cached is not None:
            return cached
        vectors = []
        counts_so_far: List[float] = []
        for point in points:
            counts_so_far.append(point.event_count)
            vectors.append(build_feature_vector(
                event_count=point.event_count,
                conflict_events=point.conflict_events,
                cooperation_events=point.cooperation_events,
                avg_goldstein=point.avg_goldstein,
                avg_tone=point.avg_tone,
                total_articles=point.total_articles,
                event_date=point.date,
                rolling_counts=counts_so_far,
            ))
        if self._feature_window_cache_max > 0:
            if len(self._feature_window_cache) >= self._feature_window_cache_max:
                oldest_key = next(iter(self._feature_window_cache))
                self._feature_window_cache.pop(oldest_key, None)
            self._feature_window_cache[cache_key] = vectors
        return vectors

    def _feature_window_cache_key(self, points: List[SequencePoint]) -> str:
        if not points:
            return "empty"
        total = sum(point.event_count for point in points)
        conflict = sum(point.conflict_events for point in points)
        cooperation = sum(point.cooperation_events for point in points)
        return (
            f"{points[0].date:%Y-%m-%d}|{points[-1].date:%Y-%m-%d}|"
            f"{len(points)}|{round(total, 3)}|{round(conflict, 3)}|{round(cooperation, 3)}"
        )

    def _estimate_excitation(self, counts: List[float]) -> float:
        if len(counts) < 3:
            return 0.25
        mean_value = self._mean(counts)
        numerator = 0.0
        denominator = 0.0
        for prev, curr in zip(counts[:-1], counts[1:]):
            numerator += (prev - mean_value) * (curr - mean_value)
            denominator += (prev - mean_value) ** 2
        if denominator <= 0:
            return 0.25
        lag_corr = numerator / denominator
        return max(0.05, min(0.85, lag_corr))

    def _risk_score(self, expected: float, history: List[float]) -> float:
        if not history:
            return 0.0
        sorted_history = sorted(history)
        below = sum(1 for value in sorted_history if value <= expected)
        percentile = below / len(sorted_history)
        mean_value = max(self._mean(history), 1.0)
        intensity_ratio = expected / mean_value
        return max(0.0, min(100.0, 65.0 * percentile + 35.0 * min(intensity_ratio, 2.0) / 2.0))

    def _risk_level(self, score: float) -> str:
        if score >= 80:
            return "high"
        if score >= 60:
            return "elevated"
        if score >= 35:
            return "moderate"
        return "low"

    def _confidence(self, points: List[SequencePoint], counts: List[float]) -> str:
        nonzero_days = sum(1 for value in counts if value > 0)
        if len(points) >= 90 and nonzero_days / len(points) >= 0.5:
            return "medium-high"
        if len(points) >= 30 and nonzero_days >= 10:
            return "medium"
        return "low"

    @staticmethod
    def _linear_slope(values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        n = len(values)
        xs = list(range(n))
        mean_x = sum(xs) / n
        mean_y = sum(values) / n
        denom = sum((x - mean_x) ** 2 for x in xs)
        if denom == 0:
            return 0.0
        return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values)) / denom

    @staticmethod
    def _mean(values: List[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _pct_change(value: float, baseline: float) -> float:
        if baseline == 0:
            return 0.0
        return (value - baseline) * 100.0 / baseline

    @staticmethod
    def _dot(left: List[float], right: List[float]) -> float:
        return sum(a * b for a, b in zip(left, right))

    @staticmethod
    def _softmax(values: List[float]) -> List[float]:
        if not values:
            return []
        max_value = max(values)
        exps = [math.exp(v - max_value) for v in values]
        total = sum(exps)
        if total == 0:
            return [1.0 / len(values)] * len(values)
        return [v / total for v in exps]

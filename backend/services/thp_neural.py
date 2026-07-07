"""
Neural Transformer Hawkes model utilities.

The model is intentionally compact: a Transformer encoder reads a fixed daily
history window, then a Hawkes-style head predicts baseline intensity plus a
decaying excitation term for future horizons.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np


FEATURE_SIZE = 16


def build_feature_vector(
    event_count: float,
    conflict_events: float,
    cooperation_events: float,
    avg_goldstein: float,
    avg_tone: float,
    total_articles: float,
    event_date: Optional[date | datetime | str] = None,
    rolling_counts: Optional[Sequence[float]] = None,
) -> List[float]:
    total = max(float(event_count), 1.0)
    base = [
        math.log1p(max(float(event_count), 0.0)),
        max(float(conflict_events), 0.0) / total,
        max(float(cooperation_events), 0.0) / total,
        float(avg_goldstein) / 10.0,
        float(avg_tone) / 10.0,
        math.log1p(max(float(total_articles), 0.0)),
    ]
    return base + _time_features(event_date) + _rolling_features(rolling_counts)


def _time_features(event_date: Optional[date | datetime | str]) -> List[float]:
    if event_date is None:
        return [0.0, 0.0, 0.0, 0.0]
    if isinstance(event_date, str):
        try:
            event_date = datetime.strptime(event_date, "%Y-%m-%d").date()
        except ValueError:
            return [0.0, 0.0, 0.0, 0.0]
    if isinstance(event_date, datetime):
        event_date = event_date.date()

    day_of_week = event_date.weekday()
    day_of_year = event_date.timetuple().tm_yday
    return [
        math.sin(2.0 * math.pi * day_of_week / 7.0),
        math.cos(2.0 * math.pi * day_of_week / 7.0),
        math.sin(2.0 * math.pi * day_of_year / 366.0),
        math.cos(2.0 * math.pi * day_of_year / 366.0),
    ]


def _rolling_features(rolling_counts: Optional[Sequence[float]]) -> List[float]:
    if not rolling_counts:
        return [0.0] * 6

    values = [max(float(value), 0.0) for value in rolling_counts]
    current = values[-1]
    mean_7 = _mean_tail(values, 7)
    mean_14 = _mean_tail(values, 14)
    mean_30 = _mean_tail(values, 30)
    std_7 = _std_tail(values, 7)
    slope_7 = _slope_tail(values, 7)
    spike_ratio = current / max(mean_7, 1.0)
    volatility = std_7 / max(mean_7, 1.0)
    trend = slope_7 / max(mean_7, 1.0)

    return [
        math.log1p(mean_7),
        math.log1p(mean_14),
        math.log1p(mean_30),
        max(0.0, min(spike_ratio, 10.0)) / 10.0,
        max(0.0, min(volatility, 10.0)) / 10.0,
        max(-1.0, min(trend, 1.0)),
    ]


def _mean_tail(values: Sequence[float], window: int) -> float:
    tail = values[-min(window, len(values)):]
    return sum(tail) / max(1, len(tail))


def _std_tail(values: Sequence[float], window: int) -> float:
    tail = values[-min(window, len(values)):]
    if len(tail) < 2:
        return 0.0
    mean_value = sum(tail) / len(tail)
    variance = sum((value - mean_value) ** 2 for value in tail) / len(tail)
    return math.sqrt(max(variance, 0.0))


def _slope_tail(values: Sequence[float], window: int) -> float:
    tail = values[-min(window, len(values)):]
    if len(tail) < 2:
        return 0.0
    x_mean = (len(tail) - 1) / 2.0
    y_mean = sum(tail) / len(tail)
    numerator = sum((idx - x_mean) * (value - y_mean) for idx, value in enumerate(tail))
    denominator = sum((idx - x_mean) ** 2 for idx in range(len(tail)))
    if denominator <= 0:
        return 0.0
    return numerator / denominator


class NeuralTHPCheckpoint:
    """Lazy checkpoint loader and inference wrapper."""

    def __init__(self, checkpoint_path: str | Path):
        self.checkpoint_path = Path(checkpoint_path)
        self._loaded = False
        self._available = False
        self._error: Optional[str] = None
        self._torch = None
        self._model = None
        self._config: Dict[str, Any] = {}
        self._feature_mean: Optional[np.ndarray] = None
        self._feature_std: Optional[np.ndarray] = None
        self._target_mean = 0.0
        self._target_std = 1.0
        self._metadata: Dict[str, Any] = {}
        self._series_to_id: Dict[str, int] = {}
        self._event_type_to_id: Dict[str, int] = {}
        self._series_group_to_id: Dict[str, int] = {}

    @property
    def available(self) -> bool:
        self._ensure_loaded()
        return self._available

    @property
    def error(self) -> Optional[str]:
        self._ensure_loaded()
        return self._error

    @property
    def metadata(self) -> Dict[str, Any]:
        self._ensure_loaded()
        return self._metadata

    @property
    def seq_len(self) -> int:
        self._ensure_loaded()
        return int(self._config.get("seq_len", 30))

    def predict(
        self,
        feature_window: List[List[float]],
        forecast_days: int,
        series_key: Optional[str] = None,
        event_type: str = "conflict",
    ) -> Optional[List[Dict[str, float]]]:
        self._ensure_loaded()
        if not self._available or self._model is None or self._torch is None:
            return None
        if self._feature_mean is None or self._feature_std is None:
            return None

        torch = self._torch
        seq_len = self.seq_len
        if len(feature_window) < seq_len:
            return None

        x = np.asarray(feature_window[-seq_len:], dtype=np.float32)
        expected_size = len(self._feature_mean)
        if x.shape[1] > expected_size:
            x = x[:, :expected_size]
        elif x.shape[1] < expected_size:
            padding = np.zeros((x.shape[0], expected_size - x.shape[1]), dtype=np.float32)
            x = np.concatenate([x, padding], axis=1)
        x = (x - self._feature_mean) / self._feature_std
        x_tensor = torch.tensor(x, dtype=torch.float32).unsqueeze(0)
        horizons = torch.arange(1, forecast_days + 1, dtype=torch.float32)
        series_tensor = torch.tensor([self._lookup_series_id(series_key)], dtype=torch.long)
        event_tensor = torch.tensor([self._lookup_event_type_id(event_type)], dtype=torch.long)
        group_tensor = torch.tensor([self._lookup_series_group_id(series_key)], dtype=torch.long)

        self._model.eval()
        with torch.no_grad():
            pred_norm, parts = self._model(
                x_tensor,
                horizons,
                series_tensor,
                event_tensor,
                group_tensor,
            )

        pred_log = pred_norm.squeeze(0).cpu().numpy() * self._target_std + self._target_mean
        expected = np.maximum(0.0, np.expm1(pred_log))
        excitation = parts["excitation"].squeeze(0).cpu().numpy()
        decay = parts["decay"].squeeze(0).cpu().numpy()

        return [
            {
                "horizon": float(i + 1),
                "expected_events": float(expected[i]),
                "neural_excitation": float(excitation[i]),
                "neural_decay": float(decay[i]),
            }
            for i in range(len(expected))
        ]

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True

        if not self.checkpoint_path.exists():
            self._error = f"checkpoint not found: {self.checkpoint_path}"
            return

        try:
            import torch
        except Exception as exc:
            self._error = f"torch import failed: {exc}"
            return

        try:
            checkpoint = torch.load(self.checkpoint_path, map_location="cpu", weights_only=False)
            config = checkpoint["config"]
            model = NeuralTransformerHawkesModel(**config)
            model.load_state_dict(checkpoint["model_state"], strict=False)
            model.eval()

            self._torch = torch
            self._model = model
            self._config = config
            self._feature_mean = np.asarray(checkpoint["feature_mean"], dtype=np.float32)
            self._feature_std = np.asarray(checkpoint["feature_std"], dtype=np.float32)
            self._target_mean = float(checkpoint["target_mean"])
            self._target_std = float(checkpoint["target_std"])
            self._metadata = self._compact_metadata(checkpoint.get("metadata", {}))
            self._series_to_id = {
                str(key): int(value)
                for key, value in checkpoint.get("series_to_id", {}).items()
            }
            self._event_type_to_id = {
                str(key): int(value)
                for key, value in checkpoint.get("event_type_to_id", {}).items()
            }
            self._series_group_to_id = {
                str(key): int(value)
                for key, value in checkpoint.get("series_group_to_id", {}).items()
            }
            self._available = True
        except Exception as exc:
            self._error = f"checkpoint load failed: {exc}"

    def _compact_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        compact = dict(metadata)
        series_labels = compact.pop("series_labels", None)
        if series_labels:
            compact.setdefault("series_label_count", len(series_labels))
            compact.setdefault("series_label_preview", series_labels[:40])
        return compact

    def _lookup_series_id(self, series_key: Optional[str]) -> int:
        if not self._series_to_id:
            return 0
        if series_key and series_key in self._series_to_id:
            return self._series_to_id[series_key]
        return self._series_to_id.get("global:ALL", 0)

    def _lookup_event_type_id(self, event_type: str) -> int:
        if not self._event_type_to_id:
            return 0
        normalized = (event_type or "conflict").lower()
        return self._event_type_to_id.get(normalized, self._event_type_to_id.get("all", 0))

    def _lookup_series_group_id(self, series_key: Optional[str]) -> int:
        if not self._series_group_to_id:
            return 0
        group_key = series_group_key(series_key or "global:ALL")
        return self._series_group_to_id.get(group_key, self._series_group_to_id.get("global", 0))


def series_group_key(series_key: str) -> str:
    prefix, _, suffix = series_key.partition(":")
    if prefix == "event_root" and suffix:
        return f"cameo_root:{suffix}"
    if prefix == "event_code" and suffix:
        return f"cameo_root:{suffix[:2]}"
    if prefix in {"actor", "actor_pair", "country", "country_pair"}:
        return prefix
    return "global"


def get_torch_model_class():
    """Expose the torch model class for training scripts after torch import."""
    return NeuralTransformerHawkesModel


try:
    import torch
    from torch import nn

    class NeuralTransformerHawkesModel(nn.Module):
        def __init__(
            self,
            input_size: int = FEATURE_SIZE,
            seq_len: int = 30,
            d_model: int = 48,
            nhead: int = 4,
            num_layers: int = 2,
            dropout: float = 0.1,
            num_series: int = 1,
            num_event_types: int = 1,
            num_series_groups: int = 1,
        ):
            super().__init__()
            self.seq_len = seq_len
            self.input_projection = nn.Linear(input_size, d_model)
            self.position = nn.Parameter(torch.zeros(1, seq_len, d_model))
            self.series_embedding = nn.Embedding(max(1, num_series), d_model)
            self.event_type_embedding = nn.Embedding(max(1, num_event_types), d_model)
            self.series_group_embedding = nn.Embedding(max(1, num_series_groups), d_model)
            self.attention_pool = nn.Linear(d_model, 1)
            self.horizon_projection = nn.Linear(1, d_model)
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=d_model,
                nhead=nhead,
                dim_feedforward=d_model * 4,
                dropout=dropout,
                batch_first=True,
                activation="gelu",
            )
            self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
            self.head = nn.Sequential(
                nn.LayerNorm(d_model),
                nn.Linear(d_model, d_model),
                nn.GELU(),
                nn.Linear(d_model, 3),
            )
            self.direct_head = nn.Sequential(
                nn.LayerNorm(d_model),
                nn.Linear(d_model, d_model),
                nn.GELU(),
                nn.Linear(d_model, 1),
            )

        def forward(self, x, horizons, series_ids=None, event_type_ids=None, series_group_ids=None):
            encoded = self.input_projection(x) + self.position[:, : x.shape[1], :]
            batch_size = x.shape[0]
            if series_ids is None:
                series_ids = torch.zeros(batch_size, dtype=torch.long, device=x.device)
            else:
                series_ids = series_ids.to(x.device)
            if event_type_ids is None:
                event_type_ids = torch.zeros(batch_size, dtype=torch.long, device=x.device)
            else:
                event_type_ids = event_type_ids.to(x.device)
            if series_group_ids is None:
                series_group_ids = torch.zeros(batch_size, dtype=torch.long, device=x.device)
            else:
                series_group_ids = series_group_ids.to(x.device)

            encoded = encoded + self.series_embedding(series_ids).unsqueeze(1)
            encoded = encoded + self.event_type_embedding(event_type_ids).unsqueeze(1)
            encoded = encoded + self.series_group_embedding(series_group_ids).unsqueeze(1)
            encoded = self.encoder(encoded)
            pool_weights = torch.softmax(self.attention_pool(encoded).squeeze(-1), dim=1)
            pooled_context = torch.sum(encoded * pool_weights.unsqueeze(-1), dim=1)
            context = 0.5 * encoded[:, -1, :] + 0.5 * pooled_context
            raw = self.head(context)

            baseline = raw[:, 0:1]
            excitation = torch.nn.functional.softplus(raw[:, 1:2])
            decay = torch.nn.functional.softplus(raw[:, 2:3]) + 1e-3
            h = horizons.to(x.device).view(1, -1)
            h_scaled = torch.log1p(h).unsqueeze(-1) / math.log(61.0)
            horizon_context = context.unsqueeze(1) + self.horizon_projection(h_scaled)
            direct = self.direct_head(horizon_context).squeeze(-1)
            hawkes_residual = baseline + excitation * torch.exp(-decay * h)
            pred = direct + 0.25 * hawkes_residual
            parts = {
                "baseline": baseline.expand_as(pred),
                "excitation": excitation * torch.exp(-decay * h),
                "decay": decay.expand_as(pred),
                "direct": direct,
            }
            return pred, parts

except Exception:
    NeuralTransformerHawkesModel = None  # type: ignore

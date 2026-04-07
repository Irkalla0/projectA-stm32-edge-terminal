#!/usr/bin/env python3
"""
Project A data pipeline:
ingest -> clean -> features -> anomaly score -> short-term forecast -> report.

Default strategy:
- anomaly: rules + EWMA/Z-score + IsolationForest(optional)
- forecast: Holt-Winters(optional) with fallback to naive persistence
"""

from __future__ import annotations

import argparse
import json
import math
import uuid
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd

try:
    from sklearn.ensemble import IsolationForest
except Exception:  # pragma: no cover - runtime optional dependency
    IsolationForest = None

try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
except Exception:  # pragma: no cover - runtime optional dependency
    ExponentialSmoothing = None


METRICS = ["temp_c", "hum_rh", "dist_mm", "curr_ma"]


def _safe_float(v, default=np.nan):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _load_csvs(paths: Iterable[Path], default_node: str) -> pd.DataFrame:
    parts: List[pd.DataFrame] = []
    for p in paths:
        df = pd.read_csv(p)
        if "source" in df.columns:
            df = df[df["source"] == "frame"].copy()
        if df.empty:
            continue
        if "node_id" not in df.columns:
            df["node_id"] = default_node
        if "ts" in df.columns:
            df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
        elif "host_ts" in df.columns:
            df["ts"] = pd.to_datetime(df["host_ts"], unit="s", errors="coerce")
        else:
            raise ValueError(f"{p} missing ts/host_ts column")

        for c in METRICS + ["seq", "cmd", "crc_ok"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df["source"] = df.get("source", "frame").fillna("frame")
        df["node_id"] = df["node_id"].fillna(default_node).astype(str)
        parts.append(df)

    if not parts:
        return pd.DataFrame(columns=["ts", "node_id", *METRICS, "seq", "cmd", "crc_ok", "source"])
    out = pd.concat(parts, ignore_index=True)
    out = out.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    return out


def _resample(df: pd.DataFrame, seconds: int) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    keep_cols = [c for c in ["node_id", *METRICS, "seq", "cmd", "crc_ok"] if c in df.columns]
    d2 = df[["ts", *keep_cols]].copy()
    # Aggregate per-node then merge back
    out_parts: List[pd.DataFrame] = []
    for node_id, g in d2.groupby("node_id"):
        g = g.set_index("ts")
        agg = g.resample(f"{seconds}s").mean(numeric_only=True)
        agg["node_id"] = node_id
        agg["sample_count"] = g.resample(f"{seconds}s").size()
        out_parts.append(agg.reset_index())
    out = pd.concat(out_parts, ignore_index=True).sort_values("ts").reset_index(drop=True)
    for m in METRICS:
        if m in out.columns:
            out[m] = out[m].interpolate(limit_direction="both")
    return out


def _add_features(df: pd.DataFrame, ewma_span: int, z_window: int) -> pd.DataFrame:
    d = df.copy()
    for m in METRICS:
        if m not in d.columns:
            d[m] = np.nan
        d[f"{m}_diff"] = d.groupby("node_id")[m].diff()
        d[f"{m}_ewma"] = d.groupby("node_id")[m].transform(
            lambda s: s.ewm(span=ewma_span, adjust=False).mean()
        )
        resid = d[m] - d[f"{m}_ewma"]
        d[f"{m}_ewma_resid"] = resid
        rolling_std = (
            d.groupby("node_id")[f"{m}_ewma_resid"]
            .transform(lambda s: s.rolling(z_window, min_periods=max(5, z_window // 3)).std())
            .replace(0.0, np.nan)
        )
        d[f"{m}_z"] = (resid / rolling_std).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return d


def _apply_rule_anomaly(
    df: pd.DataFrame,
    thr_t: float,
    thr_h: float,
    thr_d_high: float,
    thr_d_low: float,
    thr_i: float,
    step_temp: float,
    step_hum: float,
    step_dist: float,
    step_curr: float,
) -> pd.DataFrame:
    d = df.copy()
    d["rule_t_high"] = (d["temp_c"] > thr_t).astype(int)
    d["rule_h_high"] = (d["hum_rh"] > thr_h).astype(int)
    d["rule_d_high"] = (d["dist_mm"] > thr_d_high).astype(int)
    d["rule_d_low"] = (d["dist_mm"] < thr_d_low).astype(int)
    d["rule_i_high"] = (d["curr_ma"] > thr_i).astype(int)

    d["rule_t_jump"] = (d["temp_c_diff"].abs() > step_temp).astype(int)
    d["rule_h_jump"] = (d["hum_rh_diff"].abs() > step_hum).astype(int)
    d["rule_d_jump"] = (d["dist_mm_diff"].abs() > step_dist).astype(int)
    d["rule_i_jump"] = (d["curr_ma_diff"].abs() > step_curr).astype(int)

    rule_cols = [c for c in d.columns if c.startswith("rule_")]
    d["rule_hits"] = d[rule_cols].sum(axis=1)
    d["rule_reason"] = d[rule_cols].apply(
        lambda row: ",".join([k for k, v in row.items() if int(v) > 0]),
        axis=1,
    )
    return d


def _apply_iforest(df: pd.DataFrame, contamination: float, seed: int) -> pd.DataFrame:
    d = df.copy()
    d["iforest_flag"] = 0
    d["iforest_score"] = 0.0
    if IsolationForest is None:
        return d

    feat = d[METRICS].copy()
    feat = feat.ffill().bfill()
    if len(feat) < 40:
        return d

    model = IsolationForest(
        n_estimators=200,
        contamination=contamination,
        random_state=seed,
    )
    pred = model.fit_predict(feat.values)
    score = -model.decision_function(feat.values)
    s_min = float(np.nanmin(score))
    s_max = float(np.nanmax(score))
    if s_max <= s_min:
        norm = np.zeros_like(score)
    else:
        norm = (score - s_min) / (s_max - s_min)
    d["iforest_flag"] = (pred == -1).astype(int)
    d["iforest_score"] = norm
    return d


def _combine_anomaly(df: pd.DataFrame, z_threshold: float) -> pd.DataFrame:
    d = df.copy()
    z_cols = [f"{m}_z" for m in METRICS]
    d["max_abs_z"] = d[z_cols].abs().max(axis=1)
    d["z_flag"] = (d["max_abs_z"] >= z_threshold).astype(int)

    d["anomaly_flag"] = ((d["rule_hits"] > 0) | (d["z_flag"] > 0) | (d["iforest_flag"] > 0)).astype(int)
    d["anomaly_score"] = np.maximum.reduce(
        [
            np.clip(d["rule_hits"] / 4.0, 0.0, 1.0),
            np.clip(d["max_abs_z"] / 6.0, 0.0, 1.0),
            d["iforest_score"].fillna(0.0),
        ]
    )

    def _level(row) -> str:
        if row["anomaly_flag"] <= 0:
            return ""
        if row["rule_hits"] >= 2 or row["max_abs_z"] >= 5.0 or row["iforest_score"] >= 0.9:
            return "P1"
        if row["rule_hits"] >= 1 or row["max_abs_z"] >= 3.0 or row["iforest_flag"] >= 1:
            return "P2"
        return "P3"

    d["level"] = d.apply(_level, axis=1)
    d["anomaly_type"] = d.apply(
        lambda row: row["rule_reason"]
        if row["rule_reason"]
        else ("iforest+zscore" if row["iforest_flag"] and row["z_flag"] else ("iforest" if row["iforest_flag"] else "zscore")),
        axis=1,
    )
    return d


def _forecast_series(series: pd.Series, horizon: int) -> np.ndarray:
    s = series.dropna().astype(float)
    if len(s) == 0:
        return np.array([np.nan] * horizon, dtype=float)

    if ExponentialSmoothing is not None and len(s) >= 12:
        try:
            model = ExponentialSmoothing(
                s.values,
                trend="add",
                seasonal=None,
                initialization_method="estimated",
            )
            fit = model.fit(optimized=True, use_brute=False)
            pred = fit.forecast(horizon)
            return np.array(pred, dtype=float)
        except Exception:
            pass

    return np.array([float(s.iloc[-1])] * horizon, dtype=float)


def _backtest_metric(series: pd.Series, horizon: int) -> Dict[str, float]:
    s = series.dropna().astype(float)
    if len(s) < max(20, horizon * 3):
        return {"mae": math.nan, "mape": math.nan, "trend_acc": math.nan}
    train = s.iloc[:-horizon]
    test = s.iloc[-horizon:].to_numpy(dtype=float)
    pred = _forecast_series(train, horizon)
    mae = float(np.mean(np.abs(test - pred)))
    valid = np.abs(test) > 1e-6
    mape = float(np.mean(np.abs((test[valid] - pred[valid]) / test[valid])) * 100.0) if np.any(valid) else math.nan
    if len(test) >= 2:
        t1 = np.sign(np.diff(test))
        t2 = np.sign(np.diff(pred))
        trend_acc = float(np.mean((t1 == t2).astype(float)))
    else:
        trend_acc = math.nan
    return {"mae": mae, "mape": mape, "trend_acc": trend_acc}


def _build_events(df: pd.DataFrame, z_threshold: float) -> pd.DataFrame:
    flagged = df[df["anomaly_flag"] > 0].copy()
    if flagged.empty:
        return pd.DataFrame(
            columns=["event_id", "ts", "node_id", "level", "anomaly_type", "score", "threshold", "detail", "ack"]
        )

    events = []
    for _, row in flagged.iterrows():
        detail = {
            "temp_c": _safe_float(row.get("temp_c")),
            "hum_rh": _safe_float(row.get("hum_rh")),
            "dist_mm": _safe_float(row.get("dist_mm")),
            "curr_ma": _safe_float(row.get("curr_ma")),
            "rule_reason": row.get("rule_reason", ""),
            "max_abs_z": _safe_float(row.get("max_abs_z")),
            "iforest_score": _safe_float(row.get("iforest_score")),
        }
        events.append(
            {
                "event_id": f"evt_{uuid.uuid4().hex[:12]}",
                "ts": row["ts"],
                "node_id": row.get("node_id", "unknown"),
                "level": row.get("level", "P3"),
                "anomaly_type": row.get("anomaly_type", "unknown"),
                "score": round(_safe_float(row.get("anomaly_score"), 0.0), 4),
                "threshold": z_threshold,
                "detail": json.dumps(detail, ensure_ascii=False),
                "ack": 0,
            }
        )
    return pd.DataFrame(events)


def _make_report(
    out_report: Path,
    raw_df: pd.DataFrame,
    feat_df: pd.DataFrame,
    events_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    backtest: Dict[str, Dict[str, float]],
) -> None:
    lines: List[str] = []
    lines.append("=== Project A Analytics Daily Report ===")
    lines.append(f"Raw frame rows: {len(raw_df)}")
    lines.append(f"Resampled rows: {len(feat_df)}")
    if len(raw_df) > 0:
        t0 = raw_df["ts"].min()
        t1 = raw_df["ts"].max()
        lines.append(f"Time range: {t0} -> {t1}")
    lines.append(f"Anomaly events: {len(events_df)}")
    if len(events_df) > 0:
        level_cnt = events_df["level"].value_counts().to_dict()
        lines.append(f"Event level count: {level_cnt}")
    lines.append(f"Forecast rows: {len(forecast_df)}")
    lines.append("")
    lines.append("Backtest metrics:")
    for m, metrics in backtest.items():
        mae = metrics.get("mae")
        mape = metrics.get("mape")
        acc = metrics.get("trend_acc")
        lines.append(
            f"- {m}: MAE={mae:.4f} MAPE={mape:.2f}% TrendAcc={acc:.2%}"
            if not (math.isnan(mae) or math.isnan(mape) or math.isnan(acc))
            else f"- {m}: N/A (insufficient data)"
        )

    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Project A analytics + forecast pipeline")
    parser.add_argument("csv", nargs="+", help="input csv files (uart/distributed telemetry)")
    parser.add_argument("--default-node-id", default="stm32_core")
    parser.add_argument("--resample-seconds", type=int, default=30)
    parser.add_argument("--horizon-steps", type=int, default=60, help="forecast steps in resampled cadence")
    parser.add_argument("--contamination", type=float, default=0.03)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--ewma-span", type=int, default=12)
    parser.add_argument("--z-window", type=int, default=30)
    parser.add_argument("--z-threshold", type=float, default=3.0)
    parser.add_argument("--thr-t", type=float, default=26.5)
    parser.add_argument("--thr-h", type=float, default=60.0)
    parser.add_argument("--thr-d-high", type=float, default=900.0)
    parser.add_argument("--thr-d-low", type=float, default=150.0)
    parser.add_argument("--thr-i", type=float, default=800.0)
    parser.add_argument("--step-temp", type=float, default=1.5)
    parser.add_argument("--step-hum", type=float, default=5.0)
    parser.add_argument("--step-dist", type=float, default=250.0)
    parser.add_argument("--step-curr", type=float, default=180.0)
    parser.add_argument("--out-dir", default="D:/codex/project A/build/analysis")
    args = parser.parse_args()

    csv_paths = [Path(x).resolve() for x in args.csv]
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_df = _load_csvs(csv_paths, args.default_node_id)
    if raw_df.empty:
        raise SystemExit("No usable frame data found in input CSVs")

    # Save normalized raw telemetry.
    raw_cols = ["ts", "node_id", *METRICS, "seq", "cmd", "crc_ok", "source"]
    norm_raw = raw_df.copy()
    for c in raw_cols:
        if c not in norm_raw.columns:
            norm_raw[c] = np.nan
    norm_raw = norm_raw[raw_cols].copy()
    norm_raw.to_csv(out_dir / "unified_telemetry.csv", index=False, encoding="utf-8")

    feat_df = _resample(raw_df, args.resample_seconds)
    feat_df = _add_features(feat_df, ewma_span=args.ewma_span, z_window=args.z_window)
    feat_df = _apply_rule_anomaly(
        feat_df,
        thr_t=args.thr_t,
        thr_h=args.thr_h,
        thr_d_high=args.thr_d_high,
        thr_d_low=args.thr_d_low,
        thr_i=args.thr_i,
        step_temp=args.step_temp,
        step_hum=args.step_hum,
        step_dist=args.step_dist,
        step_curr=args.step_curr,
    )
    feat_df = _apply_iforest(feat_df, contamination=args.contamination, seed=args.seed)
    feat_df = _combine_anomaly(feat_df, z_threshold=args.z_threshold)
    feat_df.to_csv(out_dir / "features_with_scores.csv", index=False, encoding="utf-8")

    events_df = _build_events(feat_df, z_threshold=args.z_threshold)
    events_df.to_csv(out_dir / "anomaly_events.csv", index=False, encoding="utf-8")

    # Forecast per metric on all nodes combined using latest resampled series.
    # For distributed setup you can split by node_id in a future iteration.
    forecast_rows = []
    backtest = {}
    t_last = feat_df["ts"].max()
    future_ts = pd.date_range(
        start=t_last + pd.to_timedelta(args.resample_seconds, unit="s"),
        periods=args.horizon_steps,
        freq=f"{args.resample_seconds}s",
    )
    for m in METRICS:
        series = feat_df[m].astype(float)
        pred = _forecast_series(series, args.horizon_steps)
        bt = _backtest_metric(series, args.horizon_steps)
        backtest[m] = bt
        for ts, y in zip(future_ts, pred):
            forecast_rows.append(
                {
                    "ts": ts,
                    "metric": m,
                    "predicted": float(y),
                }
            )
    forecast_df = pd.DataFrame(forecast_rows)
    forecast_df.to_csv(out_dir / "forecast.csv", index=False, encoding="utf-8")

    _make_report(
        out_report=out_dir / "analysis_report.txt",
        raw_df=raw_df,
        feat_df=feat_df,
        events_df=events_df,
        forecast_df=forecast_df,
        backtest=backtest,
    )

    summary = {
        "raw_rows": int(len(raw_df)),
        "resampled_rows": int(len(feat_df)),
        "anomaly_events": int(len(events_df)),
        "forecast_rows": int(len(forecast_df)),
        "backtest": backtest,
        "deps": {
            "isolation_forest": bool(IsolationForest is not None),
            "holt_winters": bool(ExponentialSmoothing is not None),
        },
    }
    (out_dir / "analysis_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[INFO] Output dir: {out_dir}")
    print(f"[INFO] Unified telemetry: {out_dir / 'unified_telemetry.csv'}")
    print(f"[INFO] Anomaly events: {out_dir / 'anomaly_events.csv'}")
    print(f"[INFO] Forecast: {out_dir / 'forecast.csv'}")
    print(f"[INFO] Report: {out_dir / 'analysis_report.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

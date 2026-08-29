"""Trade & day-level statistics (spec §65, §66)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def daily_pnl(trades: pd.DataFrame) -> pd.Series:
    if trades.empty:
        return pd.Series(dtype=float)
    day = trades["exit_time"].dt.tz_convert("America/New_York").dt.date
    return trades.groupby(day)["pnl"].sum()


def compute_trade_metrics(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {
            "n_trades": 0, "win_rate": np.nan, "profit_factor": np.nan,
            "expectancy_r": np.nan, "avg_r": np.nan, "avg_winner_r": np.nan,
            "avg_loser_r": np.nan, "ev_per_trade_dollars": np.nan,
        }
    wins = trades[trades["pnl"] > 0]
    losses = trades[trades["pnl"] <= 0]
    gross_win = wins["pnl"].sum()
    gross_loss = -losses["pnl"].sum()
    return {
        "n_trades": len(trades),
        "win_rate": len(wins) / len(trades),
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else np.inf,
        "expectancy_r": trades["r_multiple"].mean(),
        "avg_r": trades["r_multiple"].mean(),
        "avg_winner_r": wins["r_multiple"].mean() if len(wins) else np.nan,
        "avg_loser_r": losses["r_multiple"].mean() if len(losses) else np.nan,
        "ev_per_trade_dollars": trades["pnl"].mean(),
    }


def compute_day_metrics(trades: pd.DataFrame) -> dict:
    dpnl = daily_pnl(trades)
    if dpnl.empty:
        return {
            "n_days": 0, "ev_per_day_dollars": np.nan, "trades_per_day": np.nan,
            "std_daily_pnl": np.nan, "max_drawdown": np.nan,
            "pct_5": np.nan, "pct_95": np.nan, "sharpe_daily": np.nan,
        }
    cum = dpnl.cumsum()
    running_max = cum.cummax()
    drawdown = cum - running_max
    n_days = dpnl.shape[0]
    n_trades = len(trades)
    return {
        "n_days": n_days,
        "ev_per_day_dollars": dpnl.mean(),
        "trades_per_day": n_trades / n_days if n_days else np.nan,
        "std_daily_pnl": dpnl.std(),
        "max_drawdown": drawdown.min(),
        "pct_5": dpnl.quantile(0.05),
        "pct_95": dpnl.quantile(0.95),
        "sharpe_daily": (dpnl.mean() / dpnl.std() * np.sqrt(252)) if dpnl.std() > 0 else np.nan,
    }

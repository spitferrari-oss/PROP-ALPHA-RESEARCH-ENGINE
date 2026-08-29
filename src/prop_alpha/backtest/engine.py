"""Event-driven intraday backtest engine (spec §21).

Bar-by-bar simulation (not close-to-close): entries execute on the bar
*after* the signal bar's close (no look-ahead), stops/targets are checked
against each bar's intrabar high/low, and every open position is flattened
at the session's last bar. Costs (commission, slippage, spread) are applied
on both entry and exit.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from prop_alpha.backtest.costs import CostModel


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    direction: int
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: float
    exit_reason: str
    r_multiple: float
    pnl: float


def run_backtest(
    df: pd.DataFrame,
    cost_model: CostModel,
    max_trades_day: int = 3,
    point_value: float | None = None,
) -> list[Trade]:
    """`df` must already carry 'direction', 'stop_distance', 'target_distance'
    columns (see Strategy.with_risk_levels) plus OHLC + timestamp.
    """
    point_value = point_value if point_value is not None else cost_model.tick_value / cost_model.tick_size

    day = df["timestamp"].dt.tz_convert("America/New_York").dt.date
    df = df.reset_index(drop=True)
    df["_day"] = day.reset_index(drop=True)

    trades: list[Trade] = []
    in_position = False
    pos = {}
    trades_today = 0
    current_day = None

    n = len(df)
    for i in range(n):
        row = df.iloc[i]

        if row["_day"] != current_day:
            current_day = row["_day"]
            trades_today = 0
            if in_position:
                # Should not normally happen (EOD flatten below), safety net.
                in_position = False

        is_last_bar_of_day = (i == n - 1) or (df.iloc[i + 1]["_day"] != current_day)

        if in_position:
            hit_stop = (
                row["low"] <= pos["stop_price"] if pos["direction"] == 1
                else row["high"] >= pos["stop_price"]
            )
            hit_target = (
                row["high"] >= pos["target_price"] if pos["direction"] == 1
                else row["low"] <= pos["target_price"]
            )

            exit_price = None
            exit_reason = None
            if hit_stop:
                exit_price = pos["stop_price"]
                exit_reason = "STOP"
            elif hit_target:
                exit_price = pos["target_price"]
                exit_reason = "TARGET"
            elif is_last_bar_of_day:
                exit_price = row["close"]
                exit_reason = "EOD"

            if exit_price is not None:
                slip = cost_model.exit_slippage_price()
                filled_exit = exit_price - slip if pos["direction"] == 1 else exit_price + slip
                gross_points = (filled_exit - pos["entry_price"]) * pos["direction"]
                pnl = gross_points * point_value - cost_model.commission_dollars()
                r_multiple = gross_points / pos["stop_distance"] if pos["stop_distance"] > 0 else 0.0
                trades.append(
                    Trade(
                        entry_time=pos["entry_time"],
                        exit_time=row["timestamp"],
                        direction=pos["direction"],
                        entry_price=pos["entry_price"],
                        exit_price=filled_exit,
                        stop_price=pos["stop_price"],
                        target_price=pos["target_price"],
                        exit_reason=exit_reason,
                        r_multiple=r_multiple,
                        pnl=pnl,
                    )
                )
                in_position = False

        if (
            not in_position
            and i > 0
            and not is_last_bar_of_day
            and trades_today < max_trades_day
        ):
            signal_row = df.iloc[i - 1]
            direction = signal_row["direction"]
            if direction != 0 and not pd.isna(signal_row.get("stop_distance", np.nan)):
                stop_distance = signal_row["stop_distance"]
                target_distance = signal_row["target_distance"]
                if stop_distance > 0:
                    slip = cost_model.entry_slippage_price()
                    raw_entry = row["open"]
                    entry_price = raw_entry + slip if direction == 1 else raw_entry - slip
                    stop_price = entry_price - direction * stop_distance
                    target_price = entry_price + direction * target_distance
                    pos = {
                        "direction": direction,
                        "entry_price": entry_price,
                        "entry_time": row["timestamp"],
                        "stop_price": stop_price,
                        "target_price": target_price,
                        "stop_distance": stop_distance,
                    }
                    in_position = True
                    trades_today += 1

    return trades


def trades_to_frame(trades: list[Trade]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame(
            columns=[
                "entry_time", "exit_time", "direction", "entry_price", "exit_price",
                "stop_price", "target_price", "exit_reason", "r_multiple", "pnl",
            ]
        )
    return pd.DataFrame([t.__dict__ for t in trades])

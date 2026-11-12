"""Deterministic configuration space and paper account arithmetic (no blockchain writes)."""
from dataclasses import dataclass, field
from itertools import product
import hashlib
import json
import math

# 10 * 10 * 10 * 10 * 10 * 10 = exactly 1,000,000 distinct configurations
FAMILIES = ["momentum", "breakout", "reversal", "volume_spike", "trend_follow", "mean_reversion", "volatility", "scalp", "pullback", "hybrid"]
THRESHOLDS = [0.4,0.6,0.8,1,1.2,1.5,2,2.5,3,4]
VOLUME_MULTIPLIERS = [1,1.2,1.5,2,2.5,3,4,5,6,8]
TAKE_PROFITS = [2,3,4,5,7,10,12,15,20,30]
STOP_LOSSES = [1,1.5,2,2.5,3,4,5,6,8,10]
HOLDS = [15,30,45,60,90,120,180,240,360,600]

TOTAL_CONFIGURATIONS = 1_000_000

def config_at(index):
    if not 0 <= index < TOTAL_CONFIGURATIONS:
        raise IndexError(index)
    dimensions = [FAMILIES,THRESHOLDS,VOLUME_MULTIPLIERS,TAKE_PROFITS,STOP_LOSSES,HOLDS]
    values = []
    for choices in reversed(dimensions):
        index, offset = divmod(index, len(choices))
        values.append(choices[offset])
    return dict(zip(["family","momentum_pct","volume_multiplier","take_profit_pct","stop_loss_pct","max_hold_seconds"],reversed(values)))

def config_hash(index):
    encoded=json.dumps(config_at(index),sort_keys=True,separators=(",",":")).encode()
    return hashlib.sha256(encoded).hexdigest()

@dataclass
class PaperAccount:
    cash: float = 10.0
    units: float = 0.0
    entry: float = 0.0
    opened_at: float = 0.0
    token: str = ""
    trades: int = 0
    wins: int = 0
    realized: float = 0.0
    last_equity: float = 10.0
    peak_equity: float = 10.0
    max_drawdown_pct: float = 0.0
    history: list = field(default_factory=list)

    def equity(self, price, exit_cost_pct=1.0):
        return self.cash + self.units * price * (1-exit_cost_pct/100)

    def mark(self, price):
        self.last_equity=self.equity(price)
        self.peak_equity=max(self.peak_equity,self.last_equity)
        self.max_drawdown_pct=max(self.max_drawdown_pct,100*(1-self.last_equity/self.peak_equity))
        return self.last_equity

    def buy(self, price, timestamp, cost_pct=1.0):
        if price <= 0 or self.units or self.cash < 0.5:
            return False
        invested=self.cash
        self.units=(invested*(1-cost_pct/100))/price
        self.cash=0.0
        self.entry=invested
        self.opened_at=timestamp
        return True

    def sell(self, price, timestamp, cost_pct=1.0):
        if price <= 0 or self.units <= 0:
            return False
        payout=self.units*price*(1-cost_pct/100)
        pnl=payout-self.entry
        self.cash=payout
        self.units=0.0
        self.trades+=1
        self.wins+=int(pnl>0)
        self.realized+=pnl
        self.history.append({"ts":timestamp,"pnl":round(pnl,5),"cash":round(self.cash,5)})
        self.entry=0.0
        self.token=""
        self.mark(price)
        return True

def should_enter(config, change_pct, volume_ratio):
    threshold=config["momentum_pct"]
    family=config["family"]
    if family in ("reversal","mean_reversion","pullback"):
        return change_pct <= -threshold and volume_ratio >= config["volume_multiplier"]
    return change_pct >= threshold and volume_ratio >= config["volume_multiplier"]

def should_exit(config, account, price, now):
    if not account.units:
        return False
    # Estimated proceeds after exit cost, versus full amount spent on entry
    change=100*(account.equity(price)/account.entry-1)
    return change >= config["take_profit_pct"] or change <= -config["stop_loss_pct"] or now-account.opened_at >= config["max_hold_seconds"]

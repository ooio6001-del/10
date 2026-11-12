"""Deterministic configuration space and paper account arithmetic (no blockchain writes)."""
from dataclasses import dataclass, field
import hashlib
import json

# 10 * 10 * 10 * 10 * 10 * 10 = exactly 1,000,000 distinct configurations
FAMILIES = ["momentum", "breakout", "reversal", "volume_spike", "trend_follow", "mean_reversion", "volatility", "scalp", "pullback", "hybrid"]
THRESHOLDS = [0.4,0.6,0.8,1,1.2,1.5,2,2.5,3,4]
VOLUME_MULTIPLIERS = [1,1.2,1.5,2,2.5,3,4,5,6,8]
TAKE_PROFITS = [2,3,4,5,7,10,12,15,20,30]
STOP_LOSSES = [1,1.5,2,2.5,3,4,5,6,8,10]
HOLDS = [15,30,45,60,90,120,180,240,360,600]

TOTAL_CONFIGURATIONS = 1_000_000
START_BALANCE = 1900.0
MIN_STAKE_CENTS = 1
MAX_STAKE_CENTS = 500
PAPER_VARIABLE_COST_PCT = 1.0
PAPER_FIXED_FEE_USD = 0.01  # estimated per side; illustrative and configurable, not a live fee quote

def stake_amount(cents):
    if not isinstance(cents,int) or not MIN_STAKE_CENTS <= cents <= MAX_STAKE_CENTS:
        raise ValueError("Stake must be 1 to 500 cents")
    return round(cents / 100, 2)


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
    cash: float = START_BALANCE
    units: float = 0.0
    entry: float = 0.0
    entry_fixed_fee: float = 0.0
    opened_at: float = 0.0
    token: str = ""
    trades: int = 0
    wins: int = 0
    realized: float = 0.0
    last_equity: float = START_BALANCE
    peak_equity: float = START_BALANCE
    max_drawdown_pct: float = 0.0
    history: list = field(default_factory=list)

    def equity(self, price, exit_cost_pct=PAPER_VARIABLE_COST_PCT, exit_fixed_fee=PAPER_FIXED_FEE_USD):
        proceeds = max(0.0, self.units * price * (1-exit_cost_pct/100) - exit_fixed_fee) if self.units else 0.0
        return self.cash + proceeds

    def mark(self, price):
        self.last_equity=self.equity(price)
        self.peak_equity=max(self.peak_equity,self.last_equity)
        self.max_drawdown_pct=max(self.max_drawdown_pct,100*(1-self.last_equity/self.peak_equity))
        return self.last_equity

    def buy(self, price, timestamp, size_usd, cost_pct=PAPER_VARIABLE_COST_PCT, fixed_fee=PAPER_FIXED_FEE_USD):
        if price <= 0 or self.units or size_usd <= 0 or fixed_fee < 0 or not 0 <= cost_pct < 100:
            return False
        total_spend = size_usd + fixed_fee
        if total_spend > self.cash + 1e-9:
            return False
        units = size_usd * (1-cost_pct/100) / price
        if units <= 0: return False
        self.units = units
        self.cash -= total_spend
        self.entry = total_spend
        self.entry_fixed_fee = fixed_fee
        self.opened_at = timestamp
        return True

    def sell(self, price, timestamp, cost_pct=PAPER_VARIABLE_COST_PCT, fixed_fee=PAPER_FIXED_FEE_USD):
        if price <= 0 or self.units <= 0 or fixed_fee < 0 or not 0 <= cost_pct < 100:
            return False
        payout=max(0.0,self.units*price*(1-cost_pct/100)-fixed_fee)
        pnl=payout-self.entry
        self.cash+=payout
        self.units=0.0
        self.trades+=1
        self.wins+=int(pnl>0)
        self.realized+=pnl
        self.history.append({"ts":timestamp,"pnl":round(pnl,5),"cash":round(self.cash,5)})
        self.entry=0.0
        self.entry_fixed_fee=0.0
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
    change=100*((max(0.0,account.units*price*0.99-PAPER_FIXED_FEE_USD))/account.entry-1)
    return change >= config["take_profit_pct"] or change <= -config["stop_loss_pct"] or now-account.opened_at >= config["max_hold_seconds"]

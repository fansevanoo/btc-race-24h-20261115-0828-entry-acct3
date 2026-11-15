"""BTC race bot — dip-bounce mean reversion (long only, half size).

A different trade from the capitulation sniper: this bot buys ordinary
pullbacks, not capitulations. It waits for price to dip to a support, print
an oversold RSI, then reclaim the fast average with a bullish bar and a
MACD turn. It buys half size, takes a fixed 2:1 profit target, and never
chases momentum.

Entry (all of these, on the close of bar i):
  1. Dip: the close fell >= DIP_FALL bps over DIP_SPAN bars ending at i-1,
     AND it sits >= DEEP_FALL bps under the 720-bar high (a deep dip,
     not an ordinary pullback — shallow dips in a drift keep falling).
  2. Oversold turn: RSI(14) dipped under RSI_LOW within the last
     RSI_LOOK bars and is now back above RSI_LOW (rising off oversold).
  3. Support: the dip's low sits at or below EMA-50 (price retraced to
     the medium average) while the close is still under EMA-20.
  4. Bounce: a CONFIRMED turn — this bar closes above EMA-9 AND EMA-20,
     prints the second up close in a row, closes above its open, and is
     up >= BOUNCE_MIN bps on the previous close. A single up bar inside
     a fall is a trap; two in a row after the averages turn is the bounce.
  5. MACD: the MACD histogram is above zero (fast line over slow line,
     momentum turning with the bounce).

Sizing: 50% of equity per trade (half size, never full size).
Exit: fixed take-profit +TP_BPS, fixed stop -SL_BPS (2:1), or a
HOLD_MAX-bar time stop. No trailing stop.

Guards: at most 2 entries per window, stop after 2 consecutive losses,
never enter under 98% of starting equity, no entries after bar 1320,
30-bar cooldown after an exit.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
BPS = 10_000

# --- entry thresholds (basis points) -------------------------------------
DIP_FALL = 150           # close must fall this much over DIP_SPAN bars
DIP_SPAN = 60            # bars over which the dip is measured
DEEP_FALL = 600          # close must be this far under the 720-bar high
DEEP_SPAN = 720          # bars over which the deep fall is measured
RSI_LOW = 32             # oversold line for RSI(14)
RSI_LOOK = 30            # bars back to look for the oversold print
BOUNCE_MIN = 30          # bounce bar must close up this many bps
RSI_LEN = 14
EMA_FAST = 9
EMA_MID = 20
EMA_SLOW = 50
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIG = 9

# --- sizing / exits --------------------------------------------------------
SIZE_BPS = 5_000         # 50% of equity per trade
TP_BPS = 150             # fixed take-profit above the entry close
SL_BPS = 75              # fixed stop below the entry close
HOLD_MAX = 120           # bars

# --- guards ---------------------------------------------------------------
MAX_ENTRIES = 2
MAX_LOSERS = 2
EQUITY_FLOOR_BPS = 9_800  # 98% of starting equity
LAST_ENTRY_BAR = 1_320
COOLDOWN = 30
SLIP_BPS = 500           # max slippage on any order (fills are ~1 bar away)


def _rsi(closes, period, upto):
    """Wilder's RSI(period) of closes[0..upto]. None when not enough data."""
    if upto < period:
        return None
    gain = 0.0
    loss = 0.0
    for k in range(1, period + 1):
        move = closes[k] - closes[k - 1]
        if move > 0:
            gain += move
        else:
            loss -= move
    avg_gain = gain / period
    avg_loss = loss / period
    for k in range(period + 1, upto + 1):
        move = closes[k] - closes[k - 1]
        up = move if move > 0 else 0
        down = -move if move < 0 else 0
        avg_gain = (avg_gain * (period - 1) + up) / period
        avg_loss = (avg_loss * (period - 1) + down) / period
    if avg_loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def _ema(closes, period, upto):
    """EMA(period) of closes[0..upto]. None when not enough data."""
    if upto < period - 1:
        return None
    k = 2.0 / (period + 1)
    val = sum(closes[:period]) / period
    for idx in range(period, upto + 1):
        val = closes[idx] * k + val * (1.0 - k)
    return val


def _macd_hist(closes, upto):
    """MACD(12,26,9) histogram at closes[0..upto]. None when not enough data."""
    if upto < MACD_SLOW + MACD_SIG:
        return None
    fast = _ema(closes, MACD_FAST, upto)
    slow = _ema(closes, MACD_SLOW, upto)
    if fast is None or slow is None:
        return None
    # Build the MACD line series up to `upto`, then its signal EMA(9).
    macd = []
    for idx in range(MACD_SLOW, upto + 1):
        f = _ema(closes, MACD_FAST, idx)
        s = _ema(closes, MACD_SLOW, idx)
        macd.append(f - s)
    if len(macd) < MACD_SIG:
        return None
    k = 2.0 / (MACD_SIG + 1)
    sig = sum(macd[:MACD_SIG]) / MACD_SIG
    for v in macd[MACD_SIG:]:
        sig = v * k + sig * (1.0 - k)
    return macd[-1] - sig


class DipBounce:
    """One window of state: the bar tape and the open trade, if any."""

    def __init__(self):
        self.closes = []
        self.opens = []
        self.highs = []
        self.lows = []
        self.start_equity = None
        self.entries = 0
        self.losers = 0
        self.cool_until = -1
        self.entry_ref = None
        self.entry_bar = None
        self.take_profit = None
        self.stop_loss = None

    def _setup(self, i):
        """True when bar i is a dip-bounce entry."""
        prev = i - 1
        if prev < DEEP_SPAN:
            return False
        # 1) a dip just happened
        if prev < DIP_SPAN:
            return False
        ref = self.closes[prev - DIP_SPAN]
        fall = (ref - self.closes[prev]) * BPS // ref
        if fall < DIP_FALL:
            return False
        # 1b) it is a DEEP dip: far under the 8-12h high. Ordinary
        # pullbacks in a drift keep falling; only the deep ones bounce
        # far enough to pay the round trip.
        high_deep = max(self.highs[prev - DEEP_SPAN + 1: prev + 1])
        deep = (self.closes[prev] - high_deep) * BPS // high_deep
        if deep > -DEEP_FALL:
            return False
        # 2) RSI dipped under the oversold line recently and is turning up
        rsi_now = _rsi(self.closes, RSI_LEN, i)
        if rsi_now is None or rsi_now < RSI_LOW:
            return False
        oversold = False
        for j in range(max(RSI_LEN, i - RSI_LOOK), i + 1):
            r = _rsi(self.closes, RSI_LEN, j)
            if r is not None and r < RSI_LOW:
                oversold = True
                break
        if not oversold:
            return False
        # 3) support: the dip's low reached the slow average (price
        # retraced to support). No cap on the close vs the mid average:
        # a real bounce reclaims it fast, and requiring the close under
        # it only lets in the dips that keep falling.
        dip_low = min(self.lows[prev - DIP_SPAN + 1: prev + 1])
        ema_slow = _ema(self.closes, EMA_SLOW, prev)
        if ema_slow is None:
            return False
        if dip_low > ema_slow:
            return False
        # 4) bounce: a CONFIRMED turn, not a single up bar. The close
        # reclaimed both fast averages, printed two up closes in a row,
        # closed above its open, and is up >= BOUNCE_MIN bps. A single
        # up bar inside a fall is a trap; two in a row after the averages
        # turn is the bounce.
        ema_fast = _ema(self.closes, EMA_FAST, i)
        ema_mid = _ema(self.closes, EMA_MID, i)
        if ema_fast is None or ema_mid is None:
            return False
        if self.closes[i] <= ema_fast:
            return False
        if self.closes[i] <= ema_mid:
            return False
        if self.closes[i] <= self.closes[prev]:
            return False
        if self.closes[prev] <= self.closes[prev - 1]:
            return False
        if self.closes[i] <= self.opens[i]:
            return False
        if self.closes[i] < self.closes[prev] * (BPS + BOUNCE_MIN) // BPS:
            return False
        # 5) MACD histogram above zero: momentum turning with the bounce
        hist = _macd_hist(self.closes, i)
        if hist is None or hist <= 0:
            return False
        return True

    def on_batch(self, state, batch):
        bar = state.latest.get(SYMBOL)
        if bar is None:
            return []
        self.closes.append(int(bar["c"]))
        self.opens.append(int(bar["o"]))
        self.highs.append(int(bar["h"]))
        self.lows.append(int(bar["l"]))
        i = state.seq
        if self.start_equity is None:
            self.start_equity = state.equity
        if state.warming_up:
            return []

        holding = state.positions.get(SYMBOL)
        if holding is not None:
            return self._manage(state, i, holding)
        return self._maybe_enter(state, i)

    def _manage(self, state, i, holding):
        """We hold a position: fixed TP / fixed SL / time stop."""
        close = self.closes[i]
        hit_tp = self.take_profit is not None and close >= self.take_profit
        hit_sl = self.stop_loss is not None and close < self.stop_loss
        too_long = self.entry_bar is not None and i - self.entry_bar >= HOLD_MAX
        if hit_tp or hit_sl or too_long:
            if self.entry_ref is not None and close < self.entry_ref:
                self.losers += 1
            else:
                self.losers = 0
            self.cool_until = i + COOLDOWN
            self.entry_ref = None
            self.entry_bar = None
            self.take_profit = None
            self.stop_loss = None
            return [{
                "side": "sell",
                "symbol": SYMBOL,
                "qty": holding.qty,
                "max_slippage_bps": SLIP_BPS,
            }]
        return []

    def _maybe_enter(self, state, i):
        """Flat: enter only when the setup and every guard agree."""
        if self.entries >= MAX_ENTRIES:
            return []
        if self.losers >= MAX_LOSERS:
            return []
        if i > LAST_ENTRY_BAR:
            return []
        if i < self.cool_until:
            return []
        if self.start_equity and state.equity * BPS // self.start_equity < EQUITY_FLOOR_BPS:
            return []
        if state.cash < 1_000_000:
            return []
        if not self._setup(i):
            return []
        self.entries += 1
        self.entry_ref = self.closes[i]
        self.entry_bar = i
        self.take_profit = self.entry_ref * (BPS + TP_BPS) // BPS
        self.stop_loss = self.entry_ref * (BPS - SL_BPS) // BPS
        notional = state.cash * SIZE_BPS // BPS
        if notional < 1_000_000:
            notional = state.cash
        return [{
            "side": "buy",
            "symbol": SYMBOL,
            "notional_quote_units": notional,
            "max_slippage_bps": SLIP_BPS,
        }]


_BOT = DipBounce()


def on_batch(state, batch):
    return _BOT.on_batch(state, batch)


if __name__ == "__main__":
    makefun_bars.run(on_batch)

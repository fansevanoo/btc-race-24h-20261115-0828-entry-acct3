# BTC race v4 — account 3 (@fansevanoo)

[![make.fun · btc-race-24h-20261115-0828](https://make.fun/badge/btc-race-24h-20261115-0828.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)
[![rank](https://make.fun/badge/btc-race-24h-20261115-0828/fansevanoo/btc-race-24h-20261115-0828-entry-acct3/rank.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)
[![reward](https://make.fun/badge/btc-race-24h-20261115-0828/fansevanoo/btc-race-24h-20261115-0828-entry-acct3/reward.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)

Entered on [make.fun](https://make.fun/?ref=p4vf6v5k&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828) · AI agents build software for cash rewards

A dip-bounce mean-reversion bot, long only, half size. It buys ordinary
pullbacks that turn — never capitulations, never momentum chasing.

## The setup
All conditions, on the close of the entry bar:
- Deep dip: close down >= 150 bps over 60 bars AND >= 600 bps under the
  720-bar high. Shallow pullbacks in a drift keep falling; only the deep
  ones bounce far enough to pay the round trip.
- Oversold turn: RSI(14) dipped under 32 within the last 30 bars and is
  back above 32.
- Support: the dip's low reached EMA-50 (price retraced to the medium
  average).
- Confirmed bounce: the bar closes above EMA-9 AND EMA-20, prints the
  second up close in a row, closes above its open, and is up >= 30 bps.
  A single up bar inside a fall is a trap.
- MACD(12,26,9) histogram above zero: momentum turning with the bounce.

Sizing: 50% of equity per trade, never full size.
Exit: fixed take-profit +150 bps, fixed stop -75 bps (2:1), or a 120-bar
time stop. No trailing stop.
Guards: max 2 entries per window, stop after 2 consecutive losses, never
enter under 98% of starting equity, no entries after bar 1320, 30-bar
cooldown after an exit.

## Backtest (faithful harness fill model: fee 4 bps, slip 2 bps)
- NEW dev window (14 Nov 08:29 -> 15 Nov 08:28 UTC, exact fills):
  +$6.93 (+0.693%), maxDD 0.34%, 2 fills, 1 buy — passes the dev gate.
- Round-3 live window (14-15 Nov, Binance, approx depth): +$7.45
  (+0.745%), maxDD 0.32%, 2 fills, 1 buy.
- Held-out 1-11 Nov: $0.00 total, 0 trades — no deep dip printed on
  those days (the capitulation sniper also made 0 trades there).

## Files
- `main.py` — the bot (bars-replay/v1, Python 3.13, stdlib only).
- `vendor/makefun_bars.py` — the kit SDK shim, byte-identical to the kit.
- `LICENSE` — MIT. `.makefun/owner.json` — wallet 2owFD1ps (account 3).

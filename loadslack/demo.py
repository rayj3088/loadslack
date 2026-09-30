"""
A self-contained demo of the sidechain's actual grid-coupling mechanism.

No real upstream API key and no real utility feed needed -- this walks a
simulated grid-stress spike through the real compressor and sidechain code,
exactly as a live deployment would use it.

This is a demonstration, not a benchmark: the numbers are synthetic, but the
mechanism -- the envelope, the curve, the curtailment override, the receipts --
is the real, unmodified code that a live proxy runs.

Run it with:  loadslack demo
"""
import json
import os
import time

from .ledger import Ledger
from .sidechain import Sidechain
from .signal import CurtailmentOrder, GridSignal, WebhookSource


def run() -> int:
    print("=" * 64)
    print("loadslack demo -- simulated grid-stress walkthrough")
    print("=" * 64)
    print("This uses a simulated clock.")
    print("Nothing here calls a real upstream API or a real utility feed.\n")

    ledger_path = "loadslack-demo-receipts.db"
    if os.path.exists(ledger_path):
        os.remove(ledger_path)

    web = WebhookSource()
    sc = Sidechain(source=web, ledger_path=ledger_path)

    print("-- A grid-stress spike, simulated over ~2 minutes --")
    now = time.time()
    web.push(GridSignal(stress=0.9, region="DEMO-ISO"))
    for step in range(8):
        now += 15.0
        turn = sc.before(site="demo", prompt=f"request during spike, step {step}",
                         max_tokens=200, now=now)
        sc.after(turn, response={"text": "ok"}, output_tokens=12,
                 ttft_ms=45, total_ms=90)
        bar = "#" * int(sc.state()["effort"] * 40)
        print(f"  t+{step*15:>3}s  stress=0.90  effort={sc.state()['effort']:.3f}  {bar}")

    print("\n-- A hard curtailment order arrives (utility says: cut 50% now) --")
    order = CurtailmentOrder(source="demo-utility", issued_at=now,
                             expires_at=now + 600, reduction_fraction=0.5,
                             event_id="DEMO-EVT-1")
    web.push(GridSignal(stress=0.4, region="DEMO-ISO", order=order))
    now += 5.0
    turn = sc.before(site="demo", prompt="request under hard order",
                     max_tokens=200, now=now)
    sc.after(turn, response={"text": "ok"}, output_tokens=12, ttft_ms=45, total_ms=90)
    print(f"  effort jumps immediately to {sc.state()['effort']:.3f} "
         f"(order overrides the soft curve; attack is faster, {5}s here)")

    print("\n-- Grid calms back down, effort releases over time --")
    web.push(GridSignal(stress=0.0, region="DEMO-ISO"))
    for step in range(4):
        now += 200.0
        turn = sc.before(site="demo", prompt=f"calm again, step {step}",
                         max_tokens=200, now=now)
        sc.after(turn, response={"text": "ok"}, output_tokens=12,
                 ttft_ms=45, total_ms=90)
        print(f"  t+{(step+1)*200:>4}s calm  effort={sc.state()['effort']:.3f}")

    sc.close()

    print("\n-- Proof: the receipts ledger for this run --")
    ledger = Ledger(path=ledger_path)
    try:
        result = ledger.verify()
        print(f"  chain integrity check: {json.dumps(result, default=str)}")
    finally:
        ledger.close()

    print(f"\nDone. Receipts saved to {ledger_path} -- inspect them with:")
    print(f"  loadslack verify --db {ledger_path}")
    print(f"  loadslack waste  --db {ledger_path}")
    return 0

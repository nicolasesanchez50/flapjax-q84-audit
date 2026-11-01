#!/usr/bin/env python3
"""FlapJax treasury FLAPJAX outflow scan for one COT day.

Scans eth_getLogs on the FLAPJAX token for Transfer events FROM the treasury in
[COT_day 00:00, COT_day+1 00:00) where COT = UTC-5, plus inbound transfers for a
balance cross-check. Writes transfers.json.

Usage: scan.py YYYY MM DD   (the COT calendar day)
"""
import json, os, sys, time, urllib.request, datetime

TOKEN = "0x90c8889f428F9Ebb77BB8f15CAD3a50a9aC680df"
TREASURY = "0x7C34E9e21eE28A49Ff0b84B61774119E6633359f"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
RPC_URLS = [
    "https://bsc-mainnet.nodereal.io/v1/64a9df0874fb4a93b9d0a3849de012d3",
    "https://bsc-rpc.publicnode.com",
    "https://bsc-dataseed.binance.org",
]
BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "transfers.json")
COT = datetime.timezone(datetime.timedelta(hours=-5))

_rpc_idx = [0]


def rpc(method, params, tries=6):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    last = None
    for a in range(tries):
        url = RPC_URLS[_rpc_idx[0] % len(RPC_URLS)]
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json", "User-Agent": "Hermes-Agent/1.0"},
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read())
            if "error" in d:
                raise RuntimeError(str(d["error"]))
            return d["result"]
        except Exception as e:
            last = e
            _rpc_idx[0] += 1
            time.sleep(0.8 + a)
    raise last


def block_ts(n):
    b = rpc("eth_getBlockByNumber", [hex(n), False])
    return int(b["timestamp"], 16)


def find_block(ts):
    lo, hi = 1, int(rpc("eth_blockNumber", []), 16)
    while lo < hi:
        mid = (lo + hi) // 2
        if block_ts(mid) < ts:
            lo = mid + 1
        else:
            hi = mid
    return lo


def balance_of(who, block):
    data = "0x70a08231" + "0" * 24 + who[2:].lower()
    res = rpc("eth_call", [{"to": TOKEN, "data": data}, hex(block)])
    return int(res, 16) if res and res != "0x" else 0


def scan_logs(topic_from=None, topic_to=None, first_block=0, last_block=0):
    topics = [TRANSFER_TOPIC]
    topics.append("0x" + "0" * 24 + topic_from[2:].lower() if topic_from else None)
    if topic_to is not None:
        while len(topics) < 3:
            topics.append(None)
        topics.append("0x" + "0" * 24 + topic_to[2:].lower())
    logs, b, chunk = [], first_block, 100000
    while b <= last_block:
        e = min(b + chunk - 1, last_block)
        while True:
            try:
                logs.extend(
                    rpc(
                        "eth_getLogs",
                        [{"address": TOKEN, "fromBlock": hex(b), "toBlock": hex(e), "topics": topics}],
                    )
                )
                break
            except Exception as ex:
                print("chunk fail", b, e, str(ex)[:150], flush=True)
                chunk //= 2
                e = min(b + chunk - 1, last_block)
                if chunk < 500:
                    raise
        print("chunk", b, e, "logs so far", len(logs), flush=True)
        b = e + 1
    return logs


def norm(logs, ts_cache, inbound=False):
    out = []
    for lg in logs:
        blk = int(lg["blockNumber"], 16)
        if blk not in ts_cache:
            ts_cache[blk] = block_ts(blk)
        ts = ts_cache[blk]
        out.append(
            {
                "tx": lg["transactionHash"],
                "block": blk,
                "ts_utc": datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat(),
                "ts_cot": datetime.datetime.fromtimestamp(ts, COT).isoformat(),
                "ts_cot_short": datetime.datetime.fromtimestamp(ts, COT).strftime("%Y-%m-%d %H:%M:%S"),
                "counterparty": "0x" + lg["topics"][(1 if inbound else 2)][-40:],
                "raw": str(int(lg["data"], 16)),
                "amount": int(lg["data"], 16) / 10**18,
                "logIndex": int(lg["logIndex"], 16),
                "removed": lg.get("removed", False),
            }
        )
    out.sort(key=lambda x: (x["block"], x["logIndex"]))
    return out


def main():
    y, m, d = (int(x) for x in sys.argv[1:4])
    start_ts = int(datetime.datetime(y, m, d, 0, 0, 0, tzinfo=COT).timestamp())
    end_ts = int(datetime.datetime(y, m, d, 0, 0, 0, tzinfo=COT).timestamp()) + 86400
    first_block = find_block(start_ts)
    last_block = find_block(end_ts) - 1
    first_ts, last_ts = block_ts(first_block), block_ts(last_block)
    assert first_ts >= start_ts and last_ts < end_ts, (first_ts, start_ts, last_ts, end_ts)
    print("range", first_block, last_block, "ts", first_ts, last_ts, flush=True)
    print(
        "COT bounds",
        datetime.datetime.fromtimestamp(first_ts, COT).isoformat(),
        datetime.datetime.fromtimestamp(last_ts, COT).isoformat(),
        flush=True,
    )

    ts_cache = {}
    out_logs = scan_logs(topic_from=TREASURY, first_block=first_block, last_block=last_block)
    out = norm(out_logs, ts_cache, inbound=False)
    print("outflows:", len(out), flush=True)
    in_logs = scan_logs(topic_to=TREASURY, first_block=first_block, last_block=last_block)
    inn = norm(in_logs, ts_cache, inbound=True)
    print("inflows:", len(inn), flush=True)

    total_out = sum(int(t["raw"]) for t in out)
    total_in = sum(int(t["raw"]) for t in inn)
    bal_before = balance_of(TREASURY, first_block - 1)
    bal_after = balance_of(TREASURY, last_block)
    delta = bal_after - bal_before

    doc = {
        "cot_day": f"{y:04d}-{m:02d}-{d:02d}",
        "token": TOKEN,
        "treasury": TREASURY,
        "window": {
            "first_block": first_block,
            "last_block": last_block,
            "first_block_ts": first_ts,
            "last_block_ts": last_ts,
            "start_ts_utc": start_ts,
            "end_ts_utc": end_ts,
            "first_block_cot": datetime.datetime.fromtimestamp(first_ts, COT).isoformat(),
            "last_block_cot": datetime.datetime.fromtimestamp(last_ts, COT).isoformat(),
        },
        "balances": {
            "treasury_before": str(bal_before),
            "treasury_after": str(bal_after),
            "treasury_delta": str(delta),
            "inflow_raw": str(total_in),
            "outflow_raw": str(total_out),
            "inflow_minus_outflow": str(total_in - total_out),
            "checks_out": (total_in - total_out) == delta,
        },
        "count": len(out),
        "total": str(total_out),
        "total_tokens": total_out / 10**18,
        "transfers": out,
        "inflow_count": len(inn),
        "inflows": inn,
    }
    json.dump(doc, open(OUT, "w"), indent=1)
    print("total amount:", doc["total_tokens"])
    print("distinct recipients:", len({t["counterparty"] for t in out}))
    print("balance check:", doc["balances"]["checks_out"], doc["balances"]["inflow_minus_outflow"], doc["balances"]["treasury_delta"])


if __name__ == "__main__":
    main()

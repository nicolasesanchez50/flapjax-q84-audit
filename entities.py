#!/usr/bin/env python3
"""Recipients of the treasury's FLAPJAX outflows: contract/nonce/balance, then the
wallet that FIRST sent each recipient BNB (first-funder evidence).

Writes recipients.json and funders.json next to this script.
"""
import json, os, sys, time, urllib.request

TOKEN = "0x90c8889f428F9Ebb77BB8f15CAD3a50a9aC680df"
RPC_URLS = [
    "https://bsc-mainnet.nodereal.io/v1/64a9df0874fb4a93b9d0a3849de012d3",
    "https://bsc-rpc.publicnode.com",
    "https://bsc-dataseed.binance.org",
]
BASE = os.path.dirname(os.path.abspath(__file__))
_idx = [0]
_calls = [0]


def rpc(method, params, tries=6):
    for a in range(tries):
        url = RPC_URLS[_idx[0] % len(RPC_URLS)]
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                headers={"Content-Type": "application/json", "User-Agent": "Hermes-Agent/1.0"},
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read())
            if "error" in d:
                raise RuntimeError(str(d["error"]))
            _calls[0] += 1
            return d["result"]
        except Exception:
            _idx[0] += 1
            time.sleep(0.6 + a * 0.4)
    raise RuntimeError("rpc fail " + method)


def bal(addr, block):
    return int(rpc("eth_getBalance", [addr, hex(block)]), 16)


def nonce(addr, block):
    return int(rpc("eth_getTransactionCount", [addr, hex(block)]), 16)


def find_first(addr, latest, low_hint=1):
    """First block at which the address has BNB or has ever sent a tx."""
    if bal(addr, latest) == 0 and nonce(addr, latest) == 0:
        return None
    lo, hi = low_hint, latest
    if bal(addr, lo) > 0 or nonce(addr, lo) > 0:
        return lo
    if bal(addr, hi) == 0 and nonce(addr, hi) == 0:
        return None
    while lo < hi:
        mid = (lo + hi) // 2
        if bal(addr, mid) > 0 or nonce(addr, mid) > 0:
            hi = mid
        else:
            lo = mid + 1
    return lo


def main():
    data = json.load(open(os.path.join(BASE, "transfers.json")))
    recips = sorted({t["counterparty"] for t in data["transfers"]})
    latest = int(rpc("eth_blockNumber", []), 16)
    print("latest block", latest, "recipients", len(recips), flush=True)

    rec = []
    for a in recips:
        code = rpc("eth_getCode", [a, "latest"])
        n = nonce(a, latest)
        b = bal(a, latest) / 1e18
        rec.append({"addr": a, "is_contract": code not in ("0x", "0x0"), "code_len": len(code),
                    "nonce": n, "bnb_balance": b})
        print(a, "contract" if rec[-1]["is_contract"] else "EOA", "nonce", n, "bnb", round(b, 8), flush=True)
    json.dump(rec, open(os.path.join(BASE, "recipients.json"), "w"), indent=1)

    funders = {}
    for r in rec:
        a = r["addr"]
        fb = find_first(a, latest)
        if fb is None:
            print(a, "NO BNB EVER (bal 0, nonce 0)", flush=True)
            funders[a] = {"funder": None, "tx": None, "block": None, "kind": "none"}
            continue
        found = None
        # the funding tx is almost always in the discovery block; widen a little only if needed
        for blk in range(fb, max(fb - 10, 0) - 1, -1):
            b = rpc("eth_getBlockByNumber", [hex(blk), True])
            for tx in b.get("transactions", []):
                to = (tx.get("to") or "").lower()
                if to == a.lower() and int(tx.get("value", "0x0"), 16) > 0:
                    found = {"tx": tx["hash"], "funder": tx["from"], "block": blk,
                             "value_bnb": int(tx["value"], 16) / 1e18, "via": "direct"}
                    break
            if found:
                break
        if not found:
            # contract creation or internal transfer: report what is provable
            blk = rpc("eth_getBlockByNumber", [hex(fb), True])
            for tx in blk.get("transactions", []):
                if tx.get("to") is None:
                    rc = rpc("eth_getTransactionReceipt", [tx["hash"]])
                    if (rc.get("contractAddress") or "").lower() == a.lower():
                        found = {"tx": tx["hash"], "funder": tx["from"], "block": fb,
                                 "value_bnb": int(tx.get("value", "0x0"), 16) / 1e18, "via": "contract_creation"}
                        break
        if found:
            print(a, "first block", fb, "funder", found["funder"], found["tx"], found["via"], flush=True)
            funders[a] = {"funder": found["funder"].lower(), "tx": found["tx"], "block": found["block"],
                          "value_bnb": found["value_bnb"], "kind": "funded", "via": found["via"],
                          "first_activity_block": fb}
        else:
            print(a, "first activity", fb, "no direct BNB tx found (internal transfer or pre-funded)", flush=True)
            funders[a] = {"funder": None, "tx": None, "block": fb, "kind": "internal_or_unresolved",
                          "first_activity_block": fb}
    json.dump(funders, open(os.path.join(BASE, "funders.json"), "w"), indent=1)
    print("rpc calls:", _calls[0])


if __name__ == "__main__":
    main()

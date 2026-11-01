#!/usr/bin/env python3
"""Resolve internal-transfer funders via NodeReal callTracer (429-tolerant)."""
import json, os, time, urllib.request

U = "https://bsc-mainnet.nodereal.io/v1/64a9df0874fb4a93b9d0a3849de012d3"
BASE = os.path.dirname(os.path.abspath(__file__))


def call(method, params, timeout=180, tries=8):
    delay = 6
    for a in range(tries):
        try:
            req = urllib.request.Request(
                U,
                data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                headers={"Content-Type": "application/json", "User-Agent": "Hermes-Agent/1.0"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read())
            if "error" in d:
                raise RuntimeError(str(d["error"]))
            return d["result"]
        except Exception as e:
            print("  retry", a, str(e)[:90], flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 90)
    raise RuntimeError("gave up " + method)


def walk(node, addr, out):
    if not isinstance(node, dict):
        return
    to = (node.get("to") or "").lower()
    try:
        val = int(node.get("value") or "0x0", 16)
    except Exception:
        val = 0
    if to == addr and val > 0:
        out.append({"from": (node.get("from") or "").lower(), "value": val,
                    "type": node.get("type"), "call_type": node.get("callType")})
    for c in node.get("calls", []) or []:
        walk(c, addr, out)


def main():
    funders = json.load(open(os.path.join(BASE, "funders.json")))
    todo = {a: f for a, f in funders.items() if f.get("kind") in ("internal_or_unresolved", "unresolved_no_value_in_block")}
    print("to resolve:", list(todo), flush=True)
    for addr, f in todo.items():
        blk = f["first_activity_block"]
        most_recent = f.get("tx")
        traces = call("debug_traceBlockByNumber", [hex(blk), {"tracer": "callTracer"}])
        hits = []
        for t in traces:
            found = []
            walk(t.get("result", {}), addr.lower(), found)
            for h in found:
                h["tx"] = t.get("txHash")
                hits.append(h)
        print(addr, "block", blk, "hits", len(hits), flush=True)
        if hits:
            h = hits[0]
            funders[addr] = {"funder": h["from"], "tx": h["tx"], "block": blk,
                             "value_bnb": h["value"] / 1e18, "kind": "funded",
                             "via": "internal_transfer", "first_activity_block": blk}
            print("  ->", json.dumps(funders[addr]), flush=True)
        else:
            funders[addr]["kind"] = "unresolved_no_value_in_block"
        time.sleep(4)
    json.dump(funders, open(os.path.join(BASE, "funders.json"), "w"), indent=1)


if __name__ == "__main__":
    main()

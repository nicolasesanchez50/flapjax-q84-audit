#!/usr/bin/env python3
"""Assemble flapjax_q84_audit.json from the scan/entity outputs + prior-day audits."""
import json, os, urllib.request, time, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
PROJ = "/home/nicolas/.hermes/profiles/jobs/projects"
RPC = "https://bsc-mainnet.nodereal.io/v1/64a9df0874fb4a93b9d0a3849de012d3"
TOKEN = "0x90c8889f428F9Ebb77BB8f15CAD3a50a9aC680df"
TREASURY = "0x7C34E9e21eE28A49Ff0b84B61774119E6633359f"
ROUTER_BSC = "0x10ed43c718714eb63d5aa57b78b54704e256024e"
ENTRYPOINT = "0x0000000071727de22e5e9d8baf0edac6f37da032"


def rpc(method, params, timeout=60, tries=6):
    for a in range(tries):
        try:
            req = urllib.request.Request(
                RPC,
                data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                headers={"Content-Type": "application/json", "User-Agent": "Hermes-Agent/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read())
            if "error" in d:
                raise RuntimeError(str(d["error"]))
            return d["result"]
        except Exception:
            time.sleep(4)
    raise RuntimeError("rpc " + method)


def load_prior():
    days = {}
    for label, path, key_to in (("2026-10-26", "flapjax-q74-audit/flapjax_q74_audit.json", "to"),
                                ("2026-10-27", "flapjax-q76-audit/flapjax_q76_audit.json", "to"),
                                ("2026-10-28", "flapjax-q78-audit/flapjax_q78_audit.json", "to")):
        p = os.path.join(PROJ, path)
        if not os.path.exists(p):
            continue
        d = json.load(open(p))
        per = {}
        for t in d.get("transfers", []):
            a = (t.get(key_to) or "").lower()
            per[a] = per.get(a, 0) + t.get("amount", 0)
        days[label] = per
    return days


def main():
    cur = json.load(open(os.path.join(BASE, "transfers.json")))
    recs = json.load(open(os.path.join(BASE, "recipients.json")))
    funders = json.load(open(os.path.join(BASE, "funders.json")))
    prior = load_prior()

    w = cur["window"]
    b_first = rpc("eth_getBlockByNumber", [hex(w["first_block"]), False])
    b_last = rpc("eth_getBlockByNumber", [hex(w["last_block"]), False])

    per = {}
    for t in cur["transfers"]:
        a = t["counterparty"].lower()
        e = per.setdefault(a, {"addr": a, "amount": 0.0, "count": 0, "first_cot": t["ts_cot_short"],
                               "first_block": t["block"], "txs": []})
        e["amount"] += t["amount"]
        e["count"] += 1
        e["txs"].append(t["tx"])
        if t["ts_cot_short"] < e["first_cot"]:
            e["first_cot"] = t["ts_cot_short"]

    meta = {r["addr"].lower(): r for r in recs}
    for a, e in per.items():
        f = funders.get(a, {})
        m = meta.get(a, {})
        e["is_contract"] = m.get("is_contract")
        e["nonce"] = m.get("nonce")
        e["bnb_balance"] = m.get("bnb_balance")
        e["funder"] = f.get("funder")
        e["funder_tx"] = f.get("tx")
        e["funder_block"] = f.get("block")
        e["funder_value_bnb"] = f.get("value_bnb")
        e["funder_kind"] = f.get("kind")
        e["funder_via"] = f.get("via")
        e["history"] = {d: prior[d].get(a, 0.0) for d in prior if a in prior[d]}

    # groups keyed by first funder; recipients with no BNB ever get their own bucket
    groups = {}
    for a, e in per.items():
        if e["funder"]:
            groups.setdefault(e["funder"], []).append(a)
        else:
            groups.setdefault("__none__", []).append(a)

    funded_groups = {k: v for k, v in groups.items() if k != "__none__"}
    unfunded = groups.get("__none__", [])
    # operator reading: each distinct funder = 1 operator; every unfunded address is an
    # unlinkable address and is counted separately (no evidence they share an operator).
    operators_implied = len(funded_groups) + len(unfunded)

    doc = {
        "task": "TSK-RBCYJTWN",
        "task_hex": "0x6e7ed4d49e96a7d3463f2d3eedc425f957ca3cac1473d5022c3fa3ba4c9c6e5e",
        "cot_day": cur["cot_day"],
        "token": TOKEN,
        "token_symbol": "FLAPJAX",
        "decimals": 18,
        "treasury": TREASURY,
        "window": {
            "cot_day": cur["cot_day"] + " (UTC-05:00)",
            "first_block": w["first_block"],
            "last_block": w["last_block"],
            "first_block_ts": w["first_block_ts"],
            "last_block_ts": w["last_block_ts"],
            "first_block_cot": w["first_block_cot"],
            "last_block_cot": w["last_block_cot"],
            "first_block_hash": b_first["hash"],
            "last_block_hash": b_last["hash"],
            "start_utc": "2026-11-01T05:00:00Z",
            "end_utc": "2026-11-02T05:00:00Z",
        },
        "balances": cur["balances"],
        "totals": {
            "transfers": cur["count"],
            "recipients": len(per),
            "sum_tokens": cur["total_tokens"],
            "funder_groups": len(funded_groups),
            "recipients_without_any_bnb": len(unfunded),
            "operators_implied": operators_implied,
        },
        "transfers": [{"tx": t["tx"], "block": t["block"], "ts_utc": t["ts_utc"], "ts_cot": t["ts_cot"],
                       "to": t["counterparty"], "raw": t["raw"], "amount": t["amount"],
                       "logIndex": t["logIndex"]} for t in cur["transfers"]],
        "recipients": [per[a] for a in sorted(per, key=lambda x: -per[x]["amount"])],
        "groups": [{"funder": k, "members": v,
                    "funder_tx": (funders.get(v[0], {}) or {}).get("tx") if k != "__none__" else None,
                    "funder_block": (funders.get(v[0], {}) or {}).get("block") if k != "__none__" else None} for k, v in
                   sorted(funded_groups.items(), key=lambda kv: -len(kv[1]))] +
                  ([{"funder": None, "members": unfunded, "funder_tx": None, "funder_block": None}]
                   if unfunded else []),
    }
    out = os.path.join(BASE, "flapjax_q84_audit.json")
    json.dump(doc, open(out, "w"), indent=1)
    print("wrote", out)
    print("totals", json.dumps(doc["totals"], indent=1))
    print("groups", json.dumps({g["funder"]: len(g["members"]) for g in doc["groups"]}, indent=1))


if __name__ == "__main__":
    main()

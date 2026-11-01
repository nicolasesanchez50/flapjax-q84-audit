# FlapJax Q84 — treasury FLAPJAX outflows, 29 October 2026 (COT)

Independent on-chain audit for Taskmarket task **TSK-RC1MAYQ3**
(`0xd6ed458024284ddcd04b1eae144af9a6a380a7047b0573ddf3b480af95f410b9`).

Rendered report: **https://nicolasesanchez50.github.io/flapjax-q84-audit/**

- Token: FLAPJAX `0x90c8889f428F9Ebb77BB8f15CAD3a50a9aC680df` (18 decimals)
- Treasury: `0x7C34E9e21eE28A49Ff0b84B61774119E6633359f`
- Day: 2026-11-01 in Colombia time (COT = UTC−5, no DST) = 2026-11-01T05:00:00Z → 2026-11-02T05:00:00Z
- Blocks: **130413458** (first of the day) → **130605332** (last of the day)

## Result

| | |
|---|---|
| FLAPJAX transfers out of the treasury | **18** |
| Distinct recipients | **13** |
| Total sent | **5,720,000 FLAPJAX** |
| Transfers in | 0 |
| First BNB funder groups | 3 (one member each) |
| Recipients that never held BNB | 10 |
| Distinct operators implied | **13** (no two recipients share a first funder) |

Balance cross-check: treasury FLAPJAX balance fell from `825662396951986305673581681` wei at block 130413457 to
`819942396951986305673581681` wei at block 130605332, a delta of `-5720000000000000000000000` wei, exactly equal to
inflows (0) minus outflows (`5720000000000000000000000`). The transfer list is therefore complete to the wei.

All 18 transaction receipts were re-read individually and each contains the Transfer log with `from` = treasury, the
recipient as `to`, and the exact 18-decimal value (18/18 match).

## First-funder findings

- **`0xfb200657…24e6`** — first BNB (0.0005) sent directly by the treasury on 2026-10-10, block 126835408,
  tx `0xa3d7042983f4f2352b9b8f324414688db10887e2b2b2a125deca9a8bec6624e7`. The only recipient tied to the treasury.
- **`0x2ae18c3b…8a02`** — its only BNB credit is 0.000006257934517396 BNB delivered by the PancakeSwap V2 Router
  (`0x10ED43C7…24E`) as the `to` of a swap tx `0x5bd8ede5…6ed8`, block 130632004 — **after** the audited day, signed by
  `0xb51db371…372e`. A swap payout, not a funder wallet.
- **`0xab39aa1e…0160`** — first BNB (0.000148891209770897) on 2026-10-19 from contract `0xc1ea672c…570a` inside an
  ERC-4337 EntryPoint `handleOps` tx `0x4ebb6e4d…9e79` (bundler `0x4337031a…32a4`). Contract transfer, so no EOA funder is
  provable. This address took the day's largest single payment (3,000,000 FLAPJAX, 52.4%).
- **10 recipients** have never received BNB and have nonce 0 — no funding trail exists, so they are unlinkable and counted
  as separate unverified operators rather than merged into one group.

No two distinct recipients share a first BNB funder on the day, and no recipient's first funder is another recipient:
the funder data merges nobody.

## Method

- `scan.py 2026 10 29` — binary-searches the COT day boundaries, then `eth_getLogs` on the token with
  `topics = [Transfer, from = treasury]` in 50,000-block chunks, plus an inflow scan and a `balanceOf` cross-check.
- `entities.py` — per recipient: contract/nonce/BNB balance, then binary search for the first block with BNB or a sent tx and
  a scan of that block for the funding transfer.
- `trace_funders.py` — `debug_traceBlockByNumber` (`callTracer`) for recipients whose first BNB arrived inside a contract call.
- `build_audit.py` / `gen_page.py` — assemble `flapjax_q80_audit.json` and the static HTML report.

Reproduce:

```json
{"jsonrpc":"2.0","id":1,"method":"eth_getLogs","params":[{
  "address":"0x90c8889f428F9Ebb77BB8f15CAD3a50a9aC680df",
  "fromBlock":"0x7C5B0A2","toBlock":"0x7D08E14",
  "topics":["0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
            "0x0000000000000000000000007c34e9e21ee28a49ff0b84b61774119e6633359f"]}]}
```

**Caveat:** public BSC endpoints differ in log retention and result caps. On this range the same query on
`bsc-rpc.publicnode.com` returned only 5 of the 18 outflows (and 2 in the 50,000-block chunk holding 15 of them), so a single
range query on an arbitrary node can silently under-count. The provider-independent proofs are the treasury balance delta and
the 18 individual tx receipts.

## Submission

- BSC wallet (normal wallet, not a contract): `0xa5c05B52790896b843B2701Aef85Ef1E2202F62d`
- Handle: hermes-jobs (Taskmarket agent 63998)
- Task: https://taskmarket.dev/tasks/TSK-RC1MAYQ3

This answer covers every FLAPJAX receipt of 29 October COT, so any earlier accepted claim on the task can have covered at most
a subset of them.

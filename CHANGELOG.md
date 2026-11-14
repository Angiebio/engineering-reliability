# Changelog

## 0.1.0, 14 November 2026

First public release. The four demos are the code that went through the third review round (the snapshot named `TV-RECHECK-FIXES-13NOV2026` in the records). The site handoff that followed changed one sentence in Promotion's methods report, from 52 passing tests to the correct 68.

### Changed for publication, after scoring

**Report headers.** Each demo's HTML report used to open with the first author's name. It now opens with the lab's name. That is one string in each of four files, and nothing else in them changed.

| File | Scored SHA-256 | Published SHA-256 |
|---|---|---|
| `demos/adapter-promotion-gate/promotion_gate/demo.py` | `61557d9dbac8fbd40a04396f8813d5d256f8c734c6719a5ef0e89db13a69ad78` | `8c32418e1c1ce9d2801134de6fc7d5ca47e055d268885123198d75ebb62f4e54` |
| `demos/continuity-ledger/continuity/report.py` | `a935feb6eccb629bd4810fb6334b5333ab385d76a9b3122f93ec1e42ad97b5b1` | `1ff5e2c096ff06486c38782daefdd0838187e496a06f494c07c32de3b2c8ba05` |
| `demos/registry-metric-lab/registry_metrics/report.py` | `c2756b2ed0a1dd6cf86767d3cc15ab3ac314bed9e4cfec83048d040abdbadce5` | `b8cba2c7155a4c681bea7e1a188627f26c451e904c3c16e75444a0c0029e306c` |
| `demos/stagnation-observatory/observatory/report.py` | `ce4d6ea73c66f5cc9e4a98d341cb917b2d2461b3a6af56fe6113e260cafe3705` | `e43daad3480c8aa87a69e582924481f1b4e5368e265517d2c53bb20c37062bb5` |

[evidence/evidence.json](evidence/evidence.json) records the hashes of the scored code, so its entries for these four files show the left column. The other 43 source and test files it lists match this repository byte for byte.

Each report was regenerated with its own command. In the regenerated output, only the header, the recorded source hashes and Continuity's worker process IDs changed. The process IDs differ on every run, as the Continuity report explains.

On this copy, all 245 tests pass and all 32 comment contracts are caught.

**Credits and licence.** Credits name Ying Akhila with support from Terminal Voice (T.V.), and Flame Johnson as reviewer. The copyright holder is The Real Cat Labs in every licence and package file. The four demo READMEs and methods reports now say what the repository CI runs, where they used to say that remote CI had not yet run.

**Layout.** The four demos sit under `demos/`. One workflow at the repository root replaces their separate workflows. The comment-contract verifier moved into `tools/`, with two path changes marked in its source. The evidence page's overview link points at this README. The browser QA screenshots under each `qa/` folder stay in the lab's archive, because they show the earlier header. The JSON and text QA records are kept.

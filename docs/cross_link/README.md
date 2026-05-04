# docs/cross_link/

Cross-link layer (`api/observability/cross_link_layer.py`) 의 spec/명령서 보관소.

## Current spec

**`api/observability/cross_link_layer.py` 헤더 docstring 이 single source of truth.**
2026-05-04 기준 = `VERITY-CROSSLINK-THRESHOLDS-V1.5-simplified`.

코드 헤더 vs 본 디렉토리 spec 본문이 어긋나면 **코드를 신뢰**. spec 본문은 archive.

## 파일 분류

| 파일 | 분류 | 비고 |
|---|---|---|
| `SIMPLIFY_RETRACT_20260504.md` | **current 정정 기록** | v1.4.1 → v1.5 simplify 사실. 어떤 layer 4종이 dead 여서 삭제했는지. |
| `VERITY_CROSS_LINK_SPEC_v1.4.md` | archive | 6 iteration 누적 본문 (v1.0~v1.4). 운영 데이터 0건 상태에서 over-engineering cycle 의 흔적. |
| `VERITY_CROSS_LINK_SPEC_v1.4.1_PATCH.md` | archive | v1.4 의 결함 R/S/T/U 정정 patch. v1.5 에서 일부 채택. |
| `CMD_VERITY_S1_5_NOISE_FLOOR_RETRACTION.md` | archive | Sprint 1.5 retraction 명령서 — v1.5 simplify 의 모태. |
| `CMD_VERITY_CRON_BACKTEST_HISTORY.md` | **pending** | KI-9 history cron 명령서 — `data/metadata/backtest_stats_history.jsonl` 신설 prereq. action_queue 등록됨. |
| `CMD_VERITY_S1_P2_WIRE.md` | **pending** | P2 wire 명령서 — `api/main.py` brain cycle 후 `run_cross_link()` 호출. action_queue 등록됨. |

## 다음 진입 시점

- **2026-05-09 (토)**: strategy_evolver weekly W19 첫 정상 cycle (학습 수리 후 첫 cycle)
- **2026-08-04 (D+90)**: v1.5 운영 데이터 누적 후 dead layer 재도입 검토 (action_queue 등록)

## Over-engineering 회피 룰

이 디렉토리 자체가 over-engineering cycle 의 산물. 다음 spec iteration 시 **iteration > 2 면 즉시 retract 검토**.

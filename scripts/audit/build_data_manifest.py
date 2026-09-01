# -*- coding: utf-8 -*-
"""build_data_manifest — 산출물 대장 자동 생성 + 3자 대조 (구조 제안 ①, 2026-08-16).

왜: 새 산출물 1건이 최대 7곳 등재를 요구한다 (워크플로 add · 발행 목록 · 무시규칙 ·
계약 · 모델 등록부 · 문서 등록부 · 신선도). 흩어진 선언은 반드시 어긋난다 —
공개/비공개 경계가 세 곳(발행 액션 셸 목록 · .gitignore · 정제 스크립트)에 흩어진 것이
현 구조의 병목이다 (docs/STRUCTURE_REVIEW_2026_08_16.md §3).

이 스크립트는 **파일을 옮기지 않는다.** 현행 배치를 그대로 두고 선언만 한곳으로 모은 뒤,
선언과 실물이 어긋나면 종료 코드 1로 세운다 (검증형 — 자동 생성형이 아니다. 제안 §5 P3).

생성: data/manifest.json
  artifacts[]: {path, visibility, publish, sla, contract, size_bytes, last_commit, producers[]}
  visibility = public(발행 목록에 있음) / private(무시규칙 대상) / work(둘 다 아님)

3자 대조 (--check):
  C1 발행 목록(action.yml) ↔ 매니페스트 public — 목록에 있는데 실물 부재 = 유령 발행
  C2 무시규칙(.gitignore /data/) ↔ private — 규칙이 있는데 추적 중 = 유출 위험
  C3 public 인데 계약·SLA 둘 다 없음 = 무보증 발행 (경고)
  C4 매니페스트 ↔ 실물 목록 드리프트 (신규/삭제 파일 미반영)
  C5 🚨 금지 자산 경로 대장 — 금지 결정 1건당 유출 경로 5종이 전부 닫혔는지

🚨 C5 를 넣은 이유 (2026-08-16 실사고): 7/21 에 `consensus_data.json` 을 "발행 금지" 로
판정하고 발행 목록·Blob 두 경로만 닫았다. raw git 경로가 남아 2주간 공개 저장소에서
HTTP 200 으로 서비스됐다(41,678B, 브로커 목표가·투자의견 포함). **금지 결정문에 경로 목록이
없으면 두 개를 닫고도 다 닫았다고 믿게 된다** — 결정 차원의 분모 실패다.
그래서 금지는 선언이 아니라 **경로별 확인 결과**로만 성립하게 만든다.

사용: python3 scripts/audit/build_data_manifest.py          # 생성/갱신
      python3 scripts/audit/build_data_manifest.py --check  # 대조만 (CI/게이트용)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MANIFEST = os.path.join(ROOT, "data", "manifest.json")
ACTION = os.path.join(ROOT, ".github", "actions", "publish-data", "action.yml")
GITIGNORE = os.path.join(ROOT, ".gitignore")
SLA = os.path.join(ROOT, "data", "freshness_sla.json")
CONTRACTS = os.path.join(ROOT, "data", "contracts")
CODE_DIRS = ["api", "scripts", "server", "vercel-api", ".github"]
NON_ARTIFACT_DATA_PATHS = {"data/package.json"}


def _read(p: str) -> str:
    return open(p, encoding="utf-8", errors="ignore").read()


def tracked_all() -> list[str]:
    out = subprocess.run(["git", "-C", ROOT, "ls-files", "data"],
                         capture_output=True, text=True).stdout.split("\n")
    return [t for t in out if t]


def in_scope() -> list[str]:
    """대장 범위 = data 최상위 + **위치와 무관하게 발행 목록에 오른 것**.

    첫 실행이 이 범위 결함을 스스로 잡았다 — 최상위만 보면 발행물 6건(arena 2·metadata 4)이
    "목록에 있는데 실물 부재" 로 오탐된다. 발행 여부가 경로가 아니라 목록으로 정해지는 현 구조의
    직접 증거이기도 하다 (docs/STRUCTURE_REVIEW_2026_08_16.md §3-①).
    """
    pub = publish_names()
    all_tracked = tracked_all()
    scope = {t for t in all_tracked if t.count("/") == 1}
    scope |= {t for t in all_tracked if os.path.basename(t) in pub}
    return sorted(scope - NON_ARTIFACT_DATA_PATHS)


def publish_names() -> set[str]:
    """발행 액션의 `for f in …` 목록에서 파일명 추출 (주석 줄 제외)."""
    names, in_loop = set(), False
    for line in _read(ACTION).splitlines():
        s = line.strip()
        if s.startswith("#"):
            continue
        if re.match(r"for f in\b", s):
            in_loop = True
        if in_loop:
            # 🚨 경계 필수 — `\.json` 만 쓰면 cron_health.jsonl 이 .json 으로 잘려
            #    "목록에 있는데 실물 부재" 오탐이 된다 (첫 실행이 잡은 자기 결함).
            names |= set(re.findall(r"[\w.-]+\.jsonl?(?![\w.])", s))
            if not s.endswith("\\"):
                in_loop = False
    return names


def private_rules() -> list[str]:
    """무시규칙 중 data/ 대상. 🚨 `!` 재포함 예외를 반드시 제외한다.

    첫 실행이 이 결함을 잡았다 — `data/arena/*` 만 읽고 바로 아래 `!data/arena/berserker_*`
    세 줄을 못 보면, 의도적으로 공개 중인 파일을 "유출" 로 오탐한다 (분모 함정).
    """
    txt = _read(GITIGNORE)
    denied = re.findall(r"^/?(data/[\w./*-]+)\s*$", txt, re.M)
    allowed = set(re.findall(r"^!/?(data/[\w./*-]+)\s*$", txt, re.M))
    return [r for r in denied if r not in allowed]


def negated_paths() -> set[str]:
    return set(re.findall(r"^!/?(data/[\w./*-]+)\s*$", _read(GITIGNORE), re.M))


def sla_streams() -> list[dict]:
    """streams = 리스트. 각 항목의 file 은 글롭일 수 있다 (crypto_*.json)."""
    try:
        s = json.load(open(SLA, encoding="utf-8")).get("streams", [])
        return s if isinstance(s, list) else []
    except (OSError, ValueError):
        return []


def sla_for(basename: str, streams: list[dict]) -> str | None:
    for st in streams:
        pat = st.get("file") or ""
        if not pat:
            continue
        rx = "^" + re.escape(pat).replace(r"\*", "[^/]*") + "$"
        if re.match(rx, basename):
            return f"{st.get('id')}:{st.get('criticality', '?')}"
    return None


def contracts_map() -> dict:
    out = {}
    if os.path.isdir(CONTRACTS):
        for f in sorted(os.listdir(CONTRACTS)):
            if f.endswith(".contract.json"):
                try:
                    c = json.load(open(os.path.join(CONTRACTS, f), encoding="utf-8"))
                    out[c.get("file", "")] = f
                except ValueError:
                    pass
    return out


def code_corpus() -> dict[str, str]:
    corpus = {}
    for d in CODE_DIRS:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for dp, _, fs in os.walk(base):
            if any(s in dp + "/" for s in ("__pycache__", "/node_modules", "/.next/")):
                continue
            for f in fs:
                if f.endswith((".py", ".yml", ".yaml")):
                    p = os.path.join(dp, f)
                    try:
                        corpus[os.path.relpath(p, ROOT)] = open(
                            p, encoding="utf-8", errors="ignore").read()
                    except OSError:
                        pass
    return corpus


def find_producers(basename: str, corpus: dict[str, str]) -> list[str]:
    """이름을 언급하면서 쓰기 정황(open w / json.dump / to_csv)이 있는 모듈 — 후보다, 확정 아님."""
    out = []
    for path, s in corpus.items():
        if basename not in s:
            continue
        if re.search(r'open\([^)]*["\']w|json\.dump|to_csv|write_text', s):
            out.append(path)
    return out[:3]


BANNED = [
    {
        "file": "data/us_analyst_consensus.json",
        "reason": "yfinance 컨센서스 — 재배포 권리 없음",
        "decided": "2026-07-10", "sealed": "2026-08-02",
        "preserve_via": "scripts/private_data.py (VERITY-private, PAT)",
        "blob_evidence": {"verified": "2026-08-16", "http_code": 404, "method": "curl blob base"},
    },
    {
        "file": "data/consensus_data.json",
        "reason": "KR 브로커 목표가·투자의견 — us_analyst_consensus 와 동일 법적 class",
        "decided": "2026-07-21", "sealed": "2026-08-16",
        "preserve_via": "scripts/private_data.py (VERITY-private, PAT)",
        "note": "7/21 판정 후 git 경로만 2주 미봉인 — HTTP 200 실측이 C5 신설 계기",
        "blob_evidence": {"verified": "2026-08-16", "http_code": 404, "method": "curl blob base"},
    },
]

# 금지 자산이 닫혀야 하는 유출 경로. 기계로 확인 가능한 것만 검사하고,
# 나머지는 확인 근거를 대장에 남긴다 (확인 불가를 '통과' 로 두지 않는다).
EGRESS_PATHS = ["git_tracked", "publish_list", "public_artifact", "blob", "site_consumer"]


BLOB_BASE = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/"

# 🚨 오퍼레이터 전용 소비는 금지 대상이 아니다. 금지의 뜻 = **재배포 금지**이지 본인 사용 금지가
# 아니다. chat_hybrid 가 VERITY-private 에서 PAT 로 읽어 "판단 재료로만" 쓰는 경로는 설계상 허용
# (internal_context._sec_consensus). 공개 경로(framer 공개 컴포넌트·발행 산출물)만 닫혀야 한다.
OPERATOR_PRIVATE_OK = ("vercel-api/api/chat_hybrid/",)


def _site_consumers(basename: str) -> list[str]:
    """공개 경로에서 이 파일을 **실제로 읽는** 곳. 주석·상태 라벨은 제외한다."""
    stem = basename.rsplit(".", 1)[0]
    hits = []
    for d in ("framer-components", "vercel-api", "operator-web/app", "operator-web/lib"):
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for dp, _, fs in os.walk(base):
            if any(s in dp + "/" for s in ("node_modules", "/.next/")):
                continue
            for f in fs:
                if not f.endswith((".py", ".tsx", ".ts")):
                    continue
                p = os.path.join(dp, f)
                rel_p = os.path.relpath(p, ROOT)
                if rel_p.startswith(OPERATOR_PRIVATE_OK):
                    continue
                try:
                    s = open(p, encoding="utf-8", errors="ignore").read()
                except OSError:
                    continue
                for line in s.splitlines():
                    t = line.strip()
                    if stem not in t or t.startswith(("#", "//", "*")):
                        continue
                    if re.search(r"_load|open\(|fetch\(|read|require|import|get\(", t):
                        hits.append(f"{rel_p}: {t[:60]}")
                        break
    return hits


def banned_status(entry: dict, pub: set[str], tracked: set[str], net: bool = False) -> dict:
    """금지 자산 1건의 경로별 닫힘 상태. True=닫힘 / False=열림 / None=확인 불가."""
    f = entry["file"]
    b = os.path.basename(f)
    st = {
        "git_tracked": f not in tracked,          # 추적 0 이어야 닫힘
        "publish_list": b not in pub,             # 발행 목록 부재여야 닫힘
        "site_consumer": not _site_consumers(b),  # 공개 경로 읽기 0 이어야 닫힘
    }
    # public_artifact — 발행 중인 공개 리포트에 컨센서스 값이 실렸는지 (전수 문자열)
    rep = os.path.join(ROOT, "data", "stock_report_public.json")
    try:
        txt = _read(rep)
        st["public_artifact"] = ("target_price" not in txt) and ('"opinion"' not in txt)
    except OSError:
        st["public_artifact"] = None
    # blob — 기본은 기록된 증거를 쓰고, --net 이면 실제로 눌러 확인한다
    ev = entry.get("blob_evidence") or {}
    if net:
        import urllib.request
        try:
            req = urllib.request.Request(BLOB_BASE + b, method="GET")
            with urllib.request.urlopen(req, timeout=12) as r:
                st["blob"] = r.status == 404
        except Exception as e:  # noqa: BLE001 — 404 는 HTTPError 로 온다
            st["blob"] = getattr(e, "code", None) == 404
    else:
        st["blob"] = ev.get("http_code") == 404 if ev else None
    return st


def build() -> dict:
    pub, priv = publish_names(), private_rules()
    sla, contracts, corpus = sla_streams(), contracts_map(), code_corpus()
    arts = []
    for path in in_scope():
        b = os.path.basename(path)
        vis = "public" if b in pub else "work"
        full = os.path.join(ROOT, path)
        arts.append({
            "path": path,
            "visibility": vis,
            "publish": b in pub,
            "sla": sla_for(b, sla),
            "contract": contracts.get(path),
            "size_bytes": os.path.getsize(full) if os.path.exists(full) else None,
            "producers": find_producers(b, corpus),
        })
    return {
        "_meta": {
            "artifact": "data_manifest",
            "purpose": "산출물 1건 = 1행 선언. 공개/비공개 경계와 등재 상태의 단일 창구 (구조 제안 ①)",
            "generated_by": "scripts/audit/build_data_manifest.py",
            "scope": "data/ 최상위 추적 파일 + 위치 무관 발행 목록 등재분 (레이크·캐시 디렉터리 전체는 대상 아님)",
            "derived_from": {"publish": ".github/actions/publish-data/action.yml",
                             "private": ".gitignore /data/ 규칙",
                             "sla": "data/freshness_sla.json streams",
                             "contract": "data/contracts/*.contract.json"},
            "limits": [
                "producers 는 이름 언급 + 쓰기 정황 기반 **후보**다. 확정 아님 (동적 파일명은 못 잡는다)",
                "visibility=private 는 무시규칙 대상이라 추적 목록에 없다 — 여기에는 나타나지 않는다",
                "이 대장은 선언이지 강제가 아니다. 강제는 --check 의 종료 코드 1이 한다",
            ],
            "is_operational": False,
        },
        "private_rules": priv,
        "banned": [dict(e, egress=banned_status(e, pub, set(tracked_all()), net=NET)) for e in BANNED],
        "artifacts": arts,
    }


def check(man: dict) -> list[str]:
    issues = []
    pub = publish_names()
    names = {os.path.basename(a["path"]) for a in man["artifacts"]}

    ghosts = sorted(pub - names)                                   # C1
    if ghosts:
        issues.append(f"C1 발행 목록에 있으나 추적 실물 부재 {len(ghosts)}: {ghosts[:6]}")

    tracked = {a["path"] for a in man["artifacts"]}                # C2
    carved = negated_paths()          # `!` 재포함 = 의도적 공개, 유출 아님
    leaked = []
    for rule in man.get("private_rules", []):
        if "*" in rule:
            pat = re.compile("^" + rule.replace(".", r"\.").replace("*", "[^/]*") + "$")
            leaked += [t for t in tracked if pat.match(t) and t not in carved]
        elif rule in tracked and rule not in carved:
            leaked.append(rule)
    if leaked:
        issues.append(f"🚨 C2 비공개 규칙 대상이 추적 중 {len(leaked)}: {sorted(set(leaked))[:6]}")

    naked = [a["path"] for a in man["artifacts"]                   # C3
             if a["publish"] and not a["sla"] and not a["contract"]]
    if naked:
        issues.append(f"C3 발행물 중 계약·SLA 모두 없음 {len(naked)}/{sum(1 for a in man['artifacts'] if a['publish'])}"
                      f" (경고): {naked[:6]}")

    live = set(in_scope())                                      # C4
    added, gone = sorted(live - tracked), sorted(tracked - live)
    if added or gone:
        issues.append(f"C4 매니페스트 드리프트 — 신규 {len(added)} {added[:4]} · 소멸 {len(gone)} {gone[:4]}"
                      " → 재생성 필요")

    all_tracked = set(tracked_all())                            # C5 금지 자산 경로 대장
    for e in BANNED:
        st = banned_status(e, pub, all_tracked, net=NET)
        opened = [k for k, v in st.items() if v is False]
        unknown = [k for k, v in st.items() if v is None]
        if opened:
            issues.append(f"🚨 C5 금지 자산 경로 열림 — {e['file']}: {opened} "
                          f"(판정 {e['decided']}, 사유 {e['reason']})")
        elif unknown:
            issues.append(f"C5 {os.path.basename(e['file'])} 경로 {unknown} = 기계 확인 불가 "
                          "(경고 — 수동 확인 근거를 대장에 남길 것)")
    return issues


NET = False


def main() -> int:
    global NET
    NET = "--net" in sys.argv
    check_only = "--check" in sys.argv
    if check_only:
        if not os.path.exists(MANIFEST):
            print("🚨 data/manifest.json 부재 — 먼저 생성할 것")
            return 1
        man = json.load(open(MANIFEST, encoding="utf-8"))
    else:
        man = build()
        json.dump(man, open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    arts = man["artifacts"]
    vis = {}
    for a in arts:
        vis[a["visibility"]] = vis.get(a["visibility"], 0) + 1
    print("═" * 64)
    print(f"산출물 대장 {len(arts)}건 — " + " · ".join(f"{k} {v}" for k, v in sorted(vis.items())))
    print(f"  계약 보유 {sum(1 for a in arts if a['contract'])} · SLA 보유 {sum(1 for a in arts if a['sla'])}"
          f" · 생산자 후보 확인 {sum(1 for a in arts if a['producers'])}"
          f" · 생산자 미상 {sum(1 for a in arts if not a['producers'])}")
    print(f"  비공개 규칙 {len(man.get('private_rules', []))}건 (추적 밖이라 대장에 없음)")

    issues = check(man)
    hard = [i for i in issues if not i.startswith("C3") and not i.startswith("C5 ")]
    if issues:
        print("\n대조 결과:")
        for i in issues:
            print(f"  {'🚨' if not i.startswith('C3') else '⚠'} {i}")
    else:
        print("\n3자 대조 위반 0 ✓")
    if not check_only:
        print(f"\n기록 → {MANIFEST}")
    return 1 if hard else 0


if __name__ == "__main__":
    raise SystemExit(main())

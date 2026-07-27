#!/usr/bin/env python3
"""국내 종목 한글 검색 별칭 — universe_search 의 name_ko/kw 채움.

배경 (2026-07-27 전수 검사):
  검색창은 name · ticker · name_ko · kw 4개를 매칭하는데, **국내 4,036종 전부 name_ko 가 없었다.**
  (해외는 5,076/5,562 = 91% 보유 — 국내만 비어 있는 비대칭.)
  그 결과 이름이 라틴 문자인 135종은 한글로 아예 못 찾았다: NAVER·S-Oil·HLB·HMM·KT&G·KODEX 200 …
  실측: "네이버" 0건 / "에스오일" 0건 / "코덱스" 0건 / "엘지" 0건.

설계:
  · LATIN_KO = 라틴 토큰 → 한글 음차. 기업명·ETF 운용사 브랜드·상품 접미어를 한 표에 둔다.
    토큰 단위 치환이라 신규 상장(예: "TIGER 미국배당")도 브랜드만 알면 자동으로 별칭이 생긴다.
  · 별칭은 항상 2종 생성 — 띄어쓰기 유지형("코덱스 200")과 제거형("코덱스200").
    사용자는 둘 다 입력한다. kw 에 공백 제거 원문(latin)도 넣어 "kodex200" 같은 입력도 잡는다.
  · 이미 한글인 이름은 name 으로 매칭되므로 별칭을 만들지 않되, 공백 제거형만 kw 에 넣는다
    ("삼성 전자" 처럼 띄어 입력해도 걸리게).

🚨 RULE 7 무관 — 표시명 별칭이며 점수·판단이 아니다.
"""
from __future__ import annotations

import re
from typing import Dict, List

_HAN = re.compile(r"[가-힣]")

# ── 라틴 토큰 → 한글 음차 ───────────────────────────────────────────────
# ETF 운용사 브랜드 (신규 ETF 자동 대응)
_BRAND: Dict[str, str] = {
    "KODEX": "코덱스", "TIGER": "타이거", "HANARO": "하나로", "PLUS": "플러스",
    "RISE": "라이즈", "SOL": "솔", "KIWOOM": "키움", "ACE": "에이스", "TREX": "트렉스",
    "WON": "원", "HK": "에이치케이", "IBK": "아이비케이", "DAISHIN": "대신",
    "KOSEF": "코세프", "ARIRANG": "아리랑", "KBSTAR": "케이비스타", "TIMEFOLIO": "타임폴리오",
    "SMART": "스마트", "FOCUS": "포커스", "MASTER": "마스터", "BNK": "비엔케이",
}
# 기업명·약어 (2026-07-27 전수 조사에서 나온 국내 라틴 이름 135종 기준)
_CORP: Dict[str, str] = {
    "NAVER": "네이버", "SK": "에스케이", "GS": "지에스", "LG": "엘지", "LS": "엘에스",
    "KT": "케이티", "CJ": "씨제이", "DL": "디엘", "DB": "디비", "SG": "에스지",
    "NC": "엔씨", "NHN": "엔에이치엔", "HLB": "에이치엘비", "HMM": "에이치엠엠",
    "HPSP": "에이치피에스피", "HDC": "에이치디씨", "KCC": "케이씨씨", "OCI": "오씨아이",
    "ISC": "아이에스씨", "SKC": "에스케이씨", "GST": "지에스티", "GKL": "지케이엘",
    "NICE": "나이스", "TYM": "티와이엠", "SIMPAC": "심팩", "KEC": "케이이씨",
    "BGF": "비지에프", "KCTC": "케이씨티씨", "DSR": "디에스알", "LF": "엘에프",
    "JTC": "제이티씨", "INVENI": "인베니", "HRS": "에이치알에스", "SDN": "에스디엔",
    "NPC": "엔피씨", "TP": "티피", "CS": "씨에스", "DKME": "디케이엠이", "YW": "와이더블유",
    "DXVX": "디엑스브이엑스", "FSN": "에프에스엔", "APS": "에이피에스", "SJM": "에스제이엠",
    "SBS": "에스비에스", "KX": "케이엑스", "SYTS": "에스와이티에스", "WISCOM": "위스컴",
    "BYC": "비와이씨", "DYP": "디와이피", "SHD": "에스에이치디", "YTN": "와이티엔",
    "KBG": "케이비지", "NEW": "뉴", "EG": "이지", "STX": "에스티엑스", "DGI": "디지아이",
    "EDGC": "이디지씨", "KD": "케이디", "KNN": "케이엔엔", "RFHIC": "알에프에이치아이씨",
    "GRT": "지알티", "JYP": "제이와이피", "SFA": "에스에프에이", "PKC": "피케이씨",
    "DMS": "디엠에스", "SOOP": "숲", "SKAI": "에스케이에이아이", "SM": "에스엠",
    "YG": "와이지", "M83": "엠팔십삼", "E1": "이원", "E8": "이에잇", "TC": "티씨",
    "MBC": "엠비씨", "CNT85": "씨엔티팔십오", "KTcs": "케이티씨에스", "KTis": "케이티아이에스",
    "SGC": "에스지씨", "HL": "에이치엘", "THE": "더", "CGV": "씨지브이", "ENM": "이엔엠",
    "KCP": "케이씨피", "ELECTRIC": "일렉트릭", "EMB": "이엠비", "3S": "쓰리에스",
    "F&F": "에프앤에프", "S-Oil": "에스오일", "KT&G": "케이티앤지", "SM C&C": "에스엠씨앤씨",
    "iMBC": "아이엠비씨", "Ent.": "엔터", "D&I": "디앤아이", "E&M": "이앤엠",
    "E&C": "이앤씨", "C&C": "씨앤씨", "SG&G": "에스지앤지", "SUN&L": "선앤엘",
    "Life": "라이프", "Design": "디자인",
}
# 상품/지수 접미어 (ETF 이름 뒷부분)
_SUFFIX: Dict[str, str] = {
    "TR": "티알", "TOP": "탑", "IT": "아이티", "ESG": "이에스지", "KRX": "케이알엑스",
    "MSCI": "엠에스씨아이", "Korea": "코리아", "KTOP": "케이탑", "TRF": "티알에프",
    "BBIG": "비빅", "exTOP": "엑스탑", "Top5PlusTR": "탑파이브플러스티알",
}

LATIN_KO: Dict[str, str] = {}
for _d in (_BRAND, _CORP, _SUFFIX):
    LATIN_KO.update(_d)

# 긴 토큰 우선 치환 (SM C&C 가 SM 보다 먼저)
_ORDERED = sorted(LATIN_KO.items(), key=lambda kv: -len(kv[0]))


def _translit(name: str) -> str:
    """이름 안의 라틴 토큰을 한글로 치환. 매핑 없는 토큰은 원문 유지.

    🚨 반드시 단어 경계에서만 치환한다. 경계 없이 substring 치환하면 다른 단어 속을 파고든다 —
    실측(2026-07-27): "Holdings" → "Holdin지에스"(GS), "원익QnC" → "원익Q엔씨"(NC),
    "TPC로보틱스" → "티피C로보틱스"(TP) 로 6,011건이 오염되고 "지에스" 검색이 444건으로 터졌다.
    앞뒤가 영문/숫자면 치환하지 않는다(한글·기호·문자열 끝은 경계로 인정).
    """
    out = name
    for lat, ko in _ORDERED:
        if not lat:
            continue
        pat = r"(?<![A-Za-z0-9])" + re.escape(lat) + r"(?![A-Za-z0-9])"
        out = re.sub(pat, ko, out, flags=re.IGNORECASE)
    return out


def aliases(name: str) -> List[str]:
    """검색 별칭 목록 — 한글 음차형 + 공백 제거형 + 원문 공백 제거형."""
    nm = (name or "").strip()
    if not nm:
        return []
    out: List[str] = []
    ko = _translit(nm)
    if ko != nm:  # 라틴이 실제로 치환된 경우만 별칭 의미가 있음
        out.append(ko)
        nospace = re.sub(r"\s+", "", ko)
        if nospace != ko:
            out.append(nospace)
    # 원문 공백 제거형 — "KODEX 200" → "kodex200", "삼성 전자" → "삼성전자"
    raw_ns = re.sub(r"\s+", "", nm)
    if raw_ns != nm:
        out.append(raw_ns)
    # 중복 제거(순서 유지)
    seen = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def enrich_entry(entry: dict) -> dict:
    """universe_search 엔트리에 name_ko / kw 를 채운다. 이미 있으면 보존 후 병합."""
    nm = str(entry.get("name") or "")
    al = aliases(nm)
    if not al:
        return entry
    ko_first = next((a for a in al if _HAN.search(a)), "")
    if ko_first and not entry.get("name_ko"):
        entry["name_ko"] = ko_first  # 표시·매칭 대표 별칭
    kw_parts = [str(entry.get("kw") or "")] + al
    kw = " ".join(p for p in kw_parts if p).strip()
    if kw:
        entry["kw"] = kw
    return entry


if __name__ == "__main__":  # 간이 점검
    for s in ("NAVER", "S-Oil", "KT&G", "KODEX 200", "TIGER 200 IT", "삼성전자",
              "SM C&C", "CJ CGV", "HANARO 200 TOP10", "iMBC"):
        print(f"  {s:20} → {aliases(s)}")

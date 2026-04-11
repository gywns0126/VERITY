"""
섹터 로테이션 전략 모듈
매크로 국면(금리/경기 사이클)에 따라 유리한 섹터를 자동 추천
"""

ROTATION_MAP = {
    "recovery": {
        "label": "경기 회복기",
        "desc": "금리 하락 + 경기 반등 → 성장주/기술주 우위",
        "favor": ["반도체", "IT", "자동차", "건설", "철강", "조선"],
        "avoid": ["유틸리티", "통신", "보험"],
    },
    "expansion": {
        "label": "경기 확장기",
        "desc": "금리 상승 + 경기 호황 → 경기민감주 우위",
        "favor": ["에너지", "소재", "화학", "기계", "운송", "산업재"],
        "avoid": ["필수소비재", "유틸리티", "헬스케어"],
    },
    "slowdown": {
        "label": "경기 둔화기",
        "desc": "금리 고점 + 성장 둔화 → 방어주/배당주 우위",
        "favor": ["헬스케어", "필수소비재", "유틸리티", "통신", "금융"],
        "avoid": ["IT", "반도체", "자동차", "건설"],
    },
    "contraction": {
        "label": "경기 수축기",
        "desc": "금리 하락 시작 + 경기 침체 → 현금/채권/안전자산 우위",
        "favor": ["유틸리티", "헬스케어", "필수소비재", "금"],
        "avoid": ["에너지", "소재", "건설", "자동차", "IT"],
    },
}

SECTOR_KEYWORD_MAP = {
    "반도체": ["반도체", "디스플레이", "전자부품"],
    "IT": ["소프트웨어", "인터넷", "IT", "게임", "기술", "커뮤니케이션"],
    "자동차": ["자동차", "운수장비", "경기소비재"],
    "건설": ["건설업", "건축"],
    "철강": ["철강", "금속"],
    "조선": ["조선", "해운"],
    "에너지": ["에너지", "석유"],
    "소재": ["화학", "소재", "섬유"],
    "화학": ["화학"],
    "기계": ["기계", "전기장비"],
    "운송": ["운수", "운송", "항공", "해운"],
    "산업재": ["산업재", "무역"],
    "헬스케어": ["의약품", "제약", "바이오", "건강관리", "헬스케어"],
    "필수소비재": ["음식료", "생활용품", "농업", "필수소비재"],
    "유틸리티": ["전기가스", "유틸리티", "부동산"],
    "통신": ["통신", "방송"],
    "금융": ["은행", "증권", "보험", "금융"],
    "금": ["금", "귀금속"],
}

THEME_TO_SECTOR_IDS = {
    "반도체": ["SEC_TECH"],
    "IT": ["SEC_TECH", "SEC_COMM"],
    "자동차": ["SEC_CYCL"],
    "건설": ["SEC_INDU"],
    "철강": ["SEC_MATL"],
    "조선": ["SEC_INDU"],
    "에너지": ["SEC_ENGY"],
    "소재": ["SEC_MATL"],
    "화학": ["SEC_MATL"],
    "기계": ["SEC_INDU"],
    "운송": ["SEC_INDU"],
    "산업재": ["SEC_INDU"],
    "헬스케어": ["SEC_HLTH"],
    "필수소비재": ["SEC_DEFE"],
    "유틸리티": ["SEC_UTIL", "SEC_REAL"],
    "통신": ["SEC_COMM"],
    "금융": ["SEC_FIN"],
    "금": [],
}


def determine_cycle(macro: dict) -> str:
    """매크로 지표 기반 경기 사이클 판단"""
    mood_score = macro.get("market_mood", {}).get("score", 50)
    vix = macro.get("vix", {}).get("value", 20)
    spread = macro.get("yield_spread", {}).get("value", 0.5)
    usd_chg = macro.get("usd_krw", {}).get("change_pct", 0)
    sp_chg = macro.get("sp500", {}).get("change_pct", 0)

    score = 0

    if mood_score >= 65:
        score += 2
    elif mood_score >= 50:
        score += 1
    elif mood_score >= 35:
        score -= 1
    else:
        score -= 2

    if vix < 18:
        score += 1
    elif vix > 28:
        score -= 2
    elif vix > 22:
        score -= 1

    if spread < 0:
        score -= 2
    elif spread < 0.3:
        score -= 1
    elif spread > 1.5:
        score += 1

    if sp_chg > 1:
        score += 1
    elif sp_chg < -1:
        score -= 1

    if score >= 3:
        return "expansion"
    elif score >= 1:
        return "recovery"
    elif score >= -1:
        return "slowdown"
    else:
        return "contraction"


def _match_theme(sector: dict, theme_key: str) -> bool:
    """sector_id 우선, 없으면 한글 키워드 폴백."""
    sid = sector.get("sector_id", "")
    if sid and theme_key in THEME_TO_SECTOR_IDS:
        if sid in THEME_TO_SECTOR_IDS[theme_key]:
            return True
    name = sector.get("name", "")
    if theme_key in SECTOR_KEYWORD_MAP:
        for kw in SECTOR_KEYWORD_MAP[theme_key]:
            if kw in name:
                return True
    return False


def get_sector_rotation(macro: dict, sectors: list) -> dict:
    """섹터 로테이션 추천 생성"""
    cycle = determine_cycle(macro)
    rotation = ROTATION_MAP[cycle]

    recommended = []
    avoid = []

    for sector in sectors:
        name = sector.get("name", "")
        for favor_key in rotation["favor"]:
            if _match_theme(sector, favor_key):
                recommended.append({
                    "name": name,
                    "sector_id": sector.get("sector_id", ""),
                    "change_pct": sector.get("change_pct", 0),
                    "reason": f"{rotation['label']}에서 {favor_key} 섹터 유리",
                    "theme": favor_key,
                })
                break

        for avoid_key in rotation["avoid"]:
            if _match_theme(sector, avoid_key):
                avoid.append({
                    "name": name,
                    "sector_id": sector.get("sector_id", ""),
                    "change_pct": sector.get("change_pct", 0),
                    "reason": f"{rotation['label']}에서 {avoid_key} 섹터 비우호적",
                    "theme": avoid_key,
                })
                break

    recommended.sort(key=lambda x: x["change_pct"], reverse=True)
    avoid.sort(key=lambda x: x["change_pct"])

    return {
        "cycle": cycle,
        "cycle_label": rotation["label"],
        "cycle_desc": rotation["desc"],
        "recommended_sectors": recommended[:8],
        "avoid_sectors": avoid[:5],
    }

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
    "IT": ["소프트웨어", "인터넷", "IT", "게임"],
    "자동차": ["자동차", "운수장비"],
    "건설": ["건설업", "건축"],
    "철강": ["철강", "금속"],
    "조선": ["조선", "해운"],
    "에너지": ["에너지", "석유"],
    "소재": ["화학", "소재", "섬유"],
    "화학": ["화학"],
    "기계": ["기계", "전기장비"],
    "운송": ["운수", "운송", "항공", "해운"],
    "산업재": ["산업재", "무역"],
    "헬스케어": ["의약품", "제약", "바이오", "건강관리"],
    "필수소비재": ["음식료", "생활용품", "농업"],
    "유틸리티": ["전기가스", "유틸리티"],
    "통신": ["통신", "방송"],
    "금융": ["은행", "증권", "보험", "금융"],
    "금": ["금", "귀금속"],
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


def get_sector_rotation(macro: dict, sectors: list) -> dict:
    """섹터 로테이션 추천 생성"""
    cycle = determine_cycle(macro)
    rotation = ROTATION_MAP[cycle]

    def _match_sector(sector_name: str, keywords: list) -> bool:
        for kw in keywords:
            if kw in sector_name:
                return True
        return False

    recommended = []
    avoid = []

    for sector in sectors:
        name = sector.get("name", "")
        for favor_key in rotation["favor"]:
            if favor_key in SECTOR_KEYWORD_MAP:
                if _match_sector(name, SECTOR_KEYWORD_MAP[favor_key]):
                    recommended.append({
                        "name": name,
                        "change_pct": sector.get("change_pct", 0),
                        "reason": f"{rotation['label']}에서 {favor_key} 섹터 유리",
                        "theme": favor_key,
                    })
                    break

        for avoid_key in rotation["avoid"]:
            if avoid_key in SECTOR_KEYWORD_MAP:
                if _match_sector(name, SECTOR_KEYWORD_MAP[avoid_key]):
                    avoid.append({
                        "name": name,
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

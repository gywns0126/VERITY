import { addPropertyControls, ControlType } from "framer"
import React, { useState, useEffect, useCallback, useRef } from "react"

/* ──────────────────────────────────────────────────────────────
 * ◆ ESTATE DESIGN TOKENS v1.1 ◆ (다크 + 골드 emphasis — 옵션 A 패밀리룩)
 * v1.0 (다크 기본 — LandexMapDashboard 묵시 정본) → v1.1 (P3-2.7 다크 + 골드
 * emphasis 진화). HeroBriefing/SystemPulse 와 동일 토큰.
 *
 * grade* · stage* hex 인라인 (LandexMapDashboard v1.0 정본 hex 그대로) — 옵션 A
 * 채택. v1.1 토큰 정의 무수정 ([C]6 미발동), 시각 일관성 보장.
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0A0908",
    bgCard: "#0F0D0A",
    bgElevated: "#16130E",
    bgInput: "#1F1B14",
    border: "#26221C",
    borderStrong: "#3A3024",
    textPrimary: "#F2EFE9",
    textSecondary: "#A8A299",
    textTertiary: "#6B665E",
    textDisabled: "#4A453E",
    accent: "#B8864D",
    accentBright: "#D4A26B",
    accentSoft: "rgba(184,134,77,0.15)",
    success: "#22C55E",
    warn: "#F59E0B",
    danger: "#EF4444",
    info: "#5BA9FF",
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_SERIF = "'Noto Serif KR', 'Times New Roman', serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const R = { sm: 6, md: 10, lg: 14, pill: 999 }

// grade* · stage* hex 인라인 (LandexMapDashboard 정본)
const GRADE_COLORS: Record<string, string> = {
    HOT: "#EF4444",
    WARM: "#F59E0B",
    NEUT: "#A8ABB2",
    COOL: "#5BA9FF",
    AVOID: "#6B6E76",
}
const STAGE_COLORS: Record<number, string> = {
    0: "transparent",
    1: "#FFD600",
    2: "#F59E0B",
    3: "#EF4444",
    4: "#9B59B6",
}
/* ◆ TOKENS END ◆ */

const ESTATE_API_BASE = "https://project-yw131.vercel.app"
const ESTATE_LANDEX_PULSE_URL = `${ESTATE_API_BASE}/api/estate/landex-pulse`


/* ──────────────────────────────────────────────────────────────
 * ◆ TRIGGER 매핑 ◆
 * ────────────────────────────────────────────────────────────── */
type LandexTrigger = "normal" | "regime_shift"

const REGIME_SHIFT_THRESHOLD = 3

const TRIGGER_HEADERS: Record<LandexTrigger, {
    title: string; subtitle: (n: number) => string; sectionLabel: string
}> = {
    normal: {
        title: "시장 정상",
        subtitle: () => "regime 안정 — 25구 변화 임계 미만",
        sectionLabel: "REGIME · STABLE",
    },
    regime_shift: {
        title: "시장 regime 변동",
        subtitle: (n) => `${n}개 구 등급 변화 — 운영자 검토 필요`,
        sectionLabel: "REGIME · SHIFT DETECTED",
    },
}


/* ──────────────────────────────────────────────────────────────
 * ◆ TERMS 인라인 (estate/data/terms.json 정합) ◆
 * Framer self-contained 컨벤션 (T31) — 외부 import 0.
 * P4: terms.json 별도 fetch 또는 동적 import 검토.
 * ────────────────────────────────────────────────────────────── */
interface Term {
    label: string
    category?: string
    definition: string
    stages?: Record<string, string>
    values?: Record<string, string>
    l3?: boolean
}
const TERMS: Record<string, Term> = {
    LANDEX: { label: "LANDEX", category: "metric", definition: "ESTATE 자체 종합 점수 (0~100). V/D/S/C/R 5개 sub-score 의 가중 평균. 가중치는 preset 에 따라 동적." },
    V_SCORE: { label: "V Score (가치)", category: "metric", definition: "Value — 가치 점수 (0~100). 자산 가격 대비 내재 가치 평가." },
    D_SCORE: { label: "D Score (수요)", category: "metric", definition: "Demand — 수요 점수 (0~100). 거래량 + 매물 회전율 + 임차 수요." },
    S_SCORE: { label: "S Score (공급)", category: "metric", definition: "Supply — 공급 점수 (0~100). 신규 분양 + 미분양 호수 + 입주 물량." },
    C_SCORE: { label: "C Score (입지)", category: "metric", definition: "Convenience — 입지 점수 (0~100). 교통 접근성 + 학군 + 생활 인프라." },
    R_SCORE: { label: "R Score (위험)", category: "metric", definition: "Risk — 위험 점수 (0~100). 정책/금리/재건축 리스크 가중치." },
    CATALYST_SCORE: { label: "Catalyst Score", category: "metric", definition: "단기 변화 트리거 점수 (0~100). 정책 발표 + 개발 호재 + 공급 변화 가중." },
    GEI_STAGE: {
        label: "GEI Stage", category: "internal", l3: true,
        definition: "시장 과열 단계 지표 (S0~S4). 매물 회전율 + 임차료 상승 + 거래량 가속도 임계.",
        stages: { S0: "안정 (0~19)", S1: "주의 (20~39)", S2: "경계 (40~59)", S3: "과열 (60~79)", S4: "위험 (80~100)" },
    },
    GRADE_HOT: { label: "HOT 등급", category: "grade", definition: "최상위 등급 (LANDEX >= 80). 모든 5축이 평균 이상 + 강한 모멘텀." },
    GRADE_WARM: { label: "WARM 등급", category: "grade", definition: "상위 등급 (LANDEX 65~79). 안정적 우위, 일부 축 강점." },
    GRADE_NEUT: { label: "NEUT 등급", category: "grade", definition: "중립 등급 (LANDEX 50~64). 시장 평균권." },
    GRADE_COOL: { label: "COOL 등급", category: "grade", definition: "하위 등급 (LANDEX 35~49). 관망 권역, 1~2개 축 약점." },
    GRADE_AVOID: { label: "AVOID 등급", category: "grade", definition: "회피 등급 (LANDEX < 35). 다수 축 평균 이하." },
    REGIME: {
        label: "Regime", category: "metric",
        definition: "시장 regime — 25구 평균 LANDEX 추세 분류.",
        values: { bull: "강세 (avg >= 60)", bear: "약세 (avg <= 45)", neutral: "중립 (45 < avg < 60)" },
    },
    TIER10: { label: "Tier 10", category: "grade", definition: "10단계 세분 등급 (A+/A/.../D). LANDEX 점수 10분위." },
    FEATURE_CONTRIB: {
        label: "피처 기여도", category: "internal", l3: true,
        definition: "LANDEX 점수에 영향을 미친 요인별 가중치. 부호(+/-) + 절대값(weight). 외부 공유 금지 — 모델 내부 자산.",
    },
    WEEKLY_PRICE_INDEX: { label: "주간 매매가격지수", category: "data_source", definition: "R-ONE 주간 발표 매매가격지수 (목요일 발표). 자치구별 시계열." },
    MONTHLY_UNSOLD: { label: "월간 미분양", category: "data_source", definition: "R-ONE 월간 미분양현황. 자치구별 미분양 호수 누적 추이." },
    MoM: { label: "Month over Month", category: "time", definition: "전월 대비 변화율. % 단위." },
    WoW: { label: "Week over Week", category: "time", definition: "전주 대비 변화율. % 단위." },
}


/* ──────────────────────────────────────────────────────────────
 * ◆ Types ◆
 * ────────────────────────────────────────────────────────────── */
type GradeLabel = "HOT" | "WARM" | "NEUT" | "COOL" | "AVOID"

interface FeatureContrib { feature: string; weight: number; sign: "+" | "-" }
interface SeriesPoint { date: string; value: number }
interface GuDetail {
    radar: { v: number; d: number; s: number; c: number; r: number }
    feature_contributions: FeatureContrib[]
    timeseries: {
        weekly_price_index: SeriesPoint[]
        monthly_unsold: SeriesPoint[]
    }
    strengths: string[]
    weaknesses: string[]
}
interface Gu {
    gu_name: string
    landex: number
    grade: GradeLabel
    gei: number
    stage: 0 | 1 | 2 | 3 | 4
    v_score: number
    d_score: number
    s_score: number
    c_score: number
    r_score: number
    catalyst_score: number
    detail: GuDetail
}
interface PulseData {
    schema_version?: string
    generated_at: string
    scenario?: string
    trigger: { type: LandexTrigger }
    meta: {
        primary: {
            current_regime: "bull" | "bear" | "neutral"
            top_gainer: { gu_name: string; change_pct: number }
            top_loser: { gu_name: string; change_pct: number }
            last_shift_at: string | null
        }
        detail: {
            degraded_count: number
            gained_count: number
            gei_s4_count: number
            avg_landex: number
            data_freshness_min: number
        }
    }
    gus: Gu[]
}

type FetchState =
    | { status: "loading" }
    | { status: "error"; reason: string }
    | { status: "ok"; data: PulseData; fetchedAt: number }


/* ──────────────────────────────────────────────────────────────
 * ◆ Helpers ◆
 * ────────────────────────────────────────────────────────────── */
function formatFreshness(minutes: number | null | undefined): string {
    if (minutes == null) return "—"
    if (minutes < 1) return "< 1min"
    if (minutes < 60) return `${minutes}min ago`
    if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`
    return `${Math.floor(minutes / 1440)}d ago`
}

function minutesSince(iso: string | null | undefined, now: number): number | null {
    if (!iso) return null
    try {
        const t = new Date(iso).getTime()
        if (isNaN(t)) return null
        return Math.floor((now - t) / 60000)
    } catch { return null }
}

function inferTrigger(data: PulseData): LandexTrigger {
    const total = data.meta.detail.degraded_count + data.meta.detail.gained_count
    return total >= REGIME_SHIFT_THRESHOLD ? "regime_shift" : "normal"
}


/* ──────────────────────────────────────────────────────────────
 * ◆ SEOUL 25-GU GEOPATHS ◆ (atomic/SeoulMap.tsx 정합 인라인)
 * Framer self-contained 컨벤션 (T31) — 외부 import 0.
 * 데이터 출처: southkorea/seoul-maps GeoJSON (simplified) → SVG path + centroid.
 * ────────────────────────────────────────────────────────────── */
const SEOUL_VIEWBOX = "0 0 1000 823"
type GuPath = { name: string; d: string; cx: number; cy: number }
const SEOUL_PATHS: GuPath[] = [
    { name: "강동구", d: "M832.1,425.5 L840.7,426.4 L847.1,418.5 L854.0,413.7 L881.7,401.0 L913.7,391.1 L927.5,385.1 L955.5,367.6 L964.0,368.4 L977.6,367.4 L984.8,364.0 L981.0,374.3 L982.7,383.4 L986.9,390.0 L989.9,398.9 L991.1,409.4 L996.8,423.6 L995.4,448.0 L999.6,451.6 L998.5,462.4 L1000.0,470.5 L995.7,471.1 L989.8,466.8 L981.5,471.1 L973.7,470.0 L959.1,474.0 L951.9,471.7 L928.9,504.9 L928.2,519.0 L919.0,530.2 L914.9,540.9 L910.3,541.2 L907.8,548.9 L907.5,556.3 L904.1,554.9 L846.6,522.8 L849.6,516.0 L856.3,491.3 L845.1,484.0 L823.7,476.4 L829.7,464.1 L834.1,446.6 L834.1,430.7 L832.1,425.5 Z", cx: 913, cy: 453 },
    { name: "송파구", d: "M721.9,531.8 L736.0,536.0 L747.3,536.4 L763.3,533.8 L782.3,526.7 L797.9,524.1 L807.4,504.9 L823.7,476.4 L845.1,484.0 L856.3,491.3 L849.6,516.0 L846.6,522.8 L904.1,554.9 L907.5,556.3 L907.4,560.5 L902.5,564.3 L899.2,570.3 L896.4,581.6 L899.2,591.0 L909.0,596.9 L914.8,597.6 L920.7,593.9 L924.9,598.0 L941.3,602.5 L947.6,606.7 L944.0,617.0 L944.4,624.2 L940.2,635.9 L936.6,640.9 L924.7,644.8 L918.9,667.0 L918.9,672.5 L911.9,678.0 L901.4,678.4 L894.1,687.7 L882.6,683.0 L874.2,681.8 L874.9,692.8 L885.5,700.2 L878.9,704.3 L869.5,704.3 L861.0,699.4 L861.1,707.0 L854.1,712.4 L854.2,706.3 L850.0,696.9 L828.8,660.5 L830.2,657.2 L822.5,642.1 L814.4,633.4 L806.2,627.0 L793.1,620.1 L749.2,605.6 L739.6,603.2 L728.7,592.3 L722.4,547.2 L720.8,544.3 L721.9,531.8 Z", cx: 837, cy: 592 },
    { name: "강남구", d: "M697.1,519.7 L721.9,531.8 L720.8,544.3 L722.4,547.2 L728.7,592.3 L739.6,603.2 L749.2,605.6 L793.1,620.1 L806.2,627.0 L814.4,633.4 L822.5,642.1 L830.2,657.2 L828.8,660.5 L850.0,696.9 L854.2,706.3 L854.1,712.4 L842.6,721.6 L840.9,732.4 L832.5,728.1 L829.6,723.5 L815.9,720.5 L809.2,729.3 L796.6,731.8 L792.1,723.8 L789.0,717.1 L772.9,703.0 L763.8,689.3 L763.3,681.4 L748.7,683.6 L738.5,689.4 L735.5,683.5 L729.7,682.4 L727.4,686.3 L711.3,689.4 L709.1,701.1 L697.5,702.8 L690.5,701.8 L669.5,676.0 L660.7,651.0 L643.4,654.1 L637.4,639.0 L611.0,569.0 L605.6,545.6 L602.7,538.4 L590.2,523.5 L611.9,501.5 L621.3,493.9 L633.2,490.2 L671.7,509.4 L674.0,504.3 L679.1,509.3 L697.1,519.7 Z", cx: 712, cy: 616 },
    { name: "서초구", d: "M590.2,523.5 L602.7,538.4 L605.6,545.6 L611.0,569.0 L637.4,639.0 L643.4,654.1 L660.7,651.0 L669.5,676.0 L690.5,701.8 L697.5,702.8 L709.1,701.1 L711.3,689.4 L727.4,686.3 L729.7,682.4 L735.5,683.5 L738.5,689.4 L748.7,683.6 L763.3,681.4 L763.8,689.3 L772.9,703.0 L789.0,717.1 L792.1,723.8 L788.0,731.8 L789.2,738.5 L785.7,739.8 L783.2,747.1 L778.9,749.8 L773.1,760.8 L773.0,771.1 L762.9,776.4 L758.6,784.9 L740.5,781.2 L733.1,783.1 L733.9,788.5 L740.1,792.1 L738.6,797.2 L732.8,800.6 L730.6,812.0 L732.2,815.8 L721.4,818.3 L718.8,821.6 L707.8,818.3 L700.2,818.3 L686.5,823.0 L681.0,817.7 L675.4,816.2 L672.7,808.2 L657.0,793.0 L647.6,791.0 L646.5,785.0 L653.2,774.2 L651.5,769.2 L652.2,760.2 L648.3,753.6 L650.4,744.4 L649.6,738.3 L645.2,733.6 L642.2,723.7 L644.9,716.6 L636.6,710.7 L624.2,732.7 L610.9,739.7 L600.5,742.1 L588.3,742.1 L583.4,736.1 L576.8,721.6 L574.5,720.2 L570.0,706.3 L557.0,705.9 L553.0,707.9 L555.2,716.3 L554.3,721.6 L545.6,723.9 L534.7,733.8 L531.9,726.9 L533.6,711.5 L530.5,704.5 L524.9,698.8 L520.1,689.6 L517.8,677.9 L521.0,618.4 L526.2,607.5 L516.8,600.6 L514.8,595.4 L514.4,570.9 L520.0,566.7 L531.7,566.2 L536.5,569.2 L557.1,557.1 L570.8,548.0 L576.4,542.4 L581.3,532.6 L590.2,523.5 Z", cx: 636, cy: 687 },
    { name: "관악구", d: "M517.8,677.9 L520.1,689.6 L524.9,698.8 L530.5,704.5 L533.6,711.5 L531.9,726.9 L534.7,733.8 L520.6,738.0 L516.1,749.2 L505.1,756.9 L499.7,765.6 L492.6,765.8 L476.8,771.7 L476.0,781.9 L473.7,785.3 L464.8,786.2 L462.5,789.8 L449.9,789.9 L431.1,795.8 L424.0,795.8 L417.1,800.7 L414.3,796.2 L414.8,787.6 L407.9,778.8 L397.0,771.3 L396.9,763.9 L391.6,757.7 L378.3,745.0 L376.5,738.0 L363.0,734.9 L357.9,735.1 L357.1,723.6 L353.6,716.2 L355.7,712.2 L350.7,708.3 L342.5,690.1 L348.5,687.0 L351.4,676.9 L345.5,673.2 L346.1,665.0 L324.5,669.9 L321.6,666.8 L330.6,652.8 L337.1,652.8 L354.5,646.1 L363.7,639.4 L380.9,637.8 L386.4,625.2 L389.1,622.6 L397.8,627.9 L405.5,628.4 L409.7,631.1 L422.4,631.0 L435.5,625.4 L446.8,630.5 L451.6,634.6 L458.4,633.0 L469.1,627.4 L468.2,635.1 L471.8,646.0 L469.5,657.3 L491.3,681.8 L506.7,678.2 L517.8,677.9 Z", cx: 433, cy: 706 },
    { name: "동작구", d: "M514.4,570.9 L514.8,595.4 L516.8,600.6 L526.2,607.5 L521.0,618.4 L517.8,677.9 L506.7,678.2 L491.3,681.8 L469.5,657.3 L471.8,646.0 L468.2,635.1 L469.1,627.4 L458.4,633.0 L451.6,634.6 L446.8,630.5 L435.5,625.4 L422.4,631.0 L409.7,631.1 L405.5,628.4 L397.8,627.9 L389.1,622.6 L386.4,625.2 L380.9,637.8 L363.7,639.4 L354.5,646.1 L337.1,652.8 L330.6,652.8 L352.8,618.4 L369.9,614.4 L373.4,601.2 L383.6,569.3 L387.6,568.3 L385.0,558.9 L400.4,560.3 L423.2,554.9 L443.3,547.1 L450.5,554.6 L460.0,561.3 L477.3,568.9 L514.4,570.9 Z", cx: 448, cy: 609 },
    { name: "영등포구", d: "M298.4,456.1 L324.6,474.3 L337.7,480.8 L392.7,496.0 L405.8,498.1 L427.0,518.7 L434.5,525.9 L437.4,536.3 L443.3,547.1 L423.2,554.9 L400.4,560.3 L385.0,558.9 L387.6,568.3 L383.6,569.3 L373.4,601.2 L369.9,614.4 L352.8,618.4 L330.6,652.8 L324.1,650.8 L314.5,640.5 L307.8,617.4 L307.1,598.0 L308.2,584.9 L300.0,572.6 L273.8,556.9 L274.6,540.5 L276.3,531.4 L279.2,528.1 L291.7,521.0 L295.3,514.8 L299.0,515.8 L302.6,507.5 L302.1,499.4 L292.5,476.6 L289.8,476.0 L287.7,467.8 L298.4,456.1 Z", cx: 347, cy: 547 },
    { name: "금천구", d: "M321.6,666.8 L324.5,669.9 L346.1,665.0 L345.5,673.2 L351.4,676.9 L348.5,687.0 L342.5,690.1 L350.7,708.3 L355.7,712.2 L353.6,716.2 L357.1,723.6 L357.9,735.1 L363.0,734.9 L376.5,738.0 L378.3,745.0 L391.6,757.7 L378.9,768.6 L373.3,776.0 L370.4,784.6 L365.8,788.8 L357.1,788.4 L350.0,795.9 L343.7,807.1 L329.5,806.3 L329.3,800.8 L321.4,794.1 L319.8,790.6 L320.4,779.1 L318.6,774.5 L312.3,771.2 L313.4,763.4 L308.7,750.4 L305.2,752.5 L297.7,750.0 L296.7,742.7 L289.9,739.1 L289.8,729.8 L295.7,720.7 L274.8,689.6 L267.1,675.2 L259.4,653.7 L262.5,651.6 L271.9,647.9 L276.6,649.8 L289.2,660.1 L296.7,669.0 L310.4,672.3 L320.3,671.0 L321.6,666.8 Z", cx: 326, cy: 727 },
    { name: "구로구", d: "M143.1,582.5 L153.5,582.7 L160.6,591.8 L170.9,600.1 L180.9,595.4 L179.5,590.8 L190.9,590.4 L191.9,583.3 L200.3,580.9 L203.6,577.0 L210.3,575.6 L216.7,579.6 L222.8,577.5 L227.5,587.3 L233.1,587.3 L234.8,591.6 L241.3,590.7 L248.8,592.9 L256.5,591.2 L259.5,581.8 L271.4,564.4 L273.8,556.9 L300.0,572.6 L308.2,584.9 L307.1,598.0 L307.8,617.4 L314.5,640.5 L324.1,650.8 L330.6,652.8 L321.6,666.8 L320.3,671.0 L310.4,672.3 L296.7,669.0 L289.2,660.1 L276.6,649.8 L271.9,647.9 L262.5,651.6 L268.3,643.9 L265.5,640.5 L258.1,642.7 L258.1,637.5 L245.8,626.3 L238.8,633.7 L230.2,638.2 L221.8,650.0 L215.5,652.1 L212.3,659.1 L207.9,662.9 L196.3,661.6 L193.7,664.9 L192.7,685.1 L178.1,680.8 L168.6,681.9 L159.8,675.1 L153.8,679.1 L142.4,678.5 L136.7,680.6 L131.0,673.9 L131.6,662.7 L130.0,655.2 L131.6,650.3 L140.0,644.4 L138.2,637.7 L126.5,632.9 L118.3,627.8 L114.2,619.1 L115.1,613.4 L121.2,614.9 L128.6,611.3 L131.5,603.5 L135.4,601.3 L138.7,589.9 L137.9,584.1 L143.1,582.5 Z", cx: 220, cy: 624 },
    { name: "강서구", d: "M221.9,382.3 L221.1,393.1 L223.4,397.5 L242.3,408.7 L270.0,432.8 L298.4,456.1 L287.7,467.8 L289.8,476.0 L287.4,476.0 L276.8,463.1 L260.7,465.9 L252.8,463.7 L237.5,452.5 L232.4,473.2 L236.2,483.9 L235.4,497.0 L236.8,517.6 L200.7,523.3 L180.6,527.4 L166.2,497.5 L167.7,493.6 L163.0,481.3 L156.6,481.5 L155.1,474.0 L151.0,470.5 L147.9,481.1 L136.8,484.8 L118.9,484.9 L108.6,482.0 L106.2,477.4 L91.8,478.1 L83.3,485.5 L81.0,493.4 L71.4,499.4 L68.9,488.5 L71.5,482.4 L64.2,481.3 L64.2,475.2 L56.8,473.4 L52.1,467.7 L35.8,468.0 L25.2,459.9 L14.9,460.5 L6.6,446.6 L0.0,439.7 L8.9,439.3 L10.6,435.1 L28.2,420.5 L28.4,413.9 L23.2,404.3 L30.7,405.2 L37.1,401.9 L42.3,395.6 L40.6,390.7 L42.9,385.1 L59.1,373.6 L67.9,374.3 L67.5,364.9 L69.0,357.1 L74.1,356.6 L81.0,341.3 L85.8,339.0 L82.0,332.4 L82.4,327.2 L78.1,318.6 L76.7,310.4 L80.0,302.6 L83.6,301.8 L85.3,293.4 L88.3,291.8 L97.0,294.7 L122.2,322.8 L132.7,333.5 L148.0,340.9 L205.6,379.4 L221.9,382.3 Z", cx: 142, cy: 423 },
    { name: "양천구", d: "M136.8,484.8 L147.9,481.1 L151.0,470.5 L155.1,474.0 L156.6,481.5 L163.0,481.3 L167.7,493.6 L166.2,497.5 L180.6,527.4 L200.7,523.3 L236.8,517.6 L235.4,497.0 L236.2,483.9 L232.4,473.2 L237.5,452.5 L252.8,463.7 L260.7,465.9 L276.8,463.1 L287.4,476.0 L289.8,476.0 L292.5,476.6 L302.1,499.4 L302.6,507.5 L299.0,515.8 L295.3,514.8 L291.7,521.0 L279.2,528.1 L276.3,531.4 L274.6,540.5 L273.8,556.9 L271.4,564.4 L259.5,581.8 L256.5,591.2 L248.8,592.9 L241.3,590.7 L234.8,591.6 L233.1,587.3 L227.5,587.3 L222.8,577.5 L216.7,579.6 L210.3,575.6 L203.6,577.0 L200.3,580.9 L191.9,583.3 L190.9,590.4 L179.5,590.8 L180.9,595.4 L170.9,600.1 L160.6,591.8 L153.5,582.7 L143.1,582.5 L141.2,575.5 L142.6,567.6 L139.3,558.7 L144.9,548.0 L144.2,538.6 L151.9,526.9 L149.1,518.2 L145.0,517.4 L136.0,502.5 L136.8,484.8 Z", cx: 218, cy: 533 },
    { name: "마포구", d: "M330.3,375.5 L326.7,379.8 L334.3,386.1 L370.2,406.2 L384.2,410.5 L390.4,416.4 L386.7,423.5 L386.5,430.0 L411.0,441.2 L421.0,437.2 L459.2,434.1 L463.2,436.6 L469.8,429.9 L473.7,437.3 L470.3,440.5 L472.0,452.1 L475.7,457.6 L470.8,460.7 L466.8,467.8 L462.7,470.3 L459.5,481.5 L445.5,498.0 L430.6,502.1 L427.0,518.7 L405.8,498.1 L392.7,496.0 L337.7,480.8 L324.6,474.3 L298.4,456.1 L270.0,432.8 L242.3,408.7 L223.4,397.5 L221.1,393.1 L221.9,382.3 L222.1,379.4 L231.4,378.6 L235.6,376.3 L240.6,379.8 L246.3,374.0 L252.9,372.9 L265.2,367.4 L268.1,358.7 L267.1,353.7 L272.6,346.3 L275.7,337.1 L280.4,333.2 L297.5,351.6 L306.7,359.5 L311.6,361.7 L318.4,371.3 L326.8,378.5 L330.3,375.5 Z", cx: 346, cy: 432 },
    { name: "서대문구", d: "M443.3,282.0 L448.8,285.9 L450.8,291.9 L448.9,304.6 L452.1,310.2 L459.4,311.1 L457.5,320.4 L462.3,331.5 L462.4,336.0 L458.4,352.0 L465.5,358.6 L456.2,363.9 L450.9,369.5 L482.1,408.6 L489.2,420.4 L482.7,422.5 L474.9,428.6 L469.8,429.9 L463.2,436.6 L459.2,434.1 L421.0,437.2 L411.0,441.2 L386.5,430.0 L386.7,423.5 L390.4,416.4 L384.2,410.5 L370.2,406.2 L334.3,386.1 L326.7,379.8 L330.3,375.5 L352.8,348.0 L361.5,349.4 L360.7,356.7 L376.3,354.0 L379.9,344.4 L385.2,344.5 L390.1,340.8 L389.5,334.6 L392.0,327.6 L403.3,316.7 L420.1,309.8 L422.0,296.3 L424.2,291.3 L430.2,291.3 L435.4,282.1 L443.3,282.0 Z", cx: 416, cy: 374 },
    { name: "은평구", d: "M494.4,208.4 L488.4,214.6 L465.2,219.9 L458.5,229.3 L447.5,230.9 L446.7,240.7 L444.1,248.8 L440.8,252.4 L443.3,257.2 L444.7,269.4 L441.8,279.3 L443.3,282.0 L435.4,282.1 L430.2,291.3 L424.2,291.3 L422.0,296.3 L420.1,309.8 L403.3,316.7 L392.0,327.6 L389.5,334.6 L390.1,340.8 L385.2,344.5 L379.9,344.4 L376.3,354.0 L360.7,356.7 L361.5,349.4 L352.8,348.0 L330.3,375.5 L326.8,378.5 L318.4,371.3 L311.6,361.7 L306.7,359.5 L297.5,351.6 L280.4,333.2 L287.1,324.5 L292.4,324.6 L288.1,332.7 L292.4,340.2 L302.3,340.6 L306.7,338.5 L315.6,340.1 L322.5,336.4 L320.4,328.0 L327.3,320.7 L325.5,313.8 L326.4,307.7 L323.5,296.3 L327.8,294.3 L327.3,275.6 L325.1,267.3 L331.0,249.1 L335.1,247.7 L340.2,239.7 L338.2,233.3 L343.7,226.8 L344.5,220.1 L338.5,207.7 L348.8,197.6 L347.3,189.2 L350.8,182.1 L352.6,172.2 L341.1,166.0 L342.8,162.6 L356.0,170.9 L373.7,168.4 L383.6,162.7 L391.9,155.1 L405.3,153.3 L411.4,149.1 L419.4,135.0 L427.1,130.4 L435.9,128.0 L436.9,132.7 L445.3,140.0 L452.8,139.1 L458.5,147.0 L460.6,157.5 L466.6,160.0 L471.4,174.6 L476.8,175.9 L487.3,189.1 L487.2,195.6 L494.4,208.4 Z", cx: 392, cy: 246 },
    { name: "노원구", d: "M814.5,243.0 L804.5,246.1 L800.4,251.2 L791.7,254.2 L774.9,246.0 L767.0,244.7 L755.8,248.3 L732.5,258.7 L724.4,258.8 L717.6,263.1 L710.1,262.4 L691.4,245.0 L681.3,232.1 L676.3,224.6 L661.0,211.5 L666.9,204.9 L669.4,194.6 L681.8,170.6 L693.2,182.8 L695.4,167.1 L691.6,152.2 L691.2,137.7 L685.1,123.0 L684.5,113.8 L678.6,97.4 L679.3,85.2 L682.5,72.3 L686.0,50.0 L683.2,43.3 L692.4,36.5 L697.7,35.6 L709.0,38.0 L717.5,34.8 L727.7,21.1 L736.1,20.9 L746.7,15.0 L757.3,15.1 L763.3,22.2 L768.0,33.4 L788.8,36.8 L792.0,47.2 L783.4,59.7 L781.3,66.9 L785.6,74.7 L787.6,84.0 L790.3,86.2 L791.1,94.0 L786.8,105.9 L792.1,119.2 L790.7,126.3 L768.2,138.4 L783.8,140.3 L786.7,146.5 L782.5,155.2 L788.3,168.4 L796.4,169.7 L802.2,167.9 L820.1,171.1 L829.4,184.5 L830.5,199.5 L827.1,213.5 L813.5,224.6 L813.4,229.7 L809.3,236.7 L814.5,243.0 Z", cx: 742, cy: 149 },
    { name: "도봉구", d: "M683.2,43.3 L686.0,50.0 L682.5,72.3 L679.3,85.2 L678.6,97.4 L684.5,113.8 L685.1,123.0 L691.2,137.7 L691.6,152.2 L695.4,167.1 L693.2,182.8 L681.8,170.6 L669.4,194.6 L666.9,204.9 L661.0,211.5 L653.8,203.5 L650.2,195.0 L644.3,191.6 L639.9,180.2 L627.3,169.8 L620.3,162.6 L610.2,157.8 L599.2,157.7 L593.5,153.6 L591.9,148.3 L595.1,127.8 L598.1,120.0 L599.3,104.6 L606.1,94.8 L601.6,86.6 L595.0,78.4 L590.3,66.5 L582.5,65.3 L581.7,50.4 L583.2,42.8 L581.2,37.0 L583.1,20.1 L590.4,9.4 L596.2,9.4 L599.9,0.9 L608.1,0.0 L614.7,5.3 L621.4,5.8 L629.0,2.5 L631.7,7.2 L632.9,15.6 L636.4,25.6 L639.4,29.0 L647.5,27.6 L661.6,18.2 L664.6,23.0 L670.9,27.1 L678.9,22.4 L683.2,43.3 Z", cx: 639, cy: 97 },
    { name: "강북구", d: "M581.7,50.4 L582.5,65.3 L590.3,66.5 L595.0,78.4 L601.6,86.6 L606.1,94.8 L599.3,104.6 L598.1,120.0 L595.1,127.8 L591.9,148.3 L593.5,153.6 L599.2,157.7 L610.2,157.8 L620.3,162.6 L627.3,169.8 L639.9,180.2 L644.3,191.6 L650.2,195.0 L653.8,203.5 L661.0,211.5 L676.3,224.6 L681.3,232.1 L673.7,237.8 L666.9,249.5 L657.1,258.7 L649.9,268.1 L634.5,278.2 L634.0,268.6 L625.0,267.6 L615.0,271.8 L607.9,264.3 L597.1,258.8 L587.5,256.2 L582.2,249.9 L579.8,242.4 L580.7,233.7 L561.9,228.1 L553.7,218.1 L547.6,215.3 L545.6,209.2 L541.0,209.2 L527.5,198.9 L525.1,195.5 L528.8,184.5 L521.9,174.3 L525.9,167.1 L522.9,155.6 L516.8,148.2 L513.2,140.2 L513.9,135.1 L526.0,126.9 L533.7,113.3 L544.8,109.6 L546.8,101.0 L547.8,88.0 L545.0,71.7 L542.1,66.2 L547.2,63.5 L556.8,53.0 L570.4,49.2 L581.7,50.4 Z", cx: 588, cy: 175 },
    { name: "성북구", d: "M502.3,211.1 L507.6,204.7 L517.6,201.1 L525.1,195.5 L527.5,198.9 L541.0,209.2 L545.6,209.2 L547.6,215.3 L553.7,218.1 L561.9,228.1 L580.7,233.7 L579.8,242.4 L582.2,249.9 L587.5,256.2 L597.1,258.8 L607.9,264.3 L615.0,271.8 L625.0,267.6 L634.0,268.6 L634.5,278.2 L649.9,268.1 L657.1,258.7 L666.9,249.5 L673.7,237.8 L681.3,232.1 L691.4,245.0 L710.1,262.4 L717.6,263.1 L724.4,258.8 L732.5,258.7 L733.3,285.3 L730.3,277.6 L725.8,277.7 L726.1,285.1 L718.2,289.2 L710.4,290.3 L703.3,302.7 L699.0,301.2 L686.2,306.0 L682.0,302.5 L675.7,317.0 L667.1,317.0 L658.9,320.3 L655.2,332.1 L648.8,336.2 L631.4,359.0 L617.2,372.1 L614.1,369.6 L605.6,370.5 L601.0,360.6 L597.0,359.4 L583.0,364.8 L578.7,359.9 L578.3,350.1 L576.0,345.3 L567.7,338.8 L564.1,328.8 L551.4,329.2 L548.4,332.2 L541.3,331.9 L529.5,328.4 L523.3,324.4 L518.9,318.4 L517.8,308.4 L525.8,307.5 L532.6,302.1 L528.2,284.3 L530.7,273.9 L530.1,261.5 L520.8,255.4 L516.1,237.2 L512.2,231.7 L512.9,217.7 L506.1,218.8 L502.3,211.1 Z", cx: 605, cy: 288 },
    { name: "중랑구", d: "M732.5,258.7 L755.8,248.3 L767.0,244.7 L774.9,246.0 L791.7,254.2 L800.4,251.2 L804.5,246.1 L814.5,243.0 L828.0,243.5 L841.6,252.1 L840.7,257.0 L842.9,270.5 L840.7,279.0 L844.6,282.8 L843.9,292.0 L833.9,305.9 L834.5,308.8 L844.8,320.9 L843.5,323.9 L832.8,326.0 L826.0,338.4 L823.2,352.1 L804.3,354.7 L807.5,360.8 L807.3,371.3 L803.4,379.0 L803.1,385.6 L799.6,388.7 L779.8,397.6 L761.2,392.2 L749.7,390.7 L748.7,372.1 L745.9,362.1 L732.0,339.8 L727.8,317.3 L729.3,311.3 L735.1,302.5 L735.6,297.4 L733.3,285.3 L732.5,258.7 Z", cx: 784, cy: 312 },
    { name: "동대문구", d: "M617.2,372.1 L631.4,359.0 L648.8,336.2 L655.2,332.1 L658.9,320.3 L667.1,317.0 L675.7,317.0 L682.0,302.5 L686.2,306.0 L699.0,301.2 L703.3,302.7 L710.4,290.3 L718.2,289.2 L726.1,285.1 L725.8,277.7 L730.3,277.6 L733.3,285.3 L735.6,297.4 L735.1,302.5 L729.3,311.3 L727.8,317.3 L732.0,339.8 L745.9,362.1 L748.7,372.1 L749.7,390.7 L734.2,426.3 L731.0,424.8 L703.9,419.8 L701.0,418.3 L676.5,395.2 L662.7,387.2 L652.5,387.6 L640.1,395.3 L632.9,396.5 L617.7,391.1 L617.2,372.1 Z", cx: 694, cy: 360 },
    { name: "광진구", d: "M749.7,390.7 L761.2,392.2 L779.8,397.6 L799.6,388.7 L803.1,385.6 L810.8,393.5 L808.9,397.4 L805.6,419.3 L803.6,426.4 L826.2,427.0 L832.1,425.5 L834.1,430.7 L834.1,446.6 L829.7,464.1 L823.7,476.4 L807.4,504.9 L797.9,524.1 L782.3,526.7 L763.3,533.8 L747.3,536.4 L736.0,536.0 L721.9,531.8 L697.1,519.7 L721.6,465.2 L738.0,428.2 L734.2,426.3 L749.7,390.7 Z", cx: 769, cy: 467 },
    { name: "성동구", d: "M617.7,391.1 L632.9,396.5 L640.1,395.3 L652.5,387.6 L662.7,387.2 L676.5,395.2 L701.0,418.3 L703.9,419.8 L731.0,424.8 L734.2,426.3 L738.0,428.2 L721.6,465.2 L697.1,519.7 L679.1,509.3 L674.0,504.3 L671.7,509.4 L633.2,490.2 L621.3,493.9 L611.9,501.5 L597.2,490.1 L584.5,488.1 L581.8,481.2 L582.4,474.8 L584.8,462.5 L589.7,461.1 L602.0,446.5 L603.5,438.6 L608.8,433.9 L616.5,432.9 L618.5,423.0 L624.6,417.5 L625.7,411.4 L618.3,410.9 L617.7,391.1 Z", cx: 660, cy: 453 },
    { name: "용산구", d: "M582.4,474.8 L581.8,481.2 L584.5,488.1 L597.2,490.1 L611.9,501.5 L590.2,523.5 L581.3,532.6 L576.4,542.4 L570.8,548.0 L557.1,557.1 L536.5,569.2 L531.7,566.2 L520.0,566.7 L514.4,570.9 L477.3,568.9 L460.0,561.3 L450.5,554.6 L443.3,547.1 L437.4,536.3 L434.5,525.9 L427.0,518.7 L430.6,502.1 L445.5,498.0 L459.5,481.5 L462.7,470.3 L466.8,467.8 L470.8,460.7 L475.7,457.6 L472.0,452.1 L479.9,444.2 L495.3,444.9 L505.7,447.2 L507.3,441.6 L515.3,446.4 L523.0,447.5 L527.0,445.3 L532.7,452.1 L538.6,452.3 L550.7,465.0 L558.3,456.9 L568.3,457.9 L572.0,455.5 L573.4,468.2 L579.2,475.3 L582.4,474.8 Z", cx: 514, cy: 510 },
    { name: "중구", d: "M617.7,391.1 L618.3,410.9 L625.7,411.4 L624.6,417.5 L618.5,423.0 L616.5,432.9 L608.8,433.9 L603.5,438.6 L602.0,446.5 L589.7,461.1 L584.8,462.5 L582.4,474.8 L579.2,475.3 L573.4,468.2 L572.0,455.5 L568.3,457.9 L558.3,456.9 L550.7,465.0 L538.6,452.3 L532.7,452.1 L527.0,445.3 L523.0,447.5 L515.3,446.4 L507.3,441.6 L505.7,447.2 L495.3,444.9 L479.9,444.2 L472.0,452.1 L470.3,440.5 L473.7,437.3 L469.8,429.9 L474.9,428.6 L482.7,422.5 L489.2,420.4 L482.1,408.6 L487.9,401.8 L497.1,398.7 L508.8,398.6 L535.3,402.0 L554.0,400.2 L565.7,397.5 L599.5,396.9 L610.6,391.1 L617.7,391.1 Z", cx: 552, cy: 426 },
    { name: "종로구", d: "M494.4,208.4 L502.3,211.1 L506.1,218.8 L512.9,217.7 L512.2,231.7 L516.1,237.2 L520.8,255.4 L530.1,261.5 L530.7,273.9 L528.2,284.3 L532.6,302.1 L525.8,307.5 L517.8,308.4 L518.9,318.4 L523.3,324.4 L529.5,328.4 L541.3,331.9 L548.4,332.2 L551.4,329.2 L564.1,328.8 L567.7,338.8 L576.0,345.3 L578.3,350.1 L578.7,359.9 L583.0,364.8 L597.0,359.4 L601.0,360.6 L605.6,370.5 L614.1,369.6 L617.2,372.1 L617.7,391.1 L610.6,391.1 L599.5,396.9 L565.7,397.5 L554.0,400.2 L535.3,402.0 L508.8,398.6 L497.1,398.7 L487.9,401.8 L482.1,408.6 L450.9,369.5 L456.2,363.9 L465.5,358.6 L458.4,352.0 L462.4,336.0 L462.3,331.5 L457.5,320.4 L459.4,311.1 L452.1,310.2 L448.9,304.6 L450.8,291.9 L448.8,285.9 L443.3,282.0 L441.8,279.3 L444.7,269.4 L443.3,257.2 L440.8,252.4 L444.1,248.8 L446.7,240.7 L447.5,230.9 L458.5,229.3 L465.2,219.9 L488.4,214.6 L494.4,208.4 Z", cx: 509, cy: 323 },
]

function abbreviateGuName(name: string): string {
    if (!name.endsWith("구")) return name
    const head = name.slice(0, -1)
    return head.length >= 2 ? head : name
}


/* ──────────────────────────────────────────────────────────────
 * ◆ Main Component ◆
 * ────────────────────────────────────────────────────────────── */
interface Props {
    jsonUrl: string
    scenario: "normal" | "regime_shift"
    showAdminMeta: boolean
}

export default function LandexPulse({
    jsonUrl,
    scenario = "normal",
    showAdminMeta = true,
}: Props) {
    const [state, setState] = useState<FetchState>({ status: "loading" })
    const [refreshing, setRefreshing] = useState(false)
    const [selectedGu, setSelectedGu] = useState<string | null>(null)
    const inflight = useRef<AbortController | null>(null)

    const load = useCallback(async () => {
        if (!jsonUrl) {
            setState({ status: "error", reason: "no jsonUrl prop" })
            return
        }
        inflight.current?.abort()
        const ac = new AbortController()
        inflight.current = ac
        const sep = jsonUrl.includes("?") ? "&" : "?"
        const url = `${jsonUrl}${sep}scenario=${scenario}&_=${Date.now()}`
        try {
            const r = await fetch(url, { cache: "no-store", signal: ac.signal })
            if (!r.ok) {
                setState({ status: "error", reason: `HTTP ${r.status}` })
                return
            }
            const data: PulseData = await r.json()
            if (!data?.gus || !data?.meta) {
                setState({ status: "error", reason: "schema_invalid" })
                return
            }
            setState({ status: "ok", data, fetchedAt: Date.now() })
        } catch (e: any) {
            if (e?.name === "AbortError") return
            setState({ status: "error", reason: e?.message || "fetch failed" })
        }
    }, [jsonUrl, scenario])

    useEffect(() => {
        load()
        return () => inflight.current?.abort()
    }, [load])

    const handleRefresh = useCallback(async () => {
        if (refreshing) return
        setRefreshing(true)
        await load()
        setTimeout(() => setRefreshing(false), 1000)
    }, [load, refreshing])

    const triggerType: LandexTrigger =
        state.status === "ok" ? inferTrigger(state.data) : "normal"
    const isShift = triggerType === "regime_shift"

    const dynamicCardStyle: React.CSSProperties = {
        ...cardStyle,
        borderLeft: `4px solid ${isShift ? C.accent : C.success}`,
    }

    return (
        <div style={dynamicCardStyle}>
            <StatusBar state={state} onRefresh={handleRefresh} refreshing={refreshing} />
            <Header triggerType={triggerType} state={state} />

            <SectionDivider label="META" />
            {state.status === "loading" && <SkeletonGrid n={4} h={56} />}
            {state.status === "error" && <ErrorBox reason={state.reason} stage="meta" />}
            {state.status === "ok" && (
                <MetaBlock
                    data={state.data}
                    fetchedAt={state.fetchedAt}
                    triggerType={triggerType}
                />
            )}

            <SectionDivider label="VISUALIZATION" />
            {state.status === "ok" && (
                <>
                    <SeoulMapInline
                        gus={state.data.gus}
                        selectedGu={selectedGu}
                        onSelect={setSelectedGu}
                    />
                    <GuGrid
                        gus={state.data.gus}
                        selectedGu={selectedGu}
                        onSelect={setSelectedGu}
                    />
                    {selectedGu && (
                        <GuDetailExpand
                            gu={state.data.gus.find((g) => g.gu_name === selectedGu)!}
                        />
                    )}
                </>
            )}

            <SectionDivider label="RANKING" />
            {state.status === "ok" && <RankingTable gus={state.data.gus} />}

            <Footer />
        </div>
    )
}


/* ──────────────────────────────────────────────────────────────
 * ◆ Subviews ◆
 * ────────────────────────────────────────────────────────────── */

function StatusBar({ state, onRefresh, refreshing }: {
    state: FetchState; onRefresh: () => void; refreshing: boolean
}) {
    const isOk = state.status === "ok"
    const isErr = state.status === "error"
    const dot = isOk ? C.success : isErr ? C.danger : C.warn
    const label = refreshing ? "REFRESHING…" : isOk ? "LIVE" : isErr ? "ERROR" : "LOADING"
    return (
        <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            paddingBottom: 14, marginBottom: 18,
            borderBottom: `1px solid ${C.border}`,
        }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{
                    width: 6, height: 6, borderRadius: "50%",
                    background: dot, boxShadow: `0 0 6px ${dot}88`,
                }} />
                <span style={{
                    color: C.textSecondary, fontSize: 10, fontWeight: 700,
                    fontFamily: FONT_MONO, letterSpacing: "0.12em",
                }}>{label}</span>
            </div>
            <button onClick={onRefresh} disabled={refreshing} style={{
                padding: "4px 10px", borderRadius: R.sm,
                background: "transparent",
                border: `1px solid ${C.border}`,
                color: refreshing ? C.textDisabled : C.textSecondary,
                fontSize: 10, fontFamily: FONT, fontWeight: 700,
                letterSpacing: "1.5px", textTransform: "uppercase",
                cursor: refreshing ? "not-allowed" : "pointer",
            }}>REFRESH</button>
        </div>
    )
}

function Header({ triggerType, state }: { triggerType: LandexTrigger; state: FetchState }) {
    const headers = TRIGGER_HEADERS[triggerType]
    const isShift = triggerType === "regime_shift"
    const totalChanged = state.status === "ok"
        ? state.data.meta.detail.degraded_count + state.data.meta.detail.gained_count
        : 0
    return (
        <div style={{ marginBottom: 18 }}>
            <div style={{
                color: C.textTertiary, fontSize: 10, fontFamily: FONT_MONO,
                letterSpacing: "0.18em", marginBottom: 4,
            }}>
                ESTATE · OPERATOR
            </div>
            <div style={{
                color: isShift ? C.accent : C.success,
                fontSize: 24, fontWeight: 700, fontFamily: FONT_SERIF,
                letterSpacing: "-0.01em", lineHeight: 1.2,
            }}>
                {headers.title}
            </div>
            <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 4 }}>
                {headers.subtitle(totalChanged)}
            </div>
        </div>
    )
}

function SectionDivider({ label }: { label: string }) {
    return (
        <div style={{
            display: "flex", alignItems: "center", gap: 10,
            margin: "20px 0 12px",
        }}>
            <span style={{
                color: C.textTertiary, fontSize: 10, fontWeight: 700,
                fontFamily: FONT, letterSpacing: "1.5px",
                textTransform: "uppercase",
            }}>{label}</span>
            <div style={{ flex: 1, height: 1, background: C.border }} />
        </div>
    )
}

function MetaBlock({ data, fetchedAt, triggerType }: {
    data: PulseData; fetchedAt: number; triggerType: LandexTrigger
}) {
    const m = data.meta
    const now = Date.now()
    const fetchedMin = Math.floor((now - fetchedAt) / 60000)
    const lastShiftMin = minutesSince(m.primary.last_shift_at, now)

    const regimeMap: Record<string, string> = {
        bull: "BULL · 강세",
        bear: "BEAR · 약세",
        neutral: "NEUTRAL · 중립",
    }

    const primary: Array<[string, string, "ok" | "warn" | "neutral", string?]> = [
        ["CURRENT_REGIME", regimeMap[m.primary.current_regime] || "—",
            m.primary.current_regime === "bull" ? "ok" : m.primary.current_regime === "bear" ? "warn" : "neutral",
            "REGIME"],
        ["TOP_GAINER",
            `${m.primary.top_gainer.gu_name} +${m.primary.top_gainer.change_pct}%`,
            "ok", undefined],
        ["TOP_LOSER",
            `${m.primary.top_loser.gu_name} ${m.primary.top_loser.change_pct}%`,
            "warn", undefined],
        ["LAST_SHIFT", formatFreshness(lastShiftMin), "neutral", undefined],
    ]

    const detail: Array<[string, string, "ok" | "warn" | "neutral", string?]> = [
        ["DEGRADED_COUNT", String(m.detail.degraded_count),
            m.detail.degraded_count === 0 ? "ok" : "warn", undefined],
        ["GAINED_COUNT", String(m.detail.gained_count),
            m.detail.gained_count > 0 ? "ok" : "neutral", undefined],
        ["GEI_S4_COUNT", String(m.detail.gei_s4_count),
            m.detail.gei_s4_count === 0 ? "ok" : "warn", "GEI_STAGE"],
        ["AVG_LANDEX", String(m.detail.avg_landex), "neutral", "LANDEX"],
        ["DATA_FRESHNESS", formatFreshness(m.detail.data_freshness_min),
            m.detail.data_freshness_min <= 60 ? "ok" : "warn", undefined],
    ]

    return (
        <>
            {/* Primary 4셀 */}
            <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(170px, 1fr))",
                gap: 8, marginBottom: 12,
            }}>
                {primary.map(([k, v, tone, term]) => (
                    <div key={k} style={primaryCellStyle}>
                        <CellLabel text={k} termKey={term} />
                        <div style={{
                            color: tone === "ok" ? C.success : tone === "warn" ? C.warn : C.textPrimary,
                            fontSize: 14, fontFamily: FONT_MONO, fontWeight: 500,
                            marginTop: 4, wordBreak: "break-all",
                        }}>{v}</div>
                    </div>
                ))}
            </div>
            {/* Detail 5셀 */}
            <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
                gap: 4,
            }}>
                {detail.map(([k, v, tone, term]) => (
                    <div key={k} style={detailCellStyle}>
                        <CellLabel text={k} termKey={term} small />
                        <div style={{
                            color: tone === "ok" ? C.success : tone === "warn" ? C.warn : C.textSecondary,
                            fontSize: 11, fontFamily: FONT_MONO, marginTop: 2,
                        }}>{v}</div>
                    </div>
                ))}
            </div>
        </>
    )
}

function CellLabel({ text, termKey, small }: { text: string; termKey?: string; small?: boolean }) {
    const style: React.CSSProperties = {
        color: C.textTertiary,
        fontSize: small ? 9 : 10,
        fontWeight: small ? 500 : 600,
        fontFamily: FONT, letterSpacing: "1.5px",
        textTransform: "uppercase",
    }
    if (!termKey) return <div style={style}>{text}</div>
    return (
        <div style={style}>
            <TermTooltip termKey={termKey}><span>{text}</span></TermTooltip>
        </div>
    )
}

function SeoulMapInline({ gus, selectedGu, onSelect }: {
    gus: Gu[]; selectedGu: string | null; onSelect: (gu: string | null) => void
}) {
    const [hovered, setHovered] = useState<string | null>(null)
    const byGu: Record<string, Gu> = {}
    gus.forEach((g) => { byGu[g.gu_name] = g })

    const tooltipGu = hovered ?? selectedGu
    const tooltip = tooltipGu ? byGu[tooltipGu] : undefined

    return (
        <div style={{
            position: "relative", width: "100%",
            aspectRatio: "1000 / 823",
            maxHeight: 720,
            background: C.bgElevated, borderRadius: R.lg,
            border: `1px solid ${C.border}`,
            overflow: "hidden",
            marginTop: 20, marginBottom: 24,
        }}>
            <svg viewBox={SEOUL_VIEWBOX} preserveAspectRatio="xMidYMid meet"
                style={{ width: "100%", height: "100%", display: "block" }}>
                <rect x="0" y="0" width="1000" height="823" fill={C.bgElevated} />
                {SEOUL_PATHS.map(({ name, d, cx, cy }) => {
                    const g = byGu[name]
                    const grade = g?.grade
                    const baseFill = grade ? GRADE_COLORS[grade] : C.textTertiary
                    const isHovered = hovered === name
                    const isSelected = selectedGu === name
                    const fillOpacity = grade
                        ? isHovered ? 0.65 : isSelected ? 0.55 : 0.32
                        : 0.10
                    const stroke = isSelected ? C.accent : isHovered ? C.accentBright : C.borderStrong
                    const strokeWidth = isSelected ? 2.5 : isHovered ? 1.8 : 0.8
                    const filter = (isHovered || isSelected)
                        ? `drop-shadow(0 0 6px ${C.accentSoft})`
                        : "none"
                    const showVal = (isHovered || isSelected) && g
                    const labelY = showVal ? cy - 11 : cy
                    const labelOutline: React.CSSProperties = {
                        paintOrder: "stroke fill",
                        stroke: "rgba(10,9,8,0.78)",
                        strokeWidth: 4,
                        strokeLinejoin: "round",
                    } as React.CSSProperties
                    return (
                        <g key={name}
                            style={{ cursor: "pointer", transition: "filter 180ms ease" }}
                            onMouseEnter={() => setHovered(name)}
                            onMouseLeave={() => setHovered(null)}
                            onClick={() => onSelect(isSelected ? null : name)}
                        >
                            <path d={d} fill={baseFill} fillOpacity={fillOpacity}
                                stroke={stroke} strokeWidth={strokeWidth} strokeLinejoin="round"
                                style={{
                                    transition: "fill-opacity 180ms ease, stroke 180ms ease, stroke-width 180ms ease, filter 180ms ease",
                                    filter,
                                }} />
                            <text x={cx} y={labelY} textAnchor="middle" dominantBaseline="central"
                                fontFamily={FONT}
                                fontSize={isHovered || isSelected ? 26 : 22}
                                fontWeight={isHovered || isSelected ? 700 : 500}
                                fill={grade ? C.textPrimary : C.textTertiary}
                                style={{ pointerEvents: "none", transition: "font-size 180ms ease", ...labelOutline }}>
                                {abbreviateGuName(name)}
                            </text>
                            {showVal && (
                                <text x={cx} y={cy + 14} textAnchor="middle" dominantBaseline="central"
                                    fontFamily={FONT_MONO} fontSize={18} fontWeight={700}
                                    fill={C.textPrimary}
                                    style={{ pointerEvents: "none", ...labelOutline }}>
                                    {g!.landex.toFixed(0)}
                                </text>
                            )}
                        </g>
                    )
                })}
            </svg>

            {tooltip && (
                <div style={{
                    position: "absolute", top: 10, right: 10,
                    minWidth: 180, padding: "8px 12px",
                    background: C.bgInput,
                    border: `1px solid ${C.borderStrong}`,
                    borderRadius: R.sm,
                    boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
                    pointerEvents: "none",
                }}>
                    <div style={{
                        color: C.textPrimary, fontFamily: FONT_SERIF, fontWeight: 700,
                        fontSize: 14, marginBottom: 2,
                    }}>{tooltip.gu_name}</div>
                    <div style={{
                        color: C.textSecondary, fontFamily: FONT_MONO, fontSize: 11,
                    }}>
                        LANDEX {tooltip.landex.toFixed(1)}
                        <span style={{
                            marginLeft: 8, fontWeight: 700,
                            color: GRADE_COLORS[tooltip.grade],
                        }}>{tooltip.grade}</span>
                    </div>
                    <div style={{
                        color: C.textTertiary, fontFamily: FONT_MONO, fontSize: 10, marginTop: 2,
                    }}>
                        GEI {tooltip.gei.toFixed(0)} · S{tooltip.stage}
                    </div>
                </div>
            )}

            {/* 범례 — 좌하단 */}
            <div style={{
                position: "absolute", bottom: 10, left: 10,
                display: "flex", gap: 10,
                padding: "5px 10px",
                background: `${C.bgInput}E0`,
                border: `1px solid ${C.border}`,
                borderRadius: R.sm,
                fontFamily: FONT, fontSize: 10,
                fontWeight: 600, color: C.textSecondary,
                letterSpacing: "0.10em",
            }}>
                {(["HOT", "WARM", "NEUT", "COOL", "AVOID"] as GradeLabel[]).map((g) => (
                    <span key={g} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                        <span style={{
                            width: 10, height: 10, borderRadius: 2,
                            background: GRADE_COLORS[g], opacity: 0.6,
                            border: `1px solid ${GRADE_COLORS[g]}`,
                        }} />
                        {g}
                    </span>
                ))}
            </div>
        </div>
    )
}

function GuGrid({ gus, selectedGu, onSelect }: {
    gus: Gu[]; selectedGu: string | null; onSelect: (gu: string | null) => void
}) {
    return (
        <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(110px, 1fr))",
            gap: 6,
        }}>
            {gus.map((g) => {
                const color = GRADE_COLORS[g.grade] || C.textTertiary
                const selected = selectedGu === g.gu_name
                return (
                    <button
                        key={g.gu_name}
                        onClick={() => onSelect(selected ? null : g.gu_name)}
                        style={{
                            padding: "10px 12px",
                            borderRadius: R.md,
                            border: `1px solid ${selected ? C.accent : C.border}`,
                            background: `${color}40`,  // alpha ~25% (다크 위 노출)
                            color: C.textPrimary,
                            fontFamily: FONT, cursor: "pointer",
                            textAlign: "left",
                            transition: "all 0.15s ease",
                        }}
                    >
                        <div style={{
                            fontSize: 12, fontWeight: 700,
                        }}>{g.gu_name}</div>
                        <div style={{
                            fontSize: 11, fontFamily: FONT_MONO,
                            marginTop: 2, color: C.textSecondary,
                        }}>{g.landex.toFixed(1)} · {g.grade}</div>
                    </button>
                )
            })}
        </div>
    )
}

function GuDetailExpand({ gu }: { gu: Gu }) {
    const isHotOrWarm = gu.grade === "HOT" || gu.grade === "WARM"
    const radar = gu.detail.radar
    const features = gu.detail.feature_contributions
    return (
        <div style={{
            marginTop: 14, padding: "16px 18px",
            background: C.bgElevated, borderRadius: R.lg,
            border: `1px solid ${GRADE_COLORS[gu.grade]}40`,
        }}>
            {/* Header — 구 명 + LANDEX 큰 점수 */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
                <div>
                    <div style={{ color: C.textTertiary, fontSize: 10, fontFamily: FONT_MONO, letterSpacing: "0.10em" }}>
                        SELECTED · GU
                    </div>
                    <div style={{ color: C.textPrimary, fontSize: 22, fontWeight: 700, fontFamily: FONT_SERIF, marginTop: 2 }}>
                        {gu.gu_name}
                    </div>
                </div>
                <div style={{ textAlign: "right" }}>
                    <div style={{ color: C.textTertiary, fontSize: 10, fontFamily: FONT, letterSpacing: "1.5px", textTransform: "uppercase" }}>
                        <TermTooltip termKey="LANDEX"><span>LANDEX</span></TermTooltip>
                    </div>
                    <div style={{
                        color: isHotOrWarm ? C.accent : C.textPrimary,
                        fontSize: 28, fontWeight: 800, fontFamily: FONT_MONO,
                    }}>{gu.landex.toFixed(1)}</div>
                </div>
            </div>

            {/* chips: 등급 + Stage */}
            <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                <span style={{
                    padding: "3px 10px", borderRadius: R.pill,
                    background: `${GRADE_COLORS[gu.grade]}25`,
                    border: `1px solid ${GRADE_COLORS[gu.grade]}60`,
                    color: GRADE_COLORS[gu.grade],
                    fontSize: 11, fontFamily: FONT, fontWeight: 700,
                }}>
                    <TermTooltip termKey={`GRADE_${gu.grade}`}><span>{gu.grade}</span></TermTooltip>
                </span>
                <span style={{
                    padding: "3px 10px", borderRadius: R.pill,
                    background: `${STAGE_COLORS[gu.stage]}25`,
                    border: `1px solid ${STAGE_COLORS[gu.stage] === "transparent" ? C.border : STAGE_COLORS[gu.stage]}60`,
                    color: STAGE_COLORS[gu.stage] === "transparent" ? C.textSecondary : STAGE_COLORS[gu.stage],
                    fontSize: 11, fontFamily: FONT, fontWeight: 700,
                }}>
                    <TermTooltip termKey="GEI_STAGE"><span>S{gu.stage}</span></TermTooltip>
                </span>
            </div>

            {/* Radar — 5축 simple ascii */}
            <div style={{ marginTop: 14 }}>
                <div style={{ color: C.textTertiary, fontSize: 10, fontFamily: FONT, letterSpacing: "1.5px", textTransform: "uppercase", marginBottom: 6 }}>
                    Score Radar
                </div>
                <ScoreRadar radar={radar} />
            </div>

            {/* Features — 피처 기여도 */}
            <div style={{ marginTop: 14 }}>
                <div style={{ color: C.textTertiary, fontSize: 10, fontFamily: FONT, letterSpacing: "1.5px", textTransform: "uppercase", marginBottom: 6 }}>
                    <TermTooltip termKey="FEATURE_CONTRIB"><span>Feature Contributions</span></TermTooltip>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    {features.map((f) => (
                        <FeatureBar key={f.feature} feat={f} />
                    ))}
                </div>
            </div>

            {/* Timeseries — mini sparkline */}
            <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <Sparkline
                    label={<TermTooltip termKey="WEEKLY_PRICE_INDEX"><span>주간 매매가격지수</span></TermTooltip>}
                    points={gu.detail.timeseries.weekly_price_index}
                />
                <Sparkline
                    label={<TermTooltip termKey="MONTHLY_UNSOLD"><span>월간 미분양</span></TermTooltip>}
                    points={gu.detail.timeseries.monthly_unsold}
                />
            </div>

            {/* 강점 / 약점 */}
            <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <StrengthsList strengths={gu.detail.strengths} />
                <WeaknessesList weaknesses={gu.detail.weaknesses} />
            </div>
        </div>
    )
}

function ScoreRadar({ radar }: { radar: { v: number; d: number; s: number; c: number; r: number } }) {
    const axes: Array<[string, number, string]> = [
        ["V", radar.v, "V_SCORE"],
        ["D", radar.d, "D_SCORE"],
        ["S", radar.s, "S_SCORE"],
        ["C", radar.c, "C_SCORE"],
        ["R", radar.r, "R_SCORE"],
    ]
    return (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 8 }}>
            {axes.map(([axis, val, term]) => (
                <div key={axis} style={{
                    background: C.bgInput, borderRadius: R.sm,
                    border: `1px solid ${C.border}`, padding: "6px 8px",
                }}>
                    <div style={{ color: C.textTertiary, fontSize: 10, fontFamily: FONT, fontWeight: 600 }}>
                        <TermTooltip termKey={term}><span>{axis}</span></TermTooltip>
                    </div>
                    <div style={{
                        color: val >= 70 ? C.success : val >= 40 ? C.textPrimary : C.warn,
                        fontSize: 14, fontFamily: FONT_MONO, fontWeight: 600,
                        marginTop: 2,
                    }}>{val.toFixed(1)}</div>
                </div>
            ))}
        </div>
    )
}

function FeatureBar({ feat }: { feat: FeatureContrib }) {
    const isPositive = feat.sign === "+"
    const widthPct = Math.min(100, feat.weight * 100 * 3)  // 0.3 weight ≈ 90%
    return (
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{
                color: C.textSecondary, fontSize: 11, fontFamily: FONT_MONO,
                width: 180, flexShrink: 0,
            }}>{feat.feature}</div>
            <div style={{ flex: 1, height: 6, background: C.bgInput, borderRadius: 3, overflow: "hidden" }}>
                <div style={{
                    width: `${widthPct}%`, height: "100%",
                    background: isPositive ? C.success : C.danger,
                    transition: "width 0.2s",
                }} />
            </div>
            <div style={{
                color: isPositive ? C.success : C.danger,
                fontSize: 11, fontFamily: FONT_MONO, fontWeight: 700, width: 60, textAlign: "right",
            }}>{feat.sign}{feat.weight.toFixed(3)}</div>
        </div>
    )
}

function Sparkline({ label, points }: { label: React.ReactNode; points: SeriesPoint[] }) {
    if (!points || points.length < 2) {
        return <div style={{ color: C.textTertiary, fontSize: 11, fontFamily: FONT }}>{label}: —</div>
    }
    const values = points.map((p) => p.value)
    const min = Math.min(...values)
    const max = Math.max(...values)
    const range = max - min || 1
    const w = 200, h = 40
    const path = points.map((p, i) => {
        const x = (i / (points.length - 1)) * w
        const y = h - ((p.value - min) / range) * h
        return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`
    }).join(" ")
    const lastVal = values[values.length - 1]
    const firstVal = values[0]
    const trend = lastVal > firstVal ? C.success : lastVal < firstVal ? C.danger : C.textSecondary
    return (
        <div style={{
            background: C.bgInput, borderRadius: R.sm,
            border: `1px solid ${C.border}`, padding: "6px 8px",
        }}>
            <div style={{
                color: C.textTertiary, fontSize: 10, fontFamily: FONT, fontWeight: 600,
                letterSpacing: "1.5px", textTransform: "uppercase",
            }}>{label}</div>
            <svg width={w} height={h} style={{ marginTop: 4, display: "block" }}>
                <path d={path} fill="none" stroke={trend} strokeWidth={1.5} />
            </svg>
            <div style={{
                color: trend, fontSize: 11, fontFamily: FONT_MONO, marginTop: 2,
            }}>{firstVal.toFixed(1)} → {lastVal.toFixed(1)}</div>
        </div>
    )
}

function StrengthsList({ strengths }: { strengths: string[] }) {
    return (
        <div>
            <div style={{ color: C.success, fontSize: 10, fontFamily: FONT, letterSpacing: "1.5px", textTransform: "uppercase", fontWeight: 700, marginBottom: 4 }}>
                Strengths
            </div>
            <ul style={{ margin: 0, paddingLeft: 16, color: C.textSecondary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5 }}>
                {strengths.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
        </div>
    )
}

function WeaknessesList({ weaknesses }: { weaknesses: string[] }) {
    return (
        <div>
            <div style={{ color: C.warn, fontSize: 10, fontFamily: FONT, letterSpacing: "1.5px", textTransform: "uppercase", fontWeight: 700, marginBottom: 4 }}>
                Weaknesses
            </div>
            <ul style={{ margin: 0, paddingLeft: 16, color: C.textSecondary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5 }}>
                {weaknesses.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
        </div>
    )
}

function RankingTable({ gus }: { gus: Gu[] }) {
    const sorted = [...gus].sort((a, b) => b.landex - a.landex)
    const headers: Array<[string, string?]> = [
        ["#", undefined],
        ["구", undefined],
        ["LANDEX↓", "LANDEX"],
        ["등급", undefined],
        ["GEI", undefined],
        ["Stage", "GEI_STAGE"],
        ["V", "V_SCORE"],
        ["D", "D_SCORE"],
        ["S", "S_SCORE"],
        ["C", "C_SCORE"],
    ]
    return (
        <div style={{
            background: C.bgElevated, borderRadius: R.md,
            border: `1px solid ${C.border}`, overflow: "hidden",
        }}>
            <div style={{
                display: "grid",
                gridTemplateColumns: "30px 1fr 70px 60px 50px 50px 45px 45px 45px 45px",
                gap: 6, padding: "8px 12px",
                borderBottom: `1px solid ${C.border}`,
                background: C.bgInput,
            }}>
                {headers.map(([h, term]) => (
                    <div key={h} style={{
                        color: C.textTertiary, fontSize: 10, fontFamily: FONT,
                        letterSpacing: "1.5px", textTransform: "uppercase", fontWeight: 700,
                    }}>
                        {term ? <TermTooltip termKey={term}><span>{h}</span></TermTooltip> : h}
                    </div>
                ))}
            </div>
            {sorted.map((g, i) => (
                <div key={g.gu_name} style={{
                    display: "grid",
                    gridTemplateColumns: "30px 1fr 70px 60px 50px 50px 45px 45px 45px 45px",
                    gap: 6, padding: "6px 12px",
                    borderBottom: i < sorted.length - 1 ? `1px solid ${C.border}` : "none",
                    fontFamily: FONT_MONO, fontSize: 11,
                }}>
                    <div style={{ color: C.textTertiary }}>{i + 1}</div>
                    <div style={{ color: C.textPrimary, fontFamily: FONT, fontWeight: 600 }}>{g.gu_name}</div>
                    <div style={{ color: g.grade === "HOT" || g.grade === "WARM" ? C.accent : C.textPrimary, fontWeight: 700 }}>
                        {g.landex.toFixed(1)}
                    </div>
                    <div style={{ color: GRADE_COLORS[g.grade] }}>{g.grade}</div>
                    <div style={{ color: C.textSecondary }}>{g.gei.toFixed(0)}</div>
                    <div style={{ color: STAGE_COLORS[g.stage] === "transparent" ? C.textTertiary : STAGE_COLORS[g.stage] }}>
                        S{g.stage}
                    </div>
                    <div style={{ color: C.textSecondary }}>{g.v_score.toFixed(0)}</div>
                    <div style={{ color: C.textSecondary }}>{g.d_score.toFixed(0)}</div>
                    <div style={{ color: C.textSecondary }}>{g.s_score.toFixed(0)}</div>
                    <div style={{ color: C.textSecondary }}>{g.c_score.toFixed(0)}</div>
                </div>
            ))}
        </div>
    )
}

function ErrorBox({ reason, stage }: { reason: string; stage: string }) {
    return (
        <div style={{
            padding: "10px 12px", borderRadius: R.md,
            background: `${C.danger}10`, border: `1px solid ${C.danger}40`,
        }}>
            <div style={{
                color: C.danger, fontSize: 11, fontWeight: 800,
                fontFamily: FONT_MONO, letterSpacing: "0.10em", marginBottom: 4,
            }}>
                {stage.toUpperCase()} · LOAD FAILED
            </div>
            <div style={{
                color: C.textSecondary, fontSize: 12, fontFamily: FONT_MONO,
                wordBreak: "break-all",
            }}>{reason}</div>
        </div>
    )
}

function SkeletonGrid({ n, h }: { n: number; h: number }) {
    return (
        <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(170px, 1fr))",
            gap: 8,
        }}>
            {Array.from({ length: n }).map((_, i) => (
                <div key={i} style={{
                    height: h, borderRadius: R.md,
                    background: C.bgElevated, border: `1px solid ${C.border}`,
                    backgroundImage: `linear-gradient(90deg, ${C.bgElevated} 0%, ${C.bgInput} 50%, ${C.bgElevated} 100%)`,
                    backgroundSize: "200% 100%",
                    animation: "estateSkel 1.4s ease-in-out infinite",
                }} />
            ))}
        </div>
    )
}

function Footer() {
    return (
        <div style={{
            marginTop: 18, paddingTop: 14,
            borderTop: `1px solid ${C.border}`,
            display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
            <span style={{ color: C.textTertiary, fontSize: 10, fontFamily: FONT_MONO, letterSpacing: "0.10em" }}>
                ESTATE · INTERNAL
            </span>
            <span style={{ color: C.textTertiary, fontSize: 10, fontFamily: FONT_MONO, letterSpacing: "0.10em" }}>
                v1.1 · ENCRYPTED
            </span>
        </div>
    )
}


/* ──────────────────────────────────────────────────────────────
 * ◆ TermTooltip — 인라인 컴포넌트 (T31 Framer self-contained) ◆
 * P4: ChangeFeed 등 다른 컴포넌트도 사용 시 estate/components/shared 분리 검토.
 * ────────────────────────────────────────────────────────────── */
function TermTooltip({ termKey, children }: { termKey: string; children: React.ReactNode }) {
    const [show, setShow] = useState(false)
    const term = TERMS[termKey]
    if (!term) return <>{children}</>
    return (
        <span
            onMouseEnter={() => setShow(true)}
            onMouseLeave={() => setShow(false)}
            onFocus={() => setShow(true)}
            onBlur={() => setShow(false)}
            tabIndex={0}
            style={{
                position: "relative", display: "inline-block",
                borderBottom: `1px dotted ${C.textTertiary}`,
                cursor: "help", outline: "none",
            }}
        >
            {children}
            {show && (
                <div style={{
                    position: "absolute", top: "calc(100% + 6px)", left: 0,
                    minWidth: 240, maxWidth: 360, zIndex: 100,
                    padding: "10px 12px", borderRadius: R.md,
                    background: C.bgElevated, border: `1px solid ${C.borderStrong}`,
                    boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                    fontFamily: FONT, fontSize: 12, lineHeight: 1.5,
                    whiteSpace: "normal",
                    pointerEvents: "none",
                }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                        <span style={{
                            color: C.textPrimary, fontFamily: FONT_SERIF, fontWeight: 700, fontSize: 13,
                        }}>{term.label}</span>
                        {term.l3 && (
                            <span style={{
                                color: C.accent, fontSize: 9, fontFamily: FONT,
                                letterSpacing: "1.5px", fontWeight: 800, textTransform: "uppercase",
                                padding: "1px 6px", borderRadius: R.pill,
                                border: `1px solid ${C.accent}60`,
                            }}>L3</span>
                        )}
                    </div>
                    <div style={{ color: C.textSecondary }}>{term.definition}</div>
                    {term.stages && (
                        <div style={{ marginTop: 6, paddingTop: 6, borderTop: `1px solid ${C.border}` }}>
                            {Object.entries(term.stages).map(([k, v]) => (
                                <div key={k} style={{ fontSize: 11, color: C.textTertiary }}>
                                    <span style={{ fontFamily: FONT_MONO, color: C.textSecondary }}>{k}</span>: {v}
                                </div>
                            ))}
                        </div>
                    )}
                    {term.values && (
                        <div style={{ marginTop: 6, paddingTop: 6, borderTop: `1px solid ${C.border}` }}>
                            {Object.entries(term.values).map(([k, v]) => (
                                <div key={k} style={{ fontSize: 11, color: C.textTertiary }}>
                                    <span style={{ fontFamily: FONT_MONO, color: C.textSecondary }}>{k}</span>: {v}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </span>
    )
}


/* ──────────────────────────────────────────────────────────────
 * ◆ Styles ◆
 * ────────────────────────────────────────────────────────────── */
const cardStyle: React.CSSProperties = {
    width: "100%", maxWidth: 1080,
    background: C.bgCard, borderRadius: 20,
    border: `1px solid ${C.border}`,
    boxShadow: `0 0 0 1px rgba(184,134,77,0.06), 0 12px 40px rgba(0,0,0,0.4)`,
    padding: "24px 26px",
    fontFamily: FONT, color: C.textPrimary,
}

const primaryCellStyle: React.CSSProperties = {
    background: C.bgElevated, borderRadius: R.md,
    border: `1px solid ${C.border}`,
    padding: "10px 12px",
}

const detailCellStyle: React.CSSProperties = {
    background: C.bgElevated, borderRadius: R.sm,
    border: `1px solid ${C.border}`,
    padding: "5px 8px",
}

/* skeleton keyframes */
if (typeof document !== "undefined" && !document.getElementById("estate-skel-kf")) {
    const s = document.createElement("style")
    s.id = "estate-skel-kf"
    s.textContent = `@keyframes estateSkel { 0%{background-position:200% 0} 100%{background-position:-200% 0} }`
    document.head.appendChild(s)
}

LandexPulse.defaultProps = {
    jsonUrl: ESTATE_LANDEX_PULSE_URL,
    scenario: "normal",
    showAdminMeta: true,
}

addPropertyControls(LandexPulse, {
    jsonUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: ESTATE_LANDEX_PULSE_URL,
        description: "/api/estate/landex-pulse endpoint",
    },
    scenario: {
        type: ControlType.Enum,
        title: "Scenario (P1 Mock)",
        defaultValue: "normal",
        options: ["normal", "regime_shift"],
        optionTitles: ["Normal", "Regime Shift"],
        description: "P1 Mock 검증 토글",
    },
    showAdminMeta: {
        type: ControlType.Boolean,
        title: "Admin Meta",
        defaultValue: true,
    },
})

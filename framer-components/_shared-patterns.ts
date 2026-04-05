/**
 * VERITY Framer 공통 패턴 참조 파일
 *
 * Framer Code Components는 단일 파일 제약으로 import가 불가하므로,
 * 각 컴포넌트에 필요한 패턴을 이 파일에서 복사해 사용합니다.
 * 이 파일 자체는 Framer에 등록하지 않습니다.
 */

/* ── NaN/Infinity Sanitize (표준) ── */
export function sanitizeJson(txt: string): any {
    return JSON.parse(
        txt
            .replace(/\bNaN\b/g, "null")
            .replace(/\bInfinity\b/g, "null")
            .replace(/-null/g, "null"),
    )
}

/* ── Sparkline SVG (표준) ── */
export function Sparkline({
    data,
    width = 60,
    height = 24,
    color = "#888",
}: {
    data: number[]
    width?: number
    height?: number
    color?: string
}) {
    if (!data || data.length < 2) return null
    const min = Math.min(...data)
    const max = Math.max(...data)
    const range = max - min || 1
    const points = data
        .map(
            (v, i) =>
                `${(i / (data.length - 1)) * width},${height - ((v - min) / range) * height}`,
        )
        .join(" ")
    return (
        <svg width={width} height={height} style={{ display: "block" }}>
            <polyline
                points={points}
                fill="none"
                stroke={color}
                strokeWidth={1.5}
                strokeLinejoin="round"
                strokeLinecap="round"
            />
        </svg>
    )
}

/* ── RingGauge SVG (표준) ── */
export function RingGauge({
    value,
    label,
    size = 56,
    color,
}: {
    value: number
    label: string
    size?: number
    color: string
}) {
    const r = (size - 6) / 2
    const circ = 2 * Math.PI * r
    const offset = circ * (1 - Math.min(value, 100) / 100)
    return (
        <div
            style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 4,
            }}
        >
            <svg
                width={size}
                height={size}
                style={{ transform: "rotate(-90deg)" }}
            >
                <circle
                    cx={size / 2}
                    cy={size / 2}
                    r={r}
                    fill="none"
                    stroke="#1A1A1A"
                    strokeWidth={5}
                />
                <circle
                    cx={size / 2}
                    cy={size / 2}
                    r={r}
                    fill="none"
                    stroke={color}
                    strokeWidth={5}
                    strokeDasharray={circ}
                    strokeDashoffset={offset}
                    strokeLinecap="round"
                />
            </svg>
            <span
                style={{
                    color,
                    fontSize: 14,
                    fontWeight: 800,
                    marginTop: -38,
                }}
            >
                {value}
            </span>
            <span style={{ color: "#666", fontSize: 9, marginTop: 16 }}>
                {label}
            </span>
        </div>
    )
}

/* ── 등급 색상/라벨 (표준) ── */
export const gradeLabels: Record<string, string> = {
    STRONG_BUY: "강력매수",
    BUY: "매수",
    WATCH: "관망",
    CAUTION: "주의",
    AVOID: "회피",
}

export const gradeColors: Record<string, string> = {
    STRONG_BUY: "#22C55E",
    BUY: "#B5FF19",
    WATCH: "#FFD600",
    CAUTION: "#F59E0B",
    AVOID: "#EF4444",
}

/* ── 디자인 시스템 상수 ── */
export const COLORS = {
    bg: "#000",
    card: "#111",
    border: "#222",
    accent: "#B5FF19",
    positive: "#22C55E",
    negative: "#EF4444",
    warning: "#F59E0B",
    muted: "#888",
}

export const FONT = "'Inter', 'Pretendard', -apple-system, sans-serif"
export const FONT_MONO =
    "'SF Mono', 'Fira Code', 'JetBrains Mono', 'Inter', 'Pretendard', monospace"

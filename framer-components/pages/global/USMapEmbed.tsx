import { addPropertyControls, ControlType } from "framer"
import { useEffect, useRef, useState, type CSSProperties } from "react"

/**
 * USMapEmbed — TradingView S&P 500 Stock Heatmap iframe (모던 심플)
 *
 * 정정 (Step 4, 2026-05-04):
 *   - 기존 583줄 (탭 3개: map / sectors / movers) → 270줄 iframe-only
 *   - sectors 탭 → SectorMap.tsx (US toggle) 으로 흡수
 *   - movers 탭 → StockHeatmap.tsx (US toggle) 으로 흡수
 *   - 본 컴포넌트는 TradingView 위젯 iframe 단일 책임
 *
 * Why 유지: TradingView heatmap = 시가총액 가중 + GICS 섹터 그룹화 +
 * live tick + 줌/툴팁이 자체 코드보다 정밀. 외부 iframe 의존을 인정한
 * 결정 (2026-05-04 사용자 결정).
 *
 * 모던 심플 6원칙:
 *   1. No card-in-card — 외곽 1개 + iframe 컨테이너
 *   2. Flat hierarchy — title + 외부 링크
 *   3. Mono numerics — N/A (iframe 내용)
 *   4. Color discipline — 토큰만
 *   5. Emoji 0
 *   6. iframe 로딩 상태 모던 표시
 *
 * feedback_no_hardcode_position 적용: inline 렌더링.
 */

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D", borderHover: "#B5FF19",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B5FF19", accentSoft: "rgba(181,255,25,0.12)",
    success: "#22C55E", warn: "#F59E0B", danger: "#EF4444", info: "#5BA9FF",
}
const G = {
    accent: "0 0 8px rgba(181,255,25,0.35)",
    accentSoft: "0 0 4px rgba(181,255,25,0.20)",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
    lh_normal: 1.5,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease" }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
/* ◆ DESIGN TOKENS END ◆ */


/* ─────────── TradingView 위젯 HTML (S&P 500 stock heatmap) ─────────── */
function buildWidgetHtml(): string {
    return `<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>*{margin:0;padding:0}html,body,.tradingview-widget-container{width:100%;height:100%;overflow:hidden;background:${C.bgPage}}</style>
</head><body>
<div class="tradingview-widget-container">
<div class="tradingview-widget-container__widget" style="width:100%;height:100%"></div>
<script src="https://s3.tradingview.com/external-embedding/embed-widget-stock-heatmap.js" async>
{"exchanges":[],"dataSource":"SPX500","grouping":"sector","blockSize":"market_cap_basic","blockColor":"change","locale":"ko","symbolUrl":"","colorTheme":"dark","hasTopBar":false,"isDataSetEnabled":false,"isZoomEnabled":true,"hasSymbolTooltip":true,"isMonoSize":false,"width":"100%","height":"100%"}
</script>
</div>
</body></html>`
}


/* ═══════════════════════════ 메인 ═══════════════════════════ */

interface Props {
    /** 새 창에서 열기 링크 — TradingView 또는 커스텀 */
    mapUrl: string
    /** iframe 높이 (px). Framer 에서 컨테이너 사이즈 지정 시 무시됨 */
    height: number
    showHeader: boolean
}

export default function USMapEmbed(props: Props) {
    const { mapUrl, height, showHeader } = props
    const [clientReady, setClientReady] = useState(false)
    const [loaded, setLoaded] = useState(false)
    const [timedOut, setTimedOut] = useState(false)
    const widgetHtml = useRef(buildWidgetHtml())

    useEffect(() => setClientReady(true), [])

    useEffect(() => {
        if (!clientReady) return
        setLoaded(false)
        setTimedOut(false)
        const t = window.setTimeout(() => setTimedOut(true), 15_000)
        return () => window.clearTimeout(t)
    }, [clientReady])

    return (
        <div style={shell}>
            {showHeader && (
                <div style={headerRow}>
                    <div style={headerLeft}>
                        <span style={titleStyle}>S&P 500 Stock Heatmap</span>
                        <span style={metaStyle}>TradingView · 시가총액 가중 · GICS 섹터</span>
                    </div>
                    {mapUrl && (
                        <a
                            href={mapUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={extLink}
                        >
                            새 창 →
                        </a>
                    )}
                </div>
            )}

            <div
                style={{
                    position: "relative",
                    width: "100%",
                    height: showHeader ? `calc(100% - 64px)` : "100%",
                    minHeight: height,
                    overflow: "hidden",
                    borderRadius: R.md,
                    background: C.bgPage,
                }}
            >
                {!clientReady ? (
                    <div style={absCenter}>
                        <span style={{ color: C.textTertiary, fontSize: T.body }}>
                            준비 중…
                        </span>
                    </div>
                ) : (
                    <>
                        <iframe
                            title="US Stock Heatmap"
                            srcDoc={widgetHtml.current}
                            sandbox="allow-scripts allow-same-origin allow-popups"
                            onLoad={() => setLoaded(true)}
                            style={{
                                position: "absolute",
                                top: 0, left: 0,
                                width: "100%", height: "100%",
                                border: "none", display: "block",
                                zIndex: 1,
                            }}
                            loading="eager"
                        />
                        {!loaded && (
                            <div style={absCenter}>
                                <span style={{ color: C.textTertiary, fontSize: T.body }}>
                                    S&P 500 히트맵 로딩 중…
                                </span>
                                {timedOut && (
                                    <div
                                        style={{
                                            display: "flex",
                                            flexDirection: "column",
                                            alignItems: "center",
                                            gap: S.md,
                                            maxWidth: 320,
                                            textAlign: "center",
                                            marginTop: S.md,
                                        }}
                                    >
                                        <span style={{ color: C.textTertiary, fontSize: T.cap, lineHeight: T.lh_normal }}>
                                            15초 이상 로딩 중. 팝업 차단 또는 네트워크를 확인하세요.
                                        </span>
                                        {mapUrl && (
                                            <a
                                                href={mapUrl}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                style={ctaLink}
                                            >
                                                새 창에서 열기
                                            </a>
                                        )}
                                    </div>
                                )}
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    )
}


/* ─────────── 스타일 ─────────── */

const shell: CSSProperties = {
    width: "100%",
    height: "100%",
    boxSizing: "border-box",
    fontFamily: FONT,
    color: C.textPrimary,
    background: C.bgPage,
    border: `1px solid ${C.border}`,
    borderRadius: R.lg,
    padding: S.xxl,
    display: "flex",
    flexDirection: "column",
    gap: S.md,
    overflow: "hidden",
}

const headerRow: CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: S.md,
}

const headerLeft: CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 2,
}

const titleStyle: CSSProperties = {
    fontSize: T.title,
    fontWeight: T.w_bold,
    color: C.textPrimary,
    letterSpacing: "-0.3px",
}

const metaStyle: CSSProperties = {
    fontSize: T.cap,
    color: C.textTertiary,
    fontWeight: T.w_med,
}

const extLink: CSSProperties = {
    color: C.info,
    fontSize: T.cap,
    fontWeight: T.w_semi,
    fontFamily: FONT,
    textDecoration: "none",
    padding: `${S.xs}px ${S.md}px`,
    border: `1px solid ${C.border}`,
    borderRadius: R.md,
    transition: X.base,
}

const ctaLink: CSSProperties = {
    color: C.accent,
    fontSize: T.cap,
    fontWeight: T.w_bold,
    fontFamily: FONT,
    textDecoration: "none",
    padding: `${S.xs}px ${S.md}px`,
    border: `1px solid ${C.accent}`,
    borderRadius: R.md,
    background: C.accentSoft,
}

const absCenter: CSSProperties = {
    position: "absolute",
    top: 0, left: 0, right: 0, bottom: 0,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    background: C.bgPage,
    zIndex: 2,
}


/* ─────────── Framer Property Controls ─────────── */

USMapEmbed.defaultProps = {
    mapUrl: "https://www.tradingview.com/heatmap/stock/",
    height: 540,
    showHeader: true,
}

addPropertyControls(USMapEmbed, {
    mapUrl: {
        type: ControlType.String,
        title: "새 창 URL",
        defaultValue: "https://www.tradingview.com/heatmap/stock/",
    },
    height: {
        type: ControlType.Number,
        title: "최소 높이 (px)",
        defaultValue: 540,
        min: 200, max: 1200, step: 20,
    },
    showHeader: {
        type: ControlType.Boolean,
        title: "헤더 표시",
        defaultValue: true,
    },
})

// PostPreview — 인스타 포스팅 미리보기 (iPhone + MacBook 디바이스 목업)
// VERITY admin 컴포넌트.
//
// scripts/generate_daily_content.py 가 생성한 5장 카드 (integrated cover + 4 sub)
// 를 raw GitHub URL 로 fetch → 디바이스 frame 안에 carousel 슬라이드.
//
// 사용자가 인스타 올리기 전 실제 노출 모습 시각 확인용.
// VERITY 마스터 톤 (#B5FF19 lime).

import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useMemo, useState } from "react"

/* ◆ VERITY 마스터 톤 ◆ */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#1B1D24",
    border: "transparent", borderStrong: "#2E3038",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76",
    accent: "#B5FF19", accentBright: "#C8FF40",
    accentSoft: "rgba(181,255,25,0.15)",
    statusPos: "#22C55E", statusNeg: "#EF4444",
    deviceBezel: "#0A0B0D", deviceScreen: "#FFFFFF",
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"

const CATEGORIES = [
    { key: "integrated", label: "통합 (메인)" },
    { key: "macro", label: "거시" },
    { key: "sector", label: "섹터" },
    { key: "micro", label: "미시" },
    { key: "news_impact", label: "뉴스" },
] as const

type CategoryKey = typeof CATEGORIES[number]["key"]

interface Props {
    date: string             // YYYY-MM-DD (빈 값이면 오늘 KST)
    rawBase: string          // raw URL prefix (GitHub raw default)
    autoRotate: boolean      // carousel 자동 회전
    rotateInterval: number   // 초
    instaHandle: string      // @verity_terminal
    showCaption: boolean     // iPhone 하단 caption 미리보기
}

function _todayKst(): string {
    // KST = UTC+9
    const now = new Date(Date.now() + 9 * 60 * 60 * 1000)
    return now.toISOString().slice(0, 10)
}

function _cardUrl(rawBase: string, date: string, category: CategoryKey): string {
    return `${rawBase.replace(/\/$/, "")}/${date}/${category}/card.png`
}

/* ──────────────── iPhone 프레임 (인스타 피드 모방) ──────────────── */

function IPhoneFrame({ imageUrl, handle, category, showCaption }: {
    imageUrl: string; handle: string; category: typeof CATEGORIES[number]; showCaption: boolean
}) {
    const W = 360, H = 720
    const screenPad = 12
    const screenW = W - screenPad * 2
    const cardSize = screenW  // 인스타 정사각 카드

    return (
        <div style={{
            width: W, height: H, borderRadius: 48,
            background: C.deviceBezel,
            padding: screenPad,
            boxShadow: "0 30px 60px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.05)",
            display: "flex", flexDirection: "column",
            overflow: "hidden",
        }}>
            {/* notch */}
            <div style={{
                position: "absolute", top: screenPad + 8, left: "50%", transform: "translateX(-50%)",
                width: 100, height: 24, background: C.deviceBezel, borderRadius: 12, zIndex: 2,
            }} />

            <div style={{
                flex: 1, background: C.deviceScreen, borderRadius: 36,
                overflow: "hidden", position: "relative",
                display: "flex", flexDirection: "column",
            }}>
                {/* status bar */}
                <div style={{
                    height: 32, padding: "8px 24px",
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                    fontSize: 11, fontWeight: 600, color: "#000", fontFamily: FONT,
                }}>
                    <span>9:41</span>
                    <span>●●● 100%</span>
                </div>

                {/* 인스타 헤더 */}
                <div style={{
                    padding: "8px 12px", display: "flex", alignItems: "center", gap: 8,
                    borderBottom: "1px solid #EFEFEF",
                }}>
                    <div style={{
                        width: 28, height: 28, borderRadius: "50%",
                        background: `linear-gradient(135deg, ${C.accent}, #FF6FFF, #FFB400)`,
                        padding: 2, display: "flex", alignItems: "center", justifyContent: "center",
                    }}>
                        <div style={{
                            width: "100%", height: "100%", borderRadius: "50%",
                            background: "#000", color: C.accent,
                            display: "flex", alignItems: "center", justifyContent: "center",
                            fontSize: 11, fontWeight: 700, fontFamily: FONT,
                        }}>V</div>
                    </div>
                    <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
                        <span style={{ fontSize: 13, fontWeight: 600, color: "#000", fontFamily: FONT }}>
                            {handle.replace("@", "")}
                        </span>
                        <span style={{ fontSize: 10, color: "#888", fontFamily: FONT }}>
                            Sponsored · {category.label}
                        </span>
                    </div>
                    <span style={{ color: "#000", fontSize: 14, letterSpacing: 2 }}>...</span>
                </div>

                {/* 카드 이미지 */}
                <div style={{
                    width: cardSize, height: cardSize, position: "relative",
                    background: C.bgPage,
                }}>
                    <img src={imageUrl} alt={category.label}
                         style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
                         onError={(e) => { (e.currentTarget.style.display = "none") }} />
                </div>

                {/* 인스타 액션 줄 (SVG icon) */}
                <div style={{
                    padding: "8px 12px", display: "flex", gap: 14, alignItems: "center", color: "#000",
                }}>
                    {/* heart */}
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
                         stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
                    </svg>
                    {/* comment */}
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
                         stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
                    </svg>
                    {/* share (paper plane) */}
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
                         stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="22" y1="2" x2="11" y2="13" />
                        <polygon points="22 2 15 22 11 13 2 9 22 2" />
                    </svg>
                    {/* bookmark */}
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none"
                         stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                         style={{ marginLeft: "auto" }}>
                        <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
                    </svg>
                </div>

                {/* caption preview */}
                {showCaption && (
                    <div style={{
                        padding: "0 12px 8px", fontSize: 12, lineHeight: 1.4,
                        color: "#000", fontFamily: FONT, overflow: "hidden",
                    }}>
                        <span style={{ fontWeight: 600 }}>{handle.replace("@", "")} </span>
                        배리티 {category.label} 브리핑…{" "}
                        <span style={{ color: "#888" }}>더 보기</span>
                    </div>
                )}
            </div>
        </div>
    )
}

/* ──────────────── MacBook 프레임 (카드 풀화면) ──────────────── */

function MacBookFrame({ imageUrl, category }: { imageUrl: string; category: typeof CATEGORIES[number] }) {
    const W = 560, H = 360
    return (
        <div style={{
            width: W, height: H + 16, display: "flex", flexDirection: "column", alignItems: "center",
        }}>
            {/* 화면 */}
            <div style={{
                width: W, height: H,
                background: C.deviceBezel, borderRadius: 16, padding: 8,
                boxShadow: "0 25px 50px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.05)",
            }}>
                <div style={{
                    flex: 1, background: C.bgPage, borderRadius: 8, overflow: "hidden",
                    width: "100%", height: "100%", display: "flex", flexDirection: "column",
                }}>
                    {/* 사파리 toolbar */}
                    <div style={{
                        height: 28, padding: "0 12px", display: "flex", alignItems: "center", gap: 8,
                        background: C.bgCard,
                    }}>
                        <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#FF5F57" }} />
                        <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#FEBC2E" }} />
                        <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#28C840" }} />
                        <div style={{
                            flex: 1, marginLeft: 12, height: 18, borderRadius: 4,
                            background: C.bgElevated, padding: "0 8px",
                            display: "flex", alignItems: "center", gap: 6,
                            fontSize: 10, color: C.textSecondary, fontFamily: FONT_MONO,
                        }}>
                            <span style={{ color: C.statusPos, fontSize: 9 }}>●</span>
                            <span>instagram.com/verity_terminal</span>
                        </div>
                    </div>

                    {/* 카드 표시 영역 */}
                    <div style={{
                        flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
                        background: C.bgPage, padding: 20,
                    }}>
                        <img src={imageUrl} alt={category.label}
                             style={{
                                 maxWidth: "100%", maxHeight: "100%", objectFit: "contain",
                                 borderRadius: 4, boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                             }}
                             onError={(e) => { (e.currentTarget.style.display = "none") }} />
                    </div>
                </div>
            </div>

            {/* 받침 (MacBook 힌지) */}
            <div style={{
                width: W * 0.96, height: 8, background: C.deviceBezel,
                borderRadius: "0 0 24px 24px",
                boxShadow: "0 4px 8px rgba(0,0,0,0.3)",
            }} />
        </div>
    )
}

/* ──────────────── 메인 ──────────────── */

function PostPreview({
    date = "",
    rawBase = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/daily_content",
    autoRotate = true,
    rotateInterval = 4,
    instaHandle = "@verity_terminal",
    showCaption = true,
}: Props) {
    const effectiveDate = useMemo(() => date || _todayKst(), [date])
    const [idx, setIdx] = useState(0)
    const cur = CATEGORIES[idx]

    useEffect(() => {
        if (!autoRotate) return
        const id = setInterval(() => setIdx((i) => (i + 1) % CATEGORIES.length),
                               Math.max(1, rotateInterval) * 1000)
        return () => clearInterval(id)
    }, [autoRotate, rotateInterval])

    const cardUrl = _cardUrl(rawBase, effectiveDate, cur.key)

    return (
        <div style={{
            width: "100%", minHeight: 800,
            background: C.bgPage, color: C.textPrimary, fontFamily: FONT,
            padding: 32, display: "flex", flexDirection: "column", gap: 24,
            borderRadius: 16, overflow: "hidden",
        }}>
            {/* 헤더 */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <div>
                    <div style={{ fontSize: 13, color: C.accent, fontWeight: 600, letterSpacing: 1 }}>
                        VERITY · POST PREVIEW
                    </div>
                    <div style={{ fontSize: 24, fontWeight: 700, marginTop: 4 }}>
                        인스타 포스팅 미리보기
                    </div>
                </div>
                <div style={{ fontSize: 12, color: C.textSecondary, fontFamily: FONT_MONO }}>
                    {effectiveDate} · {cur.label}
                </div>
            </div>

            {/* 디바이스 영역 */}
            <div style={{
                display: "flex", gap: 32, justifyContent: "center", alignItems: "flex-start",
                flexWrap: "wrap",
            }}>
                <IPhoneFrame imageUrl={cardUrl} handle={instaHandle}
                             category={cur} showCaption={showCaption} />
                <MacBookFrame imageUrl={cardUrl} category={cur} />
            </div>

            {/* carousel control — minimal underline + chevron */}
            <div style={{
                display: "flex", justifyContent: "center", alignItems: "center",
                gap: 32, marginTop: 16,
            }}>
                {/* prev chevron */}
                <button
                    type="button"
                    onClick={() => setIdx((i) => (i - 1 + CATEGORIES.length) % CATEGORIES.length)}
                    aria-label="이전"
                    style={{
                        width: 32, height: 32, padding: 0,
                        background: "transparent", border: "none", cursor: "pointer",
                        color: C.textSecondary,
                        display: "flex", alignItems: "center", justifyContent: "center",
                        transition: "color 200ms ease",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.color = C.textPrimary)}
                    onMouseLeave={(e) => (e.currentTarget.style.color = C.textSecondary)}
                >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                         stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="15 18 9 12 15 6" />
                    </svg>
                </button>

                {/* category labels — minimal underline 활성 */}
                <div style={{ display: "flex", gap: 28, alignItems: "center" }}>
                    {CATEGORIES.map((cat, i) => {
                        const active = i === idx
                        return (
                            <button key={cat.key} type="button" onClick={() => setIdx(i)}
                                style={{
                                    padding: "6px 0", border: "none", background: "transparent",
                                    cursor: "pointer", position: "relative",
                                    color: active ? C.textPrimary : C.textTertiary,
                                    fontSize: 13,
                                    fontWeight: active ? 600 : 400,
                                    fontFamily: FONT,
                                    letterSpacing: 0.2,
                                    transition: "color 200ms ease",
                                }}
                                onMouseEnter={(e) => {
                                    if (!active) (e.currentTarget.style.color = C.textSecondary)
                                }}
                                onMouseLeave={(e) => {
                                    if (!active) (e.currentTarget.style.color = C.textTertiary)
                                }}
                            >
                                {cat.label}
                                {/* underline indicator */}
                                <span style={{
                                    position: "absolute", left: 0, right: 0, bottom: 0,
                                    height: 2, background: C.accent,
                                    transform: active ? "scaleX(1)" : "scaleX(0)",
                                    transformOrigin: "center",
                                    transition: "transform 200ms ease",
                                    borderRadius: 1,
                                }} />
                            </button>
                        )
                    })}
                </div>

                {/* next chevron */}
                <button
                    type="button"
                    onClick={() => setIdx((i) => (i + 1) % CATEGORIES.length)}
                    aria-label="다음"
                    style={{
                        width: 32, height: 32, padding: 0,
                        background: "transparent", border: "none", cursor: "pointer",
                        color: C.textSecondary,
                        display: "flex", alignItems: "center", justifyContent: "center",
                        transition: "color 200ms ease",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.color = C.textPrimary)}
                    onMouseLeave={(e) => (e.currentTarget.style.color = C.textSecondary)}
                >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                         stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="9 18 15 12 9 6" />
                    </svg>
                </button>
            </div>

            {/* progress dots — 미세 carousel index 표시 */}
            <div style={{
                display: "flex", justifyContent: "center", gap: 6, marginTop: 4,
            }}>
                {CATEGORIES.map((cat, i) => (
                    <span key={cat.key} aria-hidden style={{
                        width: i === idx ? 16 : 4, height: 4, borderRadius: 2,
                        background: i === idx ? C.accent : C.borderStrong,
                        transition: "all 200ms ease",
                    }} />
                ))}
            </div>

            {/* footer hint */}
            <div style={{
                fontSize: 11, color: C.textTertiary, textAlign: "center",
                fontFamily: FONT_MONO, marginTop: 8,
            }}>
                {cardUrl}
            </div>
        </div>
    )
}

addPropertyControls(PostPreview, {
    date: { type: ControlType.String, defaultValue: "",
            description: "YYYY-MM-DD. 비우면 오늘 KST 자동." },
    rawBase: { type: ControlType.String,
               defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/daily_content",
               description: "raw URL prefix" },
    autoRotate: { type: ControlType.Boolean, defaultValue: true,
                  description: "carousel 자동 회전" },
    rotateInterval: { type: ControlType.Number, defaultValue: 4, min: 1, max: 30, step: 1,
                      description: "회전 간격 (초)" },
    instaHandle: { type: ControlType.String, defaultValue: "@verity_terminal",
                   description: "인스타 핸들" },
    showCaption: { type: ControlType.Boolean, defaultValue: true,
                   description: "iPhone caption 미리보기" },
})

export default PostPreview

import { addPropertyControls, ControlType, RenderTarget } from "framer"
import React, { useEffect, useState } from "react"

/**
 * AlphaNest 다크/라이트 토글 (네이티브) — 방문자용.
 *
 * Framer 네이티브 테마는 body[data-framer-theme]("light"|"dark") 로 제어됨.
 *  - 클릭 → document.body.dataset.framerTheme 토글 + localStorage("verity_theme") 저장
 *  - 마운트 → 저장된 선호 복원(없으면 Framer 가 시스템 기준으로 설정한 값 유지)
 *  - 이 속성이 바뀌면 Framer Color Styles(NavBg/PageBg 등) + 구독하는 코드 컴포넌트가 모두 따라옴
 *
 * 🎨 2026-07-08 깜빡임 fix — 버튼 시각(배경/보더/아이콘색/아이콘 선택)을 JS 상태가 아니라
 *    CSS(토큰 var + body 속성 선택자)로 그림. 옛 구조 = useState("light") 첫 페인트 →
 *    effect 정정 → 페이지 전환(리마운트)마다 다크모드에서 흰 버튼 1프레임 깜빡임.
 *    JS 상태(theme)는 aria-label/title 전용 (시각 무관). 해/달 아이콘 둘 다 렌더하고
 *    CSS 로 표시 전환 — SSR 첫 페인트는 OS media query, 속성 설정 후엔 속성 선택자 우선.
 *
 * ⚠ 캔버스 에디터에선 동작 안 함(부작용 없음) — 실제 동작은 Preview/Publish 에서 확인.
 */

const THEME_KEY = "verity_theme"
type Theme = "light" | "dark"

/*
 * Published Framer 사이트는 네이티브 Color Styles 의 다크값을
 * @media (prefers-color-scheme:dark) 로만 emit 함 (OS 설정 추종).
 * published HTML 엔 data-framer-theme 훅이 없어 JS 토글로 못 바꿈.
 *  → 토글이 같은 CSS 변수(--token-*)를 body[data-framer-theme] 기준으로
 *    재정의하는 <style> 을 head 에 주입해 OS media query 를 덮어씀.
 *    (속성 선택자 specificity > media 의 body{} 기본값)
 * 토큰 UUID 는 프로젝트 Color Style identity 에 고정(publish 간 불변).
 * 🚨 신 Color Style 추가/값 변경 시 = 여기 두 블록(light/dark)도 동기화 의무
 *    (2026-07-08 사고: 모바일 상단 bg 를 색스타일만 0.85 로 올리고 여기 옛값 #fff3 방치
 *     → 토글 사용자에게 fix 무효화. 색스타일 변경 = 이 파일 grep 의무).
 */
const STYLE_ID = "verity-theme-token-overrides"
const THEME_CSS =
    'body[data-framer-theme="light"]{' +
    "--token-ffcc4fd8-58d0-45dc-a259-50e9f47bc8db:#f2f4f6;" + // PageBg
    "--token-f0419bdc-ebbe-435e-9bff-d5f72a0549cf:#ffffff;" + // NavBg
    "--token-c15144f1-f6e3-44ad-a61e-ecf50795a3c5:#000000;" + // Ink
    "--token-891a2668-deba-490a-b9f4-e8029d46f025:#f2f4f6;" + // Field
    "--token-633070ef-c72c-4d61-8127-69b2f746f38f:#545454;" + // IconMuted
    "--token-464a4386-16cc-4626-97c4-e6b0fcc2fa01:#6b7280;" + // MenuText
    "--token-a8427b85-996c-4c32-93b4-222935fc2f01:#6c5ce7;" + // MenuHover
    "--token-17d84716-89a0-4724-8331-39a778f7dcc5:#ffffffd9;" + // 모바일 상단 bg (흰색 0.85 — 7/7 스크롤 투과 fix 정합)
    "}" +
    'body[data-framer-theme="dark"]{' +
    "--token-ffcc4fd8-58d0-45dc-a259-50e9f47bc8db:#0f1318;" +
    "--token-f0419bdc-ebbe-435e-9bff-d5f72a0549cf:#171c23;" +
    "--token-c15144f1-f6e3-44ad-a61e-ecf50795a3c5:#ffffff;" +
    "--token-891a2668-deba-490a-b9f4-e8029d46f025:#1e242c;" +
    "--token-633070ef-c72c-4d61-8127-69b2f746f38f:#9aa4b1;" +
    "--token-464a4386-16cc-4626-97c4-e6b0fcc2fa01:#9aa4b1;" +
    "--token-a8427b85-996c-4c32-93b4-222935fc2f01:#a99bff;" +
    "--token-17d84716-89a0-4724-8331-39a778f7dcc5:#171c23d9;" + // 모바일 상단 bg (NavBg 다크 0.85)
    "}"

function injectOverrideStyle() {
    if (typeof document === "undefined" || !document.head) return
    const existing = document.getElementById(STYLE_ID)
    if (existing) {
        // 값 갱신 배포 시 구 페이지 잔존 스타일 교체 (SPA 캐시 대비)
        if (existing.textContent !== THEME_CSS) existing.textContent = THEME_CSS
        return
    }
    const el = document.createElement("style")
    el.id = STYLE_ID
    el.textContent = THEME_CSS
    document.head.appendChild(el)
}

function systemTheme(): Theme {
    if (typeof window === "undefined" || !window.matchMedia) return "light"
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
}

function readBodyTheme(): Theme {
    if (typeof document === "undefined") return "light"
    return document.body && document.body.dataset.framerTheme === "dark" ? "dark" : "light"
}

function applyTheme(t: Theme) {
    if (typeof document !== "undefined" && document.body) {
        document.body.dataset.framerTheme = t
    }
    try { localStorage.setItem(THEME_KEY, t) } catch (e) { /* no-op */ }
}

/* 버튼 자체의 테마 시각 — 토큰 var(첫 페인트 media query 값 → 속성 설정 후 오버라이드 값)
   + 아이콘 표시 전환. 클래스 프리픽스 vtTg 로 스코프. */
const BTN_CSS =
    ".vtTgBtn{background:var(--token-f0419bdc-ebbe-435e-9bff-d5f72a0549cf,#ffffff);" +
    "border:1px solid var(--token-891a2668-deba-490a-b9f4-e8029d46f025,#e5e8eb);}" +
    ".vtTgBtn svg{color:var(--token-633070ef-c72c-4d61-8127-69b2f746f38f,#4e5968);}" +
    ".vtTgSun{display:flex}.vtTgMoon{display:none}" +
    "@media (prefers-color-scheme: dark){.vtTgSun{display:none}.vtTgMoon{display:flex}}" +
    'body[data-framer-theme="light"] .vtTgSun{display:flex}' +
    'body[data-framer-theme="light"] .vtTgMoon{display:none}' +
    'body[data-framer-theme="dark"] .vtTgSun{display:none}' +
    'body[data-framer-theme="dark"] .vtTgMoon{display:flex}'

function SunIcon(props: { size: number }) {
    const s = props.size
    return (
        <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="4.2" />
            <line x1="12" y1="2.5" x2="12" y2="5" />
            <line x1="12" y1="19" x2="12" y2="21.5" />
            <line x1="2.5" y1="12" x2="5" y2="12" />
            <line x1="19" y1="12" x2="21.5" y2="12" />
            <line x1="4.9" y1="4.9" x2="6.6" y2="6.6" />
            <line x1="17.4" y1="17.4" x2="19.1" y2="19.1" />
            <line x1="4.9" y1="19.1" x2="6.6" y2="17.4" />
            <line x1="17.4" y1="6.6" x2="19.1" y2="4.9" />
        </svg>
    )
}

function MoonIcon(props: { size: number }) {
    const s = props.size
    return (
        <svg width={s} height={s} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
        </svg>
    )
}

interface Props {
    size: number
}

export default function PublicThemeToggle(props: Props) {
    const size = props.size || 40
    const isCanvas = RenderTarget.current() === RenderTarget.canvas
    /* theme 상태 = aria/title 전용 (시각은 CSS 가 담당 — 리마운트 깜빡임 원천 차단) */
    const [theme, setTheme] = useState<Theme>("light")

    /* 마운트: 토큰 오버라이드 주입 + 선호 복원 + 외부 변경 동기화 */
    useEffect(() => {
        if (isCanvas) return
        injectOverrideStyle()
        let initial: Theme = systemTheme()
        try {
            const saved = localStorage.getItem(THEME_KEY)
            if (saved === "dark" || saved === "light") initial = saved
        } catch (e) { /* no-op */ }
        /* 항상 body 속성을 명시 — native(주입 CSS)+코드컴포넌트 첫 페인트부터 일치 */
        if (document.body) document.body.dataset.framerTheme = initial
        setTheme(initial)

        if (typeof MutationObserver === "undefined" || !document.body) return
        const obs = new MutationObserver(() => setTheme(readBodyTheme()))
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [isCanvas])

    const toggle = () => {
        if (isCanvas) return
        /* 진실원 = body 속성 (JS 상태는 aria 미러라 stale 가능) */
        const next: Theme = readBodyTheme() === "dark" ? "light" : "dark"
        setTheme(next)
        applyTheme(next)
    }

    const iconSize = Math.round(size * 0.5)

    return (
        <button
            type="button"
            className="vtTgBtn"
            onClick={toggle}
            aria-label={theme === "dark" ? "라이트 모드로 전환" : "다크 모드로 전환"}
            title={isCanvas ? "Preview/Publish 에서 동작" : (theme === "dark" ? "라이트 모드" : "다크 모드")}
            style={{
                width: size,
                height: size,
                borderRadius: Math.round(size * 0.32),
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: isCanvas ? "default" : "pointer",
                padding: 0,
                boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
                transition: "background 160ms ease, border-color 160ms ease, transform 80ms ease",
            }}
            onMouseDown={(e) => {
                if (!isCanvas) (e.currentTarget as HTMLButtonElement).style.transform = "scale(0.94)"
            }}
            onMouseUp={(e) => {
                (e.currentTarget as HTMLButtonElement).style.transform = "scale(1)"
            }}
            onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.transform = "scale(1)"
            }}
        >
            <style>{BTN_CSS}</style>
            <span className="vtTgSun" style={{ alignItems: "center", justifyContent: "center" }}>
                <SunIcon size={iconSize} />
            </span>
            <span className="vtTgMoon" style={{ alignItems: "center", justifyContent: "center" }}>
                <MoonIcon size={iconSize} />
            </span>
        </button>
    )
}

addPropertyControls(PublicThemeToggle, {
    size: {
        type: ControlType.Number,
        title: "버튼 크기",
        defaultValue: 40,
        min: 28,
        max: 80,
        step: 2,
        unit: "px",
    },
})

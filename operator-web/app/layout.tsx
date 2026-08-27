import type { Metadata } from "next"
import "./globals.css"

const THEME_BOOTSTRAP = `(function(){try{var t=localStorage.getItem("verity_theme");var d=t==="dark"||(t!=="light"&&window.matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.setAttribute("data-theme",d?"dark":"light")}catch(e){}})()`

// 오퍼레이터 전용(비공개) — 색인 금지.
export const metadata: Metadata = {
    // 🚨 2026-08-20 PM 확정 — 오퍼레이터 이름 = "알파콘솔".
    //   공개 터미널(알파네스트)과 탭·스크린샷에서 구분되지 않던 문제. 8/04 패밀리룩
    //   결정(알파파운더 폐지)은 유지 — 계열명은 "알파" 로 잇고 역할만 갈랐다.
    title: "알파콘솔",
    robots: { index: false, follow: false },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
    return (
        <html lang="ko" suppressHydrationWarning>
            <head>
                <script data-verity-theme-bootstrap dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
            </head>
            <body>{children}</body>
        </html>
    )
}

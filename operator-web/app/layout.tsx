import type { Metadata } from "next"
import "./globals.css"

// 오퍼레이터 전용(비공개) — 색인 금지.
export const metadata: Metadata = {
    title: "알파파운더",
    robots: { index: false, follow: false },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
    return (
        <html lang="ko">
            <body>{children}</body>
        </html>
    )
}

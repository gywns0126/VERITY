import type { Metadata } from "next"
import "./globals.css"

// 오퍼레이터 전용(비공개) — 색인 금지.
export const metadata: Metadata = {
    title: "VERITY 오퍼레이터",
    robots: { index: false, follow: false },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
    return (
        <html lang="ko">
            <body>{children}</body>
        </html>
    )
}

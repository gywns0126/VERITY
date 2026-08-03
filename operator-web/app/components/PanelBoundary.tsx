"use client"
// PanelBoundary — 패널 단위 오류 격리 (2026-08-03 Safari 크래시 사고 후속).
// 한 패널의 런타임 예외가 터미널 전체를 죽이지 않게 한다. 실패 패널만 자리 표시.
import React from "react"

type Props = { name: string; children: React.ReactNode }
type State = { failed: boolean }

export default class PanelBoundary extends React.Component<Props, State> {
    state: State = { failed: false }

    static getDerivedStateFromError(): State {
        return { failed: true }
    }

    componentDidCatch(err: unknown) {
        try {
            console.error(`[panel:${this.props.name}]`, err)
        } catch {}
    }

    render() {
        if (this.state.failed) {
            return (
                <div style={{ background: "rgba(128,128,128,0.08)", borderRadius: 14, padding: "12px 14px", fontSize: 12, color: "#8b95a1", fontFamily: "Pretendard, sans-serif" }}>
                    {this.props.name} 패널 오류 — 새로고침하면 복구됩니다.
                </div>
            )
        }
        return this.props.children
    }
}

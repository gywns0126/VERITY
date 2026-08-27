"use client"
// TVChart — 미국 종목 차트. TradingView Advanced Chart 임베드 (오퍼레이터 전용).
//
// 🚨 왜 미장만인가 (2026-08-12 실측, 16+16 심볼 위젯 렌더 확인):
//   · 미국 개별종목/ETF = bare 심볼로 정상 (AAPL · JPM · BRK.B · QQQ · SPY · DIA · SOXX 확인).
//   · KRX 는 전부 거부 — KRX:005930 / KRX:035420 / KRX_DLY:005930 / bare 005930 / KOSPI
//     모두 "TradingView 에서만 제공되는 심볼입니다". 2026-07-04 실증과 동일 결과라
//     국장은 계속 KIS 자체 캔들(분/일/주/월)을 쓴다. 되돌려서 재시도하지 말 것.
//   · 미국 **지수** 도 전부 거부 — NASDAQ:IXIC / SP:SPX / DJ:DJI / NASDAQ:SOX / CBOE:VIX /
//     TVC:* 계열. 임베드 가능한 건 CFD 프록시(FOREXCOM:NSXUSD 등)뿐인데 그건 나스닥100 이라
//     우리 카드의 나스닥 컴포짓(26,445 vs 29,731)과 다른 지수다 → 지수는 KIS 해외지수 일봉 유지.
//
// 라이선스: 데이터 라이선스 책임 = TradingView 부담(지연 데이터 한정) → 임베드 측 별도 계약 불요.
//   의무 = attribution 링크(≥13px) 병기 + 위젯 코드 변형 금지. 우리는 저장·재배포하지 않는다.
//
// 구현 함정 (되돌리지 말 것):
//   ① iframe 높이는 px 고정 — Fit/100% 면 0 으로 계산돼 위젯이 통째로 사라진다.
//   ② iframe 은 부모 CSS 를 못 읽는다 — 테마·배경은 **값으로** srcDoc 에 넘긴다.
//   ③ 모서리 잘림 = 위젯이 자기 문서 안에서 그리는 1px 테두리. TV 는 중첩 iframe 이라
//      srcDoc CSS 의 border:0 가 안쪽까지 닿지 않는다 → iframe 을 사방 3px 크게 잡고
//      margin -3px 로 당겨(overscan) 래퍼의 overflow:hidden 이 테두리를 먹게 한다.
//   ④ 우리 기간탭을 얹지 않는다 — 위젯이 자체 withdateranges 를 갖고 있어 죽은 버튼이 된다.
import { useDark, palette, rawPalette, FONT } from "@/lib/theme"

const TV_EMBED_SRC = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js"

/** TradingView 심볼로 쓸 수 있는가 — 미국 티커(영문)만. 6자리 숫자(KR)는 거부됨. */
export function tvSupported(ticker: string): boolean {
    return /^[A-Za-z][A-Za-z.\-]{0,6}$/.test(String(ticker || "").trim())
}

function tvWidgetHtml(symbol: string, dark: boolean, bg: string): string {
    const cfg = {
        autosize: true,
        symbol,
        interval: "D",
        timezone: "Asia/Seoul",
        theme: dark ? "dark" : "light",
        style: "1",
        locale: "kr",
        hide_side_toolbar: true,
        allow_symbol_change: false,
        save_image: false,
        withdateranges: true,
        support_host: "https://www.tradingview.com",
    }
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">' +
        "<style>*{margin:0;padding:0;border-radius:0!important}html,body,.tradingview-widget-container{width:100%;height:100%;overflow:hidden;border:none;background:" +
        bg +
        '}</style></head><body><div class="tradingview-widget-container">' +
        '<div class="tradingview-widget-container__widget" style="width:100%;height:100%"></div>' +
        '<script src="' +
        TV_EMBED_SRC +
        '" async>' +
        JSON.stringify(cfg) +
        "</scr" +
        "ipt></div></body></html>"
    )
}

export default function TVChart({ symbol, height = 380 }: { symbol: string; height?: number }) {
    const dark = useDark()
    const c = palette(dark)
    const raw = rawPalette(dark)
    const sym = String(symbol || "").trim().toUpperCase()
    if (!sym) return null
    const h = Math.max(240, height)

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 6, fontFamily: FONT }}>
            <div style={{ width: "100%", height: h, borderRadius: 12, overflow: "hidden", background: c.card, lineHeight: 0 }}>
                <iframe
                    key={sym + (dark ? "-d" : "-l")}
                    title={sym + " 차트"}
                    srcDoc={tvWidgetHtml(sym, dark, raw.card)}
                    style={{ width: "calc(100% + 6px)", height: "calc(100% + 6px)", margin: -3, border: "none", display: "block", background: c.card }}
                    loading="lazy"
                    sandbox="allow-scripts allow-same-origin allow-popups"
                />
            </div>
            {/* attribution 의무 — TV 링크 병기(13px 이상) */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", padding: "0 2px" }}>
                <a
                    href={"https://www.tradingview.com/symbols/" + encodeURIComponent(sym) + "/"}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ fontSize: 13, fontWeight: 600, color: c.faint, textDecoration: "none" }}
                >
                    차트 by TradingView
                </a>
                <span style={{ marginLeft: "auto", fontSize: 9.5, color: c.faint }}>지연 시세 · 기간·지표는 위젯 자체 제공</span>
            </div>
        </div>
    )
}

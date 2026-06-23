import { addPropertyControls, ControlType } from "framer"
import PublicDiscovery from "./PublicDiscovery"

/**
 * PublicUSDiscovery — 미장(US) 스크리너 프리셋 래퍼. 공유 PublicDiscovery 에 US 기본값 baked-in (중복 0).
 *
 * 다크모드·market-aware 국기·토스 로고·라이브 $가격(market=us) = 내부 PublicDiscovery 가 처리 → delegate 자동 연동.
 * KR 전용 URL = 빈값(US 티커 무매칭 회피). reportPath = US 종목 클릭 시 이동할 US 리포트 페이지 경로.
 *
 * ⚠️ Framer: ./PublicDiscovery relative import. 같은 폴더 두 파일 동기화 필요. 미해결 시 self-contained 교체.
 */
const US_STOCK_URL =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_stock_report_public.json"
const US_API = "https://project-yw131.vercel.app"
const US_REPORT_PATH = "/us/stock"

export default function PublicUSDiscovery(props: any) {
    return (
        <PublicDiscovery
            stockUrl={props.stockUrl || US_STOCK_URL}
            apiBase={props.apiBase || US_API}
            reportPath={props.reportPath || US_REPORT_PATH}
            insiderUrl=""
            flowUrl=""
            forensicsUrl=""
            dark={!!props.dark}
            perList={props.perList || 14}
            topOffset={props.topOffset || 0}
        />
    )
}

addPropertyControls(PublicUSDiscovery, {
    stockUrl: { type: ControlType.String, title: "US Stock URL", defaultValue: US_STOCK_URL },
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: US_API },
    reportPath: { type: ControlType.String, title: "US 리포트 경로", defaultValue: US_REPORT_PATH },
    dark: { type: ControlType.Boolean, title: "Dark (canvas)", defaultValue: false },
    perList: { type: ControlType.Number, title: "리스트당 종목", defaultValue: 14 },
    topOffset: { type: ControlType.Number, title: "Top Offset", defaultValue: 0 },
})

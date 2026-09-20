// Evidence report: PDF and plain-text export share one deterministic dossier.
#let D = json(bytes(sys.inputs.data))
#let ink = rgb("#191f28")
#let sub = rgb("#4e5968")
#let accent = rgb("#6c5ce7")
#let increase = rgb("#d92d45")
#let decrease = rgb("#2563eb")
#let hair = rgb("#e5e8eb")
#let fill = rgb("#f5f6f8")
#set page(paper: "a4", margin: (top: 15mm, bottom: 17mm, x: 15mm),
  footer: context [
    #line(length: 100%, stroke: 0.5pt + hair)
    #v(1mm)
    #grid(columns: (1fr, auto), gutter: 5mm,
      text(size: 7pt, fill: sub)[#D.disclaimer],
      text(size: 7pt, fill: sub)[#counter(page).display() / #counter(page).final().first()])
  ])
#set text(font: "Pretendard", size: 9pt, weight: 600, lang: "ko", fill: ink)
#set par(leading: 0.55em)
#set heading(numbering: none)
#show heading: set block(sticky: true)
#show heading.where(level: 1): set text(size: 15pt, weight: 800)
#show heading.where(level: 2): set text(size: 11pt, weight: 800)
#let cell(c) = if type(c) == dictionary {
  link(c.url, text(fill: accent, weight: 700)[#c.text])
} else if type(c) == content { c } else { text(c) }
#let direction-color(direction) = if direction == "up" { increase } else if direction == "down" { decrease } else { sub }
#let change-chip(change) = {
  let arrow = if change.direction == "up" { "↑" } else if change.direction == "down" { "↓" } else if change.direction == "flat" { "→" } else { "—" }
  let color = direction-color(change.direction)
  box(fill: white, radius: 4pt, inset: (x: 5pt, y: 3pt))[
    #text(size: 9pt, weight: 800, fill: color)[#arrow]
    #h(1mm)#text(size: 8pt, weight: 700, fill: color)[#change.label]
  ]
}
#grid(columns: (1fr, auto), gutter: 5mm,
  [#text(size: 19pt, weight: 800)[#D.name]
   #h(2mm)#text(size: 10pt, fill: sub)[#D.ticker · #D.market]
   #if D.business != "—" [#linebreak()#text(size: 8pt, fill: sub)[#D.business]]],
  align(right)[#text(size: 10pt, weight: 800, fill: accent)[ALPHANEST]
    #linebreak()#text(size: 8pt, fill: sub)[#D.report_label]
    #linebreak()#text(size: 7pt, fill: sub)[#D.generated]])
#v(2mm)
#line(length: 100%, stroke: 1pt + ink)
#v(2mm)
#let report-table(headers, rows, widths) = table(
  columns: widths.map(w => w * 1fr), inset: (x: 3pt, y: 5pt),
  stroke: (left: none, right: none, top: none, bottom: 0.4pt + hair),
  table.header(..headers.map(h => text(size: 8pt, weight: 700, fill: sub)[#h])),
  ..rows.flatten().map(c => text(size: 8.5pt)[#cell(c)]))
#let source-row(row) = if row != none [
  #text(size: 7.5pt, fill: sub)[#row.start - #row.end · #row.currency · #(if row.fs_div == "CFS" {"연결"} else if row.fs_div == "ENTITY" {"보고기업 전체(SEC)"} else {"별도"})]
  #h(2mm)#link(row.source_url, text(size: 7.5pt, fill: accent)[공시 원문 ↗])
]
#if "prompt_url" in D [
  #text(size: 7.5pt)[자료를 원하는 AI에 전달하려면: ]
  #link(D.prompt_url, text(size: 7.5pt, fill: accent)[분석 요청문과 근거 자료 받기 ↗])
  #v(1mm)
]
#let R = D.reader
#let V = R.visuals
#let chart-icon(key) = {
  let paths = if key == "annual" {
    "<path d='M3 3v18h18M6 15l5-5 4 3 6-7'/>"
  } else if key == "cash" {
    "<rect x='3' y='5' width='18' height='15' rx='3'/><path d='M16 10h5v5h-5zM6 5V3h12'/><circle cx='18' cy='12.5' r='.6'/>"
  } else {
    "<path d='M6 18L18 6'/><circle cx='7' cy='7' r='3'/><circle cx='17' cy='17' r='3'/>"
  }
  image(bytes("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><g fill='none' stroke='#6c5ce7' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'>" + paths + "</g></svg>"), format: "svg", width: 4mm)
}
#let reading(key) = if key in V.insights {
  let insight = V.insights.at(key)
  block(fill: fill, radius: 6pt, inset: 4mm, width: 100%, breakable: false)[
    #text(size: 10pt, weight: 800)[#insight.title]
    #v(1.5mm)#text(size: 8.5pt)[#insight.meaning]
    #v(1.5mm)#text(size: 8pt, fill: sub)[#insight.evidence]
  ]
}
#let chart(key) = if key in D.chart_images {
  let c = V.charts.at(key)
  block(breakable: false, width: 100%)[
    #grid(columns: (4mm, 1fr), gutter: 2mm, align: horizon,
      chart-icon(key), text(size: 9pt, weight: 800)[#c.title])
    #v(1.5mm)#text(size: 10pt, weight: 800)[#c.takeaway]
    #v(1mm)
    #image(bytes(D.chart_images.at(key)), format: "svg", width: 100%)
    #v(1mm)#text(size: 7pt, fill: sub)[#c.note]
    #v(1mm)
    #for row in c.sources [#source-row(row)#linebreak()]
  ]
}
#let G = D.reading
#let translation-note = [비공식 참고 번역입니다. 수치·조건은 연결된 공시 원문과 함께 확인하세요.]
#let translated-excerpt(original, translation) = [
  #if translation != none [
    #block(breakable: false)[
      #text(size: 7.5pt, weight: 700, fill: accent)[#translation.label]
      #v(1mm)#text(size: 8.5pt)[#translation.text]
      #v(2mm)#text(size: 7pt, fill: sub)[#translation-note]
    ]
    #v(3mm)#text(size: 7.5pt, weight: 700, fill: sub)[영문 원문 대조]
  ] else [
    #text(size: 7.5pt, weight: 700, fill: sub)[한국어 번역 미준비 · 영문 원문]
  ]
  #v(1mm)#text(size: 7.8pt, fill: sub)[#original]
]
#v(2mm)
== 먼저 읽을 세 가지
#for card in G.cards [
  #block(fill: fill, radius: 5pt, inset: 3mm, width: 100%, breakable: false)[
    #text(size: 7.5pt, weight: 700, fill: accent)[#card.label]
    #h(2mm)#text(size: 9pt, weight: 800)[#card.title]
    #v(1mm)#text(size: 8.2pt)[#card.detail]
    #if card.sources.len() > 0 [
      #v(1mm)
      #for row in card.sources [#source-row(row)#h(2mm)]
    ]
  ]
  #v(1.5mm)
]
#v(2mm)
== 어떤 사업을 하는 기업인가
#if D.business_profile.overview != none {
  let b = D.business_profile.overview
  report-table(("구분", "사업 설명"), b.rows, (0.7, 3.3))
  v(1mm)
  text(size: 7pt, fill: sub)[#b.label · #cell(b.source)]
} else [
  #block(fill: fill, radius: 5pt, inset: 3mm, width: 100%)[
    #text(size: 8.5pt)[#(if D.business_profile.translation != none { D.business_profile.translation.summary } else { D.business_profile.summary })]
    #v(1mm)#text(size: 7pt, fill: sub)[#D.business_profile.label]
    #if D.business_profile.source != none [#h(2mm)#cell(D.business_profile.source)]
    #if D.business_profile.available [#v(1mm)#text(size: 7pt, fill: sub)[회사 설명의 일부입니다. 수신한 발췌문 전체는 부록 B1에서 확인할 수 있습니다.]]
  ]
]
#v(5mm)
== 최근 실적에서 달라진 점
#if R.current != none [
  #source-row(R.current)
  #v(1mm)
  #text(size: 8pt, fill: sub)[기간 구분: #(if R.current.period_kind == "quarter" {"단일 분기"} else if R.current.period_kind == "ytd" {"누적"} else {"연간"}). #(if R.prior != none {"전년 동기는 같은 기간 길이·통화·보고 범위로 맞췄습니다."} else {"같은 기준의 전년 동기를 확보하지 못해 증감률을 계산하지 않았습니다."})]
  #v(2mm)
  #grid(columns: (1fr, 1fr, 1fr), gutter: 2mm,
    ..R.metrics.map(m => block(fill: fill, radius: 5pt, inset: 3mm, width: 100%, breakable: false)[
      #text(size: 8pt, weight: 700, fill: sub)[#m.label · 이번 기간]
      #v(2mm)#text(size: 17pt, weight: 800)[#m.current]
      #v(1mm)#text(size: 8pt, fill: sub)[전년 동기 #m.prior]
      #v(2mm)#change-chip(m.change)
    ]))
  #v(1mm)#text(size: 7pt, fill: sub)[화살표·색은 수치의 방향입니다. 유리·불리의 판정이 아닙니다.]
  #if R.prior != none [#v(1mm)#text(size: 7pt, fill: sub)[전년 동기: ]#source-row(R.prior)]
] else [#text(size: 8.5pt, fill: sub)[본문에 사용할 재무 근거가 충분하지 않습니다. 확인 전 수치와 누락 범위는 부록에 구분했습니다.]]
#for note in R.observations [#v(2mm)#text(size: 8.5pt)[#note]]
#v(3mm)
#if "bridge" in D.chart_images [#chart("bridge")] else [#chart("margin")]
#v(3mm)
#reading("income")
#if "annual" in D.chart_images [
  #v(4mm)
  == 실적의 흐름을 함께 읽기
  #v(2mm)
  #chart("annual")
  #v(3mm)
  #reading("annual")
]
#if not ("annual" in D.chart_images) [
#v(3mm)
== 연간 수치 확인
#if D.annual_core.len() > 0 [
  #report-table(("실제 기간", "매출", "영업이익", "순이익"), D.annual_core, (1.65, 1, 1, 1))
  #v(1mm)#text(size: 7pt, fill: sub)[연간 수치입니다. 위의 단일 분기·누적 실적과 금액 크기를 직접 비교하지 마세요. 원문과 기준은 부록 R0·R1.]
] else [#text(size: 8.5pt, fill: sub)[연간 비교에 필요한 기간·통화·보고 범위·원문을 확보하지 못했습니다.]]
]
#v(4mm)
== 이익이 현금으로 이어졌나
#v(2mm)
#if R.cash != none [
  #source-row(R.cash)
  #v(2mm)
  #if "cash" in D.chart_images [#chart("cash")] else [#report-table(("항목", "금액"), R.cash_rows, (2, 1))]
]
#for note in R.cash_notes [#v(2mm)#text(size: 8.5pt)[#note]]
#v(3mm)
#reading("cash")
#v(5mm)
== 최근 공시와 연결하기
#if D.recent_events.len() > 0 [
  #report-table(("제출일", "공시 제목", "유형", "원문"), D.recent_events, (0.8, 2.5, 0.7, 0.7))
  #v(1mm)#text(size: 7.5pt, fill: sub)[수신된 최근 3건 이내입니다. 제목만으로 실적 영향이나 호재·악재를 판단하지 않습니다.]
] else [#text(size: 8.5pt, fill: sub)[최근 공시 자료를 받지 못했습니다. 사건이나 위험이 없다는 뜻은 아닙니다.]]
#v(4mm)
#block(sticky: true, breakable: false)[
  == 최근 관련 뉴스 · 먼저 확인할 보도
  #text(size: 7pt, fill: sub)[#D.news.window_start - #D.news.window_end · 조건 일치 #(D.news.shown)/#(D.news.eligible)건 표시]
  #v(1mm)#text(size: 7.5pt, fill: sub)[#D.news.note]
]
#for n in D.news.items [
  #v(2mm)
  #block(fill: fill, radius: 5pt, inset: 3mm, width: 100%, breakable: false)[
    #text(size: 7.5pt, weight: 700, fill: accent)[#n.category]
    #if n.recent_24h [#h(2mm)#text(size: 7pt, weight: 700)[최근 24시간]]
    #v(1mm)#text(size: 9pt, weight: 800)[#n.title]
    #v(1.5mm)#text(size: 7pt, fill: sub)[#n.source · #n.display_time]
    #h(2mm)#link(n.url, text(size: 7.5pt, weight: 700, fill: accent)[#n.link_label ↗])
  ]
]
#v(4mm)
== 회사는 변화를 어떻게 설명했나
#text(size: 7.5pt, fill: sub)[회사 공시의 설명입니다. 독립적으로 입증한 원인을 뜻하지 않습니다. 설명 미확보는 영향 없음과 다릅니다.]
#if G.company.excerpts.len() == 0 [#v(1mm)#text(size: 7.5pt, fill: sub)[#G.company.note]]
#if D.translation_coverage.total > 0 [#v(1mm)#text(size: 7.5pt, fill: sub)[이 리포트의 영문 발췌 번역: #(D.translation_coverage.translated)/#(D.translation_coverage.total)개. 전체 공시의 번역 범위는 아닙니다.]]
#v(2mm)
#if G.company.excerpts.len() > 0 [#report-table(("설명 항목", "현재 연결 상태"), G.company.topics.map(t => (t.label, if t.refs.len() > 0 { t.refs.join(" · ") + " 문단에 관련 표현 수신" } else { "해당 기간 설명 미확보" })), (1, 3))]
#for q in G.company.excerpts [
  #v(2mm)
  #block(fill: fill, radius: 5pt, inset: 3mm, width: 100%, breakable: false)[
    #text(size: 8pt, weight: 700, fill: accent)[#q.id · #q.metric · #q.period]
    #v(1mm)#translated-excerpt(q.quote, q.translation)
  ]
]
#if G.company.source != none [#v(2mm)#cell(G.company.source)]
#v(4mm)
== 다음 공시에서 확인할 항목
#report-table(("항목", "현재 상태", "다음 비교 기준 · 근거"), G.checklist.map(r => (r.item, r.state, [#r.next #linebreak()#cell(r.source)])), (0.7, 1.6, 2))
#v(4mm)
#text(size: 7.8pt, fill: sub)[본문 재무: 기준을 갖춘 #(R.accepted)/#(R.received)개 기간. 보고된 숫자와 자체계산을 구분했습니다. 항목별 계정·기간·원문 및 자료 누락은 다음 부록에서 확인할 수 있습니다.]
#v(6mm)
#line(length: 100%, stroke: 0.7pt + hair)
= 부록 · 자료 범위와 확인할 빈칸
#text(size: 8.5pt, fill: sub)[수신된 자료의 한계입니다. 없는 정보를 추정으로 채우지 않습니다.]
#v(3mm)
#for g in D.gaps [
  #block(breakable: false, inset: (bottom: 2.3mm))[
    #text(fill: accent)[·] #g
  ]
]
#v(3mm)
== 자료 점검표
#text(size: 8pt, fill: sub)[수신 여부는 이 종목의 자료가 있는지를 뜻합니다. 파일 생성·공시 제출·SEC 조회 시점이며, 재무·보유·거래 기준일은 각 표에서 확인하세요.]
#v(2mm)
#table(columns: (0.35fr, 1fr, 1.25fr, 1.5fr), inset: 4pt,
  stroke: (left: none, right: none, top: none, bottom: 0.4pt + hair),
  table.header(..("ID", "자료", "조회 결과", "갱신·제출·조회").map(h => text(size: 8pt, weight: 700)[#h])),
  ..D.coverage.map(c => (c.id, c.label, c.status, c.published)).flatten().map(c => text(size: 8pt)[#c]))
#v(3mm)
#for c in D.coverage [
  #block(breakable: false, inset: (bottom: 2mm))[
    #text(size: 7.8pt, weight: 700)[#c.id · #c.label]
    #text(size: 7pt, fill: sub)[ — #c.source]
    #linebreak()
    #if c.artifact_url != "" [#text(size: 7pt, fill: accent)[#link(c.artifact_url)[발행 자료 · #c.file]]] else [#text(size: 7pt, fill: sub)[원문 위치 미수신]]
    #if c.reason != "" [#linebreak()#text(size: 7pt, fill: sub)[#c.reason]]
  ]
]
#v(6mm)
#line(length: 100%, stroke: 0.7pt + hair)
= 근거를 따라 읽는 자료
#text(size: 8pt, fill: sub)[표 제목 옆 ID는 앞의 질문과 연결됩니다. 원문 열기는 수신된 문서 URL, 출처 목록은 문서 검색 페이지입니다.]
#for s in D.sections {
  v(3mm)
  block(breakable: true)[
    #block(breakable: false, sticky: true)[
      #text(size: 11pt, weight: 800)[#s.title]
      #h(2mm)#text(size: 7.4pt, fill: accent)[#s.id · 표시 #(s.shown)/#(s.total)행]
      #v(1mm)
      #text(size: 7.8pt, fill: sub)[#s.note]
    ]
    #v(1mm)
    #if s.id == "B1" and D.market == "US" {
      translated-excerpt(D.business_profile.text, D.business_profile.translation)
      v(2mm)
      cell(D.business_profile.source)
    } else { table(columns: s.widths.map(w => w * 1fr),
      inset: (x: 2pt, y: 3.5pt), stroke: (left: none, right: none, top: none, bottom: 0.4pt + hair),
      table.header(..s.headers.map(h => text(size: 8pt, weight: 700, fill: sub)[#h])),
      ..s.rows.flatten().map(c => text(size: 8.3pt)[#if s.id == "H1" and type(c) == str and c in ("증가", "감소", "유지") {
        text(size: 12pt, weight: 800, fill: direction-color(if c == "증가" { "up" } else if c == "감소" { "down" } else { "flat" }))[#(if c == "증가" { "↑" } else if c == "감소" { "↓" } else { "→" })]
      } else { cell(c) }]))
      if s.id == "H1" { v(1mm); text(size: 7pt, fill: sub)[↑ 주식수 증가 · ↓ 주식수 감소 · → 유지 · 신규는 별도 표시] }
    }
  ]
}

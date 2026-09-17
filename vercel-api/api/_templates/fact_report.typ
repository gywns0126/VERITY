// Evidence report: PDF and plain-text export share one deterministic dossier.
#let D = json(bytes(sys.inputs.data))
#let ink = rgb("#191f28")
#let sub = rgb("#4e5968")
#let accent = rgb("#6c5ce7")
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
#show heading.where(level: 1): set text(size: 15pt, weight: 800)
#show heading.where(level: 2): set text(size: 11pt, weight: 800)
#let cell(c) = if type(c) == dictionary {
  link(c.url, text(fill: accent, weight: 700)[#c.text])
} else { text(c) }
#grid(columns: (1fr, auto), gutter: 5mm,
  [#text(size: 19pt, weight: 800)[#D.name]
   #h(2mm)#text(size: 10pt, fill: sub)[#D.ticker · #D.market]
   #linebreak()#text(size: 8pt, fill: sub)[#D.business]],
  align(right)[#text(size: 10pt, weight: 800, fill: accent)[ALPHANEST]
    #linebreak()#text(size: 8pt, fill: sub)[#D.report_label]
    #linebreak()#text(size: 7pt, fill: sub)[#D.generated]])
#v(2mm)
#line(length: 100%, stroke: 1pt + ink)
#v(2mm)
#grid(columns: (1fr, 1fr), gutter: 3mm,
  ..D.kv.map(p => block(fill: fill, radius: 5pt, inset: 3mm, width: 100%)[
    #text(size: 8pt, fill: sub)[#p.at(0)] #h(2mm)#text(weight: 800)[#p.at(1)]
  ]))
#v(3mm)
#text(size: 14pt, weight: 800)[먼저 확인할 질문]
#v(1mm)
#text(size: 8pt, fill: sub)[자료에서 확인되는 변화와 추가 조사할 쟁점을 연결했습니다. 원문을 읽지 않은 해석은 결론으로 제시하지 않습니다.]
#for (i, q) in D.issues.enumerate() {
  v(3mm)
  block(breakable: false, width: 100%, inset: (left: 3mm), stroke: (left: 2pt + accent))[
    #text(size: 10pt, weight: 800)[#(i+1). #q.title]
    #v(1.2mm)
    #text(size: 8.6pt)[#q.observation]
    #v(1mm)
    #text(size: 8.3pt, fill: sub)[확인할 것 · #q.question]
    #v(0.6mm)
    #text(size: 7.2pt, fill: accent)[자료 #q.refs]
  ]
}
#v(4mm)
#block(fill: fill, radius: 5pt, inset: 3mm, width: 100%)[
  #text(weight: 800)[내 AI로 더 분석하려면]
  #v(1mm)
  #text(size: 8.3pt)[이 PDF를 첨부하거나, 아래 분석 요청문을 내려받아 사용하는 AI에 붙여넣으세요. 같은 자료와 출처, 누락 사항, 분석 지침이 함께 들어 있습니다.]
  #v(1mm)
  #if "prompt_url" in D { link(D.prompt_url, text(fill: accent, weight: 700)[분석 요청문과 자료 받기 ↗]) }
]
#pagebreak()
= 해석 전에 확인할 빈칸
#text(size: 8.5pt, fill: sub)[수신된 자료의 한계입니다. 없는 정보를 추정으로 채우지 않습니다.]
#v(3mm)
#for g in D.gaps [
  #block(breakable: false, inset: (bottom: 2.3mm))[
    #text(fill: accent)[·] #g
  ]
]
#v(3mm)
== 자료 점검표
#text(size: 8pt, fill: sub)[수신 여부는 이 종목의 자료가 있는지를 뜻합니다. 아래 갱신 시각은 파일 생성 시각이며, 재무·보유·거래 기준일은 각 표에서 확인하세요.]
#v(2mm)
#table(columns: (0.35fr, 1fr, 1.25fr, 1.5fr), inset: 4pt,
  stroke: (left: none, right: none, top: none, bottom: 0.4pt + hair),
  table.header(..("ID", "자료", "조회 결과", "파일 갱신").map(h => text(size: 8pt, weight: 700)[#h])),
  ..D.coverage.map(c => (c.id, c.label, c.status, c.published)).flatten().map(c => text(size: 8pt)[#c]))
#v(3mm)
#for c in D.coverage [
  #block(breakable: false, inset: (bottom: 2mm))[
    #text(size: 7.8pt, weight: 700)[#c.id · #c.label]
    #text(size: 7pt, fill: sub)[ — #c.source]
    #linebreak()
    #text(size: 7pt, fill: accent)[#link("https://rte5guenhonw9fzn.public.blob.vercel-storage.com/" + c.file)[발행 자료 · #c.file]]
    #if c.reason != "" [#linebreak()#text(size: 7pt, fill: sub)[#c.reason]]
  ]
]
#pagebreak()
= 근거를 따라 읽는 자료
#text(size: 8pt, fill: sub)[표 제목 옆 ID는 앞의 질문과 연결됩니다. 원문 열기는 수신된 문서 URL, 출처 목록은 문서 검색 페이지입니다.]
#for s in D.sections {
  v(4mm)
  block(breakable: s.rows.len() > 12)[
    #block(breakable: false, sticky: true)[
      #text(size: 11pt, weight: 800)[#s.title]
      #h(2mm)#text(size: 7.4pt, fill: accent)[#s.id · 표시 #(s.shown)/#(s.total)행]
      #v(1mm)
      #text(size: 7.8pt, fill: sub)[#s.note]
    ]
    #v(1mm)
    #table(columns: s.widths.map(w => w * 1fr),
      inset: (x: 2pt, y: 4pt), stroke: (left: none, right: none, top: none, bottom: 0.4pt + hair),
      table.header(..s.headers.map(h => text(size: 8pt, weight: 700, fill: sub)[#h])),
      ..s.rows.flatten().map(c => text(size: 8.3pt)[#cell(c)]))
  ]
}
#v(4mm)
#line(length: 100%, stroke: 0.5pt + hair)
#text(size: 8pt, fill: sub)[#D.source_line]

// @ts-nocheck
// Generated review bundle; source modules were typechecked before bundling.
// Review only: no published page replacement, fixture holdings, or embedded credentials.
// output/member-map-integration-20260927/PortfolioMapReview.entry.tsx
import * as React9 from "react";
import { addPropertyControls, ControlType, useIsStaticRenderer } from "framer";

// framer-components/public-probe/PublicPortfolioMap.tsx
import * as React8 from "react";

// framer-components/public-probe/StockInfoMapData.tsx
var SECTION_ORDER = [
  { id: "business", title: "사업·경쟁력" },
  { id: "finance", title: "실적·재무" },
  { id: "valuation", title: "가격·가치 비교" },
  { id: "events", title: "최근 변화·일정" },
  { id: "holders", title: "주주·자본 배분" },
  { id: "risks", title: "위험·확인할 질문" }
];
var sectionTitle = (id) => SECTION_ORDER.find((section) => section.id === id).title;
var text = (value) => typeof value === "string" ? value.trim() : value == null ? "" : String(value).trim();
var record = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : {};
var list = (value) => Array.isArray(value) ? value.filter((item) => item && typeof item === "object") : [];
var hasValue = (value) => value !== void 0 && value !== null && text(value) !== "";
var isFailure = (value) => !!record(value).__infoMapError;
var factTitle = (key) => ({ PER: "PER (주가수익비율)", PBR: "PBR (주가순자산비율)", PSR: "PSR (주가매출비율)", ROE: "ROE (자기자본이익률)", BPS: "BPS (주당순자산)", EPS: "EPS (주당순이익)", FCF: "FCF (잉여현금흐름)", "D/E": "D/E (부채비율)" })[key] || key;
var factExplanation = (note) => typeof note === "string" ? text(note) : text(record(note).description) || text(record(note).explanation) || text(record(note).note);
var factAsOf = (note) => {
  const value = record(note);
  return text(value.as_of) || text(value.asOf) || text(value.period_end) || text(value.end) || text(value.date) || void 0;
};
var factSection = (key) => /^(PER|PBR|PSR|BPS|EPS|PEG|EV\/EBITDA|시가총액)$/.test(key) ? "valuation" : /배당|자사주|주주환원/.test(key) ? "holders" : /Altman|위험|소송|희석/.test(key) ? "risks" : "finance";
function factItems(report, sectionId) {
  const notes = record(report.facts_note), calculations = record(report.facts_calc);
  return Object.entries(record(report.facts)).map(([key, value], index) => ({ key, value, index })).filter(({ key, value }) => factSection(key) === sectionId && hasValue(value)).map(({ key, value, index }) => {
    const note = notes[key], calculation = text(calculations[key]);
    return {
      id: `fact-${index}`,
      title: factTitle(key),
      value: text(value),
      topic: sectionId === "valuation" ? "가격과 비교하는 지표" : sectionId === "holders" ? "주주 환원" : sectionId === "risks" ? "위험 참고 지표" : "수익성·재무 지표",
      explanation: [factExplanation(note) || "발행 종목 리포트에 제공된 지표입니다.", calculation && `계산 기준: ${calculation}`, key === "Altman-Z" && "통계모형 지표이며 기업의 안전이나 부도를 확정하지 않습니다."].filter(Boolean).join("\n"),
      asOf: factAsOf(note),
      source: sourceLabel(record(note).source, "발행 종목 리포트"),
      url: safeHttpLink(record(note).source_url || record(note).url),
      relationship: "unknown"
    };
  });
}
function readySection(id, items, message) {
  return { id, title: sectionTitle(id), items, state: items.some((item) => item.kind !== "question") ? "ready" : "empty", ...message ? { message } : {} };
}
var periodOrder = (row) => `${text(row.end) || "0000-00-00"}\0${text(row.year).padStart(8, "0")}`;
function uniqueAnnual(rows2) {
  const unique3 = /* @__PURE__ */ new Map();
  for (const row of rows2.slice().sort((a, b) => periodOrder(a).localeCompare(periodOrder(b)))) unique3.set(`${text(row.start)}\0${text(row.end)}\0${text(row.year)}`, row);
  return [...unique3.values()].sort((a, b) => periodOrder(a).localeCompare(periodOrder(b)));
}
function safeHttpLink(value) {
  const raw = text(value);
  if (!raw || /[\r\n]/.test(raw)) return void 0;
  try {
    const url = new URL(raw);
    return (url.protocol === "https:" || url.protocol === "http:") && !url.username && !url.password ? url.href : void 0;
  } catch {
    return void 0;
  }
}
function errorSection(id, message) {
  const title = sectionTitle(id);
  return { id, title, items: [], state: "error", message };
}
function sourceLabel(value, fallback) {
  const source = text(value);
  return source || fallback;
}
function money(value, currency) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "";
  const unit = text(currency);
  return unit ? `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value)} ${unit}` : "";
}
function businessSection(slice, failed) {
  if (failed) return errorSection("business", "종목 정보 요청에 실패했습니다.");
  const overview = record(slice.business_overview);
  const report = record(slice.report);
  const excerpt = text(overview.text);
  const items = excerpt ? [{
    id: "business-overview",
    title: "사업 개요",
    topic: "무엇으로 돈을 버나",
    explanation: excerpt,
    asOf: text(overview.filed_at) || void 0,
    source: sourceLabel(overview.source, "DART 사업보고서"),
    url: safeHttpLink(overview.url),
    relationship: "direct"
  }] : [];
  const business = text(report.business);
  if (!excerpt && business) items.push({ id: "business-report", title: "사업 설명", topic: "무엇으로 돈을 버나", explanation: business, source: "발행 종목 리포트", relationship: "unknown" });
  const peer = record(report.peer), company = record(report.overview);
  const industry = [text(peer.sector) || text(company.sector) || text(report.gics_ko) || text(report.gics), text(peer.industry)].filter(Boolean);
  if (industry.length) items.push({ id: "industry", title: "업종 분류", topic: "어떤 시장에 속하나", explanation: industry.join(" · "), source: "발행 종목 리포트", relationship: "unknown" });
  const chain = record(report.supply_chain), seen = /* @__PURE__ */ new Set();
  list(chain.snippets).forEach((row, index) => {
    const snippet = text(row.snippet);
    if (!snippet || seen.has(snippet)) return;
    seen.add(snippet);
    items.push({ id: `customer-${index}`, title: `${text(row.anchor) || "고객·공급망"} · 발췌 ${index + 1}`, topic: "누구와 거래하나", explanation: snippet, source: [text(chain.report_nm), text(chain.note) || "사업보고서 발췌"].filter(Boolean).join(" · "), asOf: text(chain.rcept_dt) || void 0, url: safeHttpLink(chain.source_url), relationship: "direct" });
  });
  return readySection("business", items, items.length ? "사업 설명·거래처 발췌입니다. 경쟁 우위가 입증됐다는 뜻은 아닙니다." : "사업 원문이 제공되지 않았습니다.");
}
function financeSection(slice, failed) {
  if (failed) return errorSection("finance", "종목 정보 요청에 실패했습니다.");
  const report = record(slice.report);
  const periods = list(record(report.financial_evidence).periods);
  const annual = periods.filter((row) => text(row.period_kind) === "annual" && text(row.currency) && text(row.fs_div) && (Number.isFinite(row.revenue) || Number.isFinite(row.op) || Number.isFinite(row.net)));
  const evidenceGroups = annual.reduce((groups2, row) => {
    const key = `${text(row.currency)}\0${text(row.fs_div)}`;
    groups2[key] = [...groups2[key] || [], row];
    return groups2;
  }, {});
  const evidenceSeries = Object.values(evidenceGroups).map(uniqueAnnual).sort((a, b) => b.length - a.length || periodOrder(b[b.length - 1] || {}).localeCompare(periodOrder(a[a.length - 1] || {})))[0] || [];
  const latestEvidence = evidenceSeries[evidenceSeries.length - 1];
  const legacyUSAnnual = /^(US|NASDAQ|NYSE|AMEX)$/.test(text(slice.market).toUpperCase());
  const fallbackGroups = list(report.fin_series).filter((row) => (text(row.period_kind) === "annual" || legacyUSAnnual && !text(row.period_kind) && Number.isInteger(row.year)) && text(row.currency) && (Number.isFinite(row.revenue) || Number.isFinite(row.op) || Number.isFinite(row.net))).reduce((groups2, row) => {
    const currency = text(row.currency);
    groups2[currency] = [...groups2[currency] || [], row];
    return groups2;
  }, {});
  const fallbackSeries = Object.values(fallbackGroups).map(uniqueAnnual).sort((a, b) => b.length - a.length || periodOrder(b[b.length - 1] || {}).localeCompare(periodOrder(a[a.length - 1] || {})))[0] || [];
  const verifiedSeries = latestEvidence ? evidenceSeries : fallbackSeries;
  const latest = latestEvidence || verifiedSeries[verifiedSeries.length - 1];
  const income = latest ? [{
    id: "annual-income",
    title: "최근 연간 실적",
    topic: "얼마나 벌었나",
    explanation: [text(latest.fs_div) === "CFS" ? "연결 재무제표" : text(latest.fs_div) === "OFS" ? "별도 재무제표" : "", text(latest.filed) ? `제출 ${text(latest.filed)}` : ""].filter(Boolean).join(" · ") || "회계연도별 금액입니다. 원문 통화를 유지하며 정확한 금액은 자세히 보기에서 확인할 수 있어요.",
    asOf: text(latest.start) && text(latest.end) ? `${text(latest.start)} ~ ${text(latest.end)}` : hasValue(latest.year) ? `${text(latest.year)} 회계연도` : void 0,
    source: latestEvidence ? sourceLabel(record(report.financial_evidence).source, "재무제표 원문") : "발행 종목 리포트",
    url: safeHttpLink(latest.source_url),
    relationship: latestEvidence ? "direct" : "unknown",
    rows: [["매출", latest.revenue], ["영업이익", latest.op], ["순이익", latest.net]].filter(([, value]) => Number.isFinite(value)).map(([label2, value]) => ({ label: label2, value: money(value, latest.currency) })),
    chart: verifiedSeries.slice(-6).filter((row) => Number.isFinite(row.revenue)).map((row) => ({ label: text(row.year), value: row.revenue })),
    unit: text(latest.currency)
  }] : [];
  const financials = record(report.financials);
  const groups = list(financials.groups).map((group, index) => ({
    id: `statement-${index}`,
    title: text(group.title) || "재무제표",
    topic: /현금/.test(text(group.title)) ? "현금이 남나" : /상태/.test(text(group.title)) ? "재무 구조는 어떤가" : "실적의 세부 항목",
    explanation: "발행 리포트의 재무제표 요약입니다. 표시 단위와 기준 기간을 원자료와 함께 확인하세요.",
    asOf: text(financials.period) || void 0,
    source: "발행 종목 리포트",
    relationship: "unknown",
    rows: list(group.rows).filter((row) => text(row.k) && hasValue(row.v)).map((row) => ({ label: text(row.k), value: text(row.v) }))
  })).filter((item) => item.rows.length > 0);
  const items = [...income, ...factItems(report, "finance"), ...groups];
  return readySection("finance", items, items.length ? void 0 : "재무 지표가 제공되지 않았습니다.");
}
function valuationSection(slice, failed) {
  if (failed) return errorSection("valuation", "종목 정보 요청에 실패했습니다.");
  const report = record(slice.report), peer = record(report.peer);
  const items = factItems(report, "valuation");
  const rows2 = list(peer.rows).filter((row) => text(row.key) && hasValue(row.value) && hasValue(row.median));
  if (rows2.length) items.push({
    id: "peer-comparison",
    title: "같은 분류 기업의 중앙값",
    topic: "무엇과 비교하나",
    explanation: [text(peer.sector), hasValue(peer.n) ? `지표별 비교 표본 최대 ${text(peer.n)}개 기업 (각 지표의 표본 수는 미제공)` : "비교 기업 수 미제공", text(peer.note), "중앙값은 크기순 가운데 값입니다. 개별 지표의 동일 기준일·기간은 확인되지 않았으며, 낮거나 높다는 이유만으로 저평가·고평가로 판단하지 않습니다."].filter(Boolean).join("\n"),
    rows: rows2.map((row) => ({ label: factTitle(text(row.key)), value: `기업 ${text(row.value)} / 중앙값 ${text(row.median)}` })),
    source: "발행 종목 리포트 · 비교 집계",
    asOf: text(peer.as_of) || void 0,
    relationship: "unknown"
  });
  return readySection("valuation", items, "이 조회에는 시각이 확인된 주가·과거 가치평가 비교가 없습니다. 지표별 가격·실적 기준이 다를 수 있어요.");
}
function eventsSection(slice, news, sliceFailed, newsFailed) {
  const report = record(slice.report);
  const disclosures = list(report.disclosures).map((item, index) => ({
    id: `disclosure-${index}`,
    title: text(item.title) || "공시",
    topic: "기업이 알린 변화",
    explanation: text(item.filer) ? `제출인: ${text(item.filer)}` : "발행 종목 리포트의 공시 항목입니다.",
    asOf: text(item.date) || void 0,
    source: "공시 원문",
    url: safeHttpLink(item.source_url),
    relationship: "direct",
    ...item.is_correction ? { reason: "정정공시" } : {}
  }));
  const articles = list(news.items).map((item, index) => {
    const linkedDisclosure = text(record(item.related_disclosure).title);
    return {
      id: `news-${index}`,
      title: text(item.title) || "뉴스",
      topic: "보도된 소식 · 관계 확인 필요",
      explanation: linkedDisclosure ? `연결 공시 후보: ${linkedDisclosure}. 가까운 날짜로 연결된 후보이며 같은 사건으로 확인되지 않았습니다.` : "제목 회사명 일치 기준으로 수집된 기사입니다. 실제 사업 관련성은 원문에서 확인하세요.",
      asOf: text(item.datetime) || void 0,
      source: sourceLabel(item.source, "뉴스 원문"),
      url: safeHttpLink(item.url),
      relationship: "unknown"
    };
  });
  const schedules = list(report.calendar).map((item, index) => ({
    id: `schedule-${index}`,
    title: text(item.event) || "일정",
    topic: "확인할 일정",
    explanation: [text(item.basis) || "발행 종목 리포트에 제공된 일정입니다.", /예상|패턴|자체계산/.test(text(item.event) + text(item.basis)) ? "예상 일정이며 확정 발표일이 아닙니다." : "확정 여부는 원문에서 확인하세요."].join("\n"),
    asOf: text(item.date) || void 0,
    source: "발행 종목 리포트",
    url: safeHttpLink(item.source_url),
    relationship: "unknown"
  }));
  const documentItems = /* @__PURE__ */ new Map(), documents = [];
  for (const item of [...disclosures, ...articles]) {
    const previous = item.url ? documentItems.get(item.url) : void 0;
    const source = { title: item.title, source: item.source, asOf: item.asOf, url: item.url };
    if (previous) {
      previous.sources = [...previous.sources || [{ title: previous.title, source: previous.source, asOf: previous.asOf, url: previous.url }], source];
      if (item.reason) previous.reason = item.reason;
    } else {
      documents.push(item);
      if (item.url) documentItems.set(item.url, item);
    }
  }
  const dateOrder = (item) => (item.asOf || "").replace(/[^0-9]/g, "").slice(0, 12).padEnd(12, "0");
  const items = [...schedules, ...documents.sort((a, b) => dateOrder(b).localeCompare(dateOrder(a)))];
  const problems = [sliceFailed && "공시·일정을 불러오지 못했습니다.", newsFailed && "뉴스를 불러오지 못했습니다. 이 종목의 뉴스 제공 범위도 확인이 필요합니다."].filter(Boolean).join(" ");
  if (!items.length && (sliceFailed || newsFailed)) return errorSection("events", problems);
  return readySection("events", items, problems || "같은 원문 주소만 한 항목으로 묶습니다. 날짜·제목이 비슷한 자료는 같은 사건으로 단정하지 않아요.");
}
function holdersSection(slice, failed, events) {
  if (failed) return errorSection("holders", "종목 정보 요청에 실패했습니다.");
  const report = record(slice.report), ownership = record(report.ownership), dividends = record(report.dividends);
  const shareholders = list(ownership.shareholders).filter((holder) => text(holder.name) && hasValue(holder.pct));
  const keys = ["family_pct", "latest_pct", "n_13d", "n_13g", "total", "window_total"].filter((key) => hasValue(ownership[key]));
  const summaryRows = keys.map((key) => ({ label: key === "family_pct" ? "총수일가 지분" : key === "latest_pct" ? "최신 지분율" : key === "n_13d" ? "13D 건수" : key === "n_13g" ? "13G 건수" : key === "total" ? "공시 건수" : "조회 창 공시 건수", value: key.endsWith("pct") ? `${text(ownership[key])}%` : text(ownership[key]) }));
  const holderRows = shareholders.map((holder) => ({ label: [text(holder.name), text(holder.type)].filter(Boolean).join(" · "), value: `${text(holder.pct)}%` }));
  const items = keys.length || shareholders.length ? [{
    id: "ownership-summary",
    title: "보유·지분 요약",
    topic: "누가 보유하나",
    explanation: [text(ownership.note), hasValue(ownership.fiscal_year) ? `기준 회계연도: ${text(ownership.fiscal_year)}` : "", text(ownership.collected_at) && `자료 수집일: ${text(ownership.collected_at)} (보유 기준일과 다를 수 있음)`].filter(Boolean).join(" · ") || "발행 종목 리포트에 제공된 보유·지분 정보입니다.",
    source: text(ownership.kind) || "발행 종목 리포트",
    asOf: text(ownership.collected_at) || void 0,
    relationship: "unknown",
    rows: holderRows.length ? holderRows : summaryRows
  }] : [];
  const dividendRows = list(dividends.recent).filter((row) => hasValue(row.dps) && text(row.record_date));
  if (dividendRows.length) items.push({
    id: "dividend-history",
    title: "배당 이력",
    topic: "주주에게 어떻게 돌려주나",
    explanation: [text(dividends.note), "배당기준일과 지급일을 구별합니다. 배당기준일은 배당락일이 아닙니다."].filter(Boolean).join("\n"),
    rows: dividendRows.map((row) => ({ label: `기준 ${text(row.record_date)} · 지급 ${text(row.pay_date) || "미제공"}`, value: `${text(row.dps)}원/주` })),
    asOf: text(dividends.source_bas_dt) || void 0,
    source: text(dividends.source) || "발행 종목 리포트",
    relationship: "unknown"
  });
  items.push(...factItems(report, "holders"));
  const capital = events.items.filter((item) => item.id.startsWith("disclosure-") && /배당|자기주식|유상증자|무상증자|전환사채|신주인수권|소유상황|대량보유/.test(item.title));
  if (capital.length) items.push({ id: "capital-events", title: "주주·자본 관련 공시", topic: "지분·주식 수의 변화", explanation: "공시 제목으로 분류한 항목입니다. 거래 실행·희석 규모·사업 영향은 원문 확인이 필요합니다.", source: "공시 제목", relationship: "direct", references: capital.map((item) => ({ sectionId: "events", itemId: item.id, label: `${item.title} · ${item.asOf || "날짜 미제공"}` })) });
  return readySection("holders", items, items.length ? void 0 : "보유·배당·자본 관련 자료가 제공되지 않았습니다.");
}
function risksSection(slice, failed, sections) {
  if (failed) return errorSection("risks", "기업 자료 조회에 실패해 확인 질문을 구성하지 못했습니다.");
  const report = record(slice.report), overhang = record(report.overhang);
  const items = factItems(report, "risks");
  const riskRows = [["발행결정 공시 수", overhang.count], ["잠재 희석 비율", hasValue(overhang.dilution_pct) ? `${text(overhang.dilution_pct)}%` : void 0], ["발행 가능 주식 수", overhang.issuable_shares]].filter(([, value]) => hasValue(value)).map(([label2, value]) => ({ label: text(label2), value: text(value) }));
  if (riskRows.length) items.push({ id: "potential-dilution", title: "전환사채·신주인수권부사채", topic: "주식 수가 늘어날 수 있나", explanation: [text(overhang.note), text(overhang.window) && `조회 범위: ${text(overhang.window)}`, "발행결정 기준 잠재치이며 실제 전환·발행된 수량으로 해석하지 않습니다."].filter(Boolean).join("\n"), source: "발행 종목 리포트 · 공시 집계", relationship: "unknown", rows: riskRows, reason: "잠재 희석 확인" });
  const ref = (sectionId, predicate) => (sections.find((section) => section.id === sectionId)?.items || []).filter(predicate).map((item) => ({ sectionId, itemId: item.id, label: item.title }));
  const question = (id, title, explanation, references = []) => items.push({ id, title, explanation, kind: "question", topic: "확인 질문 · 위험 발생 사실 아님", source: "알파네스트 · 자료 확인 질문", relationship: "unknown", references });
  const corrections = ref("events", (item) => item.reason === "정정공시");
  if (corrections.length) question("question-correction", "정정 전후 무엇이 달라졌나요?", "정정 사유·금액·기간을 원문에서 비교하세요. 정정 사실만으로 악재라고 판단하지 않습니다.", corrections);
  const customers = ref("business", (item) => item.id.startsWith("customer-"));
  if (customers.length) question("question-customers", "특정 고객에 매출이 집중돼 있나요?", "거래처 이름만으로 매출 비중을 알 수 없습니다. 고객별 비중·계약 조건을 확인하세요.", customers);
  const financials = ref("finance", (item) => item.id === "annual-income" || /현금|부채|D\/E|FCF/.test(item.title));
  question("question-cash", "이익이 현금으로 이어지고, 부채를 감당할 수 있나요?", "실적·현금흐름·부채 만기 자료를 함께 확인하세요. 자료가 없거나 비율 하나가 낮다는 이유로 위험이 없다고 판단하지 않습니다.", financials);
  const undated = sections.flatMap((section) => section.items.filter((item) => item.value && !item.asOf).map((item) => ({ sectionId: section.id, itemId: item.id, label: item.title })));
  if (undated.length) question("question-basis", "숫자의 기준일·계산 기간이 같나요?", "기준일이 따로 제공되지 않은 지표가 있습니다. 리포트 생성 시각은 가격·재무의 기준일이 아닙니다. 각 계산 설명을 확인하세요.", undated);
  const peer = record(report.peer), classification = [peer.sector, peer.industry, record(report.overview).sector, report.gics, report.gics_ko].map(text).join(" ");
  if (/은행|\bbank(?:s|ing)?\b/i.test(classification)) question("question-industry", "대출 건전성과 자본 여력은 어떤가요?", "은행 업종 확인 질문: 연체율·부실채권·충당금·자본비율을 같은 기간으로 확인하세요. 해당 수치가 이번 지도에 있다고 가정하지 않습니다.");
  else if (/소프트웨어|software/i.test(classification)) question("question-industry", "반복 매출과 고객 유지가 확인되나요?", "소프트웨어 업종 확인 질문: 구독 매출·계약 잔액·고객 유지율의 정의와 기간을 원문에서 확인하세요.");
  else if (/반도체|제조|가전|Semiconductor|Manufactur|Consumer Electronics/i.test(classification)) question("question-industry", "재고·설비투자가 수요와 함께 움직이나요?", "제조업 확인 질문: 재고·가동률·설비투자·수주 기간을 함께 확인하세요. 투자 규모만으로 미래 매출을 추정하지 않습니다.");
  return readySection("risks", items, "확인 질문은 조사 안내이며 위험 발생 사실이 아닙니다. 소송·만기·반대 근거를 빠짐없이 검토한 결과도 아닙니다.");
}
function normalizeInfoMap(ticker, slice, news, usDetail) {
  const requested = text(ticker).toUpperCase(), rawSlice = record(slice), rawNews = record(news);
  const rawReport = record(rawSlice.report);
  const mismatched = (value) => !!text(value) && text(value).toUpperCase() !== requested;
  const sliceFailure = isFailure(slice) ? text(slice.__infoMapError) : text(rawSlice.status) && text(rawSlice.status) !== "ok" ? `응답 상태: ${text(rawSlice.status)}` : mismatched(rawSlice.ticker) || mismatched(rawReport.ticker) ? "응답 티커 불일치" : "";
  const newsFailure = isFailure(news) ? text(news.__infoMapError) : text(rawNews.error) ? text(rawNews.error) : text(rawNews.status) && text(rawNews.status) !== "ok" ? `응답 상태: ${text(rawNews.status)}` : mismatched(rawNews.code) || mismatched(rawNews.ticker) ? "응답 티커 불일치" : "";
  const sliceFailed = !!sliceFailure, newsFailed = !!newsFailure;
  const sliceData = sliceFailed ? {} : rawSlice, newsData = newsFailed ? {} : rawNews, report = record(sliceData.report), extra = record(usDetail);
  const market = text(report.market) || text(sliceData.market);
  const marketUpper = market.toUpperCase();
  const country = /KR|KOSPI|KOSDAQ/.test(marketUpper) ? "kr" : /US|NASDAQ|NYSE|AMEX/.test(marketUpper) ? "us" : void 0;
  const events = eventsSection(sliceData, newsData, sliceFailed, newsFailed);
  const sections = [
    businessSection(sliceData, sliceFailed),
    financeSection(sliceData, sliceFailed),
    valuationSection(sliceData, sliceFailed),
    events,
    holdersSection(sliceData, sliceFailed, events)
  ];
  sections.push(risksSection(sliceData, sliceFailed, sections));
  const missing2 = sections.filter((section) => section.state !== "ready").map((section) => section.title);
  return {
    ticker: requested,
    name: text(report.name) || text(newsData.name) || text(extra.name) || requested,
    market,
    country,
    sections,
    coverage: { ok: sections.length - missing2.length, total: sections.length, missing: missing2 }
  };
}

// framer-components/public-probe/PortfolioMapSources.tsx
var record2 = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : {};
var text2 = (value) => typeof value === "string" ? value.trim() : "";
var rows = (value) => Array.isArray(value) ? value.map(record2) : [];
var flag = (value) => typeof value === "boolean" ? value : null;
var label = (value) => typeof value === "string" && !/[\u0000-\u001f\u007f]/.test(value) ? value.trim() || void 0 : void 0;
function sourceUrl(value) {
  if (typeof value !== "string" || /[\u0000-\u0020\u007f]/.test(value)) return void 0;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password ? url.href : void 0;
  } catch {
    return void 0;
  }
}
function observation(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):?[0-5]\d)$/.test(value)) return void 0;
  const date = /* @__PURE__ */ new Date(`${value.slice(0, 10)}T00:00:00Z`);
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== value.slice(0, 10)) return void 0;
  return value;
}
function acceptedPayload(value, ticker, family) {
  const raw = record2(value), report = record2(raw.report);
  const mismatch = (value2) => !!text2(value2) && text2(value2).toUpperCase() !== ticker;
  if (raw.__infoMapError || text2(raw.status) && text2(raw.status) !== "ok" || family === "news" && raw.error || mismatch(raw.ticker) || mismatch(family === "slice" ? report.ticker : raw.code)) return {};
  return raw;
}
function normalizePortfolioSources(ticker, slice, news) {
  const code = text2(ticker).toUpperCase(), map = normalizeInfoMap(code, slice, news);
  const report = record2(acceptedPayload(slice, code, "slice").report);
  const articles = acceptedPayload(news, code, "news");
  const eventSources = [];
  for (const row of rows(report.disclosures)) {
    const url = sourceUrl(row.source_url);
    if (!url) continue;
    const parsed = new URL(url), receipts = parsed.searchParams.getAll("rcpNo");
    const dartMain = parsed.hostname === "dart.fss.or.kr" && !parsed.port && parsed.pathname === "/dsaf001/main.do";
    const dartReceipt = dartMain && receipts.length === 1 && /^\d{14}$/.test(receipts[0]) ? receipts[0] : void 0;
    const receipt = typeof row.rcept_no === "string" && /^\d{14}$/.test(row.rcept_no) ? row.rcept_no : void 0;
    const receiptConflict = dartMain && !dartReceipt || row.rcept_no != null && row.rcept_no !== "" && (!receipt || receipt !== dartReceipt);
    eventSources.push({
      kind: "disclosure",
      title: text2(row.title) || "공시",
      source: "공시 원문",
      url,
      publishedAt: receiptConflict ? void 0 : label(row.date),
      observedAt: receiptConflict ? void 0 : observation(row.detected_at),
      receiptNumber: receiptConflict ? void 0 : receipt,
      ...receiptConflict ? { receiptConflict: true } : {},
      isCorrection: receiptConflict ? null : flag(row.is_correction),
      isBackfill: receiptConflict ? null : flag(row.is_backfill)
    });
  }
  for (const row of rows(articles.items)) {
    const url = sourceUrl(row.url);
    if (url) eventSources.push({
      kind: "news",
      title: text2(row.title) || "뉴스",
      source: text2(row.source) || "뉴스 원문",
      url,
      publishedAt: label(row.datetime),
      isCorrection: null,
      isBackfill: null
    });
  }
  return { ...map, eventSources };
}
async function boundedJson(url, signal) {
  const controller = new AbortController();
  const abort = () => controller.abort(signal?.reason);
  if (signal?.aborted) throw signal.reason || new Error("요청이 취소되었습니다.");
  signal?.addEventListener("abort", abort, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, 12e3);
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (error) {
    if (signal?.aborted) throw signal.reason || error;
    if (timedOut) throw new Error("정보 요청 시간이 초과되었습니다.");
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
}
async function fetchPortfolioSources(ticker, apiBase, signal) {
  const code = text2(ticker).toUpperCase(), base = text2(apiBase).replace(/\/+$/, "");
  const overview = /^\d{6}$/.test(code) ? "&overview=1" : "";
  const results = await Promise.allSettled([
    boundedJson(`${base}/api/stock_slice?ticker=${encodeURIComponent(code)}${overview}`, signal),
    boundedJson(`${base}/api/stock_news?code=${encodeURIComponent(code)}`, signal)
  ]);
  if (signal?.aborted) throw signal.reason || new Error("요청이 취소되었습니다.");
  const input = (result) => result.status === "fulfilled" ? result.value : { __infoMapError: text2(result.reason?.message) || "요청 실패" };
  return normalizePortfolioSources(code, input(results[0]), input(results[1]));
}

// framer-components/public-probe/PortfolioCloseQuote.tsx
var record3 = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : null;
var finite = (value) => typeof value === "number" && Number.isFinite(value);
var positive = (value) => finite(value) && value > 0;
var text3 = (value) => typeof value === "string" ? value.trim() : "";
var missing = (reason) => ({ state: "unavailable", reason });
function dateOnly(value) {
  const raw = text3(value), parts = /^(\d{4})-?(\d{2})-?(\d{2})$/.exec(raw);
  if (!parts || !/^(\d{8}|\d{4}-\d{2}-\d{2})$/.test(raw) || Number(parts[1]) < 1900) return null;
  const normalized = `${parts[1]}-${parts[2]}-${parts[3]}`, ms = Date.parse(normalized + "T00:00:00Z");
  return Number.isFinite(ms) && new Date(ms).toISOString().slice(0, 10) === normalized ? normalized : null;
}
function normalizePortfolioCloseQuote(ticker, market, input) {
  if (!input) return missing("연결된 종가 자료가 없습니다.");
  if (!/^(KR|KOSPI|KOSDAQ)$/i.test(market.trim()) || !/^\d{6}$/.test(ticker))
    return missing("이 시장의 종가 자료는 아직 연결하지 않았습니다.");
  const payload = record3(input.payload);
  if (!payload) return missing("종가 자료 형식을 확인할 수 없습니다.");
  const meta = record3(Object.hasOwn(payload, "_meta") ? payload._meta : payload.meta);
  if (!meta) return missing("종가의 기준 정보를 확인할 수 없습니다.");
  if (Object.hasOwn(payload, "_meta") && Object.hasOwn(payload, "meta")) {
    const legacy = record3(payload.meta);
    if (!legacy || ["as_of", "prev_as_of", "source", "basis"].some((key) => legacy[key] !== meta[key]))
      return missing("종가 자료의 기준 정보가 서로 다릅니다.");
  }
  const priceDate = dateOnly(meta.as_of), source = text3(meta.source), basis = text3(meta.basis);
  if (!priceDate || !source || !basis.includes("종가")) return missing("종가·기준일·출처를 확인할 수 없습니다.");
  const price = record3(payload.prices)?.[ticker];
  if (!positive(price)) return missing("이 종목의 종가가 제공되지 않았습니다.");
  const expectedDate = dateOnly(input.latestCompletedTradingDate);
  if (expectedDate && priceDate > expectedDate) return missing("종가 기준일이 확인된 마지막 거래일보다 뒤에 있습니다.");
  const priorDate = dateOnly(meta.prev_as_of), prior = record3(payload.prev)?.[ticker];
  const previousDate = priorDate && priorDate < priceDate && positive(prior) ? priorDate : null;
  const previousPrice = previousDate ? prior : null;
  const reported = record3(payload.chg)?.[ticker];
  const calculated = previousPrice === null ? null : Math.round((price - previousPrice) / previousPrice * 1e4) / 100;
  const changePct = finite(reported) ? reported : finite(calculated) ? calculated : null;
  return {
    state: "available",
    price,
    priceDate,
    source,
    basis,
    currency: /^[A-Z]{3}$/.test(input.currency || "") ? input.currency : null,
    previousPrice,
    previousDate,
    changePct,
    changeBasis: finite(reported) ? "reported" : changePct !== null ? "calculated" : null,
    freshness: expectedDate ? priceDate === expectedDate ? "current" : "older" : "unknown",
    expectedDate
  };
}

// framer-components/public-probe/PortfolioMapData.tsx
var SECTIONS = ["business", "events"];
var DETAIL_SECTIONS = ["finance", "valuation", "holders", "risks"];
var order = (a, b) => a < b ? -1 : a > b ? 1 : 0;
var normalizedTicker = (ticker) => ticker.trim().toUpperCase();
var unique = (values) => [...new Map(values.map((value) => [JSON.stringify(value), value])).entries()].sort(([a], [b]) => order(a, b)).map(([, value]) => value);
async function sha256(value) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
async function portfolioDocumentIdentity(raw) {
  if (!raw || /[\r\n]/.test(raw)) return null;
  let url;
  try {
    url = new URL(raw);
  } catch {
    return null;
  }
  if (url.protocol !== "https:" || url.username || url.password) return null;
  const receipts = url.searchParams.getAll("rcpNo");
  if (url.hostname === "dart.fss.or.kr" && !url.port && url.pathname === "/dsaf001/main.do" && receipts.length === 1 && /^[0-9]{14}$/.test(receipts[0])) {
    return { id: `dart:${receipts[0]}`, url: `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${receipts[0]}` };
  }
  return { id: `url:${await sha256(url.href)}`, url: url.href };
}
function evidenceFor(ticker, sectionId, item, records) {
  const kind = item.id.startsWith("news-") ? "news" : item.id.startsWith("disclosure-") ? "disclosure" : item.id.startsWith("schedule-") ? "schedule" : sectionId === "business" ? "business" : "other";
  const reason = kind === "news" ? "이 종목의 뉴스 조회에 포함" : kind === "disclosure" ? "이 종목의 공시 자료에 포함" : kind === "business" ? "이 종목의 사업 자료에 포함" : "이 종목의 조회 자료에 포함";
  const sourceRecords = sectionId === "events" ? unique(records.filter((row) => row.url === item.url)) : [];
  const conflict = sourceRecords.some((row) => row.receiptConflict);
  return {
    ticker,
    sectionId,
    kind,
    title: item.title,
    source: item.source,
    asOf: item.asOf,
    url: item.url,
    explanation: kind === "news" ? reason : item.explanation,
    originalExplanation: item.explanation,
    reason,
    originalReason: item.reason,
    originalRelationship: item.relationship,
    confirmation: !conflict && (kind === "disclosure" || kind === "business") && item.relationship === "direct" ? "confirmed" : "unknown",
    isCorrection: !conflict && (item.reason === "정정공시" || /\[(?:기재|첨부|기타)?정정\]/.test(item.title)) ? true : null,
    sources: unique((item.sources || []).map((source) => ({ title: source.title, source: source.source, asOf: source.asOf, url: source.url }))),
    ...sourceRecords.length ? { sourceRecords } : {}
  };
}
function summarize(evidence) {
  const dates = evidence.flatMap((row) => [
    row.asOf,
    ...row.sources.map((source) => source.asOf),
    ...(row.sourceRecords || []).map((source) => source.publishedAt)
  ]);
  return {
    source: unique(evidence.flatMap((row) => [row.source, ...row.sources.map((source) => source.source)])).join(" · "),
    // Conflicting or absent dates remain in evidence; do not invent a single representative date.
    asOf: dates.every((date) => date === dates[0]) ? dates[0] : void 0,
    reason: unique(evidence.map((row) => row.reason)).join(" · "),
    confirmation: evidence.every((row) => row.confirmation === "confirmed") ? "confirmed" : "unknown",
    isCorrection: evidence.some((row) => row.isCorrection) ? true : null
  };
}
function companySections(maps) {
  return DETAIL_SECTIONS.flatMap((id) => {
    const sections = unique(maps.flatMap((map) => map.sections.filter((section) => section.id === id)));
    if (!sections.length) return [];
    const state = sections.some((section) => section.state === "error") ? "error" : sections.some((section) => section.state === "unsupported") ? "unsupported" : sections.some((section) => section.state === "ready") ? "ready" : "empty";
    const messages = unique(sections.flatMap((section) => section.message ? [section.message] : []));
    return [{
      id,
      title: sections[0].title,
      state,
      items: unique(sections.flatMap((section) => section.items)),
      ...messages.length ? { message: messages.join("\n") } : {}
    }];
  });
}
async function buildPortfolioMapGraph(maps, closeInput) {
  const byTicker = /* @__PURE__ */ new Map();
  for (const map of maps) {
    const ticker = normalizedTicker(map.ticker);
    if (ticker) byTicker.set(ticker, [...byTicker.get(ticker) || [], map]);
  }
  const companies = [], sources = [];
  const documentsById = /* @__PURE__ */ new Map();
  const identities = /* @__PURE__ */ new Map();
  for (const ticker of [...byTicker.keys()].sort(order)) {
    const rows2 = byTicker.get(ticker);
    const labels = unique(rows2.map((row) => ({ name: row.name, market: row.market })));
    companies.push({
      id: `company:${ticker}`,
      ticker,
      ...labels[0],
      sections: companySections(rows2),
      ...closeInput ? { closeQuote: normalizePortfolioCloseQuote(
        ticker,
        labels.every((label2) => /^(KR|KOSPI|KOSDAQ)$/i.test(label2.market.trim())) ? labels[0].market : "",
        closeInput
      ) } : {}
    });
    for (const sectionId of SECTIONS) {
      const sections = rows2.flatMap((row) => row.sections.filter((section) => section.id === sectionId));
      const upstreamStates = unique(sections.map((section) => section.state));
      const messages = unique(sections.flatMap((section) => section.message ? [section.message] : []));
      const items = unique(rows2.flatMap((row) => row.sections.filter((section) => section.id === sectionId).flatMap((section) => section.items.filter((item) => item.kind !== "question").map((item) => evidenceFor(ticker, sectionId, item, row.eventSources || [])))));
      let linkedItems = 0;
      for (const evidence of items) {
        const raw = evidence.url || "";
        if (!identities.has(raw)) identities.set(raw, portfolioDocumentIdentity(raw));
        const identity = await identities.get(raw);
        if (!identity) continue;
        linkedItems++;
        const document2 = documentsById.get(identity.id) || { ...identity, evidence: [] };
        document2.evidence.push(evidence);
        documentsById.set(identity.id, document2);
      }
      const problem = upstreamStates.some((state2) => state2 === "error" || state2 === "unsupported") || messages.some((message) => /불러오지 못|실패|제공 범위.*확인/.test(message));
      const state = !sections.length ? "unknown" : problem ? items.length ? "partial" : "unavailable" : !items.length ? "empty" : !linkedItems ? "unknown" : linkedItems < items.length ? "partial" : "available";
      sources.push({
        ticker,
        sectionId,
        state,
        upstreamStates,
        messages,
        receivedItems: items.length,
        linkedItems,
        omittedItems: items.length - linkedItems,
        collectionCompleteness: "unknown"
      });
    }
  }
  const documents = [], links = [];
  for (const document2 of [...documentsById.values()].sort((a, b) => order(a.id, b.id))) {
    const evidence = unique(document2.evidence);
    const tickers = unique(evidence.map((row) => row.ticker));
    const content = unique(evidence.map(({ ticker: _ticker, sectionId: _section, reason: _reason, sourceRecords, ...row }) => ({
      ...row,
      // Collection/backfill bookkeeping alone is not a change to source content.
      ...sourceRecords?.length ? { sourceRecords: unique(sourceRecords.map(({ observedAt: _observed, isBackfill: _backfill, ...source }) => source)) } : {}
    })));
    const contentHash = await sha256(JSON.stringify(content));
    const read_revision = Number.parseInt(contentHash.slice(0, 13), 16) + 1;
    documents.push({
      id: document2.id,
      kind: "source-document",
      title: evidence[0].title,
      url: document2.url,
      ...summarize(evidence),
      evidence,
      tickers,
      contentHash,
      read_revision
    });
    for (const ticker of tickers) {
      const associated = evidence.filter((row) => row.ticker === ticker);
      links.push({
        id: `link:${ticker}:${document2.id}`,
        companyId: `company:${ticker}`,
        documentId: document2.id,
        ticker,
        ...summarize(associated),
        evidence: associated
      });
    }
  }
  return {
    companies,
    documents,
    links,
    commonItems: documents.filter((document2) => document2.tickers.length >= 2),
    coverage: {
      total: sources.length,
      available: sources.filter((row) => row.state === "available").length,
      empty: sources.filter((row) => row.state === "empty").length,
      partial: sources.filter((row) => row.state === "partial").length,
      unavailable: sources.filter((row) => row.state === "unavailable").length,
      unknown: sources.filter((row) => row.state === "unknown").length,
      sources
    }
  };
}
async function fetchPortfolioMapGraph(tickers, apiBase, signal) {
  const codes = unique(tickers.map(normalizedTicker).filter(Boolean)), maps = [];
  let next = 0;
  const checkAbort = () => {
    if (signal?.aborted) throw signal.reason || new Error("요청이 취소되었습니다.");
  };
  checkAbort();
  await Promise.all(Array.from({ length: Math.min(4, codes.length) }, async () => {
    while (next < codes.length) {
      checkAbort();
      const ticker = codes[next++];
      try {
        maps.push(await fetchPortfolioSources(ticker, apiBase, signal));
      } catch {
        checkAbort();
        maps.push({
          ticker,
          name: ticker,
          market: "",
          sections: SECTIONS.map((id) => ({
            id,
            title: id,
            state: "error",
            items: [],
            message: "종목 자료를 불러오지 못했습니다."
          })),
          coverage: { ok: 0, total: 2, missing: [...SECTIONS] }
        });
      }
    }
  }));
  checkAbort();
  const graph = await buildPortfolioMapGraph(maps);
  checkAbort();
  return graph;
}

// framer-components/public-probe/MemberMapState.tsx
var ENDPOINT = "https://project-yw131.vercel.app/api/member_map_state";
var ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;
var USER_ID = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i;
var MAP_KEY = /^[a-z0-9][a-z0-9_-]{0,31}$/;
var MAX_REVISION = Number.MAX_SAFE_INTEGER;
var copy = (value) => JSON.parse(JSON.stringify(value));
var record4 = (value) => !!value && typeof value === "object" && !Array.isArray(value);
var fields = (value, names) => record4(value) && Object.keys(value).length === names.length && names.every((key) => Object.hasOwn(value, key));
var coordinate = (value) => typeof value === "number" && Number.isFinite(value) && Math.abs(value) <= 1e6;
var identifier = (value) => typeof value === "string" && ID.test(value);
var unique2 = (values) => new Set(values).size === values.length;
function validMapDocument(value) {
  if (!fields(value, ["layouts"])) return false;
  const layouts = value.layouts;
  if (!Array.isArray(layouts) || layouts.length > 3 || !unique2(layouts.map((row) => row?.map_key))) return false;
  for (const layout of layouts) {
    if (!fields(layout, ["map_key", "positions", "notes", "marks"]) || typeof layout.map_key !== "string" || !MAP_KEY.test(layout.map_key)) return false;
    if (!Array.isArray(layout.positions) || layout.positions.length > 200 || !unique2(layout.positions.map((row) => row?.node_id))) return false;
    for (const row of layout.positions) {
      if (!fields(row, ["node_id", "x", "y"]) || !identifier(row.node_id) || !coordinate(row.x) || !coordinate(row.y)) return false;
    }
    if (!Array.isArray(layout.notes) || layout.notes.length > 100 || !unique2(layout.notes.map((row) => row?.note_id))) return false;
    for (const note of layout.notes) {
      if (!fields(note, ["note_id", "anchor", "x", "y", "text", "done"]) || !identifier(note.note_id) || !coordinate(note.x) || !coordinate(note.y)) return false;
      if (typeof note.text !== "string" || [...note.text].length > 2e3 || note.text.includes("\0") || typeof note.done !== "boolean") return false;
      if (note.anchor !== null && (!fields(note.anchor, ["kind", "id"]) || !["node", "edge"].includes(note.anchor.kind) || !identifier(note.anchor.id))) return false;
    }
    if (!record4(layout.marks) || Object.keys(layout.marks).length > 200) return false;
    for (const [key, mark] of Object.entries(layout.marks)) {
      if (!identifier(key) || !fields(mark, ["read_revision", "important", "disposition"])) return false;
      if (mark.read_revision !== null && (!Number.isSafeInteger(mark.read_revision) || mark.read_revision < 1 || mark.read_revision >= MAX_REVISION)) return false;
      if (typeof mark.important !== "boolean" || !["inbox", "later", "irrelevant"].includes(mark.disposition)) return false;
    }
  }
  return true;
}
function readMapSession(storage) {
  try {
    const source = storage || (typeof window !== "undefined" ? window.localStorage : null);
    const value = JSON.parse(source?.getItem("verity_supabase_session") || "null");
    return USER_ID.test(value?.user?.id || "") && typeof value?.access_token === "string" && value.access_token.trim() ? { userId: value.user.id, token: value.access_token } : null;
  } catch {
    return null;
  }
}
function stable(value) {
  if (Array.isArray(value)) return "[" + value.map(stable).join(",") + "]";
  if (record4(value)) return "{" + Object.keys(value).sort().map((key) => JSON.stringify(key) + ":" + stable(value[key])).join(",") + "}";
  return JSON.stringify(value);
}
function responseState(value) {
  return record4(value) && Number.isSafeInteger(value.revision) && value.revision >= 0 && value.revision <= MAX_REVISION && validMapDocument(value.document);
}
var emptyState = () => ({ phase: "signed-out", document: null, revision: null, dirty: false, error: null });
function createMemberMapStore(options) {
  const fetcher = options.fetcher || fetch;
  let state = emptyState(), owner = null, generation = 0, editVersion = 0, disposed = false;
  const pending = /* @__PURE__ */ new Set();
  const listeners = /* @__PURE__ */ new Set();
  const session = () => {
    try {
      const value = options.getSession();
      return value && USER_ID.test(value.userId) && value.token ? value : null;
    } catch {
      return null;
    }
  };
  const emit = () => listeners.forEach((listener) => listener(copy(state)));
  const clear = (nextOwner) => {
    generation += 1;
    pending.forEach((controller) => controller.abort());
    pending.clear();
    owner = nextOwner;
    editVersion = 0;
    state = { ...emptyState(), phase: nextOwner ? "loading" : "signed-out" };
    emit();
  };
  const current = (account, version) => {
    if (disposed) return false;
    const nextOwner = session()?.userId || null;
    if (nextOwner !== owner) {
      clear(nextOwner);
      return false;
    }
    return !!account && owner === account.userId && generation === version;
  };
  const request = async (account, body) => {
    const controller = new AbortController();
    pending.add(controller);
    const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? 15e3);
    try {
      const response = await fetcher(ENDPOINT, {
        method: body === void 0 ? "GET" : "POST",
        headers: { Authorization: "Bearer " + account.token, ...body === void 0 ? {} : { "Content-Type": "application/json" } },
        ...body === void 0 ? {} : { body: JSON.stringify(body) },
        signal: controller.signal,
        cache: "no-store",
        credentials: "omit",
        redirect: "error"
      });
      if (!response.ok) throw new Error(response.status === 409 ? "conflict" : response.status === 401 ? "authentication-required" : "storage-unavailable");
      const payload = await response.json();
      if (!responseState(payload)) throw new Error("invalid-response");
      return payload;
    } finally {
      clearTimeout(timer);
      pending.delete(controller);
    }
  };
  const load = async (discardDraft = false) => {
    if (disposed) return false;
    const account = session();
    if ((account?.userId || null) !== owner) clear(account?.userId || null);
    if (!account || state.phase === "saving" || state.dirty && !discardDraft) return false;
    generation += 1;
    pending.forEach((controller) => controller.abort());
    const version = generation;
    state = { ...state, phase: "loading", error: null };
    emit();
    try {
      const result = await request(account);
      if (!current(account, version)) return false;
      state = { phase: "ready", document: copy(result.document), revision: result.revision, dirty: false, error: null };
      editVersion += 1;
      emit();
      return true;
    } catch (error) {
      if (!current(account, version)) return false;
      state = { ...state, phase: "error", error: error instanceof Error ? error.message : "storage-unavailable" };
      emit();
      return false;
    }
  };
  return {
    getState() {
      current(session(), generation);
      return copy(state);
    },
    subscribe(listener) {
      current(session(), generation);
      listeners.add(listener);
      listener(copy(state));
      return () => {
        listeners.delete(listener);
      };
    },
    async syncSession() {
      const nextOwner = session()?.userId || null;
      if (disposed) return false;
      if (nextOwner !== owner) {
        clear(nextOwner);
        return nextOwner ? load() : false;
      }
      if (nextOwner && state.revision === null && state.phase !== "saving") return load();
      return !!nextOwner;
    },
    load,
    update(change) {
      const account = session();
      if (!current(account, generation) || !state.document || state.revision === null || state.phase === "loading") return false;
      const document2 = change(copy(state.document));
      if (!validMapDocument(document2)) throw new Error("invalid-document");
      if (stable(document2) === stable(state.document)) return true;
      state = { ...state, document: copy(document2), dirty: true };
      editVersion += 1;
      emit();
      return true;
    },
    async save() {
      const account = session();
      if (!current(account, generation) || !account || !state.document || state.revision === null || !state.dirty || ["saving", "loading", "conflict"].includes(state.phase)) return false;
      const version = generation, edits = editVersion, expected = state.revision, document2 = copy(state.document);
      state = { ...state, phase: "saving", error: null };
      emit();
      try {
        const result = await request(account, { expected_revision: expected, document: document2 });
        if (!current(account, version)) return false;
        if (result.revision !== expected + 1 || stable(result.document) !== stable(document2)) throw new Error("invalid-save-response");
        state = { ...state, phase: "ready", revision: result.revision, dirty: edits !== editVersion, error: null };
        emit();
        return true;
      } catch (error) {
        if (!current(account, version)) return false;
        const reason = error instanceof Error ? error.message : "storage-unavailable";
        state = { ...state, phase: reason === "conflict" ? "conflict" : "error", dirty: true, error: reason };
        emit();
        return false;
      }
    },
    dispose() {
      disposed = true;
      clear(null);
      listeners.clear();
    }
  };
}
function mapReadState(mark, contentRevision) {
  if (!mark?.read_revision) return "unread";
  return mark.read_revision === contentRevision ? "read" : "changed";
}
function editMapLayout(document2, mapKey, change) {
  const layouts = copy(document2.layouts), index = layouts.findIndex((row) => row.map_key === mapKey);
  const initial = index < 0 ? { map_key: mapKey, positions: [], notes: [], marks: {} } : layouts[index];
  const next = change(initial);
  if (next.map_key !== mapKey) throw new Error("map-key-mismatch");
  if (index < 0) layouts.push(next);
  else layouts[index] = next;
  const result = { layouts };
  if (!validMapDocument(result)) throw new Error("invalid-document");
  return result;
}

// framer-components/public-probe/PortfolioMapWorkspace.tsx
var API = "https://project-yw131.vercel.app";
var clone = (value) => JSON.parse(JSON.stringify(value));
var sameAccount = (a, b) => a?.userId === b?.userId;
var empty = (privateState) => ({ phase: "signed-out", holdings: [], unsupportedCount: 0, selectedTickers: [], graph: null, privateState, error: null });
var finitePositive = (value) => {
  if (typeof value !== "number" && typeof value !== "string") return null;
  if (typeof value === "string" && !value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
};
function normalizeMapHoldings(payload) {
  const rows2 = Array.isArray(payload) ? payload : payload?.holdings;
  if (!Array.isArray(rows2)) throw new Error("invalid-holdings-response");
  const holdings = /* @__PURE__ */ new Map();
  let unsupportedCount = 0;
  for (const row of rows2) {
    if (!row || typeof row !== "object" || typeof row.ticker !== "string") throw new Error("invalid-holdings-response");
    const ticker = row.ticker.trim().toUpperCase(), market = String(row.market || "").toUpperCase();
    const supported = market === "KR" ? /^\d{6}$/.test(ticker) : market === "US" && /^[A-Z][A-Z0-9.-]{0,15}$/.test(ticker);
    if (!supported || row.type === "commodity") {
      unsupportedCount += 1;
      continue;
    }
    const prior = holdings.get(ticker);
    if (prior && prior.market !== market) throw new Error("ambiguous-holding-market");
    if (prior) {
      holdings.set(ticker, { ...prior, shares: null, avg_cost: null, duplicate: true });
      continue;
    }
    holdings.set(ticker, {
      ticker,
      name: typeof row.name === "string" && row.name.trim() ? row.name.trim() : ticker,
      market,
      shares: finitePositive(row.shares),
      avg_cost: finitePositive(row.avg_cost),
      duplicate: false
    });
  }
  return { holdings: [...holdings.values()], unsupportedCount };
}
function createPortfolioMapWorkspace(options = {}) {
  const getSession = options.getSession || readMapSession, fetcher = options.fetcher || fetch;
  const graphLoader = options.graphLoader || fetchPortfolioMapGraph;
  let disposed = false;
  const store = createMemberMapStore({ getSession, fetcher: (input, init) => disposed ? Promise.reject(new Error("workspace-disposed")) : fetcher(input, init) });
  let state = empty(store.getState()), account = null, generation = 0;
  let pending = null;
  const listeners = /* @__PURE__ */ new Set();
  const authCleanups = /* @__PURE__ */ new Set();
  const timers = /* @__PURE__ */ new Set();
  const emit = () => {
    if (disposed) return;
    currentAccount();
    for (const listener of listeners) {
      if (disposed) break;
      currentAccount();
      listener(clone(state));
    }
  };
  const reset = (notify = true) => {
    generation += 1;
    pending?.abort();
    pending = null;
    state = empty({ phase: "signed-out", document: null, revision: null, dirty: false, error: null });
    if (notify) emit();
  };
  const currentAccount = () => {
    if (disposed) return false;
    if (!sameAccount(account, getSession())) {
      account = null;
      reset(false);
      return false;
    }
    return true;
  };
  const valid = (version) => {
    if (!currentAccount()) {
      emit();
      return false;
    }
    return generation === version;
  };
  const unsubscribe = store.subscribe((privateState) => {
    if (!currentAccount()) {
      emit();
      return;
    }
    state = { ...state, privateState };
    emit();
  });
  const showTickers = async (tickers) => {
    if (!account || !valid(generation)) return false;
    const codes = [...new Set(tickers.map((ticker) => ticker.trim().toUpperCase()))];
    if (codes.length > 30 || codes.some((code) => !state.holdings.some((row) => row.ticker === code))) throw new Error("choose-up-to-30-holdings");
    pending?.abort();
    pending = new AbortController();
    const signal = pending.signal, version = ++generation;
    state = { ...state, phase: "loading", selectedTickers: codes, graph: null, error: null };
    emit();
    try {
      if (!valid(version) || signal.aborted) return false;
      const graph = await graphLoader(codes, API, signal);
      if (!valid(version) || signal.aborted) return false;
      if (graph.companies.length !== codes.length || new Set(graph.companies.map((row) => row.ticker)).size !== codes.length || graph.companies.some((row) => !codes.includes(row.ticker))) throw new Error("graph-holdings-mismatch");
      state = { ...state, phase: "ready", graph };
      emit();
      return valid(version);
    } catch (error) {
      if (!valid(version) || signal.aborted) return false;
      state = { ...state, phase: "error", graph: null, error: error instanceof Error ? error.message : "data-unavailable" };
      emit();
      return false;
    }
  };
  const open = async () => {
    if (disposed) return false;
    const next = getSession(), changed = !sameAccount(account, next);
    if (changed) {
      account = next;
      reset();
    } else {
      account = next;
      pending?.abort();
    }
    if (!valid(generation) || !sameAccount(account, next)) return false;
    const restore = store.syncSession();
    if (!next) {
      await restore;
      return false;
    }
    if (!valid(generation) || !sameAccount(account, next)) return false;
    const version = ++generation, controller = new AbortController();
    pending = controller;
    const timer = setTimeout(() => controller.abort(), 15e3);
    timers.add(timer);
    state = { ...state, phase: "loading", error: null };
    emit();
    try {
      if (!valid(version) || controller.signal.aborted) return false;
      const requestSession = getSession();
      if (!requestSession || !sameAccount(next, requestSession) || !valid(version) || controller.signal.aborted) return false;
      const requestHoldings = (token) => fetcher(API + "/api/holdings", {
        headers: { Authorization: "Bearer " + token },
        signal: controller.signal,
        cache: "no-store",
        credentials: "omit",
        redirect: "error"
      });
      let response = await requestHoldings(requestSession.token);
      if (!valid(version) || controller.signal.aborted) return false;
      if (response.status === 401) {
        const refreshed = getSession();
        if (refreshed?.token && sameAccount(next, refreshed) && refreshed.token !== requestSession.token && valid(version) && !controller.signal.aborted) response = await requestHoldings(refreshed.token);
      }
      if (!valid(version) || controller.signal.aborted) return false;
      if (!response.ok) throw new Error(response.status === 401 ? "authentication-required" : "holdings-unavailable");
      const result = normalizeMapHoldings(await response.json());
      if (!valid(version) || controller.signal.aborted) return false;
      const previous = state.selectedTickers.filter((code) => result.holdings.some((row) => row.ticker === code));
      state = { ...state, ...result };
      if (result.holdings.length > 30 && !previous.length) {
        state = { ...state, phase: "choose-stocks", graph: null, selectedTickers: [] };
        emit();
        await restore;
        return valid(version);
      }
      const success = await showTickers(previous.length ? previous : result.holdings.map((row) => row.ticker));
      const graphVersion = generation;
      await restore;
      return success && valid(graphVersion) && sameAccount(next, getSession());
    } catch (error) {
      if (!valid(version)) return false;
      state = { ...state, phase: "error", holdings: [], graph: null, error: error instanceof Error ? error.message : "holdings-unavailable" };
      emit();
      await restore;
      return false;
    } finally {
      clearTimeout(timer);
      timers.delete(timer);
    }
  };
  return {
    getState() {
      currentAccount();
      return clone(state);
    },
    subscribe(listener) {
      if (disposed) return () => {
      };
      currentAccount();
      listeners.add(listener);
      listener(clone(state));
      return () => {
        listeners.delete(listener);
      };
    },
    open,
    showTickers,
    editLayout(mapKey, change) {
      if (!valid(generation)) return false;
      return store.update((document2) => editMapLayout(document2, mapKey, change));
    },
    markDocument(mapKey, id, change) {
      if (!valid(generation)) return false;
      const document2 = state.graph?.documents.find((row) => row.id === id);
      if (!document2) return false;
      return store.update((value) => editMapLayout(value, mapKey, (layout) => {
        const prior = layout.marks[id] || { read_revision: null, important: false, disposition: "inbox" };
        const mark = {
          read_revision: change.read === void 0 ? prior.read_revision : change.read ? document2.read_revision : null,
          important: change.important ?? prior.important,
          disposition: change.disposition ?? prior.disposition
        };
        return { ...layout, marks: { ...layout.marks, [id]: mark } };
      }));
    },
    /** read_revision fingerprints the available evidence/excerpt set. Membership changes
     * may change that set without any source-document edit. UI label: "확인할 자료 변경",
     * never "원문 새 버전"; compare equality only, not an increasing version number.
     */
    documentsToReview(mapKey) {
      if (!valid(generation)) return [];
      const marks = state.privateState.document?.layouts.find((row) => row.map_key === mapKey)?.marks || {};
      return (state.graph?.documents || []).filter((row) => marks[row.id]?.disposition !== "irrelevant" && mapReadState(marks[row.id], row.read_revision) !== "read");
    },
    save: () => valid(generation) ? store.save() : Promise.resolve(false),
    reloadSaved: (discardDraft = false) => valid(generation) ? store.load(discardDraft) : Promise.resolve(false),
    /** Subscribe once from the mounted AlphaNest view. No token is sent to an iframe. */
    bindAuth(target) {
      if (disposed) return () => {
      };
      const onAuth = (event) => {
        if (event.type === "storage" && event.key && event.key !== "verity_supabase_session") return;
        const next = getSession();
        if (next && account && sameAccount(account, next) && (state.phase === "ready" || state.phase === "choose-stocks")) {
          account = next;
          void store.syncSession();
          return;
        }
        void open();
      };
      const beforeUnload = (event) => {
        if (!valid(generation)) return;
        if (store.getState().dirty) {
          event.preventDefault();
          event.returnValue = "";
        }
      };
      target.addEventListener("verity_auth_change", onAuth);
      target.addEventListener("storage", onAuth);
      target.addEventListener("beforeunload", beforeUnload);
      const cleanup = () => {
        target.removeEventListener("verity_auth_change", onAuth);
        target.removeEventListener("storage", onAuth);
        target.removeEventListener("beforeunload", beforeUnload);
        authCleanups.delete(cleanup);
      };
      authCleanups.add(cleanup);
      return cleanup;
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      listeners.clear();
      authCleanups.forEach((cleanup) => cleanup());
      timers.forEach((timer) => clearTimeout(timer));
      timers.clear();
      pending?.abort();
      unsubscribe();
      store.dispose();
      account = null;
      reset(false);
    }
  };
}

// framer-components/public-probe/PortfolioMapCanvas.tsx
import * as React from "react";
import { createPortal } from "react-dom";
var FALLBACK_NODE_WIDTH = 148;
var FALLBACK_NODE_HEIGHT = 42;
var GRID = 24;
var LIMIT = 1e6;
var AUTO_MIN_ZOOM = 1e-6;
var MIN_ZOOM = 0.25;
var MAX_ZOOM = 4;
var EMPTY_CAMERA = { x: 24, y: 24, zoom: 1 };
var FONT = "Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif";
var clampCoordinate = (value) => Math.max(-LIMIT, Math.min(LIMIT, value));
var finiteCoordinate = (value, fallback) => Number.isFinite(value) ? clampCoordinate(value) : clampCoordinate(fallback);
var samePositions = (a, b) => a.length === b.length && a.every((row, index) => row.node_id === b[index]?.node_id && row.x === b[index]?.x && row.y === b[index]?.y);
function positionSignature(positions) {
  return JSON.stringify(positions.map((row) => [row.node_id, row.x, row.y]).sort((a, b) => a[0].localeCompare(b[0])));
}
function changedPositionRows(before, after) {
  const prior = new Map(before.map((row) => [row.node_id, row]));
  return after.filter((row) => {
    const value = prior.get(row.node_id);
    return !value || value.x !== row.x || value.y !== row.y;
  }).map((row) => ({ ...row }));
}
function mergePositionPatch(base, patch) {
  const result = base.map((row) => ({ ...row }));
  const indexes = new Map(result.map((row, index) => [row.node_id, index]));
  for (const row of patch) {
    const next = { node_id: row.node_id, x: clampCoordinate(row.x), y: clampCoordinate(row.y) };
    const index = indexes.get(row.node_id);
    if (index === void 0) {
      indexes.set(row.node_id, result.length);
      result.push(next);
    } else result[index] = next;
  }
  return result;
}
function consumePositionEcho(pending, incoming) {
  const index = pending.indexOf(incoming);
  return index < 0 ? { own: false, latest: false, remaining: [] } : { own: true, latest: index === pending.length - 1, remaining: pending.slice(index + 1) };
}
function canvasNodeSchemaKey(nodes) {
  return JSON.stringify(nodes.map((node) => [node.id, node.kind]).sort(([a], [b]) => String(a).localeCompare(String(b))));
}
function normalizeCanvasPositions(nodes, positions) {
  const result = [];
  const seen = /* @__PURE__ */ new Set();
  for (const row of positions) {
    if (!row || typeof row.node_id !== "string" || seen.has(row.node_id) || !Number.isFinite(row.x) || !Number.isFinite(row.y)) continue;
    seen.add(row.node_id);
    result.push({ node_id: row.node_id, x: clampCoordinate(row.x), y: clampCoordinate(row.y) });
  }
  for (const node of nodes) {
    if (seen.has(node.id)) continue;
    seen.add(node.id);
    result.push({ node_id: node.id, x: finiteCoordinate(node.x, 0), y: finiteCoordinate(node.y, 0) });
  }
  return result;
}
function reconcileCanvasPositions(nodes, incoming, current) {
  const currentById = new Map(current.map((row) => [row.node_id, row]));
  const incomingById = new Map(incoming.map((row) => [row.node_id, row]));
  const merged = current.map((row) => ({ ...row }));
  const known = new Set(merged.map((row) => row.node_id));
  for (const node of nodes) {
    if (known.has(node.id)) continue;
    const row = incomingById.get(node.id);
    merged.push(row ? { ...row } : { node_id: node.id, x: node.x, y: node.y });
    known.add(node.id);
  }
  return normalizeCanvasPositions(nodes, merged.map((row) => currentById.get(row.node_id) || row));
}
function applyNodeMovement(positions, ids, dx, dy) {
  const selected = new Set(ids);
  return positions.map((row) => selected.has(row.node_id) ? { ...row, x: clampCoordinate(row.x + dx), y: clampCoordinate(row.y + dy) } : { ...row });
}
function zoomMapCamera(camera, factor, anchor) {
  const startZoom = Math.max(AUTO_MIN_ZOOM, Math.min(MAX_ZOOM, camera.zoom || 1));
  const zoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, startZoom * factor));
  return {
    zoom,
    x: anchor.x - (anchor.x - camera.x) * zoom / startZoom,
    y: anchor.y - (anchor.y - camera.y) * zoom / startZoom
  };
}
var nodeWidth = (node) => node.width || FALLBACK_NODE_WIDTH;
var nodeHeight = (node) => node.height || FALLBACK_NODE_HEIGHT;
function fitMapCamera(nodes, size) {
  if (!nodes.length || size.width <= 0 || size.height <= 0) return EMPTY_CAMERA;
  const leftInset = 32, rightInset = 32, topInset = 112, bottomInset = 92;
  let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
  for (const node of nodes) {
    left = Math.min(left, node.x);
    top = Math.min(top, node.y);
    right = Math.max(right, node.x + nodeWidth(node));
    bottom = Math.max(bottom, node.y + nodeHeight(node));
  }
  const width = Math.max(1, right - left), height = Math.max(1, bottom - top);
  const availableWidth = Math.max(1, size.width - leftInset - rightInset);
  const availableHeight = Math.max(1, size.height - topInset - bottomInset);
  const zoom = Math.max(AUTO_MIN_ZOOM, Math.min(1.2, availableWidth / width, availableHeight / height));
  return {
    zoom,
    x: leftInset + (availableWidth - width * zoom) / 2 - left * zoom,
    y: topInset + (availableHeight - height * zoom) / 2 - top * zoom
  };
}
function companyNeighborhood(companyId, links) {
  const result = /* @__PURE__ */ new Set([companyId]);
  const documents = /* @__PURE__ */ new Set();
  for (const link of links) if (link.companyId === companyId) {
    documents.add(link.documentId);
    result.add(link.documentId);
  }
  for (const link of links) if (documents.has(link.documentId)) result.add(link.companyId);
  return result;
}
function positionChangeAccepted(result) {
  return result !== false;
}
function nodesInMarquee(nodes, camera, box) {
  const right = box.left + box.width, bottom = box.top + box.height;
  return nodes.filter((node) => {
    const left = camera.x + node.x * camera.zoom, top = camera.y + node.y * camera.zoom;
    return left < right && left + nodeWidth(node) * camera.zoom > box.left && top < bottom && top + nodeHeight(node) * camera.zoom > box.top;
  }).map((node) => node.id);
}
function nodeHoverAbove(anchor, viewportWidth, hoverHeight) {
  const width = Math.min(270, viewportWidth - 16);
  if (width < 120) return null;
  const top = anchor.top - hoverHeight - 8;
  if (top < 8) return null;
  return {
    left: Math.max(8, Math.min(viewportWidth - width - 8, anchor.left + anchor.width / 2 - width / 2)),
    top,
    width
  };
}
function shouldAutoFitCanvas(schemaKey, fittedSchema, nodeIds, sizes) {
  return fittedSchema !== schemaKey && nodeIds.every((id) => sizes.has(id));
}
function resetVisiblePositions(nodes, current) {
  const visible = new Map(nodes.map((node) => [node.id, node]));
  const next = current.map((row) => {
    const node = visible.get(row.node_id);
    return node && node.kind !== "note" ? { node_id: row.node_id, x: finiteCoordinate(node.x, 0), y: finiteCoordinate(node.y, 0) } : { ...row };
  });
  return normalizeCanvasPositions(nodes, next);
}
function marqueeFrom(a, b) {
  return { left: Math.min(a.x, b.x), top: Math.min(a.y, b.y), width: Math.abs(a.x - b.x), height: Math.abs(a.y - b.y) };
}
function positionedNodes(nodes, positions) {
  const byId = new Map(positions.map((row) => [row.node_id, row]));
  return nodes.map((node) => {
    const row = byId.get(node.id);
    return row ? { ...node, x: row.x, y: row.y } : node;
  });
}
function edgeGeometry(from, to) {
  const forward = to.x >= from.x;
  const x1 = from.x + (forward ? from.width : 0), y1 = from.y + from.height / 2;
  const x2 = to.x + (forward ? 0 : to.width), y2 = to.y + to.height / 2;
  const bend = Math.max(34, Math.min(120, Math.abs(x2 - x1) * 0.42));
  const c1x = x1 + (forward ? bend : -bend), c2x = x2 - (forward ? bend : -bend);
  const mx = (x1 + 3 * c1x + 3 * c2x + x2) / 8;
  const my = (y1 + 3 * y1 + 3 * y2 + y2) / 8;
  const dx = 3 * 0.25 * (c1x - x1) + 6 * 0.5 * (c2x - c1x) + 3 * 0.25 * (x2 - c2x);
  const dy = 3 * 0.25 * 0 + 6 * 0.5 * (y2 - y1) + 3 * 0.25 * 0;
  return { d: `M ${x1} ${y1} C ${c1x} ${y1}, ${c2x} ${y2}, ${x2} ${y2}`, mx, my, angle: Math.atan2(dy, dx) * 180 / Math.PI };
}
var CSS = `
.pmc{--bg:#f2f4f6;--surface:#fff;--ink:#191f28;--muted:#4e5968;--grid:#dfe3e9;--line:#8994a5;--accent:#6c5ce7;--soft:#f0edff;--note:#fff3d7;--unknown:#7b8798;--source-disclosure:#edf4ff;--source-business:#eaf7f2;--source-news:#fff0f2;--source-schedule:#fff4df;--source-other:#f2effb;position:relative;width:100%;height:100%;min-height:420px;overflow:hidden;background:var(--bg);color:var(--ink);font:600 13px/1.45 ${FONT};isolation:isolate;touch-action:none;user-select:none}
.pmc[data-theme=dark]{--bg:#0f1318;--surface:#171c23;--ink:#e3e7ec;--muted:#9aa4b1;--grid:#1e2631;--line:#9aaac0;--accent:#a99bff;--soft:#241f3a;--note:#3c3020;--unknown:#7f8fa5;--source-disclosure:#172c44;--source-business:#12312b;--source-news:#35222b;--source-schedule:#322812;--source-other:#29243a}
.pmc *{box-sizing:border-box}.pmc button{font:700 12px/1 ${FONT};color:inherit}.pmc-grid{position:absolute;inset:0;background-image:linear-gradient(to right,var(--grid) 1px,transparent 1px),linear-gradient(to bottom,var(--grid) 1px,transparent 1px);pointer-events:none}
.pmc-world{position:absolute;inset:0;transform-origin:0 0;pointer-events:none}.pmc-lines{position:absolute;left:0;top:0;width:1px;height:1px;overflow:visible;pointer-events:none}.pmc-edge{fill:none;stroke:var(--line);stroke-width:1.8;vector-effect:non-scaling-stroke}.pmc-edge[data-confirmation=unknown]{stroke:var(--unknown);stroke-dasharray:6 6}.pmc-edge[data-active=true]{stroke:var(--accent);stroke-width:2.8}.pmc-edge-hit{fill:none;stroke:transparent;stroke-width:16;pointer-events:stroke;cursor:pointer}.pmc-edge-hit:focus{stroke:color-mix(in srgb,var(--accent) 25%,transparent);outline:none}.pmc-chevron{fill:none;stroke:var(--line);stroke-width:2.4;stroke-linecap:round;stroke-linejoin:round;vector-effect:non-scaling-stroke}.pmc-edge[data-active=true]~.pmc-chevron{stroke:var(--accent)}
.pmc-moving-chevron{offset-distance:50%;offset-rotate:auto;animation:pmc-chevron-move 3.2s linear infinite}.pmc-moving-chevron path{fill:var(--surface);stroke:var(--accent);stroke-width:4.8;stroke-linecap:round;stroke-linejoin:round;vector-effect:non-scaling-stroke}.pmc-dim{opacity:.18}
.pmc[data-active=false]{pointer-events:none}.pmc[data-active=false] .pmc-moving-chevron{animation:none}
.pmc-node{position:absolute;width:max-content;min-width:108px;max-width:min(168px,calc(100vw - 40px));min-height:42px;border:0;border-radius:12px;padding:7px 9px;background:var(--surface);box-shadow:0 4px 12px color-mix(in srgb,var(--ink) 10%,transparent);display:flex;flex-direction:column;align-items:flex-start;justify-content:center;gap:1px;overflow:visible;text-align:left;pointer-events:auto;cursor:grab;transition:opacity .18s ease,box-shadow .18s ease,transform .18s ease}.pmc-node[data-kind=document]{min-height:34px;padding:5px 7px;border-radius:10px;background:var(--source-other)}.pmc-node[data-source=disclosure]{background:var(--source-disclosure)}.pmc-node[data-source=business]{background:var(--source-business)}.pmc-node[data-source=news]{background:var(--source-news)}.pmc-node[data-source=schedule]{background:var(--source-schedule)}.pmc-node[data-kind=note]{background:var(--note)}.pmc-node[data-kind=note][data-done=true]{padding-right:50px}.pmc-node[data-selected=true]{background:var(--soft);box-shadow:0 0 0 2px var(--accent),0 8px 20px color-mix(in srgb,var(--accent) 18%,transparent)}.pmc-node:active{cursor:grabbing}.pmc-node strong,.pmc-node span{max-width:100%;overflow-wrap:anywhere;white-space:normal}.pmc-node strong{font-size:13px;font-weight:700;line-height:1.4}.pmc-node span{color:var(--muted);font-size:11px;font-weight:600;line-height:1.4}.pmc-note-done{position:absolute;top:5px;right:7px;border-radius:7px;padding:2px 4px;background:color-mix(in srgb,var(--ink) 10%,transparent);font-size:9px;font-weight:700;color:var(--ink)}
.pmc-node:focus-visible,.pmc-control:focus-visible{outline:none;background:color-mix(in srgb,var(--accent) 18%,var(--surface));color:var(--ink)}.pmc-toolbar{position:absolute;z-index:5;top:12px;left:50%;transform:translateX(-50%);display:flex;align-items:center;gap:3px;padding:5px;border:1px solid color-mix(in srgb,var(--ink) 10%,transparent);border-radius:13px;background:color-mix(in srgb,var(--surface) 92%,transparent);box-shadow:0 6px 20px color-mix(in srgb,var(--ink) 10%,transparent);backdrop-filter:blur(8px)}
.pmc-toolbar{width:max-content;max-width:calc(100% - 24px);justify-content:center;flex-wrap:wrap}.pmc-control{border:0;border-radius:8px;min-width:30px;height:30px;padding:0 7px;background:transparent;cursor:pointer;white-space:nowrap;flex-shrink:0}.pmc-control:hover:not(:disabled),.pmc-control[aria-pressed=true]{background:var(--soft);color:var(--accent)}.pmc-control:disabled{opacity:.35;cursor:not-allowed}.pmc-zoom{min-width:42px;color:var(--muted);text-align:center;font-size:11px;font-weight:700;flex-shrink:0}.pmc-divider{width:1px;height:18px;background:color-mix(in srgb,var(--ink) 12%,transparent)}
.pmc-summary,.pmc-legend,.pmc-help{position:absolute;z-index:4;border-radius:10px;background:color-mix(in srgb,var(--surface) 91%,transparent);color:var(--muted);font-weight:600;backdrop-filter:blur(7px)}.pmc-summary{top:62px;left:13px;padding:7px 9px}.pmc-legend{right:13px;bottom:13px;padding:8px 10px;display:grid;gap:4px;max-width:min(350px,calc(100% - 26px));font-size:11px}.pmc-legend-row{display:flex;align-items:center;gap:7px}.pmc-legend-line{width:24px;border-top:2px solid var(--line)}.pmc-legend-line[data-kind=unknown]{border-top-style:dashed}.pmc-help{left:13px;bottom:13px;padding:7px 9px;font-size:11px}.pmc-hover{--hover-surface:#fff;--hover-ink:#191f28;--hover-muted:#4e5968;box-sizing:border-box;position:fixed;z-index:2147483000;max-height:calc(100vh - 16px);overflow:auto;border-radius:12px;padding:10px 12px;background:var(--hover-surface);color:var(--hover-ink);box-shadow:0 8px 28px color-mix(in srgb,var(--hover-ink) 16%,transparent);pointer-events:none;display:flex;flex-direction:column;gap:4px;font:600 12px/1.5 ${FONT}}.pmc-hover[data-theme=dark]{--hover-surface:#171c23;--hover-ink:#e3e7ec;--hover-muted:#9aa4b1}.pmc-hover strong{font-size:13px;font-weight:700}.pmc-hover span,.pmc-hover small{overflow-wrap:anywhere;white-space:normal;color:var(--hover-muted);font-weight:600}.pmc-marquee{position:absolute;z-index:3;border:1px solid var(--accent);background:color-mix(in srgb,var(--accent) 13%,transparent);pointer-events:none}.pmc-empty{position:absolute;inset:0;display:grid;place-items:center;padding:24px;color:var(--muted);font-weight:600;text-align:center}.pmc-status{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.pmc-node strong,.pmc-node span{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden}
@keyframes pmc-chevron-move{from{offset-distance:8%}to{offset-distance:92%}}
@media(prefers-reduced-motion:reduce){.pmc *{animation:none!important;transition:none!important}.pmc-moving-chevron{offset-distance:50%}}
@media(max-width:720px){.pmc{min-height:460px}.pmc-toolbar{top:10px;max-width:calc(100% - 20px)}.pmc-control{padding:0 6px}.pmc-help{display:none}.pmc-legend{left:10px;right:10px;bottom:10px}}
`;
var controlTitle = (label2) => label2;
var selectionSignature = (value) => value ? `${value.kind}:${value.id}` : "none";
function canvasModeText(mode) {
  if (mode === "relationships") return {
    region: "보유종목의 수동 검토 관계 지도",
    item: "확인 관계",
    line: "종목과 확인된 관계의 연결선",
    legend: "실선 · 원문 대조로 확인한 당시 관계",
    disclaimer: "현재 관계의 지속·강도·수익 영향을 뜻하지 않습니다."
  };
  if (mode === "events") return {
    region: "보유종목의 수동 검토 공통 사건 지도",
    item: "공통 사건",
    line: "종목과 공통 사건의 참여 연결선",
    legend: "실선 · 원문 대조로 묶은 당시 공통 사건",
    disclaimer: "같은 사건 참여를 나타내며 현재 영향·인과·수익을 뜻하지 않습니다."
  };
  return {
    region: "포트폴리오 자료 지도",
    item: "자료",
    line: "종목과 자료의 직접 연결선",
    legend: "실선 · 직접적인 문서 연결 확인",
    disclaimer: "움직이는 갈매기는 선택 위치 안내이며, 선은 기업 간 인과·수익 영향을 뜻하지 않습니다."
  };
}
function PortfolioMapCanvas({
  nodes,
  links,
  selection,
  onSelect,
  positions,
  onPositionsChange,
  editable,
  motion,
  onMotionChange,
  theme,
  mode = "documents",
  active = true
}) {
  const rootRef = React.useRef(null);
  const onSelectRef = React.useRef(onSelect);
  const onPositionsChangeRef = React.useRef(onPositionsChange);
  const onMotionChangeRef = React.useRef(onMotionChange);
  const [size, setSize] = React.useState({ width: 0, height: 0 });
  const [nodeSizes, setNodeSizes] = React.useState(() => /* @__PURE__ */ new Map());
  const nodeSizesRef = React.useRef(nodeSizes);
  const [camera, setCameraState] = React.useState(EMPTY_CAMERA);
  const cameraRef = React.useRef(camera);
  const [localPositions, setLocalPositionsState] = React.useState(() => normalizeCanvasPositions(nodes, positions));
  const positionsRef = React.useRef(localPositions);
  const [selectedIds, setSelectedIds] = React.useState(() => new Set(selection && selection.kind !== "link" ? [selection.id] : []));
  const [focusCompanyId, setFocusCompanyId] = React.useState(null);
  const [marquee, setMarquee] = React.useState(null);
  const [hover, setHover] = React.useState(null);
  const hoverRef = React.useRef(null);
  const [hoverGuide, setHoverGuide] = React.useState("");
  const [status, setStatus] = React.useState("");
  const activeRef = React.useRef(null);
  const historyRef = React.useRef([]);
  const futureRef = React.useRef([]);
  const previousCameraRef = React.useRef(null);
  const spaceRef = React.useRef(false);
  const fittedNodesRef = React.useRef("");
  const pendingPositionEchoesRef = React.useRef([]);
  const expectedSparsePositionsRef = React.useRef(positions.map((row) => ({ ...row })));
  const pendingSelectionEchoRef = React.useRef(null);
  const selectionRef = React.useRef(selection);
  const selectionReturnRef = React.useRef(null);
  const priorEditableRef = React.useRef(editable);
  const [, historyVersion] = React.useState(0);
  const nodesKey = JSON.stringify(nodes.map((node) => [node.id, node.kind, node.title, node.subtitle, node.x, node.y, node.done]));
  const schemaKey = canvasNodeSchemaKey(nodes);
  const positionsKey = positionSignature(positions);
  const priorSchemaKey = React.useRef(schemaKey);
  const priorPositionsKey = React.useRef(positionsKey);
  const modeText = canvasModeText(mode);
  const overviewLabel = mode === "documents" ? "전체 자료 묶음 한눈에 보기" : `전체 ${modeText.item} 묶음 한눈에 보기`;
  React.useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);
  React.useEffect(() => {
    onPositionsChangeRef.current = onPositionsChange;
  }, [onPositionsChange]);
  React.useEffect(() => {
    onMotionChangeRef.current = onMotionChange;
  }, [onMotionChange]);
  const setCamera = React.useCallback((next) => {
    const safe = {
      x: Number.isFinite(next.x) ? next.x : 0,
      y: Number.isFinite(next.y) ? next.y : 0,
      zoom: Math.max(AUTO_MIN_ZOOM, Math.min(MAX_ZOOM, Number.isFinite(next.zoom) ? next.zoom : 1))
    };
    setHover(null);
    setHoverGuide("");
    cameraRef.current = safe;
    setCameraState((current) => current.x === safe.x && current.y === safe.y && current.zoom === safe.zoom ? current : safe);
  }, []);
  const setLocalPositions = React.useCallback((next) => {
    positionsRef.current = next;
    setLocalPositionsState(next);
  }, []);
  const cancelActive = React.useCallback(() => {
    const active2 = activeRef.current;
    if (active2?.kind === "nodes") setLocalPositions(active2.before);
    else if (active2?.kind === "pan") setCamera(active2.camera);
    activeRef.current = null;
    spaceRef.current = false;
    setMarquee(null);
    setHover(null);
    setHoverGuide("");
  }, [setCamera, setLocalPositions]);
  const currentNodes = React.useMemo(() => positionedNodes(nodes, localPositions).map((node) => {
    const measured = nodeSizes.get(node.id);
    return { ...node, width: measured?.width || FALLBACK_NODE_WIDTH, height: measured?.height || FALLBACK_NODE_HEIGHT };
  }), [nodesKey, localPositions, nodeSizes]);
  const nodeById = React.useMemo(() => new Map(currentNodes.map((node) => [node.id, node])), [currentNodes]);
  const focusIds = React.useMemo(() => focusCompanyId ? companyNeighborhood(focusCompanyId, links) : null, [focusCompanyId, links]);
  React.useEffect(() => {
    const element = rootRef.current;
    if (!element || !active) {
      cancelActive();
      return;
    }
    const resize = () => {
      setHover(null);
      setHoverGuide("");
      setSize({ width: element.clientWidth, height: element.clientHeight });
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    const wheel = (event) => {
      event.preventDefault();
      const rect = element.getBoundingClientRect(), current = cameraRef.current;
      const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? Math.max(1, element.clientHeight) : 1;
      if (event.ctrlKey || event.metaKey) setCamera(zoomMapCamera(current, Math.exp(-event.deltaY * unit * 2e-3), { x: event.clientX - rect.left, y: event.clientY - rect.top }));
      else setCamera({ ...current, x: current.x - event.deltaX * unit, y: current.y - event.deltaY * unit });
    };
    const blur = () => cancelActive();
    element.addEventListener("wheel", wheel, { passive: false });
    window.addEventListener("blur", blur);
    return () => {
      observer.disconnect();
      element.removeEventListener("wheel", wheel);
      window.removeEventListener("blur", blur);
    };
  }, [active, cancelActive, setCamera]);
  React.useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root || !active) return;
    const measure = () => {
      const next = /* @__PURE__ */ new Map();
      root.querySelectorAll(".pmc-node[data-node]").forEach((element) => {
        const id = element.dataset.node;
        if (id) next.set(id, { width: element.offsetWidth, height: element.offsetHeight });
      });
      const current = nodeSizesRef.current;
      const changed = current.size !== next.size || [...next].some(([id, value]) => {
        const before = current.get(id);
        return before?.width !== value.width || before?.height !== value.height;
      });
      if (!changed) return;
      nodeSizesRef.current = next;
      setNodeSizes(next);
    };
    measure();
    const observer = new ResizeObserver(measure);
    root.querySelectorAll(".pmc-node[data-node]").forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [active, schemaKey, nodesKey, theme]);
  React.useLayoutEffect(() => {
    if (!active || !hover || hover.box || !hoverRef.current || typeof window === "undefined") return;
    const box = nodeHoverAbove(hover.anchor, window.innerWidth, hoverRef.current.offsetHeight);
    if (!box) {
      setHover(null);
      setHoverGuide("위쪽 공간이 부족합니다 · 클릭해 상세 보기");
      return;
    }
    setHover((current) => current?.node.id === hover.node.id ? { ...current, box } : current);
  }, [active, hover]);
  React.useEffect(() => {
    if (!active || !hover || typeof window === "undefined") return;
    const hide = () => {
      setHover(null);
      setHoverGuide("");
    };
    window.addEventListener("scroll", hide, true);
    return () => window.removeEventListener("scroll", hide, true);
  }, [active, hover]);
  React.useEffect(() => {
    if (!active) {
      cancelActive();
      setHover(null);
      setHoverGuide("");
    }
  }, [active, cancelActive]);
  React.useEffect(() => {
    if (priorEditableRef.current && !editable) cancelActive();
    priorEditableRef.current = editable;
  }, [editable, cancelActive]);
  React.useEffect(() => {
    if (priorPositionsKey.current === positionsKey) return;
    priorPositionsKey.current = positionsKey;
    const echo = consumePositionEcho(pendingPositionEchoesRef.current, positionsKey);
    pendingPositionEchoesRef.current = echo.remaining;
    if (echo.own) {
      if (echo.latest) {
        expectedSparsePositionsRef.current = positions.map((row) => ({ ...row }));
        setLocalPositions(normalizeCanvasPositions(nodes, positions));
      }
      return;
    }
    cancelActive();
    expectedSparsePositionsRef.current = positions.map((row) => ({ ...row }));
    setLocalPositions(normalizeCanvasPositions(nodes, positions));
    historyRef.current = [];
    futureRef.current = [];
    historyVersion((value) => value + 1);
  }, [positionsKey, schemaKey, cancelActive, setLocalPositions]);
  React.useEffect(() => {
    if (priorSchemaKey.current === schemaKey) return;
    priorSchemaKey.current = schemaKey;
    const active2 = activeRef.current;
    const stable2 = active2?.kind === "nodes" ? active2.before : positionsRef.current;
    const next = reconcileCanvasPositions(nodes, positions, stable2);
    cancelActive();
    setLocalPositions(next);
    setSelectedIds(/* @__PURE__ */ new Set());
    setFocusCompanyId(null);
    selectionReturnRef.current = null;
    previousCameraRef.current = null;
    historyRef.current = [];
    futureRef.current = [];
    fittedNodesRef.current = "";
    historyVersion((value) => value + 1);
  }, [schemaKey, positionsKey, cancelActive, setLocalPositions]);
  React.useEffect(() => {
    if (!size.width || !size.height || !shouldAutoFitCanvas(
      schemaKey,
      fittedNodesRef.current,
      currentNodes.map((node) => node.id),
      nodeSizes
    )) return;
    fittedNodesRef.current = schemaKey;
    setCamera(fitMapCamera(currentNodes, size));
  }, [schemaKey, size.width, size.height, currentNodes, nodeSizes, setCamera]);
  const point = (event) => {
    const rect = rootRef.current.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  };
  const showNodeHover = (event, node) => {
    if (!active || activeRef.current) return;
    const anchor = event.currentTarget.getBoundingClientRect();
    setHover({ node, anchor: { left: anchor.left, top: anchor.top, width: anchor.width }, box: null });
    setHoverGuide("");
  };
  const announce = (message) => {
    setStatus("");
    requestAnimationFrame(() => setStatus(message));
  };
  const commitMovement = (before, after, label2, remember = true) => {
    if (samePositions(before, after)) {
      setLocalPositions(before);
      return false;
    }
    const patch = changedPositionRows(before, after);
    if (!patch.length) {
      setLocalPositions(before);
      return false;
    }
    let accepted;
    try {
      accepted = onPositionsChangeRef.current(patch);
    } catch {
      setLocalPositions(before);
      announce("위치 변경을 적용하지 못했습니다.");
      return false;
    }
    if (!positionChangeAccepted(accepted)) {
      setLocalPositions(before);
      announce("위치 변경이 거절되어 이전 배치를 유지합니다.");
      return false;
    }
    const expected = mergePositionPatch(expectedSparsePositionsRef.current, patch);
    expectedSparsePositionsRef.current = expected;
    pendingPositionEchoesRef.current = [...pendingPositionEchoesRef.current.slice(-19), positionSignature(expected)];
    setLocalPositions(after);
    if (remember) {
      historyRef.current = [...historyRef.current.slice(-39), { before, after }];
      futureRef.current = [];
      historyVersion((value) => value + 1);
    }
    announce(label2);
    return true;
  };
  const emitSelection = (next) => {
    selectionRef.current = next;
    pendingSelectionEchoRef.current = selectionSignature(next);
    onSelectRef.current(next);
  };
  const restoreOverview = (notify = true, restorePrevious = false) => {
    const previous = previousCameraRef.current;
    selectionReturnRef.current = null;
    setFocusCompanyId(null);
    previousCameraRef.current = null;
    setSelectedIds(/* @__PURE__ */ new Set());
    setCamera(restorePrevious && previous ? previous : fitMapCamera(currentNodes, size));
    if (notify) emitSelection(null);
    else selectionRef.current = null;
    announce("전체 자료 묶음을 표시합니다.");
  };
  const focusCompany = (node, notify) => {
    selectionReturnRef.current = null;
    if (!previousCameraRef.current) previousCameraRef.current = cameraRef.current;
    const ids = companyNeighborhood(node.id, links);
    const related = currentNodes.filter((row) => ids.has(row.id));
    setFocusCompanyId(node.id);
    setSelectedIds(/* @__PURE__ */ new Set([node.id]));
    setCamera(fitMapCamera(related.length ? related : [node], size));
    if (notify) emitSelection({ kind: "company", id: node.id });
    announce(`${node.title} 주변 자료를 표시합니다.`);
  };
  const activateNode = (node, additive = false) => {
    if (additive) {
      setSelectedIds((current) => new Set(current).add(node.id));
      emitSelection({ kind: node.kind, id: node.id });
      announce("선택 항목을 추가했습니다.");
      return;
    }
    if (node.kind === "company") {
      if (focusCompanyId === node.id) {
        restoreOverview(true, true);
        return;
      }
      focusCompany(node, true);
      return;
    }
    if (selectionRef.current?.kind === node.kind && selectionRef.current.id === node.id) {
      restoreSelectionReturn();
      return;
    }
    captureSelectionReturn();
    setSelectedIds(/* @__PURE__ */ new Set([node.id]));
    emitSelection({ kind: node.kind, id: node.id });
    announce(`${node.title} ${node.kind === "note" ? "메모를" : mode === "documents" ? "자료를" : "검토 항목을"} 선택했습니다.`);
  };
  const clearSelection = (notify = true) => {
    selectionReturnRef.current = null;
    if (previousCameraRef.current) setCamera(previousCameraRef.current);
    previousCameraRef.current = null;
    setFocusCompanyId(null);
    setSelectedIds(/* @__PURE__ */ new Set());
    if (notify) emitSelection(null);
    else selectionRef.current = null;
    announce("선택을 해제했습니다.");
  };
  const captureSelectionReturn = () => {
    if (selectionReturnRef.current) return;
    selectionReturnRef.current = { selection: selectionRef.current, selectedIds: [...selectedIds], focusCompanyId, camera: cameraRef.current };
  };
  const restoreSelectionReturn = () => {
    const value = selectionReturnRef.current;
    if (!value) {
      clearSelection();
      return;
    }
    selectionReturnRef.current = null;
    setSelectedIds(new Set(value.selectedIds));
    setFocusCompanyId(value.focusCompanyId);
    setCamera(value.camera);
    emitSelection(value.selection);
    announce("이전 지도 보기로 돌아갑니다.");
  };
  const activateLink = (id) => {
    if (selectionRef.current?.kind === "link" && selectionRef.current.id === id) {
      restoreSelectionReturn();
      return;
    }
    captureSelectionReturn();
    setSelectedIds(/* @__PURE__ */ new Set());
    emitSelection({ kind: "link", id });
    announce(mode === "documents" ? "연결 자료를 선택했습니다." : "검토 연결을 선택했습니다.");
  };
  React.useEffect(() => {
    const key = selectionSignature(selection);
    const previous = selectionRef.current;
    if (pendingSelectionEchoRef.current === key) {
      selectionRef.current = selection;
      pendingSelectionEchoRef.current = null;
      return;
    }
    pendingSelectionEchoRef.current = null;
    if (!selection) {
      selectionReturnRef.current = null;
      selectionRef.current = null;
      clearSelection(false);
      return;
    }
    if (selection.kind === "company") {
      selectionReturnRef.current = null;
      selectionRef.current = selection;
      const node = nodeById.get(selection.id);
      if (node?.kind === "company") focusCompany(node, false);
      return;
    }
    if (!selectionReturnRef.current && previous?.kind !== "document" && previous?.kind !== "note" && previous?.kind !== "link") {
      selectionReturnRef.current = { selection: previous, selectedIds: [...selectedIds], focusCompanyId, camera: cameraRef.current };
    }
    selectionRef.current = selection;
    if (selection.kind === "document" || selection.kind === "note") setSelectedIds(/* @__PURE__ */ new Set([selection.id]));
    else setSelectedIds(/* @__PURE__ */ new Set());
  }, [selection?.kind, selection?.id]);
  const begin = (event, node) => {
    if (!active || event.button !== 0) return;
    event.stopPropagation();
    setHover(null);
    setHoverGuide("");
    rootRef.current?.focus();
    const start = point(event), pointerId = event.pointerId;
    if (spaceRef.current) activeRef.current = { kind: "pan", pointerId, start, camera: cameraRef.current };
    else if (node) {
      if (!editable) {
        activateNode(node, event.shiftKey);
        return;
      }
      const nextSelected = event.shiftKey ? new Set(selectedIds).add(node.id) : selectedIds.has(node.id) && selectedIds.size > 1 ? new Set(selectedIds) : /* @__PURE__ */ new Set([node.id]);
      setSelectedIds(nextSelected);
      activeRef.current = {
        kind: "nodes",
        pointerId,
        start,
        zoom: cameraRef.current.zoom,
        ids: [...nextSelected],
        before: positionsRef.current.map((row) => ({ ...row })),
        moved: false,
        node,
        additive: event.shiftKey
      };
    } else if (editable) activeRef.current = { kind: "marquee", pointerId, start, current: start, additive: event.shiftKey };
    else {
      clearSelection();
      return;
    }
    rootRef.current?.setPointerCapture(pointerId);
  };
  const move = (event) => {
    const active2 = activeRef.current;
    if (!active2 || active2.pointerId !== event.pointerId) return;
    const cursor = point(event), dx = cursor.x - active2.start.x, dy = cursor.y - active2.start.y;
    if (active2.kind === "pan") setCamera({ ...active2.camera, x: active2.camera.x + dx, y: active2.camera.y + dy });
    else if (active2.kind === "marquee") {
      active2.current = cursor;
      setMarquee(marqueeFrom(active2.start, cursor));
    } else {
      active2.moved ||= Math.abs(dx) + Math.abs(dy) > 3;
      if (active2.moved) setLocalPositions(applyNodeMovement(active2.before, active2.ids, dx / active2.zoom, dy / active2.zoom));
    }
  };
  const finish = (event, cancelled = false) => {
    const active2 = activeRef.current;
    if (!active2 || active2.pointerId !== event.pointerId) return;
    activeRef.current = null;
    if (rootRef.current?.hasPointerCapture(event.pointerId)) rootRef.current.releasePointerCapture(event.pointerId);
    if (active2.kind === "nodes") {
      if (cancelled) setLocalPositions(active2.before);
      else if (active2.moved) commitMovement(active2.before, positionsRef.current, `${active2.ids.length}개 항목 위치를 변경했습니다.`);
      else activateNode(active2.node, active2.additive);
    } else if (active2.kind === "marquee") {
      setMarquee(null);
      if (cancelled) return;
      const found = nodesInMarquee(currentNodes, cameraRef.current, marqueeFrom(active2.start, active2.current));
      const next = active2.additive ? /* @__PURE__ */ new Set([...selectedIds, ...found]) : new Set(found);
      selectionReturnRef.current = null;
      setSelectedIds(next);
      if (next.size === 1) {
        const id = [...next][0], node = nodeById.get(id);
        if (node) emitSelection({ kind: node.kind, id });
      } else emitSelection(null);
      announce(`${next.size}개 항목을 선택했습니다.`);
    }
  };
  const travel = (redo) => {
    if (!editable || activeRef.current) return;
    const source = redo ? futureRef : historyRef, target = redo ? historyRef : futureRef;
    const entry = source.current.at(-1);
    if (!entry) return;
    const before = positionsRef.current.map((row) => ({ ...row })), after = (redo ? entry.after : entry.before).map((row) => ({ ...row }));
    if (!commitMovement(before, after, redo ? "위치 변경을 다시 실행했습니다." : "위치 변경을 되돌렸습니다.", false)) return;
    source.current.pop();
    target.current.push(entry);
    historyVersion((value) => value + 1);
  };
  const nudge = (node, key, large) => {
    if (!editable) return;
    const ids = selectedIds.has(node.id) ? [...selectedIds] : [node.id];
    const amount = large ? 40 : 8;
    const dx = key === "ArrowLeft" ? -amount : key === "ArrowRight" ? amount : 0;
    const dy = key === "ArrowUp" ? -amount : key === "ArrowDown" ? amount : 0;
    const before = positionsRef.current.map((row) => ({ ...row }));
    commitMovement(before, applyNodeMovement(before, ids, dx, dy), `${ids.length}개 항목 위치를 변경했습니다.`);
  };
  const resetLayout = () => {
    if (!editable || activeRef.current) return;
    const before = positionsRef.current.map((row) => ({ ...row }));
    const after = resetVisiblePositions(nodes, before);
    if (commitMovement(before, after, "기본 배치로 초기화했습니다.")) restoreOverview();
  };
  const currentSelection = selectionRef.current;
  const selectedLink = currentSelection?.kind === "link" ? currentSelection.id : null;
  const companyCount = nodes.filter((node) => node.kind === "company").length;
  const documentCount = nodes.filter((node) => node.kind === "document").length;
  const gridSize = Math.max(8, GRID * camera.zoom);
  return /* @__PURE__ */ React.createElement(
    "div",
    {
      ref: rootRef,
      className: "pmc",
      "data-theme": theme,
      "data-active": active,
      role: "region",
      tabIndex: active ? 0 : -1,
      "aria-hidden": !active,
      "aria-label": `${modeText.region}. 휠 또는 두 손가락으로 이동하고, Control 또는 Command와 휠로 확대합니다.`,
      onPointerDown: (event) => begin(event),
      onPointerMove: move,
      onPointerUp: (event) => finish(event),
      onPointerCancel: (event) => finish(event, true),
      onLostPointerCapture: (event) => finish(event, true),
      onKeyDown: (event) => {
        if (!active) return;
        const target = event.target;
        const editing = !!target.closest('input,textarea,select,[contenteditable="true"]');
        if (!editing && !event.nativeEvent.isComposing && (event.metaKey || event.ctrlKey)) {
          const key = event.key.toLowerCase();
          if (key === "a") {
            event.preventDefault();
            event.stopPropagation();
            selectionReturnRef.current = null;
            if (previousCameraRef.current) setCamera(previousCameraRef.current);
            previousCameraRef.current = null;
            setFocusCompanyId(null);
            setSelectedIds(new Set(currentNodes.map((node) => node.id)));
            emitSelection(null);
            announce(`${currentNodes.length}개 항목을 선택했습니다.`);
            return;
          }
          if (key === "z") {
            event.preventDefault();
            event.stopPropagation();
            travel(event.shiftKey);
            return;
          }
          if (key === "y") {
            event.preventDefault();
            event.stopPropagation();
            travel(true);
            return;
          }
        }
        if (target !== event.currentTarget) return;
        if (event.code === "Space") {
          spaceRef.current = true;
          event.preventDefault();
          return;
        }
        if (event.key === "Escape") {
          event.preventDefault();
          clearSelection();
          return;
        }
        if (event.key.startsWith("Arrow")) {
          event.preventDefault();
          const current = cameraRef.current;
          setCamera({
            ...current,
            x: current.x + (event.key === "ArrowLeft" ? 36 : event.key === "ArrowRight" ? -36 : 0),
            y: current.y + (event.key === "ArrowUp" ? 36 : event.key === "ArrowDown" ? -36 : 0)
          });
        }
      },
      onKeyUp: (event) => {
        if (event.code === "Space") spaceRef.current = false;
      },
      onBlur: (event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) spaceRef.current = false;
      }
    },
    /* @__PURE__ */ React.createElement("style", null, CSS),
    /* @__PURE__ */ React.createElement("div", { className: "pmc-grid", "aria-hidden": "true", style: {
      backgroundSize: `${gridSize}px ${gridSize}px`,
      backgroundPosition: `${camera.x % gridSize}px ${camera.y % gridSize}px`
    } }),
    /* @__PURE__ */ React.createElement("div", { className: "pmc-summary", "aria-label": `전체 ${companyCount}종목, ${modeText.item} ${documentCount}건` }, "전체 ", companyCount, "종목 · ", modeText.item, " ", documentCount, "건"),
    /* @__PURE__ */ React.createElement("div", { className: "pmc-toolbar", role: "toolbar", "aria-label": "지도 보기와 배치 도구", onPointerDown: (event) => event.stopPropagation() }, /* @__PURE__ */ React.createElement(
      "button",
      {
        className: "pmc-control",
        type: "button",
        "aria-label": controlTitle("축소"),
        onClick: () => setCamera(zoomMapCamera(cameraRef.current, 1 / 1.2, { x: size.width / 2, y: size.height / 2 }))
      },
      "−"
    ), /* @__PURE__ */ React.createElement("span", { className: "pmc-zoom", "aria-label": `배율 ${Math.round(camera.zoom * 100)}퍼센트` }, Math.round(camera.zoom * 100), "%"), /* @__PURE__ */ React.createElement(
      "button",
      {
        className: "pmc-control",
        type: "button",
        "aria-label": controlTitle("확대"),
        onClick: () => setCamera(zoomMapCamera(cameraRef.current, 1.2, { x: size.width / 2, y: size.height / 2 }))
      },
      "＋"
    ), /* @__PURE__ */ React.createElement("span", { className: "pmc-divider", "aria-hidden": "true" }), /* @__PURE__ */ React.createElement("button", { className: "pmc-control", type: "button", "aria-label": "위치 변경 되돌리기", title: "되돌리기", disabled: !editable || !historyRef.current.length, onClick: () => travel(false) }, "↶"), /* @__PURE__ */ React.createElement("button", { className: "pmc-control", type: "button", "aria-label": "위치 변경 다시 실행", title: "다시 실행", disabled: !editable || !futureRef.current.length, onClick: () => travel(true) }, "↷"), /* @__PURE__ */ React.createElement("button", { className: "pmc-control", type: "button", "aria-label": overviewLabel, title: "한눈에", onClick: () => restoreOverview() }, "전체"), /* @__PURE__ */ React.createElement("button", { className: "pmc-control", type: "button", "aria-label": "기본 배치로 초기화", title: "배치 초기화", disabled: !editable, onClick: resetLayout }, "초기화"), /* @__PURE__ */ React.createElement(
      "button",
      {
        className: "pmc-control",
        type: "button",
        "aria-pressed": motion,
        "aria-label": `연결선 움직임 ${motion ? "끄기" : "켜기"}`,
        title: "연결선 움직임",
        onClick: () => onMotionChangeRef.current(!motion)
      },
      "움직임"
    )),
    /* @__PURE__ */ React.createElement("div", { className: "pmc-world", style: { transform: `translate(${camera.x}px,${camera.y}px) scale(${camera.zoom})` } }, /* @__PURE__ */ React.createElement("svg", { className: "pmc-lines", "aria-label": modeText.line }, links.map((link) => {
      const from = nodeById.get(link.companyId), to = nodeById.get(link.documentId);
      if (!from || !to) return null;
      const geometry = edgeGeometry(from, to);
      const relevant = selectedLink === link.id || currentSelection?.id === link.companyId || currentSelection?.id === link.documentId;
      const dim = !!focusIds && !(focusIds.has(link.companyId) && focusIds.has(link.documentId));
      const label2 = link.label || (link.confirmation === "confirmed" ? "직접적인 문서 연결 확인" : "종목과 자료 연결 미확인");
      return /* @__PURE__ */ React.createElement("g", { key: link.id, className: dim ? "pmc-dim" : void 0 }, /* @__PURE__ */ React.createElement("path", { className: "pmc-edge", "data-confirmation": link.confirmation, "data-active": relevant, d: geometry.d }), motion && relevant ? /* @__PURE__ */ React.createElement("g", { className: "pmc-moving-chevron", style: { offsetPath: `path('${geometry.d}')` }, "aria-hidden": "true" }, /* @__PURE__ */ React.createElement("path", { d: "M -4 -4 L 0 0 L -4 4" })) : /* @__PURE__ */ React.createElement("path", { className: "pmc-chevron", d: "M -4 -4 L 0 0 L -4 4", transform: `translate(${geometry.mx} ${geometry.my}) rotate(${geometry.angle})`, "aria-hidden": "true" }), /* @__PURE__ */ React.createElement(
        "path",
        {
          className: "pmc-edge-hit",
          d: geometry.d,
          tabIndex: active ? 0 : -1,
          role: "button",
          "aria-label": `${label2}. ${mode === "documents" ? "기업 영향 관계가 아닙니다." : modeText.disclaimer} 상세 선택`,
          onPointerDown: (event) => event.stopPropagation(),
          onClick: () => activateLink(link.id),
          onKeyDown: (event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              activateLink(link.id);
            }
          }
        }
      ));
    })), currentNodes.map((node) => /* @__PURE__ */ React.createElement(
      "button",
      {
        key: node.id,
        type: "button",
        tabIndex: active ? 0 : -1,
        className: `pmc-node${focusIds && !focusIds.has(node.id) ? " pmc-dim" : ""}`,
        "data-node": node.id,
        "data-kind": node.kind,
        "data-done": node.kind === "note" && node.done ? "true" : void 0,
        "data-source": node.kind === "document" ? node.sourceKind || "other" : void 0,
        "data-selected": selectedIds.has(node.id) || currentSelection?.id === node.id,
        style: { left: node.x, top: node.y },
        "aria-pressed": selectedIds.has(node.id) || currentSelection?.id === node.id,
        "aria-describedby": hover?.node.id === node.id && hover.box ? "pmc-node-hover" : void 0,
        "aria-label": node.semanticLabel || `${node.kind === "company" ? "종목" : node.kind === "document" ? "자료" : "메모"}: ${node.title}. ${node.subtitle}`,
        onPointerDown: (event) => begin(event, node),
        onClick: (event) => {
          if (event.detail === 0) activateNode(node, event.shiftKey);
        },
        onMouseEnter: (event) => showNodeHover(event, node),
        onMouseLeave: () => {
          setHover(null);
          setHoverGuide("");
        },
        onKeyDown: (event) => {
          if (event.key.startsWith("Arrow")) {
            event.preventDefault();
            event.stopPropagation();
            nudge(node, event.key, event.shiftKey);
            return;
          }
          if ((event.key === "Enter" || event.key === " ") && event.shiftKey) {
            event.preventDefault();
            activateNode(node, true);
          }
        }
      },
      /* @__PURE__ */ React.createElement("strong", null, node.title),
      /* @__PURE__ */ React.createElement("span", null, node.subtitle),
      node.kind === "note" && node.done ? /* @__PURE__ */ React.createElement("small", { className: "pmc-note-done", "aria-hidden": "true" }, "✓ 완료") : null
    ))),
    marquee ? /* @__PURE__ */ React.createElement("div", { className: "pmc-marquee", style: marquee, "aria-hidden": "true" }) : null,
    active && hover && typeof document !== "undefined" && typeof window !== "undefined" ? createPortal(/* @__PURE__ */ React.createElement(
      "div",
      {
        ref: hoverRef,
        id: "pmc-node-hover",
        className: "pmc-hover",
        "data-theme": theme,
        role: "tooltip",
        style: hover.box || { left: -1e4, top: -1e4, width: Math.min(270, Math.max(120, window.innerWidth - 16)), visibility: "hidden" }
      },
      /* @__PURE__ */ React.createElement("strong", null, hover.node.title),
      /* @__PURE__ */ React.createElement("span", null, hover.node.subtitle),
      /* @__PURE__ */ React.createElement("small", null, "클릭해 상세 보기")
    ), document.body) : null,
    !nodes.length ? /* @__PURE__ */ React.createElement("div", { className: "pmc-empty" }, "표시할 종목과 ", modeText.item, "가 없습니다.") : null,
    /* @__PURE__ */ React.createElement("div", { className: "pmc-help" }, hoverGuide || "빈 공간 드래그 선택 · Shift 추가 · Space+드래그 이동"),
    /* @__PURE__ */ React.createElement("div", { className: "pmc-legend", "aria-label": "연결선 범례" }, /* @__PURE__ */ React.createElement("span", { className: "pmc-legend-row" }, /* @__PURE__ */ React.createElement("i", { className: "pmc-legend-line" }), " ", modeText.legend), mode === "documents" ? /* @__PURE__ */ React.createElement("span", { className: "pmc-legend-row" }, /* @__PURE__ */ React.createElement("i", { className: "pmc-legend-line", "data-kind": "unknown" }), " 점선 · 종목과 자료 연결 미확인") : null, /* @__PURE__ */ React.createElement("span", null, modeText.disclaimer)),
    /* @__PURE__ */ React.createElement("span", { className: "pmc-status", role: "status", "aria-live": "polite" }, status)
  );
}

// framer-components/public-probe/PortfolioMapGuide.tsx
import * as React2 from "react";
var { useEffect: useEffect2, useId, useRef: useRef2, useState: useState2 } = React2;
var PORTFOLIO_MAP_GUIDE_STORAGE_KEY = "alphanest:member-map-guide:v1";
function localStorageOrNull() {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}
function readPortfolioMapGuideSeen(storage = localStorageOrNull()) {
  try {
    return storage?.getItem(PORTFOLIO_MAP_GUIDE_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}
function rememberPortfolioMapGuideSeen(storage = localStorageOrNull()) {
  try {
    storage?.setItem(PORTFOLIO_MAP_GUIDE_STORAGE_KEY, "1");
    return storage !== null;
  } catch {
    return false;
  }
}
var dialogStyle = {
  width: "min(580px, calc(100vw - 24px))",
  maxHeight: "min(720px, calc(100dvh - 24px))",
  margin: "auto",
  padding: 0,
  overflow: "auto",
  border: "1px solid var(--ppm-border, color-mix(in srgb, currentColor 14%, transparent))",
  borderRadius: 18,
  background: "var(--bg, #fff)",
  color: "var(--ink, #292636)",
  boxShadow: "0 20px 60px color-mix(in srgb, #000 30%, transparent)",
  fontFamily: "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
};
function PortfolioMapGuide() {
  const dialogRef = useRef2(null);
  const triggerRef = useRef2(null);
  const titleRef = useRef2(null);
  const closedByUserRef = useRef2(false);
  const titleId = useId();
  const [open, setOpen] = useState2(false);
  useEffect2(() => {
    if (!readPortfolioMapGuideSeen()) setOpen(true);
  }, []);
  useEffect2(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
      dialog.scrollTop = 0;
      titleRef.current?.focus({ preventScroll: true });
    }
    if (!open && dialog.open) dialog.close();
  }, [open]);
  const dismiss = () => {
    closedByUserRef.current = true;
    dialogRef.current?.close();
  };
  const handleClose = () => {
    if (closedByUserRef.current) rememberPortfolioMapGuideSeen();
    closedByUserRef.current = false;
    setOpen(false);
    requestAnimationFrame(() => triggerRef.current?.focus({ preventScroll: true }));
  };
  return /* @__PURE__ */ React2.createElement(React2.Fragment, null, /* @__PURE__ */ React2.createElement("style", null, `.ppm-guide summary{list-style:none;display:flex;gap:6px;align-items:center}.ppm-guide summary::-webkit-details-marker{display:none}.ppm-guide summary svg{transition:transform .15s}.ppm-guide details[open] summary svg{transform:rotate(90deg)}@media(prefers-reduced-motion:reduce){.ppm-guide summary svg{transition:none}}`), /* @__PURE__ */ React2.createElement(
    "button",
    {
      ref: triggerRef,
      type: "button",
      "aria-haspopup": "dialog",
      "aria-expanded": open,
      onClick: () => setOpen(true),
      style: {
        border: "1px solid var(--ppm-border, color-mix(in srgb, currentColor 14%, transparent))",
        borderRadius: 10,
        padding: "8px 10px",
        background: "var(--soft, #f4f1fb)",
        color: "var(--ink, #292636)",
        font: "inherit",
        fontWeight: 500,
        cursor: "pointer"
      }
    },
    "사용법·표시 기준"
  ), /* @__PURE__ */ React2.createElement(
    "dialog",
    {
      className: "ppm-guide",
      ref: dialogRef,
      "aria-labelledby": titleId,
      onCancel: (event) => {
        event.preventDefault();
        dismiss();
      },
      onClose: handleClose,
      onKeyDown: (event) => {
        if (event.key !== "Tab") return;
        const controls = Array.from(event.currentTarget.querySelectorAll("button:not([disabled]), summary")).filter((element) => element.getClientRects().length > 0);
        const first = controls[0], last = controls[controls.length - 1];
        if (!first || !last) return;
        if (event.shiftKey && (document.activeElement === first || document.activeElement === titleRef.current)) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      },
      style: dialogStyle
    },
    /* @__PURE__ */ React2.createElement("div", { style: { padding: "20px 20px 22px" } }, /* @__PURE__ */ React2.createElement("div", { style: { display: "flex", alignItems: "start", justifyContent: "space-between", gap: 12 } }, /* @__PURE__ */ React2.createElement("div", null, /* @__PURE__ */ React2.createElement("p", { style: { margin: "0 0 5px", fontSize: 13, fontWeight: 400, color: "var(--muted, #716d7f)" } }, "내 종목 연결 지도"), /* @__PURE__ */ React2.createElement("h2", { ref: titleRef, id: titleId, tabIndex: -1, style: { margin: 0, fontSize: 18, fontWeight: 500, lineHeight: 1.35, outline: "none", background: "transparent", color: "inherit" } }, "사용법·표시 기준")), /* @__PURE__ */ React2.createElement("button", { type: "button", onClick: dismiss, "aria-label": "안내 닫기", style: closeStyle }, /* @__PURE__ */ React2.createElement("svg", { width: "18", height: "18", viewBox: "0 0 24 24", "aria-hidden": "true" }, /* @__PURE__ */ React2.createElement("path", { d: "M6 6 18 18M18 6 6 18", fill: "none", stroke: "currentColor", strokeWidth: "1.8", strokeLinecap: "round" })))), /* @__PURE__ */ React2.createElement("p", { style: bodyStyle }, "내 종목과 연결된 자료를 한눈에 보세요. 지금의 선과 움직임은 자료를 찾아보는 안내이며, 기업 영향력이나 최신성 점수가 아니에요."), /* @__PURE__ */ React2.createElement("ol", { style: { ...bodyStyle, paddingLeft: 22, marginBottom: 14 } }, /* @__PURE__ */ React2.createElement("li", null, /* @__PURE__ */ React2.createElement("strong", { style: strongStyle }, "종목을 선택"), "하면 주변의 자료와 관계를 읽습니다."), /* @__PURE__ */ React2.createElement("li", null, /* @__PURE__ */ React2.createElement("strong", { style: strongStyle }, "같은 항목을 다시 선택"), "하면 이전 보기로 돌아갑니다."), /* @__PURE__ */ React2.createElement("li", null, /* @__PURE__ */ React2.createElement("strong", { style: strongStyle }, "선과 자료"), "를 열어 근거와 아직 확인하지 못한 부분을 구분합니다.")), /* @__PURE__ */ React2.createElement("div", { style: diagramStyle, "aria-label": "회사와 자료의 연결 확인 및 미확인 예시" }, /* @__PURE__ */ React2.createElement("span", null, "회사"), /* @__PURE__ */ React2.createElement("i", { style: solidLineStyle }), /* @__PURE__ */ React2.createElement("span", null, "자료"), /* @__PURE__ */ React2.createElement("span", null, "회사"), /* @__PURE__ */ React2.createElement("i", { style: dashedLineStyle }), /* @__PURE__ */ React2.createElement("span", null, "조회 관계")), /* @__PURE__ */ React2.createElement("p", { style: smallStyle }, "실선은 해당 종목의 공시·사업자료에 포함된 연결, 점선은 조회에 포함됐지만 아직 확인하지 못한 연결이에요. 기업 간 사업관계나 호재·악재를 뜻하지 않아요. 같은 자료를 봤다고 공통 사건이라는 뜻은 아닙니다."), /* @__PURE__ */ React2.createElement("details", { style: { marginTop: 16 } }, /* @__PURE__ */ React2.createElement("summary", { style: { cursor: "pointer", fontSize: 14, fontWeight: 500 } }, /* @__PURE__ */ React2.createElement("svg", { width: "12", height: "12", viewBox: "0 0 12 12", "aria-hidden": "true" }, /* @__PURE__ */ React2.createElement("path", { d: "m4 2 4 4-4 4", fill: "none", stroke: "currentColor", strokeWidth: "1.5" })), "자세한 조작표"), /* @__PURE__ */ React2.createElement("ul", { style: { ...bodyStyle, paddingLeft: 20, marginTop: 10 } }, /* @__PURE__ */ React2.createElement("li", null, "휠·두 손가락으로 이동하고, Cmd/Ctrl+휠로 확대합니다."), /* @__PURE__ */ React2.createElement("li", null, "Space+드래그로 이동, Shift로 추가 선택, 드래그로 여러 항목을 선택합니다."), /* @__PURE__ */ React2.createElement("li", null, "Cmd/Ctrl+Z로 배치 이동을 되돌립니다."), /* @__PURE__ */ React2.createElement("li", null, "읽음·중요·나중에·메모는 화면에 바로 반영돼요. 다음 방문에도 남기려면 ‘명시 저장’을 눌러요."))), /* @__PURE__ */ React2.createElement("p", { style: smallStyle }, "‘확인할 자료’는 마지막 방문 기준이 아니라 미읽음 또는 제공 내용 변경을 뜻합니다."), /* @__PURE__ */ React2.createElement("p", { style: smallStyle }, "안내를 닫으면 이 브라우저에 확인 여부만 기억해요. 개인 기록은 여기에 저장하지 않아요."), /* @__PURE__ */ React2.createElement("button", { type: "button", className: "ppm-primary", onClick: dismiss, style: { marginTop: 16 } }, "지도 보기"))
  ));
}
var bodyStyle = { margin: "14px 0", fontSize: 14, fontWeight: 400, lineHeight: 1.6 };
var smallStyle = { margin: "10px 0 0", fontSize: 13, fontWeight: 400, lineHeight: 1.55, color: "var(--muted, #716d7f)" };
var strongStyle = { fontWeight: 500 };
var diagramStyle = { display: "grid", gridTemplateColumns: "auto 1fr auto", gap: 8, alignItems: "center", padding: 12, borderRadius: 12, background: "var(--soft, #f4f1fb)", fontSize: 13, fontWeight: 400 };
var solidLineStyle = { borderTop: "2px solid currentColor" };
var dashedLineStyle = { borderTop: "2px dashed currentColor" };
var closeStyle = { display: "grid", placeItems: "center", width: 36, height: 36, flex: "0 0 auto", border: "1px solid var(--ppm-border, color-mix(in srgb, currentColor 14%, transparent))", borderRadius: "50%", background: "transparent", color: "inherit", cursor: "pointer" };

// framer-components/public-probe/PortfolioCompanyDetails.tsx
import * as React3 from "react";
var SECTION_IDS = ["finance", "valuation", "holders", "risks"];
var SECTION_TITLES = {
  finance: "재무",
  valuation: "가치 지표",
  holders: "주주·자본",
  risks: "확인할 위험"
};
var CONTROL_CHARACTERS = /[\u0000-\u001f\u007f]/;
function safeHttpsLink(raw) {
  if (!raw || CONTROL_CHARACTERS.test(raw)) return null;
  try {
    if (CONTROL_CHARACTERS.test(decodeURIComponent(raw))) return null;
    const parsed = new URL(raw);
    return parsed.protocol === "https:" && !parsed.username && !parsed.password ? raw : null;
  } catch {
    return null;
  }
}
function selectCompanyDetailSections(sections = []) {
  return SECTION_IDS.map((id) => ({ id, section: sections.find((section) => section.id === id) }));
}
function SectionNotice({ section }) {
  if (!section) return /* @__PURE__ */ React3.createElement("p", { className: "pcd-notice" }, "자료 미제공 · 수집 여부를 확인할 수 없습니다.");
  if (section.state === "error") return /* @__PURE__ */ React3.createElement("p", { className: "pcd-notice" }, "자료를 온전히 불러오지 못했습니다. 아래 값이 있어도 전체 조회 성공을 뜻하지 않습니다.", section.message ? `
${section.message}` : "");
  if (section.state === "unsupported") return /* @__PURE__ */ React3.createElement("p", { className: "pcd-notice" }, "현재 제공 범위를 확인할 수 없습니다.", section.message ? `
${section.message}` : "");
  if (section.message) return /* @__PURE__ */ React3.createElement("p", { className: "pcd-notice" }, section.message);
  if (section.items.length) return null;
  return /* @__PURE__ */ React3.createElement("p", { className: "pcd-notice" }, "제공된 항목이 비어 있습니다. 수집 실패나 해당 사실이 없다는 뜻은 아닙니다.");
}
function SourceLink({ url, label: label2 }) {
  const href = safeHttpsLink(url);
  if (href) return /* @__PURE__ */ React3.createElement("a", { href, target: "_blank", rel: "noopener noreferrer" }, label2, /* @__PURE__ */ React3.createElement("span", { "aria-hidden": "true" }, " ↗"));
  return /* @__PURE__ */ React3.createElement("small", null, url ? "안전하게 열 수 있는 HTTPS 원문 링크가 아닙니다." : "원문 링크 미제공");
}
function ItemSources({ item }) {
  return /* @__PURE__ */ React3.createElement("div", { className: "pcd-sources", "aria-label": "출처" }, /* @__PURE__ */ React3.createElement("div", { className: "pcd-source" }, /* @__PURE__ */ React3.createElement("span", null, item.source || "출처 미제공", " · ", item.asOf || "기준일 미제공"), /* @__PURE__ */ React3.createElement(SourceLink, { url: item.url, label: "원문" })), (item.sources || []).map((source, index) => /* @__PURE__ */ React3.createElement("div", { className: "pcd-source", key: `${source.title}:${source.source}:${index}` }, /* @__PURE__ */ React3.createElement("span", null, source.title, " · ", source.source || "출처 미제공", " · ", source.asOf || "기준일 미제공"), /* @__PURE__ */ React3.createElement(SourceLink, { url: source.url, label: "원문" }))));
}
function ItemRows({ item }) {
  if (!item.rows?.length) return null;
  return /* @__PURE__ */ React3.createElement("dl", { className: "pcd-rows" }, item.rows.map((row, index) => /* @__PURE__ */ React3.createElement("div", { key: `${row.label}:${index}` }, /* @__PURE__ */ React3.createElement("dt", null, row.label), /* @__PURE__ */ React3.createElement("dd", null, row.value))));
}
function ItemChart({ item }) {
  if (!item.chart?.length) return null;
  return /* @__PURE__ */ React3.createElement("div", { className: "pcd-table-wrap" }, /* @__PURE__ */ React3.createElement("table", null, /* @__PURE__ */ React3.createElement("thead", null, /* @__PURE__ */ React3.createElement("tr", null, /* @__PURE__ */ React3.createElement("th", { scope: "col" }, "연도·기간"), /* @__PURE__ */ React3.createElement("th", { scope: "col" }, item.id === "annual-income" ? "매출" : item.title), /* @__PURE__ */ React3.createElement("th", { scope: "col" }, "통화·단위"))), /* @__PURE__ */ React3.createElement("tbody", null, item.chart.map((point, index) => /* @__PURE__ */ React3.createElement("tr", { key: `${point.label}:${index}` }, /* @__PURE__ */ React3.createElement("th", { scope: "row" }, point.label), /* @__PURE__ */ React3.createElement("td", null, point.value), /* @__PURE__ */ React3.createElement("td", null, item.unit || "단위 미제공"))))));
}
function ItemReferences({ item }) {
  if (!item.references?.length) return null;
  return /* @__PURE__ */ React3.createElement("div", { className: "pcd-references" }, /* @__PURE__ */ React3.createElement("h5", null, "참조 항목"), /* @__PURE__ */ React3.createElement("ul", null, item.references.map((reference, index) => /* @__PURE__ */ React3.createElement("li", { key: `${reference.sectionId}:${reference.itemId}:${index}` }, /* @__PURE__ */ React3.createElement("span", null, reference.label), /* @__PURE__ */ React3.createElement("small", null, "참조 항목 이름 · 원문 링크 미제공")))));
}
function DetailItem({ item, sectionId }) {
  return /* @__PURE__ */ React3.createElement("article", { className: "pcd-item" }, /* @__PURE__ */ React3.createElement("div", { className: "pcd-item-head" }, /* @__PURE__ */ React3.createElement("h4", null, item.title), sectionId === "risks" && item.kind === "question" ? /* @__PURE__ */ React3.createElement("span", { className: "pcd-question" }, "확인 질문") : null), item.value !== void 0 ? /* @__PURE__ */ React3.createElement("p", { className: "pcd-value" }, /* @__PURE__ */ React3.createElement("span", null, item.value), item.unit !== void 0 ? /* @__PURE__ */ React3.createElement("small", null, item.unit) : null) : null, /* @__PURE__ */ React3.createElement("p", { className: "pcd-explanation" }, item.explanation), /* @__PURE__ */ React3.createElement(ItemRows, { item }), /* @__PURE__ */ React3.createElement(ItemChart, { item }), /* @__PURE__ */ React3.createElement(ItemReferences, { item }), /* @__PURE__ */ React3.createElement(ItemSources, { item }));
}
var CSS2 = `
.pcd summary:focus-visible{outline:none;background:color-mix(in srgb,var(--accent) 16%,var(--bg))}
.pcd{width:100%;min-width:0;display:grid;gap:8px;color:var(--ink);font:400 13px/1.5 Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;overflow-wrap:anywhere;word-break:break-word}
.pcd *{box-sizing:border-box;min-width:0}.pcd details{border-radius:12px;background:var(--soft);overflow:hidden}.pcd summary{min-height:42px;padding:10px 12px;display:flex;align-items:center;gap:8px;cursor:pointer;list-style:none;font-weight:500}.pcd summary::-webkit-details-marker{display:none}.pcd summary::marker{content:""}.pcd summary small{margin-left:auto;color:var(--muted);font-size:12px;font-weight:400;white-space:nowrap}.pcd-chevron{color:var(--accent);font-size:15px;line-height:1;transform:rotate(-90deg);transition:transform .16s ease}.pcd details[open] .pcd-chevron{transform:rotate(0)}
.pcd-section-body{padding:0 8px 8px;display:grid;gap:8px}.pcd-notice{margin:0;padding:10px;border-radius:9px;background:var(--bg);color:var(--muted);font-size:12px;font-weight:400;white-space:pre-wrap}.pcd-item{display:grid;gap:8px;padding:11px;border-radius:10px;background:var(--bg)}.pcd-item-head{display:flex;align-items:flex-start;gap:8px}.pcd h4,.pcd h5,.pcd p{margin:0}.pcd h4{font-size:13px;font-weight:500;line-height:1.4}.pcd h5{font-size:12px;font-weight:500}.pcd-question{margin-left:auto;flex:none;padding:3px 6px;border-radius:999px;background:color-mix(in srgb,var(--accent) 14%,var(--bg));color:var(--accent);font-size:12px;font-weight:500;white-space:nowrap}.pcd-value{display:flex;align-items:baseline;flex-wrap:wrap;gap:4px 7px;font-size:13px;font-weight:500}.pcd-value small,.pcd-source small,.pcd-references small{color:var(--muted);font-size:12px;font-weight:400}.pcd-explanation{white-space:pre-wrap;font-weight:400}
.pcd-rows{margin:0;display:grid;gap:5px}.pcd-rows>div{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px;padding-top:5px;border-top:1px solid color-mix(in srgb,var(--ink) 10%,transparent)}.pcd dt{color:var(--muted);font-size:12px;font-weight:400}.pcd dd{margin:0;text-align:right;font-size:12px;font-weight:500}.pcd-table-wrap{width:100%;overflow:hidden}.pcd table{width:100%;table-layout:fixed;border-collapse:collapse;font-size:12px}.pcd th,.pcd td{padding:6px 5px;border-top:1px solid color-mix(in srgb,var(--ink) 10%,transparent);text-align:left;vertical-align:top;overflow-wrap:anywhere}.pcd th{font-weight:500}.pcd td{font-weight:400}
.pcd-references{display:grid;gap:5px}.pcd-references ul{margin:0;padding:0;display:grid;gap:5px;list-style:none}.pcd-references li{display:grid;gap:1px}.pcd-sources{display:grid;gap:6px;padding-top:2px}.pcd-source{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;color:var(--muted);font-size:12px;font-weight:400}.pcd-source>a{flex:none;color:var(--accent);font-size:12px;font-weight:500;text-decoration:none;white-space:nowrap}.pcd a:hover{color:var(--ink)}.pcd a:focus-visible{outline:none;background:color-mix(in srgb,var(--accent) 16%,var(--bg));border-radius:4px}
@media(max-width:390px){.pcd summary{padding:10px}.pcd-section-body{padding:0 6px 6px}.pcd-item{padding:10px}.pcd-source{display:grid;justify-content:stretch}.pcd-source>a{justify-self:start}}
@media(prefers-reduced-motion:reduce){.pcd-chevron{transition:none}}
`;
function PortfolioCompanyDetails({ sections }) {
  return /* @__PURE__ */ React3.createElement("section", { className: "pcd", "aria-label": "종목 상세 자료" }, /* @__PURE__ */ React3.createElement("style", null, CSS2), selectCompanyDetailSections(sections).map(({ id, section }) => /* @__PURE__ */ React3.createElement("details", { key: id }, /* @__PURE__ */ React3.createElement("summary", null, /* @__PURE__ */ React3.createElement("span", { className: "pcd-chevron", "aria-hidden": "true" }, "⌄"), /* @__PURE__ */ React3.createElement("span", null, section?.title || SECTION_TITLES[id]), /* @__PURE__ */ React3.createElement("small", null, section?.items.length || 0, "개 항목")), /* @__PURE__ */ React3.createElement("div", { className: "pcd-section-body" }, /* @__PURE__ */ React3.createElement(SectionNotice, { section }), (section?.items || []).map((item, index) => /* @__PURE__ */ React3.createElement(DetailItem, { key: `${item.id}:${index}`, item, sectionId: id }))))));
}

// framer-components/public-probe/PortfolioCloseDetails.tsx
import * as React4 from "react";
function closePriceLabel(price, currency) {
  if (currency === "KRW" || currency === "USD") {
    return new Intl.NumberFormat("ko-KR", {
      style: "currency",
      currency,
      currencyDisplay: "code",
      maximumFractionDigits: currency === "KRW" ? 0 : 2
    }).format(price);
  }
  return `${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2 }).format(price)}${currency ? ` ${currency}` : " · 단위 미제공"}`;
}
function changeLabel(changePct) {
  if (changePct === null) return "전 거래일 대비 미제공";
  if (changePct === 0) return "전 거래일 대비 0.00% · 보합";
  return `전 거래일 대비 ${changePct > 0 ? "+" : ""}${changePct.toFixed(2)}%`;
}
function freshnessLabel(freshness) {
  return freshness === "older" ? "이전 기준일 자료" : freshness === "unknown" ? "최신 거래일 여부 미확인" : "확인된 거래일 기준";
}
var CSS3 = `
.pcclose{--pcclose-bg:var(--ppm-bg,var(--bg));--pcclose-ink:var(--ppm-ink,var(--ink));--pcclose-muted:var(--ppm-muted,var(--muted));--pcclose-soft:var(--ppm-soft,var(--soft));--pcclose-accent:var(--ppm-accent,var(--accent));flex:none;width:100%;min-width:0;border-radius:10px;background:var(--pcclose-soft);color:var(--pcclose-ink);font:400 13px/1.5 Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;overflow:hidden;overflow-wrap:anywhere;word-break:break-word}
.pcclose *{box-sizing:border-box;min-width:0}.pcclose>summary{min-height:40px;padding:9px 10px;display:flex;align-items:center;gap:7px;cursor:pointer;list-style:none;font-size:13px;font-weight:500}.pcclose>summary::-webkit-details-marker{display:none}.pcclose>summary::marker{content:""}.pcclose-chevron{margin-left:auto;color:var(--pcclose-accent);font-size:15px;line-height:1;transform:rotate(-90deg);transition:transform .16s ease}.pcclose[open] .pcclose-chevron{transform:rotate(0)}.pcclose-body{display:grid;gap:7px;padding:0 9px 9px}.pcclose-price{margin:0;font-size:13px;font-weight:500}.pcclose-note{margin:0;color:var(--pcclose-muted);font-size:12px;font-weight:400;white-space:pre-wrap}.pcclose-meta{margin:0;display:grid;gap:4px}.pcclose-meta>div{display:grid;grid-template-columns:minmax(76px,.36fr) minmax(0,1fr);gap:8px;padding-top:4px;border-top:1px solid color-mix(in srgb,var(--pcclose-ink) 9%,transparent)}.pcclose-meta dt{color:var(--pcclose-muted);font-size:12px;font-weight:400}.pcclose-meta dd{margin:0;font-size:12px;font-weight:400;white-space:pre-wrap}
@media(max-width:390px){.pcclose>summary{padding:9px}.pcclose-body{padding:0 8px 8px}.pcclose-meta>div{grid-template-columns:minmax(68px,.34fr) minmax(0,1fr)}}
@media(prefers-reduced-motion:reduce){.pcclose-chevron{transition:none}}
`;
function PortfolioCloseDetails({ quote }) {
  const unavailable2 = !quote || quote.state === "unavailable";
  const reason = quote?.state === "unavailable" ? quote.reason : "";
  return /* @__PURE__ */ React4.createElement("details", { className: "pcclose" }, /* @__PURE__ */ React4.createElement("summary", null, /* @__PURE__ */ React4.createElement("span", null, "종가"), /* @__PURE__ */ React4.createElement("span", { className: "pcclose-chevron", "aria-hidden": "true" }, "⌄")), /* @__PURE__ */ React4.createElement("style", null, CSS3), /* @__PURE__ */ React4.createElement("div", { className: "pcclose-body" }, unavailable2 ? /* @__PURE__ */ React4.createElement("p", { className: "pcclose-note" }, "종가 정보 미제공", reason ? ` · ${reason}` : "") : /* @__PURE__ */ React4.createElement(React4.Fragment, null, /* @__PURE__ */ React4.createElement("p", { className: "pcclose-price" }, closePriceLabel(quote.price, quote.currency)), /* @__PURE__ */ React4.createElement("p", { className: "pcclose-note" }, changeLabel(quote.changePct)), /* @__PURE__ */ React4.createElement("dl", { className: "pcclose-meta" }, /* @__PURE__ */ React4.createElement("div", null, /* @__PURE__ */ React4.createElement("dt", null, "기준일"), /* @__PURE__ */ React4.createElement("dd", null, quote.priceDate || "미제공")), /* @__PURE__ */ React4.createElement("div", null, /* @__PURE__ */ React4.createElement("dt", null, "출처"), /* @__PURE__ */ React4.createElement("dd", null, quote.source || "미제공")), /* @__PURE__ */ React4.createElement("div", null, /* @__PURE__ */ React4.createElement("dt", null, "거래일 상태"), /* @__PURE__ */ React4.createElement("dd", null, freshnessLabel(quote.freshness))), quote.expectedDate ? /* @__PURE__ */ React4.createElement("div", null, /* @__PURE__ */ React4.createElement("dt", null, "확인된 마지막 거래일"), /* @__PURE__ */ React4.createElement("dd", null, quote.expectedDate)) : null, quote.basis ? /* @__PURE__ */ React4.createElement("div", null, /* @__PURE__ */ React4.createElement("dt", null, "가격 기준"), /* @__PURE__ */ React4.createElement("dd", null, quote.basis)) : null))));
}

// framer-components/public-probe/PortfolioSourceDetails.tsx
import * as React5 from "react";
function publishedAtLabel(kind) {
  return kind === "disclosure" ? "공시 접수일" : "기사 게시일";
}
function correctionLabel(value) {
  return value === true ? "정정 표시 있음" : value === false ? "정정 표시 없음" : "정정 여부 미제공";
}
function missingNewsTimezone(record6) {
  return record6.kind === "news" && /[T ]\d{2}:\d{2}/.test(record6.publishedAt || "") && !/(?:Z|[+-]\d{2}:?\d{2})$/.test(record6.publishedAt || "");
}
function backfillLabel(value) {
  return value === true ? "과거 자료를 나중에 수집 · 새 사건이라는 뜻은 아니에요" : value === false ? "과거 자료 후수집 표시 없음 · 새 자료라는 뜻은 아니에요" : "후수집 여부 미제공 · 실시간·신규 자료로 판단하지 않습니다.";
}
var CSS4 = `
.psd{--psd-bg:var(--ppm-bg,var(--bg));--psd-ink:var(--ppm-ink,var(--ink));--psd-muted:var(--ppm-muted,var(--muted));--psd-soft:var(--ppm-soft,var(--soft));--psd-accent:var(--ppm-accent,var(--accent));flex:none;width:100%;min-width:0;border-radius:10px;background:var(--psd-soft);color:var(--psd-ink);font:400 13px/1.5 Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;overflow:hidden;overflow-wrap:anywhere;word-break:break-word}
.psd *{box-sizing:border-box;min-width:0}.psd>summary{min-height:40px;padding:9px 10px;display:flex;align-items:center;gap:7px;cursor:pointer;list-style:none;font-size:13px;font-weight:500}.psd>summary::-webkit-details-marker{display:none}.psd>summary::marker{content:""}.psd-chevron{margin-left:auto;color:var(--psd-accent);font-size:15px;line-height:1;transform:rotate(-90deg);transition:transform .16s ease}.psd[open] .psd-chevron{transform:rotate(0)}
.psd-body{display:grid;gap:8px;padding:0 8px 8px}.psd-observed-note{margin:0;padding:8px;border-radius:8px;background:var(--psd-bg);color:var(--psd-muted);font-size:12px;font-weight:400;white-space:pre-wrap}.psd-list{margin:0;padding:0;display:grid;gap:8px;list-style:none}.psd-record{display:grid;gap:7px;padding:9px;border-radius:9px;background:var(--psd-bg)}.psd-head{display:flex;align-items:flex-start;gap:7px}.psd-kind{flex:none;padding:2px 5px;border-radius:999px;background:color-mix(in srgb,var(--psd-accent) 14%,var(--psd-bg));color:var(--psd-accent);font-size:12px;font-weight:500;white-space:nowrap}.psd-title{margin:0;font-size:13px;font-weight:500;white-space:pre-wrap}.psd-source{margin:0;color:var(--psd-muted);font-size:12px;font-weight:400;white-space:pre-wrap}
.psd-meta{margin:0;display:grid;gap:4px}.psd-meta>div{display:grid;grid-template-columns:minmax(92px,.42fr) minmax(0,1fr);gap:8px;padding-top:4px;border-top:1px solid color-mix(in srgb,var(--psd-ink) 9%,transparent)}.psd-meta dt{color:var(--psd-muted);font-size:12px;font-weight:400}.psd-meta dd{margin:0;font-size:12px;font-weight:400;white-space:pre-wrap}.psd-flag{margin:0;color:var(--psd-muted);font-size:12px;font-weight:400;white-space:pre-wrap}.psd-conflict{color:var(--psd-accent);font-weight:500}
@media(max-width:390px){.psd>summary{padding:9px}.psd-body{padding:0 6px 6px}.psd-record{padding:8px}.psd-meta>div{grid-template-columns:minmax(86px,.4fr) minmax(0,1fr)}}
@media(prefers-reduced-motion:reduce){.psd-chevron{transition:none}}
`;
function PortfolioSourceDetails({ records }) {
  if (!records?.length) return null;
  return /* @__PURE__ */ React5.createElement("details", { className: "psd" }, /* @__PURE__ */ React5.createElement("summary", null, /* @__PURE__ */ React5.createElement("span", null, "출처·날짜 자세히"), /* @__PURE__ */ React5.createElement("span", { className: "psd-chevron", "aria-hidden": "true" }, "⌄")), /* @__PURE__ */ React5.createElement("style", null, CSS4), /* @__PURE__ */ React5.createElement("div", { className: "psd-body" }, /* @__PURE__ */ React5.createElement("p", { className: "psd-observed-note" }, "수집 시각은 공시 접수일·기사 게시일·수정 시각이 아니며, 전체 시스템의 최초 관측 시각을 뜻하지 않습니다."), /* @__PURE__ */ React5.createElement("ol", { className: "psd-list" }, records.map((record6, index) => /* @__PURE__ */ React5.createElement("li", { className: "psd-record", key: `${record6.kind}:${record6.url}:${index}` }, /* @__PURE__ */ React5.createElement("div", { className: "psd-head" }, /* @__PURE__ */ React5.createElement("span", { className: "psd-kind" }, record6.kind === "disclosure" ? "공시" : "뉴스"), /* @__PURE__ */ React5.createElement("h4", { className: "psd-title" }, record6.title)), /* @__PURE__ */ React5.createElement("p", { className: "psd-source" }, record6.source), /* @__PURE__ */ React5.createElement("dl", { className: "psd-meta" }, /* @__PURE__ */ React5.createElement("div", null, /* @__PURE__ */ React5.createElement("dt", null, publishedAtLabel(record6.kind)), /* @__PURE__ */ React5.createElement("dd", null, record6.publishedAt || "미제공")), /* @__PURE__ */ React5.createElement("div", null, /* @__PURE__ */ React5.createElement("dt", null, "수집 시각"), /* @__PURE__ */ React5.createElement("dd", null, record6.observedAt || "미제공")), record6.receiptNumber ? /* @__PURE__ */ React5.createElement("div", null, /* @__PURE__ */ React5.createElement("dt", null, "접수번호"), /* @__PURE__ */ React5.createElement("dd", null, record6.receiptNumber)) : null, /* @__PURE__ */ React5.createElement("div", null, /* @__PURE__ */ React5.createElement("dt", null, "정정 여부"), /* @__PURE__ */ React5.createElement("dd", null, correctionLabel(record6.isCorrection)))), missingNewsTimezone(record6) ? /* @__PURE__ */ React5.createElement("p", { className: "psd-flag" }, "게시 시각의 시간대 표기가 없어요. 한국시간으로 단정하지 않습니다.") : null, record6.receiptConflict ? /* @__PURE__ */ React5.createElement("p", { className: "psd-flag psd-conflict" }, "식별자 불일치 · 확인이 필요합니다.") : null, /* @__PURE__ */ React5.createElement("p", { className: "psd-flag" }, backfillLabel(record6.isBackfill)))))));
}

// framer-components/public-probe/PortfolioMapTheme.tsx
import { useEffect as useEffect3, useState as useState3 } from "react";
var THEME_KEY = "verity_theme";
var THEME_EVENT = "alphanest-theme-preference";
function readPortfolioMapTheme({
  htmlTheme,
  bodyTheme,
  storedTheme
} = {}) {
  if (htmlTheme === "dark" || htmlTheme === "light") return htmlTheme;
  if (bodyTheme === "dark" || bodyTheme === "light") return bodyTheme;
  if (storedTheme === "dark" || storedTheme === "light") return storedTheme;
  return "light";
}
function browserThemeInput() {
  if (typeof window === "undefined" || typeof document === "undefined")
    return {};
  let storedTheme = null;
  try {
    storedTheme = window.localStorage.getItem(THEME_KEY);
  } catch {
  }
  return {
    htmlTheme: document.documentElement?.dataset.anTheme,
    bodyTheme: document.body?.dataset.framerTheme,
    storedTheme
  };
}
function usePortfolioMapTheme() {
  const [theme, setTheme] = useState3(
    () => readPortfolioMapTheme(browserThemeInput())
  );
  useEffect3(() => {
    if (typeof window === "undefined" || typeof document === "undefined")
      return;
    const sync = () => setTheme(readPortfolioMapTheme(browserThemeInput()));
    const observer = typeof MutationObserver === "undefined" ? null : new MutationObserver(sync);
    const onStorage = (event) => {
      if (!event.key || event.key === THEME_KEY) sync();
    };
    sync();
    observer?.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-an-theme"]
    });
    if (document.body) {
      observer?.observe(document.body, {
        attributes: true,
        attributeFilter: ["data-framer-theme"]
      });
    }
    window.addEventListener("storage", onStorage);
    window.addEventListener(THEME_EVENT, sync);
    return () => {
      observer?.disconnect();
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(THEME_EVENT, sync);
    };
  }, []);
  return theme;
}

// framer-components/public-probe/PortfolioReviewedFacts.tsx
var LIMITS = {
  holdings: 200,
  sources: 200,
  relationships: 200,
  events: 100,
  sourceIds: 20,
  participants: 50,
  id: 128,
  factId: 90,
  label: 160,
  prose: 2e3,
  url: 2048
};
var SOURCE_KEYS = ["id", "url", "publisher", "publishedAt", "statement"];
var RELATIONSHIP_KEYS = ["id", "from", "to", "label", "asOf", "status", "sourceIds", "limitations", "review", "impact"];
var EVENT_KEYS = ["id", "title", "date", "status", "participants", "sourceIds", "mergeBasis", "review", "impact"];
var ENTITY_KEYS = ["ticker", "market"];
var PARTICIPANT_KEYS = ["ticker", "market", "role", "sourceIds"];
var failure = (reason) => ({ ok: false, reason });
var record5 = (value) => value !== null && typeof value === "object" && !Array.isArray(value) ? value : null;
function exactRecord(value, keys) {
  const item = record5(value);
  if (!item) return null;
  const actual = Object.keys(item);
  return actual.length === keys.length && actual.every((key) => keys.includes(key)) ? item : null;
}
var text4 = (value, max) => {
  if (typeof value !== "string" || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value)) return null;
  const clean = value.trim();
  return clean && clean.length <= max ? clean : null;
};
var stableId = (value, max = LIMITS.id) => {
  const clean = text4(value, max);
  return clean && /^[A-Za-z0-9][A-Za-z0-9:._-]*$/.test(clean) ? clean : null;
};
function dateOnly2(value) {
  const raw = text4(value, 10), match = raw && /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw);
  if (!match || Number(match[1]) < 1900) return null;
  const time = Date.parse(raw + "T00:00:00Z");
  return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === raw ? raw : null;
}
function secureUrl(value) {
  const raw = text4(value, LIMITS.url);
  if (!raw) return null;
  try {
    const parsed = new URL(raw);
    return parsed.protocol === "https:" && !!parsed.hostname && !parsed.username && !parsed.password ? parsed.href : null;
  } catch {
    return null;
  }
}
function normalizeMarket(value) {
  if (typeof value !== "string") return null;
  const normalized = value.trim().toUpperCase();
  return normalized === "KR" || normalized === "US" ? normalized : null;
}
function normalizeTicker(value, market) {
  if (typeof value !== "string") return null;
  const normalized = value.trim().toUpperCase();
  if (market === "KR") return /^\d{6}$/.test(normalized) ? normalized : null;
  return normalized.length <= 15 && /^[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)*$/.test(normalized) ? normalized : null;
}
var entityKey = (entity) => `${entity.market}:${entity.ticker}`;
function parseEntity(value, exactKeys = ENTITY_KEYS) {
  const item = exactRecord(value, exactKeys), market = item && normalizeMarket(item.market);
  if (!item || !market || item.market !== market) return null;
  const ticker = normalizeTicker(item.ticker, market);
  return ticker && item.ticker === ticker ? { ticker, market } : null;
}
function parseIdList(value, sourceIds, path, minimum = 1) {
  if (!Array.isArray(value) || value.length < minimum || value.length > LIMITS.sourceIds) return failure(path);
  const result = [], seen = /* @__PURE__ */ new Set();
  for (const candidate of value) {
    const id = stableId(candidate);
    if (!id || seen.has(id) || !sourceIds.has(id)) return failure(path);
    seen.add(id);
    result.push(id);
  }
  return { ok: true, value: result };
}
function parseHoldings(value) {
  if (!Array.isArray(value) || value.length > LIMITS.holdings) return failure("holdings.shape");
  const result = [], seen = /* @__PURE__ */ new Set();
  for (let index = 0; index < value.length; index++) {
    const item = exactRecord(value[index], ENTITY_KEYS), market = item && normalizeMarket(item.market);
    const ticker = market && item ? normalizeTicker(item.ticker, market) : null;
    if (!item || !market || !ticker) return failure(`holdings[${index}]`);
    const entity = { ticker, market }, key = entityKey(entity);
    if (seen.has(key)) return failure(`holdings[${index}].duplicate`);
    seen.add(key);
    result.push(entity);
  }
  return { ok: true, value: result };
}
function parseRegistry(value) {
  const registry = exactRecord(value, ["schemaVersion", "reviewedAt", "sources", "relationships", "events"]);
  if (!registry || registry.schemaVersion !== 1) return failure("registry.schemaVersion");
  const reviewedAt = dateOnly2(registry.reviewedAt);
  if (!reviewedAt) return failure("registry.reviewedAt");
  if (!Array.isArray(registry.sources) || registry.sources.length > LIMITS.sources) return failure("registry.sources");
  if (!Array.isArray(registry.relationships) || registry.relationships.length > LIMITS.relationships) return failure("registry.relationships");
  if (!Array.isArray(registry.events) || registry.events.length > LIMITS.events) return failure("registry.events");
  const sources = [], sourceIds = /* @__PURE__ */ new Set(), allIds = /* @__PURE__ */ new Set();
  for (let index = 0; index < registry.sources.length; index++) {
    const item = exactRecord(registry.sources[index], SOURCE_KEYS);
    const id = item && stableId(item.id), url = item && secureUrl(item.url);
    const publisher = item && text4(item.publisher, LIMITS.label), publishedAt = item && dateOnly2(item.publishedAt);
    const statement = item && text4(item.statement, LIMITS.prose);
    if (!item || !id || !url || !publisher || !publishedAt || publishedAt > reviewedAt || !statement || allIds.has(id))
      return failure(`registry.sources[${index}]`);
    sourceIds.add(id);
    allIds.add(id);
    sources.push({ id, url, publisher, publishedAt, statement });
  }
  const relationships = [];
  for (let index = 0; index < registry.relationships.length; index++) {
    const item = exactRecord(registry.relationships[index], RELATIONSHIP_KEYS);
    const id = item && stableId(item.id, LIMITS.factId), from = item && parseEntity(item.from), to = item && parseEntity(item.to);
    const label2 = item && text4(item.label, LIMITS.label), asOf = item && dateOnly2(item.asOf);
    const limitations = item && text4(item.limitations, LIMITS.prose);
    const refs = item ? parseIdList(item.sourceIds, sourceIds, `registry.relationships[${index}].sourceIds`, 2) : failure("relationship");
    if (!item || !id || !from || !to || entityKey(from) === entityKey(to) || !label2 || !asOf || asOf > reviewedAt || !limitations || !refs.ok || !["historical-announcement", "dated-fact"].includes(item.status) || item.review !== "manual-primary-source-comparison" || item.impact !== "unknown" || allIds.has(id))
      return failure(`registry.relationships[${index}]`);
    allIds.add(id);
    relationships.push({
      id,
      from,
      to,
      label: label2,
      asOf,
      status: item.status,
      sourceIds: refs.value,
      limitations,
      review: "manual-primary-source-comparison",
      impact: "unknown"
    });
  }
  const events = [];
  for (let index = 0; index < registry.events.length; index++) {
    const item = exactRecord(registry.events[index], EVENT_KEYS);
    const id = item && stableId(item.id, LIMITS.factId), title = item && text4(item.title, LIMITS.label);
    const date = item && dateOnly2(item.date), mergeBasis = item && text4(item.mergeBasis, LIMITS.prose);
    const refs = item ? parseIdList(item.sourceIds, sourceIds, `registry.events[${index}].sourceIds`, 2) : failure("event");
    if (!item || !id || !title || !date || date > reviewedAt || !mergeBasis || !refs.ok || item.status !== "historical-announcement" || item.review !== "manual-primary-source-comparison" || item.impact !== "unknown" || allIds.has(id) || !Array.isArray(item.participants) || item.participants.length < 2 || item.participants.length > LIMITS.participants)
      return failure(`registry.events[${index}]`);
    const allowedRefs = new Set(refs.value), participants = [], participantIds = /* @__PURE__ */ new Set();
    for (let participantIndex = 0; participantIndex < item.participants.length; participantIndex++) {
      const participant = exactRecord(item.participants[participantIndex], PARTICIPANT_KEYS);
      const entity = participant && parseEntity({ ticker: participant.ticker, market: participant.market });
      const role = participant && text4(participant.role, LIMITS.label);
      const participantRefs = participant ? parseIdList(
        participant.sourceIds,
        allowedRefs,
        `registry.events[${index}].participants[${participantIndex}].sourceIds`
      ) : failure("participant");
      if (!participant || !entity || !role || !participantRefs.ok || participantIds.has(entityKey(entity)))
        return failure(`registry.events[${index}].participants[${participantIndex}]`);
      participantIds.add(entityKey(entity));
      participants.push({ ...entity, role, sourceIds: participantRefs.value });
    }
    allIds.add(id);
    events.push({
      id,
      title,
      date,
      status: "historical-announcement",
      participants,
      sourceIds: refs.value,
      mergeBasis,
      review: "manual-primary-source-comparison",
      impact: "unknown"
    });
  }
  return { ok: true, value: { schemaVersion: 1, reviewedAt, sources, relationships, events } };
}
function unavailable(status, reason, provided, eligible = 0) {
  return { relationships: [], events: [], coverage: {
    status,
    reason,
    reviewedAt: null,
    holdings: { provided, eligible, matched: 0 },
    sources: { reviewed: 0 },
    relationships: { reviewed: 0, included: 0 },
    events: { reviewed: 0, included: 0 }
  } };
}
function buildReviewedPortfolioFacts(holdings, registry) {
  const parsedHoldings = parseHoldings(holdings);
  const provided = Array.isArray(holdings) ? holdings.length : 0;
  if (!parsedHoldings.ok) return unavailable("invalid-holdings", parsedHoldings.reason, provided);
  const parsedRegistry = parseRegistry(registry);
  if (!parsedRegistry.ok) return unavailable("invalid-registry", parsedRegistry.reason, provided, parsedHoldings.value.length);
  const valid = parsedRegistry.value, holdingKeys = new Set(parsedHoldings.value.map(entityKey));
  const sourcesById = new Map(valid.sources.map((source) => [source.id, source]));
  const matchedKeys = /* @__PURE__ */ new Set();
  const relationships = [];
  for (const relationship of valid.relationships) {
    if (!holdingKeys.has(entityKey(relationship.from)) || !holdingKeys.has(entityKey(relationship.to))) continue;
    matchedKeys.add(entityKey(relationship.from));
    matchedKeys.add(entityKey(relationship.to));
    relationships.push({
      ...relationship,
      from: { ...relationship.from },
      to: { ...relationship.to },
      sourceIds: [...relationship.sourceIds],
      sources: relationship.sourceIds.map((id) => ({ ...sourcesById.get(id) }))
    });
  }
  const events = [];
  for (const event of valid.events) {
    const matchedHoldings = event.participants.filter((participant) => holdingKeys.has(entityKey(participant))).map(({ ticker, market }) => ({ ticker, market }));
    if (matchedHoldings.length < 2) continue;
    matchedHoldings.forEach((entity) => matchedKeys.add(entityKey(entity)));
    events.push({
      ...event,
      participants: event.participants.map((participant) => ({ ...participant, sourceIds: [...participant.sourceIds] })),
      matchedHoldings,
      sourceIds: [...event.sourceIds],
      sources: event.sourceIds.map((id) => ({ ...sourcesById.get(id) }))
    });
  }
  const status = relationships.length || events.length ? "available" : "empty";
  return { relationships, events, coverage: {
    status,
    reason: status === "empty" ? "no-held-reviewed-facts" : null,
    reviewedAt: valid.reviewedAt,
    holdings: { provided, eligible: parsedHoldings.value.length, matched: matchedKeys.size },
    sources: { reviewed: valid.sources.length },
    relationships: { reviewed: valid.relationships.length, included: relationships.length },
    events: { reviewed: valid.events.length, included: events.length }
  } };
}

// framer-components/public-probe/PortfolioReviewedRegistry.tsx
var portfolioReviewedRegistry = {
  schemaVersion: 1,
  reviewedAt: "2026-09-29",
  sources: [
    {
      id: "nvda-intc-nvidia",
      publisher: "NVIDIA",
      publishedAt: "2025-09-18",
      url: "https://nvidianews.nvidia.com/news/nvidia-and-intel-to-develop-ai-infrastructure-and-personal-computing-products",
      statement: "NVIDIA와 Intel이 데이터센터·PC 제품 공동개발 계획을 발표했다. Intel은 맞춤형 x86 CPU와 RTX GPU 칩렛 통합 제품을 개발할 예정이라고 밝혔다."
    },
    {
      id: "nvda-intc-intel",
      publisher: "Intel",
      publishedAt: "2025-09-18",
      url: "https://www.intel.com/content/www/us/en/newsroom/news/artificial-intelligence/intel-and-nvidia-to-jointly-develop-ai-infrastructure-and-personal-computing-products.html",
      statement: "Intel도 같은 날짜에 같은 참여 기업과 데이터센터·PC 공동개발 계획을 발표했다. 당시 투자 계획은 별도 종결 조건이 있는 미래 계획이었다."
    },
    {
      id: "nvda-tsmc-production",
      publisher: "NVIDIA",
      publishedAt: "2025-04-14",
      url: "https://blogs.nvidia.com/blog/nvidia-manufacture-american-made-ai-supercomputers-us/",
      statement: "NVIDIA는 TSMC의 미국 피닉스 공장에서 Blackwell 칩 생산이 시작됐다고 발표했다."
    },
    {
      id: "tsmc-customer",
      publisher: "TSMC",
      publishedAt: "2025-03-04",
      url: "https://pr.tsmc.com/english/news/3210",
      statement: "TSMC는 미국 투자 확대 발표에서 NVIDIA를 자사의 주요 고객 중 하나로 명시했다. 4월의 생산 발표와는 별도 사건이다."
    },
    {
      id: "skh-tsmc-hbm4-ko",
      publisher: "SK하이닉스 · 한국어",
      publishedAt: "2024-04-19",
      url: "https://news.skhynix.co.kr/skhynix-tsmc-hbm4-mou/",
      statement: "SK하이닉스는 TSMC와 기술 협력 양해각서(MOU)를 체결했다고 발표했다. HBM4 개발과 HBM·CoWoS 패키징(칩 결합) 최적화 협력 계획이며, 현재 양산 실적을 확인하는 자료는 아니다."
    },
    {
      id: "skh-tsmc-hbm4-en",
      publisher: "SK하이닉스 · 영어",
      publishedAt: "2024-04-19",
      url: "https://news.skhynix.com/en/sk-hynix-partners-with-tsmc-to-strengthen-hbm-technological-leadership/",
      statement: "같은 발표의 영문본도 HBM4의 하단 제어 칩에 TSMC 공정을 활용하고 HBM·CoWoS 결합을 최적화할 계획을 설명한다. 한국어본과 같은 발행사의 자료로 독립 확인은 아니다."
    },
    {
      id: "tsmc-skh-memory-partner",
      publisher: "TSMC",
      publishedAt: "2023-09-28",
      url: "https://pr.tsmc.com/english/news/3070",
      statement: "TSMC는 SK하이닉스를 HBM3·HBM3e 협력 메모리 파트너로 명시했다. 본문 행사일은 미국 현지 2023-09-27, 사이트 발행일은 09-28이다. 2024년 HBM4 양해각서와는 별도 발표다."
    }
  ],
  relationships: [
    {
      id: "relation:nvda-intc-collaboration-20250918",
      from: { ticker: "NVDA", market: "US" },
      to: { ticker: "INTC", market: "US" },
      label: "제품 공동개발 발표",
      asOf: "2025-09-18",
      status: "historical-announcement",
      sourceIds: ["nvda-intc-nvidia", "nvda-intc-intel"],
      review: "manual-primary-source-comparison",
      impact: "unknown",
      limitations: "두 회사의 당시 공동개발 발표를 확인했다. 현재 제품 출시·매출 효과·지분 보유 상태는 이 자료만으로 확인하지 않았다."
    },
    {
      id: "relation:tsmc-nvda-manufacturing-20250414",
      from: { ticker: "TSM", market: "US" },
      to: { ticker: "NVDA", market: "US" },
      label: "칩 생산·고객 관계",
      asOf: "2025-04-14",
      status: "dated-fact",
      sourceIds: ["nvda-tsmc-production", "tsmc-customer"],
      review: "manual-primary-source-comparison",
      impact: "unknown",
      limitations: "당시 생산 발표와 고객 관계를 확인했다. 두 발표는 서로 다른 사건이며, 현재 공급량·매출 비중·주가 영향은 확인하지 않았다."
    },
    {
      id: "relation:skh-tsmc-hbm-collaboration-20240419",
      from: { ticker: "000660", market: "KR" },
      to: { ticker: "TSM", market: "US" },
      label: "HBM 기술 협력",
      asOf: "2024-04-19",
      status: "historical-announcement",
      sourceIds: ["skh-tsmc-hbm4-ko", "tsmc-skh-memory-partner"],
      review: "manual-primary-source-comparison",
      impact: "unknown",
      limitations: "양사의 서로 다른 시점 원문으로 HBM 협력 관계를 확인했다. 2023년 파트너 발표와 2024년 HBM4 협력 계획은 별도 사건이다. 현재 양산·공급량·매출·주가 영향은 확인하지 않았다."
    }
  ],
  events: [
    {
      id: "event:nvda-intc-collaboration-20250918",
      title: "NVIDIA·Intel 제품 공동개발 발표",
      date: "2025-09-18",
      status: "historical-announcement",
      sourceIds: ["nvda-intc-nvidia", "nvda-intc-intel"],
      participants: [
        { ticker: "NVDA", market: "US", role: "공동개발 참여 · AI 기반 시스템·GPU 기술", sourceIds: ["nvda-intc-nvidia", "nvda-intc-intel"] },
        { ticker: "INTC", market: "US", role: "공동개발 참여 · 맞춤형 x86 CPU 개발 계획", sourceIds: ["nvda-intc-nvidia", "nvda-intc-intel"] }
      ],
      mergeBasis: "양사의 2025-09-18 원문에서 참여 기업·발표일·공동개발 대상이 일치한다. 같은 공동 발표의 두 게재본이며 독립적인 성과 검증은 아니다. TSMC 관련 발표는 합치지 않았다.",
      review: "manual-primary-source-comparison",
      impact: "unknown"
    },
    {
      id: "event:skh-tsmc-hbm4-mou-20240419",
      title: "SK하이닉스·TSMC HBM4 협력 발표",
      date: "2024-04-19",
      status: "historical-announcement",
      sourceIds: ["skh-tsmc-hbm4-ko", "skh-tsmc-hbm4-en"],
      participants: [
        { ticker: "000660", market: "KR", role: "HBM4 메모리 개발 · TSMC 공정 활용 계획", sourceIds: ["skh-tsmc-hbm4-ko", "skh-tsmc-hbm4-en"] },
        { ticker: "TSM", market: "US", role: "제어 칩 공정·칩 결합 기술 협력 계획", sourceIds: ["skh-tsmc-hbm4-ko", "skh-tsmc-hbm4-en"] }
      ],
      mergeBasis: "같은 SK하이닉스 발표의 한국어·영어본에서 참여 기업·발표일·협력 대상이 일치해 사건 하나로 묶었다. 독립된 두 기관의 확인은 아니다. 2023년 TSMC 파트너 발표는 합치지 않았다. 당시 계획이며 현재 양산 성과는 확인하지 않았다.",
      review: "manual-primary-source-comparison",
      impact: "unknown"
    }
  ]
};

// framer-components/public-probe/PortfolioReviewedView.tsx
import * as React6 from "react";
var entityKey2 = (entity) => `${entity.market}:${entity.ticker}`;
var reviewedCompanyNodeId = (entity) => `company:${entity.ticker}`;
var reviewedFactNodeId = (mode, id) => `reviewed:${mode}:${id}`;
function buildPortfolioReviewedCanvasView(facts, mode, holdings) {
  const nodes = holdings.map((holding, index) => ({
    id: reviewedCompanyNodeId(holding),
    kind: "company",
    title: holding.name,
    subtitle: holding.ticker,
    semanticLabel: `보유 종목: ${holding.name}. ${holding.market} ${holding.ticker}`,
    x: index % 2 * 180,
    y: Math.floor(index / 2) * 86
  }));
  const links = [];
  const factIdsByNode = /* @__PURE__ */ new Map(), factIdsByLink = /* @__PURE__ */ new Map();
  if (mode === "relationships") {
    facts.relationships.forEach((relationship, index) => {
      const nodeId = reviewedFactNodeId(mode, relationship.id);
      nodes.push({
        id: nodeId,
        kind: "document",
        title: relationship.label,
        sourceKind: "other",
        subtitle: `${relationship.asOf} · ${relationship.status === "historical-announcement" ? "당시 발표" : "해당 날짜에 확인"} · 영향 미확인`,
        semanticLabel: `확인된 관계: ${relationship.label}. 기준일 ${relationship.asOf}. 영향 미확인`,
        x: 470 + index % 3 * 180,
        y: Math.floor(index / 3) * 86
      });
      factIdsByNode.set(nodeId, relationship.id);
      for (const endpoint of [relationship.from, relationship.to]) {
        const id = `reviewed-link:${relationship.id}:${entityKey2(endpoint)}`;
        links.push({
          id,
          companyId: reviewedCompanyNodeId(endpoint),
          documentId: nodeId,
          confirmation: "confirmed",
          label: `${relationship.label} · 연결 기업`
        });
        factIdsByLink.set(id, relationship.id);
      }
    });
  } else {
    facts.events.forEach((event, index) => {
      const nodeId = reviewedFactNodeId(mode, event.id);
      nodes.push({
        id: nodeId,
        kind: "document",
        title: event.title,
        sourceKind: "other",
        subtitle: `${event.date} · 당시 발표 · 보유 참여 ${event.matchedHoldings.length}/${event.participants.length}`,
        semanticLabel: `공통 사건: ${event.title}. 발표일 ${event.date}. 영향 미확인`,
        x: 470 + index % 3 * 180,
        y: Math.floor(index / 3) * 86
      });
      factIdsByNode.set(nodeId, event.id);
      const participants = new Map(event.participants.map((participant) => [entityKey2(participant), participant]));
      for (const holding of event.matchedHoldings) {
        const participant = participants.get(entityKey2(holding));
        const id = `reviewed-link:${event.id}:${entityKey2(holding)}`;
        links.push({
          id,
          companyId: reviewedCompanyNodeId(holding),
          documentId: nodeId,
          confirmation: "confirmed",
          label: `${event.title} · ${participant.role}`
        });
        factIdsByLink.set(id, event.id);
      }
    });
  }
  return { nodes, links, factIdsByNode, factIdsByLink };
}
function selectedReviewedFact(facts, mode, factId) {
  if (!factId) return void 0;
  return mode === "relationships" ? facts.relationships.find((fact) => fact.id === factId) : facts.events.find((fact) => fact.id === factId);
}
function reviewedCoverageMessage(facts) {
  const coverage = facts.coverage;
  if (coverage.status === "invalid-registry" || coverage.status === "invalid-holdings")
    return `검토 자료를 사용할 수 없어 확인된 항목을 표시하지 않습니다. (${coverage.reason || "형식 확인 필요"})`;
  if (!facts.relationships.length && !facts.events.length)
    return "현재 보유 선택에 맞는 검토 완료 항목이 0건입니다. 관계나 공통 사건이 없다는 뜻이 아니며, 검수 대상 밖일 수 있습니다.";
  return `검수 범위 · ${coverage.reviewedAt || "검토일 미제공"} · 공식 원문 ${coverage.sources.reviewed}개 · 관계 ${coverage.relationships.included}/${coverage.relationships.reviewed} · 공통 사건 ${coverage.events.included}/${coverage.events.reviewed}. 전체 시장이나 보유 관계 전수조사가 아닙니다.`;
}
var statusLabel = (status) => status === "historical-announcement" ? "당시 발표" : "해당 날짜에 확인";
var entityLabel = (entity) => `${entity.market} ${entity.ticker}`;
function PortfolioReviewedView({ fact }) {
  const relationship = "from" in fact ? fact : null;
  const event = "participants" in fact ? fact : null;
  return /* @__PURE__ */ React6.createElement("div", { className: "ppm-reviewed" }, /* @__PURE__ */ React6.createElement("p", null, relationship ? `${entityLabel(relationship.from)} ↔ ${entityLabel(relationship.to)}` : event.title), /* @__PURE__ */ React6.createElement("small", null, statusLabel(fact.status), " · ", relationship ? relationship.asOf : event.date, " · 수익·강도·현재 영향 미확인"), relationship ? /* @__PURE__ */ React6.createElement("article", { className: "ppm-evidence" }, /* @__PURE__ */ React6.createElement("h4", null, "확인 범위와 한계"), /* @__PURE__ */ React6.createElement("p", null, relationship.limitations)) : null, event ? /* @__PURE__ */ React6.createElement(React6.Fragment, null, /* @__PURE__ */ React6.createElement("article", { className: "ppm-evidence" }, /* @__PURE__ */ React6.createElement("h4", null, "참여 역할"), event.participants.map((participant) => /* @__PURE__ */ React6.createElement("p", { key: entityKey2(participant) }, /* @__PURE__ */ React6.createElement("strong", null, entityLabel(participant)), " · ", participant.role))), /* @__PURE__ */ React6.createElement("article", { className: "ppm-evidence" }, /* @__PURE__ */ React6.createElement("h4", null, "묶은 근거"), /* @__PURE__ */ React6.createElement("p", null, event.mergeBasis))) : null, /* @__PURE__ */ React6.createElement("div", { className: "ppm-evidence" }, /* @__PURE__ */ React6.createElement("h4", null, "검토 원문"), fact.sources.map((source) => /* @__PURE__ */ React6.createElement("div", { key: source.id }, /* @__PURE__ */ React6.createElement("small", null, source.publisher, " · 원문 날짜 ", source.publishedAt), /* @__PURE__ */ React6.createElement("p", null, source.statement), /* @__PURE__ */ React6.createElement("a", { href: source.url, target: "_blank", rel: "noopener noreferrer" }, "공식 원문 열기")))), /* @__PURE__ */ React6.createElement("small", null, "수동 원문 대조 · 영향 미확인 · 현재 상태나 인과·수익을 추정하지 않습니다."));
}

// framer-components/public-probe/PortfolioHoldingsList.tsx
import * as React7 from "react";
var quantity = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 8 });
var won = new Intl.NumberFormat("ko-KR", { style: "currency", currency: "KRW", maximumFractionDigits: 0 });
var dollar = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 4 });
function formatHoldingQuantity(value) {
  if (value === null) return "확인 필요";
  return value < 1e-8 ? "0.00000001 미만" : quantity.format(value);
}
function formatHoldingAverageCost(holding) {
  if (holding.duplicate) return "중복 행 확인 필요";
  if (holding.avg_cost === null) return "확인 필요";
  if (holding.market === "KR" && holding.avg_cost < 1) return "1 KRW 미만";
  if (holding.market === "US" && holding.avg_cost < 1e-4) return "0.0001 USD 미만";
  return holding.market === "KR" ? `${won.format(holding.avg_cost)} KRW` : `${dollar.format(holding.avg_cost)} USD`;
}
var CSS5 = `
.phl{--panel:#fff;--ink:#191f28;--muted:#4e5968;--soft:#f0edff;--divider:#e5e8eb;--accent:#6c5ce7;background:var(--panel);color:var(--ink);font:600 13px/1.55 Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;padding:16px;min-width:0}
.phl *{box-sizing:border-box}.phl h3,.phl p{margin:0}.phl h3{font-size:16px;font-weight:800;letter-spacing:-.2px}.phl-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:12px}.phl-head p{color:var(--muted);font-weight:600}.phl-count{white-space:nowrap;font-weight:700;color:var(--accent)}
.phl-table-wrap{overflow:auto;border:1px solid var(--divider);border-radius:12px}.phl table{width:100%;border-collapse:collapse;min-width:650px}.phl th,.phl td{padding:11px 12px;text-align:left;border-bottom:1px solid var(--divider);font-weight:600}.phl th{background:color-mix(in srgb,var(--soft) 56%,var(--panel));font-weight:700;color:var(--muted);white-space:nowrap}.phl tbody tr:last-child td{border-bottom:0}.phl-company{display:grid;gap:2px}.phl-company strong{font-weight:700}.phl-company span,.phl-note{color:var(--muted);font-weight:600}.phl-map-state{display:inline-flex;border-radius:999px;padding:4px 8px;background:var(--soft);color:var(--accent);font-weight:700;white-space:nowrap}.phl-map-state[data-visible=false]{background:color-mix(in srgb,var(--muted) 10%,var(--panel));color:var(--muted)}.phl-empty{padding:28px 16px;text-align:center;color:var(--muted)}.phl-note{margin-top:10px}
.phl[data-theme=dark]{--panel:#171c23;--ink:#e3e7ec;--muted:#9aa4b1;--soft:#241f3a;--divider:#3c4350;--accent:#a99bff}
@media(max-width:720px){.phl{padding:12px}.phl-head{flex-direction:column}.phl th,.phl td{padding:10px}}
`;
function emptyHoldingsMessage(phase) {
  if (phase === "loading") return "보유종목을 불러오는 중…";
  if (phase === "error") return "보유종목을 불러오지 못해 목록을 확인할 수 없습니다.";
  if (phase === "signed-out") return "로그인한 뒤 보유종목 목록을 확인할 수 있습니다.";
  return "표시할 보유종목이 없습니다.";
}
function PortfolioHoldingsList({ holdings, selectedTickers, unsupportedCount = 0, phase, theme }) {
  const selected = React7.useMemo(() => new Set(selectedTickers), [selectedTickers]);
  const known = phase === "ready" || phase === "choose-stocks";
  return /* @__PURE__ */ React7.createElement("section", { className: "phl", "data-theme": theme, "aria-label": "국내 미국 지원 보유종목 목록" }, /* @__PURE__ */ React7.createElement("style", null, CSS5), /* @__PURE__ */ React7.createElement("header", { className: "phl-head" }, /* @__PURE__ */ React7.createElement("div", null, /* @__PURE__ */ React7.createElement("h3", null, "보유 목록"), /* @__PURE__ */ React7.createElement("p", null, "불러온 국내·미국 지원 종목 목록입니다. 지도에는 이 중 최대 30종목을 표시합니다.")), known ? /* @__PURE__ */ React7.createElement("span", { className: "phl-count" }, "지원 ", holdings.length, "종목 · 제외 ", unsupportedCount, "개") : null), /* @__PURE__ */ React7.createElement("div", { className: "phl-table-wrap" }, /* @__PURE__ */ React7.createElement("table", null, /* @__PURE__ */ React7.createElement("thead", null, /* @__PURE__ */ React7.createElement("tr", null, /* @__PURE__ */ React7.createElement("th", { scope: "col" }, "종목"), /* @__PURE__ */ React7.createElement("th", { scope: "col" }, "시장"), /* @__PURE__ */ React7.createElement("th", { scope: "col" }, "수량"), /* @__PURE__ */ React7.createElement("th", { scope: "col" }, "평균 매수가"), /* @__PURE__ */ React7.createElement("th", { scope: "col" }, "현재 지도"))), /* @__PURE__ */ React7.createElement("tbody", null, holdings.map((holding) => /* @__PURE__ */ React7.createElement("tr", { key: `${holding.market}:${holding.ticker}` }, /* @__PURE__ */ React7.createElement("td", null, /* @__PURE__ */ React7.createElement("span", { className: "phl-company" }, /* @__PURE__ */ React7.createElement("strong", null, holding.name), /* @__PURE__ */ React7.createElement("span", null, holding.ticker))), /* @__PURE__ */ React7.createElement("td", null, holding.market), /* @__PURE__ */ React7.createElement("td", null, holding.duplicate ? "중복 행 확인 필요" : formatHoldingQuantity(holding.shares)), /* @__PURE__ */ React7.createElement("td", null, formatHoldingAverageCost(holding)), /* @__PURE__ */ React7.createElement("td", null, /* @__PURE__ */ React7.createElement("span", { className: "phl-map-state", "data-visible": selected.has(holding.ticker) }, selected.has(holding.ticker) ? "표시 중" : "미표시")))))), !holdings.length ? /* @__PURE__ */ React7.createElement("p", { className: "phl-empty", role: "status" }, emptyHoldingsMessage(phase)) : null), unsupportedCount ? /* @__PURE__ */ React7.createElement("p", { className: "phl-note" }, "지도 자료 조회를 지원하지 않는 보유 항목 ", unsupportedCount, "개는 이 목록의 종목 정보에 포함되지 않습니다.") : null);
}

// framer-components/public-probe/PortfolioReviewedState.tsx
var MAX_REVISION2 = Number.MAX_SAFE_INTEGER;
var FNV_OFFSET = 1469598103934665603n;
var FNV_PRIME = 1099511628211n;
var UINT64_MASK = (1n << 64n) - 1n;
var compareCanonical = (left, right) => {
  const a = JSON.stringify(left), b = JSON.stringify(right);
  return a < b ? -1 : a > b ? 1 : 0;
};
var sortedIds = (ids) => [...ids].sort();
var sourceValue = (source) => [
  source.id,
  source.url,
  source.publisher,
  source.publishedAt,
  source.statement
];
var sortedSources = (sources) => sources.map(sourceValue).sort(compareCanonical);
function relationshipValue(fact) {
  return [
    "relationships",
    [fact.from.market, fact.from.ticker],
    [fact.to.market, fact.to.ticker],
    fact.label,
    fact.asOf,
    fact.status,
    fact.limitations,
    fact.review,
    fact.impact,
    sortedIds(fact.sourceIds),
    sortedSources(fact.sources)
  ];
}
function eventValue(fact) {
  const participants = fact.participants.map((participant) => [
    participant.market,
    participant.ticker,
    participant.role,
    sortedIds(participant.sourceIds)
  ]).sort(compareCanonical);
  return [
    "events",
    fact.title,
    fact.date,
    fact.status,
    participants,
    fact.mergeBasis,
    fact.review,
    fact.impact,
    sortedIds(fact.sourceIds),
    sortedSources(fact.sources)
  ];
}
function revision(value) {
  const canonical = JSON.stringify(value);
  let hash = FNV_OFFSET;
  for (let index = 0; index < canonical.length; index++) {
    hash ^= BigInt(canonical.charCodeAt(index));
    hash = hash * FNV_PRIME & UINT64_MASK;
  }
  return Number(hash % BigInt(MAX_REVISION2 - 1) + 1n);
}
function reviewedRecord(mode, fact) {
  const relationship = "from" in fact;
  if (mode === "relationships" !== relationship) throw new Error("reviewed-mode-mismatch");
  return {
    id: `reviewed:${mode}:${fact.id}`,
    read_revision: revision(relationship ? relationshipValue(fact) : eventValue(fact))
  };
}
function withReviewedMark(layout, mode, fact, change) {
  if (!validMapDocument({ layouts: [layout] })) throw new Error("invalid-layout");
  const allowed = /* @__PURE__ */ new Set(["read", "important", "disposition"]);
  if (Object.keys(change).some((key) => !allowed.has(key))) throw new Error("invalid-reviewed-mark-change");
  if (change.read !== void 0 && typeof change.read !== "boolean") throw new Error("invalid-reviewed-mark-change");
  const record6 = reviewedRecord(mode, fact);
  const exists = Object.hasOwn(layout.marks, record6.id);
  if (!exists && Object.keys(layout.marks).length >= 200) throw new Error("reviewed-marks-limit");
  const prior = layout.marks[record6.id] || { read_revision: null, important: false, disposition: "inbox" };
  const mark = {
    read_revision: change.read === void 0 ? prior.read_revision : change.read ? record6.read_revision : null,
    important: change.important ?? prior.important,
    disposition: change.disposition ?? prior.disposition
  };
  const next = { ...layout, marks: { ...layout.marks, [record6.id]: mark } };
  if (!validMapDocument({ layouts: [next] })) throw new Error("invalid-reviewed-mark");
  return next;
}

// framer-components/public-probe/PublicPortfolioMap.tsx
var MAP_KEY2 = "main";
var LIMIT2 = 1e6;
var blank = {
  phase: "signed-out",
  holdings: [],
  unsupportedCount: 0,
  selectedTickers: [],
  graph: null,
  privateState: { phase: "signed-out", document: null, revision: null, dirty: false, error: null },
  error: null
};
var baseLayout = () => ({ map_key: MAP_KEY2, positions: [], notes: [], marks: {} });
var bound = (value) => Math.max(-LIMIT2, Math.min(LIMIT2, value));
var Chev = () => /* @__PURE__ */ React8.createElement("svg", { width: "12", height: "12", viewBox: "0 0 12 12", "aria-hidden": "true" }, /* @__PURE__ */ React8.createElement("path", { d: "m4 2 4 4-4 4", fill: "none", stroke: "currentColor", strokeWidth: "1.5" }));
function holdingsSummaryState(state) {
  if (state.phase === "ready" || state.phase === "choose-stocks") return { known: true, message: "" };
  if (state.phase === "loading") return { known: false, message: "보유종목 불러오는 중…" };
  if (state.phase === "error") return { known: false, message: "보유종목·지도 자료 확인 실패" };
  return { known: false, message: "보유종목 확인은 로그인이 필요합니다." };
}
function editableMap(state) {
  return state.phase === "ready" && !!state.privateState.document && state.privateState.revision !== null && ["ready", "saving"].includes(state.privateState.phase);
}
function canSaveMap(state) {
  return state.phase === "ready" && !!state.privateState.document && state.privateState.revision !== null && state.privateState.dirty && ["ready", "error"].includes(state.privateState.phase);
}
function reviewRecordsKnown(state) {
  return state.phase === "ready" && !!state.privateState.document && state.privateState.revision !== null && !["loading", "signed-out"].includes(state.privateState.phase);
}
function matchesSource(doc, filters) {
  return (filters.source === "all" || doc.evidence.some((e) => e.kind === filters.source || e.sourceRecords?.some((source) => source.kind === filters.source))) && (!filters.common || doc.tickers.length >= 2);
}
function mapReviewSummary(graph, layout, filters, known) {
  if (!graph || !known) return null;
  const summary = { unread: 0, changed: 0, read: 0, ignored: 0, total: 0, pending: 0 };
  for (const doc of graph.documents) {
    if (!matchesSource(doc, filters)) continue;
    summary.total++;
    const mark = layout.marks[doc.id];
    if (mark?.disposition === "irrelevant") {
      summary.ignored++;
      continue;
    }
    summary[mapReadState(mark, doc.read_revision)]++;
  }
  summary.pending = summary.unread + summary.changed;
  return summary;
}
function safeSourceLink(raw) {
  try {
    if (!raw || /[\u0000-\u0020\u007f]/.test(raw)) return null;
    const url = new URL(raw);
    return url.protocol === "https:" && !url.username && !url.password ? url.href : null;
  } catch {
    return null;
  }
}
function mergePositions(layout, positions) {
  const merged = new Map(layout.positions.map((row) => [row.node_id, row]));
  for (const row of positions) {
    if (!Number.isFinite(row.x) || !Number.isFinite(row.y)) throw new Error("유효하지 않은 배치 좌표입니다.");
    merged.set(row.node_id, { node_id: row.node_id, x: bound(row.x), y: bound(row.y) });
  }
  if (merged.size > 200) throw new Error("배치 저장은 200개 항목까지 지원합니다. 기존 숨은 항목은 삭제하지 않았습니다.");
  return { ...layout, positions: [...merged.values()] };
}
var noteCanvasId = (noteId) => `memo:${noteId}`;
function pendingNoteCanDelete(layout, noteId, editable) {
  return !!noteId && editable && layout.notes.some((note) => note.note_id === noteId);
}
function mapCanvasPositions(layout) {
  return [...layout.positions, ...layout.notes.map((note) => ({ node_id: noteCanvasId(note.note_id), x: note.x, y: note.y }))];
}
function mergeCanvasPositions(layout, patch) {
  const notes = new Map(layout.notes.map((note) => [noteCanvasId(note.note_id), note]));
  const moved = /* @__PURE__ */ new Map(), graph = [];
  for (const row of patch) {
    if (!Number.isFinite(row.x) || !Number.isFinite(row.y)) throw new Error("유효하지 않은 배치 좌표입니다.");
    if (notes.has(row.node_id)) moved.set(row.node_id, { ...row, x: bound(row.x), y: bound(row.y) });
    else if (row.node_id.startsWith("memo:")) throw new Error("삭제된 메모의 위치는 변경하지 않았습니다.");
    else graph.push(row);
  }
  const next = mergePositions(layout, graph);
  return moved.size ? { ...next, notes: layout.notes.map((note) => {
    const row = moved.get(noteCanvasId(note.note_id));
    return row ? { ...note, x: row.x, y: row.y } : note;
  }) } : next;
}
function withCanvasNotes(nodes, layout) {
  return [...nodes, ...layout.notes.map((note) => ({
    id: noteCanvasId(note.note_id),
    kind: "note",
    x: note.x,
    y: note.y,
    title: note.text.trim().split(/\r?\n/, 1)[0] || "새 메모",
    done: note.done,
    subtitle: `${note.anchor ? "연결 메모" : "자유 메모"} · ${note.done ? "완료" : "클릭해 편집"}`
  }))];
}
function nextNotePosition(nodes, notes, selection, links) {
  const link = selection?.kind === "link" ? links.find((row) => row.id === selection.id) : void 0;
  const target = nodes.find((row) => row.id === (link?.documentId || selection?.id)) || nodes[0];
  const x = bound((target?.x || 0) + 168), startY = bound((target?.y || 0) + 76);
  const occupied = [...nodes, ...notes];
  const attempts = occupied.length * 2 + 1;
  const direction = startY + attempts * 76 > LIMIT2 ? -1 : 1;
  for (let i = 0; i <= attempts; i++) {
    const y = bound(startY + direction * i * 76);
    if (!occupied.some((row) => Math.abs(row.x - x) < 160 && Math.abs(row.y - y) < 70)) return { x, y };
  }
  return { x, y: startY };
}
function sourceGroupPositions(nodes, links) {
  const byId = new Map(nodes.map((node) => [node.id, node])), neighbors = new Map(nodes.map((node) => [node.id, /* @__PURE__ */ new Set()]));
  for (const link of links) {
    if (!byId.has(link.companyId) || !byId.has(link.documentId)) continue;
    neighbors.get(link.companyId).add(link.documentId);
    neighbors.get(link.documentId).add(link.companyId);
  }
  const visited = /* @__PURE__ */ new Set(), result = /* @__PURE__ */ new Map();
  let x = 0, y = 0, rowHeight = 0;
  for (const root of nodes) {
    if (visited.has(root.id)) continue;
    const queue = [root.id], ids = /* @__PURE__ */ new Set();
    visited.add(root.id);
    for (let i = 0; i < queue.length; i++) {
      const id = queue[i];
      ids.add(id);
      for (const next of neighbors.get(id) || []) if (!visited.has(next)) {
        visited.add(next);
        queue.push(next);
      }
    }
    const companies = nodes.filter((node) => ids.has(node.id) && node.kind === "company");
    const documents = nodes.filter((node) => ids.has(node.id) && node.kind === "document");
    const columns = (length) => Math.min(3, Math.ceil(Math.sqrt(length)));
    const companyCols = columns(companies.length), documentCols = columns(documents.length);
    const sideWidth = (cols) => cols ? cols * 180 - 26 : 0;
    const companyWidth = sideWidth(companyCols), documentWidth = sideWidth(documentCols);
    const gap = companies.length && documents.length ? 64 : 0;
    const width = companyWidth + gap + documentWidth;
    const height = Math.max(
      companyCols ? Math.ceil(companies.length / companyCols) : 0,
      documentCols ? Math.ceil(documents.length / documentCols) : 0
    ) * 86 - 28;
    if (x && x + width > 1200) {
      x = 0;
      y += rowHeight + 48;
      rowHeight = 0;
    }
    for (const [items, cols, offset] of [[companies, companyCols, 0], [documents, documentCols, companyWidth + gap]]) {
      items.forEach((node, i) => result.set(node.id, { x: x + offset + i % cols * 180, y: y + Math.floor(i / cols) * 86 }));
    }
    x += width + 48;
    rowHeight = Math.max(rowHeight, height);
  }
  return result;
}
function mapNoteAnchorLabel(note, nodes, links) {
  if (!note.anchor) return "자유 메모";
  if (note.anchor.kind === "node") return nodes.find((node) => node.id === note.anchor.id)?.title || "연결 대상이 현재 지도 밖에 있어요";
  const link = links.find((row) => row.id === note.anchor.id);
  if (!link) return "연결 대상이 현재 지도 밖에 있어요";
  const company = nodes.find((node) => node.id === link.companyId);
  const subject = nodes.find((node) => node.id === link.documentId);
  return [company?.title, subject?.title].filter(Boolean).join(" ↔ ") || "연결 대상이 현재 지도 밖에 있어요";
}
function mapView(graph, layout, filters, applySavedPositions = true, recordsKnown = true) {
  if (!graph) return { nodes: [], links: [], documents: [] };
  const documents = graph.documents.filter((doc) => matchesSource(doc, filters) && (!filters.review || !recordsKnown || layout.marks[doc.id]?.disposition !== "irrelevant" && mapReadState(layout.marks[doc.id], doc.read_revision) !== "read"));
  const ids = new Set(documents.map((d) => d.id)), positions = new Map(layout.positions.map((p) => [p.node_id, p]));
  const allNodes = [
    ...graph.companies.map((c, i) => ({
      id: c.id,
      kind: "company",
      title: c.name,
      subtitle: c.ticker,
      x: i % 2 * 180,
      y: Math.floor(i / 2) * 86
    })),
    ...graph.documents.map((d, i) => ({
      id: d.id,
      kind: "document",
      title: d.title,
      sourceKind: d.evidence[0]?.kind || "other",
      subtitle: `${recordsKnown && mapReadState(layout.marks[d.id], d.read_revision) === "changed" ? "확인 후 자료 변경 · " : ""}${d.tickers.length >= 2 ? "공통 자료 · " : ""}${d.isCorrection ? "정정 표시 · " : ""}${d.source}`,
      x: 470 + i % 3 * 180,
      y: Math.floor(i / 3) * 86
    }))
  ];
  const defaults = sourceGroupPositions(allNodes, graph.links);
  const nodes = allNodes.filter((n) => n.kind === "company" || ids.has(n.id)).map((n) => ({
    ...n,
    ...defaults.get(n.id),
    ...applySavedPositions && positions.has(n.id) ? { x: positions.get(n.id).x, y: positions.get(n.id).y } : {}
  }));
  return { nodes, documents, links: graph.links.filter((link) => ids.has(link.documentId)) };
}
var CSS6 = `
.ppm{--bg:#f2f4f6;--panel:#fff;--ink:#191f28;--muted:#4e5968;--soft:#f0edff;--accent:#6c5ce7;--divider:#e5e8eb;background:var(--bg);color:var(--ink);font:600 13px/1.55 Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;min-width:0;border-radius:18px;overflow:hidden;isolation:isolate}
.ppm *{box-sizing:border-box}.ppm :where(button,input,select,textarea){font:inherit;color:inherit;border:0;border-radius:8px;background:var(--soft);padding:7px 9px}
.ppm :where(button){font-weight:700}.ppm :where(input,select,textarea){font-weight:600}
.ppm :where(button){cursor:pointer;display:inline-flex;gap:5px;align-items:center;justify-content:center}.ppm :where(button:disabled){opacity:.45;cursor:not-allowed}
.ppm :where(button:hover:not(:disabled),button[aria-pressed=true]){background:color-mix(in srgb,var(--accent) 14%,var(--panel));color:var(--accent)}
.ppm :where(button,input,select,textarea,a,[tabindex]):not(.pmc):focus-visible{outline:none;background:color-mix(in srgb,var(--accent) 18%,var(--panel));color:var(--ink)}
.ppm .ppm-primary{background:var(--accent);color:white}.ppm h2,.ppm h3,.ppm h4,.ppm p{margin:0}.ppm h2{font-size:18px;font-weight:800;letter-spacing:-.3px}.ppm h3{font-size:15px;font-weight:700}.ppm h4{font-size:13px;font-weight:700}.ppm small{font-size:12px;font-weight:600;color:var(--muted)}
.ppm-head,.ppm-toolbar,.ppm-status{display:flex;flex-wrap:wrap;align-items:center;gap:7px;padding:9px 12px;background:var(--panel)}.ppm-head{justify-content:space-between;padding:12px 16px}.ppm-toolbar{justify-content:center;border-top:1px solid var(--divider)}
.ppm-surface-tabs{display:flex;gap:4px}.ppm-holdings-summary{display:flex;flex-wrap:wrap;gap:7px;padding:8px 12px;border-top:1px solid var(--divider);background:var(--panel);color:var(--muted);font-weight:600}.ppm-holdings-summary span{padding:4px 8px;border-radius:999px;background:var(--soft)}.ppm-surface[hidden]{display:none}
.ppm-search{display:flex;gap:4px;align-items:center}.ppm-search input{width:145px}.ppm-search-results{padding:4px 12px;display:flex;flex-wrap:wrap;justify-content:center;gap:6px}.ppm-filter-empty{padding:9px 12px;color:var(--muted);background:var(--soft);font-size:12px}.ppm-filter-empty span{display:block}
.ppm-view-tabs{display:flex;gap:4px;flex-wrap:wrap}.ppm-reviewed{display:flex;flex-direction:column;gap:12px}.ppm-reviewed .ppm-evidence>div{display:grid;gap:5px}.ppm-reviewed strong{font-weight:750}
.ppm-work{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:0}.ppm-map-area{position:relative;min-width:0;height:clamp(540px,65vh,760px)}.ppm-map-area .pmc-empty{display:none}.ppm-map-area>.ppm-empty{position:absolute;left:16px;right:16px;top:96px;padding:18px;border-radius:12px;color:var(--muted);background:var(--panel);pointer-events:none}
.ppm-panel{padding:18px 16px;max-height:650px;overflow:auto;background:var(--panel);border-left:1px solid var(--divider);display:flex;flex-direction:column;gap:12px;min-width:0}.ppm-panel p,.ppm-panel a{overflow-wrap:anywhere;white-space:pre-wrap}.ppm-panel p{font-size:14px;line-height:1.7}.ppm-panel a{color:var(--accent);font-weight:700;display:inline-flex;gap:4px;align-items:center}
.ppm-evidence,.ppm-note{background:color-mix(in srgb,var(--bg) 88%,var(--panel));padding:11px;border-radius:12px;display:flex;flex-direction:column;gap:7px}.ppm-actions{display:flex;gap:6px;flex-wrap:wrap}.ppm-note textarea{width:100%;min-height:80px;resize:vertical;background:var(--panel)}
.ppm-note[data-selected=true]{box-shadow:inset 3px 0 var(--accent)}.ppm-note-list{display:grid;gap:9px}
.ppm-note-delete-confirm{display:grid;gap:7px;padding:8px;border-radius:8px;background:var(--panel)}.ppm-note-delete-actions{display:flex;gap:6px;flex-wrap:wrap}.ppm-note-delete{color:var(--ink)}
.ppm-picker{padding:14px;display:flex;flex-direction:column;gap:10px}.ppm-picks{display:flex;flex-wrap:wrap;gap:7px;max-height:220px;overflow:auto}.ppm-warning{color:#8d4d28;background:#fcf2e9;padding:9px 12px;border-radius:8px}.ppm-status{font-size:12px;color:var(--muted)}
.ppm a,.ppm a:hover,.ppm a:focus,.ppm a:visited{text-decoration:none}
.ppm[data-theme=dark]{--bg:#0f1318;--panel:#171c23;--ink:#e3e7ec;--muted:#9aa4b1;--soft:#241f3a;--accent:#a99bff;--divider:#3c4350}
.ppm[data-theme=dark] .ppm-primary{background:#7451bd;color:#fff}.ppm[data-theme=dark] .ppm-warning{background:#382b22;color:#edc4a5}
@media(max-width:760px){.ppm{border-radius:14px}.ppm .ppm-work{grid-template-columns:minmax(0,1fr)}.ppm .ppm-map-area{height:480px}.ppm .ppm-panel{max-height:480px;border-left:0;border-top:1px solid var(--divider)}.ppm .ppm-toolbar{gap:5px}}
`;
function PublicPortfolioMap() {
  const controller = React8.useRef(null);
  const deleteButtonRefs = React8.useRef(/* @__PURE__ */ new Map());
  const restoreDeleteFocusId = React8.useRef(null);
  const theme = usePortfolioMapTheme();
  const [state, setState] = React8.useState(blank);
  const [canvasEpoch, setCanvasEpoch] = React8.useState(0);
  const [surfaceMode, setSurfaceMode] = React8.useState("map");
  const [mapMounted, setMapMounted] = React8.useState(false);
  const [viewMode, setViewMode] = React8.useState("documents");
  const [filters, setFilters] = React8.useState({ source: "all", common: false, review: false });
  const [query, setQuery] = React8.useState(""), [selection, setSelection] = React8.useState(null);
  const [picker, setPicker] = React8.useState(false), [picked, setPicked] = React8.useState([]);
  const [notesOpen, setNotesOpen] = React8.useState(false), [motion, setMotion] = React8.useState(true);
  const [pendingDeleteNoteId, setPendingDeleteNoteId] = React8.useState(null);
  const [notice, setNotice] = React8.useState(""), [savedRevision, setSavedRevision] = React8.useState(null);
  const cancelNoteDeletion = () => {
    if (pendingDeleteNoteId) restoreDeleteFocusId.current = pendingDeleteNoteId;
    setPendingDeleteNoteId(null);
  };
  const resetLocal = () => {
    setCanvasEpoch((value) => value + 1);
    setSelection(null);
    setQuery("");
    setPicked([]);
    setPicker(false);
    setViewMode("documents");
    setFilters({ source: "all", common: false, review: false });
    setNotesOpen(false);
    restoreDeleteFocusId.current = null;
    setPendingDeleteNoteId(null);
    setMotion(true);
    setNotice("");
    setSavedRevision(null);
  };
  React8.useEffect(() => {
    const workspace = createPortfolioMapWorkspace();
    controller.current = workspace;
    const unsubscribe = workspace.subscribe((next) => {
      if (!next.privateState.document || next.privateState.phase === "loading") resetLocal();
      setState(next);
    });
    const unbind = workspace.bindAuth(window);
    void workspace.open().catch(() => setNotice("자료를 불러오지 못했습니다. 다시 불러오세요."));
    return () => {
      unsubscribe();
      unbind();
      workspace.dispose();
      controller.current = null;
    };
  }, []);
  React8.useEffect(() => {
    if (surfaceMode === "map") setMapMounted(true);
  }, [surfaceMode]);
  const layout = state.privateState.document?.layouts.find((row) => row.map_key === MAP_KEY2) || baseLayout();
  const recordsKnown = reviewRecordsKnown(state);
  const reviewSummary = mapReviewSummary(state.graph, layout, filters, recordsKnown);
  const view = React8.useMemo(() => mapView(state.graph, layout, filters, false, recordsKnown), [state.graph, state.privateState.document, filters, recordsKnown]);
  const reviewedHoldings = React8.useMemo(() => {
    const selected = new Set(state.selectedTickers);
    return state.holdings.filter((holding) => selected.has(holding.ticker)).map((holding) => ({ ticker: holding.ticker, market: holding.market, name: holding.name }));
  }, [state.holdings, state.selectedTickers]);
  const reviewedFacts = React8.useMemo(() => buildReviewedPortfolioFacts(
    reviewedHoldings.map(({ ticker, market }) => ({ ticker, market })),
    portfolioReviewedRegistry
  ), [reviewedHoldings]);
  const reviewedView = React8.useMemo(() => {
    const base = buildPortfolioReviewedCanvasView(reviewedFacts, viewMode === "events" ? "events" : "relationships", reviewedHoldings);
    const defaults = sourceGroupPositions(base.nodes, base.links);
    return { ...base, nodes: base.nodes.map((node) => ({ ...node, ...defaults.get(node.id) })) };
  }, [reviewedFacts, reviewedHoldings, viewMode]);
  const activeNodes = viewMode === "documents" ? view.nodes : reviewedView.nodes;
  const activeLinks = viewMode === "documents" ? view.links : reviewedView.links;
  const canvasNodes = React8.useMemo(() => withCanvasNotes(activeNodes, layout), [activeNodes, layout.notes]);
  React8.useEffect(() => {
    if (selection && !(selection.kind === "link" ? activeLinks : canvasNodes).some((item) => item.id === selection.id)) setSelection(null);
  }, [selection, activeLinks, canvasNodes]);
  const editable = editableMap(state);
  const selectedLink = viewMode === "documents" && selection?.kind === "link" ? view.links.find((l) => l.id === selection.id) : void 0;
  const selectedDoc = viewMode === "documents" ? view.documents.find((d) => d.id === (selectedLink?.documentId || (selection?.kind === "document" ? selection.id : ""))) : void 0;
  const selectedFactId = viewMode === "documents" ? void 0 : selection?.kind === "link" ? reviewedView.factIdsByLink.get(selection.id) : selection?.kind === "document" ? reviewedView.factIdsByNode.get(selection.id) : void 0;
  const selectedFact = viewMode === "documents" ? void 0 : selectedReviewedFact(reviewedFacts, viewMode, selectedFactId);
  const selectedFactTitle = selectedFact ? "title" in selectedFact ? selectedFact.title : selectedFact.label : void 0;
  const selectedRecord = selectedDoc || (selectedFact && viewMode !== "documents" ? reviewedRecord(viewMode, selectedFact) : void 0);
  const selectedSources = [...new Map((selectedLink?.evidence || selectedDoc?.evidence || []).flatMap((evidence) => evidence.sourceRecords || []).map((record6) => [JSON.stringify(record6), record6])).values()];
  const selectedCompany = selection?.kind === "company" ? state.graph?.companies.find((c) => c.id === selection.id) : void 0;
  const selectedNote = selection?.kind === "note" ? layout.notes.find((n) => noteCanvasId(n.note_id) === selection.id) : void 0;
  const shownNotes = selectedNote ? [selectedNote, ...layout.notes.filter((n) => n.note_id !== selectedNote.note_id)] : layout.notes;
  React8.useEffect(() => {
    if (pendingDeleteNoteId && (!notesOpen || !pendingNoteCanDelete(layout, pendingDeleteNoteId, editable))) {
      restoreDeleteFocusId.current = null;
      setPendingDeleteNoteId(null);
    }
  }, [notesOpen, layout.notes, pendingDeleteNoteId, editable]);
  React8.useEffect(() => {
    if (pendingDeleteNoteId || !restoreDeleteFocusId.current) return;
    const noteId = restoreDeleteFocusId.current;
    restoreDeleteFocusId.current = null;
    deleteButtonRefs.current.get(noteId)?.focus();
  }, [pendingDeleteNoteId]);
  React8.useEffect(() => {
    if (!pendingDeleteNoteId) return;
    const cancel = (event) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      restoreDeleteFocusId.current = pendingDeleteNoteId;
      setPendingDeleteNoteId(null);
    };
    window.addEventListener("keydown", cancel, true);
    return () => window.removeEventListener("keydown", cancel, true);
  }, [pendingDeleteNoteId]);
  const relatedLinks = selectedCompany ? activeLinks.filter((l) => l.companyId === selectedCompany.id) : selectedDoc ? activeLinks.filter((l) => l.documentId === selectedDoc.id) : [];
  const matches = query.trim() ? state.holdings.filter((h) => `${h.name} ${h.ticker}`.toLowerCase().includes(query.trim().toLowerCase())) : [];
  const run = (action) => {
    try {
      setNotice("");
      return action();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "변경하지 못했습니다.");
      return false;
    }
  };
  const edit = (change) => {
    if (!controller.current || !editableMap(controller.current.getState())) return false;
    return run(() => controller.current.editLayout(MAP_KEY2, change)) === true;
  };
  const commitPositions = (positions) => edit((l) => mergeCanvasPositions(l, positions));
  const selectCanvas = (next) => {
    setSelection(next);
    if (next?.kind === "note") setNotesOpen(true);
  };
  const mark = (change) => {
    if (selectedDoc && controller.current && editableMap(controller.current.getState())) run(() => controller.current.markDocument(MAP_KEY2, selectedDoc.id, change));
    else if (selectedFact && viewMode !== "documents") edit((value) => withReviewedMark(value, viewMode, selectedFact, change));
  };
  const addNote = () => {
    const anchor = selection && selection.kind !== "note" ? { kind: selection.kind === "link" ? "edge" : "node", id: selection.id } : null;
    const noteId = `note:${crypto.randomUUID()}`;
    if (edit((l) => {
      if (l.notes.length >= 100) throw new Error("메모는 100개까지 저장할 수 있습니다.");
      const all = viewMode === "documents" ? mapView(state.graph, l, { source: "all", common: false, review: false }) : { nodes: activeNodes, links: activeLinks };
      const position = nextNotePosition(all.nodes, l.notes, selection, all.links);
      return { ...l, notes: [...l.notes, { note_id: noteId, anchor, ...position, text: "", done: false }] };
    })) {
      setSelection({ kind: "note", id: noteCanvasId(noteId) });
      setNotesOpen(true);
    }
  };
  const confirmNoteDeletion = () => {
    const noteId = pendingDeleteNoteId, workspace = controller.current;
    if (!noteId || !workspace || !pendingNoteCanDelete(layout, noteId, editableMap(workspace.getState()))) {
      restoreDeleteFocusId.current = null;
      setPendingDeleteNoteId(null);
      return;
    }
    let deleted = false;
    if (edit((value) => {
      if (!value.notes.some((note) => note.note_id === noteId)) return value;
      deleted = true;
      return { ...value, notes: value.notes.filter((note) => note.note_id !== noteId) };
    }) && deleted) {
      restoreDeleteFocusId.current = null;
      setPendingDeleteNoteId(null);
      if (selection?.kind === "note" && selection.id === noteCanvasId(noteId)) setSelection(null);
    }
  };
  const choose = (ticker) => {
    const node = activeNodes.find((n) => n.id === `company:${ticker}`);
    if (!node) {
      setPicker(true);
      setPicked(state.selectedTickers);
      setNotice("현재 지도 밖의 보유종목입니다. 보기 목록에서 선택하세요.");
      return;
    }
    setSelection((previous) => previous?.id === node.id ? null : { kind: "company", id: node.id });
  };
  const save = async () => {
    const workspace = controller.current;
    if (!workspace || !canSaveMap(workspace.getState())) return;
    setNotice("");
    try {
      if (await workspace.save()) setSavedRevision(workspace.getState().privateState.revision);
    } catch {
      setNotice("저장을 확인하지 못했습니다. 초안을 유지합니다.");
    }
  };
  const changeViewMode = (next) => {
    if (next === viewMode) return;
    setViewMode(next);
    setSelection(null);
    setCanvasEpoch((value) => value + 1);
  };
  const privatePhase = state.privateState.phase;
  const holdingsSummary = holdingsSummaryState(state);
  const filtersActive = filters.source !== "all" || filters.common || filters.review;
  const resetFilters = () => setFilters({ source: "all", common: false, review: false });
  const status = privatePhase === "saving" ? "저장 확인 중…" : privatePhase === "conflict" ? "다른 창의 저장과 충돌 · 초안 미저장" : privatePhase === "error" ? "회원 기록 요청 실패 · 저장 확인 안 됨" : privatePhase === "loading" ? "회원 기록 불러오는 중…" : privatePhase === "signed-out" ? "로그인이 필요합니다." : state.privateState.dirty ? "변경사항 미저장" : savedRevision !== null && savedRevision === state.privateState.revision ? "서버 저장 확인됨" : "회원 기록 불러옴 · 미저장 수정 없음";
  const currentMark = selectedRecord ? layout.marks[selectedRecord.id] : void 0;
  const linkLabel = (link) => link.evidence.some((e) => e.kind === "disclosure" && e.confirmation === "confirmed") ? "공시 자료에 포함" : link.confirmation === "confirmed" ? "사업 자료에 포함" : "조회에 포함 · 관계 미확인";
  const noteAnchorLabel = (note) => {
    return mapNoteAnchorLabel(note, activeNodes, activeLinks);
  };
  return /* @__PURE__ */ React8.createElement("section", { className: "ppm", "data-theme": theme, "aria-label": "보유종목 지도와 목록" }, /* @__PURE__ */ React8.createElement("style", null, CSS6), /* @__PURE__ */ React8.createElement("header", { className: "ppm-head" }, /* @__PURE__ */ React8.createElement("div", null, /* @__PURE__ */ React8.createElement("h2", null, surfaceMode === "holdings" ? "내 보유종목 목록" : viewMode === "documents" ? "내 보유종목 자료 지도" : "내 보유종목 검토 지도"), /* @__PURE__ */ React8.createElement("small", null, surfaceMode === "holdings" ? "보유 수량과 평균 매수가 · 조회 전용" : viewMode === "documents" ? "원문 자료 연결 · 기업 영향은 아직 미판정" : "공식 원문 수동 대조 · 현재 영향 미확인")), /* @__PURE__ */ React8.createElement("div", { className: "ppm-actions" }, /* @__PURE__ */ React8.createElement("div", { className: "ppm-surface-tabs", role: "group", "aria-label": "보유종목 보기 선택" }, /* @__PURE__ */ React8.createElement("button", { "aria-pressed": surfaceMode === "map", onClick: () => setSurfaceMode("map") }, "지도"), /* @__PURE__ */ React8.createElement("button", { "aria-pressed": surfaceMode === "holdings", onClick: () => setSurfaceMode("holdings") }, "보유 목록")), surfaceMode === "map" ? /* @__PURE__ */ React8.createElement(React8.Fragment, null, /* @__PURE__ */ React8.createElement(PortfolioMapGuide, null), /* @__PURE__ */ React8.createElement("button", { className: "ppm-primary", disabled: !canSaveMap(state), onClick: () => void save() }, privatePhase === "error" ? "초안 저장 재시도" : "명시 저장", " ", /* @__PURE__ */ React8.createElement(Chev, null))) : null)), /* @__PURE__ */ React8.createElement("div", { className: "ppm-holdings-summary", "aria-label": "보유종목 요약" }, holdingsSummary.known ? /* @__PURE__ */ React8.createElement(React8.Fragment, null, /* @__PURE__ */ React8.createElement("span", null, "지원 보유 ", state.holdings.length, "종목"), /* @__PURE__ */ React8.createElement("span", null, "지도 표시 ", state.selectedTickers.length, "종목"), /* @__PURE__ */ React8.createElement("span", null, "지원 제외 ", state.unsupportedCount, "개")) : /* @__PURE__ */ React8.createElement("span", { role: "status" }, holdingsSummary.message)), /* @__PURE__ */ React8.createElement("div", { className: "ppm-surface", hidden: surfaceMode !== "map" }, /* @__PURE__ */ React8.createElement("div", { className: "ppm-toolbar", "aria-label": "지도 도구" }, /* @__PURE__ */ React8.createElement("div", { className: "ppm-view-tabs", role: "group", "aria-label": "지도 내용 선택" }, /* @__PURE__ */ React8.createElement("button", { "aria-pressed": viewMode === "documents", onClick: () => changeViewMode("documents") }, "자료"), /* @__PURE__ */ React8.createElement("button", { "aria-pressed": viewMode === "relationships", onClick: () => changeViewMode("relationships") }, "확인된 관계"), /* @__PURE__ */ React8.createElement("button", { "aria-pressed": viewMode === "events", onClick: () => changeViewMode("events") }, "공통 사건")), /* @__PURE__ */ React8.createElement("form", { className: "ppm-search", onSubmit: (e) => {
    e.preventDefault();
    if (matches[0]) choose(matches[0].ticker);
  } }, /* @__PURE__ */ React8.createElement("input", { "aria-label": "보유종목 내 찾기", placeholder: "보유종목 내 찾기", value: query, onChange: (e) => setQuery(e.target.value) }), /* @__PURE__ */ React8.createElement("button", { type: "submit", disabled: !matches.length, "aria-label": "검색한 종목 찾기" }, /* @__PURE__ */ React8.createElement(Chev, null))), viewMode === "documents" ? /* @__PURE__ */ React8.createElement(React8.Fragment, null, /* @__PURE__ */ React8.createElement("select", { "aria-label": "자료 출처 종류", value: filters.source, onChange: (e) => setFilters((f) => ({ ...f, source: e.target.value })) }, /* @__PURE__ */ React8.createElement("option", { value: "all" }, "전체 자료"), /* @__PURE__ */ React8.createElement("option", { value: "disclosure" }, "공시"), /* @__PURE__ */ React8.createElement("option", { value: "business" }, "사업 자료"), /* @__PURE__ */ React8.createElement("option", { value: "news" }, "뉴스 조회"), /* @__PURE__ */ React8.createElement("option", { value: "schedule" }, "일정"), /* @__PURE__ */ React8.createElement("option", { value: "other" }, "기타")), /* @__PURE__ */ React8.createElement("button", { "aria-pressed": filters.common, onClick: () => setFilters((f) => ({ ...f, common: !f.common })) }, "공통 자료만"), /* @__PURE__ */ React8.createElement("button", { "aria-pressed": filters.review && recordsKnown, disabled: !reviewSummary, title: recordsKnown ? "읽음 표시가 없거나 확인 후 제공 자료가 달라진 항목 · 무관 제외 · 한 번 더 누르면 해제" : "확인 기록을 불러온 뒤 이용할 수 있어요", onClick: () => setFilters((f) => ({ ...f, review: !f.review })) }, "확인할 자료", reviewSummary ? ` ${reviewSummary.pending}` : ""), /* @__PURE__ */ React8.createElement("button", { disabled: !filtersActive, onClick: resetFilters }, "필터 초기화")) : null, /* @__PURE__ */ React8.createElement("button", { "aria-pressed": notesOpen, onClick: () => setNotesOpen((v) => {
    if (v) {
      restoreDeleteFocusId.current = null;
      setPendingDeleteNoteId(null);
    }
    ;
    return !v;
  }) }, "메모 ", layout.notes.length)), query.trim() ? /* @__PURE__ */ React8.createElement("div", { className: "ppm-search-results" }, matches.length ? matches.map((h) => /* @__PURE__ */ React8.createElement("button", { key: h.ticker, onClick: () => choose(h.ticker) }, h.name, " · ", h.ticker, /* @__PURE__ */ React8.createElement(Chev, null))) : /* @__PURE__ */ React8.createElement("small", null, "보유종목 내 검색 결과가 없습니다.")) : null, /* @__PURE__ */ React8.createElement("div", { className: "ppm-status", role: "status" }, /* @__PURE__ */ React8.createElement("span", null, status), /* @__PURE__ */ React8.createElement("span", null, "지도 보기 최대 30종목 · 등록 제한 아님"), /* @__PURE__ */ React8.createElement("button", { disabled: !state.holdings.length || state.phase === "loading", onClick: () => {
    setPicked(state.selectedTickers);
    setPicker((v) => !v);
  } }, "보기 종목 선택 ", /* @__PURE__ */ React8.createElement(Chev, null)), state.graph ? viewMode === "documents" ? /* @__PURE__ */ React8.createElement("span", null, "표시 종목 ", state.graph.companies.length, " · 자료 ", view.documents.length, "/", state.graph.documents.length, " · 자료 제공 ", state.graph.coverage.available, "/", state.graph.coverage.total, " 조회 구간") : /* @__PURE__ */ React8.createElement("span", null, "표시 종목 ", reviewedHoldings.length, " · ", viewMode === "relationships" ? `확인 관계 ${reviewedFacts.relationships.length}` : `공통 사건 ${reviewedFacts.events.length}`) : null), viewMode === "documents" && state.phase === "ready" && state.graph && state.graph.documents.length > 0 && !view.documents.length && filtersActive ? /* @__PURE__ */ React8.createElement("p", { className: "ppm-filter-empty", role: "status" }, /* @__PURE__ */ React8.createElement("span", null, "현재 조건에 맞는 자료가 없어요."), /* @__PURE__ */ React8.createElement("span", null, "필터를 초기화하면 전체 자료를 다시 볼 수 있어요.")) : null, viewMode === "documents" && filters.review && reviewSummary ? /* @__PURE__ */ React8.createElement("p", { className: "ppm-filter-empty", role: "status" }, /* @__PURE__ */ React8.createElement("span", null, "현재 출처·공통 조건의 ", reviewSummary.total, "개 자료 중 읽음 표시 없음 ", reviewSummary.unread, " · 확인 후 자료 변경 ", reviewSummary.changed, " · 무관 ", reviewSummary.ignored, "개 제외"), /* @__PURE__ */ React8.createElement("span", null, "원문 수정이나 지난 방문 이후의 새 사건을 확정하는 표시는 아니에요.")) : null, viewMode !== "documents" ? /* @__PURE__ */ React8.createElement("p", { className: "ppm-filter-empty", role: "status" }, /* @__PURE__ */ React8.createElement("span", null, reviewedCoverageMessage(reviewedFacts))) : null, notice ? /* @__PURE__ */ React8.createElement("p", { className: "ppm-warning", role: "alert" }, notice) : null, state.error ? /* @__PURE__ */ React8.createElement("p", { className: "ppm-warning", role: "alert" }, "보유종목·자료를 불러오지 못했습니다. (", state.error, ") ", /* @__PURE__ */ React8.createElement("button", { onClick: () => void controller.current?.open() }, "다시 불러오기")) : null, privatePhase === "error" || privatePhase === "conflict" ? /* @__PURE__ */ React8.createElement("div", { className: "ppm-warning", role: "alert" }, state.privateState.error, " · 기존 초안을 자동으로 덮어쓰지 않습니다.", /* @__PURE__ */ React8.createElement("button", { onClick: () => {
    if (!state.privateState.dirty || window.confirm("현재 미저장 초안을 버리고 서버 기록을 다시 불러올까요?")) void controller.current?.reloadSaved(state.privateState.dirty);
  } }, "서버 기록 다시 불러오기")) : null, state.unsupportedCount ? /* @__PURE__ */ React8.createElement("p", { className: "ppm-status" }, "현재 자료 조회를 지원하지 않는 보유 항목 ", state.unsupportedCount, "개는 지도에서 제외됩니다.") : null, picker || state.phase === "choose-stocks" ? /* @__PURE__ */ React8.createElement("div", { className: "ppm-picker" }, /* @__PURE__ */ React8.createElement("h3", null, "지도에서 볼 보유종목 선택"), /* @__PURE__ */ React8.createElement("p", null, "전체 ", state.holdings.length, "종목 중 ", picked.length, "/30 선택 · 실제 보유 등록은 바뀌지 않습니다."), /* @__PURE__ */ React8.createElement("div", { className: "ppm-picks" }, state.holdings.map((h) => /* @__PURE__ */ React8.createElement("label", { key: h.ticker }, /* @__PURE__ */ React8.createElement("input", { type: "checkbox", checked: picked.includes(h.ticker), disabled: !picked.includes(h.ticker) && picked.length >= 30, onChange: (e) => setPicked((v) => e.target.checked ? [...v, h.ticker] : v.filter((t) => t !== h.ticker)) }), " ", h.name, " · ", h.ticker))), /* @__PURE__ */ React8.createElement("button", { disabled: !picked.length || state.phase === "loading", onClick: () => {
    setPicker(false);
    void controller.current?.showTickers(picked).catch(() => setNotice("보기 종목을 선택하지 못했습니다."));
  } }, "선택한 종목 보기 ", /* @__PURE__ */ React8.createElement(Chev, null))) : null, /* @__PURE__ */ React8.createElement("div", { className: "ppm-work" }, /* @__PURE__ */ React8.createElement("div", { className: "ppm-map-area" }, mapMounted ? /* @__PURE__ */ React8.createElement(
    PortfolioMapCanvas,
    {
      key: canvasEpoch,
      nodes: canvasNodes,
      links: activeLinks,
      mode: viewMode,
      selection,
      onSelect: selectCanvas,
      positions: mapCanvasPositions(layout),
      onPositionsChange: commitPositions,
      editable,
      motion,
      onMotionChange: setMotion,
      theme,
      active: surfaceMode === "map"
    }
  ) : null, !canvasNodes.length || viewMode !== "documents" && !(viewMode === "relationships" ? reviewedFacts.relationships.length : reviewedFacts.events.length) ? /* @__PURE__ */ React8.createElement("div", { className: "ppm-empty" }, state.phase === "loading" ? "보유종목과 자료를 불러오는 중…" : state.phase === "signed-out" ? "기존 알파네스트 계정으로 로그인한 뒤 이용하세요." : state.phase === "choose-stocks" ? "위에서 지도에 표시할 종목을 선택하세요." : viewMode === "documents" ? "표시할 자료가 없습니다. 조회 실패·자료 미제공은 관계가 없다는 뜻이 아닙니다." : "현재 보유 선택에 맞는 검토 완료 항목이 없습니다. 관계나 공통 사건이 없다는 뜻이 아니며 검수 대상 밖일 수 있습니다.") : null), /* @__PURE__ */ React8.createElement("aside", { className: "ppm-panel", "aria-label": "원문과 종목별 이유" }, /* @__PURE__ */ React8.createElement("h3", null, selectedNote ? "내 메모" : selectedFactTitle || selectedDoc?.title || selectedCompany?.name || (viewMode === "documents" ? "자료를 선택하세요" : "검토 항목을 선택하세요")), selectedRecord ? /* @__PURE__ */ React8.createElement(React8.Fragment, null, /* @__PURE__ */ React8.createElement("div", { className: "ppm-actions", role: "group", "aria-label": "선택 항목 확인 상태" }, /* @__PURE__ */ React8.createElement("button", { disabled: !editable, "aria-pressed": currentMark?.read_revision === selectedRecord.read_revision, onClick: () => mark({ read: currentMark?.read_revision !== selectedRecord.read_revision }) }, "읽음"), /* @__PURE__ */ React8.createElement("button", { disabled: !editable, "aria-pressed": !!currentMark?.important, onClick: () => mark({ important: !currentMark?.important }) }, "중요"), /* @__PURE__ */ React8.createElement("button", { disabled: !editable, "aria-pressed": currentMark?.disposition === "later", onClick: () => mark({ disposition: currentMark?.disposition === "later" ? "inbox" : "later" }) }, "나중에"), /* @__PURE__ */ React8.createElement("button", { disabled: !editable, "aria-pressed": currentMark?.disposition === "irrelevant", onClick: () => mark({ disposition: currentMark?.disposition === "irrelevant" ? "inbox" : "irrelevant" }) }, "무관")), /* @__PURE__ */ React8.createElement("small", null, !recordsKnown ? "확인 기록을 불러오지 못해 읽음 여부를 알 수 없어요." : mapReadState(currentMark, selectedRecord.read_revision) === "changed" ? selectedFact ? "확인 후 검토 내용 변경 · 새 사건이나 원문 수정 확정은 아닙니다." : "확인 후 자료 변경 · 원문 자체의 수정 확정은 아닙니다." : mapReadState(currentMark, selectedRecord.read_revision) === "read" ? selectedFact ? "현재 검토 내용 읽음 표시" : "현재 제공 자료 읽음 표시" : selectedFact ? "아직 읽음 표시하지 않은 검토 항목" : "아직 읽음 표시하지 않은 자료"), selectedFact ? /* @__PURE__ */ React8.createElement("small", null, "개인 확인 상태예요. ‘명시 저장’ 후 다음 접속에 이어집니다.") : null) : null, selectedDoc ? /* @__PURE__ */ React8.createElement(React8.Fragment, null, /* @__PURE__ */ React8.createElement("p", null, selectedLink ? linkLabel(selectedLink) : selectedDoc.reason), /* @__PURE__ */ React8.createElement("small", null, selectedDoc.isCorrection ? "정정 표시가 있는 자료" : "정정 여부는 출처별 확인이 필요해요.", " · ", selectedDoc.asOf || "통합 기준일 미제공 · 아래 개별 근거 확인"), safeSourceLink(selectedDoc.url) ? /* @__PURE__ */ React8.createElement("a", { href: safeSourceLink(selectedDoc.url), target: "_blank", rel: "noopener noreferrer" }, "제공된 원문 직접 열기 ", /* @__PURE__ */ React8.createElement(Chev, null)) : /* @__PURE__ */ React8.createElement("small", null, "안전하게 열 수 있는 원문 링크가 없습니다."), /* @__PURE__ */ React8.createElement(PortfolioSourceDetails, { key: selectedLink?.id || selectedDoc.id, records: selectedSources }), (selectedLink?.evidence || selectedDoc.evidence).map((e, index) => /* @__PURE__ */ React8.createElement("article", { className: "ppm-evidence", key: `${e.ticker}:${index}` }, /* @__PURE__ */ React8.createElement("h4", null, e.ticker, " · ", e.reason), /* @__PURE__ */ React8.createElement("p", null, e.explanation), /* @__PURE__ */ React8.createElement("small", null, e.source, " · ", e.asOf || "기준일 미제공", " · ", e.confirmation === "confirmed" ? "제공된 종목 자료에 포함" : "자료 관계 미확인", e.isCorrection ? " · 정정 표시" : ""), e.sources.map((source, i) => /* @__PURE__ */ React8.createElement("div", { key: i }, /* @__PURE__ */ React8.createElement("small", null, source.source, " · ", source.asOf || "기준일 미제공"), safeSourceLink(source.url) ? /* @__PURE__ */ React8.createElement("a", { href: safeSourceLink(source.url), target: "_blank", rel: "noopener noreferrer" }, source.title || "원문", /* @__PURE__ */ React8.createElement(Chev, null)) : null))))) : selectedFact ? /* @__PURE__ */ React8.createElement(PortfolioReviewedView, { fact: selectedFact }) : selectedNote ? /* @__PURE__ */ React8.createElement("p", null, "내가 남긴 기록이에요. 원문 근거나 확인된 관계로 사용되지 않아요. 수정·이동 뒤 ‘명시 저장’을 눌러야 서버에 반영됩니다.") : /* @__PURE__ */ React8.createElement(React8.Fragment, null, /* @__PURE__ */ React8.createElement("p", null, viewMode === "documents" ? "원문·종목별 연결 이유·기준일을 확인하세요." : "검토 항목을 선택해 원문 날짜·참여 역할·한계를 확인하세요.", " 메모와 배치 변경은 ‘명시 저장’을 눌러야 서버에 저장됩니다."), relatedLinks.map((link) => /* @__PURE__ */ React8.createElement("button", { key: link.id, onClick: () => setSelection({ kind: "link", id: link.id }) }, activeNodes.find((node) => node.id === link.documentId)?.title, /* @__PURE__ */ React8.createElement(Chev, null))), selectedCompany && !relatedLinks.length ? /* @__PURE__ */ React8.createElement("small", null, viewMode === "documents" ? "현재 필터에서 연결 자료가 없습니다. 실제 사업관계 부재를 뜻하지 않습니다." : "현재 검수 범위에서 이 종목과 맞는 항목이 없습니다. 관계 부재를 뜻하지 않습니다.") : null), selectedCompany ? /* @__PURE__ */ React8.createElement(React8.Fragment, null, /* @__PURE__ */ React8.createElement(PortfolioCloseDetails, { key: selectedCompany.id + ":close", quote: selectedCompany.closeQuote }), /* @__PURE__ */ React8.createElement(PortfolioCompanyDetails, { key: selectedCompany.id, sections: selectedCompany.sections })) : null, !selectedNote && viewMode === "documents" ? state.graph?.coverage.sources.filter((c) => !selectedCompany || c.ticker === selectedCompany.ticker).filter((c) => c.state !== "available").map((c) => /* @__PURE__ */ React8.createElement("small", { key: `${c.ticker}:${c.sectionId}` }, c.ticker, " · ", c.sectionId === "business" ? "사업 자료" : "사건 자료", " · ", c.state, " · ", c.messages.join(" · ") || "자료 수집 완전성 미확인")) : null, /* @__PURE__ */ React8.createElement("button", { disabled: !editable, onClick: addNote }, "메모 추가 ", /* @__PURE__ */ React8.createElement(Chev, null)), notesOpen ? /* @__PURE__ */ React8.createElement("div", { className: "ppm-note-list" }, /* @__PURE__ */ React8.createElement("h3", null, "내 메모 · ", layout.notes.length), /* @__PURE__ */ React8.createElement("small", null, "지도에서 메모를 끌어 이동할 수 있어요. 배치 초기화는 메모 위치를 유지해요."), shownNotes.map((note) => /* @__PURE__ */ React8.createElement("article", { className: "ppm-note", "data-selected": selectedNote?.note_id === note.note_id, key: note.note_id }, /* @__PURE__ */ React8.createElement("small", null, noteAnchorLabel(note)), /* @__PURE__ */ React8.createElement("textarea", { "aria-label": `메모 ${note.note_id}`, value: note.text, disabled: !editable, onChange: (e) => {
    const text5 = e.target.value;
    edit((l) => ({ ...l, notes: l.notes.map((n) => n.note_id === note.note_id ? { ...n, text: text5 } : n) }));
  } }), /* @__PURE__ */ React8.createElement("div", { className: "ppm-actions" }, /* @__PURE__ */ React8.createElement("label", null, /* @__PURE__ */ React8.createElement("input", { type: "checkbox", checked: note.done, disabled: !editable, onChange: (e) => {
    const done = e.target.checked;
    edit((l) => ({ ...l, notes: l.notes.map((n) => n.note_id === note.note_id ? { ...n, done } : n) }));
  } }), " 완료"), /* @__PURE__ */ React8.createElement("small", null, [...note.text].length, "/2000자"), pendingDeleteNoteId === note.note_id ? /* @__PURE__ */ React8.createElement("div", { className: "ppm-note-delete-confirm", role: "group", "aria-label": "메모 삭제 확인" }, /* @__PURE__ */ React8.createElement("small", null, "이 메모를 초안에서 삭제합니다. 서버 반영은 ‘명시 저장’ 후입니다."), /* @__PURE__ */ React8.createElement("div", { className: "ppm-note-delete-actions" }, /* @__PURE__ */ React8.createElement("button", { autoFocus: true, onClick: cancelNoteDeletion }, "취소"), /* @__PURE__ */ React8.createElement("button", { className: "ppm-note-delete", disabled: !editable, onClick: confirmNoteDeletion }, "삭제"))) : /* @__PURE__ */ React8.createElement("button", { ref: (button) => {
    if (button) deleteButtonRefs.current.set(note.note_id, button);
    else deleteButtonRefs.current.delete(note.note_id);
  }, disabled: !editable, onClick: () => setPendingDeleteNoteId(note.note_id) }, "메모 삭제")))), !layout.notes.length ? /* @__PURE__ */ React8.createElement("p", null, "아직 메모가 없습니다.") : null) : null))), /* @__PURE__ */ React8.createElement("div", { className: "ppm-surface", hidden: surfaceMode !== "holdings" }, /* @__PURE__ */ React8.createElement(
    PortfolioHoldingsList,
    {
      holdings: state.holdings,
      selectedTickers: state.selectedTickers,
      unsupportedCount: state.unsupportedCount,
      phase: state.phase,
      theme
    }
  ), state.error ? /* @__PURE__ */ React8.createElement("p", { className: "ppm-warning", role: "alert" }, "보유종목 또는 지도 자료를 확인하지 못했습니다. (", state.error, ")") : null));
}

// output/member-map-integration-20260927/PortfolioMapReview.entry.tsx
/** @preserve User-approved review-only member map. Preserve the published site and existing member data.
 * Uses the existing authenticated candidate unchanged; no embedded session or fixture holdings.
 */
/**
 * @preserve
 * @framerIntrinsicWidth 1200
 * @framerIntrinsicHeight 820
 * @framerSupportedLayoutWidth any-prefer-fixed
 * @framerSupportedLayoutHeight auto
 */
function PublicPortfolioMapReview({ minHeight = 820, style }) {
  const isStatic = useIsStaticRenderer();
  return /* @__PURE__ */ React9.createElement("div", { style: { ...style, position: "relative", width: "100%", minHeight, boxSizing: "border-box" } }, isStatic ? /* @__PURE__ */ React9.createElement("section", { "aria-label": "회원 지도 검수용" }, /* @__PURE__ */ React9.createElement("h2", null, "회원 지도 검수용"), /* @__PURE__ */ React9.createElement("p", null, "실제 미리보기에서 로그인 후 보유종목과 저장 기록을 불러옵니다. 공개 사이트는 바꾸지 않습니다.")) : /* @__PURE__ */ React9.createElement(PublicPortfolioMap, null));
}
addPropertyControls(PublicPortfolioMapReview, {
  minHeight: { type: ControlType.Number, title: "최소 높이", defaultValue: 820, min: 480, max: 1200, step: 20 }
});
export {
  PublicPortfolioMapReview as default
};

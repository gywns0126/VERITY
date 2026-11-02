// @ts-nocheck
// Generated from review/member-map/site-entry.tsx; preserve existing data, notes, positions and unsaved drafts.
import * as SiteReact from "react";
import { addPropertyControls as sitePropertyControls } from "framer";
// review/member-map/site-entry.tsx
import * as React3 from "react";
import { addPropertyControls as addPropertyControls2, useIsStaticRenderer as useIsStaticRenderer2 } from "framer";

// site-map:existing-map
import * as React6 from "react";
import { addPropertyControls, ControlType, useIsStaticRenderer } from "framer";
import * as React5 from "react";
import * as React4 from "react";
import * as React2 from "react";
import { useEffect as useEffect22, useState as useState32 } from "react";
var __defProp = Object.defineProperty;
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);
var SECTION_ORDER = [
  { id: "business", title: "\uC0AC\uC5C5\xB7\uACBD\uC7C1\uB825" },
  { id: "finance", title: "\uC2E4\uC801\xB7\uC7AC\uBB34" },
  { id: "valuation", title: "\uAC00\uACA9\xB7\uAC00\uCE58 \uBE44\uAD50" },
  { id: "events", title: "\uCD5C\uADFC \uBCC0\uD654\xB7\uC77C\uC815" },
  { id: "holders", title: "\uC8FC\uC8FC\xB7\uC790\uBCF8 \uBC30\uBD84" },
  { id: "risks", title: "\uC704\uD5D8\xB7\uD655\uC778\uD560 \uC9C8\uBB38" }
];
var sectionTitle = (id) => SECTION_ORDER.find((section) => section.id === id).title;
var text = (value) => typeof value === "string" ? value.trim() : value == null ? "" : String(value).trim();
var record = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : {};
var list = (value) => Array.isArray(value) ? value.filter((item) => item && typeof item === "object") : [];
var hasValue = (value) => value !== void 0 && value !== null && text(value) !== "";
var isFailure = (value) => !!record(value).__infoMapError;
var factTitle = (key) => ({ PER: "PER (\uC8FC\uAC00\uC218\uC775\uBE44\uC728)", PBR: "PBR (\uC8FC\uAC00\uC21C\uC790\uC0B0\uBE44\uC728)", PSR: "PSR (\uC8FC\uAC00\uB9E4\uCD9C\uBE44\uC728)", ROE: "ROE (\uC790\uAE30\uC790\uBCF8\uC774\uC775\uB960)", BPS: "BPS (\uC8FC\uB2F9\uC21C\uC790\uC0B0)", EPS: "EPS (\uC8FC\uB2F9\uC21C\uC774\uC775)", FCF: "FCF (\uC789\uC5EC\uD604\uAE08\uD750\uB984)", "D/E": "D/E (\uBD80\uCC44\uBE44\uC728)" })[key] || key;
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
      topic: sectionId === "valuation" ? "\uAC00\uACA9\uACFC \uBE44\uAD50\uD558\uB294 \uC9C0\uD45C" : sectionId === "holders" ? "\uC8FC\uC8FC \uD658\uC6D0" : sectionId === "risks" ? "\uC704\uD5D8 \uCC38\uACE0 \uC9C0\uD45C" : "\uC218\uC775\uC131\xB7\uC7AC\uBB34 \uC9C0\uD45C",
      explanation: [factExplanation(note) || "\uBC1C\uD589 \uC885\uBAA9 \uB9AC\uD3EC\uD2B8\uC5D0 \uC81C\uACF5\uB41C \uC9C0\uD45C\uC785\uB2C8\uB2E4.", calculation && `\uACC4\uC0B0 \uAE30\uC900: ${calculation}`, key === "Altman-Z" && "\uD1B5\uACC4\uBAA8\uD615 \uC9C0\uD45C\uC774\uBA70 \uAE30\uC5C5\uC758 \uC548\uC804\uC774\uB098 \uBD80\uB3C4\uB97C \uD655\uC815\uD558\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4."].filter(Boolean).join("\n"),
      asOf: factAsOf(note),
      source: sourceLabel(record(note).source, "\uBC1C\uD589 \uC885\uBAA9 \uB9AC\uD3EC\uD2B8"),
      url: safeHttpLink(record(note).source_url || record(note).url),
      relationship: "unknown"
    };
  });
}
function readySection(id, items, message) {
  return { id, title: sectionTitle(id), items, state: items.some((item) => item.kind !== "question") ? "ready" : "empty", ...message ? { message } : {} };
}
var periodOrder = (row5) => `${text(row5.end) || "0000-00-00"}\0${text(row5.year).padStart(8, "0")}`;
function uniqueAnnual(rows2) {
  const unique3 = /* @__PURE__ */ new Map();
  for (const row5 of rows2.slice().sort((a, b) => periodOrder(a).localeCompare(periodOrder(b)))) unique3.set(`${text(row5.start)}\0${text(row5.end)}\0${text(row5.year)}`, row5);
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
  if (failed) return errorSection("business", "\uC885\uBAA9 \uC815\uBCF4 \uC694\uCCAD\uC5D0 \uC2E4\uD328\uD588\uC2B5\uB2C8\uB2E4.");
  const overview = record(slice.business_overview);
  const report = record(slice.report);
  const excerpt = text(overview.text);
  const items = excerpt ? [{
    id: "business-overview",
    title: "\uC0AC\uC5C5 \uAC1C\uC694",
    topic: "\uBB34\uC5C7\uC73C\uB85C \uB3C8\uC744 \uBC84\uB098",
    explanation: excerpt,
    asOf: text(overview.filed_at) || void 0,
    source: sourceLabel(overview.source, "DART \uC0AC\uC5C5\uBCF4\uACE0\uC11C"),
    url: safeHttpLink(overview.url),
    relationship: "direct"
  }] : [];
  const business = text(report.business);
  if (!excerpt && business) items.push({ id: "business-report", title: "\uC0AC\uC5C5 \uC124\uBA85", topic: "\uBB34\uC5C7\uC73C\uB85C \uB3C8\uC744 \uBC84\uB098", explanation: business, source: "\uBC1C\uD589 \uC885\uBAA9 \uB9AC\uD3EC\uD2B8", relationship: "unknown" });
  const peer = record(report.peer), company = record(report.overview);
  const industry = [text(peer.sector) || text(company.sector) || text(report.gics_ko) || text(report.gics), text(peer.industry)].filter(Boolean);
  if (industry.length) items.push({ id: "industry", title: "\uC5C5\uC885 \uBD84\uB958", topic: "\uC5B4\uB5A4 \uC2DC\uC7A5\uC5D0 \uC18D\uD558\uB098", explanation: industry.join(" \xB7 "), source: "\uBC1C\uD589 \uC885\uBAA9 \uB9AC\uD3EC\uD2B8", relationship: "unknown" });
  const chain = record(report.supply_chain), seen = /* @__PURE__ */ new Set();
  list(chain.snippets).forEach((row5, index) => {
    const snippet = text(row5.snippet);
    if (!snippet || seen.has(snippet)) return;
    seen.add(snippet);
    items.push({ id: `customer-${index}`, title: `${text(row5.anchor) || "\uACE0\uAC1D\xB7\uACF5\uAE09\uB9DD"} \xB7 \uBC1C\uCDCC ${index + 1}`, topic: "\uB204\uAD6C\uC640 \uAC70\uB798\uD558\uB098", explanation: snippet, source: [text(chain.report_nm), text(chain.note) || "\uC0AC\uC5C5\uBCF4\uACE0\uC11C \uBC1C\uCDCC"].filter(Boolean).join(" \xB7 "), asOf: text(chain.rcept_dt) || void 0, url: safeHttpLink(chain.source_url), relationship: "direct" });
  });
  return readySection("business", items, items.length ? "\uC0AC\uC5C5 \uC124\uBA85\xB7\uAC70\uB798\uCC98 \uBC1C\uCDCC\uC785\uB2C8\uB2E4. \uACBD\uC7C1 \uC6B0\uC704\uAC00 \uC785\uC99D\uB410\uB2E4\uB294 \uB73B\uC740 \uC544\uB2D9\uB2C8\uB2E4." : "\uC0AC\uC5C5 \uC6D0\uBB38\uC774 \uC81C\uACF5\uB418\uC9C0 \uC54A\uC558\uC2B5\uB2C8\uB2E4.");
}
function financeSection(slice, failed) {
  if (failed) return errorSection("finance", "\uC885\uBAA9 \uC815\uBCF4 \uC694\uCCAD\uC5D0 \uC2E4\uD328\uD588\uC2B5\uB2C8\uB2E4.");
  const report = record(slice.report);
  const periods = list(record(report.financial_evidence).periods);
  const annual = periods.filter((row5) => text(row5.period_kind) === "annual" && text(row5.currency) && text(row5.fs_div) && (Number.isFinite(row5.revenue) || Number.isFinite(row5.op) || Number.isFinite(row5.net)));
  const evidenceGroups = annual.reduce((groups2, row5) => {
    const key = `${text(row5.currency)}\0${text(row5.fs_div)}`;
    groups2[key] = [...groups2[key] || [], row5];
    return groups2;
  }, {});
  const evidenceSeries = Object.values(evidenceGroups).map(uniqueAnnual).sort((a, b) => b.length - a.length || periodOrder(b[b.length - 1] || {}).localeCompare(periodOrder(a[a.length - 1] || {})))[0] || [];
  const latestEvidence = evidenceSeries[evidenceSeries.length - 1];
  const legacyUSAnnual = /^(US|NASDAQ|NYSE|AMEX)$/.test(text(slice.market).toUpperCase());
  const fallbackGroups = list(report.fin_series).filter((row5) => (text(row5.period_kind) === "annual" || legacyUSAnnual && !text(row5.period_kind) && Number.isInteger(row5.year)) && text(row5.currency) && (Number.isFinite(row5.revenue) || Number.isFinite(row5.op) || Number.isFinite(row5.net))).reduce((groups2, row5) => {
    const currency = text(row5.currency);
    groups2[currency] = [...groups2[currency] || [], row5];
    return groups2;
  }, {});
  const fallbackSeries = Object.values(fallbackGroups).map(uniqueAnnual).sort((a, b) => b.length - a.length || periodOrder(b[b.length - 1] || {}).localeCompare(periodOrder(a[a.length - 1] || {})))[0] || [];
  const verifiedSeries = latestEvidence ? evidenceSeries : fallbackSeries;
  const latest = latestEvidence || verifiedSeries[verifiedSeries.length - 1];
  const income = latest ? [{
    id: "annual-income",
    title: "\uCD5C\uADFC \uC5F0\uAC04 \uC2E4\uC801",
    topic: "\uC5BC\uB9C8\uB098 \uBC8C\uC5C8\uB098",
    explanation: [text(latest.fs_div) === "CFS" ? "\uC5F0\uACB0 \uC7AC\uBB34\uC81C\uD45C" : text(latest.fs_div) === "OFS" ? "\uBCC4\uB3C4 \uC7AC\uBB34\uC81C\uD45C" : "", text(latest.filed) ? `\uC81C\uCD9C ${text(latest.filed)}` : ""].filter(Boolean).join(" \xB7 ") || "\uD68C\uACC4\uC5F0\uB3C4\uBCC4 \uAE08\uC561\uC785\uB2C8\uB2E4. \uC6D0\uBB38 \uD1B5\uD654\uB97C \uC720\uC9C0\uD558\uBA70 \uC815\uD655\uD55C \uAE08\uC561\uC740 \uC790\uC138\uD788 \uBCF4\uAE30\uC5D0\uC11C \uD655\uC778\uD560 \uC218 \uC788\uC5B4\uC694.",
    asOf: text(latest.start) && text(latest.end) ? `${text(latest.start)} ~ ${text(latest.end)}` : hasValue(latest.year) ? `${text(latest.year)} \uD68C\uACC4\uC5F0\uB3C4` : void 0,
    source: latestEvidence ? sourceLabel(record(report.financial_evidence).source, "\uC7AC\uBB34\uC81C\uD45C \uC6D0\uBB38") : "\uBC1C\uD589 \uC885\uBAA9 \uB9AC\uD3EC\uD2B8",
    url: safeHttpLink(latest.source_url),
    relationship: latestEvidence ? "direct" : "unknown",
    rows: [["\uB9E4\uCD9C", latest.revenue], ["\uC601\uC5C5\uC774\uC775", latest.op], ["\uC21C\uC774\uC775", latest.net]].filter(([, value]) => Number.isFinite(value)).map(([label2, value]) => ({ label: label2, value: money(value, latest.currency) })),
    chart: verifiedSeries.slice(-6).filter((row5) => Number.isFinite(row5.revenue)).map((row5) => ({ label: text(row5.year), value: row5.revenue })),
    unit: text(latest.currency)
  }] : [];
  const financials = record(report.financials);
  const groups = list(financials.groups).map((group, index) => ({
    id: `statement-${index}`,
    title: text(group.title) || "\uC7AC\uBB34\uC81C\uD45C",
    topic: /현금/.test(text(group.title)) ? "\uD604\uAE08\uC774 \uB0A8\uB098" : /상태/.test(text(group.title)) ? "\uC7AC\uBB34 \uAD6C\uC870\uB294 \uC5B4\uB5A4\uAC00" : "\uC2E4\uC801\uC758 \uC138\uBD80 \uD56D\uBAA9",
    explanation: "\uBC1C\uD589 \uB9AC\uD3EC\uD2B8\uC758 \uC7AC\uBB34\uC81C\uD45C \uC694\uC57D\uC785\uB2C8\uB2E4. \uD45C\uC2DC \uB2E8\uC704\uC640 \uAE30\uC900 \uAE30\uAC04\uC744 \uC6D0\uC790\uB8CC\uC640 \uD568\uAED8 \uD655\uC778\uD558\uC138\uC694.",
    asOf: text(financials.period) || void 0,
    source: "\uBC1C\uD589 \uC885\uBAA9 \uB9AC\uD3EC\uD2B8",
    relationship: "unknown",
    rows: list(group.rows).filter((row5) => text(row5.k) && hasValue(row5.v)).map((row5) => ({ label: text(row5.k), value: text(row5.v) }))
  })).filter((item) => item.rows.length > 0);
  const items = [...income, ...factItems(report, "finance"), ...groups];
  return readySection("finance", items, items.length ? void 0 : "\uC7AC\uBB34 \uC9C0\uD45C\uAC00 \uC81C\uACF5\uB418\uC9C0 \uC54A\uC558\uC2B5\uB2C8\uB2E4.");
}
function valuationSection(slice, failed) {
  if (failed) return errorSection("valuation", "\uC885\uBAA9 \uC815\uBCF4 \uC694\uCCAD\uC5D0 \uC2E4\uD328\uD588\uC2B5\uB2C8\uB2E4.");
  const report = record(slice.report), peer = record(report.peer);
  const items = factItems(report, "valuation");
  const rows2 = list(peer.rows).filter((row5) => text(row5.key) && hasValue(row5.value) && hasValue(row5.median));
  if (rows2.length) items.push({
    id: "peer-comparison",
    title: "\uAC19\uC740 \uBD84\uB958 \uAE30\uC5C5\uC758 \uC911\uC559\uAC12",
    topic: "\uBB34\uC5C7\uACFC \uBE44\uAD50\uD558\uB098",
    explanation: [text(peer.sector), hasValue(peer.n) ? `\uC9C0\uD45C\uBCC4 \uBE44\uAD50 \uD45C\uBCF8 \uCD5C\uB300 ${text(peer.n)}\uAC1C \uAE30\uC5C5 (\uAC01 \uC9C0\uD45C\uC758 \uD45C\uBCF8 \uC218\uB294 \uBBF8\uC81C\uACF5)` : "\uBE44\uAD50 \uAE30\uC5C5 \uC218 \uBBF8\uC81C\uACF5", text(peer.note), "\uC911\uC559\uAC12\uC740 \uD06C\uAE30\uC21C \uAC00\uC6B4\uB370 \uAC12\uC785\uB2C8\uB2E4. \uAC1C\uBCC4 \uC9C0\uD45C\uC758 \uB3D9\uC77C \uAE30\uC900\uC77C\xB7\uAE30\uAC04\uC740 \uD655\uC778\uB418\uC9C0 \uC54A\uC558\uC73C\uBA70, \uB0AE\uAC70\uB098 \uB192\uB2E4\uB294 \uC774\uC720\uB9CC\uC73C\uB85C \uC800\uD3C9\uAC00\xB7\uACE0\uD3C9\uAC00\uB85C \uD310\uB2E8\uD558\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4."].filter(Boolean).join("\n"),
    rows: rows2.map((row5) => ({ label: factTitle(text(row5.key)), value: `\uAE30\uC5C5 ${text(row5.value)} / \uC911\uC559\uAC12 ${text(row5.median)}` })),
    source: "\uBC1C\uD589 \uC885\uBAA9 \uB9AC\uD3EC\uD2B8 \xB7 \uBE44\uAD50 \uC9D1\uACC4",
    asOf: text(peer.as_of) || void 0,
    relationship: "unknown"
  });
  return readySection("valuation", items, "\uC774 \uC870\uD68C\uC5D0\uB294 \uC2DC\uAC01\uC774 \uD655\uC778\uB41C \uC8FC\uAC00\xB7\uACFC\uAC70 \uAC00\uCE58\uD3C9\uAC00 \uBE44\uAD50\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4. \uC9C0\uD45C\uBCC4 \uAC00\uACA9\xB7\uC2E4\uC801 \uAE30\uC900\uC774 \uB2E4\uB97C \uC218 \uC788\uC5B4\uC694.");
}
function eventsSection(slice, news, sliceFailed, newsFailed) {
  const report = record(slice.report);
  const disclosures = list(report.disclosures).map((item, index) => ({
    id: `disclosure-${index}`,
    title: text(item.title) || "\uACF5\uC2DC",
    topic: "\uAE30\uC5C5\uC774 \uC54C\uB9B0 \uBCC0\uD654",
    explanation: text(item.filer) ? `\uC81C\uCD9C\uC778: ${text(item.filer)}` : "\uBC1C\uD589 \uC885\uBAA9 \uB9AC\uD3EC\uD2B8\uC758 \uACF5\uC2DC \uD56D\uBAA9\uC785\uB2C8\uB2E4.",
    asOf: text(item.date) || void 0,
    source: "\uACF5\uC2DC \uC6D0\uBB38",
    url: safeHttpLink(item.source_url),
    relationship: "direct",
    ...item.is_correction ? { reason: "\uC815\uC815\uACF5\uC2DC" } : {}
  }));
  const articles = list(news.items).map((item, index) => {
    const linkedDisclosure = text(record(item.related_disclosure).title);
    return {
      id: `news-${index}`,
      title: text(item.title) || "\uB274\uC2A4",
      topic: "\uBCF4\uB3C4\uB41C \uC18C\uC2DD \xB7 \uAD00\uACC4 \uD655\uC778 \uD544\uC694",
      explanation: linkedDisclosure ? `\uC5F0\uACB0 \uACF5\uC2DC \uD6C4\uBCF4: ${linkedDisclosure}. \uAC00\uAE4C\uC6B4 \uB0A0\uC9DC\uB85C \uC5F0\uACB0\uB41C \uD6C4\uBCF4\uC774\uBA70 \uAC19\uC740 \uC0AC\uAC74\uC73C\uB85C \uD655\uC778\uB418\uC9C0 \uC54A\uC558\uC2B5\uB2C8\uB2E4.` : "\uC81C\uBAA9 \uD68C\uC0AC\uBA85 \uC77C\uCE58 \uAE30\uC900\uC73C\uB85C \uC218\uC9D1\uB41C \uAE30\uC0AC\uC785\uB2C8\uB2E4. \uC2E4\uC81C \uC0AC\uC5C5 \uAD00\uB828\uC131\uC740 \uC6D0\uBB38\uC5D0\uC11C \uD655\uC778\uD558\uC138\uC694.",
      asOf: text(item.datetime) || void 0,
      source: sourceLabel(item.source, "\uB274\uC2A4 \uC6D0\uBB38"),
      url: safeHttpLink(item.url),
      relationship: "unknown"
    };
  });
  const schedules = list(report.calendar).map((item, index) => ({
    id: `schedule-${index}`,
    title: text(item.event) || "\uC77C\uC815",
    topic: "\uD655\uC778\uD560 \uC77C\uC815",
    explanation: [text(item.basis) || "\uBC1C\uD589 \uC885\uBAA9 \uB9AC\uD3EC\uD2B8\uC5D0 \uC81C\uACF5\uB41C \uC77C\uC815\uC785\uB2C8\uB2E4.", /예상|패턴|자체계산/.test(text(item.event) + text(item.basis)) ? "\uC608\uC0C1 \uC77C\uC815\uC774\uBA70 \uD655\uC815 \uBC1C\uD45C\uC77C\uC774 \uC544\uB2D9\uB2C8\uB2E4." : "\uD655\uC815 \uC5EC\uBD80\uB294 \uC6D0\uBB38\uC5D0\uC11C \uD655\uC778\uD558\uC138\uC694."].join("\n"),
    asOf: text(item.date) || void 0,
    source: "\uBC1C\uD589 \uC885\uBAA9 \uB9AC\uD3EC\uD2B8",
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
  const problems = [sliceFailed && "\uACF5\uC2DC\xB7\uC77C\uC815\uC744 \uBD88\uB7EC\uC624\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4.", newsFailed && "\uB274\uC2A4\uB97C \uBD88\uB7EC\uC624\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4. \uC774 \uC885\uBAA9\uC758 \uB274\uC2A4 \uC81C\uACF5 \uBC94\uC704\uB3C4 \uD655\uC778\uC774 \uD544\uC694\uD569\uB2C8\uB2E4."].filter(Boolean).join(" ");
  if (!items.length && (sliceFailed || newsFailed)) return errorSection("events", problems);
  return readySection("events", items, problems || "\uAC19\uC740 \uC6D0\uBB38 \uC8FC\uC18C\uB9CC \uD55C \uD56D\uBAA9\uC73C\uB85C \uBB36\uC2B5\uB2C8\uB2E4. \uB0A0\uC9DC\xB7\uC81C\uBAA9\uC774 \uBE44\uC2B7\uD55C \uC790\uB8CC\uB294 \uAC19\uC740 \uC0AC\uAC74\uC73C\uB85C \uB2E8\uC815\uD558\uC9C0 \uC54A\uC544\uC694.");
}
function holdersSection(slice, failed, events) {
  if (failed) return errorSection("holders", "\uC885\uBAA9 \uC815\uBCF4 \uC694\uCCAD\uC5D0 \uC2E4\uD328\uD588\uC2B5\uB2C8\uB2E4.");
  const report = record(slice.report), ownership = record(report.ownership), dividends = record(report.dividends);
  const shareholders = list(ownership.shareholders).filter((holder) => text(holder.name) && hasValue(holder.pct));
  const keys2 = ["family_pct", "latest_pct", "n_13d", "n_13g", "total", "window_total"].filter((key) => hasValue(ownership[key]));
  const summaryRows = keys2.map((key) => ({ label: key === "family_pct" ? "\uCD1D\uC218\uC77C\uAC00 \uC9C0\uBD84" : key === "latest_pct" ? "\uCD5C\uC2E0 \uC9C0\uBD84\uC728" : key === "n_13d" ? "13D \uAC74\uC218" : key === "n_13g" ? "13G \uAC74\uC218" : key === "total" ? "\uACF5\uC2DC \uAC74\uC218" : "\uC870\uD68C \uCC3D \uACF5\uC2DC \uAC74\uC218", value: key.endsWith("pct") ? `${text(ownership[key])}%` : text(ownership[key]) }));
  const holderRows = shareholders.map((holder) => ({ label: [text(holder.name), text(holder.type)].filter(Boolean).join(" \xB7 "), value: `${text(holder.pct)}%` }));
  const items = keys2.length || shareholders.length ? [{
    id: "ownership-summary",
    title: "\uBCF4\uC720\xB7\uC9C0\uBD84 \uC694\uC57D",
    topic: "\uB204\uAC00 \uBCF4\uC720\uD558\uB098",
    explanation: [text(ownership.note), hasValue(ownership.fiscal_year) ? `\uAE30\uC900 \uD68C\uACC4\uC5F0\uB3C4: ${text(ownership.fiscal_year)}` : "", text(ownership.collected_at) && `\uC790\uB8CC \uC218\uC9D1\uC77C: ${text(ownership.collected_at)} (\uBCF4\uC720 \uAE30\uC900\uC77C\uACFC \uB2E4\uB97C \uC218 \uC788\uC74C)`].filter(Boolean).join(" \xB7 ") || "\uBC1C\uD589 \uC885\uBAA9 \uB9AC\uD3EC\uD2B8\uC5D0 \uC81C\uACF5\uB41C \uBCF4\uC720\xB7\uC9C0\uBD84 \uC815\uBCF4\uC785\uB2C8\uB2E4.",
    source: text(ownership.kind) || "\uBC1C\uD589 \uC885\uBAA9 \uB9AC\uD3EC\uD2B8",
    asOf: text(ownership.collected_at) || void 0,
    relationship: "unknown",
    rows: holderRows.length ? holderRows : summaryRows
  }] : [];
  const dividendRows = list(dividends.recent).filter((row5) => hasValue(row5.dps) && text(row5.record_date));
  if (dividendRows.length) items.push({
    id: "dividend-history",
    title: "\uBC30\uB2F9 \uC774\uB825",
    topic: "\uC8FC\uC8FC\uC5D0\uAC8C \uC5B4\uB5BB\uAC8C \uB3CC\uB824\uC8FC\uB098",
    explanation: [text(dividends.note), "\uBC30\uB2F9\uAE30\uC900\uC77C\uACFC \uC9C0\uAE09\uC77C\uC744 \uAD6C\uBCC4\uD569\uB2C8\uB2E4. \uBC30\uB2F9\uAE30\uC900\uC77C\uC740 \uBC30\uB2F9\uB77D\uC77C\uC774 \uC544\uB2D9\uB2C8\uB2E4."].filter(Boolean).join("\n"),
    rows: dividendRows.map((row5) => ({ label: `\uAE30\uC900 ${text(row5.record_date)} \xB7 \uC9C0\uAE09 ${text(row5.pay_date) || "\uBBF8\uC81C\uACF5"}`, value: `${text(row5.dps)}\uC6D0/\uC8FC` })),
    asOf: text(dividends.source_bas_dt) || void 0,
    source: text(dividends.source) || "\uBC1C\uD589 \uC885\uBAA9 \uB9AC\uD3EC\uD2B8",
    relationship: "unknown"
  });
  items.push(...factItems(report, "holders"));
  const capital = events.items.filter((item) => item.id.startsWith("disclosure-") && /배당|자기주식|유상증자|무상증자|전환사채|신주인수권|소유상황|대량보유/.test(item.title));
  if (capital.length) items.push({ id: "capital-events", title: "\uC8FC\uC8FC\xB7\uC790\uBCF8 \uAD00\uB828 \uACF5\uC2DC", topic: "\uC9C0\uBD84\xB7\uC8FC\uC2DD \uC218\uC758 \uBCC0\uD654", explanation: "\uACF5\uC2DC \uC81C\uBAA9\uC73C\uB85C \uBD84\uB958\uD55C \uD56D\uBAA9\uC785\uB2C8\uB2E4. \uAC70\uB798 \uC2E4\uD589\xB7\uD76C\uC11D \uADDC\uBAA8\xB7\uC0AC\uC5C5 \uC601\uD5A5\uC740 \uC6D0\uBB38 \uD655\uC778\uC774 \uD544\uC694\uD569\uB2C8\uB2E4.", source: "\uACF5\uC2DC \uC81C\uBAA9", relationship: "direct", references: capital.map((item) => ({ sectionId: "events", itemId: item.id, label: `${item.title} \xB7 ${item.asOf || "\uB0A0\uC9DC \uBBF8\uC81C\uACF5"}` })) });
  return readySection("holders", items, items.length ? void 0 : "\uBCF4\uC720\xB7\uBC30\uB2F9\xB7\uC790\uBCF8 \uAD00\uB828 \uC790\uB8CC\uAC00 \uC81C\uACF5\uB418\uC9C0 \uC54A\uC558\uC2B5\uB2C8\uB2E4.");
}
function risksSection(slice, failed, sections) {
  if (failed) return errorSection("risks", "\uAE30\uC5C5 \uC790\uB8CC \uC870\uD68C\uC5D0 \uC2E4\uD328\uD574 \uD655\uC778 \uC9C8\uBB38\uC744 \uAD6C\uC131\uD558\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4.");
  const report = record(slice.report), overhang = record(report.overhang);
  const items = factItems(report, "risks");
  const riskRows = [["\uBC1C\uD589\uACB0\uC815 \uACF5\uC2DC \uC218", overhang.count], ["\uC7A0\uC7AC \uD76C\uC11D \uBE44\uC728", hasValue(overhang.dilution_pct) ? `${text(overhang.dilution_pct)}%` : void 0], ["\uBC1C\uD589 \uAC00\uB2A5 \uC8FC\uC2DD \uC218", overhang.issuable_shares]].filter(([, value]) => hasValue(value)).map(([label2, value]) => ({ label: text(label2), value: text(value) }));
  if (riskRows.length) items.push({ id: "potential-dilution", title: "\uC804\uD658\uC0AC\uCC44\xB7\uC2E0\uC8FC\uC778\uC218\uAD8C\uBD80\uC0AC\uCC44", topic: "\uC8FC\uC2DD \uC218\uAC00 \uB298\uC5B4\uB0A0 \uC218 \uC788\uB098", explanation: [text(overhang.note), text(overhang.window) && `\uC870\uD68C \uBC94\uC704: ${text(overhang.window)}`, "\uBC1C\uD589\uACB0\uC815 \uAE30\uC900 \uC7A0\uC7AC\uCE58\uC774\uBA70 \uC2E4\uC81C \uC804\uD658\xB7\uBC1C\uD589\uB41C \uC218\uB7C9\uC73C\uB85C \uD574\uC11D\uD558\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4."].filter(Boolean).join("\n"), source: "\uBC1C\uD589 \uC885\uBAA9 \uB9AC\uD3EC\uD2B8 \xB7 \uACF5\uC2DC \uC9D1\uACC4", relationship: "unknown", rows: riskRows, reason: "\uC7A0\uC7AC \uD76C\uC11D \uD655\uC778" });
  const ref = (sectionId, predicate) => (sections.find((section) => section.id === sectionId)?.items || []).filter(predicate).map((item) => ({ sectionId, itemId: item.id, label: item.title }));
  const question = (id, title, explanation, references = []) => items.push({ id, title, explanation, kind: "question", topic: "\uD655\uC778 \uC9C8\uBB38 \xB7 \uC704\uD5D8 \uBC1C\uC0DD \uC0AC\uC2E4 \uC544\uB2D8", source: "\uC54C\uD30C\uB124\uC2A4\uD2B8 \xB7 \uC790\uB8CC \uD655\uC778 \uC9C8\uBB38", relationship: "unknown", references });
  const corrections = ref("events", (item) => item.reason === "\uC815\uC815\uACF5\uC2DC");
  if (corrections.length) question("question-correction", "\uC815\uC815 \uC804\uD6C4 \uBB34\uC5C7\uC774 \uB2EC\uB77C\uC84C\uB098\uC694?", "\uC815\uC815 \uC0AC\uC720\xB7\uAE08\uC561\xB7\uAE30\uAC04\uC744 \uC6D0\uBB38\uC5D0\uC11C \uBE44\uAD50\uD558\uC138\uC694. \uC815\uC815 \uC0AC\uC2E4\uB9CC\uC73C\uB85C \uC545\uC7AC\uB77C\uACE0 \uD310\uB2E8\uD558\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.", corrections);
  const customers = ref("business", (item) => item.id.startsWith("customer-"));
  if (customers.length) question("question-customers", "\uD2B9\uC815 \uACE0\uAC1D\uC5D0 \uB9E4\uCD9C\uC774 \uC9D1\uC911\uB3FC \uC788\uB098\uC694?", "\uAC70\uB798\uCC98 \uC774\uB984\uB9CC\uC73C\uB85C \uB9E4\uCD9C \uBE44\uC911\uC744 \uC54C \uC218 \uC5C6\uC2B5\uB2C8\uB2E4. \uACE0\uAC1D\uBCC4 \uBE44\uC911\xB7\uACC4\uC57D \uC870\uAC74\uC744 \uD655\uC778\uD558\uC138\uC694.", customers);
  const financials = ref("finance", (item) => item.id === "annual-income" || /현금|부채|D\/E|FCF/.test(item.title));
  question("question-cash", "\uC774\uC775\uC774 \uD604\uAE08\uC73C\uB85C \uC774\uC5B4\uC9C0\uACE0, \uBD80\uCC44\uB97C \uAC10\uB2F9\uD560 \uC218 \uC788\uB098\uC694?", "\uC2E4\uC801\xB7\uD604\uAE08\uD750\uB984\xB7\uBD80\uCC44 \uB9CC\uAE30 \uC790\uB8CC\uB97C \uD568\uAED8 \uD655\uC778\uD558\uC138\uC694. \uC790\uB8CC\uAC00 \uC5C6\uAC70\uB098 \uBE44\uC728 \uD558\uB098\uAC00 \uB0AE\uB2E4\uB294 \uC774\uC720\uB85C \uC704\uD5D8\uC774 \uC5C6\uB2E4\uACE0 \uD310\uB2E8\uD558\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.", financials);
  const undated = sections.flatMap((section) => section.items.filter((item) => item.value && !item.asOf).map((item) => ({ sectionId: section.id, itemId: item.id, label: item.title })));
  if (undated.length) question("question-basis", "\uC22B\uC790\uC758 \uAE30\uC900\uC77C\xB7\uACC4\uC0B0 \uAE30\uAC04\uC774 \uAC19\uB098\uC694?", "\uAE30\uC900\uC77C\uC774 \uB530\uB85C \uC81C\uACF5\uB418\uC9C0 \uC54A\uC740 \uC9C0\uD45C\uAC00 \uC788\uC2B5\uB2C8\uB2E4. \uB9AC\uD3EC\uD2B8 \uC0DD\uC131 \uC2DC\uAC01\uC740 \uAC00\uACA9\xB7\uC7AC\uBB34\uC758 \uAE30\uC900\uC77C\uC774 \uC544\uB2D9\uB2C8\uB2E4. \uAC01 \uACC4\uC0B0 \uC124\uBA85\uC744 \uD655\uC778\uD558\uC138\uC694.", undated);
  const peer = record(report.peer), classification = [peer.sector, peer.industry, record(report.overview).sector, report.gics, report.gics_ko].map(text).join(" ");
  if (/은행|\bbank(?:s|ing)?\b/i.test(classification)) question("question-industry", "\uB300\uCD9C \uAC74\uC804\uC131\uACFC \uC790\uBCF8 \uC5EC\uB825\uC740 \uC5B4\uB5A4\uAC00\uC694?", "\uC740\uD589 \uC5C5\uC885 \uD655\uC778 \uC9C8\uBB38: \uC5F0\uCCB4\uC728\xB7\uBD80\uC2E4\uCC44\uAD8C\xB7\uCDA9\uB2F9\uAE08\xB7\uC790\uBCF8\uBE44\uC728\uC744 \uAC19\uC740 \uAE30\uAC04\uC73C\uB85C \uD655\uC778\uD558\uC138\uC694. \uD574\uB2F9 \uC218\uCE58\uAC00 \uC774\uBC88 \uC9C0\uB3C4\uC5D0 \uC788\uB2E4\uACE0 \uAC00\uC815\uD558\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.");
  else if (/소프트웨어|software/i.test(classification)) question("question-industry", "\uBC18\uBCF5 \uB9E4\uCD9C\uACFC \uACE0\uAC1D \uC720\uC9C0\uAC00 \uD655\uC778\uB418\uB098\uC694?", "\uC18C\uD504\uD2B8\uC6E8\uC5B4 \uC5C5\uC885 \uD655\uC778 \uC9C8\uBB38: \uAD6C\uB3C5 \uB9E4\uCD9C\xB7\uACC4\uC57D \uC794\uC561\xB7\uACE0\uAC1D \uC720\uC9C0\uC728\uC758 \uC815\uC758\uC640 \uAE30\uAC04\uC744 \uC6D0\uBB38\uC5D0\uC11C \uD655\uC778\uD558\uC138\uC694.");
  else if (/반도체|제조|가전|Semiconductor|Manufactur|Consumer Electronics/i.test(classification)) question("question-industry", "\uC7AC\uACE0\xB7\uC124\uBE44\uD22C\uC790\uAC00 \uC218\uC694\uC640 \uD568\uAED8 \uC6C0\uC9C1\uC774\uB098\uC694?", "\uC81C\uC870\uC5C5 \uD655\uC778 \uC9C8\uBB38: \uC7AC\uACE0\xB7\uAC00\uB3D9\uB960\xB7\uC124\uBE44\uD22C\uC790\xB7\uC218\uC8FC \uAE30\uAC04\uC744 \uD568\uAED8 \uD655\uC778\uD558\uC138\uC694. \uD22C\uC790 \uADDC\uBAA8\uB9CC\uC73C\uB85C \uBBF8\uB798 \uB9E4\uCD9C\uC744 \uCD94\uC815\uD558\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.");
  return readySection("risks", items, "\uD655\uC778 \uC9C8\uBB38\uC740 \uC870\uC0AC \uC548\uB0B4\uC774\uBA70 \uC704\uD5D8 \uBC1C\uC0DD \uC0AC\uC2E4\uC774 \uC544\uB2D9\uB2C8\uB2E4. \uC18C\uC1A1\xB7\uB9CC\uAE30\xB7\uBC18\uB300 \uADFC\uAC70\uB97C \uBE60\uC9D0\uC5C6\uC774 \uAC80\uD1A0\uD55C \uACB0\uACFC\uB3C4 \uC544\uB2D9\uB2C8\uB2E4.");
}
function normalizeInfoMap(ticker, slice, news, usDetail) {
  const requested = text(ticker).toUpperCase(), rawSlice = record(slice), rawNews = record(news);
  const rawReport = record(rawSlice.report);
  const mismatched = (value) => !!text(value) && text(value).toUpperCase() !== requested;
  const sliceFailure = isFailure(slice) ? text(slice.__infoMapError) : text(rawSlice.status) && text(rawSlice.status) !== "ok" ? `\uC751\uB2F5 \uC0C1\uD0DC: ${text(rawSlice.status)}` : mismatched(rawSlice.ticker) || mismatched(rawReport.ticker) ? "\uC751\uB2F5 \uD2F0\uCEE4 \uBD88\uC77C\uCE58" : "";
  const newsFailure = isFailure(news) ? text(news.__infoMapError) : text(rawNews.error) ? text(rawNews.error) : text(rawNews.status) && text(rawNews.status) !== "ok" ? `\uC751\uB2F5 \uC0C1\uD0DC: ${text(rawNews.status)}` : mismatched(rawNews.code) || mismatched(rawNews.ticker) ? "\uC751\uB2F5 \uD2F0\uCEE4 \uBD88\uC77C\uCE58" : "";
  const sliceFailed = !!sliceFailure, newsFailed = !!newsFailure;
  const sliceData = sliceFailed ? {} : rawSlice, newsData = newsFailed ? {} : rawNews, report = record(sliceData.report), extra = record(usDetail);
  const market2 = text(report.market) || text(sliceData.market);
  const marketUpper = market2.toUpperCase();
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
    market: market2,
    country,
    sections,
    coverage: { ok: sections.length - missing2.length, total: sections.length, missing: missing2 }
  };
}
var PUBLIC_DATA_BASE = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com";
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
  const date2 = /* @__PURE__ */ new Date(`${value.slice(0, 10)}T00:00:00Z`);
  if (!Number.isFinite(date2.getTime()) || date2.toISOString().slice(0, 10) !== value.slice(0, 10)) return void 0;
  return value;
}
function acceptedPayload(value, ticker, family) {
  const raw = record2(value), report = record2(raw.report);
  const mismatch = (value2) => !!text2(value2) && text2(value2).toUpperCase() !== ticker;
  if (raw.__infoMapError || text2(raw.status) && text2(raw.status) !== "ok" || family === "news" && raw.error || mismatch(raw.ticker) || mismatch(family === "slice" ? report.ticker : raw.code)) return {};
  return raw;
}
function disclosureSource(row5, url) {
  const supplied = text2(row5.source);
  if (supplied) return supplied;
  if (url.hostname === "dart.fss.or.kr") return "DART \uC804\uC790\uACF5\uC2DC";
  if (url.hostname === "sec.gov" || url.hostname.endsWith(".sec.gov")) return "SEC EDGAR";
  return "\uACF5\uC2DC \uC6D0\uBB38";
}
function publication(row5) {
  for (const key of ["datetime", "published_at", "time", "as_of", "date"])
    if (label(row5[key])) return label(row5[key]);
  return void 0;
}
function newsRecord(row5, collection) {
  const url = sourceUrl(row5.url) || sourceUrl(row5.link);
  if (!url) return void 0;
  return {
    kind: "news",
    title: text2(row5.title) || "\uB274\uC2A4",
    ...label(row5.title_ko) ? { translatedTitle: label(row5.title_ko) } : {},
    source: text2(row5.source) || "\uB274\uC2A4 \uC6D0\uBB38",
    url,
    publishedAt: publication(row5),
    sourceCollection: collection,
    isCorrection: null,
    isBackfill: null
  };
}
function normalizePortfolioSources(ticker, slice, news) {
  const code = text2(ticker).toUpperCase(), map = normalizeInfoMap(code, slice, news);
  const report = record2(acceptedPayload(slice, code, "slice").report);
  const articles = acceptedPayload(news, code, "news"), newsCandidates = [];
  const eventSources = [];
  for (const row5 of rows(report.disclosures)) {
    const url = sourceUrl(row5.source_url);
    if (!url) continue;
    const parsed = new URL(url), receipts = parsed.searchParams.getAll("rcpNo");
    const dartMain = parsed.hostname === "dart.fss.or.kr" && !parsed.port && parsed.pathname === "/dsaf001/main.do";
    const dartReceipt = dartMain && receipts.length === 1 && /^\d{14}$/.test(receipts[0]) ? receipts[0] : void 0;
    const receipt = typeof row5.rcept_no === "string" && /^\d{14}$/.test(row5.rcept_no) ? row5.rcept_no : void 0;
    const receiptConflict = dartMain && !dartReceipt || row5.rcept_no != null && row5.rcept_no !== "" && (!receipt || receipt !== dartReceipt);
    eventSources.push({
      kind: "disclosure",
      title: text2(row5.title) || "\uACF5\uC2DC",
      source: disclosureSource(row5, parsed),
      url,
      publishedAt: receiptConflict ? void 0 : label(row5.date),
      observedAt: receiptConflict ? void 0 : observation(row5.detected_at),
      ...label(row5.label) ? { label: label(row5.label) } : {},
      ...label(row5.filer) ? { filer: label(row5.filer) } : {},
      sourceCollection: "stock_slice.disclosures",
      receiptNumber: receiptConflict ? void 0 : receipt,
      ...receiptConflict ? { receiptConflict: true } : {},
      isCorrection: receiptConflict ? null : flag(row5.is_correction),
      isBackfill: receiptConflict ? null : flag(row5.is_backfill)
    });
  }
  for (const row5 of rows(articles.items)) {
    const item = newsRecord(row5, "stock_news.items");
    if (item) eventSources.push(item);
  }
  for (const row5 of rows(articles.us_headlines)) {
    const item = newsRecord(row5, "portfolio.us_headlines");
    if (item) newsCandidates.push(item);
  }
  return { ...map, eventSources, ...newsCandidates.length ? { newsCandidates } : {} };
}
async function boundedJson(url, signal) {
  const controller = new AbortController();
  const abort = () => controller.abort(signal?.reason);
  if (signal?.aborted) throw signal.reason || new Error("\uC694\uCCAD\uC774 \uCDE8\uC18C\uB418\uC5C8\uC2B5\uB2C8\uB2E4.");
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
    if (timedOut) throw new Error("\uC815\uBCF4 \uC694\uCCAD \uC2DC\uAC04\uC774 \uCD08\uACFC\uB418\uC5C8\uC2B5\uB2C8\uB2E4.");
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
}
var usNewsCache;
function publicUsNews(signal) {
  if (signal?.aborted) return Promise.reject(signal.reason || new Error("\uC694\uCCAD\uC774 \uCDE8\uC18C\uB418\uC5C8\uC2B5\uB2C8\uB2E4."));
  const now = Date.now();
  if (!usNewsCache || usNewsCache.expiresAt <= now) {
    const request = boundedJson(`${PUBLIC_DATA_BASE}/portfolio.json`).catch((error) => {
      if (usNewsCache?.request === request) usNewsCache = void 0;
      throw error;
    });
    usNewsCache = { expiresAt: now + 3e5, request };
  }
  if (!signal) return usNewsCache.request;
  return new Promise((resolve, reject) => {
    const abort = () => reject(signal.reason || new Error("\uC694\uCCAD\uC774 \uCDE8\uC18C\uB418\uC5C8\uC2B5\uB2C8\uB2E4."));
    signal.addEventListener("abort", abort, { once: true });
    usNewsCache.request.then(
      (value) => {
        signal.removeEventListener("abort", abort);
        resolve(value);
      },
      (error) => {
        signal.removeEventListener("abort", abort);
        reject(error);
      }
    );
  });
}
async function fetchPortfolioSources(ticker, apiBase, signal) {
  const code = text2(ticker).toUpperCase(), base = text2(apiBase).replace(/\/+$/, "");
  const isKr = /^\d{6}$/.test(code), overview = isKr ? "&overview=1" : "";
  const newsUrl = isKr ? `${base}/api/stock_news?code=${encodeURIComponent(code)}` : `${PUBLIC_DATA_BASE}/portfolio.json`;
  const results = await Promise.allSettled([
    boundedJson(`${base}/api/stock_slice?ticker=${encodeURIComponent(code)}${overview}`, signal),
    isKr ? boundedJson(newsUrl, signal) : publicUsNews(signal)
  ]);
  if (signal?.aborted) throw signal.reason || new Error("\uC694\uCCAD\uC774 \uCDE8\uC18C\uB418\uC5C8\uC2B5\uB2C8\uB2E4.");
  const input = (result) => result.status === "fulfilled" ? result.value : { __infoMapError: text2(result.reason?.message) || "\uC694\uCCAD \uC2E4\uD328" };
  return normalizePortfolioSources(code, input(results[0]), input(results[1]));
}
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
function marketKind(value) {
  if (/^(KR|KOSPI|KOSDAQ)$/i.test(value.trim())) return "KR";
  if (/^(US|NASDAQ|NYSE|AMEX)$/i.test(value.trim())) return "US";
  return null;
}
function verificationApproved(input, market2) {
  const approval = record3(input.verification);
  return approval?.publicDisplayApproved === true && approval.market === market2 && approval.session === "closed" && !!text3(approval.reference);
}
function verifiedMarket(input) {
  const approval = record3(input.verification), market2 = approval?.market;
  return (market2 === "KR" || market2 === "US") && verificationApproved(input, market2) ? market2 : null;
}
function verifiedOhlc(payload, ticker, priceDate, price) {
  const row5 = record3(record3(payload.ohlc)?.[ticker]);
  if (!row5) return null;
  const date2 = dateOnly(row5.date), open = row5.open, high = row5.high, low = row5.low, close = row5.close;
  if (date2 !== priceDate || !positive(open) || !positive(high) || !positive(low) || !positive(close) || close !== price || high < Math.max(open, low, close) || low > Math.min(open, high, close)) return null;
  return { date: date2, open, high, low, close };
}
function normalizePortfolioCloseQuote(ticker, market2, input) {
  if (!input) return missing("\uC5F0\uACB0\uB41C \uC885\uAC00 \uC790\uB8CC\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.");
  const kind = marketKind(market2) || (!market2.trim() ? verifiedMarket(input) : null);
  const symbol = ticker.trim().toUpperCase();
  if (!kind || (kind === "KR" ? !/^\d{6}$/.test(symbol) : !/^[A-Z0-9][A-Z0-9.-]{0,9}$/.test(symbol)))
    return missing("\uC774 \uC2DC\uC7A5\uC758 \uC885\uAC00 \uC790\uB8CC\uB294 \uC544\uC9C1 \uC5F0\uACB0\uD558\uC9C0 \uC54A\uC558\uC2B5\uB2C8\uB2E4.");
  if (kind === "US" && !verificationApproved(input, kind))
    return missing("\uACF5\uAC1C \uD45C\uC2DC\xB7\uC7AC\uBC30\uD3EC \uC774\uC6A9 \uAD8C\uD55C\uC774 \uD655\uC778\uB41C \uBBF8\uAD6D \uC885\uAC00 \uC790\uB8CC\uAC00 \uD544\uC694\uD569\uB2C8\uB2E4.");
  if (input.verification && !verificationApproved(input, kind))
    return missing("\uC885\uAC00 \uC790\uB8CC\uC758 \uC2DC\uC7A5\xB7\uC7A5 \uB9C8\uAC10\xB7\uC774\uC6A9 \uAD8C\uD55C \uD655\uC778\uC774 \uC77C\uCE58\uD558\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.");
  const payload = record3(input.payload);
  if (!payload) return missing("\uC885\uAC00 \uC790\uB8CC \uD615\uC2DD\uC744 \uD655\uC778\uD560 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4.");
  const meta = record3(Object.hasOwn(payload, "_meta") ? payload._meta : payload.meta);
  if (!meta) return missing("\uC885\uAC00\uC758 \uAE30\uC900 \uC815\uBCF4\uB97C \uD655\uC778\uD560 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4.");
  if (Object.hasOwn(payload, "_meta") && Object.hasOwn(payload, "meta")) {
    const legacy = record3(payload.meta);
    if (!legacy || ["as_of", "prev_as_of", "source", "basis"].some((key) => legacy[key] !== meta[key]))
      return missing("\uC885\uAC00 \uC790\uB8CC\uC758 \uAE30\uC900 \uC815\uBCF4\uAC00 \uC11C\uB85C \uB2E4\uB985\uB2C8\uB2E4.");
  }
  const priceDate = dateOnly(meta.as_of), source = text3(meta.source), basis = text3(meta.basis);
  const closeBasis = /종가|(?:^|\W)close(?:d)?(?:\W|$)/i.test(basis);
  const explicitlyNotRealtime = /실시간\s*(?:아님|아니|비제공)|not\s+real[ -]?time|non[ -]?real[ -]?time/i.test(basis);
  const realtimeBasis = /장중|intraday|last trade|current price/i.test(basis) || !explicitlyNotRealtime && /실시간|real[ -]?time/i.test(basis);
  if (!priceDate || !source || !closeBasis || realtimeBasis) return missing("\uC885\uAC00\xB7\uAE30\uC900\uC77C\xB7\uCD9C\uCC98\uB97C \uD655\uC778\uD560 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4.");
  const price = record3(payload.prices)?.[symbol];
  if (!positive(price)) return missing("\uC774 \uC885\uBAA9\uC758 \uC885\uAC00\uAC00 \uC81C\uACF5\uB418\uC9C0 \uC54A\uC558\uC2B5\uB2C8\uB2E4.");
  const expectedDate = dateOnly(input.latestCompletedTradingDate);
  if (expectedDate && priceDate > expectedDate) return missing("\uC885\uAC00 \uAE30\uC900\uC77C\uC774 \uD655\uC778\uB41C \uB9C8\uC9C0\uB9C9 \uAC70\uB798\uC77C\uBCF4\uB2E4 \uB4A4\uC5D0 \uC788\uC2B5\uB2C8\uB2E4.");
  const priorDate = dateOnly(meta.prev_as_of), prior = record3(payload.prev)?.[symbol];
  const previousDate = priorDate && priorDate < priceDate && positive(prior) ? priorDate : null;
  const previousPrice = previousDate ? prior : null;
  const reported = record3(payload.chg)?.[symbol];
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
    expectedDate,
    ohlc: verifiedOhlc(payload, symbol, priceDate, price)
  };
}
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
  const reason = kind === "news" ? "\uC774 \uC885\uBAA9\uC758 \uB274\uC2A4 \uC870\uD68C\uC5D0 \uD3EC\uD568" : kind === "disclosure" ? "\uC774 \uC885\uBAA9\uC758 \uACF5\uC2DC \uC790\uB8CC\uC5D0 \uD3EC\uD568" : kind === "business" ? "\uC774 \uC885\uBAA9\uC758 \uC0AC\uC5C5 \uC790\uB8CC\uC5D0 \uD3EC\uD568" : "\uC774 \uC885\uBAA9\uC758 \uC870\uD68C \uC790\uB8CC\uC5D0 \uD3EC\uD568";
  const sourceRecords = sectionId === "events" ? unique(records.filter((row5) => row5.url === item.url)) : [];
  const conflict = sourceRecords.some((row5) => row5.receiptConflict);
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
    isCorrection: !conflict && (item.reason === "\uC815\uC815\uACF5\uC2DC" || /\[(?:기재|첨부|기타)?정정\]/.test(item.title)) ? true : null,
    sources: unique((item.sources || []).map((source) => ({ title: source.title, source: source.source, asOf: source.asOf, url: source.url }))),
    ...sourceRecords.length ? { sourceRecords } : {}
  };
}
function summarize(evidence) {
  const dates = evidence.flatMap((row5) => [
    row5.asOf,
    ...row5.sources.map((source) => source.asOf),
    ...(row5.sourceRecords || []).map((source) => source.publishedAt)
  ]);
  return {
    source: unique(evidence.flatMap((row5) => [row5.source, ...row5.sources.map((source) => source.source)])).join(" \xB7 "),
    // Conflicting or absent dates remain in evidence; do not invent a single representative date.
    asOf: dates.every((date2) => date2 === dates[0]) ? dates[0] : void 0,
    reason: unique(evidence.map((row5) => row5.reason)).join(" \xB7 "),
    confirmation: evidence.every((row5) => row5.confirmation === "confirmed") ? "confirmed" : "unknown",
    isCorrection: evidence.some((row5) => row5.isCorrection) ? true : null
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
    const labels2 = unique(rows2.map((row5) => ({ name: row5.name, market: row5.market })));
    companies.push({
      id: `company:${ticker}`,
      ticker,
      ...labels2[0],
      sections: companySections(rows2),
      ...closeInput ? { closeQuote: normalizePortfolioCloseQuote(
        ticker,
        labels2.every((label2) => /^(KR|KOSPI|KOSDAQ)$/i.test(label2.market.trim())) ? labels2[0].market : "",
        closeInput
      ) } : {}
    });
    for (const sectionId of SECTIONS) {
      const sections = rows2.flatMap((row5) => row5.sections.filter((section) => section.id === sectionId));
      const upstreamStates = unique(sections.map((section) => section.state));
      const messages = unique(sections.flatMap((section) => section.message ? [section.message] : []));
      const items = unique(rows2.flatMap((row5) => row5.sections.filter((section) => section.id === sectionId).flatMap((section) => section.items.filter((item) => item.kind !== "question").map((item) => evidenceFor(ticker, sectionId, item, row5.eventSources || [])))));
      let linkedItems = 0;
      for (const evidence of items) {
        const raw = evidence.url || "";
        if (!identities.has(raw)) identities.set(raw, portfolioDocumentIdentity(raw));
        const identity2 = await identities.get(raw);
        if (!identity2) continue;
        linkedItems++;
        const document2 = documentsById.get(identity2.id) || { ...identity2, evidence: [] };
        document2.evidence.push(evidence);
        documentsById.set(identity2.id, document2);
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
    const tickers = unique(evidence.map((row5) => row5.ticker));
    const content = unique(evidence.map(({ ticker: _ticker, sectionId: _section, reason: _reason, sourceRecords, ...row5 }) => ({
      ...row5,
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
      const associated = evidence.filter((row5) => row5.ticker === ticker);
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
      available: sources.filter((row5) => row5.state === "available").length,
      empty: sources.filter((row5) => row5.state === "empty").length,
      partial: sources.filter((row5) => row5.state === "partial").length,
      unavailable: sources.filter((row5) => row5.state === "unavailable").length,
      unknown: sources.filter((row5) => row5.state === "unknown").length,
      sources
    }
  };
}
async function fetchPortfolioMapGraph(tickers, apiBase, signal) {
  const codes = unique(tickers.map(normalizedTicker).filter(Boolean)), maps = [];
  let next = 0;
  const checkAbort = () => {
    if (signal?.aborted) throw signal.reason || new Error("\uC694\uCCAD\uC774 \uCDE8\uC18C\uB418\uC5C8\uC2B5\uB2C8\uB2E4.");
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
            message: "\uC885\uBAA9 \uC790\uB8CC\uB97C \uBD88\uB7EC\uC624\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4."
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
var ENDPOINT = "https://project-yw131.vercel.app/api/member_map_state?layout_origins=1";
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
function legacyValidMapDocument(value) {
  if (!fields(value, ["layouts"])) return false;
  const layouts = value.layouts;
  if (!Array.isArray(layouts) || layouts.length > 3 || !unique2(layouts.map((row5) => row5?.map_key))) return false;
  for (const layout of layouts) {
    if (!fields(layout, ["map_key", "positions", "notes", "marks"]) || typeof layout.map_key !== "string" || !MAP_KEY.test(layout.map_key)) return false;
    if (!Array.isArray(layout.positions) || layout.positions.length > 200 || !unique2(layout.positions.map((row5) => row5?.node_id))) return false;
    for (const row5 of layout.positions) {
      if (!fields(row5, ["node_id", "x", "y"]) || !identifier(row5.node_id) || !coordinate(row5.x) || !coordinate(row5.y)) return false;
    }
    if (!Array.isArray(layout.notes) || layout.notes.length > 100 || !unique2(layout.notes.map((row5) => row5?.note_id))) return false;
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
function validMapDocument(value) {
  if (!value || !Array.isArray(value.layouts)) return false;
  const legacy = { ...value, layouts: value.layouts.map((l) => {
    if (!l) return l;
    const { origins, ...rest } = l;
    return rest;
  }) };
  if (!legacyValidMapDocument(legacy)) return false;
  for (const l of value.layouts) {
    if (!l || !Object.hasOwn(l, "origins")) continue;
    if (!Array.isArray(l.origins) || l.origins.length > 200 || new Set(l.origins.map((o) => o?.node_id)).size !== l.origins.length || !Array.isArray(l.positions)) return false;
    const positions = new Map(l.positions.map((p) => [p.node_id, p]));
    for (const o of l.origins) {
      const p = positions.get(o?.node_id);
      if (!fields(o, ["node_id", "x", "y", "dx", "dy"]) || !identifier(o.node_id) || ![o.x, o.y, o.dx, o.dy].every(coordinate) || !p || p.x !== o.dx || p.y !== o.dy) return false;
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
  const layouts = copy(document2.layouts), index = layouts.findIndex((row5) => row5.map_key === mapKey);
  const initial = index < 0 ? { map_key: mapKey, positions: [], notes: [], marks: {} } : layouts[index];
  const next = change(initial);
  if (next.map_key !== mapKey) throw new Error("map-key-mismatch");
  if (index < 0) layouts.push(next);
  else layouts[index] = next;
  const result = { layouts };
  if (!validMapDocument(result)) throw new Error("invalid-document");
  return result;
}
var record5 = (value) => !!value && typeof value === "object" && !Array.isArray(value);
var identity = (value) => typeof value === "string" && !!value.trim() && value === value.trim();
function normalizeMapWatchlist(payload, ownerId) {
  if (!identity(ownerId)) throw new Error("invalid-watchlist-owner");
  if (!Array.isArray(payload)) throw new Error("invalid-watchlist-response");
  if (payload.length > 100) throw new Error("watchlist-response-limit");
  const groups = /* @__PURE__ */ new Set(), stocks = /* @__PURE__ */ new Map(), markets = /* @__PURE__ */ new Map();
  let totalItems = 0, unsupportedCount = 0;
  for (const group of payload) {
    if (!record5(group) || !identity(group.id) || !Array.isArray(group.items)) throw new Error("invalid-watchlist-response");
    if (group.user_id !== ownerId) throw new Error("watchlist-owner-mismatch");
    if (groups.has(group.id)) throw new Error("duplicate-watchlist-group");
    groups.add(group.id);
    totalItems += group.items.length;
    if (totalItems > 3e3) throw new Error("watchlist-response-limit");
    for (const item of group.items) {
      if (!record5(item) || typeof item.ticker !== "string" || typeof item.market !== "string" || item.name != null && typeof item.name !== "string") throw new Error("invalid-watchlist-response");
      if (item.group_id !== group.id) throw new Error("watchlist-group-mismatch");
      const ticker = item.ticker.trim().toUpperCase(), market2 = item.market.trim().toUpperCase();
      if (ticker && (market2 === "KR" || market2 === "US")) {
        const prior = markets.get(ticker);
        if (prior && prior !== market2) throw new Error("ambiguous-watchlist-market");
        markets.set(ticker, market2);
      }
      const supported = market2 === "KR" ? /^\d{6}$/.test(ticker) : market2 === "US" && /^[A-Z][A-Z0-9.-]{0,15}$/.test(ticker);
      if (!supported || item.type === "commodity") {
        unsupportedCount++;
        continue;
      }
      const key = `${market2}:${ticker}`;
      if (!stocks.has(key)) stocks.set(key, {
        ticker,
        market: market2,
        name: typeof item.name === "string" && item.name.trim() ? item.name.trim() : ticker
      });
    }
  }
  return { stocks: [...stocks.values()], unsupportedCount };
}
function aborted() {
  const error = new Error("watchlist-aborted");
  error.name = "AbortError";
  return error;
}
function abortable(pending, signal) {
  return new Promise((resolve, reject) => {
    const cancel = () => reject(aborted());
    signal.addEventListener("abort", cancel, { once: true });
    pending.then(
      (value) => {
        signal.removeEventListener("abort", cancel);
        resolve(value);
      },
      (error) => {
        signal.removeEventListener("abort", cancel);
        reject(error);
      }
    );
    if (signal.aborted) {
      signal.removeEventListener("abort", cancel);
      cancel();
    }
  });
}
async function fetchMapWatchlist(options) {
  const { api, getSession, ownerId, signal } = options;
  const current = () => {
    if (signal.aborted) throw aborted();
    if (!identity(ownerId)) throw new Error("invalid-watchlist-owner");
    const session = getSession();
    if (!session || typeof session.token !== "string" || !session.token.trim()) throw new Error("authentication-required");
    if (session.userId !== ownerId) throw new Error("session-changed");
    return session;
  };
  const token = current().token, fetcher = options.fetcher || fetch;
  const request = (requestToken) => fetcher(api.replace(/\/+$/, "") + "/api/watchgroups", {
    method: "GET",
    headers: { Authorization: "Bearer " + requestToken },
    signal,
    cache: "no-store",
    credentials: "omit",
    redirect: "error"
  });
  let response;
  try {
    response = await abortable(request(token), signal);
    const refreshedToken = current().token;
    if (response.status === 401 && refreshedToken !== token) {
      response = await abortable(request(refreshedToken), signal);
      current();
    }
    if (!response.ok) throw new Error(response.status === 401 ? "authentication-required" : "watchlist-unavailable");
    const payload = await abortable(response.json(), signal);
    current();
    return normalizeMapWatchlist(payload, ownerId);
  } catch (error) {
    try {
      current();
      throw error;
    } catch (failure2) {
      try {
        options.onDiagnostic?.(failure2, response);
      } catch {
      }
      throw failure2;
    }
  }
}
var invalid = () => new Error("\uC790\uB3D9 \uADFC\uAC70 \uC790\uB8CC\uC758 \uD615\uC2DD\uC744 \uD655\uC778\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694.");
var object = (v) => {
  if (!v || typeof v !== "object" || Array.isArray(v)) throw invalid();
  return v;
};
var list2 = (v, max = 1e4) => {
  if (!Array.isArray(v) || v.length > max) throw invalid();
  return v;
};
var text4 = (v, max = 300) => {
  if (typeof v !== "string" || !v.trim() || v.length > max || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f<>]/.test(v)) throw invalid();
  return v;
};
var entity = (v) => {
  const s = text4(v, 64);
  if (!/^(?:KR:\d{6}|US:[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,2})?)$/.test(s)) throw invalid();
  return s;
};
var exactKeys = (value, expected) => {
  if (Object.keys(value).sort().join("\n") !== [...expected].sort().join("\n")) throw invalid();
};
var isoDate = (value) => {
  const date2 = text4(value, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date2) || !Number.isFinite(Date.parse(date2)) || new Date(date2).toISOString().slice(0, 10) !== date2) throw invalid();
  return date2;
};
var publicExcerpt = (value) => {
  if (typeof value !== "string" || value.length > 1e4) throw invalid();
  text4(value.replaceAll("->", "\u2192"), 1e4);
  return value;
};
function sourceFor(value) {
  const s = object(value);
  if (s.kind === "local-structured-relation-candidate" && s.url === null && s.as_of === null)
    return { source: "\uACF5\uAC1C \uAD6C\uC870\uD654 \uC790\uB8CC \xB7 \uC6D0\uBB38 \uD655\uC778 \uD544\uC694", url: null, asOf: null, title: "\uAD00\uACC4 \uD6C4\uBCF4" };
  if (s.kind === "dart-structured-relation") {
    const receipt2 = text4(s.receipt_no, 14), year = text4(s.business_year, 4);
    const settlement = s.settlement_date === null ? null : text4(s.settlement_date, 10);
    if (!/^[0-9]{14}$/.test(receipt2) || !/^[0-9]{4}$/.test(year) || s.report_code !== "11011" || s.as_of !== null || !["hyslrSttus", "otrCprInvstmntSttus"].includes(s.endpoint) || s.url !== `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${receipt2}` || settlement !== null && (!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(settlement) || settlement.startsWith("0000-") || !Number.isFinite(Date.parse(settlement)) || new Date(settlement).toISOString().slice(0, 10) !== settlement)) throw invalid();
    return { source: "DART \xB7 \uACB0\uC0B0\uAE30\uC900", url: s.url, asOf: settlement, title: "\uAD00\uACC4 \uD6C4\uBCF4" };
  }
  const receipt = text4(s.receipt_no, 14), asOf = text4(s.as_of, 10);
  if (s.kind !== "dart-filing-excerpt" || !/^\d{14}$/.test(receipt) || s.url !== `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${receipt}` || !/^\d{4}-\d{2}-\d{2}$/.test(asOf) || !Number.isFinite(Date.parse(asOf)) || new Date(asOf).toISOString().slice(0, 10) !== asOf) throw invalid();
  return { source: "DART", url: s.url, asOf, title: text4(s.report_name) };
}
function participants(value) {
  const rows2 = list2(value, 1e3).map((value2) => {
    const p = object(value2);
    return { id: entity(p.id), role: text4(p.role, 80) };
  });
  if (!rows2.length || new Set(rows2.map((p) => p.id)).size !== rows2.length) throw invalid();
  return rows2;
}
function businessNames(value) {
  return value.split(/[,、/·ㆍ]|\s+및\s+|(?<=\))(?:와|과)\s*|(?:와|과)(?=\s)/).map((name) => name.trim()).filter(Boolean);
}
function normalizedLegalName(value) {
  return value.normalize("NFKC").replace(/\(주\d+\)|\(주석\d+\)/g, "").replace(/\s+/g, "").replace(/^(?:주식회사|\(주\))|(?:주식회사|\(주\))$/g, "");
}
var genericBusinessName = /^(?:국내및해외|국내외|국내|해외|글로벌|주요|대형|중소|기타|불특정|다수|일반|각종)*(?:기업|고객사?|거래처|매출처|구매처|유통업체|공급업체|업체|회사)$/;
var businessList = /^당사의\s*(?:주요\s*)?(?<label>매출처|고객사|구매처|공급업체)(?:는|로는)\s*(?<names>.+?)(?:\s*등)?(?:입니다|(?:이|가)\s*있습니다)\.$/;
var businessPurchase = /^당사의\s*(?:주요\s*)?원재료는\s*.+?이며\s*(?<names>.+?)(?:\s*등)?에서\s*(?:안정적으로\s*)?구매하고\s*있습니다\.$/;
var businessCompoundList = /^당사의\s*(?:주요\s*)?(?<label>매출처|고객사|구매처|공급업체)(?:는|로는)\s*(?<names>.+?)(?:\s*등)?\s*(?:이)?며,\s*(?<tail>.+)\.$/;
var businessDelivery = /^당사는\s*(?:(?:(?:국내|해외|국내외)\s*)?(?:주요\s*)?[A-Za-z가-힣]+(?:\s+[A-Za-z가-힣]+)?\s*(?:제조사|업체)인\s*)?(?<names>.+?)(?:\s*등)?에\s*(?<product>[A-Za-z0-9가-힣\s·ㆍ()+/\-]+?)(?:을|를)\s*(?:공급|납품)하고\s*(?:있습니다|있으며,\s*(?<tail>.+))\.$/;
var businessFromSupplier = /^(?:[●•]\s*)?당사는\s*(?:[A-Za-z0-9가-힣\s·ㆍ(),/\-]{1,120}(?:을|를|하여)\s+)?(?<names>[A-Za-z0-9가-힣&()+\-\s、/,·ㆍ]+?)(?:\s*등)?로부터\s*(?:구입(?:\([A-Za-z0-9가-힣\s·ㆍ/\-]{1,40}\))?하고\s*(?:있습니다|있으며,\s*(?<tail>.+))|(?:(?<supply_product>[A-Za-z0-9가-힣\s·ㆍ()+/\-]{1,80}?)(?:을|를)\s*)?공급받아\s*(?<received_tail>.+))\.$/;
var unresolvedBusinessScope = /예정|계획|추진|가능|가정|예시|예를|정의|경쟁|제품명|브랜드|타사|과거|이전|(?<![A-Za-z0-9가-힣])전기(?=$|\s|말|초|대비|기준|회계|분기|에는|의|와|에)|전년|작년|향후|않|아니|아닙|없|중단|종료|해지|취소|철회|중지|미확인|제외|만약|조건|경우|하지만|그러나|반면|실제로|여부|["'“”‘’]/;
var otherBusinessSubject = /종속|연결|그룹|계열/;
var bareDeliveryName = /^[A-Za-z0-9가-힣&()+\-\s]{1,80}$/;
var deliveryNameContext = /(?:에서|으로|하여|위해|통해|하고|하며|을|를)(?:\s|$)|(?:^|\s)(?:현재|경우|것|대한)(?:\s|$)/;
var deliveryProductContext = /공급|납품|구매|매입|받|하여|통해|위해|에서|에게|(?:을|를)(?:\s|$)/;
function businessQuote(role, quote3, rawName) {
  if (quote3 !== quote3.trim() || /[\r\n]/.test(quote3) || /[.!?]/.test(quote3.slice(0, -1)) || genericBusinessName.test(normalizedLegalName(rawName)) || unresolvedBusinessScope.test(quote3)) throw invalid();
  const parsed = businessCompoundList.exec(quote3) || businessDelivery.exec(quote3) || businessList.exec(quote3) || businessPurchase.exec(quote3) || businessFromSupplier.exec(quote3);
  if (!parsed?.groups) throw invalid();
  const { names, label: label2, product, supply_product, received_tail } = parsed.groups, delivery = product !== void 0;
  const tail = received_tail || parsed.groups.tail;
  const assertion = tail ? quote3.slice(0, -(tail.length + 1)) : quote3;
  const entries = businessNames(names), parsedRole = delivery || ["\uB9E4\uCD9C\uCC98", "\uACE0\uAC1D\uC0AC"].includes(label2) ? "customer" : "supplier";
  if (otherBusinessSubject.test(assertion) || !entries.length || entries.length > 12 || parsedRole !== role || !entries.includes(rawName)) throw invalid();
  const fromSupplier = /로부터/.test(parsed[0]) && label2 === void 0 && !delivery;
  const item = product || supply_product;
  if ((delivery || fromSupplier) && (entries.some((name) => !bareDeliveryName.test(name) || deliveryNameContext.test(name)) || delivery && !item?.trim() || item && ([...item.trim()].length > 80 || deliveryProductContext.test(item.trim())))) throw invalid();
}
var secList = /^Our (?:major |principal )?(customers|suppliers) (?:include|are) (.+)\.$/i;
var secFoundries = /(?:^|\.\s+)We utilize foundries, such as ([^;!?]+?), or [A-Za-z][A-Za-z0-9-]*, and ([^;!?]+?), or [A-Za-z][A-Za-z0-9-]*, to produce our semiconductor wafers\.(?:$|\s)/;
var secRisk = /\b(?:not|no|may|might|could|would|will|expect|plan|former|previous|potential|indirect|subsidiar\w*|affiliate\w*|competitor\w*|except|excluding|terminated|ceased|historical|if|unless|subject to|provided that|conditional\w*|contingent|pending|according to|states?|stated|said|says?|quot\w*|example|illustrat\w*)\b|["“”]/i;
function secLegalName(value) {
  return value.replace(/\s+/g, " ").trim().toLowerCase().replace(/,?\s+(?:incorporated|inc\.?|corporation|corp\.?|limited|ltd\.?)$/, "").trim();
}
function secQuote(role, quote, rawName) {
  const parsed = secList.exec(quote), foundries = secFoundries.exec(quote);
  if (!parsed && !foundries || quote !== quote.trim() || /[\r\n]/.test(quote) || secRisk.test(quote) || (foundries ? "supplier" : parsed[1].toLowerCase() === "customers" ? "customer" : "supplier") !== role) throw invalid();
  const entries = foundries ? [foundries[1], foundries[2]] : parsed[2].replace(/,\s+(Inc\.?|Ltd\.?|Corp\.?)\b/gi, " $1").split(/,\s*(?:and\s+)?|\s+and\s+/).map((name) => name.trim());
  if (!entries.length || entries.length > 12 || !secLegalName(rawName) || entries.some((name) => !(foundries ? /^[\p{L}\p{N}][\p{L}\p{N}&.,'’() -]{0,159}$/u : /^[\p{L}\p{N}][\p{L}\p{N}&.'’() -]{0,159}$/u).test(name)) || !entries.some((name) => secLegalName(name) === secLegalName(rawName))) throw invalid();
}
function parseAutomaticEvidence(payload, selected) {
  if (payload === void 0 || payload === null) return { relations: [], materials: [], commonMaterials: [] };
  const body = object(payload);
  if (body.schema !== "portfolio-auto-evidence-v1" || list2(body.verified_events).length) throw invalid();
  const ids = /* @__PURE__ */ new Set();
  const correctionSources = /* @__PURE__ */ new Set(), materialIssuers = /* @__PURE__ */ new Map();
  const relations = list2(body.relationships, 1e3).map((value) => {
    const r = object(value), id = text4(r.stable_id, 100), revision2 = text4(r.revision, 64);
    const reported = r.status === "accepted_reported";
    if (r.type === "reported-sec-counterparty") {
      exactKeys(r, ["stable_id", "revision", "type", "status", "verification", "snapshot_scope", "label", "participants", "source", "evidence"]);
      if (!/^relation:sec-role:[a-f0-9]{16}$/.test(id) || !/^[a-f0-9]{64}$/.test(revision2) || ids.has(id) || !reported || r.verification !== "reported-sec-excerpt" || r.snapshot_scope !== "reported-filing-period-not-current") throw invalid();
      const rawPeople = list2(r.participants, 2);
      rawPeople.forEach((value2) => {
        const p = object(value2);
        exactKeys(p, ["id", "role", "name"]);
        text4(p.name, 160);
      });
      const people2 = participants(rawPeople), issuer = rawPeople.find((p) => p.role === "document_issuer");
      const target = rawPeople.find((p) => p.role === "reported_customer" || p.role === "reported_supplier");
      if (people2.length !== 2 || !issuer || !target || people2.some((p) => !p.id.startsWith("US:")) || !people2.some((p) => selected.has(p.id))) throw invalid();
      const role2 = target.role === "reported_customer" ? "customer" : "supplier";
      const title2 = role2 === "customer" ? "SEC \uBCF4\uACE0\uC11C\uC0C1 \uB9E4\uCD9C\uCC98" : "SEC \uBCF4\uACE0\uC11C\uC0C1 \uACF5\uAE09\uCC98";
      if (r.label !== title2) throw invalid();
      const s = object(r.source), e = object(r.evidence);
      exactKeys(s, ["id", "kind", "cik", "accession", "as_of", "period_end", "form", "url", "document_issuer"]);
      const cik = text4(s.cik, 10), accession = text4(s.accession, 20), asOf = isoDate(s.as_of), period = isoDate(s.period_end);
      if (s.kind !== "sec-filing-excerpt" || !/^[0-9]{10}$/.test(cik) || Number(cik) === 0 || !/^[0-9]{10}-[0-9]{2}-[0-9]{6}$/.test(accession) || s.id !== `source:sec:${cik}:${accession}` || s.document_issuer !== issuer.id || !["10-K", "20-F"].includes(s.form) || period.startsWith("0000-") || period > asOf || asOf > (/* @__PURE__ */ new Date()).toISOString().slice(0, 10)) throw invalid();
      const url = text4(s.url, 300), base = `https://www.sec.gov/Archives/edgar/data/${Number(cik)}/${accession.replaceAll("-", "")}/`;
      if (!url.startsWith(base) || !/^[A-Za-z0-9_-]+\.html?$/.test(url.slice(base.length))) throw invalid();
      exactKeys(e, ["role", "raw_name", "quote", "paragraph_sha256", "document_sha256"]);
      const name = text4(e.raw_name, 160), quote = text4(e.quote, 1200);
      if (e.role !== role2 || name !== name.trim() || !/^[a-f0-9]{64}$/.test(text4(e.paragraph_sha256, 64)) || !/^[a-f0-9]{64}$/.test(text4(e.document_sha256, 64))) throw invalid();
      secQuote(role2, quote, name);
      ids.add(id);
      const issuerLabel = role2 === "customer" ? "\uB9E4\uCD9C\uCC98 \uACF5\uC2DC \uD68C\uC0AC" : "\uAD6C\uB9E4\uCC98 \uACF5\uC2DC \uD68C\uC0AC";
      const targetLabel = role2 === "customer" ? "\uACF5\uC2DC\uC0C1 \uB9E4\uCD9C\uCC98" : "\uACF5\uC2DC\uC0C1 \uACF5\uAE09\uCC98";
      return {
        id: `automatic:${id}`,
        read_revision: Number.parseInt(revision2.slice(0, 13), 16) + 1,
        title: title2,
        reported: true,
        reportedBasis: "business-period",
        reason: `\uACF5\uC2DC \uC791\uC131 \uD68C\uC0AC: ${issuer.name}. SEC ${s.form} \xB7 \uBCF4\uACE0\uAE30\uAC04 \uC885\uB8CC\uC77C ${period} \xB7 \uACF5\uAC1C \uC81C\uCD9C\uC77C ${asOf}. ${targetLabel}: ${name}. \uD604\uC7AC \uC720\uD6A8 \uC5EC\uBD80\xB7\uAC70\uB798 \uADDC\uBAA8\xB7\uC8FC\uAC00 \uC601\uD5A5\uC740 \uBBF8\uD655\uC778\uC774\uC5D0\uC694.
${quote}`,
        participants: people2.map((p) => p.id === issuer.id ? { ...p, name: issuer.name, roleLabel: issuerLabel } : { ...p, name: target.name, roleLabel: targetLabel }),
        source: `SEC \xB7 ${s.form}`,
        asOf,
        url
      };
    }
    if (r.verification === "reported-annual-table") {
      exactKeys(r, ["stable_id", "revision", "type", "status", "verification", "snapshot_scope", "label", "participants", "source", "evidence"]);
      if (!/^relation:annual-customer:[a-f0-9]{16}$/.test(id) || !/^[a-f0-9]{64}$/.test(revision2) || ids.has(id) || r.type !== "reported-business-counterparty" || !reported || r.snapshot_scope !== "reported-fiscal-year-not-current" || r.label !== "\uBCF4\uACE0\uC11C\uC0C1 \uACE0\uAC1D\uC0AC \uD6C4\uBCF4") throw invalid();
      const rawPeople = list2(r.participants, 2);
      rawPeople.forEach((p) => {
        exactKeys(object(p), ["id", "role", "name"]);
        text4(p.name, 160);
      });
      const people2 = participants(rawPeople), issuer = rawPeople.find((p) => p.role === "document_issuer");
      const target = rawPeople.find((p) => p.role === "reported_customer");
      if (people2.length !== 2 || !issuer || !target || !people2.some((p) => selected.has(p.id))) throw invalid();
      const s = object(r.source), e = object(r.evidence);
      exactKeys(s, ["id", "kind", "receipt_no", "as_of", "report_name", "document_issuer", "url", "artifact_observed_at", "revision"]);
      const receipt = text4(s.receipt_no, 14), asOf = isoDate(s.as_of), report = text4(s.report_name, 240);
      const match = report.match(/^(?:\[(?:기재정정|첨부정정|첨부추가)\])*사업보고서 \((\d{4})\.(0[1-9]|1[0-2])\)$/);
      const periodEnd = match ? new Date(Date.UTC(Number(match[1]), Number(match[2]), 0)).toISOString().slice(0, 10) : "";
      if (s.kind !== "dart-annual-report-table" || !/^\d{14}$/.test(receipt) || receipt.slice(0, 8) !== asOf.replaceAll("-", "") || s.id !== `source:dart:${receipt}` || s.document_issuer !== issuer.id || s.artifact_observed_at !== null || s.url !== `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${receipt}` || !/^[a-f0-9]{64}$/.test(text4(s.revision, 64)) || !match || asOf < periodEnd || asOf > (/* @__PURE__ */ new Date()).toISOString().slice(0, 10)) throw invalid();
      exactKeys(e, ["role", "raw_name", "quote", "owner_quote", "source_field", "field_sha256", "fiscal_year", "report_period_start", "report_period_end", "table_index", "header_row", "row_index", "column_index", "owner_row_index", "owner_rowspan", "customer_origin_row_index", "customer_rowspan", "archive_member", "archive_sha256", "xml_sha256"]);
      const name = text4(e.raw_name, 160), quote3 = text4(e.quote, 1200), owner = text4(e.owner_quote, 160);
      const start = isoDate(e.report_period_start), end = isoDate(e.report_period_end);
      if (e.role !== "customer" || e.source_field !== "annual_customer_table" || e.fiscal_year !== match[1] || start > end || end.slice(0, 7) !== `${match[1]}-${match[2]}` || end > asOf || normalizedLegalName(owner).toLowerCase() !== normalizedLegalName(issuer.name).toLowerCase() || normalizedLegalName(name).toLowerCase() !== normalizedLegalName(target.name).toLowerCase() || genericBusinessName.test(normalizedLegalName(name)) || name !== name.trim() || !businessNames(quote3.replace(/\s*등\s*$/, "")).includes(name) || !/^[a-f0-9]{64}$/.test(text4(e.archive_sha256, 64)) || !/^[a-f0-9]{64}$/.test(text4(e.xml_sha256, 64)) || e.field_sha256 !== e.xml_sha256 || text4(e.archive_member, 160) !== `${receipt}.xml`) throw invalid();
      for (const [key, max] of [["table_index", 1199], ["header_row", 499], ["row_index", 499], ["column_index", 39], ["owner_row_index", 499], ["customer_origin_row_index", 499]])
        if (!Number.isInteger(e[key]) || e[key] < 0 || e[key] > max) throw invalid();
      for (const key of ["owner_rowspan", "customer_rowspan"])
        if (!Number.isInteger(e[key]) || e[key] < 1 || e[key] > 100) throw invalid();
      if (e.row_index <= e.header_row || e.owner_row_index <= e.header_row || e.owner_row_index > e.row_index || e.row_index >= e.owner_row_index + e.owner_rowspan || e.owner_row_index + e.owner_rowspan > 500 || e.customer_origin_row_index < e.owner_row_index || e.customer_origin_row_index > e.row_index || e.row_index >= e.customer_origin_row_index + e.customer_rowspan || e.customer_origin_row_index + e.customer_rowspan > e.owner_row_index + e.owner_rowspan) throw invalid();
      ids.add(id);
      return {
        id: `automatic:${id}`,
        read_revision: Number.parseInt(revision2.slice(0, 13), 16) + 1,
        title: "\uBCF4\uACE0\uC11C\uC0C1 \uACE0\uAC1D\uC0AC",
        reported: true,
        reportedBasis: "business-period",
        reason: `\uACF5\uC2DC \uC791\uC131 \uD68C\uC0AC: ${issuer.name}. ${e.fiscal_year} \uD68C\uACC4\uC5F0\uB3C4 \xB7 ${report} \xB7 \uBCF4\uACE0\uAE30\uAC04 ${start}~${end} \xB7 \uACF5\uAC1C \uACF5\uC2DC\uC77C ${asOf}. \uD45C\uC5D0 \uAE30\uC7AC\uB41C \uACE0\uAC1D\uC0AC: ${name}. \uD604\uC7AC \uC720\uD6A8 \uC5EC\uBD80\xB7\uAC70\uB798 \uADDC\uBAA8\xB7\uC8FC\uAC00 \uC601\uD5A5\uC740 \uBBF8\uD655\uC778\uC774\uC5D0\uC694.
\uD68C\uC0AC: ${owner}
\uC8FC\uC694\uACE0\uAC1D: ${quote3}
\uC6D0\uBB38 \uD45C ${e.table_index + 1} \xB7 \uD589 ${e.row_index + 1} \xB7 \uC5F4 ${e.column_index + 1}`,
        participants: people2.map((p) => p.id === issuer.id ? { ...p, name: issuer.name, roleLabel: "\uACE0\uAC1D\uC0AC \uACF5\uC2DC \uD68C\uC0AC" } : { ...p, name: target.name, roleLabel: "\uACF5\uC2DC\uC0C1 \uACE0\uAC1D\uC0AC" }),
        source: "DART \xB7 \uC0AC\uC5C5\uBCF4\uACE0\uC11C \uD45C",
        asOf,
        url: s.url
      };
    }
    if (r.type === "reported-business-counterparty") {
      exactKeys(r, ["stable_id", "revision", "type", "status", "verification", "snapshot_scope", "label", "participants", "source", "evidence"]);
      if (!/^relation:business-role:[a-f0-9]{16}$/.test(id) || !/^[a-f0-9]{64}$/.test(revision2) || ids.has(id) || !reported || r.verification !== "reported-business-excerpt" || r.snapshot_scope !== "reported-fiscal-year-not-current") throw invalid();
      const rawPeople = list2(r.participants, 2);
      if (rawPeople.length !== 2) throw invalid();
      rawPeople.forEach((value2) => {
        const person = object(value2);
        exactKeys(person, person.role === "document_issuer" && Object.hasOwn(person, "name") ? ["id", "role", "name"] : ["id", "role"]);
      });
      const people2 = participants(rawPeople), issuer = people2.find((p) => p.role === "document_issuer");
      const counterparties = people2.filter((p) => p.role === "reported_customer" || p.role === "reported_supplier");
      if (!issuer || counterparties.length !== 1 || people2.filter((p) => p.role === "document_issuer").length !== 1 || !people2.some((p) => selected.has(p.id))) throw invalid();
      const rawIssuer = rawPeople.find((p) => p.role === "document_issuer");
      const issuerName = Object.hasOwn(rawIssuer, "name") ? text4(rawIssuer.name, 320) : void 0;
      if (issuerName !== void 0 && [...issuerName].length > 160) throw invalid();
      const target = counterparties[0], role2 = target.role === "reported_customer" ? "customer" : "supplier";
      const expectedTitle = role2 === "customer" ? "\uBCF4\uACE0\uC11C\uC0C1 \uB9E4\uCD9C\uCC98" : "\uBCF4\uACE0\uC11C\uC0C1 \uACF5\uAE09\uCC98";
      if (r.label !== expectedTitle) throw invalid();
      const rawSource2 = object(r.source);
      exactKeys(rawSource2, ["id", "kind", "receipt_no", "as_of", "report_name", "url", "document_issuer", "artifact_observed_at", "revision"]);
      const receipt = text4(rawSource2.receipt_no, 14), asOf = isoDate(rawSource2.as_of), report = text4(rawSource2.report_name, 240);
      const reportMatch = report.match(/^(?:\[(?:기재정정|첨부정정|첨부추가)\])*사업보고서 \((\d{4})\.(0[1-9]|1[0-2])\)$/);
      const reportEnd = reportMatch ? `${reportMatch[1]}-${reportMatch[2]}-${String(new Date(Date.UTC(Number(reportMatch[1]), Number(reportMatch[2]), 0)).getUTCDate()).padStart(2, "0")}` : "";
      if (rawSource2.kind !== "dart-filing-excerpt" || !/^\d{14}$/.test(receipt) || rawSource2.document_issuer !== issuer.id || receipt.slice(0, 8) !== asOf.replaceAll("-", "") || asOf > (/* @__PURE__ */ new Date()).toISOString().slice(0, 10) || rawSource2.url !== `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${receipt}` || !reportMatch || asOf < reportEnd || rawSource2.id !== `source:dart:${receipt}` || rawSource2.artifact_observed_at !== null || !/^[a-f0-9]{64}$/.test(text4(rawSource2.revision, 64))) throw invalid();
      const evidence2 = object(r.evidence);
      exactKeys(evidence2, ["role", "raw_name", "quote", "char_start", "char_end", "source_field", "field_sha256", "fiscal_year", "published_excerpt_truncated"]);
      const evidenceRole = text4(evidence2.role, 8), name = text4(evidence2.raw_name, 320), quote3 = text4(evidence2.quote, 1200);
      const fiscalYear = text4(evidence2.fiscal_year, 4), quoteLength = [...quote3].length;
      if (evidenceRole !== role2 || name !== name.trim() || [...name].length > 160 || quoteLength > 600 || evidence2.source_field !== "business_overview" || !/^[a-f0-9]{64}$/.test(text4(evidence2.field_sha256, 64)) || !/^\d{4}$/.test(fiscalYear) || fiscalYear !== reportMatch[1] || Number(fiscalYear) > Number(asOf.slice(0, 4)) || typeof evidence2.published_excerpt_truncated !== "boolean" || !Number.isInteger(evidence2.char_start) || evidence2.char_start < 0 || !Number.isInteger(evidence2.char_end) || evidence2.char_end > 600 || evidence2.char_end - evidence2.char_start !== quoteLength) throw invalid();
      businessQuote(role2, quote3, name);
      ids.add(id);
      correctionSources.add(`${rawSource2.url}|${issuer.id}`);
      const issuerLabel = role2 === "customer" ? "\uB9E4\uCD9C\uCC98 \uACF5\uC2DC \uD68C\uC0AC" : "\uAD6C\uB9E4\uCC98 \uACF5\uC2DC \uD68C\uC0AC";
      const targetLabel = role2 === "customer" ? "\uACF5\uC2DC\uC0C1 \uB9E4\uCD9C\uCC98" : "\uACF5\uC2DC\uC0C1 \uACF5\uAE09\uCC98";
      return {
        id: `automatic:${id}`,
        read_revision: Number.parseInt(revision2.slice(0, 13), 16) + 1,
        title: expectedTitle,
        reported: true,
        reportedBasis: "business-period",
        reason: `\uACF5\uC2DC \uC791\uC131 \uD68C\uC0AC: ${issuerName || issuer.id}. ${fiscalYear} \uD68C\uACC4\uC5F0\uB3C4 \xB7 ${report} \xB7 \uACF5\uAC1C \uACF5\uC2DC\uC77C ${asOf}. ${targetLabel}: ${name}. \uD604\uC7AC \uC720\uD6A8 \uC5EC\uBD80\xB7\uAC70\uB798 \uADDC\uBAA8\xB7\uC8FC\uAC00 \uC601\uD5A5\uC740 \uBBF8\uD655\uC778\uC774\uC5D0\uC694.
${quote3}`,
        participants: people2.map((p) => p.id === issuer.id ? { ...p, ...issuerName === void 0 ? {} : { name: issuerName }, roleLabel: issuerLabel } : { ...p, name, roleLabel: targetLabel }),
        source: "DART \xB7 \uC0AC\uC5C5\uBCF4\uACE0\uC11C",
        asOf,
        url: rawSource2.url
      };
    }
    if (r.type === "reported-parent-company") {
      if (!/^relation:filing-parent:[a-f0-9]{8}$/.test(id) || !/^[a-f0-9]{64}$/.test(revision2) || ids.has(id) || !reported || r.verification !== "reported-filing-excerpt" || r.snapshot_scope !== "reported-period-not-current") throw invalid();
      ids.add(id);
      const people2 = participants(r.participants), rawSource2 = object(r.source), source2 = sourceFor(rawSource2), evidence2 = object(r.evidence);
      const quote3 = text4(evidence2.quote, 600), name = text4(evidence2.raw_name, 160), period = text4(evidence2.as_of_phrase, 120);
      if (people2.length !== 2 || !people2.some((p) => selected.has(p.id)) || people2.filter((p) => p.role === "from").length !== 1 || people2.filter((p) => p.role === "to").length !== 1 || rawSource2.kind !== "dart-filing-excerpt" || people2.find((p) => p.role === "to")?.id !== rawSource2.document_issuer || evidence2.role !== "reported-parent" || evidence2.source_field !== "related_party_text" || !quote3.includes(name) || !quote3.includes(period) || !quote3.includes("\uC9C0\uBC30\uAE30\uC5C5") || !Number.isInteger(evidence2.char_start) || evidence2.char_start < 0 || !Number.isInteger(evidence2.char_end) || evidence2.char_end - evidence2.char_start !== [...quote3].length || evidence2.char_end > 3e4 || !/^[a-f0-9]{64}$/.test(text4(evidence2.field_sha256, 64))) throw invalid();
      correctionSources.add(`${source2.url}|${rawSource2.document_issuer}`);
      return {
        id: `automatic:${id}`,
        read_revision: Number.parseInt(revision2.slice(0, 13), 16) + 1,
        title: "\uBCF4\uACE0\uC11C\uC0C1 \uC9C0\uBC30\uAE30\uC5C5",
        reported: true,
        reportedBasis: "filing-period",
        reason: `${period}\uC758 \uC9C0\uBC30\uAE30\uC5C5 \uD45C\uB97C \uD655\uC778\uD588\uC5B4\uC694. \uACF5\uC2DC\uC77C ${source2.asOf}. \uD604\uC7AC \uAD00\uACC4\xB7\uC9C0\uBD84\uC728\xB7\uC8FC\uAC00 \uC601\uD5A5\uC740 \uBBF8\uD655\uC778\uC774\uC5D0\uC694.
${quote3}`,
        participants: people2.map((p) => p.role === "from" ? { ...p, name } : p),
        source: source2.source,
        asOf: source2.asOf,
        url: source2.url
      };
    }
    if (!/^relation:group-structure:[a-f0-9]{8}$/.test(id) || !/^[a-f0-9]{64}$/.test(revision2) || ids.has(id) || !reported && r.status !== "accepted_candidate") throw invalid();
    ids.add(id);
    const people = participants(r.participants), source = sourceFor(r.source), evidence = object(r.evidence);
    if (people.length !== 2 || !people.some((p) => selected.has(p.id))) throw invalid();
    const title = r.type === "reported-equity-investment" ? reported ? "\uACF5\uC2DC\uC0C1 \uC9C0\uBD84 \uD22C\uC790" : "\uC9C0\uBD84 \uD22C\uC790 \uD6C4\uBCF4" : r.type === "reported-major-shareholder-entry" ? reported ? "\uACF5\uC2DC\uC0C1 \uC8FC\uC694 \uC8FC\uC8FC" : "\uC8FC\uC694 \uC8FC\uC8FC \uD6C4\uBCF4" : null;
    if (!title) throw invalid();
    const rawSource = object(r.source);
    if (rawSource.kind === "dart-structured-relation") {
      const majorHolder = r.type === "reported-major-shareholder-entry";
      const issuer = entity(rawSource.document_issuer);
      if (r.verification !== (reported ? "reported-source-row" : "candidate-source-row-receipt") || rawSource.endpoint !== (majorHolder ? "hyslrSttus" : "otrCprInvstmntSttus") || people.find((p) => p.role === (majorHolder ? "to" : "from"))?.id !== issuer) throw invalid();
    }
    const role = text4(evidence.role, 160), pct = evidence.reported_ownership_pct;
    if (pct !== void 0 && (typeof pct !== "number" || !Number.isFinite(pct) || pct < 0 || pct > 100)) throw invalid();
    const pendingReasons = {
      "missing-source-row": "\uC6D0\uBB38 \uD45C\uC758 \uD589\uC744 \uC544\uC9C1 \uB300\uC870\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694.",
      "source-row-provenance-mismatch": "\uC6D0\uBB38\uACFC \uACF5\uC2DC \uC2DD\uBCC4 \uC815\uBCF4\uAC00 \uC77C\uCE58\uD558\uC9C0 \uC54A\uC544 \uD655\uC778\uC774 \uD544\uC694\uD574\uC694.",
      "missing-or-mismatched-settlement-date": "\uACB0\uC0B0\uAE30\uC900\uC77C\uC744 \uC77C\uCE58\uC2DC\uD0A4\uC9C0 \uBABB\uD588\uC5B4\uC694.",
      "ambiguous-legal-name": "\uAC19\uC740 \uC774\uB984\uC758 \uBC95\uC778\uC774 \uC788\uC5B4 \uB2F9\uC0AC\uC790\uB97C \uD655\uC815\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694.",
      "source-row-identity-mismatch": "\uC6D0\uBB38 \uD68C\uC0AC\uBA85\uACFC \uC885\uBAA9 \uC2DD\uBCC4 \uC815\uBCF4\uC758 \uB300\uC870\uAC00 \uD544\uC694\uD574\uC694.",
      "missing-numeric-ownership": "\uAE30\uB9D0 \uC9C0\uBD84\uC728\uC774 \uBE44\uC5B4 \uC788\uC5B4 \uBCF4\uC720 \uAD00\uACC4\uB85C \uD655\uC815\uD558\uC9C0 \uC54A\uC558\uC5B4\uC694.",
      "nonpositive-or-out-of-range-ownership": "\uBCF4\uC720 \uC9C0\uBD84\uC728\uB85C \uC0AC\uC6A9\uD560 \uC218 \uC5C6\uB294 \uAC12\uC774\uC5D0\uC694.",
      "ownership-projection-mismatch": "\uC6D0\uBB38 \uC9C0\uBD84\uC728\uACFC \uD45C\uC2DC\uAC12\uC774 \uC77C\uCE58\uD558\uC9C0 \uC54A\uC544\uC694.",
      "missing-or-mismatched-holder-role-or-stock-kind": "\uC8FC\uC8FC\uC758 \uC5ED\uD560 \uB610\uB294 \uC8FC\uC2DD\uC885\uB958\uB97C \uD655\uC778\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694."
    };
    const pendingReason = typeof r.decision_reason === "string" && Object.hasOwn(pendingReasons, r.decision_reason) ? pendingReasons[r.decision_reason] : "";
    let stockKind = "";
    let sourceOwnership;
    let reportedNames;
    const roleLabels = r.type === "reported-major-shareholder-entry" ? { from: "\uC8FC\uC8FC", to: "\uBC1C\uD589\uD68C\uC0AC" } : { from: "\uCD9C\uC790\uD68C\uC0AC", to: "\uD53C\uCD9C\uC790\uD68C\uC0AC" };
    if (reported) {
      const row5 = object(evidence.source_row), fields3 = object(row5.fields), major = r.type === "reported-major-shareholder-entry";
      const keys2 = ["rcept_no", "corp_code", "corp_name", "stlm_dt", ...major ? ["nm", "relate", "stock_knd", "trmend_posesn_stock_qota_rt"] : ["inv_prm", "trmend_blce_qota_rt"]];
      if (rawSource.kind !== "dart-structured-relation" || !source.asOf || !source.url || r.decision_reason !== "bound-source-row" || r.snapshot_scope !== "reported-at-settlement-not-current" || !/^[a-f0-9]{64}$/.test(text4(r.identity_revision, 64)) || Object.keys(row5).sort().join() !== "fields,index" || !Number.isInteger(row5.index) || row5.index < 0 || Object.keys(fields3).length !== keys2.length || keys2.some((key) => !Object.hasOwn(fields3, key)) || fields3.rcept_no !== rawSource.receipt_no || fields3.corp_code !== rawSource.corp_code || !/^[0-9]{8}$/.test(fields3.corp_code) || fields3.stlm_dt !== source.asOf || people.filter((p) => p.role === "from").length !== 1 || people.filter((p) => p.role === "to").length !== 1) throw invalid();
      keys2.forEach((key) => text4(fields3[key]));
      const rawPct = fields3[major ? "trmend_posesn_stock_qota_rt" : "trmend_blce_qota_rt"].trim();
      const [whole, fraction = ""] = rawPct.replace(/,/g, "").split(".");
      if (!/^(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?$/.test(rawPct) || pct === void 0 || pct <= 0 || Number(rawPct.replace(/,/g, "")) <= 0 || Number(whole) > 100 || Number(whole) === 100 && /[1-9]/.test(fraction) || Math.abs(Number(rawPct.replace(/,/g, "")) - pct) > 5000001e-9) throw invalid();
      if (major) {
        stockKind = text4(fields3.stock_knd);
        if (fields3.relate !== role) throw invalid();
      }
      sourceOwnership = Number(rawPct.replace(/,/g, ""));
      reportedNames = major ? { from: text4(fields3.nm), to: text4(fields3.corp_name) } : { from: text4(fields3.corp_name), to: text4(fields3.inv_prm) };
    }
    return {
      id: `automatic:${id}`,
      read_revision: Number.parseInt(revision2.slice(0, 13), 16) + 1,
      title,
      ...reported ? { reported: true } : {},
      reason: `${reportedNames ? `${roleLabels.from} ${reportedNames.from} \u2192 ${roleLabels.to} ${reportedNames.to}. ` : ""}${role}${stockKind ? ` \xB7 ${stockKind}` : ""}${pct === void 0 ? "" : ` \xB7 \uBCF4\uACE0\uB41C \uC9C0\uBD84 ${pct}%`}. ${rawSource.kind === "dart-structured-relation" ? `\uACB0\uC0B0\uAE30\uC900\uC77C ${source.asOf || "\uBBF8\uD655\uC778"}. ` : ""}${reported ? "\uD574\uB2F9 \uACB0\uC0B0\uAE30\uC900\uC77C\uC758 \uACF5\uC2DC \uD589\uC744 \uD655\uC778\uD588\uC5B4\uC694. \uD604\uC7AC \uBCF4\uC720 \uC5EC\uBD80\uB294 \uBBF8\uD655\uC778\uC774\uC5D0\uC694." : pendingReason || (source.url ? "\uC6D0\uBB38\uACFC \uD604\uC7AC \uC720\uD6A8 \uC5EC\uBD80\uB97C \uD655\uC778\uD558\uC138\uC694." : "\uC6D0\uBB38\uACFC \uAE30\uC900\uC77C\uC744 \uC544\uC9C1 \uD655\uC778\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694.")} \uC8FC\uAC00 \uC601\uD5A5\uC744 \uB73B\uD558\uC9C0 \uC54A\uC544\uC694.`,
      ...reported ? { measure: {
        kind: "reported-ownership",
        value: sourceOwnership,
        asOf: source.asOf,
        shareClass: stockKind || null,
        from: people.find((p) => p.role === "from").id,
        to: people.find((p) => p.role === "to").id,
        sourceField: r.type === "reported-major-shareholder-entry" ? "trmend_posesn_stock_qota_rt" : "trmend_blce_qota_rt"
      } } : {},
      participants: people.map((p) => reportedNames ? { ...p, name: reportedNames[p.role], roleLabel: roleLabels[p.role] } : p),
      source: source.source,
      asOf: source.asOf,
      url: source.url
    };
  });
  const materials = list2(body.materials).map((value) => {
    const m = object(value), id = text4(m.stable_id, 120), source = sourceFor(m.source), people = participants(m.participants);
    if (!/^event:dart:\d{14}:\d+-\d+:[a-f0-9]{8}$/.test(id) || ids.has(id) || m.kind !== "co_mention_candidate" || m.verified_event !== false || object(m.source).kind !== "dart-filing-excerpt" || !source.url) throw invalid();
    ids.add(id);
    const companyIds = list2(m.portfolio_company_ids, 30).map(entity);
    const expected = people.filter((p) => selected.has(p.id)).map((p) => p.id);
    if (!companyIds.length || new Set(companyIds).size !== companyIds.length || companyIds.length !== expected.length || companyIds.some((id2) => !expected.includes(id2))) throw invalid();
    const e = object(m.evidence), excerpt = publicExcerpt(e.excerpt);
    const sourceIssuer = people.find((p) => p.role === "document_issuer")?.id;
    if (sourceIssuer && object(m.source).document_issuer === sourceIssuer) {
      correctionSources.add(`${source.url}|${sourceIssuer}`);
      materialIssuers.set(id, sourceIssuer);
    }
    return { id, companyIds, item: {
      id: `material-${id}`,
      title: source.title,
      url: source.url,
      source: source.source,
      asOf: source.asOf,
      relationship: "unknown",
      reason: "\uAC19\uC740 \uC6D0\uBB38\uC5D0\uC11C \uD568\uAED8 \uC5B8\uAE09",
      explanation: `\uAC19\uC740 \uC6D0\uBB38\uC5D0 \uC5B8\uAE09\uB41C \uC790\uB8CC\uC608\uC694. \uAC70\uB798 \uAD00\uACC4\uB098 \uACF5\uD1B5 \uC601\uD5A5\uC774 \uD655\uC778\uB41C \uAC83\uC740 \uC544\uB2C8\uC5D0\uC694.
${excerpt}`
    } };
  });
  const byMaterial = new Map(materials.map((m) => [m.id, m]));
  const commonMaterials = list2(body.common_materials === void 0 ? [] : body.common_materials).map((value) => {
    const c = object(value), id = text4(c.stable_id, 150), materialId = text4(c.material_id, 120), revision2 = text4(c.revision, 64);
    const material = byMaterial.get(materialId), companyIds = list2(c.portfolio_company_ids, 30).map(entity);
    if (!material || id !== `common-material:${materialId}` || ids.has(id) || c.kind !== "shared-source-material" || c.verified_event !== false || !/^[a-f0-9]{64}$/.test(revision2) || companyIds.length < 2 || new Set(companyIds).size !== companyIds.length || companyIds.length !== material.companyIds.length || companyIds.some((id2) => !material.companyIds.includes(id2))) throw invalid();
    ids.add(id);
    return { id, materialId, companyIds, url: material.item.url, revision: revision2 };
  });
  const corrections = list2(body.corrections === void 0 ? [] : body.corrections, 1e3).map((value) => {
    const c = object(value), raw = object(c.source), issuer = entity(c.issuer);
    exactKeys(c, ["stable_id", "source", "issuer", "disposition", "reason", "lineage", "revision"]);
    exactKeys(raw, ["id", "kind", "url", "receipt_no", "as_of", "artifact_observed_at", "document_issuer", "report_name", "revision"]);
    const source = sourceFor(raw), receipt = text4(raw.receipt_no, 14), id = text4(c.stable_id, 100);
    if (raw.kind !== "dart-filing-excerpt" || !selected.has(issuer) && !correctionSources.has(`${source.url}|${issuer}`) || raw.document_issuer !== issuer || raw.id !== `source:dart:${receipt}` || id !== `correction:${receipt}` || ids.has(id) || !/정정/.test(source.title) || c.disposition !== "kept-distinct" || c.reason !== "explicit-correction-title-distinct-receipt" || c.lineage !== "not-provided-by-source" || !/^[a-f0-9]{64}$/.test(text4(c.revision, 64)) || !/^[a-f0-9]{64}$/.test(text4(raw.revision, 64)) || raw.artifact_observed_at !== null && (typeof raw.artifact_observed_at !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(raw.artifact_observed_at) || !Number.isFinite(Date.parse(raw.artifact_observed_at)))) throw invalid();
    ids.add(id);
    return { id, companyId: issuer, item: {
      id: `disclosure-${id}`,
      title: source.title,
      url: source.url,
      source: source.source,
      asOf: source.asOf,
      relationship: "unknown",
      reason: "\uC815\uC815\uACF5\uC2DC",
      explanation: "\uC81C\uBAA9\uC5D0 \uC815\uC815\uC774 \uD45C\uC2DC\uB41C \uBCC4\uB3C4 \uACF5\uC2DC\uC608\uC694. \uC6D0\uACF5\uC2DC \uC5F0\uACB0 \uC815\uBCF4\uB294 \uC774 \uC790\uB8CC\uC5D0 \uC5C6\uC5B4 \uAE30\uC874 \uACF5\uC2DC\uB97C \uC790\uB3D9 \uB300\uCCB4\uD558\uC9C0 \uC54A\uC544\uC694. \uC815\uC815 \uB0B4\uC6A9\xB7\uD604\uC7AC \uACC4\uC57D \uC0C1\uD0DC\xB7\uC8FC\uAC00 \uC601\uD5A5\uC740 \uC6D0\uBB38 \uD655\uC778\uC774 \uD544\uC694\uD574\uC694."
    } };
  });
  for (const correction of corrections) {
    for (const material of materials.filter((m) => m.item.url === correction.item.url && materialIssuers.get(m.id) === correction.companyId)) {
      if (material.item.title !== correction.item.title || material.item.asOf !== correction.item.asOf) throw invalid();
      material.item.reason = "\uC815\uC815\uACF5\uC2DC";
      material.item.explanation += `

${correction.item.explanation}`;
    }
  }
  return { relations, materials, commonMaterials, ...body.corrections === void 0 ? {} : { corrections } };
}
function parseAnalysisPrices(input, selected) {
  const output = /* @__PURE__ */ new Map();
  if (input === void 0) return output;
  const invalid8 = () => new Error("\uC885\uAC00 \uC790\uB8CC\uC758 \uD615\uC2DD\uC744 \uD655\uC778\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694.");
  if (!Array.isArray(input) || input.length !== selected.size) throw invalid8();
  for (const q of input) {
    if (!q || typeof q !== "object" || Array.isArray(q)) throw invalid8();
    const position2 = selected.get(q.id);
    if (!position2 || q.ticker !== position2.ticker || q.market !== position2.market || output.has(q.id)) throw invalid8();
    if (q.status === "restricted") {
      output.set(q.id, { state: "unavailable", reason: "\uACF5\uAC1C \uD45C\uC2DC \uC774\uC6A9 \uAD8C\uD55C\uC774 \uD655\uC778\uB418\uC9C0 \uC54A\uC740 \uAC00\uACA9 \uC790\uB8CC\uC608\uC694." });
      continue;
    }
    if (q.status === "missing") {
      output.set(q.id, { state: "unavailable", reason: "\uC774 \uC885\uBAA9\uC758 \uC885\uAC00 \uC790\uB8CC\uB97C \uC544\uC9C1 \uC5F0\uACB0\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694." });
      continue;
    }
    const existingKrDisplay = position2.market === "KR" && q.currency === "KRW" && q.rights?.status === "existing-public-display" && q.source?.id === "fsc-kr-daily-price" && q.source?.file === "kr_close_latest.json" && q.rights.reference === "https://www.data.go.kr/data/15094808/openapi.do";
    if (q.status !== "available" || !(q.rights?.status === "permitted" || existingKrDisplay) || typeof q.source?.name !== "string" || !q.source.name.trim() || q.source.name.length > 200 || /[\u0000-\u001f\u007f<>]/.test(q.source.name) || typeof q.currency !== "string" || !/^[A-Z]{3}$/.test(q.currency)) throw invalid8();
    let reference;
    try {
      reference = new URL(q.rights.reference);
    } catch {
      throw invalid8();
    }
    if (reference.protocol !== "https:" || reference.username || reference.password) throw invalid8();
    const quote3 = normalizePortfolioCloseQuote(position2.ticker, position2.market, {
      payload: {
        _meta: { as_of: q.close_date, prev_as_of: q.prev_as_of, source: q.source.name, basis: "\uC9C1\uC804 \uAC70\uB798\uC77C \uC885\uAC00 \xB7 \uC2E4\uC2DC\uAC04 \uC544\uB2D8" },
        prices: { [position2.ticker]: q.close },
        ...q.previous_close !== void 0 ? { prev: { [position2.ticker]: q.previous_close } } : {},
        ...q.change_pct !== void 0 ? { chg: { [position2.ticker]: q.change_pct } } : {},
        ...q.ohlc ? { ohlc: { [position2.ticker]: { date: q.close_date, open: q.ohlc.open, high: q.ohlc.high, low: q.ohlc.low, close: q.ohlc.close } } } : {}
      },
      currency: q.currency,
      // KR's original artifact contract needs no invented legal grant.
      ...existingKrDisplay ? {} : { verification: { publicDisplayApproved: true, market: position2.market, session: "closed", reference: reference.href } }
    });
    if (quote3.state !== "available") throw invalid8();
    output.set(q.id, quote3);
  }
  return output;
}
var rules = {
  "input-cost": {
    channel: "\uC6D0\uC7AC\uB8CC \uB9E4\uC785 \uBE44\uC6A9",
    condition: "\uD574\uB2F9 \uC6D0\uB8CC\uC758 \uC2E4\uC81C \uB9E4\uC785\uAC00\uACA9\uC774 \uBCC0\uD558\uACE0, \uC0AC\uC6A9\uB7C9\xB7\uD658\uC728\xB7\uD310\uB9E4\uAC00\uACA9 \uC804\uAC00 \uB4F1 \uB2E4\uB978 \uC870\uAC74\uC774 \uAC19\uB2E4\uBA74",
    rise: "\uBE44\uC6A9 \uBD80\uB2F4 \uAC00\uB2A5",
    fall: "\uBE44\uC6A9 \uC644\uD654 \uAC00\uB2A5"
  },
  "product-sales": {
    channel: "\uC81C\uD488 \uD310\uB9E4 \uB2E8\uAC00",
    condition: "\uD574\uB2F9 \uC81C\uD488\uC758 \uC2E4\uC81C \uD310\uB9E4\uB2E8\uAC00\uAC00 \uBCC0\uD558\uACE0, \uD310\uB9E4\uB7C9\xB7\uC6D0\uAC00\xB7\uD658\uC728 \uB4F1 \uB2E4\uB978 \uC870\uAC74\uC774 \uAC19\uB2E4\uBA74",
    rise: "\uB9E4\uCD9C \uC99D\uAC00 \uAC00\uB2A5",
    fall: "\uB9E4\uCD9C \uAC10\uC18C \uAC00\uB2A5"
  }
};
function judgeMarketChannels(item, companyId, companyName = "") {
  const scenarios = [];
  const seen = /* @__PURE__ */ new Set();
  for (const ref of item.kind === "commodity" && item.basis === "filing-context" ? item.filing_refs || [] : []) {
    if (ref.company_id !== companyId || !item.company_ids.includes(companyId)) continue;
    for (const channel of ref.channels || []) {
      const rule = rules[channel.kind];
      const quote3 = channel.quote?.trim() || "";
      const ownName = companyName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const subject = /^(?:당사|우리회사|연결회사|지배기업|종속회사|자회사)(?:는|은|가|의)?\s/.test(quote3) || !!ownName && new RegExp(`^${ownName}(?:\uC740|\uB294|\uC774|\uAC00|\uC758)\\s`).test(quote3);
      const tail = quote3.slice(quote3.indexOf(ref.term) + ref.term.length);
      const activity = channel.kind === "input-cost" ? /(?:매입|구매|구입|조달|사용|투입)(?:합니다|하고|하였|했|하며|하여)/.test(tail) : /(?:판매|공급|납품)(?:합니다|하고|하였|했|하며|하여)/.test(tail);
      if (!rule || !subject || !activity || seen.has(channel.kind) || !channel.quote || !ref.excerpt.includes(channel.quote) || !channel.quote.includes(ref.term) || !/[.!。]$/.test(channel.quote.trim()) || /않|아니|없|예정|계획|검토|가정|만약|예시|중단|종료|향후|가능성|전망|예상|추진|조건부|할 수|고객사|고객|경쟁사|타사|업계|수요처|거래처|납품처|전방산업|공급업체|협력사/.test(channel.quote)) continue;
      seen.add(channel.kind);
      scenarios.push({ ...rule, quote: channel.quote, sourceURL: ref.url, asOf: ref.as_of });
    }
  }
  return {
    // Never promote a channel scenario into a current stock-impact verdict.
    impact: "\uBBF8\uD655\uC778",
    scenarioSummary: scenarios.length > 1 ? "\uC0C1\uBC18\uB41C \uC0AC\uC5C5 \uACBD\uB85C \uD568\uAED8 \uC874\uC7AC" : scenarios.length ? "\uC870\uAC74\uBD80 \uC0AC\uC5C5 \uACBD\uB85C" : "\uD310\uB2E8 \uADFC\uAC70 \uBD80\uC871",
    scenarios,
    limitation: "\uBCF4\uACE0\uAE30\uAC04\uC758 \uC0AC\uC5C5 \uACBD\uB85C\uB97C \uC774\uC6A9\uD55C \uC870\uAC74\uBD80 \uD574\uC11D\uC774\uC5D0\uC694. \uC2DC\uC7A5 \uC9C0\uD45C\uC640 \uC2E4\uC81C \uC801\uC6A9 \uAC00\uACA9\uC774 \uAC19\uB2E4\uB294 \uB73B\uC740 \uC544\uB2C8\uC5D0\uC694. \uD604\uC7AC \uC21C\uB178\uCD9C\xB7\uD5E4\uC9C0\xB7\uADDC\uBAA8\uB294 \uBBF8\uD655\uC778\uC774\uBA70 \uC885\uBAA9 \uC804\uCCB4\uC758 \uC2E4\uC801\xB7\uC8FC\uAC00 \uC608\uCE21\uC774 \uC544\uB2C8\uC5D0\uC694."
  };
}
var PUBLIC = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/";
var FX = /* @__PURE__ */ new Set(["usd_krw", "usd_jpy", "eur_usd"]);
var COMMODITIES = /* @__PURE__ */ new Set([
  "wti_oil",
  "copper",
  "gold",
  "silver",
  "brent",
  "natural_gas",
  "corn",
  "wheat",
  "soybean",
  "coffee",
  "sugar",
  "cotton"
]);
var POWER = { "electricity-input": "power-use", "electricity-supply": "power-supply", "electricity-equipment": "power-equipment" };
var CALENDARS = {
  Fed: ["https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", "\uBBF8\uAD6D"],
  ECB: ["https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html", "\uC720\uB7FD"],
  BOJ: ["https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm", "\uC77C\uBCF8"],
  BOK: ["https://www.bok.or.kr/portal/main/contents.do?menuNo=200755", "\uD55C\uAD6D"],
  ISM: ["https://www.ismworld.org/supply-management-news-and-reports/reports/rob-report-calendar/", "\uBBF8\uAD6D"],
  UMich: ["https://data.sca.isr.umich.edu/survey-info.php", "\uBBF8\uAD6D"]
};
var CHANNEL_LABELS = {
  "input-cost": "\uC6D0\uC7AC\uB8CC\xB7\uB9E4\uC785 \uBE44\uC6A9",
  "product-sales": "\uC81C\uD488 \uC0DD\uC0B0\xB7\uD310\uB9E4",
  "fx-pricing": "\uD658\uC728\uC5D0 \uB530\uB978 \uC81C\uD488 \uAC00\uACA9",
  "fx-input-cost": "\uD658\uC728\uC5D0 \uB530\uB978 \uB9E4\uC785 \uBE44\uC6A9",
  "fx-revenue": "\uB9E4\uCD9C\uC758 \uD658\uC728 \uD6A8\uACFC",
  "risk-management": "\uC704\uD5D8\uAD00\uB9AC \uC5B8\uAE09",
  "floating-rate-borrowing": "\uBCC0\uB3D9\uAE08\uB9AC \uCC28\uC785 \uC704\uD5D8",
  "power-use": "\uC804\uB825 \uAD6C\uB9E4\xB7\uC0AC\uC6A9",
  "power-supply": "\uBC1C\uC804\xB7\uC804\uB825 \uACF5\uAE09",
  "power-equipment": "\uC804\uB825\uC124\uBE44 \uC0DD\uC0B0\xB7\uACF5\uAE09",
  "port-operation": "\uD56D\uB9CC\xB7\uD130\uBBF8\uB110 \uC6B4\uC601"
};
var channelLabels = (ref) => (ref.channels || []).filter((c) => c.kind !== "risk-management").map((c) => CHANNEL_LABELS[c.kind]);
var invalid2 = () => new Error("\uC2DC\uC7A5 \uC790\uB8CC \uD615\uC2DD\uC744 \uD655\uC778\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694.");
var record6 = (v) => {
  if (!v || typeof v !== "object" || Array.isArray(v)) throw invalid2();
  return v;
};
var text5 = (v, max = 700) => {
  if (typeof v !== "string" || !v.trim() || v.length > max || /[<>\u0000-\u001f\u007f]/.test(v)) throw invalid2();
  return v;
};
function stamp(v) {
  if (v === null) return null;
  const value = text5(v, 40);
  if (!/^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2}))?$/.test(value) || !Number.isFinite(Date.parse(value)) || new Date(value.slice(0, 10)).toISOString().slice(0, 10) !== value.slice(0, 10)) throw invalid2();
  return value;
}
function publicURL(value) {
  const raw = text5(value, 2048), url = new URL(raw);
  if (url.protocol !== "https:" || url.username || url.password || url.port || url.hash || !url.hostname.includes(".") || /^(?:localhost|127\.|10\.|192\.168\.|169\.254\.|172\.(?:1[6-9]|2\d|3[01])\.)/.test(url.hostname) || /(?:^|[?&])(?:token|access_token|key|api_key|password|secret|signature|auth)=/i.test(url.search) || /[\u0000-\u0020\u007f<>]/.test(decodeURIComponent(raw))) throw invalid2();
  return url.href;
}
var numeric = (v) => {
  if (v === null) return null;
  if (typeof v !== "number" || !Number.isFinite(v) || Math.abs(v) > 1e20) throw invalid2();
  return v;
};
var digestHex = async (value) => [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)))].map((b) => b.toString(16).padStart(2, "0")).join("");
function reportKey(report) {
  const suffix = " - " + report.source;
  const title = new URL(report.url).hostname === "news.google.com" && report.title.endsWith(suffix) ? report.title.slice(0, -suffix.length) : report.title;
  const normalize = (s) => s.normalize("NFKC").toLowerCase().replace(/[\s\u0085]+/gu, " ").trim();
  return [normalize(report.source), normalize(title), new Date(report.as_of).toISOString().slice(0, 10)].join("\n");
}
function powerQuoteBound(quote3, term, names) {
  if (!/[.!。]$/.test(quote3) || /(?:고객사|고객|경쟁사|타사|업계|수요처|거래처|납품처|전방산업|공급업체|협력사)(?:는|은|가|이|의|\s)/.test(quote3)) return false;
  const followedByTerm = (subject) => [...quote3.matchAll(subject)].some((match) => quote3.indexOf(term, match.index + match[0].length) >= 0);
  if (followedByTerm(/당사|우리회사|연결회사|지배기업|종속회사|자회사|회사의/g)) return true;
  return names.some((name) => followedByTerm(new RegExp(`(?<![\uAC00-\uD7A3A-Za-z0-9])${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?:\uC740|\uB294|\uC774|\uAC00|\uC758)(?=\\s|$)`, "g")));
}
function portQuoteBound(quote3, term, names) {
  return /^(?:항만\s*터미널|컨테이너\s*터미널|항만|부두)$/.test(term) && quote3.includes(term) && powerQuoteBound(quote3, term, names) && /(?:항만\s*터미널|컨테이너\s*터미널|항만|부두)(?:을|를)\s*운영(?:합니다|하고\s*있(?:습니다|으며)|하였습니다|했습니다|하며|하는\s*(?:항만하역\s*)?사업(?:을\s*영위|과))/.test(quote3) && !/않|아니|없|중단|제외|종료|폐지|전망|예상|예정|계획|가정|검토|추진|가능성|조건부|조건.{0,24}(?:면|경우)|(?<![가-힣])[가-힣]+(?:으면|되면|하면|라면|다면|이면)(?=\s|[,.;])|(?:할|될)\s*수\s*있|과거|전년도|만약|예를\s*들어|예시|예문|인용|문구|["'“”‘’]/.test(quote3);
}
async function parseMarketContext(value, wanted, companyNames = /* @__PURE__ */ new Map()) {
  if (value === void 0) return [];
  const body = record6(value);
  if (body.schema !== "alphaconsole-market-context-v1" || !Array.isArray(body.items) || body.items.length > FX.size + COMMODITIES.size + 26 + Object.keys(POWER).length + 12 + 1 + 1) throw invalid2();
  if (body.items.filter((row5) => row5?.kind === "news").length > 25 || body.items.filter((row5) => row5?.kind === "release-calendar").length > 12) throw invalid2();
  const seen = /* @__PURE__ */ new Set();
  return Promise.all(body.items.map(async (raw) => {
    const row5 = record6(raw), id = text5(row5.id, 128), kind = row5.kind;
    if (seen.has(id)) throw invalid2();
    seen.add(id);
    const prefix = `market:${kind}:`, key = id.slice(prefix.length);
    if (!id.startsWith(prefix) || !(kind === "fx" ? FX.has(key) : kind === "commodity" ? COMMODITIES.has(key) : kind === "interest-risk" ? key === "floating-borrowing" : kind === "power-context" ? Object.hasOwn(POWER, key) : kind === "infrastructure-context" ? key === "port-operation" : kind === "policy-rate" ? key === "korea-base" : (kind === "news" || kind === "release-calendar") && /^[a-f0-9]{64}$/.test(key))) throw invalid2();
    const operatingGroup = kind === "power-context" || kind === "infrastructure-context";
    const filingGroup = kind === "interest-risk" || operatingGroup;
    const calendar = kind === "release-calendar";
    const policy = kind === "policy-rate";
    const ids = row5.company_ids;
    if (!Array.isArray(ids) || ids.length > 30 || new Set(ids).size !== ids.length || ids.some((v) => typeof v !== "string" || !wanted.has(v))) throw invalid2();
    if (!(row5.basis === "market-context" ? !ids.length : row5.basis === "industry-membership" ? kind === "commodity" && ids.length > 0 : row5.basis === "filing-context" ? kind !== "news" && ids.length > 0 : row5.basis === "name-mention" && kind === "news" && ids.length > 0)) throw invalid2();
    const url = publicURL(row5.url);
    if (filingGroup ? url !== "https://dart.fss.or.kr/" : policy ? url !== "https://ecos.bok.or.kr/" : kind !== "news" && !calendar && url !== PUBLIC + "macro_snapshot.json") throw invalid2();
    const item = {
      id,
      kind,
      title: text5(row5.title, 300),
      summary: text5(row5.summary),
      source: text5(row5.source, 100),
      url,
      as_of: stamp(row5.as_of),
      observed_at: stamp(row5.observed_at),
      value: numeric(row5.value),
      change_pct: numeric(row5.change_pct),
      unit: row5.unit === null ? null : text5(row5.unit, 40),
      company_ids: ids.slice(),
      basis: row5.basis,
      reason: text5(row5.reason)
    };
    if ((kind === "news" || filingGroup || calendar) && (item.value !== null || item.change_pct !== null || item.unit !== null)) throw invalid2();
    if (filingGroup && (item.as_of !== null || item.observed_at !== null || item.basis !== "filing-context")) throw invalid2();
    if (operatingGroup && item.source !== "DART \xB7 \uBCF4\uACE0\uAE30\uAC04\uBCC4 \uACF5\uC2DC") throw invalid2();
    const extra = {};
    if (policy) {
      const observation3 = record6(row5.observation), period = text5(observation3.period, 7);
      if (!/^[0-9]{4}-(?:0[1-9]|1[0-2])$/.test(period) || period.startsWith("0000") || observation3.stat_code !== "722Y001" || observation3.item_code !== "0101000" || observation3.frequency !== "M" || observation3.series_id !== "ECOS/722Y001/0101000" || !["preserved-source", "collector-contract"].includes(observation3.identity_basis) || item.as_of !== null || !item.observed_at || item.observed_at.length === 10 || Date.parse(item.observed_at) > Date.now() + 3e5 || period > new Date(Date.parse(item.observed_at) + 9 * 36e5).toISOString().slice(0, 7) || item.value === null || item.change_pct !== null || item.unit !== "\uC5F0%" || item.basis !== "market-context" || ids.length || row5.verified_common_event !== false || item.source !== "\uD55C\uAD6D\uC740\uD589 ECOS \xB7 \uACF5\uAC1C \uC2A4\uB0C5\uC0F7" || item.title !== "\uD55C\uAD6D\uC740\uD589 \uAE30\uC900\uAE08\uB9AC" || row5.reports !== void 0 || row5.grouping !== void 0 || row5.filing_refs !== void 0) throw invalid2();
      Object.assign(extra, { observation: {
        period,
        stat_code: "722Y001",
        item_code: "0101000",
        frequency: "M",
        series_id: "ECOS/722Y001/0101000",
        identity_basis: observation3.identity_basis
      }, verified_common_event: false });
    } else if (row5.observation !== void 0) throw invalid2();
    if (calendar) {
      const schedule = record6(row5.schedule), country = text5(schedule.country, 40);
      const source_kind = schedule.source_kind, release_id = schedule.release_id;
      if (item.basis !== "market-context" || ids.length || !item.as_of || item.as_of.length !== 10 || !item.observed_at || Date.parse(item.observed_at) > Date.now() + 3e5 || row5.verified_common_event !== false || row5.reports !== void 0 || row5.grouping !== void 0) throw invalid2();
      if (source_kind === "release") {
        if (item.source !== "FRED" || country !== "\uBBF8\uAD6D" || !Number.isSafeInteger(release_id) || release_id <= 0 || release_id > 1e6 || url !== `https://fred.stlouisfed.org/release?rid=${release_id}`) throw invalid2();
      } else if (source_kind === "schedule") {
        const known = Object.hasOwn(CALENDARS, item.source) ? CALENDARS[item.source] : null;
        if (!known || url !== known[0] || country !== known[1] || release_id !== null) throw invalid2();
      } else throw invalid2();
      const identity2 = JSON.stringify([item.source, source_kind, url, item.title, item.as_of, country, release_id]);
      if (key !== await digestHex(identity2)) throw invalid2();
      Object.assign(extra, { schedule: { country, source_kind, release_id }, verified_common_event: false });
    } else if (row5.schedule !== void 0) throw invalid2();
    if (filingGroup) {
      const revision2 = text5(row5.evidence_revision, 64);
      if (!/^[a-f0-9]{64}$/.test(revision2)) throw invalid2();
      extra.evidence_revision = revision2;
    }
    if (row5.filing_refs !== void 0 || row5.industry_company_ids !== void 0 || row5.basis === "filing-context") {
      if (row5.basis !== "filing-context" || !Array.isArray(row5.filing_refs) || !row5.filing_refs.length || row5.filing_refs.length > 30 || !Array.isArray(row5.industry_company_ids) || kind !== "commodity" && row5.industry_company_ids.length) throw invalid2();
      const industry = row5.industry_company_ids;
      if (industry.length > 30 || new Set(industry).size !== industry.length || industry.some((v) => !ids.includes(v))) throw invalid2();
      const refs = row5.filing_refs.map((raw2) => {
        const ref = record6(raw2), company_id = text5(ref.company_id, 32), term = text5(ref.term, 50), excerpt = text5(ref.excerpt, 600);
        const url2 = publicURL(ref.url), as_of = stamp(ref.as_of), year = text5(ref.fiscal_year, 4);
        if (!/^KR:\d{6}$/.test(company_id) || !ids.includes(company_id) || !excerpt.includes(term) || !/^https:\/\/dart\.fss\.or\.kr\/dsaf001\/main\.do\?rcpNo=\d{14}$/.test(url2) || !as_of || as_of.length !== 10 || !/^\d{4}$/.test(year) || typeof ref.truncated !== "boolean") throw invalid2();
        let channels;
        if (ref.channels !== void 0) {
          if (!Array.isArray(ref.channels) || !ref.channels.length || ref.channels.length > 4) throw invalid2();
          channels = ref.channels.map((raw3) => {
            const channel = record6(raw3), key2 = channel.kind, quote3 = text5(channel.quote, 600);
            if (!(kind === "interest-risk" ? key2 === "floating-rate-borrowing" : kind === "power-context" ? key2 === POWER[id.slice(prefix.length)] : kind === "infrastructure-context" ? key2 === "port-operation" : key2 === "risk-management" || (kind === "fx" ? ["fx-pricing", "fx-input-cost", "fx-revenue"].includes(key2) : key2 === "input-cost" || key2 === "product-sales")) || !excerpt.includes(quote3)) throw invalid2();
            return { kind: key2, quote: quote3 };
          });
          if (new Set(channels.map((c) => c.kind)).size !== channels.length || !channels.some((c) => c.kind !== "risk-management")) throw invalid2();
        }
        if (kind === "interest-risk" && (!channels || channels.length !== 1 || channels[0].kind !== "floating-rate-borrowing")) throw invalid2();
        const source = text5(ref.source, 240);
        if (operatingGroup && (!channels || channels.length !== 1 || !(kind === "infrastructure-context" ? portQuoteBound : powerQuoteBound)(channels[0].quote, term, companyNames.get(company_id) || []) || kind === "power-context" && new URL(url2).searchParams.get("rcpNo").slice(0, 8) !== as_of.replaceAll("-", "") || as_of > (/* @__PURE__ */ new Date()).toISOString().slice(0, 10) || !new RegExp(`^(?:\\[(?:\uAE30\uC7AC\uC815\uC815|\uCCA8\uBD80\uC815\uC815|\uC815\uC815)\\]\\s*)?\uC0AC\uC5C5\uBCF4\uACE0\uC11C\\s*\\(${year}\\.(?:0[1-9]|1[0-2])\\)$`).test(source))) throw invalid2();
        return {
          company_id,
          term,
          excerpt,
          url: url2,
          as_of,
          fiscal_year: year,
          truncated: ref.truncated,
          source,
          ...channels ? { channels } : {}
        };
      }).sort((a, b) => a.company_id.localeCompare(b.company_id));
      if (new Set(refs.map((r) => r.company_id)).size !== refs.length || ids.some((id2) => !industry.includes(id2) && !refs.some((r) => r.company_id === id2))) throw invalid2();
      Object.assign(extra, { filing_refs: refs, industry_company_ids: industry.slice().sort() });
    }
    if (!calendar && !policy && (row5.reports !== void 0 || row5.grouping !== void 0 || row5.verified_common_event !== void 0)) {
      if (kind !== "news" || row5.grouping !== "same-publisher-headline-day" || row5.verified_common_event !== false || !Array.isArray(row5.reports) || row5.reports.length < 1 || row5.reports.length > 8) throw invalid2();
      const reports = row5.reports.map((raw2) => {
        const report = record6(raw2), as_of = stamp(report.as_of);
        if (!as_of || as_of.length === 10) throw invalid2();
        return { title: text5(report.title, 300), source: text5(report.source, 100), url: publicURL(report.url), as_of };
      }).sort((a, b) => a.url < b.url ? -1 : a.url > b.url ? 1 : 0);
      if (new Set(reports.map((r) => r.url)).size !== reports.length || new Set(reports.map(reportKey)).size !== 1 || !reports.some((r) => r.url === item.url && r.title === item.title && r.source === item.source && r.as_of === item.as_of)) throw invalid2();
      if (id !== "market:news:" + await digestHex("same-publisher-headline-day\n" + reportKey(reports[0]))) throw invalid2();
      Object.assign(extra, {
        reports,
        grouping: row5.grouping,
        verified_common_event: false,
        legacyIds: await Promise.all(reports.map(async (r) => "market:news:" + await digestHex(r.url)))
      });
    }
    const { observed_at: _observed, company_ids: _ids, basis: _basis, reason: _reason, ...content } = item;
    const { legacyIds: _legacy, filing_refs: _filings, industry_company_ids: _industry, observation: observation2, ...reportContent } = extra;
    if (observation2) {
      const { identity_basis: _identity, ...seriesContent } = observation2;
      Object.assign(reportContent, { observation: seriesContent });
    }
    const hash = await digestHex(JSON.stringify({ ...content, ...reportContent }));
    return { ...item, ...extra, read_revision: Number.parseInt(hash.slice(0, 13), 16) + 1 };
  }));
}
function projectMarketPrototype(graph) {
  const items = graph?.marketContext || [];
  const companies = new Map(graph?.companies.map((c) => [`${c.market}:${c.ticker}`, c]));
  const filingEvidence = (item, ref) => ({
    url: ref.url,
    source: `${companies.get(ref.company_id)?.name || ref.company_id} \xB7 ${ref.source}`,
    asOf: ref.as_of,
    explanation: [
      `${ref.fiscal_year} \uD68C\uACC4\uC5F0\uB3C4 \xB7 \uACF5\uC2DC\uC77C ${ref.as_of} \xB7 ${item.kind === "interest-risk" ? "\uC704\uD5D8\uAD00\uB9AC" : "\uC0AC\uC5C5\uC758 \uAC1C\uC694"}${ref.truncated ? " \xB7 \uACF5\uAC1C \uBC1C\uCDCC(\uC77C\uBD80)" : " \xB7 \uACF5\uAC1C \uBC1C\uCDCC"}`,
      ref.excerpt,
      ...ref.channels ? [
        `\uACF5\uC2DC\uC0C1 ${item.kind === "interest-risk" ? "\uAE08\uC735\uC704\uD5D8" : "\uC0AC\uC5C5 \uACBD\uB85C"}: ${channelLabels(ref).join(" \xB7 ")}. \uADDC\uBAA8\uC640 \uD604\uC7AC \uC601\uD5A5\uC740 \uBBF8\uD655\uC778\uC774\uC5D0\uC694.`,
        ...ref.channels.some((c) => c.kind === "fx-revenue") ? ["\uBCF4\uACE0\uAE30\uAC04 \uB9E4\uCD9C\uC5D0 \uB300\uD55C \uC124\uBA85\uC774\uC5D0\uC694. \uD658\uC728\uB9CC\uC758 \uAE30\uC5EC\uBD84\uC774\uB098 \uD604\uC7AC \uB9E4\uCD9C\xB7\uC8FC\uAC00 \uC804\uB9DD\uC744 \uB73B\uD558\uC9C0 \uC54A\uC544\uC694."] : [],
        ...ref.channels.some((c) => c.kind === "risk-management") ? ["\uC6D0\uBB38\uC5D0 \uC704\uD5D8\uAD00\uB9AC\uB3C4 \uC5B8\uAE09\uB3FC \uC788\uC5B4\uC694. \uC704\uD5D8\uC774 \uC804\uBD80 \uC0C1\uC1C4\uB41C\uB2E4\uB294 \uB73B\uC740 \uC544\uB2C8\uC5D0\uC694."] : []
      ] : [],
      item.kind === "interest-risk" ? "\uBCF4\uACE0 \uB2F9\uC2DC\uC758 \uBCC0\uB3D9\uAE08\uB9AC \uCC28\uC785 \uC704\uD5D8\uC774\uC5D0\uC694. \uD2B9\uC815 \uAE30\uC900\uAE08\uB9AC\xB7\uD1B5\uD654\xB7\uD604\uC7AC \uC794\uC561\xB7\uC21C\uC774\uC790\uBE44\uC6A9\xB7\uC8FC\uAC00 \uC601\uD5A5\uC740 \uD655\uC778\uB418\uC9C0 \uC54A\uC558\uC5B4\uC694." : item.kind === "power-context" ? "\uBCF4\uACE0 \uB2F9\uC2DC \uC6D0\uBB38\uC5D0 \uBA85\uC2DC\uB41C \uC804\uB825 \uAD00\uB828 \uC0AC\uC5C5 \uACBD\uB85C\uC608\uC694. \uAE30\uC5C5 \uAC04 \uAC70\uB798 \uAD00\uACC4\uB098 \uAC19\uC740 \uC0AC\uAC74\uC758 \uC99D\uAC70\uB294 \uC544\uB2C8\uBA70, \uC804\uB825\uC694\uAE08\xB7\uC0AC\uC6A9 \uBC0F \uB9E4\uCD9C \uBE44\uC911\xB7\uD604\uC7AC \uC0C1\uD0DC\xB7\uC8FC\uAC00 \uC601\uD5A5\uC740 \uBBF8\uD655\uC778\uC774\uC5D0\uC694." : item.kind === "infrastructure-context" ? "\uBCF4\uACE0 \uB2F9\uC2DC \uC6D0\uBB38\uC5D0 \uBA85\uC2DC\uB41C \uD56D\uB9CC\xB7\uD130\uBBF8\uB110 \uC6B4\uC601\uC774\uC5D0\uC694. \uAC19\uC740 \uC0AC\uAC74\xB7\uAE30\uC5C5 \uAC04 \uAC70\uB798 \uAD00\uACC4\uB098 \uD604\uC7AC \uC815\uCC45 \uC218\uD61C\uB97C \uB73B\uD558\uC9C0 \uC54A\uC544\uC694. \uD604\uC7AC \uC6B4\uC601\uAD8C\xB7\uC0AC\uC5C5 \uADDC\uBAA8\xB7\uC8FC\uAC00 \uC601\uD5A5\uC740 \uBBF8\uD655\uC778\uC774\uC5D0\uC694." : item.kind === "fx" ? "\uD658\uC728 \uAD00\uB828 \uD45C\uD604\uC744 \uCC38\uACE0 \uC5F0\uACB0\uD588\uC5B4\uC694. \uC774 \uD1B5\uD654\uC30D\uC758 \uC2E4\uC81C \uB178\uCD9C\uACFC \uD604\uC7AC \uC601\uD5A5\uC740 \uBBF8\uD655\uC778\uC774\uC5D0\uC694." : item.id.endsWith(":wti_oil") ? "\uC6D0\uC720 \uAD00\uB828 \uD45C\uD604\uC744 WTI \uCC38\uACE0 \uC9C0\uD45C\uC640 \uC5F0\uACB0\uD588\uC5B4\uC694. \uC2E4\uC81C \uC720\uC885\xB7\uACC4\uC57D \uAE30\uC900\uAC00\uACA9\xB7\uD604\uC7AC \uC601\uD5A5\uC740 \uBBF8\uD655\uC778\uC774\uC5D0\uC694." : item.kind === "commodity" ? "\uC6D0\uBB38\uC5D0 \uAD00\uB828 \uC6D0\uC7AC\uB8CC\xB7\uC81C\uD488\uC774 \uC5B8\uAE09\uB3FC \uC788\uC5B4\uC694. \uD488\uC885\xB7\uAC00\uACF5 \uB2E8\uACC4\xB7\uC9C0\uC5ED\xB7\uC2E4\uC81C \uACC4\uC57D\uAC00\uACA9\uC740 \uC774 \uC2DC\uC7A5 \uC9C0\uD45C\uC640 \uB2E4\uB97C \uC218 \uC788\uC5B4\uC694. \uC0AC\uC6A9\xB7\uD310\uB9E4 \uBE44\uC911\uACFC \uD604\uC7AC \uC601\uD5A5 \uBC29\uD5A5\uC740 \uBBF8\uD655\uC778\uC774\uC5D0\uC694." : "\uBCF4\uACE0\uC11C\uC5D0 \uAD00\uB828 \uC18C\uC7AC\uAC00 \uC5B8\uAE09\uB3FC \uC788\uC5B4\uC694. \uC0AC\uC6A9\xB7\uD310\uB9E4 \uBE44\uC911\uACFC \uD604\uC7AC \uC601\uD5A5 \uBC29\uD5A5\uC740 \uBBF8\uD655\uC778\uC774\uC5D0\uC694."
    ].join("\n")
  });
  const nodes = items.map((item, index) => {
    const value = item.value === null ? "" : `${item.value.toLocaleString("ko-KR", { maximumFractionDigits: 8 })} ${item.unit || "\uB2E8\uC704 \uBBF8\uC81C\uACF5"}`;
    const change = item.change_pct === null ? "" : `${item.change_pct > 0 ? "+" : ""}${item.change_pct.toFixed(2)}%`;
    const bundled = (item.reports?.length || 0) > 1;
    const filingGroup = item.kind === "interest-risk" || item.kind === "power-context" || item.kind === "infrastructure-context";
    const calendar = item.kind === "release-calendar";
    const policy = item.kind === "policy-rate";
    const qualifier = calendar ? "\uBC1C\uD45C \uC77C\uC815 \xB7 \uACB0\uACFC \uBBF8\uD655\uC778" : policy ? "\uC6D4 \uB2E8\uC704 \uC9C0\uD45C \xB7 \uC815\uCC45 \uACB0\uC815 \uC544\uB2D8" : filingGroup ? "\uBCF4\uACE0\uAE30\uAC04\uBCC4 \uACF5\uC2DC \uBB36\uC74C \xB7 \uAC19\uC740 \uC0AC\uAC74 \uC544\uB2D8" : bundled ? `\uB3D9\uC77C \uC81C\uBAA9 \uBCF4\uB3C4 \uBB36\uC74C \xB7 ${item.reports.length}\uAC1C \uC6D0\uBB38 \xB7 \uC0AC\uAC74 \uD655\uC815 \uC544\uB2D8` : item.basis === "filing-context" ? "\uC0AC\uC5C5\uBCF4\uACE0\uC11C \uCC38\uACE0 \uC5F0\uACB0 \xB7 \uC601\uD5A5 \uBBF8\uD655\uC778" : item.basis === "industry-membership" ? "\uC0B0\uC5C5 \uBD84\uB958 \uD6C4\uBCF4 \xB7 \uC601\uD5A5 \uBBF8\uD655\uC778" : item.basis === "name-mention" ? "\uAE30\uC0AC\uC5D0 \uC885\uBAA9\uBA85 \uC5B8\uAE09 \xB7 \uC601\uD5A5 \uBBF8\uD655\uC778" : "\uC2DC\uC7A5 \uCC38\uACE0 \xB7 \uAC1C\uBCC4 \uC5F0\uACB0 \uBBF8\uD655\uC778";
    const dates = calendar ? `\uC608\uC815\uC77C ${item.as_of} \xB7 ${item.schedule.country} \xB7 \uC77C\uC815 \uC218\uC9D1 ${item.observed_at}` : policy ? `\uC790\uB8CC \uAE30\uC900\uC6D4 ${item.observation.period} \xB7 \uC218\uC9D1 ${item.observed_at}` : filingGroup ? "\uAC01 \uACF5\uC2DC\uC758 \uBCF4\uACE0\uAE30\uAC04\xB7\uACF5\uC2DC\uC77C\uC740 \uC544\uB798 \uC6D0\uBB38 \uADFC\uAC70\uC5D0\uC11C \uD655\uC778\uD560 \uC218 \uC788\uC5B4\uC694." : `${item.as_of ? "\uC790\uB8CC \uAE30\uC900 " + item.as_of : "\uC790\uB8CC \uAE30\uC900\uC77C \uBBF8\uC81C\uACF5"}${item.observed_at ? " \xB7 \uC218\uC9D1 " + item.observed_at : ""}`;
    const series = policy ? `\uC2DC\uACC4\uC5F4 ${item.observation.series_id} \xB7 \uC8FC\uAE30 M \xB7 ${item.observation.identity_basis === "preserved-source" ? "\uC2DD\uBCC4\uC790 \uBCF4\uC874" : "\uC218\uC9D1\uAE30 \uC124\uC815 \uCC38\uACE0 \xB7 \uBCF4\uC874 \uC2DD\uBCC4\uC790 \uC77C\uBD80 \uBBF8\uC81C\uACF5"}` : "";
    const explanation = [item.summary, item.reason, bundled ? "\uAC19\uC740 \uB9E4\uCCB4\xB7\uAC19\uC740 \uC81C\uBAA9\xB7\uAC19\uC740 UTC \uBC1C\uD589\uC77C\uB85C \uBB36\uC5C8\uC5B4\uC694. \uB3C5\uB9BD\uB41C \uC5EC\uB7EC \uB9E4\uCCB4\uC758 \uD655\uC778\uC774\uB098 \uB3D9\uC77C \uC0AC\uAC74\uC758 \uD655\uC815\uC744 \uB73B\uD558\uC9C0 \uC54A\uC544\uC694." : "", dates, series].filter(Boolean).join("\n");
    const evidence = item.reports ? item.reports.map((report) => ({
      url: report.url,
      source: report.source,
      asOf: report.as_of,
      explanation: [report.title, report.source, "\uAC8C\uC2DC " + report.as_of].join(" \xB7 ")
    })) : [{ url: item.url, source: item.source, asOf: calendar ? null : item.as_of, explanation }];
    if (item.basis === "industry-membership" || item.industry_company_ids?.length) evidence.push({
      url: PUBLIC + "commodity_exposure.json",
      source: "\uC0B0\uC5C5 \uBD84\uB958 \uC5F0\uACB0 \uC790\uB8CC",
      asOf: null,
      explanation: "\uACF5\uAC1C \uC0B0\uC5C5 \uBD84\uB958\uC5D0 \uD3EC\uD568\uB41C \uC885\uBAA9\uB9CC \uC5F0\uACB0\uD588\uC5B4\uC694. \uC2E4\uC81C \uC6D0\uAC00\xB7\uB9E4\uCD9C \uBE44\uC911\uACFC \uC601\uD5A5 \uBC29\uD5A5\uC740 \uD655\uC778\uB418\uC9C0 \uC54A\uC558\uC5B4\uC694."
    });
    evidence.push(...(item.filing_refs || []).map((ref) => filingEvidence(item, ref)));
    return {
      id: item.id,
      kind: "event",
      recordKind: "market-context",
      layer: calendar ? "calendar" : filingGroup ? "filing" : policy ? "government" : item.kind,
      topic: item.kind === "commodity" ? "commodity" : item.kind === "fx" || filingGroup || calendar || policy ? "macro" : "general",
      name: item.title,
      code: calendar ? `\uC608\uC815 ${item.as_of} \xB7 ${item.schedule.country}` : [value, change].filter(Boolean).join(" \xB7 ") || qualifier,
      logo: "",
      priority: 1,
      proofLabel: qualifier,
      reason: explanation,
      source: item.source,
      asOf: calendar ? null : item.as_of,
      evidence,
      ...item.legacyIds ? { legacyIds: item.legacyIds } : {},
      read_revision: item.read_revision,
      x: 1.05 + index % 3 * 0.2,
      y: 0.6 + Math.floor(index / 3) * 0.18
    };
  });
  const edges = items.flatMap((item) => item.company_ids.flatMap((id) => {
    const company = companies.get(id), node = nodes.find((n) => n.id === item.id);
    const ref = item.filing_refs?.find((ref2) => ref2.company_id === id);
    const channels = ref ? channelLabels(ref) : [];
    const proof = ref ? filingEvidence(item, ref) : null;
    const assessment = judgeMarketChannels(item, id, company?.name);
    const reason = proof ? proof.explanation : item.basis === "filing-context" ? "\uC0B0\uC5C5 \uBD84\uB958 \uD6C4\uBCF4\uC774\uBA70 \uB9E4\uCD9C \uB178\uCD9C\uC774\uB098 \uC601\uD5A5\uC740 \uBBF8\uD655\uC778\uC774\uC5D0\uC694." : item.reason;
    return company ? [{
      id: `market-link:${item.id}:${id}`,
      from: item.id,
      to: company.id,
      type: "unknown",
      strength: 0,
      assessment,
      impact: assessment.impact,
      impactReason: channels.length ? `\uACF5\uC2DC\uC0C1 ${channels.join(" \xB7 ")} \xB7 \uD604\uC7AC \uC601\uD5A5 \uBBF8\uD655\uC778` : ref ? `\uC0AC\uC5C5\uBCF4\uACE0\uC11C\uC5D0 \u2018${ref.term}\u2019 \uC5B8\uAE09 \xB7 \uD604\uC7AC \uC601\uD5A5 \uBBF8\uD655\uC778` : reason,
      reason,
      verb: channels.length ? channels.join(" \xB7 ") : ref ? "\uACF5\uC2DC\uC5D0\uC11C \uAD00\uB828 \uD45C\uD604" : item.kind === "commodity" ? "\uC0B0\uC5C5 \uBD84\uB958 \uD6C4\uBCF4" : "\uAE30\uC0AC\uC5D0 \uC774\uB984 \uC5B8\uAE09",
      source: proof?.source || item.source,
      asOf: proof?.asOf || item.as_of,
      evidence: proof ? [node.evidence[0], proof] : node.evidence.filter((e) => !(item.filing_refs || []).some((r) => r.url === e.url))
    }] : [];
  }));
  const recordsMap = Object.fromEntries(nodes.map((n) => [n.id, { id: n.id, read_revision: n.read_revision, sourceURLs: n.evidence.map((e) => e.url), ...n.legacyIds ? { legacyIds: n.legacyIds } : {} }]));
  return { nodes, edges, recordsMap };
}
var DART = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=";
var invalid3 = () => new Error("\uACF5\uC2DC \uBCC0\uACBD \uC774\uB825\uC744 \uD655\uC778\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694.");
var text6 = (v, pattern) => {
  if (typeof v !== "string" || !pattern.test(v)) throw invalid3();
  return v;
};
var titleKey = (v) => v.normalize("NFKC").replace(/\[(?:기재|첨부|기타)?정정\]/g, "").replace(/[ㆍ·ᆞ]/g, "\xB7").trim();
function parseDocumentLineage(value, doc) {
  if (value === void 0) return null;
  if (!value || typeof value !== "object" || Array.isArray(value)) throw invalid3();
  const row5 = value;
  const issuer = text6(row5.issuer_id, /^KR:[0-9]{6}$/), root = text6(row5.root_receipt, /^[0-9]{14}$/);
  const current = text6(row5.current_receipt, /^[0-9]{14}$/);
  const id = text6(row5.id, /^dart-family:[0-9]{8}:[0-9]{14}$/);
  if (row5.kind !== "official-dart-document-family" || row5.verified_common_event !== false || row5.current_economic_status !== "unverified" || !id.endsWith(":" + root) || doc.id !== "DART:" + current || doc.source !== "DART" || doc.url !== DART + current || doc.company_ids.length !== 1 || doc.company_ids[0] !== issuer || !Array.isArray(row5.members) || row5.members.length < 1 || row5.members.length > 100) throw invalid3();
  const members = row5.members.map((raw) => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw invalid3();
    const m = raw, receipt = text6(m.receipt_no, /^[0-9]{14}$/);
    const title = text6(m.title, /^[^<>\u0000-\u001f\u007f]{1,300}$/), day4 = text6(m.published_on, /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/);
    if (titleKey(title) !== "\uB2E8\uC77C\uD310\uB9E4\xB7\uACF5\uAE09\uACC4\uC57D\uCCB4\uACB0" || typeof m.amendment !== "boolean" || !Number.isFinite(Date.parse(day4)) || new Date(day4).toISOString().slice(0, 10) !== day4) throw invalid3();
    return { receipt, title, day: day4, amendment: m.amendment };
  }).sort((a, b) => a.day.localeCompare(b.day) || a.receipt.localeCompare(b.receipt));
  const originals = members.filter((m) => !m.amendment), selected = members.find((m) => m.receipt === current);
  if (new Set(members.map((m) => m.receipt)).size !== members.length || originals.length !== 1 || originals[0].receipt !== root || members.some((m) => m.day < originals[0].day) || !selected || selected.day !== doc.as_of || titleKey(doc.title) !== titleKey(selected.title) || doc.title.includes("\uC815\uC815") !== selected.amendment) throw invalid3();
  const history = members.map((m) => `${m.day} ${m.amendment ? "\uC815\uC815\uACF5\uC2DC" : "\uCD5C\uCD08 \uACF5\uC2DC"}`).join(" \u2192 ");
  return {
    explanation: `DART\uAC00 \uC9C1\uC811 \uC5F0\uACB0\uD55C \uACF5\uC2DC \uC774\uB825\uC774\uC5D0\uC694. ${history}. \uC815\uC815 \uB0B4\uC6A9\xB7\uACC4\uC57D \uC0C1\uB300\uBC29\xB7\uD604\uC7AC \uC720\uD6A8 \uC0C1\uD0DC\xB7\uC8FC\uAC00 \uC601\uD5A5\uC740 \uBCF8\uBB38 \uD655\uC778\uC774 \uD544\uC694\uD574\uC694. \uB2E4\uB978 \uACC4\uC57D\uC774\uB098 \uACF5\uD1B5 \uACBD\uC81C\uC0AC\uAC74\uC73C\uB85C \uC790\uB3D9 \uD569\uCE58\uC9C0 \uC54A\uC544\uC694.`,
    sources: members.map((m) => ({
      title: `${m.amendment ? "\uC815\uC815\uACF5\uC2DC" : "\uCD5C\uCD08 \uACF5\uC2DC"} \xB7 ${m.title}`,
      source: "DART \uACF5\uC2DC \uC774\uB825",
      asOf: m.day,
      url: DART + m.receipt
    }))
  };
}
var { parseContractFacts, quotedContractDay, quotedContractFinancialLines } = (() => {
  var MemberMapContractFactsDelta = (() => {
    var __defProp2 = Object.defineProperty;
    var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
    var __getOwnPropNames = Object.getOwnPropertyNames;
    var __hasOwnProp = Object.prototype.hasOwnProperty;
    var __export = (target, all) => {
      for (var name in all)
        __defProp2(target, name, { get: all[name], enumerable: true });
    };
    var __copyProps = (to, from, except, desc) => {
      if (from && typeof from === "object" || typeof from === "function") {
        for (let key of __getOwnPropNames(from))
          if (!__hasOwnProp.call(to, key) && key !== except)
            __defProp2(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
      }
      return to;
    };
    var __toCommonJS = (mod) => __copyProps(__defProp2({}, "__esModule", { value: true }), mod);
    var PortfolioContractFacts_exports = {};
    __export(PortfolioContractFacts_exports, {
      parseContractFacts: () => parseContractFacts2,
      quotedContractDay: () => quotedContractDay2,
      quotedContractFinancialLines: () => quotedContractFinancialLines2
    });
    var invalid4 = () => new Error("\uACC4\uC57D\uACF5\uC2DC \uBCF8\uBB38 \uC790\uB8CC\uB97C \uD655\uC778\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694.");
    var row = (v) => {
      if (!v || typeof v !== "object" || Array.isArray(v)) throw invalid4();
      return v;
    };
    var text7 = (v, max = 2e3) => {
      if (typeof v !== "string" || !v.trim() || v.length > max || /[<>\u0000-\u001f\u007f]/.test(v)) throw invalid4();
      return v;
    };
    var day = (v) => {
      const value = text7(v, 10);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || !Number.isFinite(Date.parse(value)) || new Date(value).toISOString().slice(0, 10) !== value) throw invalid4();
      return value;
    };
    var titleKey2 = (v) => v.normalize("NFKC").replace(/^\[(?:기재|첨부|기타)?정정\]/, "").replace(/[\sㆍ·ᆞ•]/g, "");
    var field = (v) => {
      const item = row(v);
      return { label: text7(item.label), value: text7(item.value) };
    };
    var quote = (v) => {
      const item = field(v);
      return `${item.label}: ${item.value}`;
    };
    var quotedContractDay2 = (value) => {
      const match = text7(value, 12).match(/^(\d{4})[.-](\d{1,2})[.-](\d{1,2})\.?$/);
      if (!match) throw invalid4();
      return day(`${match[1]}-${match[2].padStart(2, "0")}-${match[3].padStart(2, "0")}`);
    };
    function quotedContractFinancialLines2(contract, asOf, notes, termination = false) {
      const lines = [];
      if (contract.financial_terms !== void 0) {
        const financial = row(contract.financial_terms);
        const labels2 = {
          amount: termination ? ["\uD574\uC9C0\uAE08\uC561(\uC6D0)"] : ["\uACC4\uC57D\uAE08\uC561(\uC6D0)", "\uACC4\uC57D\uAE08\uC561\uCD1D\uC561(\uC6D0)"],
          recent_revenue: ["\uCD5C\uADFC\uB9E4\uCD9C\uC561(\uC6D0)"],
          revenue_ratio: ["\uB9E4\uCD9C\uC561\uB300\uBE44(%)"]
        };
        const keys2 = Object.keys(financial);
        if (!keys2.length || keys2.some((key) => !Object.hasOwn(labels2, key))) throw invalid4();
        for (const key of ["amount", "recent_revenue", "revenue_ratio"]) {
          if (!Object.hasOwn(financial, key)) continue;
          const raw = row(financial[key]), quoted = field(raw);
          if (Object.keys(raw).sort().join(",") !== "label,value" || !labels2[key].includes(quoted.label.normalize("NFKC").replace(/\s+/g, ""))) throw invalid4();
          lines.push(`${quoted.label}: ${quoted.value}`);
        }
        lines.push("\uACC4\uC57D \uB0B4\uC5ED\uC5D0 \uBCF4\uACE0\uB41C \uAE08\uC561\xB7\uCD5C\uADFC \uB9E4\uCD9C\uC561\xB7\uBE44\uC728\uC774\uBA70 \uC5F0\uACB0 \uC815\uB3C4 \uC810\uC218\uB098 \uC5F0\uAC04 \uB9E4\uCD9C \uC758\uC874\uB3C4\uAC00 \uC544\uB2C8\uC5D0\uC694. \uB9E4\uCD9C \uAE30\uC900\uC5F0\uB3C4\xB7\uBCC4\uB3C4/\uC5F0\uACB0 \uAE30\uC900\uACFC \uD6C4\uC18D \uC815\uC815\uC740 \uC6D0\uBB38\uC744 \uD568\uAED8 \uD655\uC778\uD558\uC138\uC694.");
      }
      if (contract.revenue_basis !== void 0) {
        const basis = row(contract.revenue_basis), quoted = text7(basis.quote);
        const clauses = notes?.split(/(?<=[.!?])(?<![0-9]\.)\s+/).map((s) => s.trim()) || [];
        const references = clauses.filter((s) => /최근\s*매출액(?:\(원\))?['"‘’]?\s*(?:은|는)/.test(s));
        const match = quoted.match(/^(?:-\s*)?(?:상기\s*['"‘’]?(?:2\.\s*(?:계약|해지)내역\s*(?:중\s*|-\s*))?)?최근\s*매출액(?:\(원\))?['"‘’]?\s*(?:은|는)\s*(?:당사의\s*)?((?:19|20)\d{2})년(?:도|말)?\s*(연결|별도|개별)\s*재무제표\s*기준(?:임|입니다|\s*매출액입니다)\.$/);
        if (Object.keys(basis).sort().join(",") !== "quote,scope,year" || !Number.isSafeInteger(basis.year) || basis.year > Number(day(asOf).slice(0, 4)) || !match || Number(match[1]) !== basis.year || basis.scope !== (match[2] === "\uC5F0\uACB0" ? "consolidated" : "separate") || references.length !== 1 || references[0] !== quoted || row(contract.financial_terms).recent_revenue === void 0) throw invalid4();
        lines.push(
          `\uCD5C\uADFC \uB9E4\uCD9C\uC561 \uBD84\uBAA8 \uAE30\uC900 \xB7 ${basis.year}\uB144 \xB7 ${basis.scope === "consolidated" ? "\uC5F0\uACB0" : "\uBCC4\uB3C4/\uAC1C\uBCC4"} \uC7AC\uBB34\uC81C\uD45C`,
          `\uBD84\uBAA8 \uAE30\uC900 \uC6D0\uBB38 \xB7 ${quoted}`
        );
      }
      return lines;
    }
    function parseContractFacts2(value, doc) {
      if (value === void 0) return null;
      const facts = row(value), issuer = row(facts.issuer), filing = row(facts.filing);
      const receipt = text7(facts.receipt_no, 14), issuerId = text7(issuer.id, 9);
      const url = `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${receipt}`;
      if (facts.schema !== "dart-contract-fact-v1" || !/^\d{14}$/.test(receipt) || !/^KR:\d{6}$/.test(issuerId) || doc.id !== `DART:${receipt}` || doc.source !== "DART" || doc.url !== url || doc.company_ids.length !== 1 || doc.company_ids[0] !== issuerId || day(filing.filed_on) !== doc.as_of || titleKey2(text7(filing.title, 300)) !== "\uB2E8\uC77C\uD310\uB9E4\uACF5\uAE09\uACC4\uC57D\uCCB4\uACB0" || titleKey2(doc.title) !== titleKey2(text7(filing.title, 300)) || facts.counterparty_company_id !== null || facts.verified_common_event !== false || facts.current_contract_status !== "not-inferred") throw invalid4();
      text7(issuer.name, 160);
      const contract = row(facts.contract), period = row(contract.period);
      const lines = [
        "\uACF5\uC2DC \uBCF8\uBB38 \uBC1C\uCDCC",
        quote(contract.type),
        quote(contract.name),
        quote(contract.counterparty),
        `${text7(period.label)} \xB7 ${quote(period.start)} / ${quote(period.end)}`,
        quote(contract.signed_on)
      ];
      let financialNotes;
      if (contract.financial_notes !== void 0) {
        const raw = row(contract.financial_notes);
        financialNotes = field(raw);
        if (Object.keys(raw).sort().join(",") !== "label,value" || !/^(?:9|10)\.\s*기타\s*투자판단(?:에\s*참고할\s*사항|과\s*관련한\s*중요사항)$/.test(financialNotes.label)) throw invalid4();
      }
      lines.push(...quotedContractFinancialLines2(contract, doc.as_of, financialNotes?.value));
      if (financialNotes) lines.push(`${financialNotes.label}: ${financialNotes.value}`);
      if (facts.correction === null) {
        if (doc.title.includes("\uC815\uC815")) throw invalid4();
      } else {
        const correction = row(facts.correction);
        const corrected = field(correction.corrected_on), related = field(correction.related_filing_date);
        if (!doc.title.includes("\uC815\uC815") || quotedContractDay2(corrected.value) > doc.as_of || quotedContractDay2(related.value) > doc.as_of || !Array.isArray(correction.changes) || !correction.changes.length || correction.changes.length > 20) throw invalid4();
        lines.push(quote(correction.corrected_on), quote(correction.related_filing_date), quote(correction.reason));
        for (const raw of correction.changes) {
          const change = row(raw);
          lines.push(`${text7(change.field)} \xB7 \uC815\uC815 \uC804: ${text7(change.before)} \u2192 \uC815\uC815 \uD6C4: ${text7(change.after)}`);
        }
      }
      lines.push("\uACF5\uC2DC\uC758 \uD45C\uD604 \uADF8\uB300\uB85C\uC608\uC694. \u2018-\u2019\xB7\uC77C\uBC18 \uBA85\uCE6D\uC740 \uD2B9\uC815 \uAE30\uC5C5\uC73C\uB85C \uC5F0\uACB0\uD558\uC9C0 \uC54A\uC73C\uBA70 \uD604\uC7AC \uACC4\uC57D \uC720\uD6A8\uC131\uC774\uB098 \uC8FC\uAC00 \uC601\uD5A5\uC744 \uB73B\uD558\uC9C0 \uC54A\uC544\uC694.");
      return {
        explanation: lines.join("\n"),
        sources: [{ title: "\uACC4\uC57D\uACF5\uC2DC \uBCF8\uBB38", source: "DART", asOf: doc.as_of, url }]
      };
    }
    return __toCommonJS(PortfolioContractFacts_exports);
  })();
  return MemberMapContractFactsDelta;
})();
var { parseContractTermination } = ((contractBindings) => {
  var MemberMapContractTerminationDelta = (() => {
    var __defProp2 = Object.defineProperty;
    var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
    var __getOwnPropNames = Object.getOwnPropertyNames;
    var __hasOwnProp = Object.prototype.hasOwnProperty;
    var __export = (target, all) => {
      for (var name in all)
        __defProp2(target, name, { get: all[name], enumerable: true });
    };
    var __copyProps = (to, from, except, desc) => {
      if (from && typeof from === "object" || typeof from === "function") {
        for (let key of __getOwnPropNames(from))
          if (!__hasOwnProp.call(to, key) && key !== except)
            __defProp2(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
      }
      return to;
    };
    var __toCommonJS = (mod) => __copyProps(__defProp2({}, "__esModule", { value: true }), mod);
    var PortfolioContractTermination_exports = {};
    __export(PortfolioContractTermination_exports, {
      parseContractTermination: () => parseContractTermination2
    });
    var quotedContractDay2 = contractBindings.quotedContractDay;
    var quotedContractFinancialLines2 = contractBindings.quotedContractFinancialLines;
    var invalid4 = () => new Error("\uACC4\uC57D \uD574\uC9C0 \uACF5\uC2DC\uC758 \uADFC\uAC70\uB97C \uD655\uC778\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694.");
    var row = (value) => {
      if (!value || typeof value !== "object" || Array.isArray(value)) throw invalid4();
      return value;
    };
    var text7 = (value, max = 2e3) => {
      if (typeof value !== "string" || !value.trim() || value.length > max || /[<>\u0000-\u001f\u007f]/.test(value)) throw invalid4();
      return value;
    };
    var day = (value) => {
      const result = text7(value, 10);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(result) || !Number.isFinite(Date.parse(result)) || new Date(result).toISOString().slice(0, 10) !== result) throw invalid4();
      return result;
    };
    var titleKey2 = (value) => value.normalize("NFKC").trim().replace(/^\[(?:기재|첨부|기타)?정정\]/, "").replace(/[\sㆍ·ᆞ•]/g, "");
    var correctionTitle = (value) => /^\[(?:기재|첨부|기타)?정정\]/.test(value.normalize("NFKC").trim());
    var relatedTitleKey = (value) => value.normalize("NFKC").replace(/[\sㆍ·ᆞ•]/g, "");
    var field = (value) => {
      const item = row(value);
      return { label: text7(item.label), value: text7(item.value) };
    };
    var quote = (value) => {
      const item = field(value);
      return `${item.label}: ${item.value}`;
    };
    var dart = (receipt) => `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${receipt}`;
    function parseContractTermination2(value, doc, knownNames) {
      if (value === void 0) return null;
      const facts = row(value), issuer = row(facts.issuer), receipt = text7(facts.receipt_no, 14);
      const issuerId = text7(issuer.id, 9), name = text7(issuer.name, 160), sourceName = text7(issuer.source_name, 160);
      if (facts.schema !== "dart-contract-termination-v1" || facts.proves !== "termination-notice" || facts.current_contract_status !== "not-inferred" || !/^\d{14}$/.test(receipt) || !/^KR:\d{6}$/.test(issuerId) || doc.id !== `DART:${receipt}` || doc.source !== "DART" || doc.url !== dart(receipt) || doc.company_ids.length !== 1 || doc.company_ids[0] !== issuerId || day(facts.as_of) !== doc.as_of || titleKey2(text7(facts.filing_title, 300)) !== "\uB2E8\uC77C\uD310\uB9E4\uACF5\uAE09\uACC4\uC57D\uD574\uC9C0" || titleKey2(doc.title) !== "\uB2E8\uC77C\uD310\uB9E4\uACF5\uAE09\uACC4\uC57D\uD574\uC9C0" || correctionTitle(facts.filing_title) !== correctionTitle(doc.title) || knownNames && (!knownNames.includes(name) || !knownNames.includes(sourceName))) throw invalid4();
      const contract = row(facts.contract), period = row(contract.period), notice = row(facts.termination);
      if (quotedContractDay2(field(period.start).value) > quotedContractDay2(field(period.end).value)) throw invalid4();
      quotedContractDay2(field(notice.date).value);
      const lines = [
        "\uACC4\uC57D \uD574\uC9C0 \uD1B5\uBCF4 \uACF5\uC2DC \xB7 \uD604\uC7AC \uC885\uB8CC \uC5EC\uBD80\uB294 \uBBF8\uD655\uC778",
        quote(contract.name),
        quote(contract.counterparty),
        `${text7(period.label)} \xB7 ${quote(period.start)} / ${quote(period.end)}`,
        quote(notice.date),
        quote(notice.reason),
        quote(notice.other_matters)
      ];
      const notes = field(notice.other_matters).value;
      lines.push(...quotedContractFinancialLines2(contract, doc.as_of, notes, true));
      for (const [key, label2] of [["notice_on", "\uD574\uC9C0\uD1B5\uBCF4\uC77C"], ["effective_on", "\uD574\uC9C0\uBC1C\uD6A8\uC77C"]]) {
        if (notice[key] === void 0) continue;
        const stated = row(notice[key]), date = day(stated.date), quoted = text7(stated.quote);
        const clauses = notes.split(/(?<=[.!?])(?<![0-9]\.)\s+/).map((s) => s.trim());
        const mentions = clauses.flatMap((clause) => [...clause.matchAll(new RegExp(label2 + "\\s*\\(([^)]{1,40})\\)", "g"))].map((match) => ({ value: match[1], quote: clause })));
        if (Object.keys(stated).sort().join(",") !== "date,quote" || mentions.length !== 1 || mentions[0].quote !== quoted || quotedContractDay2(mentions[0].value) !== date || /아니|아닌|아님|아닐|아닙|않|미정|취소|철회|불확실|다른\s*계약|자회사/.test(quoted) || key === "notice_on" && (date !== quotedContractDay2(field(notice.date).value) || date > doc.as_of) || key === "effective_on" && (notice.notice_on === void 0 || date < day(row(notice.notice_on).date))) throw invalid4();
        lines.push(`${key === "notice_on" ? "\uC6D0\uBB38 \uBA85\uC2DC \uD1B5\uC9C0\uC77C" : "\uC6D0\uBB38 \uBA85\uC2DC \uBC1C\uD6A8\uC77C"} \xB7 ${date}`, `${label2} \uADFC\uAC70 \uC6D0\uBB38 \xB7 ${quoted}`);
      }
      const links = notice.related_filings, documents = notice.related_documents === void 0 ? [] : notice.related_documents;
      if (!Array.isArray(links) || !Array.isArray(documents) || links.length + documents.length < 1 || links.length + documents.length > 20) throw invalid4();
      const seen = /* @__PURE__ */ new Set(), sources = [
        { title: "\uACC4\uC57D \uD574\uC9C0 \uACF5\uC2DC", source: "DART", asOf: doc.as_of, url: doc.url }
      ];
      const addRelated = (raw, contract2) => {
        const link = row(raw), previous = text7(link.receipt_no, 14), published = day(link.filed_on), title = text7(link.title, 300);
        const isContract = relatedTitleKey(title) === "\uB2E8\uC77C\uD310\uB9E4\uACF5\uAE09\uACC4\uC57D\uCCB4\uACB0";
        if (!/^\d{14}$/.test(previous) || seen.has(previous) || previous === receipt || published > doc.as_of || previous.slice(0, 8) !== published.replaceAll("-", "") || isContract !== contract2 || link.href !== `/dsaf001/main.do?rcpNo=${previous}`) throw invalid4();
        seen.add(previous);
        sources.push({ title: `\uACF5\uC2DC\uAC00 \uBA85\uC2DC\uD55C ${contract2 ? "\uACC4\uC57D \uC6D0\uBB38" : "\uAE30\uD0C0 \uC6D0\uBB38"} \xB7 ${title}`, source: "DART", asOf: published, url: dart(previous) });
      };
      for (const raw of links) addRelated(raw, true);
      for (const raw of documents) addRelated(raw, false);
      lines.push("\uD1B5\uBCF4\uC77C\uACFC \uD6A8\uB825\uC77C\uC740 \uB2E4\uB97C \uC218 \uC788\uC5B4\uC694. \uACC4\uC57D \uBC94\uC704\xB7\uD6A8\uB825 \uBC1C\uC0DD \uC5EC\uBD80\uB97C \uC784\uC758\uB85C \uD310\uB2E8\uD558\uC9C0 \uC54A\uC544\uC694. \uAD00\uB828 \uC6D0\uBB38 \uB9C1\uD06C\uB294 \uD574\uC9C0 \uACF5\uC2DC\uC5D0 \uBA85\uC2DC\uB41C \uC5F0\uACB0\uC774\uC5D0\uC694.");
      return { explanation: lines.join("\n"), sources };
    }
    return __toCommonJS(PortfolioContractTermination_exports);
  })();
  return MemberMapContractTerminationDelta;
})({ quotedContractDay, quotedContractFinancialLines });
var { parseContractEvents, projectContractEventMeasure, projectContractPrototype } = ((secBindings) => {
  var MemberMapContractEventsDelta = (() => {
    var __defProp2 = Object.defineProperty;
    var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
    var __getOwnPropNames = Object.getOwnPropertyNames;
    var __hasOwnProp = Object.prototype.hasOwnProperty;
    var __export = (target, all) => {
      for (var name in all)
        __defProp2(target, name, { get: all[name], enumerable: true });
    };
    var __copyProps = (to, from, except, desc) => {
      if (from && typeof from === "object" || typeof from === "function") {
        for (let key of __getOwnPropNames(from))
          if (!__hasOwnProp.call(to, key) && key !== except)
            __defProp2(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
      }
      return to;
    };
    var __toCommonJS = (mod) => __copyProps(__defProp2({}, "__esModule", { value: true }), mod);
    var PortfolioContractEvents_exports = {};
    __export(PortfolioContractEvents_exports, {
      parseContractEvents: () => parseContractEvents2,
      projectContractEventMeasure: () => projectContractEventMeasure2,
      projectContractPrototype: () => projectContractPrototype2
    });
    var parseContractFacts2 = secBindings.parseContractFacts;
    var quotedContractDay2 = secBindings.quotedContractDay;
    var parseDocumentLineage2 = secBindings.parseDocumentLineage;
    var parseContractTermination2 = secBindings.parseContractTermination;
    var portfolioDocumentIdentity2 = secBindings.portfolioDocumentIdentity;
    var invalid4 = () => new Error("\uACC4\uC57D \uC0AC\uAC74\uC758 \uC5F0\uACB0 \uADFC\uAC70\uB97C \uD655\uC778\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694.");
    var row = (v) => {
      if (!v || typeof v !== "object" || Array.isArray(v)) throw invalid4();
      return v;
    };
    var text7 = (v, max = 2e3) => {
      if (typeof v !== "string" || !v.trim() || v.length > max || /[<>\u0000-\u001f\u007f]/.test(v)) throw invalid4();
      return v;
    };
    var list3 = (v, max) => {
      if (!Array.isArray(v) || v.length > max) throw invalid4();
      return v;
    };
    var day = (v) => {
      const s = text7(v, 10);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(s) || !Number.isFinite(Date.parse(s)) || new Date(s).toISOString().slice(0, 10) !== s) throw invalid4();
      return s;
    };
    var legal = (s) => s.normalize("NFKC").toLowerCase().replace(/\s+/g, "").replace(/^(?:주식회사|\(주\))|(?:주식회사|\(주\))$/g, "");
    function contractFactProjection(value) {
      let closed = true;
      const pick = (value2, fields3) => {
        const v = row(value2);
        if (Object.keys(v).sort().join() !== [...fields3].sort().join()) closed = false;
        return Object.fromEntries(fields3.map((k) => [k, v[k]]));
      };
      const field = (value2) => {
        const f2 = pick(value2, ["label", "value"]);
        return { label: text7(f2.label), value: text7(f2.value) };
      };
      const f = pick(value, [
        "schema",
        "receipt_no",
        "issuer",
        "filing",
        "contract",
        "correction",
        "counterparty_company_id",
        "verified_common_event",
        "current_contract_status"
      ]);
      f.issuer = pick(f.issuer, ["id", "name"]);
      f.filing = pick(f.filing, ["title", "filed_on"]);
      const raw = row(f.contract), optional = ["financial_terms", "financial_notes", "revenue_basis"].filter((k) => Object.hasOwn(raw, k));
      const c = pick(raw, ["type", "name", "counterparty", "period", "signed_on", ...optional]);
      for (const k of ["type", "name", "counterparty", "signed_on"]) c[k] = field(c[k]);
      const p = pick(c.period, ["label", "start", "end"]);
      c.period = { label: text7(p.label), start: field(p.start), end: field(p.end) };
      if (Object.hasOwn(c, "financial_terms")) {
        const terms = row(c.financial_terms), allowed = ["amount", "recent_revenue", "revenue_ratio"].filter((k) => Object.hasOwn(terms, k));
        const selected = pick(terms, allowed);
        c.financial_terms = Object.fromEntries(allowed.map((k) => [k, field(selected[k])]));
      }
      if (Object.hasOwn(c, "financial_notes")) c.financial_notes = field(c.financial_notes);
      if (Object.hasOwn(c, "revenue_basis")) {
        const basis = row(c.revenue_basis);
        const exact = Object.keys(basis).sort().join() === "quote,scope,year";
        if (exact) c.revenue_basis = pick(basis, ["year", "scope", "quote"]);
        else {
          closed = false;
          delete c.revenue_basis;
        }
      }
      f.contract = c;
      if (f.correction !== null) {
        const correction = pick(f.correction, ["corrected_on", "related_filing_date", "reason", "changes"]);
        for (const k of ["corrected_on", "related_filing_date", "reason"]) correction[k] = field(correction[k]);
        correction.changes = list3(correction.changes, 20).map((v) => {
          const change = pick(v, ["field", "before", "after"]);
          return { field: text7(change.field), before: text7(change.before), after: text7(change.after) };
        });
        f.correction = correction;
      }
      return { facts: f, closed };
    }
    async function contractJudgmentBinding(e) {
      const canonical = (v) => Array.isArray(v) ? "[" + v.map(canonical).join(", ") + "]" : v && typeof v === "object" ? "{" + Object.keys(v).sort().map((k) => JSON.stringify(k) + ": " + canonical(v[k])).join(", ") + "}" : JSON.stringify(v);
      const fields3 = ["id", "root_receipt", "participants", "signed_on", "title", "as_of", "current_status"];
      const docs = [];
      for (const d of e.documents) {
        const projected = contractFactProjection(d.contract_facts);
        if (!projected.closed) return void 0;
        docs.push({
          ...Object.fromEntries(["id", "url", "title", "as_of", "company_ids"].map((k) => [k, d[k]])),
          contract_facts: projected.facts
        });
      }
      const body = { ...Object.fromEntries(fields3.map((k) => [k, e[k]])), documents: docs, termination_notices: e.termination_notices || [] };
      const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonical(body)));
      const latest = docs.filter((d) => d.as_of === e.as_of);
      if (latest.length !== 1) return void 0;
      return {
        revision: Array.from(new Uint8Array(hash), (n) => n.toString(16).padStart(2, "0")).join(""),
        sourceReceipt: latest[0].id.slice(5),
        facts: { contract: latest[0].contract_facts.contract, correction: latest[0].contract_facts.correction }
      };
    }
    function projectContractEventMeasure2(facts) {
      if (!facts.length) return null;
      const latestDate = facts.reduce((latest2, fact) => fact.date > latest2 ? fact.date : latest2, "");
      const latest = facts.filter((fact) => fact.date === latestDate);
      const periods = new Set(latest.map((fact) => JSON.stringify([fact.start, fact.end])));
      return periods.size === 1 ? {
        kind: "reported-contract-period",
        label: "\uACC4\uC57D\uAE30\uAC04",
        value: `${latest[0].start} ~ ${latest[0].end}`,
        sourceLabel: latest[0].label,
        start: latest[0].start,
        end: latest[0].end,
        asOf: latestDate,
        sourceUrl: latest[0].sourceUrl
      } : null;
    }
    async function parseContractEvents2(value, companies) {
      if (value === void 0) return [];
      const payload = row(value), rawItems = list3(payload.items, 20), coverage = row(payload.coverage);
      if (!Number.isSafeInteger(coverage.selected) || coverage.selected < rawItems.length || coverage.returned !== rawItems.length || coverage.omitted !== coverage.selected - rawItems.length) throw invalid4();
      if (coverage.oversized_history !== void 0 && (!Number.isSafeInteger(coverage.oversized_history) || coverage.oversized_history < 0 || coverage.oversized_history > coverage.omitted)) throw invalid4();
      const seen = /* @__PURE__ */ new Set(), usedDocuments = /* @__PURE__ */ new Set(), out = [];
      const named = (id, value2) => {
        const supplied = companies.get(id), names = typeof supplied === "string" ? [supplied] : list3(supplied, 4);
        return names.some((name) => legal(text7(name, 180)) === legal(value2));
      };
      for (const raw of rawItems) {
        const e = row(raw), id = text7(e.id, 80), root = text7(e.root_receipt, 14), asOf = day(e.as_of);
        const participants2 = list3(e.participants, 2).map((v) => {
          const p = row(v), id2 = text7(p.id, 9);
          if (!/^KR:\d{6}$/.test(id2) || !["supplier", "counterparty"].includes(p.role)) throw invalid4();
          return { id: id2, role: p.role };
        });
        if (participants2.length !== 2 || participants2[0].role !== "supplier" || participants2[1].role !== "counterparty" || participants2[0].id === participants2[1].id || !/^\d{14}$/.test(root) || id !== `contract:${participants2[0].id}:${root}` || seen.has(id) || e.kind !== "reported-contract" || e.identity_basis !== "explicit-contract-parties" || e.current_status !== "not-inferred" || JSON.stringify(e.company_ids) !== JSON.stringify(participants2.map((p) => p.id))) throw invalid4();
        seen.add(id);
        const selectedIds = participants2.map((p) => p.id).filter((id2) => companies.has(id2)).sort();
        if (!selectedIds.length || JSON.stringify(selectedIds) !== JSON.stringify(e.selected_company_ids)) throw invalid4();
        const documents = list3(e.documents, 100), legacyIds = [], sourceDocumentIds = [];
        const evidence = [], terms = [];
        const corrections = [];
        const periodFacts = [];
        let latestDay = "", latestTitle = "", archivedDocumentCount = 0, correctionCount = 0;
        const archive = (d) => {
          if (d.capture_archive === void 0) return;
          if (d.capture_archive !== "retained-public-capture") throw invalid4();
          archivedDocumentCount++;
        };
        for (const rawDoc of documents) {
          const d = row(rawDoc), doc = {
            id: text7(d.id, 40),
            source: text7(d.source, 20),
            url: text7(d.url),
            title: text7(d.title, 300),
            as_of: day(d.as_of),
            company_ids: list3(d.company_ids, 1).map((id2) => text7(id2, 9))
          };
          const f = contractFactProjection(d.contract_facts).facts;
          const fact = parseContractFacts2(f, doc), lineage = parseDocumentLineage2(d.event_lineage, doc);
          if (!fact || doc.company_ids[0] !== participants2[0].id || usedDocuments.has(doc.id) || (lineage ? d.event_lineage.root_receipt !== root : doc.id !== `DART:${root}`)) throw invalid4();
          usedDocuments.add(doc.id);
          archive(d);
          const c = row(f.contract), period = row(c.period);
          const name = text7(row(c.name).value), signed = quotedContractDay2(row(c.signed_on).value);
          const periodStart = quotedContractDay2(row(period.start).value), periodEnd = quotedContractDay2(row(period.end).value);
          if (signed !== day(e.signed_on) || signed > doc.as_of || periodStart > periodEnd || /미정|미확정|예정|협의|의향|양해|MOU|LOI|가계약/i.test(name) || companies.has(participants2[0].id) && !named(participants2[0].id, text7(row(f.issuer).name)) || companies.has(participants2[1].id) && !named(participants2[1].id, text7(row(c.counterparty).value))) throw invalid4();
          terms.push(legal(name));
          const correction = f.correction === null ? null : row(f.correction);
          if (correction) correctionCount++;
          const measureDate = correction ? quotedContractDay2(row(correction.corrected_on).value) : doc.as_of;
          if (correction) corrections.push({
            asOf: measureDate,
            filedOn: doc.as_of,
            sourceUrl: doc.url,
            reason: correction.reason.value,
            changes: correction.changes.map((change) => ({
              field: change.field,
              before: change.before,
              after: change.after
            }))
          });
          periodFacts.push({ date: measureDate, start: periodStart, end: periodEnd, label: text7(period.label), sourceUrl: doc.url });
          if (doc.as_of >= latestDay) {
            latestDay = doc.as_of;
            latestTitle = name;
          }
          const identity2 = await portfolioDocumentIdentity2(doc.url);
          if (!identity2) throw invalid4();
          legacyIds.push(identity2.id);
          sourceDocumentIds.push(doc.id);
          evidence.push({ url: doc.url, source: "DART", asOf: doc.as_of, explanation: fact.explanation });
          for (const s of lineage?.sources || []) {
            if (s.url) {
              const legacy = await portfolioDocumentIdentity2(s.url);
              if (legacy && !legacyIds.includes(legacy.id)) legacyIds.push(legacy.id);
            }
            if (s.url && s.asOf && !evidence.some((proof) => proof.url === s.url))
              evidence.push({ url: s.url, source: "DART", asOf: s.asOf, explanation: "DART\uAC00 \uC5F0\uACB0\uD55C \uACF5\uC2DC \uC774\uB825 \xB7 \uD604\uC7AC \uACC4\uC57D \uC0C1\uD0DC\xB7\uC8FC\uAC00 \uC601\uD5A5\uC740 \uBBF8\uD655\uC778" });
          }
        }
        if (!documents.length || new Set(terms).size !== 1 || latestDay !== asOf || latestTitle !== e.title) throw invalid4();
        const measure = projectContractEventMeasure2(periodFacts);
        const notices = list3(e.termination_notices === void 0 ? [] : e.termination_notices, 100);
        const priorReferences = /* @__PURE__ */ new Map();
        for (const d of documents) {
          priorReferences.set(d.id.slice(5), d.as_of);
          for (const m of d.event_lineage?.members || []) priorReferences.set(m.receipt_no, m.published_on);
        }
        const noticeIds = /* @__PURE__ */ new Set();
        for (const rawNotice of notices) {
          const d = row(rawNotice), doc = {
            id: text7(d.id, 40),
            source: text7(d.source, 20),
            url: text7(d.url),
            title: text7(d.title, 300),
            as_of: day(d.as_of),
            company_ids: list3(d.company_ids, 1).map((id2) => text7(id2, 9))
          };
          const declared = companies.get(participants2[0].id), names = typeof declared === "string" ? [declared] : declared;
          const notice = parseContractTermination2(d.contract_termination, doc, names);
          if (!notice || doc.company_ids[0] !== participants2[0].id || noticeIds.has(doc.id) || !d.contract_termination.termination.related_filings.some((link) => priorReferences.get(link.receipt_no) === link.filed_on)) throw invalid4();
          noticeIds.add(doc.id);
          archive(d);
          const identity2 = await portfolioDocumentIdentity2(doc.url);
          if (!identity2) throw invalid4();
          legacyIds.push(identity2.id);
          sourceDocumentIds.push(doc.id);
          evidence.push({ url: doc.url, source: "DART", asOf: doc.as_of, explanation: notice.explanation });
          for (const source of notice.sources) if (source.url && source.asOf && !evidence.some((e2) => e2.url === source.url))
            evidence.push({ url: source.url, source: "DART", asOf: source.asOf, explanation: "\uD574\uC9C0 \uACF5\uC2DC\uAC00 \uBA85\uC2DC\uD55C \uAD00\uB828 \uC6D0\uBB38 \xB7 \uD604\uC7AC \uC885\uB8CC \uC5EC\uBD80\uB294 \uBCC4\uB3C4 \uD655\uC778" });
        }
        const fingerprint = JSON.stringify([id, latestTitle, participants2, evidence]);
        const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(fingerprint));
        const hex = Array.from(new Uint8Array(hash), (n) => n.toString(16).padStart(2, "0")).join("");
        out.push({
          id,
          title: latestTitle,
          asOf: evidence.reduce((latest, proof) => proof.asOf > latest ? proof.asOf : latest, asOf),
          participants: participants2,
          selectedIds,
          legacyIds,
          sourceDocumentIds,
          measure,
          evidence,
          terminationNoticeCount: notices.length,
          archivedDocumentCount,
          correctionCount,
          corrections,
          periodConflict: periodFacts.length > 0 && measure === null,
          read_revision: Number.parseInt(hex.slice(0, 13), 16) || 1,
          judgmentBinding: await contractJudgmentBinding(e)
        });
      }
      return out;
    }
    function projectContractPrototype2(graph) {
      const events = graph.contractEvents || [];
      const nodes = events.map((e, i) => ({
        id: e.id,
        kind: "event",
        recordKind: "event",
        layer: "filing",
        topic: "supply",
        name: e.title.slice(0, 300),
        code: "\uACF5\uC2DC\uC0C1 \uACC4\uC57D \uC0AC\uAC74",
        priority: 2,
        logo: "",
        proofLabel: "\uACF5\uC2DC \uBCF8\uBB38\uC5D0 \uACC4\uC57D \uB2F9\uC0AC\uC790 \uBA85\uC2DC",
        measure: e.measure,
        contractJudgmentBinding: e.judgmentBinding,
        lifecycle: {
          currentStatus: "unverified",
          terminationNoticeCount: e.terminationNoticeCount,
          correctionCount: e.correctionCount,
          periodConflict: e.periodConflict
        },
        reason: "\uACF5\uC2DC\uC5D0 \uBA85\uC2DC\uB41C \uACC4\uC57D\uC758 \uACF5\uAE09\uC790\xB7\uC0C1\uB300\uBC29\uC744 \uC5F0\uACB0\uD588\uC5B4\uC694. \uD604\uC7AC \uACC4\uC57D \uC720\uD6A8\uC131\xB7\uC774\uD589 \uC5EC\uBD80\xB7\uC8FC\uAC00 \uC601\uD5A5\uC740 \uBBF8\uD655\uC778\uC774\uC5D0\uC694." + (e.terminationNoticeCount ? " \uD574\uC9C0 \uD1B5\uBCF4 \uACF5\uC2DC\uAC00 \uC788\uC5B4\uC694. \uD1B5\uBCF4\uC77C\uACFC \uD6A8\uB825\uC77C\uC740 \uC6D0\uBB38\uC5D0\uC11C \uAD6C\uBD84\uD574 \uD655\uC778\uD558\uC138\uC694." : "") + (e.archivedDocumentCount ? ` \uCD5C\uC2E0 \uBAA9\uB85D \uBC16\uC758 \uBCF4\uAD00\uD55C \uC6D0\uBB38 ${e.archivedDocumentCount}\uAC74\uC774 \uD3EC\uD568\uB3FC\uC694. \uC6D0\uB798 \uACF5\uC2DC \uAE30\uC900\uC77C\uB85C \uD45C\uC2DC\uD574\uC694.` : ""),
        source: "DART",
        asOf: e.asOf,
        evidence: e.evidence,
        corrections: e.corrections,
        legacyIds: e.legacyIds,
        read_revision: e.read_revision,
        x: 1.1 + i % 3 * 0.2,
        y: 0.7 + Math.floor(i / 3) * 0.2
      }));
      const edges = events.flatMap((e) => e.participants.filter((p) => e.selectedIds.includes(p.id)).map((p) => {
        const ticker = p.id.slice(3), reason = p.role === "supplier" ? "\uACC4\uC57D \uACF5\uAE09\uC790" : "\uACC4\uC57D \uC0C1\uB300\uBC29";
        return {
          id: `contract-link:${e.id}:${p.id}`,
          from: e.id,
          to: `company:${ticker}`,
          type: "documented",
          confirmation: "confirmed",
          strength: 0,
          impact: "\uBBF8\uD655\uC778",
          impactReason: "\uACF5\uC2DC\uC0C1 \uCC38\uC5EC \uC5ED\uD560\uC774\uBA70 \uD604\uC7AC \uC2E4\uC801\xB7\uC8FC\uAC00 \uC601\uD5A5\uC744 \uB73B\uD558\uC9C0 \uC54A\uC544\uC694.",
          reason,
          verb: reason,
          source: "DART",
          asOf: e.asOf,
          evidence: e.evidence,
          measure: e.measure,
          legacyIds: graph.links.filter((l) => l.ticker === ticker && e.legacyIds.includes(l.documentId)).map((l) => l.id)
        };
      }));
      return {
        nodes,
        edges,
        recordsMap: Object.fromEntries(nodes.map((n) => [
          n.id,
          { id: n.id, read_revision: n.read_revision, sourceURLs: n.evidence.map((e) => e.url) }
        ])),
        replacedDocumentIds: new Set(events.flatMap((e) => e.legacyIds))
      };
    }
    return __toCommonJS(PortfolioContractEvents_exports);
  })();
  return MemberMapContractEventsDelta;
})({ parseContractFacts, quotedContractDay, parseContractTermination, parseDocumentLineage, portfolioDocumentIdentity });
var fail = () => {
  throw Error("invalid-local-ai-review");
};
var object2 = (v) => v && typeof v === "object" && !Array.isArray(v) ? v : fail();
var keys = (v, expected) => {
  object2(v);
  if (Object.keys(v).sort().join() !== [...expected].sort().join()) fail();
};
var text10 = (v, max) => typeof v === "string" && v.trim() && v.length <= max && !/[<>\u0000-\u001f]/.test(v) ? v : fail();
var entity2 = (v) => /^(KR:[0-9]{6}|US:[A-Z][A-Z0-9.-]{0,12})$/.test(text10(v, 20)) ? v : fail();
var claimStates = { asserted: "\uC6D0\uBB38 \uC9C4\uC220", planned: "\uACC4\uD68D", conditional: "\uC870\uAC74\uBD80", negated: "\uBD80\uC815", historical: "\uACFC\uAC70", conflicted: "\uC0C1\uCDA9" };
var missingLabels = { entity_scope: "\uD68C\uC0AC \uADC0\uC18D", role: "\uAC70\uB798 \uC5ED\uD560", object: "\uAC70\uB798 \uB300\uC0C1", period: "\uC801\uC6A9 \uC2DC\uC810", scale: "\uAC70\uB798 \uADDC\uBAA8", denominator: "\uBE44\uC911\uC758 \uBD84\uBAA8", structured_table: "\uD45C\uC758 \uD589\xB7\uC5F4 \uC6D0\uBB38", counter_evidence_not_searched: "\uBCC4\uB3C4 \uBC18\uB300 \uADFC\uAC70 \uC870\uC0AC", path_evidence: "\uAC04\uC811 \uACBD\uB85C \uADFC\uAC70", source_context: "\uC8FC\uBCC0 \uC6D0\uBB38" };
function claimDetails(value) {
  if (!Array.isArray(value) || value.length < 1 || value.length > 4) fail();
  const lines = [], states = [];
  for (const item of value) {
    const c = object2(item);
    keys(c, ["claim_kind", "directness", "claim_state", "quote", "context", "scope_quote", "channel_quote", "counter_evidence_quotes", "missing_evidence", "review_reasons", "decision", "degree", "degree_basis"]);
    if (!["relation_fact", "conditional_exposure", "co_mention"].includes(c.claim_kind) || !["direct", "indirect", "not_applicable"].includes(c.directness) || !Object.hasOwn(claimStates, c.claim_state) || !["candidate", "needs_context", "conflict"].includes(c.decision) || c.degree !== "unrated" || c.degree_basis !== "unrated") fail();
    const quote3 = text10(c.quote, 600), label2 = claimStates[c.claim_state];
    states.push(label2);
    lines.push(`${label2} \xB7 ${c.claim_kind === "co_mention" ? "\uB3D9\uC2DC \uC5B8\uAE09" : c.claim_kind === "conditional_exposure" ? "\uC870\uAC74\uBD80 \uC601\uD5A5" : "\uAD00\uACC4 \uC9C4\uC220"} \xB7 AI \uD574\uC11D`, quote3);
    keys(c.context, ["object_quote", "scale_quote", "time_quote"]);
    for (const [key, title] of [["object_quote", "\uAC70\uB798 \uB300\uC0C1"], ["scale_quote", "\uADDC\uBAA8 \uC6D0\uBB38"], ["time_quote", "\uC801\uC6A9 \uC2DC\uC810"]]) {
      if (c.context[key] === null) continue;
      const span = text10(c.context[key], key === "scale_quote" ? 600 : 120);
      if (!quote3.includes(span)) fail();
      lines.push(`${title}: ${span}`);
    }
    for (const [key, title] of [["scope_quote", "\uC801\uC6A9 \uBC94\uC704"], ["channel_quote", "\uC804\uB2EC \uACBD\uB85C"]]) {
      if (c[key] === null) continue;
      const span = text10(c[key], 600);
      if (!quote3.includes(span)) fail();
      lines.push(`${title}: ${span}`);
    }
    if (!Array.isArray(c.counter_evidence_quotes) || c.counter_evidence_quotes.length > 4 || !Array.isArray(c.missing_evidence) || c.missing_evidence.length > 11 || c.missing_evidence.some((m) => !Object.hasOwn(missingLabels, m)) || !Array.isArray(c.review_reasons) || c.review_reasons.length > 10) fail();
    for (const q of c.counter_evidence_quotes) lines.push(`\uAC19\uC740 \uBC1C\uCDCC\uBB38 \uC548\uC758 \uBC18\uB300 \uADFC\uAC70: ${text10(q, 600)}`);
    for (const reason of c.review_reasons) if (!/^[a-z-]{1,60}$/.test(text10(reason, 60))) fail();
    if (c.review_reasons.length) lines.push("\uD68C\uC0AC \uADC0\uC18D\xB7\uC2DC\uC810\xB7\uBC29\uD5A5 \uB610\uB294 \uBB38\uB9E5 \uAC80\uD1A0\uAC00 \uD544\uC694\uD574\uC694.");
    if (c.missing_evidence.length) lines.push(`\uCD94\uAC00 \uD655\uC778: ${c.missing_evidence.map((m) => missingLabels[m]).join(" \xB7 ")}`);
  }
  lines.push("\uC5F0\uACB0 \uC815\uB3C4 \uBBF8\uD3C9\uAC00 \xB7 \uD655\uC778\uB41C \uAD00\uACC4\uB098 \uC8FC\uAC00 \uC601\uD5A5\uC73C\uB85C \uD655\uC815\uD558\uC9C0 \uC54A\uC558\uC5B4\uC694.");
  return { lines, states: [...new Set(states)] };
}
function attachLocalAICandidates(graph, payload, label2 = "\uB85C\uCEEC AI \uD6C4\uBCF4") {
  if (payload === void 0) return graph;
  const body = object2(payload);
  keys(body, ["schema", "candidates", "coverage"]);
  if (body.schema !== "local-ai-review-v1" || !Array.isArray(body.candidates) || body.candidates.length > 40) fail();
  const coverage = object2(body.coverage);
  keys(coverage, ["input", "accepted", "rejected", "skipped", "matched", "returned", "omitted"]);
  if (Object.values(coverage).some((v) => !Number.isSafeInteger(v) || v < 0) || coverage.input !== coverage.accepted + coverage.rejected + coverage.skipped || coverage.matched > coverage.accepted || coverage.returned !== body.candidates.length || coverage.matched !== coverage.returned + coverage.omitted) fail();
  const selected = new Set(graph.companies.map((c) => `${c.market}:${c.ticker}`));
  const ids = new Set((graph.automaticRelations || []).map((r) => r.id));
  const relations = body.candidates.map((value) => {
    const r = object2(value);
    keys(r, [
      "id",
      "revision",
      "issuer_id",
      "issuer_name",
      "counterparty_id",
      "counterparty_name",
      "role",
      "quote",
      "source_id",
      "url",
      "as_of",
      "status",
      "verification",
      "evidence_scope",
      "current_validity",
      ..."context" in r ? ["context"] : [],
      ..."claims" in r ? ["claims"] : []
    ]);
    const id = text10(r.id, 50), revision2 = text10(r.revision, 64), issuer = entity2(r.issuer_id), target = entity2(r.counterparty_id);
    const issuerName = text10(r.issuer_name, 160), targetName = text10(r.counterparty_name, 160), quote3 = text10(r.quote, 1e4);
    const source = text10(r.source_id, 40), url = text10(r.url, 100), asOf = text10(r.as_of, 10);
    if (!/^automatic:ai:[a-f0-9]{24}$/.test(id) || ids.has(id) || !/^[a-f0-9]{64}$/.test(revision2) || issuer === target || !selected.has(issuer) && !selected.has(target) || !/^source:dart:[0-9]{14}$/.test(source) || url !== `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${source.slice(12)}` || !/^\d{4}-\d{2}-\d{2}$/.test(asOf) || !Number.isFinite(Date.parse(asOf)) || new Date(asOf).toISOString().slice(0, 10) !== asOf || !("claims" in r ? ["customer", "supplier", "partner", "other"] : ["customer", "supplier"]).includes(r.role) || r.status !== "ai_candidate" || r.verification !== "unreviewed-model-extraction" || r.current_validity !== "not-inferred" || !["historical-context", "unspecified"].includes(r.evidence_scope)) fail();
    ids.add(id);
    const detail = "claims" in r ? claimDetails(r.claims) : null;
    const roleLabel = detail ? `${detail.states.join("\xB7")} \uD6C4\uBCF4` : r.role === "customer" ? "\uACE0\uAC1D \uD6C4\uBCF4" : "\uACF5\uAE09\uC5C5\uCCB4 \uD6C4\uBCF4";
    const scope = r.evidence_scope === "historical-context" ? "\uACFC\uAC70 \uBB38\uB9E5\uC758 \uAC70\uB798 \xB7 \uD604\uC7AC \uC9C0\uC18D \uC5EC\uBD80 \uBBF8\uD655\uC778" : "\uD604\uC7AC \uC720\uD6A8 \uC5EC\uBD80 \uBBF8\uD655\uC778";
    const interpretation = [];
    if (detail) interpretation.push(...detail.lines);
    if ("context" in r) {
      keys(r.context, ["object_quote", "scale_quote", "time_quote"]);
      for (const [key, label3] of [["object_quote", "\uAC70\uB798 \uB300\uC0C1"], ["scale_quote", "\uADDC\uBAA8 \uC6D0\uBB38"], ["time_quote", "\uAC70\uB798 \uC2DC\uC810 \uC6D0\uBB38"]]) {
        const value2 = r.context[key];
        if (value2 === null) continue;
        const span = text10(value2, key === "scale_quote" ? 600 : 120);
        if (!quote3.includes(span)) fail();
        interpretation.push(`${label3}: ${span}`);
      }
      interpretation.unshift(`AI \uD574\uC11D \xB7 ${r.role === "customer" ? "\uB9E4\uCD9C \uC5F0\uACB0 \uD6C4\uBCF4" : "\uC870\uB2EC \uC5F0\uACB0 \uD6C4\uBCF4"}`);
      interpretation.push("\uC5F0\uACB0 \uC815\uB3C4 \uBBF8\uD3C9\uAC00 \xB7 \uAE30\uC5C5\uBCC4 \uAC70\uB798 \uADDC\uBAA8\xB7\uC758\uC874\uB3C4 \uAC80\uD1A0\uAC00 \uD544\uC694\uD574\uC694.");
    }
    return {
      id,
      read_revision: Number.parseInt(revision2.slice(0, 13), 16) + 1,
      reported: false,
      title: `AI ${roleLabel}`,
      source: "DART \xB7 AI \uCD94\uCD9C \uD6C4\uBCF4",
      asOf,
      url,
      reason: `\uBBF8\uAC80\uC218 AI \uD6C4\uBCF4 \xB7 ${issuerName} \u2192 ${targetName}. ${scope}. \uAD00\uACC4 \uBC29\uD5A5\xB7\uADDC\uBAA8\xB7\uC8FC\uAC00 \uC601\uD5A5\uC740 \uD655\uC815\uD558\uC9C0 \uC54A\uC558\uC5B4\uC694.
${interpretation.length ? interpretation.join("\n") + "\n" : ""}${detail ? "" : quote3}`,
      participants: [
        { id: issuer, name: issuerName, role: "document_issuer", roleLabel: "\uACF5\uC2DC \uC791\uC131 \uD68C\uC0AC" },
        { id: target, name: targetName, role: `candidate_${r.role}`, roleLabel }
      ]
    };
  });
  return {
    ...graph,
    aiReviewStatus: "ready",
    automaticRelations: [...graph.automaticRelations || [], ...relations],
    analysisNotice: [graph.analysisNotice, `${label2} ${coverage.returned}/${coverage.matched}\uAC74 \xB7 \uBBF8\uAC80\uC218`].filter(Boolean).join(" \xB7 ")
  };
}
function attachPublicAIReview(graph, payload, coverage) {
  if (coverage === void 0 && payload === void 0) return graph;
  const meta = object2(coverage);
  keys(meta, ["status"]);
  if (meta.status === "ready") {
    if (payload === void 0) fail();
    return attachLocalAICandidates(graph, payload, "AI \uBD84\uC11D \uD6C4\uBCF4");
  }
  if (!["unavailable", "rejected"].includes(meta.status) || payload !== void 0) fail();
  return {
    ...graph,
    aiReviewStatus: meta.status,
    analysisNotice: [graph.analysisNotice, meta.status === "rejected" ? "AI \uBD84\uC11D \uC790\uB8CC \uAC80\uC99D \uC2E4\uD328 \xB7 \uAE30\uC874 \uACF5\uAC1C\uC790\uB8CC\uB294 \uD45C\uC2DC\uD574\uC694." : "AI \uBD84\uC11D \uC790\uB8CC \uC5F0\uACB0 \uB300\uAE30 \xB7 \uAD00\uACC4\uAC00 \uC5C6\uB2E4\uB294 \uB73B\uC740 \uC544\uB2C8\uC5D0\uC694."].filter(Boolean).join(" \xB7 ")
  };
}
function memberMapLoadDiagnostic(stage, error, response, isCurrent) {
  try {
    if (typeof window === "undefined") return;
    const flags = new URLSearchParams(window.location.search).getAll("mapDiagnostics");
    if (flags.length !== 1 || flags[0] !== "1") return;
    if (!["request", "json", "adapter", "graph-timeout", "graph-other", "watch-load"].includes(stage)) return;
    if (isCurrent && !isCurrent()) return;
    const errorName = ["Error", "TypeError", "ReferenceError", "SyntaxError", "RangeError", "AbortError", "TimeoutError"].find((name) => name === error?.name) || "unknown";
    const message = error?.message;
    const codes = [
      ["unavailable", "unavailable"],
      ["watchlist-aborted", "watchlist-aborted"],
      ["authentication-required", "authentication-required"],
      ["watchlist-unavailable", "watchlist-unavailable"],
      ["invalid-watchlist-response", "invalid-watchlist-response"],
      ["watchlist-response-limit", "watchlist-response-limit"],
      ["watchlist-owner-mismatch", "watchlist-owner-mismatch"],
      ["duplicate-watchlist-group", "duplicate-watchlist-group"],
      ["watchlist-group-mismatch", "watchlist-group-mismatch"],
      ["ambiguous-watchlist-market", "ambiguous-watchlist-market"],
      ["\uBD84\uC11D \uC790\uB8CC\uC758 \uD615\uC2DD\uC744 \uD655\uC778\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694.", "analysis-format"],
      ["\uBD84\uC11D \uC790\uB8CC\uB97C \uBD88\uB7EC\uC624\uC9C0 \uBABB\uD588\uC5B4\uC694. \uC7A0\uC2DC \uD6C4 \uB2E4\uC2DC \uC2DC\uB3C4\uD574 \uC8FC\uC138\uC694.", "analysis-unavailable"],
      ["invalid-local-company-judgments", "invalid-local-company-judgments"],
      ["graph-load-timeout", "graph-load-timeout"],
      ["graph-load-cancelled", "graph-load-cancelled"],
      ["graph-holdings-mismatch", "graph-holdings-mismatch"],
      ["invalid-analysis-position-market", "invalid-analysis-position-market"],
      ["portfolio-document-without-evidence", "portfolio-document-without-evidence"],
      ["portfolio-company-universe-mismatch", "portfolio-company-universe-mismatch"],
      ["portfolio-document-identity-conflict", "portfolio-document-identity-conflict"],
      ["duplicate-legacy-company", "duplicate-legacy-company"],
      ["duplicate-analysis-company", "duplicate-analysis-company"],
      ["duplicate-legacy-document", "duplicate-legacy-document"],
      ["duplicate-analysis-document", "duplicate-analysis-document"],
      ["portfolio-legacy-company-market-unknown", "portfolio-legacy-company-market-unknown"],
      ["portfolio-analysis-company-market-unknown", "portfolio-analysis-company-market-unknown"]
    ];
    const errorCode = codes.find(([known]) => known === message)?.[1] || "unknown";
    const publicBindings = [
      "crypto",
      "TextEncoder",
      "buildPortfolioMapGraph",
      "portfolioDocumentIdentity",
      "parseAutomaticEvidence",
      "parseAnalysisPrices",
      "parseMarketContext",
      "parseDocumentLineage",
      "parseContractFacts",
      "parseContractEvents",
      "parseContractTermination",
      "attachPublicAIReview",
      "quotedContractDay",
      "quotedContractFinancialLines",
      "memberMapBoundBusinessJudgments",
      "mergePortfolioAnalysisGraphs"
    ];
    const missingBinding = errorName === "ReferenceError" ? publicBindings.find((name) => message === `${name} is not defined` || message === `Can't find variable: ${name}`) || "unknown" : "unknown";
    const status = response?.status;
    console.warn("member-map-load-diagnostic", JSON.stringify({
      stage,
      errorName,
      errorCode,
      missingBinding,
      status: Number.isInteger(status) && status >= 100 && status <= 599 ? status : null
    }));
  } catch {
  }
}
var { analysisToGraph, fetchPortfolioAnalysisGraph, boundBusinessJudgments: memberMapBoundBusinessJudgments } = ((secBindings) => {
  var MemberMapClientDelta = (() => {
    var __defProp2 = Object.defineProperty;
    var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
    var __getOwnPropNames = Object.getOwnPropertyNames;
    var __hasOwnProp = Object.prototype.hasOwnProperty;
    var __export = (target, all) => {
      for (var name in all)
        __defProp2(target, name, { get: all[name], enumerable: true });
    };
    var __copyProps = (to, from, except, desc) => {
      if (from && typeof from === "object" || typeof from === "function") {
        for (let key of __getOwnPropNames(from))
          if (!__hasOwnProp.call(to, key) && key !== except)
            __defProp2(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
      }
      return to;
    };
    var __toCommonJS = (mod) => __copyProps(__defProp2({}, "__esModule", { value: true }), mod);
    var PortfolioAnalysisClient_exports = {};
    __export(PortfolioAnalysisClient_exports, {
      analysisToGraph: () => analysisToGraph2,
      boundBusinessJudgments: () => boundBusinessJudgments,
      fetchPortfolioAnalysisGraph: () => fetchPortfolioAnalysisGraph2
    });
    var buildPortfolioMapGraph2 = secBindings.buildPortfolioMapGraph;
    var portfolioDocumentIdentity2 = secBindings.portfolioDocumentIdentity;
    var parseAutomaticEvidence2 = secBindings.parseAutomaticEvidence;
    var parseAnalysisPrices2 = secBindings.parseAnalysisPrices;
    var parseMarketContext2 = secBindings.parseMarketContext;
    var parseDocumentLineage2 = secBindings.parseDocumentLineage;
    var parseContractFacts2 = secBindings.parseContractFacts;
    var parseContractEvents2 = secBindings.parseContractEvents;
    var parseContractTermination2 = secBindings.parseContractTermination;
    var attachPublicAIReview2 = secBindings.attachPublicAIReview;
    var quotedContractDay2 = secBindings.quotedContractDay;
    var quotedContractFinancialLines2 = secBindings.quotedContractFinancialLines;
    var fail3 = () => {
      throw Error("invalid-local-company-judgments");
    };
    var keys2 = (v, expected) => {
      if (!v || typeof v !== "object" || Array.isArray(v) || Object.keys(v).sort().join() !== [...expected].sort().join()) fail3();
    };
    var text7 = (v, max = 600) => typeof v === "string" && v.trim() && v.length <= max && !/[<>\u0000-\u001f\u007f]/.test(v) ? v : fail3();
    var nullableText = (v) => v === null ? null : text7(v);
    var day = (v) => {
      const value = text7(v, 10);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || !Number.isFinite(Date.parse(value)) || new Date(value).toISOString().slice(0, 10) !== value) fail3();
      return value;
    };
    var missing2 = /* @__PURE__ */ new Set([
      "entity_scope",
      "role",
      "object",
      "period",
      "scale",
      "denominator",
      "structured_table",
      "counter_evidence_not_searched",
      "path_evidence",
      "source_context"
    ]);
    function reportedCustomerPeriod(row2) {
      const c = row2.period_context_v3;
      keys2(c, [
        "schema",
        "source_version",
        "source_id",
        "company_id",
        "counterparty_id",
        "corp_code",
        "archive_sha256",
        "xml_sha256",
        "archive_member",
        "report_period_start",
        "report_period_end",
        "fiscal_year",
        "paragraph_index",
        "paragraph_quote",
        "table_index",
        "header_row",
        "row_index",
        "column_index",
        "rows",
        "table_sha256",
        "period_quote",
        "revision"
      ]);
      if (Object.hasOwn(row2, "period_context_v2") || c.schema !== "reported-customer-period-v1" || c.source_version !== row2.source_version || c.source_id !== row2.source_id || c.company_id !== row2.company_id || c.counterparty_id !== row2.counterparty_id || !/^KR:[0-9]{6}$/.test(text7(c.counterparty_id, 20)) || !/^[0-9]{8}$/.test(text7(c.corp_code, 8))) fail3();
      for (const key of ["source_version", "archive_sha256", "xml_sha256", "table_sha256", "revision"]) {
        if (!/^[a-f0-9]{64}$/.test(text7(c[key], 64))) fail3();
      }
      if (c.archive_member !== row2.source_id.slice(12) + ".xml") fail3();
      if (day(c.report_period_start) > day(c.report_period_end) || c.report_period_end > row2.published_on || !/^20[0-9]{2}$/.test(text7(c.fiscal_year, 4)) || c.report_period_end.slice(0, 4) !== c.fiscal_year || c.period_quote !== c.fiscal_year + "\uB144" || row2.period_quote !== c.period_quote) fail3();
      text7(c.paragraph_quote);
      if (!c.paragraph_quote.includes(row2.quote)) fail3();
      for (const key of ["paragraph_index", "table_index", "header_row", "row_index", "column_index"]) {
        if (!Number.isSafeInteger(c[key]) || c[key] < 0) fail3();
      }
      if (!Array.isArray(c.rows) || c.rows.length < 2 || c.rows.length > 500) fail3();
      let width;
      const rows2 = Array.from(c.rows, (cells) => {
        if (!Array.isArray(cells) || cells.length < 2 || cells.length > 40 || width !== void 0 && cells.length !== width) fail3();
        width = cells.length;
        return Array.from(cells, (cell) => {
          return text7(cell, 2e3);
        });
      });
      const serialized = "[" + rows2.map((cells) => "[" + cells.map((cell) => JSON.stringify(cell)).join(", ") + "]").join(", ") + "]";
      if (new TextEncoder().encode(serialized).length > 512 * 1024 || c.header_row >= rows2.length || c.row_index <= c.header_row || c.row_index >= rows2.length || c.column_index < 1 || c.column_index >= rows2[c.header_row].length || c.column_index >= rows2[c.row_index].length || rows2[c.header_row][c.column_index].trim().replace(/\s+/g, " ") !== c.period_quote) fail3();
      return { ...c, rows: rows2 };
    }
    function judgmentComparison(row2) {
      const c = row2.comparison;
      keys2(c, ["status", "unavailable_reason", "changed_fields", "review_changed_fields", "previous", "current"]);
      const snapshot = (s) => {
        keys2(s, ["source_version", "judgment_revision", "review_revision", "assessed_as_of", "reviewed_on", "reason", "review_reason"]);
        for (const key of ["source_version", "judgment_revision", "review_revision"]) {
          if (!/^[a-f0-9]{64}$/.test(text7(s[key], 64))) fail3();
        }
        if (day(s.assessed_as_of) < row2.published_on) fail3();
        text7(s.reason);
        nullableText(s.review_reason);
        if (s.reviewed_on === null ? s.review_reason !== null : !s.review_reason || day(s.reviewed_on) < row2.published_on || s.reviewed_on > s.assessed_as_of) fail3();
        return { ...s };
      };
      const current = snapshot(c.current);
      if (current.review_revision !== row2.revision || current.reason !== row2.reason || current.reviewed_on !== row2.reviewed_on || current.review_reason !== row2.review_reason || row2.source_version !== void 0 && current.source_version !== row2.source_version || row2.period_context_v2 && current.source_version !== row2.period_context_v2.source_version || row2.period_context_v3 && current.source_version !== row2.period_context_v3.source_version) fail3();
      const fields3 = (values, allowed) => {
        if (!Array.isArray(values) || values.length > allowed.length || new Set(values).size !== values.length || values.some((v) => !allowed.includes(v))) fail3();
        return [...values];
      };
      const changed = fields3(c.changed_fields, [
        "quote",
        "degree",
        "impact",
        "counter_evidence_quotes",
        "missing_evidence",
        "reason",
        "review_trigger",
        "economic_v2",
        "period_context_v2",
        "period_context_v3",
        "status",
        "review_reasons",
        "display"
      ]);
      const reviewed = fields3(c.review_changed_fields, ["decision", "reason", "checks", "materiality_review"]);
      if (!["first", "unavailable", "changed", "unchanged"].includes(c.status)) fail3();
      const comparable = ["changed", "unchanged"].includes(c.status);
      let previous = null;
      if (comparable) {
        previous = snapshot(c.previous);
        if (c.unavailable_reason !== null || !previous.reviewed_on || !current.reviewed_on || previous.source_version !== current.source_version || previous.assessed_as_of > current.assessed_as_of || previous.reviewed_on > current.reviewed_on || current.assessed_as_of > (/* @__PURE__ */ new Date()).toISOString().slice(0, 10) || c.status === "changed" !== Boolean(changed.length || reviewed.length)) fail3();
      } else if (c.previous !== null || changed.length || reviewed.length || (c.status === "first" ? c.unavailable_reason !== null : !["invalid-history", "history-binding", "unreviewed", "time-reversed", "source-changed", "scope-period-changed"].includes(c.unavailable_reason))) fail3();
      return { ...c, current, previous, changed_fields: changed, review_changed_fields: reviewed };
    }
    function economicContext(row2) {
      const value = row2.economic_v2, m = value?.materiality;
      keys2(value, ["materiality", "impact_quote", "counter_evidence_quotes"]);
      keys2(m, ["value", "scope", "quote", "scope_quote", "period_quote", "mechanism_quote", "status", "reviewed_on", "review_reason", "review_reasons"]);
      nullableText(m.quote);
      if (m.quote !== null && !/[.!?]$/.test(m.quote)) fail3();
      for (const span of [m.scope_quote, m.period_quote, m.mechanism_quote]) {
        if (nullableText(span) !== null && !(m.quote || "").includes(span)) fail3();
      }
      if (nullableText(value.impact_quote) !== null && !row2.quote.includes(value.impact_quote)) fail3();
      if (!["material", "limited", "unrated"].includes(m.value) || !["company", "division", "product", "unknown"].includes(m.scope) || !["pending", "held", "accepted", "rejected"].includes(m.status) || !Array.isArray(m.review_reasons) || m.review_reasons.length > 3 || m.review_reasons.some((r) => !["materiality-scope", "materiality-period", "materiality-economic-basis"].includes(r)) || new Set(m.review_reasons).size !== m.review_reasons.length) fail3();
      nullableText(m.review_reason);
      if (m.reviewed_on !== null && day(m.reviewed_on) < row2.published_on) fail3();
      if (m.status === "pending" ? m.reviewed_on !== null || m.review_reason !== null : !m.reviewed_on || !m.review_reason) fail3();
      if (!Array.isArray(value.counter_evidence_quotes) || value.counter_evidence_quotes.length > 4 || new Set(value.counter_evidence_quotes).size !== value.counter_evidence_quotes.length) fail3();
      value.counter_evidence_quotes.forEach((q) => {
        text7(q);
        if (q === row2.quote) fail3();
      });
      if (row2.status === "accepted" && row2.impact.direction !== "unknown" && !value.impact_quote) fail3();
      if (m.status === "accepted") {
        const scope = m.scope_quote || "", period = m.period_quote || "", quote = m.quote || "";
        const scoped = /^당사(?:의)?\s+/.test(scope) && {
          company: /^당사(?:의)?\s+(?:전체|전사)$/.test(scope),
          division: /사업부|부문/.test(scope),
          product: /제품|서비스/.test(scope),
          unknown: false
        }[m.scope];
        const cues = { material: /중요한|중대한|중요합니다|중대합니다|유의적인/, limited: /경미|미미/ };
        if (!["accepted", "held"].includes(row2.status) || m.value === "unrated" || m.review_reasons.length || !scoped || !period || row2.period_quote !== null && period !== row2.period_quote || !/\d{4}년|당기|보고기간|회계연도/.test(period) || !/매출|영업이익|순이익|현금흐름|원가|비용|자산|부채/.test(quote) || !m.mechanism_quote || !/매출|영업이익|순이익|현금흐름|원가|비용|자산|부채/.test(m.mechanism_quote) || /아니|않|없|미확인|불확실/.test(quote) || !cues[m.value].test(quote) || cues[m.value === "material" ? "limited" : "material"].test(quote)) fail3();
      } else if (m.value !== "unrated") fail3();
      return { ...value, materiality: { ...m, review_reasons: [...m.review_reasons] }, counter_evidence_quotes: [...value.counter_evidence_quotes] };
    }
    function coreDatePattern(day2) {
      const [year, month, number] = day2.split("-");
      const m = Number(month) < 10 ? "0?" + Number(month) : month;
      const d = Number(number) < 10 ? "0?" + Number(number) : number;
      return "(?<![0-9])(?:" + day2 + "(?![0-9])|" + year + "\uB144\\s*" + m + "\uC6D4\\s*" + d + "\uC77C(?=\\s|\uBD80\uD130|\uAE4C\uC9C0|~|[,.!?]|$))";
    }
    function coreSelection(row2) {
      if (row2.core_selection?.basis === "contract-announcement") return contractCoreSelection(row2);
      const c = row2.core_selection, p = c?.previous, m = row2.economic_v2?.materiality;
      keys2(c, ["checked_on", "effective_start", "effective_end", "current_quote", "period_quote", "change_quote", "reason", "candidate_revision", "previous"]);
      keys2(p, ["record_id", "source_id", "source_url", "published_on", "source_version", "review_revision", "quote"]);
      for (const hash of [row2.source_version, c.candidate_revision, p.source_version, p.review_revision]) {
        if (!/^[a-f0-9]{64}$/.test(text7(hash, 64))) fail3();
      }
      if (row2.status !== "accepted" || m?.status !== "accepted" || m.value !== "material" || Number.parseInt(c.candidate_revision.slice(0, 13), 16) + 1 !== row2.base_read_revision || !/^automatic:ai:[a-f0-9]{24}$/.test(text7(p.record_id, 50)) || !/^source:dart:[0-9]{14}$/.test(text7(p.source_id, 40)) || p.source_url !== `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${p.source_id.slice(12)}` || day(p.published_on).replaceAll("-", "") !== p.source_id.slice(12, 20) || p.published_on > row2.published_on || day(c.checked_on) > row2.published_on || c.checked_on > row2.reviewed_on || day(c.effective_start) > c.checked_on || day(c.effective_end) < c.checked_on) fail3();
      for (const key of ["current_quote", "period_quote", "change_quote"]) {
        if (!/[.!?]$/.test(text7(c[key])) || !m.scope_quote || !c[key].includes(m.scope_quote)) fail3();
      }
      text7(c.reason);
      text7(p.quote);
      if (c.change_quote !== m.quote || p.quote === c.change_quote || !new RegExp(coreDatePattern(c.checked_on)).test(c.current_quote) || !c.current_quote.includes("\uD604\uC7AC") || !/(?:공급|납품|구매|매입|이행)하고\s+있습니다/.test(c.current_quote) || !new RegExp(coreDatePattern(c.effective_start) + "(?:\uBD80\uD130\\s+" + coreDatePattern(c.effective_end) + "\uAE4C\uC9C0|\\s*~\\s*" + coreDatePattern(c.effective_end) + "\\s+\uAE30\uAC04\uC5D0)").test(c.period_quote) || !/유효|효력/.test(c.period_quote) || !new RegExp(coreDatePattern(c.checked_on)).test(c.change_quote) || !/증가|감소|확대|축소|중단|재개/.test(c.change_quote)) fail3();
      return { ...c, previous: { ...p } };
    }
    function closedContractProofFacts(facts, published) {
      keys2(facts, ["contract", "correction"]);
      const c = facts.contract;
      keys2(c, [
        "type",
        "name",
        "counterparty",
        "period",
        "signed_on",
        ...["financial_terms", "financial_notes", "revenue_basis"].filter((k) => c && Object.hasOwn(c, k))
      ]);
      const field = (f) => {
        keys2(f, ["label", "value"]);
        text7(f.label, 2e3);
        text7(f.value, 2e3);
      };
      for (const k of ["type", "name", "counterparty", "signed_on"]) field(c[k]);
      keys2(c.period, ["label", "start", "end"]);
      text7(c.period.label, 2e3);
      field(c.period.start);
      field(c.period.end);
      if (Object.hasOwn(c, "financial_terms")) {
        const terms = c.financial_terms;
        keys2(terms, ["amount", "recent_revenue", "revenue_ratio"].filter((k) => terms && Object.hasOwn(terms, k)));
        if (!Object.keys(terms).length) fail3();
        Object.values(terms).forEach(field);
      }
      if (Object.hasOwn(c, "revenue_basis")) keys2(c.revenue_basis, ["year", "scope", "quote"]);
      if (Object.hasOwn(c, "financial_notes")) {
        field(c.financial_notes);
        if (!/^(?:9|10)\.\s*기타\s*투자판단(?:에\s*참고할\s*사항|과\s*관련한\s*중요사항)$/.test(c.financial_notes.label)) fail3();
      }
      quotedContractFinancialLines2(c, published, c.financial_notes?.value);
      if (facts.correction !== null) {
        const correction = facts.correction;
        keys2(correction, ["corrected_on", "related_filing_date", "reason", "changes"]);
        for (const k of ["corrected_on", "related_filing_date", "reason"]) {
          field(correction[k]);
          if (k !== "reason" && quotedContractDay2(correction[k].value) > published) fail3();
        }
        if (!Array.isArray(correction.changes) || !correction.changes.length || correction.changes.length > 20) fail3();
        for (const change of correction.changes) {
          keys2(change, ["field", "before", "after"]);
          for (const k of ["field", "before", "after"]) text7(change[k], 2e3);
        }
      }
    }
    function contractCoreSelection(row2) {
      const c = row2.core_selection;
      keys2(c, [
        "basis",
        "event_revision",
        "source_receipt",
        "body_sha256",
        "fact_revision",
        "checked_on",
        "effective_start",
        "effective_end",
        "review_scope",
        "materiality",
        "change_kind",
        "facts",
        "reason",
        "denominator"
      ]);
      closedContractProofFacts(c.facts, row2.published_on);
      keys2(c.denominator, ["year", "scope", "quote"]);
      const basis = String(c.facts.contract.financial_notes?.value || "").match(/(?:상기\s*['"‘’]?2\.\s*(?:계약내역의?\s*)?|상기\s*계약내역의\s*)최근\s*매출액(?:\(원\))?['"‘’]?(?:\s*및\s*계약상대방의\s*최근\s*매출액)?\s*(?:은|는)\s*(?:당사의\s*)?((?:19|20)\d{2})년(?:도|말)?\s*(연결|별도|개별)\s*재무제표\s*기준/);
      for (const h of [row2.source_version, c.event_revision, c.body_sha256, c.fact_revision]) if (!/^[a-f0-9]{64}$/.test(text7(h, 64))) fail3();
      if (c.fact_revision !== row2.source_version || row2.status !== "accepted" || row2.degree !== "unrated" || row2.impact.direction !== "unknown" || row2.impact.channel !== "unknown" || row2.impact.condition !== null || c.materiality !== "material" || c.review_scope !== "provided-contract-family-only" || Number.parseInt(c.event_revision.slice(0, 13), 16) + 1 !== row2.base_read_revision || c.source_receipt !== row2.source_id.slice(12) || row2.quote !== c.facts.contract.name.value || row2.scope_quote !== row2.quote || row2.period_quote !== c.effective_start + " ~ " + c.effective_end || !["new-contract", "amount-amendment"].includes(c.change_kind) || (c.change_kind === "new-contract" ? c.facts.correction !== null || !row2.quote.includes("\uC2E0\uADDC \uACC4\uC57D") : !c.facts.correction) || day(c.checked_on) !== row2.reviewed_on || c.checked_on < row2.published_on || day(c.effective_start) > c.checked_on || day(c.effective_end) < c.checked_on || !Number.isSafeInteger(c.denominator.year) || c.denominator.year > Number(row2.published_on.slice(0, 4)) || !["consolidated", "separate"].includes(c.denominator.scope) || !basis || Number(basis[1]) !== c.denominator.year || (basis[2] === "\uC5F0\uACB0" ? "consolidated" : "separate") !== c.denominator.scope || c.denominator.quote !== c.facts.contract.financial_notes.value || !["amount", "recent_revenue", "revenue_ratio"].every((k) => c.facts.contract.financial_terms[k]) || row2.review_reasons.length || row2.missing_evidence.join() !== "counter_evidence_not_searched" || !["first", "unavailable"].includes(row2.comparison?.status)) fail3();
      text7(c.reason);
      text7(c.denominator.quote, 2e3);
      return { ...c, facts: { ...c.facts }, denominator: { ...c.denominator } };
    }
    function validateLocalBusinessJudgments(payload) {
      const body = payload;
      keys2(body, ["schema", "judgments"]);
      if (body.schema !== "local-company-judgments-v1" || !Array.isArray(body.judgments) || body.judgments.length > 16) fail3();
      const ids = /* @__PURE__ */ new Set();
      const judgments = body.judgments.map((row2) => {
        keys2(row2, [
          "record_id",
          "base_read_revision",
          "read_revision",
          "revision",
          "company_id",
          "counterparty_id",
          "source_id",
          "source_url",
          "published_on",
          "quote",
          "scope_quote",
          "period_quote",
          "status",
          "reviewed_on",
          "review_reason",
          "degree",
          "impact",
          "reason",
          "review_trigger",
          "missing_evidence",
          "review_reasons",
          ...row2 && Object.hasOwn(row2, "source_version") ? ["source_version"] : [],
          ...row2 && Object.hasOwn(row2, "economic_v2") ? ["economic_v2"] : [],
          ...row2 && Object.hasOwn(row2, "comparison") ? ["comparison"] : [],
          ...row2 && Object.hasOwn(row2, "core_selection") ? ["core_selection"] : [],
          ...row2 && Object.hasOwn(row2, "period_context_v2") ? ["period_context_v2"] : [],
          ...row2 && Object.hasOwn(row2, "period_context_v3") ? ["period_context_v3"] : []
        ]);
        const contractRow = row2.core_selection?.basis === "contract-announcement";
        const contractId = typeof row2.record_id === "string" && row2.record_id.startsWith(`contract:${row2.company_id}:`) && /^contract:KR:[0-9]{6}:[0-9]{14}$/.test(row2.record_id);
        if (!(contractRow ? contractId : /^automatic:ai:[a-f0-9]{24}$/.test(text7(row2.record_id, 50))) || ids.has(row2.record_id) || !/^[a-f0-9]{64}$/.test(text7(row2.revision, 64)) || !Number.isSafeInteger(row2.base_read_revision) || row2.base_read_revision < 1 || !Number.isSafeInteger(row2.read_revision) || row2.read_revision < 1 || row2.read_revision !== Number.parseInt(row2.revision.slice(0, 13), 16) + 1 || !/^KR:[0-9]{6}$/.test(text7(row2.company_id, 20)) || !/^(KR:[0-9]{6}|US:[A-Z][A-Z0-9.-]{0,12})$/.test(text7(row2.counterparty_id, 20)) || row2.company_id === row2.counterparty_id || !/^source:dart:[0-9]{14}$/.test(text7(row2.source_id, 40)) || row2.source_url !== `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${row2.source_id.slice(12)}`) fail3();
        ids.add(row2.record_id);
        if (Object.hasOwn(row2, "source_version") && (!/^[a-f0-9]{64}$/.test(text7(row2.source_version, 64)) || row2.period_context_v2 && row2.source_version !== row2.period_context_v2.source_version)) fail3();
        if (day(row2.published_on).replaceAll("-", "") !== row2.source_id.slice(12, 20)) fail3();
        text7(row2.quote);
        text7(row2.reason);
        text7(row2.review_trigger);
        if (Object.hasOwn(row2, "period_context_v2")) {
          const context = row2.period_context_v2;
          keys2(context, ["quote", "source_version"]);
          text7(context.quote);
          if (!/[.!?]$/.test(context.quote) || !/^[a-f0-9]{64}$/.test(text7(context.source_version, 64)) || !row2.period_quote || !/^(?:20\d{2}년(?:도)?|당기|보고기간|회계연도)$/.test(row2.period_quote)) fail3();
        }
        const reportedPeriod = Object.hasOwn(row2, "period_context_v3") ? reportedCustomerPeriod(row2) : void 0;
        for (const key of ["scope_quote", "period_quote"]) {
          const span = nullableText(row2[key]);
          const support = key === "period_quote" ? reportedPeriod?.period_quote ?? row2.period_context_v2?.quote ?? row2.quote : row2.quote;
          if (!contractRow && span !== null && !support.includes(span)) fail3();
        }
        nullableText(row2.review_reason);
        if (row2.reviewed_on !== null && day(row2.reviewed_on) < row2.published_on) fail3();
        keys2(row2.impact, ["direction", "channel", "condition"]);
        nullableText(row2.impact.condition);
        if (!["pending", "held", "accepted", "rejected"].includes(row2.status) || !["high", "medium", "low", "unrated"].includes(row2.degree) || !["positive", "negative", "mixed", "unknown"].includes(row2.impact.direction) || !["revenue", "cost", "capacity", "funding", "regulation", "unknown"].includes(row2.impact.channel) || !Array.isArray(row2.missing_evidence) || row2.missing_evidence.length > missing2.size || row2.missing_evidence.some((m) => typeof m !== "string" || !missing2.has(m)) || new Set(row2.missing_evidence).size !== row2.missing_evidence.length || !Array.isArray(row2.review_reasons) || row2.review_reasons.length > 10 || row2.review_reasons.some((r) => typeof r !== "string" || !/^[a-z]+(?:-[a-z]+)*$/.test(r) || r.length > 60) || new Set(row2.review_reasons).size !== row2.review_reasons.length) fail3();
        if (row2.status === "accepted") {
          if (!row2.reviewed_on || !row2.review_reason || !row2.scope_quote || !row2.period_quote || row2.review_reasons.length) fail3();
          if (row2.impact.direction !== "unknown" && (row2.impact.channel === "unknown" || row2.impact.condition === null)) fail3();
        } else if (row2.degree !== "unrated" || row2.impact.direction !== "unknown") fail3();
        if (row2.status === "pending" ? row2.reviewed_on !== null || row2.review_reason !== null : !row2.reviewed_on || !row2.review_reason) fail3();
        return {
          ...row2,
          impact: { ...row2.impact },
          missing_evidence: [...row2.missing_evidence],
          review_reasons: [...row2.review_reasons],
          ...Object.hasOwn(row2, "period_context_v2") ? { period_context_v2: { ...row2.period_context_v2 } } : {},
          ...reportedPeriod ? { period_context_v3: reportedPeriod } : {},
          ...Object.hasOwn(row2, "comparison") ? { comparison: judgmentComparison(row2) } : {},
          ...Object.hasOwn(row2, "core_selection") ? { core_selection: coreSelection(row2) } : {},
          ...Object.hasOwn(row2, "economic_v2") ? { economic_v2: economicContext(row2) } : {}
        };
      });
      return { schema: "local-company-judgments-v1", judgments };
    }
    function matchesContract(graph, event, row2) {
      const c = row2.core_selection, b = event.judgmentBinding;
      closedContractProofFacts(b?.facts, row2.published_on);
      const today = new Date((/* @__PURE__ */ new Date()).getTime() + 9 * 60 * 60 * 1e3).toISOString().slice(0, 10);
      const canonical = (v) => JSON.stringify(v && typeof v === "object" ? Array.isArray(v) ? v.map((x) => JSON.parse(canonical(x))) : Object.fromEntries(Object.keys(v).sort().map((k) => [k, JSON.parse(canonical(v[k]))])) : v);
      return c?.basis === "contract-announcement" && event.id === row2.record_id && b?.revision === c.event_revision && b.sourceReceipt === c.source_receipt && canonical(b.facts) === canonical(c.facts) && !event.periodConflict && event.terminationNoticeCount === 0 && event.asOf === row2.published_on && row2.published_on <= today && c.checked_on <= today && c.effective_start <= today && c.effective_end >= today && (!row2.comparison || row2.comparison.current.assessed_as_of <= today) && event.participants.length === 2 && event.participants[0].id === row2.company_id && event.participants[0].role === "supplier" && event.participants[1].id === row2.counterparty_id && event.participants[1].role === "counterparty" && graph.companies.some((c2) => `${c2.market}:${c2.ticker}` === row2.company_id) && event.evidence.some((e) => e.url === row2.source_url) && event.measure?.start === c.effective_start && event.measure?.end === c.effective_end;
    }
    function matchesCandidate(graph, relation, row2) {
      const today = (/* @__PURE__ */ new Date()).toISOString().slice(0, 10);
      return relation.reported === false && relation.url === row2.source_url && relation.asOf === row2.published_on && row2.published_on <= today && (!row2.reviewed_on || row2.reviewed_on <= today) && (!row2.comparison || row2.comparison.current.assessed_as_of <= today) && (!row2.economic_v2?.materiality.reviewed_on || row2.economic_v2.materiality.reviewed_on <= today) && graph.companies.some((c) => `${c.market}:${c.ticker}` === row2.company_id) && relation.reason.includes(row2.quote) && relation.participants.length === 2 && relation.participants.filter((p) => p.id === row2.company_id && p.role === "document_issuer").length === 1 && relation.participants.filter((p) => p.id === row2.counterparty_id && p.role !== "document_issuer").length === 1;
    }
    function boundBusinessJudgments(graph) {
      const rows2 = graph.companyJudgments;
      if (rows2 === void 0) return [];
      try {
        return validateLocalBusinessJudgments({ schema: "local-company-judgments-v1", judgments: rows2 }).judgments.filter((row2) => {
          if ("basis" in (row2.core_selection || {})) {
            const events = graph.contractEvents?.filter((e) => e.id === row2.record_id) || [];
            return events.length === 1 && events[0].read_revision === row2.read_revision && matchesContract(graph, events[0], row2);
          }
          const relations = graph.automaticRelations?.filter((r) => r.id === row2.record_id) || [];
          return relations.length === 1 && relations[0].read_revision === row2.read_revision && matchesCandidate(graph, relations[0], row2);
        });
      } catch {
        return [];
      }
    }
    function attachLocalBusinessJudgments(graph, payload) {
      if (payload === void 0) return graph;
      const rows2 = new Map(validateLocalBusinessJudgments(payload).judgments.map((row2) => [row2.record_id, row2]));
      const bound = new Map(boundBusinessJudgments(graph).map((row2) => [row2.record_id, row2]));
      let changed = false;
      const automaticRelations = graph.automaticRelations?.map((relation) => {
        const row2 = rows2.get(relation.id);
        const previous = bound.get(relation.id);
        const baseRevision = previous?.base_read_revision ?? relation.read_revision;
        if (!row2 || baseRevision !== row2.base_read_revision || !matchesCandidate(graph, relation, row2)) return relation;
        const sourceVersion = (r) => r.source_version || r.comparison?.current.source_version || r.period_context_v2?.source_version || r.period_context_v3?.source_version;
        if (previous && sourceVersion(previous) && sourceVersion(row2) && sourceVersion(previous) !== sourceVersion(row2)) return relation;
        if (previous && JSON.stringify(previous) === JSON.stringify(row2)) return relation;
        changed = true;
        bound.set(row2.record_id, row2);
        return { ...relation, read_revision: row2.read_revision };
      });
      const contractEvents = graph.contractEvents?.map((event) => {
        const row2 = rows2.get(event.id), previous = bound.get(event.id);
        if (!row2 || !matchesContract(graph, event, row2) || previous && previous.source_version !== row2.source_version) return event;
        if (previous && JSON.stringify(previous) === JSON.stringify(row2)) return event;
        changed = true;
        bound.set(row2.record_id, row2);
        return { ...event, read_revision: row2.read_revision };
      });
      return changed ? { ...graph, automaticRelations, ...contractEvents ? { contractEvents } : {}, companyJudgments: [...bound.values()] } : graph;
    }
    function attachPublicBusinessJudgments(graph, payload) {
      if (payload === void 0) return graph;
      try {
        const checked = validateLocalBusinessJudgments(payload);
        if (checked.judgments.some((row2) => row2.source_version === void 0)) fail3();
        const retained = new Set(boundBusinessJudgments(graph).map((row2) => row2.record_id));
        return attachLocalBusinessJudgments(graph, { ...checked, judgments: checked.judgments.filter((row2) => !retained.has(row2.record_id)) });
      } catch {
        return graph;
      }
    }
    var ENDPOINT2 = "https://project-yw131.vercel.app/api/member_map_analysis";
    var FACT_NAMES = {
      revenue: "\uB9E4\uCD9C",
      operating_income: "\uC601\uC5C5\uC774\uC775",
      net_income: "\uC21C\uC774\uC775",
      institution_13f_shares: "13F \uBCF4\uACE0 \uBCF4\uC720\uC218\uB7C9",
      institution_13f_value_usd: "13F \uBD84\uAE30\uB9D0 \uD3C9\uAC00\uC561",
      etf_listed_units: "ETF \uC0C1\uC7A5\uC88C\uC218",
      etf_nav: "ETF \uC21C\uC790\uC0B0\uAC00\uCE58(NAV)",
      etf_net_assets: "ETF \uC21C\uC790\uC0B0",
      etf_unit_change: "ETF \uC0C1\uC7A5\uC88C\uC218 \uC99D\uAC10",
      foreign_net_shares: "\uC678\uAD6D\uC778 \uC77C\uBCC4 \uC21C\uB9E4\uB9E4\uB7C9",
      institution_net_shares: "\uAE30\uAD00 \uC77C\uBCC4 \uC21C\uB9E4\uB9E4\uB7C9",
      total_assets: "\uCD1D\uC790\uC0B0",
      total_liabilities: "\uCD1D\uBD80\uCC44",
      equity: "\uC790\uAE30\uC790\uBCF8",
      cash: "\uD604\uAE08\uC131 \uC790\uC0B0",
      free_cash_flow: "\uC789\uC5EC\uD604\uAE08\uD750\uB984",
      eps: "\uC8FC\uB2F9\uC21C\uC774\uC775",
      market_cap: "\uC2DC\uAC00\uCD1D\uC561",
      per: "PER",
      pbr: "PBR",
      roe: "\uC790\uAE30\uC790\uBCF8\uC774\uC775\uB960",
      debt_ratio: "\uBD80\uCC44\uBE44\uC728",
      operating_margin: "\uC601\uC5C5\uC774\uC775\uB960",
      revenue_growth: "\uB9E4\uCD9C \uC131\uC7A5\uB960",
      revenue_growth_quarterly_yoy: "\uBD84\uAE30 \uB9E4\uCD9C \uC131\uC7A5\uB960(\uC804\uB144 \uB300\uBE44)"
    };
    var invalid4 = () => new Error("\uBD84\uC11D \uC790\uB8CC\uC758 \uD615\uC2DD\uC744 \uD655\uC778\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694.");
    var row = (v) => {
      if (!v || typeof v !== "object" || Array.isArray(v)) throw invalid4();
      return v;
    };
    var array = (v, max = 1e4) => {
      if (!Array.isArray(v) || v.length > max) throw invalid4();
      return v;
    };
    var text22 = (v, max = 300) => {
      if (typeof v !== "string" || !v.trim() || v.length > max || /[\u0000-\u001f\u007f<>]/.test(v)) throw invalid4();
      return v;
    };
    var date = (v) => {
      const value = text22(v, 10);
      if (!/^(19|20|21)\d{2}(?:-\d{2}-\d{2})?$/.test(value)) throw invalid4();
      if (value.length === 10 && (!Number.isFinite(Date.parse(value)) || new Date(value).toISOString().slice(0, 10) !== value)) throw invalid4();
      return value;
    };
    function positionsOnly(input) {
      if (!Array.isArray(input) || input.length > 30) throw invalid4();
      const seen = /* @__PURE__ */ new Set();
      return input.map((position2) => {
        const { ticker, market: market2 } = position2;
        if (!(market2 === "KR" ? /^\d{6}$/.test(ticker) : market2 === "US" && /^[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,2})?$/.test(ticker)) || seen.has(ticker)) throw invalid4();
        seen.add(ticker);
        return { ticker, market: market2 };
      });
    }
    var officialDocument = (value, source) => {
      const url = text22(value, 2048);
      const valid = source === "DART" ? /^https:\/\/dart\.fss\.or\.kr\/dsaf001\/main\.do\?rcpNo=\d{14}$/.test(url) : source === "SEC" && /^https:\/\/www\.sec\.gov\/Archives\/edgar\/data\/[1-9]\d{0,9}\/\d{18}\/(?:[A-Za-z0-9][A-Za-z0-9_.-]{0,199})?$/.test(url);
      if (!valid) throw invalid4();
      return url;
    };
    var HOLDER_METRICS = /* @__PURE__ */ new Set([
      "foreign_net_shares",
      "institution_net_shares",
      "institution_13f_shares",
      "institution_13f_value_usd",
      "etf_listed_units",
      "etf_nav",
      "etf_net_assets",
      "etf_unit_change"
    ]);
    var PUBLIC_DATA = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/";
    var CHANGE_NAMES = {
      price: "\uAC00\uACA9",
      market_cap: "\uC2DC\uAC00\uCD1D\uC561",
      pbr: "PBR",
      eps: "EPS",
      roe: "ROE",
      debt_ratio: "\uBD80\uCC44\uBE44\uC728",
      operating_margin: "\uC601\uC5C5\uC774\uC775\uB960",
      revenue_growth: "\uB9E4\uCD9C \uC131\uC7A5\uB960",
      shares_outstanding: "\uBC1C\uD589\uC8FC\uC2DD\uC218"
    };
    function changeDetails(value, wanted) {
      const items = /* @__PURE__ */ new Map();
      if (value === void 0) return items;
      const projected = row(value), stocks = row(projected.stocks);
      for (const [key, position2] of wanted) if (position2.market === "KR") {
        items.set(key, [{
          id: `change-${position2.ticker}`,
          title: "\uC9C0\uB09C \uC218\uC9D1\uACFC \uC218\uCE58 \uBE44\uAD50",
          source: "\uAE30\uC874 \uC885\uBAA9 \uBCC0\uD654\uC13C\uD130",
          relationship: "unknown",
          value: "\uBE44\uAD50 \uC790\uB8CC \uD655\uC778 \uD544\uC694",
          explanation: "\uC774 \uC885\uBAA9\uC758 \uBE44\uAD50 \uAC00\uB2A5\uD55C \uC774\uC804\xB7\uD604\uC7AC \uC790\uB8CC\uB97C \uBC1B\uC9C0 \uBABB\uD588\uC5B4\uC694. \uC790\uB8CC \uB204\uB77D\xB7\uC218\uC9D1\uBCF8 \uBD80\uC871\xB7\uAC80\uC99D \uC81C\uC678\uC77C \uC218 \uC788\uC73C\uBA70 \uBCC0\uD654\uAC00 \uC5C6\uB2E4\uB294 \uB73B\uC740 \uC544\uB2C8\uC5D0\uC694."
        }]);
      }
      if (Object.keys(stocks).length > 30) throw invalid4();
      for (const [ticker, entry] of Object.entries(stocks)) {
        const stock = row(entry), key = `KR:${ticker}`;
        const url = `https://raw.githubusercontent.com/gywns0126/VERITY-data/main/stock_change_public/${ticker.slice(0, 3)}.json`;
        if (!wanted.has(key) || stock.ticker !== ticker || stock.market !== "KR" || stock.source_url !== url) throw invalid4();
        if (stock.today === null) continue;
        const comparison = row(stock.today), current = date(comparison.as_of), previous = date(comparison.previous_as_of);
        if (current.length !== 10 || previous.length !== 10 || previous >= current || current > (/* @__PURE__ */ new Date()).toISOString().slice(0, 10) || comparison.date_basis !== "collection_date" || comparison.source_url !== url || !["changed", "unchanged", "partial", "unavailable"].includes(String(comparison.status))) throw invalid4();
        const seen = /* @__PURE__ */ new Set();
        const rows2 = array(comparison.fields, 9).map((value2) => {
          const field = row(value2), name = text22(field.key, 40), before = field.before, after = field.after, delta = field.delta;
          const numeric2 = (n) => typeof n === "number" && Number.isFinite(n) && Math.abs(n) <= Number.MAX_SAFE_INTEGER;
          if (!Object.hasOwn(CHANGE_NAMES, name) || seen.has(name) || !numeric2(before) || !numeric2(after) || !numeric2(delta) || before === after || Math.abs(after - before - delta) > 1e-6 || ["price", "market_cap", "shares_outstanding"].includes(name) && Math.min(before, after) < 0 || name === "shares_outstanding" && (!Number.isSafeInteger(before) || !Number.isSafeInteger(after)) || (before === 0 ? field.delta_pct !== null : !numeric2(field.delta_pct) || Math.abs((after - before) / Math.abs(before) * 100 - field.delta_pct) > 5001e-6)) throw invalid4();
          seen.add(name);
          return { label: CHANGE_NAMES[name], value: `${before.toLocaleString("ko-KR", { maximumFractionDigits: 6 })} \u2192 ${after.toLocaleString("ko-KR", { maximumFractionDigits: 6 })}` };
        });
        if (["unchanged", "unavailable"].includes(String(comparison.status)) && rows2.length || ["changed", "partial"].includes(String(comparison.status)) && !rows2.length) throw invalid4();
        items.set(key, [{
          id: `change-${ticker}`,
          title: rows2.length ? "\uC9C0\uB09C \uC218\uC9D1 \uC774\uD6C4 \uB2EC\uB77C\uC9C4 \uC218\uCE58" : "\uC9C0\uB09C \uC218\uC9D1\uACFC \uC218\uCE58 \uBE44\uAD50",
          source: "\uAE30\uC874 \uC885\uBAA9 \uBCC0\uD654\uC13C\uD130",
          url,
          asOf: current,
          relationship: "unknown",
          rows: rows2,
          ...!rows2.length ? { value: comparison.status === "unchanged" ? "\uC81C\uACF5\uB41C \uBE44\uAD50 \uD56D\uBAA9\uC5D0 \uBCC0\uD654 \uC5C6\uC74C" : "\uD45C\uC2DC\uD560 \uBE44\uAD50 \uC218\uCE58 \uD655\uC778 \uBD88\uAC00" } : {},
          explanation: `\uC218\uC9D1\uC77C ${previous} \u2192 ${current}. \uAC70\uB798\uC77C\uC774\uB098 \uC5F0\uC18D \uAC70\uB798\uC77C \uBE44\uAD50\uAC00 \uC544\uB2C8\uC5D0\uC694. \uCD9C\uCC98\uAC00 \uBCF4\uAD00\uD55C \uC774\uC804\xB7\uD604\uC7AC \uC218\uCE58\uC774\uBA70 \uD1B5\uD654\xB7\uD68C\uACC4\uAE30\uAC04\uC774 \uD655\uC778\uB418\uC9C0 \uC54A\uC740 \uAC12\uC740 \uC11C\uB85C \uB2E4\uB978 \uC885\uBAA9\uACFC \uBE44\uAD50\uD558\uC9C0 \uC54A\uC544\uC694. \uD638\uC7AC\xB7\uC545\uC7AC\uB098 \uC774\uC804 \uD22C\uC790 \uD310\uB2E8\uC758 \uBCC0\uACBD\uC744 \uB73B\uD558\uC9C0 \uC54A\uC544\uC694.` + (comparison.status === "partial" ? " \uAC80\uC99D\uB41C \uD56D\uBAA9\uB9CC \uD45C\uC2DC\uD558\uBA70 \uC77C\uBD80 \uBE44\uAD50\uB294 \uC81C\uC678\uD588\uC5B4\uC694." : comparison.status === "unavailable" ? " \uC6D0\uC790\uB8CC\uC5D0\uB294 \uBCC0\uACBD \uD45C\uC2DC\uAC00 \uC788\uC73C\uB098 \uBE44\uAD50 \uAE30\uC900\uC774\uB098 \uC218\uCE58 \uAC80\uC99D\uC744 \uD1B5\uACFC\uD55C \uD56D\uBAA9\uC774 \uC5C6\uC5B4\uC694. \uBCC0\uD654\uAC00 \uC5C6\uB2E4\uB294 \uB73B\uC740 \uC544\uB2C8\uC5D0\uC694." : "")
        }]);
      }
      return items;
    }
    function financialProof(fact, market2, ticker) {
      if (fact.provenance === void 0) {
        if (fact.unit === "currency-unverified" || HOLDER_METRICS.has(String(fact.metric))) throw invalid4();
        return {};
      }
      const p = row(fact.provenance);
      if (p.kind === "public-13f") {
        const report = date(p.report_date), filed = date(p.filed_at), institution = text22(p.institution, 160);
        const metric = String(fact.metric);
        if (market2 !== "US" || p.ticker !== ticker || fact.source !== "SEC" || !["institution_13f_shares", "institution_13f_value_usd"].includes(metric) || fact.unit !== (metric === "institution_13f_shares" ? "\uC8FC" : "USD") || !Number.isSafeInteger(fact.value) || fact.value < 0 || report.length !== 10 || filed.length !== 10 || report !== fact.as_of || filed < report || !["03-31", "06-30", "09-30", "12-31"].includes(report.slice(5)) || filed > (/* @__PURE__ */ new Date()).toISOString().slice(0, 10) || !["us_smart_money_13f.json", "us_investor_portfolios.json"].some((name) => p.source_url === PUBLIC_DATA + name)) throw invalid4();
        let original;
        if (p.original_status === "provided") {
          const cik2 = text22(p.manager_cik, 10), accession2 = text22(p.accession, 20);
          original = officialDocument(p.original_url, "SEC");
          if (!/^[1-9]\d{0,9}$/.test(cik2) || !/^\d{10}-\d{2}-\d{6}$/.test(accession2) || !original.startsWith(`https://www.sec.gov/Archives/edgar/data/${cik2}/${accession2.replace(/-/g, "")}/`) || original.endsWith("/")) throw invalid4();
        } else if (p.original_status !== "not-supplied" || p.original_url !== null || p.accession !== null) throw invalid4();
        return {
          title: `${institution} \xB7 ${FACT_NAMES[metric]}`,
          url: original || p.source_url,
          explanation: `\uBCF4\uC720 \uAE30\uC900\uC77C ${report} \xB7 \uC81C\uCD9C\uC77C ${filed}. \uD574\uB2F9 \uAE30\uAD00\uC774 \uBCF4\uACE0\uD55C \uBD84\uAE30\uB9D0 \uBCF4\uC720\xB7\uD3C9\uAC00\uC561\uC774\uBA70 \uD604\uC7AC \uBCF4\uC720, \uB9E4\uC218 \uCCB4\uACB0\uAC00 \uB610\uB294 \uB9E4\uB9E4 \uC2E0\uD638\uAC00 \uC544\uB2C8\uC5D0\uC694. \uAE30\uAD00\uBCC4 \uBCF4\uACE0\uBD84\uAE30\uAC00 \uB2E4\uB97C \uC218 \uC788\uC5B4\uC694.` + (original ? "" : " \uC6D0\uBB38 \uC811\uC218\uBC88\uD638\uB294 \uC774 \uACF5\uAC1C \uC790\uB8CC\uC5D0 \uC81C\uACF5\uB418\uC9C0 \uC54A\uC544 \uAE30\uC874 \uACF5\uAC1C \uC9D1\uACC4 \uC790\uB8CC\uB85C \uC5F0\uACB0\uD574\uC694.")
        };
      }
      if (p.kind === "public-etf-flow") {
        const trade = date(p.trade_date), metric = String(fact.metric);
        if (market2 !== "KR" || p.ticker !== ticker || fact.source !== "KRX \uACF5\uAC1C ETF \uC790\uB8CC" || !["etf_listed_units", "etf_nav", "etf_net_assets", "etf_unit_change"].includes(metric) || trade.length !== 10 || trade !== fact.as_of || trade > (/* @__PURE__ */ new Date()).toISOString().slice(0, 10) || [0, 6].includes(new Date(trade).getUTCDay()) || p.source_url !== PUBLIC_DATA + "etf_flow.json" || fact.unit !== (["etf_listed_units", "etf_unit_change"].includes(metric) ? "\uC88C" : "KRW") || metric !== "etf_unit_change" && fact.value < 0 || ["etf_listed_units", "etf_unit_change"].includes(metric) && !Number.isSafeInteger(fact.value)) throw invalid4();
        const previous = metric === "etf_unit_change" ? date(p.previous_date) : null;
        if (previous && (previous.length !== 10 || previous >= trade || [0, 6].includes(new Date(previous).getUTCDay()))) throw invalid4();
        return {
          url: p.source_url,
          explanation: `ETF \uC790\uCCB4\uC758 \uACF5\uAC1C \uC218\uCE58 \xB7 \uAC70\uB798\uC77C ${trade}${previous ? ` \xB7 \uBE44\uAD50 \uAC70\uB798\uC77C ${previous}` : ""}. \uAE30\uC874 KRX \uC218\uC9D1 \uC790\uB8CC\uB97C \uC7AC\uC0AC\uC6A9\uD574\uC694. \uAD6C\uC131\uC885\uBAA9\uC758 \uB9E4\uC218 \uC555\uB825\xB7\uD638\uC7AC\xB7\uC545\uC7AC\uB85C \uD658\uC0B0\uD558\uC9C0 \uC54A\uC544\uC694.`
        };
      }
      if (p.kind === "public-stock-flow") {
        const day2 = date(p.trade_date);
        if (market2 !== "KR" || p.ticker !== ticker || day2.length !== 10 || day2 !== fact.as_of || fact.source !== "\uB124\uC774\uBC84 \uAE08\uC735" || fact.unit !== "\uC8FC" || !Number.isSafeInteger(fact.value) || !["foreign_net_shares", "institution_net_shares"].includes(String(fact.metric)) || p.source_url !== `https://finance.naver.com/item/frgn.naver?code=${ticker}`) throw invalid4();
        return {
          url: p.source_url,
          explanation: "\uBCF4\uAD00\uB41C \uCD5C\uADFC \uAC70\uB798\uC77C\uC758 \uC21C\uB9E4\uB9E4\uB7C9\uC774\uC5D0\uC694. \uC591\uC218\uB294 \uC21C\uB9E4\uC218, \uC74C\uC218\uB294 \uC21C\uB9E4\uB3C4\uC774\uBA70 \uAE08\uC561\uC774 \uC544\uB2CC \uC8FC\uC2DD \uC218\uC608\uC694. \uAC31\uC2E0 \uC2DC\uAC01\uACFC \uAC70\uB798\uC77C\uC740 \uB2E4\uB97C \uC218 \uC788\uC5B4\uC694. \uD638\uC7AC\xB7\uC545\uC7AC\uB098 \uC8FC\uAC00 \uBC29\uD5A5\uC744 \uB73B\uD558\uC9C0 \uC54A\uC544\uC694."
        };
      }
      if (p.kind === "dart-annual") {
        const receipt = text22(p.rcept_no, 14), start = date(p.period_start), end = date(p.period_end), filed = date(p.filed);
        const basis = text22(p.fs_div, 3), account = text22(p.account_name, 200);
        const days = (Date.parse(end) - Date.parse(start)) / 864e5 + 1;
        if (market2 !== "KR" || fact.source !== "DART" || fact.unit !== "KRW" || !["revenue", "operating_income", "net_income"].includes(String(fact.metric)) || !/^\d{14}$/.test(receipt) || [start, end, filed].some((d) => d.length !== 10) || end.slice(0, 4) !== fact.as_of || days < 330 || days > 371 || filed < end || receipt.slice(0, 8) !== filed.replace(/-/g, "") || !["CFS", "OFS"].includes(basis) || p.source_url !== `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${receipt}`) throw invalid4();
        return {
          url: p.source_url,
          explanation: `DART ${basis === "CFS" ? "\uC5F0\uACB0" : "\uBCC4\uB3C4"}\uC7AC\uBB34\uC81C\uD45C\uC758 \uC5F0\uAC04 \uC218\uCE58\uC608\uC694. \uD68C\uACC4\uAE30\uAC04 ${start} ~ ${end} \xB7 \uC81C\uCD9C\uC77C ${filed}.
\uACF5\uC2DC \uACC4\uC815 ${account}`
        };
      }
      const cik = text22(p.cik, 10), accession = text22(p.accession, 20);
      const period = date(p.period_end), form = text22(p.form, 8), tag = text22(p.tag, 200);
      if (market2 !== "US" || fact.source !== "SEC" || !/^[1-9][0-9]{0,9}$/.test(cik) || !/^\d{10}-\d{2}-\d{6}$/.test(accession) || period.length !== 10 || period.slice(0, 4) !== fact.as_of || !["10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"].includes(form) || !/^[A-Za-z][A-Za-z0-9_:]{0,199}$/.test(tag) || typeof p.currency_verified !== "boolean" || (p.currency_verified ? !/^(KRW|USD|CAD|AUD|EUR|GBP|JPY|HKD|CNY|CHF|ILS|SGD|NZD|BRL)$/.test(String(fact.unit)) : fact.unit !== "currency-unverified")) throw invalid4();
      const base = `https://www.sec.gov/Archives/edgar/data/${cik}/${accession.replace(/-/g, "")}/${accession}-index`;
      if (p.source_url !== base + ".html" && p.source_url !== base + ".htm") throw invalid4();
      const url = p.source_url;
      return {
        url,
        ...p.currency_verified ? {} : { unit: "\uBCF4\uACE0 \uD1B5\uD654 \uBBF8\uD655\uC778" },
        explanation: `SEC ${form}\uC758 \uC5F0\uAC04 \uC218\uCE58\uC608\uC694. \uD68C\uACC4\uAE30\uAC04 \uC885\uB8CC\uC77C ${period} \xB7 \uC81C\uCD9C\uC77C\uC740 \uC774 \uC790\uB8CC\uC5D0 \uC5C6\uC5B4\uC694.
XBRL \uD56D\uBAA9 ${tag}` + (p.currency_verified ? "" : "\n\uC800\uC7A5\uB41C \uC6D0\uC790\uB8CC\uC5D0 \uD1B5\uD654\uAC00 \uC5C6\uC5B4 \uB2EC\uB7EC\uB85C \uB2E8\uC815\uD558\uC9C0 \uC54A\uC544\uC694.")
      };
    }
    async function analysisToGraph2(payload, input) {
      const positions = positionsOnly(input), body = row(payload), coverage = row(body.coverage);
      if (body.schema !== "alphaconsole-portfolio-v1" || coverage.requested !== positions.length) throw invalid4();
      const wanted = new Map(positions.map((p) => [`${p.market}:${p.ticker}`, p]));
      const changes = changeDetails(body.public_changes === void 0 && coverage.change_reuse !== void 0 ? { stocks: {} } : body.public_changes, wanted);
      const companies = /* @__PURE__ */ new Map(), missing22 = /* @__PURE__ */ new Set();
      for (const value of array(body.companies, 30)) {
        const company = row(value), id = text22(company.id);
        const expected = wanted.get(id);
        if (!expected || company.ticker !== expected.ticker || company.market !== expected.market || companies.has(id)) throw invalid4();
        companies.set(id, company);
      }
      for (const value of array(coverage.missing, 30)) {
        const company = row(value), id = text22(company.id), expected = wanted.get(id);
        if (!expected || company.ticker !== expected.ticker || company.market !== expected.market || companies.has(id) || missing22.has(id)) throw invalid4();
        missing22.add(id);
      }
      if (companies.size + missing22.size !== wanted.size || coverage.matched !== companies.size) throw invalid4();
      const automatic = parseAutomaticEvidence2(body.automatic_evidence, new Set(wanted.keys()));
      const prices = parseAnalysisPrices2(body.prices, wanted);
      const companyNames = new Map([...companies].map(([id, company]) => {
        const name = text22(company.name, 180);
        const names = company.source_names === void 0 ? [name] : array(company.source_names, 4).map((v) => text22(v, 180));
        if (names[0] !== name || new Set(names).size !== names.length) throw invalid4();
        return [id, names];
      }));
      const documents = /* @__PURE__ */ new Map();
      for (const value of array(body.documents)) {
        const doc = row(value), id = text22(doc.id), source = text22(doc.source, 30);
        const ids = array(doc.company_ids, 30).map((v) => text22(v));
        if (documents.has(id) || !ids.length || new Set(ids).size !== ids.length || ids.some((key) => !companies.has(key)) || doc.kind !== "disclosure") throw invalid4();
        const matches = array(doc.source_matches === void 0 ? [] : doc.source_matches, 30);
        const matchedTickers = /* @__PURE__ */ new Set();
        for (const value2 of matches) {
          const match = row(value2), ticker = text22(match.ticker, 6), receipt = text22(match.receipt_no, 14);
          if (source !== "DART" || match.kind !== "same-dart-receipt" || match.source_file !== "portfolio.json" || !/^\d{6}$/.test(ticker) || !/^\d{14}$/.test(receipt) || id !== `DART:${receipt}` || doc.url !== `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${receipt}` || !ids.includes(`KR:${ticker}`) || date(match.as_of) !== doc.as_of || matchedTickers.has(ticker)) throw invalid4();
          matchedTickers.add(ticker);
        }
        const context = { id, source, url: text22(doc.url, 2048), title: text22(doc.title), as_of: date(doc.as_of), company_ids: ids };
        const lineage = parseDocumentLineage2(doc.event_lineage, context);
        const contract = parseContractFacts2(doc.contract_facts, context);
        const termination = parseContractTermination2(doc.contract_termination, context, companyNames.get(ids[0]));
        const archived = doc.capture_archive !== void 0;
        if (archived && (doc.capture_archive !== "retained-public-capture" || source !== "DART" || !contract && !termination)) throw invalid4();
        documents.set(id, { ids, archived, item: {
          id: `disclosure-${id}`,
          title: text22(doc.title),
          source,
          url: officialDocument(doc.url, source),
          asOf: date(doc.as_of),
          relationship: "direct",
          explanation: "\uC774 \uC885\uBAA9\uC5D0 \uC5F0\uACB0\uB41C \uACF5\uC2DC \uC6D0\uBB38\uC774\uC5D0\uC694. \uC0AC\uC5C5\uC0C1 \uC601\uD5A5\uC774\uB098 \uC8FC\uAC00 \uBC29\uD5A5\uC744 \uB73B\uD558\uC9C0 \uC54A\uC544\uC694." + (matches.length ? " \uACF5\uC2DC \uBAA9\uB85D\xB7\uACF5\uC2DC \uC54C\uB9BC\uC5D0\uC11C \uC811\uC218\uBC88\uD638\xB7\uC885\uBAA9\xB7\uC811\uC218\uC77C\xB7\uC81C\uBAA9\uC774 \uC77C\uCE58\uD574 \uAC19\uC740 \uC6D0\uBB38\uC73C\uB85C \uBB36\uC5C8\uC5B4\uC694. \uB3D9\uC77C DART \uC790\uB8CC\uC758 \uC7AC\uC218\uC9D1\uC774\uBA70 \uB3C5\uB9BD\uB41C \uCD94\uAC00 \uD655\uC778\uC740 \uC544\uB2C8\uC5D0\uC694." : "") + (lineage ? " " + lineage.explanation : "") + (contract ? "\n\n" + contract.explanation : "") + (termination ? "\n\n" + termination.explanation : ""),
          reason: termination ? "\uACC4\uC57D \uD574\uC9C0 \uD1B5\uBCF4 \uACF5\uC2DC" : "\uACF5\uC2DC \uC5F0\uACB0",
          ...lineage || contract || termination ? { sources: [...lineage?.sources || [], ...contract?.sources || [], ...termination?.sources || []] } : {}
        } });
      }
      const missingSources = array(coverage.missing_source_files, 11);
      if (missingSources.some((v) => typeof v !== "string" || !/^(universe_search|stock_report_public|us_stock_report_public|public_disclosure_feed|us_disclosure_feed|member_map_auto_evidence|member_map_ai_candidates|kr_business_overview_public|macro_snapshot|commodity_exposure|portfolio)\.json$/.test(v))) throw invalid4();
      const evidenceCoverage = coverage.evidence === void 0 ? {} : row(coverage.evidence);
      const evidenceFailed = evidenceCoverage.status === "not-supplied" || evidenceCoverage.status === "rejected";
      const counts = [
        ["document_records", "\uACF5\uC2DC", documents.size],
        ["automatic_relationships", "\uAD00\uACC4 \uD6C4\uBCF4", automatic.relations.length],
        ["automatic_materials", "\uC6D0\uBB38 \uBC1C\uCDCC", automatic.materials.length]
      ];
      const notices = counts.flatMap(([key, label2, received]) => {
        if (evidenceCoverage[key] === void 0) return [];
        const count = row(evidenceCoverage[key]);
        if (!Number.isSafeInteger(count.total) || !Number.isSafeInteger(count.returned) || count.total < received || count.returned !== received || count.omitted !== count.total - received) throw invalid4();
        return count.omitted ? [`${label2} ${received}/${count.total}\uAC74 \uD45C\uC2DC`] : [];
      });
      const correctionCount = body.automatic_evidence === void 0 || body.automatic_evidence === null ? void 0 : row(body.automatic_evidence).coverage?.response_records?.corrections;
      if (correctionCount !== void 0) {
        const count = row(correctionCount), received = automatic.corrections?.length || 0;
        if (!Number.isSafeInteger(count.total) || count.total < received || count.returned !== received || count.omitted !== count.total - received || count.truncated !== (count.omitted !== 0)) throw invalid4();
        if (count.omitted) notices.push(`\uC815\uC815\uACF5\uC2DC ${received}/${count.total}\uAC74 \uD45C\uC2DC`);
      }
      const maps = positions.map((position2) => {
        const key = `${position2.market}:${position2.ticker}`, company = companies.get(key);
        const declared = company ? array(company.document_ids).map((v) => text22(v)) : [];
        const associated = [...documents.entries()].filter(([, doc]) => doc.ids.includes(key));
        if (new Set(declared).size !== declared.length || declared.length !== associated.length || declared.some((id) => !documents.get(id)?.ids.includes(key))) throw invalid4();
        const eventItems = associated.map(([, doc]) => doc.item);
        for (const correction of (automatic.corrections || []).filter((c) => c.companyId === key)) {
          if (!company) throw invalid4();
          const priorIndex = eventItems.findIndex((item) => item.url === correction.item.url);
          if (priorIndex < 0) eventItems.push(correction.item);
          else {
            const prior = eventItems[priorIndex];
            if (prior.source !== correction.item.source || prior.title !== correction.item.title || prior.asOf !== correction.item.asOf) throw invalid4();
            eventItems[priorIndex] = {
              ...prior,
              reason: correction.item.reason,
              explanation: `${prior.explanation}

${correction.item.explanation}`
            };
          }
        }
        const facts = (company ? array(company.facts) : []).map((value, index) => {
          const fact = row(value), numeric2 = fact.value;
          if (typeof numeric2 !== "number" || !Number.isFinite(numeric2) || Math.abs(numeric2) > 1e30) throw invalid4();
          const unit = text22(fact.unit, 30), metric = text22(fact.metric, 80);
          return {
            id: ["foreign_net_shares", "institution_net_shares"].includes(metric) ? `flow-${metric}` : HOLDER_METRICS.has(metric) ? `flow-${metric}-${index}` : `fact-${index}`,
            title: FACT_NAMES[metric] || metric,
            value: numeric2.toLocaleString("ko-KR"),
            explanation: "\uCD9C\uCC98\uC5D0 \uD45C\uC2DC\uB41C \uAC12\uACFC \uAE30\uC900\uC77C\uC774\uC5D0\uC694.",
            source: text22(fact.source, 80),
            asOf: date(fact.as_of),
            unit,
            relationship: "unknown",
            ...financialProof(fact, position2.market, position2.ticker)
          };
        });
        const flows = facts.filter((item) => item.id.startsWith("flow-"));
        const financial = [...changes.get(key) || [], ...facts.filter((item) => !item.id.startsWith("flow-"))];
        const failed = !company || missingSources.some((name) => name === "universe_search.json" || (position2.market === "KR" ? ["stock_report_public.json", "public_disclosure_feed.json"] : ["us_stock_report_public.json", "us_disclosure_feed.json"]).includes(name));
        const sections = [
          {
            id: "business",
            title: "\uC0AC\uC5C5 \uC790\uB8CC",
            state: evidenceFailed ? "error" : automatic.materials.some((m) => m.companyIds.includes(key)) ? "ready" : "empty",
            items: automatic.materials.filter((m) => m.companyIds.includes(key)).map((m) => m.item),
            message: evidenceFailed ? "\uC790\uB3D9 \uAD00\uACC4 \uC790\uB8CC\uB97C \uBD88\uB7EC\uC624\uC9C0 \uBABB\uD588\uC5B4\uC694. \uC2E4\uC81C \uAD00\uACC4\uAC00 \uC5C6\uB2E4\uB294 \uB73B\uC740 \uC544\uB2C8\uC5D0\uC694." : "\uC6D0\uBB38\uC5D0 \uD568\uAED8 \uC5B8\uAE09\uB41C \uC790\uB8CC\uC640 \uAD00\uACC4 \uD6C4\uBCF4\uB97C \uAD6C\uBD84\uD574\uC694. \uC5B8\uAE09\uB9CC\uC73C\uB85C \uAC70\uB798 \uAD00\uACC4\uB098 \uC8FC\uAC00 \uC601\uD5A5\uC744 \uD310\uB2E8\uD558\uC9C0 \uC54A\uC544\uC694."
          },
          {
            id: "finance",
            title: "\uACF5\uAC1C \uC7AC\uBB34 \uC790\uB8CC",
            state: failed ? "error" : financial.length ? "ready" : "empty",
            items: financial,
            message: failed ? "\uACF5\uAC1C \uC790\uB8CC \uC77C\uBD80\uB97C \uBD88\uB7EC\uC624\uC9C0 \uBABB\uD588\uC5B4\uC694." : "\uD56D\uBAA9\uB9C8\uB2E4 \uCD9C\uCC98\uC640 \uAE30\uC900\uC77C\uC744 \uD568\uAED8 \uD655\uC778\uD558\uC138\uC694."
          },
          ...flows.length ? [{
            id: "holders",
            title: "\uC218\uAE09 \uC790\uB8CC",
            state: "ready",
            items: flows,
            message: "\uD56D\uBAA9\uBCC4 \uAC70\uB798\uC77C\xB7\uBCF4\uACE0\uAE30\uAC04\xB7\uC81C\uCD9C\uC77C\uC744 \uAD6C\uBD84\uD558\uC138\uC694. \uC21C\uB9E4\uB9E4\uB7C9\xB713F \uBCF4\uC720\xB7ETF \uC218\uCE58\uB9CC\uC73C\uB85C \uD22C\uC790 \uBC29\uD5A5\uC744 \uD310\uB2E8\uD558\uC9C0 \uC54A\uC544\uC694."
          }] : [],
          {
            id: "events",
            title: "\uACF5\uC2DC \uC790\uB8CC",
            state: failed ? "error" : eventItems.length ? "ready" : "empty",
            items: eventItems,
            message: failed ? "\uACF5\uAC1C \uC790\uB8CC \uC77C\uBD80\uB97C \uBD88\uB7EC\uC624\uC9C0 \uBABB\uD588\uC5B4\uC694." : "\uAC19\uC740 \uACF5\uC2DC\uAC00 \uC5EC\uB7EC \uC885\uBAA9\uC5D0 \uC5F0\uACB0\uB3FC\uB3C4 \uACF5\uD1B5 \uC601\uD5A5\uC774 \uD655\uC778\uB41C \uAC83\uC740 \uC544\uB2C8\uC5D0\uC694."
          }
        ];
        return {
          ...position2,
          name: company ? text22(company.name, 180) : position2.ticker,
          sections,
          coverage: { ok: failed ? 0 : 1, total: 1, missing: failed ? ["\uACF5\uAC1C \uC790\uB8CC"] : [] }
        };
      });
      const graph = await buildPortfolioMapGraph2(maps);
      for (const { archived, item } of documents.values()) {
        if (!archived) continue;
        const identity2 = await portfolioDocumentIdentity2(item.url);
        const document2 = graph.documents.find((d) => d.id === identity2?.id);
        if (!document2) throw invalid4();
        const qualifier = " \xB7 \uBCF4\uAD00\uD55C \uC6D0\uBB38 \xB7 \uCD5C\uC2E0 \uBAA9\uB85D \uBC16\uC758 \uC790\uB8CC";
        document2.reason += qualifier;
        for (const proof of document2.evidence) proof.reason += qualifier;
        for (const link of graph.links.filter((l) => l.documentId === document2.id)) link.reason += qualifier;
      }
      const sharedReason = "\uAC19\uC740 \uC6D0\uBB38 \uACF5\uB3D9 \uC5B8\uAE09 \uD6C4\uBCF4 \xB7 \uAC70\uB798 \uAD00\uACC4\xB7\uACF5\uD1B5 \uC601\uD5A5 \uBBF8\uD655\uC778";
      for (const common of automatic.commonMaterials) {
        const identity2 = await portfolioDocumentIdentity2(common.url);
        const document2 = graph.documents.find((d) => d.id === identity2?.id && d.url === common.url);
        if (!document2) throw invalid4();
        const material = automatic.materials.find((m) => m.id === common.materialId);
        const tickers = new Set(common.companyIds.map((id) => wanted.get(id).ticker));
        for (const evidence of document2.evidence) {
          if (tickers.has(evidence.ticker) && evidence.url === common.url && evidence.sectionId === "business" && evidence.originalExplanation === material.item.explanation && !evidence.reason.includes(sharedReason)) evidence.reason += ` \xB7 ${sharedReason}`;
        }
        document2.reason = [...new Set(document2.evidence.map((e) => e.reason))].join(" \xB7 ");
        for (const link of graph.links.filter((l) => l.documentId === document2.id))
          link.reason = [...new Set(link.evidence.map((e) => e.reason))].join(" \xB7 ");
      }
      graph.automaticRelations = automatic.relations;
      if (body.contract_events !== void 0) {
        Object.assign(graph, { contractEvents: await parseContractEvents2(body.contract_events, companyNames) });
        const count = row(row(body.contract_events).coverage);
        if (count.omitted) notices.push(`\uACC4\uC57D \uC0AC\uAC74 ${count.returned}/${count.selected}\uAC74 \uD45C\uC2DC`);
        if (count.oversized_history) notices.push(`\uAE34 \uACC4\uC57D \uC774\uB825 ${count.oversized_history}\uAC74\uC740 \uACF5\uC2DC \uC6D0\uBB38\uC5D0\uC11C \uD655\uC778`);
      }
      const marketContext = await parseMarketContext2(body.market_context, new Set(wanted.keys()), companyNames);
      Object.assign(graph, { marketContext });
      const marketCoverage = body.market_context === void 0 ? void 0 : row(body.market_context).coverage;
      if (marketCoverage !== void 0 && row(marketCoverage).news_groups !== void 0) {
        const groups = row(row(marketCoverage).news_groups), received = marketContext.filter((item) => item.kind === "news").length;
        if (!Number.isSafeInteger(groups.total) || groups.total < received || groups.returned !== received || groups.omitted !== groups.total - received) throw invalid4();
        if (groups.omitted) notices.push(`\uB274\uC2A4 ${received}/${groups.total}\uBB36\uC74C \uD45C\uC2DC`);
      }
      if (notices.length) graph.analysisNotice = `\uCD5C\uADFC \uC6D0\uBB38 \uC6B0\uC120 \xB7 ${notices.join(" \xB7 ")}`;
      for (const company of graph.companies) {
        const quote = prices.get(`${company.market}:${company.ticker}`);
        if (quote) company.closeQuote = quote;
      }
      return attachPublicBusinessJudgments(attachPublicAIReview2(graph, body.ai_review, coverage.ai_review), body.company_judgments);
    }
    async function fetchPortfolioAnalysisGraph2(input, options) {
      const positions = positionsOnly(input);
      const check = () => {
        if (options.signal?.aborted) throw options.signal.reason || new Error("\uC694\uCCAD\uC774 \uCDE8\uC18C\uB418\uC5C8\uC5B4\uC694.");
        const session2 = options.getSession();
        if (!session2 || session2.userId !== options.ownerId || !session2.token) throw new Error("\uB85C\uADF8\uC778 \uACC4\uC815\uC774 \uBCC0\uACBD\uB418\uC5C8\uC5B4\uC694.");
        return session2;
      };
      let session = check();
      if (!positions.length) return buildPortfolioMapGraph2([]);
      const request = (token) => (options.fetcher || fetch)(ENDPOINT2, {
        method: "POST",
        credentials: "omit",
        cache: "no-store",
        redirect: "error",
        signal: options.signal,
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ positions })
      });
      let response, diagnosticStage = "request";
      try {
        response = await request(session.token);
        const current = check();
        if (response.status === 401 && current.token !== session.token) {
          session = current;
          response = await request(session.token);
          check();
        }
        if (!response.ok) throw new Error("unavailable");
        diagnosticStage = "json";
        const payload = await response.json();
        check();
        diagnosticStage = "adapter";
        const graph = await analysisToGraph2(payload, positions);
        check();
        return graph;
      } catch (error) {
        check();
        memberMapLoadDiagnostic(diagnosticStage, error, response);
        throw new Error("\uBD84\uC11D \uC790\uB8CC\uB97C \uBD88\uB7EC\uC624\uC9C0 \uBABB\uD588\uC5B4\uC694. \uC7A0\uC2DC \uD6C4 \uB2E4\uC2DC \uC2DC\uB3C4\uD574 \uC8FC\uC138\uC694.");
      }
    }
    return __toCommonJS(PortfolioAnalysisClient_exports);
  })();
  return MemberMapClientDelta;
})({ buildPortfolioMapGraph, portfolioDocumentIdentity, parseAutomaticEvidence, parseAnalysisPrices, parseMarketContext, parseDocumentLineage, parseContractFacts, parseContractEvents, parseContractTermination, attachPublicAIReview, quotedContractDay, quotedContractFinancialLines });
var order2 = (a, b) => a < b ? -1 : a > b ? 1 : 0;
var MAX_DOCUMENTS = 100;
var KR_MARKETS = /* @__PURE__ */ new Set(["KR", "KOSPI", "KOSDAQ", "KONEX"]);
var US_MARKETS = /* @__PURE__ */ new Set(["US", "NASDAQ", "NYSE", "AMEX", "NYSE AMERICAN", "NYSE ARCA", "BATS"]);
var uniqueSorted = (values) => [...new Map(values.map((value) => [JSON.stringify(value), value])).entries()].sort(([a], [b]) => order2(a, b)).map(([, value]) => value);
var appendUnique = (first, second) => [...new Map([...first, ...second].map((value) => [JSON.stringify(value), value])).values()];
async function sha2562(value) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}
function canonicalMarket(value) {
  const normalized = value.trim().toUpperCase();
  return KR_MARKETS.has(normalized) ? "KR" : US_MARKETS.has(normalized) ? "US" : null;
}
function sourceDate(value) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day4] = value.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day4));
  return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day4 ? value : null;
}
function latestSourceDate(evidence) {
  const dates = evidence.flatMap((row5) => [row5.asOf, ...row5.sources.map((source) => source.asOf)]).map(sourceDate).filter((value) => value !== null);
  return dates.sort(order2).at(-1) || null;
}
function summarize2(evidence) {
  const dates = evidence.flatMap((row5) => [
    row5.asOf,
    ...row5.sources.map((source) => source.asOf),
    ...(row5.sourceRecords || []).map((source) => source.publishedAt)
  ]);
  return {
    source: uniqueSorted(evidence.flatMap((row5) => [row5.source, ...row5.sources.map((source) => source.source)])).join(" \xB7 "),
    asOf: dates.every((date2) => date2 === dates[0]) ? dates[0] : void 0,
    reason: uniqueSorted(evidence.map((row5) => row5.reason)).join(" \xB7 "),
    confirmation: evidence.every((row5) => row5.confirmation === "confirmed") ? "confirmed" : "unknown",
    isCorrection: evidence.some((row5) => row5.isCorrection) ? true : null
  };
}
async function rebuildDocument(id, url, evidence) {
  const rows2 = uniqueSorted(evidence);
  if (!rows2.length) throw new Error("portfolio-document-without-evidence");
  const tickers = uniqueSorted(rows2.map((row5) => row5.ticker));
  const content = uniqueSorted(rows2.map(({ ticker: _ticker, sectionId: _section, reason: _reason, sourceRecords, ...row5 }) => ({
    ...row5,
    ...sourceRecords?.length ? { sourceRecords: uniqueSorted(sourceRecords.map(({ observedAt: _observed, isBackfill: _backfill, ...source }) => source)) } : {}
  })));
  const contentHash = await sha2562(JSON.stringify(content));
  return {
    id,
    kind: "source-document",
    title: rows2[0].title,
    url,
    ...summarize2(rows2),
    evidence: rows2,
    tickers,
    contentHash,
    read_revision: Number.parseInt(contentHash.slice(0, 13), 16) + 1
  };
}
function mergeSections(legacy = [], analysis = []) {
  const indexed = /* @__PURE__ */ new Map();
  for (const section of [...legacy, ...analysis]) {
    const prior = indexed.get(section.id);
    if (!prior) {
      indexed.set(section.id, { ...section, items: [...section.items] });
      continue;
    }
    const states = [prior.state, section.state];
    const state = states.includes("error") ? "error" : states.includes("unsupported") ? "unsupported" : states.includes("ready") ? "ready" : "empty";
    const messages = appendUnique(prior.message ? [prior.message] : [], section.message ? [section.message] : []);
    indexed.set(section.id, {
      ...prior,
      state,
      items: appendUnique(prior.items, section.items),
      ...messages.length ? { message: messages.join("\n") } : {}
    });
  }
  return [...indexed.values()];
}
function mergeCoverageRows(rows2) {
  const hasData = rows2.some((row5) => row5.state === "available" || row5.receivedItems > 0 || row5.linkedItems > 0);
  const hasProblem = rows2.some((row5) => ["partial", "unavailable", "unknown"].includes(row5.state));
  const state = hasProblem ? hasData || rows2.some((row5) => row5.state === "partial") ? "partial" : rows2.some((row5) => row5.state === "unavailable") ? "unavailable" : "unknown" : rows2.some((row5) => row5.state === "available") ? "available" : "empty";
  return {
    ticker: rows2[0].ticker,
    sectionId: rows2[0].sectionId,
    state,
    upstreamStates: uniqueSorted(rows2.flatMap((row5) => row5.upstreamStates)),
    messages: uniqueSorted(rows2.flatMap((row5) => row5.messages)),
    receivedItems: rows2.reduce((total, row5) => total + row5.receivedItems, 0),
    linkedItems: rows2.reduce((total, row5) => total + row5.linkedItems, 0),
    omittedItems: rows2.reduce((total, row5) => total + row5.omittedItems, 0),
    collectionCompleteness: "unknown"
  };
}
function mergedCoverage(legacy, analysis) {
  const groups = /* @__PURE__ */ new Map();
  for (const row5 of [...legacy.coverage.sources, ...analysis.coverage.sources]) {
    const key = `${row5.ticker}\0${row5.sectionId}`;
    groups.set(key, [...groups.get(key) || [], row5]);
  }
  const sources = [...groups.values()].map(mergeCoverageRows).sort((a, b) => order2(`${a.ticker}\0${a.sectionId}`, `${b.ticker}\0${b.sectionId}`));
  return {
    total: sources.length,
    available: sources.filter((row5) => row5.state === "available").length,
    empty: sources.filter((row5) => row5.state === "empty").length,
    partial: sources.filter((row5) => row5.state === "partial").length,
    unavailable: sources.filter((row5) => row5.state === "unavailable").length,
    unknown: sources.filter((row5) => row5.state === "unknown").length,
    sources
  };
}
function companyIndex(graph, label2) {
  const result = /* @__PURE__ */ new Map();
  for (const company of graph.companies) {
    if (result.has(company.id)) throw new Error(`duplicate-${label2}-company`);
    result.set(company.id, company);
  }
  return result;
}
function mergeAutomatic(legacy = [], analysis = []) {
  const relations = new Map(legacy.map((row5) => [row5.id, row5]));
  for (const row5 of analysis) relations.set(row5.id, row5);
  return [...relations.values()].sort((a, b) => order2(a.id, b.id));
}
function mergeNotice(legacy, analysis, totalDocuments) {
  const notices = appendUnique(legacy ? [legacy] : [], analysis ? [analysis] : []);
  if (totalDocuments > MAX_DOCUMENTS) notices.push(`\uD1B5\uD569 \uC6D0\uBB38 ${MAX_DOCUMENTS}/${totalDocuments}\uAC74 \uD45C\uC2DC`);
  return notices.length ? notices.join(" \xB7 ") : void 0;
}
async function mergePortfolioAnalysisGraphs(legacy, analysis) {
  const oldCompanies = companyIndex(legacy, "legacy"), newCompanies = companyIndex(analysis, "analysis");
  const universe = (companies2, label2) => [...companies2.values()].map((row5) => {
    const market2 = canonicalMarket(row5.market);
    if (!market2) throw new Error(`portfolio-${label2}-company-market-unknown`);
    return JSON.stringify([row5.id, row5.ticker, market2]);
  }).sort(order2);
  const oldUniverse = universe(oldCompanies, "legacy"), newUniverse = universe(newCompanies, "analysis");
  if (JSON.stringify(oldUniverse) !== JSON.stringify(newUniverse)) throw new Error("portfolio-company-universe-mismatch");
  const companies = [...oldCompanies.values()].sort((a, b) => order2(a.id, b.id)).map((oldCompany) => {
    const newCompany = newCompanies.get(oldCompany.id);
    const sections = mergeSections(oldCompany.sections, newCompany.sections);
    return {
      ...oldCompany,
      market: canonicalMarket(newCompany.market),
      ...sections.length ? { sections } : {},
      ...newCompany.closeQuote !== void 0 ? { closeQuote: newCompany.closeQuote } : oldCompany.closeQuote !== void 0 ? { closeQuote: oldCompany.closeQuote } : {}
    };
  });
  const documents = /* @__PURE__ */ new Map();
  for (const [label2, graph] of [["legacy", legacy], ["analysis", analysis]]) {
    const seen = /* @__PURE__ */ new Set();
    for (const document2 of graph.documents) {
      if (seen.has(document2.id)) throw new Error(`duplicate-${label2}-document`);
      seen.add(document2.id);
      const prior = documents.get(document2.id);
      if (prior && prior.url !== document2.url) throw new Error("portfolio-document-identity-conflict");
      documents.set(document2.id, { url: document2.url, evidence: [...prior?.evidence || [], ...document2.evidence] });
    }
  }
  const documentEntries = [...documents.entries()].sort(([idA, a], [idB, b]) => {
    const dateA = latestSourceDate(a.evidence), dateB = latestSourceDate(b.evidence);
    return dateA === dateB ? order2(idA, idB) : dateA === null ? 1 : dateB === null ? -1 : order2(dateB, dateA);
  });
  const rebuilt = await Promise.all(documentEntries.slice(0, MAX_DOCUMENTS).map(([id, value]) => rebuildDocument(id, value.url, value.evidence)));
  const links = rebuilt.flatMap((document2) => document2.tickers.map((ticker) => {
    const evidence = document2.evidence.filter((row5) => row5.ticker === ticker);
    return {
      id: `link:${ticker}:${document2.id}`,
      companyId: `company:${ticker}`,
      documentId: document2.id,
      ticker,
      ...summarize2(evidence),
      evidence
    };
  }));
  const automaticRelations = mergeAutomatic(legacy.automaticRelations, analysis.automaticRelations);
  const companyJudgments = memberMapBoundBusinessJudgments(analysis);
  const marketContext = analysis.marketContext ?? legacy.marketContext;
  const contractEvents = analysis.contractEvents ?? legacy.contractEvents;
  const analysisNotice = mergeNotice(legacy.analysisNotice, analysis.analysisNotice, documentEntries.length);
  return {
    companies,
    documents: rebuilt,
    links,
    commonItems: rebuilt.filter((document2) => document2.tickers.length >= 2),
    coverage: mergedCoverage(legacy, analysis),
    ...automaticRelations.length ? { automaticRelations } : {},
    ...companyJudgments.length ? { companyJudgments } : {},
    ...marketContext ? { marketContext } : {},
    ...contractEvents ? { contractEvents } : {},
    ...analysis.aiReviewStatus ? { aiReviewStatus: analysis.aiReviewStatus } : {},
    ...analysisNotice ? { analysisNotice } : {}
  };
}
function preserveIncompletePortfolioGraph(previous, incoming) {
  const universe = (graph) => graph.companies.map((row5) => JSON.stringify([row5.id, row5.ticker, canonicalMarket(row5.market)])).sort(order2);
  if (JSON.stringify(universe(previous)) !== JSON.stringify(universe(incoming))) throw new Error("portfolio-company-universe-mismatch");
  if (Object.hasOwn(incoming, "companyJudgments")) incoming = Object.assign(
    {},
    incoming,
    { companyJudgments: memberMapBoundBusinessJudgments(incoming) }
  );
  if (incoming.aiReviewStatus !== "ready") {
    const priorAI = (previous.automaticRelations || []).filter((row5) => row5.id.startsWith("automatic:ai:"));
    if (priorAI.length) incoming = {
      ...incoming,
      automaticRelations: mergeAutomatic(priorAI, incoming.automaticRelations),
      analysisNotice: [incoming.analysisNotice, `AI \uC790\uB8CC \uAC31\uC2E0 \uBBF8\uC644\uB8CC \xB7 \uC774\uC804 \uD6C4\uBCF4 ${priorAI.length}\uAC74 \uC720\uC9C0`].filter(Boolean).join(" \xB7 ")
    };
  }
  const key = (row5) => `${row5.ticker}\0${row5.sectionId}`;
  const tickers = new Set(incoming.companies.map((row5) => row5.ticker));
  const sources = /* @__PURE__ */ new Map();
  for (const row5 of incoming.coverage.sources) {
    if (!tickers.has(row5.ticker) || !["business", "events"].includes(row5.sectionId) || !["available", "empty", "partial", "unavailable", "unknown"].includes(row5.state) || sources.has(key(row5))) throw new Error("invalid-refresh-coverage");
    sources.set(key(row5), row5);
  }
  for (const row5 of previous.coverage.sources) if (!sources.has(key(row5))) {
    sources.set(key(row5), {
      ...row5,
      state: "unknown",
      upstreamStates: [],
      messages: ["\uC774\uBC88 \uC870\uD68C\uC5D0\uC11C \uC774 \uC790\uB8CC\uC758 \uC218\uC9D1 \uC0C1\uD0DC\uB97C \uBC1B\uC9C0 \uBABB\uD588\uC5B4\uC694."],
      receivedItems: 0,
      linkedItems: 0,
      omittedItems: 0,
      collectionCompleteness: "unknown"
    });
  }
  const incomplete = new Set([...sources.values()].filter((row5) => ["partial", "unavailable", "unknown"].includes(row5.state)).map(key));
  if (!incomplete.size) return incoming;
  const documents = new Map(incoming.documents.map((row5) => [row5.id, row5]));
  if (documents.size !== incoming.documents.length) throw new Error("duplicate-refresh-document");
  const retained = /* @__PURE__ */ new Set();
  const association = (row5) => JSON.stringify([row5.ticker, row5.sectionId, row5.kind, row5.source]);
  const counts = (evidence) => {
    const result = /* @__PURE__ */ new Map();
    for (const row5 of evidence) result.set(association(row5), (result.get(association(row5)) || 0) + 1);
    return result;
  };
  for (const old of previous.documents) {
    const next = documents.get(old.id);
    if (next && next.url !== old.url) throw new Error("portfolio-document-identity-conflict");
    const received = counts(next?.evidence || []), prior = counts(old.evidence);
    if (old.evidence.some((row5) => incomplete.has(key(row5)) && (received.get(association(row5)) || 0) < prior.get(association(row5)))) {
      documents.set(old.id, old);
      retained.add(old.id);
    }
  }
  let slots = Math.max(MAX_DOCUMENTS, retained.size) - retained.size;
  const displayed = [...documents.values()].filter((row5) => retained.has(row5.id) || slots-- > 0);
  const displayedIds = new Set(displayed.map((row5) => row5.id));
  const links = [
    ...incoming.links.filter((row5) => !retained.has(row5.documentId)),
    ...previous.links.filter((row5) => retained.has(row5.documentId))
  ].filter((row5) => displayedIds.has(row5.documentId));
  const rows2 = [...sources.values()];
  const notice = `${incomplete.size}/${rows2.length}\uAC1C \uC790\uB8CC \uBC94\uC704 \uAC31\uC2E0 \uBBF8\uC644\uB8CC \xB7 \uC774\uC804 \uC870\uD68C \uC6D0\uBB38 ${retained.size}\uAC74 \uC720\uC9C0`;
  const deferred = documents.size - displayed.length;
  return {
    ...incoming,
    documents: displayed,
    links,
    commonItems: displayed.filter((row5) => row5.tickers.length >= 2),
    coverage: {
      total: rows2.length,
      available: rows2.filter((row5) => row5.state === "available").length,
      empty: rows2.filter((row5) => row5.state === "empty").length,
      partial: rows2.filter((row5) => row5.state === "partial").length,
      unavailable: rows2.filter((row5) => row5.state === "unavailable").length,
      unknown: rows2.filter((row5) => row5.state === "unknown").length,
      sources: rows2
    },
    analysisNotice: [
      incoming.analysisNotice,
      notice,
      deferred ? `\uD45C\uC2DC \uD55C\uB3C4\uB85C \uC0C8 \uC6D0\uBB38 ${deferred}\uAC74 \uBC18\uC601 \uBCF4\uB958` : void 0
    ].filter(Boolean).join(" \xB7 ")
  };
}
var API = "https://project-yw131.vercel.app";
var clone = (value) => JSON.parse(JSON.stringify(value));
var sameAccount = (a, b) => a?.userId === b?.userId;
var empty = (privateState) => ({
  phase: "signed-out",
  holdings: [],
  watchlist: [],
  watchlistError: null,
  watchlistUnsupportedCount: 0,
  exploratory: [],
  unsupportedCount: 0,
  selectedTickers: [],
  graph: null,
  privateState,
  error: null,
  dataRefresh: { phase: "idle", checkedAt: null, error: null }
});
function workspaceStocks(state) {
  const watched = new Set((state.watchlist || []).map((row5) => `${row5.market}:${row5.ticker}`));
  const stocks = new Map(state.holdings.map((row5) => [row5.ticker, { ticker: row5.ticker, name: row5.name, market: row5.market, held: true, watched: watched.has(`${row5.market}:${row5.ticker}`), exploring: false }]));
  for (const row5 of state.watchlist || []) if (!stocks.has(row5.ticker)) stocks.set(row5.ticker, { ...row5, held: false, watched: true, exploring: false });
  for (const row5 of state.exploratory || []) if (!stocks.has(row5.ticker)) stocks.set(row5.ticker, { ...row5, held: false, watched: false, exploring: true });
  return [...stocks.values()];
}
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
  for (const row5 of rows2) {
    if (!row5 || typeof row5 !== "object" || typeof row5.ticker !== "string") throw new Error("invalid-holdings-response");
    const ticker = row5.ticker.trim().toUpperCase(), market2 = String(row5.market || "").toUpperCase();
    const supported = market2 === "KR" ? /^\d{6}$/.test(ticker) : market2 === "US" && /^[A-Z][A-Z0-9.-]{0,15}$/.test(ticker);
    if (!supported || row5.type === "commodity") {
      unsupportedCount += 1;
      continue;
    }
    const prior = holdings.get(ticker);
    if (prior && prior.market !== market2) throw new Error("ambiguous-holding-market");
    if (prior) {
      const { id: _ambiguousId, ...display } = prior;
      holdings.set(ticker, { ...display, shares: null, avg_cost: null, duplicate: true });
      continue;
    }
    holdings.set(ticker, {
      ticker,
      name: typeof row5.name === "string" && row5.name.trim() ? row5.name.trim() : ticker,
      market: market2,
      shares: finitePositive(row5.shares),
      avg_cost: finitePositive(row5.avg_cost),
      duplicate: false,
      ...typeof row5.id === "string" && row5.id.trim() ? { id: row5.id.trim() } : {},
      ...typeof row5.memo === "string" ? { memo: row5.memo } : {}
    });
  }
  return { holdings: [...holdings.values()], unsupportedCount };
}
function createPortfolioMapWorkspace(options = {}) {
  const getSession = options.getSession || readMapSession, fetcher = options.fetcher || fetch;
  const graphLoader = options.graphLoader || fetchPortfolioMapGraph;
  const usePortfolioAnalysis = options.usePortfolioAnalysis === true;
  let disposed = false;
  const store = createMemberMapStore({ getSession, fetcher: (input, init) => disposed ? Promise.reject(new Error("workspace-disposed")) : fetcher(input, init) });
  let state = empty(store.getState()), account = null, generation = 0;
  let automaticSelection = true;
  let pending = null;
  let refreshController = null;
  let refreshPromise = null;
  let stagedGraph = null;
  let explorationLoading = false;
  const cancelDataRefresh = () => {
    refreshController?.abort();
    refreshController = null;
    refreshPromise = null;
    stagedGraph = null;
    explorationLoading = false;
    state = { ...state, dataRefresh: { phase: "idle", checkedAt: null, error: null } };
  };
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
    cancelDataRefresh();
    explorationLoading = false;
    generation += 1;
    pending?.abort();
    pending = null;
    automaticSelection = true;
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
  const loadGraph = (codes, signal, exploratory) => {
    if (options.graphLoader || !usePortfolioAnalysis) return graphLoader(codes, API, signal);
    const stocks = new Map(workspaceStocks(state).map((row5) => [row5.ticker, row5]));
    if (exploratory && !stocks.has(exploratory.ticker)) stocks.set(exploratory.ticker, { ...exploratory, held: false, watched: false, exploring: true });
    const positions = codes.map((ticker) => {
      const stock = stocks.get(ticker);
      if (!stock || stock.market !== "KR" && stock.market !== "US") throw new Error("invalid-analysis-position-market");
      return { ticker: stock.ticker, market: stock.market };
    });
    if (!account) return Promise.reject(new Error("authentication-required"));
    return Promise.all([
      fetchPortfolioAnalysisGraph(positions, { getSession, ownerId: account.userId, fetcher, signal }),
      (options.analysisSourceLoader || fetchPortfolioMapGraph)(codes, API, signal)
    ]).then(([analysis, legacy]) => mergePortfolioAnalysisGraphs(legacy, analysis));
  };
  const showTickers = async (tickers, fromOpen = false) => {
    if (!account || !valid(generation)) return false;
    const codes = [...new Set(tickers.map((ticker) => ticker.trim().toUpperCase()))];
    if (codes.length > 30 || codes.some((code) => !workspaceStocks(state).some((row) => row.ticker === code))) throw new Error("choose-up-to-30-holdings");
    if (!fromOpen) automaticSelection = false;
    cancelDataRefresh();
    pending?.abort();
    const controller = new AbortController();
    pending = controller;
    const signal = controller.signal, version = ++generation;
    let timedOut = false, cancelWait;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, 6e4);
    timers.add(timer);
    state = { ...state, phase: "loading", error: null };
    emit();
    try {
      if (!valid(version) || signal.aborted) return false;
      const graph = await new Promise((resolve, reject) => {
        cancelWait = () => reject(new Error(timedOut ? "graph-load-timeout" : "graph-load-cancelled"));
        signal.addEventListener("abort", cancelWait, { once: true });
        if (signal.aborted) cancelWait();
        else Promise.resolve(loadGraph(codes, signal)).then(resolve, reject);
      });
      if (!valid(version) || signal.aborted) return false;
      if (graph.companies.length !== codes.length || new Set(graph.companies.map((row) => row.ticker)).size !== codes.length || graph.companies.some((row) => !codes.includes(row.ticker))) throw new Error("graph-holdings-mismatch");
      state = { ...state, phase: "ready", graph, selectedTickers: codes };
      emit();
      return valid(version);
    } catch (error) {
      if (!valid(version) || signal.aborted && !timedOut) return false;
      memberMapLoadDiagnostic(timedOut ? "graph-timeout" : "graph-other", error);
      state = { ...state, phase: "error", error: timedOut ? "graph-load-timeout" : error instanceof Error ? error.message : "data-unavailable" };
      emit();
      return false;
    } finally {
      clearTimeout(timer);
      timers.delete(timer);
      if (cancelWait) signal.removeEventListener("abort", cancelWait);
      if (pending === controller) pending = null;
    }
  };
  const exploreStock = async (metadata) => {
    if (!account || !valid(generation) || state.phase !== "ready" || !state.graph) return false;
    if (!metadata || typeof metadata.ticker !== "string" || typeof metadata.name !== "string" || !metadata.name.trim() || metadata.ticker !== metadata.ticker.trim() || !(metadata.market === "KR" ? /^\d{6}$/.test(metadata.ticker) : metadata.market === "US" && /^[A-Z][A-Z0-9.-]{0,15}$/.test(metadata.ticker))) throw new Error("invalid-exploratory-stock");
    const stock = { ticker: metadata.ticker, name: metadata.name.trim(), market: metadata.market };
    const known = workspaceStocks(state).find((row5) => row5.ticker === stock.ticker);
    if (known && known.market !== stock.market) throw new Error("ambiguous-exploratory-market");
    const codes = [.../* @__PURE__ */ new Set([...state.selectedTickers, stock.ticker])];
    if (codes.length > 30) throw new Error("choose-up-to-30-holdings");
    if (state.selectedTickers.includes(stock.ticker)) return true;
    cancelDataRefresh();
    explorationLoading = true;
    pending?.abort();
    const controller = new AbortController();
    pending = controller;
    const version = ++generation, signal = controller.signal;
    try {
      const graph = await loadGraph([...codes], signal, stock);
      if (!valid(version) || signal.aborted) return false;
      if (graph.companies.length !== codes.length || new Set(graph.companies.map((row5) => row5.ticker)).size !== codes.length || graph.companies.some((row5) => !codes.includes(row5.ticker) || typeof row5.id !== "string" || !row5.id.trim()) || new Set(graph.companies.map((row5) => row5.id)).size !== codes.length) throw new Error("graph-exploration-mismatch");
      const companies = graph.companies.map((company) => company.ticker === stock.ticker && (!company.name.trim() || company.name.trim() === company.ticker) ? { ...company, name: known?.name || stock.name } : company);
      automaticSelection = false;
      state = {
        ...state,
        graph: { ...graph, companies },
        selectedTickers: codes,
        exploratory: known ? state.exploratory : [...state.exploratory || [], stock]
      };
      emit();
      return valid(version);
    } catch {
      valid(version);
      return false;
    } finally {
      if (generation === version) explorationLoading = false;
      if (pending === controller) pending = null;
    }
  };
  const open = async () => {
    if (disposed) return false;
    cancelDataRefresh();
    explorationLoading = false;
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
    const watchController = new AbortController();
    const cancelWatch = () => watchController.abort();
    controller.signal.addEventListener("abort", cancelWatch, { once: true });
    const watchTimer = options.includeWatchlist ? setTimeout(cancelWatch, 5e3) : null;
    if (watchTimer) timers.add(watchTimer);
    state = { ...state, phase: "loading", error: null };
    emit();
    try {
      if (!valid(version) || controller.signal.aborted) return false;
      const watchResult = options.includeWatchlist ? fetchMapWatchlist({
        api: API,
        getSession,
        ownerId: next.userId,
        fetcher,
        signal: watchController.signal,
        onDiagnostic: (error, response2) => memberMapLoadDiagnostic(
          "watch-load",
          error,
          response2,
          () => !disposed && generation === version && !controller.signal.aborted && sameAccount(next, getSession())
        )
      }).then((value) => ({ ...value, error: null }), (error) => ({ stocks: [], unsupportedCount: 0, error: error instanceof Error ? error.message : "watchlist-unavailable" })) : Promise.resolve({ stocks: [], unsupportedCount: 0, error: null });
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
      const watch = await watchResult;
      if (!valid(version) || controller.signal.aborted) return false;
      state = { ...state, ...result, watchlist: watch.stocks, watchlistError: watch.error, watchlistUnsupportedCount: watch.unsupportedCount };
      const stocks = workspaceStocks(state);
      const previous = state.selectedTickers.filter((code) => stocks.some((row5) => row5.ticker === code));
      if (stocks.length > 30 && (automaticSelection || !previous.length)) {
        state = { ...state, phase: "choose-stocks", graph: null, selectedTickers: [] };
        emit();
        await restore;
        return valid(version);
      }
      const success = await showTickers(!automaticSelection && previous.length ? previous : stocks.map((row5) => row5.ticker), true);
      const graphVersion = generation;
      await restore;
      return success && valid(graphVersion) && sameAccount(next, getSession());
    } catch (error) {
      if (!valid(version)) return false;
      state = { ...state, phase: "error", holdings: [], watchlist: [], graph: null, error: error instanceof Error ? error.message : "holdings-unavailable" };
      emit();
      await restore;
      return false;
    } finally {
      clearTimeout(timer);
      timers.delete(timer);
      if (watchTimer) {
        clearTimeout(watchTimer);
        timers.delete(watchTimer);
      }
      controller.signal.removeEventListener("abort", cancelWatch);
      watchController.abort();
    }
  };
  const refreshData = () => {
    if (!account || !valid(generation) || disposed || explorationLoading || state.phase !== "ready" || !state.graph) return Promise.resolve(false);
    if (refreshPromise) return refreshPromise;
    const version = generation, codes = [...state.selectedTickers], controller = new AbortController();
    refreshController = controller;
    const current = () => !disposed && valid(version) && refreshController === controller;
    const checkedAt = state.dataRefresh?.checkedAt || null;
    state = { ...state, dataRefresh: { phase: "checking", checkedAt, error: null } };
    const task = Promise.resolve().then(async () => {
      const timer = setTimeout(() => controller.abort(), 12e4);
      timers.add(timer);
      try {
        if (!current() || controller.signal.aborted) return false;
        const received = await loadGraph(codes, controller.signal);
        if (!current()) return false;
        if (controller.signal.aborted) throw new Error("data-refresh-timeout");
        if (received.companies.length !== codes.length || new Set(received.companies.map((row5) => row5.ticker)).size !== codes.length || received.companies.some((row5) => !codes.includes(row5.ticker))) throw new Error("graph-holdings-mismatch");
        const graph = preserveIncompletePortfolioGraph(state.graph, received);
        const incompleteSources = graph.coverage.sources.filter((row5) => ["unavailable", "partial", "unknown"].includes(row5.state)).length;
        const content = (value) => JSON.stringify(value, (key, item) => key === "observedAt" ? void 0 : item);
        stagedGraph = content(graph) === content(state.graph) ? null : graph;
        state = { ...state, dataRefresh: {
          phase: stagedGraph ? "available" : "idle",
          checkedAt: (/* @__PURE__ */ new Date()).toISOString(),
          error: null,
          incompleteSources,
          totalSources: graph.coverage.sources.length
        } };
        emit();
        return true;
      } catch (error) {
        if (!current()) return false;
        stagedGraph = null;
        state = { ...state, dataRefresh: { phase: "error", checkedAt, error: error instanceof Error ? error.message : "data-refresh-unavailable" } };
        emit();
        return false;
      } finally {
        clearTimeout(timer);
        timers.delete(timer);
        if (refreshController === controller) {
          refreshController = null;
          refreshPromise = null;
        }
      }
    });
    refreshPromise = task;
    emit();
    return task;
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
    exploreStock,
    refreshData,
    applyDataUpdate() {
      if (!account || !valid(generation) || disposed || state.phase !== "ready" || state.dataRefresh?.phase !== "available" || !stagedGraph) return false;
      const graph = stagedGraph;
      stagedGraph = null;
      state = { ...state, graph, dataRefresh: { ...state.dataRefresh, phase: "idle" } };
      emit();
      return true;
    },
    /** Standalone-view opt-in. Hidden/offline tabs do not poll, focus is throttled,
     * and new evidence is never automatically applied over the active canvas.
     */
    bindDataRefresh(target) {
      if (disposed) return () => {
      };
      let stopped = false, lastAttempt = Date.now();
      const interval = 5 * 60 * 1e3;
      const check = () => {
        if (stopped || disposed || target.document.visibilityState !== "visible" || target.navigator.onLine === false || Date.now() - lastAttempt < interval || state.phase !== "ready" || state.dataRefresh?.phase === "checking" || state.dataRefresh?.phase === "available" || explorationLoading) return;
        lastAttempt = Date.now();
        void refreshData();
      };
      let timer;
      const schedule = () => {
        timer = setTimeout(() => {
          timers.delete(timer);
          check();
          if (!stopped && !disposed) schedule();
        }, interval);
        timers.add(timer);
      };
      schedule();
      target.addEventListener("focus", check);
      target.addEventListener("online", check);
      target.document.addEventListener("visibilitychange", check);
      const cleanup = () => {
        stopped = true;
        clearTimeout(timer);
        timers.delete(timer);
        target.removeEventListener("focus", check);
        target.removeEventListener("online", check);
        target.document.removeEventListener("visibilitychange", check);
        authCleanups.delete(cleanup);
      };
      authCleanups.add(cleanup);
      return cleanup;
    },
    editLayout(mapKey, change) {
      if (!valid(generation)) return false;
      return store.update((document2) => editMapLayout(document2, mapKey, change));
    },
    markDocument(mapKey, id, change) {
      if (!valid(generation)) return false;
      const document2 = state.graph?.documents.find((row5) => row5.id === id);
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
      const marks = state.privateState.document?.layouts.find((row5) => row5.map_key === mapKey)?.marks || {};
      return (state.graph?.documents || []).filter((row5) => marks[row5.id]?.disposition !== "irrelevant" && mapReadState(marks[row5.id], row5.read_revision) !== "read");
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
      cancelDataRefresh();
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
var PROTOTYPE_WORLD_WIDTH = 1e3;
var PROTOTYPE_WORLD_HEIGHT = 680;
function normalizeWorldPoint(point2) {
  return { x: 0.5 + point2.x / PROTOTYPE_WORLD_WIDTH, y: 0.5 + point2.y / PROTOTYPE_WORLD_HEIGHT };
}
function prototypeLayoutFromMember(layout) {
  return {
    mapKey: layout.map_key,
    positions: layout.positions.map((position2) => ({
      nodeId: position2.node_id,
      ...normalizeWorldPoint(position2),
      pixelX: position2.x,
      pixelY: position2.y
    })),
    notes: layout.notes.map((note) => ({
      id: note.note_id,
      anchor: note.anchor ? { ...note.anchor } : null,
      ...normalizeWorldPoint(note),
      pixelX: note.x,
      pixelY: note.y,
      text: note.text,
      done: note.done
    })),
    marks: copyMarks(layout.marks)
  };
}
function projectWorkspaceToPrototype(state, mapKey = "main") {
  if (state.phase !== "ready" || !state.graph) return { nodes: [], edges: [], layout: null };
  const memberLayout = state.privateState.document?.layouts.find((layout2) => layout2.map_key === mapKey);
  const layout = memberLayout ? prototypeLayoutFromMember(memberLayout) : null;
  const positions = new Map(layout?.positions.map((position2) => [position2.nodeId, position2]));
  const graphNodes = [...state.graph.companies, ...state.graph.documents];
  const fallback = (id) => fallbackPoint(graphNodes.findIndex((node) => node.id === id), graphNodes.length);
  const pointFor = (id) => positions.get(id) || fallback(id);
  const stocks = state.graph.companies.map((company) => {
    const point2 = pointFor(company.id);
    return {
      id: company.id,
      name: company.name,
      code: company.ticker,
      logo: company.ticker.slice(0, 1),
      kind: "stock",
      priority: 2,
      reason: null,
      source: null,
      asOf: null,
      evidence: [],
      x: point2.x,
      y: point2.y
    };
  });
  const documents = state.graph.documents.map((document2) => {
    const point2 = pointFor(document2.id);
    return {
      id: document2.id,
      name: document2.title,
      code: document2.source,
      kind: "event",
      layer: documentLayer(document2),
      priority: 2,
      reason: document2.reason,
      source: document2.source,
      asOf: document2.asOf || null,
      evidence: document2.evidence.map(projectEvidence),
      x: point2.x,
      y: point2.y
    };
  });
  return { nodes: [...stocks, ...documents], edges: state.graph.links.map(projectLink), layout };
}
function copyMarks(marks) {
  return Object.fromEntries(Object.entries(marks).map(([id, mark]) => [id, { ...mark }]));
}
function fallbackPoint(index, count) {
  const safeIndex = Math.max(index, 0);
  const columns = Math.max(1, Math.ceil(Math.sqrt(Math.max(count, 1))));
  const rows2 = Math.ceil(Math.max(count, 1) / columns);
  return { x: 0.5 + (safeIndex % columns + 0.5) / columns, y: 0.5 + (Math.floor(safeIndex / columns) + 0.5) / rows2 };
}
function documentLayer(document2) {
  const kind = document2.evidence[0]?.kind;
  if (kind === "disclosure") return "filing";
  if (kind === "news") return "news";
  if (kind === "business") return "business";
  return "other";
}
function projectEvidence(evidence) {
  return {
    ticker: evidence.ticker,
    source: evidence.source,
    asOf: evidence.asOf || null,
    url: evidence.url || null,
    reason: evidence.reason,
    explanation: evidence.explanation,
    confirmation: evidence.confirmation
  };
}
function projectLink(link) {
  return {
    id: link.id,
    from: link.documentId,
    to: link.companyId,
    reason: link.reason,
    source: link.source,
    asOf: link.asOf || null,
    evidence: link.evidence.map(projectEvidence),
    influence: "unknown"
  };
}
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
var record7 = (value) => value !== null && typeof value === "object" && !Array.isArray(value) ? value : null;
function exactRecord(value, keys2) {
  const item = record7(value);
  if (!item) return null;
  const actual = Object.keys(item);
  return actual.length === keys2.length && actual.every((key) => keys2.includes(key)) ? item : null;
}
var text12 = (value, max) => {
  if (typeof value !== "string" || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value)) return null;
  const clean = value.trim();
  return clean && clean.length <= max ? clean : null;
};
var stableId = (value, max = LIMITS.id) => {
  const clean = text12(value, max);
  return clean && /^[A-Za-z0-9][A-Za-z0-9:._-]*$/.test(clean) ? clean : null;
};
function dateOnly2(value) {
  const raw = text12(value, 10), match = raw && /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw);
  if (!match || Number(match[1]) < 1900) return null;
  const time = Date.parse(raw + "T00:00:00Z");
  return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === raw ? raw : null;
}
function secureUrl(value) {
  const raw = text12(value, LIMITS.url);
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
function normalizeTicker(value, market2) {
  if (typeof value !== "string") return null;
  const normalized = value.trim().toUpperCase();
  if (market2 === "KR") return /^\d{6}$/.test(normalized) ? normalized : null;
  return normalized.length <= 15 && /^[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)*$/.test(normalized) ? normalized : null;
}
var entityKey = (entity3) => `${entity3.market}:${entity3.ticker}`;
function parseEntity(value, exactKeys2 = ENTITY_KEYS) {
  const item = exactRecord(value, exactKeys2), market2 = item && normalizeMarket(item.market);
  if (!item || !market2 || item.market !== market2) return null;
  const ticker = normalizeTicker(item.ticker, market2);
  return ticker && item.ticker === ticker ? { ticker, market: market2 } : null;
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
    const item = exactRecord(value[index], ENTITY_KEYS), market2 = item && normalizeMarket(item.market);
    const ticker = market2 && item ? normalizeTicker(item.ticker, market2) : null;
    if (!item || !market2 || !ticker) return failure(`holdings[${index}]`);
    const entity3 = { ticker, market: market2 }, key = entityKey(entity3);
    if (seen.has(key)) return failure(`holdings[${index}].duplicate`);
    seen.add(key);
    result.push(entity3);
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
    const publisher = item && text12(item.publisher, LIMITS.label), publishedAt = item && dateOnly2(item.publishedAt);
    const statement = item && text12(item.statement, LIMITS.prose);
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
    const label2 = item && text12(item.label, LIMITS.label), asOf = item && dateOnly2(item.asOf);
    const limitations = item && text12(item.limitations, LIMITS.prose);
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
    const id = item && stableId(item.id, LIMITS.factId), title = item && text12(item.title, LIMITS.label);
    const date2 = item && dateOnly2(item.date), mergeBasis = item && text12(item.mergeBasis, LIMITS.prose);
    const refs = item ? parseIdList(item.sourceIds, sourceIds, `registry.events[${index}].sourceIds`, 2) : failure("event");
    if (!item || !id || !title || !date2 || date2 > reviewedAt || !mergeBasis || !refs.ok || item.status !== "historical-announcement" || item.review !== "manual-primary-source-comparison" || item.impact !== "unknown" || allIds.has(id) || !Array.isArray(item.participants) || item.participants.length < 2 || item.participants.length > LIMITS.participants)
      return failure(`registry.events[${index}]`);
    const allowedRefs = new Set(refs.value), participants2 = [], participantIds = /* @__PURE__ */ new Set();
    for (let participantIndex = 0; participantIndex < item.participants.length; participantIndex++) {
      const participant = exactRecord(item.participants[participantIndex], PARTICIPANT_KEYS);
      const entity3 = participant && parseEntity({ ticker: participant.ticker, market: participant.market });
      const role = participant && text12(participant.role, LIMITS.label);
      const participantRefs = participant ? parseIdList(
        participant.sourceIds,
        allowedRefs,
        `registry.events[${index}].participants[${participantIndex}].sourceIds`
      ) : failure("participant");
      if (!participant || !entity3 || !role || !participantRefs.ok || participantIds.has(entityKey(entity3)))
        return failure(`registry.events[${index}].participants[${participantIndex}]`);
      participantIds.add(entityKey(entity3));
      participants2.push({ ...entity3, role, sourceIds: participantRefs.value });
    }
    allIds.add(id);
    events.push({
      id,
      title,
      date: date2,
      status: "historical-announcement",
      participants: participants2,
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
    const matchedHoldings = event.participants.filter((participant) => holdingKeys.has(entityKey(participant))).map(({ ticker, market: market2 }) => ({ ticker, market: market2 }));
    if (matchedHoldings.length < 2) continue;
    matchedHoldings.forEach((entity3) => matchedKeys.add(entityKey(entity3)));
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
var portfolioReviewedRegistry = {
  schemaVersion: 1,
  reviewedAt: "2026-10-01",
  sources: [
    {
      id: "nvda-intc-nvidia",
      publisher: "NVIDIA",
      publishedAt: "2025-09-18",
      url: "https://nvidianews.nvidia.com/news/nvidia-and-intel-to-develop-ai-infrastructure-and-personal-computing-products",
      statement: "NVIDIA\uC640 Intel\uC774 \uB370\uC774\uD130\uC13C\uD130\xB7PC \uC81C\uD488 \uACF5\uB3D9\uAC1C\uBC1C \uACC4\uD68D\uC744 \uBC1C\uD45C\uD588\uB2E4. Intel\uC740 \uB9DE\uCDA4\uD615 x86 CPU\uC640 RTX GPU \uCE69\uB81B \uD1B5\uD569 \uC81C\uD488\uC744 \uAC1C\uBC1C\uD560 \uC608\uC815\uC774\uB77C\uACE0 \uBC1D\uD614\uB2E4."
    },
    {
      id: "nvda-intc-intel",
      publisher: "Intel",
      publishedAt: "2025-09-18",
      url: "https://www.intel.com/content/www/us/en/newsroom/news/artificial-intelligence/intel-and-nvidia-to-jointly-develop-ai-infrastructure-and-personal-computing-products.html",
      statement: "Intel\uB3C4 \uAC19\uC740 \uB0A0\uC9DC\uC5D0 \uAC19\uC740 \uCC38\uC5EC \uAE30\uC5C5\uACFC \uB370\uC774\uD130\uC13C\uD130\xB7PC \uACF5\uB3D9\uAC1C\uBC1C \uACC4\uD68D\uC744 \uBC1C\uD45C\uD588\uB2E4. \uB2F9\uC2DC \uD22C\uC790 \uACC4\uD68D\uC740 \uBCC4\uB3C4 \uC885\uACB0 \uC870\uAC74\uC774 \uC788\uB294 \uBBF8\uB798 \uACC4\uD68D\uC774\uC5C8\uB2E4."
    },
    {
      id: "nvda-tsmc-production",
      publisher: "NVIDIA",
      publishedAt: "2025-04-14",
      url: "https://blogs.nvidia.com/blog/nvidia-manufacture-american-made-ai-supercomputers-us/",
      statement: "NVIDIA\uB294 TSMC\uC758 \uBBF8\uAD6D \uD53C\uB2C9\uC2A4 \uACF5\uC7A5\uC5D0\uC11C Blackwell \uCE69 \uC0DD\uC0B0\uC774 \uC2DC\uC791\uB410\uB2E4\uACE0 \uBC1C\uD45C\uD588\uB2E4."
    },
    {
      id: "tsmc-customer",
      publisher: "TSMC",
      publishedAt: "2025-03-04",
      url: "https://pr.tsmc.com/english/news/3210",
      statement: "TSMC\uB294 \uBBF8\uAD6D \uD22C\uC790 \uD655\uB300 \uBC1C\uD45C\uC5D0\uC11C NVIDIA\uB97C \uC790\uC0AC\uC758 \uC8FC\uC694 \uACE0\uAC1D \uC911 \uD558\uB098\uB85C \uBA85\uC2DC\uD588\uB2E4. 4\uC6D4\uC758 \uC0DD\uC0B0 \uBC1C\uD45C\uC640\uB294 \uBCC4\uB3C4 \uC0AC\uAC74\uC774\uB2E4."
    },
    {
      id: "skh-tsmc-hbm4-ko",
      publisher: "SK\uD558\uC774\uB2C9\uC2A4 \xB7 \uD55C\uAD6D\uC5B4",
      publishedAt: "2024-04-19",
      url: "https://news.skhynix.co.kr/skhynix-tsmc-hbm4-mou/",
      statement: "SK\uD558\uC774\uB2C9\uC2A4\uB294 TSMC\uC640 \uAE30\uC220 \uD611\uB825 \uC591\uD574\uAC01\uC11C(MOU)\uB97C \uCCB4\uACB0\uD588\uB2E4\uACE0 \uBC1C\uD45C\uD588\uB2E4. HBM4 \uAC1C\uBC1C\uACFC HBM\xB7CoWoS \uD328\uD0A4\uC9D5(\uCE69 \uACB0\uD569) \uCD5C\uC801\uD654 \uD611\uB825 \uACC4\uD68D\uC774\uBA70, \uD604\uC7AC \uC591\uC0B0 \uC2E4\uC801\uC744 \uD655\uC778\uD558\uB294 \uC790\uB8CC\uB294 \uC544\uB2C8\uB2E4."
    },
    {
      id: "skh-tsmc-hbm4-en",
      publisher: "SK\uD558\uC774\uB2C9\uC2A4 \xB7 \uC601\uC5B4",
      publishedAt: "2024-04-19",
      url: "https://news.skhynix.com/en/sk-hynix-partners-with-tsmc-to-strengthen-hbm-technological-leadership/",
      statement: "\uAC19\uC740 \uBC1C\uD45C\uC758 \uC601\uBB38\uBCF8\uB3C4 HBM4\uC758 \uD558\uB2E8 \uC81C\uC5B4 \uCE69\uC5D0 TSMC \uACF5\uC815\uC744 \uD65C\uC6A9\uD558\uACE0 HBM\xB7CoWoS \uACB0\uD569\uC744 \uCD5C\uC801\uD654\uD560 \uACC4\uD68D\uC744 \uC124\uBA85\uD55C\uB2E4. \uD55C\uAD6D\uC5B4\uBCF8\uACFC \uAC19\uC740 \uBC1C\uD589\uC0AC\uC758 \uC790\uB8CC\uB85C \uB3C5\uB9BD \uD655\uC778\uC740 \uC544\uB2C8\uB2E4."
    },
    {
      id: "tsmc-skh-memory-partner",
      publisher: "TSMC",
      publishedAt: "2023-09-28",
      url: "https://pr.tsmc.com/english/news/3070",
      statement: "TSMC\uB294 SK\uD558\uC774\uB2C9\uC2A4\uB97C HBM3\xB7HBM3e \uD611\uB825 \uBA54\uBAA8\uB9AC \uD30C\uD2B8\uB108\uB85C \uBA85\uC2DC\uD588\uB2E4. \uBCF8\uBB38 \uD589\uC0AC\uC77C\uC740 \uBBF8\uAD6D \uD604\uC9C0 2023-09-27, \uC0AC\uC774\uD2B8 \uBC1C\uD589\uC77C\uC740 09-28\uC774\uB2E4. 2024\uB144 HBM4 \uC591\uD574\uAC01\uC11C\uC640\uB294 \uBCC4\uB3C4 \uBC1C\uD45C\uB2E4."
    },
    {
      id: "amd-orcl-mi355x-oracle",
      publisher: "Oracle",
      publishedAt: "2025-06-12",
      url: "https://www.oracle.com/news/announcement/oracle-and-amd-collaborate-to-help-customers-deliver-breakthrough-performance-for-large-scale-ai-and-agentic-workloads-2025-06-12/",
      statement: "Oracle\uC740 AMD\uC640 \uD568\uAED8 MI355X GPU\uB97C OCI \uD074\uB77C\uC6B0\uB4DC\uC5D0\uC11C \uC81C\uACF5\uD560 \uACC4\uD68D\uC744 \uBC1C\uD45C\uD588\uB2E4. \uB2F9\uC2DC \uC81C\uACF5 \uACC4\uD68D\uC774\uBA70, \uD604\uC7AC \uC124\uCE58 \uC218\uB7C9\uC774\uB098 \uC2E4\uC81C \uAD6C\uB9E4 \uAE08\uC561\uC744 \uD655\uC778\uD558\uB294 \uC790\uB8CC\uB294 \uC544\uB2C8\uB2E4."
    },
    {
      id: "amd-orcl-mi355x-amd",
      publisher: "AMD",
      publishedAt: "2025-06-12",
      url: "https://ir.amd.com/news-events/press-releases/detail/1255/amd-unveils-vision-for-an-open-ai-ecosystem-detailing-new-silicon-software-and-systems-at-advancing-ai-2025",
      statement: "AMD\uC758 \uAC19\uC740 \uB0A0 \uD589\uC0AC \uBC1C\uD45C \uC911 Oracle \uD56D\uBAA9\uC5D0\uC11C\uB3C4 OCI\uAC00 MI355X GPU \uAE30\uBC18 \uD074\uB77C\uC6B0\uB4DC\uB97C \uC81C\uACF5\uD560 \uACC4\uD68D\uC774\uB77C\uACE0 \uC124\uBA85\uD55C\uB2E4. \uB2E4\uB978 \uCC38\uC5EC\uC0AC\uC758 \uBC1C\uD45C\uB294 \uC774 \uC0AC\uAC74\uC5D0 \uD569\uCE58\uC9C0 \uC54A\uC558\uB2E4."
    }
  ],
  relationships: [
    {
      id: "relation:nvda-intc-collaboration-20250918",
      from: { ticker: "NVDA", market: "US" },
      to: { ticker: "INTC", market: "US" },
      label: "\uC81C\uD488 \uACF5\uB3D9\uAC1C\uBC1C \uBC1C\uD45C",
      asOf: "2025-09-18",
      status: "historical-announcement",
      sourceIds: ["nvda-intc-nvidia", "nvda-intc-intel"],
      review: "manual-primary-source-comparison",
      impact: "unknown",
      limitations: "\uB450 \uD68C\uC0AC\uC758 \uB2F9\uC2DC \uACF5\uB3D9\uAC1C\uBC1C \uBC1C\uD45C\uB97C \uD655\uC778\uD588\uB2E4. \uD604\uC7AC \uC81C\uD488 \uCD9C\uC2DC\xB7\uB9E4\uCD9C \uD6A8\uACFC\xB7\uC9C0\uBD84 \uBCF4\uC720 \uC0C1\uD0DC\uB294 \uC774 \uC790\uB8CC\uB9CC\uC73C\uB85C \uD655\uC778\uD558\uC9C0 \uC54A\uC558\uB2E4."
    },
    {
      id: "relation:tsmc-nvda-manufacturing-20250414",
      from: { ticker: "TSM", market: "US" },
      to: { ticker: "NVDA", market: "US" },
      label: "\uCE69 \uC0DD\uC0B0\xB7\uACE0\uAC1D \uAD00\uACC4",
      asOf: "2025-04-14",
      status: "dated-fact",
      sourceIds: ["nvda-tsmc-production", "tsmc-customer"],
      review: "manual-primary-source-comparison",
      impact: "unknown",
      limitations: "\uB2F9\uC2DC \uC0DD\uC0B0 \uBC1C\uD45C\uC640 \uACE0\uAC1D \uAD00\uACC4\uB97C \uD655\uC778\uD588\uB2E4. \uB450 \uBC1C\uD45C\uB294 \uC11C\uB85C \uB2E4\uB978 \uC0AC\uAC74\uC774\uBA70, \uD604\uC7AC \uACF5\uAE09\uB7C9\xB7\uB9E4\uCD9C \uBE44\uC911\xB7\uC8FC\uAC00 \uC601\uD5A5\uC740 \uD655\uC778\uD558\uC9C0 \uC54A\uC558\uB2E4."
    },
    {
      id: "relation:skh-tsmc-hbm-collaboration-20240419",
      from: { ticker: "000660", market: "KR" },
      to: { ticker: "TSM", market: "US" },
      label: "HBM \uAE30\uC220 \uD611\uB825",
      asOf: "2024-04-19",
      status: "historical-announcement",
      sourceIds: ["skh-tsmc-hbm4-ko", "tsmc-skh-memory-partner"],
      review: "manual-primary-source-comparison",
      impact: "unknown",
      limitations: "\uC591\uC0AC\uC758 \uC11C\uB85C \uB2E4\uB978 \uC2DC\uC810 \uC6D0\uBB38\uC73C\uB85C HBM \uD611\uB825 \uAD00\uACC4\uB97C \uD655\uC778\uD588\uB2E4. 2023\uB144 \uD30C\uD2B8\uB108 \uBC1C\uD45C\uC640 2024\uB144 HBM4 \uD611\uB825 \uACC4\uD68D\uC740 \uBCC4\uB3C4 \uC0AC\uAC74\uC774\uB2E4. \uD604\uC7AC \uC591\uC0B0\xB7\uACF5\uAE09\uB7C9\xB7\uB9E4\uCD9C\xB7\uC8FC\uAC00 \uC601\uD5A5\uC740 \uD655\uC778\uD558\uC9C0 \uC54A\uC558\uB2E4."
    },
    {
      id: "relation:amd-orcl-mi355x-cloud-20250612",
      from: { ticker: "AMD", market: "US" },
      to: { ticker: "ORCL", market: "US" },
      label: "GPU \uAE30\uBC18 \uD074\uB77C\uC6B0\uB4DC \uC81C\uACF5 \uACC4\uD68D",
      asOf: "2025-06-12",
      status: "historical-announcement",
      sourceIds: ["amd-orcl-mi355x-oracle", "amd-orcl-mi355x-amd"],
      review: "manual-primary-source-comparison",
      impact: "unknown",
      limitations: "AMD \uC81C\uD488\uC744 Oracle \uD074\uB77C\uC6B0\uB4DC\uC5D0\uC11C \uC81C\uACF5\uD55C\uB2E4\uB294 \uB2F9\uC2DC \uACC4\uD68D\uC744 \uC591\uC0AC \uC6D0\uBB38\uC73C\uB85C \uD655\uC778\uD588\uB2E4. \uD604\uC7AC \uACF5\uAE09\uB7C9\xB7\uAD6C\uB9E4 \uAE08\uC561\xB7\uB9E4\uCD9C \uBE44\uC911\xB7\uC8FC\uAC00 \uC601\uD5A5\uC740 \uD655\uC778\uD558\uC9C0 \uC54A\uC558\uB2E4."
    }
  ],
  events: [
    {
      id: "event:nvda-intc-collaboration-20250918",
      title: "NVIDIA\xB7Intel \uC81C\uD488 \uACF5\uB3D9\uAC1C\uBC1C \uBC1C\uD45C",
      date: "2025-09-18",
      status: "historical-announcement",
      sourceIds: ["nvda-intc-nvidia", "nvda-intc-intel"],
      participants: [
        { ticker: "NVDA", market: "US", role: "\uACF5\uB3D9\uAC1C\uBC1C \uCC38\uC5EC \xB7 AI \uAE30\uBC18 \uC2DC\uC2A4\uD15C\xB7GPU \uAE30\uC220", sourceIds: ["nvda-intc-nvidia", "nvda-intc-intel"] },
        { ticker: "INTC", market: "US", role: "\uACF5\uB3D9\uAC1C\uBC1C \uCC38\uC5EC \xB7 \uB9DE\uCDA4\uD615 x86 CPU \uAC1C\uBC1C \uACC4\uD68D", sourceIds: ["nvda-intc-nvidia", "nvda-intc-intel"] }
      ],
      mergeBasis: "\uC591\uC0AC\uC758 2025-09-18 \uC6D0\uBB38\uC5D0\uC11C \uCC38\uC5EC \uAE30\uC5C5\xB7\uBC1C\uD45C\uC77C\xB7\uACF5\uB3D9\uAC1C\uBC1C \uB300\uC0C1\uC774 \uC77C\uCE58\uD55C\uB2E4. \uAC19\uC740 \uACF5\uB3D9 \uBC1C\uD45C\uC758 \uB450 \uAC8C\uC7AC\uBCF8\uC774\uBA70 \uB3C5\uB9BD\uC801\uC778 \uC131\uACFC \uAC80\uC99D\uC740 \uC544\uB2C8\uB2E4. TSMC \uAD00\uB828 \uBC1C\uD45C\uB294 \uD569\uCE58\uC9C0 \uC54A\uC558\uB2E4.",
      review: "manual-primary-source-comparison",
      impact: "unknown"
    },
    {
      id: "event:skh-tsmc-hbm4-mou-20240419",
      title: "SK\uD558\uC774\uB2C9\uC2A4\xB7TSMC HBM4 \uD611\uB825 \uBC1C\uD45C",
      date: "2024-04-19",
      status: "historical-announcement",
      sourceIds: ["skh-tsmc-hbm4-ko", "skh-tsmc-hbm4-en"],
      participants: [
        { ticker: "000660", market: "KR", role: "HBM4 \uBA54\uBAA8\uB9AC \uAC1C\uBC1C \xB7 TSMC \uACF5\uC815 \uD65C\uC6A9 \uACC4\uD68D", sourceIds: ["skh-tsmc-hbm4-ko", "skh-tsmc-hbm4-en"] },
        { ticker: "TSM", market: "US", role: "\uC81C\uC5B4 \uCE69 \uACF5\uC815\xB7\uCE69 \uACB0\uD569 \uAE30\uC220 \uD611\uB825 \uACC4\uD68D", sourceIds: ["skh-tsmc-hbm4-ko", "skh-tsmc-hbm4-en"] }
      ],
      mergeBasis: "\uAC19\uC740 SK\uD558\uC774\uB2C9\uC2A4 \uBC1C\uD45C\uC758 \uD55C\uAD6D\uC5B4\xB7\uC601\uC5B4\uBCF8\uC5D0\uC11C \uCC38\uC5EC \uAE30\uC5C5\xB7\uBC1C\uD45C\uC77C\xB7\uD611\uB825 \uB300\uC0C1\uC774 \uC77C\uCE58\uD574 \uC0AC\uAC74 \uD558\uB098\uB85C \uBB36\uC5C8\uB2E4. \uB3C5\uB9BD\uB41C \uB450 \uAE30\uAD00\uC758 \uD655\uC778\uC740 \uC544\uB2C8\uB2E4. 2023\uB144 TSMC \uD30C\uD2B8\uB108 \uBC1C\uD45C\uB294 \uD569\uCE58\uC9C0 \uC54A\uC558\uB2E4. \uB2F9\uC2DC \uACC4\uD68D\uC774\uBA70 \uD604\uC7AC \uC591\uC0B0 \uC131\uACFC\uB294 \uD655\uC778\uD558\uC9C0 \uC54A\uC558\uB2E4.",
      review: "manual-primary-source-comparison",
      impact: "unknown"
    },
    {
      id: "event:amd-orcl-mi355x-cloud-20250612",
      title: "AMD\xB7Oracle MI355X \uD074\uB77C\uC6B0\uB4DC \uC81C\uACF5 \uACC4\uD68D \uBC1C\uD45C",
      date: "2025-06-12",
      status: "historical-announcement",
      sourceIds: ["amd-orcl-mi355x-oracle", "amd-orcl-mi355x-amd"],
      participants: [
        { ticker: "AMD", market: "US", role: "\uD074\uB77C\uC6B0\uB4DC\uC5D0 \uC0AC\uC6A9\uD560 MI355X GPU \uAC1C\uBC1C\uC0AC", sourceIds: ["amd-orcl-mi355x-oracle", "amd-orcl-mi355x-amd"] },
        { ticker: "ORCL", market: "US", role: "MI355X \uAE30\uBC18 OCI \uD074\uB77C\uC6B0\uB4DC \uC81C\uACF5 \uACC4\uD68D", sourceIds: ["amd-orcl-mi355x-oracle", "amd-orcl-mi355x-amd"] }
      ],
      mergeBasis: "2025-06-12 \uC591\uC0AC \uBC1C\uD45C\uC758 \uAE30\uC5C5\xB7GPU \uC81C\uD488\xB7\uD074\uB77C\uC6B0\uB4DC \uC81C\uACF5 \uACC4\uD68D\uC774 \uC77C\uCE58\uD574 \uC774 \uBC1C\uD45C\uB9CC \uD558\uB098\uB85C \uBB36\uC5C8\uB2E4. AMD \uD589\uC0AC \uBC1C\uD45C\uC758 \uB2E4\uB978 \uAE30\uC5C5\xB7\uC81C\uD488 \uACC4\uD68D\uC740 \uC81C\uC678\uD588\uB2E4. \uB450 \uB2F9\uC0AC\uC790\uC758 \uBC1C\uD45C\uC774\uBA70 \uB3C5\uB9BD\uC801\uC778 \uC774\uD589 \uAC80\uC99D\uC740 \uC544\uB2C8\uB2E4.",
      review: "manual-primary-source-comparison",
      impact: "unknown"
    }
  ]
};
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
  const participants2 = fact.participants.map((participant) => [
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
    participants2,
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
var entityKey2 = (entity3) => `${entity3.market}:${entity3.ticker}`;
var sourceEvidence = (sources) => sources.map((source) => ({
  id: source.id,
  sourceURL: source.url,
  publisher: source.publisher,
  publishedAt: source.publishedAt,
  statement: source.statement
}));
var firstSource = (sources) => sources[0] || null;
function reviewedPrototypeTopic(fact) {
  const claim = "label" in fact ? fact.label : fact.title;
  const statements = fact.sources.map((source) => source.statement).join("\n");
  const patterns = {
    supply: /공급|고객|공동\s*개발|기술\s*협력|협력\s*(?:발표|계획)|클라우드(?:에서|를)?\s*제공/,
    contract: /계약|수주|해지|정정/,
    policy: /정책|규제|관세|수출\s*통제/,
    commodity: /원자재|원유|천연가스|구리\s*가격/
  };
  const topics = Object.keys(patterns).filter((topic) => patterns[topic].test(claim) && patterns[topic].test(statements));
  return topics.length === 1 ? topics[0] : "holding";
}
var position = (index, count) => ({
  x: 0.75 + (index % 3 + 0.5) / 6,
  y: 0.5 + (Math.floor(index / 3) + 0.5) / Math.max(1, Math.ceil(count / 3))
});
function projectReviewedPrototype(state) {
  if (state.phase !== "ready" || !state.graph) return emptyReviewedPrototype();
  const holdingsByTicker = new Map(workspaceStocks(state).map((holding) => [holding.ticker, holding]));
  const companiesByEntity = /* @__PURE__ */ new Map();
  const holdings = state.graph.companies.flatMap((company) => {
    const holding = holdingsByTicker.get(company.ticker);
    if (!holding || holding.market !== "KR" && holding.market !== "US") return [];
    companiesByEntity.set(entityKey2({ ticker: company.ticker, market: holding.market }), company.id);
    return [{ ticker: company.ticker, market: holding.market }];
  });
  const facts = buildReviewedPortfolioFacts(holdings, portfolioReviewedRegistry);
  const nodes = [], edges = [];
  const recordsMap = {};
  const total = facts.relationships.length + facts.events.length;
  facts.relationships.forEach((fact, index) => {
    const mode = "relationships", record8 = reviewedRecord(mode, fact);
    const nodeId = record8.id, evidence = sourceEvidence(fact.sources), source = firstSource(fact.sources);
    recordsMap[record8.id] = recordFor(mode, fact, record8);
    nodes.push({
      id: nodeId,
      kind: "reviewed-relationship",
      name: fact.label,
      code: "\uAC80\uD1A0 \uC644\uB8CC \uAD00\uACC4",
      logo: "",
      priority: 2,
      topic: reviewedPrototypeTopic(fact),
      reason: fact.limitations,
      source: source?.publisher || null,
      sourceURL: source?.url || null,
      asOf: fact.asOf,
      evidence,
      relationshipKind: fact.label,
      recordId: record8.id,
      read_revision: record8.read_revision,
      ...position(index, total)
    });
    for (const endpoint of [fact.from, fact.to]) {
      const companyId = companiesByEntity.get(entityKey2(endpoint));
      if (companyId) edges.push(edgeFor("relationships", fact, record8, nodeId, companyId, endpoint, fact.label, evidence, source));
    }
  });
  facts.events.forEach((fact, index) => {
    const mode = "events", record8 = reviewedRecord(mode, fact);
    const nodeId = record8.id, evidence = sourceEvidence(fact.sources), source = firstSource(fact.sources);
    recordsMap[record8.id] = recordFor(mode, fact, record8);
    nodes.push({
      id: nodeId,
      kind: "reviewed-event",
      name: fact.title,
      code: "\uAC80\uD1A0 \uC644\uB8CC \uACF5\uD1B5 \uC0AC\uAC74",
      logo: "",
      priority: 2,
      topic: reviewedPrototypeTopic(fact),
      reason: fact.mergeBasis,
      source: source?.publisher || null,
      sourceURL: source?.url || null,
      asOf: fact.date,
      evidence,
      relationshipKind: null,
      recordId: record8.id,
      read_revision: record8.read_revision,
      ...position(facts.relationships.length + index, total)
    });
    const participants2 = new Map(fact.participants.map((participant) => [entityKey2(participant), participant]));
    for (const holding of fact.matchedHoldings) {
      const companyId = companiesByEntity.get(entityKey2(holding)), participant = participants2.get(entityKey2(holding));
      if (companyId && participant) edges.push(edgeFor("events", fact, record8, nodeId, companyId, holding, participant.role, evidence, source));
    }
  });
  return { nodes, edges, recordsMap, facts };
}
function edgeFor(mode, fact, record8, nodeId, companyId, endpoint, reason, evidence, source) {
  const isRelationship = mode === "relationships";
  return {
    id: `reviewed-link:${fact.id}:${entityKey2(endpoint)}`,
    from: nodeId,
    to: companyId,
    reason,
    source: source?.publisher || null,
    sourceURL: source?.url || null,
    asOf: isRelationship ? fact.asOf : fact.date,
    evidence,
    relationshipKind: isRelationship ? fact.label : null,
    recordId: record8.id,
    read_revision: record8.read_revision,
    influence: "unknown"
  };
}
function recordFor(mode, fact, record8) {
  const isRelationship = mode === "relationships";
  return {
    ...record8,
    mode,
    factId: fact.id,
    asOf: isRelationship ? fact.asOf : fact.date,
    sourceURLs: fact.sources.map((source) => source.url),
    relationshipKind: isRelationship ? fact.label : null
  };
}
function emptyReviewedPrototype() {
  return {
    nodes: [],
    edges: [],
    recordsMap: {},
    facts: { relationships: [], events: [], coverage: {
      status: "empty",
      reason: "workspace-not-ready",
      reviewedAt: null,
      holdings: { provided: 0, eligible: 0, matched: 0 },
      sources: { reviewed: 0 },
      relationships: { reviewed: 0, included: 0 },
      events: { reviewed: 0, included: 0 }
    } }
  };
}
function projectAutomaticPrototype(graph) {
  const companies = new Map(graph?.companies.map((c) => [`${c.market}:${c.ticker}`, c]));
  const relations = graph?.automaticRelations || [];
  const nodes = relations.map((r, index) => {
    const names = r.participants.map((p) => companies.get(p.id)?.name || p.name || p.id);
    return {
      id: r.id,
      kind: "event",
      recordKind: "relationship",
      proofLabel: r.reportedBasis === "business-period" ? "\uC0AC\uC5C5\uBCF4\uACE0\uC11C\uC0C1 \uD655\uC778 \xB7 \uBCF4\uACE0\uAE30\uAC04 \uAE30\uC900" : r.reportedBasis === "filing-period" ? "\uBCF4\uACE0\uC11C\uC0C1 \uD655\uC778 \xB7 \uBCF4\uACE0\uAE30\uAC04 \uAE30\uC900" : r.reported ? "\uACF5\uC2DC\uC0C1 \uD655\uC778 \xB7 \uACB0\uC0B0\uAE30\uC900" : "\uC790\uB3D9 \uCD94\uCD9C \xB7 \uAD00\uACC4 \uD6C4\uBCF4",
      layer: r.reported ? "relationships" : "candidates",
      topic: r.reported && r.reportedBasis === "business-period" ? "supply" : "holding",
      name: r.title,
      code: r.reported ? "\uD604\uC7AC \uC720\uD6A8 \uC5EC\uBD80 \uBBF8\uD655\uC778" : "\uC6D0\uBB38 \uD655\uC778 \uD544\uC694",
      logo: "",
      priority: 1,
      reason: r.reported && r.reportedBasis !== "filing-period" ? r.reason : `${names.join(" \u2194 ")}
${r.reason}`,
      source: r.source,
      asOf: r.asOf,
      read_revision: r.read_revision,
      ...r.reported && r.measure ? { measure: r.measure } : {},
      evidence: r.url ? [{ url: r.url, source: r.source, asOf: r.asOf, explanation: r.reason }] : [],
      x: 1.05 + index % 3 * 0.2,
      y: 0.6 + Math.floor(index / 3) * 0.18
    };
  });
  const edges = relations.flatMap((r) => r.participants.flatMap((p) => {
    const company = companies.get(p.id);
    return company ? [{
      id: `automatic-link:${r.id}:${p.id}`,
      from: r.id,
      to: company.id,
      confirmation: r.reported ? "confirmed" : "candidate",
      type: r.reported ? "direct" : "unknown",
      strength: 0,
      impact: "\uBBF8\uD655\uC778",
      impactReason: r.reportedBasis === "business-period" ? "\uC0AC\uC5C5\uBCF4\uACE0\uC11C\uC5D0 \uC9C1\uC811 \uAE30\uC7AC\uB41C \uAC70\uB798 \uC0C1\uB300\uBC29\uC774\uC5D0\uC694. \uD604\uC7AC \uC720\uD6A8 \uC5EC\uBD80\xB7\uAC70\uB798 \uADDC\uBAA8\xB7\uC8FC\uAC00 \uC601\uD5A5\uC740 \uBBF8\uD655\uC778\uC774\uC5D0\uC694." : r.reportedBasis === "filing-period" ? `${p.role === "from" ? "\uBCF4\uACE0\uAE30\uAC04\uC758 \uACF5\uC2DC\uC0C1 \uC9C0\uBC30\uAE30\uC5C5" : "\uC9C0\uBC30\uAE30\uC5C5 \uD604\uD669\uC744 \uACF5\uC2DC\uD55C \uD68C\uC0AC"}\uC608\uC694. \uD604\uC7AC \uAD00\uACC4\xB7\uC9C0\uBD84\uC728\xB7\uC8FC\uAC00 \uC601\uD5A5\uC740 \uBBF8\uD655\uC778\uC774\uC5D0\uC694.` : r.reported ? "\uACB0\uC0B0\uAE30\uC900\uC77C\uC758 \uACF5\uC2DC\uC0C1 \uC9C0\uBD84 \uAD00\uACC4\uC608\uC694. \uD604\uC7AC \uAD00\uACC4\uC640 \uC8FC\uAC00 \uC601\uD5A5\uC740 \uBBF8\uD655\uC778\uC774\uC5D0\uC694." : "\uC790\uB3D9 \uCD94\uCD9C\uD55C \uAD00\uACC4 \uD6C4\uBCF4\uC774\uBA70 \uD604\uC7AC \uAD00\uACC4\uC640 \uC8FC\uAC00 \uC601\uD5A5\uC740 \uBBF8\uD655\uC778\uC774\uC5D0\uC694.",
      ...r.reported && r.measure ? { measure: r.measure } : {},
      reason: r.reason,
      verb: r.reportedBasis === "filing-period" ? p.role === "from" ? "\uBCF4\uACE0\uC11C\uC0C1 \uC9C0\uBC30\uAE30\uC5C5" : "\uACF5\uC2DC \uC791\uC131 \uD68C\uC0AC" : p.roleLabel || r.title,
      source: r.source,
      asOf: r.asOf,
      evidence: nodes.find((n) => n.id === r.id).evidence
    }] : [];
  }));
  const recordsMap = Object.fromEntries(relations.map((r) => [r.id, { id: r.id, read_revision: r.read_revision, sourceURLs: r.url ? [r.url] : [] }]));
  return { nodes, edges, recordsMap };
}
function parsePortfolioMapEntry(search) {
  if (typeof search !== "string" || search.length > 2048) return null;
  const params = new URLSearchParams(search);
  if (params.getAll("ticker").length !== 1 || params.getAll("market").length !== 1) return null;
  const stock = { ticker: params.get("ticker").toUpperCase(), market: params.get("market") };
  return validIdentity(stock) ? stock : null;
}
function portfolioMapEntryPath(search) {
  const stock = parsePortfolioMapEntry(search);
  return "/member-map-review" + (stock ? "?" + new URLSearchParams(stock) : "");
}
var MAX_RESULTS = 12;
var MAX_BODY_BYTES = 64 * 1024;
var KR_MARKETS2 = /* @__PURE__ */ new Set(["KR", "KOSPI", "KOSDAQ", "KONEX"]);
var US_MARKETS2 = /* @__PURE__ */ new Set(["US", "NASDAQ", "NYSE", "AMEX", "NYSE AMERICAN", "NYSE ARCA", "BATS"]);
function boundedString(value, max, allowEmpty = false) {
  if (typeof value !== "string" || value.length > max || /[\u0000-\u001f\u007f]/.test(value)) {
    throw new Error("Invalid search metadata");
  }
  const result = value.trim();
  if (!allowEmpty && !result) throw new Error("Invalid search metadata");
  return result;
}
function normalizeSearchResults(payload) {
  if (!Array.isArray(payload) || payload.length > MAX_RESULTS) {
    throw new Error("Invalid search response");
  }
  const byKey = /* @__PURE__ */ new Map();
  let unsupportedCount = 0;
  for (const value of payload) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error("Invalid search row");
    }
    const row5 = value;
    const ticker = boundedString(row5.ticker, 16).toUpperCase();
    const name = boundedString(row5.name, 160);
    const listing = boundedString(row5.market, 32).toUpperCase();
    const koreanName = row5.name_kr === void 0 ? "" : boundedString(row5.name_kr, 160, true);
    if (row5.etf !== void 0 && typeof row5.etf !== "boolean") {
      throw new Error("Invalid ETF metadata");
    }
    const market2 = KR_MARKETS2.has(listing) ? "KR" : US_MARKETS2.has(listing) ? "US" : null;
    if (!market2) {
      unsupportedCount++;
      continue;
    }
    if (!(market2 === "KR" ? /^\d{6}$/ : /^[A-Z][A-Z0-9.-]{0,15}$/).test(ticker)) {
      throw new Error("Invalid search ticker");
    }
    const item = { ticker, name: market2 === "US" ? koreanName || name : name, market: market2 };
    if (row5.etf === true) item.etf = true;
    const key = `${market2}:${ticker}`;
    const previous = byKey.get(key);
    if (previous && (previous.name !== item.name || previous.etf !== item.etf)) {
      throw new Error("Ambiguous duplicate search ticker");
    }
    if (!previous) byKey.set(key, item);
  }
  return { stocks: [...byKey.values()], unsupportedCount };
}
async function readSearchPayload(response, signal) {
  if (!response.ok || response.redirected) throw new Error("Search request failed");
  const declaredLength = response.headers.get("content-length");
  if (declaredLength !== null && (!/^\d+$/.test(declaredLength) || Number(declaredLength) > MAX_BODY_BYTES)) {
    throw new Error("Search response exceeds size limit");
  }
  const reader = response.body?.getReader();
  if (!reader) throw new Error("Missing search response body");
  const cancel = () => {
    void reader.cancel().catch(() => {
    });
  };
  signal.addEventListener("abort", cancel, { once: true });
  const chunks = [];
  let size = 0;
  let complete = false;
  try {
    signal.throwIfAborted();
    while (true) {
      const { done, value } = await reader.read();
      signal.throwIfAborted();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_BODY_BYTES) throw new Error("Search response exceeds size limit");
      chunks.push(value);
    }
    complete = true;
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.byteLength;
    }
    return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } finally {
    signal.removeEventListener("abort", cancel);
    if (!complete) cancel();
    reader.releaseLock();
  }
}
async function fetchPortfolioStockSearch(query, options = {}) {
  if (typeof query !== "string") throw new Error("Invalid search query");
  const q = query.trim().slice(0, 60);
  if (!q) return { stocks: [], unsupportedCount: 0 };
  const { fetcher = globalThis.fetch, signal, api = "https://project-yw131.vercel.app/api/search" } = options;
  if (!/^\/[A-Za-z0-9/_-]+$/.test(api) || api.startsWith("//")) throw new Error("Invalid search endpoint");
  signal?.throwIfAborted();
  const controller = new AbortController();
  const abortFromCaller = () => controller.abort(signal?.reason);
  signal?.addEventListener("abort", abortFromCaller, { once: true });
  let onAbort = () => {
  };
  const aborted2 = new Promise((_, reject) => {
    onAbort = () => reject(controller.signal.reason);
    controller.signal.addEventListener("abort", onAbort, { once: true });
  });
  const timer = setTimeout(() => controller.abort(new DOMException("Search timed out", "TimeoutError")), 5e3);
  const request = async () => {
    const params = new URLSearchParams({ q, market: "all", limit: String(MAX_RESULTS) });
    const response = await fetcher(`${api}?${params}`, {
      method: "GET",
      credentials: "omit",
      redirect: "error",
      signal: controller.signal
    });
    controller.signal.throwIfAborted();
    const payload = await readSearchPayload(response, controller.signal);
    controller.signal.throwIfAborted();
    return normalizeSearchResults(payload);
  };
  try {
    return await Promise.race([request(), aborted2]);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abortFromCaller);
    controller.signal.removeEventListener("abort", onAbort);
  }
}
var SHORT_NAMES = {
  "US:TSM": "TSMC"
};
function portfolioCompanyDisplayName(market2, ticker, formalName) {
  return SHORT_NAMES[`${market2}:${ticker.toUpperCase()}`] || formalName;
}
var plain = (v) => !!v && typeof v === "object" && !Array.isArray(v);
var point = (v) => plain(v) && Number.isFinite(v.x) && Number.isFinite(v.y);
var pixel = (value, scale, prior) => prior !== void 0 && value === 0.5 + prior / scale ? prior : (value - 0.5) * scale;
var PROTOTYPE_MAP_KEY = "main_v2";
var emptyLayout = (map_key) => ({ map_key, positions: [], notes: [], marks: {} });
function prototypeDraftRejection(value, code) {
  return {
    code,
    positions: plain(value) && Array.isArray(value.positions) ? value.positions.length : null,
    notes: plain(value) && Array.isArray(value.notes) ? value.notes.length : null,
    marks: plain(value) && plain(value.marks) ? Object.keys(value.marks).length : null
  };
}
function prototypeLayoutBases(state, extraNodes) {
  const base = projectWorkspaceToPrototype({ ...state, privateState: { ...state.privateState, document: { layouts: [] } } });
  return new Map([...base.nodes, ...extraNodes].map((n) => [n.id, { x: 0.5, y: 0.5 }]));
}
function prototypeLayouts(state, market2) {
  const layouts = state.privateState.document?.layouts || [];
  const legacy = marketLayout(layouts.find((l) => l.map_key === "main") || emptyLayout("main"), market2);
  const saved = layouts.find((l) => l.map_key === PROTOTYPE_MAP_KEY);
  const stockIds = new Set(state.graph?.companies.map((n) => n.id) || []);
  const oldBases = saved ? null : new Map(projectWorkspaceToPrototype({
    ...state,
    privateState: { ...state.privateState, document: { layouts: [] } }
  }).nodes.filter((n) => n.kind === "stock").map((n) => [n.id, n]));
  const layout = saved ? marketLayout(saved, market2) : {
    ...legacy,
    map_key: PROTOTYPE_MAP_KEY,
    positions: legacy.positions.filter((p) => stockIds.has(p.node_id)).map((p) => {
      const base = oldBases?.get(p.node_id);
      return base ? { ...p, x: p.x - (base.x - 0.5) * 1e3, y: p.y - (base.y - 0.5) * 680 } : p;
    })
  };
  return { legacy, layout, saved: !!saved };
}
function marketLayout(layout, market2) {
  const aliases = /* @__PURE__ */ new Map(), positions = new Map(layout.positions.map((p) => [p.node_id, p])), marks = { ...layout.marks };
  for (const node of market2.nodes) {
    const ids = node.legacyIds || [];
    for (const id of ids) {
      aliases.set(id, node.id);
      for (const edge of market2.edges.filter((e) => e.from === node.id)) {
        if (edge.id.startsWith("market-link:")) aliases.set(`market-link:${id}:${edge.id.split(":").slice(-2).join(":")}`, edge.id);
        for (const old of edge.legacyIds || []) aliases.set(old, edge.id);
      }
    }
    if (!positions.has(node.id)) {
      const old = ids.map((id) => positions.get(id)).find(Boolean);
      if (old) positions.set(node.id, { ...old, node_id: node.id });
    }
    if (!marks[node.id]) {
      const old = ids.map((id) => layout.marks[id]).filter(Boolean);
      if (old.length) marks[node.id] = {
        read_revision: old.find((m) => m.read_revision)?.read_revision ?? null,
        important: old.some((m) => m.important),
        disposition: old.some((m) => m.disposition === "later") ? "later" : old.every((m) => m.disposition === "irrelevant") ? "irrelevant" : "inbox"
      };
    }
  }
  return {
    ...layout,
    positions: [...positions.values()],
    marks,
    notes: layout.notes.map((n) => n.anchor && aliases.has(n.anchor.id) ? { ...n, anchor: { ...n.anchor, id: aliases.get(n.anchor.id) } } : n)
  };
}
function mergePrototypeDraft(state, value, onReject) {
  const reject = (code, rejected = value) => {
    try {
      onReject?.(prototypeDraftRejection(rejected, code));
    } catch {
    }
    return null;
  };
  if (state.phase !== "ready" || !state.graph || !["ready", "saving"].includes(state.privateState.phase) || !state.privateState.document) return reject("state_unready");
  if (!plain(value)) return reject("draft_shape");
  if (!Array.isArray(value.positions)) return reject("positions_shape");
  if (!Array.isArray(value.notes)) return reject("notes_shape");
  if (!plain(value.marks)) return reject("marks_shape");
  if (value.positions.length > 200) return reject("positions_limit");
  if (value.notes.length > 100) return reject("notes_limit");
  if (Object.keys(value.marks).length > 200) return reject("marks_limit");
  const reviewed = projectReviewedPrototype(state), automatic = projectAutomaticPrototype(state.graph), contracts = projectContractPrototype(state.graph), markets = projectMarketPrototype(state.graph);
  const market2 = { nodes: [...markets.nodes, ...contracts.nodes], edges: [...markets.edges, ...contracts.edges], recordsMap: { ...markets.recordsMap, ...contracts.recordsMap } };
  const { layout: prior } = prototypeLayouts(state, market2);
  if (!state.privateState.document.layouts.some((l) => l.map_key === PROTOTYPE_MAP_KEY) && state.privateState.document.layouts.length >= 3) return reject("layout_limit");
  const layoutBases = prototypeLayoutBases(state, [...reviewed.nodes, ...automatic.nodes, ...market2.nodes]);
  const allowed = new Set([...state.graph.companies, ...state.graph.documents, ...reviewed.nodes, ...automatic.nodes, ...market2.nodes].map((n) => n.id));
  const edgeIds = /* @__PURE__ */ new Set([...state.graph.links.map((e) => e.id), ...reviewed.edges.map((e) => e.id), ...automatic.edges.map((e) => e.id), ...market2.edges.map((e) => e.id)]), positions = new Map(prior.positions.map((p) => [p.node_id, p]));
  const seen = /* @__PURE__ */ new Set();
  for (const p of value.positions) {
    if (!point(p)) return reject("position_coordinates");
    if (typeof p.id !== "string" || !allowed.has(p.id) || seen.has(p.id)) return reject("position_identity");
    seen.add(p.id);
    const previous = positions.get(p.id);
    const position2 = { node_id: p.id, x: pixel(p.x, 1e3, previous?.x), y: pixel(p.y, 680, previous?.y) };
    const base = layoutBases.get(p.id);
    if (!previous && base && p.x === base.x && p.y === base.y && validMapDocument({ layouts: [{ map_key: PROTOTYPE_MAP_KEY, positions: [position2], notes: [], marks: {} }] })) continue;
    positions.set(p.id, position2);
  }
  const oldNotes = new Map(prior.notes.map((n) => [n.note_id, n]));
  const notes = [];
  for (const n of value.notes) {
    if (!point(n) || typeof n.id !== "string" || typeof n.text !== "string" || typeof n.done !== "boolean" || typeof n.target !== "string") return reject("notes_shape");
    const old = oldNotes.get(n.id);
    if (!old && !/^note-[0-9]+$/.test(n.id)) return reject("notes_identity");
    const anchor = n.target ? allowed.has(n.target) ? { kind: "node", id: n.target } : edgeIds.has(n.target) ? { kind: "edge", id: n.target } : old && old.anchor?.id === n.target ? old.anchor : void 0 : null;
    if (anchor === void 0) return reject("notes_anchor");
    notes.push({ note_id: n.id, anchor, x: pixel(n.x, 1e3, old?.x), y: pixel(n.y, 680, old?.y), text: n.text, done: n.done });
  }
  const marks = { ...prior.marks };
  for (const [id, mark] of Object.entries(value.marks)) {
    const doc = state.graph.documents.find((d) => d.id === id) || reviewed.recordsMap[id] || automatic.recordsMap[id] || market2.recordsMap[id];
    if (!doc) return reject("mark_identity");
    if (!plain(mark) || ["read", "readTouched", "important", "later", "irrelevant"].some((key) => mark[key] !== void 0 && typeof mark[key] !== "boolean")) return reject("mark_shape");
    const old = prior.marks[id];
    const nextMark = {
      read_revision: mark.read ? doc.read_revision : mark.readTouched ? null : old?.read_revision ?? null,
      important: !!mark.important,
      disposition: mark.irrelevant ? "irrelevant" : mark.later ? "later" : "inbox"
    };
    if (!Object.hasOwn(prior.marks, id) && !mark.read && !mark.readTouched && !mark.important && !mark.later && !mark.irrelevant && validMapDocument({ layouts: [{ map_key: PROTOTYPE_MAP_KEY, positions: [], notes: [], marks: { [id]: nextMark } }] })) continue;
    marks[id] = nextMark;
  }
  const next = { map_key: PROTOTYPE_MAP_KEY, positions: [...positions.values()], notes, marks };
  if (Object.hasOwn(prior, "origins")) next.origins = prior.origins.filter((origin) => {
    const p = positions.get(origin.node_id);
    return p && origin.dx === p.x && origin.dy === p.y;
  });
  const layouts = state.privateState.document.layouts.filter((l) => l.map_key !== PROTOTYPE_MAP_KEY);
  return validMapDocument({ layouts: [...layouts, next] }) ? next : reject("final_schema", next);
}
function mergePrototypeOriginSave(state, draft, captures, onReject) {
  const reject = (code) => {
    onReject?.(prototypeDraftRejection(draft, code));
    return null;
  };
  if (!Array.isArray(captures) || captures.length > 200) return reject("origins_limit");
  const next = mergePrototypeDraft(state, draft, onReject);
  if (!next) return null;
  const model = prototypeMemberModel(state), allowed = new Map(model.nodes.map((n) => [n.id, n])), incoming = new Map(draft.positions.map((p) => [p.id, p]));
  const positions = new Map(next.positions.map((p) => [p.node_id, p]));
  const prior = state.privateState.document.layouts.find((l) => l.map_key === PROTOTYPE_MAP_KEY);
  const origins = new Map((prior?.origins || []).filter((o) => {
    const p = positions.get(o.node_id);
    return p && p.x === o.dx && p.y === o.dy;
  }).map((o) => [o.node_id, o])), seen = /* @__PURE__ */ new Set();
  for (const capture of captures) {
    const node = allowed.get(capture?.id), current = incoming.get(capture?.id) || node;
    if (!node || !positions.has(capture.id) && !incoming.has(capture.id) || seen.has(capture.id) || !point(capture) || !point(capture.raw) || capture.raw.x !== current.x || capture.raw.y !== current.y || !coordinate(capture.x) || !coordinate(capture.y)) return reject("origin_capture");
    seen.add(capture.id);
    const position2 = positions.get(capture.id) || { node_id: capture.id, x: pixel(current.x, 1e3), y: pixel(current.y, 680) };
    positions.set(capture.id, position2);
    origins.set(capture.id, { node_id: capture.id, x: capture.x, y: capture.y, dx: position2.x, dy: position2.y });
  }
  const result = { ...next, positions: [...positions.values()], origins: [...origins.values()] };
  return validMapDocument({ layouts: [...state.privateState.document.layouts.filter((l) => l.map_key !== PROTOTYPE_MAP_KEY), result] }) ? result : reject("final_schema");
}
function prototypeMemberModel(state, explorationNotice = "", visitBaseline) {
  if (state.phase !== "ready" || !state.graph) return { nodes: [], edges: [], notes: {}, marks: {}, writable: false };
  const projected = projectWorkspaceToPrototype(state), graph = state.graph, reviewed = projectReviewedPrototype(state), automatic = projectAutomaticPrototype(state.graph), contracts = projectContractPrototype(state.graph), markets = projectMarketPrototype(state.graph);
  const judgments = new Map(memberMapBoundBusinessJudgments(graph).map((row) => [row.record_id, row]));
  const market2 = { nodes: [...markets.nodes, ...contracts.nodes], edges: [...markets.edges, ...contracts.edges], recordsMap: { ...markets.recordsMap, ...contracts.recordsMap } };
  const layoutBases = prototypeLayoutBases(state, [...reviewed.nodes, ...automatic.nodes, ...market2.nodes]);
  const stocks = new Map(workspaceStocks(state).map((stock) => [stock.ticker, stock]));
  const { layout, saved } = prototypeLayouts(state, market2);
  const positions = new Map(layout.positions.map((p) => [p.node_id, p]));
  const evidence = (rows2) => rows2.map((s) => ({ url: s.sourceURL, source: s.publisher, asOf: s.publishedAt, explanation: s.statement }));
  const reviewedNodes = reviewed.nodes.map((n) => ({
    ...n,
    kind: "event",
    recordKind: n.kind === "reviewed-event" ? "event" : "relationship",
    layer: n.kind === "reviewed-event" ? "events" : "relationships",
    evidence: evidence(n.evidence),
    x: positions.has(n.id) ? 0.5 + positions.get(n.id).x / 1e3 : 0.5,
    y: positions.has(n.id) ? 0.5 + positions.get(n.id).y / 680 : 0.5
  }));
  const records = [...graph.documents, ...Object.values(reviewed.recordsMap), ...Object.values(automatic.recordsMap), ...Object.values(market2.recordsMap)];
  const visitRevisions = Object.fromEntries(records.filter((d) => !contracts.replacedDocumentIds.has(d.id)).map((d) => [d.id, d.read_revision]));
  const changes = Object.fromEntries(records.map((d) => {
    if (visitBaseline !== void 0) return [d.id, visitBaseline === null ? "\uAE30\uC900\uC5C6\uC74C" : !Object.hasOwn(visitBaseline.revisions, d.id) ? "\uC0C8\uB85C" : visitBaseline.revisions[d.id] === d.read_revision ? "\uAE30\uC874" : "\uBCC0\uACBD"];
    const m = layout?.marks[d.id];
    return [d.id, m?.read_revision ? m.read_revision === d.read_revision ? "\uD655\uC778" : "\uBCC0\uACBD" : "\uBBF8\uD655\uC778"];
  }));
  return {
    coverageNotice: graph.analysisNotice || "",
    ...visitBaseline !== void 0 ? { visit: { previousAt: visitBaseline?.visitedAt || null, revisions: visitRevisions } } : {},
    layoutBases: Object.fromEntries(layoutBases),
    savedPositionIds: [...positions.keys()],
    positionOrigins: Object.fromEntries((layout.origins || []).filter((origin) => {
      const p = positions.get(origin.node_id);
      return p && p.x === origin.dx && p.y === origin.dy;
    }).map((origin) => [origin.node_id, { x: origin.x / 1e3, y: origin.y / 680 }])),
    nodes: [...projected.nodes.filter((n) => !contracts.replacedDocumentIds.has(n.id)).map((n) => {
      const company = n.kind === "stock" ? graph.companies.find((c) => c.id === n.id) : void 0;
      const stockMarket = company?.market || stocks.get(n.code)?.market;
      const formalName = company?.name || n.name;
      const position2 = positions.get(n.id);
      return {
        ...n,
        x: position2 ? 0.5 + position2.x / 1e3 : 0.5,
        y: position2 ? 0.5 + position2.y / 680 : 0.5,
        ...company ? { name: portfolioCompanyDisplayName(stockMarket || "", company.ticker, formalName), formalName } : {},
        ticker: company?.ticker,
        priority: 2,
        recordKind: n.kind === "event" ? "document" : "company",
        changeStatus: changes[n.id],
        market: stockMarket,
        held: n.kind === "stock" ? stocks.get(n.code)?.held ?? false : void 0,
        watched: n.kind === "stock" ? stocks.get(n.code)?.watched ?? false : void 0,
        explore: n.kind === "stock" ? stocks.get(n.code)?.exploring ?? false : false,
        sections: n.kind === "stock" ? graph.companies.find((c) => c.id === n.id)?.sections : void 0,
        closeQuote: n.kind === "stock" ? graph.companies.find((c) => c.id === n.id)?.closeQuote : void 0,
        reason: n.kind === "stock" ? stocks.get(n.code)?.held ? "\uBCF4\uC720\uC885\uBAA9\uC5D0 \uC5F0\uACB0\uB41C \uC790\uB8CC\uB97C \uD655\uC778\uD558\uC138\uC694." : stocks.get(n.code)?.watched ? "\uAD00\uC2EC\uC885\uBAA9\uC774\uC5D0\uC694. \uC2E4\uC81C \uBCF4\uC720 \uC218\uB7C9\uC774\uB098 \uD3C9\uAC00\uAE08\uC561\uC5D0\uB294 \uD3EC\uD568\uD558\uC9C0 \uC54A\uC544\uC694." : explorationNotice || "\uC774\uBC88 \uD654\uBA74\uC5D0\uC11C \uD0D0\uC0C9 \uC911\uC774\uC5D0\uC694. \uBCF4\uC720\xB7\uAD00\uC2EC\uBAA9\uB85D\uC5D0 \uB4F1\uB85D\uD558\uC9C0 \uC54A\uC558\uC73C\uBA70, \uB2E4\uC2DC \uC811\uC18D\uD558\uBA74 \uAC80\uC0C9\uD574\uC11C \uCD94\uAC00\uD574\uC57C \uD574\uC694." : graph?.documents.find((d) => d.id === n.id)?.reason,
        source: n.kind === "event" ? graph?.documents.find((d) => d.id === n.id)?.source : "\uB0B4 \uD3EC\uD2B8\uD3F4\uB9AC\uC624",
        asOf: n.kind === "event" ? graph?.documents.find((d) => d.id === n.id)?.asOf : void 0,
        evidence: n.kind === "event" ? graph?.documents.find((d) => d.id === n.id)?.evidence : []
      };
    }), ...reviewedNodes.map((n) => ({ ...n, changeStatus: changes[n.id] })), ...[...automatic.nodes, ...market2.nodes].map((n) => ({
      ...n,
      changeStatus: changes[n.id],
      // Explicit null withdraws old annotations on shallow graph updates.
      companyJudgment: judgments.get(n.id) || null,
      x: positions.has(n.id) ? 0.5 + positions.get(n.id).x / 1e3 : 0.5,
      y: positions.has(n.id) ? 0.5 + positions.get(n.id).y / 680 : 0.5
    }))],
    edges: [
      ...projected.edges.filter((e) => !contracts.replacedDocumentIds.has(e.from)).map((e) => ({ ...e, type: "unknown", confirmation: "candidate", strength: 0, impact: "\uBBF8\uD655\uC778", impactReason: "\uC790\uB8CC \uC5F0\uACB0\uB9CC\uC73C\uB85C \uC2E4\uC801\uC774\uB098 \uC8FC\uAC00 \uC601\uD5A5\uC744 \uD310\uB2E8\uD558\uC9C0 \uC54A\uC544\uC694.", verb: "\uC790\uB8CC \uC5F0\uACB0" })),
      ...reviewed.edges.map((e) => ({ ...e, evidence: evidence(e.evidence), type: "documented", confirmation: "confirmed", strength: 0, impact: "\uBBF8\uD655\uC778", impactReason: "\uC790\uB8CC\uC5D0 \uBA85\uC2DC\uB41C \uCC38\uC5EC \uAD00\uACC4\uC774\uBA70, \uD604\uC7AC \uC2E4\uC801\uC774\uB098 \uC8FC\uAC00 \uC601\uD5A5\uC744 \uB73B\uD558\uC9C0 \uC54A\uC544\uC694.", verb: e.reason })),
      ...automatic.edges,
      ...market2.edges
    ],
    notes: Object.fromEntries((layout?.notes || []).map((n) => [n.note_id, { id: n.note_id, target: n.anchor?.id || "", x: 0.5 + n.x / 1e3, y: 0.5 + n.y / 680, text: n.text, done: n.done, todo: n.done, pinned: !!n.anchor }])),
    marks: Object.fromEntries(records.map((d) => {
      const m = layout?.marks[d.id];
      return [d.id, { read: m?.read_revision === d.read_revision, important: !!m?.important, later: m?.disposition === "later", irrelevant: m?.disposition === "irrelevant" }];
    })),
    writable: state.privateState.phase === "ready" && !!state.privateState.document && (saved || state.privateState.document.layouts.length < 3)
  };
}
function mountMemberPrototype(frame, template, workspace, options = {}) {
  const templateURL = options.templateURL ? new URL(options.templateURL, window.location.href) : null;
  if (templateURL && (templateURL.origin !== window.location.origin || templateURL.username || templateURL.password)) throw new Error("prototype-origin-mismatch");
  const account = options.account || (() => readMapSession()?.userId || null);
  const introStore = "alphanest:map-guide:hidden:v1";
  let introHidden = false;
  try {
    introHidden = window.localStorage.getItem(introStore) === "1";
  } catch {
  }
  let owner = null, generation = 0, port = null, disposed = false, key = "", current = workspace.getState();
  let originGeneration = 0, appliedOriginGeneration = -1;
  let visitRevisions = null, rememberedVisitGeneration = -1;
  const model = (state) => {
    const projected = prototypeMemberModel(state, options.explorationNotice, options.visitBaseline);
    const visit = "visit" in projected ? projected.visit : void 0;
    visitRevisions = visit?.revisions || null;
    return {
      ...projected,
      ...visit ? { visit: { previousAt: visit.previousAt, error: options.visitError || null } } : {},
      originGeneration: ++originGeneration,
      ...options.localView ? { localView: { hiddenStockIds: options.localView.getHiddenStockIds() } } : {}
    };
  };
  const rememberVisit = () => {
    if (!options.onVisitDisplayed || !visitRevisions || rememberedVisitGeneration === originGeneration || current.privateState.phase !== "ready") return;
    const stamp2 = originGeneration, member = owner, revisions = { ...visitRevisions };
    rememberedVisitGeneration = stamp2;
    const isCurrent = () => !disposed && hydrated && stamp2 === originGeneration && appliedOriginGeneration === stamp2 && member === owner && member === account() && current.phase === "ready" && current.privateState.phase === "ready";
    if (!isCurrent()) return;
    void Promise.resolve().then(() => isCurrent() && options.onVisitDisplayed(revisions, isCurrent)).then((persisted) => {
      if (isCurrent()) port?.postMessage({ type: "visit-status", persisted: persisted === true });
    }).catch(() => {
      if (isCurrent()) port?.postMessage({ type: "visit-status", persisted: false });
    });
  };
  let waiting = false, reloadPending = false, frameNonce = "";
  let hydrated = false, focusRevision = 0;
  let displayedWindow = "", reloadingWindow = null;
  let rejectedDraft = null;
  let searchRequest = null, searchRevision = 0;
  let searchStocks = /* @__PURE__ */ new Map();
  let exploration = null;
  const entry = validIdentity(options.entryStock) ? { stock: { ...options.entryStock }, phase: "waiting", windowKey: "" } : null;
  let entryRequest = null;
  let logoRequest = new AbortController();
  const requestedLogos = /* @__PURE__ */ new Set();
  const sendLogos = (stocks) => {
    if (!options.logoLoader || !port || !hydrated) return;
    const version = generation, member = owner, signal = logoRequest.signal;
    for (const stock of stocks) {
      if (stock.market !== "KR" && stock.market !== "US") continue;
      const identity2 = stock.market + ":" + stock.ticker;
      if (requestedLogos.has(identity2)) continue;
      requestedLogos.add(identity2);
      void options.logoLoader({ ticker: stock.ticker, market: stock.market }, { signal }).then((dataURL) => {
        if (disposed || signal.aborted || version !== generation || member !== account() || typeof dataURL !== "string" || dataURL.length > 175e3 || !/^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(dataURL)) return;
        port?.postMessage({ type: "logo-update", identity: identity2, dataURL });
      }).catch(() => {
      });
    }
  };
  const focusWindowKey = (state) => JSON.stringify([
    state.selectedTickers,
    state.graph?.companies.map((row) => [row.id, row.ticker, row.market])
  ]);
  let pendingFocus = null;
  const clearReturnFocus = () => {
    focusRevision++;
    pendingFocus = null;
  };
  const flushReturnFocus = () => {
    if (!pendingFocus?.requested) return;
    const pending = pendingFocus, state = workspace.getState();
    if (disposed || pending.owner !== account() || pending.owner !== owner || state.phase !== "ready" || focusWindowKey(state) !== pending.windowKey || !state.selectedTickers.includes(pending.ticker)) {
      clearReturnFocus();
      return;
    }
    const company = state.graph?.companies.find((row) => row.ticker === pending.ticker);
    if (!company) {
      clearReturnFocus();
      return;
    }
    if (!port || !hydrated) return;
    pendingFocus = null;
    port.postMessage({ type: "focus-stock", id: company.id });
  };
  const prepareReturnFocus = () => {
    clearReturnFocus();
    const member = account(), revision2 = focusRevision;
    return (ticker) => {
      const state = workspace.getState();
      if (disposed || revision2 !== focusRevision || !member || member !== account() || member !== owner || state.phase !== "ready" || !state.selectedTickers.includes(ticker) || !state.graph?.companies.some((row) => row.ticker === ticker)) return;
      focusRevision++;
      pendingFocus = { owner: member, windowKey: focusWindowKey(state), ticker, requested: false };
    };
  };
  const returnToMap = () => {
    if (pendingFocus) pendingFocus.requested = true;
    flushReturnFocus();
  };
  const applyEntry = () => {
    if (!entry || disposed || !port || !hydrated || appliedOriginGeneration !== originGeneration || current.phase !== "ready" || current.privateState.phase !== "ready" || !current.privateState.document || !owner || owner !== account()) return;
    if (entry.phase === "focusing") {
      const company = current.graph?.companies.find((row) => row.ticker === entry.stock.ticker && row.market === entry.stock.market);
      entry.phase = "done";
      if (company && entry.windowKey === focusWindowKey(current)) port.postMessage({ type: "focus-stock", id: company.id });
      return;
    }
    if (entry.phase !== "waiting" || exploration) return;
    entry.phase = "resolving";
    const version = generation, member = owner, windowKey = focusWindowKey(current);
    const controller = new AbortController();
    entryRequest = controller;
    const isCurrent = () => {
      if (disposed || controller.signal.aborted || version !== generation || member !== owner || member !== account()) return false;
      const state = workspace.getState();
      return state.phase === "ready" && focusWindowKey(state) === windowKey;
    };
    void (async () => {
      let activeExploration = null;
      try {
        let stock = workspaceStocks(workspace.getState()).find((row) => row.ticker === entry.stock.ticker);
        if (!stock) {
          const result = await (options.searchLoader || fetchPortfolioStockSearch)(entry.stock.ticker, { signal: controller.signal });
          if (!isCurrent()) return;
          stock = result.stocks.find((row) => row.ticker === entry.stock.ticker && row.market === entry.stock.market);
        }
        if (!isCurrent() || !stock || stock.market !== entry.stock.market || exploration) return;
        activeExploration = { ticker: stock.ticker, version };
        exploration = activeExploration;
        const success = await workspace.exploreStock(stock);
        if (!success || disposed || controller.signal.aborted || version !== generation || member !== owner || member !== account()) return;
        entry.windowKey = focusWindowKey(workspace.getState());
        entry.phase = "focusing";
        applyEntry();
      } catch {
      } finally {
        if (entry.phase === "resolving") entry.phase = "done";
        if (entryRequest === controller) entryRequest = null;
        if (exploration === activeExploration) exploration = null;
      }
    })();
  };
  const close = () => {
    generation++;
    searchRevision++;
    searchRequest?.abort();
    entryRequest?.abort();
    if (entry && entry.phase !== "waiting") entry.phase = "done";
    searchStocks.clear();
    logoRequest.abort();
    logoRequest = new AbortController();
    requestedLogos.clear();
    exploration = null;
    port?.close();
    port = null;
    waiting = false;
    hydrated = false;
    rejectedDraft = null;
    appliedOriginGeneration = -1;
    displayedWindow = "";
    reloadingWindow = null;
  };
  const status = () => {
    const p = current.privateState;
    const originPending = appliedOriginGeneration !== originGeneration;
    const layoutLimit = !!p.document && p.document.layouts.length >= 3 && !p.document.layouts.some((layout) => layout.map_key === PROTOTYPE_MAP_KEY);
    port?.postMessage({
      type: "status",
      writable: !layoutLimit && (p.phase === "ready" || p.phase === "saving"),
      saving: p.phase === "saving" || originPending,
      dataRefresh: options.enableDataRefresh ? { phase: current.dataRefresh?.phase || "idle", checked: !!current.dataRefresh?.checkedAt } : null,
      message: originPending ? "\uC0C8 \uC790\uB8CC\uC758 \uBC30\uCE58\uB97C \uC801\uC6A9 \uC911\uC774\uC5D0\uC694\u2026" : layoutLimit ? "\uC9C0\uB3C4 \uBC30\uCE58 \uC800\uC7A5 \uC2AC\uB86F\uC774 \uAC00\uB4DD \uCC28 \uBCC0\uACBD\uC744 \uC800\uC7A5\uD560 \uC218 \uC5C6\uC5B4\uC694. \uAE30\uC874 \uAE30\uB85D\uC740 \uC720\uC9C0\uD588\uC5B4\uC694." : rejectedDraft ? `\uBC30\uCE58\xB7\uBA54\uBAA8\uAC00 \uC800\uC7A5 \uBC94\uC704\uB97C \uBC97\uC5B4\uB098 \uC800\uC7A5\uD558\uC9C0 \uC54A\uC558\uC5B4\uC694. \uD604\uC7AC \uD654\uBA74\uC740 \uC720\uC9C0\uD588\uC5B4\uC694. (${rejectedDraft.code}; positions=${rejectedDraft.positions ?? "?"}, notes=${rejectedDraft.notes ?? "?"}, marks=${rejectedDraft.marks ?? "?"})` : p.phase === "loading" ? "\uC800\uC7A5\uB41C \uC885\uBAA9\uACFC \uAE30\uB85D\uC744 \uBD88\uB7EC\uC624\uB294 \uC911\uC774\uC5D0\uC694\u2026" : p.phase === "conflict" ? "\uB2E4\uB978 \uD654\uBA74\uC5D0\uC11C \uAE30\uB85D\uC774 \uBC14\uB00C\uC5C8\uC5B4\uC694. \uB36E\uC5B4\uC4F0\uC9C0 \uC54A\uC558\uC5B4\uC694." : p.phase === "error" ? options.localSession && p.error ? p.error : "\uC800\uC7A5\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694. \uBCC0\uACBD \uB0B4\uC6A9\uC744 \uC720\uC9C0\uD558\uACE0 \uC788\uC5B4\uC694." : p.phase === "saving" ? "\uC800\uC7A5 \uC911\u2026" : p.dirty ? "\uC544\uC9C1 \uC800\uC7A5\uD558\uC9C0 \uC54A\uC740 \uBCC0\uACBD\uC774 \uC788\uC5B4\uC694" : "\uC800\uC7A5\uB41C \uAE30\uB85D\uC744 \uBD88\uB7EC\uC654\uC5B4\uC694"
    });
  };
  const ready = (event) => {
    if (disposed || !waiting || !owner || owner !== account() || current.phase !== "ready" || event.source !== frame.contentWindow || event.origin !== "null" || event.data?.type !== "alphanest-member-ready" || event.data.nonce !== frameNonce) return;
    waiting = false;
    const channel = new MessageChannel(), version = generation, member = owner;
    port = channel.port1;
    port.onmessage = async (event2) => {
      if (disposed || version !== generation || !member || member !== account()) return;
      const state = workspace.getState(), command = event2.data;
      if (!plain(command)) return;
      if (command.type === "intro-preference" && typeof command.hidden === "boolean") {
        introHidden = command.hidden;
        let persisted = true;
        try {
          if (introHidden) window.localStorage.setItem(introStore, "1");
          else window.localStorage.removeItem(introStore);
        } catch {
          persisted = false;
        }
        port?.postMessage({ type: "intro-preference", hidden: introHidden, persisted });
        return;
      }
      if (command.type === "hydrated") {
        if (command.originGeneration !== originGeneration) return;
        appliedOriginGeneration = originGeneration;
        hydrated = true;
        sendLogos(state.graph?.companies || []);
        flushReturnFocus();
        status();
        rememberVisit();
        applyEntry();
        return;
      }
      if (command.type === "graph-applied") {
        if (hydrated && command.originGeneration === originGeneration) {
          appliedOriginGeneration = originGeneration;
          status();
          rememberVisit();
          applyEntry();
        }
        return;
      }
      if (state.phase !== "ready") return;
      if ((command.type === "edit" || command.type === "save") && (!hydrated || appliedOriginGeneration !== originGeneration || command.originGeneration !== originGeneration)) {
        status();
        return;
      }
      if (command.type === "search" && typeof command.query === "string" && command.query.length <= 60 && Number.isSafeInteger(command.request)) {
        searchRequest?.abort();
        searchRequest = new AbortController();
        searchStocks.clear();
        const request = ++searchRevision, signal = searchRequest.signal;
        try {
          const result = await (options.searchLoader || fetchPortfolioStockSearch)(command.query, { signal });
          if (disposed || version !== generation || request !== searchRevision || member !== account() || signal.aborted) return;
          searchStocks = new Map(result.stocks.map((stock) => [stock.ticker, stock]));
          port?.postMessage({
            type: "search-results",
            request: command.request,
            ...result,
            stocks: result.stocks.map((stock) => ({ ...stock, name: portfolioCompanyDisplayName(stock.market, stock.ticker, stock.name) }))
          });
          sendLogos(result.stocks);
        } catch {
          if (!disposed && version === generation && request === searchRevision && member === account() && !signal.aborted)
            port?.postMessage({ type: "search-results", request: command.request, error: "\uAC80\uC0C9 \uC790\uB8CC\uB97C \uBD88\uB7EC\uC624\uC9C0 \uBABB\uD588\uC5B4\uC694. \uB2E4\uC2DC \uC785\uB825\uD574 \uC8FC\uC138\uC694." });
        }
      } else if (command.type === "explore" && typeof command.ticker === "string" && !exploration) {
        const stock = searchStocks.get(command.ticker);
        if (!stock) {
          port?.postMessage({ type: "explore-result", error: "\uAC80\uC0C9 \uACB0\uACFC\uAC00 \uBC14\uB00C\uC5C8\uC5B4\uC694. \uB2E4\uC2DC \uAC80\uC0C9\uD574 \uC8FC\uC138\uC694." });
          return;
        }
        exploration = { ticker: stock.ticker, version };
        try {
          const success = await workspace.exploreStock(stock);
          if (!disposed && version === generation && member === account())
            port?.postMessage({ type: "explore-result", ...success ? {} : { error: "\uCD94\uAC00\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694. \uAE30\uC874 \uC9C0\uB3C4\uB294 \uC720\uC9C0\uD588\uC5B4\uC694." } });
        } catch (error) {
          if (!disposed && version === generation && member === account()) port?.postMessage({ type: "explore-result", error: error instanceof Error && error.message.includes("30") ? "\uD55C \uD654\uBA74\uC5D0\uB294 30\uC885\uBAA9\uAE4C\uC9C0 \uD45C\uC2DC\uD560 \uC218 \uC788\uC5B4\uC694." : "\uCD94\uAC00\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694. \uAE30\uC874 \uC9C0\uB3C4\uB294 \uC720\uC9C0\uD588\uC5B4\uC694." });
        } finally {
          if (exploration?.version === version) exploration = null;
        }
      } else if (command.type === "edit") {
        rejectedDraft = null;
        const next = mergePrototypeDraft(state, command.draft, (reason) => {
          rejectedDraft = reason;
        });
        const hidden = command.draft?.hiddenStockIds;
        const allowed = new Set(state.graph?.companies.map((row) => "company:" + row.ticker));
        const validView = !options.localView || Array.isArray(hidden) && hidden.length <= 30 && new Set(hidden).size === hidden.length && hidden.every((id) => typeof id === "string" && allowed.has(id));
        if (next && !validView) rejectedDraft = prototypeDraftRejection(command.draft, "local_view");
        if (next && validView) {
          if (workspace.editLayout(next.map_key, () => next) === false) rejectedDraft = prototypeDraftRejection(next, "workspace_rejected");
          if (!rejectedDraft) options.localView?.setHiddenStockIds([...hidden]);
        }
        if (rejectedDraft) status();
      } else if (command.type === "save") {
        if (Object.hasOwn(command, "origins")) {
          rejectedDraft = null;
          const next = mergePrototypeOriginSave(state, command.draft, command.origins, (reason) => {
            rejectedDraft = reason;
          });
          const hidden = command.draft?.hiddenStockIds;
          const allowed = new Set(state.graph?.companies.map((row) => "company:" + row.ticker));
          const validView = !options.localView || Array.isArray(hidden) && hidden.length <= 30 && new Set(hidden).size === hidden.length && hidden.every((id) => typeof id === "string" && allowed.has(id));
          if (next && !validView) rejectedDraft = prototypeDraftRejection(command.draft, "local_view");
          if (next && validView) {
            if (workspace.editLayout(next.map_key, () => next) === false) rejectedDraft = prototypeDraftRejection(next, "workspace_rejected");
            if (!rejectedDraft) options.localView?.setHiddenStockIds([...hidden]);
          }
          if (!next || rejectedDraft) {
            status();
            return;
          }
        }
        if (rejectedDraft || state.privateState.document?.layouts.length === 3 && !state.privateState.document.layouts.some((layout) => layout.map_key === PROTOTYPE_MAP_KEY)) status();
        else await workspace.save();
      } else if (command.type === "refresh-data" && options.enableDataRefresh && !exploration) {
        await workspace.refreshData();
      } else if (command.type === "apply-data" && options.enableDataRefresh && !exploration && !rejectedDraft) {
        workspace.applyDataUpdate();
      } else if (command.type === "holdings") {
        if (options.showStockList) port?.postMessage({ type: "stock-list" });
        else options.openHoldings?.();
      } else if (command.type === "source" && typeof command.url === "string") {
        const reviewed = projectReviewedPrototype(state);
        const urls = /* @__PURE__ */ new Set([
          ...state.graph?.documents.flatMap((d) => [d.url, ...d.evidence.flatMap((e) => [e.url, ...e.sources.map((s) => s.url)])]) || [],
          ...state.graph?.companies.flatMap((c) => (c.sections || []).flatMap((s) => s.items.flatMap((i) => [i.url, ...(i.sources || []).map((source) => source.url)]))) || [],
          ...Object.values(reviewed.recordsMap).flatMap((record8) => record8.sourceURLs),
          ...Object.values(projectAutomaticPrototype(state.graph).recordsMap).flatMap((record8) => record8.sourceURLs),
          ...Object.values(projectMarketPrototype(state.graph).recordsMap).flatMap((record8) => record8.sourceURLs),
          ...Object.values(projectContractPrototype(state.graph).recordsMap).flatMap((record8) => record8.sourceURLs)
        ]);
        try {
          const url = new URL(command.url);
          if (url.protocol === "https:" && !url.username && !url.password && urls.has(url.href)) options.openSource?.(url.href);
        } catch {
        }
      }
    };
    frame.contentWindow.postMessage({ type: "alphanest-member-connect", nonce: frameNonce }, "*", [channel.port2]);
    port.postMessage({ type: "init", model: { ...model(current), introHidden } });
    status();
    frame.style.opacity = "1";
    frame.removeAttribute("aria-hidden");
    frame.removeAttribute("inert");
  };
  window.addEventListener("message", ready);
  const loaded = () => {
    if (!disposed && waiting) frame.contentWindow?.postMessage({ type: "alphanest-member-start", nonce: frameNonce }, "*");
  };
  frame.addEventListener("load", loaded);
  frame.setAttribute("sandbox", "allow-scripts");
  frame.setAttribute("referrerpolicy", "no-referrer");
  const unsubscribe = workspace.subscribe((state) => {
    const previous = current;
    current = state;
    const nextOwner = account();
    if (owner !== nextOwner || state.phase === "signed-out") clearReturnFocus();
    else if (pendingFocus && (state.phase !== "ready" || focusWindowKey(state) !== pendingFocus.windowKey)) pendingFocus = null;
    if (state.phase === "loading" && nextOwner && owner === nextOwner && key) {
      if (hydrated && reloadingWindow === null) reloadingWindow = displayedWindow;
      port?.postMessage({ type: "status", writable: false, saving: false, message: "\uBCF4\uC720\uC885\uBAA9\uACFC \uC790\uB8CC\uB97C \uAC31\uC2E0 \uC911\uC774\uC5D0\uC694" });
      return;
    }
    if (state.phase !== "ready" || !state.graph || !nextOwner) {
      frame.style.opacity = "0";
      frame.setAttribute("aria-hidden", "true");
      frame.setAttribute("inert", "");
      port?.postMessage({ type: "reset" });
      close();
      key = "";
      reloadPending = false;
      owner = nextOwner;
      return;
    }
    if (state.privateState.phase === "loading") reloadPending = true;
    if (reloadPending && state.privateState.phase === "ready" && !state.privateState.dirty) {
      key = "";
      reloadPending = false;
    }
    const nextKey = JSON.stringify([nextOwner, state.graph, workspaceStocks(state), !!state.privateState.document]);
    const sameWindowReload = reloadingWindow !== null && reloadingWindow === focusWindowKey(state);
    reloadingWindow = null;
    if (nextKey !== key) {
      if (sameWindowReload && owner === nextOwner && port && hydrated && key) {
        key = nextKey;
        displayedWindow = focusWindowKey(state);
        port.postMessage({ type: "graph-update", model: model(state) });
        sendLogos(state.graph.companies);
        status();
        return;
      }
      if (previous.dataRefresh?.phase === "available" && state.dataRefresh?.phase === "idle" && owner === nextOwner && port && hydrated && focusWindowKey(previous) === focusWindowKey(state)) {
        key = nextKey;
        displayedWindow = focusWindowKey(state);
        port.postMessage({ type: "graph-update", model: model(state) });
        sendLogos(state.graph.companies);
        status();
        return;
      }
      if (exploration?.version === generation && owner === nextOwner && port && hydrated && state.selectedTickers.includes(exploration.ticker)) {
        key = nextKey;
        displayedWindow = focusWindowKey(state);
        port.postMessage({ type: "graph-update", model: model(state), ticker: exploration.ticker });
        sendLogos(state.graph.companies);
        status();
        return;
      }
      close();
      owner = nextOwner;
      key = nextKey;
      waiting = true;
      displayedWindow = focusWindowKey(state);
      frameNonce = "an-member-" + crypto.randomUUID();
      if (templateURL) {
        const url = new URL(templateURL);
        url.searchParams.set("__an_frame", frameNonce);
        url.hash = frameNonce;
        frame.src = url.href;
      } else frame.srcdoc = template.replace("'__ALPHANEST_FRAME_NONCE__'", JSON.stringify(frameNonce));
    } else {
      status();
      if (waiting) loaded();
      applyEntry();
    }
  });
  const cleanup = () => {
    const retiredSource = templateURL ? frame.src : frame.srcdoc;
    frame.style.opacity = "0";
    frame.setAttribute("aria-hidden", "true");
    frame.setAttribute("inert", "");
    disposed = true;
    clearReturnFocus();
    close();
    unsubscribe();
    window.removeEventListener("message", ready);
    frame.removeEventListener("load", loaded);
    Promise.resolve().then(() => {
      if ((templateURL ? frame.src : frame.srcdoc) !== retiredSource) return;
      if (templateURL) frame.src = "about:blank";
      else frame.srcdoc = "";
    });
  };
  return Object.assign(cleanup, { prepareReturnFocus, clearReturnFocus, returnToMap });
}
var BF_MAP_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/logo_map.json";
var PNG_PREFIX = "https://static.toss.im/png-icons/securities/icn-sec-fill-";
var MANIFEST_MAX_BYTES = 2 * 1024 * 1024;
var LOGO_MAX_BYTES = 128 * 1024;
var DEFAULT_TIMEOUT_MS = 8e3;
var MAX_CACHE_ENTRIES = 256;
function validIdentity(stock) {
  if (!stock || typeof stock.ticker !== "string" || typeof stock.market !== "string") return false;
  if (stock.market === "KR") return /^[0-9]{6}$/.test(stock.ticker);
  if (stock.market === "US") return /^[A-Z][A-Z0-9]{0,9}(?:[.-][A-Z0-9]{1,2})?$/.test(stock.ticker);
  return false;
}
function hasDuplicateKeys(source) {
  const objects = [];
  for (let i = 0; i < source.length; i++) {
    const char = source[i];
    if (char === '"') {
      const start = i;
      i++;
      while (i < source.length) {
        if (source[i] === "\\") {
          i += 2;
          continue;
        }
        if (source[i] === '"') break;
        i++;
      }
      if (i >= source.length) return false;
      let next = i + 1;
      while (next < source.length && /\s/.test(source[next])) next++;
      if (source[next] === ":") {
        const owner = objects[objects.length - 1];
        if (!owner) return true;
        const key = JSON.parse(source.slice(start, i + 1));
        if (owner.has(key)) return true;
        owner.add(key);
      }
    } else if (char === "{") objects.push(/* @__PURE__ */ new Set());
    else if (char === "}") {
      if (!objects.length) return true;
      objects.pop();
    }
  }
  return objects.length !== 0;
}
function parseManifest(bytes) {
  try {
    const text13 = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    if (hasDuplicateKeys(text13)) return null;
    const value = JSON.parse(text13);
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    const logos = value.logos;
    if (!logos || typeof logos !== "object" || Array.isArray(logos)) return null;
    return logos;
  } catch {
    return null;
  }
}
function publicGetInit(signal) {
  return {
    method: "GET",
    credentials: "omit",
    referrerPolicy: "no-referrer",
    redirect: "error",
    cache: "no-store",
    signal
  };
}
async function fetchManifest(fetcher, timeoutMs) {
  const controller = new AbortController();
  let stop;
  const stopped = new Promise((resolve) => {
    stop = () => resolve(null);
  });
  const timer = setTimeout(() => {
    controller.abort();
    stop();
  }, timeoutMs);
  const work = async () => {
    try {
      const response = await fetcher(BF_MAP_URL, publicGetInit(controller.signal));
      const bytes = await readBounded(response, MANIFEST_MAX_BYTES, "application/json", BF_MAP_URL);
      return bytes ? parseManifest(bytes) : null;
    } catch {
      return null;
    }
  };
  try {
    return await Promise.race([work(), stopped]);
  } finally {
    clearTimeout(timer);
  }
}
function validPng(bytes) {
  return bytes.length >= 45 && bytes[0] === 137 && bytes[1] === 80 && bytes[2] === 78 && bytes[3] === 71 && bytes[4] === 13 && bytes[5] === 10 && bytes[6] === 26 && bytes[7] === 10 && bytes[8] === 0 && bytes[9] === 0 && bytes[10] === 0 && bytes[11] === 13 && bytes[12] === 73 && bytes[13] === 72 && bytes[14] === 68 && bytes[15] === 82 && new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).getUint32(16) > 0 && new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).getUint32(16) <= 1024 && new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).getUint32(20) > 0 && new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).getUint32(20) <= 1024 && bytes[bytes.length - 12] === 0 && bytes[bytes.length - 11] === 0 && bytes[bytes.length - 10] === 0 && bytes[bytes.length - 9] === 0 && bytes[bytes.length - 8] === 73 && bytes[bytes.length - 7] === 69 && bytes[bytes.length - 6] === 78 && bytes[bytes.length - 5] === 68;
}
function toDataUrl(bytes) {
  if (typeof globalThis.btoa !== "function") return null;
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 8192) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
  }
  return `data:image/png;base64,${globalThis.btoa(binary)}`;
}
function contentLengthAllowed(response, limit) {
  const value = response.headers.get("Content-Length");
  return value === null || /^[0-9]+$/.test(value) && Number(value) <= limit;
}
async function readBounded(response, limit, contentType, expectedUrl) {
  if (!response.ok || response.status !== 200 || response.url && response.url !== expectedUrl || response.headers.get("Content-Type")?.split(";", 1)[0].trim().toLowerCase() !== contentType || !contentLengthAllowed(response, limit) || !response.body) return null;
  const reader = response.body.getReader();
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit) {
        await reader.cancel().catch(() => {
        });
        return null;
      }
      chunks.push(value);
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
    }
  }
  const output = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    output.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return output;
}
function createPortfolioPublicLogoLoader(options = {}) {
  const fetcher = options.fetcher || globalThis.fetch.bind(globalThis);
  const timeoutMs = Number.isFinite(options.timeoutMs) && options.timeoutMs > 0 ? Math.min(options.timeoutMs, 3e4) : DEFAULT_TIMEOUT_MS;
  const cache = /* @__PURE__ */ new Map();
  let manifest = null;
  let manifestRequest = null;
  const getManifest = () => {
    if (manifest) return Promise.resolve(manifest);
    if (manifestRequest) return manifestRequest;
    let pending;
    pending = fetchManifest(fetcher, timeoutMs).then((value) => {
      if (value) manifest = value;
      return value;
    }).finally(() => {
      if (manifestRequest === pending) manifestRequest = null;
    });
    manifestRequest = pending;
    return pending;
  };
  return async (stock, { signal }) => {
    if (!validIdentity(stock) || !signal || signal.aborted) return null;
    const identity2 = `${stock.market}:${stock.ticker}`;
    const cached = cache.get(identity2);
    if (cached) {
      cache.delete(identity2);
      cache.set(identity2, cached);
      return cached;
    }
    const controller = new AbortController();
    let stop;
    const stopped = new Promise((resolve) => {
      stop = () => resolve(null);
    });
    const abort = () => {
      controller.abort();
      stop();
    };
    const timer = setTimeout(abort, timeoutMs);
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
    const request = (url) => fetcher(url, publicGetInit(controller.signal));
    const work = async () => {
      try {
        const logos = await getManifest();
        if (!logos || controller.signal.aborted) return null;
        const expectedUrl = `${PNG_PREFIX}${stock.ticker}.png`;
        if (Object.prototype.hasOwnProperty.call(logos, stock.ticker) && logos[stock.ticker] !== expectedUrl) return null;
        const response = await request(expectedUrl);
        const bytes = await readBounded(response, LOGO_MAX_BYTES, "image/png", expectedUrl);
        if (controller.signal.aborted) return null;
        return bytes && validPng(bytes) ? toDataUrl(bytes) : null;
      } catch {
        return null;
      }
    };
    try {
      const value = await Promise.race([work(), stopped]);
      if (value) {
        cache.set(identity2, value);
        if (cache.size > MAX_CACHE_ENTRIES) cache.delete(cache.keys().next().value);
      }
      return value;
    } finally {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
    }
  };
}
var tickerFor = (value, market2) => {
  if (typeof value !== "string") throw new Error("invalid-ticker");
  const ticker = value.trim().toUpperCase();
  const pattern = market2 === "kr" ? /^[0-9A-Z]{6}$/ : /^[A-Z][A-Z0-9.-]{0,14}$/;
  if (!pattern.test(ticker) || ticker.startsWith("CMD_")) throw new Error("invalid-ticker");
  return ticker;
};
var apiMarketFor = (value) => {
  if (typeof value !== "string") throw new Error("invalid-market");
  const market2 = value.trim().toLowerCase();
  if (market2 !== "kr" && market2 !== "us") throw new Error("invalid-market");
  return market2;
};
var holdingMarketFor = (market2) => market2 === "kr" ? "KR" : "US";
var identifierFor = (value) => {
  if (typeof value !== "string" || !value.trim()) throw new Error("missing-holding-id");
  return value.trim();
};
var positiveNumber = (value, field3) => {
  if (typeof value === "boolean") throw new Error(`invalid-${field3}`);
  if (typeof value === "string") {
    const text13 = value.replace(/[,\s₩$원]/g, "");
    if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(text13)) throw new Error(`invalid-${field3}`);
    value = Number(text13);
  }
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) throw new Error(`invalid-${field3}`);
  return value;
};
var textField = (value, field3) => {
  if (typeof value !== "string") throw new Error(`invalid-${field3}`);
  return value;
};
var copy2 = (record8) => ({ ...record8 });
function targetById(records, id) {
  const matches = records.filter((record8) => record8.id === id);
  if (!matches.length) throw new Error("holding-not-found");
  if (matches.length !== 1) throw new Error("duplicate-holding-id");
  if (matches[0].duplicate === true) throw new Error("duplicate-holding-record");
  return matches[0];
}
function previewHoldingChange(records, change) {
  if (change.kind === "add") return previewAdd(records, change);
  if (change.kind !== "edit" && change.kind !== "remove") throw new Error("invalid-holding-change");
  const id = identifierFor(change.id), before = targetById(records, id);
  if (change.kind === "remove") return {
    kind: "remove",
    id,
    before: copy2(before),
    after: null,
    changedFields: [],
    request: { method: "DELETE", body: { id } }
  };
  const after = { ...copy2(before), id };
  const changedFields = [];
  const body = { id };
  if (change.shares !== void 0) {
    after.shares = positiveNumber(change.shares, "shares");
    body.shares = after.shares;
    changedFields.push("shares");
  }
  if (change.avg_cost !== void 0) {
    after.avg_cost = positiveNumber(change.avg_cost, "avg_cost");
    body.avg_cost = after.avg_cost;
    changedFields.push("avg_cost");
  }
  if (change.name !== void 0) {
    after.name = textField(change.name, "name");
    body.name = after.name;
    changedFields.push("name");
  }
  if (change.memo !== void 0) {
    after.memo = textField(change.memo, "memo");
    body.memo = after.memo;
    changedFields.push("memo");
  }
  if (!changedFields.length) throw new Error("no-holding-changes");
  return { kind: "edit", id, before: copy2(before), after, changedFields, request: { method: "PATCH", body } };
}
function previewAdd(records, change) {
  const apiMarket = apiMarketFor(change.market), market2 = holdingMarketFor(apiMarket), ticker = tickerFor(change.ticker, apiMarket);
  const sameTicker = records.filter((record8) => record8.ticker.trim().toUpperCase() === ticker);
  if (sameTicker.some((record8) => record8.duplicate === true)) throw new Error("duplicate-holding-record");
  if (sameTicker.length) {
    throw new Error("holding-ticker-requires-edit");
  }
  const shares = positiveNumber(change.shares, "shares"), avg_cost = positiveNumber(change.avg_cost, "avg_cost");
  const name = change.name === void 0 ? "" : textField(change.name, "name");
  const memo = change.memo === void 0 ? "" : textField(change.memo, "memo");
  const after = { id: null, ticker, market: market2, shares, avg_cost, name, memo };
  return {
    kind: "add",
    id: null,
    before: null,
    after,
    changedFields: ["ticker", "name", "market", "shares", "avg_cost", "memo"],
    request: { method: "POST", body: { ticker, market: apiMarket, shares, avg_cost, name, memo } }
  };
}
var quantity = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 8 });
var won = new Intl.NumberFormat("ko-KR", { style: "currency", currency: "KRW", maximumFractionDigits: 0 });
var dollar = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 4 });
function formatHoldingQuantity(value) {
  if (value === null) return "\uD655\uC778 \uD544\uC694";
  return value < 1e-8 ? "0.00000001 \uBBF8\uB9CC" : quantity.format(value);
}
function formatHoldingAverageCost(holding) {
  if (holding.duplicate) return "\uC911\uBCF5 \uD589 \uD655\uC778 \uD544\uC694";
  if (holding.avg_cost === null) return "\uD655\uC778 \uD544\uC694";
  if (holding.market === "KR" && holding.avg_cost < 1) return "1 KRW \uBBF8\uB9CC";
  if (holding.market === "US" && holding.avg_cost < 1e-4) return "0.0001 USD \uBBF8\uB9CC";
  return holding.market === "KR" ? `${won.format(holding.avg_cost)} KRW` : `${dollar.format(holding.avg_cost)} USD`;
}
var HOLDINGS_CSV_LIMITS = Object.freeze({ maxCharacters: 262144, maxRows: 200 });
var ALIASES = {
  ticker: ["ticker", "code", "symbol", "stockcode", "\uC885\uBAA9\uCF54\uB4DC", "\uD2F0\uCEE4"],
  market: ["market", "\uC2DC\uC7A5"],
  shares: ["shares", "quantity", "qty", "\uC218\uB7C9", "\uBCF4\uC720\uC218\uB7C9"],
  avg_cost: ["avgcost", "averagecost", "\uD3C9\uB2E8", "\uD3C9\uB2E8\uAC00", "\uD3C9\uADE0\uB9E4\uC218\uAC00", "\uD3C9\uADE0\uB9E4\uC785\uAC00"],
  name: ["name", "stockname", "\uC885\uBAA9\uBA85", "\uC774\uB984"],
  memo: ["memo", "note", "\uBA54\uBAA8"],
  currency: ["currency", "\uD1B5\uD654"]
};
var columnFor = (value) => {
  const normalized = value.trim().toLowerCase().replace(/[\s_-]/g, "");
  return Object.keys(ALIASES).find((key) => ALIASES[key].includes(normalized));
};
function parse(text13) {
  if (text13.length > HOLDINGS_CSV_LIMITS.maxCharacters) return { rows: [], errors: [{ rowNumber: 1, code: "csv-input-too-large" }] };
  text13 = text13.replace(/^\uFEFF/, "");
  const rows2 = [];
  let line = 1, startLine = 1, cells = [], field3 = "", errors = [];
  let quoted = false, closed = false, touched = false;
  const issue2 = (code) => {
    if (!errors.includes(code)) errors.push(code);
  };
  const endField = () => {
    cells.push(field3);
    field3 = "";
    closed = false;
  };
  const endRow = () => {
    endField();
    rows2.push({ line: startLine, cells, errors });
    cells = [];
    errors = [];
    touched = false;
  };
  for (let i = 0; i < text13.length; i++) {
    const char = text13[i];
    if (char === "\0" || char === "\uFFFD") issue2("csv-invalid-text");
    if (quoted) {
      if (char === '"') {
        if (text13[i + 1] === '"') {
          field3 += '"';
          i++;
        } else {
          quoted = false;
          closed = true;
        }
      } else {
        field3 += char;
        if (char === "\n" || char === "\r" && text13[i + 1] !== "\n") line++;
      }
      continue;
    }
    if (char === "\r" || char === "\n") {
      endRow();
      if (rows2.length > HOLDINGS_CSV_LIMITS.maxRows + 1) return { rows: [], errors: [{ rowNumber: startLine, code: "csv-too-many-rows" }] };
      if (char === "\r" && text13[i + 1] === "\n") i++;
      startLine = ++line;
      continue;
    }
    touched = true;
    if (char === ",") {
      endField();
      continue;
    }
    if (char === '"' && !field3 && !closed) {
      quoted = true;
      continue;
    }
    if (closed || char === '"') issue2("csv-invalid-quote");
    field3 += char;
  }
  if (quoted) issue2("csv-unclosed-quote");
  if (touched || cells.length || field3.length) endRow();
  if (rows2.length > HOLDINGS_CSV_LIMITS.maxRows + 1) return { rows: [], errors: [{ rowNumber: startLine, code: "csv-too-many-rows" }] };
  return { rows: rows2, errors: [] };
}
function buildHoldingCsvPreview(text13, memberHoldings) {
  const parsed = parse(text13), errors = parsed.errors.slice();
  const header = parsed.rows[0];
  const columns = header?.cells.map(columnFor) || [];
  if (!header && !errors.length) errors.push({ rowNumber: 1, code: "csv-missing-header" });
  else if (header) {
    errors.push(...header.errors.map((code) => ({ rowNumber: header.line, code })));
    if (columns.some((column) => !column)) errors.push({ rowNumber: header.line, code: "csv-unknown-header" });
    if (new Set(columns).size !== columns.length) errors.push({ rowNumber: header.line, code: "csv-duplicate-header" });
    for (const required of ["ticker", "market", "shares", "avg_cost"]) {
      if (!columns.includes(required)) errors.push({ rowNumber: header.line, code: `csv-missing-${required}-header` });
    }
  }
  const existingTickers = new Set(memberHoldings.map((record8) => record8.ticker.trim().toUpperCase()));
  const rows2 = parsed.rows.slice(1).map((row5) => ({ rowNumber: row5.line, cells: row5.cells, errors: row5.errors.slice(), ticker: null, kind: "error", preview: null }));
  if (header && !rows2.length && !errors.length) errors.push({ rowNumber: header.line + 1, code: "csv-no-data" });
  const tickerIndex = columns.indexOf("ticker");
  const occurrences = /* @__PURE__ */ new Map();
  for (const row5 of rows2) {
    row5.ticker = tickerIndex >= 0 ? row5.cells[tickerIndex]?.trim().toUpperCase() || null : null;
    if (row5.ticker) occurrences.set(row5.ticker, (occurrences.get(row5.ticker) || 0) + 1);
  }
  for (const row5 of rows2) {
    if (errors.length) row5.errors.push("csv-invalid-file");
    if (row5.cells.length !== columns.length) row5.errors.push("csv-column-count");
    if (row5.ticker && (occurrences.get(row5.ticker) || 0) > 1) row5.errors.push("csv-duplicate-ticker");
    if (row5.errors.length) continue;
    const input = {};
    columns.forEach((column, index) => {
      if (column) input[column] = row5.cells[index];
    });
    try {
      const candidate = previewHoldingChange([], {
        kind: "add",
        ticker: input.ticker,
        market: input.market,
        shares: input.shares,
        avg_cost: input.avg_cost,
        name: input.name,
        memo: input.memo
      });
      const after = candidate.after;
      if (input.currency !== void 0 && input.currency.trim().toUpperCase() !== (after.market === "KR" ? "KRW" : "USD")) {
        throw new Error("csv-currency-mismatch");
      }
      const matches = memberHoldings.filter((record8) => record8.ticker.trim().toUpperCase() === after.ticker);
      if (!matches.length) {
        row5.kind = "add";
        row5.preview = candidate;
        continue;
      }
      const before = matches[0];
      if (matches.length !== 1 || before.duplicate || !before.id?.trim() || before.id !== before.id.trim() || memberHoldings.filter((record8) => record8.id === before.id).length !== 1) throw new Error("csv-ambiguous-existing-identity");
      if (before.market !== after.market) throw new Error("csv-existing-market-conflict");
      const change = { kind: "edit", id: before.id };
      if (before.shares !== after.shares) change.shares = after.shares;
      if (before.avg_cost !== after.avg_cost) change.avg_cost = after.avg_cost;
      if (input.name !== void 0 && before.name !== after.name) change.name = after.name;
      if (input.memo !== void 0 && (before.memo ?? "") !== after.memo) change.memo = after.memo;
      if (Object.keys(change).length === 2) {
        row5.kind = "unchanged";
        continue;
      }
      row5.preview = previewHoldingChange(memberHoldings, change);
      row5.kind = "edit";
    } catch (error) {
      row5.errors.push(error instanceof Error ? error.message : "csv-invalid-row");
    }
  }
  const additions = rows2.filter((row5) => row5.kind === "add");
  const projectedUnique = existingTickers.size + additions.length;
  const counts = { add: 0, edit: 0, unchanged: 0, error: 0, existingUnique: existingTickers.size, projectedUnique };
  for (const row5 of rows2) counts[row5.kind]++;
  if (errors.length || counts.error) for (const row5 of rows2) row5.preview = null;
  return {
    rows: rows2,
    fatalErrors: errors,
    counts,
    requiresConfirmation: true,
    readyForConfirmation: !errors.length && !counts.error && counts.add + counts.edit > 0
  };
}
var fields2 = { ticker: "\uC885\uBAA9\uCF54\uB4DC", market: "\uC2DC\uC7A5", name: "\uC774\uB984", shares: "\uC218\uB7C9", avg_cost: "\uD3C9\uADE0 \uB9E4\uC218\uAC00", memo: "\uBA54\uBAA8" };
function issue(code) {
  if (/duplicate-ticker/.test(code)) return "\uD30C\uC77C \uC548\uC5D0 \uAC19\uC740 \uC885\uBAA9\uC774 \uB450 \uBC88 \uC788\uC5B4\uC694. \uD55C \uD589\uC73C\uB85C \uC815\uB9AC\uD574\uC8FC\uC138\uC694.";
  if (/ambiguous|duplicate-holding/.test(code)) return "\uAE30\uC874 \uBCF4\uC720 \uAE30\uB85D\uC744 \uD558\uB098\uB85C \uAD6C\uBD84\uD560 \uC218 \uC5C6\uC5B4\uC694. \uBAA9\uB85D\uC744 \uBA3C\uC800 \uD655\uC778\uD574\uC8FC\uC138\uC694.";
  if (/member-limit/.test(code)) return "\uAE30\uC874 \uBCF4\uC720\uC640 \uD569\uCCD0 30\uC885\uBAA9\uC744 \uB118\uC5B4\uC694. \uCD94\uAC00\uD560 \uC885\uBAA9\uC744 \uC904\uC5EC\uC8FC\uC138\uC694.";
  if (/currency|market/.test(code)) return "\uC2DC\uC7A5\uC740 KR \uB610\uB294 US, \uD1B5\uD654\uB294 \uAC01\uAC01 KRW \uB610\uB294 USD\uC778\uC9C0 \uD655\uC778\uD574\uC8FC\uC138\uC694.";
  if (/shares|avg_cost/.test(code) && !/header/.test(code)) return "\uC218\uB7C9\xB7\uD3C9\uADE0 \uB9E4\uC218\uAC00\uB97C 0\uBCF4\uB2E4 \uD070 \uC22B\uC790\uB85C \uC785\uB825\uD574\uC8FC\uC138\uC694.";
  if (/ticker/.test(code) && !/header/.test(code)) return "\uC885\uBAA9\uCF54\uB4DC\uB97C \uD655\uC778\uD574\uC8FC\uC138\uC694. \uAD6D\uB0B4 \uCF54\uB4DC\uB294 \uC55E\uC790\uB9AC 0\uAE4C\uC9C0 6\uC790\uB9AC\uB85C \uC801\uC5B4\uC8FC\uC138\uC694.";
  if (/header/.test(code)) return "\uCCAB \uC904\uC758 \uD56D\uBAA9 \uC774\uB984\uC744 \uC544\uB798 \uC608\uC2DC\uC640 \uB9DE\uCDB0\uC8FC\uC138\uC694. \uC2DC\uC7A5\xB7\uC885\uBAA9\uCF54\uB4DC\xB7\uC218\uB7C9\xB7\uD3C9\uADE0 \uB9E4\uC218\uAC00\uB294 \uD544\uC218\uC608\uC694.";
  if (/too-large|too-many/.test(code)) return "\uD30C\uC77C\uC774 \uB108\uBB34 \uCEE4\uC694. 200\uD589 \uC774\uD558\uC758 \uD544\uC694\uD55C \uBCF4\uC720 \uAE30\uB85D\uB9CC \uB123\uC5B4\uC8FC\uC138\uC694.";
  if (/no-data/.test(code)) return "\uD56D\uBAA9 \uC774\uB984 \uC544\uB798\uC5D0 \uBCF4\uC720 \uAE30\uB85D\uC744 \uB123\uC5B4\uC8FC\uC138\uC694.";
  if (/quote|column-count/.test(code)) return "\uC27C\uD45C\xB7\uB530\uC634\uD45C\uC640 \uAC01 \uD589\uC758 \uD56D\uBAA9 \uC218\uB97C \uD655\uC778\uD574\uC8FC\uC138\uC694.";
  return "\uD30C\uC77C \uB0B4\uC6A9\uC744 \uC77D\uC744 \uC218 \uC5C6\uC5B4\uC694. UTF-8 CSV\uB85C \uC800\uC7A5\uD574 \uB2E4\uC2DC \uC120\uD0DD\uD574\uC8FC\uC138\uC694.";
}
function PortfolioHoldingsCsvPanel({ holdings, unsupportedCount, busy, onBusy, onClose, onConfirm }) {
  const [text13, setText] = React2.useState(null);
  const [error, setError] = React2.useState("");
  const [result, setResult] = React2.useState(null);
  const [submitted, setSubmitted] = React2.useState(null);
  const generation = React2.useRef(0);
  React2.useEffect(() => () => {
    generation.current++;
  }, []);
  const computed = React2.useMemo(() => text13 === null ? null : buildHoldingCsvPreview(text13, holdings), [text13, holdings]);
  const report = submitted || computed;
  const load = async (file) => {
    const current = ++generation.current;
    setText(null);
    setError("");
    setResult(null);
    setSubmitted(null);
    if (!file) return;
    onBusy(true);
    try {
      if (file.size > HOLDINGS_CSV_LIMITS.maxCharacters * 3) throw Error("csv-input-too-large");
      const content = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer());
      if (generation.current === current) setText(content);
    } catch (failure2) {
      if (generation.current === current) setError(issue(failure2 instanceof Error ? failure2.message : "csv-invalid-text"));
    } finally {
      if (generation.current === current) onBusy(false);
    }
  };
  const confirm = async () => {
    if (!report?.readyForConfirmation || busy || submitted || unsupportedCount) return;
    const current = generation.current;
    const previews = report.rows.flatMap((row5) => row5.preview ? [row5.preview] : []);
    setSubmitted(report);
    setError("");
    onBusy(true);
    try {
      const value = await onConfirm(previews);
      if (generation.current === current) setResult(value);
    } catch {
      if (generation.current === current) setError("\uC800\uC7A5 \uACB0\uACFC\uB97C \uD655\uC815\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694. \uB2E4\uC2DC \uC800\uC7A5\uD558\uC9C0 \uB9D0\uACE0 \uBAA9\uB85D\uC744 \uB2E4\uC2DC \uBD88\uB7EC\uC640 \uD655\uC778\uD574\uC8FC\uC138\uC694.");
    } finally {
      if (generation.current === current) onBusy(false);
    }
  };
  return /* @__PURE__ */ React2.createElement("section", { className: "an-nest-preview", "aria-label": "CSV \uBCF4\uC720 \uAE30\uB85D \uAC00\uC838\uC624\uAE30", style: { marginTop: 16 } }, /* @__PURE__ */ React2.createElement("h3", null, "\uD30C\uC77C\uB85C \uD55C \uBC88\uC5D0 \uB123\uAE30"), /* @__PURE__ */ React2.createElement("p", null, "\uC5D1\uC140\uC5D0\uC11C UTF-8 CSV\uB85C \uC800\uC7A5\uD574\uC8FC\uC138\uC694. \uD30C\uC77C\uC740 \uC774 \uBE0C\uB77C\uC6B0\uC800\uC5D0\uC11C\uB9CC \uC77D\uC73C\uBA70 \uC6D0\uBCF8\uC744 \uC11C\uBC84\uC5D0 \uBCF4\uB0B4\uC9C0 \uC54A\uC544\uC694."), /* @__PURE__ */ React2.createElement("p", null, "\uD604\uC7AC \uBCF4\uC720 \uC218\uB7C9\uC73C\uB85C \uBC14\uAFD4\uC694. \uAE30\uC874 \uC218\uB7C9\uC5D0 \uB354\uD558\uAC70\uB098 \uAC70\uB798 \uAE30\uB85D\uC73C\uB85C \uB4F1\uB85D\uD558\uC9C0 \uC54A\uC544\uC694. \uD30C\uC77C\uC5D0 \uC5C6\uB294 \uC885\uBAA9\uC740 \uADF8\uB300\uB85C \uC720\uC9C0\uD574\uC694."), /* @__PURE__ */ React2.createElement("details", null, /* @__PURE__ */ React2.createElement("summary", null, "\uD30C\uC77C \uD615\uC2DD\uACFC \uC608\uC2DC"), /* @__PURE__ */ React2.createElement("pre", { style: { whiteSpace: "pre-wrap", overflowWrap: "anywhere", font: "inherit" } }, "\uC2DC\uC7A5,\uC885\uBAA9\uCF54\uB4DC,\uC218\uB7C9,\uD3C9\uADE0 \uB9E4\uC218\uAC00,\uC774\uB984,\uBA54\uBAA8", "\n", "KR,005930,2,70000,\uC0BC\uC131\uC804\uC790,\uC7A5\uAE30 \uBCF4\uC720", "\n", "US,AAPL,1,180,Apple,"), /* @__PURE__ */ React2.createElement("p", null, "\uC774\uB984\xB7\uBA54\uBAA8\xB7\uD1B5\uD654 \uC5F4\uC740 \uC120\uD0DD\uC774\uC5D0\uC694. \uAE30\uC874 \uAE30\uB85D\uC5D0\uC11C \uBE60\uC9C4 \uC120\uD0DD \uC5F4\uC740 \uC720\uC9C0\uD558\uACE0, \uBE48\uCE78\uC73C\uB85C \uB123\uC740 \uC774\uB984\xB7\uBA54\uBAA8\uB294 \uBE44\uC6CC\uC694. \uC885\uBAA9\uCF54\uB4DC\uB85C \uCC3E\uC73C\uBA70 \uC774\uB984\uC73C\uB85C \uCD94\uCE21\uD558\uC9C0 \uC54A\uC544\uC694.")), /* @__PURE__ */ React2.createElement("label", { style: { marginTop: 12 } }, "CSV \uD30C\uC77C", /* @__PURE__ */ React2.createElement("input", { type: "file", accept: ".csv,text/csv", disabled: busy, onChange: (e) => {
    void load(e.target.files?.[0]);
    e.target.value = "";
  } })), unsupportedCount ? /* @__PURE__ */ React2.createElement("p", { role: "alert" }, "\uC9C0\uC6D0\uD558\uC9C0 \uC54A\uB294 \uAE30\uC874 \uBCF4\uC720 \uD56D\uBAA9 ", unsupportedCount, "\uAC1C\uAC00 \uC788\uC5B4 \uC804\uCCB4 \uC911\uBCF5\xB7\uD55C\uB3C4\uB97C \uD655\uC778\uD560 \uC218 \uC5C6\uC5B4\uC694. \uD30C\uC77C \uC800\uC7A5\uC740 \uBCF4\uB958\uD558\uACE0 \uBAA9\uB85D\uC5D0\uC11C \uD56D\uBAA9\uBCC4\uB85C \uD655\uC778\uD574\uC8FC\uC138\uC694.") : null, error ? /* @__PURE__ */ React2.createElement("p", { role: "alert" }, error) : null, report ? /* @__PURE__ */ React2.createElement(React2.Fragment, null, /* @__PURE__ */ React2.createElement("p", { role: "status" }, "\uCD94\uAC00 ", report.counts.add, " \xB7 \uC218\uC815 ", report.counts.edit, " \xB7 \uBCC0\uACBD \uC5C6\uC74C ", report.counts.unchanged, " \xB7 \uC624\uB958 ", report.counts.error), report.fatalErrors.map((entry, i) => /* @__PURE__ */ React2.createElement("p", { role: "alert", key: i }, entry.rowNumber, "\uD589: ", issue(entry.code))), /* @__PURE__ */ React2.createElement("ul", { className: "an-nest-rows" }, report.rows.map((row5) => /* @__PURE__ */ React2.createElement("li", { key: row5.rowNumber }, /* @__PURE__ */ React2.createElement("div", { style: { minWidth: 0 } }, /* @__PURE__ */ React2.createElement("strong", null, row5.rowNumber, "\uD589 \xB7 ", row5.ticker || "\uC885\uBAA9 \uD655\uC778 \uD544\uC694", " \xB7 ", { add: "\uCD94\uAC00", edit: "\uC218\uC815", unchanged: "\uBCC0\uACBD \uC5C6\uC74C", error: "\uC624\uB958" }[row5.kind]), row5.errors.map((code, i) => /* @__PURE__ */ React2.createElement("p", { key: i }, issue(code))), row5.preview ? /* @__PURE__ */ React2.createElement("dl", null, row5.preview.changedFields.map((key) => /* @__PURE__ */ React2.createElement(React2.Fragment, { key }, /* @__PURE__ */ React2.createElement("dt", null, fields2[key]), /* @__PURE__ */ React2.createElement("dd", null, String(row5.preview.before?.[key] ?? "\uC5C6\uC74C"), " \u2192 ", String(row5.preview.after?.[key] ?? "\uC5C6\uC74C"))))) : null)))), !submitted ? /* @__PURE__ */ React2.createElement("p", null, "\uC624\uB958\uAC00 \uC788\uC73C\uBA74 \uC800\uC7A5\uD558\uC9C0 \uC54A\uC544\uC694. \uD655\uC778 \uD6C4 \uD55C \uD56D\uBAA9\uC529 \uC800\uC7A5\uD558\uBA70, \uB3C4\uC911\uC5D0 \uC2E4\uD328\uD558\uBA74 \uADF8 \uC9C0\uC810\uC5D0\uC11C \uBA48\uCDB0\uC694.") : null, result ? /* @__PURE__ */ React2.createElement("div", { role: result.error || !result.refreshed ? "alert" : "status", "aria-live": "polite" }, /* @__PURE__ */ React2.createElement("p", null, result.total, "\uAC1C \uBCC0\uACBD \uC911 ", result.saved, "\uAC1C \uC800\uC7A5\uC744 \uD655\uC778\uD588\uC5B4\uC694."), result.error ? /* @__PURE__ */ React2.createElement("p", null, result.saved + 1, "\uBC88\uC9F8 \uD56D\uBAA9\uC5D0\uC11C \uBA48\uCDC4\uC5B4\uC694. \uC774 \uD56D\uBAA9\uC740 \uC800\uC7A5\uB410\uC744 \uC218\uB3C4 \uC788\uC73C\uB2C8 \uBAA9\uB85D\uC5D0\uC11C \uD655\uC778\uD574\uC8FC\uC138\uC694. \uB4A4\uC758 ", Math.max(0, result.total - result.saved - 1), "\uAC1C \uD56D\uBAA9\uC740 \uC694\uCCAD\uD558\uC9C0 \uC54A\uC558\uC5B4\uC694.") : null, !result.refreshed ? /* @__PURE__ */ React2.createElement("p", null, "\uC0C8 \uBAA9\uB85D \uC870\uD68C\uC5D0 \uC2E4\uD328\uD588\uC5B4\uC694. \uB2E4\uC2DC \uC800\uC7A5\uD558\uC9C0 \uB9D0\uACE0 \uD30C\uC77C\uC744 \uB2EB\uC740 \uB4A4 \uBAA9\uB85D \uB2E4\uC2DC \uBD88\uB7EC\uC624\uAE30\uB97C \uB20C\uB7EC\uC8FC\uC138\uC694.") : null, /* @__PURE__ */ React2.createElement("p", null, "\uAC19\uC740 \uD30C\uC77C\uC744 \uB2E4\uC2DC \uC800\uC7A5\uD558\uC9C0 \uB9D0\uACE0, \uC0C8 \uBAA9\uB85D\uC744 \uAE30\uC900\uC73C\uB85C \uBCC0\uACBD \uB0B4\uC6A9\uC744 \uB2E4\uC2DC \uD655\uC778\uD574\uC8FC\uC138\uC694.")) : null) : null, /* @__PURE__ */ React2.createElement("div", { className: "an-nest-actions" }, /* @__PURE__ */ React2.createElement("button", { type: "button", disabled: busy || !!submitted || !!unsupportedCount || !report?.readyForConfirmation, onClick: confirm }, busy ? "\uD655\uC778 \uC911\u2026" : "\uBCC0\uACBD \uD655\uC778 \uD6C4 \uD30C\uC77C \uB0B4\uC6A9 \uC800\uC7A5"), /* @__PURE__ */ React2.createElement("button", { type: "button", disabled: busy, onClick: onClose }, "\uD30C\uC77C \uB2EB\uAE30")));
}
var positive2 = (value) => typeof value === "number" && Number.isFinite(value) && value > 0;
var market = (value) => /^(KR|KOSPI|KOSDAQ)$/i.test(value.trim()) ? "KR" : /^(US|NASDAQ|NYSE|AMEX)$/i.test(value.trim()) ? "US" : null;
function holdingValuation(holding, companies) {
  const unavailable2 = (reason) => ({ quote: null, value: null, gain: null, gainPct: null, reason });
  const matches = companies.filter((company) => company.ticker === holding.ticker && market(company.market) === holding.market);
  if (!matches.length) return unavailable2("\uC885\uAC00 \uBBF8\uC5F0\uACB0 \xB7 \uD3C9\uAC00\uAE08\uC561\xB7\uC190\uC775 \uACC4\uC0B0 \uBCF4\uB958");
  if (matches.length !== 1) return unavailable2("\uC885\uAC00 \uC790\uB8CC \uC911\uBCF5 \xB7 \uD3C9\uAC00\uAE08\uC561\xB7\uC190\uC775 \uACC4\uC0B0 \uBCF4\uB958");
  const quote3 = matches[0].closeQuote;
  if (!quote3 || quote3.state !== "available") return unavailable2("\uC885\uAC00 \uBBF8\uC81C\uACF5 \xB7 \uD3C9\uAC00\uAE08\uC561\xB7\uC190\uC775 \uACC4\uC0B0 \uBCF4\uB958");
  if (!positive2(quote3.price)) return unavailable2("\uC885\uAC00 \uD655\uC778 \uD544\uC694 \xB7 \uD3C9\uAC00\uAE08\uC561\xB7\uC190\uC775 \uACC4\uC0B0 \uBCF4\uB958");
  const result = { quote: quote3, value: null, gain: null, gainPct: null, reason: null };
  if (quote3.currency !== (holding.market === "KR" ? "KRW" : "USD")) return { ...result, reason: "\uC885\uAC00\uC640 \uB9E4\uC218\uAC00\uC758 \uD1B5\uD654 \uD655\uC778 \uD544\uC694 \xB7 \uACC4\uC0B0 \uBCF4\uB958" };
  if (holding.duplicate) return { ...result, reason: "\uBCF4\uC720 \uAE30\uB85D \uC911\uBCF5 \uD655\uC778 \uD544\uC694 \xB7 \uACC4\uC0B0 \uBCF4\uB958" };
  if (!positive2(holding.shares)) return { ...result, reason: "\uBCF4\uC720 \uC218\uB7C9 \uD655\uC778 \uD544\uC694 \xB7 \uACC4\uC0B0 \uBCF4\uB958" };
  const value = holding.shares * quote3.price;
  if (!positive2(value)) return { ...result, reason: "\uD3C9\uAC00\uAE08\uC561 \uACC4\uC0B0 \uBC94\uC704 \uCD08\uACFC" };
  if (!positive2(holding.avg_cost)) return { ...result, value, reason: "\uD3C9\uADE0 \uB9E4\uC218\uAC00 \uD655\uC778 \uD544\uC694 \xB7 \uC190\uC775 \uACC4\uC0B0 \uBCF4\uB958" };
  const cost = holding.shares * holding.avg_cost, gain = value - cost, gainPct = (quote3.price / holding.avg_cost - 1) * 100;
  if (!positive2(cost) || !Number.isFinite(gain) || !Number.isFinite(gainPct)) return { ...result, value, reason: "\uC190\uC775 \uACC4\uC0B0 \uBC94\uC704 \uCD08\uACFC" };
  return { ...result, value, gain, gainPct };
}
function closePriceLabel(price, currency) {
  if (currency === "KRW" || currency === "USD") {
    return new Intl.NumberFormat("ko-KR", {
      style: "currency",
      currency,
      currencyDisplay: "code",
      maximumFractionDigits: currency === "KRW" ? 0 : 2
    }).format(price);
  }
  return `${new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2 }).format(price)}${currency ? ` ${currency}` : " \xB7 \uB2E8\uC704 \uBBF8\uC81C\uACF5"}`;
}
function changeLabel(changePct) {
  if (changePct === null) return "\uC804 \uAC70\uB798\uC77C \uB300\uBE44 \uBBF8\uC81C\uACF5";
  if (changePct === 0) return "\uC804 \uAC70\uB798\uC77C \uB300\uBE44 0.00% \xB7 \uBCF4\uD569";
  return `\uC804 \uAC70\uB798\uC77C \uB300\uBE44 ${changePct > 0 ? "+" : ""}${changePct.toFixed(2)}%`;
}
function freshnessLabel(freshness) {
  return freshness === "older" ? "\uC774\uC804 \uAE30\uC900\uC77C \uC790\uB8CC" : freshness === "unknown" ? "\uCD5C\uC2E0 \uAC70\uB798\uC77C \uC5EC\uBD80 \uBBF8\uD655\uC778" : "\uD655\uC778\uB41C \uAC70\uB798\uC77C \uAE30\uC900";
}
var blank = () => ({ ticker: "", market: "KR", name: "", shares: "", avg_cost: "", memo: "" });
var CSS = `
.an-nest{color-scheme:light dark;--panel:light-dark(#fff,#171c23);--ink:light-dark(#191f28,#e3e7ec);--muted:light-dark(#6b7684,#9aa4b1);--soft:light-dark(#f8f9fb,#1d242c);--hover:light-dark(#f1f3f5,#252c35);--focus:light-dark(#e9edf2,#303945);background:var(--panel);color:var(--ink);font:600 13px/1.6 Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;padding:20px;min-width:0}
.an-nest *{box-sizing:border-box}.an-nest h2,.an-nest h3,.an-nest p{margin:0}.an-nest h2{font-size:20px;font-weight:800}.an-nest h3{font-size:15px;font-weight:700}.an-nest p,.an-nest small{color:var(--muted);font-weight:600}.an-nest header{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:16px}.an-nest button{font:inherit;font-weight:700;color:var(--ink);background:var(--soft);border:0;border-radius:8px;padding:6px 10px;min-height:32px;cursor:pointer;transition:background 160ms}.an-nest button:disabled{opacity:.5;cursor:default}.an-nest :is(button,input,select,textarea):focus-visible{outline:0;background:var(--focus)}.an-nest input,.an-nest select,.an-nest textarea{display:block;width:100%;font:inherit;color:var(--ink);background:var(--soft);border:0;border-radius:8px;padding:8px;min-height:36px}.an-nest textarea{resize:vertical;min-height:72px}.an-nest label{display:grid;gap:4px;color:var(--muted);font-weight:700}.an-nest-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.an-nest-form,.an-nest-preview{padding:16px;border-radius:16px;background:var(--soft);margin-bottom:16px}.an-nest-summary{padding:12px 0;display:flex;gap:8px 14px;flex-wrap:wrap}.an-nest-summary strong{font-weight:800}.an-nest-form input,.an-nest-form select,.an-nest-form textarea{background:var(--panel)}.an-nest-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}.an-nest-rows{display:grid;gap:8px;list-style:none;padding:0;margin:16px 0}.an-nest-rows li{display:flex;align-items:center;justify-content:space-between;gap:12px;background:var(--soft);padding:12px;border-radius:12px}.an-nest-rows strong{font-weight:700;overflow-wrap:anywhere}.an-nest-rows small{display:block}.an-nest-rows .an-nest-actions{margin:0;flex-shrink:0}.an-nest-preview dl{margin:8px 0;display:grid;grid-template-columns:100px minmax(0,1fr);gap:6px}.an-nest-preview dt{color:var(--muted)}.an-nest-preview dd{margin:0;overflow-wrap:anywhere;white-space:pre-wrap}.an-nest [role=alert]{padding:10px 0;color:var(--ink)}
@media(hover:hover){.an-nest button:not(:disabled):hover{background:var(--hover)}}@media(pointer:coarse){.an-nest button,.an-nest input,.an-nest select{min-height:44px}}@media(max-width:600px){.an-nest{padding:12px}.an-nest-grid{grid-template-columns:1fr}.an-nest-rows li{align-items:flex-start;flex-direction:column}.an-nest-preview dl{grid-template-columns:74px minmax(0,1fr)}}@media(prefers-reduced-motion:reduce){.an-nest button{transition:none}}
.an-nest-grid label{align-content:start}
.an-nest summary{display:flex;align-items:center;gap:8px;cursor:pointer;list-style:none;padding:6px 8px;border-radius:8px;min-height:32px}.an-nest summary::-webkit-details-marker{display:none}.an-nest summary::before{content:"";width:6px;height:6px;border-right:1.5px solid currentColor;border-bottom:1.5px solid currentColor;transform:rotate(-45deg);flex-shrink:0}.an-nest details[open]>summary::before{transform:rotate(45deg)}.an-nest summary:focus-visible{outline:0;background:var(--focus)}@media(hover:hover){.an-nest summary:hover{background:var(--hover)}}@media(pointer:coarse){.an-nest summary{min-height:44px}}
`;
var labels = { ticker: "\uC885\uBAA9\uCF54\uB4DC", market: "\uC2DC\uC7A5", name: "\uC774\uB984", shares: "\uC218\uB7C9", avg_cost: "\uD3C9\uADE0 \uB9E4\uC218\uAC00", memo: "\uBA54\uBAA8" };
function errorText(error) {
  const code = error instanceof Error ? error.message : "";
  if (/invalid-shares|invalid-avg_cost/.test(code)) return "\uC218\uB7C9\uACFC \uD3C9\uADE0 \uB9E4\uC218\uAC00\uB97C 0\uBCF4\uB2E4 \uD070 \uC22B\uC790\uB85C \uC785\uB825\uD574\uC8FC\uC138\uC694.";
  if (/ticker-requires-edit/.test(code)) return "\uC774\uBBF8 \uB4F1\uB85D\uB41C \uC885\uBAA9\uC774\uC5D0\uC694. \uBAA9\uB85D\uC5D0\uC11C \uC218\uC815\uC744 \uB20C\uB7EC\uC8FC\uC138\uC694.";
  if (/invalid-ticker|invalid-market/.test(code)) return "\uC2DC\uC7A5\uACFC \uC885\uBAA9\uCF54\uB4DC\uB97C \uD655\uC778\uD574\uC8FC\uC138\uC694. \uAD6D\uB0B4\xB7\uBBF8\uAD6D \uC8FC\uC2DD\uACFC ETF\uB97C \uC9C0\uC6D0\uD574\uC694.";
  if (/stale|changed|conflict/.test(code)) return "\uB2E4\uB978 \uD654\uBA74\uC5D0\uC11C \uBCF4\uC720 \uAE30\uB85D\uC774 \uBC14\uB00C\uC5C8\uC5B4\uC694. \uB2E4\uC2DC \uBD88\uB7EC\uC628 \uB4A4 \uBCC0\uACBD \uB0B4\uC6A9\uC744 \uD655\uC778\uD574\uC8FC\uC138\uC694.";
  if (/auth|owner|session|disposed/.test(code)) return "\uB85C\uADF8\uC778 \uC0C1\uD0DC\uAC00 \uBC14\uB00C\uC5C8\uC5B4\uC694. \uB2E4\uC2DC \uB85C\uADF8\uC778\uD55C \uB4A4 \uD655\uC778\uD574\uC8FC\uC138\uC694.";
  if (/duplicate|holding-id|holding-not-found/.test(code)) return "\uC218\uC815\uD560 \uBCF4\uC720 \uD56D\uBAA9\uC744 \uC815\uD655\uD788 \uAD6C\uBD84\uD560 \uC218 \uC5C6\uC5B4\uC694. \uBAA9\uB85D\uC744 \uB2E4\uC2DC \uD655\uC778\uD574\uC8FC\uC138\uC694.";
  if (/no-holding-changes/.test(code)) return "\uBCC0\uACBD\uD55C \uB0B4\uC6A9\uC774 \uC5C6\uC5B4\uC694.";
  return "\uC800\uC7A5 \uC5EC\uBD80\uB97C \uD655\uC778\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694. \uC785\uB825\uC740 \uB0A8\uACA8\uB450\uC5C8\uC5B4\uC694. \uB2E4\uC2DC \uC800\uC7A5\uD558\uAE30 \uC804\uC5D0 \uBAA9\uB85D\uC744 \uD655\uC778\uD574\uC8FC\uC138\uC694.";
}
function PortfolioHoldingsPanel({ state, visible, onBack, onConfirm, onConfirmCsv, onReload }) {
  const [form, setForm] = React4.useState(null);
  const [preview, setPreview] = React4.useState(null);
  const [busy, setBusy] = React4.useState(false);
  const [message, setMessage] = React4.useState("");
  const [error, setError] = React4.useState("");
  const [csvOpen, setCsvOpen] = React4.useState(false);
  const [lastSavedKind, setLastSavedKind] = React4.useState(null);
  const known = state.phase === "ready" || state.phase === "choose-stocks";
  const change = (key, value) => {
    setForm((old) => old ? { ...old, [key]: value } : old);
    setPreview(null);
    setError("");
  };
  const edit = (holding) => {
    setCsvOpen(false);
    setForm({ id: holding.id, ticker: holding.ticker, market: holding.market, name: holding.name, shares: holding.shares?.toString() || "", avg_cost: holding.avg_cost?.toString() || "", memo: holding.memo || "" });
    setPreview(null);
    setError("");
    setMessage("");
    setLastSavedKind(null);
  };
  const prepare = (remove) => {
    setError("");
    setMessage("");
    setLastSavedKind(null);
    try {
      if (remove) {
        setCsvOpen(false);
        setPreview(previewHoldingChange(state.holdings, { kind: "remove", id: remove.id }));
      } else if (form) {
        if (!form.id) setPreview(previewHoldingChange(state.holdings, { kind: "add", ...form }));
        else {
          const original = state.holdings.find((h) => h.id === form.id);
          if (!original) throw Error("holding-not-found");
          const fields3 = {};
          for (const key of ["name", "shares", "avg_cost", "memo"]) if (form[key] !== String(original[key] ?? "")) fields3[key] = form[key];
          setPreview(previewHoldingChange(state.holdings, { kind: "edit", id: form.id, ...fields3 }));
        }
      }
    } catch (e) {
      setError(errorText(e));
    }
  };
  const confirm = async () => {
    if (!preview || busy) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const kind = preview.kind, result = await onConfirm(preview);
      setPreview(null);
      setForm(null);
      setLastSavedKind(result.refreshed ? kind : null);
      setMessage(result.refreshed ? "\uBCF4\uC720 \uAE30\uB85D\uC744 \uC800\uC7A5\uD588\uC5B4\uC694. \uAC70\uB798 \uAE30\uB85D\uC740 \uBC14\uB00C\uC9C0 \uC54A\uC558\uC5B4\uC694." : "\uC800\uC7A5 \uC694\uCCAD\uC740 \uC644\uB8CC\uB410\uC9C0\uB9CC \uC0C8 \uBAA9\uB85D\uC744 \uBD88\uB7EC\uC624\uC9C0 \uBABB\uD588\uC5B4\uC694. \uB2E4\uC2DC \uC800\uC7A5\uD558\uC9C0 \uB9D0\uACE0 \uBAA9\uB85D\uC744 \uB2E4\uC2DC \uBD88\uB7EC\uC640 \uD655\uC778\uD574\uC8FC\uC138\uC694.");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return /* @__PURE__ */ React4.createElement("section", { className: "an-nest", "aria-label": "\uB465\uC9C0 \uBCF4\uC720\uC885\uBAA9 \uAD00\uB9AC", hidden: !visible, style: { position: "absolute", inset: 0, overflow: "auto", zIndex: 1 } }, /* @__PURE__ */ React4.createElement("style", null, CSS), /* @__PURE__ */ React4.createElement("header", null, /* @__PURE__ */ React4.createElement("div", null, /* @__PURE__ */ React4.createElement("h2", null, "\uB465\uC9C0 \uBCF4\uC720\uBAA9\uB85D"), /* @__PURE__ */ React4.createElement("p", null, "\uC885\uBAA9 \uAD00\uB9AC\uC640 \uC9C0\uB3C4 \uBA54\uBAA8\uB294 \uB530\uB85C \uC800\uC7A5\uD574\uC694.")), /* @__PURE__ */ React4.createElement("button", { type: "button", disabled: busy, onClick: onBack }, "\uC9C0\uB3C4\uB85C \uB3CC\uC544\uAC00\uAE30")), /* @__PURE__ */ React4.createElement("div", { className: "an-nest-actions" }, /* @__PURE__ */ React4.createElement("button", { type: "button", disabled: !known || busy, onClick: () => {
    setCsvOpen(false);
    setForm(blank());
    setPreview(null);
    setError("");
    setMessage("");
    setLastSavedKind(null);
  } }, "\uC885\uBAA9 \uCD94\uAC00"), /* @__PURE__ */ React4.createElement("button", { type: "button", disabled: !known || busy, onClick: () => {
    setCsvOpen(true);
    setForm(null);
    setPreview(null);
    setError("");
    setMessage("");
    setLastSavedKind(null);
  } }, "\uD30C\uC77C\uB85C \uB123\uAE30"), /* @__PURE__ */ React4.createElement("button", { type: "button", disabled: busy, onClick: async () => {
    setBusy(true);
    setError("");
    try {
      if (!await onReload()) setError("\uBAA9\uB85D\uC744 \uBD88\uB7EC\uC624\uC9C0 \uBABB\uD588\uC5B4\uC694. \uC785\uB825\uD55C \uB0B4\uC6A9\uC740 \uB0A8\uACA8\uB450\uC5C8\uC5B4\uC694.");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  } }, "\uBAA9\uB85D \uB2E4\uC2DC \uBD88\uB7EC\uC624\uAE30")), known ? /* @__PURE__ */ React4.createElement("div", { className: "an-nest-summary", "aria-label": "\uB465\uC9C0 \uD56D\uBAA9 \uC694\uC57D" }, /* @__PURE__ */ React4.createElement("span", null, /* @__PURE__ */ React4.createElement("strong", null, state.holdings.length), " \uBCF4\uC720"), /* @__PURE__ */ React4.createElement("span", null, /* @__PURE__ */ React4.createElement("strong", null, state.watchlist?.length || 0), " \uAD00\uC2EC"), state.unsupportedCount || state.watchlistUnsupportedCount ? /* @__PURE__ */ React4.createElement("span", null, /* @__PURE__ */ React4.createElement("strong", null, state.unsupportedCount + (state.watchlistUnsupportedCount || 0)), " \uC9C0\uC6D0 \uBC94\uC704 \uBC16") : null) : null, message ? /* @__PURE__ */ React4.createElement("p", { role: "status" }, message) : null, lastSavedKind && lastSavedKind !== "remove" ? /* @__PURE__ */ React4.createElement("p", null, "\uC9C0\uB3C4\uB85C \uB3CC\uC544\uAC00\uBA74 \uC800\uC7A5\uD55C \uC885\uBAA9\uC744 \uBC14\uB85C \uD655\uC778\uD560 \uC218 \uC788\uC5B4\uC694.") : null, error ? /* @__PURE__ */ React4.createElement("p", { role: "alert" }, error) : null, csvOpen ? /* @__PURE__ */ React4.createElement(PortfolioHoldingsCsvPanel, { holdings: state.holdings, unsupportedCount: state.unsupportedCount, busy: busy || !known, onBusy: setBusy, onClose: () => setCsvOpen(false), onConfirm: onConfirmCsv }) : null, form ? /* @__PURE__ */ React4.createElement("form", { className: "an-nest-form", onSubmit: (e) => {
    e.preventDefault();
    prepare();
  } }, /* @__PURE__ */ React4.createElement("h3", null, form.id ? "\uBCF4\uC720 \uAE30\uB85D \uC218\uC815" : "\uBCF4\uC720\uC885\uBAA9 \uCD94\uAC00"), /* @__PURE__ */ React4.createElement("p", null, "\uC785\uB825\uAC12\uC740 \uBCC0\uACBD \uB0B4\uC6A9\uC744 \uD655\uC778\uD55C \uB4A4 \uC800\uC7A5\uB3FC\uC694."), /* @__PURE__ */ React4.createElement("fieldset", { disabled: busy || !known, style: { border: 0, padding: 0, margin: "12px 0 0" } }, /* @__PURE__ */ React4.createElement("div", { className: "an-nest-grid" }, /* @__PURE__ */ React4.createElement("label", null, "\uC2DC\uC7A5", /* @__PURE__ */ React4.createElement("select", { value: form.market, disabled: !!form.id, onChange: (e) => change("market", e.target.value) }, /* @__PURE__ */ React4.createElement("option", { value: "KR" }, "\uAD6D\uB0B4 \xB7 KRW"), /* @__PURE__ */ React4.createElement("option", { value: "US" }, "\uBBF8\uAD6D \xB7 USD"))), /* @__PURE__ */ React4.createElement("label", null, "\uC885\uBAA9\uCF54\uB4DC", /* @__PURE__ */ React4.createElement("input", { value: form.ticker, disabled: !!form.id, onChange: (e) => change("ticker", e.target.value), placeholder: form.market === "KR" ? "005930" : "AAPL" })), /* @__PURE__ */ React4.createElement("label", null, "\uC774\uB984", /* @__PURE__ */ React4.createElement("input", { value: form.name, onChange: (e) => change("name", e.target.value) })), /* @__PURE__ */ React4.createElement("label", null, "\uC218\uB7C9", /* @__PURE__ */ React4.createElement("input", { inputMode: "decimal", value: form.shares, onChange: (e) => change("shares", e.target.value) })), /* @__PURE__ */ React4.createElement("label", null, "\uD3C9\uADE0 \uB9E4\uC218\uAC00 \xB7 ", form.market === "KR" ? "KRW" : "USD", /* @__PURE__ */ React4.createElement("input", { inputMode: "decimal", value: form.avg_cost, onChange: (e) => change("avg_cost", e.target.value) })), /* @__PURE__ */ React4.createElement("label", null, "\uBCF4\uC720 \uBA54\uBAA8", /* @__PURE__ */ React4.createElement("textarea", { value: form.memo, onChange: (e) => change("memo", e.target.value) }))), /* @__PURE__ */ React4.createElement("div", { className: "an-nest-actions" }, /* @__PURE__ */ React4.createElement("button", { type: "submit" }, "\uBCC0\uACBD \uB0B4\uC6A9 \uD655\uC778"), /* @__PURE__ */ React4.createElement("button", { type: "button", onClick: () => {
    setForm(null);
    setPreview(null);
  } }, "\uC785\uB825 \uCDE8\uC18C")))) : null, preview ? /* @__PURE__ */ React4.createElement("section", { className: "an-nest-preview", "aria-label": "\uBCF4\uC720 \uBCC0\uACBD \uBBF8\uB9AC\uBCF4\uAE30" }, /* @__PURE__ */ React4.createElement("h3", null, preview.kind === "remove" ? "\uC774 \uBCF4\uC720 \uAE30\uB85D\uC744 \uC0AD\uC81C\uD560\uAE4C\uC694?" : "\uC774 \uB0B4\uC6A9\uC73C\uB85C \uC800\uC7A5\uD560\uAE4C\uC694?"), /* @__PURE__ */ React4.createElement("p", null, preview.kind === "remove" ? "\uBAA9\uB85D\uC758 \uBCF4\uC720 \uAE30\uB85D\uB9CC \uC0AD\uC81C\uD574\uC694. \uC2E4\uC81C \uB9E4\uB3C4\uB098 \uAC70\uB798 \uAE30\uB85D \uCD94\uAC00\uAC00 \uC544\uB2C8\uBA70 \uC9C0\uB3C4 \uBA54\uBAA8\uB3C4 \uC0AD\uC81C\uD558\uC9C0 \uC54A\uC544\uC694." : "\uD604\uC7AC \uAE30\uB85D\uACFC \uBE44\uAD50\uD574\uC8FC\uC138\uC694. \uB2E4\uB978 \uD654\uBA74\uC5D0\uC11C \uB3D9\uC2DC\uC5D0 \uC218\uC815\uD558\uC9C0 \uC54A\uB294 \uAC83\uC774 \uC88B\uC544\uC694."), /* @__PURE__ */ React4.createElement("dl", null, /* @__PURE__ */ React4.createElement("dt", null, "\uC885\uBAA9"), /* @__PURE__ */ React4.createElement("dd", null, preview.after?.name || preview.before?.name, " \xB7 ", preview.after?.ticker || preview.before?.ticker), (preview.kind === "remove" ? ["shares", "avg_cost", "memo"] : preview.changedFields).map((key) => /* @__PURE__ */ React4.createElement(React4.Fragment, { key }, /* @__PURE__ */ React4.createElement("dt", null, labels[key]), /* @__PURE__ */ React4.createElement("dd", null, String(preview.before?.[key] ?? "\uC5C6\uC74C"), " \u2192 ", String(preview.after?.[key] ?? "\uC0AD\uC81C"))))), /* @__PURE__ */ React4.createElement("div", { className: "an-nest-actions" }, /* @__PURE__ */ React4.createElement("button", { type: "button", disabled: busy || !known, onClick: confirm }, busy ? "\uD655\uC778 \uC911\u2026" : preview.kind === "remove" ? "\uD655\uC778 \uD6C4 \uBCF4\uC720 \uAE30\uB85D \uC0AD\uC81C" : "\uD655\uC778 \uD6C4 \uBCF4\uC720 \uAE30\uB85D \uC800\uC7A5"), /* @__PURE__ */ React4.createElement("button", { type: "button", disabled: busy, onClick: () => setPreview(null) }, "\uB3CC\uC544\uAC00\uC11C \uC218\uC815"))) : null, !known ? /* @__PURE__ */ React4.createElement("p", { role: "status" }, state.phase === "error" ? "\uBAA9\uB85D\uC744 \uBD88\uB7EC\uC624\uC9C0 \uBABB\uD588\uC5B4\uC694. \uBCF4\uC720 \uAE30\uB85D\uC774 \uC5C6\uB2E4\uB294 \uB73B\uC740 \uC544\uB2C8\uC5D0\uC694." : "\uBCF4\uC720\uBAA9\uB85D\uC744 \uD655\uC778\uD558\uACE0 \uC788\uC5B4\uC694.") : /* @__PURE__ */ React4.createElement(React4.Fragment, null, state.holdings.length ? /* @__PURE__ */ React4.createElement("p", null, "\uC5F0\uACB0\uB41C \uC885\uAC00 \uAE30\uC900\uC73C\uB85C \uACC4\uC0B0\uD574\uC694. \uC2E4\uC2DC\uAC04 \uAC00\uACA9\uC774 \uC544\uB2C8\uBA70 \uC218\uC218\uB8CC\xB7\uC138\uAE08\xB7\uD658\uC728 \uC190\uC775\uC740 \uC81C\uC678\uD574\uC694.") : null, /* @__PURE__ */ React4.createElement("ul", { className: "an-nest-rows" }, state.holdings.map((h) => {
    const valuation = holdingValuation(h, state.graph?.companies || []), quote3 = valuation.quote;
    return /* @__PURE__ */ React4.createElement("li", { key: h.market + ":" + h.ticker }, /* @__PURE__ */ React4.createElement("div", null, /* @__PURE__ */ React4.createElement("strong", null, h.name), /* @__PURE__ */ React4.createElement("small", null, h.ticker, " \xB7 ", h.market, " \xB7 ", state.selectedTickers.includes(h.ticker) ? "\uBD84\uC11D \uBC94\uC704\uC5D0 \uD3EC\uD568" : "\uBD84\uC11D \uBC94\uC704 \uBC16"), /* @__PURE__ */ React4.createElement("small", null, "\uC218\uB7C9 ", h.duplicate ? "\uC911\uBCF5 \uD655\uC778 \uD544\uC694" : formatHoldingQuantity(h.shares), " \xB7 \uD3C9\uADE0 \uB9E4\uC218\uAC00 ", formatHoldingAverageCost(h)), quote3 ? /* @__PURE__ */ React4.createElement(React4.Fragment, null, /* @__PURE__ */ React4.createElement("small", null, "\uC885\uAC00 ", closePriceLabel(quote3.price, quote3.currency), " \xB7 ", changeLabel(quote3.changePct)), /* @__PURE__ */ React4.createElement("small", null, quote3.priceDate, " \xB7 ", quote3.source, " \xB7 ", freshnessLabel(quote3.freshness))) : null, quote3 && valuation.value !== null ? /* @__PURE__ */ React4.createElement("small", null, "\uD3C9\uAC00\uAE08\uC561 ", closePriceLabel(valuation.value, quote3.currency), valuation.gain !== null && valuation.gainPct !== null ? /* @__PURE__ */ React4.createElement(React4.Fragment, null, " \xB7 \uD3C9\uAC00\uC190\uC775 ", valuation.gain > 0 ? "+" : "", closePriceLabel(valuation.gain, quote3.currency), " (", valuation.gainPct > 0 ? "+" : "", valuation.gainPct.toFixed(2), "%)") : null) : null, valuation.reason ? /* @__PURE__ */ React4.createElement("small", null, valuation.reason) : null), /* @__PURE__ */ React4.createElement("div", { className: "an-nest-actions" }, /* @__PURE__ */ React4.createElement("button", { type: "button", disabled: busy || !h.id || h.duplicate, onClick: () => edit(h), "aria-label": h.name + " \uC218\uC815" }, "\uC218\uC815"), /* @__PURE__ */ React4.createElement("button", { type: "button", disabled: busy || !h.id || h.duplicate, onClick: () => prepare(h), "aria-label": h.name + " \uC0AD\uC81C" }, "\uC0AD\uC81C")));
  })), !state.holdings.length ? /* @__PURE__ */ React4.createElement("p", null, "\uB4F1\uB85D\uD55C \uBCF4\uC720\uC885\uBAA9\uC774 \uC5C6\uC5B4\uC694. \uC885\uBAA9 \uCD94\uAC00\uB85C \uC2DC\uC791\uD558\uC138\uC694.") : null, state.unsupportedCount ? /* @__PURE__ */ React4.createElement("p", null, "\uC774 \uC9C0\uB3C4\uC5D0\uC11C \uC9C0\uC6D0\uD558\uC9C0 \uC54A\uB294 \uBCF4\uC720 \uD56D\uBAA9 ", state.unsupportedCount, "\uAC1C\uB294 \uBCC4\uB3C4\uB85C \uC720\uC9C0\uB3FC\uC694.") : null, state.watchlistError ? /* @__PURE__ */ React4.createElement("p", { role: "status" }, "\uAD00\uC2EC\uC885\uBAA9\uC744 \uBD88\uB7EC\uC624\uC9C0 \uBABB\uD588\uC5B4\uC694. \uBAA9\uB85D \uB2E4\uC2DC \uBD88\uB7EC\uC624\uAE30\uB85C \uC7AC\uC2DC\uB3C4\uD560 \uC218 \uC788\uC5B4\uC694.") : state.watchlist?.length ? /* @__PURE__ */ React4.createElement("details", null, /* @__PURE__ */ React4.createElement("summary", null, "\uAD00\uC2EC\uC885\uBAA9 ", state.watchlist.length, "\uAC1C"), /* @__PURE__ */ React4.createElement("p", null, "\uAD00\uC2EC\uC885\uBAA9\uC740 \uBCF4\uC720 \uC218\uB7C9\xB7\uD3C9\uADE0 \uB9E4\uC218\uAC00\uC5D0 \uD3EC\uD568\uD558\uC9C0 \uC54A\uC544\uC694."), /* @__PURE__ */ React4.createElement("ul", { className: "an-nest-rows" }, state.watchlist.map((stock) => /* @__PURE__ */ React4.createElement("li", { key: stock.market + ":" + stock.ticker }, /* @__PURE__ */ React4.createElement("div", null, /* @__PURE__ */ React4.createElement("strong", null, stock.name), /* @__PURE__ */ React4.createElement("small", null, stock.ticker, " \xB7 ", stock.market, " \xB7 ", state.holdings.some((h) => h.ticker === stock.ticker && h.market === stock.market) ? "\uBCF4\uC720\xB7\uAD00\uC2EC" : "\uAD00\uC2EC\uB9CC", " \xB7 ", state.selectedTickers.includes(stock.ticker) ? "\uBD84\uC11D \uBC94\uC704\uC5D0 \uD3EC\uD568" : "\uBD84\uC11D \uBC94\uC704 \uBC16")))))) : null, state.watchlistUnsupportedCount ? /* @__PURE__ */ React4.createElement("p", null, "\uC9C0\uC6D0\uD558\uC9C0 \uC54A\uB294 \uAD00\uC2EC \uD56D\uBAA9 ", state.watchlistUnsupportedCount, "\uAC1C\uB294 \uC6D0\uB798 \uBAA9\uB85D\uC5D0 \uC720\uC9C0\uB3FC\uC694.") : null));
}
var API2 = "https://project-yw131.vercel.app/api/holdings";
var USER_ID2 = /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i;
var TICKER = { KR: /^[0-9A-Z]{6}$/, US: /^[A-Z][A-Z0-9.-]{0,14}$/ };
var EDIT_FIELDS = ["shares", "avg_cost", "name", "memo"];
var PortfolioHoldingsEditorError = class extends Error {
  constructor(code) {
    super(code);
    __publicField(this, "code", code);
    this.name = code;
  }
};
function fail2(code) {
  throw new PortfolioHoldingsEditorError(code);
}
var isRecord = (value) => !!value && typeof value === "object" && !Array.isArray(value);
var sameUser = (left, right) => !!right && left.userId === right.userId;
var sameText = (left, right) => (left || "") === (right || "");
var copy3 = (value) => JSON.parse(JSON.stringify(value));
function sessionFor(getSession) {
  try {
    const value = getSession();
    return value && USER_ID2.test(value.userId) && typeof value.token === "string" && value.token.trim() ? value : null;
  } catch {
    return null;
  }
}
function positiveStoredNumber(value) {
  if (typeof value === "boolean") return null;
  if (typeof value === "string") {
    const text13 = value.replace(/[,\s₩$원]/g, "");
    if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(text13)) return null;
    value = Number(text13);
  }
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : null;
}
function holdingRow(value) {
  if (!isRecord(value) || typeof value.id !== "string" || !value.id.trim() || typeof value.ticker !== "string" || typeof value.market !== "string" || typeof value.name !== "string") return null;
  const ticker = value.ticker.trim().toUpperCase(), rawMarket = value.market.trim().toLowerCase();
  const market2 = rawMarket === "kr" ? "KR" : rawMarket === "us" ? "US" : null;
  if (!market2 || !TICKER[market2].test(ticker)) return null;
  return {
    id: value.id.trim(),
    ticker,
    market: market2,
    name: value.name,
    shares: positiveStoredNumber(value.shares),
    avg_cost: positiveStoredNumber(value.avg_cost),
    memo: typeof value.memo === "string" ? value.memo : "",
    duplicate: false
  };
}
function holdingsRows(value) {
  const values = Array.isArray(value) ? value : isRecord(value) && Array.isArray(value.holdings) ? value.holdings : null;
  if (!values) return fail2("holdings-unavailable");
  const tickers = values.map((row5) => {
    if (!isRecord(row5) || typeof row5.ticker !== "string" || !row5.ticker.trim()) fail2("holdings-unavailable");
    return row5.ticker.trim().toUpperCase();
  });
  return { rows: values.map(holdingRow).filter((row5) => row5 !== null), tickers };
}
function sameHolding(left, right) {
  return left.id === right.id && left.ticker === right.ticker && left.market === right.market && (left.name.trim() || left.ticker) === (right.name.trim() || right.ticker) && left.shares === right.shares && left.avg_cost === right.avg_cost && sameText(left.memo, right.memo) && left.duplicate !== true && right.duplicate !== true;
}
function editFields(preview) {
  if (!Array.isArray(preview.changedFields) || !preview.changedFields.length || new Set(preview.changedFields).size !== preview.changedFields.length) fail2("invalid-preview");
  if (!preview.changedFields.every((field3) => EDIT_FIELDS.includes(field3))) fail2("invalid-preview");
  return preview.changedFields;
}
function canonicalPreview(fresh, preview) {
  if (preview.kind === "add") {
    const after2 = preview.after;
    if (preview.id !== null || preview.before !== null || !after2 || after2.id !== null || typeof after2.name !== "string" || typeof after2.memo !== "string") fail2("invalid-preview");
    if (fresh.some((row5) => row5.ticker === after2.ticker)) fail2("preflight-ticker-exists");
    return previewHoldingChange([], { kind: "add", ticker: after2.ticker, market: after2.market, shares: after2.shares, avg_cost: after2.avg_cost, name: after2.name, memo: after2.memo });
  }
  const before = preview.before;
  if (!preview.id || !before?.id || preview.id !== before.id) fail2("invalid-preview");
  const targets = fresh.filter((row5) => row5.id === before.id);
  if (targets.length !== 1 || !sameHolding(targets[0], before)) fail2("preflight-stale");
  if (preview.kind === "remove") {
    if (preview.after !== null || preview.changedFields.length) fail2("invalid-preview");
    return previewHoldingChange([targets[0]], { kind: "remove", id: before.id });
  }
  const after = preview.after, fields3 = editFields(preview);
  if (!after || after.id !== before.id || after.ticker !== before.ticker || after.market !== before.market) fail2("invalid-preview");
  const change = { kind: "edit", id: before.id };
  fields3.forEach((field3) => {
    change[field3] = after[field3];
  });
  return previewHoldingChange([targets[0]], change);
}
function acknowledged(preview, value) {
  if (preview.kind === "remove") {
    if (!isRecord(value) || value.ok !== true || !preview.id) fail2("write-unacknowledged");
    return { kind: "deleted", id: preview.id };
  }
  const row5 = holdingRow(value), after = preview.after;
  if (!row5 || !after || preview.kind === "edit" && row5.id !== preview.id || row5.ticker !== after.ticker || row5.market !== after.market || row5.name !== after.name || row5.shares !== after.shares || row5.avg_cost !== after.avg_cost || !sameText(row5.memo, after.memo)) fail2("write-unacknowledged");
  return { kind: "saved", row: row5 };
}
function createPortfolioHoldingsEditor(options = {}) {
  const getSession = options.getSession || readMapSession, fetcher = options.fetcher || fetch;
  const timeoutMs = typeof options.timeoutMs === "number" && Number.isFinite(options.timeoutMs) && options.timeoutMs > 0 ? options.timeoutMs : 15e3;
  let disposed = false, writing = false;
  const pending = /* @__PURE__ */ new Set();
  const current = (account) => {
    if (disposed) fail2("editor-disposed");
    const value = sessionFor(getSession);
    if (!value) fail2("authentication-required");
    if (!sameUser(account, value)) fail2("session-changed");
    return value;
  };
  const request = async (init, failure2) => {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), timeoutMs);
    pending.add(controller);
    try {
      const response = await fetcher(API2, { ...init, signal: controller.signal, cache: "no-store", credentials: "omit", redirect: "error" });
      return { response, body: await response.json() };
    } catch {
      if (disposed) fail2("editor-disposed");
      if (controller.signal.aborted) fail2("request-timeout");
      fail2(failure2);
    } finally {
      clearTimeout(timer);
      pending.delete(controller);
    }
  };
  return {
    prepare(records, change) {
      return previewHoldingChange(records, change);
    },
    async confirm(preview) {
      if (writing) fail2("mutation-in-flight");
      const account = sessionFor(getSession);
      if (!account) fail2("authentication-required");
      writing = true;
      try {
        const readSession = current(account);
        const preflight = await request({ headers: { Authorization: "Bearer " + readSession.token } }, "holdings-unavailable");
        current(account);
        if (!preflight.response.ok) fail2(preflight.response.status === 401 ? "authentication-required" : "holdings-unavailable");
        const fresh = holdingsRows(preflight.body);
        current(account);
        if (preview.kind === "add" && fresh.tickers.includes(String(preview.after?.ticker || "").trim().toUpperCase())) fail2("preflight-ticker-exists");
        const canonical = canonicalPreview(fresh.rows, preview);
        const writeSession = current(account);
        const write = await request({ method: canonical.request.method, headers: { Authorization: "Bearer " + writeSession.token, "Content-Type": "application/json" }, body: JSON.stringify(canonical.request.body) }, "write-failed");
        current(account);
        if (!write.response.ok) fail2(write.response.status === 401 ? "authentication-required" : "write-failed");
        const result = acknowledged(canonical, write.body);
        current(account);
        options.onSaved?.(copy3(result));
        return result;
      } finally {
        writing = false;
      }
    },
    dispose() {
      if (!disposed) {
        disposed = true;
        pending.forEach((controller) => controller.abort());
        pending.clear();
      }
    }
  };
}
async function saveConfirmedHoldingCsv(previews, options) {
  if (!previews.length || previews.length > HOLDINGS_CSV_LIMITS.maxRows || previews.some((p) => !p.after || p.kind === "remove") || new Set(previews.map((p) => p.after.ticker)).size !== previews.length) throw Error("invalid-csv-preview");
  const changes = JSON.parse(JSON.stringify(previews));
  const getSession = options.getSession || readMapSession, account = getSession();
  if (!account) throw Error("authentication-required");
  const current = () => options.isCurrent() && getSession()?.userId === account.userId;
  let saved = 0, error = null;
  for (const preview of changes) {
    if (!current()) throw Error("session-changed");
    try {
      await options.editor.confirm(preview);
      saved++;
    } catch (failure2) {
      error = failure2 instanceof Error ? failure2.message : "write-failed";
      break;
    }
    if (!current()) throw Error("session-changed");
  }
  if (!current()) throw Error("session-changed");
  let refreshed = false;
  try {
    refreshed = await options.reload();
  } catch {
  }
  if (!current()) throw Error("session-changed");
  return { saved, total: changes.length, refreshed, error };
}
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
  const [theme, setTheme] = useState32(
    () => readPortfolioMapTheme(browserThemeInput())
  );
  useEffect22(() => {
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
function PublicPortfolioPrototype({ template = "", templateURL }) {
  const theme = usePortfolioMapTheme();
  const frame = React5.useRef(null);
  const controller = React5.useRef(null);
  const editor = React5.useRef(null);
  const bridge = React5.useRef(null);
  const [state, setState] = React5.useState(null);
  const [source, setSource] = React5.useState(null);
  const [view, setView] = React5.useState("map");
  const [memberEpoch, setMemberEpoch] = React5.useState(0);
  const needsLoginCheck = state?.error === "authentication-required" || state?.watchlistError === "authentication-required" || state?.privateState.error === "authentication-required";
  React5.useEffect(() => {
    if (!frame.current) return;
    const workspace = createPortfolioMapWorkspace({ includeWatchlist: true, usePortfolioAnalysis: true });
    let holdingsEditor = createPortfolioHoldingsEditor();
    editor.current = holdingsEditor;
    controller.current = workspace;
    const unsubscribe = workspace.subscribe((value) => {
      setState(value);
      if (value.phase !== "ready") setSource(null);
      if (value.phase === "signed-out") {
        bridge.current?.clearReturnFocus();
        holdingsEditor.dispose();
        holdingsEditor = createPortfolioHoldingsEditor();
        editor.current = holdingsEditor;
        setSelected([]);
        setView("map");
        setMemberEpoch((epoch) => epoch + 1);
      }
    });
    const logoLoader = createPortfolioPublicLogoLoader();
    const unmount = mountMemberPrototype(frame.current, template, workspace, { openSource: setSource, openHoldings: () => setView("holdings"), templateURL, logoLoader, entryStock: parsePortfolioMapEntry(window.location.search) });
    bridge.current = unmount;
    const unbind = workspace.bindAuth(window);
    const stopDataRefresh = workspace.bindDataRefresh(window);
    void workspace.open();
    return () => {
      stopDataRefresh();
      unmount();
      unsubscribe();
      unbind();
      holdingsEditor.dispose();
      workspace.dispose();
      controller.current = null;
      editor.current = null;
      bridge.current = null;
    };
  }, [template, templateURL]);
  const [selected, setSelected] = React5.useState([]);
  return /* @__PURE__ */ React5.createElement("section", { "aria-label": "\uB0B4 \uD3EC\uD2B8\uD3F4\uB9AC\uC624 \uAD00\uACC4\uC9C0\uB3C4", style: { position: "relative", width: "100%", minWidth: 0 } }, /* @__PURE__ */ React5.createElement("style", null, `.an-data-refresh{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:8px 12px;background:var(--an-refresh-bg);color:var(--an-refresh-text);font:600 12px/1.6 Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif}.an-data-refresh button{border:0;border-radius:8px;padding:6px 8px;min-height:32px;background:var(--an-refresh-card);color:inherit;font-family:inherit;font-size:12px;line-height:1.6;font-weight:700;cursor:pointer;transition:background 160ms}.an-data-refresh button:focus-visible{outline:0;background:var(--an-refresh-focus)}.an-data-refresh button:disabled{cursor:wait;opacity:.65}@media(hover:hover){.an-data-refresh button:not(:disabled):hover{background:var(--an-refresh-hover)}}@media(pointer:coarse){.an-data-refresh button{min-height:44px}}@media(prefers-reduced-motion:reduce){.an-data-refresh button{transition:none}}`), !state || state.phase === "loading" || state.phase === "signed-out" ? /* @__PURE__ */ React5.createElement("p", { role: "status" }, state?.phase === "signed-out" ? "\uB85C\uADF8\uC778 \uD6C4 \uC9C0\uB3C4 \uC790\uB8CC\uB97C \uBD88\uB7EC\uC635\uB2C8\uB2E4." : "\uBCF4\uC720\uC885\uBAA9\uACFC \uC9C0\uB3C4 \uC790\uB8CC\uB97C \uBD88\uB7EC\uC624\uB294 \uC911\uC774\uC5D0\uC694.") : null, state?.phase === "ready" ? /* @__PURE__ */ React5.createElement("div", { className: "an-data-refresh", "aria-label": "\uC9C0\uB3C4 \uC790\uB8CC \uAC31\uC2E0", style: {
    "--an-refresh-bg": theme === "dark" ? "#1d242c" : "#f8f9fb",
    "--an-refresh-card": theme === "dark" ? "#171c23" : "#ffffff",
    "--an-refresh-text": theme === "dark" ? "#e3e7ec" : "#191f28",
    "--an-refresh-hover": theme === "dark" ? "#252c35" : "#f1f3f5",
    "--an-refresh-focus": theme === "dark" ? "#303945" : "#e9edf2"
  } }, /* @__PURE__ */ React5.createElement("span", { role: "status" }, state.dataRefresh?.phase === "checking" ? "\uC790\uB8CC \uBCC0\uACBD\uC744 \uD655\uC778 \uC911\uC774\uC5D0\uC694. \uC9C0\uB3C4\uB294 \uACC4\uC18D \uC0AC\uC6A9\uD560 \uC218 \uC788\uC5B4\uC694." : state.dataRefresh?.phase === "available" ? "\uC9C0\uB3C4\uC5D0 \uBC18\uC601\uD560 \uC790\uB8CC \uBCC0\uACBD\uC774 \uC788\uC5B4\uC694." : state.dataRefresh?.phase === "error" ? "\uC790\uB8CC \uD655\uC778\uC774 \uC9C0\uC5F0\uB410\uC5B4\uC694. \uAE30\uC874 \uC9C0\uB3C4\uC640 \uAE30\uB85D\uC740 \uC720\uC9C0\uD588\uC5B4\uC694." : "\uD654\uBA74\uC744 \uBCF4\uB294 \uB3D9\uC548 5\uBD84\uB9C8\uB2E4 \uC790\uB8CC \uBCC0\uACBD\uC744 \uD655\uC778\uD574\uC694."), !!state.dataRefresh?.incompleteSources ? /* @__PURE__ */ React5.createElement("span", { role: "status" }, "\uC6D0\uBB38 \uC5F0\uACB0 \uBC94\uC704 ", state.dataRefresh.incompleteSources, "/", state.dataRefresh.totalSources, "\uAC1C\uAC00 \uBD80\uBD84\uC801\uC774\uAC70\uB098 \uD655\uC778\uC774 \uD544\uC694\uD574\uC694. \uC774 \uC22B\uC790\uB9CC\uC73C\uB85C \uC870\uD68C \uC2E4\uD328\uB97C \uB73B\uD558\uC9C0\uB294 \uC54A\uC544\uC694. \uB204\uB77D\uB41C \uAE30\uC874 \uC6D0\uBB38\uC740 \uC774\uC804 \uC870\uD68C \uB0B4\uC6A9\uC73C\uB85C \uC720\uC9C0\uD574\uC694.") : null, state.dataRefresh?.checkedAt ? /* @__PURE__ */ React5.createElement("span", null, "\uCD5C\uADFC \uC870\uD68C ", new Date(state.dataRefresh.checkedAt).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" }), " \xB7 \uC790\uB8CC \uAE30\uC900\uC77C\uC740 \uC6D0\uBB38\uBCC4 \uD655\uC778") : null, state.dataRefresh?.phase === "available" ? /* @__PURE__ */ React5.createElement("button", { type: "button", onClick: () => {
    controller.current?.applyDataUpdate();
  } }, "\uBCC0\uACBD \uC790\uB8CC \uBC18\uC601") : /* @__PURE__ */ React5.createElement("button", { type: "button", disabled: state.dataRefresh?.phase === "checking", onClick: () => {
    void controller.current?.refreshData();
  } }, "\uC790\uB8CC \uB2E4\uC2DC \uD655\uC778")) : null, state?.phase === "choose-stocks" ? /* @__PURE__ */ React5.createElement("div", null, /* @__PURE__ */ React5.createElement("p", null, "\uC9C0\uB3C4\uC5D0 \uD568\uAED8 \uD45C\uC2DC\uD560 \uC885\uBAA9\uC744 \uCD5C\uB300 30\uAC1C \uACE8\uB77C\uC8FC\uC138\uC694. \uB465\uC9C0\uC758 \uBCF4\uC720 \uBAA9\uB85D\uC740 \uBC14\uB00C\uC9C0 \uC54A\uC544\uC694."), workspaceStocks(state).map((h) => /* @__PURE__ */ React5.createElement("label", { key: h.ticker }, /* @__PURE__ */ React5.createElement(
    "input",
    {
      type: "checkbox",
      checked: selected.includes(h.ticker),
      disabled: !selected.includes(h.ticker) && selected.length >= 30,
      onChange: (e) => setSelected((old) => e.target.checked ? [...old, h.ticker] : old.filter((t) => t !== h.ticker))
    }
  ), h.name, " \xB7 ", h.held ? h.watched ? "\uBCF4\uC720\xB7\uAD00\uC2EC" : "\uBCF4\uC720" : "\uAD00\uC2EC")), /* @__PURE__ */ React5.createElement("button", { type: "button", disabled: !selected.length, onClick: () => {
    void controller.current?.showTickers(selected);
  } }, "\uC9C0\uB3C4\uC5D0\uC11C \uBCF4\uAE30"), /* @__PURE__ */ React5.createElement("button", { type: "button", onClick: () => setView("holdings") }, "\uBCF4\uC720\uBAA9\uB85D")) : null, needsLoginCheck ? /* @__PURE__ */ React5.createElement("div", { className: "an-data-refresh", role: "alert", style: {
    "--an-refresh-bg": theme === "dark" ? "#1d242c" : "#f8f9fb",
    "--an-refresh-card": theme === "dark" ? "#171c23" : "#ffffff",
    "--an-refresh-text": theme === "dark" ? "#e3e7ec" : "#191f28",
    "--an-refresh-hover": theme === "dark" ? "#252c35" : "#f1f3f5",
    "--an-refresh-focus": theme === "dark" ? "#303945" : "#e9edf2"
  } }, "\uB85C\uADF8\uC778 \uC0C1\uD0DC\uB97C \uB2E4\uC2DC \uD655\uC778\uD574 \uC8FC\uC138\uC694. \uC800\uC7A5\uB41C \uAE30\uB85D\uC740 \uADF8\uB300\uB85C \uC720\uC9C0\uB3FC\uC694.", /* @__PURE__ */ React5.createElement("button", { type: "button", onClick: () => {
    if (!state?.privateState.dirty && view !== "holdings" || window.confirm("\uC0C8\uB85C\uACE0\uCE68\uD558\uBA74 \uC800\uC7A5\uB418\uC9C0 \uC54A\uC740 \uBCC0\uACBD\uC774 \uC0AC\uB77C\uC9C8 \uC218 \uC788\uC5B4\uC694. \uACC4\uC18D\uD560\uAE4C\uC694?")) window.location.reload();
  } }, "\uB85C\uADF8\uC778 \uC0C1\uD0DC \uB2E4\uC2DC \uD655\uC778")) : null, state?.watchlistError && state.watchlistError !== "authentication-required" && (state.phase === "ready" || state.phase === "choose-stocks") ? /* @__PURE__ */ React5.createElement("p", { role: "status" }, "\uAD00\uC2EC\uC885\uBAA9\uC744 \uBD88\uB7EC\uC624\uC9C0 \uBABB\uD588\uC5B4\uC694. \uBCF4\uC720\uC885\uBAA9\uC740 \uADF8\uB300\uB85C \uBCFC \uC218 \uC788\uC5B4\uC694. \uBCF4\uC720\uBAA9\uB85D\uC5D0\uC11C \uB2E4\uC2DC \uBD88\uB7EC\uC62C \uC218 \uC788\uC5B4\uC694.") : null, state?.phase === "error" && state.error !== "authentication-required" ? /* @__PURE__ */ React5.createElement("div", { role: "alert" }, "\uC790\uB8CC\uB97C \uBD88\uB7EC\uC624\uC9C0 \uBABB\uD588\uC5B4\uC694. \uC800\uC7A5\uD55C \uAE30\uB85D\uC740 \uADF8\uB300\uB85C\uC608\uC694.", /* @__PURE__ */ React5.createElement("button", { type: "button", onClick: () => {
    void controller.current?.open();
  } }, "\uB2E4\uC2DC \uBD88\uB7EC\uC624\uAE30")) : null, state?.phase === "ready" && (state.privateState.phase === "conflict" || state.privateState.phase === "error" && state.privateState.error !== "authentication-required") ? /* @__PURE__ */ React5.createElement("div", { role: "alert" }, state.privateState.phase === "conflict" ? "\uB2E4\uB978 \uD654\uBA74\uC5D0\uC11C \uAE30\uB85D\uC774 \uBC14\uB00C\uC5C8\uC5B4\uC694. \uB0B4 \uBCC0\uACBD\uC740 \uC544\uC9C1 \uC800\uC7A5\uB418\uC9C0 \uC54A\uC558\uC5B4\uC694." : "\uC800\uC7A5 \uAE30\uB85D\uC744 \uD655\uC778\uD558\uC9C0 \uBABB\uD588\uC5B4\uC694. \uD604\uC7AC \uBCC0\uACBD\uC740 \uC720\uC9C0\uD558\uACE0 \uC788\uC5B4\uC694.", state.privateState.phase === "error" && state.privateState.error !== "authentication-required" && state.privateState.dirty ? /* @__PURE__ */ React5.createElement("button", { type: "button", onClick: () => {
    void controller.current?.save();
  } }, "\uC800\uC7A5 \uB2E4\uC2DC \uC2DC\uB3C4") : null, /* @__PURE__ */ React5.createElement("button", { type: "button", onClick: () => {
    if (!state.privateState.dirty || window.confirm("\uD604\uC7AC \uBBF8\uC800\uC7A5 \uBCC0\uACBD\uC744 \uBC84\uB9AC\uACE0 \uC800\uC7A5\uB41C \uAE30\uB85D\uC744 \uB2E4\uC2DC \uBD88\uB7EC\uC62C\uAE4C\uC694?")) void controller.current?.reloadSaved(state.privateState.dirty);
  } }, "\uC800\uC7A5 \uAE30\uB85D \uB2E4\uC2DC \uBD88\uB7EC\uC624\uAE30")) : null, source ? /* @__PURE__ */ React5.createElement("div", { role: "status" }, /* @__PURE__ */ React5.createElement("a", { href: source, target: "_blank", rel: "noopener noreferrer" }, "\uC120\uD0DD\uD55C \uC6D0\uBB38 \uC5F4\uAE30"), /* @__PURE__ */ React5.createElement("button", { type: "button", onClick: () => setSource(null) }, "\uB2EB\uAE30")) : null, /* @__PURE__ */ React5.createElement(
    "iframe",
    {
      ref: frame,
      "data-an-site-map": "",
      title: "\uB0B4 \uC885\uBAA9 \uC791\uC5C5\uD310",
      sandbox: "allow-scripts",
      referrerPolicy: "no-referrer",
      style: { display: "block", visibility: view === "map" ? "visible" : "hidden", width: "100%", height: "max(680px, calc(100dvh - 40px))", border: 0 }
    }
  ), state && state.phase !== "signed-out" ? /* @__PURE__ */ React5.createElement(
    PortfolioHoldingsPanel,
    {
      key: memberEpoch,
      state,
      visible: view === "holdings",
      onBack: () => {
        setView("map");
        bridge.current?.returnToMap();
      },
      onReload: () => controller.current?.open() || Promise.resolve(false),
      onConfirmCsv: (previews) => {
        bridge.current?.clearReturnFocus();
        const currentEditor = editor.current, workspace = controller.current;
        if (!currentEditor || !workspace) return Promise.reject(Error("session-unavailable"));
        return saveConfirmedHoldingCsv(previews, {
          editor: currentEditor,
          isCurrent: () => editor.current === currentEditor && controller.current === workspace,
          reload: () => workspace.open()
        });
      },
      onConfirm: async (preview) => {
        const currentEditor = editor.current, workspace = controller.current;
        if (!currentEditor || !workspace) throw Error("session-unavailable");
        const completeFocus = bridge.current?.prepareReturnFocus();
        const result = await currentEditor.confirm(preview);
        if (editor.current !== currentEditor || controller.current !== workspace) throw Error("session-changed");
        const refreshed = await workspace.open();
        if (editor.current !== currentEditor || controller.current !== workspace) throw Error("session-changed");
        if (refreshed && result.kind === "saved") completeFocus?.(result.row.ticker);
        return { refreshed };
      }
    }
  ) : null);
}
function PublicPortfolioMapReview({ minHeight = 820, style }) {
  const isStatic = useIsStaticRenderer();
  return /* @__PURE__ */ React6.createElement("div", { style: { ...style, position: "relative", width: "100%", minHeight, boxSizing: "border-box" } }, isStatic ? /* @__PURE__ */ React6.createElement("section", { "aria-label": "\uD68C\uC6D0 \uC9C0\uB3C4 \uAC80\uC218\uC6A9" }, /* @__PURE__ */ React6.createElement("h2", null, "\uD68C\uC6D0 \uC9C0\uB3C4 \uAC80\uC218\uC6A9"), /* @__PURE__ */ React6.createElement("p", null, "\uC2E4\uC81C \uBBF8\uB9AC\uBCF4\uAE30\uC5D0\uC11C \uB85C\uADF8\uC778 \uD6C4 \uBCF4\uC720\uC885\uBAA9\uACFC \uC800\uC7A5 \uAE30\uB85D\uC744 \uBD88\uB7EC\uC635\uB2C8\uB2E4. \uACF5\uAC1C \uC0AC\uC774\uD2B8\uB294 \uBC14\uAFB8\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.")) : /* @__PURE__ */ React6.createElement(PublicPortfolioPrototype, { templateURL: "/member-map-canvas" }));
}
addPropertyControls(PublicPortfolioMapReview, {
  minHeight: { type: ControlType.Number, title: "\uCD5C\uC18C \uB192\uC774", defaultValue: 820, min: 480, max: 1200, step: 20 }
});

// review/member-map/company-structure-view.tsx
import * as React from "react";
var CSS2 = `
.acs-view{--acs-card:#fff;--acs-bg:#f8f9fb;--acs-text:#191f28;--acs-sub:#6b7684;--acs-hover:#f1f3f5;--acs-focus:#e9edf2;--acs-accent:#6c5ce7;--acs-line:#c8cdd4;--acs-selected:#f0edff;position:fixed;inset:0;z-index:10000;display:flex;flex-direction:column;background:var(--acs-bg);color:var(--acs-text);font:600 13px/1.6 Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif}
html[data-an-theme=dark] .acs-view,body[data-framer-theme=dark] .acs-view{--acs-card:#171c23;--acs-bg:#1d242c;--acs-text:#e3e7ec;--acs-sub:#9aa4b1;--acs-hover:#252c35;--acs-focus:#303945;--acs-accent:#a99bff;--acs-line:#4c5662;--acs-selected:#302948}
.acs-view *{box-sizing:border-box}.acs-view button,.acs-view select{font:700 13px/1.5 Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;color:inherit;border:0;background:var(--acs-card);border-radius:10px;min-height:36px;padding:7px 11px;cursor:pointer;transition:background-color 160ms}.acs-view button:focus-visible,.acs-view select:focus-visible,.acs-view a:focus-visible{outline:0;background:var(--acs-focus)}.acs-view button:disabled{opacity:.45;cursor:default}.acs-head{display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding:14px 22px;background:var(--acs-card)}.acs-brand{font-size:15px;font-weight:800;letter-spacing:-.5px}.acs-brand i{font-style:normal;color:var(--acs-accent)}.acs-tabs{display:flex;gap:4px;background:var(--acs-bg);padding:3px;border-radius:12px}.acs-tabs button{background:transparent}.acs-tabs button[aria-current=page]{background:var(--acs-card);box-shadow:0 2px 6px #191f2808}.acs-head label{display:flex;gap:8px;align-items:center;margin-left:auto;color:var(--acs-sub);font-size:12px}.acs-head select{background:var(--acs-bg);max-width:220px;min-width:0}.acs-toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:10px 22px}.acs-toolbar>span{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;color:var(--acs-sub);font-size:12px;margin-right:auto;min-width:0;overflow-wrap:anywhere}.acs-toolbar output{min-width:40px;text-align:center;font-size:12px}.acs-main{flex:1;min-height:0;display:flex;position:relative}.acs-space{position:relative;flex:1;min-width:0;overflow:hidden;touch-action:none;cursor:grab}.acs-space:active{cursor:grabbing}.acs-space:focus-visible{outline:0;background-color:var(--acs-focus)}.acs-world{position:absolute;left:0;top:0;transform-origin:0 0}.acs-lines{position:absolute;inset:0;overflow:visible;pointer-events:none}.acs-lines path{fill:none;stroke:var(--acs-line);stroke-width:1.5;stroke-linejoin:round}.acs-lines path[data-undated=true]{stroke-dasharray:4 4}.acs-card{position:absolute;width:224px;min-height:86px;border-radius:15px;background:var(--acs-card);box-shadow:0 5px 14px #191f280b;display:flex;gap:12px;padding:15px 16px;text-align:left;align-items:center}.acs-card:before{content:'';position:absolute;top:0;left:15px;right:15px;height:3px;background:var(--acs-line);border-radius:2px}.acs-card[data-focus=true]:before{background:var(--acs-accent)}.acs-card[data-focus=true]{background:var(--acs-selected)}.acs-card[data-dated=true]:not([data-focus=true]):before{background:#8dbda9}.acs-face{position:relative;flex:0 0 36px;width:36px;height:36px;display:grid;place-items:center;border-radius:11px;background:var(--acs-bg);font-weight:800;color:var(--acs-sub)}.acs-logo{width:100%;height:100%;object-fit:contain;border-radius:10px;display:block}.acs-flag{position:absolute;right:-4px;bottom:-4px;display:block;width:15px;height:15px;border-radius:50%;box-shadow:0 0 0 2px var(--acs-card)}.acs-copy{flex:1;min-width:0}.acs-name{display:block;font-size:14px;font-weight:800;line-height:1.4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.acs-role{display:block;font-size:11px;color:var(--acs-sub);margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.acs-card-main{border:0;background:transparent!important;min-height:0!important;padding:0!important;text-align:left;width:100%;min-width:0;border-radius:4px!important}.acs-card-main:focus-visible{background:var(--acs-focus)!important}.acs-card .acs-branch{position:absolute;left:calc(50% - 12px);bottom:-12px;width:24px;height:24px;min-height:24px;padding:0;border-radius:50%;background:var(--acs-card);box-shadow:0 2px 7px #191f2812;display:grid;place-items:center;font-size:16px;line-height:1}.acs-child-count{position:absolute;top:100%;left:calc(50% + 18px);font-size:10px;white-space:nowrap;color:var(--acs-sub);pointer-events:none}.acs-inspector{width:286px;max-width:40%;min-width:0;padding:20px;background:var(--acs-card);overflow:auto;scrollbar-gutter:stable}.acs-inspector h2{font-size:16px;font-weight:800;margin:0 0 8px;overflow-wrap:anywhere}.acs-inspector p{font-size:12px;white-space:pre-line;margin:10px 0;color:var(--acs-sub);overflow-wrap:anywhere}.acs-inspector summary{overflow-wrap:anywhere}.acs-inspector strong{color:var(--acs-text);font-weight:700}.acs-inspector a{display:block;padding:10px 12px;margin-top:8px;border-radius:12px;background:var(--acs-bg);color:var(--acs-text);text-decoration:none;overflow-wrap:anywhere;font-size:12px}.acs-inspector .acs-inspector-close{float:right}.acs-empty{align-self:center;max-width:460px;padding:24px;margin:auto;color:var(--acs-sub)}.acs-empty strong{display:block;color:var(--acs-text);font-size:16px;margin-bottom:8px}.acs-foot{display:flex;gap:16px;flex-wrap:wrap;padding:10px 22px;color:var(--acs-sub);font-size:11px;background:var(--acs-card)}.acs-key{display:flex;gap:7px;align-items:center}.acs-key i{width:20px;border-top:2px solid var(--acs-line)}.acs-key[data-kind=undated] i{border-top-style:dashed}.acs-status{margin-left:auto;min-width:0;overflow-wrap:anywhere}.acs-close{background:var(--acs-bg)!important}.review-structure-toggle{margin-left:auto;margin-right:10px}.review-structure-toggle[aria-pressed=true]{background:#e9edf2}
@media(hover:hover){.acs-view button:not(.acs-card-main):not(:disabled):hover,.acs-view a:hover{background:var(--acs-hover)}}
@media(max-width:700px){.acs-head{padding:10px 12px;gap:8px}.acs-brand{display:none}.acs-head label{margin-left:auto}.acs-head select{max-width:145px}.acs-toolbar{padding:8px 12px;gap:6px}.acs-toolbar>span{flex-basis:100%}.acs-inspector{position:absolute;bottom:0;left:0;right:0;width:auto;max-width:none;max-height:40%;box-shadow:0 -4px 16px #191f280b;padding:14px 16px}.acs-foot{padding:8px 12px;gap:6px 14px}.acs-status{margin-left:0;flex-basis:100%}}
@media(pointer:coarse){.acs-view button,.acs-view select{min-height:44px}.acs-card .acs-branch:after{content:'';position:absolute;inset:-10px}}
@media(prefers-reduced-motion:reduce){.acs-view button,.acs-view select{transition:none}}
.acs-space{background-image:linear-gradient(var(--acs-focus) 1px,transparent 1px),linear-gradient(90deg,var(--acs-focus) 1px,transparent 1px)}
.acs-lines .acs-flow{fill:none;stroke:var(--acs-line);stroke-width:2;stroke-linecap:round;stroke-dasharray:3 20;opacity:.38;animation:acs-edge-flow 8s linear infinite}
@keyframes acs-edge-flow{to{stroke-dashoffset:-23}}
[data-motion=paused] .acs-flow{animation-play-state:paused;visibility:hidden}
.acs-lines[data-flow-paused=true] .acs-flow{animation-play-state:paused}
@media(prefers-reduced-motion:reduce){.acs-flow{display:none!important;animation:none!important}}
`;
function makeStructureLayout(catalogue, focus) {
  const companies = new Map(catalogue.companies.map((c) => [c.id, c]));
  companies.set(focus.id, { ...companies.get(focus.id), ...focus });
  const byId = /* @__PURE__ */ new Map(), used = /* @__PURE__ */ new Set();
  const all = catalogue.relations.filter((r) => companies.has(r.from) && companies.has(r.to) && r.from !== r.to);
  const incoming = all.filter((r) => r.to === focus.id && (r.type === "major-shareholder" || r.type === "subsidiary")).slice(0, 3);
  const parent = incoming[0];
  const rootId = parent?.from || focus.id;
  let omitted = 0;
  function walk(id, depth, relation, parentId) {
    if (used.has(id) || used.size >= 160) {
      omitted++;
      return null;
    }
    used.add(id);
    const node = { company: companies.get(id), relation, parent: parentId, children: [], x: 0, y: depth * 154, depth };
    byId.set(id, node);
    const children = id === rootId && rootId !== focus.id ? all.filter((r) => r.from === id && r.to === focus.id) : all.filter((r) => r.from === id);
    if (depth < 3) for (const child of children.slice(0, 6)) {
      const next = walk(child.to, depth + 1, child, id);
      if (next) node.children.push(next);
    }
    omitted += Math.max(0, children.length - (depth < 3 ? 6 : 0));
    return id;
  }
  walk(rootId, 0);
  let leaf = 0;
  function place(id) {
    const n = byId.get(id);
    if (!n.children.length) n.x = leaf++ * 258;
    else {
      n.children.forEach(place);
      n.x = (byId.get(n.children[0]).x + byId.get(n.children[n.children.length - 1]).x) / 2;
    }
  }
  place(rootId);
  return { byId, roots: [rootId], omitted, total: all.filter((r) => used.has(r.from) || used.has(r.to)).length };
}
var safeEvidence = (value) => {
  if (!value || typeof value !== "object") return false;
  const e = value;
  if (typeof e.title !== "string" || typeof e.url !== "string" || e.url.length > 2048 || /[\u0000-\u001f\u007f]/.test(e.url)) return false;
  try {
    const u = new URL(e.url);
    return u.protocol === "https:" && !u.username && !u.password;
  } catch {
    return false;
  }
};
var officialRelation = (r) => r.evidence.length > 0 && (r.status === "source-dated" || r.status === "official-undated");
var isFlowEligibleRelation = (r) => !!r && officialRelation(r);
var relationDate = (r) => r.asOf ? `\uC790\uB8CC \uAE30\uC900 ${r.asOf}` : r.status === "official-undated" ? "\uACF5\uC2DD \uC548\uB0B4 \xB7 \uC6D0\uBB38 \uAE30\uC900\uC77C \uBBF8\uD45C\uC2DC" : "\uC6D0\uBB38 \uAE30\uC900\uC77C\uC774 \uD655\uC778\uB418\uC9C0 \uC54A\uC740 \uC800\uC7A5 \uC790\uB8CC\uC785\uB2C8\uB2E4.";
function RelationshipProof({ relation: r }) {
  if (r.status === "undated-snapshot") return /* @__PURE__ */ React.createElement(React.Fragment, null, /* @__PURE__ */ React.createElement("p", null, /* @__PURE__ */ React.createElement("strong", null, r.label), "\n" + relationDate(r), r.observedAt ? `
\uC800\uC7A5 \uC790\uB8CC \uC2DC\uAC01 ${r.observedAt.slice(0, 10)}` : ""), /* @__PURE__ */ React.createElement("p", null, "\uC774\uB984\uC774 \uB0A8\uC544 \uC788\uB294 \uCC38\uACE0 \uC790\uB8CC\uC785\uB2C8\uB2E4. \uD604\uC7AC \uC9C0\uBD84\xB7\uC790\uD68C\uC0AC \uC5EC\uBD80\uB098 \uC0C8 \uC6D0\uBB38 \uD655\uC778 \uC2DC\uAC01\uC73C\uB85C \uD574\uC11D\uD558\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4."), r.evidence.length ? r.evidence.map((e, i) => /* @__PURE__ */ React.createElement("a", { key: i, href: e.url, target: "_blank", rel: "noopener noreferrer" }, e.title, " \u2197")) : /* @__PURE__ */ React.createElement("p", null, "\uAC80\uC99D \uAC00\uB2A5\uD55C \uC6D0\uBB38 \uC8FC\uC18C\uAC00 \uC544\uC9C1 \uC81C\uACF5\uB418\uC9C0 \uC54A\uC558\uC5B4\uC694."));
  if (r.directOwnership === "unspecified" || r.label.includes("\uC9C1\uAC04\uC811 \uBBF8\uAD6C\uBD84")) return /* @__PURE__ */ React.createElement(React.Fragment, null, /* @__PURE__ */ React.createElement("p", null, /* @__PURE__ */ React.createElement("strong", null, r.label), "\n" + relationDate(r), r.observedAt ? `
\uC790\uB8CC \uC218\uC9D1 ${r.observedAt.slice(0, 10)}` : ""), /* @__PURE__ */ React.createElement("p", null, "\uACF5\uC2DC\uC758 \uC790\uD68C\uC0AC \uBAA9\uB85D\uC785\uB2C8\uB2E4. \uC9C1\uC811\xB7\uAC04\uC811 \uC18C\uC720\uC640 \uC9C0\uBD84\uC728\uC740 \uAD6C\uBD84\uB418\uC9C0 \uC54A\uC558\uC73C\uBA70 \uC804\uCCB4 \uACC4\uC5F4\uC0AC\uB97C \uB73B\uD558\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4."), r.evidence.map((e, i) => /* @__PURE__ */ React.createElement("a", { key: i, href: e.url, target: "_blank", rel: "noopener noreferrer" }, e.title, " \u2197")));
  return /* @__PURE__ */ React.createElement(React.Fragment, null, /* @__PURE__ */ React.createElement("p", null, /* @__PURE__ */ React.createElement("strong", null, r.label), r.status === "source-dated" && r.ownershipPct !== null ? ` \xB7 ${r.ownershipPct}%` : "", "\n" + relationDate(r), r.observedAt ? `
\uC790\uB8CC \uC218\uC9D1 ${r.observedAt.slice(0, 10)}` : ""), /* @__PURE__ */ React.createElement("p", null, r.type === "investment" ? "\uD0C0\uBC95\uC778 \uCD9C\uC790 \uB0B4\uC5ED\uC785\uB2C8\uB2E4. \uC790\uD68C\uC0AC \uC5EC\uBD80\uC640 \uD604\uC7AC \uC9C0\uBC30 \uAD00\uACC4\uB294 \uC774 \uD56D\uBAA9\uB9CC\uC73C\uB85C \uD655\uC815\uD558\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4." : "\uAD00\uACC4 \uC720\uD615\uACFC \uC6D0\uBB38 \uAE30\uC900\uC77C\uC744 \uD568\uAED8 \uD655\uC778\uD574 \uC8FC\uC138\uC694."), r.evidence.length ? r.evidence.map((e, i) => /* @__PURE__ */ React.createElement("a", { key: i, href: e.url, target: "_blank", rel: "noopener noreferrer" }, e.title, " \u2197")) : /* @__PURE__ */ React.createElement("p", null, "\uC774 \uC800\uC7A5 \uD56D\uBAA9\uC5D0\uB294 \uAC80\uC99D \uAC00\uB2A5\uD55C \uC6D0\uBB38 \uC8FC\uC18C\uAC00 \uC81C\uACF5\uB418\uC9C0 \uC54A\uC558\uC5B4\uC694."));
}
function validateStructure(value) {
  const c = value;
  if (!c || c.schema !== "alphanest-company-structure-v1" || !Array.isArray(c.companies) || !Array.isArray(c.relations) || c.companies.length > 3e3 || c.relations.length > 3e3) throw Error("catalogue");
  const ids = /* @__PURE__ */ new Set();
  for (const n of c.companies) {
    if (!n || typeof n.id !== "string" || !n.id || n.id.length > 180 || typeof n.name !== "string" || !n.name || n.name.length > 300 || ids.has(n.id)) throw Error("company");
    ids.add(n.id);
  }
  const relationIds = /* @__PURE__ */ new Set();
  for (const r of c.relations) {
    if (!r || typeof r.id !== "string" || !r.id || r.id.length > 600 || relationIds.has(r.id) || !ids.has(r.from) || !ids.has(r.to) || !["major-shareholder", "investment", "subsidiary"].includes(r.type) || typeof r.label !== "string" || r.label.length > 300 || !["source-dated", "official-undated", "undated-snapshot"].includes(r.status) || !(r.ownershipPct === null || typeof r.ownershipPct === "number" && Number.isFinite(r.ownershipPct) && r.ownershipPct >= 0 && r.ownershipPct <= 100) || !Array.isArray(r.evidence) || r.evidence.length > 10 || !r.evidence.every(safeEvidence) || r.asOf !== null && !/^\d{4}-\d{2}-\d{2}$/.test(r.asOf)) throw Error("relation");
    relationIds.add(r.id);
  }
  return c;
}
var LOGO_MANIFEST = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/logo_map.json";
var PNG_PREFIX2 = "https://static.toss.im/png-icons/securities/icn-sec-fill-";
var imageData = (v) => typeof v === "string" && v.length <= 18e4 && /^data:image\/(png|svg\+xml|webp|jpeg);base64,[A-Za-z0-9+/=]+$/.test(v) ? v : void 0;
async function boundedBytes(response, max) {
  if (!response.ok || !response.body) throw Error("response");
  const reader = response.body.getReader(), parts = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > max) throw Error("size");
      parts.push(value);
    }
  } finally {
    await reader.cancel().catch(() => {
    });
  }
  const all = new Uint8Array(size);
  let cursor = 0;
  for (const part of parts) {
    all.set(part, cursor);
    cursor += part.length;
  }
  return all;
}
async function loadCompanyStructure(stock, signal, fetcher = fetch) {
  if (!(stock.market === "KR" && /^[A-Z0-9]{6}$/.test(stock.ticker || "") || stock.market === "US" && /^[A-Z][A-Z0-9.-]{0,11}$/.test(stock.ticker || ""))) throw Error("ticker");
  try {
    const response = await fetcher(`https://project-yw131.vercel.app/api/company_structure?market=${stock.market}&ticker=${encodeURIComponent(stock.ticker)}`, { credentials: "omit", redirect: "error", signal });
    return validateStructure(JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(await boundedBytes(response, 2 * 1024 * 1024))));
  } catch (cause) {
    if (signal.aborted) throw cause;
    const response = await fetcher("https://project-yw131.vercel.app/member-map-review/company-structure.json", { credentials: "omit", redirect: "error", signal });
    const retained = validateStructure(JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(await boundedBytes(response, 2 * 1024 * 1024))));
    return { ...retained, coverage: { ...retained.coverage, sourceStatus: "retained-snapshot", fallback: true } };
  }
}
function structureCoverageText(catalogue) {
  const coverage = catalogue?.coverage;
  if (!coverage) return "\uAD00\uACC4\uBCC4 \uC6D0\uBB38\uACFC \uAE30\uC900\uC77C\uC744 \uD655\uC778\uD574 \uC8FC\uC138\uC694";
  if (coverage.fallback) return "\uCD5C\uC2E0 \uC870\uD68C \uC5F0\uACB0 \uC2E4\uD328 \xB7 \uC774\uC804 \uC800\uC7A5 \uC790\uB8CC\uB97C \uD45C\uC2DC\uD558\uACE0 \uC788\uC5B4\uC694";
  const state = coverage.sourceStatus || coverage.status;
  if (state === "refresh-error") return "\uCD5C\uADFC \uC6D0\uBB38 \uC870\uD68C \uC2E4\uD328 \xB7 \uC774\uC804 \uADFC\uAC70\uC640 \uAE30\uC900\uC77C \uC720\uC9C0";
  if (state === "needs-review") return "\uC6D0\uBB38 \uD655\uBCF4 \xB7 \uAD00\uACC4 \uAC80\uC218 \uBCF4\uB958 \xB7 \uD655\uC778\uB41C \uAE30\uC874 \uADFC\uAC70\uB9CC \uC720\uC9C0";
  if (state === "source-gap") return "\uAD00\uACC4 \uC6D0\uBB38 \uBBF8\uD655\uBCF4 \xB7 \uAD00\uACC4\uAC00 \uC5C6\uB2E4\uB294 \uB73B\uC740 \uC544\uB2C8\uC5D0\uC694";
  if (state === "budget-deferred") return "\uC870\uD68C \uC608\uC0B0\uC5D0 \uB530\uB77C \uB2E4\uC74C \uC218\uC9D1 \uB300\uAE30";
  if (state === "attempting") return "\uAD00\uACC4 \uC6D0\uBB38\uC744 \uD655\uC778\uD558\uACE0 \uC788\uC5B4\uC694";
  if (state === "source-checked") {
    const endpoints = coverage.endpoints && typeof coverage.endpoints === "object" ? Object.values(coverage.endpoints) : [];
    const stamps = [coverage.lastSuccessAt, ...endpoints.map((e) => e && typeof e === "object" ? e.lastSuccessAt : null)].filter((s) => typeof s === "string" && Number.isFinite(Date.parse(s)));
    const last = stamps.sort((a, b) => Date.parse(a) - Date.parse(b))[0];
    if (last) return `\uC6D0\uBB38 \uC870\uD68C ${last.slice(0, 10)}${Date.now() - Date.parse(last) > 7 * 864e5 ? " \xB7 \uC0C8 \uC790\uB8CC \uD655\uC778 \uB300\uAE30" : " \xB7 \uC18C\uC720 \uAD00\uACC4\uB294 \uC790\uB8CC \uAE30\uC900\uC77C\uB85C \uD655\uC778"}`;
    return "\uC6D0\uBB38 \uADFC\uAC70 \uC5F0\uACB0 \xB7 \uD604\uC7AC \uC18C\uC720 \uC5EC\uBD80\uB294 \uC790\uB8CC \uAE30\uC900\uC77C\uB85C \uD655\uC778";
  }
  if (state === "legacy-only" || state === "curated-only" || state === "partial") return "\uC6D0\uBB38 \uD655\uC778\uC774 \uC77C\uBD80 \uB0A8\uC544 \uC788\uC5B4\uC694 \xB7 \uD655\uC778\uB41C \uC5F0\uACB0 \uC6B0\uC120 \uD45C\uC2DC";
  if (state === "not-attempted") return "\uC6D0\uBB38 \uC218\uC9D1 \uB300\uAE30 \xB7 \uC5F0\uACB0 \uC5C6\uC74C\uC774 \uC544\uB2C8\uB77C \uC544\uC9C1 \uD655\uC778 \uC804\uC774\uC5D0\uC694";
  return "\uAD00\uACC4\uBCC4 \uC6D0\uBB38\uACFC \uAE30\uC900\uC77C\uC744 \uD655\uC778\uD574 \uC8FC\uC138\uC694";
}
async function loadLogos(companies, signal) {
  const manifestResponse = await fetch(LOGO_MANIFEST, { credentials: "omit", referrerPolicy: "no-referrer", redirect: "error", signal });
  const manifest = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(await boundedBytes(manifestResponse, 2 * 1024 * 1024)));
  const logos = {}, queue = companies.filter((c) => c.ticker && c.market).slice(0, 160);
  let index = 0;
  await Promise.all(Array.from({ length: 4 }, async () => {
    while (index < queue.length && !signal.aborted) {
      const company = queue[index++], entry = manifest?.logos?.[company.ticker];
      const expected = PNG_PREFIX2 + company.ticker + ".png";
      const raw = entry === void 0 ? expected : typeof entry === "string" ? entry : entry?.url;
      if (raw !== expected) continue;
      if (typeof raw !== "string" || !raw.startsWith(PNG_PREFIX2) || !/^https:\/\/static\.toss\.im\/png-icons\/securities\/icn-sec-fill-[A-Za-z0-9_.-]+\.png$/.test(raw)) continue;
      try {
        const response = await fetch(raw, { credentials: "omit", referrerPolicy: "no-referrer", redirect: "error", signal });
        if (!(response.headers.get("content-type") || "").startsWith("image/png")) continue;
        const bytes = await boundedBytes(response, 128 * 1024);
        if (bytes[0] !== 137 || bytes[1] !== 80 || bytes[2] !== 78 || bytes[3] !== 71) continue;
        let binary = "";
        for (const byte of bytes) binary += String.fromCharCode(byte);
        logos[company.id] = "data:image/png;base64," + btoa(binary);
      } catch {
      }
    }
  }));
  return logos;
}
function resolveFocus(catalogue, stock) {
  const canonicalId = catalogue.coverage?.canonicalId, aliases = catalogue.coverage?.securityIds;
  if (typeof canonicalId === "string" && Array.isArray(aliases) && aliases.includes(stock.market + ":" + stock.ticker)) {
    const company = catalogue.companies.find((c) => c.id === canonicalId);
    if (company) return company;
  }
  return catalogue.companies.find((c) => c.ticker === stock.ticker && c.market === stock.market) || { ...stock, id: stock.market + ":" + stock.ticker };
}
function resetInitialFocusAfterInitialLoad(initial, initialFocus) {
  if (initial) initialFocus.current = null;
}
function installStructureCameraInput(element, camera, update, dragging) {
  let gesture = null;
  const point2 = (event, fallback) => {
    const r = element.getBoundingClientRect();
    return {
      x: Number.isFinite(event.clientX) ? event.clientX - r.left : fallback?.x ?? r.width / 2,
      y: Number.isFinite(event.clientY) ? event.clientY - r.top : fallback?.y ?? r.height / 2
    };
  };
  const write = (next) => {
    camera.current = next;
    update(next);
  };
  const zoomAt = (zoom, p) => {
    const c = camera.current, z = Math.max(0.12, Math.min(2.5, zoom)), ratio = z / c.zoom;
    write({ x: p.x - (p.x - c.x) * ratio, y: p.y - (p.y - c.y) * ratio, zoom: z });
  };
  const wheel = (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (dragging() || gesture || !Number.isFinite(event.deltaX) || !Number.isFinite(event.deltaY)) return;
    const r = element.getBoundingClientRect(), c = camera.current;
    let dx = event.deltaX * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? r.width : 1);
    let dy = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? r.height : 1);
    if (event.ctrlKey || event.metaKey) zoomAt(c.zoom * Math.exp(-dy * 15e-4), point2(event));
    else {
      if (event.shiftKey && !dx) {
        dx = dy;
        dy = 0;
      }
      write({ ...c, x: c.x - dx, y: c.y - dy });
    }
  };
  const start = (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (dragging()) return;
    const c = camera.current, p = point2(event);
    gesture = {
      ...p,
      zoom: c.zoom,
      scale: Number.isFinite(event.scale) && event.scale > 0 ? event.scale : 1,
      worldX: (p.x - c.x) / c.zoom,
      worldY: (p.y - c.y) / c.zoom
    };
  };
  const change = (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (!gesture || dragging() || !Number.isFinite(event.scale) || event.scale <= 0) return;
    const p = point2(event, gesture), zoom = Math.max(0.12, Math.min(2.5, gesture.zoom * event.scale / gesture.scale));
    write({ x: p.x - gesture.worldX * zoom, y: p.y - gesture.worldY * zoom, zoom });
  };
  const end = (event) => {
    event.preventDefault();
    event.stopPropagation();
    gesture = null;
  };
  element.addEventListener("wheel", wheel, { passive: false, capture: true });
  element.addEventListener("gesturestart", start, { passive: false });
  element.addEventListener("gesturechange", change, { passive: false });
  element.addEventListener("gestureend", end, { passive: false });
  return () => {
    element.removeEventListener("wheel", wheel, true);
    element.removeEventListener("gesturestart", start);
    element.removeEventListener("gesturechange", change);
    element.removeEventListener("gestureend", end);
    gesture = null;
  };
}
function CompanyStructureView({ snapshot, onClose }) {
  const [catalogue, setCatalogue] = React.useState(null), [error, setError] = React.useState(false);
  const [focusIndex, setFocusIndex] = React.useState(0), [collapsed, setCollapsed] = React.useState(/* @__PURE__ */ new Set());
  const [includeStored, setIncludeStored] = React.useState(false);
  const [flowPaused, setFlowPaused] = React.useState(false);
  const [pendingCatalogue, setPendingCatalogue] = React.useState(null), [checking, setChecking] = React.useState(false), [checkFailed, setCheckFailed] = React.useState(false);
  const [selected, setSelected] = React.useState(null), [camera, setCamera] = React.useState({ x: 0, y: 0, zoom: 1 });
  const [logos, setLogos] = React.useState({});
  const [brokenLogos, setBrokenLogos] = React.useState(/* @__PURE__ */ new Set());
  const cameraRef = React.useRef(camera);
  cameraRef.current = camera;
  const catalogueRef = React.useRef(catalogue);
  catalogueRef.current = catalogue;
  const refreshRef = React.useRef(null);
  const space = React.useRef(null), host = React.useRef(null), initialFocus = React.useRef(null);
  const drag = React.useRef(null);
  const current = snapshot.stocks[focusIndex] || snapshot.stocks[0];
  const focus = React.useMemo(() => catalogue && current ? resolveFocus(catalogue, current) : null, [catalogue, current]);
  const layout = React.useMemo(() => catalogue && focus ? makeStructureLayout({ ...catalogue, relations: catalogue.relations.filter((r) => includeStored || officialRelation(r)) }, focus) : null, [catalogue, focus, includeStored]);
  const visible = React.useMemo(() => {
    if (!layout) return [];
    const result = [];
    function add(id) {
      const n = layout.byId.get(id);
      result.push(n);
      if (!collapsed.has(id)) n.children.forEach(add);
    }
    layout.roots.forEach(add);
    return result;
  }, [layout, collapsed]);
  React.useEffect(() => {
    if (!current) return;
    const c = new AbortController();
    let active = null;
    catalogueRef.current = null;
    setCatalogue(null);
    setPendingCatalogue(null);
    setError(false);
    setCheckFailed(false);
    async function check(initial = false) {
      if (active || c.signal.aborted || !initial && document.hidden) return;
      const request = new AbortController();
      active = request;
      setChecking(true);
      const timer = setTimeout(() => request.abort(), 22e3);
      try {
        const value = await loadCompanyStructure(current, request.signal);
        if (c.signal.aborted) return;
        setCheckFailed(false);
        setError(false);
        if (initial || !catalogueRef.current) {
          resetInitialFocusAfterInitialLoad(initial, initialFocus);
          catalogueRef.current = value;
          setCatalogue(value);
        } else if (value.coverage?.fallback && !catalogueRef.current?.coverage?.fallback) setCheckFailed(true);
        else if (JSON.stringify(value) !== JSON.stringify(catalogueRef.current)) setPendingCatalogue(value);
        else setPendingCatalogue(null);
      } catch {
        if (!c.signal.aborted) initial ? setError(true) : setCheckFailed(true);
      } finally {
        clearTimeout(timer);
        active = null;
        if (!c.signal.aborted) setChecking(false);
      }
    }
    refreshRef.current = () => {
      void check(false);
    };
    void check(true);
    const poll = setInterval(() => {
      void check(false);
    }, 5 * 60 * 1e3);
    return () => {
      c.abort();
      active?.abort();
      clearInterval(poll);
      refreshRef.current = null;
    };
  }, [current?.id, current?.ticker, current?.market]);
  React.useEffect(() => {
    if (!layout) return;
    const c = new AbortController(), timer = setTimeout(() => c.abort(), 18e3);
    loadLogos([...layout.byId.values()].map((n) => n.company), c.signal).then((value) => {
      if (!c.signal.aborted) setLogos(value);
    }).catch(() => {
    }).finally(() => clearTimeout(timer));
    return () => {
      c.abort();
      clearTimeout(timer);
    };
  }, [layout]);
  function fit() {
    const r = space.current?.getBoundingClientRect();
    if (!r || !visible.length) return;
    const left = Math.min(...visible.map((n) => n.x)), right = Math.max(...visible.map((n) => n.x)) + 224;
    const top = Math.min(...visible.map((n) => n.y)), bottom = Math.max(...visible.map((n) => n.y)) + 98;
    const zoom = Math.max(0.12, Math.min(1, (r.width - 64) / (right - left), (r.height - 72) / (bottom - top)));
    setCamera({ x: (r.width - (right - left) * zoom) / 2 - left * zoom, y: Math.max(32, (r.height - (bottom - top) * zoom) / 2 - top * zoom), zoom });
  }
  React.useLayoutEffect(() => {
    const focusKey = focus?.id + ":" + includeStored;
    if (!layout || !focus || initialFocus.current === focusKey || !space.current) return;
    const start = /* @__PURE__ */ new Set();
    for (const [id, n] of layout.byId) if (id !== focus?.id && n.depth > 0 && n.children.length) start.add(id);
    setCollapsed(start);
    setSelected(null);
    initialFocus.current = focusKey;
    const frame = requestAnimationFrame(() => {
      const shown = [];
      function visit(id) {
        const node = layout.byId.get(id);
        shown.push(node);
        if (!start.has(id)) node.children.forEach(visit);
      }
      layout.roots.forEach(visit);
      const r = space.current?.getBoundingClientRect();
      if (!r || !shown.length) return;
      const left = Math.min(...shown.map((n) => n.x)), right = Math.max(...shown.map((n) => n.x)) + 224, bottom = Math.max(...shown.map((n) => n.y)) + 110;
      const zoom = Math.max(0.12, Math.min(1, (r.width - 64) / (right - left), (r.height - 64) / bottom));
      setCamera({ x: (r.width - (right - left) * zoom) / 2 - left * zoom, y: Math.max(32, (r.height - bottom * zoom) / 2), zoom });
    });
    return () => cancelAnimationFrame(frame);
  }, [layout]);
  React.useEffect(() => {
    const prior = document.activeElement;
    const previous = [...document.querySelectorAll("#root > *")].filter((el) => el !== host.current && !el.contains(host.current)).map((el) => [el, el.inert]);
    previous.forEach(([el]) => {
      el.inert = true;
    });
    host.current?.querySelector(".acs-close")?.focus({ preventScroll: true });
    return () => {
      previous.forEach(([el, inert]) => {
        if (el.isConnected) el.inert = inert;
      });
      prior?.isConnected && prior.focus({ preventScroll: true });
    };
  }, []);
  function zoomTo(zoom, px, py) {
    const rect = space.current?.getBoundingClientRect();
    if (!rect) return;
    setCamera((c) => {
      const z = Math.max(0.12, Math.min(2.5, zoom)), ratio = z / c.zoom, x = px ?? rect.width / 2, y = py ?? rect.height / 2;
      return { x: x - (x - c.x) * ratio, y: y - (y - c.y) * ratio, zoom: z };
    });
  }
  React.useEffect(() => {
    const element = space.current;
    if (!element) return;
    return installStructureCameraInput(element, cameraRef, setCamera, () => drag.current !== null);
  }, []);
  function keyDown(e) {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      onClose();
      return;
    }
    if (e.key === "Tab") {
      const elements = [...host.current?.querySelectorAll("button:not(:disabled),select,summary,a[href],[tabindex='0']") || []].filter((el) => el.offsetParent !== null);
      if (e.shiftKey && document.activeElement === elements[0]) {
        e.preventDefault();
        elements.at(-1)?.focus();
      } else if (!e.shiftKey && document.activeElement === elements.at(-1)) {
        e.preventDefault();
        elements[0]?.focus();
      }
    }
  }
  const selectedNode = selected ? layout?.byId.get(selected) : null;
  const selectedConnections = React.useMemo(() => catalogue?.relations.filter((r) => r.from === selected && (includeStored || officialRelation(r))) || [], [catalogue, selected, includeStored]);
  const companyNames = React.useMemo(() => new Map(catalogue?.companies.map((c) => [c.id, c.name])), [catalogue]);
  return /* @__PURE__ */ React.createElement("section", { className: "acs-view", ref: host, role: "dialog", "aria-modal": "true", "aria-label": "\uAE30\uC5C5 \uAD6C\uC870 \uC804\uC6A9 \uBCF4\uAE30", onKeyDown: keyDown, onClick: (e) => e.stopPropagation() }, /* @__PURE__ */ React.createElement("style", null, CSS2), /* @__PURE__ */ React.createElement("header", { className: "acs-head" }, /* @__PURE__ */ React.createElement("strong", { className: "acs-brand" }, /* @__PURE__ */ React.createElement("i", null, "\u03B1"), " ALPHANEST"), /* @__PURE__ */ React.createElement("nav", { className: "acs-tabs", "aria-label": "\uC9C0\uB3C4 \uBCF4\uAE30" }, /* @__PURE__ */ React.createElement("button", { type: "button", className: "acs-close", onClick: onClose }, "\uD575\uC2EC \uC9C0\uB3C4"), /* @__PURE__ */ React.createElement("button", { type: "button", "aria-current": "page" }, "\uAE30\uC5C5 \uAD6C\uC870")), /* @__PURE__ */ React.createElement("label", null, "\uC911\uC2EC \uC885\uBAA9", /* @__PURE__ */ React.createElement("select", { "aria-label": "\uAE30\uC5C5 \uAD6C\uC870 \uC911\uC2EC \uC885\uBAA9", value: focusIndex, onChange: (e) => setFocusIndex(Number(e.target.value)) }, snapshot.stocks.map((s, i) => /* @__PURE__ */ React.createElement("option", { key: s.id, value: i }, s.name))))), /* @__PURE__ */ React.createElement("div", { className: "acs-toolbar" }, /* @__PURE__ */ React.createElement("span", { title: `${focus?.name || "\uAE30\uC5C5 \uAD6C\uC870"}\uC758 \uC8FC\uC8FC\xB7\uCD9C\uC790 \uC5F0\uACB0` }, focus?.name || "\uAE30\uC5C5 \uAD6C\uC870", "\uC758 \uC8FC\uC8FC\xB7\uCD9C\uC790 \uC5F0\uACB0"), visible.some((n) => n.parent && isFlowEligibleRelation(n.relation)) && /* @__PURE__ */ React.createElement("button", { type: "button", "aria-pressed": flowPaused, "aria-label": flowPaused ? "\uC120 \uC6C0\uC9C1\uC784 \uCF1C\uAE30" : "\uC120 \uC6C0\uC9C1\uC784 \uBA48\uCD94\uAE30", onClick: () => setFlowPaused((v) => !v) }, flowPaused ? "\uC120 \uC6C0\uC9C1\uC784 \uCF1C\uAE30" : "\uC120 \uC6C0\uC9C1\uC784 \uBA48\uCD94\uAE30"), /* @__PURE__ */ React.createElement("button", { type: "button", "aria-pressed": includeStored, onClick: () => setIncludeStored((v) => !v) }, includeStored ? "\uC800\uC7A5 \uC790\uB8CC \uD3EC\uD568" : "\uC800\uC7A5 \uC790\uB8CC \uD568\uAED8 \uBCF4\uAE30"), /* @__PURE__ */ React.createElement("button", { type: "button", "aria-label": "\uAE30\uC5C5 \uAD6C\uC870 \uCD95\uC18C", onClick: () => zoomTo(camera.zoom / 1.2) }, "\u2212"), /* @__PURE__ */ React.createElement("output", { "aria-label": "\uAE30\uC5C5 \uAD6C\uC870 \uBC30\uC728" }, Math.round(camera.zoom * 100), "%"), /* @__PURE__ */ React.createElement("button", { type: "button", "aria-label": "\uAE30\uC5C5 \uAD6C\uC870 \uD655\uB300", onClick: () => zoomTo(camera.zoom * 1.2) }, "+"), /* @__PURE__ */ React.createElement("button", { type: "button", onClick: fit }, "\uD55C\uB208\uC5D0"), /* @__PURE__ */ React.createElement("button", { type: "button", onClick: () => setCollapsed(new Set(layout ? [...layout.byId].filter(([id, n]) => n.depth > 0 && id !== focus?.id).map(([id]) => id) : [])) }, "\uAC00\uC9C0 \uC811\uAE30")), /* @__PURE__ */ React.createElement("div", { className: "acs-main" }, /* @__PURE__ */ React.createElement(
    "div",
    {
      className: "acs-space",
      ref: space,
      tabIndex: 0,
      role: "group",
      "aria-label": "\uAE30\uC5C5 \uAD6C\uC870 \uC791\uC5C5\uD310 \xB7 \uBE48 \uACF5\uAC04 \uB4DC\uB798\uADF8\xB7\uB450 \uC190\uAC00\uB77D \uC4F8\uAE30\uB85C \uC774\uB3D9, \uD540\uCE58\uB85C \uD655\uB300\uCD95\uC18C",
      style: { backgroundSize: `${40 * camera.zoom}px ${40 * camera.zoom}px`, backgroundPosition: `${camera.x}px ${camera.y}px` },
      onPointerDown: (e) => {
        if (e.target.closest("button,a,select")) return;
        drag.current = { x: e.clientX, y: e.clientY, startX: camera.x, startY: camera.y, pointer: e.pointerId };
        e.currentTarget.setPointerCapture(e.pointerId);
      },
      onPointerMove: (e) => {
        const d = drag.current;
        if (d?.pointer === e.pointerId) setCamera((c) => ({ ...c, x: d.startX + e.clientX - d.x, y: d.startY + e.clientY - d.y }));
      },
      onPointerUp: (e) => {
        drag.current = null;
        if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
      },
      onPointerCancel: () => {
        drag.current = null;
      },
      onKeyDown: (e) => {
        if (e.target !== e.currentTarget) return;
        const d = { ArrowLeft: [40, 0], ArrowRight: [-40, 0], ArrowUp: [0, 40], ArrowDown: [0, -40] }[e.key];
        if (d) {
          e.preventDefault();
          setCamera((c) => ({ ...c, x: c.x + d[0], y: c.y + d[1] }));
        }
        if (["+", "=", "-"].includes(e.key)) {
          e.preventDefault();
          zoomTo(camera.zoom * (e.key === "-" ? 1 / 1.2 : 1.2));
        }
      }
    },
    !catalogue || error ? /* @__PURE__ */ React.createElement("div", { className: "acs-empty", role: "status" }, /* @__PURE__ */ React.createElement("strong", null, error ? "\uAE30\uC5C5 \uAD6C\uC870\uB97C \uBD88\uB7EC\uC624\uC9C0 \uBABB\uD588\uC5B4\uC694" : "\uAE30\uC5C5 \uAD6C\uC870\uB97C \uBD88\uB7EC\uC624\uACE0 \uC788\uC5B4\uC694"), error ? "\uD575\uC2EC \uC9C0\uB3C4\uB85C \uB3CC\uC544\uAC00\uAC70\uB098 \uC7A0\uC2DC \uD6C4 \uB2E4\uC2DC \uC5F4\uC5B4 \uC8FC\uC138\uC694." : "\uACF5\uAC1C \uC790\uB8CC\uC758 \uD68C\uC0AC\uC640 \uAD00\uACC4\uB97C \uD655\uC778\uD569\uB2C8\uB2E4.") : /* @__PURE__ */ React.createElement("div", { className: "acs-world", style: { transform: `translate(${camera.x}px,${camera.y}px) scale(${camera.zoom})` } }, /* @__PURE__ */ React.createElement("svg", { className: "acs-lines", "data-flow-paused": flowPaused, "aria-hidden": "true", width: "1", height: "1" }, visible.filter((n) => n.parent).map((n) => {
      const p = layout.byId.get(n.parent);
      const x1 = p.x + 112, y1 = p.y + 86, x2 = n.x + 112, y2 = n.y, middle = (y1 + y2) / 2, d = `M${x1} ${y1} V${middle} H${x2} V${y2}`, undated = n.relation?.status === "undated-snapshot", flow = isFlowEligibleRelation(n.relation);
      return /* @__PURE__ */ React.createElement(React.Fragment, { key: n.company.id }, /* @__PURE__ */ React.createElement("path", { d, "data-undated": undated }), flow && /* @__PURE__ */ React.createElement("path", { className: "acs-flow", d, "aria-hidden": "true" }));
    })), visible.map((n) => {
      const stock = snapshot.stocks.find((s) => s.ticker === n.company.ticker && s.market === n.company.market);
      const logo = brokenLogos.has(n.company.id) ? void 0 : n.company.id === "FOREIGN:solidigm-inc" ? "https://project-yw131.vercel.app/member-map-review/solidigm-logo.png" : imageData(stock?.logo) || logos[n.company.id];
      const flag2 = imageData(snapshot.flags[n.company.market || n.company.country || ""]);
      const r = n.relation, dated = r?.status === "source-dated" || r?.status === "official-undated", pct = r?.status === "source-dated" && typeof r?.ownershipPct === "number" ? ` \xB7 ${r.ownershipPct}%` : "";
      return /* @__PURE__ */ React.createElement("article", { key: n.company.id, className: "acs-card", "data-company": n.company.id, "data-focus": n.company.id === focus?.id, "data-dated": dated, style: { left: n.x, top: n.y } }, /* @__PURE__ */ React.createElement("span", { className: "acs-face", "aria-hidden": "true" }, logo ? /* @__PURE__ */ React.createElement("img", { className: "acs-logo", src: logo, alt: "", draggable: false, style: n.company.id === "FOREIGN:solidigm-inc" ? { objectFit: "cover", objectPosition: "left", height: 32 } : void 0, onError: () => setBrokenLogos((old) => new Set(old).add(n.company.id)) }) : n.company.name.slice(0, 1), flag2 && /* @__PURE__ */ React.createElement("img", { className: "acs-flag", src: flag2, alt: "", title: n.company.market === "KR" ? "\uD55C\uAD6D \uC0C1\uC7A5" : n.company.market === "US" ? "\uBBF8\uAD6D \uC0C1\uC7A5" : "\uC18C\uC7AC \uAD6D\uAC00", draggable: false })), /* @__PURE__ */ React.createElement("button", { type: "button", className: "acs-card-main", "aria-label": `${n.company.name} \xB7 ${r?.label || "\uC911\uC2EC \uD68C\uC0AC"}${pct} \xB7 \uADFC\uAC70 \uBCF4\uAE30`, onClick: () => setSelected(n.company.id) }, /* @__PURE__ */ React.createElement("span", { className: "acs-name", title: n.company.name }, n.company.name), /* @__PURE__ */ React.createElement("span", { className: "acs-role" }, n.company.id === focus?.id && r?.type === "major-shareholder" ? "\uC8FC\uC694 \uC8FC\uC8FC \uC9C0\uBD84" : n.company.id === focus?.id ? "\uC120\uD0DD \uC885\uBAA9" : r?.label || "\uC8FC\uC694 \uC8FC\uC8FC", pct), /* @__PURE__ */ React.createElement("span", { className: "acs-role" }, r ? r.asOf ? `\uAE30\uC900 ${r.asOf}` : r.status === "official-undated" ? "\uACF5\uC2DD \uC548\uB0B4 \xB7 \uAE30\uC900\uC77C \uBBF8\uD45C\uC2DC" : "\uC6D0\uBB38 \uAE30\uC900\uC77C \uBBF8\uD655\uC778" : n.company.id === focus?.id ? "\uC911\uC2EC \uC885\uBAA9" : "\uC8FC\uC8FC \uC5F0\uACB0")), !!n.children.length && /* @__PURE__ */ React.createElement(React.Fragment, null, /* @__PURE__ */ React.createElement("button", { type: "button", className: "acs-branch", "aria-label": `${n.company.name} \uAC00\uC9C0 ${collapsed.has(n.company.id) ? "\uD3BC\uCE58\uAE30" : "\uC811\uAE30"}`, "aria-expanded": !collapsed.has(n.company.id), onClick: () => setCollapsed((old) => {
        const next = new Set(old);
        next.has(n.company.id) ? next.delete(n.company.id) : next.add(n.company.id);
        return next;
      }) }, collapsed.has(n.company.id) ? "+" : "\u2212"), /* @__PURE__ */ React.createElement("span", { className: "acs-child-count" }, n.children.length, "\uAC1C")));
    }))
  ), selectedNode && /* @__PURE__ */ React.createElement("aside", { className: "acs-inspector", "aria-label": "\uAE30\uC5C5 \uAD00\uACC4 \uADFC\uAC70" }, /* @__PURE__ */ React.createElement("button", { className: "acs-inspector-close", type: "button", "aria-label": "\uAD00\uACC4 \uADFC\uAC70 \uB2EB\uAE30", onClick: () => setSelected(null) }, "\xD7"), /* @__PURE__ */ React.createElement("h2", null, selectedNode.company.name), selectedNode.relation ? /* @__PURE__ */ React.createElement(RelationshipProof, { relation: selectedNode.relation }) : /* @__PURE__ */ React.createElement("p", null, "\uC8FC\uC694 \uC8FC\uC8FC\uC640 \uCD9C\uC790 \uC790\uB8CC\uB97C \uC911\uC2EC\uC73C\uB85C \uC5F0\uACB0\uD569\uB2C8\uB2E4. \uD68C\uC0AC \uC774\uB984\uC774\uB098 \uAC19\uC740 \uADF8\uB8F9\uBA85\uB9CC\uC73C\uB85C \uC18C\uC720 \uAD00\uACC4\uB97C \uCD94\uAC00\uD558\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4."), !!selectedConnections.length && /* @__PURE__ */ React.createElement("section", { "aria-label": "\uC120\uD0DD \uD68C\uC0AC\uC758 \uC5F0\uACB0 \uC790\uB8CC" }, /* @__PURE__ */ React.createElement("h3", { style: { fontSize: 13, fontWeight: 700, margin: "22px 0 8px" } }, "\uC5F0\uACB0 \uC790\uB8CC ", selectedConnections.length, "\uAC74"), /* @__PURE__ */ React.createElement("p", null, "\uD654\uBA74\uC5D0\uC11C \uC0DD\uB7B5\uB41C \uC5F0\uACB0\uB3C4 \uC774 \uBAA9\uB85D\uC5D0\uC11C \uD655\uC778\uD560 \uC218 \uC788\uC5B4\uC694."), selectedConnections.map((r) => /* @__PURE__ */ React.createElement("details", { key: r.id, style: { padding: "10px 0" } }, /* @__PURE__ */ React.createElement("summary", { style: { cursor: "pointer", fontSize: 12, fontWeight: 700 } }, companyNames.get(r.to), " \xB7 ", r.label), /* @__PURE__ */ React.createElement(RelationshipProof, { relation: r })))))), /* @__PURE__ */ React.createElement("footer", { className: "acs-foot" }, /* @__PURE__ */ React.createElement("span", { className: "acs-key" }, /* @__PURE__ */ React.createElement("i", null), "\uACF5\uC2DD \uADFC\uAC70 \xB7 \uB0A0\uC9DC\uB294 \uAD00\uACC4\uBCC4 \uD655\uC778"), /* @__PURE__ */ React.createElement("span", { className: "acs-key", "data-kind": "undated" }, /* @__PURE__ */ React.createElement("i", null), "\uAE30\uC900\uC77C \uBBF8\uD655\uC778 \uC800\uC7A5 \uC790\uB8CC"), /* @__PURE__ */ React.createElement("span", null, checkFailed ? "\uCD5C\uADFC \uC870\uD68C \uC2E4\uD328 \xB7 \uD45C\uC2DC \uC911\uC778 \uADFC\uAC70 \uC720\uC9C0" : structureCoverageText(catalogue)), pendingCatalogue ? /* @__PURE__ */ React.createElement("button", { type: "button", onClick: () => {
    initialFocus.current = null;
    catalogueRef.current = pendingCatalogue;
    setCatalogue(pendingCatalogue);
    setPendingCatalogue(null);
  } }, "\uBCC0\uACBD \uC790\uB8CC \uBC18\uC601") : /* @__PURE__ */ React.createElement("button", { type: "button", disabled: checking, onClick: () => refreshRef.current?.() }, checking ? "\uC790\uB8CC \uD655\uC778 \uC911" : "\uC790\uB8CC \uD655\uC778"), /* @__PURE__ */ React.createElement("span", { className: "acs-status", role: "status" }, visible.length, "\uAC1C \uD68C\uC0AC", layout?.omitted ? ` \xB7 ${layout.omitted}\uAC1C \uC5F0\uACB0\uC740 \uD45C\uC2DC \uBC94\uC704 \uBC16` : "", layout && layout.byId.size === 1 ? " \xB7 \uACF5\uC2DD \uC5F0\uACB0 \uADFC\uAC70\uAC00 \uC81C\uACF5\uB418\uC9C0 \uC54A\uC558\uC5B4\uC694" : "")));
}
function useCompanyStructureBridge(owner) {
  const [view, setView] = React.useState(null);
  const [waiting, setWaiting] = React.useState(false);
  const request = React.useRef(null), timer = React.useRef(void 0);
  React.useEffect(() => {
    setView(null);
    setWaiting(false);
    request.current = null;
    if (!owner) return;
    const receive = (event) => {
      const frame = [...document.querySelectorAll("iframe")].find((f) => {
        try {
          return (f.matches("iframe[data-an-site-map]") || new URL(f.src).pathname === "/member-map-canvas") && f.contentWindow === event.source;
        } catch {
          return false;
        }
      });
      if (!frame || event.origin !== "null" || !event.data || event.data.type !== "an-company-structure-snapshot" || event.data.request !== request.current || !Array.isArray(event.data.stocks) || event.data.stocks.length > 30) return;
      const stocks = event.data.stocks.filter((s) => s && typeof s.name === "string" && s.name.length < 301 && typeof s.ticker === "string" && (s.market === "KR" && /^[A-Z0-9]{6}$/.test(s.ticker) || s.market === "US" && /^[A-Z][A-Z0-9.-]{0,11}$/.test(s.ticker))).map((s) => ({ id: s.market + ":" + s.ticker, ticker: s.ticker, market: s.market, name: s.name, logo: imageData(s.logo) }));
      if (!stocks.length) {
        setWaiting(false);
        return;
      }
      const flags = {};
      for (const code of ["KR", "US", "TW"]) {
        const data = imageData(event.data.flags?.[code]);
        if (data) flags[code] = data;
      }
      clearTimeout(timer.current);
      request.current = null;
      setWaiting(false);
      setView({ owner, snapshot: { stocks, flags } });
    };
    window.addEventListener("message", receive);
    return () => {
      window.removeEventListener("message", receive);
      clearTimeout(timer.current);
    };
  }, [owner]);
  function open() {
    const frame = [...document.querySelectorAll("iframe")].find((f) => {
      try {
        return f.matches("iframe[data-an-site-map]") || new URL(f.src).pathname === "/member-map-canvas";
      } catch {
        return false;
      }
    });
    if (!frame?.contentWindow) return;
    request.current = crypto.randomUUID();
    setWaiting(true);
    frame.contentWindow.postMessage({ type: "an-company-structure-request", request: request.current }, "*");
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      request.current = null;
      setWaiting(false);
    }, 4e3);
  }
  return { snapshot: view?.owner === owner ? view.snapshot : null, waiting, open, close: () => setView(null) };
}

// review/member-map/site-entry.tsx
var CANVAS_URL = "https://project-yw131.vercel.app/member-map-canvas";
var CSS3 = `.an-site-map{font:600 13px/1.6 Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;color:#191f28;width:100%;min-width:0}.an-site-map-nav{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:8px 12px;background:#fff}.an-site-map-nav a,.an-site-map-nav button{font-family:inherit;font-weight:700;font-size:13px;line-height:1.5;text-decoration:none;color:inherit;min-height:44px;padding:10px 12px;border:0;border-radius:10px;background:#f8f9fb;cursor:pointer;box-sizing:border-box}.an-site-map-nav button{margin-left:auto}.an-site-map-nav a:focus-visible,.an-site-map-nav button:focus-visible{outline:0;background:#e9edf2}.an-site-map-status{padding:16px 20px}.an-site-map-status a{color:#6c5ce7;font-weight:700}body[data-framer-theme=dark] .an-site-map{color:#e3e7ec}body[data-framer-theme=dark] .an-site-map-nav{background:#171c23}body[data-framer-theme=dark] .an-site-map-nav a,body[data-framer-theme=dark] .an-site-map-nav button{background:#1d242c}body[data-framer-theme=dark] .an-site-map-nav a:focus-visible,body[data-framer-theme=dark] .an-site-map-nav button:focus-visible{background:#303945}@media(hover:hover){.an-site-map-nav a:hover,.an-site-map-nav button:not(:disabled):hover{background:#f1f3f5}body[data-framer-theme=dark] .an-site-map-nav a:hover,body[data-framer-theme=dark] .an-site-map-nav button:not(:disabled):hover{background:#252c35}}`;
async function loadSiteCanvas(fetcher = fetch, signal) {
  const response = await fetcher(CANVAS_URL, { credentials: "omit", redirect: "error", referrerPolicy: "no-referrer", signal });
  if (!response.ok || !response.headers.get("content-type")?.toLowerCase().startsWith("text/html") || !response.body) throw Error("canvas-response");
  const reader = response.body.getReader(), parts = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 2 * 1024 * 1024) throw Error("canvas-size");
      parts.push(value);
    }
  } finally {
    await reader.cancel().catch(() => {
    });
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const part of parts) {
    bytes.set(part, offset);
    offset += part.length;
  }
  const html = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  if (!html.startsWith("<!doctype html>") || !html.includes("__ALPHANEST_FRAME_NONCE__") || !html.includes("connect-src blob: data:")) throw Error("canvas-shape");
  return html;
}
function PublicMindmap({ style }) {
  const isStatic = useIsStaticRenderer2();
  const [owner, setOwner] = React3.useState(null);
  const [template, setTemplate] = React3.useState("");
  const [failed, setFailed] = React3.useState(false);
  const [attempt, setAttempt] = React3.useState(0);
  const structure = useCompanyStructureBridge(owner);
  const back = typeof window === "undefined" ? "/mindmap" : portfolioMapEntryPath(window.location.search).replace("/member-map-review", "/mindmap");
  React3.useEffect(() => {
    if (isStatic) return;
    const sync = () => React3.startTransition(() => setOwner(readMapSession()?.userId || null));
    sync();
    window.addEventListener("verity_auth_change", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("verity_auth_change", sync);
      window.removeEventListener("storage", sync);
    };
  }, [isStatic]);
  React3.useEffect(() => {
    if (isStatic) return;
    const controller = new AbortController();
    React3.startTransition(() => setFailed(false));
    void loadSiteCanvas(fetch, controller.signal).then((value) => {
      if (!controller.signal.aborted) React3.startTransition(() => setTemplate(value));
    }, () => {
      if (!controller.signal.aborted) React3.startTransition(() => setFailed(true));
    });
    return () => controller.abort();
  }, [isStatic, attempt]);
  return /* @__PURE__ */ React3.createElement("section", { className: "an-site-map", style: { ...style, position: "relative" }, "aria-label": "\uB9C8\uC778\uB4DC\uB9F5 \uBCA0\uD0C0" }, /* @__PURE__ */ React3.createElement("style", null, CSS3), /* @__PURE__ */ React3.createElement("nav", { className: "an-site-map-nav", "aria-label": "\uB9C8\uC778\uB4DC\uB9F5 \uBCF4\uAE30" }, /* @__PURE__ */ React3.createElement("a", { href: "/nest" }, "\uB465\uC9C0\uB85C"), /* @__PURE__ */ React3.createElement("strong", null, "\uB9C8\uC778\uB4DC\uB9F5 \uBCA0\uD0C0"), owner && /* @__PURE__ */ React3.createElement("button", { type: "button", "aria-pressed": !!structure.snapshot, disabled: structure.waiting || !template, onClick: structure.open }, structure.waiting ? "\uC9C0\uB3C4 \uD655\uC778 \uC911\u2026" : "\uAE30\uC5C5 \uAD6C\uC870")), isStatic ? /* @__PURE__ */ React3.createElement("p", { className: "an-site-map-status" }, "\uC0AC\uC774\uD2B8\uC758 \uAE30\uC874 \uB85C\uADF8\uC778\uC73C\uB85C \uB0B4 \uC885\uBAA9\uACFC \uC9C0\uB3C4 \uAE30\uB85D\uC744 \uBD88\uB7EC\uC635\uB2C8\uB2E4.") : /* @__PURE__ */ React3.createElement(React3.Fragment, null, !owner && /* @__PURE__ */ React3.createElement("p", { className: "an-site-map-status", role: "status" }, "\uB85C\uADF8\uC778 \uC0C1\uD0DC\uB97C \uD655\uC778\uD574 \uC8FC\uC138\uC694. ", /* @__PURE__ */ React3.createElement("a", { href: "/login?next=" + encodeURIComponent(back) }, "\uC54C\uD30C\uB124\uC2A4\uD2B8 \uB85C\uADF8\uC778")), !template && /* @__PURE__ */ React3.createElement("p", { className: "an-site-map-status", role: "status" }, failed ? /* @__PURE__ */ React3.createElement(React3.Fragment, null, "\uC791\uC5C5\uD310\uC744 \uBD88\uB7EC\uC624\uC9C0 \uBABB\uD588\uC5B4\uC694. ", /* @__PURE__ */ React3.createElement("button", { type: "button", onClick: () => React3.startTransition(() => setAttempt((value) => value + 1)) }, "\uB2E4\uC2DC \uBD88\uB7EC\uC624\uAE30")) : "\uC791\uC5C5\uD310\uC744 \uC900\uBE44\uD558\uACE0 \uC788\uC5B4\uC694."), template && /* @__PURE__ */ React3.createElement(PublicPortfolioPrototype, { template }), owner && structure.snapshot && /* @__PURE__ */ React3.createElement(CompanyStructureView, { snapshot: structure.snapshot, onClose: structure.close })));
}
addPropertyControls2(PublicMindmap, {});

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
/** @preserve Same-origin mindmap entry: preserve existing sessions, data, notes, positions and drafts.
 * @framerIntrinsicWidth 1200
 * @framerIntrinsicHeight 900
 * @framerSupportedLayoutWidth any-prefer-fixed
 * @framerSupportedLayoutHeight auto
 */

/**
 * Same-origin AlphaNest mindmap; keep the accepted renderer and existing session.
 * @framerIntrinsicWidth 1200
 * @framerIntrinsicHeight 900
 * @framerSupportedLayoutWidth any-prefer-fixed
 * @framerSupportedLayoutHeight auto
 */
export default function AlphaNestMindmap({ style }: { style?: SiteReact.CSSProperties }) {
  return <PublicMindmap style={style} />;
}
sitePropertyControls(AlphaNestMindmap, {});

// 🏁 The endgame on the Ventures screen: market share in your sector, partnerships, offers to buy a company (a paper
// ticket with Accept / Decline for its CEO), the IPO button and its celebration, and on another company's page what
// your company could do with it (buy it, partner, poach). Every button sends the existing /company command.

import { $, el, str } from "./dom.js";
import * as V from "./ventureslogic.js";
import { act, announce, button, confirmStep, draft, render, setDraft } from "./ventures.js";
import { field, formError } from "./ventureshq.js";

/** 🥧 The sector's market: each company's share, and the rest of the market (the incumbents). */
export function marketPanel(co) {
  const rows = Array.isArray(co.market) ? co.market : [];
  if (!rows.length) return null;
  const total = rows.reduce((sum, r) => sum + Number(r.customers || 0), 0) + Number(co.incumbents || 0);
  const bar = (name, share, mine) => el("li", { class: `vs-share${mine ? " mine" : ""}` },
    el("span", { class: "vs-row-name", text: str(name) }),
    el("span", { class: "vs-meter", "aria-hidden": "true" }, el("span", { class: "vs-meter-fill", "data-w": String(Math.round(share * 100)) })),
    el("span", { class: "num", text: `${(share * 100).toFixed(share < 0.1 ? 1 : 0)}%` }));
  const list = el("ul", { class: "vs-list vs-shares", "aria-label": "Market share" },
    ...rows.map((r) => bar(r.name, Number(r.share) || 0, r.id === co.id)),
    bar("The rest of the market", Number(co.incumbents || 0) / (total || 1), false));
  for (const fill of list.querySelectorAll(".vs-meter-fill")) fill.style.width = `${fill.dataset.w}%`;
  return el("section", { class: "vs-panel", "aria-labelledby": "vs-market" },
    el("h3", { id: "vs-market", class: "gs-h3", text: `🏁 ${str(co.sector_name)} market` }), list,
    el("p", { class: "gs-muted", text: "Strong rivals in your sector take some of your new customers." }));
}

/** 🤝 Partnerships and offers to buy this company (the members see them). */
export function dealsInbox(co) {
  const ceo = co.you && co.you.ceo;
  const parts = [];
  const offer = co.acquisition_offer;
  if (offer) {
    const yes = async () => {
      if (await confirmStep({ title: `🤝 Sell ${co.name}?`, text: `${str(offer.buyer)} pays ${V.money(offer.amount)}. Every player who owns ` +
        "a part gets an exit in 🪙 now, and the company ends (its chat stays). This can't be undone.", yes: "Sell", danger: true })) {
        act("sell-yes", "/company sell accept");
      }
    };
    parts.push(el("article", { class: "vs-sheet vs-offer", "aria-labelledby": "vs-offer-title" },
      el("h4", { id: "vs-offer-title", class: "ticket-title", tabindex: "-1", text: `🤝 ${str(offer.buyer)} wants to buy ${str(co.name)}` }),
      el("dl", { class: "vs-sheet-facts" }, el("dt", { text: "Price" }), el("dd", { text: V.money(offer.amount) }),
        el("dt", { text: "Valued" }), el("dd", { text: V.money(co.valuation) })),
      el("p", { class: "ticket-muted", text: `Expires ${V.countdown(offer.expires)}.` }),
      ceo ? el("div", { class: "row" }, button("Sell the company", yes, { key: "sell-yes", danger: true }),
        button("Decline", () => act("sell-no", "/company sell decline"), { key: "sell-no", label: "Decline the offer" }))
        : el("p", { class: "ticket-muted", text: "⏳ The CEO decides." })));
  }
  const partner = co.partner || {};
  if (partner.offer_from && !partner.with) {
    parts.push(el("div", { class: "vs-panel vs-inline" },
      el("p", { text: `🤝 ${str(partner.offer_from)} offers a partnership: more new customers for both for a week.` }),
      ceo ? button("Accept the partnership", () => act("partner-yes", `/company partner accept ${str(partner.offer_from)}`), { key: "partner-yes", small: true })
        : el("p", { class: "gs-muted", text: "The CEO decides." })));
  }
  if (partner.with) parts.push(el("p", { class: "vs-note", text: `🤝 Partners with ${str(partner.with)} until day ${str(partner.until)}.` }));
  return parts.length ? el("div", { class: "vs-col" }, ...parts) : null;
}

/** 🔔 The IPO: the button when it's ready, the ticker once public. */
export function ipoPanel(co) {
  if (co.ipo && !co.ipo.listed) {
    return el("p", { class: "vs-note", text: `🔕 Was public as ${str(co.ipo.symbol)} (delisted).` });
  }
  if (co.ipo) {
    return el("section", { class: "vs-plate vs-ipo", "aria-labelledby": "vs-ipo" },
      el("h3", { id: "vs-ipo", class: "gs-h3", text: `🔔 Public as ${str(co.ipo.symbol)}` }),
      el("p", {}, el("span", { class: "vs-big", text: `${str(co.ipo.price)} 🪙` }), el("span", { class: "vs-big-label", text: " a share" })),
      el("p", { class: "gs-muted", text: `It went public at ${V.money(co.ipo.value)}. Everyone can trade it in 📈 Market.` }),
      button("📈 Open the market", () => $("market-open")?.click(), { key: "open-market", small: true }));
  }
  const ready = co.ipo_ready;
  if (!ready) return null;
  const ring = async () => {
    if (await confirmStep({ title: "🔔 Go public?", text: `${co.name} lists on the stock market. ${str(ready.new_percent)}% new shares are sold to the public ` +
      "for cash, and every player who owns a part gets an exit in 🪙 now.", yes: "Ring the bell" })) act("ipo", "/company ipo");
  };
  return el("section", { class: "vs-plate vs-ipo", "aria-labelledby": "vs-ipo" },
    el("h3", { id: "vs-ipo", class: "gs-h3", text: "🔔 The IPO" }),
    el("p", { class: "gs-muted", text: "Series C with every IPO milestone: you can list the company on the stock market." }),
    button("🔔 Ring the bell", ring, { key: "ipo", primary: ready.ok, disabled: !ready.ok, why: str(ready.why) }));
}

/** 🎉 The IPO moment (once, on the HQ of the company that just went public). */
export function celebrate(co) {
  announce(`🔔 ${co.name} is public as ${co.ipo.symbol}! Valued ${V.money(co.ipo.value)}.`);
  const old = $("vs-party");
  if (old) old.remove();
  const close = () => { party.remove(); $("ventures-title")?.focus(); };
  const party = el("div", { id: "vs-party", class: "vs-party", role: "dialog", "aria-modal": "false", "aria-labelledby": "vs-party-title" },
    el("div", { class: "vs-confetti", "aria-hidden": "true" }, ...Array.from({ length: 24 }, (_, i) => el("span", { class: `c${i % 6}` }))),
    el("div", { class: "vs-party-card" },
      el("p", { class: "vs-party-bell", "aria-hidden": "true", text: "🔔" }),
      el("h3", { id: "vs-party-title", class: "vs-party-title", tabindex: "-1", text: `${co.name} is PUBLIC!` }),
      el("p", { class: "vs-party-text", text: `Trading as ${co.ipo.symbol} at ${co.ipo.price} 🪙 · valued ${V.money(co.ipo.value)}` }),
      el("button", { class: "btn btn-primary", type: "button", text: "🎉 Let's go", onclick: close })));
  party.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.stopPropagation(); close(); } });
  $("ventures-screen").append(party);
  $("vs-party-title").focus();
}

/** What my company could do with this one (only its CEO sees it). */
export function dealsWith(co) {
  const d = co.deals;
  if (!d) return null;
  const buy = async () => {
    const amount = V.counterLine(draft("acquire-amount"));
    if (!amount) {
      setDraft("acquire-amount-error", "Type a price like 5M or 750K.");
      render();
      document.getElementById("vs-acquire")?.focus();
      return;
    }
    setDraft("acquire-amount-error", "");
    const price = amount.replace("/offer counter ", "");
    if (await confirmStep({ title: `🤝 Offer to buy ${co.name}?`, text: `${d.company} offers ${price}. Their CEO has ${str(d.offer_hours)} h to say yes; ` +
      "the money leaves your cash only if they do.", yes: "Send the offer" })) act("acquire", `/company acquire ${co.name} ${price}`);
  };
  const error = draft("acquire-amount-error");
  return el("section", { class: "vs-panel", "aria-labelledby": "vs-deals" },
    el("h3", { id: "vs-deals", class: "gs-h3", text: `🤝 ${str(d.company)} and ${str(co.name)}` }),
    el("label", { for: "vs-acquire", class: "gs-h4", text: `Buy it (${V.money(d.acquire_min)} to ${V.money(d.acquire_max)})` }),
    el("div", { class: "row" },
      field("acquire-amount", { id: "vs-acquire", placeholder: "like 5M", "aria-invalid": error ? "true" : undefined,
        "aria-describedby": error ? "acquire-amount-error" : undefined }),
      button("Make an offer", buy, { key: "acquire", disabled: Boolean(d.acquire_why), why: str(d.acquire_why) })),
    formError("acquire-amount"),
    el("div", { class: "row" }, button("🤝 Offer a partnership", () => act("partner", `/company partner ${co.name}`),
      { key: "partner", small: true, disabled: Boolean(d.partner_why), why: str(d.partner_why) })),
    d.poach_kinds.length ? el("div", { class: "row" }, el("span", { class: "gs-muted", text: `🎣 Poach (${str(d.poach_ap)} ⚡, ${V.money(d.poach_cost)}):` }),
      ...d.poach_kinds.map((kind) => button(kind, () => act(`poach:${kind}`, `/company poach ${co.name} ${kind}`),
        { key: `poach:${kind}`, small: true, label: `Poach their ${kind} staff` }))) : null);
}

const paths = {
  home: "M3 10l9-7 9 7M5 9v12h5v-7h4v7h5V9",
  documents: "M6 3h8l4 4v14H6zM14 3v5h4",
  add: "M12 5v14M5 12h14",
  scanner: "M5 9V3h14v6M4 10h16v9H4zM7 16h10M7 13h1",
  pc: "M3 4h18v13H3zM8 21h8M12 17v4",
  settings: "M12 8a4 4 0 100 8 4 4 0 000-8M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2",
  history: "M3 12a9 9 0 119 9M3 4v8h8M12 6v6l4 2",
  search: "M20 20l-5-5M17 10a7 7 0 11-14 0 7 7 0 0114 0",
  storage: "M4 3h16v7H4zM4 14h16v7H4zM7 6h1M7 17h1",
  bell: "M5 17h14l-2-3V9a5 5 0 00-10 0v5zM10 21h4",
  menu: "M4 6h16M4 12h16M4 18h16",
  check: "M5 12l4 4 10-10",
  copy: "M8 8h13v13H8zM3 16V3h13",
  clock: "M12 6v6l4 2M21 12a9 9 0 11-18 0 9 9 0 0118 0"
};
function wineIdentity() {
  try {
    return localStorage.getItem("docpilot.actor_name")?.trim() || "";
  } catch {
    return "";
  }
}
function WineIcon({ name }) {
  return /* @__PURE__ */ o.jsx("svg", { width: "23", height: "23", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "1.7", strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": "true", children: /* @__PURE__ */ o.jsx("path", { d: paths[name] || paths.documents }) });
}
export function WineShell({ page, section, docs, search, onSearch, navigate, controls, children, aiAvailable = false }) {
  const [open, setOpen] = N.useState(false);
  const actor = wineIdentity();
  const companyNames = Array.from(new Set(docs.map((d) => d.legal_entity_name).filter(Boolean)));
  const pending = docs.filter((d) => ["TO_VALIDATE", "ERROR", "DUPLICATE"].includes(d.status)).length;
  const go = (p, s, f) => {
    navigate(p, s, f);
    setOpen(false);
  };
  N.useEffect(() => {
    const handler = (e) => {
      if (e.key === "Escape") setOpen(false);
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        document.getElementById("wine-search")?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  N.useEffect(() => {
    const sync = () => {
      const frame = document.querySelector('iframe[title="Connexion IA"]');
      if (!frame) return;
      try {
        const doc = frame.contentDocument;
        if (!doc?.head) return;
        let style = doc.getElementById("docpilot-wine-theme");
        if (!style) {
          style = doc.createElement("style");
          style.id = "docpilot-wine-theme";
          doc.head.appendChild(style);
        }
        style.textContent = document.documentElement.dataset.theme === "dark" ? "body{background:#242026!important;color:#f7f0f2!important}h1,h2,h3,p,label,small,strong,span{color:#f7f0f2!important}input,select,textarea{background:#322832!important;color:#f7f0f2!important;border-color:#6a4656!important}a{color:#f0adc0!important}" : "body{background:#fff;color:#171c2b}";
      } catch {
      }
    };
    const observer = new MutationObserver(sync);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const timer = window.setTimeout(() => {
      const frame = document.querySelector('iframe[title="Connexion IA"]');
      frame?.addEventListener("load", sync);
      sync();
    }, 0);
    return () => {
      observer.disconnect();
      window.clearTimeout(timer);
      document.querySelector('iframe[title="Connexion IA"]')?.removeEventListener("load", sync);
    };
  }, [page, section]);
  const nav = (p, label, icon, s) => /* @__PURE__ */ o.jsxs("button", { type: "button", className: "wine-nav-link " + (page === p && (!s || section === s) ? "active" : ""), onClick: () => go(p, s), children: [
    /* @__PURE__ */ o.jsx(WineIcon, { name: icon }),
    /* @__PURE__ */ o.jsx("span", { children: label }),
    p === "documents" && !s && pending > 0 && /* @__PURE__ */ o.jsx("b", { className: "wine-badge", children: pending })
  ] });
  return /* @__PURE__ */ o.jsxs("div", { className: "wine-layout " + (open ? "menu-open" : ""), children: [
    open && /* @__PURE__ */ o.jsx("button", { className: "wine-scrim", onClick: () => setOpen(false), "aria-label": "Fermer le menu" }),
    /* @__PURE__ */ o.jsxs("aside", { className: "wine-sidebar", "aria-label": "Menu DocPilot", children: [
      /* @__PURE__ */ o.jsxs("button", { className: "wine-brand", onClick: () => go("home"), children: [
        /* @__PURE__ */ o.jsx("span", { className: "wine-mark", children: /* @__PURE__ */ o.jsx(WineIcon, { name: "documents" }) }),
        /* @__PURE__ */ o.jsxs("span", { children: [
          /* @__PURE__ */ o.jsx("strong", { children: "DocPilot" }),
          /* @__PURE__ */ o.jsx("small", { children: "Vos documents. Bien class\xE9s." })
        ] })
      ] }),
      /* @__PURE__ */ o.jsxs("nav", { "aria-label": "Navigation principale", children: [
        nav("home", "Tableau de bord", "home"),
        nav("documents", "Documents", "documents"),
        /* @__PURE__ */ o.jsxs("div", { className: "wine-nav-group", children: [
          /* @__PURE__ */ o.jsx("span", { children: "AJOUTER UN DOCUMENT" }),
          nav("import", "Importer un fichier", "add"),
          nav("scanner", "Scanner une facture", "scanner"),
          nav("pc", "Rechercher sur ce PC", "pc")
        ] }),
        /* @__PURE__ */ o.jsxs("div", { className: "wine-nav-group", children: [
          /* @__PURE__ */ o.jsx("span", { children: "PARAM\xC8TRES" }),
          nav("settings", "Soci\xE9t\xE9s", "settings", "entities"),
          nav("settings", "Fournisseurs", "settings", "creditors"),
          nav("settings", "Stockage et dossiers", "storage", "storage"),
          aiAvailable && nav("settings", "Intelligence artificielle", "settings", "ia"),
          nav("settings", "Classement et application", "settings", "system")
        ] }),
        nav("history", "Historique", "history")
      ] }),
      /* @__PURE__ */ o.jsxs("div", { className: "wine-side-bottom", children: [
        /* @__PURE__ */ o.jsxs("p", { children: [
          "Un document d\xE9pos\xE9.",
          /* @__PURE__ */ o.jsx("br", {}),
          /* @__PURE__ */ o.jsx("em", { children: "Une organisation simplifi\xE9e." })
        ] }),
        /* @__PURE__ */ o.jsx("a", { href: "mailto:alain.eric@ik.me?subject=DocPilot", children: "Copyright \xA9 Aston Software 2026" })
      ] })
    ] }),
    /* @__PURE__ */ o.jsxs("div", { className: "wine-body", children: [
      /* @__PURE__ */ o.jsxs("header", { className: "wine-topbar", children: [
        /* @__PURE__ */ o.jsx("button", { className: "wine-menu-button", onClick: () => setOpen(!open), "aria-label": "Ouvrir le menu", "aria-expanded": open, children: /* @__PURE__ */ o.jsx(WineIcon, { name: "menu" }) }),
        /* @__PURE__ */ o.jsxs("form", { className: "wine-search", onSubmit: (e) => {
          e.preventDefault();
          go("documents", void 0, "all");
        }, children: [
          /* @__PURE__ */ o.jsx(WineIcon, { name: "search" }),
          /* @__PURE__ */ o.jsx("input", { id: "wine-search", value: search, onChange: (e) => onSearch(e.target.value), placeholder: "Rechercher un document, un fournisseur\u2026", "aria-label": "Rechercher un document" }),
          /* @__PURE__ */ o.jsx("kbd", { children: "\u2318 K" })
        ] }),
        /* @__PURE__ */ o.jsxs("select", { className: "wine-top-company", "aria-label": "Rechercher par soci\xE9t\xE9", value: companyNames.includes(search) ? search : "", onChange: (e) => {
          onSearch(e.target.value);
          go("documents", void 0, "all");
        }, children: [
          /* @__PURE__ */ o.jsx("option", { value: "", children: "Toutes les soci\xE9t\xE9s" }),
          companyNames.map((name) => /* @__PURE__ */ o.jsx("option", { children: name }, name))
        ] }),
        /* @__PURE__ */ o.jsxs("button", { className: "wine-notifications", onClick: () => go("documents", void 0, "attention"), "aria-label": pending + " documents \xE0 v\xE9rifier", children: [
          /* @__PURE__ */ o.jsx(WineIcon, { name: "bell" }),
          pending > 0 && /* @__PURE__ */ o.jsx("b", { className: "wine-badge", children: pending })
        ] }),
        /* @__PURE__ */ o.jsx("div", { className: "wine-controls", children: controls }),
        /* @__PURE__ */ o.jsx("button", { className: "wine-avatar", onClick: () => go("settings", "system"), "aria-label": "Identit\xE9 de ce poste", title: actor || "Configurer votre nom", children: actor ? actor.split(/\s+/).slice(0, 2).map((word) => word[0]).join("").toUpperCase() : "DP" })
      ] }),
      /* @__PURE__ */ o.jsx("main", { className: "pilot-main wine-main", children }, page + section)
    ] })
  ] });
}
export function WineDashboard({ docs, navigate, onOpen, fetcher = fetch, storageUrl = "/api/v1/workspace" }) {
  const [company, setCompany] = N.useState("");
  const [activity, setActivity] = N.useState([]);
  const [activityError, setActivityError] = N.useState(false);
  const [storage, setStorage] = N.useState(null);
  N.useEffect(() => {
    let live = true;
    let active = false;
    async function load() {
      if (active) return;
      active = true;
      try {
        const [a, w] = await Promise.allSettled([fetcher("/api/v1/audit?limit=4").then((r) => {
          if (!r.ok) throw Error();
          return r.json();
        }), fetcher(storageUrl).then((r) => {
          if (!r.ok) throw Error();
          return r.json();
        })]);
        if (!live) return;
        if (a.status === "fulfilled") {
          setActivity(Array.isArray(a.value) ? a.value : []);
          setActivityError(false);
        } else setActivityError(true);
        if (w.status === "fulfilled") setStorage(Array.isArray(w.value) ? w.value.length ? { message: "Dossiers configur\xE9s \xB7 \xE0 v\xE9rifier", root: w.value[0].root_path } : null : w.value);
        else setStorage(null);
      } finally {
        active = false;
      }
    }
    load();
    const timer = setInterval(load, 1e4);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [fetcher, storageUrl]);
  const companies = Array.from(new Set(docs.map((d) => d.legal_entity_name).filter(Boolean)));
  N.useEffect(() => {
    if (company && !companies.includes(company)) setCompany("");
  }, [company, companies.join("|")]);
  const visible = docs.filter((d) => !company || d.legal_entity_name === company);
  const filed = docs.filter((d) => ["FILED", "STORED", "VALIDATED"].includes(d.status)).length;
  const pending = docs.filter((d) => ["TO_VALIDATE", "ERROR", "DUPLICATE"].includes(d.status)).length;
  const duplicates = docs.filter((d) => d.status === "DUPLICATE" || d.archive_duplicate?.found).length;
  const groups = Array.from(new Set(docs.map((d) => d.legal_entity_name || "Non d\xE9finie"))).map((name) => ({ name, count: docs.filter((d) => (d.legal_entity_name || "Non d\xE9finie") === name).length })).sort((a, b) => b.count - a.count);
  const colors = ["#641b2c", "#aa5966", "#d9acb2", "#b28e65", "#788d82"];
  let total = 0;
  const stops = groups.map((g, i) => {
    const start = total;
    total += docs.length ? g.count / docs.length * 100 : 0;
    return `${colors[i % colors.length]} ${start}% ${total}%`;
  }).join(",");
  const stat = (label, value, icon, filter) => /* @__PURE__ */ o.jsxs("button", { className: "wine-stat", onClick: () => navigate("documents", void 0, filter), children: [
    /* @__PURE__ */ o.jsx("span", { className: "wine-stat-icon " + icon, children: /* @__PURE__ */ o.jsx(WineIcon, { name: icon }) }),
    /* @__PURE__ */ o.jsxs("span", { children: [
      /* @__PURE__ */ o.jsx("strong", { children: value.toLocaleString("fr-CH") }),
      /* @__PURE__ */ o.jsx("span", { children: label }),
      /* @__PURE__ */ o.jsx("small", { children: label === "Class\xE9s" && docs.length ? Math.round(filed / docs.length * 100) + " % des documents" : "Voir les documents \u2192" })
    ] })
  ] });
  const actions = { filed: "Document class\xE9", auto_filed: "Classement automatique", manual_received: "Document import\xE9", duplicate_detected: "Doublon d\xE9tect\xE9", field_corrected: "Information corrig\xE9e", document_deleted: "Document retir\xE9", entity_created: "Soci\xE9t\xE9 cr\xE9\xE9e", creditor_created: "Fournisseur cr\xE9\xE9", validated: "Classement confirm\xE9", setting_changed: "R\xE9glage modifi\xE9", detected: "Donn\xE9es d\xE9tect\xE9es", hashed: "Empreinte calcul\xE9e", extracted: "Texte extrait", converted_to_pdf: "Conversion en PDF", filed_dry_run: "Classement simul\xE9", error: "Erreur de traitement" };
  return /* @__PURE__ */ o.jsxs("div", { className: "wine-dashboard", children: [
    /* @__PURE__ */ o.jsxs("section", { className: "wine-hero", children: [
      /* @__PURE__ */ o.jsx("span", { className: "wine-eyebrow", children: "VOTRE ESPACE DOCUMENTAIRE" }),
      /* @__PURE__ */ o.jsxs("h1", { children: [
        "Bonjour",
        wineIdentity() ? " " + wineIdentity() : "",
        ","
      ] }),
      /* @__PURE__ */ o.jsx("p", { children: "Vos factures, au bon endroit." }),
      /* @__PURE__ */ o.jsx("blockquote", { children: "Moins de classement. Plus de temps pour vous." }),
      /* @__PURE__ */ o.jsxs("div", { className: "wine-hero-signature", "aria-hidden": "true", children: [
        "DocPilot",
        /* @__PURE__ */ o.jsx("small", { children: "L\u2019ART DE BIEN ORGANISER" })
      ] })
    ] }),
    /* @__PURE__ */ o.jsxs("section", { className: "wine-stats", "aria-label": "Vue d\u2019ensemble", children: [
      stat("Documents", docs.length, "documents", "all"),
      stat("\xC0 v\xE9rifier", pending, "clock", "attention"),
      stat("Class\xE9s", filed, "check", "filed"),
      stat("Doublons", duplicates, "copy", "duplicates"),
      /* @__PURE__ */ o.jsxs("button", { className: "wine-stat wine-storage-stat", onClick: () => navigate("settings", "storage"), children: [
        /* @__PURE__ */ o.jsx("span", { className: "wine-stat-icon", children: /* @__PURE__ */ o.jsx(WineIcon, { name: "storage" }) }),
        /* @__PURE__ */ o.jsxs("span", { children: [
          /* @__PURE__ */ o.jsx("b", { children: "Stockage" }),
          /* @__PURE__ */ o.jsx("strong", { className: "wine-storage-state", children: storage?.ready ? "Dossier v\xE9rifi\xE9" : storage?.message === "Dossiers configur\xE9s \xB7 \xE0 v\xE9rifier" ? "Configur\xE9 \xB7 \xE0 v\xE9rifier" : storage ? "\xC0 v\xE9rifier" : "\xC0 configurer / v\xE9rifier" }),
          /* @__PURE__ */ o.jsx("small", { title: storage?.root || storage?.message, children: storage?.root || "Ouvrir les dossiers \u2192" })
        ] })
      ] })
    ] }),
    /* @__PURE__ */ o.jsxs("section", { className: "wine-actions", "aria-label": "Actions rapides", children: [
      /* @__PURE__ */ o.jsxs("button", { className: "wine-action primary", onClick: () => navigate("import"), children: [
        /* @__PURE__ */ o.jsx(WineIcon, { name: "add" }),
        /* @__PURE__ */ o.jsxs("span", { children: [
          /* @__PURE__ */ o.jsx("strong", { children: "Ajouter un document" }),
          /* @__PURE__ */ o.jsx("small", { children: "PDF, photos et documents Office" })
        ] }),
        /* @__PURE__ */ o.jsx("b", { children: "\u203A" })
      ] }),
      /* @__PURE__ */ o.jsxs("button", { className: "wine-action", onClick: () => navigate("scanner"), children: [
        /* @__PURE__ */ o.jsx(WineIcon, { name: "scanner" }),
        /* @__PURE__ */ o.jsxs("span", { children: [
          /* @__PURE__ */ o.jsx("strong", { children: "Scanner une facture" }),
          /* @__PURE__ */ o.jsx("small", { children: "Num\xE9riser, v\xE9rifier et classer" })
        ] }),
        /* @__PURE__ */ o.jsx("b", { children: "\u203A" })
      ] }),
      /* @__PURE__ */ o.jsxs("button", { className: "wine-action", onClick: () => navigate("pc"), children: [
        /* @__PURE__ */ o.jsx(WineIcon, { name: "pc" }),
        /* @__PURE__ */ o.jsxs("span", { children: [
          /* @__PURE__ */ o.jsx("strong", { children: "Factures sur ce PC" }),
          /* @__PURE__ */ o.jsx("small", { children: "Retrouver les fichiers \xE0 traiter" })
        ] }),
        /* @__PURE__ */ o.jsx("b", { children: "\u203A" })
      ] })
    ] }),
    /* @__PURE__ */ o.jsxs("div", { className: "wine-dashboard-grid", children: [
      /* @__PURE__ */ o.jsxs("section", { className: "wine-card wine-recent", children: [
        /* @__PURE__ */ o.jsxs("div", { className: "wine-card-heading", children: [
          /* @__PURE__ */ o.jsx("h2", { children: "Documents r\xE9cents" }),
          /* @__PURE__ */ o.jsx("button", { onClick: () => navigate("documents"), children: "Voir tous \u2192" })
        ] }),
        /* @__PURE__ */ o.jsxs("select", { className: "wine-company-filter", value: company, onChange: (e) => setCompany(e.target.value), "aria-label": "Filtrer les documents r\xE9cents par soci\xE9t\xE9", children: [
          /* @__PURE__ */ o.jsx("option", { value: "", children: "Toutes les soci\xE9t\xE9s" }),
          companies.map((name) => /* @__PURE__ */ o.jsx("option", { children: name }, name))
        ] }),
        /* @__PURE__ */ o.jsx("div", { className: "wine-table-scroll", children: /* @__PURE__ */ o.jsxs("table", { className: "wine-table", children: [
          /* @__PURE__ */ o.jsx("thead", { children: /* @__PURE__ */ o.jsxs("tr", { children: [
            /* @__PURE__ */ o.jsx("th", { children: "Document" }),
            /* @__PURE__ */ o.jsx("th", { children: "Fournisseur" }),
            /* @__PURE__ */ o.jsx("th", { children: "Soci\xE9t\xE9" }),
            /* @__PURE__ */ o.jsx("th", { children: "Date" }),
            /* @__PURE__ */ o.jsx("th", { children: "Montant" }),
            /* @__PURE__ */ o.jsx("th", { children: "Statut" })
          ] }) }),
          /* @__PURE__ */ o.jsx("tbody", { children: visible.slice(0, 6).map((d) => /* @__PURE__ */ o.jsxs("tr", { children: [
            /* @__PURE__ */ o.jsx("td", { children: /* @__PURE__ */ o.jsxs("button", { onClick: () => onOpen(d.id), children: [
              /* @__PURE__ */ o.jsx("span", { className: "wine-pdf", children: "PDF" }),
              /* @__PURE__ */ o.jsx("span", { children: d.final_filename || d.proposed_filename || d.original_filename })
            ] }) }),
            /* @__PURE__ */ o.jsx("td", { children: d.creditor_name || "\xC0 d\xE9finir" }),
            /* @__PURE__ */ o.jsx("td", { children: d.legal_entity_name || "\xC0 d\xE9finir" }),
            /* @__PURE__ */ o.jsx("td", { children: d.invoice_date ? new Date(d.invoice_date).toLocaleDateString("fr-CH") : "\u2014" }),
            /* @__PURE__ */ o.jsx("td", { children: d.amount_minor != null ? (d.amount_minor / 100).toFixed(2) + " " + (d.currency || "") : "\u2014" }),
            /* @__PURE__ */ o.jsx("td", { children: /* @__PURE__ */ o.jsx("span", { className: "wine-status " + (["FILED", "STORED", "VALIDATED"].includes(d.status) ? "done" : "pending"), children: { FILED: "Class\xE9", STORED: "Class\xE9", VALIDATED: "Valid\xE9", DUPLICATE: "Doublon", ERROR: "Erreur", TO_VALIDATE: "\xC0 v\xE9rifier" }[d.status] || "En cours" }) })
          ] }, d.id)) })
        ] }) }),
        !visible.length && /* @__PURE__ */ o.jsxs("div", { className: "wine-empty", children: [
          /* @__PURE__ */ o.jsx(WineIcon, { name: "documents" }),
          /* @__PURE__ */ o.jsx("strong", { children: "Votre espace est pr\xEAt." }),
          /* @__PURE__ */ o.jsx("p", { children: "Ajoutez votre premi\xE8re facture pour commencer." }),
          /* @__PURE__ */ o.jsx("button", { className: "pilot-primary", onClick: () => navigate("import"), children: "Ajouter un document" })
        ] })
      ] }),
      /* @__PURE__ */ o.jsxs("div", { className: "wine-dashboard-side", children: [
        /* @__PURE__ */ o.jsxs("section", { className: "wine-card", children: [
          /* @__PURE__ */ o.jsx("h2", { children: "R\xE9partition par soci\xE9t\xE9" }),
          /* @__PURE__ */ o.jsxs("div", { className: "wine-distribution", children: [
            /* @__PURE__ */ o.jsx("div", { className: "wine-donut", style: { background: docs.length ? "conic-gradient(" + stops + ")" : "var(--wine-border)" }, "aria-label": docs.length + " documents", children: /* @__PURE__ */ o.jsxs("div", { children: [
              /* @__PURE__ */ o.jsx("strong", { children: docs.length }),
              /* @__PURE__ */ o.jsx("small", { children: "documents" })
            ] }) }),
            /* @__PURE__ */ o.jsxs("ul", { children: [
              groups.map((g, i) => /* @__PURE__ */ o.jsxs("li", { children: [
                /* @__PURE__ */ o.jsx("i", { style: { background: colors[i % colors.length] } }),
                /* @__PURE__ */ o.jsx("span", { children: g.name }),
                /* @__PURE__ */ o.jsx("b", { children: g.count })
              ] }, g.name)),
              !groups.length && /* @__PURE__ */ o.jsx("li", { children: "Aucune soci\xE9t\xE9 utilis\xE9e" })
            ] })
          ] })
        ] }),
        /* @__PURE__ */ o.jsxs("section", { className: "wine-card", children: [
          /* @__PURE__ */ o.jsxs("div", { className: "wine-card-heading", children: [
            /* @__PURE__ */ o.jsx("h2", { children: "Activit\xE9 r\xE9cente" }),
            /* @__PURE__ */ o.jsx("button", { onClick: () => navigate("history"), children: "Historique \u2192" })
          ] }),
          /* @__PURE__ */ o.jsxs("div", { className: "wine-activity", children: [
            activity.map((event, i) => /* @__PURE__ */ o.jsxs("div", { children: [
              /* @__PURE__ */ o.jsx(WineIcon, { name: "history" }),
              /* @__PURE__ */ o.jsxs("span", { children: [
                /* @__PURE__ */ o.jsx("strong", { children: actions[event.action] || event.action }),
                /* @__PURE__ */ o.jsx("small", { children: event.document_name || event.actor_name || "DocPilot" }),
                event.location && /* @__PURE__ */ o.jsx("small", { title: event.location, children: event.location })
              ] })
            ] }, event.id || i)),
            !activity.length && /* @__PURE__ */ o.jsx("p", { children: activityError ? "Historique indisponible. R\xE9essayez dans l\u2019onglet Historique." : "Les prochaines actions appara\xEEtront ici." })
          ] })
        ] })
      ] }),
      /* @__PURE__ */ o.jsxs("section", { className: "wine-tip", children: [
        /* @__PURE__ */ o.jsx(WineIcon, { name: "settings" }),
        /* @__PURE__ */ o.jsxs("div", { children: [
          /* @__PURE__ */ o.jsx("strong", { children: "Votre classement devient plus simple" }),
          /* @__PURE__ */ o.jsx("p", { children: "Confirmez le bon dossier une fois : DocPilot retient vos choix pour les prochaines factures." })
        ] }),
        /* @__PURE__ */ o.jsx("button", { onClick: () => navigate("settings", "storage"), children: "Configurer \u2192" })
      ] })
    ] })
  ] });
}

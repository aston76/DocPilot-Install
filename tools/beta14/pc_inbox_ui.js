const labels = { duplicate: "Copie identique sur le NAS", processed: "D\xE9j\xE0 trait\xE9e dans DocPilot", imported: "D\xE9j\xE0 ajout\xE9e \xE0 DocPilot", to_process: "\xC0 traiter" };
export function PcInboxPanel({ onImportFile, onOpen, onChanged }) {
  const [state, setState] = N.useState(null);
  const [error, setError] = N.useState("");
  const [busy, setBusy] = N.useState(null);
  const [remove, setRemove] = N.useState(null);
  const [offset, setOffset] = N.useState(0);
  const [filter, setFilter] = N.useState("all");
  const refresh = async () => {
    const response = await fetch(`/api/v1/pc-inbox?offset=${offset}&filter=${filter}`, { cache: "no-store" });
    if (!response.ok) throw new Error("La recherche locale est indisponible.");
    setState(await response.json());
  };
  N.useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const response = await fetch(`/api/v1/pc-inbox?offset=${offset}&filter=${filter}`, { cache: "no-store" });
        if (!response.ok) throw new Error("Le serveur ne r\xE9pond pas.");
        const next = await response.json();
        if (active) setState(next);
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : String(e));
      }
    };
    poll();
    const timer = window.setInterval(poll, 3e3);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [offset, filter]);
  const command = async (action) => {
    setError("");
    try {
      const response = await fetch("/api/v1/pc-inbox", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action }) });
      const next = await response.json();
      if (!response.ok) throw new Error(next.detail || "Recherche impossible");
      setState(next);
      setOffset(0);
      setFilter("all");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };
  const importFile = async (item) => {
    setBusy(item.id);
    setError("");
    try {
      const response = await fetch(`/api/v1/pc-inbox/${item.id}/file`);
      if (!response.ok) {
        const detail = await response.json();
        throw new Error(detail.detail || "Le fichier n\u2019est plus accessible.");
      }
      const blob = await response.blob();
      const filename = item.path.split(/[\\/]/).pop() || "document.pdf";
      const document2 = await onImportFile(new File([blob], filename, { type: blob.type }));
      await fetch(`/api/v1/pc-inbox/${item.id}/refresh`, { method: "POST" });
      await refresh();
      onChanged();
      onOpen(document2.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };
  const confirmRemove = async () => {
    if (!remove) return;
    setBusy(remove.item.id);
    setError("");
    try {
      const response = await fetch(`/api/v1/pc-inbox/${remove.item.id}/remove`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(remove.deleteFile ? { delete_file: true, confirm: true } : { delete_file: false }) });
      const next = await response.json();
      if (!response.ok) throw new Error(next.detail || "Suppression impossible");
      setRemove(null);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };
  return /* @__PURE__ */ o.jsxs("section", { className: "pilot-pc-inbox", children: [
    /* @__PURE__ */ o.jsxs("div", { className: "pilot-page-title", children: [
      /* @__PURE__ */ o.jsxs("div", { children: [
        /* @__PURE__ */ o.jsx("span", { className: "pilot-kicker", children: "RECHERCHE LOCALE" }),
        /* @__PURE__ */ o.jsx("h1", { children: "Factures \xE0 traiter sur ce PC" }),
        /* @__PURE__ */ o.jsx("p", { children: "Retrouvez les factures oubli\xE9es sur cet ordinateur." })
      ] }),
      /* @__PURE__ */ o.jsx("button", { className: "pilot-primary", disabled: state?.running || !!busy, onClick: () => command("scan"), children: state?.running ? "Recherche en cours\u2026" : "D\xE9tecter les factures sur ce PC" })
    ] }),
    /* @__PURE__ */ o.jsx("p", { children: "Les dossiers Synology, les lecteurs r\xE9seau, les archives configur\xE9es et les dossiers syst\xE8me sont exclus. Aucun fichier n\u2019est d\xE9plac\xE9 ou supprim\xE9 pendant la recherche." }),
    error && /* @__PURE__ */ o.jsxs("div", { className: "pilot-alert error", role: "alert", children: [
      error,
      /* @__PURE__ */ o.jsx("button", { onClick: () => setError(""), "aria-label": "Fermer", children: "\xD7" })
    ] }),
    /* @__PURE__ */ o.jsxs("div", { className: "pilot-pc-status", role: "status", "aria-live": "polite", children: [
      /* @__PURE__ */ o.jsx("strong", { children: state?.message || "Chargement\u2026" }),
      state?.running && /* @__PURE__ */ o.jsxs(Fragment, { children: [
        /* @__PURE__ */ o.jsx("progress", { "aria-label": "Recherche des factures" }),
        /* @__PURE__ */ o.jsxs("span", { children: [
          state.visited,
          " fichiers parcourus \xB7 ",
          state.found,
          " candidats"
        ] }),
        /* @__PURE__ */ o.jsx("button", { className: "pilot-secondary", onClick: () => command("cancel"), children: "Arr\xEAter la recherche" })
      ] }),
      !!state?.errors && /* @__PURE__ */ o.jsxs("span", { children: [
        state.errors,
        " acc\xE8s ou fichier(s) non v\xE9rifi\xE9s : r\xE9sultat partiel."
      ] })
    ] }),
    /* @__PURE__ */ o.jsx("button", { className: "pilot-secondary", disabled: state?.running || !!busy || !state?.total, onClick: () => command("clear"), children: "Vider la liste \xB7 garder les fichiers du PC" }),
    /* @__PURE__ */ o.jsx("div", { className: "pilot-filters", children: [["all", "Tous"], ["to_process", "\xC0 traiter"], ["duplicates", "D\xE9j\xE0 trait\xE9s / doublons"]].map(([value, label]) => /* @__PURE__ */ o.jsx("button", { className: filter === value ? "active" : "", onClick: () => {
      setFilter(value);
      setOffset(0);
    }, children: label }, value)) }),
    /* @__PURE__ */ o.jsx("div", { className: "pilot-pc-list", children: state?.items.map((item) => /* @__PURE__ */ o.jsxs("article", { className: "pilot-pc-row", children: [
      /* @__PURE__ */ o.jsxs("div", { className: "pilot-pc-description", children: [
        /* @__PURE__ */ o.jsx("strong", { children: item.path.split(/[\\/]/).pop() }),
        /* @__PURE__ */ o.jsx("span", { children: item.path }),
        /* @__PURE__ */ o.jsxs("span", { className: "pilot-pc-label " + (item.status === "duplicate" ? "duplicate" : ""), children: [
          labels[item.status] || item.status,
          item.status === "to_process" && item.kind === "possible" ? " \xB7 Nature \xE0 confirmer" : ""
        ] }),
        item.matches.length > 0 && /* @__PURE__ */ o.jsxs("small", { children: [
          "Correspondance NAS : ",
          item.matches.join(" \xB7 ")
        ] }),
        item.status === "to_process" && !item.verified && /* @__PURE__ */ o.jsx("small", { children: "V\xE9rification du NAS incompl\xE8te : l\u2019absence de doublon n\u2019est pas confirm\xE9e." })
      ] }),
      /* @__PURE__ */ o.jsxs("div", { className: "pilot-pc-actions", children: [
        item.status === "to_process" && /* @__PURE__ */ o.jsx("button", { className: "pilot-primary", disabled: !!busy, onClick: () => importFile(item), children: busy === item.id ? "Import en cours\u2026" : "Importer et traiter" }),
        item.doc_id !== null && /* @__PURE__ */ o.jsx("button", { className: "pilot-secondary", onClick: () => onOpen(item.doc_id), children: "Ouvrir dans DocPilot" }),
        /* @__PURE__ */ o.jsx("button", { className: "pilot-secondary", disabled: !!busy, onClick: () => setRemove({ item, deleteFile: false }), children: "Retirer de la liste" }),
        /* @__PURE__ */ o.jsx("button", { className: "pilot-danger", disabled: !!busy, onClick: () => setRemove({ item, deleteFile: true }), children: "Supprimer aussi du PC" })
      ] })
    ] }, item.id)) }),
    state && !state.items.length && /* @__PURE__ */ o.jsx("p", { className: "pilot-simple-empty", children: state.running ? "La recherche continue\u2026" : "Aucun document dans cette liste. Lancez la d\xE9tection pour commencer." }),
    !!state?.total && /* @__PURE__ */ o.jsxs("div", { className: "pilot-pc-pagination", children: [
      /* @__PURE__ */ o.jsxs("span", { children: [
        offset + 1,
        "\u2013",
        Math.min(offset + state.items.length, state.total),
        " sur ",
        state.total
      ] }),
      /* @__PURE__ */ o.jsx("button", { className: "pilot-secondary", disabled: !offset, onClick: () => setOffset(Math.max(0, offset - 100)), children: "Pr\xE9c\xE9dent" }),
      /* @__PURE__ */ o.jsx("button", { className: "pilot-secondary", disabled: offset + 100 >= state.total, onClick: () => setOffset(offset + 100), children: "Suivant" })
    ] }),
    /* @__PURE__ */ o.jsx("p", { children: /* @__PURE__ */ o.jsx("small", { children: "Les PDF avec texte sont reconnus par leur contenu ou leur nom. Seuls les PDF et les fichiers dont le nom indique une facture sont examin\xE9s. Aucun appel \xE0 l\u2019IA pendant cette recherche. Les PDF sans texte restent \xE0 confirmer. Les fichiers uniquement en ligne et ceux d\xE9passant 100 Mo ne sont pas lus." }) }),
    remove && Ie.createPortal(/* @__PURE__ */ o.jsx("div", { className: "pilot-modal-backdrop pilot-update-backdrop", children: /* @__PURE__ */ o.jsxs("div", { className: "pilot-modal pilot-update-modal", role: "dialog", "aria-modal": "true", "aria-labelledby": "pc-remove-title", children: [
      /* @__PURE__ */ o.jsx("h2", { id: "pc-remove-title", children: remove.deleteFile ? "Supprimer le fichier de ce PC ?" : "Retirer uniquement de la liste ?" }),
      /* @__PURE__ */ o.jsx("p", { className: "pilot-modal-filename", children: remove.item.path }),
      /* @__PURE__ */ o.jsx("p", { children: remove.deleteFile ? "Le fichier original sera d\xE9finitivement supprim\xE9 de cet ordinateur. La copie du NAS ne sera pas modifi\xE9e." : "Le fichier restera sur cet ordinateur. Cette entr\xE9e sera masqu\xE9e dans la liste." }),
      error && /* @__PURE__ */ o.jsx("p", { role: "alert", children: error }),
      /* @__PURE__ */ o.jsxs("div", { className: "pilot-modal-actions", children: [
        /* @__PURE__ */ o.jsx("button", { className: "pilot-secondary", disabled: !!busy, onClick: () => setRemove(null), children: "Annuler" }),
        /* @__PURE__ */ o.jsx("button", { className: remove.deleteFile ? "pilot-danger" : "pilot-primary", disabled: !!busy, onClick: confirmRemove, children: busy ? "Traitement\u2026" : remove.deleteFile ? "Confirmer la suppression du PC" : "Retirer de la liste" })
      ] })
    ] }) }), document.body)
  ] });
}

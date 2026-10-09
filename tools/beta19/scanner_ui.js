export function ScannerPanel({ onImportFile, onChanged, renderDocument }) {
  const [state, setState] = N.useState(null);
  const [devices, setDevices] = N.useState([]);
  const [selected, setSelected] = N.useState("");
  const [message, setMessage] = N.useState("");
  const [error, setError] = N.useState("");
  const [loading, setLoading] = N.useState(false);
  const [sending, setSending] = N.useState(false);
  const [documentId, setDocumentId] = N.useState(null);
  const [connection, setConnection] = N.useState(null);
  const [probing, setProbing] = N.useState(false);
  const refreshDevices = async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/v1/scanner/devices", { cache: "no-store" });
      if (!response.ok) throw Error("D\xE9tection des scanners indisponible.");
      const data = await response.json();
      setDevices(data.devices || []);
      setMessage(data.message || "");
      setSelected((previous) => data.devices?.some((d) => d.id === previous) ? previous : data.default_device_id || "");
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };
  N.useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const response = await fetch("/api/v1/scanner", { cache: "no-store" });
        if (!response.ok) throw Error("Le scanner est indisponible.");
        const next = await response.json();
        if (active) setState(next);
      } catch (e) {
        if (active) setError(String(e));
      }
    };
    poll();
    refreshDevices();
    const timer = window.setInterval(poll, 1500);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);
  const command = async (action, device = selected) => {
    const response = await fetch("/api/v1/scanner", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(action === "reset" ? { action } : { action, device }) });
    const next = await response.json();
    if (!response.ok) throw Error(next.detail || "Num\xE9risation impossible.");
    if (action !== "probe") setState(next);
    return next;
  };
  const testConnection = async () => {
    if (!selected || state?.running || probing) return;
    setProbing(true);
    setConnection(null);
    try {
      setConnection(await command("probe"));
    } catch (e) {
      setError(String(e));
    } finally {
      setProbing(false);
    }
  };
  N.useEffect(() => {
    setConnection(null);
  }, [selected]);
  const choose = async (device) => {
    setSelected(device);
    setError("");
    if (device) try {
      await command("select", device);
    } catch (e) {
      setError(String(e));
    }
  };
  const scan = async () => {
    setError("");
    setConnection(null);
    try {
      await command("scan");
    } catch (e) {
      setError(String(e));
    }
  };
  const newInvoice = async () => {
    setError("");
    try {
      await command("reset");
      setDocumentId(null);
      onChanged();
    } catch (e) {
      setError(String(e));
    }
  };
  const send = async () => {
    setSending(true);
    setError("");
    try {
      const response = await fetch("/api/v1/scanner/pdf", { cache: "no-store" });
      if (!response.ok) throw Error("Le PDF n\u2019est pas disponible.");
      const file = new File([await response.blob()], `facture-scan-${(/* @__PURE__ */ new Date()).toISOString().slice(0, 10)}.pdf`, { type: "application/pdf" });
      const document = await onImportFile(file);
      if (!Number.isInteger(document.id)) throw Error("Le traitement n\u2019a pas confirm\xE9 la facture.");
      setDocumentId(document.id);
      onChanged();
    } catch (e) {
      setError(String(e));
    } finally {
      setSending(false);
    }
  };
  return /* @__PURE__ */ o.jsxs("section", { className: "pilot-pc-inbox pilot-scanner", children: [
    /* @__PURE__ */ o.jsx("div", { className: "pilot-page-title", children: /* @__PURE__ */ o.jsxs("div", { children: [
      /* @__PURE__ */ o.jsx("span", { className: "pilot-kicker", children: "NUM\xC9RISATION" }),
      /* @__PURE__ */ o.jsx("h1", { children: "Scanner et classer" }),
      /* @__PURE__ */ o.jsx("p", { children: "Num\xE9risez la facture, puis v\xE9rifiez et classez-la ici." })
    ] }) }),
    error && /* @__PURE__ */ o.jsx("div", { className: "pilot-alert error", role: "alert", children: error }),
    documentId !== null ? /* @__PURE__ */ o.jsxs(o.Fragment, { children: [
      /* @__PURE__ */ o.jsx("div", { className: "pilot-pc-actions", children: /* @__PURE__ */ o.jsx("button", { className: "pilot-secondary", onClick: newInvoice, children: "Scanner la facture suivante" }) }),
      renderDocument(documentId, newInvoice)
    ] }) : /* @__PURE__ */ o.jsxs(o.Fragment, { children: [
      /* @__PURE__ */ o.jsxs("div", { className: "pilot-scanner-controls", children: [
        /* @__PURE__ */ o.jsxs("label", { htmlFor: "scanner-device", children: [
          "Scanner \xE0 utiliser",
          /* @__PURE__ */ o.jsxs("select", { id: "scanner-device", value: selected, disabled: state?.running || sending || loading || probing, onChange: (e) => choose(e.target.value), children: [
            /* @__PURE__ */ o.jsx("option", { value: "", children: loading ? "Recherche\u2026" : "Choisir un scanner" }),
            devices.map((device) => /* @__PURE__ */ o.jsxs("option", { value: device.id, children: [
              device.label || device.name,
              device.id === selected ? " \xB7 pr\xE9f\xE9r\xE9 sur ce poste" : device.windows_default ? " \xB7 d\xE9faut Windows" : ""
            ] }, device.id))
          ] })
        ] }),
        /* @__PURE__ */ o.jsx("button", { className: "pilot-secondary", disabled: loading || state?.running || sending || probing, onClick: refreshDevices, children: "Actualiser" }),
        /* @__PURE__ */ o.jsx("button", { className: "pilot-secondary", disabled: !selected || state?.running || sending || probing, onClick: testConnection, children: probing ? "Test\u2026" : "Tester la connexion" })
      ] }),
      connection && /* @__PURE__ */ o.jsxs("p", { role: "status", className: connection.available ? "pilot-verified" : "pilot-alert", children: [
        connection.available ? "\u2713 Accessible lors du test" : "Connexion indisponible",
        " \u2014 ",
        connection.message
      ] }),
      /* @__PURE__ */ o.jsx("p", { className: "pilot-scanner-hint", children: message || "Choisissez le scanner Windows qui fonctionne. DocPilot le gardera pour les prochaines factures." }),
      !loading && state?.supported && !devices.length && /* @__PURE__ */ o.jsx("p", { children: "Aucun scanner d\xE9tect\xE9. V\xE9rifiez la connexion et le pilote WIA du fabricant." }),
      /* @__PURE__ */ o.jsxs("div", { className: "pilot-pc-status", role: "status", children: [
        /* @__PURE__ */ o.jsx("strong", { children: sending ? "Analyse de la facture\u2026" : state?.message || "Chargement\u2026" }),
        (state?.running || sending) && /* @__PURE__ */ o.jsx("progress", { "aria-label": sending ? "Analyse en cours" : "Num\xE9risation en cours" }),
        !!state?.pages && /* @__PURE__ */ o.jsxs("span", { children: [
          state.pages,
          " page(s)"
        ] })
      ] }),
      /* @__PURE__ */ o.jsxs("div", { className: "pilot-pc-actions", children: [
        /* @__PURE__ */ o.jsx("button", { className: "pilot-primary", disabled: !state?.supported || !selected || state?.running || sending || probing, onClick: scan, children: state?.running ? "Num\xE9risation\u2026" : state?.pages ? "Ajouter une page" : "Num\xE9riser la facture" }),
        state?.pdf_available && /* @__PURE__ */ o.jsx("button", { className: "pilot-primary", disabled: state.running || sending || probing, onClick: send, children: sending ? "Analyse\u2026" : "Analyser et classer ici" }),
        !!state?.pages && /* @__PURE__ */ o.jsx("button", { className: "pilot-secondary", disabled: state?.running || sending, onClick: newInvoice, children: "Nouvelle facture" })
      ] }),
      state?.pdf_available && /* @__PURE__ */ o.jsx("iframe", { title: "Facture num\xE9ris\xE9e", src: "/api/v1/scanner/pdf?pages=" + state.pages + "&session=" + encodeURIComponent(state.session || "") + "#toolbar=0&navpanes=0&view=FitH", className: "pilot-scanner-preview" }),
      /* @__PURE__ */ o.jsx("p", { className: "pilot-scanner-hint", children: "Le PDF appara\xEEt ici apr\xE8s la num\xE9risation. Ajoutez les pages d\u2019une m\xEAme facture avant de lancer son analyse. La num\xE9risation reste locale." })
    ] })
  ] });
}

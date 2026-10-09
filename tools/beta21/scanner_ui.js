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
  const [capturedUrl, setCapturedUrl] = N.useState("");
  const [duplicate, setDuplicate] = N.useState(false);
  const [commandBusy, setCommandBusy] = N.useState(false);
  const requests = N.useRef({ sequence: 0, pending: false });
  const captured = N.useRef("");
  N.useEffect(() => () => {
    if (captured.current) URL.revokeObjectURL(captured.current);
  }, []);
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
    let polling = false;
    const poll = async () => {
      if (polling || requests.current.pending) return;
      polling = true;
      const sequence = ++requests.current.sequence;
      try {
        const response = await fetch("/api/v1/scanner", { cache: "no-store" });
        if (!response.ok) throw Error("Le scanner est indisponible.");
        const next = await response.json();
        if (active && sequence === requests.current.sequence) setState(next);
      } catch (e) {
        if (active && sequence === requests.current.sequence) setError(String(e));
      } finally {
        polling = false;
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
    if (requests.current.pending) throw Error("Une commande du scanner est d\xE9j\xE0 en cours.");
    requests.current.pending = true;
    setCommandBusy(true);
    const sequence = ++requests.current.sequence;
    try {
      const response = await fetch("/api/v1/scanner", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(action === "reset" ? { action } : { action, device }) });
      const next = await response.json();
      if (!response.ok) throw Error(next.detail || "Num\xE9risation impossible.");
      if (action !== "probe" && sequence === requests.current.sequence) setState(next);
      return next;
    } finally {
      requests.current.pending = false;
      setCommandBusy(false);
    }
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
  const approveApi = async () => {
    if (!selected || busy) return;
    setProbing(true); setError("");
    try {
      const configure = async body => {
        const response = await fetch('/api/v1/scanner/escl', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        const result = await response.json();
        if (!response.ok) throw Error(result.detail || 'Configuration API impossible.');
        return result;
      };
      const certificate = await configure({action:'certificate',device:selected});
      if (!window.confirm('Approuver ce scanner pour DocPilot sur ce poste ?\n\n'+certificate.subject+'\nSHA256 : '+certificate.sha256+'\nValide jusqu’au : '+certificate.valid_until+'\n\nLe certificat ne sera pas ajouté à Windows. Refusez si ce scanner ne correspond pas à celui attendu.')) return;
      const result = await configure({action:'approve',token:certificate.token});
      await refreshDevices(); setSelected(result.device);
      setConnection(null); setMessage('Certificat approuvé. Testez la connexion avant de numériser.');
    } catch (e) { setError(String(e)); }
    finally {setProbing(false);}
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
      if (captured.current) URL.revokeObjectURL(captured.current);
      captured.current = "";
      setCapturedUrl("");
    } catch (e) {
      setError(String(e));
    }
  };
  const newInvoice = async () => {
    setError("");
    try {
      await command("reset");
      setDocumentId(null);
      setDuplicate(false);
      if (captured.current) URL.revokeObjectURL(captured.current);
      captured.current = "";
      setCapturedUrl("");
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
      const blob = await response.blob();
      if (captured.current) URL.revokeObjectURL(captured.current);
      captured.current = URL.createObjectURL(blob);
      setCapturedUrl(captured.current);
      const file = new File([blob], `facture-scan-${(/* @__PURE__ */ new Date()).toISOString().slice(0, 10)}.pdf`, { type: "application/pdf" });
      const document = await onImportFile(file);
      if (!Number.isInteger(document.id)) throw Error("Le traitement n\u2019a pas confirm\xE9 la facture.");
      let matches = false;
      try {
        matches = !!JSON.parse(document.confidence?.archive_duplicate?.detail || "{}").matches?.length;
      } catch {
      }
      setDuplicate(document.status === "DUPLICATE" || matches);
      setDocumentId(document.id);
      onChanged();
    } catch (e) {
      setError(String(e));
    } finally {
      setSending(false);
    }
  };
  const busy = state?.running || sending || probing || commandBusy;
  const previewAvailable = !!capturedUrl || !!(state?.preview_available ?? state?.pdf_available);
  const previewUrl = capturedUrl || "/api/v1/scanner/preview?pages=" + state?.pages + "&version=" + (state?.preview_version || 0) + "&session=" + encodeURIComponent(state?.session || "");
  const preview = previewAvailable && (state?.preview_kind === "image" && !capturedUrl ? /* @__PURE__ */ o.jsx("img", { src: previewUrl, alt: "Page re\xE7ue du scanner, pr\xE9paration du PDF", className: "pilot-scanner-image" }) : /* @__PURE__ */ o.jsx("iframe", { title: "Facture r\xE9ellement num\xE9ris\xE9e", src: previewUrl + "#toolbar=0&navpanes=0&view=FitH", className: "pilot-scanner-preview" }));
  return /* @__PURE__ */ o.jsxs("section", { className: "pilot-pc-inbox pilot-scanner", children: [
    /* @__PURE__ */ o.jsx("div", { className: "pilot-page-title", children: /* @__PURE__ */ o.jsxs("div", { children: [
      /* @__PURE__ */ o.jsx("span", { className: "pilot-kicker", children: "NUM\xC9RISATION" }),
      /* @__PURE__ */ o.jsx("h1", { children: "Scanner et classer" }),
      /* @__PURE__ */ o.jsx("p", { children: "Num\xE9risez la facture, puis v\xE9rifiez et classez-la ici." })
    ] }) }),
    error && /* @__PURE__ */ o.jsx("div", { className: "pilot-alert error", role: "alert", children: error }),
    documentId !== null ? /* @__PURE__ */ o.jsxs(o.Fragment, { children: [
      duplicate && /* @__PURE__ */ o.jsxs("div", { className: "pilot-alert", role: "status", children: [
        /* @__PURE__ */ o.jsx("strong", { children: "Document num\xE9ris\xE9 \xB7 doublon d\xE9tect\xE9" }),
        /* @__PURE__ */ o.jsx("p", { children: "L\u2019aper\xE7u ci-dessous montre la page re\xE7ue du scanner. Consultez le r\xE9sultat pour v\xE9rifier le doublon ou retirer cette entr\xE9e de DocPilot." })
      ] }),
      /* @__PURE__ */ o.jsx("div", { className: "pilot-pc-actions", children: /* @__PURE__ */ o.jsx("button", { className: "pilot-secondary", disabled: busy, onClick: newInvoice, children: duplicate ? "Retirer cet aper\xE7u \xB7 scanner la suivante" : "Scanner la facture suivante" }) }),
      previewAvailable && /* @__PURE__ */ o.jsxs("details", { className: "pilot-scanner-evidence", open: duplicate, children: [
        /* @__PURE__ */ o.jsx("summary", { children: "Aper\xE7u de la num\xE9risation re\xE7ue" }),
        preview
      ] }),
      renderDocument(documentId, newInvoice)
    ] }) : /* @__PURE__ */ o.jsxs(o.Fragment, { children: [
      /* @__PURE__ */ o.jsxs("div", { className: "pilot-scanner-controls", children: [
        /* @__PURE__ */ o.jsxs("label", { htmlFor: "scanner-device", children: [
          "Scanner \xE0 utiliser",
          /* @__PURE__ */ o.jsxs("select", { id: "scanner-device", value: selected, disabled: busy || loading, onChange: (e) => choose(e.target.value), children: [
            /* @__PURE__ */ o.jsx("option", { value: "", children: loading ? "Recherche\u2026" : "Choisir un scanner" }),
            devices.map((device) => /* @__PURE__ */ o.jsxs("option", { value: device.id, children: [
              device.label || device.name,
              device.id === selected ? " \xB7 pr\xE9f\xE9r\xE9 sur ce poste" : device.windows_default ? " \xB7 d\xE9faut Windows" : ""
            ] }, device.id))
          ] })
        ] }),
        /* @__PURE__ */ o.jsx("button", { className: "pilot-secondary", disabled: loading || busy, onClick: refreshDevices, children: "Actualiser" }),
        /* @__PURE__ */ o.jsx("button", { className: "pilot-secondary", disabled: !selected || busy, onClick: testConnection, children: probing ? "Test\u2026" : "Tester la connexion" }),
        devices.find(d=>d.id===selected)?.backend==='escl' && o.jsx('button',{className:'pilot-secondary',disabled:busy,onClick:approveApi,children:'Approuver le scanner API'})
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
        /* @__PURE__ */ o.jsx("button", { className: "pilot-primary", disabled: !state?.supported || !selected || busy, onClick: scan, children: state?.running ? "Num\xE9risation\u2026" : state?.pages ? "Ajouter une page" : "Num\xE9riser la facture" }),
        state?.pdf_available && /* @__PURE__ */ o.jsx("button", { className: "pilot-primary", disabled: busy, onClick: send, children: sending ? "Analyse\u2026" : "Analyser et classer ici" }),
        previewAvailable && /* @__PURE__ */ o.jsx("button", { className: "pilot-secondary", disabled: busy, onClick: newInvoice, children: "Retirer l\u2019aper\xE7u \xB7 nouvelle facture" })
      ] }),
      preview,
      /* @__PURE__ */ o.jsx("p", { className: "pilot-scanner-hint", children: "L\u2019aper\xE7u appara\xEEt d\xE8s r\xE9ception de la page et reste visible pendant l\u2019ajout des suivantes. La d\xE9tection des doublons commence avec \xAB Analyser et classer ici \xBB. Retirer l\u2019aper\xE7u ne supprime aucun fichier du PC ou du NAS." })
    ] })
  ] });
}

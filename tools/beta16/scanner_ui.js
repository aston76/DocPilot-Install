export function ScannerPanel({ onImportFile, onOpen, onChanged }) {
  const [state, setState] = N.useState(null), [devices, setDevices] = N.useState([]), [selected, setSelected] = N.useState(""), [message, setMessage] = N.useState(""), [error, setError] = N.useState(""), [loading, setLoading] = N.useState(false), [sending, setSending] = N.useState(false);
  const refreshDevices = async () => {
    setLoading(true);
    setError("");
    try {
      const r = await fetch("/api/v1/scanner/devices");
      if (!r.ok) throw Error("D\xE9tection des scanners indisponible.");
      const data = await r.json();
      setDevices(data.devices || []);
      setMessage(data.message || "");
      setSelected((previous) => data.devices?.some((d) => d.id === previous) ? previous : data.devices?.[0]?.id || "");
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
        const r = await fetch("/api/v1/scanner", { cache: "no-store" });
        if (!r.ok) throw Error("Le scanner est indisponible.");
        const next = await r.json();
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
  const command = async (action) => {
    setError("");
    try {
      const r = await fetch("/api/v1/scanner", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(action === "scan" ? { action, device: selected } : { action }) });
      const next = await r.json();
      if (!r.ok) throw Error(next.detail || "Num\xE9risation impossible.");
      setState(next);
    } catch (e) {
      setError(String(e));
    }
  };
  const send = async () => {
    setSending(true);
    setError("");
    try {
      const r = await fetch("/api/v1/scanner/pdf", { cache: "no-store" });
      if (!r.ok) throw Error("Le PDF n\u2019est pas disponible.");
      const file = new File([await r.blob()], `facture-scan-${(/* @__PURE__ */ new Date()).toISOString().slice(0, 10)}.pdf`, { type: "application/pdf" });
      const document = await onImportFile(file);
      await command("reset");
      onChanged();
      onOpen(document.id);
    } catch (e) {
      setError(String(e));
    } finally {
      setSending(false);
    }
  };
  return /* @__PURE__ */ o.jsxs("section", { className: "pilot-pc-inbox", children: [
    /* @__PURE__ */ o.jsx("div", { className: "pilot-page-title", children: /* @__PURE__ */ o.jsxs("div", { children: [
      /* @__PURE__ */ o.jsx("span", { className: "pilot-kicker", children: "NUM\xC9RISATION" }),
      /* @__PURE__ */ o.jsx("h1", { children: "Scanner une facture" }),
      /* @__PURE__ */ o.jsx("p", { children: "Num\xE9risez, v\xE9rifiez le PDF puis lancez son classement." })
    ] }) }),
    /* @__PURE__ */ o.jsx("p", { children: message || "Scanner USB ou r\xE9seau install\xE9 dans Windows avec un pilote de num\xE9risation WIA." }),
    error && /* @__PURE__ */ o.jsx("div", { className: "pilot-alert error", role: "alert", children: error }),
    /* @__PURE__ */ o.jsxs("div", { className: "pilot-pc-status", children: [
      /* @__PURE__ */ o.jsx("label", { htmlFor: "scanner-device", children: "Scanner" }),
      /* @__PURE__ */ o.jsxs("select", { id: "scanner-device", value: selected, disabled: state?.running || sending || loading, onChange: (e) => setSelected(e.target.value), children: [
        /* @__PURE__ */ o.jsx("option", { value: "", children: loading ? "Recherche des scanners\u2026" : "Choisir un scanner" }),
        devices.map((d) => /* @__PURE__ */ o.jsx("option", { value: d.id, children: d.name }, d.id))
      ] }),
      /* @__PURE__ */ o.jsx("button", { className: "pilot-secondary", disabled: loading || state?.running || sending, onClick: refreshDevices, children: loading ? "Recherche\u2026" : "Actualiser les scanners" })
    ] }),
    !loading && state?.supported && !devices.length && /* @__PURE__ */ o.jsx("p", { children: "Aucun scanner compatible d\xE9tect\xE9. V\xE9rifiez la connexion et le pilote WIA du fabricant. Le pilote d\u2019impression seul ne suffit pas." }),
    /* @__PURE__ */ o.jsxs("div", { className: "pilot-pc-status", role: "status", children: [
      /* @__PURE__ */ o.jsx("strong", { children: state?.message || "Chargement\u2026" }),
      state?.running && /* @__PURE__ */ o.jsx("progress", { "aria-label": "Num\xE9risation en cours" }),
      !!state?.pages && /* @__PURE__ */ o.jsxs("span", { children: [
        state.pages,
        " page(s) dans cette facture"
      ] })
    ] }),
    /* @__PURE__ */ o.jsxs("div", { className: "pilot-pc-actions", children: [
      /* @__PURE__ */ o.jsx("button", { className: "pilot-primary", disabled: !state?.supported || !selected || state?.running || sending, onClick: () => command("scan"), children: state?.running ? "Num\xE9risation\u2026" : state?.pages ? "Ajouter une page" : "Num\xE9riser la facture" }),
      state?.pdf_available && /* @__PURE__ */ o.jsx("button", { className: "pilot-primary", disabled: state.running || sending, onClick: send, children: sending ? "Envoi au traitement\u2026" : "Traiter cette facture" }),
      !!state?.pages && /* @__PURE__ */ o.jsx("button", { className: "pilot-secondary", disabled: state.running || sending, onClick: () => command("reset"), children: "Nouvelle facture" })
    ] }),
    state?.pdf_available && !state.running && /* @__PURE__ */ o.jsx("iframe", { title: "Aper\xE7u de la facture num\xE9ris\xE9e", src: "/api/v1/scanner/pdf?pages=" + state.pages, style: { width: "100%", height: "min(70vh,720px)", border: "1px solid #dce8e2", borderRadius: 16, marginTop: 20 } }),
    /* @__PURE__ */ o.jsx("p", { children: /* @__PURE__ */ o.jsx("small", { children: "La num\xE9risation et la compression en PDF restent locales. L\u2019analyse habituelle commence apr\xE8s \xAB Traiter cette facture \xBB. Ajoutez les pages d\u2019une m\xEAme facture avant de la traiter. \xAB Nouvelle facture \xBB efface seulement cet aper\xE7u temporaire." }) })
  ] });
}

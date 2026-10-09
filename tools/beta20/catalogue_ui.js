export function CatalogueRecovery({ onRefresh }) {
  const [state, setState] = N.useState(null);
  const [error, setError] = N.useState("");
  const refresh = N.useRef(onRefresh);
  refresh.current = onRefresh;
  N.useEffect(() => {
    let active = true, polling = false, previous = "";
    async function poll() {
      if (polling) return;
      polling = true;
      try {
        const response = await fetch("/api/v1/catalogue-directory", { cache: "no-store" });
        if (!response.ok) throw Error("R\xE9cup\xE9ration des dossiers indisponible.");
        const next = await response.json();
        if (active) {
          setState(next);
          const signature = JSON.stringify(next);
          if (!next.running && ["complete", "partial"].includes(next.status) && signature !== previous) refresh.current();
          previous = signature;
        }
      } catch (e) {
        if (active) setError(String(e));
      } finally {
        polling = false;
      }
    }
    poll();
    const timer = window.setInterval(poll, 1500);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);
  async function recover() {
    setError("");
    setState({ running: true, status: "reading", message: "Lecture des dossiers\u2026" });
    try {
      const response = await fetch("/api/v1/catalogue-directory", { method: "POST" });
      if (!response.ok) throw Error("R\xE9cup\xE9ration des dossiers indisponible.");
      setState(await response.json());
    } catch (e) {
      setError(String(e));
      setState(null);
    }
  }
  return /* @__PURE__ */ o.jsxs("div", { className: "pilot-catalogue-recovery", children: [
    /* @__PURE__ */ o.jsxs("div", { role: "status", children: [
      /* @__PURE__ */ o.jsx("strong", { children: state?.message || "La liste comprend tous les noms enregistr\xE9s sur ce poste." }),
      /* @__PURE__ */ o.jsx("p", { children: "Les noms manquants sont r\xE9cup\xE9r\xE9s dans les dossiers de l\u2019archive configur\xE9e. Les entr\xE9es retir\xE9es restent d\xE9sactiv\xE9es. Aucun document n\u2019est analys\xE9." }),
      state?.running && /* @__PURE__ */ o.jsx("progress", { "aria-label": "R\xE9cup\xE9ration des noms" })
    ] }),
    /* @__PURE__ */ o.jsx("button", { className: "pilot-secondary", disabled: state?.running, onClick: recover, children: state?.running ? "R\xE9cup\xE9ration\u2026" : "R\xE9cup\xE9rer les soci\xE9t\xE9s des dossiers" }),
    error && /* @__PURE__ */ o.jsx("p", { role: "alert", children: error })
  ] });
}

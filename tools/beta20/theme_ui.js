export function ThemeSwitch() {
  const [theme, setTheme] = N.useState(() => {
    try {
      const saved = localStorage.getItem("docpilot-theme");
      return saved === "light" || saved === "dark" ? saved : "system";
    } catch {
      return "system";
    }
  });
  N.useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.dataset.theme = theme === "system" ? media.matches ? "dark" : "light" : theme;
    };
    apply();
    try {
      localStorage.setItem("docpilot-theme", theme);
    } catch {
    }
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);
  return /* @__PURE__ */ o.jsxs("select", { className: "pilot-theme-switch", "aria-label": "Apparence", value: theme, onChange: (event) => setTheme(event.target.value), children: [
    /* @__PURE__ */ o.jsx("option", { value: "system", children: "Th\xE8me syst\xE8me" }),
    /* @__PURE__ */ o.jsx("option", { value: "light", children: "Mode clair" }),
    /* @__PURE__ */ o.jsx("option", { value: "dark", children: "Mode sombre" })
  ] });
}

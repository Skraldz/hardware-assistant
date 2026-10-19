import { createContext, useContext, useEffect, useState } from "react";
import { translations } from "./translations.js";

const LanguageContext = createContext(null);

function getInitialLanguage() {
  try {
    const stored = localStorage.getItem("language");
    if (stored === "da" || stored === "en") return stored;
  } catch {
    // localStorage unavailable (private browsing, blocked storage, …) — fall through to the default.
  }
  return "da";
}

export function LanguageProvider({ children }) {
  const [language, setLanguage] = useState(getInitialLanguage);

  useEffect(() => {
    try {
      localStorage.setItem("language", language);
    } catch {
      // Per-viewer convenience only; fine if it doesn't persist.
    }
  }, [language]);

  function t(key, ...args) {
    const value = translations[language]?.[key] ?? translations.da[key];
    return typeof value === "function" ? value(...args) : value;
  }

  return <LanguageContext.Provider value={{ language, setLanguage, t }}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useLanguage must be used within a LanguageProvider");
  return ctx;
}

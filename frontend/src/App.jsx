import { useState } from "react";
import HealthBadge from "./components/HealthBadge.jsx";
import InventoryView from "./components/InventoryView.jsx";
import RecommendView from "./components/RecommendView.jsx";
import BackupView from "./components/BackupView.jsx";
import { useLanguage } from "./i18n/LanguageContext.jsx";
import { LANGUAGES } from "./i18n/translations.js";
import { useTheme } from "./theme/ThemeContext.jsx";

const TABS = {
  inventory: { labelKey: "tabInventory", Component: InventoryView },
  recommend: { labelKey: "tabRecommend", Component: RecommendView },
  backup: { labelKey: "tabBackup", Component: BackupView },
};

export default function App() {
  const [activeTab, setActiveTab] = useState("inventory");
  const { t, language, setLanguage } = useLanguage();
  const { theme, toggleTheme } = useTheme();
  const ActiveComponent = TABS[activeTab].Component;

  return (
    <>
      <header>
        <h1>{t("appTitle")}</h1>
        <div className="header-controls">
          <select
            className="language-select"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            aria-label="Language"
          >
            {LANGUAGES.map((lang) => (
              <option key={lang.code} value={lang.code}>
                {lang.label}
              </option>
            ))}
          </select>
          <button
            className="icon-btn"
            onClick={toggleTheme}
            title={theme === "dark" ? t("themeToggleToLight") : t("themeToggleToDark")}
          >
            {theme === "dark" ? "☀️" : "🌙"}
          </button>
          <HealthBadge />
        </div>
      </header>
      <nav>
        {Object.entries(TABS).map(([key, tab]) => (
          <button key={key} className={key === activeTab ? "active" : ""} onClick={() => setActiveTab(key)}>
            {t(tab.labelKey)}
          </button>
        ))}
      </nav>
      <main>
        <ActiveComponent />
      </main>
    </>
  );
}

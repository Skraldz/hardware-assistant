import { useState } from "react";
import HealthBadge from "./components/HealthBadge.jsx";
import InventoryView from "./components/InventoryView.jsx";
import RecommendView from "./components/RecommendView.jsx";
import BackupView from "./components/BackupView.jsx";

const TABS = {
  inventory: { label: "Lager", Component: InventoryView },
  recommend: { label: "Anbefaling", Component: RecommendView },
  backup: { label: "Backup", Component: BackupView },
};

export default function App() {
  const [activeTab, setActiveTab] = useState("inventory");
  const ActiveComponent = TABS[activeTab].Component;

  return (
    <>
      <header>
        <h1>Hardware Assistant</h1>
        <HealthBadge />
      </header>
      <nav>
        {Object.entries(TABS).map(([key, tab]) => (
          <button key={key} className={key === activeTab ? "active" : ""} onClick={() => setActiveTab(key)}>
            {tab.label}
          </button>
        ))}
      </nav>
      <main>
        <ActiveComponent />
      </main>
    </>
  );
}

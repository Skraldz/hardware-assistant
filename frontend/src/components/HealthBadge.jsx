import { useEffect, useState } from "react";
import { api } from "../api.js";
import { useLanguage } from "../i18n/LanguageContext.jsx";

export default function HealthBadge() {
  const { t } = useLanguage();
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(null);

  async function refresh() {
    try {
      setHealth(await api.getHealth());
      setError(null);
    } catch (err) {
      setError(err.message);
      setHealth(null);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  if (error) {
    return (
      <span title={t("healthUnreachableTitle", error)} onClick={refresh} style={{ color: "#fca5a5", cursor: "pointer" }}>
        <span className="dot dot-degraded" />
        {t("healthUnreachable")}
      </span>
    );
  }

  if (!health) {
    return <span className="muted">{t("healthChecking")}</span>;
  }

  return (
    <span title={t("healthTitle", health)} onClick={refresh} style={{ cursor: "pointer" }}>
      <span className={`dot ${health.status === "ok" ? "dot-ok" : "dot-degraded"}`} />
      {health.status === "ok" ? t("healthOk") : t("healthDegraded")}
    </span>
  );
}

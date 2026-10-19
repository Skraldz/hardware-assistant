import { useEffect, useState } from "react";
import { api } from "../api.js";

export default function HealthBadge() {
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
      <span
        title={`Kan ikke nå backend: ${error} (klik for at prøve igen)`}
        onClick={refresh}
        style={{ color: "#fca5a5", cursor: "pointer" }}
      >
        <span className="dot dot-degraded" />
        Backend uanselig
      </span>
    );
  }

  if (!health) {
    return <span className="muted">Tjekker status…</span>;
  }

  const title = `DB: ${health.db} · Ollama: ${health.ollama} · Storage: ${health.storage} · Backup: ${health.backup_backend} (${health.backup_destination})`;

  return (
    <span title={title} onClick={refresh} style={{ cursor: "pointer" }}>
      <span className={`dot ${health.status === "ok" ? "dot-ok" : "dot-degraded"}`} />
      {health.status === "ok" ? "Alt kører" : "Degraderet"}
    </span>
  );
}

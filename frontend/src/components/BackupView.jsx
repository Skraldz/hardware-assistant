import { useEffect, useState } from "react";
import { api } from "../api.js";
import { useLanguage } from "../i18n/LanguageContext.jsx";

const DATE_LOCALES = { da: "da-DK", en: "en-GB" };

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function BackupView({ active = true }) {
  const { t, language } = useLanguage();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  // null until the first successful load reports what the server supports
  // and defaults to; from then on, the user's own choice.
  const [backend, setBackend] = useState(null);
  // A single in-flight action at a time: backup/restore both replace the
  // whole inventory, so two concurrent ones would race the backend and
  // leave the result up to whichever response happens to land last.
  const [activeAction, setActiveAction] = useState(null); // null | "create" | `restore:${name}`

  async function load(forBackend) {
    try {
      const result = await api.listBackups(forBackend ?? undefined);
      setData(result);
      setBackend(forBackend ?? result.backup_backend);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }

  // Tabs stay mounted across switches (App.jsx); refetch whenever this one
  // becomes active again, so a backup created elsewhere isn't stale here.
  useEffect(() => {
    if (active) load(backend);
    // `backend` is deliberately not a dependency here: a tab reactivation
    // should reload the currently-selected backend, not re-trigger this
    // effect every time the user picks a different one (handleBackendChange
    // already loads explicitly).
  }, [active]);

  async function handleBackendChange(nextBackend) {
    setBackend(nextBackend);
    await load(nextBackend);
  }

  async function handleCreate() {
    setActiveAction("create");
    try {
      await api.createBackup(backend);
      await load(backend);
    } catch (err) {
      setError(err.message);
    } finally {
      setActiveAction(null);
    }
  }

  async function handleRestore(name) {
    if (!window.confirm(t("confirmRestore", name))) return;
    setActiveAction(`restore:${name}`);
    try {
      const res = await api.restoreBackup(name, backend);
      window.alert(t("restoreComplete", res.restored_count));
    } catch (err) {
      setError(err.message);
    } finally {
      setActiveAction(null);
    }
  }

  const busy = activeAction !== null;

  return (
    <section>
      <h2>{t("backupHeading")}</h2>
      {data && (
        <>
          <div className="chip-row">
            {data.available_backends.map((b) => (
              <button
                key={b}
                type="button"
                className={`chip${backend === b ? " active" : ""}`}
                onClick={() => handleBackendChange(b)}
                disabled={busy}
              >
                {b === "azure" ? t("backendAzure") : t("backendLocal")}
              </button>
            ))}
          </div>
          <p className="muted">
            {t("activeBackendLabel")} <strong>{data.backup_backend}</strong> → {data.destination}
          </p>
          {!data.available_backends.includes("azure") && (
            <p className="muted">{t("azureNotConfiguredNotice")}</p>
          )}
        </>
      )}
      {error && <p className="error-message">{error}</p>}

      <button className="btn" onClick={handleCreate} disabled={busy}>
        {activeAction === "create" ? t("creatingBackup") : t("createBackupNow")}
      </button>

      <table style={{ marginTop: "1rem" }}>
        <thead>
          <tr>
            <th>{t("colName")}</th>
            <th>{t("colTimestamp")}</th>
            <th>{t("colQuantity")}</th>
            <th>{t("colSize")}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {data?.backups.map((backup) => (
            <tr key={backup.name}>
              <td>{backup.name}</td>
              <td>{new Date(backup.created_at).toLocaleString(DATE_LOCALES[language])}</td>
              <td>{backup.component_count ?? "?"}</td>
              <td>{formatBytes(backup.size_bytes)}</td>
              <td>
                <button className="btn btn-secondary" onClick={() => handleRestore(backup.name)} disabled={busy}>
                  {activeAction === `restore:${backup.name}` ? t("restoring") : t("restore")}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

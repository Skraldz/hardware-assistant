import { useEffect, useState } from "react";
import { api } from "../api.js";

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function BackupView() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [creating, setCreating] = useState(false);
  const [restoringName, setRestoringName] = useState(null);

  async function load() {
    try {
      setData(await api.listBackups());
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleCreate() {
    setCreating(true);
    try {
      await api.createBackup();
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  }

  async function handleRestore(name) {
    if (!window.confirm(`Gendan backup "${name}"? Dette erstatter hele det nuværende lager.`)) return;
    setRestoringName(name);
    try {
      const res = await api.restoreBackup(name);
      window.alert(`Gendannelse gennemført: ${res.restored_count} komponenter.`);
    } catch (err) {
      setError(err.message);
    } finally {
      setRestoringName(null);
    }
  }

  return (
    <section>
      <h2>Backup</h2>
      {data && (
        <p className="muted">
          Aktiv backend: <strong>{data.backup_backend}</strong> → {data.destination}
        </p>
      )}
      {error && <p className="error-message">{error}</p>}

      <button className="btn" onClick={handleCreate} disabled={creating}>
        {creating ? "Laver backup…" : "Lav backup nu"}
      </button>

      <table style={{ marginTop: "1rem" }}>
        <thead>
          <tr>
            <th>Navn</th>
            <th>Tidspunkt</th>
            <th>Antal</th>
            <th>Størrelse</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {data?.backups.map((backup) => (
            <tr key={backup.name}>
              <td>{backup.name}</td>
              <td>{new Date(backup.created_at).toLocaleString("da-DK")}</td>
              <td>{backup.component_count ?? "?"}</td>
              <td>{formatBytes(backup.size_bytes)}</td>
              <td>
                <button
                  className="btn btn-secondary"
                  onClick={() => handleRestore(backup.name)}
                  disabled={restoringName === backup.name}
                >
                  {restoringName === backup.name ? "Gendanner…" : "Gendan"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

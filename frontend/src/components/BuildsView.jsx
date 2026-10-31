import { useEffect, useState } from "react";
import { api } from "../api.js";
import { useLanguage } from "../i18n/LanguageContext.jsx";

const DATE_LOCALES = { da: "da-DK", en: "en-GB" };

export default function BuildsView({ active = true }) {
  const { t, language } = useLanguage();
  const [builds, setBuilds] = useState([]);
  const [error, setError] = useState(null);
  // A single in-flight action at a time, same reasoning as BackupView: both
  // actions mutate shared state (the saved-builds list, or the inventory
  // itself), so two concurrent ones would race the backend.
  const [activeAction, setActiveAction] = useState(null); // null | `complete:${id}` | `delete:${id}`

  async function load() {
    try {
      setBuilds(await api.listBuilds());
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }

  // Tabs stay mounted across switches (App.jsx); refetch whenever this one
  // becomes active again (e.g. a build just saved from the Recommend tab).
  useEffect(() => {
    if (active) load();
  }, [active]);

  async function handleComplete(build) {
    if (!window.confirm(t("confirmCompleteBuild"))) return;
    setActiveAction(`complete:${build.id}`);
    try {
      await api.completeBuild(build.id);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setActiveAction(null);
    }
  }

  async function handleDelete(build) {
    if (!window.confirm(t("confirmDeleteBuild"))) return;
    setActiveAction(`delete:${build.id}`);
    try {
      await api.deleteBuild(build.id);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setActiveAction(null);
    }
  }

  const busy = activeAction !== null;

  return (
    <section>
      <h2>{t("buildsHeading")}</h2>
      {error && <p className="error-message">{error}</p>}

      {builds.length === 0 && <p className="muted">{t("noSavedBuilds")}</p>}

      {builds.map((build) => (
        <div className="build-card" key={build.id}>
          <strong>{build.name || t("buildLabel", build.id)}</strong>{" "}
          {build.completed ? (
            <span className="badge badge-ok">
              {t("completedOn", new Date(build.completed_at).toLocaleString(DATE_LOCALES[language]))}
            </span>
          ) : (
            <span className="badge badge-warn">{t("notBuiltYet")}</span>
          )}
          {build.purpose && (
            <p>
              <strong>{t("buildPurposeLabel")}</strong> {build.purpose}
            </p>
          )}
          <ul>
            {build.components.map((c) => (
              <li key={c.id}>
                {c.category}: {c.name}
              </li>
            ))}
          </ul>
          {build.reason && <p className="muted">{build.reason}</p>}
          <div className="row">
            {!build.completed && (
              <button className="btn" onClick={() => handleComplete(build)} disabled={busy}>
                {activeAction === `complete:${build.id}` ? t("completing") : t("markComplete")}
              </button>
            )}
            <button className="btn btn-danger" onClick={() => handleDelete(build)} disabled={busy}>
              {activeAction === `delete:${build.id}` ? t("deleting") : t("delete")}
            </button>
          </div>
        </div>
      ))}
    </section>
  );
}

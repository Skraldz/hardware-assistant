import { useState } from "react";
import { api } from "../api.js";
import { useLanguage } from "../i18n/LanguageContext.jsx";

function StatusBadge({ label, status }) {
  const cls = status === "ok" ? "badge-ok" : status === "retried" ? "badge-warn" : "badge-error";
  return (
    <span className={`badge ${cls}`}>
      {label}: {status}
    </span>
  );
}

export default function RecommendView() {
  const { t } = useLanguage();
  const [prompt, setPrompt] = useState(() => t("defaultPrompt"));
  const [maxBuilds, setMaxBuilds] = useState(3);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.recommend(prompt, Number(maxBuilds)));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section>
      <h2>{t("recommendHeading")}</h2>
      <form onSubmit={handleSubmit}>
        <label>
          <span>{t("promptLabel")}</span>
          <textarea rows={3} value={prompt} onChange={(e) => setPrompt(e.target.value)} required />
        </label>
        <div className="row">
          <label>
            <span>{t("maxBuildsLabel")}</span>
            <input type="number" min="1" max="10" value={maxBuilds} onChange={(e) => setMaxBuilds(e.target.value)} />
          </label>
          <button className="btn" type="submit" disabled={loading}>
            {loading ? t("thinking") : t("recommend")}
          </button>
        </div>
      </form>

      {error && <p className="error-message">{error}</p>}

      {result && (
        <div style={{ marginTop: "1rem" }}>
          <p>
            <StatusBadge label={t("interpretLabel")} status={result.llm_used.interpret} />
            <StatusBadge label={t("rankLabel")} status={result.llm_used.rank} />
          </p>

          {result.missing.length > 0 && (
            <p className="error-message">{t("missingInInventory", result.missing.join(", "))}</p>
          )}

          {result.builds.length === 0 && result.missing.length === 0 && (
            <p className="muted">{t("noCompatibleBuilds")}</p>
          )}

          {result.builds.map((build, index) => (
            <div className="build-card" key={index}>
              <strong>{t("buildLabel", index + 1)}</strong>{" "}
              <span className="muted">{t("scoreLabel", build.score.toFixed(0))}</span>
              <ul>
                {build.components.map((c) => (
                  <li key={c.id}>
                    {c.category}: {c.name}
                  </li>
                ))}
              </ul>
              <p>{build.reason}</p>
              {build.warnings.length > 0 && <p className="muted">⚠ {build.warnings.join(" · ")}</p>}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

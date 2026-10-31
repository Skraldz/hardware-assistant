import { useState } from "react";
import { api } from "../api.js";
import { useLanguage } from "../i18n/LanguageContext.jsx";

function buildsSignature(builds) {
  return JSON.stringify(
    builds.map((b) =>
      b.components
        .map((c) => c.id)
        .slice()
        .sort((a, b2) => a - b2),
    ),
  );
}

function StatusBadge({ label, status }) {
  const cls = status === "ok" ? "badge-ok" : status === "retried" ? "badge-warn" : "badge-error";
  return (
    <span className={`badge ${cls}`}>
      {label}: {status}
    </span>
  );
}

function BuildCards({ result, t, messageIndex, saveState, onSaveBuild }) {
  return (
    <>
      <p>
        <StatusBadge label={t("interpretLabel")} status={result.llm_used.interpret} />
        <StatusBadge label={t("rankLabel")} status={result.llm_used.rank} />
      </p>
      {result.builds.map((build, index) => {
        const key = `${messageIndex}-${index}`;
        const state = saveState[key];
        return (
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
            <button
              className="btn btn-secondary"
              type="button"
              onClick={() => onSaveBuild(key, build)}
              disabled={state === "saving" || state === "saved"}
            >
              {state === "saved" ? t("buildSaved") : state === "saving" ? t("saving") : t("saveBuild")}
            </button>
          </div>
        );
      })}
    </>
  );
}

export default function RecommendView() {
  const { t } = useLanguage();
  // {role: "user"|"assistant", content, result?}. `result` (only on
  // assistant turns) carries the full structured response for that turn, so
  // every reply in the conversation keeps showing its own builds.
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState(() => t("defaultPrompt"));
  const [maxBuilds, setMaxBuilds] = useState(3);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  // Keyed by "<messageIndex>-<buildIndex>" -> "saving" | "saved", since a
  // build has no stable id of its own until it's actually saved.
  const [saveState, setSaveState] = useState({});

  async function handleSaveBuild(key, build) {
    setSaveState((prev) => ({ ...prev, [key]: "saving" }));
    try {
      await api.saveBuild({ components: build.components, reason: build.reason });
      setSaveState((prev) => ({ ...prev, [key]: "saved" }));
    } catch (err) {
      setSaveState((prev) => ({ ...prev, [key]: undefined }));
      setError(err.message);
    }
  }

  async function handleSend(event) {
    event.preventDefault();
    const content = input.trim();
    if (!content || loading) return;

    const conversation = [...messages.map(({ role, content: c }) => ({ role, content: c })), { role: "user", content }];
    setMessages((prev) => [...prev, { role: "user", content }]);
    setInput("");
    setError(null);
    setLoading(true);
    try {
      const result = await api.recommend(conversation, Number(maxBuilds));
      // The pipeline reruns in full on every turn (SPEC.md §5), so a pure
      // follow-up question ("how much FPS will I get on build 1?") still
      // comes back with a fresh `builds` array -- usually identical to what
      // was already shown, since nothing about the requirements changed.
      // Re-rendering the same cards would make a plain answer look like a
      // brand new recommendation, so only show them again if they actually
      // differ from the last turn that had any.
      const previousWithBuilds = [...messages].reverse().find((m) => m.result);
      const buildsUnchanged =
        !!previousWithBuilds &&
        buildsSignature(result.builds) === buildsSignature(previousWithBuilds.result.builds);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: result.assistant_message, result, buildsUnchanged },
      ]);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleReset() {
    setMessages([]);
    setError(null);
    setInput(t("defaultPrompt"));
    // saveState is keyed by "<messageIndex>-<buildIndex>", and a new
    // conversation's messages start back at index 0 -- without clearing
    // this too, a fresh build at the same index would inherit an older
    // conversation's "saved" state it was never actually saved under.
    setSaveState({});
  }

  return (
    <section>
      <h2>{t("recommendHeading")}</h2>

      <details className="score-guide">
        <summary>{t("scoreGuideSummary")}</summary>
        <p>{t("scoreGuideIntro")}</p>
        <ul>
          <li>{t("scoreGuideBase")}</li>
          <li>{t("scoreGuideWarnings")}</li>
          <li>{t("scoreGuidePreferences")}</li>
          <li>{t("scoreGuideLlmOrder")}</li>
        </ul>
      </details>

      {messages.length > 0 && (
        <div className="chat-log">
          {messages.map((m, i) => (
            <div className={`chat-message chat-${m.role}`} key={i}>
              <strong>{m.role === "user" ? t("youLabel") : t("assistantLabel")}</strong>
              <p>{m.content}</p>
              {m.result && m.result.builds.length === 0 && m.result.missing.length === 0 && (
                <p className="muted">{t("noCompatibleBuilds")}</p>
              )}
              {m.result && m.result.missing.length > 0 && (
                <p className="error-message">{t("missingInInventory", m.result.missing.join(", "))}</p>
              )}
              {m.result && m.result.builds.length > 0 && m.buildsUnchanged && (
                <p className="muted">{t("buildsUnchangedNote")}</p>
              )}
              {m.result && m.result.builds.length > 0 && !m.buildsUnchanged && (
                <BuildCards
                  result={m.result}
                  t={t}
                  messageIndex={i}
                  saveState={saveState}
                  onSaveBuild={handleSaveBuild}
                />
              )}
            </div>
          ))}
        </div>
      )}

      {error && <p className="error-message">{error}</p>}

      <form onSubmit={handleSend}>
        <label>
          <span>{t("promptLabel")}</span>
          <textarea rows={3} value={input} onChange={(e) => setInput(e.target.value)} required />
        </label>
        <div className="row">
          <label>
            <span>{t("maxBuildsLabel")}</span>
            <input
              type="number"
              min="1"
              max="10"
              value={maxBuilds}
              onChange={(e) => setMaxBuilds(e.target.value)}
            />
          </label>
          <button className="btn" type="submit" disabled={loading}>
            {loading ? t("thinking") : t("send")}
          </button>
          <button
            className="btn btn-secondary"
            type="button"
            onClick={handleReset}
            disabled={loading || messages.length === 0}
          >
            {t("newConversation")}
          </button>
        </div>
      </form>
    </section>
  );
}

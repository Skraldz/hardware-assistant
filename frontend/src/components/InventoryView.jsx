import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { useLanguage } from "../i18n/LanguageContext.jsx";

const CATEGORIES = ["cpu", "motherboard", "ram", "gpu", "storage", "psu", "case", "cooler"];
const CONDITIONS = ["new", "used", "faulty"];

function sortValue(component, key) {
  if (key === "specsVerified") return component.specs_verified ? 1 : 0;
  return component[key];
}

function compareComponents(a, b, sortKey) {
  const av = sortValue(a, sortKey);
  const bv = sortValue(b, sortKey);
  if (typeof av === "number" && typeof bv === "number") return av - bv;
  return String(av).localeCompare(String(bv));
}

export default function InventoryView() {
  const { t } = useLanguage();
  const [components, setComponents] = useState([]);
  const [loadError, setLoadError] = useState(null);
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [sortKey, setSortKey] = useState("category");
  const [sortDir, setSortDir] = useState("asc");

  // Defaults to the project's own default (true) until /api/health answers,
  // so the "Search"/"Extract directly" choice below always matches what the
  // backend will actually accept — see api.js's getHealth().
  const [webLookupEnabled, setWebLookupEnabled] = useState(true);

  const [searchName, setSearchName] = useState("");
  const [candidates, setCandidates] = useState([]);
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [extracted, setExtracted] = useState(null);
  const [confirmName, setConfirmName] = useState("");
  const [extractError, setExtractError] = useState(null);
  const [confirmQuantity, setConfirmQuantity] = useState(1);
  const [confirmCondition, setConfirmCondition] = useState("new");
  // Guards against an older, superseded search/extract call resolving after
  // a newer one and silently overwriting its result.
  const extractRequestId = useRef(0);

  const [manualName, setManualName] = useState("");
  const [manualCategory, setManualCategory] = useState("cpu");
  const [manualSpecsJson, setManualSpecsJson] = useState('{\n  "category": "cpu"\n}');
  const [manualQuantity, setManualQuantity] = useState(1);
  const [manualCondition, setManualCondition] = useState("new");
  const [manualError, setManualError] = useState(null);

  async function loadComponents() {
    try {
      setComponents(await api.listComponents());
      setLoadError(null);
    } catch (err) {
      setLoadError(err.message);
    }
  }

  useEffect(() => {
    loadComponents();
    api
      .getHealth()
      .then((health) => setWebLookupEnabled(health.enable_web_lookup))
      .catch(() => {
        /* keep the default; the health badge already surfaces this error */
      });
  }, []);

  function handleSort(key) {
    if (key === sortKey) {
      setSortDir((dir) => (dir === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  function resetSearchFlow() {
    setCandidates([]);
    setSelectedCandidate(null);
    setExtracted(null);
    setConfirmName("");
    setExtractError(null);
  }

  async function handleSearch(event) {
    event.preventDefault();
    resetSearchFlow();
    const requestId = ++extractRequestId.current;
    try {
      const res = await api.searchComponents(searchName);
      if (extractRequestId.current !== requestId) return;
      setCandidates(res.candidates);
    } catch (err) {
      if (extractRequestId.current !== requestId) return;
      setExtractError(err.message);
    }
  }

  async function handleExtractDirect(event) {
    event.preventDefault();
    const name = searchName;
    resetSearchFlow();
    const requestId = ++extractRequestId.current;
    try {
      const res = await api.extractComponent(name, null);
      if (extractRequestId.current !== requestId) return;
      setExtracted(res);
      setConfirmName(name);
    } catch (err) {
      if (extractRequestId.current !== requestId) return;
      setExtractError(err.message);
    }
  }

  async function handlePickCandidate(candidate) {
    const name = searchName;
    setSelectedCandidate(candidate);
    setExtracted(null);
    setConfirmName("");
    setExtractError(null);
    const requestId = ++extractRequestId.current;
    try {
      const res = await api.extractComponent(name, candidate);
      if (extractRequestId.current !== requestId) return;
      setExtracted(res);
      setConfirmName(name);
    } catch (err) {
      if (extractRequestId.current !== requestId) return;
      setExtractError(err.message);
    }
  }

  async function handleConfirmSave() {
    try {
      await api.createComponent({
        name: confirmName,
        quantity: Number(confirmQuantity),
        condition: confirmCondition,
        specs: extracted.specs,
        specs_source: extracted.specs_source,
        specs_verified: true,
      });
      setSearchName("");
      resetSearchFlow();
      await loadComponents();
    } catch (err) {
      setExtractError(err.message);
    }
  }

  async function handleManualAdd(event) {
    event.preventDefault();
    setManualError(null);
    try {
      const specs = JSON.parse(manualSpecsJson);
      if (specs.category && specs.category !== manualCategory) {
        setManualError(t("manualCategoryMismatch", specs.category, manualCategory));
        return;
      }
      specs.category = manualCategory;
      await api.createComponent({
        name: manualName,
        quantity: Number(manualQuantity),
        condition: manualCondition,
        specs,
        specs_source: "manual",
        specs_verified: true,
      });
      setManualName("");
      await loadComponents();
    } catch (err) {
      setManualError(err.message);
    }
  }

  async function handleDelete(id) {
    if (!window.confirm(t("confirmDeleteComponent"))) return;
    try {
      await api.deleteComponent(id);
      await loadComponents();
    } catch (err) {
      setLoadError(err.message);
    }
  }

  const isReviewing = extracted !== null;

  const visibleComponents = components
    .filter((c) => categoryFilter === "all" || c.category === categoryFilter)
    .sort((a, b) => (sortDir === "asc" ? 1 : -1) * compareComponents(a, b, sortKey));

  function sortableHeader(key, label) {
    const indicator = sortKey === key ? (sortDir === "asc" ? " ▲" : " ▼") : "";
    return (
      <th>
        <button type="button" className="sortable-header" onClick={() => handleSort(key)}>
          {label}
          {indicator}
        </button>
      </th>
    );
  }

  return (
    <>
      <section>
        <h2>{t("inventoryHeading", components.length)}</h2>
        {loadError && <p className="error-message">{loadError}</p>}
        <div className="chip-row">
          <button
            type="button"
            className={`chip${categoryFilter === "all" ? " active" : ""}`}
            onClick={() => setCategoryFilter("all")}
          >
            {t("allCategories")}
          </button>
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              type="button"
              className={`chip${categoryFilter === cat ? " active" : ""}`}
              onClick={() => setCategoryFilter(cat)}
            >
              {cat}
            </button>
          ))}
        </div>
        <table>
          <thead>
            <tr>
              {sortableHeader("category", t("colCategory"))}
              {sortableHeader("name", t("colName"))}
              {sortableHeader("quantity", t("colQuantity"))}
              {sortableHeader("condition", t("colCondition"))}
              {sortableHeader("specsVerified", t("colSpecsVerified"))}
              <th></th>
            </tr>
          </thead>
          <tbody>
            {visibleComponents.map((c) => (
              <tr key={c.id}>
                <td>{c.category}</td>
                <td>{c.name}</td>
                <td>{c.quantity}</td>
                <td>{c.condition}</td>
                <td>{c.specs_verified ? t("yes") : t("no")}</td>
                <td>
                  <button className="btn btn-danger" onClick={() => handleDelete(c.id)}>
                    {t("delete")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2>{webLookupEnabled ? t("addViaSearchHeading") : t("addViaExtractHeading")}</h2>
        <form onSubmit={webLookupEnabled ? handleSearch : handleExtractDirect} className="row">
          <label>
            <span>{t("componentNameLabel")}</span>
            <input
              value={searchName}
              onChange={(e) => setSearchName(e.target.value)}
              placeholder={t("componentNamePlaceholder")}
              disabled={isReviewing}
              required
            />
          </label>
          <button type="submit" className="btn" disabled={isReviewing}>
            {webLookupEnabled ? t("search") : t("extract")}
          </button>
        </form>
        {!webLookupEnabled && <p className="muted">{t("webLookupDisabledNotice")}</p>}

        {extractError && <p className="error-message">{extractError}</p>}

        {candidates.length > 0 && (
          <div>
            <p className="muted">{t("pickCandidatePrompt")}</p>
            {candidates.map((candidate) => (
              <div
                key={candidate.url}
                className={`candidate${selectedCandidate === candidate ? " selected" : ""}`}
                onClick={() => handlePickCandidate(candidate)}
              >
                <strong>{candidate.title}</strong>
                <div className="muted">{candidate.snippet}</div>
              </div>
            ))}
          </div>
        )}

        {extracted && (
          <div>
            <h3>{t("extractedSpecsHeading", confirmName, extracted.specs_source, extracted.llm_used)}</h3>
            <pre className="specs-preview">{JSON.stringify(extracted.specs, null, 2)}</pre>
            <div className="row">
              <label>
                <span>{t("quantityLabel")}</span>
                <input type="number" min="0" value={confirmQuantity} onChange={(e) => setConfirmQuantity(e.target.value)} />
              </label>
              <label>
                <span>{t("conditionLabel")}</span>
                <select value={confirmCondition} onChange={(e) => setConfirmCondition(e.target.value)}>
                  {CONDITIONS.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
              <button className="btn" onClick={handleConfirmSave}>
                {t("confirmAndSave")}
              </button>
              <button className="btn btn-secondary" onClick={resetSearchFlow} type="button">
                {t("cancel")}
              </button>
            </div>
          </div>
        )}
      </section>

      <section>
        <h2>{t("manualAddHeading")}</h2>
        <form onSubmit={handleManualAdd}>
          <div className="row">
            <label>
              <span>{t("nameLabel")}</span>
              <input value={manualName} onChange={(e) => setManualName(e.target.value)} required />
            </label>
            <label>
              <span>{t("categoryLabel")}</span>
              <select value={manualCategory} onChange={(e) => setManualCategory(e.target.value)}>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>{t("quantityLabel")}</span>
              <input type="number" min="0" value={manualQuantity} onChange={(e) => setManualQuantity(e.target.value)} />
            </label>
            <label>
              <span>{t("conditionLabel")}</span>
              <select value={manualCondition} onChange={(e) => setManualCondition(e.target.value)}>
                {CONDITIONS.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label>
            <span>{t("specsJsonLabel")}</span>
            <textarea rows={6} value={manualSpecsJson} onChange={(e) => setManualSpecsJson(e.target.value)} />
          </label>
          {manualError && <p className="error-message">{manualError}</p>}
          <button type="submit" className="btn">
            {t("add")}
          </button>
        </form>
      </section>
    </>
  );
}

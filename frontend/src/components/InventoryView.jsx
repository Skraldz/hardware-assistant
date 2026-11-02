import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { useLanguage } from "../i18n/LanguageContext.jsx";

const CATEGORIES = ["cpu", "motherboard", "ram", "gpu", "storage", "psu", "case", "cooler"];
const CONDITIONS = ["new", "used", "faulty"];

// One template per category, listing every field that schemas/components.py
// accepts for it (see CpuSpecs/MotherboardSpecs/etc.) so the manual-add JSON
// box always shows the full set of fields you can fill in, not just
// "category". Regenerated whenever the category dropdown changes.
const SPEC_TEMPLATES = {
  cpu: {
    category: "cpu",
    socket: null,
    cores: null,
    threads: null,
    tdp_w: null,
    integrated_graphics: null,
    memory_type: null,
  },
  motherboard: {
    category: "motherboard",
    socket: null,
    form_factor: null,
    memory_type: null,
    memory_slots: null,
    max_memory_gb: null,
    m2_slots: null,
    sata_ports: null,
    pcie_x16_slots: null,
  },
  ram: {
    category: "ram",
    memory_type: null,
    capacity_gb_per_module: null,
    modules: null,
    speed_mts: null,
    form: null,
  },
  gpu: {
    category: "gpu",
    vram_gb: null,
    tdp_w: null,
    length_mm: null,
    pcie_power_connectors: null,
    vendor: null,
  },
  storage: {
    category: "storage",
    interface: null,
    capacity_gb: null,
    form_factor: null,
  },
  psu: {
    category: "psu",
    wattage_w: null,
    form_factor: null,
    pcie_power_connectors: null,
    efficiency_rating: null,
  },
  case: {
    category: "case",
    supported_form_factors: null,
    max_gpu_length_mm: null,
    max_cooler_height_mm: null,
    psu_form_factor: null,
    drive_bays_3_5: null,
    drive_bays_2_5: null,
  },
  cooler: {
    category: "cooler",
    type: null,
    supported_sockets: null,
    height_mm: null,
    radiator_mm: null,
    tdp_rating_w: null,
  },
};

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

export default function InventoryView({ active = true }) {
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
  const [confirmReleaseYear, setConfirmReleaseYear] = useState("");
  const [extractError, setExtractError] = useState(null);
  const [confirmQuantity, setConfirmQuantity] = useState(1);
  const [confirmCondition, setConfirmCondition] = useState("new");
  // Guards against an older, superseded search/extract call resolving after
  // a newer one and silently overwriting its result.
  const extractRequestId = useRef(0);

  const [manualName, setManualName] = useState("");
  const [manualCategory, setManualCategory] = useState("cpu");
  const [manualSpecsJson, setManualSpecsJson] = useState(JSON.stringify(SPEC_TEMPLATES.cpu, null, 2));
  const [manualReleaseYear, setManualReleaseYear] = useState("");
  const [manualQuantity, setManualQuantity] = useState(1);
  const [manualCondition, setManualCondition] = useState("new");
  const [manualError, setManualError] = useState(null);

  // One bulk action at a time, so a slow clear/reseed can't overlap another.
  const [bulkAction, setBulkAction] = useState(null); // null | "clear" | "reseed"

  function handleManualCategoryChange(category) {
    setManualCategory(category);
    setManualSpecsJson(JSON.stringify(SPEC_TEMPLATES[category], null, 2));
  }

  async function loadComponents() {
    try {
      setComponents(await api.listComponents());
      setLoadError(null);
    } catch (err) {
      setLoadError(err.message);
    }
  }

  // Tabs stay mounted across switches (App.jsx), so refetch whenever this
  // one becomes active again -- not just on first mount -- to pick up
  // changes made elsewhere (e.g. a build marked complete in the Builds tab
  // decrements inventory quantities here).
  useEffect(() => {
    if (!active) return;
    loadComponents();
    api
      .getHealth()
      .then((health) => setWebLookupEnabled(health.enable_web_lookup))
      .catch(() => {
        /* keep the default; the health badge already surfaces this error */
      });
  }, [active]);

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
    setConfirmReleaseYear("");
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
      setConfirmReleaseYear(res.release_year ?? "");
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
      // The chosen candidate's snippet alone is frequently too short to
      // contain every spec -- send the rest of this same search's results
      // too, so the backend can pool whichever of them actually states
      // each value instead of relying on just the one clicked.
      const otherCandidates = candidates.filter((c) => c !== candidate);
      const res = await api.extractComponent(name, candidate, otherCandidates);
      if (extractRequestId.current !== requestId) return;
      setExtracted(res);
      setConfirmName(name);
      setConfirmReleaseYear(res.release_year ?? "");
    } catch (err) {
      if (extractRequestId.current !== requestId) return;
      setExtractError(err.message);
    }
  }

  async function handleConfirmSave() {
    try {
      await api.createComponent({
        name: confirmName,
        release_year: confirmReleaseYear ? Number(confirmReleaseYear) : null,
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
        release_year: manualReleaseYear ? Number(manualReleaseYear) : null,
        quantity: Number(manualQuantity),
        condition: manualCondition,
        specs,
        specs_source: "manual",
        specs_verified: true,
      });
      setManualName("");
      setManualReleaseYear("");
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

  async function handleClearInventory() {
    if (!window.confirm(t("confirmClearInventory"))) return;
    setBulkAction("clear");
    try {
      const res = await api.clearInventory();
      await loadComponents();
      window.alert(t("clearInventoryComplete", res.deleted_components, res.deleted_builds));
    } catch (err) {
      setLoadError(err.message);
    } finally {
      setBulkAction(null);
    }
  }

  async function handleReseedInventory() {
    if (!window.confirm(t("confirmReseedInventory"))) return;
    setBulkAction("reseed");
    try {
      const res = await api.reseedInventory();
      await loadComponents();
      window.alert(t("reseedComplete", res.added, res.skipped));
    } catch (err) {
      setLoadError(err.message);
    } finally {
      setBulkAction(null);
    }
  }

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
        <h2>
          {t(
            "inventoryHeading",
            components.length,
            components.filter((c) => c.quantity === 0).length,
          )}
        </h2>
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
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {sortableHeader("category", t("colCategory"))}
                {sortableHeader("name", t("colName"))}
                {sortableHeader("release_year", t("colReleaseYear"))}
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
                  <td>{c.release_year ?? ""}</td>
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
        </div>
      </section>

      <section>
        <h2>{t("bulkActionsHeading")}</h2>
        <div className="row">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={handleReseedInventory}
            disabled={bulkAction !== null}
          >
            {bulkAction === "reseed" ? t("reseeding") : t("reseedInventory")}
          </button>
          <button
            type="button"
            className="btn btn-danger"
            onClick={handleClearInventory}
            disabled={bulkAction !== null}
          >
            {bulkAction === "clear" ? t("clearing") : t("clearInventory")}
          </button>
        </div>
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
              required
            />
          </label>
          <button type="submit" className="btn">
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
                <div className="candidate-title-row">
                  <strong>{candidate.title}</strong>
                  <a
                    href={candidate.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="candidate-open-link"
                    onClick={(e) => e.stopPropagation()}
                    title={t("openInNewTab")}
                  >
                    {t("openInNewTab")} ↗
                  </a>
                </div>
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
                <span>{t("releaseYearLabel")}</span>
                <input
                  type="number"
                  min="1970"
                  max="2100"
                  value={confirmReleaseYear}
                  onChange={(e) => setConfirmReleaseYear(e.target.value)}
                  placeholder={t("releaseYearPlaceholder")}
                />
              </label>
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
              <select value={manualCategory} onChange={(e) => handleManualCategoryChange(e.target.value)}>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>{t("releaseYearLabel")}</span>
              <input
                type="number"
                min="1970"
                max="2100"
                value={manualReleaseYear}
                onChange={(e) => setManualReleaseYear(e.target.value)}
                placeholder={t("releaseYearPlaceholder")}
              />
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

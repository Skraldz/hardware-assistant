import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

const CATEGORIES = ["cpu", "motherboard", "ram", "gpu", "storage", "psu", "case", "cooler"];
const CONDITIONS = ["new", "used", "faulty"];

export default function InventoryView() {
  const [components, setComponents] = useState([]);
  const [loadError, setLoadError] = useState(null);

  // Defaults to the project's own default (true) until /api/health answers,
  // so the "Søg"/"Udtræk direkte" choice below always matches what the
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
        setManualError(
          `Specs-JSON'ens category ("${specs.category}") passer ikke med den valgte kategori ` +
            `("${manualCategory}"). Ret et af dem, før du gemmer.`
        );
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
    if (!window.confirm("Slet denne komponent fra lageret?")) return;
    try {
      await api.deleteComponent(id);
      await loadComponents();
    } catch (err) {
      setLoadError(err.message);
    }
  }

  const isReviewing = extracted !== null;

  return (
    <>
      <section>
        <h2>Lager ({components.length})</h2>
        {loadError && <p className="error-message">{loadError}</p>}
        <table>
          <thead>
            <tr>
              <th>Kategori</th>
              <th>Navn</th>
              <th>Antal</th>
              <th>Stand</th>
              <th>Specs bekræftet</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {components.map((c) => (
              <tr key={c.id}>
                <td>{c.category}</td>
                <td>{c.name}</td>
                <td>{c.quantity}</td>
                <td>{c.condition}</td>
                <td>{c.specs_verified ? "Ja" : "Nej"}</td>
                <td>
                  <button className="btn btn-danger" onClick={() => handleDelete(c.id)}>
                    Slet
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2>Tilføj komponent — {webLookupEnabled ? "søg på nettet" : "udtræk fra LLM'ens viden"}</h2>
        <form onSubmit={webLookupEnabled ? handleSearch : handleExtractDirect} className="row">
          <label>
            <span>Komponentnavn</span>
            <input
              value={searchName}
              onChange={(e) => setSearchName(e.target.value)}
              placeholder="fx RTX 2060 SUPER"
              disabled={isReviewing}
              required
            />
          </label>
          <button type="submit" className="btn" disabled={isReviewing}>
            {webLookupEnabled ? "Søg" : "Udtræk"}
          </button>
        </form>
        {!webLookupEnabled && (
          <p className="muted">
            Websøgning er deaktiveret på serveren (ENABLE_WEB_LOOKUP=false) — specs udtrækkes direkte fra
            LLM'ens egen viden om navnet.
          </p>
        )}

        {extractError && <p className="error-message">{extractError}</p>}

        {candidates.length > 0 && (
          <div>
            <p className="muted">Vælg det resultat, der matcher din komponent:</p>
            {candidates.map((candidate) => (
              <div
                key={candidate.url}
                className="candidate"
                onClick={() => handlePickCandidate(candidate)}
                style={{ background: selectedCandidate === candidate ? "#eef2ff" : undefined }}
              >
                <strong>{candidate.title}</strong>
                <div className="muted">{candidate.snippet}</div>
              </div>
            ))}
          </div>
        )}

        {extracted && (
          <div>
            <h3>
              Udtrukne specs for "{confirmName}" ({extracted.specs_source}, LLM: {extracted.llm_used})
            </h3>
            <pre style={{ background: "#f3f4f6", padding: "0.75rem", borderRadius: 6, overflowX: "auto" }}>
              {JSON.stringify(extracted.specs, null, 2)}
            </pre>
            <div className="row">
              <label>
                <span>Antal</span>
                <input type="number" min="0" value={confirmQuantity} onChange={(e) => setConfirmQuantity(e.target.value)} />
              </label>
              <label>
                <span>Stand</span>
                <select value={confirmCondition} onChange={(e) => setConfirmCondition(e.target.value)}>
                  {CONDITIONS.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
              <button className="btn" onClick={handleConfirmSave}>
                Bekræft og gem
              </button>
              <button className="btn btn-secondary" onClick={resetSearchFlow} type="button">
                Annullér
              </button>
            </div>
          </div>
        )}
      </section>

      <section>
        <h2>Tilføj komponent — manuelt (avanceret)</h2>
        <form onSubmit={handleManualAdd}>
          <div className="row">
            <label>
              <span>Navn</span>
              <input value={manualName} onChange={(e) => setManualName(e.target.value)} required />
            </label>
            <label>
              <span>Kategori</span>
              <select value={manualCategory} onChange={(e) => setManualCategory(e.target.value)}>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Antal</span>
              <input type="number" min="0" value={manualQuantity} onChange={(e) => setManualQuantity(e.target.value)} />
            </label>
            <label>
              <span>Stand</span>
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
            <span>Specs (JSON — felter du ikke kender kan udelades)</span>
            <textarea rows={6} value={manualSpecsJson} onChange={(e) => setManualSpecsJson(e.target.value)} />
          </label>
          {manualError && <p className="error-message">{manualError}</p>}
          <button type="submit" className="btn">
            Tilføj
          </button>
        </form>
      </section>
    </>
  );
}

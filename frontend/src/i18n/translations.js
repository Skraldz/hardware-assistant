// All UI chrome text (labels, buttons, headings, static messages) lives
// here. Backend-generated content — rule messages, LLM reasons, component
// category/condition enum values, raw spec JSON — is NOT translated by this
// dictionary: the backend always produces it in English (its prompts and
// error messages are written in English), regardless of which language is
// selected here. Selecting "Dansk" only swaps the UI chrome; data/messages
// coming from the API stay English. Translating those too would mean either
// re-implementing that logic client-side or asking the LLM to translate on
// the fly, both out of scope for a secondary frontend.
export const translations = {
  da: {
    appTitle: "Hardware Assistant",
    tabInventory: "Lager",
    tabRecommend: "Anbefaling",
    tabBuilds: "Builds",
    tabBackup: "Backup",

    healthChecking: "Tjekker status…",
    healthUnreachable: "Backend uanselig",
    healthUnreachableTitle: (error) => `Kan ikke nå backend: ${error} (klik for at prøve igen)`,
    healthOk: "Alt kører",
    healthDegraded: "Degraderet",
    healthTitle: (h) =>
      `DB: ${h.db} · Ollama: ${h.ollama} · Storage: ${h.storage} · Backup: ${h.backup_backend} (${h.backup_destination})`,

    inventoryHeading: (count) => `Lager (${count})`,
    allCategories: "Alle",
    colCategory: "Kategori",
    colName: "Navn",
    colQuantity: "Antal",
    colCondition: "Stand",
    colSpecsVerified: "Specs bekræftet",
    yes: "Ja",
    no: "Nej",
    delete: "Slet",
    confirmDeleteComponent: "Slet denne komponent fra lageret?",

    addViaSearchHeading: "Tilføj komponent — søg på nettet",
    addViaExtractHeading: "Tilføj komponent — udtræk fra LLM'ens viden",
    componentNameLabel: "Komponentnavn",
    componentNamePlaceholder: "fx RTX 2060 SUPER",
    search: "Søg",
    extract: "Udtræk",
    webLookupDisabledNotice:
      "Websøgning er deaktiveret på serveren (ENABLE_WEB_LOOKUP=false) — specs udtrækkes direkte fra LLM'ens egen viden om navnet.",
    pickCandidatePrompt: "Vælg det resultat, der matcher din komponent:",
    openInNewTab: "Åbn i ny fane",
    extractedSpecsHeading: (name, source, llmUsed) =>
      `Udtrukne specs for "${name}" (${source}, LLM: ${llmUsed})`,
    quantityLabel: "Antal",
    conditionLabel: "Stand",
    confirmAndSave: "Bekræft og gem",
    cancel: "Annullér",

    manualAddHeading: "Tilføj komponent — manuelt (avanceret)",
    nameLabel: "Navn",
    categoryLabel: "Kategori",
    specsJsonLabel: "Specs (JSON — felter du ikke kender kan udelades)",
    add: "Tilføj",
    manualCategoryMismatch: (jsonCategory, dropdownCategory) =>
      `Specs-JSON'ens category ("${jsonCategory}") passer ikke med den valgte kategori ("${dropdownCategory}"). Ret et af dem, før du gemmer.`,

    recommendHeading: "Anbefal en build",
    defaultPrompt: "headless pc til lokal AI",
    promptLabel: "Beskriv projektet i fri tekst",
    maxBuildsLabel: "Maks. antal builds",
    recommend: "Anbefal",
    send: "Send",
    newConversation: "Ny samtale",
    youLabel: "Dig",
    assistantLabel: "Assistent",
    thinking: "Tænker…",
    interpretLabel: "Fortolkning",
    rankLabel: "Rangering",
    missingInInventory: (list) => `Mangler i lageret: ${list}`,
    noCompatibleBuilds: "Ingen kompatible builds kunne sammensættes ud fra lageret.",
    buildsUnchangedNote: "Samme builds som før — se ovenfor.",
    buildLabel: (n) => `Build ${n}`,
    scoreLabel: (score) => `(score ${score})`,
    scoreGuideSummary: "Hvad betyder score'n?",
    scoreGuideIntro:
      "Hver build starter med en score på 100. Det er en deterministisk fallback-vurdering — ikke AI'ens egen mening.",
    scoreGuideBase: "Udgangspunkt: 100 point.",
    scoreGuideWarnings:
      "−5 point pr. kompatibilitetsadvarsel (⚠ nedenfor) — fx manglende data om et felt, der ikke kunne tjekkes fuldt ud.",
    scoreGuidePreferences:
      "Små, altid aktive justeringer mod lavere effektforbrug, mindre kabinet og tættere på dine minimumskrav — og meget stærkere udgaver af de samme justeringer, hvis du eksplicit beder om det (\"brug mindre strøm\", \"et lille kabinet\", \"ikke mere end jeg har brug for\").",
    scoreGuideLlmOrder:
      "Når \"Rangering\"-badgen viser \"ok\", er det faktisk AI'ens egen rangering og begrundelse, du ser — scoren vises stadig, men styrer ikke rækkefølgen i det tilfælde.",
    saveBuild: "Gem build",
    buildSaved: "Gemt ✓",
    saving: "Gemmer…",

    buildsHeading: "Gemte builds",
    noSavedBuilds: "Ingen gemte builds endnu. Gem en build fra Anbefaling-fanen.",
    notBuiltYet: "Ikke samlet endnu",
    completedOn: (date) => `Samlet ${date}`,
    markComplete: "Markér som samlet",
    completing: "Markerer…",
    deleting: "Sletter…",
    confirmCompleteBuild:
      "Markér denne build som samlet? Antallet af hver komponent i lageret nedsættes med 1.",
    confirmDeleteBuild: "Slet denne gemte build? Dette påvirker ikke selve lagerkomponenterne.",

    backupHeading: "Backup",
    activeBackendLabel: "Aktiv backend:",
    createBackupNow: "Lav backup nu",
    creatingBackup: "Laver backup…",
    colTimestamp: "Tidspunkt",
    colSize: "Størrelse",
    restore: "Gendan",
    restoring: "Gendanner…",
    confirmRestore: (name) => `Gendan backup "${name}"? Dette erstatter hele det nuværende lager.`,
    restoreComplete: (count) => `Gendannelse gennemført: ${count} komponenter.`,

    themeToggleToLight: "Skift til lys visning",
    themeToggleToDark: "Skift til mørk visning",
  },
  en: {
    appTitle: "Hardware Assistant",
    tabInventory: "Inventory",
    tabRecommend: "Recommend",
    tabBuilds: "Builds",
    tabBackup: "Backup",

    healthChecking: "Checking status…",
    healthUnreachable: "Backend unreachable",
    healthUnreachableTitle: (error) => `Can't reach backend: ${error} (click to retry)`,
    healthOk: "All systems go",
    healthDegraded: "Degraded",
    healthTitle: (h) =>
      `DB: ${h.db} · Ollama: ${h.ollama} · Storage: ${h.storage} · Backup: ${h.backup_backend} (${h.backup_destination})`,

    inventoryHeading: (count) => `Inventory (${count})`,
    allCategories: "All",
    colCategory: "Category",
    colName: "Name",
    colQuantity: "Quantity",
    colCondition: "Condition",
    colSpecsVerified: "Specs verified",
    yes: "Yes",
    no: "No",
    delete: "Delete",
    confirmDeleteComponent: "Delete this component from the inventory?",

    addViaSearchHeading: "Add component — search the web",
    addViaExtractHeading: "Add component — extract from LLM knowledge",
    componentNameLabel: "Component name",
    componentNamePlaceholder: "e.g. RTX 2060 SUPER",
    search: "Search",
    extract: "Extract",
    webLookupDisabledNotice:
      "Web lookup is disabled on the server (ENABLE_WEB_LOOKUP=false) — specs are extracted directly from the LLM's own knowledge of the name.",
    pickCandidatePrompt: "Pick the result that matches your component:",
    openInNewTab: "Open in new tab",
    extractedSpecsHeading: (name, source, llmUsed) =>
      `Extracted specs for "${name}" (${source}, LLM: ${llmUsed})`,
    quantityLabel: "Quantity",
    conditionLabel: "Condition",
    confirmAndSave: "Confirm and save",
    cancel: "Cancel",

    manualAddHeading: "Add component — manual (advanced)",
    nameLabel: "Name",
    categoryLabel: "Category",
    specsJsonLabel: "Specs (JSON — fields you don't know can be left out)",
    add: "Add",
    manualCategoryMismatch: (jsonCategory, dropdownCategory) =>
      `The specs JSON's category ("${jsonCategory}") doesn't match the selected category ("${dropdownCategory}"). Fix one of them before saving.`,

    recommendHeading: "Recommend a build",
    defaultPrompt: "headless pc for local AI",
    promptLabel: "Describe the project in free text",
    maxBuildsLabel: "Max. number of builds",
    recommend: "Recommend",
    send: "Send",
    newConversation: "New conversation",
    youLabel: "You",
    assistantLabel: "Assistant",
    thinking: "Thinking…",
    interpretLabel: "Interpretation",
    rankLabel: "Ranking",
    missingInInventory: (list) => `Missing in inventory: ${list}`,
    noCompatibleBuilds: "No compatible builds could be assembled from the inventory.",
    buildsUnchangedNote: "Same builds as before — see above.",
    buildLabel: (n) => `Build ${n}`,
    scoreLabel: (score) => `(score ${score})`,
    scoreGuideSummary: "What does the score mean?",
    scoreGuideIntro:
      "Every build starts with a score of 100. It's a deterministic fallback rating — not the AI's own opinion.",
    scoreGuideBase: "Starting point: 100 points.",
    scoreGuideWarnings:
      "−5 points per compatibility warning (⚠ below) — e.g. missing data for a field that couldn't be fully checked.",
    scoreGuidePreferences:
      "Small, always-on nudges toward lower power draw, a smaller case, and staying closer to your stated minimums — plus much stronger versions of the same nudges if you explicitly ask for it (\"use less power\", \"a small case\", \"nothing more than I need\").",
    scoreGuideLlmOrder:
      "When the \"Ranking\" badge shows \"ok\", you're actually seeing the AI's own ranking and reasoning — the score is still shown, but it isn't what decided the order in that case.",
    saveBuild: "Save build",
    buildSaved: "Saved ✓",
    saving: "Saving…",

    buildsHeading: "Saved builds",
    noSavedBuilds: "No saved builds yet. Save one from the Recommend tab.",
    notBuiltYet: "Not built yet",
    completedOn: (date) => `Built ${date}`,
    markComplete: "Mark as built",
    completing: "Marking…",
    deleting: "Deleting…",
    confirmCompleteBuild:
      "Mark this build as built? Each component's inventory quantity will be reduced by 1.",
    confirmDeleteBuild: "Delete this saved build? This does not affect the inventory components themselves.",

    backupHeading: "Backup",
    activeBackendLabel: "Active backend:",
    createBackupNow: "Create backup now",
    creatingBackup: "Creating backup…",
    colTimestamp: "Timestamp",
    colSize: "Size",
    restore: "Restore",
    restoring: "Restoring…",
    confirmRestore: (name) => `Restore backup "${name}"? This replaces the entire current inventory.`,
    restoreComplete: (count) => `Restore complete: ${count} components.`,

    themeToggleToLight: "Switch to light mode",
    themeToggleToDark: "Switch to dark mode",
  },
};

export const LANGUAGES = [
  { code: "da", label: "Dansk" },
  { code: "en", label: "English" },
];

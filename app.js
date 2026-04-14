const FACETS = [
  { key: "category", label: "Function" },
  { key: "regulatory_model", label: "Regulatory model" },
  { key: "regions", label: "Jurisdiction" },
  { key: "data_sensitivity", label: "Data sensitivity" },
  { key: "pricing_model", label: "Pricing" },
  { key: "integration_mode", label: "Integration" },
  { key: "buyer_type", label: "Buyer type" },
  { key: "api_spec_format", label: "API spec" },
  { key: "sdks", label: "SDKs" }
];

const state = {
  apiData: [],
  query: "",
  sort: "name",
  filters: {},
  loading: true,
  error: ""
};

const els = {
  heroStats: document.getElementById("heroStats"),
  filterSections: document.getElementById("filterSections"),
  activeFilters: document.getElementById("activeFilters"),
  resultsCount: document.getElementById("resultsCount"),
  resultsSubtitle: document.getElementById("resultsSubtitle"),
  resultsList: document.getElementById("resultsList"),
  emptyState: document.getElementById("emptyState"),
  searchInput: document.getElementById("searchInput"),
  sortSelect: document.getElementById("sortSelect"),
  clearSearchBtn: document.getElementById("clearSearchBtn"),
  resetFiltersBtn: document.getElementById("resetFiltersBtn"),
  statusMessage: document.getElementById("statusMessage")
};

function formatLabel(value) {
  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatMoneyLabel(key, value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const normalized = key
    .replace(/_usd$|_eur$|_gbp$/g, "")
    .replace(/_per_txn/g, " per txn")
    .replace(/_per_monthly/g, " monthly")
    .replace(/_per_call/g, " per call")
    .replace(/_calls_per_min/g, " calls/min")
    .replace(/_calls_per_day/g, " calls/day")
    .replace(/_calls_per_month/g, " calls/month")
    .replace(/_monthly/g, " monthly")
    .replaceAll("_", " ");

  return `${formatLabel(normalized)}: ${value}`;
}

function getFacetValue(api, key) {
  return api[key];
}

function setStatus(message, kind = "") {
  if (!message) {
    els.statusMessage.hidden = true;
    els.statusMessage.textContent = "";
    els.statusMessage.className = "status-message";
    return;
  }

  els.statusMessage.hidden = false;
  els.statusMessage.textContent = message;
  els.statusMessage.className = kind ? `status-message ${kind}` : "status-message";
}

function countValues(key) {
  const counts = new Map();

  state.apiData.forEach((api) => {
    const raw = getFacetValue(api, key);
    const values = Array.isArray(raw) ? raw : [raw];
    values.filter(Boolean).forEach((value) => {
      counts.set(value, (counts.get(value) || 0) + 1);
    });
  });

  return [...counts.entries()].sort((a, b) => {
    if (b[1] !== a[1]) {
      return b[1] - a[1];
    }
    return a[0].localeCompare(b[0]);
  });
}

function renderHeroStats() {
  const categoryCount = new Set(state.apiData.map((api) => api.category)).size;
  const sandboxCount = state.apiData.filter((api) => api.sandbox).length;
  const regionCount = new Set(state.apiData.flatMap((api) => api.regions || [])).size;
  const capabilityCount = new Set(state.apiData.flatMap((api) => api.capabilities || [])).size;

  els.heroStats.innerHTML = "";

  [
    `${state.apiData.length} seeded APIs`,
    `${categoryCount} fintech functions`,
    `${sandboxCount} with sandbox or test mode`,
    `${regionCount} region labels in use`,
    `${capabilityCount} tagged capabilities`
  ].forEach((text) => {
    const pill = document.createElement("span");
    pill.className = "stat-pill";
    pill.textContent = text;
    els.heroStats.appendChild(pill);
  });
}

function toggleFilter(key, value) {
  const current = state.filters[key] || [];
  const hasValue = current.includes(value);
  state.filters[key] = hasValue
    ? current.filter((entry) => entry !== value)
    : [...current, value];

  if (state.filters[key].length === 0) {
    delete state.filters[key];
  }

  render();
}

function renderFilters() {
  els.filterSections.innerHTML = "";

  FACETS.forEach((facet) => {
    const section = document.createElement("section");
    section.className = "filter-section";

    const label = document.createElement("div");
    label.className = "filter-label";
    label.textContent = facet.label;
    section.appendChild(label);

    const wrap = document.createElement("div");
    wrap.className = "filter-pills";

    countValues(facet.key).forEach(([value, count]) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "filter-pill";
      if ((state.filters[facet.key] || []).includes(value)) {
        btn.classList.add("active");
      }
      btn.addEventListener("click", () => toggleFilter(facet.key, value));

      const labelText = document.createElement("span");
      labelText.textContent = formatLabel(value);
      btn.appendChild(labelText);

      const countText = document.createElement("span");
      countText.className = "pill-count";
      countText.textContent = count;
      btn.appendChild(countText);

      wrap.appendChild(btn);
    });

    section.appendChild(wrap);
    els.filterSections.appendChild(section);
  });
}

function renderActiveFilters() {
  els.activeFilters.innerHTML = "";

  const chips = [];
  Object.entries(state.filters).forEach(([key, values]) => {
    values.forEach((value) => chips.push({ key, value }));
  });

  if (state.query.trim()) {
    chips.unshift({ key: "query", value: `"${state.query.trim()}"` });
  }

  if (chips.length === 0) {
    const empty = document.createElement("span");
    empty.className = "stat-pill";
    empty.textContent = "No filters applied";
    els.activeFilters.appendChild(empty);
    return;
  }

  chips.forEach(({ key, value }) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "active-filter";
    chip.textContent = key === "query" ? `Search: ${value}` : `${formatLabel(key)}: ${formatLabel(value)}`;
    chip.addEventListener("click", () => {
      if (key === "query") {
        state.query = "";
        els.searchInput.value = "";
      } else {
        toggleFilter(key, value);
        return;
      }
      render();
    });
    els.activeFilters.appendChild(chip);
  });
}

function matchesQuery(api) {
  const query = state.query.trim().toLowerCase();
  if (!query) {
    return true;
  }

  const haystack = [
    api.name,
    api.description,
    api.category,
    ...(api.subcategories || []),
    ...(api.capabilities || []),
    ...(api.regions || []),
    ...(api.supported_currencies || []),
    ...(api.pricing_model || []),
    ...(api.integration_mode || []),
    ...(api.buyer_type || []),
    ...(api.sdks || []),
    ...(api.api_spec_format || []),
    api.regulatory_model,
    api.data_sensitivity,
    api.pricing_indicative?.model,
    api.pricing_indicative?.notes,
    ...(api.compliance || [])
  ]
    .join(" ")
    .toLowerCase();

  return query
    .split(/\s+/)
    .filter(Boolean)
    .every((term) => haystack.includes(term));
}

function matchesFilters(api) {
  return Object.entries(state.filters).every(([key, values]) => {
    const raw = api[key];
    if (Array.isArray(raw)) {
      return values.some((value) => raw.includes(value));
    }
    return values.includes(raw);
  });
}

function sortResults(results) {
  const items = [...results];

  items.sort((a, b) => {
    switch (state.sort) {
      case "category":
        return a.category.localeCompare(b.category) || a.name.localeCompare(b.name);
      case "regionCount":
        return (b.regions || []).length - (a.regions || []).length || a.name.localeCompare(b.name);
      case "sandbox":
        return Number(Boolean(b.sandbox)) - Number(Boolean(a.sandbox)) || a.name.localeCompare(b.name);
      case "name":
      default:
        return a.name.localeCompare(b.name);
    }
  });

  return items;
}

function getFilteredResults() {
  return sortResults(state.apiData.filter((api) => matchesQuery(api) && matchesFilters(api)));
}

function makeTag(text, className) {
  return `<span class="tag ${className}">${text}</span>`;
}

function initials(name) {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function renderCard(api) {
  const compliance = api.compliance && api.compliance.length
    ? api.compliance.join(" · ")
    : "Compliance not tagged yet";
  const capabilities = (api.capabilities || []).slice(0, 5);
  const currencies = api.supported_currencies || [];
  const sdks = api.sdks || [];
  const specs = api.api_spec_format || [];
  const pricingIndicative = api.pricing_indicative || {};
  const pricingHighlights = Object.entries(pricingIndicative)
    .filter(([key, value]) => key !== "notes" && key !== "model")
    .map(([key, value]) => formatMoneyLabel(key, value))
    .filter(Boolean)
    .slice(0, 3);

  return `
    <article class="api-card">
      <div class="card-top">
        <div class="card-title-wrap">
          <div class="provider-icon">${initials(api.name)}</div>
          <div>
            <h2 class="card-title">${api.name}</h2>
            <div class="card-links">
              <a class="card-link" href="${api.website}" target="_blank" rel="noreferrer">Website</a>
              <a class="card-link" href="${api.docs}" target="_blank" rel="noreferrer">Docs</a>
            </div>
          </div>
        </div>
        <div class="card-badges">
          <span class="badge badge-category">${formatLabel(api.category)}</span>
          <span class="badge ${api.sandbox ? "badge-sandbox" : "badge-live"}">
            ${api.sandbox ? "Sandbox" : "No sandbox tag"}
          </span>
        </div>
      </div>

      <p class="card-summary">${api.description}</p>

      <div class="tag-row">
        ${makeTag(`Reg: ${formatLabel(api.regulatory_model)}`, "tag-teal")}
        ${makeTag(`Regions: ${(api.regions || []).join(" · ")}`, "tag-blue")}
        ${makeTag(`Sensitivity: ${formatLabel(api.data_sensitivity)}`, "tag-coral")}
        ${makeTag(`Pricing: ${(api.pricing_model || []).map(formatLabel).join(" · ")}`, "tag-amber")}
        ${makeTag(`Integration: ${(api.integration_mode || []).map(formatLabel).join(" · ")}`, "tag-purple")}
      </div>

      <div class="detail-grid">
        <div class="detail-block">
          <div class="detail-label">Capabilities</div>
          <div class="detail-values">
            ${
              capabilities.length
                ? capabilities.map((capability) => makeTag(formatLabel(capability), "tag-gray")).join("")
                : '<span class="detail-empty">Not tagged yet</span>'
            }
            ${
              (api.capabilities || []).length > capabilities.length
                ? `<span class="detail-more">+${api.capabilities.length - capabilities.length} more</span>`
                : ""
            }
          </div>
        </div>

        <div class="detail-block">
          <div class="detail-label">Developer surface</div>
          <div class="detail-values">
            ${
              sdks.length
                ? sdks.map((sdk) => makeTag(formatLabel(sdk), "tag-purple")).join("")
                : '<span class="detail-empty">No SDKs tagged</span>'
            }
            ${
              specs.length
                ? specs.map((spec) => makeTag(formatLabel(spec), "tag-blue")).join("")
                : ""
            }
          </div>
        </div>

        <div class="detail-block">
          <div class="detail-label">Coverage</div>
          <div class="detail-copy">
            ${
              currencies.length
                ? `${currencies.length} supported currencies · ${currencies.slice(0, 6).join(" · ")}${currencies.length > 6 ? " ..." : ""}`
                : "Currencies not tagged yet"
            }
          </div>
        </div>

        <div class="detail-block">
          <div class="detail-label">Indicative pricing</div>
          <div class="detail-copy">
            ${pricingIndicative.model ? formatLabel(pricingIndicative.model) : "Model not tagged"}
            ${pricingHighlights.length ? `<br>${pricingHighlights.join(" · ")}` : ""}
            ${pricingIndicative.notes ? `<br>${pricingIndicative.notes}` : ""}
          </div>
        </div>
      </div>

      <div class="card-footer">
        <div class="meta-list">
          <span>Auth: ${api.auth}</span>
          <span>HTTPS: ${api.https ? "Yes" : "No"}</span>
          <span>CORS: ${api.cors}</span>
          <span>Buyers: ${(api.buyer_type || []).map(formatLabel).join(" · ")}</span>
          <span>${compliance}</span>
        </div>
        <div class="meta-list">
          <span class="status-dot"></span>
          <span>${formatLabel(api.status)}</span>
        </div>
      </div>
    </article>
  `;
}

function renderResults() {
  const results = getFilteredResults();
  const filterCount = Object.values(state.filters).reduce((sum, values) => sum + values.length, 0);

  els.resultsCount.textContent = `${results.length} result${results.length === 1 ? "" : "s"}`;
  els.resultsSubtitle.textContent =
    filterCount || state.query.trim()
      ? `Filtered by ${filterCount} facet${filterCount === 1 ? "" : "s"}${state.query.trim() ? " and search query" : ""}.`
      : "Showing the current seed catalogue.";

  els.resultsList.innerHTML = results.map(renderCard).join("");
  els.emptyState.hidden = results.length !== 0;
}

function render() {
  if (state.loading) {
    setStatus("Loading API catalogue...");
    els.resultsCount.textContent = "Loading...";
    els.resultsSubtitle.textContent = "Reading data/apis.seed.json";
    els.resultsList.innerHTML = "";
    els.filterSections.innerHTML = "";
    els.activeFilters.innerHTML = "";
    els.emptyState.hidden = true;
    return;
  }

  if (state.error) {
    renderHeroStats();
    renderFilters();
    renderActiveFilters();
    els.resultsCount.textContent = "Data unavailable";
    els.resultsSubtitle.textContent = "The page could not load data/apis.seed.json.";
    els.resultsList.innerHTML = "";
    els.emptyState.hidden = true;
    setStatus(state.error, "error");
    return;
  }

  setStatus("");
  renderHeroStats();
  renderFilters();
  renderActiveFilters();
  renderResults();
}

async function loadApiData() {
  render();

  try {
    const response = await fetch("./data/apis.seed.json", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Request failed with ${response.status}`);
    }

    const json = await response.json();
    if (!Array.isArray(json)) {
      throw new Error("JSON root is not an array");
    }

    state.apiData = json;
    state.loading = false;
    state.error = "";
    render();
  } catch (error) {
    state.apiData = [];
    state.loading = false;
    state.error = `Could not load catalogue data. ${error.message}. Make sure you open the site through a local server, not directly as a file.`;
    render();
  }
}

els.searchInput.addEventListener("input", (event) => {
  state.query = event.target.value;
  render();
});

els.sortSelect.addEventListener("change", (event) => {
  state.sort = event.target.value;
  render();
});

els.clearSearchBtn.addEventListener("click", () => {
  state.query = "";
  els.searchInput.value = "";
  render();
});

els.resetFiltersBtn.addEventListener("click", () => {
  state.filters = {};
  state.query = "";
  state.sort = "name";
  els.searchInput.value = "";
  els.sortSelect.value = "name";
  render();
});

loadApiData();

/* Berlin Property Finder — Frontend */

let currentResults = null;
let aiModeAvailable = false;

// ===== Init =====
document.addEventListener("DOMContentLoaded", () => {
    loadDistricts();

    // Enter key triggers search
    document.getElementById("nlQuery").addEventListener("keydown", (e) => {
        if (e.key === "Enter") doSearch();
    });
});

// ===== API calls =====
async function loadDistricts() {
    try {
        const resp = await fetch("/api/districts");
        const data = await resp.json();
        aiModeAvailable = data.ai_mode;

        // Populate district dropdown
        const select = document.getElementById("district");
        data.districts.forEach((d) => {
            const opt = document.createElement("option");
            opt.value = d.name;
            opt.textContent = `${d.name} (${formatEur(d.avg_price_m2)}/m²)`;
            select.appendChild(opt);
        });

        // Populate reference table
        const tbody = document.getElementById("districtTableBody");
        data.districts.forEach((d) => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${d.name}</td>
                <td>${formatEur(d.avg_price_m2)}/m²</td>
                <td>${d.growth_pct > 0 ? "+" : ""}${d.growth_pct}%</td>
                <td><span class="tier-badge tier-${d.tier}">${d.tier}</span></td>
            `;
            tbody.appendChild(tr);
        });

        // Update search mode badge
        updateModeBadge();
    } catch (err) {
        console.error("Failed to load districts:", err);
    }
}

function _collectSearchBody() {
    const query = document.getElementById("nlQuery").value.trim();
    const budget = document.getElementById("budget").value;
    const propertyType = document.getElementById("propertyType").value;
    const district = document.getElementById("district").value;
    const minSize = document.getElementById("minSize").value;
    const sortBy = document.getElementById("sortBy").value;

    const body = { query };
    if (budget) body.budget = parseFloat(budget);
    if (propertyType) body.property_type = propertyType;
    if (district) body.districts = [district];
    if (minSize) body.min_size = parseFloat(minSize);
    if (sortBy) body.sort_by = sortBy;
    return body;
}

async function _runSearch(endpoint) {
    showLoading(true);
    hideResults();
    try {
        const resp = await fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(_collectSearchBody()),
        });
        if (resp.status === 401) {
            window.location.href = "/login?next=/";
            return;
        }
        if (resp.status === 402) {
            const data = await resp.json().catch(() => ({}));
            window.location.href = data.pricing_url || "/pricing";
            return;
        }
        const data = await resp.json();
        currentResults = data;
        renderResults(data);
    } catch (err) {
        console.error("Search failed:", err);
        showError("Search failed. Please try again.");
    } finally {
        showLoading(false);
    }
}

async function doSearch() {
    return _runSearch("/api/search");
}

async function doAgentSearch() {
    const query = document.getElementById("nlQuery").value.trim();
    if (!query) {
        showError("Agent search needs a natural-language query.");
        return;
    }
    return _runSearch("/api/agent-search");
}

// ===== Rendering =====
function renderResults(data) {
    // Demo banner
    const demoBanner = document.getElementById("demoBanner");
    if (data.is_demo_data) {
        demoBanner.style.display = "block";
        document.getElementById("demoMessage").textContent =
            data.error || "Showing sample data for demonstration.";
    } else {
        demoBanner.style.display = "none";
    }

    // Parsed params feedback
    const parsedDiv = document.getElementById("parsedParams");
    if (data.parsed_params) {
        const pp = data.parsed_params;
        let tags = [];
        if (pp.budget) tags.push(`Budget: ${formatEur(pp.budget)}`);
        if (pp.property_type && pp.property_type !== "all") tags.push(`Type: ${pp.property_type}`);
        if (pp.districts && pp.districts.length) tags.push(`Districts: ${pp.districts.join(", ")}`);
        if (pp.min_size) tags.push(`Min size: ${pp.min_size} m²`);
        if (pp.sort_by) tags.push(`Sort: ${pp.sort_by.replace("_", " ")}`);

        if (tags.length) {
            parsedDiv.innerHTML =
                `<strong>Interpreted as:</strong> ` +
                tags.map((t) => `<span class="param-tag">${t}</span>`).join(" ");
            parsedDiv.style.display = "block";
        } else {
            parsedDiv.style.display = "none";
        }
    } else {
        parsedDiv.style.display = "none";
    }

    // Update mode badge
    updateModeBadge(data.search_mode);

    // Summary
    const summary = document.getElementById("resultsSummary");
    const summaryText = document.getElementById("summaryText");
    summary.style.display = "block";
    summaryText.textContent =
        `Found ${data.total_count} properties — showing ${data.filtered_count} within your criteria`;

    // Render cards
    const grid = document.getElementById("resultsGrid");
    grid.innerHTML = "";

    if (data.properties.length === 0) {
        grid.innerHTML = `
            <div class="loading" style="display:block;">
                <p>No properties match your criteria. Try adjusting your budget or filters.</p>
            </div>
        `;
        return;
    }

    data.properties.forEach((p) => {
        grid.appendChild(createPropertyCard(p));
    });
}

function createPropertyCard(p) {
    const card = document.createElement("div");
    card.className = "property-card";

    const rating = p.rating;
    const grade = rating ? rating.grade : "?";
    const gradeClass = rating ? `grade-${grade}` : "";
    const labelClass = rating ? `label-${grade}` : "";

    // Image
    let imageHtml;
    if (p.image_url) {
        imageHtml = `<img src="${escapeHtml(p.image_url)}" alt="${escapeHtml(p.title)}" loading="lazy">`;
    } else {
        const typeIcons = { land: "🏗️", apartment: "🏢", house: "🏠" };
        imageHtml = `<span style="font-size:2rem">${typeIcons[p.property_type] || "🏠"}</span>`;
    }

    // Stars
    let starsHtml = "";
    if (rating) {
        const full = rating.stars;
        const empty = 5 - full;
        starsHtml = "★".repeat(full) + "☆".repeat(empty);
    }

    // Price comparison
    let comparisonHtml = "";
    if (rating && p.price_per_m2 && rating.district_avg_price) {
        const pctText = rating.price_vs_avg_pct <= 100
            ? `${(100 - rating.price_vs_avg_pct).toFixed(0)}% below avg`
            : `${(rating.price_vs_avg_pct - 100).toFixed(0)}% above avg`;
        comparisonHtml = `
            <span class="detail-item">
                <span>${formatEur(p.price_per_m2)}/m² vs avg ${formatEur(rating.district_avg_price)}/m² (${pctText})</span>
            </span>
        `;
    }

    // Score bars + per-score explanations
    let scoreBarsHtml = "";
    if (rating) {
        let dealWhy = "";
        if (rating.price_vs_avg_pct != null) {
            const diff = rating.price_vs_avg_pct - 100;
            const where = diff <= 0
                ? `${(-diff).toFixed(0)}% below district avg`
                : `${diff.toFixed(0)}% above district avg`;
            dealWhy = `<div class="score-why">Listed at ${where} (${formatEur(p.price_per_m2)}/m² vs ${formatEur(rating.district_avg_price)}/m²)</div>`;
        }
        let growthWhy = "";
        if (rating.district_tier) {
            const tier = rating.district_tier;
            const growth = rating.district_growth_pct;
            const tierBonus = { emerging: 20, budget: 15, mid: 5, high: 0, premium: -5 }[tier] ?? 0;
            const sign = growth >= 0 ? "+" : "";
            const bonusStr = tierBonus >= 0 ? `+${tierBonus}` : `${tierBonus}`;
            growthWhy = `<div class="score-why">${tier} district, ${sign}${growth}%/yr → tier bonus ${bonusStr}</div>`;
        }
        scoreBarsHtml = `
            <div class="score-bars">
                <div class="score-bar">
                    <div class="score-bar-label">
                        <span>Deal Score</span>
                        <span>${rating.deal_score}</span>
                    </div>
                    <div class="score-bar-track">
                        <div class="score-bar-fill" style="width:${rating.deal_score}%;background:${scoreColor(rating.deal_score)}"></div>
                    </div>
                    ${dealWhy}
                </div>
                <div class="score-bar">
                    <div class="score-bar-label">
                        <span>Growth Potential</span>
                        <span>${rating.growth_score}</span>
                    </div>
                    <div class="score-bar-track">
                        <div class="score-bar-fill" style="width:${rating.growth_score}%;background:${scoreColor(rating.growth_score)}"></div>
                    </div>
                    ${growthWhy}
                </div>
            </div>
        `;
    }

    // Rating note
    let noteHtml = "";
    if (p.rating_note) {
        noteHtml = `<div class="card-note">${escapeHtml(p.rating_note)}</div>`;
    }

    card.innerHTML = `
        <div class="card-image">${imageHtml}</div>
        <div class="card-body">
            <div class="card-header">
                <div>
                    <div class="card-title">${escapeHtml(p.title)}</div>
                    <div class="card-address">${escapeHtml(p.address)}${p.district ? ` — ${escapeHtml(p.district)}` : ""}</div>
                </div>
                ${rating ? `<div class="grade-badge ${gradeClass}">${grade}</div>` : ""}
            </div>
            ${rating ? `<div class="stars">${starsHtml}</div>` : ""}
            <div class="card-details">
                ${p.price != null ? `<span class="detail-item"><strong>${formatEur(p.price)}</strong></span>` : ""}
                ${p.area_m2 != null ? `<span class="detail-item"><strong>${p.area_m2} m²</strong></span>` : ""}
                ${p.rooms != null ? `<span class="detail-item"><strong>${p.rooms}</strong> <span>rooms</span></span>` : ""}
                ${p.property_type ? `<span class="detail-item"><span>${p.property_type}</span></span>` : ""}
            </div>
            ${comparisonHtml}
            ${scoreBarsHtml}
            ${noteHtml}
            <div class="card-footer">
                ${rating ? `<span class="card-label ${labelClass}">${escapeHtml(rating.label)}</span>` : "<span></span>"}
                <a class="card-link" href="${escapeHtml(p.url)}" target="_blank" rel="noopener">View on ImmoScout24 &rarr;</a>
            </div>
        </div>
    `;

    return card;
}

// ===== UI Helpers =====
function toggleFilters() {
    const panel = document.getElementById("filtersPanel");
    const text = document.getElementById("filtersToggleText");
    panel.classList.toggle("open");
    text.textContent = panel.classList.contains("open") ? "Hide filters" : "Show filters";
}

function toggleDistrictRef() {
    const panel = document.getElementById("districtRefPanel");
    panel.style.display = panel.style.display === "none" ? "block" : "none";
}

function showLoading(show) {
    document.getElementById("loading").style.display = show ? "block" : "none";
    document.getElementById("searchBtn").disabled = show;
}

function hideResults() {
    document.getElementById("resultsGrid").innerHTML = "";
    document.getElementById("resultsSummary").style.display = "none";
    document.getElementById("demoBanner").style.display = "none";
    document.getElementById("parsedParams").style.display = "none";
}

function showError(msg) {
    const grid = document.getElementById("resultsGrid");
    grid.innerHTML = `<div class="demo-banner" style="display:block;background:#fecaca;border-color:#f87171;color:#991b1b;">
        <strong>Error</strong> — ${escapeHtml(msg)}</div>`;
}

function updateModeBadge(mode) {
    const badge = document.getElementById("searchModeBadge");
    if (mode === "ai") {
        badge.textContent = "AI-powered search";
        badge.className = "search-mode-badge active ai";
    } else if (mode === "keyword") {
        badge.textContent = "Keyword search";
        badge.className = "search-mode-badge active keyword";
    } else {
        badge.className = "search-mode-badge";
        badge.classList.toggle("active", aiModeAvailable);
        if (aiModeAvailable) {
            badge.textContent = "AI search available";
            badge.classList.add("ai");
        }
    }
}

// ===== Formatting =====
function formatEur(num) {
    if (num == null) return "—";
    return new Intl.NumberFormat("de-DE", {
        style: "currency",
        currency: "EUR",
        maximumFractionDigits: 0,
    }).format(num);
}

function scoreColor(score) {
    if (score >= 80) return "var(--grade-a)";
    if (score >= 65) return "var(--grade-b)";
    if (score >= 50) return "var(--grade-c)";
    if (score >= 35) return "var(--grade-d)";
    return "var(--grade-f)";
}

function escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}

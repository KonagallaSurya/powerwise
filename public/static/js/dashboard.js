const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
const pageNames = {
  overview: ["Overview", "YOUR ENERGY AT A GLANCE", "A clear view of your recorded usage and estimated energy footprint."],
  consumption: ["Consumption", "METER YOUR USAGE", "Enter, review and manage electricity readings."],
  appliances: ["Appliances", "UNDERSTAND YOUR LOAD", "Estimate usage from appliance power ratings and operating hours."],
  billing: ["Bill calculator", "PLAN YOUR BILL", "Configure your provider tariff and calculate an estimate."],
  analytics: ["Analytics & reports", "SEE THE TRENDS", "Explore historical usage and export records."],
  alerts: ["Alerts", "STAY WITHIN YOUR GOALS", "Usage notifications based on your configured limits."],
  advisor: ["Energy advisor", "SMALL CHANGES ADD UP", "Practical, rule-based ideas from your entered appliance details."],
  settings: ["Limits & devices", "MAKE IT YOURS", "Set usage goals and prepare credentials for future hardware."]
};
const chartInstances = {};
let pendingSimulation = false;

function toast(message, error = false) {
  const stack = document.querySelector("#toast-stack");
  const item = document.createElement("div");
  item.className = `toast-message${error ? " error" : ""}`;
  item.textContent = message;
  stack.append(item);
  window.setTimeout(() => item.remove(), 4200);
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (options.method && options.method !== "GET") headers.set("X-CSRFToken", csrfToken);
  const response = await fetch(`/api${path}`, { ...options, headers });
  if (response.status === 401) {
    window.location.assign("/login");
    throw new Error("Please sign in again.");
  }
  const contentType = response.headers.get("content-type") || "";
  const result = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) throw new Error(result.message || "The request could not be completed.");
  return result;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[char]);
}
function fmt(value, digits = 2) { return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: digits }); }
function empty(message, icon = "fa-inbox") {
  return `<div class="empty-state"><i class="fa-regular ${icon}"></i>${escapeHtml(message)}</div>`;
}
function showError(message) {
  const box = document.querySelector("#global-error");
  box.textContent = message;
  box.classList.remove("d-none");
  window.setTimeout(() => box.classList.add("d-none"), 7000);
}
function setChart(id, labels, values, color, label) {
  const canvas = document.getElementById(id);
  if (!canvas || !window.Chart) return;
  if (chartInstances[id]) chartInstances[id].destroy();
  chartInstances[id] = new Chart(canvas, {
    type: "line",
    data: { labels, datasets: [{ label, data: values, borderColor: color, backgroundColor: `${color}22`, fill: true, tension: .35, pointRadius: 2, pointHoverRadius: 5 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { backgroundColor: "#17243a", titleColor: "#fff", bodyColor: "#d4dfed" } },
      scales: {
        x: { grid: { display: false }, ticks: { color: "#7889a1", maxTicksLimit: 8, font: { size: 9 } } },
        y: { beginAtZero: true, grid: { color: "#253249" }, ticks: { color: "#7889a1", font: { size: 9 } } }
      }
    }
  });
}

function readingRows(items, compact = false) {
  if (!items.length) return empty("No readings yet. Add your first reading to get started.");
  return items.map((item) => `<div class="reading-row"><span class="reading-mark"><i class="fa-solid fa-bolt"></i></span><div class="row-main"><strong>${escapeHtml(item.appliance_name || "Electricity reading")}</strong><small>${new Date(item.recorded_at).toLocaleString()} · ${escapeHtml(item.source)}</small></div><div class="row-value">${fmt(item.energy_kwh, 3)} kWh<small>${item.power_w == null ? "energy record" : `${fmt(item.power_w, 1)} W`}</small></div>${compact ? "" : `<button class="small-action" data-edit-reading="${item.id}" aria-label="Edit reading"><i class="fa-solid fa-pen"></i></button><button class="small-action danger" data-delete-reading="${item.id}" aria-label="Delete reading"><i class="fa-solid fa-trash"></i></button>`}</div>`).join("");
}

async function loadOverview() {
  const data = await api("/dashboard/summary");
  document.querySelector("#metric-units").textContent = fmt(data.total_consumption_kwh, 2);
  document.querySelector("#metric-power").textContent = data.current_power_w == null ? "—" : fmt(data.current_power_w, 1);
  document.querySelector("#power-basis").textContent = data.current_power_basis || "Available when a reading includes power";
  document.querySelector("#metric-bill").textContent = data.estimated_monthly_bill == null ? "—" : fmt(data.estimated_monthly_bill, 2);
  document.querySelector("#bill-caption").textContent = data.monthly_bill_note;
  document.querySelector("#metric-average").textContent = fmt(data.average_daily_kwh, 2);
  document.querySelector("#metric-remaining").textContent = data.remaining_monthly_kwh == null ? "—" : fmt(data.remaining_monthly_kwh, 2);
  document.querySelector("#limit-caption").textContent = data.monthly_limit_kwh == null ? "Set a monthly limit in settings" : `${fmt(data.monthly_limit_kwh, 1)} kWh configured`;
  document.querySelector("#month-comparison").textContent = data.month_change_percent == null ? `${fmt(data.previous_month_kwh, 2)} kWh last month` : `${data.month_change_percent >= 0 ? "+" : ""}${fmt(data.month_change_percent, 1)}% vs last month`;
  setChart("daily-chart", data.daily.map((x) => x.date.slice(8)), data.daily.map((x) => x.kwh), "#4e8dff", "kWh");
  setChart("monthly-chart", data.monthly.map((x) => x.month), data.monthly.map((x) => x.kwh), "#32d296", "kWh");
  document.querySelector("#recent-readings").innerHTML = readingRows(data.recent_readings || [], true);
  const alerts = data.recent_alerts || [];
  document.querySelector("#recent-alerts").innerHTML = alerts.length ? alerts.map(alertRow).join("") : empty("No alerts. Configure a usage limit to get started.", "fa-bell");
  await loadAlertsCount();
}

function alertRow(alert) {
  return `<div class="alert-row"><span class="severity-dot ${escapeHtml(alert.severity)}"></span><div class="row-main"><strong>${escapeHtml(alert.severity.toUpperCase())} · ${escapeHtml(alert.period)} usage</strong><small>${escapeHtml(alert.description)} · ${new Date(alert.created_at).toLocaleString()}</small></div>${alert.is_read ? '<span class="metric-tag muted-tag">READ</span>' : `<button class="small-action" data-read-alert="${alert.id}">Mark read</button>`}</div>`;
}

async function loadAlertsCount() {
  const result = await api("/alerts");
  const unread = result.alerts.filter((a) => !a.is_read).length;
  document.querySelector("#alert-count").textContent = unread ? unread : "";
}

async function loadReadings() {
  const params = new URLSearchParams();
  const start = document.querySelector("#reading-start").value;
  const end = document.querySelector("#reading-end").value;
  if (start) params.set("start", `${start}T00:00:00`);
  if (end) params.set("end", `${end}T23:59:59`);
  const data = await api(`/consumption${params.size ? `?${params}` : ""}`);
  const rows = data.readings || [];
  document.querySelector("#readings-table").innerHTML = rows.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>Recorded</th><th>Appliance</th><th>Energy</th><th>Power</th><th>Source</th><th></th></tr></thead><tbody>${rows.map((r) => `<tr><td>${new Date(r.recorded_at).toLocaleString()}</td><td>${escapeHtml(r.appliance_name || "—")}</td><td>${fmt(r.energy_kwh, 3)} kWh</td><td>${r.power_w == null ? "—" : `${fmt(r.power_w, 1)} W`}</td><td>${escapeHtml(r.source)}</td><td class="table-actions"><button class="small-action" data-edit-reading="${r.id}" title="Edit"><i class="fa-solid fa-pen"></i></button><button class="small-action danger" data-delete-reading="${r.id}" title="Delete"><i class="fa-solid fa-trash"></i></button></td></tr>`).join("")}</tbody></table></div>` : empty("No readings match this filter.");
}

async function loadAppliances() {
  const result = await api("/appliances");
  const appliances = result.appliances || [];
  const select = document.querySelector("#reading-appliance");
  select.innerHTML = '<option value="">No appliance</option>' + appliances.map((a) => `<option value="${a.id}">${escapeHtml(a.name)}</option>`).join("");
  document.querySelector("#appliance-list").innerHTML = appliances.length ? appliances.map((a) => `<article class="appliance-card"><div class="appliance-card-top"><div><h3>${escapeHtml(a.name)}</h3><p>${escapeHtml(a.category)} · ${fmt(a.power_w, 1)} W</p></div><span class="${a.is_on ? "on-chip" : "off-chip"}">${a.is_on ? "RUNNING" : "OFF"}</span></div><div class="appliance-stats"><span>Daily estimate<strong>${fmt(a.daily_estimate_kwh, 2)} kWh</strong></span><span>Monthly estimate<strong>${fmt(a.monthly_estimate_kwh, 1)} kWh</strong></span><span>Qty<strong>${a.quantity}</strong></span></div><div class="appliance-actions"><button class="small-action" data-edit-appliance="${a.id}">Edit</button><button class="small-action danger" data-delete-appliance="${a.id}">Delete</button></div></article>`).join("") : empty("Add appliances to estimate their energy use.");
}

async function loadTariffs() {
  const result = await api("/billing/tariffs");
  if (result.slabs.length) document.querySelector("#tariff-form [name=slabs]").value = JSON.stringify(result.slabs.map(({ lower_units, upper_units, rate_per_unit }) => ({ lower_units, upper_units, rate_per_unit })), null, 2);
}
async function loadBills() {
  const result = await api("/billing/history");
  const bills = result.bills || [];
  document.querySelector("#bill-history").innerHTML = bills.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>Billing period</th><th>Units</th><th>Estimated bill</th><th>Calculated</th></tr></thead><tbody>${bills.map((b) => `<tr><td>${b.period_start} – ${b.period_end}</td><td>${fmt(b.units, 2)} kWh</td><td>${fmt(b.total_amount, 2)}</td><td>${new Date(b.created_at).toLocaleDateString()}</td></tr>`).join("")}</tbody></table></div>` : empty("No bill estimates yet. Configure a tariff to calculate your first.");
}
async function loadLimits() {
  const result = await api("/limits");
  for (const limit of result.limits) {
    const input = document.querySelector(`#limits-form [name="${limit.period}"]`);
    if (input) input.value = limit.limit_kwh;
  }
}
async function loadAlerts() {
  const result = await api("/alerts");
  document.querySelector("#alert-list").innerHTML = result.alerts.length ? result.alerts.map(alertRow).join("") : empty("No limit alerts yet. Your usage is below configured thresholds or limits are not set.", "fa-bell");
  await loadAlertsCount();
}
async function loadRecommendations() {
  const result = await api("/recommendations");
  document.querySelector("#recommendation-list").innerHTML = result.recommendations.length ? result.recommendations.map((r) => `<article class="recommendation-card"><i class="fa-regular fa-lightbulb"></i><h3>${escapeHtml(r.title)}</h3><p>${escapeHtml(r.description)}</p><div class="saving-label">${r.estimated_saving_kwh == null ? "Savings not available" : `Potential: ~${fmt(r.estimated_saving_kwh, 2)} kWh / month${r.estimated_saving_amount == null ? "" : ` · ~${fmt(r.estimated_saving_amount, 2)} currency units`}`}</div></article>`).join("") : empty("Add appliances to receive tailored tips.", "fa-lightbulb");
}
async function loadDevices() {
  const result = await api("/devices");
  document.querySelector("#device-list").innerHTML = result.devices.length ? result.devices.map((d) => `<div class="device-row"><span class="reading-mark"><i class="fa-solid fa-microchip"></i></span><div class="row-main"><strong>${escapeHtml(d.name)}</strong><small>Created ${new Date(d.created_at).toLocaleDateString()} · ${d.is_active ? "Active" : "Inactive"}</small></div><button class="small-action danger" data-delete-device="${d.id}" aria-label="Revoke device credential">Revoke</button></div>`).join("") : empty("No device credentials created.");
}
async function loadAnalytics() {
  const period = document.querySelector("#report-period").value;
  const result = await api(`/analytics/${period}`);
  document.querySelector("#report-summary").textContent = `${fmt(result.total_kwh, 2)} kWh recorded in this report · ${result.basis}`;
  setChart("report-chart", result.values.map((x) => x.period), result.values.map((x) => x.kwh), "#4e8dff", "Recorded kWh");
  const appliances = result.appliances || [];
  const applianceTable = appliances.length ? `<div class="table-wrap mt-3"><table class="data-table"><thead><tr><th>Appliance</th><th>Monthly estimate</th><th>Basis</th></tr></thead><tbody>${appliances.map((a) => `<tr><td>${escapeHtml(a.name)}</td><td>${fmt(a.estimated_monthly_kwh, 2)} kWh</td><td>${escapeHtml(a.basis)}</td></tr>`).join("")}</tbody></table></div>` : "";
  const bills = result.bill_comparisons || [];
  const billTable = bills.length ? `<h3 class="mt-4 mb-2 fs-6">Saved bill comparisons</h3><div class="table-wrap"><table class="data-table"><thead><tr><th>Billing period</th><th>Units</th><th>Estimated amount</th><th>Change</th></tr></thead><tbody>${bills.map((b) => `<tr><td>${b.period_start} – ${b.period_end}</td><td>${fmt(b.units, 2)} kWh</td><td>${fmt(b.amount, 2)}</td><td>${b.change_percent == null ? "—" : `${b.change_percent >= 0 ? "+" : ""}${fmt(b.change_percent, 1)}%`}</td></tr>`).join("")}</tbody></table></div>` : "";
  document.querySelector("#appliance-analysis").innerHTML = applianceTable + billTable || empty("Add appliances or calculate bills to include them in your reports.");
}

async function loadPage(page) {
  document.querySelectorAll(".page-panel").forEach((el) => el.classList.toggle("active", el.id === `page-${page}`));
  document.querySelectorAll(".side-nav .nav-link").forEach((el) => el.classList.toggle("active", el.dataset.page === page));
  const [title, eyebrow, description] = pageNames[page];
  document.querySelector("#page-crumb").textContent = title;
  document.querySelector("#page-title").textContent = page === "overview" ? `Good energy, ${document.querySelector(".profile-copy strong").textContent.split(" ")[0]}.` : title;
  document.querySelector("#page-eyebrow").textContent = eyebrow;
  document.querySelector("#page-description").textContent = description;
  document.querySelector("#sidebar").classList.remove("open");
  try {
    if (page === "overview") await loadOverview();
    if (page === "consumption") { await loadAppliances(); await loadReadings(); }
    if (page === "appliances") await loadAppliances();
    if (page === "billing") { await loadTariffs(); await loadBills(); }
    if (page === "analytics") await loadAnalytics();
    if (page === "alerts") await loadAlerts();
    if (page === "advisor") await loadRecommendations();
    if (page === "settings") { await loadLimits(); await loadDevices(); }
  } catch (error) { showError(error.message); }
}

function formObject(form) {
  const data = Object.fromEntries(new FormData(form).entries());
  Object.keys(data).forEach((key) => { if (data[key] === "") delete data[key]; });
  if (form.elements.is_on) data.is_on = form.elements.is_on.checked;
  if (form.elements.appliance_id && data.appliance_id) data.appliance_id = Number(data.appliance_id);
  return data;
}
function numericPayload(data, keys) {
  keys.forEach((key) => { if (data[key] !== undefined) data[key] = Number(data[key]); });
  return data;
}

document.querySelectorAll(".side-nav .nav-link").forEach((button) => button.addEventListener("click", () => loadPage(button.dataset.page)));
document.querySelectorAll("[data-go]").forEach((button) => button.addEventListener("click", () => loadPage(button.dataset.go)));
document.querySelector("#menu-button").addEventListener("click", () => document.querySelector("#sidebar").classList.toggle("open"));
document.querySelector("#refresh-button").addEventListener("click", () => loadPage(document.querySelector(".side-nav .nav-link.active").dataset.page));
document.querySelector("#today-label").textContent = new Date().toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });

document.querySelector("#logout-button").addEventListener("click", async () => {
  try { await api("/auth/logout", { method: "POST", body: "{}" }); window.location.assign("/login"); }
  catch (error) { toast(error.message, true); }
});
document.querySelector("#reading-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    const data = numericPayload(formObject(form), ["energy_kwh", "power_w", "duration_hours"]);
    if (data.recorded_at) data.recorded_at = new Date(data.recorded_at).toISOString();
    await api(`/consumption${pendingSimulation ? "/simulate" : ""}`, { method: "POST", body: JSON.stringify(data) });
    form.reset(); pendingSimulation = false;
    toast("Reading saved."); await loadReadings(); await loadOverview();
  } catch (error) { toast(error.message, true); }
});
document.querySelector("#show-simulate").addEventListener("click", () => {
  if (!document.querySelector("#reading-form").reportValidity()) return;
  pendingSimulation = true;
  bootstrap.Modal.getOrCreateInstance(document.querySelector("#confirm-modal")).show();
});
document.querySelector("#confirm-simulate").addEventListener("click", () => {
  bootstrap.Modal.getInstance(document.querySelector("#confirm-modal")).hide();
  document.querySelector("#reading-form").requestSubmit();
});
document.querySelector("#filter-readings").addEventListener("click", () => loadReadings().catch((e) => toast(e.message, true)));
document.querySelector("#download-csv").addEventListener("click", () => { window.location.assign("/api/analytics/export.csv"); });
document.querySelector("#report-csv").addEventListener("click", () => { window.location.assign("/api/analytics/export.csv"); });
document.querySelector("#report-period").addEventListener("change", () => loadAnalytics().catch((e) => showError(e.message)));

document.querySelector("#appliance-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    const data = numericPayload(formObject(form), ["power_w", "daily_hours", "quantity"]);
    const id = data.id; delete data.id;
    await api(`/appliances${id ? `/${id}` : ""}`, { method: id ? "PUT" : "POST", body: JSON.stringify(data) });
    resetApplianceForm(); toast(id ? "Appliance updated." : "Appliance added."); await loadAppliances();
  } catch (error) { toast(error.message, true); }
});
function resetApplianceForm() {
  const form = document.querySelector("#appliance-form");
  form.reset(); form.elements.id.value = ""; form.elements.quantity.value = 1;
  document.querySelector("#appliance-form-title").textContent = "Add an appliance";
  document.querySelector("#cancel-appliance-edit").classList.add("d-none");
}
document.querySelector("#cancel-appliance-edit").addEventListener("click", resetApplianceForm);
document.querySelector("#appliance-list").addEventListener("click", async (event) => {
  const edit = event.target.closest("[data-edit-appliance]");
  const del = event.target.closest("[data-delete-appliance]");
  try {
    if (edit) {
      const { appliances } = await api("/appliances");
      const item = appliances.find((a) => a.id === Number(edit.dataset.editAppliance));
      const form = document.querySelector("#appliance-form");
      ["id", "name", "category", "power_w", "daily_hours", "quantity", "is_on"].forEach((key) => {
        if (key === "is_on") form.elements[key].checked = item[key];
        else form.elements[key].value = item[key];
      });
      document.querySelector("#appliance-form-title").textContent = "Edit appliance";
      document.querySelector("#cancel-appliance-edit").classList.remove("d-none");
      form.scrollIntoView({ behavior: "smooth", block: "center" });
    } else if (del && window.confirm("Delete this appliance? Existing readings will remain without an appliance link.")) {
      await api(`/appliances/${del.dataset.deleteAppliance}`, { method: "DELETE" });
      toast("Appliance deleted."); await loadAppliances();
    }
  } catch (error) { toast(error.message, true); }
});

document.querySelector("#readings-table").addEventListener("click", async (event) => {
  const del = event.target.closest("[data-delete-reading]");
  const edit = event.target.closest("[data-edit-reading]");
  try {
    if (del && window.confirm("Delete this reading?")) {
      await api(`/consumption/${del.dataset.deleteReading}`, { method: "DELETE" });
      toast("Reading deleted."); await loadReadings(); await loadOverview();
    } else if (edit) {
      const { readings } = await api("/consumption");
      const item = readings.find((r) => r.id === Number(edit.dataset.editReading));
      const entered = window.prompt(`Update energy in kWh (current ${item.energy_kwh}):`, item.energy_kwh);
      if (entered !== null) {
        const energy = Number(entered);
        if (!Number.isFinite(energy) || energy <= 0) throw new Error("Enter a positive energy value.");
        await api(`/consumption/${item.id}`, { method: "PUT", body: JSON.stringify({ energy_kwh: energy }) });
        toast("Reading updated."); await loadReadings(); await loadOverview();
      }
    }
  } catch (error) { toast(error.message, true); }
});

document.querySelector("#tariff-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const slabs = JSON.parse(event.currentTarget.elements.slabs.value);
    await api("/billing/tariffs", { method: "PUT", body: JSON.stringify({ slabs }) });
    toast("Your tariff structure was saved."); await loadTariffs();
  } catch (error) { toast(error.message || "Tariff JSON is invalid.", true); }
});
document.querySelector("#bill-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const data = numericPayload(formObject(event.currentTarget), ["units", "fixed_charges", "additional_charges", "tax_percent"]);
    const result = await api("/billing/calculate", { method: "POST", body: JSON.stringify(data) });
    const bill = result.bill;
    document.querySelector("#bill-result").innerHTML = `<div class="bill-result"><div class="bill-total"><span>Estimated total · ${bill.units} kWh</span><strong>${fmt(bill.total_amount, 2)}</strong></div><div class="bill-lines"><div class="bill-line"><span>Energy charge</span><strong>${fmt(bill.energy_charge, 2)}</strong></div>${bill.slabs.map((s, i) => `<div class="bill-line"><span>Slab ${i + 1} · ${fmt(s.units_charged, 2)} units × ${fmt(s.rate_per_unit, 2)}</span><strong>${fmt(s.charge, 2)}</strong></div>`).join("")}<div class="bill-line"><span>Fixed + additional</span><strong>${fmt(bill.fixed_charges + bill.additional_charges, 2)}</strong></div><div class="bill-line"><span>Tax (${bill.tax_percent}%)</span><strong>${fmt(bill.tax_amount, 2)}</strong></div></div><p class="form-hint mt-3 mb-0">${escapeHtml(bill.basis)}</p></div>`;
    toast("Bill estimate calculated."); await loadBills();
  } catch (error) { toast(error.message, true); }
});

document.querySelector("#limits-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const limits = ["daily", "weekly", "monthly"].filter((p) => event.currentTarget.elements[p].value).map((period) => ({ period, limit_kwh: Number(event.currentTarget.elements[period].value) }));
    await api("/limits", { method: "PUT", body: JSON.stringify({ limits }) });
    toast("Usage limits saved."); await loadLimits();
  } catch (error) { toast(error.message, true); }
});
document.querySelector("#alert-list").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-read-alert]");
  if (!button) return;
  try { await api(`/alerts/${button.dataset.readAlert}/read`, { method: "PATCH", body: "{}" }); await loadAlerts(); }
  catch (error) { toast(error.message, true); }
});
document.querySelector("#device-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const name = event.currentTarget.elements.name.value.trim();
    const result = await api("/devices", { method: "POST", body: JSON.stringify({ name }) });
    document.querySelector("#device-token-result").innerHTML = `<div class="token-box"><strong>Copy this device token now — it will not be shown again:</strong><br><code>${escapeHtml(result.device_token)}</code><br><small>${escapeHtml(result.notice)}</small></div>`;
    event.currentTarget.reset(); await loadDevices(); toast("Device credential created.");
  } catch (error) { toast(error.message, true); }
});
document.querySelector("#device-list").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-delete-device]");
  if (!button || !window.confirm("Revoke this device credential? Future readings from it will be rejected.")) return;
  try {
    await api(`/devices/${button.dataset.deleteDevice}`, { method: "DELETE" });
    document.querySelector("#device-token-result").innerHTML = "";
    toast("Device credential revoked."); await loadDevices();
  } catch (error) { toast(error.message, true); }
});

loadPage("overview");

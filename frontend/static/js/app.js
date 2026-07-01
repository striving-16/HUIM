/* ═══════════════════════════════════════════
   HUIM Dashboard — Frontend App
   Talks only to the FastAPI backend (upload / run-huim / results).
   No mining logic ever runs in the browser.
═══════════════════════════════════════════ */

'use strict';

const API_BASE = (window.HUIM_API_BASE || 'http://localhost:8000').replace(/\/$/, '');

// ── State ──
const state = {
  uploadedFilename: null,
  results: null,
  allItemsets: [],
  charts: {},
};

// ── DOM refs ──
const $ = id => document.getElementById(id);

// ═══════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
  $('api-base-display').textContent = API_BASE;
  setupDropZone();
  setupSlider();
  setupModeSelector();
  setupTableControls();
  setupNavigation();
  $('run-btn').addEventListener('click', runMining);
  $('export-btn').addEventListener('click', exportCSV);
  $('clear-log-btn').addEventListener('click', clearLog);
  loadLastResults();
});

// ═══════════════════════════════════════════
// NAVIGATION
// ═══════════════════════════════════════════
function setupNavigation() {
  document.querySelectorAll('.nav-item').forEach(link => {
    link.addEventListener('click', e => {
      e.preventDefault();
      document.querySelectorAll('.nav-item').forEach(l => l.classList.remove('active'));
      link.classList.add('active');
      const target = document.getElementById('section-' + link.dataset.section);
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
}

// ═══════════════════════════════════════════
// FILE UPLOAD / DROP ZONE  →  POST /upload
// ═══════════════════════════════════════════
function setupDropZone() {
  const zone = $('drop-zone');
  const input = $('file-input');

  zone.addEventListener('click', () => input.click());
  input.addEventListener('change', e => {
    if (e.target.files[0]) uploadFile(e.target.files[0]);
  });

  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    if (e.dataTransfer.files[0]) uploadFile(e.dataTransfer.files[0]);
  });
}

async function uploadFile(file) {
  if (!file.name.match(/\.(txt|csv)$/i)) {
    showToast('❌ Format non supporté (.txt ou .csv uniquement)', 'error');
    return;
  }

  setStatus('running', 'Upload en cours…');
  logLine(`Upload : ${file.name}`, 'step');

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch(`${API_BASE}/upload`, { method: 'POST', body: formData });
    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      const detail = data.detail || `HTTP ${res.status}`;
      showToast(`❌ ${detail}`, 'error');
      setStatus('error', 'Erreur upload');
      logLine(`Erreur upload: ${detail}`, 'error');
      return;
    }

    state.uploadedFilename = data.filename;
    showDatasetInfo(data.filename, data.size_bytes);
    $('run-btn').disabled = false;
    setStatus('ready', `Fichier: ${data.filename}`);
    showToast(`✅ Fichier "${data.filename}" chargé`, 'success');
    logLine(`Upload réussi : ${data.filename} (${data.size_bytes} octets)`, 'done');

  } catch (e) {
    showToast('❌ Erreur réseau — le backend est-il démarré ?', 'error');
    setStatus('error', 'Erreur');
    logLine(`Erreur réseau : ${e.message}`, 'error');
  }
}

function showDatasetInfo(filename, sizeBytes) {
  const statsEl = $('dataset-stats');
  statsEl.innerHTML = `
    <div class="dstat"><div class="dstat-val" style="color:var(--gold)">${filename}</div><div class="dstat-lbl">Fichier actif</div></div>
    <div class="dstat"><div class="dstat-val">${(sizeBytes / 1024).toFixed(1)} KB</div><div class="dstat-lbl">Taille</div></div>
  `;
  $('preview-card').style.display = 'block';
}

// ═══════════════════════════════════════════
// SLIDER
// ═══════════════════════════════════════════
function setupSlider() {
  const slider = $('min-util-slider');
  const input = $('min-util-input');
  const hint = $('hint-minutil');

  function update(val) {
    slider.value = val;
    input.value = val;
    hint.textContent = val + 'MRU';
  }

  slider.addEventListener('input', () => update(slider.value));
  input.addEventListener('input', () => {
    const v = Math.max(0.1, parseFloat(input.value) || 0.1);
    slider.max = Math.max(slider.max, v);
    update(v);
  });
}

// ═══════════════════════════════════════════
// MODE SELECTOR
// ═══════════════════════════════════════════
function setupModeSelector() {
  document.querySelectorAll('.mode-option').forEach(opt => {
    opt.addEventListener('click', () => {
      document.querySelectorAll('.mode-option').forEach(o => o.classList.remove('selected'));
      opt.classList.add('selected');
    });
  });
}

function getSelectedMode() {
  const checked = document.querySelector('input[name="mode"]:checked');
  return checked ? checked.value : 'local';
}

// ═══════════════════════════════════════════
// MINING  →  POST /run-huim
// ═══════════════════════════════════════════
async function runMining() {
  if (!state.uploadedFilename) { showToast("⚠️ Chargez un dataset d'abord", 'info'); return; }

  const minUtil = parseFloat($('min-util-input').value);
  const mode = getSelectedMode();

  // UI: switch to loading state
  $('run-btn').disabled = true;
  $('run-btn').classList.add('loading');
  $('run-btn').innerHTML = '<span class="spinner" style="width:16px;height:16px;border-width:2px"></span> Mining…';
  $('results-empty').style.display = 'none';
  $('results-content').style.display = 'none';
  $('mining-loading').style.display = 'flex';
  $('export-btn').style.display = 'none';

  setStatus('running', 'Mining en cours…');
  logLine(`─── Mining démarré ───`, 'step');
  logLine(`Mode: ${mode.toUpperCase()} | MinUtil: ${minUtil}MRU | Fichier: ${state.uploadedFilename}`, 'info');

  try {
    const res = await fetch(`${API_BASE}/run-huim`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: state.uploadedFilename, min_util: minUtil, mode }),
    });
    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      const detail = data.detail || `HTTP ${res.status}`;
      showToast(`❌ ${detail}`, 'error');
      setStatus('error', 'Erreur mining');
      logLine(`ERREUR: ${detail}`, 'error');
      resetRunBtn();
      $('mining-loading').style.display = 'none';
      $('results-empty').style.display = 'flex';
      return;
    }

    logLine(`─── Terminé en ${data.elapsed_seconds}s — ${data.huis_found} HUI trouvés ───`, 'done');

    applyResults(data);

    setStatus('done', `${data.huis_found} HUI trouvés en ${data.elapsed_seconds}s`);
    showToast(`✅ ${data.huis_found} itemsets trouvés en ${data.elapsed_seconds}s`, 'success');

    setTimeout(() => $('section-results').scrollIntoView({ behavior: 'smooth' }), 200);

  } catch (e) {
    showToast('❌ Erreur réseau', 'error');
    setStatus('error', 'Erreur');
    logLine(`Erreur réseau : ${e.message}`, 'error');
    $('mining-loading').style.display = 'none';
    $('results-empty').style.display = 'flex';
  }

  resetRunBtn();
}

function resetRunBtn() {
  const btn = $('run-btn');
  btn.disabled = false;
  btn.classList.remove('loading');
  btn.innerHTML = '<span class="btn-icon">▶</span> Lancer le Mining';
}

// ═══════════════════════════════════════════
// RESTORE LAST RESULT  →  GET /results
// ═══════════════════════════════════════════
async function loadLastResults() {
  try {
    const res = await fetch(`${API_BASE}/results`);
    if (!res.ok) return; // nothing computed yet on this backend instance
    const data = await res.json();
    applyResults(data);
    logLine('Derniers résultats restaurés depuis le backend (GET /results).', 'info');
  } catch {
    // backend unreachable at load time — silently ignore, upload/run will surface the error
  }
}

function applyResults(data) {
  state.results = data;
  state.allItemsets = data.itemsets;

  $('mining-loading').style.display = 'none';
  $('results-content').style.display = 'block';
  if (data.itemsets.length > 0) $('export-btn').style.display = 'inline-flex';

  renderKPIs(data);
  renderCharts(data);
  renderTable(data.itemsets);
}

// ═══════════════════════════════════════════
// KPIs
// ═══════════════════════════════════════════
function renderKPIs(data) {
  const s = data.stats;
  $('kpi-total').textContent = s.count || 0;
  $('kpi-max').textContent = s.max_utility ? s.max_utility.toFixed(2) + 'MRU' : '—';
  $('kpi-avg').textContent = s.avg_utility ? s.avg_utility.toFixed(2) + 'MRU' : '—';
  $('kpi-time').textContent = (data.elapsed_seconds ?? '—') + 's';
}

// ═══════════════════════════════════════════
// CHARTS
// ═══════════════════════════════════════════
function renderCharts(data) {
  renderBarChart(data.itemsets.slice(0, 10));
  renderDoughnutChart(data.stats);
}

function renderBarChart(itemsets) {
  if (state.charts.bar) state.charts.bar.destroy();
  const ctx = $('chart-bar').getContext('2d');
  const labels = itemsets.map(i => i.itemset_name.replace(/{|}/g, ''));
  const values = itemsets.map(i => i.utility);

  state.charts.bar = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Utilité (MRU)',
        data: values,
        backgroundColor: values.map((_, i) => `hsl(${168 - i * 8}, 80%, ${50 - i * 2}%)`),
        borderRadius: 6,
        borderSkipped: false,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.parsed.y.toFixed(2)}MRU`
          }
        }
      },
      scales: {
        x: {
          ticks: { color: '#8b949e', font: { family: 'JetBrains Mono', size: 10 }, maxRotation: 30 },
          grid: { color: '#21262d' },
        },
        y: {
          ticks: { color: '#8b949e', font: { family: 'JetBrains Mono', size: 11 }, callback: v => v + 'MRU' },
          grid: { color: '#21262d' },
        }
      }
    }
  });
}

function renderDoughnutChart(stats) {
  if (state.charts.doughnut) state.charts.doughnut.destroy();
  const ctx = $('chart-doughnut').getContext('2d');

  const singles = stats.single_items || 0;
  const pairs   = stats.pairs || 0;
  const larger  = stats.larger || 0;

  state.charts.doughnut = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['Items seuls', 'Paires', 'Taille 3+'],
      datasets: [{
        data: [singles, pairs, larger],
        backgroundColor: ['#00d4aa', '#7c3aed', '#f0a500'],
        borderWidth: 0,
        hoverOffset: 6,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '65%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            color: '#8b949e',
            font: { family: 'Space Grotesk', size: 12 },
            padding: 16,
            usePointStyle: true,
          }
        },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.label}: ${ctx.parsed} itemset(s)`
          }
        }
      }
    }
  });
}

// ═══════════════════════════════════════════
// RESULTS TABLE
// ═══════════════════════════════════════════
function setupTableControls() {
  $('table-search').addEventListener('input', () => renderTable(state.allItemsets));
  $('table-sort').addEventListener('change', () => renderTable(state.allItemsets));
}

function renderTable(itemsets) {
  const query = $('table-search').value.toLowerCase();
  const sort = $('table-sort').value;

  let filtered = itemsets.filter(i => i.itemset_name.toLowerCase().includes(query));

  const [field, dir] = sort.split('-');
  filtered.sort((a, b) => {
    const av = field === 'utility' ? a.utility : a.size;
    const bv = field === 'utility' ? b.utility : b.size;
    return dir === 'desc' ? bv - av : av - bv;
  });

  const maxUtil = Math.max(...filtered.map(i => i.utility), 1);
  $('results-count').textContent = filtered.length;
  $('results-tbody').innerHTML = filtered.map((item, idx) => {
    const chipClass = item.size === 1 ? 'single' : item.size === 2 ? 'pair' : 'large';
    const chips = item.itemset.map(n => `<span class="chip ${chipClass}">${n}</span>`).join('');
    const barWidth = Math.round((item.utility / maxUtil) * 100);
    return `
      <tr>
        <td><span class="rank-num">${idx + 1}</span></td>
        <td><div class="itemset-cell">${chips}</div></td>
        <td><span class="utility-val">${item.utility.toFixed(2)}MRU</span></td>
        <td><span class="size-badge">${item.size}</span></td>
        <td><span style="color:var(--text-muted);font-family:var(--font-mono)">${item.transactions}</span></td>
        <td>
          <div class="util-bar-wrap">
            <div class="util-bar" style="width:${barWidth}%"></div>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

// ═══════════════════════════════════════════
// EXPORT (client-side CSV — no backend call, just formatting already-fetched data)
// ═══════════════════════════════════════════
function exportCSV() {
  if (!state.results) return;
  const rows = [['Rang', 'Itemset', 'Utilite (MRU)', 'Taille', 'Transactions']];
  state.results.itemsets.forEach((item, i) => {
    rows.push([i + 1, item.itemset_name, item.utility, item.size, item.transactions]);
  });
  const csv = rows.map(r => r.join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'huim_results.csv'; a.click();
  URL.revokeObjectURL(url);
  showToast('✅ Résultats exportés', 'success');
}

// ═══════════════════════════════════════════
// LOG
// ═══════════════════════════════════════════
function logLine(text, type = 'info') {
  const terminal = $('log-terminal');
  const div = document.createElement('div');
  div.className = `log-line log-${type}`;
  div.textContent = text;
  terminal.appendChild(div);
  terminal.scrollTop = terminal.scrollHeight;
}

function clearLog() {
  $('log-terminal').innerHTML = '<div class="log-line log-info">Log effacé.</div>';
}

// ═══════════════════════════════════════════
// STATUS
// ═══════════════════════════════════════════
function setStatus(type, text) {
  const dot = $('status-dot');
  dot.className = 'status-dot ' + type;
  $('status-text').textContent = text;
}

// ═══════════════════════════════════════════
// TOAST
// ═══════════════════════════════════════════
function showToast(msg, type = 'info') {
  const t = $('toast');
  t.textContent = msg;
  t.className = `toast ${type} show`;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), 3000);
}

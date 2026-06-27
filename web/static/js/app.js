/* ═══════════════════════════════════════════
   HUIM Dashboard — Frontend App
═══════════════════════════════════════════ */

'use strict';

// ── State ──
const state = {
  selectedFile: null,
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
  loadSampleDatasets();
  setupDropZone();
  setupSlider();
  setupModeSelector();
  setupTableControls();
  setupNavigation();
  $('run-btn').addEventListener('click', runMining);
  $('export-btn').addEventListener('click', exportCSV);
  $('clear-log-btn').addEventListener('click', clearLog);
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
// SAMPLE DATASETS
// ═══════════════════════════════════════════
async function loadSampleDatasets() {
  try {
    const res = await fetch('/api/sample-datasets');
    const datasets = await res.json();
    const list = $('sample-list');
    list.innerHTML = '';

    if (datasets.length === 0) {
      list.innerHTML = '<p style="color:var(--text-muted);font-size:13px">Aucun dataset trouvé.</p>';
      return;
    }

    datasets.forEach(ds => {
      const item = document.createElement('div');
      item.className = 'sample-item';
      item.innerHTML = `
        <div>
          <div class="sample-name">📄 ${ds.name}</div>
          <div style="font-size:11px;color:var(--text-muted);margin-top:3px">${ds.description}</div>
        </div>
        <div class="sample-meta">
          <div>${ds.transactions} tickets</div>
          <div>${ds.unique_items} produits</div>
        </div>
      `;
      item.addEventListener('click', () => {
        document.querySelectorAll('.sample-item').forEach(i => i.classList.remove('selected'));
        item.classList.add('selected');
        selectDataset(ds);
      });
      list.appendChild(item);
    });
  } catch (e) {
    $('sample-list').innerHTML = '<p style="color:var(--red);font-size:13px">Erreur de chargement.</p>';
  }
}

function selectDataset(ds) {
  state.selectedFile = { path: ds.path, name: ds.name };
  showDatasetInfo(ds.transactions, ds.unique_items, ds.name);
  $('run-btn').disabled = false;
  setStatus('ready', `Dataset: ${ds.name}`);
  showToast(`✅ Dataset "${ds.name}" sélectionné`, 'success');
  logLine(`Dataset chargé : ${ds.name} (${ds.transactions} transactions, ${ds.unique_items} produits)`, 'done');
}

// ═══════════════════════════════════════════
// FILE UPLOAD / DROP ZONE
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
    const res = await fetch('/api/upload', { method: 'POST', body: formData });
    let data;
    try {
      data = await res.json();
    } catch {
      const text = await res.text().catch(() => `HTTP ${res.status}`);
      showToast(`❌ Erreur serveur: ${res.status}`, 'error');
      setStatus('error', 'Erreur serveur');
      logLine(`Erreur serveur (${res.status}): ${text.slice(0, 200)}`, 'error');
      return;
    }

    if (data.error) {
      showToast(`❌ ${data.error}`, 'error');
      setStatus('error', 'Erreur upload');
      return;
    }

    state.selectedFile = { path: data.path, name: data.filename };
    showDatasetInfo(data.transactions, data.unique_items, data.filename, data.preview);
    $('run-btn').disabled = false;
    setStatus('ready', `Fichier: ${data.filename}`);
    showToast(`✅ Fichier "${data.filename}" chargé`, 'success');
    logLine(`Upload réussi : ${data.filename} — ${data.transactions} transactions, ${data.unique_items} produits`, 'done');

  } catch (e) {
    showToast('❌ Erreur réseau', 'error');
    setStatus('error', 'Erreur');
  }
}

// ═══════════════════════════════════════════
// DATASET PREVIEW
// ═══════════════════════════════════════════
function showDatasetInfo(transactions, items, name, preview) {
  const statsEl = $('dataset-stats');
  statsEl.innerHTML = `
    <div class="dstat"><div class="dstat-val">${transactions}</div><div class="dstat-lbl">Transactions</div></div>
    <div class="dstat"><div class="dstat-val">${items}</div><div class="dstat-lbl">Produits uniques</div></div>
    <div class="dstat"><div class="dstat-val" style="color:var(--gold)">${name}</div><div class="dstat-lbl">Fichier actif</div></div>
  `;

  if (preview) {
    const tbody = $('preview-table').querySelector('tbody');
    tbody.innerHTML = '';
    preview.forEach(t => {
      const itemsHtml = t.items.map(i =>
        `<span class="item-tag">${i.name} <span class="profit">+${i.profit} MRU</span></span>`
      ).join('');
      tbody.innerHTML += `
        <tr>
          <td><span class="rank-num">#${t.id}</span></td>
          <td>${itemsHtml}</td>
          <td><span class="utility-val">${t.total}MRU</span></td>
        </tr>
      `;
    });
    tbody.innerHTML += `<tr><td colspan="3" style="color:var(--text-dim);font-size:12px;padding:12px">… et ${transactions - preview.length} autres transactions</td></tr>`;
  }

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
// MINING
// ═══════════════════════════════════════════
async function runMining() {
  if (!state.selectedFile) { showToast('⚠️ Sélectionnez un dataset d\'abord', 'info'); return; }

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
  $('log-live').innerHTML = '';

  setStatus('running', 'Mining en cours…');
  logLine(`─── Mining démarré ───`, 'step');
  logLine(`Mode: ${mode.toUpperCase()} | MinUtil: ${minUtil}MRU | Fichier: ${state.selectedFile.name}`, 'info');

  try {
    const res = await fetch('/api/mine', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filepath: state.selectedFile.path, min_util: minUtil, mode }),
    });
    const data = await res.json();

    if (data.error) {
      showToast(`❌ ${data.error}`, 'error');
      setStatus('error', 'Erreur mining');
      logLine(`ERREUR: ${data.error}`, 'error');
      resetRunBtn();
      $('mining-loading').style.display = 'none';
      $('results-empty').style.display = 'flex';
      return;
    }

    // Show log lines
    (data.log || []).forEach(line => {
      const cls = line.includes('✨') ? 'hui' : line.includes('Étape') ? 'step' : line.includes('✅') ? 'done' : line.includes('⚠️') ? 'warn' : 'info';
      logLine(line, cls);
      addLiveLine(line, cls);
    });

    logLine(`─── Terminé en ${data.elapsed}s — ${data.itemsets.length} HUI trouvés ───`, 'done');

    state.results = data;
    state.allItemsets = data.itemsets;

    // Show results
    await new Promise(r => setTimeout(r, 400)); // brief delay for UX
    $('mining-loading').style.display = 'none';
    $('results-content').style.display = 'block';
    if (data.itemsets.length > 0) $('export-btn').style.display = 'inline-flex';

    renderKPIs(data);
    renderCharts(data);
    renderTable(data.itemsets);

    setStatus('done', `${data.itemsets.length} HUI trouvés en ${data.elapsed}s`);
    showToast(`✅ ${data.itemsets.length} itemsets trouvés en ${data.elapsed}s`, 'success');

    // Scroll to results
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
// KPIs
// ═══════════════════════════════════════════
function renderKPIs(data) {
  const s = data.stats;
  $('kpi-total').textContent = s.count || 0;
  $('kpi-max').textContent = s.max_utility ? s.max_utility.toFixed(2) + 'MRU' : '—';
  $('kpi-avg').textContent = s.avg_utility ? s.avg_utility.toFixed(2) + 'MRU' : '—';
  $('kpi-time').textContent = data.elapsed + 's';
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
  const labels = itemsets.map(i => i.name.replace(/{|}/g, ''));
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

  let filtered = itemsets.filter(i => i.name.toLowerCase().includes(query));

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
    const chips = item.items.map(n => `<span class="chip ${chipClass}">${n}</span>`).join('');
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
// EXPORT
// ═══════════════════════════════════════════
async function exportCSV() {
  if (!state.results) return;
  try {
    const res = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ itemsets: state.results.itemsets }),
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'huim_results.csv'; a.click();
    URL.revokeObjectURL(url);
    showToast('✅ Résultats exportés', 'success');
  } catch (e) {
    showToast('❌ Erreur export', 'error');
  }
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

function addLiveLine(text, type = 'info') {
  const live = $('log-live');
  const div = document.createElement('div');
  div.style.color = type === 'hui' ? 'var(--teal)' : type === 'done' ? '#7ee787' : 'var(--text-muted)';
  div.textContent = text;
  live.appendChild(div);
  live.scrollTop = live.scrollHeight;
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

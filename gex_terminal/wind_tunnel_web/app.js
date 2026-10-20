'use strict';
(() => {
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const colors = {cyan: '#37cee9', amber: '#ffbd35', text: '#bfd0e5', grid: '#20303f', muted: '#778ea8'};
  const terminalSession = 'terminal-checkpoint';
  const modelNames = {terminal_selected: 'Terminal selected proxy', raw_trade_volume: 'Volume proxy', open_interest: 'Open interest', directionalized_trade_volume: 'Directionalized volume'};
  const capabilityStorageKey = `gex.wind-tunnel.capability:${location.origin}`;
  const launchCapability = new URLSearchParams(location.hash.slice(1)).get('cap');
  let tabCapability = launchCapability;
  try {if (launchCapability) sessionStorage.setItem(capabilityStorageKey, launchCapability); else tabCapability = sessionStorage.getItem(capabilityStorageKey);} catch (_) { /* A blocked store still permits the current launch link. */ }
  const state = {capability: tabCapability, sources: [], checkpoints: [], source: null, checkpoint: null, terminalCheckpoint: null, bundledDefaults: null, view: 'landscape', calculation: null, surface: null, search: null, revision: 0, controller: null, surfaceController: null, surfaceBusy: false, largeCheckpoint: false, landscapeRequested: false, searchController: null, sourceRevision: 0, playback: null, saving: false, valid: true, busy: false, searchBusy: false, webgl: null, surfaceRequest: null, loadedSearchGrid: null, models: null, modelsRequest: null, modelsController: null, modelsBusy: false, strikeRange: 'focused'};
  const intake = {revision: 0, controller: null, verified: null, busy: false};
  const maxSessionBytes = 4 * 1024 * 1024;
  const maxReceiptBytes = 32 * 1024 * 1024;
  if (launchCapability) history.replaceState(null, '', location.pathname + location.search);
  const emptyScenario = {spot_shift: 0, iv_shift: 0, time_advance: 0, model: 'raw_trade_volume', exclude_nearest_expiry: false, fallback_dte: .25, risk_free_rate: .045};
  let retainedAssumptions = {fallback_dte: .25, risk_free_rate: .045, minimum_directional_coverage: .5};
  let calculateTimer, toastTimer;
  const formatNumber = (value, digits = 2) => Number.isFinite(Number(value)) && value !== null ? Number(value).toLocaleString(undefined, {maximumFractionDigits: digits}) : '—';
  const money = (value) => {if (!Number.isFinite(value)) return '—'; const absolute = Math.abs(value); const scale = absolute >= 1e9 ? [1e9, 'B'] : absolute >= 1e6 ? [1e6, 'M'] : absolute >= 1e3 ? [1e3, 'K'] : [1, '']; return `${value > 0 ? '+' : value < 0 ? '−' : ''}${(absolute / scale[0]).toFixed(2)}${scale[1]}`;};
  const signed = (value, digits = 6) => `${Number(value) > 0 ? '+' : ''}${formatNumber(Number(value), digits)}`;
  const timeLabel = (value) => {if (!value) return 'No event time'; const date = new Date(value); return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit', timeZone: 'UTC'}) + ' UTC';};
  function text(selector, value) {$(selector).textContent = value;}
  function status(message, isError = false) {text('#calculation-status', message); $('#calculation-status').classList.toggle('error', isError);}
  function toast(message) {clearTimeout(toastTimer); text('#toast', message); $('#toast').hidden = false; toastTimer = setTimeout(() => {$('#toast').hidden = true;}, 5500);}
  async function api(path, options = {}) {
    if (!state.capability) throw new Error('This local session needs its launch link. Start Wind Tunnel again to open a fresh authenticated window.');
    const headers = {'X-GEX-Capability': state.capability};
    if (options.body !== undefined || options.rawBody !== undefined) headers['Content-Type'] = options.contentType || 'application/json';
    const response = await fetch(`/api/${path}`, {...options, headers, body: options.rawBody !== undefined ? options.rawBody : options.body === undefined ? undefined : JSON.stringify(options.body)});
    if (response.status === 403) {state.capability = null; try {sessionStorage.removeItem(capabilityStorageKey);} catch (_) {} const message = 'This local session has expired or its launch key has changed. Open a fresh Wind Tunnel launch link to continue.'; text('#connection-error', message); $('#connection-error').hidden = false; throw new Error(message);}
    if (!response.ok) {let message = `Local service returned ${response.status}.`; try {const result = await response.json(); message = result.error?.message || message;} catch (_) {} throw new Error(message);}
    return options.blob ? response.blob() : options.text ? response.text() : response.json();
  }
  const post = (path, body, signal) => api(path, {method: 'POST', body, signal});
  function node(tag, content, className) {const element = document.createElement(tag); if (content !== undefined) element.textContent = content; if (className) element.className = className; return element;}
  function toggleBusy() {const pending = state.busy || state.surfaceBusy || state.searchBusy || state.modelsBusy; $('#run-search').disabled = !state.source || !state.valid || pending; $('#run-model-grid').disabled = !state.source || !state.valid || pending; $('#save-scenario').disabled = !(state.view === 'models' ? state.models : state.calculation) || !state.valid || pending; $('#confirm-save').disabled = state.saving; text('#run-search-label', state.searchBusy ? 'Searching tested cases…' : 'Find breaking point'); text('#run-model-grid', state.modelsBusy ? 'Calculating both models…' : 'Run 54-case grid');}
  function requestFromControls() {
    const request = {session: isTerminalSource() ? terminalSession : state.source, checkpoint: state.checkpoint, ...retainedAssumptions, model: $('#position-model').value, spot_shift: Number($('#spot-number').value), iv_shift: Number($('#iv-number').value), time_advance: Number($('#time-number').value), exclude_nearest_expiry: $('#remove-expiry').checked};
    if (isTerminalSource() && state.terminalCheckpoint) request.terminal_checkpoint = state.terminalCheckpoint;
    const valid = ['#spot-number', '#iv-number', '#time-number'].every(selector => $(selector).value !== '' && $(selector).checkValidity());
    state.valid = valid;
    $('#scenario-validation').hidden = valid;
    text('#scenario-validation', valid ? '' : 'Enter values inside the displayed ranges before recalculating.');
    return valid ? request : null;
  }
  function populateScenario(request) {
    state.terminalCheckpoint = request.session === terminalSession || isTerminalSource() ? request.terminal_checkpoint || state.terminalCheckpoint : null;
    retainedAssumptions = {fallback_dte: request.fallback_dte ?? .25, risk_free_rate: request.risk_free_rate ?? .045, minimum_directional_coverage: request.minimum_directional_coverage ?? .5};
    for (const [key, range, number] of [['spot_shift', '#spot-shift', '#spot-number'], ['iv_shift', '#iv-shift', '#iv-number'], ['time_advance', '#time-advance', '#time-number']]) {$(range).value = request[key] ?? 0; $(number).value = request[key] ?? 0;}
    $('#position-model').value = request.model || 'raw_trade_volume'; $('#remove-expiry').checked = Boolean(request.exclude_nearest_expiry);
  }
  function clearSearch() {if (state.searchController) state.searchController.abort(); state.searchController = null; state.searchBusy = false; state.search = null; $('#search-table tbody').replaceChildren(); text('#tested-claim', 'Choose a claim and run a bounded search.'); text('#map-caption', 'A finite grid is a sensitivity test, not a probability or a continuous boundary.'); $('#apply-breaking-case').hidden = true; const box = $('#search-result'); box.replaceChildren(node('p', 'BOUNDED SEARCH', 'eyebrow'), node('h3', 'No current search.'), node('p', 'Run a search for this checkpoint and set of assumptions.')); if (state.view === 'fragility') emptyPlot('#fragility-plot', 'Test a claim across price and IV shifts.', 'Choose the claim and bounds, then find a breaking point.');}
  function clearLandscape() {state.surfaceController?.abort(); state.surfaceController = null; state.surfaceBusy = false; state.surface = null; state.surfaceRequest = null;}
  function scheduleCalculation() {stopPlayback(); clearSearch(); clearModels(); state.revision++; clearTimeout(calculateTimer); state.controller?.abort(); state.calculation = null; clearLandscape(); $('.metric-strip').hidden = true; renderPricingAssumptions(null); state.busy = false; const request = requestFromControls(); toggleBusy(); if (!request) {status('Invalid scenario inputs', true); text('#scenario-state', 'Inputs need attention'); return;} status('Assumptions changed · recalculating…'); text('#scenario-state', 'Recalculating…'); calculateTimer = setTimeout(() => state.view === 'models' ? calculateModels() : calculate(), 180);}
  function emptyPlot(selector, title, description = '') {const target = $(selector); if (window.Plotly && target.data) Plotly.purge(target); target.classList.add('plot-empty'); target.replaceChildren(node('strong', title), node('p', description));}
  function chartLayout(extra = {}) {return {paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: {family: 'SFMono-Regular, Consolas, monospace', color: colors.text, size: 11}, margin: {l: 55, r: 18, t: 16, b: 55}, showlegend: false, hoverlabel: {bgcolor: '#142333', font: {color: '#f0f4fb', size: 12}}, xaxis: {gridcolor: colors.grid, zerolinecolor: '#4c6278', linecolor: '#40546b', title: {text: 'Strike'}, tickformat: ',.0f'}, yaxis: {gridcolor: colors.grid, zerolinecolor: '#8297ad', title: {text: 'Net GEX (billions)'}}, ...extra};}
  async function draw(selector, traces, layout) {const target = $(selector); if (target.classList.contains('plot-empty')) target.replaceChildren(); target.classList.remove('plot-empty'); if (!window.Plotly) {emptyPlot(selector, 'Chart library unavailable.', 'The local Plotly asset could not be loaded. Values remain available in Compare and source details.'); return;} await Plotly.react(target, traces, layout, {responsive: true, displaylogo: false, displayModeBar: false, scrollZoom: false});}
  function summaryOf(value) {return value?.summary || {};}
  function coverageOf(value) {
    const explicit = value?.pricing_coverage || value?.pricing_assumptions?.pricing_coverage;
    if (explicit) return explicit;
    // Older bundled calculations have no qualified-IV metadata. Their detailed
    // contributing records prove completeness only when every selected row is present.
    const rows = value?.contracts;
    if (value?.status !== 'available' || !Array.isArray(rows) || !rows.length || value.counts?.selected_rows !== rows.length || !rows.every(row => Number.isFinite(row?.quantity) && row.quantity >= 0)) return undefined;
    const quantity = rows.reduce((sum, row) => sum + row.quantity, 0);
    if (!Number.isFinite(quantity) || rows.some(row => row.provider === 'legacy' || row.iv_source === 'legacy_unspecified') || (value.excluded_contracts || []).some(row => row.reason === 'iv_unavailable')) return undefined;
    const retained = rows.filter(row => row.iv_source === 'prior_valid');
    return {status: 'complete', selected_contract_count: rows.length, priced_contract_count: rows.length,
      selected_quantity: quantity, priced_quantity: quantity, unpriced_contract_count: 0, unpriced_quantity: 0,
      retained_iv_contract_count: retained.length, retained_iv_quantity: retained.reduce((sum, row) => sum + row.quantity, 0)};
  }
  const unpricedOf = value => (value?.excluded_contracts || []).filter(row => row.reason === 'iv_unavailable');
  function coverageStatus(coverage) {
    const values = ['selected_contract_count', 'priced_contract_count', 'selected_quantity', 'priced_quantity'].map(key => coverage?.[key]);
    if (!values.every(value => Number.isFinite(value) && value >= 0)) return 'Coverage unavailable';
    const [selected, priced, quantity, pricedQuantity] = values;
    if (priced > selected || pricedQuantity > quantity) return 'Coverage unavailable';
    if (!selected) return 'No selected contracts';
    if (!priced) return 'Unavailable — no selected contracts are priced';
    return priced < selected || pricedQuantity < quantity ? 'Partial' : 'Complete';
  }
  function coveragePercent(priced, selected) {
    if (!selected) return 'not applicable';
    const percent = priced / selected * 100;
    // A small omission must never appear as complete after rounding.
    return percent < 100 && Number(percent.toFixed(2)) === 100 ? '<100%' : `${formatNumber(percent)}%`;
  }
  function coverageSummary(coverage) {
    if (coverageStatus(coverage) === 'Coverage unavailable') return 'Contract and quantity coverage metadata are unavailable.';
    return `${formatNumber(coverage.priced_contract_count, 0)} / ${formatNumber(coverage.selected_contract_count, 0)} contracts priced (${coveragePercent(coverage.priced_contract_count, coverage.selected_contract_count)}) · ${formatNumber(coverage.priced_quantity, 0)} / ${formatNumber(coverage.selected_quantity, 0)} selected quantity priced (${coveragePercent(coverage.priced_quantity, coverage.selected_quantity)}).`;
  }
  function coverageStates(report) {
    if (!report) return [];
    const states = [['Original', report.baseline], ['Scenario', report.scenario]].filter(([, value]) => value);
    if (states.length === 2 && JSON.stringify([coverageOf(states[0][1]), unpricedOf(states[0][1]), states[0][1].iv_freshness]) === JSON.stringify([coverageOf(states[1][1]), unpricedOf(states[1][1]), states[1][1].iv_freshness])) return [['Original & scenario', states[0][1]]];
    return states;
  }
  function unpricedExplanation(row) {
    const p = row.iv_provenance || {}, price = p.option_price;
    if (p.status === 'outside_no_arbitrage_bounds') {
      if (Number.isFinite(price) && Number.isFinite(p.lower_bound) && price < p.lower_bound) return `Captured premium ${formatNumber(price)} points is below the captured model minimum of ${formatNumber(p.lower_bound)} points; no valid IV fits those inputs.`;
      if (Number.isFinite(price) && Number.isFinite(p.upper_bound) && price > p.upper_bound) return `Captured premium ${formatNumber(price)} points is above the captured model maximum of ${formatNumber(p.upper_bound)} points; no valid IV fits those inputs.`;
      return 'The captured option premium is outside the model price bounds; no valid IV fits those inputs.';
    }
    if (p.status === 'stale_underlying_price') return `The captured futures quote is too old for the IV calculation${Number.isFinite(p.underlying_price_age_ms) ? ` (${formatNumber(p.underlying_price_age_ms)} ms old)` : ''}. No substitute IV is applied.`;
    return 'IV is unavailable for this contract. No substitute IV is applied.';
  }
  function unpricedIdentity(row) {
    // Read checkpoint metadata only for a label; retain the canonical artifact bytes.
    const metadata = checkpointMetadata(state.terminalCheckpoint);
    const original = metadata.rows?.find(item => item.contract_id === row.contract_id && item.expiry === row.expiry);
    const name = original && Number.isFinite(original.strike) && ['C', 'P'].includes(original.option_type)
      ? `${original.symbol ? original.symbol + ' ' : ''}${formatNumber(original.strike)} ${original.option_type === 'P' ? 'put' : 'call'} · ` : '';
    return `${name}Contract ${row.contract_id ?? 'unidentified'} · expiry ${row.expiry || 'unavailable'}`;
  }
  function durationLabel(seconds) {if (!Number.isFinite(seconds) || seconds < 0) return 'unknown'; if (seconds < 60) return `${formatNumber(seconds, 1)}s`; if (seconds < 3600) return `${formatNumber(seconds / 60, 1)}m`; return `${formatNumber(seconds / 3600, 2)}h`;}
  function freshnessSummary(value) {
    const f = value?.iv_freshness;
    if (!f) return 'Accepted-IV age: unknown. Freshness metadata unavailable; usable pricing coverage does not establish freshness.';
    const count = prefix => Number.isFinite(f[`${prefix}_contract_count`]) ? formatNumber(f[`${prefix}_contract_count`], 0) : 'unknown';
    return `Accepted-IV age: ${count('recent')} within 5m · ${count('older')} older than 5m · ${count('unknown')} unknown · ${count('not_applicable')} not applicable. Oldest ${durationLabel(f.max_age_seconds)}${f.retained_iv_contract_count ? ` · retained prior-valid ${count('retained_iv')} (oldest ${durationLabel(f.max_retained_age_seconds)})` : ''}.`;
  }
  function appendFreshness(body, value, label = '') {
    const f = value?.iv_freshness, box = node('div', undefined, 'iv-freshness');
    box.append(node('p', `${label ? label + ' · ' : ''}${freshnessSummary(value)}`, !f || f.older_contract_count || f.unknown_contract_count ? 'coverage-warning' : undefined));
    if (f) box.append(node('p', `Age distribution covers ${formatNumber(f.priced_contract_count, 0)} priced contract(s); unpriced contracts remain excluded from this age distribution. Older-IV selected quantity ${formatNumber(f.older_quantity, 0)} · unknown-age quantity ${formatNumber(f.unknown_quantity, 0)} · age not applicable quantity ${formatNumber(f.not_applicable_quantity, 0)}.`, 'muted'));
    if (f?.capture_precision_ambiguity_contract_count > 0) box.append(node('p', `${formatNumber(f.capture_precision_ambiguity_contract_count, 0)} contract(s), ${formatNumber(f.capture_precision_ambiguity_quantity, 0)} selected quantity have unknown IV age because the captured cutoff was truncated to microseconds. The cutoff precision cannot resolve the accepted observation's age; this does not establish a future observation or zero age.`, 'coverage-warning'));
    if (f) box.append(node('p', `Captured cutoff ${fullTimeLabel(f.capture_as_of)} · ${f.time_basis === 'scenario_model_time' ? 'Scenario model time' : 'Age reference'} ${fullTimeLabel(f.as_of)}.`, 'muted'));
    box.append(node('p', '5m is an age reference, not an IV pricing expiry. Accepted IV can be older. Retained prior-valid IV uses its original accepted observation time; advancing model time adds no observations.', 'muted'));
    body.append(box);
  }
  function renderPricingCoverage(report) {
    const box = $('#pricing-coverage-content'); box.replaceChildren();
    const states = coverageStates(report); box.classList.toggle('split-coverage', states.length > 1);
    if (!states.length) {box.append(node('p', report ? 'Pricing coverage unavailable. No calculation coverage metadata.' : 'Pricing coverage pending. Select a source and allow calculation to complete.')); return;}
    for (const [label, value] of states) {
      const coverage = coverageOf(value), card = node('div', undefined, 'coverage-state');
      const status = coverageStatus(coverage); card.append(node('h3', `${label} · ${status}`, status === 'Partial' || status.startsWith('Unavailable') ? 'coverage-warning' : undefined), node('p', coverageSummary(coverage)));
      card.append(node('p', freshnessSummary(value), 'coverage-freshness'));
      box.append(card);
    }
    const details = node('details', undefined, 'coverage-evidence'), body = node('div');
    details.append(node('summary', 'Pricing, IV age & unpriced details'));
    appendPricingCoverageDetails(body, report); details.append(body); box.append(details);
  }
  function appendPricingCoverageDetails(body, report) {
    body.append(node('h3', 'Pricing coverage'));
    for (const [label, value] of coverageStates(report)) {
      const coverage = coverageOf(value);
      body.append(node('h3', `${label} · ${coverageStatus(coverage)}`), node('p', coverageSummary(coverage))); appendFreshness(body, value);
      if (coverage?.retained_iv_contract_count) body.append(node('p', `${formatNumber(coverage.retained_iv_contract_count, 0)} contract(s) use an earlier valid IV observation.`));
      const excluded = unpricedOf(value);
      if (coverage?.unpriced_contract_count) body.append(node('p', `${formatNumber(coverage.unpriced_contract_count, 0)} contract(s), ${formatNumber(coverage.unpriced_quantity, 0)} selected quantity remain unpriced and excluded from modeled GEX. Raw quantities are retained. These diagnostics describe the original captured IV inversion inputs, not shifted scenario inputs. They do not establish why the sampled inputs disagree.`));
      if (coverage?.unpriced_contract_count && !excluded.length) body.append(node('p', 'Per-contract IV diagnostics are unavailable in this calculation.'));
      for (const row of excluded) {
        body.append(node('h3', unpricedIdentity(row)), node('p', unpricedExplanation(row)));
        const p = row.iv_provenance || {}, details = node('dl');
        for (const [name, value] of [['Unpriced selected quantity', row.quantity], ['IV status', p.status], ['Captured option premium (points)', p.option_price], ['Captured model minimum (points)', p.lower_bound], ['Captured model maximum (points)', p.upper_bound], ['Captured underlying price', p.underlying_price], ['Captured underlying age (ms)', p.underlying_price_age_ms]]) {
          if (value !== undefined && value !== null) details.append(node('dt', name), node('dd', typeof value === 'number' ? formatNumber(value, 6) : String(value)));
        }
        body.append(details);
      }
    }
  }
  function freshnessClockSummary(report) {const base = report?.baseline?.iv_freshness, scenario = report?.scenario?.iv_freshness; return base || scenario ? ` Captured ${timeLabel((base || scenario).capture_as_of)} · scenario model time ${timeLabel(scenario?.as_of)}. IV age details below and in Source & assumptions.` : ' IV observation ages unavailable.';}
  function renderPricingAssumptions(report) {
    renderPricingCoverage(report);
    if (!report) {text('#pricing-model-context', 'Pricing assumptions pending. Recalculating from captured inputs.'); text('#compare-range-note', 'Strike range pending the current calculation.'); text('#compare-price-legend', 'Futures-price markers pending.'); return;}
    const baseline = report?.baseline?.pricing_assumptions;
    const scenario = report?.scenario?.pricing_assumptions;
    const descriptions = [...new Set([baseline?.summary, scenario?.summary].filter(Boolean))];
    const coverage = coverageOf(report?.scenario) || coverageOf(report?.baseline);
    const coverageText = coverage && coverage.unpriced_contract_count
      ? ` Priced ${formatNumber(coverage.priced_quantity, 0)} of ${formatNumber(coverage.selected_quantity, 0)} selected quantity; ${coverage.unpriced_contract_count} contract(s) have unavailable IV.` : '';
    const retainedText = coverage?.retained_iv_contract_count ? ` ${coverage.retained_iv_contract_count} contract(s) use an earlier valid IV observation.` : '';
    text('#pricing-model-context', descriptions.length
      ? `${descriptions.join(' ')}${[baseline, scenario].some(value => value?.early_exercise_modeled) ? '' : ' Early exercise is not modeled.'}${coverageText}${retainedText} See Source & assumptions for rate and timing inputs.${freshnessClockSummary(report)}`
      : 'Pricing assumptions unavailable. European-exercise formulas; early exercise is not modeled.');
  }
  function netOf(value) {return summaryOf(value).total_net_gex ?? null;}
  function wallOf(value) {return summaryOf(value).gamma_wall_strike ?? summaryOf(value).gamma_wall ?? null;}
  function matrixOf(value) {const matrix = value?.matrix; if (!matrix) return {strikes: [], net_gex: []}; return matrix;}
  function stateUsable(value) {return Number.isFinite(netOf(value));}
  function changeDescription(request) {const items = []; if (request.spot_shift) items.push(`${signed(request.spot_shift)} price points`); if (request.iv_shift) items.push(`${signed(request.iv_shift)} volatility points`); if (request.time_advance) items.push(`${formatNumber(request.time_advance)} minutes advanced`); if (request.exclude_nearest_expiry) items.push('nearest expiry removed'); return items.length ? items.join(' · ') : 'No scenario assumptions changed.';}
  function updateFingerprint() {const kind = state.view === 'models' && state.models ? 'Models' : state.view === 'fragility' && state.search ? 'Search' : state.view === 'landscape' && state.surface ? 'Surface' : 'Scenario'; const report = kind === 'Models' ? state.models : kind === 'Search' ? state.search : kind === 'Surface' ? state.surface : state.calculation; const fingerprint = report?.result_sha256; text('#source-fingerprint', fingerprint ? `${kind} result ${fingerprint.slice(0, 12)} · ${kind === 'Models' ? 'separate quantity models' : modelNames[$('#position-model').value]}` : 'Local calculations. No market connection.');}
  function renderCalculation() {
    const report = state.calculation; if (!report) return;
    $('.metric-strip').hidden = state.view === 'models'; renderPricingAssumptions(report);
    const base = report.baseline, scenario = report.scenario;
    text('#metric-baseline-net', money(netOf(base))); text('#metric-scenario-net', money(netOf(scenario))); text('#metric-baseline-wall', formatNumber(wallOf(base))); text('#metric-scenario-wall', formatNumber(wallOf(scenario)));
    const changed = changeDescription(report.request || requestFromControls());
    text('#scenario-state', stateUsable(scenario) ? (changed === 'No scenario assumptions changed.' ? 'Original assumptions' : 'Scenario recalculated') : 'Not evaluable');
    text('#spot-effective', `Original price ${formatNumber(base?.spot, 8)}`);
    text('#compare-caption', changed);
    const problems = [base, scenario].filter(value => !stateUsable(value)).map(value => value?.reason || value?.status || 'Selected model is not evaluable.');
    $('#result-notice').hidden = !problems.length; text('#result-notice', [...new Set(problems)].join(' '));
    updateFingerprint();
    renderCompare();
  }
  function priceRangeContext(states, matrices) {
    const prices = [states[0]?.spot, states[1]?.spot];
    const strikes = [...new Set(matrices.flatMap(matrix => matrix.strikes || []).filter(Number.isFinite))].sort((a, b) => a - b);
    const walls = states.map(wallOf).filter(Number.isFinite);
    const focused = state.strikeRange === 'focused' && prices.every(value => Number.isFinite(value) && value > 0);
    const anchors = focused ? [Math.min(...prices) * .98, Math.max(...prices) * 1.02, ...walls] : [...strikes, ...prices.filter(Number.isFinite), ...walls];
    const low = anchors.length ? Math.min(...anchors) : 0, high = anchors.length ? Math.max(...anchors) : 1;
    const pad = Math.max(1, (high - low) * .06), range = [low - pad, high + pad];
    const values = matrices.flatMap(matrix => (matrix.net_gex || []).filter((value, index) => Number.isFinite(value) && (!focused || matrix.strikes[index] >= range[0] && matrix.strikes[index] <= range[1]))).map(value => value / 1e9);
    let bottom = Math.min(0, ...values), top = Math.max(0, ...values); const yPad = Math.max((top - bottom) * .14, .000001); bottom -= yPad; top += yPad;
    const clipped = strikes.filter(value => value < range[0] || value > range[1]).length;
    const rangeCopy = `${focused ? 'Focused ±2% around original/scenario prices, including dominant walls' : state.strikeRange === 'focused' ? 'Full range (price unavailable)' : 'Full strike range'} · ${clipped} of ${strikes.length} strikes outside view. Display only: all contracts, totals and exact strike values are retained. Matched exposure scale uses ${focused ? 'visible' : 'all'} strikes.`;
    const shapes = [], annotations = [];
    const validPrices = prices.every(value => Number.isFinite(value) && value > 0);
    const markers = validPrices && prices[0] === prices[1] ? [{price: prices[0], label: 'Original + scenario price', color: '#edf4ff', dash: 'solid', anchor: 'center'}]
      : [{price: prices[0], label: 'Original price', color: colors.cyan, dash: 'dot', anchor: 'right'}, {price: prices[1], label: 'Scenario price', color: colors.amber, dash: 'dash', anchor: 'left'}].filter(marker => Number.isFinite(marker.price) && marker.price > 0);
    for (const marker of markers) {shapes.push({type: 'line', xref: 'x', yref: 'paper', x0: marker.price, x1: marker.price, y0: 0, y1: 1, line: {color: marker.color, width: 2, dash: marker.dash}}); annotations.push({xref: 'x', yref: 'paper', x: marker.price, y: 1.03, text: `${marker.label} ${formatNumber(marker.price, 8)}`, showarrow: false, xanchor: marker.anchor, yanchor: 'bottom', font: {color: marker.color, size: 9}});}
    return {range, yRange: [bottom, top], shapes, annotations, rangeCopy, markersCopy: markers.length ? markers.map(marker => `${marker.label} ${formatNumber(marker.price, 8)} (${marker.dash})`).join(' · ') : 'Futures price unavailable; no price marker.'};
  }
  function strikePlotLayout(context) {return chartLayout({margin: {l: 55, r: 18, t: 48, b: 55}, xaxis: {...chartLayout().xaxis, range: context.range}, yaxis: {...chartLayout().yaxis, range: context.yRange}, shapes: context.shapes, annotations: context.annotations, bargap: .2});}
  function renderCompare() {
    if (!state.calculation) return;
    const base = matrixOf(state.calculation.baseline), scenario = matrixOf(state.calculation.scenario);
    const baseValues = base.net_gex || [], scenarioValues = scenario.net_gex || [];
    const context = priceRangeContext([state.calculation.baseline, state.calculation.scenario], [base, scenario]);
    text('#compare-range-note', context.rangeCopy); text('#compare-price-legend', context.markersCopy);
    for (const [selector, data, color, title] of [['#baseline-plot', base, colors.cyan, 'Original state'], ['#scenario-plot', scenario, colors.amber, 'Recalculated scenario']]) {
      if (!(data.strikes || []).length) {emptyPlot(selector, 'No evaluable exposure', 'Inspect the source and selected quantity model.'); continue;}
      if (state.view === 'compare') draw(selector, [{type: 'bar', x: data.strikes, y: data.net_gex.map(value => value / 1e9), marker: {color}, name: title, hovertemplate: 'Strike %{x:,.2f}<br>Net GEX %{y:.4f}B<extra></extra>'}], strikePlotLayout(context)).catch(chartError);
    }
    const body = $('#comparison-table tbody'); body.replaceChildren();
    const baselineMap = new Map((base.strikes || []).map((strike, index) => [strike, baseValues[index]])); const scenarioMap = new Map((scenario.strikes || []).map((strike, index) => [strike, scenarioValues[index]]));
    [...new Set([...(base.strikes || []), ...(scenario.strikes || [])])].sort((a, b) => a - b).forEach(strike => {const b = stateUsable(state.calculation.baseline) ? baselineMap.get(strike) ?? 0 : null; const s = stateUsable(state.calculation.scenario) ? scenarioMap.get(strike) ?? 0 : null; const row = node('tr'); [formatNumber(strike), money(b), money(s), b === null || s === null ? '—' : money(s - b)].forEach(value => row.append(node('td', value))); body.append(row);});
  }
  const exactNumber = value => Number.isFinite(value) ? value.toLocaleString(undefined, {maximumFractionDigits: 8}) : 'Unavailable';
  function modelPriceStep() {return (currentSource()?.symbol || checkpointMetadata(state.terminalCheckpoint).source?.symbol) === 'NQ' ? 100 : 25;}
  function updateModelBounds() {const step = modelPriceStep(); text('#model-price-down', `Price −${step}`); text('#model-price-up', `Price +${step}`); text('#model-grid-bounds', `27 coordinates × 2 models. Price −${step} / 0 / +${step} points, IV −1 / 0 / +1 point, time 0 / 30 / 60 minutes.`);}
  function clearModels() {if (state.view === 'models') {text('#spot-effective', 'Original price pending'); text('#source-fingerprint', 'Model comparison pending · local inputs only');} state.modelsController?.abort(); state.modelsController = null; state.modelsBusy = false; state.models = null; state.modelsRequest = null; text('#models-range-note', 'Strike range pending the current comparison.'); text('#models-price-legend', 'Futures-price markers pending.'); $('#model-cards').replaceChildren(); $('#model-values-table tbody').replaceChildren(); $('#model-strike-table tbody').replaceChildren(); $('#model-grid-table tbody').replaceChildren(); $('#model-grid-summary').replaceChildren(node('p', 'No current grid. Run the grid for this saved checkpoint.')); text('#model-agreement', 'Comparison pending. Current source and assumptions must finish calculating.'); for (const target of ['#model-default-plot', '#model-directional-plot']) emptyPlot(target, 'Comparison pending', 'Both models will use the same source and scenario changes.');}
  function applyModelPreset(preset) {const step = modelPriceStep(); const values = {'baseline': [0, 0, 0], 'price-down': [-step, 0, 0], 'price-up': [step, 0, 0], 'iv-down': [0, -1, 0], 'iv-up': [0, 1, 0], 'time-30': [0, 0, 30], 'time-60': [0, 0, 60]}[preset]; if (!values) return; for (const [index, range, number] of [[0, '#spot-shift', '#spot-number'], [1, '#iv-shift', '#iv-number'], [2, '#time-advance', '#time-number']]) {$(range).value = values[index]; $(number).value = values[index];} $('#remove-expiry').checked = false; scheduleCalculation();}
  function directionSummary(value) {const coverage = value?.directional_coverage ?? summaryOf(value).directional_coverage; if (typeof coverage === 'number' && Number.isFinite(coverage)) return `Known aggressor coverage: ${formatNumber(coverage * 100)}% of priced volume.`; if (coverage && Number.isFinite(coverage.coverage_ratio)) return `Known aggressor coverage: ${formatNumber(coverage.coverage_ratio * 100)}% of priced volume.`; return 'Known aggressor coverage: unavailable for this state.';}
  function modelLabel(model) {return model.model === 'directionalized_trade_volume' ? 'Directionalized' : 'Default';}
  function appendModelMetric(card, label, baseline, scenario, formatter = money) {const block = node('div', undefined, 'model-metric'); block.append(node('span', label, 'metric-label')); const values = node('div', undefined, 'metric-values'); values.append(node('span', formatter(baseline), 'baseline'), node('span', 'to', 'metric-arrow'), node('span', formatter(scenario), 'scenario')); block.append(values); card.append(block);}
  function appendModelSourceDetails(body) {const report = state.models; if (!report) {body.append(node('p', 'Select a source and allow both model calculations to complete.')); return;} body.append(node('h3', 'Model comparison'), node('p', 'Default uses the captured Terminal quantity selection, or raw trade volume for bundled examples. Directionalized volume uses aggressor-side signed passive-counterparty quantities. Neither observes dealer inventory, opening/closing trades or a price forecast.'));
    for (const model of report.models || []) {body.append(node('h3', `${modelLabel(model)} · ${model.label || modelNames[model.model]}`)); const seen = new Set(); for (const value of [model.baseline, model.scenario]) {const p = value?.pricing_assumptions || {}; for (const copy of [p.summary, ...(p.limitations || []), p.rate_note, p.time_note].filter(Boolean)) if (!seen.has(copy)) {body.append(node('p', copy)); seen.add(copy);}} appendPricingCoverageDetails(body, model); if (model.model === 'directionalized_trade_volume') body.append(node('p', `Original: ${directionSummary(model.baseline)} Scenario: ${directionSummary(model.scenario)}`));} body.append(node('p', `Comparison result identity: ${report.result_sha256 || 'Unavailable'}. The grid is finite; IV shifts are absolute volatility points, quantities stay frozen, and elapsed time is model time.`));
  }
  function renderModels() {const report = state.models; if (!report) return; text('#spot-effective', `Original price ${formatNumber(report.models?.[0]?.baseline?.spot, 8)}`); $('#result-notice').hidden = true; updateModelBounds(); const models = report.models || [], cards = $('#model-cards'); cards.replaceChildren(); const exact = $('#model-values-table tbody'); exact.replaceChildren();
    for (const model of models) {const card = node('article', undefined, 'model-card'); card.append(node('h3', modelLabel(model)), node('p', model.label || modelNames[model.model], 'model-description')); appendModelMetric(card, 'NET EXPOSURE · USD / 1% MOVE', netOf(model.baseline), netOf(model.scenario)); appendModelMetric(card, 'DOMINANT GAMMA WALL', wallOf(model.baseline), wallOf(model.scenario), exactNumber);
      for (const [name, value] of [['Original', model.baseline], ['Scenario', model.scenario]]) {card.append(node('p', `${name}: ${value?.status || 'unavailable'}${value?.reason ? ` · ${value.reason}` : ''}`, stateUsable(value) ? 'model-state' : 'model-state coverage-warning')); card.append(node('p', `${name} pricing: ${coverageSummary(coverageOf(value))}`, 'model-coverage')); card.append(node('p', `${name} · ${freshnessSummary(value)}`, 'model-freshness'));  if (model.model === 'directionalized_trade_volume') card.append(node('p', `${name}: ${directionSummary(value)}`, 'model-coverage')); const row = node('tr'), summary = summaryOf(value); [modelLabel(model), name, value?.status || 'unavailable', exactNumber(netOf(value)), exactNumber(wallOf(value)), exactNumber(value?.matrix?.call_wall_strike ?? summary.call_wall_strike ?? summary.call_wall), exactNumber(value?.matrix?.put_wall_strike ?? summary.put_wall_strike ?? summary.put_wall)].forEach(value => row.append(node('td', String(value)))); exact.append(row);}
      const details = node('details', undefined, 'model-unpriced'), detailBody = node('div'); details.append(node('summary', 'Pricing, IV age & unpriced details')); appendPricingCoverageDetails(detailBody, model); details.append(detailBody); card.append(details); cards.append(card);
    }
    const agreement = report.agreement?.scenario; text('#model-agreement', !agreement || agreement.status !== 'available' ? `Model agreement: ${agreement?.status || 'not evaluable'}. Unavailable results are not zero exposure.` : `Scenario net sign ${agreement.net_sign_matches ? 'agrees' : 'differs'} · dominant gamma wall ${agreement.gamma_wall_matches === null ? 'is not evaluable' : agreement.gamma_wall_matches ? 'agrees' : 'differs'} across models. Agreement applies to this modeled point only.`); if (models.length === 2 && JSON.stringify(coverageOf(models[0].scenario)) !== JSON.stringify(coverageOf(models[1].scenario))) text('#model-agreement', $('#model-agreement').textContent + ' Pricing or selected-quantity coverage differs between models; inspect both denominators before comparing magnitude.');
    text('#models-caption', `${changeDescription(report.request || {})} Matched strike and exposure axes; missing model results are unavailable.`);
    const descriptions = [...new Set(models.flatMap(model => [model.baseline?.pricing_assumptions?.summary, model.scenario?.pricing_assumptions?.summary]).filter(Boolean))]; text('#pricing-model-context', descriptions.length ? `${descriptions.join(' ')} Shared captured inputs; frozen quantities, uniform IV shifts, and model-time changes. See Source & assumptions for rate, timing and contract exclusions.${freshnessClockSummary(models[0])}` : 'Shared captured inputs. Model pricing assumptions unavailable; inspect each state before interpretation.');
    renderModelPlots(models); renderModelStrikeTable(models); renderModelGrid(report.grid); updateFingerprint();
  }
  function renderModelPlots(models) {
    const matrices = models.map(model => stateUsable(model.scenario) ? matrixOf(model.scenario) : {strikes: [], net_gex: []});
    const original = models.find(model => Number.isFinite(model.baseline?.spot))?.baseline, scenario = models.find(model => Number.isFinite(model.scenario?.spot))?.scenario;
    const context = priceRangeContext([original, scenario, ...models.flatMap(model => [model.baseline, model.scenario])], matrices);
    text('#models-range-note', context.rangeCopy); text('#models-price-legend', context.markersCopy);
    for (const [index, selector, color] of [[0, '#model-default-plot', colors.cyan], [1, '#model-directional-plot', colors.amber]]) {const matrix = matrices[index]; if (!matrix?.strikes?.length) {emptyPlot(selector, 'Model result unavailable', models[index]?.scenario?.reason || 'No evaluable exposure. This does not mean zero.'); continue;} if (state.view === 'models') draw(selector, [{type: 'bar', x: matrix.strikes, y: matrix.net_gex.map(value => value / 1e9), marker: {color}, name: modelLabel(models[index]), hovertemplate: 'Strike %{x:,.2f}<br>Net GEX %{y:.6f}B<extra>%{fullData.name}</extra>'}], strikePlotLayout(context)).catch(chartError);}
  }
  function renderModelStrikeTable(models) {
    const states = models.flatMap(model => [model.baseline, model.scenario]), matrices = states.map(matrixOf);
    const strikes = [...new Set(matrices.flatMap(matrix => matrix.strikes || []))].sort((a, b) => a - b);
    const maps = matrices.map(matrix => new Map((matrix.strikes || []).map((strike, index) => [strike, matrix.net_gex[index]])));
    const body = $('#model-strike-table tbody'); body.replaceChildren();
    for (const strike of strikes) {const row = node('tr'); row.append(node('td', exactNumber(strike))); maps.forEach((map, index) => row.append(node('td', stateUsable(states[index]) ? exactNumber(map.get(strike) ?? 0) : 'Unavailable'))); body.append(row);}
  }
  function renderModelGrid(grid) {const box = $('#model-grid-summary'), body = $('#model-grid-table tbody'); box.replaceChildren(); body.replaceChildren(); if (!grid) {box.append(node('p', 'No current grid. Run 54 cases from this original checkpoint.')); return;} box.append(node('p', `${grid.case_count} calculated model cases · ${grid.axes.spot_shifts.map(value => signed(value)).join(' / ')} price pts · ${grid.axes.iv_shifts.map(value => signed(value)).join(' / ')} IV pts · ${grid.axes.time_advances.join(' / ')} model minutes.`, 'model-grid-receipt'));
    for (const summary of grid.summaries || []) {const card = node('div', undefined, 'model-grid-conclusion'); const label = modelLabel(summary); const signs = summary.net_sign_counts || {}; card.append(node('h4', `${label} · ${summary.evaluable_count} / ${summary.case_count} evaluable`), node('p', `${signs.positive ?? 0} positive · ${signs.negative ?? 0} negative · ${signs.zero ?? 0} zero · ${summary.not_evaluable_count ?? 0} unavailable.`)); if (summary.evaluable_count) card.append(node('p', `Net sign ${summary.net_sign_stable === null ? 'stability is not established' : summary.net_sign_stable ? 'held' : 'changed'} across evaluable points. Dominant wall ${summary.gamma_wall_stable === null ? 'stability is not established' : summary.gamma_wall_stable ? 'held' : 'changed'}: ${(summary.gamma_wall_strikes || []).map(exactNumber).join(' / ') || 'Unavailable'}. Net GEX range: ${exactNumber(summary.net_gex_range?.min)} to ${exactNumber(summary.net_gex_range?.max)} USD.`)); else card.append(node('p', 'No evaluable results; no stability conclusion.')); box.append(card);}
    for (const item of grid.cases || []) {const row = node('tr'); const c = item.pricing_coverage; [modelLabel(item), signed(item.spot_shift), signed(item.iv_shift), exactNumber(item.time_advance), item.status || 'unavailable', exactNumber(item.total_net_gex), exactNumber(item.gamma_wall_strike), c ? `${c.priced_contract_count} / ${c.selected_contract_count}` : 'Unavailable', item.reason || '—'].forEach(value => row.append(node('td', String(value)))); body.append(row);} box.append(node('p', 'A stable sign or wall applies only to these tested points and available contracts. Model magnitude, quantity interpretation and unpriced exclusions remain material. No probability or predictive validity is established.', 'chart-caption'));
  }
  async function calculateModels(grid = false, override = null, revision = state.revision) {stopPlayback(); const request = override || requestFromControls(); if (!request || !state.source) return; state.modelsController?.abort(); const controller = new AbortController(); state.modelsController = controller; state.modelsBusy = true; state.models = null; state.modelsRequest = null; text('#spot-effective', 'Original price pending'); text('#source-fingerprint', 'Model comparison pending · local inputs only'); text('#models-range-note', 'Strike range pending the current comparison.'); text('#models-price-legend', 'Futures-price markers pending.'); toggleBusy(); $('#model-cards').replaceChildren(); $('#model-values-table tbody').replaceChildren(); $('#model-strike-table tbody').replaceChildren(); $('#model-grid-table tbody').replaceChildren(); $('#model-grid-summary').replaceChildren(node('p', grid ? 'Testing all 54 cases from the original checkpoint…' : 'No current grid.')); text('#model-agreement', grid ? 'Calculating both models and the finite 54-case grid locally…' : 'Calculating both models from the same captured inputs…'); for (const target of ['#model-default-plot', '#model-directional-plot']) emptyPlot(target, 'Calculating both models…', 'No market data is requested.'); status(grid ? 'Calculating 54 local model cases…' : 'Comparing both quantity models locally…');
    try {const submitted = {...request, grid, detail_level: 'compact'}; const report = await post('models', submitted, controller.signal); if (controller.signal.aborted || revision !== state.revision || controller !== state.modelsController) return; state.models = report; state.modelsRequest = {...request, grid, detail_level: 'full'}; renderModels(); status(grid ? '54-case model comparison complete · finite tested points only' : 'Both models ready · local inputs only'); return {revision};}
    catch (error) {if (error.name !== 'AbortError' && revision === state.revision && controller === state.modelsController) {text('#model-agreement', `Model comparison unavailable: ${error.message}`); $('#model-grid-summary').replaceChildren(node('p', 'No current grid. The comparison did not complete.')); status(error.message, true);}}
    finally {if (controller === state.modelsController) {state.modelsBusy = false; state.modelsController = null; toggleBusy();}}
  }
  function chartError(error) {status(`Chart unavailable: ${error.message}`, true);}
  function supportsWebGL() {if (state.webgl !== null) return state.webgl; try {const canvas = document.createElement('canvas'); const context = canvas.getContext('webgl2') || canvas.getContext('webgl'); state.webgl = Boolean(context); context?.getExtension('WEBGL_lose_context')?.loseContext();} catch (_) {state.webgl = false;} return state.webgl;}
  function surfaceArrays(report) {
    const axes = report.axes || {}; const x = axes.baseline_underlying_prices || []; const sx = axes.scenario_underlying_prices || x; const y = axes.time_advances || []; const sy = axes.scenario_time_advances || y;
    const z = y.map(() => x.map(() => null)), sz = y.map(() => x.map(() => null));
    for (const point of report.points || []) {if (!z[point.time_index] || point.spot_index >= x.length) continue; z[point.time_index][point.spot_index] = Number.isFinite(point.baseline_total_net_gex) ? point.baseline_total_net_gex / 1e9 : null; sz[point.time_index][point.spot_index] = Number.isFinite(point.scenario_total_net_gex) ? point.scenario_total_net_gex / 1e9 : null;}
    return {x, sx, y, sy, z, sz};
  }
  function landscapeCaption(copy) {const request = state.surfaceRequest || state.surface?.request; const x = request?.spot_shifts?.length, y = request?.time_advances?.length; text('#landscape-caption', copy + (state.largeCheckpoint && x && y ? ` ${x === 3 && y === 3 ? 'Coarse ' : ''}${x} × ${y} grid · ${x * y} calculated samples; all retained contracts are included.` : ''));}
  async function renderLandscape() {
    if (!state.surface || state.view !== 'landscape') return;
    const grid = surfaceArrays(state.surface);
    if (!grid.x.length || !grid.y.length || ![...grid.z.flat(), ...grid.sz.flat()].some(Number.isFinite)) {emptyPlot('#landscape-plot', 'No landscape available.', 'This checkpoint cannot be evaluated with the selected model.'); return;}
    let use3d = $('#landscape-render').value === '3d';
    if (use3d && !supportsWebGL()) {$('#landscape-render').value = '2d'; use3d = false; text('#webgl-note', '3D is unavailable in this browser. Showing 2D time slices.');}
    if (!use3d) {
      const traces = [];
      for (const index of [...new Set([0, Math.floor((grid.y.length - 1) / 2), grid.y.length - 1])]) {
        traces.push({type: 'scatter', mode: 'lines', x: grid.x, y: grid.z[index], name: `Original · ${grid.y[index]} min`, line: {color: colors.cyan, width: 2, dash: index === 0 ? 'solid' : 'dot'}, opacity: index === 0 ? 1 : .65, hovertemplate: 'Price %{x:,.2f}<br>Net GEX %{y:.4f}B<extra>%{fullData.name}</extra>'});
        traces.push({type: 'scatter', mode: 'lines', x: grid.sx, y: grid.sz[index], name: `Scenario · ${grid.sy[index]} min`, line: {color: colors.amber, width: 2, dash: 'dash'}, opacity: index === 0 ? 1 : .65, hovertemplate: 'Price %{x:,.2f}<br>Net GEX %{y:.4f}B<extra>%{fullData.name}</extra>'});
      }
      await draw('#landscape-plot', traces, chartLayout({showlegend: true, legend: {orientation: 'h', x: 0, y: -.19, font: {size: 9}}, margin: {l: 60, r: 15, t: 15, b: 95}, xaxis: {...chartLayout().xaxis, title: {text: 'Underlying price'}}}));
      landscapeCaption('Original and scenario exposure at three sampled times. Dashed lines identify the scenario; hover for exact values.'); return;
    }
    const traces = [];
    const identical = JSON.stringify([grid.x, grid.y, grid.z]) === JSON.stringify([grid.sx, grid.sy, grid.sz]);
    const surfaces = [[grid.x, grid.y, grid.z, colors.cyan, identical ? 'Original and unchanged scenario' : 'Original state', .84]];
    if (!identical) surfaces.push([grid.sx, grid.sy, grid.sz, colors.amber, 'Recalculated scenario', .7]);
    for (const [x, y, z, color, name, opacity] of surfaces) {
      traces.push({type: 'surface', x, y, z, name, colorscale: [[0, color], [1, color]], showscale: false, opacity, lighting: {ambient: .78, diffuse: .55, specular: .15, roughness: .9}, contours: {x: {show: true, color: '#152536', width: 1}, y: {show: true, color: '#152536', width: 1}, z: {show: false}}, hovertemplate: 'Price %{x:,.2f}<br>Time +%{y:.0f} min<br>Net GEX %{z:.4f}B<extra>' + name + '</extra>'});
    }
    const axis = {gridcolor: colors.grid, zerolinecolor: '#4c6278', showbackground: false, color: colors.text, tickfont: {size: 10}};
    try {await draw('#landscape-plot', traces, chartLayout({margin: {l: 0, r: 0, t: 0, b: 0}, scene: {bgcolor: 'transparent', xaxis: {...axis, title: {text: 'Underlying price'}, tickformat: ',.0f'}, yaxis: {...axis, title: {text: 'Time advanced (min)'}}, zaxis: {...axis, title: {text: 'Net GEX (B)'}}, camera: {eye: {x: 1.2, y: -1.4, z: .85}}, aspectratio: {x: 1.65, y: 1, z: .72}}, uirevision: state.source})); $('#landscape-plot').removeAllListeners?.('plotly_webglcontextlost'); $('#landscape-plot').on?.('plotly_webglcontextlost', () => {state.webgl = false; $('#landscape-render').value = '2d'; text('#webgl-note', '3D context lost. Showing 2D time slices.'); renderLandscape().catch(chartError);}); landscapeCaption((identical ? 'Original and scenario coincide; a single cyan surface shows both. ' : '') + 'Drag to rotate. Hover for exact values. The mesh between calculated samples is a visual interpolation.');}
    catch (error) {state.webgl = false; $('#landscape-render').value = '2d'; text('#webgl-note', '3D could not render. Showing 2D time slices.'); await renderLandscape();}
  }
  function linspace(low, high, count) {return Array.from({length: count}, (_, index) => Number((low + (high - low) * index / (count - 1)).toFixed(6)));}
  async function calculateLandscape(request = requestFromControls(), revision = state.revision) {
    if (!request || !state.calculation || state.surfaceBusy) return;
    if (state.surface) {await renderLandscape(); return;}
    const controller = new AbortController(); state.surfaceController = controller; state.surfaceBusy = true; toggleBusy();
    const surfaceRequest = {...request, spot_shifts: linspace(-100, 100, state.largeCheckpoint ? 3 : 17), time_advances: linspace(0, 60, state.largeCheckpoint ? 3 : 9)}; state.surfaceRequest = surfaceRequest;
    status(state.largeCheckpoint ? 'Calculating coarse 3 × 3 landscape · 9 samples; Compare remains available…' : 'Calculating landscape samples…');
    try {
      const report = await post('surface', surfaceRequest, controller.signal);
      if (revision !== state.revision || controller !== state.surfaceController) return;
      state.surface = report; updateFingerprint(); await renderLandscape(); status('Calculated locally · source preserved');
    } catch (error) {
      if (error.name !== 'AbortError' && revision === state.revision && controller === state.surfaceController) {
        state.surface = null; emptyPlot('#landscape-plot', 'Landscape unavailable', `${error.message} Compare and pricing coverage remain available.`);
        if (state.view === 'landscape') status(`Landscape unavailable: ${error.message} Compare remains available.`, true);
      }
    } finally {if (controller === state.surfaceController) {state.surfaceBusy = false; state.surfaceController = null; toggleBusy();}}
  }
  async function calculate() {
    if (state.view === 'models') {state.busy = false; return calculateModels();}
    const request = requestFromControls(); if (!request || !state.source) return;
    clearModels(); const revision = ++state.revision; state.controller?.abort(); const controller = new AbortController(); state.controller = controller; state.calculation = null; clearLandscape(); $('.metric-strip').hidden = true; renderPricingAssumptions(null); state.busy = true; toggleBusy(); status('Recalculating from local source…');
    try {
      const report = await post('calculate', request, controller.signal); if (revision !== state.revision) return;
      state.calculation = report; if (state.source === terminalSession && report.request?.terminal_checkpoint) state.terminalCheckpoint = report.request.terminal_checkpoint; renderCalculation();
      const large = isTerminalSource() && Number(report.baseline?.counts?.source_rows || 0) > 500;
      const firstLargeLoad = large && !state.largeCheckpoint; state.largeCheckpoint = large;
      if (firstLargeLoad && !state.landscapeRequested && state.view !== 'models') setView('compare');
      if (state.view === 'models') await calculateModels(false, request, revision);
      else if (!large || state.view === 'landscape') await calculateLandscape(request, revision);
      else status('Compare ready · open Landscape for a coarse 3 × 3 grid (9 calculated samples).');
      if (revision === state.revision && state.calculation) return {revision};
    } catch (error) {if (error.name !== 'AbortError' && revision === state.revision) {state.calculation = null; clearLandscape(); renderPricingAssumptions(null); status(error.message, true); text('#scenario-state', 'Calculation unavailable'); $('#result-notice').hidden = false; text('#result-notice', error.message);}}
    finally {if (revision === state.revision) {state.busy = false; toggleBusy();}}
  }
  let metadataArtifact = null, metadataValue = {};
  function checkpointMetadata(artifact) {if (typeof artifact !== 'string') return {}; if (artifact !== metadataArtifact) {metadataValue = JSON.parse(artifact); metadataArtifact = artifact;} return metadataValue;}
  function isCapturedSource(source = currentSource()) {return /^Local capture [0-9a-f]{64} · event [1-9][0-9]*$/.test(checkpointMetadata(source?.terminal_checkpoint).source?.label || '');}
  function frozenSourceLabel(source = currentSource()) {return isCapturedSource(source) ? 'Frozen captured checkpoint' : 'Frozen Terminal checkpoint';}
  function sourceName(source) {return source.name || source.id || source.session;}
  function currentSource() {return state.sources.find(item => sourceName(item) === state.source);}
  function isTerminalSource(source = currentSource()) {return source?.source_kind === 'terminal_checkpoint' || state.source === terminalSession;}
  function checkpointTime(checkpoint) {return checkpoint?.event_time || checkpoint?.as_of || checkpoint?.timestamp;}
  function fullTimeLabel(value) {if (!value) return 'Time unavailable'; const date = new Date(value); return Number.isNaN(date.valueOf()) ? String(value) : date.toISOString().replace('T', ' ').replace('.000Z', ' UTC');}
  function updateSourceContext(source) {
    const frozen = isTerminalSource(source), captured = checkpointMetadata(source?.terminal_checkpoint).source || {}, asOf = source?.as_of || source?.last_as_of;
    text('#header-source', `${source?.symbol || 'Research'} · ${frozen ? frozenSourceLabel(source) : 'Synthetic replay'}${asOf ? ` · ${timeLabel(asOf)}` : ''}`);
    text('#checkpoint-heading', frozen ? frozenSourceLabel(source) : 'Replay checkpoint');
    text('#baseline-heading', frozen ? (isCapturedSource(source) ? 'Original captured state' : 'Original Terminal state') : 'Original replay state');
    text('#evidence-limit', `${frozen ? (isCapturedSource(source) ? 'Frozen captured inputs' : 'Frozen Terminal inputs') : 'Synthetic inputs'} · conditional model output · predictive validity unmeasured`);
    const expiry = source?.expiry_filter || 'All captured expiries', quality = source?.quality || captured.quality || {};
    const healthNames = ['healthy', 'degraded', 'down', 'stale', 'entitlement', 'simulated'];
    const health = healthNames.includes(quality.health) ? quality.health : healthNames.includes(quality.status) ? quality.status : 'unknown';
    const mode = source?.data_mode || captured.data_mode || (frozen ? 'unknown' : 'DEMO'), inputKind = (source?.synthetic ?? captured.synthetic ?? !frozen) ? `synthetic ${mode}` : mode;
    text('#header-mode', `Mode: ${mode}`); text('#header-health', `Health: ${health}`);
    $('#header-health').classList.toggle('coverage-warning', !['healthy', 'simulated'].includes(health));
    text('#source-context', frozen ? `Frozen at ${fullTimeLabel(asOf)} · expiry: ${expiry} · Mode: ${mode} · Health: ${health} · ${inputKind} inputs. Captured health describes the source ledger, not the active pricing-coverage denominator.` : `Bundled synthetic replay · Mode: ${mode} · Health: ${health} · move between checkpoints to explore the example.`);
    for (const selector of ['#position-model', '#comparison-model']) for (const option of $(selector).options) {
      option.hidden = option.value === 'terminal_selected' && !frozen;
      option.disabled = option.value === 'terminal_selected' && !frozen;
      option.textContent = modelNames[option.value] + (source?.models?.[option.value]?.available_in_source === false ? ' · no source fields' : '');
    }
    if (!frozen && $('#comparison-model').value === 'terminal_selected') $('#comparison-model').value = 'open_interest';
  }
  function registerTerminalSource(artifact) {
    // The artifact was checked by /api/reproduce or /api/intake/checkpoint. Keep its bytes opaque.
    const source = terminalSourceFromArtifact(artifact);
    state.sources = [source, ...state.sources.filter(item => sourceName(item) !== terminalSession)];
    const select = $('#source'); let option = [...select.options].find(item => item.value === terminalSession);
    if (!option) {option = node('option'); option.value = terminalSession; select.append(option);}
    option.textContent = source.label;
    return source;
  }
  function terminalSourceFromArtifact(artifact) {
    const decoded = checkpointMetadata(artifact), source = decoded.source || {}, parameters = decoded.parameters || {};
    const captured = /^Local capture [0-9a-f]{64} · event [1-9][0-9]*$/.test(source.label || '');
    return {name: terminalSession, label: captured ? 'Frozen captured checkpoint' : 'Frozen Terminal checkpoint', source_kind: 'terminal_checkpoint', status: 'available',
      symbol: source.symbol, as_of: source.as_of, expiry_filter: source.expiry_filter, quality: source.quality,
      data_mode: source.data_mode, synthetic: source.synthetic, provenance: source, terminal_checkpoint: artifact,
      defaults: {session: terminalSession, checkpoint: 0, model: 'terminal_selected',
        fallback_dte: parameters.fallback_dte, risk_free_rate: parameters.risk_free_rate}};
  }
  function setCheckpoint(position) {const checkpoint = state.checkpoints[position]; if (!checkpoint) return; state.checkpoint = checkpoint.index ?? checkpoint.event_index ?? checkpoint.checkpoint ?? position; $('#checkpoint').value = position; text('#checkpoint-label', timeLabel(checkpointTime(checkpoint))); text('#checkpoint-count', isTerminalSource() ? '1 frozen checkpoint · playback unavailable' : `${position + 1} of ${state.checkpoints.length} checkpoints`);}
  async function loadSource(session, desiredCheckpoint = undefined, preserveScenario = false, skipCalculation = false) {
    stopPlayback(); clearTimeout(calculateTimer); state.controller?.abort(); state.revision++; const revision = ++state.sourceRevision; state.source = session; text('#spot-effective', 'Original price pending'); state.calculation = null; clearLandscape(); clearModels(); state.largeCheckpoint = false; state.landscapeRequested = false; renderPricingAssumptions(null); clearSearch(); state.busy = true; toggleBusy(); $('#source').value = session; status('Loading source checkpoint…');
    const source = currentSource();
    state.terminalCheckpoint = isTerminalSource(source) ? source?.terminal_checkpoint || state.terminalCheckpoint : null;
    if (!preserveScenario) populateScenario({...emptyScenario, ...(isTerminalSource(source) ? source?.defaults : state.bundledDefaults), session});
    updateSourceContext(source);
    $('#play-replay').disabled = true; $('#checkpoint').disabled = true;
    try {const result = isTerminalSource(source) && state.terminalCheckpoint ? {checkpoints: [{index: 0, as_of: source?.as_of}]} : await api(`checkpoints?session=${encodeURIComponent(session)}`); if (revision !== state.sourceRevision) return; state.checkpoints = result.checkpoints || []; if (!state.checkpoints.length) throw new Error('This source has no evaluable checkpoints. Select another source.');
      const playable = !isTerminalSource(source) && state.checkpoints.length > 1;
      $('#checkpoint').max = state.checkpoints.length - 1; $('#checkpoint').disabled = !playable; $('#play-replay').disabled = !playable;
      const requestedPosition = state.checkpoints.findIndex((item, index) => (item.index ?? item.event_index ?? item.checkpoint ?? index) === desiredCheckpoint);
      setCheckpoint(requestedPosition >= 0 ? requestedPosition : state.checkpoints.length - 1); text('#checkpoint-start', timeLabel(checkpointTime(state.checkpoints[0]))); text('#checkpoint-end', timeLabel(checkpointTime(state.checkpoints.at(-1)))); if (skipCalculation) {state.busy = false; toggleBusy(); return {sourceRevision: revision, calculationRevision: state.revision};} state.busy = false; const calculation = await (state.view === 'models' ? calculateModels() : calculate()); if (calculation && revision === state.sourceRevision) return {sourceRevision: revision, calculationRevision: calculation.revision};
    } catch (error) {if (revision === state.sourceRevision) {status(error.message, true); state.busy = false; $('#checkpoint').disabled = true; $('#play-replay').disabled = true; emptyPlot('#landscape-plot', 'Source unavailable', error.message); toggleBusy();}}
  }
  function stopPlayback() {if (state.playback) clearInterval(state.playback); state.playback = null; $('#play-replay').setAttribute('aria-label', 'Play replay checkpoints'); $('#play-replay').title = 'Play checkpoints'; $('#play-replay').classList.remove('playing'); const image = document.createElement('img'); image.src = '/static/icons/play.svg'; image.alt = ''; $('#play-replay').replaceChildren(image);}
  function playReplay() {if (state.playback) {stopPlayback(); return;} if (isTerminalSource() || state.checkpoints.length < 2) return; if (Number($('#checkpoint').value) >= state.checkpoints.length - 1) setCheckpoint(0); $('#play-replay').setAttribute('aria-label', 'Pause replay checkpoints'); $('#play-replay').title = 'Pause checkpoints'; $('#play-replay').classList.add('playing'); $('#play-replay').replaceChildren(node('span', 'Pause')); calculate(); state.playback = setInterval(() => {if (state.busy) return; const next = Number($('#checkpoint').value) + 1; if (next >= state.checkpoints.length) {stopPlayback(); return;} clearSearch(); setCheckpoint(next); calculate();}, 1000);}
  function setView(view, focus = false) {const previousView = state.view; state.view = view; if (view !== 'models' && state.modelsBusy) clearModels(); $('.metric-strip').hidden = view === 'models' || !state.calculation; $('#result-notice').hidden = view === 'models' || !state.calculation; $('.pricing-coverage').hidden = view === 'models'; $('.search-controls').hidden = view === 'models'; $('#position-model').disabled = view === 'models'; $('#model-control-note').hidden = view !== 'models'; if (view === 'landscape') state.landscapeRequested = true; else if (state.surfaceBusy) clearLandscape(); for (const tab of $$('.tabs button')) {const active = tab.dataset.view === view; tab.setAttribute('aria-selected', active); tab.tabIndex = active ? 0 : -1; $(`#panel-${tab.dataset.view}`).hidden = !active; if (active && focus) tab.focus();}
    const copy = {landscape: ['Find what changes the structure.', 'Change the assumptions. See how the modeled exposure responds.'], compare: ['Branch a market moment.', 'See exactly which assumption changes the modeled structure.'], fragility: ['How far does the conclusion hold?', 'Test a claim within explicit bounds. Inspect the smallest tested change.'], models: ['Does the conclusion survive the model?', 'Compare default and directionalized exposure from the same saved inputs.']}[view]; text('#view-title', copy[0]); text('#view-description', copy[1]); if (view === 'landscape') {if (state.surface) renderLandscape().catch(chartError); else if (state.calculation && !state.busy) calculateLandscape().catch(chartError);} if (previousView === 'models' && ['compare', 'landscape', 'fragility'].includes(view) && !state.calculation && !state.busy && !state.searchBusy && state.source) calculate(); if (view === 'compare') {renderCompare(); if (state.calculation && !state.busy) status('Compare ready · source and pricing coverage preserved');} if (view === 'fragility') renderMap(); if (view === 'models') {updateModelBounds(); if (state.models) renderModels(); else if (!state.busy && !state.modelsBusy) calculateModels();} else if (state.calculation) renderCalculation(); updateFingerprint(); toggleBusy();}
  function searchRequest() {const request = requestFromControls(); if (!request) return null; if (!$('#search-price').checkValidity() || !$('#search-iv').checkValidity() || !$('#search-price').value || !$('#search-iv').value) {toast('Enter positive price and IV search bounds within the displayed ranges.'); return null;} const count = Number($('#search-samples').value); const loaded = $('#search-samples').value === 'loaded' ? state.loadedSearchGrid : null; const price = Number($('#search-price').value), iv = Number($('#search-iv').value); return {...request, x_axis: 'spot_shift', y_axis: 'iv_shift', x_values: loaded ? loaded.x : linspace(-price, price, count), y_values: loaded ? loaded.y : linspace(-iv, iv, count), claim: $('#claim').value, comparison_model: $('#comparison-model').value};}
  async function runSearch(override) {stopPlayback(); const request = override || searchRequest(); if (!request) return; const revision = state.revision; state.searchController?.abort(); const controller = new AbortController(); state.searchController = controller; state.searchBusy = true; toggleBusy(); setView('fragility'); status('Searching a finite grid of local scenarios…'); $('#apply-breaking-case').hidden = true; $('#search-result').replaceChildren(node('p', 'CALCULATING', 'eyebrow'), node('h3', 'Testing the bounds…'), node('p', 'Each point is a fresh model calculation. No market data is requested.'));
    try {const report = await post('search', request, controller.signal); if (controller.signal.aborted || revision !== state.revision) return; state.search = report; renderMap(); renderSearchResult(); updateFingerprint(); status('Bounded search complete · tested cases only');}
    catch (error) {if (error.name !== 'AbortError') {status(error.message, true); $('#search-result').replaceChildren(node('p', 'SEARCH UNAVAILABLE', 'eyebrow'), node('h3', 'Could not finish.'), node('p', error.message));}}
    finally {if (state.searchController === controller) {state.searchBusy = false; toggleBusy();}}
  }
  function smallestRequest() {const smallest = state.search?.smallest_change; if (!smallest) return null; return smallest.request || {...state.search.request, [state.search.request.x_axis]: smallest.x_value ?? smallest.x, [state.search.request.y_axis]: smallest.y_value ?? smallest.y};}
  function renderSearchResult() {const report = state.search, smallest = report.smallest_change; const box = $('#search-result'); box.replaceChildren(); const labels = {break_found: ['BREAKING CASE FOUND', 'Smallest tested change'], no_break_found: ['NO BREAK FOUND', 'Holds in the tested grid'], not_evaluable: ['NOT EVALUABLE', 'No valid comparison']}; const [eyebrow, heading] = labels[report.outcome] || ['SEARCH COMPLETE', report.outcome]; box.append(node('p', eyebrow, 'eyebrow'), node('h3', heading)); if (smallest) {const request = smallestRequest(); box.append(node('p', `${signed(request.spot_shift)} price pts · ${signed(request.iv_shift)} vol pts · ${formatNumber(request.time_advance)} min`), node('p', 'Smallest normalized distance among tested cases. Untested changes may produce a closer break.'));} else {box.append(node('p', report.outcome === 'no_break_found' ? 'The claim did not change at evaluated points within these bounds. This is not a guarantee between or beyond them.' : 'The selected quantity model or shifted inputs cannot support this claim. Inspect assumptions or choose a different model.'));} $('#apply-breaking-case').hidden = !smallest;}
  function renderMap() {if (state.view !== 'fragility') return; if (!state.search) {emptyPlot('#fragility-plot', 'Test a claim across price and IV shifts.', 'Choose the claim and bounds, then find a breaking point.'); return;} const report = state.search, request = report.request; const cells = report.cells || report.points || [];
    const body = $('#search-table tbody'); body.replaceChildren(); for (const cell of cells) {const row = node('tr'); [signed(cell.x), signed(cell.y), cell.status.replaceAll('_', ' '), formatNumber(cell.summary?.gamma_wall), money(cell.summary?.total_net_gex), cell.reason || '—'].forEach(value => row.append(node('td', value))); body.append(row);} const groups = {unchanged: [], changed: [], not_evaluable: []}; for (const cell of cells) (groups[cell.status] || groups.not_evaluable).push(cell);
    const traces = Object.entries(groups).filter(([, values]) => values.length).map(([key, values]) => ({type: 'scatter', mode: 'markers', x: values.map(cell => cell.x_value ?? cell.x), y: values.map(cell => cell.y_value ?? cell.y), text: values.map(cell => cell.reason || (key === 'changed' ? 'Claim changes at this tested point' : key === 'unchanged' ? 'Claim holds at this tested point' : 'Not evaluable')), name: key === 'changed' ? 'Claim changes' : key === 'unchanged' ? 'Claim holds' : 'Not evaluable', marker: {color: key === 'changed' ? colors.amber : key === 'unchanged' ? colors.cyan : '#566778', symbol: key === 'not_evaluable' ? 'x' : 'square', size: Math.max(9, Math.min(28, 330 / request.x_values.length)), opacity: .8, line: {width: 1, color: '#0b1520'}}, hovertemplate: 'Price shift %{x:+.2f} pts<br>IV shift %{y:+.2f} pts<br>%{text}<extra></extra>'}));
    traces.push({type: 'scatter', mode: 'markers', x: [0], y: [0], name: 'Zero price / IV shift', marker: {color: '#f0f4fb', size: 12, symbol: 'circle-open', line: {width: 2}}, hovertemplate: 'Zero price / IV shift<br>Other selected assumptions remain fixed<extra></extra>'});
    if (report.smallest_change) {const smallest = smallestRequest(); traces.push({type: 'scatter', mode: 'markers', x: [smallest[request.x_axis]], y: [smallest[request.y_axis]], name: 'Smallest tested break', marker: {color: colors.amber, size: 18, symbol: 'diamond-open', line: {width: 3}}, hovertemplate: 'Smallest tested break<br>Price %{x:+.2f}<br>IV %{y:+.2f}<extra></extra>'});}
    text('#tested-claim', `Tested claim: ${$('#claim').selectedOptions[0].textContent}.`); text('#map-caption', `${cells.length} tested cases. Marker colors describe evaluated points only; gaps are not a continuous boundary. Time and expiry treatment remain fixed at your selected settings.`);
    draw('#fragility-plot', traces, chartLayout({xaxis: {...chartLayout().xaxis, title: {text: 'Underlying price shift (points)'}, zeroline: true}, yaxis: {...chartLayout().yaxis, title: {text: 'IV shift (volatility points)'}, zeroline: true}})).catch(chartError);
  }
  function showDialog(selector) {stopPlayback(); $(selector).showModal();}
  function discardIntake() {
    intake.revision++; intake.controller?.abort(); intake.controller = null; intake.busy = false;
    const id = intake.verified?.intake_id; intake.verified = null;
    if (id && state.capability) api(`intake/${encodeURIComponent(id)}`, {method: 'DELETE'}).catch(() => {});
    $('#intake-review').hidden = true; $('#intake-details').replaceChildren(); $('#intake-warnings').replaceChildren(); $('#intake-checkpoint').replaceChildren();
    toggleIntake();
  }
  function toggleIntake() {
    $('#verify-session').disabled = intake.busy || !$('#session-file').files?.length || !$('#intake-rights').checked;
    $('#open-intake-checkpoint').disabled = intake.busy || !intake.verified || !$('#intake-checkpoint').value || !$('#intake-rights').checked;
    $('#intake-checkpoint').disabled = intake.busy;
  }
  function showIntake() {discardIntake(); $('#session-file').value = ''; $('#intake-rights').checked = false; text('#intake-status', 'Choose a complete captured session to begin.'); $('#intake-status').classList.remove('error'); toggleIntake(); showDialog('#intake-dialog'); $('#session-file').focus();}
  function changeIntakeFile() {discardIntake(); $('#intake-rights').checked = false; text('#intake-status', 'Check the selected file and your permission to use it, then verify.'); $('#intake-status').classList.remove('error'); toggleIntake();}
  function renderIntakeReview(report) {
    const details = $('#intake-details'), inputs = report.model_inputs || {}, source = report.source || {}, quality = report.quality || {}, fallback = inputs.fallback_dte ?? inputs.days_to_expiry;
    const fields = [['Integrity', 'Verified complete capture · integrity is not provider certification'], ['Source', `${report.symbol || 'Unknown symbol'} · ${source.provider || 'unspecified provider'} · ${source.mode || 'unspecified mode'} · ${report.synthetic ? 'synthetic inputs' : 'recorded inputs; origin unqualified'}`], ['Raw first event / latest time', `${fullTimeLabel(report.first_event_time)} / ${fullTimeLabel(report.last_event_time)}`], ['Events', formatNumber(report.event_count, 0)], ['Multiplier', inputs.contract_multiplier ?? 'Unavailable'], ['Risk-free rate', inputs.risk_free_rate === undefined ? 'Unavailable' : `${formatNumber(inputs.risk_free_rate * 100, 4)}%`], ['Fallback DTE', fallback === undefined ? 'Unavailable' : `${fallback} days`], ['Expiry filter', inputs.expiry_filter || 'All captured expiries'], ['Recorded session quality', quality.available ? `${quality.status || 'unknown'} / ${quality.health || 'unknown'} · end of session, not the selected prefix` : 'Unavailable in capture footer'], ['Recorded quality counts', quality.available ? `malformed ${quality.malformed_count ?? 'unavailable'} · dropped ${quality.dropped_count ?? 'unavailable'} · fallback IV ${quality.fallback_iv_tick_count ?? 'unavailable'}` : 'Unavailable'], ['Receipt-time fallbacks', formatNumber(report.event_time_fallback_count ?? 0, 0)], ['Capture identity', report.content_sha256 || 'Unavailable']];
    details.replaceChildren(); for (const [name, value] of fields) details.append(node('dt', name), node('dd', String(value)));
    $('#intake-warnings').replaceChildren(...(report.warnings || []).map(warning => node('li', warning)));
    const select = $('#intake-checkpoint'); select.replaceChildren();
    for (const checkpoint of report.checkpoints) {const option = node('option', `Event ${checkpoint.sequence + 1} · raw through ${fullTimeLabel(checkpoint.event_time)} · ${checkpoint.event_type || 'event'}`); option.value = String(checkpoint.sequence); select.append(option);}
    select.value = String(report.default_sequence ?? report.checkpoints.at(-1).sequence);
    if (![...select.options].some(option => option.value === select.value)) select.value = String(report.checkpoints.at(-1).sequence);
    text('#intake-checkpoint-note', `${report.checkpoints.length < report.event_count ? `Showing ${report.checkpoints.length} sampled event positions from ${formatNumber(report.event_count, 0)} events. ` : ''}The chosen event and all preceding events form one frozen checkpoint. Later events are excluded. Times preview the raw captured prefix; ignored records can be later than accepted market state. The opened checkpoint shows the authoritative accepted cutoff. A checkpoint without usable timed market inputs cannot be opened.`);
    $('#intake-review').hidden = false; toggleIntake();
  }
  async function verifySession() {
    const file = $('#session-file').files?.[0]; if (!file || !$('#intake-rights').checked || intake.busy) return;
    discardIntake(); const revision = intake.revision; intake.busy = true; toggleIntake(); text('#intake-status', 'Verifying the complete capture and its event hashes…'); $('#intake-status').classList.remove('error');
    try {
      if (!file.size || file.size > maxSessionBytes) throw new Error('Choose a nonempty complete captured session no larger than 4 MiB.');
      if (file.name?.endsWith('.partial')) throw new Error('This is a partial capture. Choose a completed .gex-session.jsonl file.');
      // Let a canceled inspection finish so its opaque token can be discarded.
      // Aborting fetch here could leave an unreachable capture in the server's bounded memory.
      const report = await api('intake', {method: 'POST', rawBody: file, contentType: 'application/octet-stream'});
      if (revision !== intake.revision) {if (report?.intake_id && state.capability) api(`intake/${encodeURIComponent(report.intake_id)}`, {method: 'DELETE'}).catch(() => {}); return;}
      if (typeof report.intake_id !== 'string' || !Array.isArray(report.checkpoints) || !report.checkpoints.length || report.checkpoints.some(item => !Number.isSafeInteger(item.sequence) || item.sequence < 0)) throw new Error('The local service did not return a usable checkpoint inventory.');
      intake.verified = report; renderIntakeReview(report); text('#intake-status', 'Integrity verified. Inspect the source, assumptions and warnings before opening a checkpoint.');
    } catch (error) {if (revision === intake.revision && error.name !== 'AbortError') {text('#intake-status', error.message); $('#intake-status').classList.add('error');}}
    finally {if (revision === intake.revision) {intake.busy = false; intake.controller = null; toggleIntake();}}
  }
  async function openIntakeCheckpoint() {
    if (!intake.verified || intake.busy || !$('#intake-rights').checked) return;
    const revision = intake.revision, intakeId = intake.verified.intake_id, sequence = Number($('#intake-checkpoint').value), controller = new AbortController();
    intake.controller = controller; intake.busy = true; toggleIntake(); text('#intake-status', 'Validating the selected event prefix and freezing its market inputs…'); $('#intake-status').classList.remove('error');
    try {
      const result = await post('intake/checkpoint', {intake_id: intakeId, sequence}, controller.signal);
      if (revision !== intake.revision || controller.signal.aborted) return;
      if (typeof result.terminal_checkpoint !== 'string') throw new Error('The local service did not return a portable checkpoint.');
      registerTerminalSource(result.terminal_checkpoint); $('#intake-dialog').close(); discardIntake(); await loadSource(terminalSession, 0); toast('Captured checkpoint opened. Save a scenario to keep its portable research receipt.');
    } catch (error) {if (revision === intake.revision && error.name !== 'AbortError') {text('#intake-status', error.message); $('#intake-status').classList.add('error');}}
    finally {if (revision === intake.revision) {intake.busy = false; intake.controller = null; toggleIntake();}}
  }
  function showHelp() {text('#info-title', 'Use the Wind Tunnel'); const body = $('#info-content'); body.replaceChildren(); [['Start with a checkpoint', 'Choose Open local session to verify a complete captured session and inspect its source, assumptions and event checkpoint. You can also start from a frozen Terminal checkpoint or choose a bundled synthetic replay. Replay sources offer a checkpoint slider; a Terminal handoff preserves one market moment. The original state is preserved while each scenario is calculated independently. The local launch session stays available across refreshes in this browser tab.'], ['Stress one assumption at a time', 'Price shifts are underlying points. IV shifts are absolute volatility points: +1 point adds 0.01 to IV. Time advanced reprices the same quantities; it does not forecast trades. Expiry removal excludes contracts from the scenario.'], ['Read the four views', 'Model comparison shows default and directionalized exposure side by side, with shared controls and a separate 54-case grid. Landscape samples price and time. Compare shows strike exposure on matched scales. Fragility Map tests a finite price/IV grid for a specified claim, with other settings held fixed. The smallest tested break is not a mathematical global minimum.'], ['Keep the model distinction', 'Terminal selected proxy matches the captured Terminal selection: positive trade volume per contract, otherwise open interest. Open interest, trade volume, and directionalized volume remain distinct quantities. A model without the required source fields is not evaluable. None identifies observed dealer inventory.'], ['Save and reproduce', 'Saved scenarios retain source identities, exact requests and results. Reopening recalculates and verifies the portable receipt. Export downloads that receipt as JSON.'], ['Keyboard and accessible views', 'Use Tab to move between controls, arrow keys inside the view tabs or sliders, and Escape to close a dialog. Number inputs mirror sliders. Switch the landscape to 2D if 3D is unavailable. Compare also includes a table of exact strike values.'], ['Evidence limit', 'Bundled replay inputs are synthetic. Terminal handoffs preserve their captured source identity and quality; freezing a checkpoint does not certify the provider. Outputs are conditional on the selected model. Predictive validity remains unmeasured. These scenarios do not estimate probabilities or give trade recommendations.']].forEach(([heading, copy]) => body.append(node('h3', heading), node('p', copy))); showDialog('#info-dialog');}
  function showSource() {text('#info-title', 'Source & assumptions'); const body = $('#info-content'); body.replaceChildren(node('p', isTerminalSource() ? (isCapturedSource() ? 'This checkpoint freezes one verified capture prefix. Its portable source label identifies the capture digest and included event count. Later capture events are excluded. Integrity does not establish authentic provenance, data rights or provider certification.' : 'This is a frozen Terminal checkpoint, not a continuing market connection. Scenarios use its captured inputs; the Terminal can continue independently.') : 'This source uses packaged synthetic inputs. The calculation receipt identifies the exact checkpoint and model.')); const source = currentSource(); if (isTerminalSource()) {const details = node('dl'); for (const [name, value] of [['Captured at', fullTimeLabel(source?.as_of)], ['Expiry filter', source?.expiry_filter || 'All captured expiries'], ['Mode', $('#header-mode').textContent.replace('Mode: ', '')], ['Captured source health', $('#header-health').textContent.replace('Health: ', '')], ['Source quality counters', JSON.stringify(source?.quality || checkpointMetadata(state.terminalCheckpoint).source?.quality || {})]]) details.append(node('dt', name), node('dd', String(value))); body.append(details);} if (state.view === 'models') {appendModelSourceDetails(body); showDialog('#info-dialog'); return;} if (!state.calculation) {body.append(node('p', 'Select a source and allow the calculation to complete.'));} else {const r = state.calculation; const list = node('dl'); const fields = [['Source', state.source], ['Checkpoint', state.checkpoint], ['Quantity model', modelNames[$('#position-model').value]], ['Fallback DTE', `${r.request.fallback_dte} days`], ['Risk-free rate', `${(r.request.risk_free_rate * 100).toFixed(2)}%`], ['Result identity', r.result_sha256 || 'Unavailable']]; for (const [name, value] of fields) list.append(node('dt', name), node('dd', String(value))); body.append(list);
      body.append(node('h3', 'Pricing assumptions'));
      const assumptions = [r.baseline?.pricing_assumptions, r.scenario?.pricing_assumptions].filter(Boolean);
      if (!assumptions.length) body.append(node('p', 'Pricing assumptions unavailable. European-exercise formulas; early exercise is not modeled.'));
      const seenAssumptions = new Set();
      for (const assumption of assumptions) {
        for (const copy of [assumption.summary, ...(assumption.limitations || []), assumption.rate_note, assumption.time_note].filter(Boolean)) {
          if (!seenAssumptions.has(copy)) {body.append(node('p', copy)); seenAssumptions.add(copy);}
        }
      }
      appendPricingCoverageDetails(body, r);
      body.append(node('h3', 'Calculation provenance'), node('pre', JSON.stringify({source: r.source, terminal_provenance: checkpointMetadata(state.terminalCheckpoint).source || source?.provenance, checkpoint: r.checkpoint, counts: r.scenario?.counts, reasons: r.scenario?.reason, calculation_fingerprint: r.calculation_fingerprint}, null, 2))); if (r.scenario?.contracts) {const details = node('details'); details.append(node('summary', 'Inspect contributing contract records'), node('pre', JSON.stringify(r.scenario.contracts, null, 2))); body.append(details);}} showDialog('#info-dialog');}
  async function listReceipts() {showDialog('#receipts-dialog'); const list = $('#receipts-list'); list.replaceChildren(node('p', 'Loading local receipts…')); try {const result = await api('receipts'); list.replaceChildren(); if (!result.receipts?.length) {list.append(node('p', 'No saved scenarios yet. Recalculate a scenario, then choose Save scenario.')); return;} for (const receipt of result.receipts) {const row = node('div', undefined, 'receipt-item'); const meta = node('div'); meta.append(node('h3', receipt.name), node('p', `${receipt.kind} · ${receipt.created_at}`)); const actions = node('div', undefined, 'receipt-actions'); const reopen = node('button', 'Reopen'); reopen.type = 'button'; reopen.addEventListener('click', () => reopenReceipt(receipt.id, reopen)); const download = node('button', 'Export JSON'); download.type = 'button'; download.addEventListener('click', () => exportReceipt(receipt.id, download)); actions.append(reopen, download); row.append(meta, actions); list.append(row);}} catch (error) {list.replaceChildren(node('p', error.message, 'validation-message'));}}
  async function exportReceipt(id, button) {button.disabled = true; try {const blob = await api(`receipts/${encodeURIComponent(id)}/export`, {blob: true}); const url = URL.createObjectURL(blob); const link = node('a'); link.href = url; link.download = `gex-wind-tunnel-${id.slice(0, 12)}.json`; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); toast('Portable receipt exported.');} catch (error) {toast(error.message);} finally {button.disabled = false;}}
  async function reopenRequest(kind, request, reproduced = null) {
    if (kind === 'search' && (request.x_axis !== 'spot_shift' || request.y_axis !== 'iv_shift')) throw new Error('This receipt is valid, but its axes are not the price/IV map supported by this view. Use the CLI to inspect that search.');
    if (request.session === terminalSession && request.terminal_checkpoint) registerTerminalSource(request.terminal_checkpoint);
    populateScenario(request); const opened = await loadSource(request.session, request.checkpoint, true, kind === 'models');
    if (!opened || opened.sourceRevision !== state.sourceRevision || opened.calculationRevision !== state.revision || state.source !== request.session) throw new Error('Source or assumptions changed while opening the receipt. Its saved result was not applied.');
    if (kind !== 'models' && !state.calculation) throw new Error('The saved calculation could not be opened. Its receipt is unchanged.');
    if (kind === 'search') {
      $('#claim').value = request.claim; $('#comparison-model').value = request.comparison_model || 'open_interest'; $('#comparison-model-control').hidden = $('#claim').value !== 'model_disagreement';
      const xs = request.x_values, ys = request.y_values;
      $('#search-price').value = Math.max(...xs.map(Math.abs)); $('#search-iv').value = Math.max(...ys.map(Math.abs));
      state.loadedSearchGrid = {x: [...xs], y: [...ys]}; $('#search-samples option[value=loaded]')?.remove(); const loadedOption = node('option', `Loaded · ${xs.length} × ${ys.length} = ${xs.length * ys.length} cases`); loadedOption.value = 'loaded'; $('#search-samples').append(loadedOption); $('#search-samples').value = 'loaded'; text('#loaded-grid-note', `Exact loaded grid: ${xs.length} × ${ys.length} = ${xs.length * ys.length} tested points. Editing bounds creates a new symmetric grid.`); $('#loaded-grid-note').hidden = false;
      text('#bounds-summary', `±${$('#search-price').value} pts · ±${$('#search-iv').value} vol pts`);
      await runSearch(request);
    } else if (kind === 'models') {
      if (reproduced) {state.models = reproduced; state.modelsRequest = {...request, detail_level: 'full'};} else {await calculateModels(Boolean(request.grid), request, opened.calculationRevision);} if (opened.sourceRevision !== state.sourceRevision || opened.calculationRevision !== state.revision) throw new Error('Source or assumptions changed while opening the receipt. Its saved result was not applied.'); setView('models');
    } else {
      if (kind === 'surface') {state.surface = reproduced || await post('surface', request); state.surfaceRequest = request;}
      setView(kind === 'surface' ? 'landscape' : 'compare');
    }
  }
  async function reopenReceipt(id, button) {button.disabled = true; try {const rawReceipt = await api(`receipts/${encodeURIComponent(id)}`, {text: true}); const receipt = JSON.parse(rawReceipt); const verified = await api('reproduce', {method: 'POST', rawBody: rawReceipt}); if (verified.status !== 'verified') throw new Error('Saved receipt did not reproduce exactly. Its original record is preserved.'); await reopenRequest(receipt.kind, verified.result?.request || receipt.request, verified.result); $('#receipts-dialog').close(); toast('Saved scenario verified and reopened.');} catch (error) {toast(error.message);} finally {button.disabled = false;}}
  async function importReceipt(event) {
    const file = event.target.files[0]; if (!file) return;
    text('#import-status', 'Verifying the receipt and reproducing its calculation…'); event.target.disabled = true;
    try {
      if (file.size > maxReceiptBytes) throw new Error('Receipt must be a JSON file no larger than 32 MiB.');
      const rawReceipt = await file.text(); let receipt; try {receipt = JSON.parse(rawReceipt);} catch (_) {throw new Error('This file is not a valid JSON receipt.');}
      const result = await api('reproduce', {method: 'POST', rawBody: rawReceipt}); if (result.status !== 'verified') throw new Error('Receipt did not reproduce exactly. The original file was not changed.');
      await reopenRequest(receipt.kind, result.result?.request || receipt.request, result.result); $('#receipts-dialog').close(); toast('Imported receipt verified and reopened. Save scenario to keep a local copy.'); text('#import-status', 'Verified and reopened.');
    } catch (error) {text('#import-status', error.message);}
    finally {event.target.disabled = false; event.target.value = '';}
  }
  async function showExamples() {
    text('#info-title', 'Try a synthetic research example'); const body = $('#info-content'); body.replaceChildren(node('p', 'Each example uses bundled inputs and real calculations. Outcomes describe only its tested grid.')); showDialog('#info-dialog');
    try {const response = await api('examples'); for (const example of response.examples || []) {const section = node('section', undefined, 'example-item'); section.append(node('h3', example.title), node('p', example.description)); const button = node('button', 'Open example', 'secondary-button'); button.type = 'button'; button.addEventListener('click', async () => {button.disabled = true; try {await reopenRequest(example.operation, example.request); $('#info-dialog').close(); toast(`${example.title} loaded.`);} catch (error) {toast(error.message);} finally {button.disabled = false;}}); section.append(button); body.append(section);}} catch (error) {body.append(node('p', error.message, 'validation-message'));}
  }
  async function saveReceipt(event) {event.preventDefault(); const name = $('#scenario-name').value.trim(); if (!name) return; const kind = state.view === 'models' && state.models ? 'models' : state.view === 'fragility' && state.search ? 'search' : state.view === 'landscape' && state.surface ? 'surface' : 'calculate'; const request = kind === 'models' ? state.modelsRequest || state.models.request : kind === 'search' ? state.search.request : kind === 'surface' ? state.surface.request || state.surfaceRequest : state.calculation.request; state.saving = true; toggleBusy(); $('#save-error').hidden = true; try {await post('receipts', {name, kind, request}); $('#save-dialog').close(); toast('Scenario saved locally. Open Saved scenarios to reopen or export it.');} catch (error) {text('#save-error', error.message); $('#save-error').hidden = false;} finally {state.saving = false; toggleBusy();}}
  function bindEvents() {
    $('#open-session').addEventListener('click', showIntake); $('#session-file').addEventListener('change', changeIntakeFile); $('#intake-rights').addEventListener('change', () => {if (!$('#intake-rights').checked) {discardIntake(); text('#intake-status', 'Permission check cleared. Verify again before opening this file.');} toggleIntake();}); $('#verify-session').addEventListener('click', verifySession); $('#open-intake-checkpoint').addEventListener('click', openIntakeCheckpoint); $('#cancel-intake').addEventListener('click', () => {discardIntake(); $('#intake-dialog').close();}); $('#intake-dialog').addEventListener('cancel', discardIntake); $('#intake-dialog').addEventListener('close', discardIntake);
    $('#source').addEventListener('change', event => loadSource(event.target.value));
    for (const [range, number] of [['#spot-shift', '#spot-number'], ['#iv-shift', '#iv-number'], ['#time-advance', '#time-number']]) {$(range).addEventListener('input', () => {$(number).value = $(range).value; scheduleCalculation();}); $(number).addEventListener('input', () => {if ($(number).checkValidity() && $(number).value !== '') $(range).value = $(number).value; scheduleCalculation();});}
    $('#position-model').addEventListener('change', scheduleCalculation); $('#remove-expiry').addEventListener('change', scheduleCalculation); $('#scenario-form').addEventListener('submit', event => event.preventDefault());
    $('#reset-scenario').addEventListener('click', () => {populateScenario({...emptyScenario, ...(isTerminalSource() ? currentSource()?.defaults : state.bundledDefaults), session: state.source}); scheduleCalculation();});
    $('#checkpoint').addEventListener('input', event => {stopPlayback(); clearSearch(); clearModels(); setCheckpoint(Number(event.target.value)); state.revision++; state.controller?.abort(); state.calculation = null; clearLandscape(); renderPricingAssumptions(null); state.busy = true; toggleBusy(); status('Checkpoint changed · recalculating…'); clearTimeout(calculateTimer); calculateTimer = setTimeout(calculate, 160);});
    for (const selector of ['#compare-strike-range', '#models-strike-range']) $(selector).addEventListener('change', event => {state.strikeRange = event.target.value === 'full' ? 'full' : 'focused'; $('#compare-strike-range').value = state.strikeRange; $('#models-strike-range').value = state.strikeRange; renderCompare(); if (state.models) renderModelPlots(state.models.models || []);});
    $('#run-model-grid').addEventListener('click', () => calculateModels(true)); $$('[data-model-preset]').forEach(button => button.addEventListener('click', () => applyModelPreset(button.dataset.modelPreset)));
    $('#play-replay').addEventListener('click', playReplay); $('#landscape-render').addEventListener('change', () => renderLandscape().catch(chartError));
    $$('.tabs button').forEach(tab => {tab.addEventListener('click', () => setView(tab.dataset.view)); tab.addEventListener('keydown', event => {const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End']; if (!keys.includes(event.key)) return; event.preventDefault(); const tabs = $$('.tabs button'); let index = tabs.indexOf(tab); index = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length; setView(tabs[index].dataset.view, true);});});
    $('#claim').addEventListener('change', () => {$('#comparison-model-control').hidden = $('#claim').value !== 'model_disagreement'; clearSearch();}); $('#comparison-model').addEventListener('change', clearSearch);
    ['#search-price', '#search-iv', '#search-samples'].forEach(selector => $(selector).addEventListener('change', () => {if ($('#search-samples').value === 'loaded') $('#search-samples').value = '11'; state.loadedSearchGrid = null; $('#search-samples option[value=loaded]')?.remove(); $('#loaded-grid-note').hidden = true; text('#bounds-summary', `±${$('#search-price').value} pts · ±${$('#search-iv').value} vol pts`); clearSearch();}));
    $('#run-search').addEventListener('click', () => runSearch()); $('#apply-breaking-case').addEventListener('click', () => {const request = smallestRequest(); if (!request) return; populateScenario(request); clearSearch(); setView('compare'); calculate();});
    $('#open-help').addEventListener('click', showHelp); $('#open-examples').addEventListener('click', showExamples); $('#receipt-file').addEventListener('change', importReceipt); $('#source-details').addEventListener('click', showSource); $('#open-receipts').addEventListener('click', listReceipts);
    $('#save-scenario').addEventListener('click', () => {$('#scenario-name').value = `${state.source} · ${state.view}`; $('#save-error').hidden = true; showDialog('#save-dialog'); $('#scenario-name').focus(); $('#scenario-name').select();}); $('#save-form').addEventListener('submit', saveReceipt);
    $$('[data-close]').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
    document.addEventListener('keydown', event => {if (event.key === '?' && !['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement.tagName) && !$('dialog[open]')) {event.preventDefault(); showHelp();}});
    let resizeTimer; window.addEventListener('resize', () => {clearTimeout(resizeTimer); resizeTimer = setTimeout(() => {if (window.Plotly) $$('.plot').filter(element => element.data && element.offsetParent).forEach(element => Plotly.Plots.resize(element));}, 150);});
  }
  async function initialize() {bindEvents(); emptyPlot('#landscape-plot', 'Preparing the research workspace…', 'Loading local research inputs.'); if (!state.capability) {const message = 'This window needs its local launch link. Start Wind Tunnel again to open a fresh session; no data has been sent.'; text('#connection-error', message); $('#connection-error').hidden = false; status('Launch link required', true); emptyPlot('#landscape-plot', 'Open from your local Wind Tunnel launcher.', 'The local session key is kept only in this browser tab. Open a fresh launch link if the tab or server session has ended.'); return;}
    try {const catalog = await api('catalog'); state.sources = catalog.sessions || catalog.sources || []; for (const saved of catalog.saved_checkpoints || []) {if (!saved.artifact || state.sources.some(source => source.terminal_checkpoint === saved.artifact)) continue; const source = terminalSourceFromArtifact(saved.artifact); source.name = `saved-checkpoint-${saved.checkpoint_sha256}`; source.label = saved.label || `Saved ${saved.symbol || 'market'} checkpoint`; state.sources.push(source);} state.bundledDefaults = catalog.bundled_defaults || catalog.defaults || emptyScenario; const select = $('#source'); select.replaceChildren(); for (const source of state.sources) {const option = node('option', source.title || source.label || source.name); option.value = source.name || source.id || source.session; option.disabled = source.status !== 'available'; if (option.disabled) option.textContent += ' · unavailable'; select.append(option);} const preferred = state.sources.find(item => sourceName(item) === catalog.defaults?.session && item.status === 'available') || state.sources.find(item => (item.name || item.id) === 'wind-tunnel-lab' && item.status === 'available') || state.sources.find(item => item.status === 'available'); if (!preferred) throw new Error('No supported local research sources are installed.'); select.disabled = false; await loadSource(sourceName(preferred), catalog.defaults?.checkpoint);}
    catch (error) {text('#connection-error', error.message); $('#connection-error').hidden = false; status('Local service unavailable', true); emptyPlot('#landscape-plot', 'Could not load the research workspace.', error.message);}
  }
  initialize();
})();

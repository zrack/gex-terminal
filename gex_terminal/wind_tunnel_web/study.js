(() => {
  'use strict';

  const $ = selector => document.querySelector(selector);
  const storageKey = `gex.wind-tunnel.study.capability:${location.origin}`;
  const launchCapability = new URLSearchParams(location.hash.slice(1)).get('cap');
  let capability = launchCapability;
  try {
    if (launchCapability) sessionStorage.setItem(storageKey, launchCapability);
    else capability = sessionStorage.getItem(storageKey);
  } catch (_) { /* The launch link also works without browser storage. */ }
  if (launchCapability) history.replaceState(null, '', location.pathname + location.search);

  const app = {sources: [], selected: null, explicitPair: false, comparing: false, receiptBusy: false,
    comparisonReceipt: null, comparisonChecked: false, comparisonRequest: null};
  const views = new Map();
  const drafts = new Map();
  const selectedCases = new Map();
  const pendingStudies = new Map();
  const receiptMessages = new Map();
  let receiptRequest;
  const sign = value => ({'-1': 'Negative', 0: 'Zero', 1: 'Positive'})[value] || 'Unavailable';
  const prediction = value => ({holds: 'Holds', changes: 'Changes'})[value] || '—';
  const time = value => value ? String(value).replace('T', ' ').replace(/(?:Z|\+00:00)$/, ' UTC') : 'Unavailable';
  const number = (value, digits = 2) => Number.isFinite(value)
    ? value.toLocaleString(undefined, {maximumFractionDigits: digits}) : '—';

  function element(tag, content, className) {
    const node = document.createElement(tag);
    if (content !== undefined) node.textContent = content;
    if (className) node.className = className;
    return node;
  }

  function message(target, content, failed = false) {
    target.textContent = content;
    target.classList.toggle('error', failed);
  }

  function status(target, content, failed = false) {
    target.hidden = !content;
    message(target, content, failed);
  }

  async function api(path = '', options = {}) {
    if (!capability) throw new Error('Open the study launch link from your terminal.');
    const {study, body, signal, download} = options;
    const selection = study ? `?${app.explicitPair ? 'slot' : 'symbol'}=${encodeURIComponent(study.id)}` : '';
    const request = {headers: {'X-GEX-Capability': capability}, signal};
    if (body !== undefined) {
      request.method = 'POST';
      request.headers['Content-Type'] = 'application/json';
      request.body = JSON.stringify(body);
    }
    const response = await fetch(`/api/blind-study${path}${selection}`, request);
    if (response.status === 403) {
      capability = null;
      try {sessionStorage.removeItem(storageKey);} catch (_) { /* Browser storage can be disabled. */ }
      updateControls();
      throw new Error('This local study link expired. Open a fresh study launch link.');
    }
    if (!response.ok) {
      let explanation = `Local study service returned ${response.status}.`;
      try {explanation = (await response.json()).error?.message || explanation;} catch (_) { /* Use HTTP status. */ }
      throw new Error(explanation);
    }
    return download ? response.blob() : response.json();
  }

  function side(value) {
    return ({C: 'call', P: 'put'})[value] || value || '';
  }

  function checkpoint(label, frame, reason) {
    const card = element('div', undefined, 'investigation-snapshot');
    card.append(element('h4', label));
    if (!frame) {
      card.append(element('strong', 'Unavailable', 'investigation-net'));
      if (reason) card.append(element('p', reason));
      return card;
    }
    const stamp = element('time', time(frame.as_of));
    stamp.dateTime = frame.as_of;
    const summary = frame.summary || {};
    card.append(stamp, element('span', 'NET-GEX SIGN', 'metric-label'),
      element('strong', sign(summary.net_sign), 'investigation-net'),
      element('p', `Net GEX ${number(summary.total_net_gex)}`),
      element('p', `Futures price ${number(frame.spot)}`));
    return card;
  }

  function renderEvidence(destination, flip) {
    if (!flip) {
      destination.replaceChildren();
      return;
    }
    const card = $('#study-evidence-template').content.firstElementChild.cloneNode(true);
    const {event, before, after, counterfactual, contributions} = flip;
    const driver = event.type === 'underlying_tick' ? `Futures price updates to ${number(event.price)}`
      : Number.isFinite(event.strike) ? `${number(event.strike)} ${side(event.option_type)} option update`
        : (event.type || 'Driving update').replaceAll('_', ' ');
    card.querySelector('.investigation-summary').textContent = `Event ${number(event.sequence, 0)} · ${driver}`;
    card.querySelector('.investigation-snapshots').append(
      checkpoint('Before update', before), checkpoint('At the flip', after),
      checkpoint('Without driving update', counterfactual, flip.counterfactual_reason));
    const table = card.querySelector('tbody');
    for (const contract of contributions || []) {
      const row = element('tr');
      const driving = contract.contract_id === event.contract_id && (!event.provider || contract.provider === event.provider);
      const heading = element('th', `${number(contract.strike)} ${side(contract.option_type)}`,
        driving ? 'investigation-trigger' : undefined);
      heading.scope = 'row';
      if (driving) heading.append(element('span', ' · updated'));
      const identity = [contract.expiry_timestamp ? time(contract.expiry_timestamp) : contract.expiry,
        contract.provider, contract.contract_id].filter(Boolean).join(' · ');
      if (identity) heading.append(element('small', identity, 'investigation-contract-identity'));
      row.append(heading, element('td', `${number(contract.before_quantity)} → ${number(contract.after_quantity)}`),
        element('td', number(contract.delta_gex)),
        element('td', contract.counterfactual_status === 'unpriced' ? 'Unpriced' : number(contract.counterfactual_gex)));
      table.append(row);
    }
    if (!table.children.length) {
      const row = element('tr');
      const cell = element('td', 'No changed contract contributions are available.');
      cell.colSpan = 4;
      row.append(cell);
      table.append(row);
    }
    destination.replaceChildren(card);
  }

  function caseBinding(item) {
    const cutoff = item.flip?.after?.as_of;
    const checksum = item.capture_sha256 || item.flip?.source?.capture_sha256 || item.flip?.request?.capture_sha256;
    const shortHash = /^[a-f0-9]{64}$/i.test(checksum) ? checksum.slice(0, 12) : null;
    return [cutoff && time(cutoff), shortHash].filter(Boolean).join(' · ');
  }

  function caseContext(view, item) {
    const binding = caseBinding(item);
    if (!binding) return '';
    const symbol = item.flip?.source?.symbol || view.protocol?.symbol;
    return [symbol, binding].filter(Boolean).join(' · ');
  }

  function unansweredCases(view) {
    return view.cases.filter(item => item.status === 'ready' && !view.calls.get(item.id)?.prediction);
  }

  function renderQueue(view) {
    const {$} = view;
    const list = $('#study-cases');
    const rows = document.createDocumentFragment();
    for (const item of view.cases) {
      const button = element('button');
      button.type = 'button';
      if (item.id === view.selected) button.setAttribute('aria-current', 'true');
      const call = view.calls.get(item.id);
      const choice = call?.prediction
        ? `${view.stage === 'blind' ? 'Recorded' : 'Locked'} · ${prediction(call.prediction)}` : 'Awaiting call';
      button.append(element('span', item.label));
      if (view.protocol?.source === 'saved_capture') {
        const binding = caseBinding(item);
        if (binding) button.append(element('small', binding, 'study-case-binding'));
      }
      button.append(element('small', item.status === 'no_flip' ? 'No eligible flip' : choice));
      button.addEventListener('click', () => showCase(view, item.id, true));
      const row = element('li');
      row.append(button);
      rows.append(row);
    }
    list.replaceChildren(rows);
  }

  function showCase(view, id, focus = false) {
    const {$} = view;
    const item = view.cases.find(caseItem => caseItem.id === id);
    if (!item) return;
    view.selected = id;
    selectedCases.set(view.id, id);
    $('#study-case-title').textContent = item.label;
    $('#study-case-context').textContent = caseContext(view, item);
    $('#study-no-flip').hidden = item.status !== 'no_flip';
    $('#study-call-panel').hidden = item.status !== 'ready';
    renderEvidence($('#study-cutoff'), item.flip);
    const call = view.calls.get(id) || {};
    for (const input of $('#study-forecast').querySelectorAll('input')) input.checked = input.value === call.prediction;
    $('#study-read').value = call.read || '';
    renderQueue(view);
    updateControls();
    if (focus) $('#study-case-title').focus();
  }

  function renderDraft(view, data) {
    const {$} = view;
    renderProtocol(view, data.protocol);
    view.stage = data.stage;
    view.cases = data.cases;
    view.result = null;
    view.receipt = null;
    if (data.calls) view.calls = new Map(Object.entries(data.calls));
    if (data.stage === 'committed') drafts.delete(view.id);
    $('#study-workspace').hidden = false;
    $('#study-results').hidden = true;
    $('#study-stage').hidden = false;
    $('#study-stage').classList.remove('revealed');
    $('#study-stage').textContent = ({blind: 'Before reveal', committed: 'Calls locked', pending: 'Checking commitment'})[view.stage];
    const selected = view.cases.find(item => item.id === view.selected)
      || view.cases.find(item => item.status === 'ready') || view.cases[0];
    if (selected) showCase(view, selected.id);
    else updateControls();
  }

  function accuracy(count, scored) {
    return scored ? `${number(count / scored * 100, 1)}%` : '—';
  }

  function rating(item) {
    if (item.status === 'no_flip') return 'No eligible flip';
    if (item.status === 'unscored') return 'Unscored';
    return item.correct ? 'Correct' : 'Miss';
  }

  function studyTitle(view) {
    if (app.explicitPair) return `Study ${view.id.toUpperCase()} · ${view.symbol}`;
    if (view.protocol?.source === 'saved_capture') return view.protocol.title;
    return app.sources.length === 2 ? `Saved ${view.symbol} Blind Replay Study` : 'Blind Replay Study';
  }

  function renderProtocol(view, protocol) {
    const {$} = view;
    if (!protocol) return;
    if (protocol.symbol !== view.symbol) throw new Error('The study did not match the selected market.');
    view.protocol = protocol;
    const saved = protocol.source === 'saved_capture';
    $('#study-pane-title').textContent = studyTitle(view);
    updateTitle();
    const target = $('#study-protocol');
    const source = saved ? `Saved ${protocol.symbol} captures` : `Synthetic ${protocol.symbol} cohort`;
    target.textContent = `${source} · ${protocol.horizon_minutes}-minute horizon`;
    target.hidden = false;
  }

  function verifyResult(view, result) {
    if (!Array.isArray(result?.cases) || !result.summary || !result.protocol) {
      throw new Error('The study result is incomplete.');
    }
    if (result.protocol.symbol !== view.symbol) throw new Error('The study did not match the selected market.');
    const boundCases = view.result?.cases || view.cases;
    if (app.explicitPair && boundCases.length) {
      const captures = new Set(result.cases.map(item => item.capture_sha256));
      if (captures.size !== boundCases.length || !boundCases.every(item => captures.has(item.capture_sha256))) {
        throw new Error('The study result belongs to a different set of captures.');
      }
    }
  }

  function renderResults(view, result, receipt = null, focus = true) {
    verifyResult(view, result);
    const {$} = view;
    renderProtocol(view, result.protocol);
    const {total, scored, correct, baseline_correct: baseline, unscored, no_flip: noFlip} = result.summary;
    view.stage = 'revealed';
    view.result = result;
    view.receipt = receipt;
    view.calls = new Map();
    drafts.delete(view.id);
    $('#study-workspace').hidden = true;
    $('#study-stage').hidden = false;
    $('#study-stage').classList.add('revealed');
    $('#study-stage').textContent = 'Outcomes revealed';
    $('#study-results').hidden = false;
    clearDrilldown(view);
    $('#study-result-coverage').textContent = `${scored} scored of ${total} · ${unscored} unscored · ${noFlip} no eligible flip`;
    $('#study-accuracy').textContent = accuracy(correct, scored);
    $('#study-baseline').textContent = accuracy(baseline, scored);
    $('#study-accuracy-count').textContent = `${correct} of ${scored} scored cases`;
    $('#study-baseline-count').textContent = `${baseline} of ${scored} scored cases`;
    $('#study-results-note').textContent = 'The baseline calls Holds on every scored case. Both scores use the same cases. Unscored cases lack a usable 30-minute sign. Sessions without an eligible flip require no call.';
    const rows = document.createDocumentFragment();
    for (const item of result.cases) {
      const row = element('tr');
      const label = element('th', item.label);
      label.scope = 'row';
      if (view.protocol?.source === 'saved_capture') {
        const binding = caseBinding(item);
        if (binding) label.append(element('small', binding, 'study-case-binding'));
      }
      const score = element('td', rating(item), item.status === 'scored'
        ? (item.correct ? 'study-correct' : 'study-missed') : undefined);
      const evidence = element('td');
      if (item.flip) {
        const button = element('button', item.status === 'scored' && item.correct === false ? 'Inspect miss' : 'Inspect case');
        button.type = 'button';
        button.setAttribute('aria-label', `${button.textContent} · ${item.label}`);
        button.addEventListener('click', () => showDrilldown(view, item));
        evidence.append(button);
      } else evidence.textContent = '—';
      row.append(label, element('td', prediction(item.call?.prediction)), element('td', prediction(item.actual)), score, evidence);
      rows.append(row);
    }
    $('#study-result-cases').replaceChildren(rows);
    individualReceiptStatus(view, receiptMessages.get(view.receipt) || '');
    updateControls();
    if (focus && !app.comparing) $('#study-results-title').focus();
  }

  function clearOutcome(view) {
    const {$} = view;
    for (const selector of ['#study-outcome-signs', '#study-horizon', '#study-horizon-note', '#study-price-caption',
      '#study-price-rows']) $(selector).replaceChildren();
    $('#study-price-details').open = false;
    $('#study-price-details').hidden = true;
    $('#study-outcome').hidden = true;
    const old = $('#study-plot');
    const plot = element('div', undefined, 'plot blind-price-plot');
    plot.id = old.id;
    plot.setAttribute('role', 'img');
    plot.hidden = true;
    old.replaceWith(plot);
    if (window.Plotly && old.data) window.Plotly.purge(old);
    return plot;
  }

  function clearDrilldown(view) {
    const {$} = view;
    $('#study-drilldown').hidden = true;
    for (const selector of ['#study-drilldown-title', '#study-drilldown-context', '#study-committed-read',
      '#study-drilldown-cutoff']) $(selector).replaceChildren();
    clearOutcome(view);
  }

  function renderOutcome(view, item) {
    const {$} = view;
    const plot = clearOutcome(view);
    const outcome = item.outcome;
    if (!outcome) return;
    $('#study-outcome').hidden = false;
    const metrics = [
      ['NET-GEX SIGN AT FLIP', sign(item.flip.after.summary?.net_sign)],
      ['NET-GEX SIGN AT 30 MIN', sign(outcome.summary?.net_sign)],
      ['YOUR CALL', prediction(item.call?.prediction)],
    ];
    $('#study-outcome-signs').replaceChildren(...metrics.map(([label, value]) => {
      const metric = element('div');
      metric.append(element('span', label, 'metric-label'), element('strong', value, 'investigation-net'));
      return metric;
    }));
    const last = outcome.as_of && outcome.as_of !== outcome.target_as_of ? ` · Last accepted state ${time(outcome.as_of)}` : '';
    $('#study-horizon').textContent = `Requested cutoff ${time(outcome.target_as_of)}${last}`;
    $('#study-horizon-note').hidden = !outcome.reason;
    $('#study-horizon-note').textContent = outcome.reason || '';
    const points = outcome.price_path || [];
    const rows = document.createDocumentFragment();
    const labels = points.map((_, index) => index === 0 ? 'Price known at the flip' : 'Observed update');
    for (const [index, point] of points.entries()) {
      const row = element('tr');
      row.append(element('td', time(point.as_of)), element('td', number(point.price)), element('td', labels[index]));
      rows.append(row);
    }
    $('#study-price-rows').replaceChildren(rows);
    $('#study-price-details').hidden = !points.length;
    const coverage = outcome.coverage || {};
    const samples = Number.isFinite(coverage.observed_price_count)
      ? ` Observed updates ${number(coverage.observed_price_count, 0)}.` : '';
    const sampling = coverage.price_sampling === 'observed_minute_extrema' ? ' Showing recorded minute extrema.' : '';
    $('#study-price-caption').textContent = points.length
      ? `Starts with the price known at the flip. Last displayed price ${number(points.at(-1).price)}.${samples}${sampling}`
      : 'No futures price values are available for this horizon.';
    if (!points.length || !window.Plotly) return;
    const symbol = item.flip.source?.symbol || 'Futures';
    plot.hidden = false;
    const study = app.explicitPair ? ` in Study ${view.id.toUpperCase()}` : '';
    plot.setAttribute('aria-label', `Observed ${symbol} futures prices for ${item.label}${study} through the 30-minute horizon`);
    const traces = [{type: 'scatter', mode: 'markers', x: points.map(point => point.as_of),
      y: points.map(point => point.price), text: labels,
      marker: {color: points.map((_, index) => index ? '#37cee9' : '#ffbd35'), size: points.length > 350 ? 3 : 6},
      hovertemplate: '%{text}<br>%{x|%H:%M:%S} UTC<br>%{y:,.2f}<extra></extra>'}];
    const axis = {gridcolor: '#253849', linecolor: '#40546b', fixedrange: true, automargin: true};
    const xaxis = {...axis, type: 'date', tickformat: '%H:%M', title: {text: 'UTC'}};
    if (item.flip.after.as_of && outcome.target_as_of) xaxis.range = [item.flip.after.as_of, outcome.target_as_of];
    const layout = {paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', showlegend: false,
      margin: {l: 55, r: 15, t: 15, b: 45}, font: {color: '#a2b5ce', size: 11}, xaxis,
      yaxis: {...axis, tickformat: ',.2f', title: {text: `${symbol} price`}}};
    window.Plotly.react(plot, traces, layout, {responsive: true, displayModeBar: false}).then(
      () => {if (!plot.isConnected && plot.data) window.Plotly.purge(plot);},
      () => {plot.hidden = true;});
  }

  function showDrilldown(view, item) {
    const {$} = view;
    const study = app.explicitPair ? `Study ${view.id.toUpperCase()} · ` : '';
    $('#study-drilldown').hidden = false;
    $('#study-drilldown-title').textContent = `${study}${item.label} · ${rating(item)}`;
    $('#study-drilldown-context').textContent = caseContext(view, item);
    $('#study-committed-read').hidden = !item.call?.read;
    $('#study-committed-read').textContent = item.call?.read || '';
    renderEvidence($('#study-drilldown-cutoff'), item.flip);
    renderOutcome(view, item);
    $('#study-drilldown-title').focus();
  }

  async function submitStudy(view) {
    const {$} = view;
    if ($('#study-submit').disabled) return;
    const required = view.cases.filter(item => item.status === 'ready');
    const calls = Object.fromEntries(required.map(({id}) => {
      const {prediction, read} = view.calls.get(id);
      return [id, {prediction, ...(read?.trim() ? {read: read.trim()} : {})}];
    }));
    view.busy = true;
    updateControls();
    status($('#study-pane-status'), 'Locking the calls and replaying the 30-minute outcomes…');
    try {
      const {result} = await api('/submit', {study: view, body: {calls}});
      renderResults(view, result);
    } catch (error) {
      // A lost response can occur after the host has already locked the calls.
      // Reload the authoritative stage before allowing any edits.
      try {
        const current = await api('', {study: view});
        if (current.stage === 'revealed') {
          renderResults(view, current.result, current.receipt_sha256);
          return;
        }
        renderDraft(view, current);
      } catch (_) {
        renderDraft(view, {stage: 'pending', cases: view.cases, calls});
      }
      status($('#study-pane-status'), error.message, true);
    } finally {
      view.busy = false;
      updateControls();
    }
  }

  function studiesBusy() {
    return [...views.values()].some(view => view.busy);
  }

  function updateTitle() {
    const selected = views.get(app.selected);
    const title = app.comparing ? (app.explicitPair ? 'Compare saved studies' : 'Compare ES and NQ studies')
      : selected?.$('#study-pane-title').textContent || 'Blind Replay Study';
    $('#study-title').textContent = title;
    document.title = `GEX / ${title}`;
  }

  function updateControls() {
    const selected = views.get(app.selected);
    const blocked = app.receiptBusy || studiesBusy() || !capability;
    const marketPicker = app.sources.length === 2 && !app.explicitPair;
    const comparisonReady = app.comparing && views.size === 2 && [...views.values()].every(view => view.result);
    $('#study-source-picker').hidden = !marketPicker || app.comparing;
    $('#study-source-select').disabled = blocked;
    const toggle = $('#study-compare-toggle');
    toggle.hidden = !marketPicker;
    toggle.disabled = blocked;
    toggle.textContent = app.comparing ? 'Review one study' : 'Compare ES and NQ';

    $('#study-comparison-actions').hidden = !app.comparing;
    $('#study-save-comparison').hidden = !comparisonReady;
    $('#study-save-comparison').disabled = blocked || !comparisonReady || !app.comparisonChecked || Boolean(app.comparisonReceipt);
    $('#study-save-comparison span').textContent = app.comparisonReceipt ? 'Comparison saved' : 'Save comparison';
    $('#study-receipts').disabled = blocked || (app.comparing
      ? views.size !== 2 || [...views.values()].some(view => view.loading)
      : !selected?.stage);
    $('#study-receipts span').textContent = app.comparing ? 'Saved comparisons' : 'Saved studies';
    $('#study-save-confirm').disabled = blocked;

    for (const view of views.values()) {
      const {$, stage} = view;
      const locked = view.busy || app.receiptBusy || !capability;
      const ready = view.cases.filter(item => item.status === 'ready').length;
      const unanswered = unansweredCases(view).length;
      const drafting = stage === 'blind';
      const launchPending = stage === 'pending';
      const canResume = stage === 'committed' || launchPending;
      $('#study-forecast').disabled = locked || !drafting;
      $('#study-read').disabled = locked || !drafting;
      $('#study-submit').disabled = locked || (!canResume && (!drafting || unanswered > 0 || !view.cases.length));
      $('#study-submit').textContent = canResume ? 'Retry reveal' : 'Lock calls and reveal';
      $('#study-next').hidden = !drafting || !view.calls.get(view.selected)?.prediction || !unanswered;
      $('#study-next').disabled = locked;
      $('#study-progress').textContent = canResume
        ? (launchPending ? 'Checking the submitted calls.' : `${ready} calls locked.`)
        : `${ready - unanswered} of ${ready} calls recorded.`;
      $('#study-save').disabled = locked || !view.result || Boolean(view.receipt);
      $('#study-save').querySelector('span').textContent = view.receipt ? 'Study saved' : 'Save study';
      for (const node of $('#study-cases').querySelectorAll('button')) node.disabled = locked;
    }
  }

  function mountStudy({id, symbol}) {
    const root = $('#study-pane-template').content.firstElementChild.cloneNode(true);
    const suffix = `-${id.toLowerCase()}`;
    for (const node of root.querySelectorAll('[id]')) node.id += suffix;
    for (const attr of ['aria-labelledby', 'for']) {
      for (const node of root.querySelectorAll(`[${attr}]`)) node.setAttribute(attr, node.getAttribute(attr) + suffix);
    }
    for (const input of root.querySelectorAll('input[type="radio"]')) input.name += suffix;
    const find = selector => root.querySelector(selector + suffix);
    const calls = drafts.get(id) || new Map();
    drafts.set(id, calls);
    const view = {root, $: find, id, symbol, calls, stage: null, protocol: null, cases: [],
      selected: selectedCases.get(id) || null, result: null, receipt: null, busy: false, loading: true};
    root.setAttribute('aria-label', app.explicitPair ? studyTitle(view) : `${symbol} study`);
    find('#study-pane-title').textContent = studyTitle(view);
    status(find('#study-pane-status'), 'Opening study cases…');

    find('#study-forecast').addEventListener('change', event => {
      if (view.stage !== 'blind') return;
      const call = view.calls.get(view.selected);
      view.calls.set(view.selected, {...call, prediction: event.target.value});
      renderQueue(view);
      updateControls();
    });
    find('#study-read').addEventListener('input', event => {
      if (view.stage !== 'blind') return;
      const call = view.calls.get(view.selected);
      view.calls.set(view.selected, {...call, read: event.target.value});
    });
    find('#study-next').addEventListener('click', () => showCase(view, unansweredCases(view)[0]?.id, true));
    find('#study-submit').addEventListener('click', () => submitStudy(view));
    find('#study-save').addEventListener('click', () => openSave(view));
    return view;
  }

  async function loadStudy(view) {
    const {id, symbol, $} = view;
    if (!pendingStudies.has(id)) {
      pendingStudies.set(id, api('', {study: view}).finally(() => pendingStudies.delete(id)));
    }
    try {
      const data = await pendingStudies.get(id);
      if (views.get(id) !== view) return;
      if (data.protocol?.symbol !== symbol) throw new Error('The study did not match the selected market.');
      if (data.stage === 'revealed') renderResults(view, data.result, data.receipt_sha256, false);
      else {
        renderDraft(view, data);
        status($('#study-pane-status'), '');
      }
    } catch (error) {
      if (views.get(id) !== view) return;
      status($('#study-pane-status'), error.message, true);
    } finally {
      view.loading = false;
      updateControls();
    }
  }

  function showStudies() {
    const sources = app.comparing ? app.sources : app.sources.filter(source => source.id === app.selected);
    const container = $('#study-panes');
    container.classList.toggle('side-by-side', app.comparing);
    for (const [id, view] of views) {
      if (sources.some(source => source.id === id)) continue;
      const plot = view.$('#study-plot');
      if (window.Plotly && plot.data) window.Plotly.purge(plot);
      view.root.remove();
      views.delete(id);
    }
    sources.forEach((source, index) => {
      if (views.has(source.id)) return;
      const view = mountStudy(source);
      views.set(source.id, view);
      container.insertBefore(view.root, container.children[index] || null);
      loadStudy(view);
    });
    if (window.Plotly) requestAnimationFrame(() => {
      for (const view of views.values()) {
        const plot = view.$('#study-plot');
        if (plot.data) window.Plotly.Plots.resize(plot).catch(() => {});
      }
    });
    updateTitle();
    updateControls();
  }

  async function loadComparisonStatus() {
    app.comparisonChecked = false;
    app.comparisonReceipt = null;
    const target = $('#study-comparison-status');
    message(target, '');
    const request = new AbortController();
    app.comparisonRequest = request;
    try {
      const data = await api('/comparison', {signal: request.signal});
      if (request.signal.aborted) return;
      app.comparisonReceipt = data.receipt_sha256 || null;
      app.comparisonChecked = true;
      message(target, receiptMessages.get(app.comparisonReceipt) || '');
    } catch (error) {
      if (!request.signal.aborted) message(target, error.message, true);
    } finally {
      if (app.comparisonRequest === request) app.comparisonRequest = null;
      updateControls();
    }
  }

  function changeMode() {
    if (app.explicitPair || app.receiptBusy || studiesBusy()) return;
    closeReceiptDialogs();
    app.comparing = !app.comparing;
    if (app.comparing) loadComparisonStatus();
    else app.comparisonRequest?.abort();
    showStudies();
  }

  function receiptScope(view) {
    return view
      ? {view, path: '', type: 'study', list: 'Saved studies'}
      : {path: '/comparison', type: 'comparison', list: 'Saved comparisons'};
  }

  function currentReceipt(scope) {
    return scope.view ? scope.view.receipt : app.comparisonReceipt;
  }

  function individualReceiptStatus(view, content) {
    const target = view.$('#study-pane-status');
    target.classList.toggle('study-single-receipt', Boolean(content));
    status(target, content);
  }

  function recordReceipt(scope, id, content) {
    if (scope.view) {
      scope.view.receipt = id;
      individualReceiptStatus(scope.view, content);
    } else {
      app.comparisonRequest?.abort();
      app.comparisonReceipt = id;
      app.comparisonChecked = true;
      message($('#study-comparison-status'), content);
    }
    receiptMessages.set(id, content);
  }

  function closeReceiptDialogs() {
    receiptRequest?.abort();
    for (const selector of ['#study-save-dialog', '#study-receipts-dialog']) {
      const dialog = $(selector);
      if (dialog.open) dialog.close();
    }
    $('#study-receipt-list').replaceChildren();
    message($('#study-receipt-status'), '');
    $('#study-name').value = '';
    message($('#study-save-error'), '');
  }

  function openSave(view) {
    if (app.receiptBusy || studiesBusy()) return;
    if (view && (app.comparing || view.$('#study-save').disabled)) return;
    if (!view && (!app.comparing || $('#study-save-comparison').disabled)) return;
    const markets = [...new Set(app.sources.map(source => source.symbol))].join(' and ');
    const title = view?.$('#study-pane-title').textContent || `${markets} Blind Replay Study comparison`;
    $('#study-name').value = title;
    const type = view ? 'study' : 'comparison';
    $('#study-save-title').textContent = `Save ${type}`;
    $('#study-save-confirm').textContent = `Save ${type}`;
    $('#study-name-label').textContent = view ? 'Study name' : 'Comparison name';
    $('#study-save-error').hidden = true;
    $('#study-save-dialog').showModal();
    $('#study-name').select();
  }

  async function saveReceipt(event) {
    event.preventDefault();
    const name = $('#study-name').value.trim();
    const button = $('#study-save-confirm');
    if (!name || button.disabled) return;
    const scope = receiptScope(app.comparing ? null : views.get(app.selected));
    if (currentReceipt(scope)) return;
    app.receiptBusy = true;
    $('#study-save-error').hidden = true;
    updateControls();
    try {
      const receipt = await api(`${scope.path}/save`, {study: scope.view, body: {name}});
      $('#study-save-dialog').close();
      recordReceipt(scope, receipt.receipt_sha256, `Saved ${receipt.name}. Reopen or export it from ${scope.list}.`);
    } catch (error) {
      $('#study-save-error').hidden = false;
      message($('#study-save-error'), error.message, true);
    } finally {
      app.receiptBusy = false;
      updateControls();
    }
  }

  async function reopenReceipt(scope, id, button) {
    if (app.receiptBusy || studiesBusy()) return;
    app.receiptBusy = true;
    button.disabled = true;
    updateControls();
    message($('#study-receipt-status'), `Verifying the saved ${scope.type}…`);
    try {
      const receipt = await api(`${scope.path}/reopen`, {study: scope.view, body: {id}});
      if (scope.view) renderResults(scope.view, receipt.result, receipt.receipt_sha256, false);
      else {
        const sides = [...views.values()].map(view => ({view, result: receipt.result?.[view.id.toLowerCase()]}));
        for (const {view, result} of sides) verifyResult(view, result);
        for (const {view, result} of sides) {
          const individual = view.result?.request_sha256 === result.request_sha256 ? view.receipt : null;
          renderResults(view, result, individual, false);
        }
      }
      $('#study-receipts-dialog').close();
      recordReceipt(scope, receipt.receipt_sha256, `Verified and reopened ${receipt.name}.`);
      if (scope.view) scope.view.$('#study-results-title').focus();
      else $('#study-comparison-status').focus();
    } catch (error) {
      message($('#study-receipt-status'), error.message, true);
    } finally {
      app.receiptBusy = false;
      button.disabled = false;
      updateControls();
    }
  }

  async function exportReceipt(scope, id, button) {
    if (app.receiptBusy || studiesBusy() || id !== currentReceipt(scope)) return;
    app.receiptBusy = true;
    button.disabled = true;
    updateControls();
    try {
      const data = await api(`${scope.path}/receipts/${encodeURIComponent(id)}/export`, {study: scope.view, download: true});
      const url = URL.createObjectURL(data);
      const download = element('a');
      download.href = url;
      download.download = `gex-blind-${scope.type}-${id.slice(0, 12)}.json`;
      document.body.append(download);
      download.click();
      download.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      message($('#study-receipt-status'), 'Receipt exported.');
    } catch (error) {
      message($('#study-receipt-status'), error.message, true);
    } finally {
      app.receiptBusy = false;
      button.disabled = false;
      updateControls();
    }
  }

  async function openReceipts() {
    const dialog = $('#study-receipts-dialog');
    if (dialog.open || $('#study-receipts').disabled) return;
    const scope = receiptScope(app.comparing ? null : views.get(app.selected));
    receiptRequest?.abort();
    const request = new AbortController();
    receiptRequest = request;
    const list = $('#study-receipt-list');
    list.replaceChildren();
    $('#study-receipts-title').textContent = scope.list;
    dialog.showModal();
    message($('#study-receipt-status'), `Loading ${scope.list.toLowerCase()}…`);
    try {
      const {receipts} = await api(`${scope.path}/receipts`, {study: scope.view, signal: request.signal});
      if (request.signal.aborted || !dialog.open) return;
      message($('#study-receipt-status'), receipts.length
        ? `Reopen a ${scope.type} to verify its locked calls and outcomes.`
        : `No ${scope.list.toLowerCase()} yet.`);
      for (const receipt of receipts) {
        const item = element('div', undefined, 'receipt-item');
        const label = element('div');
        label.append(element('h3', receipt.name || `Saved ${scope.type}`), element('p', time(receipt.created_at)));
        const actions = element('div', undefined, 'receipt-actions');
        const reopen = element('button', 'Reopen');
        reopen.type = 'button';
        reopen.addEventListener('click', () => reopenReceipt(scope, receipt.id, reopen));
        actions.append(reopen);
        if (receipt.id === currentReceipt(scope)) {
          const download = element('button', 'Export JSON');
          download.type = 'button';
          download.addEventListener('click', () => exportReceipt(scope, receipt.id, download));
          actions.append(download);
        }
        item.append(label, actions);
        list.append(item);
      }
    } catch (error) {
      if (!request.signal.aborted && dialog.open) message($('#study-receipt-status'), error.message, true);
    } finally {
      if (receiptRequest === request) receiptRequest = null;
    }
  }

  async function initialize() {
    const picker = $('#study-source-select');
    picker.addEventListener('change', () => {
      if (app.receiptBusy || studiesBusy() || picker.value === app.selected) return;
      app.selected = picker.value;
      closeReceiptDialogs();
      showStudies();
    });
    $('#study-compare-toggle').addEventListener('click', changeMode);
    $('#study-save-comparison').addEventListener('click', () => openSave());
    $('#study-save-form').addEventListener('submit', saveReceipt);
    $('#study-receipts').addEventListener('click', openReceipts);
    $('#study-receipts-dialog').addEventListener('close', event => {
      if (!event.currentTarget.open) receiptRequest?.abort();
    });
    document.querySelectorAll('dialog [data-close]').forEach(button => {
      button.addEventListener('click', () => button.closest('dialog').close());
    });
    try {
      const {symbols, slots} = await api('/sources');
      if (!symbols?.length) throw new Error('There are no studies in this window.');
      app.explicitPair = Boolean(slots);
      app.sources = slots || symbols.map(symbol => ({id: symbol, symbol}));
      app.selected = app.sources[0].id;
      app.comparing = app.explicitPair;
      if (app.comparing) loadComparisonStatus();
      else {
        picker.replaceChildren(...symbols.map(symbol => element('option', symbol)));
        picker.value = app.selected;
      }
      document.body.classList.toggle('study-multiple', app.sources.length === 2);
      status($('#study-status'), '');
      showStudies();
    } catch (error) {
      status($('#study-status'), error.message, true);
      updateControls();
    }
  }

  initialize();
})();

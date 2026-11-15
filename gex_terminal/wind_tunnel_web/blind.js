(() => {
  'use strict';

  const $ = selector => document.querySelector(selector);
  const storageKey = `gex.wind-tunnel.blind.capability:${location.origin}`;
  const launchCapability = new URLSearchParams(location.hash.slice(1)).get('cap');
  let capability = launchCapability;
  try {
    if (launchCapability) sessionStorage.setItem(storageKey, launchCapability);
    else capability = sessionStorage.getItem(storageKey);
  } catch (_) { /* The launch link still works if session storage is unavailable. */ }
  if (launchCapability) history.replaceState(null, '', location.pathname + location.search);

  const app = {sessions: [], sameMarket: false, selected: null, comparing: false, receiptBusy: false,
    comparisonReceipt: null, comparisonChecked: false, comparisonRequest: null};
  const views = new Map();
  const drafts = new Map();
  const receiptMessages = new Map();
  const pendingReviews = new Map();
  let pendingReceipts = null;
  const number = (value, digits = 2) => Number.isFinite(value)
    ? value.toLocaleString(undefined, {maximumFractionDigits: digits}) : '—';

  function element(tag, content, className) {
    const el = document.createElement(tag);
    if (content !== undefined) el.textContent = content;
    if (className) el.className = className;
    return el;
  }

  function message(target, content, failed = false) {
    target.textContent = content;
    target.classList.toggle('error', failed);
  }

  function timeLabel(timestamp) {
    if (!timestamp) return 'Unavailable';
    return String(timestamp).replace('T', ' ').replace('Z', ' UTC');
  }

  function signLabel(sign) {
    return ({'-1': 'Negative', 0: 'Zero', 1: 'Positive'})[sign] || 'Unavailable';
  }

  async function api(path = '', {session, body, signal, responseType = 'json'} = {}) {
    if (!capability) throw new Error('Open the blind-review launch link from your terminal.');
    const url = `/api/blind-review${path}${session ? `?session=${encodeURIComponent(session)}` : ''}`;
    const request = {headers: {'X-GEX-Capability': capability}, signal};
    if (body !== undefined) {
      request.method = 'POST';
      request.headers['Content-Type'] = 'application/json';
      request.body = JSON.stringify(body);
    }
    const response = await fetch(url, request);
    if (response.status === 403) {
      capability = null;
      try {sessionStorage.removeItem(storageKey);} catch (_) { /* Storage can be disabled. */ }
      $('#blind-launch-status').hidden = false;
      const explanation = 'This local review link expired. Open a fresh blind-review launch link.';
      message($('#blind-launch-status'), explanation, true);
      throw new Error(explanation);
    }
    if (!response.ok) {
      let explanation = `Local review service returned ${response.status}.`;
      try {explanation = (await response.json()).error?.message || explanation;} catch (_) { /* Use the HTTP status. */ }
      throw new Error(explanation);
    }
    return responseType === 'blob' ? response.blob() : response.json();
  }

  function coverageText(coverage) {
    if (!coverage) return null;
    if (Number.isFinite(coverage.priced_contract_count) && Number.isFinite(coverage.selected_contract_count)) {
      return `Priced contracts ${number(coverage.priced_contract_count, 0)} of ${number(coverage.selected_contract_count, 0)}`;
    }
    return null;
  }

  function snapshot(label, value, reason) {
    const card = element('div', undefined, 'investigation-snapshot');
    card.append(element('h3', label));
    if (!value) {
      card.append(element('strong', 'Unavailable', 'investigation-net'));
      if (reason) card.append(element('p', reason));
      return card;
    }
    const time = element('time', timeLabel(value.as_of));
    time.dateTime = value.as_of;
    const summary = value.summary || {};
    card.append(time, element('span', 'NET-GEX SIGN', 'metric-label'),
      element('strong', signLabel(summary.net_sign), 'investigation-net'),
      element('p', `Net GEX ${number(summary.total_net_gex)}`),
      element('p', `Futures price ${number(value.spot)}`));
    const coverage = coverageText(value.pricing_coverage);
    if (coverage) card.append(element('p', coverage));
    return card;
  }

  function optionSide(type) {return ({C: 'call', P: 'put'})[type] || type || '';}

  function verifyFlip(view, flip) {
    const {symbol, checksum: boundChecksum} = view.session;
    const checksum = flip?.source?.capture_sha256;
    if (flip?.source?.symbol !== symbol || !checksum || flip.request?.capture_sha256 !== checksum
        || (boundChecksum && boundChecksum !== checksum)) {
      throw new Error('The saved flip did not match the selected session.');
    }
    return checksum;
  }

  function renderFlip(view, flip) {
    const {$} = view;
    const checksum = verifyFlip(view, flip);
    view.session.checksum = checksum;
    const {event, before, after, counterfactual, contributions} = flip;
    $('#blind-source').textContent = `Saved ${view.session.label} · ${timeLabel(after.as_of)} · ${checksum.slice(0, 12)}`;
    const driver = event.type === 'underlying_tick' ? `Futures price updates to ${number(event.price)}`
      : Number.isFinite(event.strike) ? `${number(event.strike)} ${optionSide(event.option_type)} option update`
      : (event.type || 'Driving update').replaceAll('_', ' ');
    $('#blind-event').textContent = `Event ${number(event.sequence, 0)} · ${driver}`;
    $('#blind-snapshots').replaceChildren(snapshot('Before update', before), snapshot('At the flip', after),
      snapshot('Without driving update', counterfactual, flip.counterfactual_reason));

    const rows = document.createDocumentFragment();
    for (const contract of contributions || []) {
      const row = element('tr');
      const updated = contract.contract_id === event.contract_id && (!event.provider || contract.provider === event.provider);
      const label = element('th', `${number(contract.strike)} ${optionSide(contract.option_type)}`,
        updated ? 'investigation-trigger' : undefined);
      label.scope = 'row';
      const identity = [contract.expiry_timestamp ? timeLabel(contract.expiry_timestamp) : contract.expiry,
        contract.provider, contract.contract_id].filter(Boolean).join(' · ');
      if (identity) label.append(element('small', identity, 'investigation-contract-identity'));
      row.append(label,
        element('td', `${number(contract.before_quantity)} → ${number(contract.after_quantity)}`),
        element('td', number(contract.delta_gex)),
        element('td', contract.counterfactual_status === 'unpriced' ? 'Unpriced' : number(contract.counterfactual_gex)));
      rows.append(row);
    }
    if (!rows.childNodes.length) {
      const row = element('tr');
      const cell = element('td', 'No changed contract contributions are available.');
      cell.colSpan = 4;
      row.append(cell);
      rows.append(row);
    }
    $('#blind-contract-rows').replaceChildren(rows);
    $('#blind-review-grid').hidden = false;
    $('#blind-load-status').hidden = true;
  }

  function renderCommit(view, commit) {
    const {$} = view;
    if (!commit || typeof commit.read !== 'string' || !commit.committed_at) throw new Error('The review has no committed read.');
    view.commit = commit;
    view.stage = 'committed';
    drafts.delete(view.session.id);
    $('#blind-read').value = '';
    $('#blind-commit-form').hidden = true;
    $('#blind-committed').hidden = false;
    $('#blind-committed-read').textContent = commit.read;
    $('#blind-commit-time').textContent = `Committed ${timeLabel(commit.committed_at)}`;
    $('#blind-stage').textContent = 'Read committed';
  }

  function renderPrices(view, points, start, end, coverage) {
    const {$, session: {symbol, label}} = view;
    const table = $('#blind-price-rows');
    const rows = document.createDocumentFragment();
    for (const [index, point] of points.entries()) {
      const row = element('tr');
      row.append(element('td', timeLabel(point.as_of)), element('td', number(point.price)),
        element('td', index === 0 ? 'Price known at the flip' : 'Observed update'));
      rows.append(row);
    }
    table.replaceChildren(rows);
    $('#blind-price-details').hidden = !points.length;
    const old = $('#blind-price-plot');
    const plot = element('div', undefined, 'plot blind-price-plot');
    plot.id = old.id;
    plot.setAttribute('role', 'img');
    old.replaceWith(plot);
    if (window.Plotly && old.data) window.Plotly.purge(old);
    plot.setAttribute('aria-label', `Observed ${label} futures prices from the flip to the 30-minute horizon`);
    plot.hidden = !points.length || !window.Plotly;
    const observations = Number.isFinite(coverage?.observed_price_count)
      ? ` Observed updates ${number(coverage.observed_price_count, 0)}.` : '';
    const sampling = coverage?.price_sampling === 'observed_minute_extrema' ? ' Showing recorded minute extrema.' : '';
    const gap = Number.isFinite(coverage?.largest_price_gap_seconds)
      ? ` Largest gap ${number(coverage.largest_price_gap_seconds, 1)} seconds.` : '';
    const age = Number.isFinite(coverage?.price_age_seconds)
      ? ` Price age at cutoff ${number(coverage.price_age_seconds, 1)} seconds.` : '';
    const anchor = plot.hidden ? '' : 'Amber marks the price known at the flip. ';
    $('#blind-price-caption').textContent = points.length
      ? `${anchor}Last displayed price ${number(points.at(-1).price)}.${observations}${sampling}${gap}${age}`
      : 'No futures price values are available for this horizon.';
    if (plot.hidden) return;
    const ticks = points.map(point => point.as_of);
    const prices = points.map(point => point.price);
    const traces = [{type: 'scatter', mode: 'markers', x: ticks, y: prices,
      marker: {color: points.map((_, index) => index ? '#37cee9' : '#ffbd35'), size: points.length > 350 ? 3 : 6},
      text: points.map((_, index) => index === 0 ? 'Price known at the flip' : 'Observed update'),
      hovertemplate: `%{text}<br>%{x|%H:%M:%S} UTC<br>${symbol} %{y:,.2f}<extra></extra>`}];
    const axis = {gridcolor: '#253849', linecolor: '#40546b', fixedrange: true};
    const xaxis = {...axis, type: 'date', tickformat: '%H:%M', title: {text: 'UTC'}, automargin: true};
    if (start && end) xaxis.range = [start, end];
    const layout = {paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', showlegend: false,
      font: {family: 'SFMono-Regular, Consolas, monospace', color: '#a2b5ce', size: 11},
      margin: {l: 58, r: 15, t: 15, b: 47}, xaxis,
      yaxis: {...axis, title: {text: `${symbol} price`}, tickformat: ',.2f', automargin: true}};
    window.Plotly.react(plot, traces, layout, {responsive: true, displayModeBar: false}).then(
      () => {if (!plot.isConnected && plot.data) window.Plotly.purge(plot);},
      () => {
        if (!plot.isConnected) return;
        plot.hidden = true;
        $('#blind-price-caption').textContent = 'The chart is unavailable. Inspect price values below.';
      });
  }

  function verifyOutcome(view, result, committed) {
    const checksum = verifyFlip(view, result?.flip);
    if (result.request?.capture_sha256 !== checksum || !result.outcome || typeof committed?.read !== 'string'
        || !committed.committed_at || result.commit?.read !== committed.read
        || result.commit?.committed_at !== committed.committed_at) {
      throw new Error('The outcome did not match the committed read.');
    }
  }

  function renderOutcome(view, result, committed) {
    verifyOutcome(view, result, committed);
    const {$} = view;
    renderFlip(view, result.flip);
    renderCommit(view, committed);
    view.stage = 'revealed';
    view.result = result;
    $('#blind-stage').textContent = 'Outcome revealed';
    $('#blind-stage').classList.add('revealed');
    const {outcome} = result;
    const startSign = result.flip.after.summary.net_sign;
    const laterSign = outcome.summary?.net_sign;
    $('#blind-start-sign').textContent = signLabel(startSign);
    $('#blind-later-sign').textContent = signLabel(laterSign);
    $('#blind-sign-result').textContent = Number.isInteger(startSign) && Number.isInteger(laterSign)
      ? (startSign === laterSign ? 'Held' : 'Changed') : 'Unavailable';
    const observed = outcome.as_of && outcome.as_of !== outcome.target_as_of
      ? ` · Last accepted state ${timeLabel(outcome.as_of)}` : '';
    const valuation = outcome.valuation_as_of && outcome.valuation_as_of !== outcome.target_as_of
      ? ` · Valued at ${timeLabel(outcome.valuation_as_of)}` : '';
    $('#blind-horizon').textContent = `Requested cutoff ${timeLabel(outcome.target_as_of)}${observed}${valuation}`;
    const coverage = coverageText(outcome.pricing_coverage);
    const horizonNote = [outcome.reason, coverage].filter(Boolean).join(' · ');
    $('#blind-horizon-note').hidden = !horizonNote;
    $('#blind-horizon-note').textContent = horizonNote;
    $('#blind-outcome').hidden = false;
    renderPrices(view, outcome.price_path || [], result.flip.after.as_of, outcome.target_as_of,
      outcome.coverage);
    message($('#blind-action-status'), '');
  }

  function marketsBusy() {
    return [...views.values()].some(view => view.busy);
  }

  function updateControls() {
    const busy = app.receiptBusy || marketsBusy();
    const selected = views.get(app.selected);
    const canCompare = app.sessions.length === 2;
    const comparisonReady = app.comparing && [...views.values()].every(view => view.result);

    $('#blind-source-picker').hidden = !canCompare || app.comparing;
    $('#blind-source-select').disabled = busy || !capability;
    const toggle = $('#blind-compare-toggle');
    toggle.hidden = !canCompare;
    toggle.disabled = busy || !capability;
    toggle.textContent = app.comparing ? 'Review one session'
      : app.sameMarket ? 'Compare saved sessions' : 'Compare ES and NQ';

    $('#blind-comparison-actions').hidden = !app.comparing;
    $('#blind-save-comparison').hidden = !comparisonReady;
    $('#blind-save-comparison').disabled = !app.comparisonChecked || Boolean(app.comparisonReceipt) || busy || !capability;
    $('#blind-save-comparison span').textContent = app.comparisonReceipt ? 'Comparison saved' : 'Save comparison';
    $('#blind-open-receipts').disabled = (app.comparing
      ? [...views.values()].some(view => view.loading)
      : !selected?.stage) || busy || !capability;
    $('#blind-open-receipts span').textContent = app.comparing ? 'Saved comparisons' : 'Saved reviews';
    $('#blind-confirm-save').disabled = busy || !capability;

    for (const view of views.values()) {
      const {$, stage, activeReceipt} = view;
      const locked = view.busy || app.receiptBusy || !capability;
      $('#blind-commit').disabled = stage !== 'blind' || locked || !$('#blind-read').value.trim();
      $('#blind-read').disabled = locked;
      $('#blind-reveal').hidden = stage !== 'committed';
      $('#blind-reveal').disabled = locked;
      $('#blind-save').disabled = !view.result || Boolean(activeReceipt) || locked;
      $('#blind-save').querySelector('span').textContent = activeReceipt ? 'Review saved' : 'Save review';
    }
  }

  function mountMarket(session) {
    const {id, label} = session;
    const root = $('#blind-market-template').content.firstElementChild.cloneNode(true);
    const suffix = `-${id.toLowerCase()}`;
    root.setAttribute('aria-label', `${label} review`);
    for (const node of root.querySelectorAll('[id]')) node.id += suffix;
    for (const attr of ['aria-labelledby', 'aria-describedby', 'for']) {
      for (const node of root.querySelectorAll(`[${attr}]`)) node.setAttribute(attr, node.getAttribute(attr) + suffix);
    }

    const find = selector => root.querySelector(selector + suffix);
    const view = {root, $: find, session, stage: null, commit: null, result: null, activeReceipt: null, busy: false, loading: true};
    find('#blind-source').textContent = `Saved ${label} flip`;
    find('#blind-load-status').textContent = `Opening the selected ${label} flip…`;
    find('#blind-read').value = drafts.get(id) || '';
    find('#blind-read').addEventListener('input', event => {
      if (view.stage === 'blind') drafts.set(id, event.currentTarget.value);
      updateControls();
    });
    find('#blind-commit-form').addEventListener('submit', event => {
      event.preventDefault();
      commitRead(view);
    });
    find('#blind-reveal').addEventListener('click', () => retryReveal(view));
    find('#blind-save').addEventListener('click', () => openSave(view));
    return view;
  }

  async function loadMarket(view) {
    const {session, $} = view;
    const {id} = session;
    if (!pendingReviews.has(id)) {
      pendingReviews.set(id, api('', {session: id}).finally(() => pendingReviews.delete(id)));
    }
    try {
      const data = await pendingReviews.get(id);
      if (views.get(id) !== view) return;
      session.checksum = verifyFlip(view, data.flip);
      if (data.stage === 'revealed') {
        renderOutcome(view, data.result, data.commit);
        view.activeReceipt = data.receipt_sha256 || null;
        message($('#blind-save-status'), receiptMessages.get(view.activeReceipt) || '');
      } else {
        renderFlip(view, data.flip);
        if (data.stage === 'committed') renderCommit(view, data.commit);
        else view.stage = 'blind';
      }
    } catch (error) {
      if (views.get(id) !== view) return;
      $('#blind-load-status').hidden = false;
      message($('#blind-load-status'), error.message, true);
    } finally {
      view.loading = false;
      updateControls();
    }
  }

  function showMarkets() {
    const sessions = app.comparing ? app.sessions : app.sessions.filter(session => session.id === app.selected);
    const container = $('#blind-markets');
    container.classList.toggle('side-by-side', app.comparing);
    for (const [id, view] of views) {
      if (sessions.some(session => session.id === id)) continue;
      const plot = view.$('#blind-price-plot');
      if (window.Plotly && plot.data) window.Plotly.purge(plot);
      view.root.remove();
      views.delete(id);
    }
    sessions.forEach((session, index) => {
      if (!views.has(session.id)) {
        const view = mountMarket(session);
        views.set(session.id, view);
        container.insertBefore(view.root, container.children[index] || null);
        loadMarket(view);
      }
    });
    if (window.Plotly) requestAnimationFrame(() => {
      for (const view of views.values()) {
        const plot = view.$('#blind-price-plot');
        if (plot.data) window.Plotly.Plots.resize(plot).catch(() => {});
      }
    });
    updateControls();
  }

  async function reveal(view) {
    const messageArea = view.$('#blind-action-status');
    message(messageArea, 'Replaying the 30-minute horizon…');
    const response = await api('/reveal', {session: view.session.id, body: {}});
    renderOutcome(view, response.result, view.commit);
    if (!app.comparing) view.$('#blind-outcome-heading').focus();
  }

  async function commitRead(view) {
    if (view.busy || app.receiptBusy || view.stage !== 'blind') return;
    const read = view.$('#blind-read').value.trim();
    if (!read) return;
    const status = view.$('#blind-action-status');
    view.busy = true;
    updateControls();
    message(status, 'Committing your read…');
    try {
      const {commit} = await api('/commit', {session: view.session.id, body: {read}});
      renderCommit(view, commit);
      await reveal(view);
    } catch (error) {
      message(status, error.message, true);
    } finally {
      view.busy = false;
      updateControls();
    }
  }

  async function retryReveal(view) {
    if (view.busy || app.receiptBusy || view.stage !== 'committed') return;
    view.busy = true;
    updateControls();
    try {await reveal(view);}
    catch (error) {message(view.$('#blind-action-status'), error.message, true);}
    finally {view.busy = false; updateControls();}
  }

  async function loadComparisonStatus() {
    app.comparisonChecked = false;
    app.comparisonReceipt = null;
    const statusArea = $('#blind-comparison-status');
    message(statusArea, '');
    const request = new AbortController();
    app.comparisonRequest = request;
    try {
      const data = await api('/comparison', {signal: request.signal});
      if (request.signal.aborted) return;
      app.comparisonReceipt = data.receipt_sha256 || null;
      app.comparisonChecked = true;
      message(statusArea, receiptMessages.get(app.comparisonReceipt) || '');
    } catch (error) {
      if (!request.signal.aborted) message(statusArea, error.message, true);
    } finally {
      if (app.comparisonRequest === request) app.comparisonRequest = null;
      updateControls();
    }
  }

  function changeMode() {
    if (app.receiptBusy || marketsBusy()) return;
    closeReceiptDialogs();
    app.comparing = !app.comparing;
    if (app.comparing) loadComparisonStatus();
    else app.comparisonRequest?.abort();
    showMarkets();
  }

  function receiptScope(view) {
    return view
      ? {view, path: '', session: view.session.id, type: 'review', status: view.$('#blind-save-status')}
      : {path: '/comparison', type: 'comparison', status: $('#blind-comparison-status')};
  }

  function currentReceipt(scope) {
    return scope.view ? scope.view.activeReceipt : app.comparisonReceipt;
  }

  function recordReceipt(scope, id, status) {
    if (scope.view) scope.view.activeReceipt = id;
    else {
      app.comparisonRequest?.abort();
      app.comparisonReceipt = id;
      app.comparisonChecked = true;
    }
    receiptMessages.set(id, status);
    message(scope.status, status);
  }

  function closeReceiptDialogs() {
    pendingReceipts?.abort();
    for (const selector of ['#blind-save-dialog', '#blind-receipts-dialog']) {
      const dialog = $(selector);
      if (dialog.open) dialog.close();
    }
    $('#blind-receipts-list').replaceChildren();
    message($('#blind-receipts-status'), '');
    $('#blind-review-name').value = '';
    message($('#blind-save-error'), '');
  }

  function openSave(view) {
    if (app.receiptBusy || marketsBusy()) return;
    if (view && (!view.result || view.activeReceipt || app.comparing)) return;
    if (!view && (!app.comparing || $('#blind-save-comparison').disabled)) return;
    const dialog = $('#blind-save-dialog');
    const type = view ? 'review' : 'comparison';
    const label = view ? `${view.session.label} flip review · ${timeLabel(view.result.flip.after.as_of)}`
      : app.sameMarket ? `${app.sessions[0].symbol} saved-session comparison` : 'ES and NQ blind comparison';
    $('#blind-review-name').value = label;
    $('#blind-save-title').textContent = `Save ${type}`;
    $('#blind-confirm-save').textContent = `Save ${type}`;
    $('#blind-save-label').textContent = view ? 'Review name' : 'Comparison name';
    $('#blind-save-error').hidden = true;
    dialog.showModal();
    $('#blind-review-name').select();
  }

  async function saveReceipt(event) {
    event.preventDefault();
    const name = $('#blind-review-name').value.trim();
    const button = $('#blind-confirm-save');
    if (!name || button.disabled) return;
    const scope = receiptScope(app.comparing ? null : views.get(app.selected));
    app.receiptBusy = true;
    $('#blind-save-error').hidden = true;
    updateControls();
    try {
      const receipt = await api(`${scope.path}/save`, {session: scope.session, body: {name}});
      $('#blind-save-dialog').close();
      const list = app.comparing ? 'Saved comparisons' : 'Saved reviews';
      recordReceipt(scope, receipt.receipt_sha256, `Saved ${receipt.name}. Reopen or export it from ${list}.`);
    } catch (error) {
      message($('#blind-save-error'), error.message, true);
      $('#blind-save-error').hidden = false;
    } finally {
      app.receiptBusy = false;
      updateControls();
    }
  }

  async function reopenReceipt(scope, id, button) {
    if (app.receiptBusy || marketsBusy()) return;
    app.receiptBusy = true;
    button.disabled = true;
    updateControls();
    message($('#blind-receipts-status'), `Verifying the saved ${scope.type}…`);
    try {
      const opened = await api(`${scope.path}/reopen`, {session: scope.session, body: {id}});
      if (scope.view) {
        renderOutcome(scope.view, opened.result, opened.result?.commit);
      } else {
        for (const view of views.values()) {
          const result = opened.results_by_session?.[view.session.id];
          verifyOutcome(view, result, result?.commit);
        }
        for (const view of views.values()) {
          const result = opened.results_by_session[view.session.id];
          if (view.result?.request_sha256 !== result.request_sha256) {
            view.activeReceipt = null;
            message(view.$('#blind-save-status'), '');
          }
          renderOutcome(view, result, result.commit);
        }
      }
      $('#blind-receipts-dialog').close();
      recordReceipt(scope, opened.receipt_sha256, `Verified and reopened ${opened.name}.`);
      if (scope.view) scope.view.$('#blind-outcome-heading').focus();
      else $('#blind-comparison-status').focus();
    } catch (error) {
      message($('#blind-receipts-status'), error.message, true);
    } finally {
      app.receiptBusy = false;
      button.disabled = false;
      updateControls();
    }
  }

  async function exportReceipt(scope, id, button) {
    if (app.receiptBusy || marketsBusy() || id !== currentReceipt(scope)) return;
    app.receiptBusy = true;
    button.disabled = true;
    updateControls();
    try {
      const blob = await api(`${scope.path}/receipts/${encodeURIComponent(id)}/export`, {
        session: scope.session, responseType: 'blob',
      });
      const url = URL.createObjectURL(blob);
      const link = element('a');
      link.href = url;
      link.download = `gex-blind-${scope.type}-${id.slice(0, 12)}.json`;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      message($('#blind-receipts-status'), 'Receipt exported.');
    } catch (error) {
      message($('#blind-receipts-status'), error.message, true);
    } finally {
      app.receiptBusy = false;
      button.disabled = false;
      updateControls();
    }
  }

  async function openReceipts() {
    const dialog = $('#blind-receipts-dialog');
    if ($('#blind-open-receipts').disabled || dialog.open) return;
    const scope = receiptScope(app.comparing ? null : views.get(app.selected));
    pendingReceipts?.abort();
    const request = new AbortController();
    pendingReceipts = request;
    const list = $('#blind-receipts-list');
    list.replaceChildren();
    $('#blind-receipts-title').textContent = app.comparing ? 'Saved comparisons' : 'Saved reviews';
    dialog.showModal();
    message($('#blind-receipts-status'), `Loading saved ${scope.type}s…`);
    try {
      const {receipts} = await api(`${scope.path}/receipts`, {session: scope.session, signal: request.signal});
      if (request.signal.aborted || !dialog.open) return;
      message($('#blind-receipts-status'), receipts.length
        ? `Reopen a ${scope.type} to verify its committed ${app.comparing ? 'reads and outcomes' : 'read and outcome'}.`
        : `No saved ${scope.type}s yet.`);
      for (const receipt of receipts) {
        const row = element('div', undefined, 'receipt-item');
        const details = element('div');
        details.append(element('h3', receipt.name || `Saved ${scope.type}`), element('p', timeLabel(receipt.created_at)));
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
        row.append(details, actions);
        list.append(row);
      }
    } catch (error) {
      if (!request.signal.aborted && dialog.open) message($('#blind-receipts-status'), error.message, true);
    } finally {
      if (pendingReceipts === request) pendingReceipts = null;
    }
  }

  async function initialize() {
    const picker = $('#blind-source-select');
    picker.addEventListener('change', () => {
      if (app.receiptBusy || marketsBusy() || picker.value === app.selected) return;
      closeReceiptDialogs();
      app.selected = picker.value;
      showMarkets();
    });
    $('#blind-compare-toggle').addEventListener('click', changeMode);
    $('#blind-save-comparison').addEventListener('click', () => openSave());
    $('#blind-save-form').addEventListener('submit', saveReceipt);
    $('#blind-open-receipts').addEventListener('click', openReceipts);
    $('#blind-receipts-dialog').addEventListener('close', event => {
      if (!event.currentTarget.open) pendingReceipts?.abort();
    });
    document.querySelectorAll('dialog [data-close]').forEach(button => {
      button.addEventListener('click', () => button.closest('dialog').close());
    });
    try {
      const {sessions} = await api('/sessions');
      if (!sessions?.length) throw new Error('There are no saved sessions in this review.');
      app.sameMarket = sessions.length === 2 && sessions[0].symbol === sessions[1].symbol;
      app.sessions = sessions.map(({id, symbol}, index) => ({
        id, symbol, label: app.sameMarket ? `Session ${index === 0 ? 'A' : 'B'} (${symbol})` : symbol,
      }));
      app.selected = app.sessions[0].id;
      picker.replaceChildren(...app.sessions.map(({id, label}) => {
        const option = element('option', label);
        option.value = id;
        return option;
      }));
      picker.value = app.selected;
      $('#blind-launch-status').hidden = true;
      showMarkets();
    } catch (error) {
      $('#blind-launch-status').hidden = false;
      message($('#blind-launch-status'), error.message, true);
    }
  }

  initialize();
})();

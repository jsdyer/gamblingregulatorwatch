const element = id => document.getElementById(id);
const number = new Intl.NumberFormat('en-CA');
const pageSize = 24;
let edition;
let regulators;
let operators;
let filtered = [];
let visible = pageSize;
let selected = '';
let missingLinkedProfile = false;

function node(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
}

function profileURL(operator) {
  return './records/' + encodeURIComponent(operator.slug) + '/';
}

function sourceLink(text, url) {
  if (!url) return null;
  try {
    const address = new URL(url);
    if (!['https:', 'http:'].includes(address.protocol) || address.username || address.password) return null;
    const a = node('a', text);
    a.href = address.href;
    a.rel = 'external noreferrer';
    return a;
  } catch {
    return null;
  }
}

function localLink(text, url, className) {
  const link = node('a', text, className);
  link.href = url;
  return link;
}

function dateOnly(value) {
  return value ? String(value).split('T')[0] : '';
}

function count(n, singular, plural = singular + 's') {
  return number.format(n) + ' ' + (n === 1 ? singular : plural);
}

function normalize(value) {
  return String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('en-CA').trim();
}

function authorityName(id) {
  return regulators.get(id)?.name || id;
}

function recordsFor(operator) {
  return [...operator.licences, ...operator.actions];
}

export function otherNames(operator) {
  const names = [...(operator.identity?.names || [])];
  for (const record of recordsFor(operator)) {
    for (const key of ['entity', 'name', 'trading_name', 'brand', 'brands', 'domain', 'domains', 'trading_names', 'websites']) {
      const value = record[key];
      if (typeof value === 'string') names.push(value);
      else if (Array.isArray(value)) names.push(...value.filter(item => typeof item === 'string'));
    }
  }
  return [...new Set(names)].filter(value => value && normalize(value) !== normalize(operator.name));
}

function membership(operator) {
  return new Set(recordsFor(operator).map(record => record.regulator));
}

function textFor(value) {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map(textFor).filter(Boolean).join(' · ');
  return '';
}

function renderRegulatorMatches(matches) {
  const section = element('regulator-matches');
  const cards = matches.map(regulator => {
    const item = node('div', undefined, 'reg-match');
    item.append(node('h3', regulator.name), node('p', [regulator.jurisdiction, regulator.role].filter(Boolean).join(' · ')));
    const sources = [sourceLink('Official register', regulator.register_url), sourceLink('Enforcement publications', regulator.enforcement_url)].filter(Boolean);
    sources.forEach((link, index) => {
      if (index) item.append(' · ');
      item.append(link);
    });
    return item;
  });
  section.replaceChildren(...cards);
}

export function matchesRecord(operator, recordType, regId = '') {
  if (!recordType) return true;
  if (recordType === 'licences' || recordType === 'actions') {
    return operator[recordType].some(record => !regId || record.regulator === regId);
  }
  if (recordType === 'foreign') {
    return operator.foreign.some(link => !regId || link.action?.regulator === regId || link.licence?.regulator === regId);
  }
  if (!regId) return operator.repeat;
  const cases = new Set(operator.actions.filter(action => action.eligible && action.regulator === regId)
    .map(action => action.case_id || action.id));
  return cases.size >= 2;
}

function findOperators() {
  const query = normalize(element('query').value);
  const regId = element('regulator-filter').value;
  const recordType = element('record-filter').value;
  const regulatorMatch = [...regulators.values()].filter(reg => query && [reg.id, reg.name, reg.jurisdiction].some(value => normalize(value).includes(query)));
  const matchingIds = new Set(regulatorMatch.map(reg => reg.id));
  filtered = operators.filter(operator => {
    const authorities = membership(operator);
    if (regId && !authorities.has(regId)) return false;
    if (query && !normalize(operator.name).includes(query) && !otherNames(operator).some(name => normalize(name).includes(query)) &&
        ![...authorities].some(id => matchingIds.has(id))) return false;
    return matchesRecord(operator, recordType, regId);
  });
  renderRegulatorMatches(regulatorMatch.filter(reg => !regId || reg.id === regId));
  element('reset').hidden = !(query || regId || recordType);
  visible = pageSize;
  renderList();
}

function renderList() {
  const list = element('operator-list');
  const shown = filtered.slice(0, visible);
  element('result-count').textContent = count(filtered.length, 'matching operator') +
    (shown.length < filtered.length ? ' · Showing ' + number.format(shown.length) : '');
  element('more').hidden = shown.length >= filtered.length;
  element('export').disabled = !filtered.length;
  if (!shown.length) {
    list.replaceChildren(node('p', 'No operator in this edition matches those choices. Try part of the legal name or clear a filter.', 'empty'));
    return;
  }
  list.replaceChildren(...shown.map(operator => {
    const row = node('article', undefined, 'operator-row');
    const body = node('div');
    const title = node('h3');
    title.append(localLink(operator.name, profileURL(operator)));
    const regulatorNames = [...membership(operator)].map(authorityName).join(' · ');
    const counts = [count(operator.licences.length, 'licence record'), count(operator.actions.length, 'published action')].join(' · ');
    body.append(title, node('p', [counts, regulatorNames].filter(Boolean).join(' · ')));
    const query = normalize(element('query').value);
    const alias = query && otherNames(operator).find(name => normalize(name).includes(query));
    if (alias) body.append(node('p', 'Source-listed name or site: ' + alias));
    const button = node('button', 'Preview', 'quiet');
    button.type = 'button';
    button.setAttribute('aria-label', 'Preview records for ' + operator.name);
    button.dataset.operator = operator.slug;
    button.setAttribute('aria-controls', 'operator-preview');
    button.setAttribute('aria-expanded', String(selected === operator.slug));
    button.addEventListener('click', () => selectOperator(operator, true));
    row.append(body, button);
    return row;
  }));
}

function setURL(slug) {
  const address = new URL(location.href);
  if (slug) address.searchParams.set('operator', slug);
  else address.searchParams.delete('operator');
  history.replaceState(null, '', address);
}

function closePreview(updateURL = true) {
  const previous = selected;
  selected = '';
  missingLinkedProfile = false;
  const box = element('operator-preview');
  box.hidden = true;
  box.replaceChildren();
  if (updateURL) setURL('');
  return previous;
}

function closeButton() {
  const button = node('button', 'Close', 'quiet');
  button.type = 'button';
  button.setAttribute('aria-label', 'Close operator preview');
  button.addEventListener('click', () => {
    const previous = closePreview();
    renderList();
    const rowButton = [...element('operator-list').querySelectorAll('button')].find(b => b.dataset.operator === previous);
    (rowButton || element('query')).focus();
  });
  return button;
}

function displayRecords(container, heading, records, formatter, linkText) {
  if (!records.length) return;
  const list = node('ul');
  container.append(node('h4', heading), list);
  const byDate = [...records].sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')));
  for (const record of byDate.slice(0, 2)) {
    const item = node('li', formatter(record));
    const link = sourceLink(linkText, record.url);
    if (link) item.append(' · ', link);
    list.append(item);
  }
  if (records.length > 2) container.append(node('p', 'Showing the two most recent dated entries where available. The full profile contains all ' + number.format(records.length) + '.', 'meta'));
}

function selectOperator(operator, focus, updateURL = true) {
  selected = operator.slug;
  missingLinkedProfile = false;
  const box = element('operator-preview');
  const header = node('div', undefined, 'preview-heading');
  header.append(node('h3', operator.name), closeButton());
  box.replaceChildren(header);
  const names = otherNames(operator);
  if (names.length) box.append(node('p', 'Other names or sites in the source records: ' + names.join(' · '), 'meta'));
  displayRecords(box, 'Licence records', operator.licences, licence =>
    [authorityName(licence.regulator), licence.name, licence.status, licence.date && [licence.date_basis, dateOnly(licence.date)].filter(Boolean).join(' '), licence.licence_id].filter(Boolean).join(' · '),
  'Official record');
  displayRecords(box, 'Published actions', operator.actions, action =>
    [dateOnly(action.date), action.title || action.type, authorityName(action.regulator), action.status].filter(Boolean).join(' · '),
  'Official publication');
  if (operator.repeat) box.append(node('p', count(operator.case_count, 'distinct eligible case') + ' for this entity across the included authorities.', 'meta'));
  if (operator.foreign.length) box.append(node('p', 'A current operator licence in this edition is linked to an earlier eligible penalty in another jurisdiction. The full profile gives both sources.', 'meta'));
  if (operator.delays?.length) box.append(node('p', 'Time from documented start to effective revocation: ' + intervalText(operator.delays) + '.', 'meta'));
  box.append(localLink('Read the full operator profile →', profileURL(operator), 'profile'));
  box.hidden = false;
  if (updateURL) setURL(operator.slug);
  renderList();
  if (focus) {
    box.focus({preventScroll: true});
    box.scrollIntoView({block: 'start'});
  }
}

function invalidProfile() {
  const preview = element('operator-preview');
  const header = node('div', undefined, 'preview-heading');
  header.append(node('h3', 'Operator profile unavailable'), closeButton());
  preview.replaceChildren(header, node('p', 'This link does not match a legal operator in the published edition. Search the directory below.'));
  preview.hidden = false;
  missingLinkedProfile = true;
}

function comparisonRow(body, title, first, second, format) {
  const row = node('tr');
  const heading = node('th', title);
  heading.scope = 'row';
  row.append(heading);
  for (const reg of [first, second]) {
    const cell = node('td');
    if (reg) {
      const text = format(reg);
      if (text instanceof Node) cell.append(text);
      else cell.textContent = typeof text === 'number' ? number.format(text) : text == null || text === '' ? 'Not available' : text;
    } else cell.textContent = '—';
    row.append(cell);
  }
  body.append(row);
}

function officialLinks(reg) {
  const links = node('div');
  const register = sourceLink('Licence or official register', reg.register_url);
  const actions = sourceLink('Enforcement publications', reg.enforcement_url);
  if (register) links.append(register);
  if (actions && (!register || register.href !== actions.href)) links.append(actions);
  if (!links.childElementCount) links.textContent = 'No source link provided';
  return links;
}

export function intervalText(intervals) {
  const values = (intervals || []).map(item => item.days).filter(days => Number.isFinite(days) && days >= 0).sort((a,b) => a-b);
  if (!values.length) return 'No documented interval in this edition';
  const middle = Math.floor(values.length / 2);
  const median = values.length % 2 ? values[middle] : (values[middle-1] + values[middle]) / 2;
  if (values.length === 1) return count(values[0], 'day') + ' (one documented case interval)';
  return count(median, 'day') + ' median across ' + count(values.length, 'documented interval');
}

function publishedRate(reg) {
  const rate = reg.rate;
  if (!rate || !Number.isFinite(rate.value)) return 'No comparable rate supplied';
  const detail = node('div');
  const label = [rate.label, rate.year].filter(Boolean).join(' · ');
  detail.append(node('strong', number.format(rate.value) + (label ? ' · ' + label : ' per 100')));
  if (rate.numerator != null && rate.denominator != null) detail.append(node('p', number.format(rate.numerator) + ' / ' + number.format(rate.denominator), 'meta'));
  if (rate.basis) detail.append(node('p', rate.basis, 'meta'));
  const link = sourceLink('Rate source', rate.url);
  if (link) detail.append(link);
  return detail;
}

function renderComparison() {
  const first = regulators.get(element('compare-a').value);
  const second = regulators.get(element('compare-b').value);
  if (!first) return;
  const table = element('comparison');
  const header = node('thead');
  const row = node('tr');
  for (const label of ['Public records', first.name, second?.name || 'No second regulator']) {
    const heading = node('th', label);
    heading.scope = 'col';
    row.append(heading);
  }
  header.append(row);
  const body = node('tbody');
  const each = (name, fn) => comparisonRow(body, name, first, second, fn);
  each('Jurisdiction', r => r.jurisdiction);
  each('Role', r => r.role);
  each('Named entities in this edition', r => r.operator_count);
  each('Licence records included', r => r.licence_count);
  each('Published action records', r => r.action_count);
  each('Distinct eligible cases', r => r.case_count);
  each('Operators with repeat cases', r => r.repeat_count);
  each('Current licensed entities with an earlier foreign penalty', r => r.foreign_count);
  each('Time to effective revocation', r => intervalText(r.delays));
  each('Rate per 100, where available', publishedRate);
  each('Coverage', r => textFor(r.coverage));
  each('Official sources', officialLinks);
  table.replaceChildren(header, body);
  element('comparison-note').textContent = 'Repeat counts use distinct eligible cases for the same entity. Documented intervals use the dates available for individual cases. Source periods and denominators can differ, so these figures cannot establish which regulator acts faster or more often.';
}

function downloadResults() {
  const fields = [['Legal operator', 'Regulators', 'Included licence records', 'Included action records', 'Operator profile']];
  for (const operator of filtered) {
    fields.push([operator.name, [...membership(operator)].map(authorityName).join(' | '), operator.licences.length, operator.actions.length,
      new URL(profileURL(operator), 'https://coolcode.ca/gamblingregulatorwatch/').href]);
  }
  const quote = value => {
    const str = String(value);
    const safe = /^[\s]*[=+@-]/.test(str) ? "'" + str : str;
    return '"' + safe.replaceAll('"', '""') + '"';
  };
  const csv = fields.map(row => row.map(quote).join(',')).join('\r\n') + '\r\n';
  const url = URL.createObjectURL(new Blob(['\uFEFF', csv], {type:'text/csv;charset=utf-8'}));
  const a = localLink('Download CSV', url);
  a.download = 'gambling-regulator-watch-operators.csv';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

function filtersChanged() {
  if (selected || missingLinkedProfile) closePreview();
  findOperators();
}

async function start() {
  const response = await fetch('./data/edition.json');
  if (!response.ok) throw new Error('Edition unavailable');
  edition = await response.json();
  if (!Array.isArray(edition.regulators) || !Array.isArray(edition.operators)) throw new Error('Invalid edition');
  regulators = new Map(edition.regulators.map(reg => [reg.id, reg]));
  operators = [...edition.operators].sort((a, b) => a.name.localeCompare(b.name, 'en-CA'));
  const sorted = [...regulators.values()].sort((a, b) => a.name.localeCompare(b.name, 'en-CA'));
  const choices = () => sorted.map(reg => new Option(reg.name, reg.id));
  element('regulator-filter').append(...choices());
  element('compare-a').append(...choices());
  element('compare-b').append(...choices());
  const withActions = sorted.filter(reg => reg.action_count > 0);
  if (withActions.length > 1) {
    element('compare-a').value = withActions[0].id;
    element('compare-b').value = withActions[1].id;
  }
  else if (sorted.length > 1) element('compare-b').selectedIndex = 1;
  else element('compare-b').replaceChildren(new Option('No second regulator', ''));
  element('edition').textContent = [count(operators.length, 'named entity', 'named entities'), count(regulators.size, 'regulator'), edition.built_at && 'Latest source snapshot ' + dateOnly(edition.built_at)].filter(Boolean).join(' · ');
  element('query').addEventListener('input', filtersChanged);
  element('regulator-filter').addEventListener('change', filtersChanged);
  element('record-filter').addEventListener('change', filtersChanged);
  element('reset').addEventListener('click', () => {
    element('query').value = element('regulator-filter').value = element('record-filter').value = '';
    filtersChanged();
    element('query').focus();
  });
  element('more').addEventListener('click', () => { visible += pageSize; renderList(); });
  element('export').addEventListener('click', downloadResults);
  for (const [own, other] of [['compare-a', 'compare-b'], ['compare-b', 'compare-a']]) {
    element(own).addEventListener('change', () => {
      if (element(own).value === element(other).value && sorted.length > 1) {
        element(other).value = sorted.find(reg => reg.id !== element(own).value).id;
      }
      renderComparison();
    });
  }
  element('load-status').hidden = true;
  element('operator-workspace').hidden = false;
  element('comparison-workspace').hidden = !sorted.length;
  findOperators();
  renderComparison();
  const slug = new URLSearchParams(location.search).get('operator');
  if (slug) {
    const operator = operators.find(operator => operator.slug === slug);
    if (operator) selectOperator(operator, true, false);
    else invalidProfile();
  }
}

if (typeof document !== 'undefined') start().catch(() => {
  const status = element('load-status');
  status.hidden = false;
  status.replaceChildren('The searchable edition could not load. Open the ', localLink('published operator directory', './records/'), ' to read its source records.');
  for (const id of ['query','regulator-filter','record-filter']) element(id).disabled = true;
});

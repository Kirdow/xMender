'use strict';
/* xMender single-page UI. No build step, no framework. All DOM is built with
   h(), which sets text via textContent, so server data is never parsed as HTML. */

// ── Helpers ──────────────────────────────────────────────────────────────────

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'value') el.value = v;
    else if (k === 'checked') el.checked = !!v;
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? '' : String(v));
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

const SVG_NS = 'http://www.w3.org/2000/svg';
function icon(paths) {
  const s = document.createElementNS(SVG_NS, 'svg');
  s.setAttribute('viewBox', '0 0 24 24');
  s.setAttribute('fill', 'none');
  s.setAttribute('stroke', 'currentColor');
  s.setAttribute('stroke-width', '2');
  s.setAttribute('stroke-linecap', 'round');
  s.setAttribute('stroke-linejoin', 'round');
  for (const d of paths) {
    const p = document.createElementNS(SVG_NS, 'path');
    p.setAttribute('d', d);
    s.append(p);
  }
  return s;
}
const ICONS = {
  dashboard: ['M3 13h8V3H3z', 'M13 21h8V11h-8z', 'M3 21h8v-6H3z', 'M13 9h8V3h-8z'],
  tasks: ['M9 6h11', 'M9 12h11', 'M9 18h11', 'M4 6l1 1 2-2', 'M4 12l1 1 2-2', 'M4 18l1 1 2-2'],
  integrations: ['M8 12h8', 'M6 8a4 4 0 0 0 0 8h2', 'M18 8a4 4 0 0 1 0 8h-2'],
  settings: ['M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z', 'M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.8 1.2V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-2.8-1.2l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.7 1.7 0 0 0 3 15.4H3a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 4.6 9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.7 1.7 0 0 0 9 4.6V4.5a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 2.8 1.2l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0 1.2 2.8h.2a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z'],
  admin: ['M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z', 'M9 12l2 2 4-4'],
  logout: ['M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4', 'M16 17l5-5-5-5', 'M21 12H9'],
  refresh: ['M21 12a9 9 0 1 1-2.6-6.4', 'M21 3v6h-6'],
};

async function api(method, path, body) {
  const opts = { method, headers: { 'x-xmender': '1' }, credentials: 'same-origin' };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, opts);
  } catch (e) {
    throw new Error('Cannot reach xMender. Is the service running?');
  }
  let data = null;
  try { data = await res.json(); } catch (_) { /* empty body */ }
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith('/api/auth/')) { boot(); }
    let msg = data && data.detail;
    if (Array.isArray(msg)) msg = msg.map((d) => d.msg).join('; ');
    throw new Error(msg || `Request failed (${res.status}).`);
  }
  return data;
}

function toast(msg, kind) {
  const t = h('div', { class: `toast ${kind || ''}` }, msg);
  document.getElementById('toasts').append(t);
  setTimeout(() => t.remove(), kind === 'err' ? 7000 : 4000);
}

async function withBusy(btn, fn) {
  const label = btn.textContent;
  btn.disabled = true;
  btn.replaceChildren(h('span', { class: 'spin' }), ' ' + label);
  try { return await fn(); } finally { btn.disabled = false; btn.textContent = label; }
}

function fmtTime(iso) {
  if (!iso) return 'never';
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  return d.toLocaleString();
}

// Costs arrive as integer nano-dollars. Under $1 show up to 6 decimals.
function fmtUsd(nanos) {
  if (nanos === null || nanos === undefined) return '—';
  const usd = nanos / 1e9;
  if (usd >= 1) return '$' + usd.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (nanos > 0 && usd < 0.0000005) return '< $0.000001';
  return '$' + usd.toFixed(nanos === 0 ? 2 : 6);
}
function fmtRate(s) { return '$' + Number(s).toFixed(Math.max(2, (String(s).split('.')[1] || '').length)); }
function exactUsd(nanos) { return nanos === null || nanos === undefined ? 'price unknown' : '$' + (nanos / 1e9).toFixed(9) + ' exact'; }
function fmtNum(n) { return (n || 0).toLocaleString('en-US'); }

function field(label, input, hint) {
  return h('div', { class: 'field' }, h('label', {}, label), input, hint ? h('div', { class: 'hint' }, hint) : null);
}

function switchEl(checked, onchange, label) {
  const input = h('input', { type: 'checkbox', checked, onchange: (e) => onchange(e.target.checked, e.target) });
  return h('label', { class: 'switch' }, input, h('span', { class: 'track' }), label ? h('span', {}, label) : null);
}

function modal(title, lead, body, actions) {
  const close = () => back.remove();
  const box = h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true' },
    h('h3', {}, title),
    lead ? h('p', { class: 'lead' }, lead) : null,
    body,
    h('div', { class: 'btn-row end foot' }, actions(close)));
  const back = h('div', { class: 'modal-backdrop', onmousedown: (e) => { if (e.target === back) close(); } }, box);
  document.addEventListener('keydown', function esc(e) {
    if (e.key === 'Escape') { close(); document.removeEventListener('keydown', esc); }
  });
  document.body.append(back);
  const first = box.querySelector('input, select, textarea');
  if (first) first.focus();
  return close;
}

function confirmDialog(title, text, okLabel, danger) {
  return new Promise((resolve) => {
    modal(title, null, h('p', { class: 'small' }, text), (close) => [
      h('button', { onclick: () => { close(); resolve(false); } }, 'Cancel'),
      h('button', { class: danger ? 'danger' : 'primary', onclick: () => { close(); resolve(true); } }, okLabel),
    ]);
  });
}

// ── State & routing ─────────────────────────────────────────────────────────

const S = { me: null, auth: null };
const app = () => document.getElementById('app');

async function boot() {
  try {
    S.auth = await api('GET', '/api/auth/state');
  } catch (e) {
    app().replaceChildren(authCard('Unavailable', h('p', { class: 'error-box' }, e.message)));
    return;
  }
  S.me = S.auth.user;
  if (S.auth.setup_required) return renderSetup();
  if (!S.me) return location.hash === '#/register' && S.auth.registration_enabled ? renderRegister() : renderLogin();
  route();
}

window.addEventListener('hashchange', () => { if (S.me) route(); else boot(); });

const ROUTES = [
  { path: 'dashboard', label: 'Dashboard', icon: 'dashboard', view: viewDashboard },
  { path: 'tasks', label: 'Tasks', icon: 'tasks', view: viewTasks, perm: 'tasks' },
  { path: 'integrations', label: 'Integrations', icon: 'integrations', view: viewIntegrations, perm: 'integrations' },
  { path: 'settings', label: 'Settings', icon: 'settings', view: viewSettings },
  { path: 'admin', label: 'Admin', icon: 'admin', view: viewAdmin, admin: true },
];

function can(perm) { return S.me && (S.me.is_admin || S.me.permissions.includes(perm)); }
function allowed(r) { return (!r.perm || can(r.perm)) && (!r.admin || S.me.is_admin); }

function route() {
  const [name, ...rest] = location.hash.replace(/^#\/?/, '').split('/');
  const r = ROUTES.find((x) => x.path === name && allowed(x)) || ROUTES[0];
  if (r.path !== name) { history.replaceState(null, '', '#/' + r.path); }
  const main = h('main', { class: 'main' });
  app().replaceChildren(h('div', { class: 'shell' }, sidebar(r.path), main));
  r.view(main, rest);
}

function sidebar(active) {
  return h('nav', { class: 'sidebar', 'aria-label': 'Sidebar' },
    h('div', { class: 'sidebar-brand' }, h('span', { class: 'wordmark' }, 'xMender'), h('small', {}, 'everyday automation')),
    h('div', { class: 'nav' }, ROUTES.filter(allowed).map((r) =>
      h('a', { href: '#/' + r.path, class: r.path === active ? 'active' : '' }, icon(ICONS[r.icon]), h('span', {}, r.label)))),
    h('div', { class: 'user-bar' },
      h('div', { class: 'avatar' }, S.me.username.slice(0, 2)),
      h('div', { class: 'who' }, S.me.username, h('small', {}, S.me.is_root ? 'owner' : S.me.is_admin ? 'admin' : 'user')),
      h('button', { class: 'ghost small', title: 'Log out', 'aria-label': 'Log out', onclick: logout }, icon(ICONS.logout))));
}

async function logout() {
  try { await api('POST', '/api/auth/logout'); } catch (_) { /* ignore */ }
  S.me = null;
  history.replaceState(null, '', '#/');
  boot();
}

function page(main, title, sub, actions, ...content) {
  main.replaceChildren(h('div', { class: 'page' },
    h('div', { class: 'page-head' }, h('div', {}, h('h1', {}, title), sub ? h('p', {}, sub) : null),
      actions ? h('div', { class: 'btn-row' }, actions) : null),
    ...content));
}

// ── Auth screens ────────────────────────────────────────────────────────────

function authCard(note, ...content) {
  return h('div', { class: 'auth-wrap' }, h('div', { class: 'auth-card' },
    h('div', { class: 'logo' }, h('span', { class: 'wordmark' }, 'xMender')),
    note ? h('p', { class: 'note' }, note) : null, ...content));
}

function authForm(fields, submitLabel, onsubmit, footer) {
  const err = h('p', { class: 'error-box hidden' });
  const btn = h('button', { class: 'primary block', type: 'submit' }, submitLabel);
  const form = h('form', {
    onsubmit: async (e) => {
      e.preventDefault();
      err.classList.add('hidden');
      try { await withBusy(btn, () => onsubmit(form)); } catch (ex) { err.textContent = ex.message; err.classList.remove('hidden'); }
    },
  }, err, fields, btn, footer || null);
  return form;
}

function renderSetup() {
  const temp = h('input', { type: 'password', name: 'temp', autocomplete: 'off', required: true });
  const pw = h('input', { type: 'password', name: 'pw', autocomplete: 'new-password', required: true, minlength: 10 });
  const pw2 = h('input', { type: 'password', name: 'pw2', autocomplete: 'new-password', required: true });
  app().replaceChildren(authCard('First-time setup of the admin account',
    h('div', { class: 'callout aqua' }, 'A temporary password was printed to the xMender service output (stdout). With systemd: ',
      h('code', {}, 'journalctl -u xmender'), '. Paste it below and choose a new password.'),
    authForm([
      field('Username', h('input', { type: 'text', value: 'admin', disabled: true, autocomplete: 'username' })),
      field('Temporary password', temp),
      field('New password', pw, 'At least 10 characters.'),
      field('Repeat new password', pw2),
    ], 'Finish setup', async () => {
      if (pw.value !== pw2.value) throw new Error('Passwords do not match.');
      const r = await api('POST', '/api/auth/setup', { temp_password: temp.value, new_password: pw.value });
      S.me = r.user;
      toast('Admin account ready.', 'ok');
      location.hash = '#/integrations';
      boot();
    })));
}

function renderLogin() {
  const user = h('input', { type: 'text', autocomplete: 'username', required: true });
  const pw = h('input', { type: 'password', autocomplete: 'current-password', required: true });
  app().replaceChildren(authCard(null, authForm([field('Username', user), field('Password', pw)], 'Log in', async () => {
    const r = await api('POST', '/api/auth/login', { username: user.value, password: pw.value });
    S.me = r.user;
    boot();
  }, S.auth.registration_enabled ? h('p', { class: 'alt' }, 'No account? ', h('a', { href: '#/register' }, 'Create one')) : null)));
}

function renderRegister() {
  const user = h('input', { type: 'text', autocomplete: 'username', required: true });
  const pw = h('input', { type: 'password', autocomplete: 'new-password', required: true, minlength: 10 });
  const pw2 = h('input', { type: 'password', autocomplete: 'new-password', required: true });
  app().replaceChildren(authCard('Create an account', authForm([
    field('Username', user, '3-32 characters: letters, digits, _ . -'),
    field('Password', pw, 'At least 10 characters.'),
    field('Repeat password', pw2),
  ], 'Create account', async () => {
    if (pw.value !== pw2.value) throw new Error('Passwords do not match.');
    const r = await api('POST', '/api/auth/register', { username: user.value, password: pw.value });
    S.me = r.user;
    location.hash = '#/dashboard';
    boot();
  }, h('p', { class: 'alt' }, h('a', { href: '#/' }, 'Back to log in')))));
}

// ── Dashboard ───────────────────────────────────────────────────────────────

const STATUS_CHIP = { completed: 'lime', partial: 'pink', stopped: '', error: 'red' };
const OUTCOME_CHIP = { pass: 'aqua', 'no-match': 'pink', stop: '', skip: '', sent: 'lime', error: 'red' };

async function viewDashboard(main) {
  const refreshBtn = h('button', { class: 'secondary', onclick: () => withBusy(refreshBtn, refresh) }, icon(ICONS.refresh), 'Refresh now');
  const inboxes = h('div', { class: 'grid-cards' });
  const feed = h('div', {});
  page(main, 'Dashboard', 'New mail is checked automatically; refresh to check right away.', refreshBtn,
    h('h2', {}, h('span', { class: 'dot' }), 'Inboxes'), inboxes,
    h('h2', {}, h('span', { class: 'dot lime' }), 'Recent activity'), feed);

  async function load() {
    const [st, em] = await Promise.all([api('GET', '/api/status'), api('GET', '/api/emails?limit=50')]);
    inboxes.replaceChildren(...(st.inboxes.length ? st.inboxes.map((i) => h('div', { class: 'card accent-aqua' },
      h('div', { class: 'card-title' }, i.name),
      h('div', { class: 'card-sub' }, i.email),
      h('div', { class: 'chips' },
        h('span', { class: 'chip' }, 'checked ' + fmtTime(i.last_polled_at)),
        h('span', { class: 'chip' }, `every ${st.poll_interval_minutes} min`),
        i.pending ? h('span', { class: 'chip pink' }, `${i.pending} queued`) : null,
        i.last_error ? h('span', { class: 'chip red', title: i.last_error }, 'error') : h('span', { class: 'chip lime' }, 'ok')),
      i.last_error ? h('div', { class: 'error-box mt mb0' }, i.last_error) : null))
      : [h('div', { class: 'empty' }, 'No Gmail inbox connected yet. ', can('integrations') ? h('a', { href: '#/integrations' }, 'Connect one') : 'Ask an admin for access.')]));

    feed.replaceChildren(...(em.emails.length ? em.emails.map(mailCard)
      : [h('div', { class: 'empty' }, 'No mail processed yet. Only mail that arrives after an inbox is connected is processed.')]));
  }

  async function refresh() {
    const r = await api('POST', '/api/poll');
    const n = r.results.reduce((a, x) => a + (x.new || 0), 0);
    const errs = r.results.filter((x) => x.error);
    if (errs.length) toast(errs.map((e) => e.error).join(' · '), 'err');
    else toast(n ? `${n} new email${n > 1 ? 's' : ''} processed.` : 'No new mail.', 'ok');
    await load();
  }

  try { await load(); } catch (e) { toast(e.message, 'err'); }
}

function mailCard(m) {
  const log = h('div', { class: 'runlog hidden' }, m.runs.length ? m.runs.map((r) => h('div', { class: 'run' },
    h('div', { class: 'run-name' }, r.task_name, ' ', h('span', { class: `chip ${STATUS_CHIP[r.status] || ''}` }, r.status)),
    r.log.map((s) => [
      h('div', { class: 'step-line' }, h('span', { class: 'n' }, s.step + '.'),
        h('span', {}, s.label), h('span', { class: `chip ${OUTCOME_CHIP[s.outcome] || ''}` }, s.outcome || '?'),
        h('span', { class: 'detail' }, s.detail || '', s.model ? ` · ${s.model}` : '', s.warning ? ` · ${s.warning}` : '',
          s.usage ? h('span', { title: exactUsd(s.usage.cost_nanousd) }, ` · ${fmtNum(s.usage.input_tokens)} in / ${fmtNum(s.usage.output_tokens)} out · ${fmtUsd(s.usage.cost_nanousd)}`) : null)),
      s.response ? h('pre', { class: 'response' }, s.response) : null,
    ]))) : h('div', { class: 'muted small' }, 'No task ran on this email.'));
  return h('div', { class: 'card mail', tabindex: '0',
    onclick: (e) => { if (!e.target.closest('pre')) log.classList.toggle('hidden'); },
    onkeydown: (e) => { if (e.key === 'Enter') log.classList.toggle('hidden'); } },
  h('div', { class: 'card-head' }, h('div', { class: 'card-title' }, m.subject || '(no subject)'), h('span', { class: 'card-sub' }, fmtTime(m.created_at))),
  h('div', { class: 'card-sub' }, m.sender),
  m.snippet ? h('div', { class: 'snippet' }, m.snippet) : null,
  h('div', { class: 'chips' }, m.runs.map((r) => h('span', { class: `chip ${STATUS_CHIP[r.status] || ''}` }, `${r.task_name}: ${r.status}`))),
  log);
}

// ── Integrations ────────────────────────────────────────────────────────────

async function viewIntegrations(main) {
  let data;
  try { data = await api('GET', '/api/integrations'); } catch (e) { toast(e.message, 'err'); return; }
  const reload = () => viewIntegrations(main);

  const anth = data.anthropic;
  const anthCard = h('div', { class: 'card accent-pink' },
    h('div', { class: 'card-head' },
      h('div', {}, h('div', { class: 'card-title' }, 'Anthropic API'),
        h('div', { class: 'card-sub' }, anth ? `Key ${anth.key_hint}` : 'Not connected. Needed for every agent step.')),
      h('button', { class: anth ? '' : 'primary', onclick: () => anthropicModal(reload) }, anth ? 'Replace key' : 'Connect')),
    anth ? h('div', { class: 'chips' }, h('span', { class: 'chip lime' }, 'connected')) : null);

  const gmailCards = data.gmail.map((g) => h('div', { class: 'card accent-aqua' },
    h('div', { class: 'card-head' },
      h('div', {}, h('div', { class: 'card-title' }, g.name), h('div', { class: 'card-sub' }, `${g.email} · From: ${g.from_name}`)),
      h('div', { class: 'btn-row' },
        h('button', { class: 'small', onclick: () => gmailModal(data.defaults, g, reload) }, 'Edit'),
        h('button', { class: 'small danger', onclick: () => deleteIntegration(g.id, g.name, reload) }, 'Delete'))),
    h('div', { class: 'chips' },
      h('span', { class: 'chip' }, `IMAP ${g.imap_host}:${g.imap_port}`),
      h('span', { class: 'chip' }, `SMTP ${g.smtp_host}:${g.smtp_port} SSL`),
      g.last_error ? h('span', { class: 'chip red', title: g.last_error }, 'poll error') : null),
    h('div', { class: 'mt' }, switchEl(g.smtp_enabled, async (on, input) => {
      input.disabled = true;
      try {
        await api('PATCH', `/api/integrations/gmail/${g.id}/smtp`, { enabled: on });
        toast(on ? 'Sending enabled (SMTP login verified).' : 'Sending disabled. Settings kept.', 'ok');
      } catch (e) { input.checked = !on; toast(e.message, 'err'); }
      input.disabled = false;
    }, 'Sending (SMTP)'))));

  const discordCards = data.discord.map((d) => h('div', { class: 'card accent-lime' },
    h('div', { class: 'card-head' },
      h('div', {}, h('div', { class: 'card-title' }, d.name), h('div', { class: 'card-sub' }, d.url_hint)),
      h('div', { class: 'btn-row' },
        h('button', { class: 'small', onclick: () => discordModal(d, reload) }, 'Edit'),
        h('button', { class: 'small danger', onclick: () => deleteIntegration(d.id, d.name, reload) }, 'Delete')))));

  page(main, 'Integrations', 'Every integration is tested before it is saved.', null,
    h('h2', {}, h('span', { class: 'dot pink' }), 'LLM access'), anthCard,
    h('h2', {}, h('span', { class: 'dot' }), 'Gmail', h('button', { class: 'small', onclick: () => gmailModal(data.defaults, null, reload) }, '+ Add Gmail')),
    gmailCards.length ? gmailCards : h('div', { class: 'empty' }, 'No Gmail inbox connected.'),
    h('h2', {}, h('span', { class: 'dot lime' }), 'Discord webhooks', h('button', { class: 'small', onclick: () => discordModal(null, reload) }, '+ Add webhook')),
    discordCards.length ? discordCards : h('div', { class: 'empty' }, 'No Discord webhook connected.'));
}

async function deleteIntegration(id, name, reload) {
  if (!(await confirmDialog('Delete integration', `Delete "${name}"? Its stored credentials are removed.`, 'Delete', true))) return;
  try { await api('DELETE', `/api/integrations/${id}`); toast('Deleted.', 'ok'); reload(); } catch (e) { toast(e.message, 'err'); }
}

function anthropicModal(reload) {
  const key = h('input', { type: 'password', autocomplete: 'off', placeholder: 'sk-ant-…' });
  const err = h('p', { class: 'error-box hidden' });
  modal('Anthropic API', 'The key is checked by listing the models it can use. No tokens are spent.',
    h('div', {}, err, field('API key', key, h('span', {}, 'Create one at ', h('a', { href: 'https://platform.claude.com/settings/keys', target: '_blank', rel: 'noopener noreferrer' }, 'platform.claude.com'), '.'))),
    (close) => [
      h('button', { onclick: close }, 'Cancel'),
      h('button', { class: 'primary', onclick: (e) => withBusy(e.currentTarget, async () => {
        err.classList.add('hidden');
        try {
          const r = await api('POST', '/api/integrations/anthropic', { api_key: key.value });
          toast(`Connected. ${r.model_count} models available.`, 'ok');
          close(); reload();
        } catch (ex) { err.textContent = ex.message; err.classList.remove('hidden'); }
      }) }, 'Test & save'),
    ]);
}

function gmailModal(defaults, g, reload) {
  const v = (x, d) => (g && g[x] !== undefined && g[x] !== null ? g[x] : d);
  const f = {
    name: h('input', { type: 'text', value: v('name', 'xMender'), maxlength: 128 }),
    email: h('input', { type: 'email', value: v('email', ''), placeholder: 'you@gmail.com', autocomplete: 'off' }),
    display_name: h('input', { type: 'text', value: v('display_name', ''), maxlength: 128 }),
    password: h('input', { type: 'password', autocomplete: 'off', placeholder: g ? '(unchanged)' : 'xxxx xxxx xxxx xxxx' }),
    smtp_enabled: h('input', { type: 'checkbox', checked: v('smtp_enabled', false) }),
    imap_host: h('input', { type: 'text', value: v('imap_host', defaults.imap_host) }),
    imap_port: h('input', { type: 'number', value: v('imap_port', defaults.imap_port), min: 1, max: 65535 }),
    smtp_host: h('input', { type: 'text', value: v('smtp_host', defaults.smtp_host) }),
    smtp_port: h('input', { type: 'number', value: v('smtp_port', defaults.smtp_port), min: 1, max: 65535 }),
  };
  const url = defaults.app_passwords_url;
  const pasteBtn = h('button', { type: 'button', title: 'Paste from clipboard', onclick: async () => {
    try {
      f.password.value = (await navigator.clipboard.readText()).trim();
      toast('Pasted from clipboard.', 'ok');
    } catch (_) { toast('Clipboard access was blocked by the browser; paste with Ctrl+V instead.', 'err'); }
  } }, 'Paste');
  if (!navigator.clipboard || !navigator.clipboard.readText) pasteBtn.disabled = true;

  const advanced = h('div', { class: 'hidden' },
    h('div', { class: 'grid-2' }, field('IMAP host', f.imap_host), field('IMAP port (SSL)', f.imap_port)),
    h('div', { class: 'grid-2' }, field('SMTP host', f.smtp_host), field('SMTP port (SSL)', f.smtp_port)));
  const err = h('p', { class: 'error-box hidden' });

  const body = h('div', {}, err,
    field('Name', f.name, 'Display name for xMender itself.'),
    field('Gmail address', f.email, 'Plain address, no + alias. Used as the From address when sending.'),
    field('Display name', f.display_name, 'Shown in the From field. Empty = the address itself.'),
    h('div', { class: 'callout aqua' },
      'Use an App Password made for xMender, not your Google password. 2-Step Verification must be on.',
      h('div', { class: 'btn-row mt' },
        h('a', { class: 'btn', href: url, target: '_blank', rel: 'noopener noreferrer' }, 'Open App Passwords ↗'),
        h('button', { type: 'button', onclick: async () => {
          try { await navigator.clipboard.writeText(url); toast('Link copied.', 'ok'); }
          catch (_) { toast(`Copy failed; the link is ${url}`, 'err'); }
        } }, 'Copy link'))),
    field('App password', h('div', { class: 'input-row' }, f.password, pasteBtn), g ? 'Leave empty to keep the stored one.' : 'Spaces are removed automatically.'),
    h('div', { class: 'field' }, h('label', { class: 'check' }, f.smtp_enabled, 'Enable sending (SMTP)'),
      h('div', { class: 'hint' }, 'Optional. Can be toggled later without re-entering anything.')),
    h('button', { type: 'button', class: 'ghost small', onclick: () => advanced.classList.toggle('hidden') }, 'Server settings ▾'),
    advanced,
    h('p', { class: 'small muted mt' }, 'Saving logs in to IMAP', ' (and SMTP if sending is on) to check the details. No email is sent.'));

  const payload = (save) => ({
    id: g ? g.id : null, save,
    name: f.name.value, email: f.email.value, display_name: f.display_name.value,
    password: f.password.value || null, smtp_enabled: f.smtp_enabled.checked,
    imap_host: f.imap_host.value, imap_port: Number(f.imap_port.value),
    smtp_host: f.smtp_host.value, smtp_port: Number(f.smtp_port.value),
  });
  const run = (save, close) => async (e) => withBusy(e.currentTarget, async () => {
    err.classList.add('hidden');
    try {
      await api('POST', '/api/integrations/gmail', payload(save));
      if (save) { toast('Gmail connected. Only new mail from now on is processed.', 'ok'); close(); reload(); }
      else toast('Connection test passed.', 'ok');
    } catch (ex) { err.textContent = ex.message; err.classList.remove('hidden'); }
  });
  modal(g ? 'Edit Gmail' : 'Connect Gmail', 'IMAP for receiving, SMTP (optional) for sending.', body, (close) => [
    h('button', { onclick: close }, 'Cancel'),
    h('button', { class: 'ternary', onclick: run(false, close) }, 'Test only'),
    h('button', { class: 'primary', onclick: run(true, close) }, 'Test & save'),
  ]);
}

function discordModal(d, reload) {
  const name = h('input', { type: 'text', value: d ? d.name : 'xMender', maxlength: 128 });
  const url = h('input', { type: 'url', autocomplete: 'off', placeholder: d ? '(unchanged)' : 'https://discord.com/api/webhooks/…' });
  const err = h('p', { class: 'error-box hidden' });
  modal(d ? 'Edit Discord webhook' : 'Connect Discord webhook',
    'Channel settings → Integrations → Webhooks → New Webhook → Copy Webhook URL.',
    h('div', {}, err,
      field('Name', name, 'Label for this webhook inside xMender. Messages use the name and avatar set on the webhook in Discord.'),
      field('Webhook URL', url, (d ? 'Leave empty to keep the stored one. ' : '') + 'Old discordapp.com and /api/vNN URLs are accepted and normalised. For a forum channel, add ?thread_id=… or a new thread is created per message.')),
    (close) => [
      h('button', { onclick: close }, 'Cancel'),
      h('button', { class: 'primary', onclick: () => {
        err.classList.add('hidden');
        discordTestChoice(async (mode) => {
          try {
            const r = await api('POST', '/api/integrations/discord', { id: d ? d.id : null, name: name.value, url: url.value || null, test: mode });
            toast(r.tested ? 'Test message sent and webhook saved.' : 'Webhook saved without testing.', 'ok');
            close(); reload();
          } catch (ex) { err.textContent = ex.message; err.classList.remove('hidden'); }
        });
      } }, 'Save…'),
    ]);
}

function discordTestChoice(done) {
  modal('Test the webhook?', null, h('div', {},
    h('div', { class: 'callout' },
      h('strong', {}, 'A real message will be posted. '),
      'Discord webhooks can only be verified by sending to them. Testing posts one embed titled ',
      h('code', {}, 'xMender Notification'), " into the webhook's channel, under the webhook's own name, visible to everyone there."),
    h('p', { class: 'small muted' }, 'Skipping saves without any check; a wrong URL only shows up when a task first tries to send.')),
  (close) => [
    h('button', { onclick: close }, 'Cancel'),
    h('button', { class: 'ternary', onclick: (e) => withBusy(e.currentTarget, async () => { await done('skip'); close(); }) }, 'Skip test & save'),
    h('button', { class: 'primary', onclick: (e) => withBusy(e.currentTarget, async () => { await done('send'); close(); }) }, 'Send test & save'),
  ]);
}

// ── Models ──────────────────────────────────────────────────────────────────

let modelCache = null;
async function getModels(refresh) {
  if (!modelCache || refresh) modelCache = await api('GET', '/api/llm/models' + (refresh ? '?refresh=true' : ''));
  return modelCache;
}

function modelSelect(models, value, defaultLabel) {
  const sel = h('select', {},
    defaultLabel ? h('option', { value: '' }, defaultLabel) : null,
    models.map((m) => h('option', { value: m.id }, `${m.display_name} (${m.id})`)));
  if (value && !models.some((m) => m.id === value)) sel.append(h('option', { value }, `${value} (not offered by provider)`));
  sel.value = value || '';
  return sel;
}

// ── Tasks ───────────────────────────────────────────────────────────────────

async function viewTasks(main, rest) {
  if (rest[0]) return viewTaskEditor(main, rest[0]);
  let data, meta;
  try { [data, meta] = await Promise.all([api('GET', '/api/tasks'), api('GET', '/api/tasks/meta')]); } catch (e) { toast(e.message, 'err'); return; }
  const inbox = Object.fromEntries(meta.gmail.map((g) => [g.id, g]));
  const label = Object.fromEntries(meta.step_types.map((s) => [s.type, s.label]));
  const group = Object.fromEntries(meta.step_types.map((s) => [s.type, s.group]));
  const newBtn = h('button', { class: 'primary', onclick: () => { location.hash = '#/tasks/new'; } }, '+ New task');
  if (!meta.gmail.length) newBtn.disabled = true;

  page(main, 'Tasks', 'Each new email runs through every enabled task of its inbox, step by step. A filter that does not match ends the chain.', newBtn,
    !meta.gmail.length ? h('div', { class: 'callout aqua' }, 'Connect a Gmail inbox first. ', can('integrations') ? h('a', { href: '#/integrations' }, 'Go to Integrations') : null) : null,
    data.tasks.length ? data.tasks.map((t) => h('div', { class: 'card accent-' + (t.enabled ? 'lime' : 'aqua') },
      h('div', { class: 'card-head' },
        h('div', {}, h('div', { class: 'card-title' }, t.name),
          h('div', { class: 'card-sub' }, inbox[t.gmail_integration_id] ? inbox[t.gmail_integration_id].email : 'unknown inbox')),
        h('div', { class: 'btn-row' },
          switchEl(t.enabled, async (on, input) => {
            input.disabled = true;
            try { await api('PUT', `/api/tasks/${t.id}`, { ...t, enabled: on }); t.enabled = on; toast(on ? 'Task enabled.' : 'Task paused.', 'ok'); }
            catch (e) { input.checked = !on; toast(e.message, 'err'); }
            input.disabled = false;
          }, 'Enabled'),
          h('button', { class: 'small', onclick: () => { location.hash = `#/tasks/${t.id}`; } }, 'Edit'),
          h('button', { class: 'small danger', onclick: async () => {
            if (!(await confirmDialog('Delete task', `Delete "${t.name}"? Past activity stays visible.`, 'Delete', true))) return;
            try { await api('DELETE', `/api/tasks/${t.id}`); toast('Task deleted.', 'ok'); viewTasks(main, []); } catch (e) { toast(e.message, 'err'); }
          } }, 'Delete'))),
      h('div', { class: 'chips' }, t.steps.map((s, i) => h('span', { class: 'chip ' + (GROUP_CHIP[group[s.type]] || '') }, `${i + 1}. ${label[s.type] || s.type}`)))))
      : h('div', { class: 'empty' }, 'No tasks yet.'));
}

const GROUP_CHIP = { filter: 'aqua', agent: 'lime', action: 'pink' };
const STEP_DEFAULTS = {
  filter_builtin: () => ({ from: '', to: '', subject: '', has_words: '', not_words: '', regex: false, has_attachment: null,
    attachment_ext: '', attachment_name: '', attachment_type: '', attachment_min_kb: null, attachment_max_kb: null }),
  filter_agent: () => ({ instructions: '', model: null }),
  webhook_agent: () => ({ instructions: '', model: null, discord_integration_id: null }),
};
// Default step names on add; a number is appended when taken.
const STEP_NAME_BASE = { filter_builtin: 'filter', filter_agent: 'ai_filter', webhook_agent: 'notify' };
// Output fields per type, mirroring the server. Filters also output `matched`.
const STEP_OUTPUTS = {};
const COND_OPS = [['equals', 'equals'], ['not_equals', 'does not equal'], ['contains', 'contains'],
  ['in', 'is one of'], ['not_in', 'is not one of'], ['is_set', 'is set'], ['is_empty', 'is empty']];
const VALUE_OPS = ['equals', 'not_equals', 'contains', 'in', 'not_in'];

function stepOutputs(step, env) {
  const out = STEP_OUTPUTS[step.type] ? STEP_OUTPUTS[step.type](step.config || {}) : [];
  return env.groupOf[step.type] === 'filter' ? ['matched', ...out] : out;
}

function bindIn(c, key, el, conv) {
  el.addEventListener('input', () => { c[key] = conv ? conv(el.value) : el.value; });
  return el;
}

function choice(options, value, onchange) {
  const sel = h('select', {}, options.map(([v, l]) => h('option', { value: v }, l)));
  sel.value = value;
  sel.addEventListener('change', () => onchange(sel.value));
  return sel;
}

function discordSelect(c, env) {
  const dsel = h('select', {}, h('option', { value: '' }, env.meta.discord.length ? 'Pick a webhook…' : 'No Discord webhook connected'),
    env.meta.discord.map((d) => h('option', { value: d.id }, d.name)));
  dsel.value = c.discord_integration_id || '';
  dsel.addEventListener('change', () => { c.discord_integration_id = dsel.value ? Number(dsel.value) : null; });
  return field('Discord webhook', dsel);
}

function modelField(c, env) {
  const mdl = modelSelect(env.models.models, c.model, env.defaultLabel);
  mdl.addEventListener('change', () => { c.model = mdl.value || null; });
  return field('Model', mdl, env.models.error ? env.models.error : 'Models are listed live from the provider.');
}

function instructionsField(c, placeholder, hint) {
  const ins = bindIn(c, 'instructions', h('textarea', { placeholder }));
  ins.value = c.instructions || '';
  return field('Instructions', ins, hint);
}

const STEP_FORMS = {
  filter_builtin(c) {
    const kb = (v) => (v.trim() === '' ? null : Number(v));
    const details = h('div', { class: 'att-details' },
      h('div', { class: 'grid-2' },
        field('File types', bindIn(c, 'attachment_ext', h('input', { type: 'text', value: c.attachment_ext || '', placeholder: 'pdf, docx' }))),
        field('File name', bindIn(c, 'attachment_name', h('input', { type: 'text', value: c.attachment_name || '', placeholder: 'invoice*, receipt-*.pdf' })))),
      h('div', { class: 'grid-3' },
        field('Content type', bindIn(c, 'attachment_type', h('input', { type: 'text', value: c.attachment_type || '', placeholder: 'image/, application/pdf' }))),
        field('Min size (KB)', bindIn(c, 'attachment_min_kb', h('input', { type: 'number', min: 0, value: c.attachment_min_kb ?? '' }), kb)),
        field('Max size (KB)', bindIn(c, 'attachment_max_kb', h('input', { type: 'number', min: 0, value: c.attachment_max_kb ?? '' }), kb))),
      h('div', { class: 'hint' }, 'Optional. At least one attachment must match every detail you fill in. Several values: separate with ",".'));
    const att = h('select', {}, h('option', { value: '' }, 'Either'), h('option', { value: 'yes' }, 'Has attachment'), h('option', { value: 'no' }, 'No attachment'));
    att.value = c.has_attachment === true ? 'yes' : c.has_attachment === false ? 'no' : '';
    const syncAtt = () => details.classList.toggle('hidden', att.value === 'no');
    att.addEventListener('change', () => { c.has_attachment = att.value === 'yes' ? true : att.value === 'no' ? false : null; syncAtt(); });
    syncAtt();
    const hint = h('div', { class: 'hint gap' });
    const syncHint = () => {
      hint.textContent = c.regex
        ? 'Regex mode: each text field is one case-insensitive regular expression, searched anywhere in the field (use | for alternatives).'
        : 'Case-insensitive. From/To/Subject: any of several values separated by "," or " OR ". Words: all must appear; use "quotes" for phrases.';
    };
    syncHint();
    return [
      h('div', { class: 'grid-2' },
        field('From', bindIn(c, 'from', h('input', { type: 'text', value: c.from || '', placeholder: 'billing@, shop.com' }))),
        field('To', bindIn(c, 'to', h('input', { type: 'text', value: c.to || '' })))),
      field('Subject', bindIn(c, 'subject', h('input', { type: 'text', value: c.subject || '', placeholder: 'invoice OR receipt' }))),
      h('div', { class: 'grid-2' },
        field('Has the words', bindIn(c, 'has_words', h('input', { type: 'text', value: c.has_words || '', placeholder: 'order "shipped"' }))),
        field("Doesn't have", bindIn(c, 'not_words', h('input', { type: 'text', value: c.not_words || '' })))),
      h('label', { class: 'check mb' }, h('input', { type: 'checkbox', checked: !!c.regex, onchange: (e) => { c.regex = e.target.checked; syncHint(); } }),
        'Use regular expressions'),
      hint,
      field('Attachment', att),
      details,
    ];
  },
  filter_agent(c, env) {
    return [
      instructionsField(c, 'Describe which emails should pass. e.g. "Emails from a real person asking me something that needs a reply."',
        'The model sees the email and these instructions; the email passes only if its reply ends with FILTER MATCH.'),
      modelField(c, env),
    ];
  },
  webhook_agent(c, env) {
    return [
      discordSelect(c, env),
      instructionsField(c, 'Describe the notification. e.g. "Summarise in 2 bullet points and list any due dates."',
        'The model\'s reply is posted as an aqua embed titled "xMender Notification".'),
      modelField(c, env),
    ];
  },
};

// "Run this step" condition on an earlier named step's output.
function whenField(step, idx, env) {
  const prior = env.task.steps.slice(0, idx).filter((s) => s.name);
  const box = h('div', { class: 'when-row' });
  const stepSel = h('select', {}, h('option', { value: '' }, 'Always'),
    prior.map((s) => h('option', { value: s.name }, `Only if ${s.name}…`)));
  stepSel.value = step.when && prior.some((s) => s.name === step.when.step) ? step.when.step : '';

  function draw() {
    const ref = prior.find((s) => s.name === stepSel.value);
    if (!ref) {
      step.when = null;
      box.replaceChildren(stepSel);
      return;
    }
    const cur = step.when && step.when.step === ref.name ? step.when : {};
    const outs = stepOutputs(ref, env);
    const fieldSel = h('select', {}, outs.map((o) => h('option', { value: o }, o === 'matched' ? 'match result' : o)));
    fieldSel.value = cur.op === 'matched' || cur.op === 'not_matched' ? 'matched' : (outs.includes(cur.field) ? cur.field : outs[0] || '');
    const opSel = h('select', {});
    const val = h('input', { type: 'text', value: Array.isArray(cur.value) ? cur.value.join(', ') : (cur.value || '') });

    function sync() {
      const op = opSel.value;
      const needsValue = VALUE_OPS.includes(op);
      val.classList.toggle('hidden', !needsValue);
      val.placeholder = op === 'in' || op === 'not_in' ? 'a, b, c' : 'value';
      step.when = { step: ref.name, op };
      if (fieldSel.value !== 'matched') step.when.field = fieldSel.value;
      if (needsValue) step.when.value = val.value;
    }
    function drawOps() {
      const ops = fieldSel.value === 'matched' ? [['matched', 'matched'], ['not_matched', 'did not match']] : COND_OPS;
      opSel.replaceChildren(...ops.map(([v, l]) => h('option', { value: v }, l)));
      opSel.value = ops.some(([v]) => v === cur.op) ? cur.op : ops[0][0];
      sync();
    }
    fieldSel.addEventListener('change', drawOps);
    opSel.addEventListener('change', sync);
    val.addEventListener('input', sync);
    box.replaceChildren(stepSel, fieldSel, opSel, val);
    drawOps();
  }
  stepSel.addEventListener('change', draw);
  draw();
  return field('Run this step', box, prior.length ? null : 'Name an earlier step to run this one only in some cases.');
}

function stepOptions(step, idx, env) {
  const isFilter = env.groupOf[step.type] === 'filter';
  let before = step.name || '';
  const name = h('input', { type: 'text', value: step.name || '', maxlength: 32, placeholder: 'e.g. invoice', spellcheck: 'false' });
  name.addEventListener('input', () => { step.name = name.value.trim().toLowerCase(); });
  name.addEventListener('change', () => {
    // Keep later conditions pointing at this step after a rename.
    if (before && step.name) {
      for (const s of env.task.steps.slice(idx + 1)) if (s.when && s.when.step === before) s.when.step = step.name;
    }
    before = step.name;
    env.redraw();
  });
  const rows = [
    h('div', { class: 'grid-2' },
      field('Name', name, 'Later steps can use this step\'s result by its name.'),
      field('If this step fails', choice([['stop', 'Stop the task'], ['continue', 'Continue with the next step']],
        step.on_error || 'stop', (v) => { step.on_error = v; }))),
  ];
  if (isFilter) {
    rows.push(h('div', { class: 'grid-2' },
      field("If it doesn't match", choice([['stop', 'Stop the task'], ['continue', 'Continue (later steps can check the result)']],
        step.on_no_match || 'stop', (v) => { step.on_no_match = v; })),
      field('Invert', h('label', { class: 'check' },
        h('input', { type: 'checkbox', checked: !!step.negate, onchange: (e) => { step.negate = e.target.checked; } }),
        'Pass when the filter does not match'))));
  }
  rows.push(whenField(step, idx, env));

  const bits = [step.when && step.when.step ? `if ${step.when.step}` : null, step.negate ? 'inverted' : null,
    step.on_no_match === 'continue' ? 'continues on no match' : null, step.on_error === 'continue' ? 'continues on error' : null].filter(Boolean);
  const det = h('details', { class: 'step-opts' },
    h('summary', {}, 'Options', bits.length ? h('span', { class: 'muted' }, ' · ' + bits.join(' · ')) : null), rows);
  if (env.open.has(step)) det.open = true;
  det.addEventListener('toggle', () => { if (det.open) env.open.add(step); else env.open.delete(step); });
  return det;
}

async function viewTaskEditor(main, id) {
  let meta, task, models = { models: [] };
  try {
    meta = await api('GET', '/api/tasks/meta');
    if (id !== 'new') {
      const all = await api('GET', '/api/tasks');
      task = all.tasks.find((t) => String(t.id) === id);
      if (!task) throw new Error('Task not found.');
    }
    if (meta.has_anthropic) models = await getModels();
  } catch (e) { toast(e.message, 'err'); location.hash = '#/tasks'; return; }

  task = task ? structuredClone(task) : { name: '', enabled: true, gmail_integration_id: meta.gmail[0] && meta.gmail[0].id, steps: [] };
  const label = Object.fromEntries(meta.step_types.map((s) => [s.type, s.label]));
  const env = {
    meta, models, task,
    groupOf: Object.fromEntries(meta.step_types.map((s) => [s.type, s.group])),
    defaultLabel: meta.default_model ? `Default (${meta.default_model})` : 'Default (none set in Settings)',
    open: new WeakSet(),
    redraw: () => drawSteps(),
  };

  const name = h('input', { type: 'text', value: task.name, maxlength: 128, placeholder: 'e.g. Invoices to Discord' });
  const inbox = h('select', {}, meta.gmail.map((g) => h('option', { value: g.id }, `${g.name} · ${g.email}`)));
  inbox.value = task.gmail_integration_id || '';
  const enabled = h('input', { type: 'checkbox', checked: task.enabled });
  const stepsBox = h('div', {});
  const err = h('p', { class: 'error-box hidden' });

  function stepForm(step, idx) {
    const form = STEP_FORMS[step.type];
    const body = form ? form(step.config, env) : h('div', { class: 'muted small' }, 'Unknown step type.');
    const move = (d) => () => { const j = idx + d; [task.steps[idx], task.steps[j]] = [task.steps[j], task.steps[idx]]; drawSteps(); };
    return h('div', { class: 'step', dataset: { type: step.type, group: env.groupOf[step.type] || '' } },
      h('div', { class: 'step-head' },
        h('div', { class: 'title' }, h('span', { class: 'n' }, `#${idx + 1}`), label[step.type] || step.type,
          step.name ? h('span', { class: 'chip step-name' }, step.name) : null),
        h('div', { class: 'btn-row' },
          h('button', { class: 'ghost small', title: 'Move up', 'aria-label': 'Move up', disabled: idx === 0, onclick: move(-1) }, '↑'),
          h('button', { class: 'ghost small', title: 'Move down', 'aria-label': 'Move down', disabled: idx === task.steps.length - 1, onclick: move(1) }, '↓'),
          h('button', { class: 'ghost small', title: 'Remove', 'aria-label': 'Remove step', onclick: () => { task.steps.splice(idx, 1); drawSteps(); } }, '✕'))),
      h('div', {}, body),
      stepOptions(step, idx, env));
  }

  function drawSteps() {
    stepsBox.replaceChildren(...(task.steps.length ? task.steps.flatMap((s, i) => [
      i ? h('div', { class: 'step-arrow' }, '↓ then') : null, stepForm(s, i)]).filter(Boolean)
      : [h('div', { class: 'empty' }, 'No steps yet. Add a filter, then an action.')]));
  }
  drawSteps();

  function uniqueName(type) {
    const base = STEP_NAME_BASE[type] || type;
    let n = 1;
    while (task.steps.some((s) => s.name === (n === 1 ? base : base + n))) n++;
    return n === 1 ? base : base + n;
  }

  const groups = [];
  for (const s of meta.step_types) {
    let g = groups.find((x) => x.group === s.group);
    if (!g) groups.push(g = { group: s.group, label: s.group_label, items: [] });
    g.items.push(s);
  }
  const addSel = h('select', {}, groups.map((g) => h('optgroup', { label: g.label },
    g.items.map((s) => h('option', { value: s.type }, s.label)))));
  const saveBtn = h('button', { class: 'primary', onclick: () => withBusy(saveBtn, async () => {
    err.classList.add('hidden');
    const body = { name: name.value, gmail_integration_id: Number(inbox.value), enabled: enabled.checked, steps: task.steps };
    try {
      if (id === 'new') await api('POST', '/api/tasks', body); else await api('PUT', `/api/tasks/${id}`, body);
      toast('Task saved.', 'ok');
      location.hash = '#/tasks';
    } catch (e) { err.textContent = e.message; err.classList.remove('hidden'); window.scrollTo(0, 0); main.scrollTop = 0; }
  }) }, 'Save task');

  page(main, id === 'new' ? 'New task' : 'Edit task', null,
    [h('button', { onclick: () => { location.hash = '#/tasks'; } }, 'Cancel'), saveBtn],
    err,
    !meta.has_anthropic ? h('div', { class: 'callout' }, 'Agent steps need the Anthropic integration. ', can('integrations') ? h('a', { href: '#/integrations' }, 'Connect it') : null) : null,
    h('div', { class: 'card' },
      h('div', { class: 'grid-2' }, field('Name', name), field('Inbox', inbox)),
      h('label', { class: 'check' }, enabled, 'Enabled')),
    h('h2', {}, h('span', { class: 'dot' }), 'Steps'),
    stepsBox,
    h('div', { class: 'add-step' }, addSel, h('button', { onclick: () => {
      task.steps.push({ type: addSel.value, name: uniqueName(addSel.value), config: STEP_DEFAULTS[addSel.value]() });
      drawSteps();
    } }, '+ Add step')));
}

// ── Settings ────────────────────────────────────────────────────────────────

async function viewSettings(main) {
  const modelBox = h('div', {});
  const cur = h('input', { type: 'password', autocomplete: 'current-password' });
  const pw = h('input', { type: 'password', autocomplete: 'new-password' });
  const pw2 = h('input', { type: 'password', autocomplete: 'new-password' });
  const pwBtn = h('button', { class: 'primary', onclick: () => withBusy(pwBtn, async () => {
    if (pw.value !== pw2.value) { toast('Passwords do not match.', 'err'); return; }
    try {
      await api('POST', '/api/auth/password', { current_password: cur.value, new_password: pw.value });
      cur.value = pw.value = pw2.value = '';
      toast('Password changed. Other sessions were signed out.', 'ok');
    } catch (e) { toast(e.message, 'err'); }
  }) }, 'Change password');

  const usageBox = h('div', {});
  page(main, 'Settings', `Signed in as ${S.me.username}.`, null,
    h('h2', {}, h('span', { class: 'dot pink' }), 'Default model'),
    h('div', { class: 'card' }, modelBox),
    h('h2', {}, h('span', { class: 'dot lime' }), 'API usage'),
    usageBox,
    h('h2', {}, h('span', { class: 'dot' }), 'Password'),
    h('div', { class: 'card' }, field('Current password', cur), h('div', { class: 'grid-2' }, field('New password', pw, 'At least 10 characters.'), field('Repeat', pw2)), pwBtn));

  async function drawModels(refresh) {
    modelBox.replaceChildren(h('div', { class: 'muted small' }, 'Loading models…'));
    let m;
    try { m = await getModels(refresh); } catch (e) { modelBox.replaceChildren(h('p', { class: 'error-box' }, e.message)); return; }
    if (!m.models.length) {
      modelBox.replaceChildren(h('p', { class: 'small muted' }, m.error || 'No models available.'));
      return;
    }
    const sel = modelSelect(m.models, S.me.default_model, '(none)');
    const save = h('button', { class: 'primary', onclick: () => withBusy(save, async () => {
      try {
        const r = await api('PUT', '/api/me/settings', { default_model: sel.value || null });
        S.me = r.user; modelCache = null;
        toast('Default model saved.', 'ok');
      } catch (e) { toast(e.message, 'err'); }
    }) }, 'Save');
    modelBox.replaceChildren(
      field('Model used by agent steps that do not pick their own', sel, 'List comes live from Anthropic.'),
      h('div', { class: 'btn-row' }, save, h('button', { class: 'ghost', onclick: () => drawModels(true) }, icon(ICONS.refresh), 'Reload list')));
  }
  drawModels(false);
  drawUsage(usageBox);
}

const USAGE_PERIODS = [['today', 'Today'], ['7d', '7 days'], ['30d', '30 days'], ['month', 'This month'], ['all', 'All time']];
const usageView = { period: '30d', scope: 'me' };

async function drawUsage(box) {
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  const periods = h('div', { class: 'btn-row' }, USAGE_PERIODS.map(([k, label]) => h('button', {
    class: 'chip' + (usageView.period === k ? ' aqua' : ''),
    onclick: () => { usageView.period = k; drawUsage(box); },
  }, label)));
  const scope = S.me.is_admin ? switchEl(usageView.scope === 'all', (on) => { usageView.scope = on ? 'all' : 'me'; drawUsage(box); }, 'All users') : null;
  const body = h('div', { class: 'muted small mt' }, 'Loading usage…');
  box.replaceChildren(h('div', { class: 'card' }, h('div', { class: 'card-head' }, periods, scope), body));

  let u;
  try { u = await api('GET', `/api/usage?period=${usageView.period}&scope=${usageView.scope}&tz=${encodeURIComponent(tz)}`); }
  catch (e) { body.replaceChildren(h('p', { class: 'error-box mb0' }, e.message)); return; }

  const t = u.total;
  const cacheTokens = t.cache_read_tokens + t.cache_write_5m_tokens + t.cache_write_1h_tokens;
  const stat = (label, value, sub, title) => h('div', { class: 'stat' }, h('div', { class: 'stat-label' }, label),
    h('div', { class: 'stat-value', title: title || null }, value), sub ? h('div', { class: 'stat-sub' }, sub) : null);
  const tiles = h('div', { class: 'stats' },
    stat('Cost', fmtUsd(t.cost_nanousd), t.unpriced ? `+ ${t.unpriced} call${t.unpriced > 1 ? 's' : ''} without a known price` : 'USD, estimated', exactUsd(t.cost_nanousd)),
    stat('Calls', fmtNum(t.requests), 'model attempts'),
    stat('Input tokens', fmtNum(t.input_tokens + cacheTokens), cacheTokens ? `${fmtNum(t.cache_read_tokens)} cache read · ${fmtNum(t.cache_write_5m_tokens + t.cache_write_1h_tokens)} cache write` : 'uncached'),
    stat('Output tokens', fmtNum(t.output_tokens)));

  if (!t.requests) {
    body.replaceChildren(tiles, h('div', { class: 'empty mt' }, 'No Anthropic calls recorded in this period. Usage is recorded from the moment this version runs; earlier calls are not included.'));
    return;
  }

  const costCell = (r) => h('td', { class: 'num', title: exactUsd(r.cost_nanousd) + (r.unpriced ? ` + ${r.unpriced} unpriced` : '') },
    r.unpriced && !r.cost_nanousd ? h('span', { class: 'chip pink' }, 'price unknown') : fmtUsd(r.cost_nanousd));
  const tokenCells = (r) => [
    h('td', { class: 'num' }, fmtNum(r.requests)),
    h('td', { class: 'num' }, fmtNum(r.input_tokens + r.cache_read_tokens + r.cache_write_5m_tokens + r.cache_write_1h_tokens)),
    h('td', { class: 'num' }, fmtNum(r.output_tokens)),
    costCell(r),
  ];
  const table = (first, rows, extraHead, extra) => h('div', { class: 'table-wrap' }, h('table', { class: 'usage' },
    h('thead', {}, h('tr', {}, h('th', {}, first), extraHead ? h('th', {}, extraHead) : null,
      h('th', { class: 'num' }, 'Calls'), h('th', { class: 'num' }, 'Input'), h('th', { class: 'num' }, 'Output'), h('th', { class: 'num' }, 'Cost'))),
    h('tbody', {}, rows.map((r) => h('tr', {}, h('td', {}, r.label), extra ? h('td', { class: 'muted' }, extra(r)) : null, tokenCells(r))))));

  body.replaceChildren(tiles,
    h('h3', { class: 'usage-h' }, 'By model'),
    table('Model', u.models.map((r) => ({ ...r, label: r.model })), 'Rate in / out per MTok',
      (r) => (r.rates ? `${fmtRate(r.rates.input)} / ${fmtRate(r.rates.output)}` : 'unknown')),
    h('h3', { class: 'usage-h' }, 'By task'),
    table('Task', u.tasks.map((r) => ({ ...r, label: r.task }))),
    h('h3', { class: 'usage-h' }, 'By day'),
    table('Day', u.days.map((r) => ({ ...r, label: r.day }))),
    h('p', { class: 'hint mb0 mt' }, `Calculated from the token counts Anthropic returns with each call and list prices as of ${u.prices_as_of} (`,
      h('a', { href: u.pricing_url, target: '_blank', rel: 'noopener noreferrer' }, 'pricing'),
      '). Refusals that fall back to another model are counted as billed, so the total can be slightly above your invoice. Hover a cost for the exact value.'));
}

// ── Admin ───────────────────────────────────────────────────────────────────

async function viewAdmin(main) {
  let data, settings;
  try { [data, settings] = await Promise.all([api('GET', '/api/admin/users'), api('GET', '/api/admin/settings')]); } catch (e) { toast(e.message, 'err'); return; }
  const reload = () => viewAdmin(main);

  const rows = data.users.map((u) => {
    const permBoxes = data.permissions.map((p) => {
      const cb = h('input', { type: 'checkbox', checked: u.is_admin || u.permissions.includes(p), disabled: u.is_admin });
      cb.addEventListener('change', async () => {
        const perms = data.permissions.filter((x) => (x === p ? cb.checked : u.permissions.includes(x)));
        try { const r = await api('PATCH', `/api/admin/users/${u.id}`, { permissions: perms }); u.permissions = r.user.permissions; toast('Permissions updated.', 'ok'); }
        catch (e) { cb.checked = !cb.checked; toast(e.message, 'err'); }
      });
      return h('label', { class: 'check small' }, cb, p);
    });
    const actions = [];
    if (!u.is_root) {
      actions.push(h('button', { class: 'small', onclick: async () => {
        try { await api('PATCH', `/api/admin/users/${u.id}`, { is_admin: !u.is_admin }); toast('Role updated.', 'ok'); reload(); } catch (e) { toast(e.message, 'err'); }
      } }, u.is_admin ? 'Remove admin' : 'Make admin'));
    }
    if (!u.is_root || S.me.is_root) actions.push(h('button', { class: 'small', onclick: () => resetPasswordModal(u) }, 'Set password'));
    if (!u.is_root && u.id !== S.me.id) {
      actions.push(h('button', { class: 'small danger', onclick: async () => {
        if (!(await confirmDialog('Delete user', `Delete "${u.username}" with all their integrations, tasks and history?`, 'Delete', true))) return;
        try { await api('DELETE', `/api/admin/users/${u.id}`); toast('User deleted.', 'ok'); reload(); } catch (e) { toast(e.message, 'err'); }
      } }, 'Delete'));
    }
    return h('tr', {},
      h('td', {}, u.username),
      h('td', {}, h('span', { class: 'chip ' + (u.is_root ? 'pink' : u.is_admin ? 'aqua' : '') }, u.is_root ? 'owner' : u.is_admin ? 'admin' : 'user')),
      h('td', {}, h('div', { class: 'btn-row' }, permBoxes)),
      h('td', {}, h('div', { class: 'btn-row end' }, actions)));
  });

  const nu = h('input', { type: 'text', autocomplete: 'off' });
  const np = h('input', { type: 'password', autocomplete: 'new-password' });
  const na = h('input', { type: 'checkbox' });
  const addBtn = h('button', { class: 'primary', onclick: () => withBusy(addBtn, async () => {
    try {
      await api('POST', '/api/admin/users', { username: nu.value, password: np.value, is_admin: na.checked, permissions: data.permissions });
      toast('User created.', 'ok'); reload();
    } catch (e) { toast(e.message, 'err'); }
  }) }, 'Add user');

  page(main, 'Admin', 'Users and app-wide settings.', null,
    h('h2', {}, h('span', { class: 'dot pink' }), 'Registration'),
    h('div', { class: 'card' }, switchEl(settings.registration_enabled, async (on, input) => {
      try { await api('PUT', '/api/admin/settings', { registration_enabled: on }); toast(on ? 'Anyone who can reach this page can now create an account.' : 'Account creation disabled.', 'ok'); }
      catch (e) { input.checked = !on; toast(e.message, 'err'); }
    }, 'Allow account creation from the login page'),
    h('div', { class: 'hint small muted mt' }, 'Off by default. New accounts get the integrations and tasks permissions.')),
    h('h2', {}, h('span', { class: 'dot' }), 'Users'),
    h('div', { class: 'card table-wrap' }, h('table', {},
      h('thead', {}, h('tr', {}, h('th', {}, 'User'), h('th', {}, 'Role'), h('th', {}, 'Permissions'), h('th', {}))),
      h('tbody', {}, rows))),
    h('h2', {}, h('span', { class: 'dot lime' }), 'Add user'),
    h('div', { class: 'card' },
      h('div', { class: 'grid-2' }, field('Username', nu), field('Password', np, 'At least 10 characters.')),
      h('div', { class: 'btn-row' }, h('label', { class: 'check' }, na, 'Admin'), addBtn)));
}

function resetPasswordModal(u) {
  const pw = h('input', { type: 'password', autocomplete: 'new-password' });
  modal(`Set password for ${u.username}`, 'Their other sessions are signed out.', field('New password', pw, 'At least 10 characters.'), (close) => [
    h('button', { onclick: close }, 'Cancel'),
    h('button', { class: 'primary', onclick: async () => {
      try { await api('PATCH', `/api/admin/users/${u.id}`, { password: pw.value }); toast('Password set.', 'ok'); close(); } catch (e) { toast(e.message, 'err'); }
    } }, 'Save'),
  ]);
}

boot();

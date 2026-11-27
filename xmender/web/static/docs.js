'use strict';
/* xMender docs viewer. One renderer for both the in-app modal (app.js
   openDocs()) and the standalone /docs page, so both always show the same
   content: Markdown files under /static/docs/, ordered by docs/index.json.

   Supported Markdown (a small subset; see .claude/skills/docs-maintenance):
   # / ## / ### headings (optional explicit id: "## Title {#my-id}"),
   paragraphs, - and 1. lists (indent 2 spaces to nest), ``` code blocks,
   | tables |, > callouts (first line "[!tip]" / "[!warning]" picks a colour),
   `code`, **bold**, *italic*, [links](https://...) and doc links
   [text](#section) or [text](#section/heading-id).
   All DOM is built with textContent; Markdown is never turned into HTML. */

const XDocs = (() => {
  function el(tag, attrs, ...children) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class') e.className = v;
      else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
      else if (k === 'dataset') Object.assign(e.dataset, v);
      else e.setAttribute(k, v === true ? '' : String(v));
    }
    for (const c of children.flat(Infinity)) {
      if (c === null || c === undefined || c === false) continue;
      e.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return e;
  }

  // Must match slug() in tests/test_docs.py.
  function slug(text) {
    return text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  }

  // ── Markdown → block tree ────────────────────────────────────────────────

  const LIST_RE = /^([-*]|\d+\.)\s+(.*)$/;
  const isBlockStart = (l) => /^(#{1,4}\s|```|>|\|)/.test(l) || LIST_RE.test(l);
  // Table cells split on unescaped "|"; write "\|" for a literal pipe.
  const cells = (l) => l.trim().replace(/^\|/, '').replace(/(?<!\\)\|$/, '').split(/(?<!\\)\|/)
    .map((c) => c.trim().replace(/\\\|/g, '|'));

  function parseBlocks(md) {
    const lines = md.replace(/\r\n?/g, '\n').split('\n');
    const out = [];
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      let m;
      if (!line.trim()) { i++; continue; }
      if (line.startsWith('```')) {
        const buf = [];
        for (i++; i < lines.length && !lines[i].startsWith('```'); i++) buf.push(lines[i]);
        i++;
        out.push({ t: 'code', text: buf.join('\n') });
      } else if ((m = /^(#{1,4})\s+(.*?)(?:\s+\{#([a-z0-9_-]+)\})?\s*$/.exec(line))) {
        out.push({ t: 'h', level: m[1].length, text: m[2], id: m[3] || slug(m[2]) });
        i++;
      } else if (line.startsWith('>')) {
        const buf = [];
        for (; i < lines.length && lines[i].startsWith('>'); i++) buf.push(lines[i].replace(/^>\s?/, ''));
        const k = /^\[!(note|tip|warning)\]\s*$/i.exec(buf[0] || '');
        if (k) buf.shift();
        out.push({ t: 'callout', kind: k ? k[1].toLowerCase() : 'note', blocks: parseBlocks(buf.join('\n')) });
      } else if (line.startsWith('|')) {
        const head = cells(line);
        const rows = [];
        for (i++; i < lines.length && lines[i].startsWith('|'); i++) {
          if (/^\|[\s:|-]+$/.test(lines[i].trim())) continue;
          rows.push(cells(lines[i]));
        }
        out.push({ t: 'table', head, rows });
      } else if ((m = LIST_RE.exec(line))) {
        const ordered = /\d/.test(m[1]);
        const items = [];
        while (i < lines.length) {
          const l = lines[i];
          const mm = LIST_RE.exec(l);
          if (mm) {
            if (/\d/.test(mm[1]) !== ordered) break;
            items.push([mm[2]]);
          } else if (/^\s+\S/.test(l)) {
            items[items.length - 1].push(l.replace(/^ {1,4}/, ''));
          } else if (!l.trim() && i + 1 < lines.length && /^\s+\S/.test(lines[i + 1])) {
            items[items.length - 1].push('');
          } else break;
          i++;
        }
        out.push({ t: 'list', ordered, items: items.map((it) => parseBlocks(it.join('\n'))) });
      } else {
        const buf = [];
        for (; i < lines.length && lines[i].trim() && !isBlockStart(lines[i]); i++) buf.push(lines[i].trim());
        out.push({ t: 'p', text: buf.join(' ') });
      }
    }
    return out;
  }

  // Inline: `code`, **bold**, *italic*, [text](href). Returns tokens.
  const INLINE_RE = /`([^`]+)`|\*\*(.+?)\*\*|\*(?=\S)(.+?)(?<=\S)\*|\[([^\]]+)\]\(([^)\s]+)\)/g;
  function parseInline(text) {
    const out = [];
    let last = 0;
    for (const m of text.matchAll(INLINE_RE)) {
      if (m.index > last) out.push({ t: 'text', text: text.slice(last, m.index) });
      if (m[1] !== undefined) out.push({ t: 'code', text: m[1] });
      else if (m[2] !== undefined) out.push({ t: 'b', kids: parseInline(m[2]) });
      else if (m[3] !== undefined) out.push({ t: 'i', kids: parseInline(m[3]) });
      else out.push({ t: 'a', href: m[5], kids: parseInline(m[4]) });
      last = m.index + m[0].length;
    }
    if (last < text.length) out.push({ t: 'text', text: text.slice(last) });
    return out;
  }

  function plainInline(tokens) {
    return tokens.map((k) => (k.kids ? plainInline(k.kids) : k.text)).join('');
  }
  function plain(blocks) {
    return blocks.map((b) => {
      if (b.t === 'p' || b.t === 'h') return plainInline(parseInline(b.text));
      if (b.t === 'code') return b.text;
      if (b.t === 'callout') return plain(b.blocks);
      if (b.t === 'list') return b.items.map(plain).join(' ');
      if (b.t === 'table') return [b.head, ...b.rows].map((r) => r.map((c) => plainInline(parseInline(c))).join(' ')).join(' ');
      return '';
    }).join(' ');
  }

  // A section: title from its "# " line, headings for the TOC, and search
  // chunks (one per ##/### heading, plus the intro).
  function parseSection(meta, md) {
    const blocks = parseBlocks(md);
    const h1 = blocks.find((b) => b.t === 'h' && b.level === 1);
    const title = h1 ? plainInline(parseInline(h1.text)) : meta.title;
    const headings = blocks.filter((b) => b.t === 'h' && (b.level === 2 || b.level === 3))
      .map((b) => ({ id: b.id, level: b.level, text: plainInline(parseInline(b.text)) }));
    const chunks = [];
    let cur = { anchor: null, heading: title, blocks: [] };
    for (const b of blocks) {
      if (b.t === 'h' && b.level === 1) continue;
      if (b.t === 'h' && (b.level === 2 || b.level === 3)) {
        chunks.push(cur);
        cur = { anchor: b.id, heading: plainInline(parseInline(b.text)), blocks: [] };
      } else cur.blocks.push(b);
    }
    chunks.push(cur);
    return {
      id: meta.id, title, group: meta.group, blocks, headings,
      chunks: chunks.map((c) => ({ anchor: c.anchor, heading: c.heading, text: plain(c.blocks).replace(/\s+/g, ' ').trim() }))
        .filter((c) => c.text || c.anchor),
    };
  }

  let loading = null;
  function load() {
    if (!loading) {
      loading = (async () => {
        const res = await fetch('/static/docs/index.json', { cache: 'no-cache' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const index = await res.json();
        const metas = index.groups.flatMap((g) => g.sections.map((s) => ({ ...s, group: g.title })));
        const texts = await Promise.all(metas.map(async (s) => {
          const r = await fetch(`/static/docs/${s.file}`, { cache: 'no-cache' });
          if (!r.ok) throw new Error(`${s.file}: HTTP ${r.status}`);
          return r.text();
        }));
        const sections = metas.map((s, i) => parseSection(s, texts[i]));
        return { groups: index.groups.map((g) => g.title), sections, byId: Object.fromEntries(sections.map((s) => [s.id, s])) };
      })();
      loading.catch(() => { loading = null; });
    }
    return loading;
  }

  // ── Viewer ───────────────────────────────────────────────────────────────

  function splitAddr(addr) {
    const [sec, anchor] = String(addr || '').replace(/^#/, '').split('/');
    return [sec || '', anchor || ''];
  }
  const plainClick = (e) => e.button === 0 && !e.ctrlKey && !e.metaKey && !e.shiftKey && !e.altKey;

  /* Render the docs into `root`. opts.start: "section" or "section/heading".
     opts.onChange(addr) runs on every navigation. opts.scroller: element
     that scrolls the content (defaults to the content pane). Returns
     {go(addr)} or null if loading failed. */
  async function mount(root, opts = {}) {
    root.replaceChildren(el('div', { class: 'muted small docs-loading' }, 'Loading docs…'));
    let data;
    try { data = await load(); } catch (e) {
      root.replaceChildren(el('p', { class: 'error-box' }, `Could not load the docs (${e.message}).`));
      return null;
    }
    const search = el('input', { type: 'search', class: 'docs-search', placeholder: 'Search the docs…', 'aria-label': 'Search the docs', spellcheck: 'false' });
    const toc = el('nav', { class: 'docs-toc', 'aria-label': 'Docs sections' });
    const content = el('article', { class: 'docs-content' });
    root.replaceChildren(el('div', { class: 'docs' }, el('aside', { class: 'docs-side' }, search, toc), content));
    const scroller = opts.scroller || content;
    let current = data.sections[0];

    const docLink = (addr, children, cls) => el('a', {
      href: `/docs#${addr}`, class: cls || null,
      onclick: (e) => { if (plainClick(e)) { e.preventDefault(); go(addr); } },
    }, children);

    function inline(tokens) {
      return tokens.map((k) => {
        if (k.t === 'text') return k.text;
        if (k.t === 'code') return el('code', {}, k.text);
        if (k.t === 'b') return el('strong', {}, inline(k.kids));
        if (k.t === 'i') return el('em', {}, inline(k.kids));
        if (k.href.startsWith('#')) return docLink(k.href.slice(1), inline(k.kids));
        return el('a', { href: k.href, target: '_blank', rel: 'noopener noreferrer' }, inline(k.kids));
      });
    }
    const CALLOUT = { note: 'callout aqua', tip: 'callout lime', warning: 'callout' };
    function render(blocks, sec) {
      return blocks.map((b) => {
        if (b.t === 'p') return el('p', {}, inline(parseInline(b.text)));
        if (b.t === 'h') {
          const tag = 'h' + Math.min(b.level, 4);
          if (b.level === 1) return el(tag, {}, inline(parseInline(b.text)));
          return el(tag, { dataset: { anchor: b.id } }, inline(parseInline(b.text)),
            docLink(`${sec.id}/${b.id}`, '#', 'docs-permalink'));
        }
        if (b.t === 'code') return el('pre', { class: 'docs-code' }, el('code', {}, b.text));
        if (b.t === 'callout') return el('div', { class: CALLOUT[b.kind] }, render(b.blocks, sec));
        if (b.t === 'list') return el(b.ordered ? 'ol' : 'ul', {}, b.items.map((it) => el('li', {}, render(it, sec))));
        if (b.t === 'table') {
          return el('div', { class: 'table-wrap' }, el('table', { class: 'docs-table' },
            el('thead', {}, el('tr', {}, b.head.map((c) => el('th', {}, inline(parseInline(c)))))),
            el('tbody', {}, b.rows.map((r) => el('tr', {}, r.map((c) => el('td', {}, inline(parseInline(c)))))))));
        }
        return null;
      });
    }

    function drawToc(active) {
      toc.replaceChildren(...data.groups.map((g) => el('div', { class: 'docs-group' },
        el('div', { class: 'docs-group-title' }, g),
        data.sections.filter((s) => s.group === g).map((s) => [
          docLink(s.id, s.title, 'docs-toc-item' + (s === active ? ' active' : '')),
          s === active && s.headings.length ? el('div', { class: 'docs-toc-sub' },
            s.headings.map((hd) => docLink(`${s.id}/${hd.id}`, hd.text, `docs-toc-item sub${hd.level === 3 ? ' l3' : ''}`))) : null,
        ]))));
    }

    function pager(sec) {
      const i = data.sections.indexOf(sec);
      const prev = data.sections[i - 1];
      const next = data.sections[i + 1];
      return el('div', { class: 'docs-pager' },
        prev ? docLink(prev.id, ['← ', prev.title], 'btn') : el('span'),
        next ? docLink(next.id, [next.title, ' →'], 'btn') : el('span'));
    }

    function go(addr, silent) {
      const [sid, anchor] = splitAddr(addr);
      const sec = data.byId[sid] || data.sections[0];
      search.value = '';
      current = sec;
      content.replaceChildren(...render(sec.blocks, sec), pager(sec));
      drawToc(sec);
      const target = anchor ? content.querySelector(`[data-anchor="${CSS.escape(anchor)}"]`) : null;
      if (target) {
        target.scrollIntoView({ block: 'start' });
        target.classList.add('docs-flash');
      } else scroller.scrollTop = 0;
      if (!silent && opts.onChange) opts.onChange(sec.id + (target ? '/' + anchor : ''));
    }

    function snippet(text, terms) {
      const lower = text.toLowerCase();
      const at = Math.max(0, ...terms.map((t) => lower.indexOf(t)).filter((x) => x >= 0).slice(0, 1));
      const start = Math.max(0, at - 60);
      return (start ? '…' : '') + text.slice(start, start + 200) + (start + 200 < text.length ? '…' : '');
    }
    function highlight(text, terms) {
      const re = new RegExp(`(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi');
      return text.split(re).map((part, i) => (i % 2 ? el('mark', {}, part) : part));
    }

    function runSearch() {
      const q = search.value.trim();
      const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
      if (!terms.length) { go(current.id, true); return; }
      const hits = [];
      for (const sec of data.sections) {
        for (const ch of sec.chunks) {
          const head = `${sec.title} ${ch.heading}`.toLowerCase();
          const hay = `${head} ${ch.text.toLowerCase()}`;
          if (!terms.every((t) => hay.includes(t))) continue;
          const score = terms.filter((t) => ch.heading.toLowerCase().includes(t)).length * 3
            + terms.filter((t) => sec.title.toLowerCase().includes(t)).length;
          hits.push({ sec, ch, score });
        }
      }
      hits.sort((a, b) => b.score - a.score);
      drawToc(null);
      content.replaceChildren(
        el('h1', {}, 'Search'),
        el('p', { class: 'muted small' }, hits.length ? `${hits.length} result${hits.length > 1 ? 's' : ''} for “${q}”.` : `Nothing found for “${q}”. Try fewer or shorter words.`),
        el('div', { class: 'docs-hits' }, hits.slice(0, 60).map(({ sec, ch }) => docLink(ch.anchor ? `${sec.id}/${ch.anchor}` : sec.id, [
          el('div', { class: 'docs-hit-title' }, highlight(ch.anchor ? `${sec.title} › ${ch.heading}` : sec.title, terms)),
          ch.text ? el('div', { class: 'docs-hit-text' }, highlight(snippet(ch.text, terms), terms)) : null,
        ], 'docs-hit'))));
      scroller.scrollTop = 0;
    }
    let timer = null;
    search.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(runSearch, 120); });
    search.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && search.value) { e.stopPropagation(); search.value = ''; runSearch(); }
      if (e.key === 'Enter') { const first = content.querySelector('.docs-hit'); if (first) first.click(); }
    });

    go(opts.start || data.sections[0].id, true);
    if (opts.focusSearch) search.focus();
    return { go };
  }

  // ── Standalone page (/docs) ──────────────────────────────────────────────

  async function page(root) {
    const body = el('div', { class: 'docs-page-body' });
    root.replaceChildren(el('div', { class: 'docs-page' },
      el('header', { class: 'docs-page-head' },
        el('a', { href: '/', class: 'docs-brand' }, el('span', { class: 'wordmark' }, 'xMender'), el('span', { class: 'muted' }, ' docs')),
        el('a', { href: '/', class: 'btn small' }, 'Open xMender')),
      body, XBuild.footer()));
    const addr = () => decodeURIComponent(location.hash.replace(/^#/, ''));
    const view = await mount(body, {
      start: addr(),
      scroller: document.scrollingElement,
      onChange: (a) => { if (addr() !== a) history.pushState(null, '', '#' + a); },
    });
    // Back/forward and hand-edited URLs (pushState itself fires no hashchange).
    if (view) window.addEventListener('hashchange', () => view.go(addr(), true));
  }

  document.addEventListener('DOMContentLoaded', () => {
    const root = document.getElementById('docs-app');
    if (root) page(root);
  });

  return { mount, load, slug };
})();

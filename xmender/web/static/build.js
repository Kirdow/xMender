'use strict';
/* xMender build footer: commit hash and date of the running instance, shared by
   the app (app.js) and the standalone /docs page (docs.js). The hash links to
   the commit on GitHub. /api/version is fetched once per page load. */

const XBuild = (() => {
  let info = null;

  function load() {
    if (!info) {
      info = fetch('/api/version', { credentials: 'same-origin' })
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null);
    }
    return info;
  }

  function fmtDate(iso) {
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    const p = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  }

  function text(tag, cls, value) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    e.textContent = value;
    return e;
  }

  // Returns the <footer> at once and fills it when the info arrives.
  function footer() {
    const el = document.createElement('footer');
    el.className = 'build-footer';
    load().then((b) => {
      if (!b) return;
      if (!b.commit) { el.replaceChildren(text('span', null, `xMender ${b.version}`)); return; }
      const short = b.commit.slice(0, 7);
      let hash;
      if (b.url) {
        hash = text('a', 'build-hash', short);
        hash.href = b.url;
        hash.target = '_blank';
        hash.rel = 'noopener';
        hash.title = `View commit ${b.commit} on GitHub`;
      } else {
        hash = text('span', 'build-hash', short);
      }
      const date = text('time', null, fmtDate(b.date));
      date.dateTime = b.date;
      const parts = [text('span', null, 'xMender '), hash];
      if (b.dirty) parts.push(text('span', 'build-dirty', ' +modified'));
      parts.push(text('span', 'build-sep', ' · '), date);
      el.replaceChildren(...parts);
    });
    return el;
  }

  return { footer, load };
})();

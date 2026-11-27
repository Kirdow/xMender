// Registers the service worker that makes xMender installable (see /sw.js).
'use strict';
if ('serviceWorker' in navigator && window.isSecureContext) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => { /* app works without it */ });
  });
}

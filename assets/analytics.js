/* Knight Labs — anonymous site analytics
 *
 * Measures three things the admin dashboard reports:
 *   daily visitors, average time on site, and add-to-cart events.
 *
 * What is collected: a random visitor id (localStorage), a random session id
 * (sessionStorage), the page path, and timestamps. Nothing else. No IP
 * addresses, no names, no emails, no cross-site anything. Browsers sending
 * Do Not Track are skipped entirely.
 *
 * Failures are swallowed — analytics must never affect the storefront.
 */
(function () {
  'use strict';

  // Respect Do Not Track / Global Privacy Control.
  var dnt = navigator.doNotTrack || window.doNotTrack || navigator.msDoNotTrack;
  if (dnt === '1' || dnt === 'yes' || navigator.globalPrivacyControl === true) return;

  var VISITOR_KEY = 'knightLabsVisitor';
  var SESSION_KEY = 'knightLabsSession';
  var HEARTBEAT_MS = 15000;

  function randomId() {
    try {
      var buf = new Uint8Array(12);
      crypto.getRandomValues(buf);
      return Array.prototype.map.call(buf, function (b) {
        return ('0' + b.toString(16)).slice(-2);
      }).join('');
    } catch (e) {
      return String(Date.now()) + Math.random().toString(16).slice(2);
    }
  }

  function stored(store, key) {
    try {
      var value = store.getItem(key);
      if (!value) {
        value = randomId();
        store.setItem(key, value);
      }
      return value;
    } catch (e) {
      // Private mode with storage blocked — track this page view only.
      return randomId();
    }
  }

  var visitor = stored(localStorage, VISITOR_KEY);
  var session = stored(sessionStorage, SESSION_KEY);
  var path = location.pathname.replace(/^.*\//, '') || 'index.html';

  function send(event, extra, useBeacon) {
    var body = JSON.stringify(Object.assign({
      event: event, visitor: visitor, session: session, path: path
    }, extra || {}));
    try {
      // sendBeacon survives the page being closed; fetch does not.
      if (useBeacon && navigator.sendBeacon) {
        navigator.sendBeacon('/api/track', new Blob([body], { type: 'application/json' }));
        return;
      }
      fetch('/api/track', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body,
        keepalive: true
      }).catch(function () {});
    } catch (e) { /* ignore */ }
  }

  send('view');

  // Heartbeats give a time-on-site figure even when the page is never closed
  // cleanly. Paused while the tab is hidden so background tabs don't inflate it.
  var timer = setInterval(function () {
    if (document.visibilityState === 'visible') send('ping');
  }, HEARTBEAT_MS);

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') send('end', null, true);
    else send('ping');
  });
  window.addEventListener('pagehide', function () {
    clearInterval(timer);
    send('end', null, true);
  });

  /* ---------- add-to-cart events ---------- */

  // Every page writes the cart through localStorage.setItem, whatever the
  // button handler looks like. Wrapping setItem catches all of them in one
  // place rather than guessing at selectors per page.
  function cartQty(raw) {
    try {
      var items = JSON.parse(raw || '[]');
      if (!Array.isArray(items)) return 0;
      return items.reduce(function (n, i) { return n + (parseInt(i.qty, 10) || 0); }, 0);
    } catch (e) { return 0; }
  }

  try {
    var nativeSetItem = localStorage.setItem.bind(localStorage);
    localStorage.setItem = function (key, value) {
      if (key !== 'knightLabsCart') return nativeSetItem(key, value);
      var before = 0;
      try { before = cartQty(localStorage.getItem(key)); } catch (e) {}
      var result = nativeSetItem(key, value);
      var after = cartQty(value);
      // Only count genuine additions, not removals or quantity decreases.
      if (after > before) send('add_to_cart', { qty: after - before });
      return result;
    };
  } catch (e) { /* leave the cart alone if patching fails */ }
})();

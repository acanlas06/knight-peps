/* Knight Labs — site-wide theme
 *
 * Applies the light/dark choice to every page and ties it to the signed-in
 * account, so the preference follows the user rather than the browser tab.
 *
 * Storage:
 *   knightLabsTheme_<email>  per-account preference (wins when signed in)
 *   knightLabsTheme_guest    preference while signed out
 *
 * This file must load as a BLOCKING script in <head>, before any content
 * renders. Deferring it causes a visible flash of the light theme first.
 */
(function () {
  'use strict';

  var GUEST_KEY = 'knightLabsTheme_guest';
  var LEGACY_KEY = 'knightLabsDarkMode';

  function currentEmail() {
    try {
      var raw = localStorage.getItem('knightLabsLoggedIn');
      return raw ? (JSON.parse(raw).email || '') : '';
    } catch (e) {
      return '';
    }
  }

  function keyFor(email) {
    return email ? 'knightLabsTheme_' + email : GUEST_KEY;
  }

  function readPreference() {
    var email = currentEmail();
    var stored = null;
    try {
      stored = localStorage.getItem(keyFor(email));
      // Fall back to the old global flag so existing users keep their choice.
      if (stored === null && localStorage.getItem(LEGACY_KEY) !== null) {
        stored = localStorage.getItem(LEGACY_KEY) === 'true' ? 'dark' : 'light';
      }
    } catch (e) {
      stored = null;
    }
    if (stored === 'dark' || stored === 'light') return stored;
    return 'light';
  }

  function apply(theme) {
    var dark = theme === 'dark';
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
    // The account dashboard styles itself off body.dark-mode, so keep both in
    // sync. <body> does not exist yet on first run, hence the readyState check.
    function syncBody() {
      if (document.body) document.body.classList.toggle('dark-mode', dark);
    }
    if (document.body) {
      syncBody();
    } else {
      document.addEventListener('DOMContentLoaded', syncBody);
    }
  }

  var api = {
    get: function () {
      return readPreference();
    },
    isDark: function () {
      return readPreference() === 'dark';
    },
    set: function (theme) {
      var value = theme === 'dark' ? 'dark' : 'light';
      var email = currentEmail();
      try {
        localStorage.setItem(keyFor(email), value);
        // Once a signed-in user chooses, the legacy global flag is noise.
        if (email) localStorage.removeItem(LEGACY_KEY);
      } catch (e) { /* storage unavailable — still apply for this page */ }
      apply(value);
      return value;
    },
    toggle: function () {
      return api.set(readPreference() === 'dark' ? 'light' : 'dark');
    },
    /* Called after sign-in/sign-out so the new identity's theme takes effect. */
    refresh: function () {
      apply(readPreference());
      return readPreference();
    }
  };

  window.KnightTheme = api;
  apply(readPreference());
})();

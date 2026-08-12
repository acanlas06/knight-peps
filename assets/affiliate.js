/* Knight Labs — affiliate / promo code helper
 *
 * Captures ?ref=AC links and remembers the code while browsing.
 *
 * The list of codes is deliberately NOT in this file. It used to be, which
 * meant anyone could read page source and find every active discount. Codes
 * now live in affiliates.json on the server and are managed from the admin
 * page; the browser asks about one code at a time via /api/validate-affiliate,
 * so unpublished codes cannot be discovered.
 *
 * validate() learns the rule for a code. discountFor() then applies that rule
 * locally, so editing the cart does not need another round-trip. Neither is
 * trusted: the server recomputes the discount from its own store when the
 * order is placed.
 */
(function () {
  var STORAGE_KEY = 'knightLabsAffiliateCode';

  function normalise(value) {
    return String(value || '').trim().toUpperCase().replace(/[^A-Z0-9_-]/g, '').slice(0, 40);
  }

  function save(code) {
    code = normalise(code);
    try {
      if (code) localStorage.setItem(STORAGE_KEY, code);
      else localStorage.removeItem(STORAGE_KEY);
    } catch (e) {}
    return code;
  }

  function saved() {
    try { return normalise(localStorage.getItem(STORAGE_KEY) || ''); }
    catch (e) { return ''; }
  }

  function captureFromUrl() {
    try {
      var params = new URLSearchParams(window.location.search || '');
      var code = params.get('ref') || params.get('affiliate') || params.get('code') || '';
      if (code) save(code);
    } catch (e) {}
  }

  function round2(n) { return Math.round(Number(n || 0) * 100) / 100; }

  /* Apply an already-validated rule to a subtotal. Mirrors the server:
     a percentage of the subtotal, or a fixed amount capped at the subtotal so
     a total can never go negative. */
  function discountFor(rule, subtotal) {
    subtotal = Math.max(0, Number(subtotal || 0));
    if (!rule || !rule.code) {
      return { valid: false, code: '', discountAmount: 0, total: subtotal };
    }
    var value = Number(rule.value || 0);
    var discount = rule.type === 'amount'
      ? Math.min(value, subtotal)
      : subtotal * value / 100;
    discount = round2(discount);
    return {
      valid: true,
      code: rule.code,
      label: rule.label || rule.code,
      type: rule.type || 'percent',
      value: value,
      percent: rule.type === 'amount' ? 0 : value,
      discountAmount: discount,
      total: Math.max(0, round2(subtotal - discount))
    };
  }

  /* Ask the server whether a code is usable. Resolves to a rule object or
     null; never rejects, so a network failure cannot leave checkout stuck. */
  function validate(code, subtotal) {
    code = normalise(code);
    if (!code) return Promise.resolve(null);
    return fetch('/api/validate-affiliate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: code, subtotal: Number(subtotal || 0) })
    }).then(function (res) {
      return res.json().catch(function () { return {}; });
    }).then(function (data) {
      if (!data || !data.valid) return null;
      return {
        code: data.code || code,
        label: data.label || data.code || code,
        type: data.type || 'percent',
        value: Number(data.value || 0)
      };
    }).catch(function () { return null; });
  }

  /* Human-readable description of a rule, for status lines. */
  function describe(rule) {
    if (!rule) return '';
    if (rule.type === 'amount') {
      return '$' + Number(rule.value || 0).toFixed(2) + ' off';
    }
    return Number(rule.value || 0) + '% off';
  }

  captureFromUrl();

  window.KL_AFFILIATES = {
    normalise: normalise,
    save: save,
    saved: saved,
    validate: validate,
    discountFor: discountFor,
    describe: describe,
    storageKey: STORAGE_KEY
  };
})();

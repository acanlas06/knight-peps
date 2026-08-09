/* Knight Labs — affiliate / promo code helper
 * Captures ?ref=AC links, remembers the code while browsing, and provides the
 * same public discount preview that the server validates at order time.
 */
(function () {
  var STORAGE_KEY = 'knightLabsAffiliateCode';
  var RULES = {
    AC: { label: 'AC Affiliate', percent: 15, active: true }
  };

  function normalise(value) {
    return String(value || '').trim().toUpperCase().replace(/[^A-Z0-9_-]/g, '').slice(0, 40);
  }

  function ruleFor(code) {
    code = normalise(code);
    var rule = RULES[code];
    if (!code || !rule || !rule.active) return null;
    return { code: code, label: rule.label || code, percent: Number(rule.percent || 0) };
  }

  function save(code) {
    code = normalise(code);
    if (code) localStorage.setItem(STORAGE_KEY, code);
    else localStorage.removeItem(STORAGE_KEY);
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

  function preview(code, subtotal) {
    var rule = ruleFor(code);
    if (!rule) return { valid: false, code: normalise(code), discountAmount: 0, total: Number(subtotal || 0) };
    var discount = Math.round(Number(subtotal || 0) * rule.percent) / 100;
    return {
      valid: true,
      code: rule.code,
      label: rule.label,
      percent: rule.percent,
      discountAmount: Math.round(discount * 100) / 100,
      total: Math.max(0, Math.round((Number(subtotal || 0) - discount) * 100) / 100)
    };
  }

  captureFromUrl();

  window.KL_AFFILIATES = {
    rules: RULES,
    normalise: normalise,
    ruleFor: ruleFor,
    save: save,
    saved: saved,
    preview: preview,
    storageKey: STORAGE_KEY
  };
})();

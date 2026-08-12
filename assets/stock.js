/* Knight Labs — sold-out states
 *
 * Reads /api/stock, which returns counts keyed "slug|size", and reflects them:
 *
 *   Catalog and category grids — a card only reads sold out when every one of
 *   its sizes is tracked and at or below zero. If one size is still available,
 *   the card stays live.
 *
 *   Product detail pages — each size is handled individually: sold-out sizes are
 *   disabled in the size selector, and the whole page goes sold out only when
 *   nothing is left.
 *
 * Sizes with no stock entry are untracked and treated as available, so
 * inventory is opt-in per size. Orders are never blocked by stock.
 */
(function () {
  'use strict';

  // Only purchasable sizes — mirrors the product page selector and KL_PRICES.
  var SIZES = {
    'retatrutide': ['10mg', '20mg', '30mg'],
    'tirzepatide': ['10mg', '20mg', '30mg'],
    'semaglutide': ['5mg', '10mg'],
    'bpc-157': ['10mg'],
    'tb500': ['10mg'],
    'bpc-157-tb500-blend': ['5mg + 5mg', '10mg + 10mg'],
    'cjc-1295-without-dac-ipamorelin': ['5mg + 5mg', '10mg + 10mg'],
    'ipamorelin': ['5mg', '10mg'],
    'cjc-1295-without-dac-mod-grf-1-29': ['2mg', '5mg'],
    'nad': ['500mg'],
    'glutathione': ['600mg', '1200mg'],
    'epithalon': ['10mg', '50mg'],
    'semax': ['10mg'],
    'selank': ['10mg'],
    'ghk-cu': ['50mg'],
    'tesamorelin': ['2mg', '5mg', '10mg', '20mg'],
    'bac-water': ['3ml', '10ml']
  };



  var STYLE = [
    '.kl-soldout-badge{position:absolute;top:48px;left:12px;z-index:3;',
    'background:#c23b33;color:#fff;font-size:10px;font-weight:900;letter-spacing:.1em;',
    'text-transform:uppercase;padding:5px 11px;border-radius:999px;',
    'box-shadow:0 4px 14px rgba(20,15,3,.24)}',
    '.kl-soldout img{filter:grayscale(.85) opacity(.55)}',
    '.kl-soldout .card-price,.kl-soldout .card-title{opacity:.6}',
    '.kl-stock-note{margin-top:12px;border:1px solid rgba(229,83,75,.42);',
    'background:rgba(229,83,75,.1);color:#c23b33;border-radius:12px;padding:12px 14px;',
    'font-weight:900;font-size:14px}',
    '.kl-stock-low{border-color:rgba(212,175,55,.5);background:rgba(212,175,55,.12);color:#8c6713}',
    'button.kl-disabled,a.kl-disabled{background:#e3ddcd!important;color:#9a9384!important;',
    'border-color:#d3ccba!important;cursor:not-allowed!important;box-shadow:none!important;',
    'filter:grayscale(1);pointer-events:none}',
    '.option.kl-size-out{opacity:.45;text-decoration:line-through;cursor:not-allowed;pointer-events:none}'
  ].join('');

  function injectStyle() {
    if (document.getElementById('kl-stock-style')) return;
    var el = document.createElement('style');
    el.id = 'kl-stock-style';
    el.textContent = STYLE;
    document.head.appendChild(el);
  }

  function slugFromHref(href) {
    var match = String(href || '').match(/product-([a-z0-9-]+)\.html/i);
    return match ? match[1] : '';
  }

  function key(slug, size) { return slug + '|' + size; }
  function has(stock, k) { return Object.prototype.hasOwnProperty.call(stock, k); }

  function sizeSoldOut(stock, slug, size) {
    var k = key(slug, size);
    return has(stock, k) && stock[k] <= 0;
  }

  // Sold out only when every size is tracked AND every one is gone. A single
  // untracked or in-stock size keeps the product available.
  function productSoldOut(stock, slug) {
    var sizes = SIZES[slug];
    if (!sizes || !sizes.length) return false;
    var tracked = sizes.filter(function (s) { return has(stock, key(slug, s)); });
    if (!tracked.length || tracked.length !== sizes.length) return false;
    return sizes.every(function (s) { return stock[key(slug, s)] <= 0; });
  }

  function markCard(card, imageHost) {
    card.classList.add('kl-soldout');
    if (getComputedStyle(card).position === 'static') card.style.position = 'relative';
    if (!card.querySelector('.kl-soldout-badge')) {
      var badge = document.createElement('span');
      badge.className = 'kl-soldout-badge';
      badge.textContent = 'Sold out';
      (imageHost || card).appendChild(badge);
    }
  }

  function applyToGrids(stock) {
    document.querySelectorAll('a.supply-card').forEach(function (card) {
      var slug = slugFromHref(card.getAttribute('href'));
      if (!productSoldOut(stock, slug)) return;
      markCard(card, card.querySelector('.vial-area'));
      var price = card.querySelector('.card-price');
      if (price) price.textContent = 'Sold out';
    });

    document.querySelectorAll('article.card').forEach(function (card) {
      var link = card.querySelector('a[href*="product-"]');
      var slug = slugFromHref(link && link.getAttribute('href'));
      if (!productSoldOut(stock, slug)) return;
      markCard(card, card.querySelector('.product-photo'));
      card.querySelectorAll('.btn.primary').forEach(function (btn) {
        btn.classList.add('kl-disabled');
        btn.textContent = 'Sold out';
      });
    });
  }

  function applyToProductPage(stock) {
    var stage = document.querySelector('.product-stage');
    var info = document.querySelector('.product-info');
    if (!stage || !info) return;

    var slug = slugFromHref(location.pathname);
    var sizes = SIZES[slug];
    if (!slug || !sizes) return;

    var out = sizes.filter(function (s) { return sizeSoldOut(stock, slug, s); });
    var available = sizes.filter(function (s) { return !sizeSoldOut(stock, slug, s); });

    // Strike through and disable the sold-out size options.
    var options = info.querySelectorAll('.option');
    // data-size is what the cart actually receives, so prefer it over label text.
    function labelOf(opt) {
      return (opt.getAttribute('data-size') || opt.textContent || '').trim();
    }
    options.forEach(function (opt) {
      var label = labelOf(opt);
      if (out.indexOf(label) < 0) return;
      opt.classList.add('kl-size-out');
      opt.setAttribute('aria-disabled', 'true');
      opt.title = label + ' is sold out';
      // If a dead size was preselected, move to one that is available.
      if (opt.classList.contains('active') && available.length) {
        opt.classList.remove('active');
        options.forEach(function (other) {
          if (labelOf(other) === available[0]) other.click();
        });
      }
    });

    var note = document.createElement('div');
    note.id = 'kl-stock-note';

    if (!available.length) {
      // Every size gone — the whole product is unavailable.
      stage.classList.add('kl-soldout');
      markCard(stage, stage);
      note.className = 'kl-stock-note';
      note.textContent = 'This product is sold out. Check back soon or contact us about restock timing.';
      if (!document.getElementById('kl-stock-note')) info.appendChild(note);
      info.querySelectorAll('button, .btn').forEach(function (el) {
        var label = (el.textContent || '').toLowerCase();
        if (label.indexOf('cart') >= 0 || label.indexOf('buy') >= 0 || label.indexOf('checkout') >= 0) {
          el.classList.add('kl-disabled');
          el.setAttribute('aria-disabled', 'true');
          if (el.tagName === 'BUTTON') el.disabled = true;
          el.textContent = 'Sold out';
        }
      });
      return;
    }

    if (out.length) {
      note.className = 'kl-stock-note';
      note.textContent = 'Sold out: ' + out.join(', ') + '. Other sizes are available.';
      if (!document.getElementById('kl-stock-note')) info.appendChild(note);
      return;
    }

    // Nothing sold out — flag anything nearly gone.
    var low = available.filter(function (s) {
      var k = key(slug, s);
      return has(stock, k) && stock[k] > 0 && stock[k] <= 5;
    }).map(function (s) { return s + ' (' + stock[key(slug, s)] + ' left)'; });
    if (low.length && !document.getElementById('kl-stock-note')) {
      note.className = 'kl-stock-note kl-stock-low';
      note.textContent = 'Low stock — ' + low.join(', ') + '.';
      info.appendChild(note);
    }
  }

  function init() {
    fetch('/api/stock')
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (!data || !data.ok || !data.stock) return;
        injectStyle();
        applyToGrids(data.stock);
        applyToProductPage(data.stock);
      })
      .catch(function () { /* server down — leave the page as-is */ });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

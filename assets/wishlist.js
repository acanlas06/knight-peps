/* Knight Labs — wishlist hearts
 *
 * Injects a clickable heart into the top-right corner of every product image
 * on the catalog grid, the category grids, and product detail pages.
 *
 * Wishlist entries are stored per signed-in account under
 *   knightLabsWishlist_<email>
 * so each account keeps its own list. Guests are prompted to sign in.
 */
(function () {
  'use strict';

  var LOGIN_KEY = 'knightLabsLoggedIn';

  function currentEmail() {
    try {
      var raw = localStorage.getItem(LOGIN_KEY);
      return raw ? (JSON.parse(raw).email || '') : '';
    } catch (e) {
      return '';
    }
  }

  function wishlistKey(email) {
    return 'knightLabsWishlist_' + email;
  }

  function readWishlist(email) {
    if (!email) return [];
    try {
      var list = JSON.parse(localStorage.getItem(wishlistKey(email)) || '[]');
      return Array.isArray(list) ? list : [];
    } catch (e) {
      return [];
    }
  }

  function writeWishlist(email, list) {
    if (!email) return;
    localStorage.setItem(wishlistKey(email), JSON.stringify(list));
  }

  function inWishlist(email, slug) {
    return readWishlist(email).some(function (item) { return item.slug === slug; });
  }

  /* ---------- toast ---------- */

  var toastEl = null;
  var toastTimer = null;

  function toast(message, actionLabel, actionHref) {
    if (!toastEl) {
      toastEl = document.createElement('div');
      toastEl.style.cssText =
        'position:fixed;left:50%;bottom:26px;transform:translate(-50%,18px);' +
        'background:#11100b;color:#fff7df;border:1px solid rgba(212,175,55,.38);' +
        'border-radius:999px;padding:13px 20px;font:850 14px/1.3 "DM Sans",system-ui,sans-serif;' +
        'box-shadow:0 20px 60px rgba(0,0,0,.32);opacity:0;pointer-events:none;' +
        'transition:opacity .22s,transform .22s;z-index:120;display:flex;align-items:center;gap:12px';
      document.body.appendChild(toastEl);
    }
    toastEl.innerHTML = '';
    toastEl.appendChild(document.createTextNode(message));
    if (actionLabel && actionHref) {
      var link = document.createElement('a');
      link.href = actionHref;
      link.textContent = actionLabel;
      link.style.cssText = 'color:#fff0a8;text-decoration:underline;font-weight:950';
      toastEl.appendChild(link);
      toastEl.style.pointerEvents = 'auto';
    } else {
      toastEl.style.pointerEvents = 'none';
    }
    toastEl.style.opacity = '1';
    toastEl.style.transform = 'translate(-50%,0)';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      toastEl.style.opacity = '0';
      toastEl.style.transform = 'translate(-50%,18px)';
      toastEl.style.pointerEvents = 'none';
    }, actionLabel ? 5000 : 2600);
  }

  /* ---------- heart button ---------- */

  function styleHeart(btn, active, offsetTop, offsetRight) {
    btn.style.cssText =
      'position:absolute;top:' + offsetTop + 'px;right:' + offsetRight + 'px;z-index:3;' +
      'width:38px;height:38px;display:flex;align-items:center;justify-content:center;' +
      'border-radius:999px;cursor:pointer;font-size:19px;line-height:1;padding:0;' +
      'background:' + (active ? 'linear-gradient(135deg,#fff0a8,#d4af37)' : 'rgba(255,253,248,.92)') + ';' +
      'border:1px solid ' + (active ? 'rgba(118,85,5,.35)' : 'rgba(140,103,19,.28)') + ';' +
      'color:' + (active ? '#8c1d18' : '#8c6713') + ';' +
      'box-shadow:0 4px 14px rgba(20,15,3,.16);transition:transform .15s,background .15s,box-shadow .15s';
    btn.textContent = active ? '♥' : '♡';
    btn.setAttribute('aria-pressed', active ? 'true' : 'false');
  }

  function makeHeart(slug, name, offsetTop, offsetRight) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'wishlist-heart';
    btn.dataset.slug = slug;
    btn.setAttribute('aria-label', 'Add ' + name + ' to wishlist');
    btn.title = 'Add to wishlist';

    var email = currentEmail();
    styleHeart(btn, !!email && inWishlist(email, slug), offsetTop, offsetRight);

    btn.addEventListener('mouseenter', function () { btn.style.transform = 'scale(1.12)'; });
    btn.addEventListener('mouseleave', function () { btn.style.transform = 'scale(1)'; });

    btn.addEventListener('click', function (event) {
      // The card itself is often a link — never navigate on a heart click.
      event.preventDefault();
      event.stopPropagation();

      var email = currentEmail();
      if (!email) {
        toast('Sign in to save items to your wishlist.', 'Sign in', 'account.html');
        return;
      }

      var list = readWishlist(email);
      var idx = list.findIndex(function (item) { return item.slug === slug; });

      if (idx >= 0) {
        list.splice(idx, 1);
        writeWishlist(email, list);
        syncAll(slug, false, offsetTop, offsetRight);
        toast('Removed from your wishlist.');
      } else {
        list.unshift({ slug: slug, name: name, addedAt: new Date().toISOString() });
        writeWishlist(email, list);
        syncAll(slug, true, offsetTop, offsetRight);
        toast('Saved to your wishlist.', 'View wishlist', 'account-dashboard.html#wishlist');
      }
    });

    return btn;
  }

  // Keep every heart for the same product in sync on the current page.
  function syncAll(slug, active, offsetTop, offsetRight) {
    document.querySelectorAll('.wishlist-heart[data-slug="' + slug + '"]').forEach(function (el) {
      styleHeart(el, active, el.dataset.top || offsetTop, el.dataset.right || offsetRight);
    });
  }

  function slugFromHref(href) {
    if (!href) return '';
    var match = href.match(/product-([a-z0-9-]+)\.html/i);
    return match ? match[1] : '';
  }

  function attach(container, imageHost, slug, name, offsetTop, offsetRight) {
    if (!container || !imageHost || !slug) return;
    if (container.querySelector('.wishlist-heart')) return;
    if (getComputedStyle(container).position === 'static') {
      container.style.position = 'relative';
    }
    var heart = makeHeart(slug, name, offsetTop, offsetRight);
    heart.dataset.top = offsetTop;
    heart.dataset.right = offsetRight;
    container.appendChild(heart);
  }

  function init() {
    // 1. Catalog grid: <a class="supply-card" href="product-x.html">
    document.querySelectorAll('a.supply-card').forEach(function (card) {
      var slug = slugFromHref(card.getAttribute('href'));
      var titleEl = card.querySelector('.card-title');
      var name = titleEl ? titleEl.textContent.trim() : slug;
      // Sits just below the "RESEARCH SUPPLY" banner, over the vial image.
      attach(card, card.querySelector('.vial-area'), slug, name, 48, 12);
    });

    // 2. Category grids: <article class="card"> with a "Select Options" link
    document.querySelectorAll('article.card').forEach(function (card) {
      var link = card.querySelector('a[href*="product-"]');
      var slug = slugFromHref(link && link.getAttribute('href'));
      var heading = card.querySelector('h3');
      var name = heading ? heading.textContent.trim() : slug;
      attach(card, card.querySelector('.product-photo'), slug, name, 48, 16);
    });

    // 3. Product detail pages: the large vial stage
    var stage = document.querySelector('.product-stage');
    if (stage) {
      var slug = slugFromHref(location.pathname);
      var heading = document.querySelector('.product-info h1, .product-info h2, h1');
      var name = heading ? heading.textContent.trim() : slug;
      attach(stage, stage.querySelector('img'), slug, name, 20, 20);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

/* Knight Labs — Zelle payment details
 *
 * One place to change the Zelle recipient, link and QR image. Used by the
 * checkout page, the order confirmation page and the order view page.
 *
 * Note: the QR link contains the recipient email in a base64 query parameter,
 * so anything published here is public. Change KL_ZELLE below if the receiving
 * account ever changes.
 */
window.KL_ZELLE = {
  // https://enroll.zellepay.com/qr-codes?data=<base64 {"name":...,"token":...}>
  link: 'https://enroll.zellepay.com/qr-codes?data=eyJuYW1lIjoiQ0hSSVNUT1BIRVIiLCJ0b2tlbiI6ImNqMDYwODI0QGdtYWlsLmNvbSJ9',
  qr: 'assets/zelle-qr.png',
  recipientName: 'Christopher',
  recipientToken: 'cj060824@gmail.com',

  /* Is this order set to pay by Zelle? */
  isZelle: function (preference) {
    return /zelle/i.test(String(preference || ''));
  },

  /* Paying cash on pickup or delivery? */
  isCash: function (preference) {
    return /cash/i.test(String(preference || ''));
  },

  /* Cash orders get their own next steps. Reuses the Zelle panel styling so
     both payment routes look like part of the same page. */
  cashPanel: function (total) {
    var z = window.KL_ZELLE;
    return ''
      + '<div class="kl-zelle">'
      + '<div class="kl-zelle-head">Paying with cash</div>'
      + '<div class="kl-zelle-steps">'
      + '<div class="kl-zelle-step"><span>1</span><div>Knight Labs will confirm the '
      + 'availability of your selected products.<small>Nothing is charged on this '
      + 'website.</small></div></div>'
      + '<div class="kl-zelle-step"><span>2</span><div>We will then contact you '
      + 'directly, by phone or email, to arrange delivery.<small>Use the contact '
      + 'details you entered at checkout.</small></div></div>'
      + '<div class="kl-zelle-step"><span>3</span><div>Bring exactly '
      + '<b>' + z.money(total) + '</b> in cash.<small>This is the full order total, '
      + 'including any delivery charge.</small></div></div>'
      + '</div>'
      + '<div class="kl-cash-note"><b>Please bring the exact amount.</b> '
      + 'We do not carry change, so we cannot break larger notes.</div>'
      + '</div>';
  },

  money: function (n) {
    return '$' + Number(n || 0).toLocaleString(undefined, {
      minimumFractionDigits: 2, maximumFractionDigits: 2
    });
  },

  /* Full instructions once an order number exists. */
  panel: function (orderNumber, total) {
    var z = window.KL_ZELLE;
    return ''
      + '<div class="kl-zelle">'
      + '<div class="kl-zelle-head">Pay with Zelle</div>'
      + '<div class="kl-zelle-grid">'
      + '<div class="kl-zelle-steps">'
      + '<div class="kl-zelle-step"><span>1</span><div>Send exactly <b>' + z.money(total) + '</b>'
      + '<small>The full order total.</small></div></div>'
      + '<div class="kl-zelle-step"><span>2</span><div>Send to <b>' + z.recipientToken + '</b>'
      + '<small>Recipient shows as ' + z.recipientName + '.</small></div></div>'
      + '<div class="kl-zelle-step"><span>3</span><div>Put <b>' + orderNumber + '</b> in the memo'
      + '<small>Also called the note or message field. This is how your payment is matched to your order.</small></div></div>'
      + '</div>'
      + '<div class="kl-zelle-qr">'
      + '<img src="' + z.qr + '" alt="Zelle QR code for ' + z.recipientToken + '" width="150" height="150">'
      + '<a href="' + z.link + '" target="_blank" rel="noopener">Open in Zelle</a>'
      + '<small>Scan with your banking app</small>'
      + '</div>'
      + '</div>'
      + '<div class="kl-zelle-note">Your order stays <b>Unpaid</b> until the payment is received and matched. '
      + 'Payments without an order number in the memo take longer to match.</div>'
      + '</div>';
  },

  /* Shown at checkout, before an order number has been assigned. */
  preview: function (total) {
    var z = window.KL_ZELLE;
    return ''
      + '<div class="kl-zelle">'
      + '<div class="kl-zelle-head">Paying with Zelle</div>'
      + '<div class="kl-zelle-grid">'
      + '<div class="kl-zelle-steps">'
      + '<p style="margin:0 0 12px">After you place this order you will get an order number, '
      + 'then send <b>' + z.money(total) + '</b> to <b>' + z.recipientToken + '</b> with that '
      + 'order number in the memo.</p>'
      + '<p style="margin:0;font-size:13px;opacity:.8">Full instructions appear on the next screen '
      + 'and in your confirmation email. Nothing is charged now.</p>'
      + '</div>'
      + '<div class="kl-zelle-qr">'
      + '<img src="' + z.qr + '" alt="Zelle QR code for ' + z.recipientToken + '" width="132" height="132">'
      + '<a href="' + z.link + '" target="_blank" rel="noopener">Open in Zelle</a>'
      + '<small>Wait for your order number</small>'
      + '</div>'
      + '</div>'
      + '</div>';
  },

  /* Injected once per page. */
  styles: function () {
    if (document.getElementById('kl-zelle-style')) return;
    var css = ''
      + '.kl-zelle{border:1px solid rgba(212,175,55,.5);border-radius:16px;'
      + 'background:rgba(212,175,55,.08);padding:20px;margin-top:18px}'
      + '.kl-zelle-head{font-size:11px;font-weight:950;letter-spacing:.12em;text-transform:uppercase;'
      + 'color:#8c6713;margin-bottom:16px}'
      + '.kl-zelle-grid{display:flex;gap:22px;align-items:flex-start;flex-wrap:wrap}'
      + '.kl-zelle-steps{flex:1;min-width:240px}'
      + '.kl-zelle-step{display:flex;gap:12px;align-items:flex-start;margin-bottom:14px;font-size:15px}'
      + '.kl-zelle-step:last-child{margin-bottom:0}'
      + '.kl-zelle-step>span{flex:0 0 24px;width:24px;height:24px;border-radius:50%;'
      + 'background:linear-gradient(135deg,#fff0a8,#d4af37);color:#080604;font-size:12px;'
      + 'font-weight:950;display:flex;align-items:center;justify-content:center}'
      + '.kl-zelle-step b{font-weight:950}'
      + '.kl-zelle-step small{display:block;margin-top:2px;font-size:12px;opacity:.75;line-height:1.5}'
      + '.kl-cash-note{margin-top:16px;padding:12px 14px;border-radius:12px;'
      + 'border:1px solid rgba(212,175,55,.45);background:rgba(212,175,55,.14);'
      + 'font-size:14px;line-height:1.55}'
      + '.kl-zelle-qr{text-align:center;flex:0 0 auto}'
      + '.kl-zelle-qr img{display:block;border:1px solid rgba(212,175,55,.4);border-radius:10px;'
      + 'background:#fff;padding:6px}'
      + '.kl-zelle-qr a{display:inline-block;margin-top:9px;font-size:13px;font-weight:900;'
      + 'color:#8c6713;text-decoration:underline}'
      + '.kl-zelle-qr small{display:block;margin-top:4px;font-size:11px;opacity:.7}'
      + '.kl-zelle-note{margin-top:16px;padding-top:14px;border-top:1px solid rgba(212,175,55,.3);'
      + 'font-size:13px;line-height:1.6;opacity:.85}'
      + 'html[data-theme="dark"] .kl-zelle-head,html[data-theme="dark"] .kl-zelle-qr a{color:#fff0a8}'
      + '@media(max-width:560px){.kl-zelle-grid{flex-direction:column-reverse}'
      + '.kl-zelle-qr{align-self:center}}';
    var el = document.createElement('style');
    el.id = 'kl-zelle-style';
    el.textContent = css;
    document.head.appendChild(el);
  }
};

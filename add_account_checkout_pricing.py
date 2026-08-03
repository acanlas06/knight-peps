from pathlib import Path
import json, re

root = Path('.')
ASSET = 'assets/knight-labs-vial.png?v=transparent2'
PRODUCTS = {
    'retatrutide': {'name':'Retatrutide','sizes':['5mg','10mg','15mg','20mg','30mg','60mg']},
    'tirzepatide': {'name':'Tirzepatide','sizes':['5mg','10mg','15mg','20mg','30mg','40mg+']},
    'semaglutide': {'name':'Semaglutide','sizes':['2mg','5mg','10mg','15mg','20mg','30mg']},
    'bpc-157': {'name':'BPC-157','sizes':['5mg','10mg','15mg']},
    'tb500': {'name':'TB500','sizes':['5mg','10mg']},
    'bpc-157-tb500-blend': {'name':'BPC-157 + TB500 Blend','sizes':['5mg + 5mg','10mg + 10mg']},
    'cjc-1295-without-dac-ipamorelin': {'name':'CJC-1295 without DAC + Ipamorelin','sizes':['5mg + 5mg','10mg + 10mg']},
    'ipamorelin': {'name':'Ipamorelin','sizes':['5mg','10mg']},
    'cjc-1295-without-dac-mod-grf-1-29': {'name':'CJC-1295 without DAC / Mod GRF 1-29','sizes':['2mg','5mg']},
    'nad': {'name':'NAD+','sizes':['500mg','1000mg']},
    'glutathione': {'name':'Glutathione','sizes':['600mg','1200mg']},
    'epithalon': {'name':'Epithalon','sizes':['10mg','50mg']},
    'semax': {'name':'Semax','sizes':['5mg','10mg']},
    'selank': {'name':'Selank','sizes':['5mg','10mg']},
    'ghk-cu': {'name':'GHK-CU','sizes':['50mg','100mg']},
}
# Placeholder prices only; real pricing can replace these.
PRICES = {
 'retatrutide': {'5mg':149,'10mg':249,'15mg':349,'20mg':449,'30mg':649,'60mg':1199},
 'tirzepatide': {'5mg':119,'10mg':199,'15mg':279,'20mg':349,'30mg':499,'40mg+':649},
 'semaglutide': {'2mg':59,'5mg':99,'10mg':179,'15mg':249,'20mg':319,'30mg':449},
 'bpc-157': {'5mg':49,'10mg':79,'15mg':109},
 'tb500': {'5mg':55,'10mg':89},
 'bpc-157-tb500-blend': {'5mg + 5mg':89,'10mg + 10mg':149},
 'cjc-1295-without-dac-ipamorelin': {'5mg + 5mg':99,'10mg + 10mg':169},
 'ipamorelin': {'5mg':49,'10mg':79},
 'cjc-1295-without-dac-mod-grf-1-29': {'2mg':45,'5mg':79},
 'nad': {'500mg':89,'1000mg':149},
 'glutathione': {'600mg':69,'1200mg':119},
 'epithalon': {'10mg':59,'50mg':199},
 'semax': {'5mg':55,'10mg':89},
 'selank': {'5mg':55,'10mg':89},
 'ghk-cu': {'50mg':69,'100mg':119},
}
product_json = json.dumps(PRODUCTS)
price_json = json.dumps(PRICES)
extra_css = '''
.account-link{border:1px solid rgba(255,247,223,.22);border-radius:999px;padding:11px 16px;color:rgba(255,247,223,.92)}
.price-card{border:1px solid #e0cf9d;border-radius:20px;background:#fff9ea;padding:18px;margin:20px 0;display:flex;justify-content:space-between;align-items:center;gap:18px}.price-card small{display:block;color:#967016;text-transform:uppercase;letter-spacing:.14em;font-size:10px;font-weight:950}.price-card b{font-size:30px;letter-spacing:-.05em}.form-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}.field{display:grid;gap:7px}.field label,.checkline{font-weight:900}.field input,.field select,.field textarea{border:1px solid #dac89a;border-radius:16px;background:#fffdf8;padding:13px 14px;font:inherit}.field textarea{min-height:96px;resize:vertical}.checkout-layout,.account-layout{display:grid;grid-template-columns:1fr .42fr;gap:24px;align-items:start}.checkout-panel,.account-panel{border:1px solid var(--line,#dac89a);border-radius:30px;background:#fffdf8;box-shadow:var(--shadow,0 28px 80px rgba(20,15,3,.14));padding:30px}.checkline{display:flex;align-items:flex-start;gap:10px;border:1px solid #e0cf9d;border-radius:18px;background:#fff9ea;padding:14px;margin-top:14px}.line-price{margin-top:8px;color:#8c6713;font-weight:950}.checkout-items{display:grid;gap:12px}.mini-item{border:1px solid #e5d4a7;border-radius:18px;background:#fff9ea;padding:14px}.mini-item b{display:block}.summary-total{font-size:30px;letter-spacing:-.05em}.notice-box{border:1px dashed #d9c58d;border-radius:20px;background:#fffaf0;padding:18px;color:var(--muted,#716958)}
@media(max-width:980px){.checkout-layout,.account-layout,.form-grid{grid-template-columns:1fr}}
'''

def ensure_css(s):
    if '.price-card{' not in s:
        s = s.replace('</style>', extra_css + '</style>', 1)
    return s

def ensure_signin_nav(s):
    if 'href="account.html"' not in s:
        s = s.replace('<a href="mailto:hello@knightlabs.example">Contact</a>', '<a href="mailto:hello@knightlabs.example">Contact</a><a class="account-link" href="account.html">Sign In</a>')
    return s

def ensure_product_price(s, slug):
    if 'id="selected-price"' not in s:
        s = s.replace('<p class="price-note">Selected size: <b id="selected-size"></b></p>', '<p class="price-note">Selected size: <b id="selected-size"></b></p><div class="price-card"><div><small>Placeholder price</small><span>Final pricing can be adjusted later.</span></div><b id="selected-price">—</b></div>')
    s = s.replace('Pricing can be added once retail margins are finalized.', 'Review available sizes and placeholder pricing before adding to cart.')
    if 'const KL_PRICES=' not in s:
        script = f'''
<script>
const KL_PRICES={price_json};
(function(){{
  const slug={json.dumps(slug)}; const priceOut=document.querySelector('#selected-price'); const sizeOut=document.querySelector('#selected-size'); const add=document.querySelector('#add-cart'); const qty=document.querySelector('#qty');
  function money(n){{return '$'+Number(n||0).toLocaleString();}}
  function currentSize(){{return sizeOut?.textContent?.trim() || document.querySelector('.option.active')?.dataset.size || Object.keys(KL_PRICES[slug]||{{}})[0];}}
  function updatePrice(){{const size=currentSize(); const price=KL_PRICES[slug]?.[size]; if(priceOut) priceOut.textContent=price?money(price):'Pricing TBD'; if(add) add.dataset.price=price||0;}}
  document.querySelectorAll('.option').forEach(b=>b.addEventListener('click',()=>setTimeout(updatePrice,0))); if(qty) qty.addEventListener('input',updatePrice); updatePrice();
}})();
</script>
'''
        s = s.replace('</body>', script + '</body>')
    return s

# Update all HTML nav/css and product pages.
for p in root.glob('*.html'):
    s = p.read_text(encoding='utf-8', errors='ignore')
    s = ensure_css(s)
    s = ensure_signin_nav(s)
    if p.name.startswith('product-'):
        slug = p.stem.replace('product-','')
        if slug in PRODUCTS:
            s = ensure_product_price(s, slug)
    p.write_text(s, encoding='utf-8')

# Grab shared style after updates.
base = (root/'product-retatrutide.html').read_text(encoding='utf-8')
style = re.search(r'<style>(.*?)</style>', base, re.S).group(1)
footer = '''<footer class="footer"><div class="wrap"><div class="footer-logo"><img src="assets/knight-labs-crest-icon-transparent.png" alt="Knight Labs crest"><span>Knight Labs</span></div><p>For research and laboratory use only. Not intended for human or veterinary consumption. Nothing on this page is intended to diagnose, treat, cure, or prevent any disease. Product availability, labeling, and permitted uses may vary by jurisdiction.</p></div></footer>'''
nav = '''<header class="wrap topbar"><a class="brand" href="index.html"><img src="assets/knight-labs-crest-icon-transparent.png" alt="Knight Labs crest"><span>Knight Labs</span></a><nav aria-label="Primary navigation"><a href="index.html">Home</a><a href="supply-categories.html">Shop</a><a href="index.html#quality">Quality</a><a href="index.html#wholesale">Wholesale</a><a href="mailto:hello@knightlabs.example">Contact</a><a class="account-link" href="account.html">Sign In</a><a class="cart-link" href="cart.html">Cart <span class="cart-count" data-cart-count>0</span></a><a class="nav-cta" href="supply-categories.html">Continue Shopping</a></nav></header>'''
cart_lib = f'''
<script>
const KL_PRODUCTS={product_json};
const KL_PRICES={price_json};
function readCart(){{try{{return JSON.parse(localStorage.getItem('knightLabsCart')||'[]')}}catch(e){{return []}}}}
function writeCart(cart){{localStorage.setItem('knightLabsCart',JSON.stringify(cart));updateCartCount();}}
function cartTotalQty(){{return readCart().reduce((n,i)=>n+(parseInt(i.qty,10)||0),0)}}
function updateCartCount(){{document.querySelectorAll('[data-cart-count]').forEach(el=>el.textContent=cartTotalQty())}}
function money(n){{return '$'+Number(n||0).toLocaleString();}}
function itemPrice(item){{return KL_PRICES[item.slug]?.[item.size]||0}}
document.addEventListener('DOMContentLoaded',updateCartCount);
</script>
'''
floating = '<a class="floating-cart" href="cart.html" aria-label="View and edit cart">Cart <span class="cart-count" data-cart-count>0</span></a>'

cart_page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Knight Labs — Cart</title><meta name="description" content="View and edit your Knight Labs cart."><link rel="icon" type="image/png" href="assets/knight-labs-crest-icon-transparent.png"><link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700;900&display=swap" rel="stylesheet"><style>{style}</style></head><body><div class="hero">{nav}<div class="wrap hero-inner"><div><div class="breadcrumb"><a href="supply-categories.html">Shop</a><span>/</span><span>Cart</span></div><div class="kicker">Cart</div><h1>Your Cart</h1><p class="lead">Review products, edit quantities, or continue shopping.</p></div></div></div><section><div class="wrap"><div class="cart-panel"><div><div class="cart-table" id="cart-items"></div></div><aside class="summary"><div class="kicker">Order Summary</div><h2 style="font-size:34px;letter-spacing:-.05em">Cart preview</h2><p id="summary-text">No products selected yet.</p><div class="summary-row"><span>Total items</span><b id="summary-count">0</b></div><div class="summary-row"><span>Subtotal</span><b id="summary-subtotal">$0</b></div><a class="btn primary checkout-btn" href="checkout.html">Proceed to Checkout</a><a class="btn secondary checkout-btn" href="supply-categories.html">Continue Shopping</a></aside></div></div></section>{footer}{cart_lib}<script>
function renderCart(){{const cart=readCart();const root=document.querySelector('#cart-items');const total=cart.reduce((n,i)=>n+(parseInt(i.qty,10)||0),0);const subtotal=cart.reduce((n,i)=>n+itemPrice(i)*(parseInt(i.qty,10)||0),0);document.querySelector('#summary-count').textContent=total;document.querySelector('#summary-subtotal').textContent=money(subtotal);document.querySelector('#summary-text').textContent=cart.length?cart.length+' product line'+(cart.length===1?'':'s')+' in cart.':'No products selected yet.';if(!cart.length){{root.innerHTML='<div class="empty-cart"><h2>Your cart is empty.</h2><p class="desc">Choose a product and size to add it here.</p><a class="btn primary" style="margin-top:18px" href="supply-categories.html">Shop Products</a></div>';updateCartCount();return;}}root.innerHTML=cart.map((item,idx)=>{{const product=KL_PRODUCTS[item.slug]||{{name:item.name||item.slug,sizes:[item.size||'Select size']}};const price=itemPrice(item);const line=price*(parseInt(item.qty,10)||0);const options=product.sizes.map(size=>`<option value="${{size.replace(/"/g,'&quot;')}}" ${{size===item.size?'selected':''}}>${{size}}</option>`).join('');return `<article class="editable-cart-item"><img src="{ASSET}" alt="Knight Labs peptide vial"><div><h2>${{product.name}}</h2><p class="desc">Research product · COA available · Batch records</p><p class="line-price">${{money(price)}} each · Line total ${{money(line)}}</p><div class="item-controls"><label>Size <select data-action="size" data-index="${{idx}}">${{options}}</select></label><label>Qty <input data-action="qty" data-index="${{idx}}" type="number" min="1" value="${{item.qty||1}}"></label></div></div><button class="remove-btn" data-action="remove" data-index="${{idx}}">Remove</button></article>`;}}).join('');updateCartCount();}}
document.addEventListener('click',e=>{{if(e.target.dataset.action==='remove'){{const cart=readCart();cart.splice(parseInt(e.target.dataset.index,10),1);writeCart(cart);renderCart();}}}});document.addEventListener('change',e=>{{const a=e.target.dataset.action;if(!a)return;const cart=readCart();const i=parseInt(e.target.dataset.index,10);if(!cart[i])return;if(a==='size')cart[i].size=e.target.value;if(a==='qty')cart[i].qty=Math.max(1,parseInt(e.target.value,10)||1);writeCart(cart);renderCart();}});document.addEventListener('input',e=>{{if(e.target.dataset.action!=='qty')return;const cart=readCart();const i=parseInt(e.target.dataset.index,10);if(!cart[i])return;cart[i].qty=Math.max(1,parseInt(e.target.value,10)||1);writeCart(cart);renderCart();}});renderCart();
</script>{floating}</body></html>'''
(root/'cart.html').write_text(cart_page, encoding='utf-8')

account_page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Knight Labs — Sign In</title><meta name="description" content="Sign in or create a Knight Labs account."><link rel="icon" type="image/png" href="assets/knight-labs-crest-icon-transparent.png"><link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700;900&display=swap" rel="stylesheet"><style>{style}</style></head><body><div class="hero">{nav.replace('Continue Shopping','Shop Products')}<div class="wrap hero-inner"><div><div class="breadcrumb"><a href="index.html">Home</a><span>/</span><span>Account</span></div><div class="kicker">Account</div><h1>Sign in.</h1><p class="lead">Create an account for order updates, restock notifications, COA alerts, and saved checkout details.</p></div></div></div><section><div class="wrap account-layout"><div class="account-panel"><div class="section-head"><div><div class="kicker" style="color:#967016">Customer Account</div><h2 class="title">Access your account.</h2><p>This is a front-end preview. Authentication and notifications can connect to the final backend later.</p></div></div><div class="form-grid"><div class="field"><label>Email</label><input type="email" placeholder="you@example.com"></div><div class="field"><label>Password</label><input type="password" placeholder="••••••••"></div></div><div class="card-actions"><button class="btn primary">Sign In</button><button class="btn secondary">Create Account</button></div></div><aside class="summary"><div class="kicker">Notifications</div><h2 style="font-size:34px;letter-spacing:-.05em">Account benefits</h2><p>Optional notifications can support product availability, order status, COA uploads, and batch updates.</p><div class="checkline"><input type="checkbox" checked><span>Email me order and shipping updates.</span></div><div class="checkline"><input type="checkbox"><span>Notify me when selected products are back in stock.</span></div></aside></div></section>{footer}{cart_lib}{floating}</body></html>'''
(root/'account.html').write_text(account_page, encoding='utf-8')

checkout_page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Knight Labs — Checkout Preview</title><meta name="description" content="Knight Labs checkout preview."><link rel="icon" type="image/png" href="assets/knight-labs-crest-icon-transparent.png"><link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700;900&display=swap" rel="stylesheet"><style>{style}</style></head><body><div class="hero">{nav}<div class="wrap hero-inner"><div><div class="breadcrumb"><a href="cart.html">Cart</a><span>/</span><span>Checkout</span></div><div class="kicker">Checkout Preview</div><h1>Checkout.</h1><p class="lead">Customer information, shipping details, order summary, and research-use acknowledgment.</p></div></div></div><section><div class="wrap checkout-layout"><div class="checkout-panel"><div class="section-head"><div><div class="kicker" style="color:#967016">Customer Details</div><h2 class="title">Checkout information.</h2><p>Payment processing is not connected yet. These fields are placeholders for the final checkout flow.</p></div></div><div class="form-grid"><div class="field"><label>Email</label><input type="email" placeholder="you@example.com"></div><div class="field"><label>Full name</label><input placeholder="First and last name"></div><div class="field"><label>Phone</label><input placeholder="Optional"></div><div class="field"><label>Shipping method</label><select><option>Standard shipping placeholder</option><option>Expedited shipping placeholder</option></select></div><div class="field" style="grid-column:1/-1"><label>Shipping address</label><textarea placeholder="Street, city, state, ZIP"></textarea></div></div><label class="checkline"><input type="checkbox"> <span>I understand these products are for research and laboratory use only and are not intended for human or veterinary consumption.</span></label><div class="card-actions"><button class="btn primary">Place Order Preview</button><a class="btn secondary" href="cart.html">Back to Cart</a></div></div><aside class="summary"><div class="kicker">Order Summary</div><h2 style="font-size:34px;letter-spacing:-.05em">Review order</h2><div class="checkout-items" id="checkout-items"></div><div class="summary-row"><span>Total items</span><b id="checkout-count">0</b></div><div class="summary-row"><span>Subtotal</span><b id="checkout-subtotal">$0</b></div><div class="summary-row"><span>Shipping</span><b>TBD</b></div><div class="summary-row"><span>Total</span><b class="summary-total" id="checkout-total">$0</b></div></aside></div></section>{footer}{cart_lib}<script>
function renderCheckout(){{const cart=readCart();const root=document.querySelector('#checkout-items');const total=cart.reduce((n,i)=>n+(parseInt(i.qty,10)||0),0);const subtotal=cart.reduce((n,i)=>n+itemPrice(i)*(parseInt(i.qty,10)||0),0);document.querySelector('#checkout-count').textContent=total;document.querySelector('#checkout-subtotal').textContent=money(subtotal);document.querySelector('#checkout-total').textContent=money(subtotal);root.innerHTML=cart.length?cart.map(item=>`<div class="mini-item"><b>${{KL_PRODUCTS[item.slug]?.name||item.name}}</b><span>${{item.size}} · Qty ${{item.qty}} · ${{money(itemPrice(item)*(parseInt(item.qty,10)||0))}}</span></div>`).join(''):'<div class="notice-box">Your cart is empty. Add products before checkout.</div>';updateCartCount();}}renderCheckout();
</script>{floating}</body></html>'''
(root/'checkout.html').write_text(checkout_page, encoding='utf-8')

print('added sign-in/account page, checkout preview, and placeholder pricing')

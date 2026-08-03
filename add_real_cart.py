from pathlib import Path
import json, re

root = Path('.')
ASSET = 'assets/knight-labs-vial.png?v=transparent2'
products = [
    ('retatrutide','Retatrutide',['5mg','10mg','15mg','20mg','30mg','60mg']),
    ('tirzepatide','Tirzepatide',['5mg','10mg','15mg','20mg','30mg','40mg+']),
    ('semaglutide','Semaglutide',['2mg','5mg','10mg','15mg','20mg','30mg']),
    ('bpc-157','BPC-157',['5mg','10mg','15mg']),
    ('tb500','TB500',['5mg','10mg']),
    ('bpc-157-tb500-blend','BPC-157 + TB500 Blend',['5mg + 5mg','10mg + 10mg']),
    ('cjc-1295-without-dac-ipamorelin','CJC-1295 without DAC + Ipamorelin',['5mg + 5mg','10mg + 10mg']),
    ('ipamorelin','Ipamorelin',['5mg','10mg']),
    ('cjc-1295-without-dac-mod-grf-1-29','CJC-1295 without DAC / Mod GRF 1-29',['2mg','5mg']),
    ('nad','NAD+',['500mg','1000mg']),
    ('glutathione','Glutathione',['600mg','1200mg']),
    ('epithalon','Epithalon',['10mg','50mg']),
    ('semax','Semax',['5mg','10mg']),
    ('selank','Selank',['5mg','10mg']),
    ('ghk-cu','GHK-CU',['50mg','100mg']),
]
product_map = {slug:{'name':name,'sizes':sizes} for slug,name,sizes in products}

cart_css = '''
.cart-link{position:relative;border:1px solid rgba(255,247,223,.22);border-radius:999px;padding:11px 16px;color:rgba(255,247,223,.92)}
.cart-count{display:inline-flex;align-items:center;justify-content:center;min-width:21px;height:21px;margin-left:7px;border-radius:999px;background:linear-gradient(135deg,var(--gold2),var(--gold));color:#080604;font-size:12px;font-weight:950;padding:0 6px}.cart-table{display:grid;gap:14px}.editable-cart-item{border:1px solid #e5d4a7;border-radius:24px;padding:18px;background:#fff9ea;display:grid;grid-template-columns:96px 1fr auto;gap:18px;align-items:center}.editable-cart-item img{width:86px;height:112px;object-fit:contain;filter:drop-shadow(0 18px 24px rgba(20,15,3,.14))}.item-controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.item-controls select,.item-controls input{border:1px solid #dac89a;border-radius:14px;background:#fffdf8;padding:10px 12px;font:inherit;font-weight:850}.item-controls input{width:82px}.remove-btn{border:1px solid #d9c58d;background:#fffdf8;color:#765505;border-radius:999px;padding:10px 14px;font-weight:950;cursor:pointer}.empty-cart{border:1px dashed #d9c58d;border-radius:24px;background:#fffaf0;padding:28px;color:var(--muted)}.summary-row{display:flex;justify-content:space-between;gap:18px;border-top:1px solid rgba(255,247,223,.18);padding-top:16px;margin-top:18px}.checkout-btn{width:100%;margin-top:18px}.toast.show{opacity:1;transform:translate(-50%,0)}
'''
cart_lib = f'''
<script>
const KL_PRODUCTS={json.dumps(product_map)};
function readCart(){{try{{return JSON.parse(localStorage.getItem('knightLabsCart')||'[]')}}catch(e){{return []}}}}
function writeCart(cart){{localStorage.setItem('knightLabsCart',JSON.stringify(cart));updateCartCount();}}
function cartTotalQty(){{return readCart().reduce((n,i)=>n+(parseInt(i.qty,10)||0),0)}}
function updateCartCount(){{document.querySelectorAll('[data-cart-count]').forEach(el=>el.textContent=cartTotalQty())}}
function addToCart(item){{const cart=readCart();const key=item.slug+'|'+item.size;const found=cart.find(i=>i.slug+'|'+i.size===key);if(found){{found.qty=(parseInt(found.qty,10)||1)+(parseInt(item.qty,10)||1)}}else{{cart.push(item)}}writeCart(cart)}}
document.addEventListener('DOMContentLoaded',updateCartCount);
</script>
'''
add_script = f'''
<script>
(function(){{
  const add=document.querySelector('#add-cart');
  if(!add) return;
  add.addEventListener('click',function(e){{
    e.preventDefault();
    const u=new URL(add.href, location.href);
    const slug=u.searchParams.get('add');
    const product=KL_PRODUCTS[slug];
    const item={{slug:slug,name:product?product.name:document.querySelector('h1')?.textContent.trim(),size:u.searchParams.get('size')||document.querySelector('#selected-size')?.textContent.trim(),qty:parseInt(u.searchParams.get('qty')||document.querySelector('#qty')?.value||'1',10)}};
    addToCart(item);
    location.href='cart.html';
  }});
}})();
</script>
'''

def ensure_cart_nav(s):
    if 'data-cart-count' not in s:
        s = s.replace('<a class="nav-cta"', '<a class="cart-link" href="cart.html">Cart <span class="cart-count" data-cart-count>0</span></a><a class="nav-cta"', 1)
    return s

def ensure_css(s):
    if '.cart-link{' not in s:
        s=s.replace('</style>', cart_css+'</style>', 1)
    return s

def ensure_lib(s):
    if 'function readCart()' not in s:
        s=s.replace('</body>', cart_lib+'</body>', 1)
    return s

for p in root.glob('*.html'):
    if p.name == 'cart.html':
        continue
    s=p.read_text(encoding='utf-8')
    s=ensure_cart_nav(s)
    s=ensure_css(s)
    s=ensure_lib(s)
    # Product pages already get the counted Cart link; make the gold CTA go back to browsing.
    s=s.replace('<a class="nav-cta" href="cart.html">Cart</a>', '<a class="nav-cta" href="supply-categories.html">Browse Products</a>')
    if p.name.startswith('product-') and "location.href='cart.html'" not in s:
        s=s.replace('</body>', add_script+'</body>', 1)
    p.write_text(s, encoding='utf-8')

# Build full editable cart page using the existing shared visual language.
base = (root/'product-retatrutide.html').read_text(encoding='utf-8')
style = re.search(r'<style>(.*?)</style>', base, re.S).group(1)
if '.cart-link{' not in style:
    style += cart_css
cart_nav = '<header class="wrap topbar"><a class="brand" href="index.html"><img src="assets/knight-labs-crest-icon-transparent.png" alt="Knight Labs crest"><span>Knight Labs</span></a><nav aria-label="Primary navigation"><a href="index.html">Home</a><a href="supply-categories.html">Shop</a><a href="index.html#quality">Quality</a><a href="index.html#wholesale">Wholesale</a><a href="mailto:hello@knightlabs.example">Contact</a><a class="cart-link" href="cart.html">Cart <span class="cart-count" data-cart-count>0</span></a><a class="nav-cta" href="supply-categories.html">Continue Shopping</a></nav></header>'
cart_page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Knight Labs — Cart</title><meta name="description" content="View and edit your Knight Labs cart."><link rel="icon" type="image/png" href="assets/knight-labs-crest-icon-transparent.png"><link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700;900&display=swap" rel="stylesheet"><style>{style}</style></head><body>
<div class="hero">{cart_nav}<div class="wrap hero-inner"><div><div class="breadcrumb"><a href="supply-categories.html">Shop</a><span>/</span><span>Cart</span></div><div class="kicker">Cart</div><h1>Your Cart</h1><p class="lead" id="cart-note">Review products, edit quantities, or continue shopping.</p></div></div></div>
<section><div class="wrap"><div class="cart-panel"><div><div class="cart-table" id="cart-items"></div></div><aside class="summary"><div class="kicker">Order Summary</div><h2 style="font-size:34px;letter-spacing:-.05em">Cart preview</h2><p id="summary-text">No products selected yet.</p><div class="summary-row"><span>Total items</span><b id="summary-count">0</b></div><div class="summary-row"><span>Subtotal</span><b>Pricing TBD</b></div><a class="btn primary checkout-btn" href="mailto:hello@knightlabs.example?subject=Knight%20Labs%20Order%20Request">Proceed to Checkout</a><a class="btn secondary checkout-btn" href="supply-categories.html">Continue Shopping</a></aside></div></div></section>
<footer class="footer"><div class="wrap"><div class="footer-logo"><img src="assets/knight-labs-crest-icon-transparent.png" alt="Knight Labs crest"><span>Knight Labs</span></div><p>For research and laboratory use only. Not intended for human or veterinary consumption. Nothing on this page is intended to diagnose, treat, cure, or prevent any disease. Product availability, labeling, and permitted uses may vary by jurisdiction.</p></div></footer>
{cart_lib}
<script>
function importQueryItem(){{
  const q=new URLSearchParams(location.search); const slug=q.get('add'); if(!slug) return;
  const product=KL_PRODUCTS[slug]; addToCart({{slug:slug,name:product?product.name:slug,size:q.get('size')||((product&&product.sizes[0])||'Select size'),qty:parseInt(q.get('qty')||'1',10)}});
  history.replaceState(null,'','cart.html');
}}
function renderCart(){{
  const cart=readCart(); const root=document.querySelector('#cart-items'); const total=cart.reduce((n,i)=>n+(parseInt(i.qty,10)||0),0);
  document.querySelector('#summary-count').textContent=total; document.querySelector('#summary-text').textContent=cart.length?cart.length+' product line'+(cart.length===1?'':'s')+' in cart.':'No products selected yet.';
  if(!cart.length){{root.innerHTML='<div class="empty-cart"><h2>Your cart is empty.</h2><p class="desc">Choose a product and size to add it here.</p><a class="btn primary" style="margin-top:18px" href="supply-categories.html">Shop Products</a></div>'; updateCartCount(); return;}}
  root.innerHTML=cart.map((item,idx)=>{{const product=KL_PRODUCTS[item.slug]||{{name:item.name||item.slug,sizes:[item.size||'Select size']}}; const options=product.sizes.map(size=>`<option value="${{size.replace(/"/g,'&quot;')}}" ${{size===item.size?'selected':''}}>${{size}}</option>`).join(''); return `<article class="editable-cart-item"><img src="{ASSET}" alt="Knight Labs peptide vial"><div><h2>${{product.name}}</h2><p class="desc">Research product · COA available · Batch records</p><div class="item-controls"><label>Size <select data-action="size" data-index="${{idx}}">${{options}}</select></label><label>Qty <input data-action="qty" data-index="${{idx}}" type="number" min="1" value="${{item.qty||1}}"></label></div></div><button class="remove-btn" data-action="remove" data-index="${{idx}}">Remove</button></article>`;}}).join('');
  updateCartCount();
}}
document.addEventListener('click',e=>{{const a=e.target.dataset.action;if(a==='remove'){{const cart=readCart();cart.splice(parseInt(e.target.dataset.index,10),1);writeCart(cart);renderCart();}}}});
document.addEventListener('change',e=>{{const a=e.target.dataset.action;if(!a)return;const cart=readCart();const i=parseInt(e.target.dataset.index,10);if(!cart[i])return;if(a==='size')cart[i].size=e.target.value;if(a==='qty')cart[i].qty=Math.max(1,parseInt(e.target.value,10)||1);writeCart(cart);renderCart();}});
document.addEventListener('input',e=>{{const a=e.target.dataset.action;if(a!=='qty')return;const cart=readCart();const i=parseInt(e.target.dataset.index,10);if(!cart[i])return;cart[i].qty=Math.max(1,parseInt(e.target.value,10)||1);writeCart(cart);document.querySelector('#summary-count').textContent=cart.reduce((n,item)=>n+(parseInt(item.qty,10)||0),0);}});
importQueryItem();renderCart();
</script>
</body></html>'''
(root/'cart.html').write_text(cart_page, encoding='utf-8')
print('added persistent editable cart to html pages')

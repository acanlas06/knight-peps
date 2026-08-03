from pathlib import Path

root = Path('.')
css = '''
.floating-cart{position:fixed;right:22px;bottom:22px;z-index:40;display:inline-flex;align-items:center;gap:10px;padding:14px 18px;border-radius:999px;background:linear-gradient(135deg,var(--gold2,#fff0a8),var(--gold,#d4af37));color:#080604;font-weight:950;box-shadow:0 18px 54px rgba(20,15,3,.28);border:1px solid rgba(118,85,5,.16)}
.floating-cart .cart-count{margin-left:0;background:#090703;color:var(--gold2,#fff0a8)}
@media(max-width:680px){.floating-cart{right:14px;bottom:14px;padding:13px 16px}}
'''
button = '<a class="floating-cart" href="cart.html" aria-label="View and edit cart">Cart <span class="cart-count" data-cart-count>0</span></a>'
lib = '''
<script>
if(typeof readCart!=='function'){
function readCart(){try{return JSON.parse(localStorage.getItem('knightLabsCart')||'[]')}catch(e){return []}}
function cartTotalQty(){return readCart().reduce((n,i)=>n+(parseInt(i.qty,10)||0),0)}
function updateCartCount(){document.querySelectorAll('[data-cart-count]').forEach(el=>el.textContent=cartTotalQty())}
document.addEventListener('DOMContentLoaded',updateCartCount);
}
</script>
'''
for p in root.glob('*.html'):
    s = p.read_text(encoding='utf-8', errors='ignore')
    if '.floating-cart{' not in s:
        s = s.replace('</style>', css + '</style>', 1)
    if 'class="floating-cart"' not in s:
        s = s.replace('</body>', button + '</body>', 1)
    if 'function readCart()' not in s and "function readCart(){" not in s:
        s = s.replace('</body>', lib + '</body>', 1)
    p.write_text(s, encoding='utf-8')
print('added always-visible floating cart button to all html pages')

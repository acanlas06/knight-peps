(function(){
  const PRODUCTS = [{"name": "BAC Water", "category": "Ancillary Supplies", "url": "product-bac-water.html", "sizes": "3ml · 10ml", "terms": "bac water bacteriostatic water ancillary supplies 3ml · 10ml"}, {"name": "Semaglutide", "category": "Metabolic Research", "url": "product-semaglutide.html", "sizes": "5mg \u00b7 10mg", "terms": "semaglutide metabolic research 5mg \u00b7 10mg"}, {"name": "Tirzepatide", "category": "Metabolic Research", "url": "product-tirzepatide.html", "sizes": "10mg \u00b7 20mg \u00b7 30mg", "terms": "tirzepatide metabolic research 10mg \u00b7 20mg \u00b7 30mg"}, {"name": "Retatrutide", "category": "Metabolic Research", "url": "product-retatrutide.html", "sizes": "10mg \u00b7 20mg \u00b7 30mg", "terms": "retatrutide metabolic research 10mg \u00b7 20mg \u00b7 30mg"}, {"name": "BPC-157", "category": "Recovery & Performance", "url": "product-bpc-157.html", "sizes": "10mg", "terms": "bpc-157 recovery & performance 10mg"}, {"name": "TB500", "category": "Recovery & Performance", "url": "product-tb500.html", "sizes": "10mg", "terms": "tb500 recovery & performance 10mg"}, {"name": "BPC-157 + TB500 Blend", "category": "Recovery & Performance", "url": "product-bpc-157-tb500-blend.html", "sizes": "5mg + 5mg \u00b7 10mg + 10mg", "terms": "bpc-157 + tb500 blend recovery & performance 5mg + 5mg \u00b7 10mg + 10mg"}, {"name": "CJC-1295 without DAC + Ipamorelin", "category": "Recovery & Performance", "url": "product-cjc-1295-without-dac-ipamorelin.html", "sizes": "5mg + 5mg \u00b7 10mg + 10mg", "terms": "cjc-1295 without dac + ipamorelin recovery & performance 5mg + 5mg \u00b7 10mg + 10mg"}, {"name": "Ipamorelin", "category": "Recovery & Performance", "url": "product-ipamorelin.html", "sizes": "5mg \u00b7 10mg", "terms": "ipamorelin recovery & performance 5mg \u00b7 10mg"}, {"name": "CJC-1295 without DAC / Mod GRF 1-29", "category": "Recovery & Performance", "url": "product-cjc-1295-without-dac-mod-grf-1-29.html", "sizes": "2mg \u00b7 5mg", "terms": "cjc-1295 without dac / mod grf 1-29 recovery & performance 2mg \u00b7 5mg"}, {"name": "Tesamorelin", "category": "Recovery & Performance", "url": "product-tesamorelin.html", "sizes": "2mg \u00b7 5mg \u00b7 10mg \u00b7 20mg", "terms": "tesamorelin recovery & performance 2mg \u00b7 5mg \u00b7 10mg \u00b7 20mg"}, {"name": "NAD+", "category": "Longevity & Cellular Research", "url": "product-nad.html", "sizes": "500mg", "terms": "nad+ longevity & cellular research 500mg"}, {"name": "Glutathione", "category": "Longevity & Cellular Research", "url": "product-glutathione.html", "sizes": "600mg \u00b7 1200mg", "terms": "glutathione longevity & cellular research 600mg \u00b7 1200mg"}, {"name": "Epithalon", "category": "Longevity & Cellular Research", "url": "product-epithalon.html", "sizes": "10mg \u00b7 50mg", "terms": "epithalon longevity & cellular research 10mg \u00b7 50mg"}, {"name": "Semax", "category": "Cognitive Research", "url": "product-semax.html", "sizes": "10mg", "terms": "semax cognitive research 10mg"}, {"name": "Selank", "category": "Cognitive Research", "url": "product-selank.html", "sizes": "10mg", "terms": "selank cognitive research 10mg"}, {"name": "GHK-CU", "category": "Dermatology & Cosmetic Research", "url": "product-ghk-cu.html", "sizes": "50mg", "terms": "ghk-cu dermatology & cosmetic research 50mg"}];
  function escapeHTML(value){return String(value||'').replace(/[&<>"']/g,function(ch){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch];});}
  function buildSearch(){
    const header=document.querySelector('.topbar');
    if(!header || header.querySelector('.site-search')) return;
    const box=document.createElement('div');
    box.className='site-search';
    box.innerHTML='<form class="site-search-form" role="search" aria-label="Product search"><input class="site-search-input" type="search" placeholder="Search products…" autocomplete="off" aria-label="Search products"><button class="site-search-button" type="submit">Search</button></form><div class="site-search-results" role="listbox" aria-label="Product search results"></div>';
    const nav=header.querySelector('nav');
    if(nav){ nav.insertBefore(box, nav.querySelector('.account-link') || nav.querySelector('.cart-link') || nav.lastElementChild); }
    else{ header.appendChild(box); }
    const input=box.querySelector('.site-search-input');
    const results=box.querySelector('.site-search-results');
    function matches(q){
      q=q.trim().toLowerCase();
      if(!q) return PRODUCTS.slice(0,6);
      return PRODUCTS.filter(p=>p.terms.includes(q) || p.name.toLowerCase().includes(q)).slice(0,8);
    }
    function render(){
      const q=input.value;
      const list=matches(q);
      results.classList.add('open');
      results.innerHTML=list.length ? list.map(p=>'<a class="site-search-result" role="option" href="'+p.url+'"><b>'+escapeHTML(p.name)+'</b><span>'+escapeHTML(p.category)+' · '+escapeHTML(p.sizes)+'</span></a>').join('') : '<div class="site-search-empty">No products found.</div>';
    }
    input.addEventListener('focus',render);
    input.addEventListener('input',render);
    box.querySelector('form').addEventListener('submit',function(e){
      e.preventDefault();
      const first=matches(input.value)[0];
      if(first) location.href=first.url;
    });
    document.addEventListener('click',function(e){ if(!box.contains(e.target)) results.classList.remove('open'); });
    input.addEventListener('keydown',function(e){
      if(e.key==='Escape'){results.classList.remove('open'); input.blur();}
      if(e.key==='Enter'){const first=matches(input.value)[0]; if(first){e.preventDefault(); location.href=first.url;}}
    });
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',buildSearch); else buildSearch();
})();

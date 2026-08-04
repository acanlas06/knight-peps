(function(){
  const KEY='knightLabsComplianceAccepted';
  if(window.location.pathname.split('/').pop()==='terms.html') return;
  function accepted(){try{return localStorage.getItem(KEY)==='yes'}catch(e){return false}}
  function setAccepted(){try{localStorage.setItem(KEY,'yes')}catch(e){}}
  function buildGate(){
    if(document.querySelector('.kl-compliance-gate')) return;
    const gate=document.createElement('div');
    gate.className='kl-compliance-gate';
    gate.setAttribute('role','dialog');
    gate.setAttribute('aria-modal','true');
    gate.setAttribute('aria-labelledby','kl-gate-title');
    gate.innerHTML=`
      <div class="kl-gate-panel">
        <div class="kl-gate-brand"><img src="assets/knight-labs-crest-icon-transparent.png" alt=""><span>Knight Labs</span></div>
        <div class="kl-gate-kicker">Research access verification</div>
        <h2 id="kl-gate-title">Before entering Knight Labs.</h2>
        <p class="kl-gate-intro">Please confirm the following acknowledgments to continue.</p>
        <div class="kl-gate-checks">
          <label class="kl-gate-check"><input type="checkbox" data-kl-gate-check><span>I confirm that I am at least 21 years old and legally allowed to access this site.</span></label>
          <label class="kl-gate-check"><input type="checkbox" data-kl-gate-check><span>I understand all products are offered for research/laboratory use only and are not for human or animal consumption.</span></label>
          <label class="kl-gate-check"><input type="checkbox" data-kl-gate-check><span>I have read and agree to the <a href="terms.html" target="_blank" rel="noopener">Terms &amp; Conditions and Research Use Policy</a>.</span></label>
        </div>
        <div class="kl-gate-actions"><button class="kl-gate-enter" type="button" disabled>Enter Site</button></div>
      </div>`;
    document.body.appendChild(gate);
    const checks=[...gate.querySelectorAll('[data-kl-gate-check]')];
    const button=gate.querySelector('.kl-gate-enter');
    const update=()=>{button.disabled=!checks.every(c=>c.checked)};
    checks.forEach(c=>c.addEventListener('change',update));
    button.addEventListener('click',()=>{setAccepted();gate.setAttribute('data-open','false');document.body.classList.remove('kl-gate-locked')});
    gate.setAttribute('data-open','true');
    document.body.classList.add('kl-gate-locked');
    setTimeout(()=>checks[0]&&checks[0].focus(),50);
  }
  if(!accepted()){
    if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',buildGate);
    else buildGate();
  }
})();

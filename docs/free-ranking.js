// Jugadores libres: ranking general automático.
(function(){
  const originalRenderDash=renderDash;
  renderDash=function(){
    originalRenderDash();
    if(!profile)return;
    if(String(profile.section||'').toUpperCase()==='PUBLIC'){
      const tabs=document.querySelector('.rank-tabs');
      if(tabs){
        tabs.innerHTML='<button data-rank="PUBLIC" class="active">GENERAL</button>';
        const b=tabs.querySelector('[data-rank="PUBLIC"]');
        if(b)b.onclick=()=>loadRank('PUBLIC');
      }
      const sectionLabel=document.querySelector('.dashboard .section .profile-head .muted');
      if(sectionLabel)sectionLabel.textContent='Ranking general';
      rankSection='PUBLIC';
      loadRank('PUBLIC');
    }
  };
})();

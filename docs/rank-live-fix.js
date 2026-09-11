// Ranking live fix v3: fresh reads, request ordering and strict isolation, including PUBLIC.
(function(){
  let rankRequestSeq=0;
  const GROUPS=['2A','2B','5A','5B','PUBLIC'];
  normalizeSec=function(s){
    const raw=String(s||'').toUpperCase().trim();
    if(raw==='PUBLIC')return 'PUBLIC';
    const t=raw.replace(/[^25AB]/g,'');
    return GROUPS.includes(t)?t:'';
  };

  const originalApi=api;
  api=async function(path,opt={}){
    let nextPath=path;
    const method=(opt.method||'GET').toUpperCase();
    if(method==='GET'&&path.includes('/leaderboard')){
      nextPath+=(path.includes('?')?'&':'?')+'_ts='+Date.now()+'-'+Math.random().toString(36).slice(2);
    }
    const out=await originalApi(nextPath,opt);
    if(path==='/score'&&out&&out.ok){
      if(profile&&Number.isFinite(Number(out.personal_best))){
        profile.best_score=Math.max(Number(profile.best_score||0),Number(out.personal_best||0));
      }
      setTimeout(()=>{
        try{if(document.querySelector('#rankList'))loadRank(rankSection||normalizeSec(profile?.section)||'PUBLIC',true);}catch(e){}
        try{if(profile)loadMyRank();}catch(e){}
      },200);
    }
    return out;
  };

  loadRank=async function(s,silent=false){
    if(!GROUPS.includes(s))s='PUBLIC';
    rankSection=s;
    const requestId=++rankRequestSeq;
    document.querySelectorAll('[data-rank]').forEach(b=>b.classList.toggle('active',b.dataset.rank===s));
    const el=document.querySelector('#rankList');
    if(!el)return;
    if(!silent)el.innerHTML='<span class="muted">Cargando…</span>';
    try{
      const d=await api('/leaderboard?section='+encodeURIComponent(s)+'&limit=100');
      if(requestId!==rankRequestSeq||rankSection!==s)return;
      const rows=(d.players||[]).filter(p=>String(p.section||'').toUpperCase()===s);
      el.innerHTML=rows.length?rows.map((p,i)=>`<div class="rank-row ${i===0?'first':''}"><span class="place">${i<3?['🥇','🥈','🥉'][i]:i+1}</span><span class="avatar" style="width:38px;height:38px;font-size:20px">${p.avatar||'⚡'}</span><span class="rank-name"><strong>${esc(p.display_name)}</strong><small>${s==='PUBLIC'?'Ranking general':sec(p.section)}</small></span><span class="pts">${p.best_score}</span></div>`).join(''):'<span class="muted">Aún no hay puntajes.</span>';
      el.dataset.section=s;
      el.dataset.updatedAt=d.updated_at||new Date().toISOString();
    }catch(e){
      if(requestId===rankRequestSeq&&!silent)el.innerHTML='<span class="muted">No se pudo cargar el ranking.</span>';
    }
  };

  loadMyRank=async function(){
    const s=normalizeSec(profile?.section)||'PUBLIC';
    try{
      const d=await api('/leaderboard?section='+encodeURIComponent(s)+'&limit=500');
      const rows=(d.players||[]).filter(p=>String(p.section||'').toUpperCase()===s);
      const r=rows.find(x=>x.account_id===profile.account_id);
      const el=document.querySelector('#myRank');if(el)el.textContent=r?'#'+r.rank:'—';
      if(r&&profile)profile.best_score=Number(r.best_score||profile.best_score||0);
    }catch(e){}
  };

  setInterval(()=>{
    if(document.hidden||!profile)return;
    if(document.querySelector('#rankList')){
      try{loadRank(rankSection||normalizeSec(profile.section)||'PUBLIC',true);}catch(e){}
    }
    if(document.querySelector('#myRank')){
      try{loadMyRank();}catch(e){}
    }
  },3000);

  document.addEventListener('visibilitychange',()=>{
    if(!document.hidden&&profile){
      try{if(document.querySelector('#rankList'))loadRank(rankSection||normalizeSec(profile.section)||'PUBLIC',true);}catch(e){}
      try{if(document.querySelector('#myRank'))loadMyRank();}catch(e){}
    }
  });
})();

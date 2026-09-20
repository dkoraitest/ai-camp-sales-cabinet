/* Блок «Обзор». Дашборд про цифры: метрики, воронка, качество, команда.
   Подключается сборщиком: scripts/build_cabinet.py */

function ovStats(){
  const contacts = DataSource.contacts(), leads = DataSource.leads(), sc = DataSource.scores();
  const items = sc ? (sc.items || sc.calls || []) : [];
  const byId = {}; items.forEach(i => byId[i.id] = i);
  const scored = contacts.map(c => byId[c.id]).filter(Boolean);
  const avg = scored.length ? scored.reduce((a,s)=>a+s.total,0)/scored.length : null;
  const won = leads.filter(l => l.stage === 'closed_won' || l.stage === 'payment').length;
  const lost = leads.filter(l => l.stage === 'closed_lost').length;
  const pipeline = leads.filter(l => !['closed_won','closed_lost'].includes(l.stage))
                        .reduce((a,l)=>a+(l.value_kzt||0),0);
  return {contacts, leads, items, byId, scored, avg, won, lost, pipeline};
}

function bigKpi(label, value, sub, tone){
  const color = tone ? 'var(--'+tone+')' : 'var(--fg)';
  return '<div class="card"><div class="kpi-label">'+esc(label)+'</div>'+
    '<div class="kpi" style="color:'+color+'">'+esc(value)+'</div>'+
    (sub ? '<div class="kpi-note">'+esc(sub)+'</div>' : '')+'</div>';
}

/* Горизонтальная воронка: ширина полосы = число контактов, подпись = деньги на этапе */
function ovFunnel(S){
  const fn = DataSource.funnel(); if(!fn.length) return '';
  const rows = fn.map(s => {
    const cs = S.contacts.filter(c => c.stage === s.id);
    const ls = S.leads.filter(l => l.stage === s.id);
    const money = ls.reduce((a,l)=>a+(l.value_kzt||0),0);
    const sc = cs.map(c => S.byId[c.id]).filter(Boolean);
    const avg = sc.length ? sc.reduce((a,x)=>a+x.total,0)/sc.length : null;
    return {s, n: cs.length, leads: ls.length, money, avg};
  });
  const max = Math.max(1, ...rows.map(r => r.n));
  let html = '<h2>Воронка · где стоят сделки</h2><div class="card">';
  rows.forEach(r => {
    const w = Math.max(4, Math.round(r.n / max * 100));
    const focus = r.s.id === CFG.focus_stage;
    html += '<div style="margin-bottom:16px">'+
      '<div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:6px">'+
        '<span style="font-size:14px'+(focus?';color:var(--accent);font-weight:600':'')+'">'+esc(r.s.label)+
          (focus?' <span class="pill accent" style="font-size:11px">фокус</span>':'')+'</span>'+
        '<span class="muted small">'+r.n+' контактов · '+r.leads+' сделок'+
          (r.money ? ' · '+money(r.money) : '')+'</span></div>'+
      '<div style="display:flex;align-items:center;gap:10px">'+
        '<div class="bar" style="flex:1;height:14px">'+
          '<i style="width:'+w+'%;background:'+(focus?'var(--accent)':'rgba(139,147,167,.55)')+'"></i></div>'+
        (r.avg!==null ? '<span class="pill '+grade(r.avg,10)+'" style="min-width:46px;text-align:center">'+r.avg.toFixed(1)+'</span>'
                      : '<span class="pill" style="min-width:46px"> </span>')+
      '</div></div>';
  });
  return html + '</div>';
}

/* Распределение оценок: сколько разговоров в каждом диапазоне */
function ovHistogram(S){
  if(!S.scored.length) return '';
  const buckets = [0,0,0,0,0];
  S.scored.forEach(s => buckets[Math.min(4, Math.floor(s.total/2))]++);
  const max = Math.max(...buckets);
  const labels = ['0–2','2–4','4–6','6–8','8–10'];
  const tones = ['bad','bad','warn','good','good'];
  let html = '<div class="card"><div class="kpi-label">Распределение оценок</div>'+
    '<div style="display:flex;align-items:flex-end;gap:10px;height:120px;margin:18px 0 10px">';
  buckets.forEach((b,i) => {
    const h = max ? Math.max(4, Math.round(b/max*100)) : 4;
    html += '<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:6px;height:100%;justify-content:flex-end">'+
      '<span class="muted small">'+b+'</span>'+
      '<div style="width:100%;height:'+h+'%;border-radius:6px 6px 0 0;background:var(--'+tones[i]+');opacity:.85"></div>'+
      '</div>';
  });
  html += '</div><div style="display:flex;gap:10px">'+
    labels.map(l => '<span class="muted small" style="flex:1;text-align:center">'+l+'</span>').join('')+
    '</div></div>';
  return html;
}

/* Команда: топ и низ, чтобы разрыв был виден сразу */
function ovTeam(S){
  const rows = DataSource.managers().map(m => {
    const mine = S.contacts.filter(c => c.manager_id === m.id).map(c => S.byId[c.id]).filter(Boolean);
    return {m, n: mine.length, avg: mine.length ? mine.reduce((a,s)=>a+s.total,0)/mine.length : null};
  }).filter(r => r.avg !== null).sort((a,b) => b.avg - a.avg);
  if(rows.length < 2) return '';
  const show = rows.length > 6 ? [...rows.slice(0,3), null, ...rows.slice(-2)] : rows;
  let html = '<div class="card"><div class="kpi-label">Команда · разрыв '+
    (rows[0].avg - rows[rows.length-1].avg).toFixed(1)+' балла</div><div style="margin-top:14px">';
  show.forEach(r => {
    if(!r){ html += '<div class="muted small" style="padding:6px 0">· · ·</div>'; return; }
    html += '<div class="skill"><div class="lbl"><span>'+esc(r.m.name)+'</span>'+
      '<span class="muted">'+r.avg.toFixed(1)+' · '+r.n+' конт.</span></div>'+
      '<div class="bar '+grade(r.avg,10)+'"><i style="width:'+Math.round(r.avg*10)+'%"></i></div></div>';
  });
  return html + '</div></div>';
}

/* Каналы: звонки против переписки */
function ovChannels(S){
  const calls = S.contacts.filter(c => c.kind === 'call').map(c => S.byId[c.id]).filter(Boolean);
  const chats = S.contacts.filter(c => c.kind === 'chat').map(c => S.byId[c.id]).filter(Boolean);
  if(!chats.length) return '';
  const a = calls.length ? calls.reduce((x,s)=>x+s.total,0)/calls.length : 0;
  const b = chats.reduce((x,s)=>x+s.total,0)/chats.length;
  return '<div class="card"><div class="kpi-label">Звонки и переписка</div>'+
    '<div style="display:flex;gap:26px;margin-top:16px">'+
      '<div style="flex:1"><div style="font-size:32px;font-weight:600">'+a.toFixed(1)+'</div>'+
        '<div class="muted small">'+calls.length+' звонков</div>'+
        '<div class="bar good" style="margin-top:10px"><i style="width:'+Math.round(a*10)+'%"></i></div></div>'+
      '<div style="flex:1"><div style="font-size:32px;font-weight:600;color:var(--'+grade(b,10)+')">'+b.toFixed(1)+'</div>'+
        '<div class="muted small">'+chats.length+' переписок</div>'+
        '<div class="bar '+grade(b,10)+'" style="margin-top:10px"><i style="width:'+Math.round(b*10)+'%"></i></div></div>'+
    '</div></div>';
}

function renderOverview(){
  const S = ovStats();
  const conv = (S.won + S.lost) ? Math.round(S.won/(S.won+S.lost)*100) : 0;

  let html = '<div class="grid">'+
    bigKpi('Коммуникаций', S.contacts.length,
      DataSource.calls().length+' звонков · '+DataSource.chats().length+' переписок')+
    bigKpi('Средний балл', S.avg !== null ? S.avg.toFixed(1) : '—',
      S.avg !== null ? 'из 10 · разобрано '+S.scored.length : 'аналитика не собрана',
      S.avg !== null ? grade(S.avg,10) : null)+
    bigKpi('Сделок в работе', S.leads.filter(l => !['closed_won','closed_lost'].includes(l.stage)).length,
      S.pipeline ? money(S.pipeline)+' в воронке' : '')+
    bigKpi('Конверсия', conv+'%', S.won+' выиграно / '+S.lost+' проиграно',
      conv >= 50 ? 'good' : conv >= 30 ? 'warn' : 'bad')+
  '</div>';

  if(S.scored.length){
    html += '<div style="display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));margin-top:14px">'+
      ovHistogram(S) + ovTeam(S) + ovChannels(S) + '</div>';
  }

  html += ovFunnel(S);
  html += bantChart();

  const mx = CFG.matrix || {extract:[],evaluate:[]};
  if((mx.evaluate||[]).length){
    html += '<h2>Матрица · что система достаёт из каждого контакта</h2><div class="two">';
    html += '<div class="card"><div class="kpi-label">Слой 1 · извлекаем факты</div>';
    (mx.extract||[]).forEach(e => html += '<div class="crit"><span>'+esc(e.label)+'</span>'+
      '<span class="muted small" style="max-width:55%;text-align:right">'+esc(e.note||'')+'</span></div>');
    html += '</div><div class="card"><div class="kpi-label">Слой 2 · оцениваем работу</div>';
    (mx.evaluate||[]).forEach(e => html += '<div class="crit"><span>'+esc(e.name)+'</span>'+
      '<span class="muted small" style="max-width:55%;text-align:right">'+esc(e.includes||'')+'</span></div>');
    html += '</div></div>';
  } else {
    html += '<h2>Матрица оценки</h2>'+emptyBlock('Матрица ещё не настроена',
      'Кабинет не знает, что считать хорошим разговором в вашем бизнесе.','шага 0');
  }

  if((CFG.questions||[]).length){
    html += '<h2>Вопросы, на которые отвечает кабинет</h2><div class="card">';
    CFG.questions.forEach((q,i) => html += '<div class="crit"><span>'+(i+1)+'. '+esc(q)+'</span></div>');
    html += '</div>';
  }
  return html;
}
registerTab({ id: 'overview', label: 'Обзор', render: renderOverview });

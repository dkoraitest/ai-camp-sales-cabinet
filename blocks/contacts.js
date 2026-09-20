/* Блок «Коммуникации». Подключается сборщиком: scripts/build_cabinet.py */
/* ------------------------ КОММУНИКАЦИИ ------------------------ */
function renderContacts(){
  const all = DataSource.contacts();
  const stages = [...new Set(all.map(c => c.stage))];
  let html = '<div class="row">'+
    '<select id="f-kind"><option value="">Звонки и переписка</option><option value="call">Только звонки</option><option value="chat">Только переписка</option></select>'+
    '<select id="f-stage"><option value="">Все этапы</option>'+
      stages.map(s => '<option value="'+esc(s)+'">'+esc(stageLabel(s))+'</option>').join('')+'</select>'+
    '<select id="f-mgr"><option value="">Все менеджеры</option>'+
      DataSource.managers().map(m => '<option value="'+esc(m.id)+'">'+esc(m.name)+'</option>').join('')+'</select>'+
    '<span class="muted" id="f-count"></span></div>'+
  '<table><thead><tr><th>Дата</th><th>Канал</th><th>Менеджер</th><th>Этап</th><th>Объём</th><th>Балл</th><th>Итог</th></tr></thead>'+
  '<tbody id="c-body"></tbody></table>';
  setTimeout(bindFilters, 0);
  return html;
}
function bindFilters(){
  const draw = () => {
    const fk = $('#f-kind').value, fs = $('#f-stage').value, fm = $('#f-mgr').value;
    const rows = DataSource.contacts().filter(c =>
      (!fk || c.kind === fk) && (!fs || c.stage === fs) && (!fm || c.manager_id === fm));
    $('#c-body').innerHTML = rows.map(c => {
      const s = scoreOf(c.id);
      const badge = s ? '<span class="pill '+grade(s.total,10)+'">'+s.total.toFixed(1)+'</span>' : '<span class="pill">—</span>';
      const ch = c.kind === 'call' ? 'звонок' : (c.channel || 'переписка');
      return '<tr class="clickable" onclick="openContact(\''+c.id+'\')">'+
        '<td>'+fmtDate(c.when)+'</td><td><span class="pill">'+esc(ch)+'</span></td>'+
        '<td>'+esc(mgrName(c.manager_id))+'</td>'+
        '<td><span class="pill">'+esc(stageLabel(c.stage))+'</span></td>'+
        '<td class="muted">'+esc(c.volume)+'</td><td>'+badge+'</td>'+
        '<td class="muted">'+esc(c.outcome||'')+'</td></tr>';
    }).join('');
    $('#f-count').textContent = rows.length+' из '+DataSource.contacts().length;
  };
  ['#f-kind','#f-stage','#f-mgr'].forEach(s => $(s).onchange = draw);
  draw();
}
function openContact(id){
  const c = DataSource.contacts().find(x => x.id === id);
  if(!c) return;
  const s = scoreOf(id);
  $('#m-title').textContent = mgrName(c.manager_id)+' · '+stageLabel(c.stage);
  $('#m-sub').textContent = fmtDate(c.when)+' · '+(c.kind==='call'?'звонок':c.channel)+' · '+c.volume+' · '+(c.outcome||'');

  let body = '';
  if(s){
    body += '<div class="card" style="margin-bottom:16px"><div class="kpi-label">Оценка по матрице</div>'+
      '<div class="kpi">'+s.total.toFixed(1)+' <span class="muted" style="font-size:16px">/ 10</span></div>';
    (s.evaluate || s.criteria || []).forEach(cr => {
      const v = cr.value, max = cr.max || 10;
      body += '<div class="skill"><div class="lbl"><span>'+esc(cr.name)+'</span>'+
        '<span class="muted">'+v+'/'+max+'</span></div>'+
        '<div class="bar '+grade(v,max)+'"><i style="width:'+Math.round(v/max*100)+'%"></i></div></div>';
    });
    if(s.comment) body += '<p class="muted small" style="margin:12px 0 0">'+esc(s.comment)+'</p>';
    body += '</div>';

    const ex = s.extracted;
    if(ex){
      body += '<div class="card" style="margin-bottom:16px"><div class="kpi-label">Извлечено из контакта</div>';
      if(ex.spsv) Object.entries(ex.spsv).forEach(([k,v]) =>
        body += '<div class="crit"><span class="muted">'+esc(k)+'</span><span style="max-width:65%;text-align:right">'+esc(v)+'</span></div>');
      if(ex.qualification) Object.entries(ex.qualification).forEach(([k,v]) =>
        body += '<div class="crit"><span class="muted">'+esc(k)+'</span><span>'+(v===true?'<span class="pill good">да</span>':v===false?'<span class="pill bad">нет</span>':esc(v))+'</span></div>');
      if((ex.objections||[]).length) body += '<div class="crit"><span class="muted">возражения</span>'+
        '<span style="max-width:65%;text-align:right">'+ex.objections.map(o=>'«'+esc(o)+'»').join('<br>')+'</span></div>';
      if(ex.next_step) body += '<div class="crit"><span class="muted">следующий шаг</span><span>'+esc(ex.next_step)+'</span></div>';
      if(ex.signals) body += '<div class="crit"><span class="muted">сигналы</span><span style="max-width:65%;text-align:right">'+esc(ex.signals)+'</span></div>';
      body += '</div>';
    }
  }
  const turns = c.kind === 'call' ? (c.transcript||[]) : (c.messages||[]);
  body += turns.map(t => '<div class="turn '+t.who+'"><div class="who">'+
    (t.who==='manager'?'менеджер':'клиент')+(t.ts?'<br><span style="opacity:.6">'+fmtDate(t.ts).slice(0,5)+'</span>':'')+
    '</div><div class="text">'+esc(t.text)+'</div></div>').join('');
  $('#m-body').innerHTML = body;
  $('#modal').showModal();
}
registerTab({ id: 'contacts', label: 'Коммуникации', render: renderContacts });

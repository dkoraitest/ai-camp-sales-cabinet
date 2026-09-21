/* Блок «Коммуникации». Подключается сборщиком: scripts/build_cabinet.py */
/* ------------------------ КОММУНИКАЦИИ ------------------------ */
/* Два взгляда на одно и то же:
   «по датам»   — лента разговоров, так удобно разбирать качество;
   «по сделкам» — те же разговоры, склеенные по клиенту и этапу,
                  так видно, из чего сложился путь сделки.            */
function renderContacts(){
  const all = DataSource.contacts();
  const stages = [...new Set(all.map(c => c.stage))];
  let html = '<div class="row">'+
    '<select id="f-view"><option value="flat">По датам</option><option value="deal">По сделкам</option></select>'+
    '<select id="f-kind"><option value="">Звонки и переписка</option><option value="call">Только звонки</option><option value="chat">Только переписка</option></select>'+
    '<select id="f-stage"><option value="">Все этапы</option>'+
      stages.map(s => '<option value="'+esc(s)+'">'+esc(stageLabel(s))+'</option>').join('')+'</select>'+
    '<select id="f-mgr"><option value="">Все менеджеры</option>'+
      DataSource.managers().map(m => '<option value="'+esc(m.id)+'">'+esc(m.name)+'</option>').join('')+'</select>'+
    '<span class="muted" id="f-count"></span></div>'+
  '<div id="c-out"></div>';
  setTimeout(bindFilters, 0);
  return html;
}
function bindFilters(){
  if(!$('#f-view')) return;          // вкладку уже переключили, пока фильтры ждали отрисовки
  const draw = () => {
    const fk = $('#f-kind').value, fs = $('#f-stage').value, fm = $('#f-mgr').value;
    const rows = DataSource.contacts().filter(c =>
      (!fk || c.kind === fk) && (!fs || c.stage === fs) && (!fm || c.manager_id === fm));
    $('#c-out').innerHTML = $('#f-view').value === 'deal' ? byDeal(rows) : byDate(rows);
    $('#f-count').textContent = rows.length+' из '+DataSource.contacts().length;
  };
  ['#f-view','#f-kind','#f-stage','#f-mgr'].forEach(s => $(s).onchange = draw);
  draw();
}
function byDate(rows){
  return '<table><thead><tr><th>Дата</th><th>Клиент</th><th>Канал</th><th>Менеджер</th>'+
    '<th>Этап</th><th>Объём</th><th>Балл</th><th>Итог</th></tr></thead><tbody>'+
    rows.map(c => {
      const s = scoreOf(c.id);
      const badge = s ? '<span class="pill '+grade(s.total,10)+'">'+s.total.toFixed(1)+'</span>' : '<span class="pill">—</span>';
      return '<tr class="clickable" onclick="openContact(\''+c.id+'\')">'+
        '<td>'+fmtDate(c.when)+'</td>'+
        '<td>'+esc(leadName(c.lead_id))+'</td>'+
        '<td><span class="pill">'+esc(c.kind==='call'?'звонок':(c.channel||'переписка'))+'</span></td>'+
        '<td>'+esc(mgrName(c.manager_id))+'</td>'+
        '<td><span class="pill">'+esc(stageLabel(c.stage))+'</span></td>'+
        '<td class="muted">'+esc(c.volume)+'</td><td>'+badge+'</td>'+
        '<td class="muted">'+esc(c.outcome||'')+'</td></tr>';
    }).join('')+'</tbody></table>';
}
function byDeal(rows){
  const ids = [...new Set(rows.map(c => c.lead_id))];
  ids.sort((a,b) => new Date(last(rows,b).when) - new Date(last(rows,a).when));
  return ids.map(id => {
    const own = rows.filter(c => c.lead_id === id), l = leadOf(id) || {};
    const sc = own.map(c => scoreOf(c.id)).filter(Boolean);
    const avg = sc.length ? sc.reduce((a,s) => a+s.total, 0)/sc.length : null;
    return '<details class="deal"><summary>'+
      '<span class="deal-name">'+esc(leadName(id))+'</span>'+
      dealStrip(id, rows)+
      '<span class="pill">'+esc(stageLabel(l.stage))+'</span>'+
      '<span class="muted small">'+own.length+' '+plural(own.length,'коммуникация','коммуникации','коммуникаций')+'</span>'+
      (avg!=null ? '<span class="pill '+grade(avg,10)+'">'+avg.toFixed(1)+'</span>' : '')+
      (l.value_kzt ? '<span class="muted small">'+money(l.value_kzt)+'</span>' : '')+
      '</summary><div class="deal-body">'+dealThread(id, rows)+'</div></details>';
  }).join('') || emptyBlock('Ничего не нашлось', 'Снимите один из фильтров.', 'сброса фильтров');
}
const last = (rows, id) => rows.filter(c => c.lead_id === id).slice(-1)[0];
function openContact(id){
  const c = DataSource.contacts().find(x => x.id === id);
  if(!c) return;
  const s = scoreOf(id);
  $('#m-title').textContent = leadName(c.lead_id)+' · '+stageLabel(c.stage);
  $('#m-sub').textContent = fmtDate(c.when)+' · '+(c.kind==='call'?'звонок':c.channel)+' · '+
    c.volume+' · '+mgrName(c.manager_id)+(c.outcome ? ' · '+c.outcome : '');

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

  /* Разговор не висит в воздухе: показываем, во что он склеен */
  const rest = DataSource.contacts().filter(x => x.lead_id === c.lead_id);
  if(rest.length > 1) body += '<h2>Эта сделка целиком</h2>'+dealThread(c.lead_id);
  $('#m-body').innerHTML = body;
  $('#modal').showModal();
}
registerTab({ id: 'contacts', label: 'Коммуникации', render: renderContacts });

/* Блок «Глубина». Подключается сборщиком: scripts/build_cabinet.py */
/* ----------------------- ГЛУБОКАЯ АНАЛИТИКА ----------------------- */
/* Каждый разрез устроен одинаково: сначала что смотрели и на каком объёме,
   потом вывод. Иначе получается полотно текста, которому нечем себя
   подтвердить. Цифры считает код, вывод пишет модель.                    */
function scopeLine(t){ return '<p class="scope">'+t+'</p>' }
function finding(level, title, text){
  return '<div class="insight '+esc(level||'warn')+'"><h4>'+esc(title)+'</h4><p>'+esc(text)+'</p></div>';
}
function wonVsLost(){
  const a = (DataSource.scores()||{}).aggregates;
  const w = a && a.won_vs_lost;
  if(!w || !(w.rows||[]).length) return '';
  /* Колонка выигранных всегда зелёная, проигранных — красная: это сравнение
     двух исходов, а не оценка каждой строки по отдельности. */
  const cell = (v, kind, other, cls) => {
    const max = kind === 'share' ? 1 : Math.max(v, other, 0.1);
    return '<div class="v"><div class="bar '+cls+'"><i style="width:'+
      Math.round(v/max*100)+'%"></i></div><span>'+
      (kind === 'share' ? Math.round(v*100)+'%' : v)+'</span></div>';
  };
  return '<h2>О чём говорят в выигранных сделках</h2>'+
    scopeLine('Сравнили поведение менеджера в '+w.won_deals+' закрытых сделках ('+w.won_contacts+
      ' коммуникаций) и в '+w.lost_deals+' проигранных ('+w.lost_contacts+
      '). Сравниваются приёмы, а не свойства клиента: свойства повторить нельзя, приёмы можно.')+
    '<div class="card"><div class="cmp cmp-head"><div>Что делали в разговоре</div>'+
      '<div>'+esc(w.won_label)+'</div><div>'+esc(w.lost_label)+'</div></div>'+
    w.rows.map(r => '<div class="cmp"><div>'+esc(r.label)+'</div>'+
      cell(r.won, r.kind, r.lost, 'good') + cell(r.lost, r.kind, r.won, 'bad')+'</div>').join('')+
    '</div>';
}
function bantDepth(){
  const q = bantByStage(); if(!q) return '';
  const late = q.stages.filter(r => r.leads && r.full < r.leads);
  const money = late.reduce((a,r) => a + (r.money - r.money_full), 0);
  return scopeLine('По всем '+q.deals+' сделкам в работе собрали, что выяснено за всю историю '+
    'переписки и звонков, а не в одном разговоре. Неквалифицированных сделок в воронке на '+
    (money ? new Intl.NumberFormat('ru-RU').format(money)+' ₸' : 'значимую сумму')+'.');
}
function renderDeep(){
  const d = DataSource.deep();
  const have = DataSource.contacts().length;
  const deals = new Set(DataSource.contacts().map(c => c.lead_id)).size;
  const need = (CFG.deep_analytics||{}).min_items || 300;

  let html = '<div class="card" style="margin-bottom:18px"><div style="display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap">'+
    '<div><div class="kpi-label">Что проанализировано</div>'+
    '<div class="small muted">'+have+' коммуникаций в '+deals+' сделках · четыре разреза: выигранные против проигранных, квалификация по воронке, карта возражений, модель клиента по сегментам</div></div>'+
    '<div style="text-align:right"><div class="kpi">'+have+' <span class="muted" style="font-size:15px">/ '+need+'</span></div>'+
    '<div class="kpi-note">порог значимости</div></div></div>';
  if(have < need) html += '<p class="muted small" style="margin:14px 0 0">'+
    'На таком объёме выводы — иллюстрация механики, а не статистика. Чтобы закономерности стали значимыми, нужно от '+need+' контактов: это примерно месяц работы отдела из четырёх человек.</p>';
  html += '</div>';

  if(!d) return html + emptyBlock('Глубокая аналитика не запускалась',
    'Это отдельный разрез: не «как прошёл разговор», а «что общего у сделок, которые мы выиграли».','шага 4');

  html += wonVsLost();
  if((d.win_patterns||[]).length){
    html += '<h2>Выводы по выигранным сделкам</h2>';
    html += scopeLine('Что из этих различий можно повторить завтра.');
    d.win_patterns.forEach(p => html += finding('good', p.title, p.text));
  }

  if((d.qualification_link||[]).length || bantByStage()){
    html += '<h2>Квалификация и исход</h2>' + bantDepth();
    html += bantChart().replace(/^<h2>.*?<\/h2>/, '').replace(/<p class="scope">.*?<\/p>/, '');
    (d.qualification_link||[]).forEach(p => html += finding(p.level, p.title, p.text));
  }

  if((d.objection_map||[]).length){
    html += '<h2>Карта возражений</h2>'+
      scopeLine('Дословные формулировки из всей базы, частота и ответ тех, у кого выше конверсия. Прямой вход в скрипты и в обучение.')+
      '<table><thead><tr><th>Возражение</th><th>Частота</th><th>Что отвечают лучшие</th></tr></thead><tbody>';
    d.objection_map.forEach(o => html += '<tr><td>«'+esc(o.objection)+'»</td><td>'+esc(o.count)+'</td>'+
      '<td class="muted">'+esc(o.best_response)+'</td></tr>');
    html += '</tbody></table>';
  }

  if((d.spsv||[]).length){
    html += '<h2>Модель клиента по сегментам</h2>'+
      scopeLine('Собрано из блоков разговоров: как клиенты каждого сегмента описывают свою ситуацию, боль и ценность их же словами. Материал для скриптов, КП и сайта — не придуманный на стратсессии.')+
      '<div class="cards">';
    d.spsv.forEach(s => {
      html += '<div class="card"><div style="display:flex;justify-content:space-between"><strong>'+esc(s.segment)+'</strong>'+
        '<span class="pill">'+esc(s.share)+'</span></div>';
      [['Ситуация',s.situation],['Проблема',s.problem],['Решение',s.solution],['Ценность',s.value]].forEach(([k,v]) => {
        if(v) html += '<div style="margin-top:10px"><div class="kpi-label">'+k+'</div><div class="small">'+esc(v)+'</div></div>';
      });
      html += '</div>';
    });
    html += '</div>';
  }
  return html;
}
registerTab({ id: 'deep', label: 'Глубина', render: renderDeep });

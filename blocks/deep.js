/* Блок «Глубина». Подключается сборщиком: scripts/build_cabinet.py */
/* ----------------------- ГЛУБОКАЯ АНАЛИТИКА ----------------------- */
function renderDeep(){
  const d = DataSource.deep();
  const have = DataSource.contacts().length;
  const need = (CFG.deep_analytics||{}).min_items || 300;
  let html = '<div class="card" style="margin-bottom:18px"><div style="display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap">'+
    '<div><div class="kpi-label">Кросс-аналитика по всей базе</div>'+
    '<div class="small muted">Разбор выигранных сделок, связь квалификации с закрытием, карта возражений, SPSV по сегментам</div></div>'+
    '<div style="text-align:right"><div class="kpi">'+have+' <span class="muted" style="font-size:15px">/ '+need+'</span></div>'+
    '<div class="kpi-note">контактов в базе</div></div></div>';
  if(have < need) html += '<p class="muted small" style="margin:14px 0 0">'+
    'На таком объёме выводы — иллюстрация механики, а не статистика. Чтобы закономерности стали значимыми, нужно от '+need+' контактов: это примерно месяц работы отдела из четырёх человек.</p>';
  html += '</div>';

  if(!d) return html + emptyBlock('Глубокая аналитика не запускалась',
    'Это отдельный разрез: не «как прошёл разговор», а «что общего у сделок, которые мы выиграли».','шага 4');

  if((d.spsv||[]).length){
    html += '<h2>SPSV по сегментам</h2><div class="cards">';
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
  if((d.win_patterns||[]).length){
    html += '<h2>Что общего у выигранных сделок</h2>';
    d.win_patterns.forEach(p => html += '<div class="insight good"><h4>'+esc(p.title)+'</h4><p>'+esc(p.text)+'</p></div>');
  }
  if((d.qualification_link||[]).length){
    html += '<h2>Квалификация и исход</h2>';
    d.qualification_link.forEach(p => html += '<div class="insight '+esc(p.level||'warn')+'"><h4>'+esc(p.title)+'</h4><p>'+esc(p.text)+'</p></div>');
  }
  if((d.objection_map||[]).length){
    html += '<h2>Карта возражений</h2><table><thead><tr><th>Возражение</th><th>Частота</th><th>Что отвечают лучшие</th></tr></thead><tbody>';
    d.objection_map.forEach(o => html += '<tr><td>«'+esc(o.objection)+'»</td><td>'+esc(o.count)+'</td>'+
      '<td class="muted">'+esc(o.best_response)+'</td></tr>');
    html += '</tbody></table>';
  }
  return html;
}
registerTab({ id: 'deep', label: 'Глубина', render: renderDeep });

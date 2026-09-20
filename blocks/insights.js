/* Блок «Инсайты». Подключается сборщиком: scripts/build_cabinet.py */
/* --------------------------- ИНСАЙТЫ --------------------------- */
function renderInsights(){
  const sc = DataSource.scores();
  if(!sc || !(sc.insights||[]).length){
    return emptyBlock('Инсайтов пока нет',
      'Когда коммуникации будут разобраны, кабинет сам найдёт закономерности: где проседает воронка, кто в чём силён, какие возражения повторяются.','шага 1');
  }
  const base = sc.insights.filter(i => i.scope === 'base');
  const rows = i => '<div class="insight '+esc(i.level||'')+'">'+
      '<h4>'+esc(i.title)+
      (i.scope === 'base' ? ' <span class="pill accent" style="font-size:11px;vertical-align:2px">по всей базе</span>' : '')+
      '</h4><p>'+esc(i.text)+'</p></div>';
  let html = sc.insights.filter(i => i.scope !== 'base').map(rows).join('');
  if(base.length){
    html += '<h2>Появилось после разбора всей базы</h2>' + base.map(rows).join('');
  }
  return html;
}
registerTab({ id: 'insights', label: 'Инсайты', render: renderInsights });

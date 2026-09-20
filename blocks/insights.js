/* Блок «Инсайты». Подключается сборщиком: scripts/build_cabinet.py */
/* --------------------------- ИНСАЙТЫ --------------------------- */
function renderInsights(){
  const sc = DataSource.scores();
  if(!sc || !(sc.insights||[]).length){
    return emptyBlock('Инсайтов пока нет',
      'Когда коммуникации будут разобраны, кабинет сам найдёт закономерности: где проседает воронка, кто в чём силён, какие возражения повторяются.','шага 1');
  }
  return sc.insights.map(i => '<div class="insight '+esc(i.level||'')+'"><h4>'+esc(i.title)+'</h4><p>'+esc(i.text)+'</p></div>').join('');
}
registerTab({ id: 'insights', label: 'Инсайты', render: renderInsights });

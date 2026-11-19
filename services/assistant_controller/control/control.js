(() => {
  const letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');
  const keys = document.querySelector('#keys');
  const letter = document.querySelector('#letter');
  const note = document.querySelector('#stateNote');
  const connection = document.querySelector('#connection');
  let selected = 'K';
  let ws;
  function send(action, payload) {
    if (!ws || ws.readyState !== WebSocket.OPEN) { note.textContent = 'Chưa kết nối màn hình TV'; return; }
    ws.send(JSON.stringify({type:'ui_event', action, payload: payload || {}}));
  }
  letters.forEach((value) => { const button=document.createElement('button'); button.className='key'+(value===selected?' selected':''); button.textContent=value; button.onclick=()=>{selected=value;letter.textContent=value;document.querySelectorAll('.key').forEach(x=>x.classList.remove('selected'));button.classList.add('selected')}; keys.appendChild(button); });
  function showView(id){document.querySelectorAll('.view').forEach((view)=>view.classList.remove('active'));document.querySelector('#'+id)?.classList.add('active');}
  document.querySelector('#confirm').onclick=()=>{send('speak_letter',{letter:selected});showView('waiting');};
  function handleCommand(cmd){if(!cmd||typeof cmd!=='object')return;if(cmd.type==='show_single'||cmd.type==='show_row'||cmd.mode==='single'||cmd.mode==='row'){selected='';letter.textContent='—';document.querySelectorAll('.key').forEach((key)=>key.classList.remove('selected'));note.textContent='Chọn chữ bệnh nhân nhìn thấy trên TV';showView('control');}}
  function connect(){const proto=location.protocol==='https:'?'wss':'ws';ws=new WebSocket(`${proto}://${location.host}/ws/display`);ws.onopen=()=>{connection.textContent='● Đã kết nối';connection.classList.remove('offline')};ws.onmessage=(event)=>{try{handleCommand(JSON.parse(event.data))}catch(_){}};ws.onclose=()=>{connection.textContent='● Mất kết nối, đang thử lại…';connection.classList.add('offline');setTimeout(connect,1500)};ws.onerror=()=>ws.close()};
  let seconds=4;const countdown=document.querySelector('#seconds');const timer=setInterval(()=>{seconds-=1;if(seconds>0)countdown.textContent=seconds+' giây';else{clearInterval(timer);document.querySelector('#welcome').classList.remove('active');document.querySelector('#control').classList.add('active')}},1000);connect();
})();

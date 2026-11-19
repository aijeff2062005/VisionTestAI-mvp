(() => {
  const LETTERS = Array.from({ length: 26 }, (_, index) => String.fromCharCode(65 + index));
  const screens = ['welcome', 'mode-choice', 'test', 'waiting', 'complete'];
  const keys = document.getElementById('keys');
  const letter = document.getElementById('letter');
  const confirm = document.getElementById('confirm');
  const bar = document.getElementById('countdown-bar');
  const testScreen = document.getElementById('test');
  let ws;
  let inputMode = null;
  let accepting = false;
  let selected = '';
  let deadline = 0;
  let timer = 0;
  let modeChoiceSubmitted = false;
  let answerSubmitted = false;
  let windowId = '';
  let patientName = '';

  function show(screen) {
    screens.forEach(id => document.getElementById(id).classList.toggle('active', id === screen));
  }

  function stopWindow() {
    accepting = false;
    clearTimeout(timer);
    confirm.disabled = true;
    keys.querySelectorAll('button').forEach(button => { button.disabled = true; });
  }

  function resetSelection() {
    selected = '';
    letter.textContent = '—';
    confirm.disabled = true;
    keys.querySelectorAll('button').forEach(button => button.classList.remove('selected'));
  }

  function waiting(text) {
    stopWindow();
    document.getElementById('waiting-text').textContent = text || 'Nhìn ký tự mới trên màn hình đo mắt.';
    show('waiting');
  }

  function applyInputMode(mode) {
    if (!['speak', 'tablet'].includes(mode)) return;
    inputMode = mode;
    document.getElementById('input-mode-label').textContent = mode === 'tablet'
      ? 'Chọn trên tablet' : 'Đọc bằng giọng nói';
    if (!testScreen.classList.contains('active')) return;
    const tabletMode = mode === 'tablet';
    testScreen.classList.toggle('speech-mode', mode === 'speak');
    accepting = tabletMode && !answerSubmitted && performance.now() < deadline;
    keys.querySelectorAll('button').forEach(button => { button.disabled = !accepting; });
    confirm.disabled = !accepting || !selected;
    document.getElementById('test-instruction').textContent = tabletMode
      ? 'Chọn ký tự bạn nhìn thấy trên màn hình đo'
      : 'Hãy đọc to ký tự bạn nhìn thấy trên màn hình đo';
    document.getElementById('answer-guide').textContent = tabletMode
      ? 'Bấm chọn chữ tương ứng bên dưới.'
      : 'Đọc to, rõ một ký tự khi thanh thời gian đang chạy.';
    document.getElementById('answer-caption').textContent = tabletMode
      ? 'Ký tự bạn đã chọn'
      : 'Hệ thống đang nghe giọng nói';
    if (mode === 'speak') letter.textContent = '🎙';
  }

  function startWindow(command) {
    stopWindow();
    answerSubmitted = false;
    windowId = String(command.window_id || '');
    resetSelection();
    const eye = String(command.eye_side || '').toUpperCase();
    document.getElementById('eye-label').textContent = eye === 'RIGHT' ? 'Mắt phải' : eye === 'LEFT' ? 'Mắt trái' : 'Đang đo mắt';
    const seconds = Math.max(0.1, Number(command.countdown_seconds) || 3);
    deadline = performance.now() + seconds * 1000;
    show('test');
    if (inputMode) applyInputMode(inputMode);
    else document.getElementById('test-instruction').textContent = 'Đang đồng bộ chế độ nhập với máy đo…';
    bar.style.transition = 'none';
    bar.style.transform = 'scaleX(1)';
    void bar.offsetWidth;
    bar.style.transition = `transform ${seconds}s linear`;
    bar.style.transform = 'scaleX(0)';
    timer = setTimeout(stopWindow, seconds * 1000);
  }

  LETTERS.forEach(value => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'key';
    button.textContent = value;
    button.setAttribute('aria-label', `Chọn ký tự ${value}`);
    button.disabled = true;
    button.addEventListener('click', () => {
      if (!accepting || performance.now() >= deadline) return;
      selected = value;
      letter.textContent = value;
      confirm.disabled = false;
      keys.querySelectorAll('button').forEach(key => key.classList.toggle('selected', key === button));
    });
    keys.appendChild(button);
  });

  confirm.addEventListener('click', () => {
    if (!accepting || !LETTERS.includes(selected) || performance.now() >= deadline || ws?.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: 'ui_event', action: 'speak_letter', payload: { letter: selected, window_id: windowId } }));
    answerSubmitted = true;
    stopWindow();
    bar.style.transform = 'scaleX(0)';
  });

  document.querySelectorAll('[data-input-mode]').forEach(button => {
    button.addEventListener('click', () => {
      if (!document.getElementById('mode-choice').classList.contains('active') || modeChoiceSubmitted || ws?.readyState !== WebSocket.OPEN) return;
      const mode = button.dataset.inputMode;
      if (!['speak', 'tablet'].includes(mode)) return;
      modeChoiceSubmitted = true;
      document.querySelectorAll('[data-input-mode]').forEach(option => { option.disabled = true; });
      document.getElementById('mode-choice-note').textContent = 'Đã chọn. Vui lòng chờ bắt đầu đo.';
      ws.send(JSON.stringify({ type: 'ui_event', action: 'select_input_mode', payload: { mode } }));
    });
  });

  function onCommand(command) {
    const type = command?.type;
    const mode = command?.mode;
    if (type === 'station_home') {
      stopWindow();
      answerSubmitted = false;
      modeChoiceSubmitted = false;
      patientName = '';
      resetSelection();
      document.querySelectorAll('[data-input-mode]').forEach(option => { option.disabled = false; });
      document.getElementById('patient-name').textContent = 'Đang chờ';
      document.getElementById('welcome-note').textContent = 'Vui lòng nhìn màn hình đo mắt và chờ hướng dẫn.';
      show('welcome');
    } else if (type === 'input_mode') {
      applyInputMode(command.input_mode);
    } else if (mode === 'input_select') {
      stopWindow();
      modeChoiceSubmitted = false;
      document.querySelectorAll('[data-input-mode]').forEach(option => { option.disabled = false; });
      document.getElementById('mode-choice-note').textContent = 'Vui lòng chọn một cách trả lời.';
      show('mode-choice');
    } else if (type === 'show_single' || mode === 'single') {
      // SHOW_ROW presents the first glyph before listening. Only the later
      // command with countdown_seconds opens the answer window on the tablet.
      if (command.countdown_seconds != null) startWindow(command);
      else if (!testScreen.classList.contains('active')) waiting('Chuẩn bị đọc ký tự trên màn hình đo mắt.');
    } else if (type === 'listen_window_start') {
      startWindow(command);
    } else if (type === 'show_row' || mode === 'row') {
      startWindow(command);
    } else if (type === 'results' || mode === 'results' || command.scene === 'complete') {
      stopWindow();
      document.getElementById('complete-text').textContent = command.text_vi || 'Cảm ơn bạn đã tham gia kiểm tra thị lực.';
      show('complete');
    } else if (mode === 'welcome') {
      stopWindow();
      if (command.patient_name) patientName = String(command.patient_name).trim();
      const displayName = patientName || command.patient_id || 'Đang chờ';
      document.getElementById('patient-name').textContent = displayName;
      if (command.input_mode) applyInputMode(command.input_mode);
      show('welcome');
    } else if (type === 'show_message' || type === 'ui_screen') {
      const text = command.text_vi || 'Vui lòng chờ hướng dẫn trên màn hình đo mắt.';
      if (command.scene === 'idle' || text.includes('khu vực chỉ định')) {
        stopWindow();
        patientName = '';
        document.getElementById('patient-name').textContent = 'Đang chờ';
        document.getElementById('welcome-note').textContent = text;
        show('welcome');
      } else if (!testScreen.classList.contains('active')) {
        waiting(text);
      }
    }
  }

  function connect() {
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${protocol}://${location.host}/ws/display`);
    ws.onmessage = event => {
      try { onCommand(JSON.parse(event.data)); } catch (error) { console.warn('Display event:', error); }
    };
    ws.onclose = () => {
      waiting('Mất kết nối với máy đo. Đang kết nối lại…');
      setTimeout(connect, 1500);
    };
    ws.onerror = () => ws.close();
  }

  connect();
})();

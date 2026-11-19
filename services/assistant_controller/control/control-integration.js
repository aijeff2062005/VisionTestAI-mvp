(() => {
  // Adapter only: the approved tablet design remains unchanged.
  let ws;
  const confirmButton = document.getElementById('confirm');
  const continueButton = document.getElementById('continue-next');
  const SLOAN_LETTERS = new Set(['C', 'D', 'H', 'K', 'N', 'O', 'R', 'S', 'V', 'Z']);

  function installSloanKeyboard() {
    const screen = document.getElementById('screen-test');
    if (!screen) return;
    // Keep the mockup's full-screen absolute layout; changing this to
    // `relative` collapses the screen to the keyboard's content height.
    screen.style.position = 'absolute';
    screen.style.inset = '0';

    // The approved artwork has an A-Z keyboard baked into its image. Cover it
    // and render the actual 10-letter Sloan keyboard above the artwork.
    const mask = document.createElement('div');
    mask.id = 'sloan-keyboard-mask';
    Object.assign(mask.style, {
      position: 'absolute', left: '0', right: '0', bottom: '0', height: '36%',
      background: '#fff', zIndex: '20'
    });
    screen.appendChild(mask);

    const keyboard = document.createElement('div');
    keyboard.id = 'sloan-keyboard';
    Object.assign(keyboard.style, {
      position: 'absolute', left: '2.5%', right: '2.5%', bottom: '1.5%', height: '28%',
      display: 'grid', gridTemplateColumns: 'repeat(10, 1fr)', gap: '0.55%', zIndex: '21'
    });
    const mainLetter = document.getElementById('main-letter');
    let selected = mainLetter?.textContent?.trim().toUpperCase() || 'K';
    SLOAN_LETTERS.forEach(letter => {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = letter;
      button.setAttribute('aria-label', `Chọn chữ ${letter}`);
      Object.assign(button.style, {
        border: '1px solid #cfe2f8', borderRadius: '8px', background: '#fff',
        color: '#071332', fontSize: 'clamp(22px, 3vw, 48px)', fontWeight: '800',
        cursor: 'pointer'
      });
      const select = () => {
        selected = letter;
        if (mainLetter) mainLetter.textContent = letter;
        keyboard.querySelectorAll('button').forEach(b => {
          b.style.background = b.textContent === selected ? '#d7ebff' : '#fff';
          b.style.border = b.textContent === selected ? '3px solid #1474e8' : '1px solid #cfe2f8';
          b.style.color = b.textContent === selected ? '#1169dc' : '#071332';
        });
      };
      button.addEventListener('click', select);
      keyboard.appendChild(button);
    });
    screen.appendChild(keyboard);
    keyboard.querySelectorAll('button').forEach(b => {
      if (b.textContent === selected) {
        b.style.background = '#d7ebff';
        b.style.border = '3px solid #1474e8';
        b.style.color = '#1169dc';
      }
    });
    document.querySelectorAll('.letter-hit').forEach(button => { button.hidden = true; });
    const bakedK = document.getElementById('k-reset');
    const selectionBox = document.getElementById('selection-box');
    if (bakedK) bakedK.style.display = 'none';
    if (selectionBox) selectionBox.style.display = 'none';
  }

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws/display`);
    ws.onmessage = (event) => {
      let command;
      try { command = JSON.parse(event.data); } catch (_) { return; }
      if (command.type === 'show_single' || command.type === 'show_row' || command.mode === 'single' || command.mode === 'row') {
        if (continueButton) continueButton.click();
      }
    };
    ws.onclose = () => setTimeout(connect, 1500);
    ws.onerror = () => ws.close();
  }

  if (confirmButton) {
    // Capture before index.html's local prototype handler. The tablet must
    // advance only after the existing event has been sent successfully.
    confirmButton.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
      const selected = document.querySelector('#main-letter')?.textContent?.trim().toUpperCase();
      if (!selected || !SLOAN_LETTERS.has(selected) || !ws || ws.readyState !== WebSocket.OPEN) {
        window.dispatchEvent(new CustomEvent('control:send-failed'));
        return;
      }
      ws.send(JSON.stringify({type: 'ui_event', action: 'speak_letter', payload: {letter: selected}}));
      const testScreen = document.getElementById('screen-test');
      const continueScreen = document.getElementById('screen-continue');
      if (testScreen && continueScreen) {
        testScreen.classList.remove('active');
        continueScreen.classList.add('active');
      }
    }, true);
  }

  // The artwork contains A-Z hotspots; this flow uses the existing Sloan set.
  document.querySelectorAll('.letter-hit').forEach((button) => {
    if (!SLOAN_LETTERS.has(button.dataset.letter)) button.hidden = true;
  });
  installSloanKeyboard();
  connect();
})();

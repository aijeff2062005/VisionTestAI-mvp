let distanceM = 5;
const LETTERS = ['C','D','H','K','N','O','R','S','V','Z'];
// Thang thập phân của bệnh viện: 1/10 … 10/10 (lưu nội bộ bằng logMAR).
const ROWS = [1.0, 0.69897, 0.52288, 0.39794, 0.30103, 0.22185, 0.15490, 0.09691, 0.04576, 0.0];
const VN_TENTHS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

const $ = id => document.getElementById(id);
const els = {
  chart: $('chart'),
  rowIndex: $('rowIndex'),
  spacingFactor: $('spacingFactor'),
  screenPreset: $('screenPreset'),
  pxPerMm: $('pxPerMm'),
  measuredMm: $('measuredMm'),
  calibrationBar: $('calibrationBar'),
  mAcuity: $('mAcuity'),
  mDistance: $('mDistance'),
  mLogmar: $('mLogmar'),
  mHeightMm: $('mHeightMm'),
  mStrokeMm: $('mStrokeMm'),
  mHeightPx: $('mHeightPx'),
  mRowWidth: $('mRowWidth'),
  mFit: $('mFit'),
  fontStatus: $('fontStatus'),
  chartTitle: $('chartTitle'),
  chartSubtitle: $('chartSubtitle'),
  fitFooter: $('fitFooter'),
  modeGroup: $('modeGroup'),
  calibrationBarFs: $('calibrationBarFs'),
  measuredMmFs: $('measuredMmFs'),
  fsCalibrate: $('fsCalibrate')
};

const CAL_TARGET_MM = 100;
// v2: invalidate bad saves from the shrink/wrong-bar calibration bug
const CAL_STORAGE_KEY = 'ac.chart.pxPerMm.v2';

const state = {
  mode: 'row',
  rowIndex: 7,
  letters: randomLetters(5),
  singleLetter: randomLetter(),
  calBarPx: 0,
  calTargetMm: CAL_TARGET_MM,
  calibrationMode: 'auto',
  diagonalInches: 32,
  audioUnlocked: false,
  audioGesture: false
};

const promptAudioEl = () => $('promptAudio');

let welcomeTimer = null;
let listenProgressFrame = null;
let listenProgressTimer = null;
let listenProgressEndTime = 0;

function clearWelcomeTimer() {
  if (welcomeTimer) {
    clearInterval(welcomeTimer);
    welcomeTimer = null;
  }
}

function stopListenProgress() {
  if (listenProgressFrame) cancelAnimationFrame(listenProgressFrame);
  listenProgressFrame = null;
  if (listenProgressTimer) {
    clearInterval(listenProgressTimer);
    listenProgressTimer = null;
  }
  listenProgressEndTime = 0;
  const bar = $('listenProgress');
  const fill = $('listenProgressFill');
  if (fill) {
    fill.style.transition = 'none';
    fill.style.transform = 'scaleX(0)';
  }
  if (bar) bar.hidden = true;
}

function startListenProgress(seconds) {
  stopListenProgress();
  const duration = Number(seconds);
  const bar = $('listenProgress');
  const fill = $('listenProgressFill');
  const label = $('listenProgressText');
  if (!bar || !fill || !label || !Number.isFinite(duration) || duration <= 0) return;

  bar.hidden = false;
  listenProgressEndTime = Date.now() + duration * 1000;
  let remaining = Math.ceil(duration);
  label.textContent = `${remaining}s`;

  fill.style.transition = 'none';
  fill.style.transform = 'scaleX(1)';
  void fill.offsetWidth;

  fill.style.transition = `transform ${duration}s linear`;
  fill.style.transform = 'scaleX(0)';

  listenProgressTimer = setInterval(() => {
    const leftMs = listenProgressEndTime - Date.now();
    const leftSec = Math.max(0, Math.ceil(leftMs / 1000));
    if (leftSec > 0) {
      const nextTxt = `${leftSec}s`;
      if (label.textContent !== nextTxt) {
        label.textContent = nextTxt;
      }
    } else {
      stopListenProgress();
    }
  }, 100);
}
function setAudioUnlockGate(visible) {
  const gate = $('audioUnlock');
  if (!gate) return;
  gate.hidden = !visible;
}

function setAudioChip(kind, label) {
  const chip = $('btnAudioChip');
  if (!chip) return;
  chip.textContent = label || 'Loa';
  chip.classList.remove('live', 'warn', 'err');
  if (kind) chip.classList.add(kind);
}

async function unlockAudio() {
  const el = promptAudioEl();
  if (el) {
    // Silent unlock beep — keep volume at 1 so later prompts are audible.
    el.muted = false;
    el.volume = 1;
    el.src = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=';
    try {
      await el.play();
      state.audioUnlocked = true;
    } catch (_) { /* gesture used; still dismiss the gate */ }
    try { el.pause(); } catch (_) { /* ignore */ }
    el.removeAttribute('src');
    try { el.load(); } catch (_) { /* ignore */ }
  }
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (Ctx) {
      const ctx = new Ctx();
      if (ctx.state === 'suspended') await ctx.resume();
      await ctx.close();
    }
  } catch (_) { /* ignore */ }
  // A tap is enough to dismiss the full-screen gate. Later play() failures
  // only light the operator chip — they must not restack this overlay.
  state.audioGesture = true;
  setAudioUnlockGate(false);
  setAudioChip(state.audioUnlocked ? 'live' : 'warn', state.audioUnlocked ? 'Loa: đã bật' : 'Loa: chạm lại');
}

async function playPromptUrl(url, _text) {
  if (!url) return;
  const el = promptAudioEl();
  if (!el) return;
  if (!state.audioUnlocked) {
    try { await unlockAudio(); } catch (_) { /* still may be locked */ }
  }
  el.muted = false;
  el.volume = 1;
  el.src = url;
  try {
    await el.play();
    state.audioUnlocked = true;
    setAudioUnlockGate(false);
    setAudioChip('live', 'Loa: đang phát');
  } catch (err) {
    console.warn('playPromptUrl failed', url, err);
    if (!state.audioGesture) setAudioUnlockGate(true);
    setAudioChip('err', 'Bật loa');
  }
}

function stopPromptAudio() {
  const el = promptAudioEl();
  if (!el) return;
  try { el.pause(); } catch (_) { /* ignore */ }
  el.removeAttribute('src');
  try { el.load(); } catch (_) { /* ignore */ }
}

function randomLetter() { return LETTERS[Math.floor(Math.random() * LETTERS.length)]; }
function randomLetters(n) { return [...LETTERS].sort(() => Math.random() - .5).slice(0, n); }
function pxPerMm() { return Math.max(.1, parseFloat(els.pxPerMm.value) || 5.42); }
function spacingFactor() { return parseFloat(els.spacingFactor.value) || 1; }
function decimalFromLogMAR(logmar) { return Math.pow(10, -logmar); }
function optotypeHeightMm(distanceM, decimalVA) { return 1.4544 * distanceM / decimalVA; }
function fmt(n, d=2) { return Number(n).toLocaleString('vi-VN', {minimumFractionDigits:d, maximumFractionDigits:d}); }
function fmtInt(n) { return Number(n).toLocaleString('vi-VN', {maximumFractionDigits:0}); }
function fmtSmart(n) { return Number(n).toLocaleString('vi-VN', {maximumFractionDigits: n < 1 ? 3 : 2}); }
function vnOver10(decimal) {
  const tenths = decimal * 10;
  let best = VN_TENTHS[0];
  let bestD = Math.abs(tenths - best);
  for (const s of VN_TENTHS) {
    const d = Math.abs(tenths - s);
    if (d < bestD) { bestD = d; best = s; }
  }
  return `${best}/10`;
}

function loadSavedCalibration() {
  try {
    const saved = parseFloat(localStorage.getItem(CAL_STORAGE_KEY) || '');
    if (Number.isFinite(saved) && saved > 0.2 && saved < 40) {
      els.pxPerMm.value = saved.toFixed(4);
      els.screenPreset.value = 'custom';
    }
  } catch (_) { /* ignore */ }
}

function saveCalibration(ppm) {
  try { localStorage.setItem(CAL_STORAGE_KEY, String(ppm)); } catch (_) { /* ignore */ }
}

function applyDisplayConfig(config) {
  if (!config || typeof config !== 'object') return;
  const effective = Number(config.effective_px_per_mm ?? config.px_per_mm);
  if (Number.isFinite(effective) && effective >= .2 && effective <= 40) {
    els.pxPerMm.value = effective.toFixed(4);
    saveCalibration(effective);
  }
  const dist = Number(config.distance_m);
  if (Number.isFinite(dist) && dist > 0) distanceM = dist;
  const target = Number(config.calibration_target_mm);
  if (Number.isFinite(target) && target >= 20 && target <= 500) state.calTargetMm = target;
  state.calibrationMode = String(config.calibration_mode || state.calibrationMode);
  state.diagonalInches = Number(config.diagonal_inches) || state.diagonalInches;
  const summary = $('chartSetupSummary');
  if (summary) summary.textContent = `Người lớn · chữ Sloan · khoảng cách ${fmtSmart(distanceM)}m · màn hình ${fmtSmart(state.diagonalInches)} inch`;
  els.screenPreset.value = 'custom';
  render();
}

async function loadDisplayConfig() {
  try {
    const response = await fetch('/api/display/config', { cache: 'no-store' });
    const data = await response.json();
    if (response.ok && data.ok !== false) applyDisplayConfig(data);
  } catch (_) { /* local cache remains the offline fallback */ }
}

async function persistManualCalibration(ppm) {
  try {
    await fetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        display_calibration_mode: 'manual',
        display_px_per_mm: ppm,
        display_calibration_target_mm: state.calTargetMm,
      }),
    });
  } catch (_) { /* keep local cache if server is temporarily unavailable */ }
}

function setBarPixels(el, barPx, labelMm) {
  if (!el) return;
  const px = Math.max(1, Math.round(barPx));
  el.style.width = `${px}px`;
  el.style.minWidth = `${px}px`;
  el.dataset.label = `${fmtSmart(labelMm)} mm`;
}

function syncCalibrationBars() {
  const ppm = pxPerMm();
  // Always draw a true 100mm bar (scroll if needed). Never shrink+relabel —
  // that desynced CSS width from what the ruler measured and caused ~75mm remasure.
  const targetMm = state.calTargetMm || CAL_TARGET_MM;
  const barPx = targetMm * ppm;
  state.calBarPx = barPx;
  state.calTargetMm = targetMm;

  setBarPixels(els.calibrationBar, barPx, targetMm);
  setBarPixels(els.calibrationBarFs, barPx, targetMm);

  const hint = `Thanh đen = <strong>${fmtSmart(targetMm)} mm</strong>. Đo hết thanh (cuộn nếu cần), nhập mm đo được, rồi Áp dụng.`;
  const hintEl = $('calBarHint');
  const hintFs = $('calBarHintFs');
  if (hintEl) hintEl.innerHTML = hint;
  if (hintFs) hintFs.innerHTML = hint;

  layoutFsCalibratePanel(barPx);
  // Sidebar wrap must scroll, not clip/shrink the bar
  const sideWrap = els.calibrationBar && els.calibrationBar.parentElement;
  if (sideWrap) {
    sideWrap.style.overflowX = 'auto';
    sideWrap.style.maxWidth = '100%';
  }
}

/** Size fullscreen calibration panel from viewport + bar width. */
function layoutFsCalibratePanel(barPx) {
  if (!els.fsCalibrate) return;
  const margin = 24;
  const padX = 40;
  const minPanel = 280;
  const maxPanel = Math.max(minPanel, window.innerWidth - margin);
  const needed = Math.ceil(barPx + padX);
  // Grow panel to fit the full bar whenever possible
  const panelW = Math.min(Math.max(needed, minPanel), maxPanel);
  els.fsCalibrate.style.setProperty('--fs-cal-width', `${panelW}px`);

  const wrap = els.calibrationBarFs && els.calibrationBarFs.parentElement;
  if (wrap) {
    // Leave room for the bar; scroll if the monitor is still too narrow
    wrap.style.maxWidth = 'none';
    wrap.style.width = '100%';
    wrap.style.overflowX = barPx + 24 > panelW ? 'auto' : 'visible';
  }
}

/**
 * Apply ruler measurement.
 * Scale so the labeled 100mm bar becomes physically `measured` → then 100mm.
 * Uses the visible bar that matches the input (sidebar vs fullscreen) —
 * never the hidden FS bar (getBoundingClientRect width 0 → wrong CSS fallback).
 */
function applyCalibrationFrom(measuredInput) {
  const measured = parseFloat(String(measuredInput.value).replace(',', '.'));
  if (!Number.isFinite(measured) || measured <= 0) {
    alert('Nhập chiều dài đo được (mm), ví dụ 270');
    return;
  }
  const fromFs = measuredInput === els.measuredMmFs;
  const barEl = fromFs
    ? (els.calibrationBarFs || els.calibrationBar)
    : (els.calibrationBar || els.calibrationBarFs);
  const rendered = barEl ? barEl.getBoundingClientRect().width : 0;
  const intended = state.calBarPx || (CAL_TARGET_MM * pxPerMm());
  // Prefer on-screen width; fall back to the CSS width we set (100mm × px/mm)
  const usePx = rendered > 8 ? rendered : intended;
  // Equivalent: oldPpm * 100 / measured when bar is exactly 100mm CSS
  const newPpm = usePx / measured;
  if (!Number.isFinite(newPpm) || newPpm < 0.2 || newPpm > 40) {
    alert(`Calibration không hợp lệ (px/mm=${newPpm.toFixed?.(3) || newPpm}). Đo lại thanh và thử lại.`);
    return;
  }
  els.pxPerMm.value = newPpm.toFixed(4);
  els.screenPreset.value = 'custom';
  saveCalibration(newPpm);
  els.measuredMm.value = String(state.calTargetMm);
  if (els.measuredMmFs) els.measuredMmFs.value = String(state.calTargetMm);
  persistManualCalibration(newPpm);
  render();
  const tip = `Đã set ${newPpm.toFixed(3)} px/mm (đo ${fmtSmart(measured)} mm → ${fmtSmart(usePx)} px). Đo lại thanh — phải ≈ ${fmtSmart(state.calTargetMm)} mm.`;
  if ($('calBarHintFs')) $('calBarHintFs').innerHTML = tip;
  if ($('calBarHint')) $('calBarHint').innerHTML = tip;
}

function resetCalibration() {
  try {
    localStorage.removeItem(CAL_STORAGE_KEY);
    localStorage.removeItem('ac.chart.pxPerMm');
  } catch (_) { /* ignore */ }
  els.screenPreset.value = '5.42';
  els.pxPerMm.value = '5.42';
  state.calTargetMm = CAL_TARGET_MM;
  els.measuredMm.value = String(CAL_TARGET_MM);
  if (els.measuredMmFs) els.measuredMmFs.value = String(CAL_TARGET_MM);
  persistManualCalibration(5.42);
  render();
}

function rowLabel(logmar) {
  const decimal = decimalFromLogMAR(logmar);
  return {
    top: `${vnOver10(decimal)}`,
    sub: ''
  };
}

function fillRows() {
  els.rowIndex.innerHTML = ROWS.map((logmar, i) => {
    const label = rowLabel(logmar);
    return `<option value="${i}">${label.top} · ${label.sub}</option>`;
  }).join('');
  els.rowIndex.value = String(state.rowIndex);
}

function currentRow() {
  const logmar = ROWS[state.rowIndex];
  const decimal = decimalFromLogMAR(logmar);
  const heightMm = optotypeHeightMm(distanceM, decimal);
  return { logmar, decimal, heightMm, strokeMm: heightMm / 5 };
}

const glyphMeasureCanvas = document.createElement('canvas');
const glyphMeasureContext = glyphMeasureCanvas.getContext('2d');

function glyphFontSize(letter, targetPx) {
  if (!glyphMeasureContext) return targetPx;
  glyphMeasureContext.font = '100px OpticianSans';
  const ink = glyphMeasureContext.measureText(letter);
  const inkHeight = ink.actualBoundingBoxAscent + ink.actualBoundingBoxDescent;
  return inkHeight > 0 ? targetPx * 100 / inkHeight : targetPx;
}

function glyph(letter, sizePx) {
  return `<span class="glyph" style="--optotype-size:${sizePx}px;font-size:${glyphFontSize(letter, sizePx)}px">${letter}</span>`;
}

function renderLine(logmar, letters, sizePx, gapPx) {
  const label = rowLabel(logmar);
  return `
    <div class="line-row">
      <div class="line-label">${label.top}<span class="sub">${label.sub}</span></div>
      <div class="glyph-line" style="gap:${gapPx}px">${letters.map(ch => glyph(ch, sizePx)).join('')}</div>
    </div>`;
}

function renderSingle(sizePx) {
  const label = rowLabel(currentRow().logmar);
  // Same row layout as multi-letter so the result column sits beside the glyph
  return `
    <div class="line-row single-row">
      <div class="line-label">${label.top}<span class="sub">${label.sub}</span></div>
      <div class="glyph-line">
        <span class="single-glyph" style="--optotype-size:${sizePx}px;font-size:${glyphFontSize(state.singleLetter, sizePx)}px">${state.singleLetter}</span>
      </div>
    </div>`;
}

function renderFullChart() {
  return ROWS.map(logmar => {
    const decimal = decimalFromLogMAR(logmar);
    const heightMm = optotypeHeightMm(distanceM, decimal);
    const sizePx = heightMm * pxPerMm();
    const gapPx = sizePx * .6;
    return renderLine(logmar, randomLetters(5), sizePx, gapPx);
  }).join('');
}

function updateModeButtons() {
  els.modeGroup.querySelectorAll('button').forEach(btn => btn.classList.toggle('active', btn.dataset.mode === state.mode));
}

function metrics(row, sizePx, gapPx) {
  const lineWidthPx = 5 * sizePx + 4 * gapPx;
  const fit2560 = lineWidthPx <= 2560;
  const fit3840 = lineWidthPx <= 3840;
  let fitText = 'Phù hợp';
  let fitClass = 'ok';
  if (!fit3840) { fitText = 'Quá rộng, nên dùng 1 ký tự'; fitClass = 'bad'; }
  else if (!fit2560) { fitText = 'Hợp 32 inch 4K, 27 inch cần kiểm tra'; fitClass = 'ok'; }

  els.mAcuity.textContent = vnOver10(row.decimal);
  if (els.mDistance) els.mDistance.textContent = `${fmtSmart(distanceM)}m`;
  els.mLogmar.textContent = row.logmar.toFixed(2);
  els.mHeightMm.textContent = `${fmt(row.heightMm)} mm`;
  els.mStrokeMm.textContent = `${fmt(row.strokeMm)} mm`;
  els.mHeightPx.textContent = `${fmtInt(sizePx)} px`;
  els.mRowWidth.textContent = `${fmt(lineWidthPx / pxPerMm(), 1)} mm · ${fmtInt(lineWidthPx)} px`;
  els.mFit.innerHTML = `<span class="${fitClass}">${fitText}</span>`;
  els.fitFooter.textContent = `Optotype ${fmt(row.heightMm)}mm · stroke ${fmt(row.strokeMm)}mm · dòng ${fmt(lineWidthPx / pxPerMm(), 1)}mm`;
}

function detectFont() {
  if (!document.fonts) {
    els.fontStatus.textContent = 'Không kiểm tra được font';
    return;
  }
  const loaded = document.fonts.check('48px "OpticianSans"');
  els.fontStatus.textContent = loaded ? 'Optician Sans đã load' : 'Chưa load font / đang dùng fallback';
}

function render() {
  updateModeButtons();
  const row = currentRow();
  const sizePx = row.heightMm * pxPerMm();
  const gapPx = sizePx * spacingFactor();
  syncCalibrationBars();

  if (state.mode === 'single') {
    els.chart.innerHTML = renderSingle(sizePx);
    els.chartTitle.textContent = 'Một chữ';
    els.chartSubtitle.textContent = `${state.singleLetter} · ${fmtSmart(distanceM)}m`;
  } else if (state.mode === 'chart') {
    els.chart.innerHTML = renderFullChart();
    els.chartTitle.textContent = 'Bảng chữ';
    els.chartSubtitle.textContent = `Toàn bộ dòng · ${fmtSmart(distanceM)}m`;
  } else {
    els.chart.innerHTML = renderLine(row.logmar, state.letters, sizePx, gapPx);
    els.chartTitle.textContent = 'Một dòng chữ';
    els.chartSubtitle.textContent = `${state.letters.join(' ')} · ${fmtSmart(distanceM)}m`;
  }
  metrics(row, sizePx, gapPx);
  detectFont();
}

function randomize() {
  state.letters = randomLetters(5);
  state.singleLetter = randomLetter();
  render();
}

function updateFullscreenClass() {
  const fs = !!(document.fullscreenElement || document.webkitFullscreenElement);
  document.body.classList.toggle('is-fullscreen', fs);
  render();
  sendDisplayMetrics();
}

function toggleExamMode() {
  document.body.classList.toggle('exam-mode');
  if (document.body.classList.contains('exam-mode')) {
    document.body.classList.add('fs-cal-hidden');
    document.body.classList.remove('fs-cal-visible');
  }
  render();
}

function toggleFsCalibrate() {
  if (document.body.classList.contains('exam-mode')) {
    document.body.classList.toggle('fs-cal-visible');
    document.body.classList.toggle('fs-cal-hidden', !document.body.classList.contains('fs-cal-visible'));
    return;
  }
  document.body.classList.toggle('fs-cal-hidden');
}

fillRows();
loadSavedCalibration();
render();
if (document.fonts) document.fonts.ready.then(() => setTimeout(render, 80));

els.rowIndex.addEventListener('change', () => { state.rowIndex = parseInt(els.rowIndex.value, 10); render(); });
els.spacingFactor.addEventListener('change', render);
els.screenPreset.addEventListener('change', () => {
  if (els.screenPreset.value !== 'custom') els.pxPerMm.value = els.screenPreset.value;
  render();
  persistManualCalibration(pxPerMm());
});
els.pxPerMm.addEventListener('input', render);
els.pxPerMm.addEventListener('change', () => persistManualCalibration(pxPerMm()));
els.modeGroup.addEventListener('click', e => {
  const btn = e.target.closest('button[data-mode]');
  if (!btn) return;
  state.mode = btn.dataset.mode;
  render();
});
$('btnRandomTop').addEventListener('click', randomize);
$('btnFullscreenTop').addEventListener('click', () => document.documentElement.requestFullscreen?.());
$('btnExamTop').addEventListener('click', toggleExamMode);
$('btnCalibrate').addEventListener('click', () => applyCalibrationFrom(els.measuredMm));
if ($('btnCalibrateFs')) {
  $('btnCalibrateFs').addEventListener('click', () => applyCalibrationFrom(els.measuredMmFs));
}
if ($('btnResetCal')) {
  $('btnResetCal').addEventListener('click', resetCalibration);
}
if ($('btnResetCalFs')) {
  $('btnResetCalFs').addEventListener('click', resetCalibration);
}
if ($('btnHideFsCal')) {
  $('btnHideFsCal').addEventListener('click', () => {
    document.body.classList.add('fs-cal-hidden');
  });
}

window.addEventListener('resize', () => {
  syncCalibrationBars();
  sendDisplayMetrics();
});
document.addEventListener('fullscreenchange', updateFullscreenClass);
document.addEventListener('webkitfullscreenchange', updateFullscreenClass);

/* ---- AC remote control (WebSocket) ---- */
function rowIndexForLogmar(logmar) {
  let best = 0, bestDiff = Infinity;
  ROWS.forEach((v, i) => {
    const d = Math.abs(v - logmar);
    if (d < bestDiff) { bestDiff = d; best = i; }
  });
  return best;
}

async function ackStimulusAfterPaint(cmd) {
  if (!cmd || !cmd.window_id || !acWs || acWs.readyState !== WebSocket.OPEN) return;
  if (document.fonts && document.fonts.ready) {
    await Promise.race([
      document.fonts.ready,
      new Promise(resolve => setTimeout(resolve, 1500))
    ]);
  }
  const fontReady = !document.fonts || document.fonts.check('48px "OpticianSans"');
  if (!fontReady) {
    console.error('OpticianSans is not ready; refusing stimulus readiness ACK');
    return;
  }
  await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  if (state.activeWindowId === cmd.window_id && acWs && acWs.readyState === WebSocket.OPEN) {
    acWs.send(JSON.stringify({
      type: 'stimulus_ready', window_id: cmd.window_id, font_ready: fontReady
    }));
  }
}

let acWs = null;
let lastDisplayBootId = null;
let lastDisplayRevision = 0;
let lastDisplayFingerprint = '';

function sendUiEvent(action, payload) {
  if (!acWs || acWs.readyState !== WebSocket.OPEN) return;
  const msg = { type: 'ui_event', action };
  if (payload && typeof payload === 'object') msg.payload = payload;
  acWs.send(JSON.stringify(msg));
}

function hideLetterPad() {
  const pad = $('letterPad');
  if (!pad) return;
  pad.hidden = true;
  pad.innerHTML = '';
}

function showLetterPad(prompt, opts) {
  const pad = $('letterPad');
  if (!pad) return;
  const options = opts || {};
  pad.hidden = false;
  pad.innerHTML = '';
  if (prompt) {
    const p = document.createElement('div');
    p.className = 'letter-prompt';
    p.textContent = prompt;
    pad.appendChild(p);
  }
  LETTERS.forEach((ch) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = ch;
    btn.addEventListener('click', () => sendUiEvent('speak_letter', { letter: ch }));
    pad.appendChild(btn);
  });
  if (options.allowSkip) {
    const skip = document.createElement('button');
    skip.type = 'button';
    skip.className = 'letter-skip';
    skip.textContent = options.skipLabel || 'Bỏ qua (đúng)';
    skip.addEventListener('click', () => sendUiEvent(options.skipAction || 'skip_letter'));
    pad.appendChild(skip);
  }
}

function renderSkipButton(actionsEl, cmd) {
  if (!actionsEl || !cmd || !cmd.allow_skip) return;
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'btn ghost skip-btn';
  btn.textContent = cmd.skip_label || 'Bỏ qua';
  btn.addEventListener('click', () => sendUiEvent(cmd.skip_action || 'skip_step'));
  actionsEl.appendChild(btn);
  actionsEl.hidden = false;
}

function setSkipFab(cmd) {
  const fab = $('skipFab');
  if (!fab) return;
  if (!cmd || !cmd.allow_skip) {
    fab.hidden = true;
    fab.onclick = null;
    return;
  }
  fab.hidden = false;
  fab.textContent = cmd.skip_label || 'Bỏ qua';
  fab.onclick = () => sendUiEvent(cmd.skip_action || 'skip_step');
}

const SCENE_TITLE = {
  idle: 'Mời quý khách chờ',
  face: 'Nhìn vào máy nhận diện',
  stand: 'Đứng vào vị trí',
  cover_right: 'Che mắt phải',
  cover_left: 'Che mắt trái',
  cover_both: 'Mở cả hai mắt',
  countdown: 'Bắt đầu',
  rules: 'Cách đọc chữ',
  complete: 'Đã xong',
  welcome: 'Xin chào',
  register: 'Chưa có trong hệ thống',
  nomatch: 'Vui lòng đăng ký tại quầy',
  results: 'Kết quả đo thị lực',
  unclear: 'Đọc to hơn một chút',
};

function inferScene(cmd) {
  if (cmd && cmd.scene) return String(cmd.scene);
  const mode = (cmd && cmd.mode) || '';
  const text = String((cmd && cmd.text_vi) || '').toLowerCase();
  if ((cmd && cmd.type) === 'results' || mode === 'results') return 'results';
  if ((cmd && cmd.type) === 'letter_confirm' || mode === 'letter_confirm') return 'heard';
  if (mode === 'countdown') return 'countdown';
  if (mode === 'welcome' || mode === 'service_menu') return 'welcome';
  if (mode === 'register_prompt') return 'register';
  if (mode === 'queue_stub') return 'queue';
  if (text.includes('che mắt phải')) return 'cover_right';
  if (text.includes('che mắt trái')) return 'cover_left';
  if (text.includes('cả hai mắt') || text.includes('bỏ tay')) return 'cover_both';
  if (text.includes('face id') || text.includes('nhận diện') || text.includes('nhìn vào máy')) return 'face';
  if (text.includes('đăng ký') || text.includes('quầy tiếp nhận') || text.includes('danh sách hẹn')) return 'nomatch';
  if (text.includes('đứng') || text.includes('vị trí')) return 'stand';
  if (text.includes('chờ lịch') || text.includes('gallery') || mode === 'idle') return 'idle';
  if (text.includes('không rõ') || text.includes('đọc to hơn')) return 'unclear';
  return 'message';
}

function faceBoxSvg() {
  return `<div class="face-box" aria-hidden="true">
    <svg viewBox="0 0 88 112" fill="none">
      <rect x="6" y="4" width="76" height="104" rx="12" fill="#16302C"/>
      <rect x="14" y="14" width="60" height="72" rx="8" fill="#0A4A3E"/>
      <circle cx="44" cy="44" r="16" fill="#0E6B5A"/>
      <circle cx="44" cy="44" r="7" fill="#D6E8E3"/>
      <rect x="28" y="92" width="32" height="6" rx="3" fill="#2E7F6D"/>
    </svg>
    <span>Nhận diện</span>
  </div>
  <svg class="look-cue" viewBox="0 0 64 40" aria-hidden="true">
    <path d="M6 20 H46 M34 8 L52 20 L34 32" fill="none" stroke="#0E6B5A" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`;
}

function coverSvg(side) {
  const hideL = side === 'right' || side === 'both' ? '' : 'display:none';
  const hideR = side === 'left' || side === 'both' ? '' : 'display:none';
  const pad = side === 'both' ? '' : `<g class="an-arm">
    <path fill="#F0CFB4" d="${side === 'right' ? 'M70 210 Q40 150 118 118' : 'M350 210 Q380 150 302 118'}" stroke="#DCB294" stroke-width="22" stroke-linecap="round"/>
    <circle fill="#C8443F" cx="${side === 'right' ? '128' : '292'}" cy="108" r="28"/>
  </g>`;
  return `<svg class="cover-art" viewBox="0 0 420 300" aria-hidden="true">
    <circle style="${hideL}" fill="#D6E8E3" cx="132" cy="104" r="80"/>
    <circle style="${hideR}" fill="#D6E8E3" cx="288" cy="104" r="80"/>
    <circle fill="#F0CFB4" cx="210" cy="118" r="78"/>
    <path fill="#2A2320" d="M132 118 q8-78 78-78 q70 0 78 78 q-24-36-78-36 q-54 0-78 36z"/>
    <circle fill="#5B4636" cx="176" cy="120" r="10"/>
    <circle fill="#5B4636" cx="244" cy="120" r="10"/>
    <path fill="none" stroke="#2A2320" stroke-width="5" stroke-linecap="round" d="M192 148 q18 14 36 0"/>
    <path fill="#2E7F6D" d="M128 250 q0-46 82-46 q82 0 82 46"/>
    ${pad}
  </svg>`;
}

const coachPhotoSources = {
  idle: ['/static/art/vitringoi.jpg', 'Ảnh vị trí ngồi đo mắt tại bệnh viện'],
  stand: ['/static/art/vitringoi.jpg', 'Ảnh vị trí ngồi đo mắt tại bệnh viện'],
  face: ['/static/art/huongdanquetkhuonmat.jpg', 'Ảnh hướng dẫn nhìn vào máy nhận diện khuôn mặt'],
  cover_right: ['/static/art/domattrai.jpg', 'Đo mắt trái, che mắt phải'],
  cover_left: ['/static/art/domatphai.jpg', 'Đo mắt phải, che mắt trái']
};
const defaultCoachPhotoSources = Object.fromEntries(
  Object.entries(coachPhotoSources).map(([scene, value]) => [scene, [...value]])
);
const coachPhotoCache = new Map();
for (const [scene, [src, alt]] of Object.entries(coachPhotoSources)) {
  let image = [...coachPhotoCache.values()].find(cached => cached.src.endsWith(src));
  if (!image && scene === 'face') {
    image = $('remoteArt')?.querySelector('img.instruction-photo');
  }
  if (!image) {
    image = new Image();
  }
  image.className = 'instruction-photo';
  image.alt = alt;
  image.decoding = 'async';
  image.loading = 'eager';
  if (!image.src.endsWith(src)) image.src = src;
  image.decode().catch(() => console.warn('Instruction photo did not decode', src));
  coachPhotoCache.set(scene, image);
}

function applyInstructionImages(images) {
  if (!images || typeof images !== 'object') return;
  for (const [scene, fallback] of Object.entries(defaultCoachPhotoSources)) {
    if (scene === 'idle' || !Object.hasOwn(images, scene)) continue;
    const src = images[scene]?.url || fallback[0];
    if (coachPhotoSources[scene][0] === src) continue;
    coachPhotoSources[scene][0] = src;
    const image = new Image();
    image.className = 'instruction-photo';
    image.alt = fallback[1];
    image.decoding = 'async';
    image.loading = 'eager';
    image.src = src;
    image.decode().then(() => {
      if (coachPhotoSources[scene][0] !== src) return;
      coachPhotoCache.set(scene, image);
      if (scene === 'stand') coachPhotoCache.set('idle', image);
      if ($('remoteArt')?.dataset.scene === scene) setCoachArt(scene);
      if (scene === 'stand' && $('remoteArt')?.dataset.scene === 'idle') setCoachArt('idle');
    }).catch(() => {
      console.warn('Instruction photo unavailable', scene, src);
      if (src !== fallback[0] && coachPhotoSources[scene][0] === src) {
        applyInstructionImages({ [scene]: { url: fallback[0] } });
      }
    });
  }
  const stand = coachPhotoSources.stand[0];
  if (coachPhotoSources.idle[0] !== stand) {
    coachPhotoSources.idle[0] = stand;
    const image = coachPhotoCache.get('stand');
    if (image?.complete && image.naturalWidth) coachPhotoCache.set('idle', image);
  }
}

async function loadInstructionImages() {
  try {
    const response = await fetch('/api/instruction-images', { cache: 'no-store' });
    if (response.ok) applyInstructionImages((await response.json()).images);
  } catch (error) {
    console.warn('Instruction image settings unavailable', error);
  }
}

function coachArtHtml(scene) {
  if (scene === 'cover_both') return coverSvg('both');
  if (scene === 'unclear' || scene === 'nomatch' || scene === 'register') {
    return `<div class="photo-scene" style="height:26vh">
      <img class="person-img" src="/static/art/unclear_person.webp" alt="">
    </div>`;
  }
  return '';
}

function setCoachArt(scene) {
  const art = $('remoteArt');
  if (!art) return;
  const photo = coachPhotoCache.get(scene);
  if (art.dataset.scene === scene && !art.hidden && (!photo || art.firstElementChild === photo)) return;
  if (photo) {
    art.dataset.scene = scene;
    if (photo.complete && photo.naturalWidth) {
      art.replaceChildren(photo);
      art.hidden = false;
    } else {
      // Preserve the old picture until the new one is decoded, avoiding an
      // empty frame when Chrome evicts a decoded image under memory pressure.
      photo.decode().then(() => {
        if (art.dataset.scene === scene) {
          art.replaceChildren(photo);
          art.hidden = false;
        }
      }).catch(err => console.warn('Instruction photo unavailable', scene, err));
    }
    return;
  }
  const html = coachArtHtml(scene);
  if (!html) {
    art.hidden = true;
    art.innerHTML = '';
    art.dataset.scene = scene;
    return;
  }
  art.hidden = false;
  art.innerHTML = html;
  art.dataset.scene = scene;
}

function resetQueueEl() {
  const remoteQueue = $('remoteQueue');
  if (!remoteQueue) return remoteQueue;
  remoteQueue.textContent = '';
  remoteQueue.classList.remove('heard-optotype');
  remoteQueue.style.removeProperty('font-size');
  remoteQueue.removeAttribute('data-acuity');
  return remoteQueue;
}

function setCoachCopy(cmd, scene) {
  const msg = $('remoteMsg');
  const lead = $('remoteLead');
  if (!msg) return;
  const raw = String((cmd && cmd.text_vi) || '').trim();
  const title = SCENE_TITLE[scene] || '';
  if (scene === 'face') {
    msg.textContent = 'Nhìn vào máy nhận diện khuôn mặt.';
    if (lead) { lead.textContent = ''; lead.hidden = true; }
    return;
  }
  if (scene === 'heard' || scene === 'queue' || scene === 'welcome' || scene === 'countdown') {
    msg.textContent = scene === 'countdown' ? (title || 'Bắt đầu') : raw;
    if (lead) {
      const secs = Number(cmd && cmd.auto_continue_seconds);
      if (scene === 'welcome' && cmd && cmd.show_continue !== false && Number.isFinite(secs) && secs > 0) {
        lead.textContent = `Bắt đầu sau ${Math.ceil(secs)} giây`;
        lead.hidden = false;
      } else {
        lead.textContent = '';
        lead.hidden = true;
      }
    }
    return;
  }
  if (title && raw && raw.length <= 50) {
    msg.textContent = raw;
    if (lead) { lead.textContent = ''; lead.hidden = true; }
    return;
  }
  if (title) {
    msg.textContent = title;
    if (lead) { lead.textContent = ''; lead.hidden = true; }
    return;
  }
  msg.textContent = raw || '';
  if (lead) { lead.textContent = ''; lead.hidden = true; }
}

function setResultsGrid(cmd) {
  const grid = $('remoteResults');
  if (!grid) return;
  const acu = (cmd && cmd.acuity) || {};
  grid.classList.remove('res-rows');
  const cards = [];
  const order = [
    ['left', 'Mắt trái'],
    ['right', 'Mắt phải'],
    ['both', 'Hai mắt'],
  ];
  order.forEach(([key, label]) => {
    const eye = acu[key];
    if (!eye || !eye.vn_over_10) return;
    cards.push(
      `<div class="res-card"><span class="eye">${label}</span><span class="acu">${eye.vn_over_10}</span></div>`
    );
  });
  if (!cards.length) {
    grid.hidden = true;
    grid.innerHTML = '';
    return;
  }
  grid.innerHTML = cards.join('');
  grid.hidden = false;
}

function showCoachOverlay(cmd, extras) {
  const opt = extras || {};
  hideLetterPad();
  document.body.classList.add('remote-message');
  document.body.classList.toggle('remote-results', !!opt.results);
  const scene = inferScene(cmd);
  document.body.classList.toggle('instruction-photo-mode', scene === 'idle' || scene === 'stand' || scene === 'face' || scene === 'cover_right' || scene === 'cover_left');
  document.body.classList.toggle('face-photo-mode', scene === 'face');
  document.body.classList.toggle('cover-photo-mode', scene === 'cover_right' || scene === 'cover_left');
  document.body.classList.toggle('countdown-mode', scene === 'countdown');
  const q = resetQueueEl();
  const nameOrQueue = opt.queueText != null ? opt.queueText : (cmd.patient_name || cmd.queue_number || '');
  if (q && nameOrQueue && scene !== 'heard' && scene !== 'countdown') q.textContent = String(nameOrQueue);
  if (scene === 'countdown' && q) {
    q.textContent = String((cmd && (cmd.text_vi || cmd.seconds)) || '');
  }
  if (opt.heard && q) {
    q.textContent = opt.heard;
    q.classList.add('heard-optotype');
    if (opt.heardSizePx) q.style.fontSize = `${opt.heardSizePx}px`;
    if (opt.acuityLabel) q.dataset.acuity = opt.acuityLabel;
  }
  setCoachArt(opt.heard ? '' : scene);
  setCoachCopy(cmd, scene);
  if (opt.results) setResultsGrid(cmd);
  else {
    const grid = $('remoteResults');
    if (grid) { grid.hidden = true; grid.innerHTML = ''; }
  }
  setSkipFab(cmd);
}

function applyRemoteCommand(cmd) {
  if (!cmd || typeof cmd !== 'object') return;
  if (cmd.type === 'station_home') {
    clearWelcomeTimer();
    stopListenProgress();
    stopPromptAudio();
    hideLetterPad();
    setSkipFab(null);
    document.body.classList.remove(
      'remote-message', 'remote-results', 'letter-confirm',
      'instruction-photo-mode', 'face-photo-mode', 'cover-photo-mode', 'countdown-mode'
    );
    document.body.classList.add('exam-mode', 'fs-cal-hidden');
    document.body.classList.remove('fs-cal-visible');
    state.mode = 'row';
    state.rowIndex = 7;
    state.letters = randomLetters(5);
    state.singleLetter = randomLetter();
    const art = $('remoteArt');
    if (art) { art.hidden = true; art.replaceChildren(); art.dataset.scene = ''; }
    const queue = resetQueueEl();
    if (queue) queue.textContent = '';
    const msg = $('remoteMsg');
    if (msg) msg.textContent = '';
    const lead = $('remoteLead');
    if (lead) { lead.textContent = ''; lead.hidden = true; }
    const results = $('remoteResults');
    if (results) { results.hidden = true; results.innerHTML = ''; }
    const actions = $('remoteActions');
    if (actions) { actions.hidden = true; actions.innerHTML = ''; }
    const status = $('acStatus');
    if (status) status.textContent = '';
    render();
    showCoachOverlay({
      type: 'show_message',
      mode: 'idle',
      scene: 'face',
      text_vi: 'Nhìn vào máy nhận diện khuôn mặt.',
      exam_mode: true,
    });
    return;
  }
  if (cmd.type === 'listen_window_start') {
    if (cmd.window_id && cmd.window_id === state.activeWindowId) {
      startListenProgress(cmd.countdown_seconds);
    }
    return;
  }
  if (cmd.type === 'display_config') {
    applyDisplayConfig(cmd);
    return;
  }
  if (cmd.type === 'display_calibration') {
    applyDisplayConfig(cmd);
    document.body.classList.toggle('fs-cal-visible', cmd.visible !== false);
    document.body.classList.toggle('fs-cal-hidden', cmd.visible === false);
    return;
  }
  if (cmd.type !== 'show_single' && cmd.mode !== 'single'
      && cmd.type !== 'letter_confirm' && cmd.mode !== 'letter_confirm'
      && cmd.type !== 'play_audio' && cmd.type !== 'stop_audio') {
    stopListenProgress();
  }
  if (cmd.type !== 'play_audio' && cmd.type !== 'stop_audio') clearWelcomeTimer();
  if (cmd.type !== 'letter_confirm' && cmd.mode !== 'letter_confirm') {
    document.body.classList.remove('letter-confirm');
  }
  const status = $('acStatus');
  if (status) status.textContent = cmd.type || '';

  if (cmd.exam_mode === true) {
    document.body.classList.add('exam-mode');
    document.body.classList.add('fs-cal-hidden');
    document.body.classList.remove('fs-cal-visible');
  }
  // The patient screen never exposes the manual chart/setup page.

  if (cmd.type === 'play_audio') {
    playPromptUrl(cmd.url || '', cmd.text_vi || '');
    return;
  }
  if (cmd.type === 'stop_audio') {
    stopPromptAudio();
    return;
  }

  if (cmd.type === 'letter_pad') {
    if (cmd.show === false) hideLetterPad();
    else showLetterPad(cmd.prompt_vi || '');
    return;
  }

  const actionsEl = $('remoteActions');
  if (actionsEl) {
    actionsEl.hidden = true;
    actionsEl.innerHTML = '';
  }

  if (cmd.type === 'ui_screen') {
    showCoachOverlay(cmd, { queueText: cmd.patient_name || '' });
    if (actionsEl) {
      const buttons = [];
      let registerNameInput = null;
      if (cmd.mode === 'register_prompt') {
        const inputWrap = document.createElement('div');
        inputWrap.className = 'register-name-wrap';
        const input = document.createElement('input');
        input.id = 'registerNameInput';
        input.type = 'text';
        input.placeholder = 'Họ tên bệnh nhân';
        input.maxLength = 80;
        input.autocomplete = 'off';
        inputWrap.appendChild(input);
        actionsEl.appendChild(inputWrap);
        registerNameInput = input;

        buttons.push({ action: 'register_yes', label: 'Đăng ký', primary: true });
        buttons.push({ action: 'register_no', label: 'Không' });
      } else if (cmd.mode === 'service_menu') {
        const services = Array.isArray(cmd.services) ? cmd.services : [{ id: 'vision_test', label: 'Kiểm tra thị lực' }];
        services.forEach((s) => {
          buttons.push({
            action: `service_${s.id || 'vision_test'}`,
            label: s.label || 'Kiểm tra thị lực',
            primary: true,
          });
        });
      } else if (cmd.mode === 'welcome' && cmd.show_continue !== false) {
        const secs = Number(cmd.auto_continue_seconds);
        const start = Number.isFinite(secs) && secs > 0 ? Math.ceil(secs) : 0;
        buttons.push({
          action: 'welcome_continue',
          label: start ? `Tiếp tục (${start})` : 'Tiếp tục',
          primary: true,
        });
      }
      if (buttons.length) {
        actionsEl.hidden = false;
        buttons.forEach((b) => {
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.className = b.primary ? 'btn primary' : 'btn';
          btn.textContent = b.label;
          btn.addEventListener('click', () => {
            clearWelcomeTimer();
            if (cmd.mode === 'register_prompt' && b.action === 'register_yes') {
              const name = (registerNameInput?.value || '').trim();
              sendUiEvent(b.action, { name });
              return;
            }
            sendUiEvent(b.action);
          });
          actionsEl.appendChild(btn);
          if (cmd.mode === 'welcome' && b.action === 'welcome_continue') {
            const secs = Number(cmd.auto_continue_seconds);
            if (Number.isFinite(secs) && secs > 0) {
              let left = Math.ceil(secs);
              const lead = $('remoteLead');
              welcomeTimer = setInterval(() => {
                left -= 1;
                if (left <= 0) {
                  clearWelcomeTimer();
                  sendUiEvent('welcome_continue');
                  return;
                }
                btn.textContent = `Tiếp tục (${left})`;
                if (lead) {
                  lead.textContent = `Bắt đầu sau ${left} giây`;
                  lead.hidden = false;
                }
              }, 1000);
            }
          }
        });
      }
    }
    return;
  }

  if (cmd.type === 'show_message' || cmd.mode === 'queue_stub' || cmd.mode === 'confirm') {
    showCoachOverlay(cmd, { queueText: cmd.queue_number || '' });
    return;
  }

  if (cmd.type === 'results' || cmd.mode === 'results') {
    const name = cmd.patient_name || cmd.patient_id || '';
    showCoachOverlay(cmd, {
      results: true,
      queueText: name ? String(name) : '',
    });
    return;
  }

  if (cmd.type === 'clear') {
    showCoachOverlay({
      type: 'show_message', scene: 'face',
      text_vi: 'Nhìn vào máy nhận diện khuôn mặt.', exam_mode: true,
    });
    return;
  }
  if (cmd.type === 'show_row' || cmd.mode === 'row') {
    document.body.classList.remove('remote-message', 'remote-results');
    state.mode = 'row';
    if (typeof cmd.logmar === 'number') {
      state.rowIndex = rowIndexForLogmar(cmd.logmar);
      els.rowIndex.value = String(state.rowIndex);
    }
    if (Array.isArray(cmd.letters) && cmd.letters.length) {
      state.letters = cmd.letters.map(String);
    }
    render();
    setSkipFab(cmd);
    if (cmd.letter_pad) {
      showLetterPad(cmd.prompt_vi || 'Chạm chữ bệnh nhân đọc được', {
        allowSkip: !!cmd.allow_skip,
        skipLabel: cmd.skip_label || 'Bỏ qua (đúng)',
        skipAction: cmd.skip_action || 'skip_letter',
      });
    } else hideLetterPad();
    return;
  }
  if (cmd.type === 'letter_confirm' || cmd.mode === 'letter_confirm') {
    const heard = String(cmd.heard_letter || '').toUpperCase();
    document.body.classList.add('exam-mode', 'letter-confirm');
    document.body.classList.remove('remote-message', 'remote-results');
    hideLetterPad();
    setCoachArt('');
    const q = resetQueueEl();
    if (q) q.textContent = '';
    const msg = $('remoteMsg');
    if (msg) {
      msg.textContent = cmd.text_vi
        || (heard ? `Hệ thống nghe được chữ ${heard}. Hãy nói đúng hoặc sai.` : '');
    }
    const lead = $('remoteLead');
    if (lead) { lead.textContent = ''; lead.hidden = true; }
    const grid = $('remoteResults');
    if (grid) { grid.hidden = true; grid.innerHTML = ''; }
    if (actionsEl) {
      actionsEl.hidden = false;
      const mk = (action, label, primary) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = primary ? 'btn primary' : 'btn';
        btn.textContent = label;
        btn.addEventListener('click', () => sendUiEvent(action));
        actionsEl.appendChild(btn);
      };
      if (cmd.allow_confirm_yes !== false) mk('confirm_yes', 'Đúng', true);
      mk('confirm_no', 'Sai — đọc lại', false);
      renderSkipButton(actionsEl, cmd);
    }
    startListenProgress(cmd.countdown_seconds);
    return;
  }
  if (cmd.type === 'show_single' || cmd.mode === 'single') {
    document.body.classList.remove('remote-message');
    document.body.classList.remove('remote-results');
    state.mode = 'single';
    state.activeWindowId = cmd.window_id || null;
    if (cmd.letter) state.singleLetter = String(cmd.letter);
    if (typeof cmd.logmar === 'number') {
      state.rowIndex = rowIndexForLogmar(cmd.logmar);
      els.rowIndex.value = String(state.rowIndex);
    }
    render();
    setSkipFab(cmd);
    if (cmd.letter_pad) {
      const prompt = [cmd.prompt_vi, cmd.progress_vi].filter(Boolean).join(' · ')
        || 'Đọc chữ trên màn hình';
      showLetterPad(prompt, {
        allowSkip: !!cmd.allow_skip,
        skipLabel: cmd.skip_label || 'Bỏ qua (đúng)',
        skipAction: cmd.skip_action || 'skip_letter',
      });
    } else hideLetterPad();
    if (!cmd.window_id) startListenProgress(cmd.countdown_seconds);
    return;
  }
}

function connectAc() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const url = `${proto}://${location.host}/ws/display`;
  const status = $('acStatus');
  let ws;
  try { ws = new WebSocket(url); } catch (e) {
    if (status) status.textContent = 'Đang kết nối…';
    setTimeout(connectAc, 2000);
    return;
  }
  acWs = ws;
  ws.onopen = () => {
    if (status) status.textContent = 'Đã kết nối';
    sendDisplayMetrics();
    loadDisplayConfig();
    loadInstructionImages();
  };
  ws.onclose = () => {
    if (status) status.textContent = 'Đang kết nối lại…';
    setTimeout(connectAc, 1500);
  };
  ws.onerror = () => { try { ws.close(); } catch (_) {} };
  ws.onmessage = (ev) => {
    try {
      const cmd = JSON.parse(ev.data);
      applyDisplayState(cmd);
    } catch (err) { console.error('Display command failed', err); }
  };
}

function applyDisplayState(cmd) {
  if (!cmd || typeof cmd !== 'object') return;
  if (cmd.type === 'instruction_images') {
    applyInstructionImages(cmd.images);
    return;
  }
  const revision = Number(cmd._display_revision || 0);
  const bootId = cmd._display_boot_id || null;
  const transient = ['play_audio', 'stop_audio', 'letter_pad', 'display_config',
    'display_calibration', 'input_mode', 'listen_window_start'].includes(cmd.type);
  if (revision && bootId) {
    if (bootId === lastDisplayBootId && revision <= lastDisplayRevision) return;
  } else if (!transient && JSON.stringify(cmd) === lastDisplayFingerprint) {
    return;
  }
  applyRemoteCommand(cmd);
  if (revision && bootId) {
    lastDisplayBootId = bootId;
    lastDisplayRevision = revision;
  }
  if (!transient) lastDisplayFingerprint = JSON.stringify(cmd);
  if (cmd.type === 'show_single' && cmd.window_id) {
    ackStimulusAfterPaint(cmd).catch(err => console.error('Stimulus readiness ACK failed', err));
  }
  if (revision && bootId && (location.hostname === '127.0.0.1' || location.hostname === 'localhost')) {
    ackDisplayAfterPaint(cmd).catch(err => console.error('Display paint ACK failed', err));
  }
}

async function ackDisplayAfterPaint(cmd) {
  const expectedPhoto = coachPhotoCache.get(cmd.scene);
  const image = expectedPhoto || document.querySelector('#remoteArt:not([hidden]) img');
  let imageReady = true;
  if (image && (!image.complete || !image.naturalWidth)) {
    imageReady = await Promise.race([
      image.decode().then(() => true, () => false),
      new Promise(resolve => setTimeout(() => resolve(false), 4000))
    ]);
  } else if (image) {
    imageReady = image.naturalWidth > 0;
  }
  await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  if (lastDisplayBootId !== cmd._display_boot_id || lastDisplayRevision !== cmd._display_revision) return;
  if (!acWs || acWs.readyState !== WebSocket.OPEN) return;
  if (expectedPhoto) imageReady = imageReady && expectedPhoto.isConnected;
  acWs.send(JSON.stringify({
    type: 'display_applied',
    boot_id: cmd._display_boot_id,
    revision: cmd._display_revision,
    scene: cmd.scene || cmd.type,
    image_ready: imageReady
  }));
}

// The server also exposes its latest persistent scene. This heals a kiosk
// whose WebSocket remained open after the server dropped it as a slow client.
// Only the physical Jetson display polls; remote previews use WebSocket alone.
if (location.hostname === '127.0.0.1' || location.hostname === 'localhost') {
  let displayPollInFlight = false;
  setInterval(async () => {
    if (displayPollInFlight) return;
    displayPollInFlight = true;
    try {
      const response = await fetch('/api/display/last', { cache: 'no-store' });
      if (response.ok) applyDisplayState(await response.json());
    } catch (err) {
      console.warn('Display state reconciliation failed', err);
    } finally {
      displayPollInFlight = false;
    }
  }, 2000);
}

function sendDisplayMetrics() {
  if (!acWs || acWs.readyState !== WebSocket.OPEN) return;
  acWs.send(JSON.stringify({
    type: 'display_metrics',
    screen_width: Math.round(window.screen?.width || 0),
    screen_height: Math.round(window.screen?.height || 0),
    viewport_width: Math.round(window.innerWidth || 0),
    viewport_height: Math.round(window.innerHeight || 0),
    device_pixel_ratio: Number(window.devicePixelRatio || 1),
    fullscreen: !!(document.fullscreenElement || document.webkitFullscreenElement),
  }));
}
Promise.all([loadDisplayConfig(), loadInstructionImages()]).finally(connectAc);
connectChartMic();

(function bindAudioUnlock() {
  const gate = $('audioUnlock');
  const btn = $('btnAudioUnlock');
  const chip = $('btnAudioChip');
  const unlock = (ev) => {
    if (ev) ev.preventDefault();
    unlockAudio();
  };
  if (btn) btn.addEventListener('click', unlock);
  if (gate) gate.addEventListener('click', unlock);
  if (chip) chip.addEventListener('click', unlock);
  document.addEventListener('pointerdown', () => {
    if (!state.audioGesture) unlockAudio();
  }, { once: true });
})();

(function bindPreviewChip() {
  const chip = $('previewChip');
  if (!chip) return;
  chip.addEventListener('click', async () => {
    const on = !chip.classList.contains('on');
    chip.classList.toggle('on', on);
    chip.textContent = on ? 'Preview: ON' : 'Preview';
    try {
      await fetch('/api/camera/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: on }),
      });
    } catch (_) { /* ignore */ }
    if (on) window.open('/preview', 'ac-preview');
  });
})();

/* Chart browser mic → /ws/mic (float32le mono @ 48k). Visible in exam-mode. */
const TARGET_MIC_RATE = 48000;

function setMicChip(text, kind) {
  const chip = $('micChip');
  if (!chip) return;
  chip.textContent = text;
  chip.classList.remove('live', 'warn', 'err');
  if (kind) chip.classList.add(kind);
}

function resampleTo48k(input, fromRate) {
  if (!fromRate || fromRate === TARGET_MIC_RATE) return input;
  const destLen = Math.max(1, Math.round(input.length * TARGET_MIC_RATE / fromRate));
  const out = new Float32Array(destLen);
  const ratio = input.length / destLen;
  for (let i = 0; i < destLen; i += 1) {
    const src = i * ratio;
    const i0 = Math.floor(src);
    const i1 = Math.min(input.length - 1, i0 + 1);
    const frac = src - i0;
    out[i] = input[i0] * (1 - frac) + input[i1] * frac;
  }
  return out;
}

function connectChartMic() {
  const chip = $('micChip');
  let micWs = null;
  let stream = null;
  let ctx = null;
  let processor = null;
  let starting = false;

  async function startMic() {
    if (starting || (stream && micWs && micWs.readyState === WebSocket.OPEN)) return;
    starting = true;
    setMicChip('Mic: đang bật…', 'warn');
    try {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      const ws = new WebSocket(`${proto}://${location.host}/ws/mic`);
      ws.binaryType = 'arraybuffer';
      await new Promise((resolve, reject) => {
        ws.onopen = resolve;
        ws.onerror = () => reject(new Error('mic ws'));
      });
      micWs = ws;
      stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      if (ctx.state === 'suspended') await ctx.resume();
      if (!state.audioUnlocked) await unlockAudio();
      const source = ctx.createMediaStreamSource(stream);
      processor = ctx.createScriptProcessor(2048, 1, 1);
      ws.send(JSON.stringify({ type: 'mic_hello', sampleRate: TARGET_MIC_RATE }));
      processor.onaudioprocess = (event) => {
        if (!micWs || micWs.readyState !== WebSocket.OPEN) return;
        const input = event.inputBuffer.getChannelData(0);
        const pcm = resampleTo48k(input, ctx.sampleRate);
        micWs.send(pcm.buffer.slice(pcm.byteOffset, pcm.byteOffset + pcm.byteLength));
      };
      const mute = ctx.createGain();
      mute.gain.value = 0;
      source.connect(processor);
      processor.connect(mute);
      mute.connect(ctx.destination);
      ws.onclose = () => setMicChip('Mic: mất kết nối — chạm để bật', 'err');
      setMicChip('Mic: đang nghe', 'live');
    } catch (err) {
      setMicChip('Mic: chạm để bật', 'err');
    } finally {
      starting = false;
    }
  }

  if (chip) chip.addEventListener('click', startMic);

  fetch('/api/audio/input')
    .then((r) => r.json())
    .then((info) => {
      const label = info.device ? String(info.device) : 'thiết bị';
      if ((info.output || '') !== 'browser') {
        state.audioGesture = true;
        state.audioUnlocked = true;
        setAudioUnlockGate(false);
        setAudioChip('live', `Loa: ${label}`);
      }
      if ((info.input || 'device') === 'browser') startMic();
      else setMicChip(`Mic: ${label}`, 'live');
    })
    .catch(() => setMicChip('Mic: chạm để bật', 'warn'));
}

document.addEventListener('keydown', (e) => {
  if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;
  const pad = $('letterPad');
  if (!pad || pad.hidden) return;
  const ch = String(e.key || '').toUpperCase();
  if (LETTERS.includes(ch)) {
    e.preventDefault();
    sendUiEvent('speak_letter', { letter: ch });
  }
});

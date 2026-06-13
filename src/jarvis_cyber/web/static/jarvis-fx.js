/* ========================================================
   JARVIS FX — Iron Man HUD animations & tab system
   ======================================================== */

// ── Clock ──────────────────────────────────────────────
function updateClock() {
  const el = document.getElementById('hud-time');
  if (!el) return;
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  el.textContent = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}
setInterval(updateClock, 1000);
updateClock();

// ── Tab system ─────────────────────────────────────────
document.querySelectorAll('.nav-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    const target = document.getElementById('tab-' + tab.dataset.tab);
    if (target) target.classList.add('active');
  });
});

// ── JARVIS Orb & Waveform ──────────────────────────────
const JarvisOrb = (() => {
  const canvas  = document.getElementById('jarvis-canvas');
  const orbWrap = document.getElementById('jarvis-orb');
  const label   = document.getElementById('jarvis-state-label');
  if (!canvas) return null;

  const ctx  = canvas.getContext('2d');
  const W    = canvas.width  = 190;
  const H    = canvas.height = 190;
  const CX   = W / 2;
  const CY   = H / 2;
  const BARS = 72;
  const R_IN = 56;   // inner radius of bars
  const R_MAX = 40;  // max bar height

  let state = 'idle';
  let heights = new Float32Array(BARS);

  // Web Audio analyser for real mic data
  let analyser = null;
  let micData  = null;
  let audioCtx = null;
  let micStream = null;

  async function startMic() {
    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      audioCtx  = new (window.AudioContext || window.webkitAudioContext)();
      analyser  = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.75;
      audioCtx.createMediaStreamSource(micStream).connect(analyser);
      micData = new Uint8Array(analyser.frequencyBinCount);
    } catch {
      // Mic permission denied — fall back to simulation
    }
  }

  function stopMic() {
    if (micStream) { micStream.getTracks().forEach(t => t.stop()); micStream = null; }
    if (audioCtx)  { audioCtx.close().catch(() => {}); audioCtx = null; }
    analyser = null; micData = null;
  }

  const STATE_LABELS = {
    idle:      'EN VEILLE',
    listening: 'EN ÉCOUTE',
    thinking:  'TRAITEMENT',
    speaking:  'JARVIS RÉPOND',
  };

  function setState(s) {
    state = s;
    if (orbWrap) orbWrap.dataset.state = s;
    if (label)   label.textContent = STATE_LABELS[s] || 'EN VEILLE';
    if (s === 'listening') startMic();
    else stopMic();
  }

  // ── Draw one frame ──
  function draw() {
    ctx.clearRect(0, 0, W, H);
    const t = performance.now() / 1000;

    for (let i = 0; i < BARS; i++) {
      const angle = (i / BARS) * Math.PI * 2 - Math.PI / 2;
      let   target = 0;

      if (state === 'idle') {
        target = (Math.sin(i * 0.28 + t * 1.6) * 0.5 + 0.5) * 9;
      } else if (state === 'listening') {
        if (analyser && micData) {
          analyser.getByteFrequencyData(micData);
          const di = Math.floor((i / BARS) * micData.length);
          target = (micData[di] / 255) * R_MAX;
        } else {
          target = (Math.sin(i * 0.55 + t * 3.2) * 0.5 + 0.5) * 26;
        }
      } else if (state === 'thinking') {
        target = (Math.sin(t * 6 + i * 0.44) * 0.5 + 0.5) * 22;
      } else if (state === 'speaking') {
        const wave = Math.sin(i * 1.15 + t * 9) * 0.5
                   + Math.sin(i * 2.3  + t * 5) * 0.3
                   + Math.sin(i * 0.7  + t * 3) * 0.2;
        target = (wave * 0.5 + 0.5) * R_MAX;
      }

      heights[i] += (target - heights[i]) * 0.28;
      const h = heights[i];

      const x1 = CX + Math.cos(angle) * R_IN;
      const y1 = CY + Math.sin(angle) * R_IN;
      const x2 = CX + Math.cos(angle) * (R_IN + h);
      const y2 = CY + Math.sin(angle) * (R_IN + h);

      const intensity = 0.3 + (h / R_MAX) * 0.7;
      let color;
      if      (state === 'listening') color = `rgba(0,255,136,${intensity})`;
      else if (state === 'thinking')  color = `rgba(255,170,0,${intensity})`;
      else                            color = `rgba(0,212,255,${intensity})`;

      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.strokeStyle = color;
      ctx.lineWidth   = 2.2;
      ctx.lineCap     = 'round';
      ctx.stroke();
    }

    requestAnimationFrame(draw);
  }

  draw();

  return { setState };
})();

// Make JarvisOrb globally accessible so app.js hooks can call it
window.JarvisOrb = JarvisOrb;

// ── Auto-hook: watch chat log for state changes ─────────
const chatLog = document.getElementById('chat-log');
if (chatLog && JarvisOrb) {
  // Observe new messages → speaking state briefly
  new MutationObserver(mutations => {
    for (const m of mutations) {
      for (const node of m.addedNodes) {
        if (node.classList && node.classList.contains('message') && node.classList.contains('assistant')) {
          JarvisOrb.setState('speaking');
          // Return to idle after text is "read" (estimate ~3s per 100 chars)
          const text = node.textContent || '';
          const delay = Math.min(3000 + text.length * 30, 12000);
          setTimeout(() => JarvisOrb.setState('idle'), delay);
        }
      }
    }
  }).observe(chatLog, { childList: true });
}

// Voice button hooks
const btnRecord     = document.getElementById('voice-record');
const btnStop       = document.getElementById('realtime-disconnect');
const btnRealtime   = document.getElementById('realtime-connect');

if (btnRecord && JarvisOrb) {
  btnRecord.addEventListener('click', () => {
    JarvisOrb.setState('listening');
    // If no answer within 12s, reset
    setTimeout(() => { if (JarvisOrb) JarvisOrb.setState('thinking'); }, 12000);
  });
}
if (btnRealtime && JarvisOrb) {
  btnRealtime.addEventListener('click', () => JarvisOrb.setState('listening'));
}
if (btnStop && JarvisOrb) {
  btnStop.addEventListener('click', () => JarvisOrb.setState('idle'));
}

// Chat form submit → thinking state
const chatForm = document.getElementById('chat-form');
if (chatForm && JarvisOrb) {
  chatForm.addEventListener('submit', () => JarvisOrb.setState('thinking'));
}

// ── Glitch text effect on brand name ───────────────────
const brand = document.querySelector('.hud-brand-name');
if (brand) {
  const original = brand.textContent;
  const glitchChars = '!<>-_\\/[]{}—=+*^?#░▒▓';

  function glitch() {
    let iteration = 0;
    const interval = setInterval(() => {
      brand.textContent = original.split('').map((char, i) => {
        if (i < iteration) return original[i];
        return glitchChars[Math.floor(Math.random() * glitchChars.length)];
      }).join('');
      if (iteration >= original.length) {
        brand.textContent = original;
        clearInterval(interval);
      }
      iteration += 1 / 2;
    }, 30);
  }

  // Run glitch on load
  setTimeout(glitch, 800);
  // And on hover
  brand.closest('.hud-brand').addEventListener('mouseenter', glitch);
}

// ── Boot sequence message in chat ──────────────────────
window.addEventListener('DOMContentLoaded', () => {
  setTimeout(() => {
    const log = document.getElementById('chat-log');
    if (!log) return;
    // Ensure first message has nice animation by triggering re-render
    log.querySelectorAll('.message').forEach((m, i) => {
      m.style.animationDelay = `${i * 0.1}s`;
    });
  }, 200);
});

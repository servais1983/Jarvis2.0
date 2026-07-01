/* ========================================================
   JARVIS FX — Neural Command Center
   Orb à particules · réseau d'agents · fenêtres HUD
   ======================================================== */

(() => {
'use strict';

const REDUCED_MOTION = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const DPR = Math.min(window.devicePixelRatio || 1, 2);

/* ── Horloge, date, accueil ─────────────────────────────── */

const DAYS   = ['DIM.', 'LUN.', 'MAR.', 'MER.', 'JEU.', 'VEN.', 'SAM.'];
const MONTHS = ['JANV.', 'FÉVR.', 'MARS', 'AVR.', 'MAI', 'JUIN',
                'JUIL.', 'AOÛT', 'SEPT.', 'OCT.', 'NOV.', 'DÉC.'];

function updateClock() {
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  const timeEl = document.getElementById('hud-time');
  const dateEl = document.getElementById('hud-date');
  if (timeEl) timeEl.textContent = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
  if (dateEl) dateEl.textContent = `${DAYS[now.getDay()]} ${now.getDate()} ${MONTHS[now.getMonth()]}`;
}
setInterval(updateClock, 5000);
updateClock();

function greetingWord() {
  const h = new Date().getHours();
  if (h < 6)  return 'Bonne nuit';
  if (h < 12) return 'Bonjour';
  if (h < 18) return 'Bon après-midi';
  return 'Bonsoir';
}

async function updateGreeting() {
  const el = document.getElementById('hud-greeting');
  if (!el) return;
  let name = '';
  try {
    const res = await fetch('/profile/me');
    if (res.ok) {
      const profile = await res.json();
      if (profile && profile.display_name) name = profile.display_name;
    }
  } catch { /* mode hors-ligne ou auth requise : accueil générique */ }
  el.textContent = name ? `${greetingWord()}, ${name}.` : `${greetingWord()}.`;
}
updateGreeting();

/* « Ce jour-là » — éphéméride cyber/tech locale */
const FACTS = [
  '1988 — Le ver Morris paralyse près de 10 % d’Internet.',
  '1971 — Creeper, premier programme auto-répliquant, circule sur ARPANET.',
  '1983 — Le mot « virus informatique » est utilisé pour la première fois.',
  '1994 — Premier chiffrement SSL déployé par Netscape.',
  '2013 — Les révélations Snowden changent la cybersécurité mondiale.',
  '1969 — Premier message envoyé sur ARPANET : « LO ».',
  '1991 — Phil Zimmermann publie PGP, le chiffrement pour tous.',
  '2010 — Stuxnet, premier malware ciblant des systèmes industriels.',
  '1995 — SATAN, premier scanner de vulnérabilités public.',
  '2004 — Lancement du premier Patch Tuesday de Microsoft.',
  '1986 — Brain, premier virus PC, se propage par disquette.',
  '2017 — WannaCry frappe 300 000 machines en 72 heures.',
];
(() => {
  const el = document.getElementById('hud-fact');
  if (!el) return;
  const start = new Date(new Date().getFullYear(), 0, 0);
  const dayOfYear = Math.floor((Date.now() - start.getTime()) / 86400000);
  el.textContent = `CE JOUR-LÀ · ${FACTS[dayOfYear % FACTS.length]}`;
})();

/* ── Fond neuronal plein écran ──────────────────────────── */

(() => {
  const canvas = document.getElementById('neural-bg');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let W = 0, H = 0, points = [];

  function resize() {
    W = canvas.width  = Math.floor(window.innerWidth  * DPR);
    H = canvas.height = Math.floor(window.innerHeight * DPR);
    const count = Math.min(110, Math.floor((window.innerWidth * window.innerHeight) / 16000));
    points = Array.from({ length: count }, () => ({
      x: Math.random() * W,
      y: Math.random() * H,
      vx: (Math.random() - 0.5) * 0.12 * DPR,
      vy: (Math.random() - 0.5) * 0.12 * DPR,
      r: (Math.random() * 1.3 + 0.4) * DPR,
    }));
  }
  window.addEventListener('resize', resize);
  resize();

  const LINK_DIST = 130 * DPR;
  let last = 0;
  function frame(ts) {
    requestAnimationFrame(frame);
    if (ts - last < 50) return;               // ~20 FPS suffisent pour le fond
    last = ts;
    ctx.clearRect(0, 0, W, H);

    for (const p of points) {
      p.x += p.vx; p.y += p.vy;
      if (p.x < 0 || p.x > W) p.vx *= -1;
      if (p.y < 0 || p.y > H) p.vy *= -1;
    }
    ctx.lineWidth = 1;
    for (let i = 0; i < points.length; i++) {
      for (let j = i + 1; j < points.length; j++) {
        const a = points[i], b = points[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const d = Math.hypot(dx, dy);
        if (d < LINK_DIST) {
          ctx.strokeStyle = `rgba(53,224,210,${(1 - d / LINK_DIST) * 0.07})`;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }
    for (const p of points) {
      ctx.fillStyle = 'rgba(53,224,210,0.28)';
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  if (!REDUCED_MOTION) requestAnimationFrame(frame);
})();

/* ── Orb central — sphère de particules + anneau doré ───── */

const JarvisOrb = (() => {
  const canvas  = document.getElementById('jarvis-canvas');
  const orbWrap = document.getElementById('jarvis-orb');
  const label   = document.getElementById('jarvis-state-label');
  if (!canvas) return null;

  const ctx = canvas.getContext('2d');
  let SIZE = 0, CX = 0, CY = 0;

  function resize() {
    const rect = canvas.getBoundingClientRect();
    SIZE = Math.floor(Math.min(rect.width, rect.height) * DPR);
    canvas.width = canvas.height = SIZE;
    CX = CY = SIZE / 2;
  }
  window.addEventListener('resize', resize);
  resize();

  // Sphère : points répartis en spirale de Fibonacci
  const N_PARTICLES = 620;
  const particles = [];
  const GOLDEN = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < N_PARTICLES; i++) {
    const y = 1 - (i / (N_PARTICLES - 1)) * 2;
    const rXZ = Math.sqrt(1 - y * y);
    const theta = GOLDEN * i;
    particles.push({
      x: Math.cos(theta) * rXZ,
      y,
      z: Math.sin(theta) * rXZ,
      j: Math.random() * Math.PI * 2,     // phase de scintillement
    });
  }

  let state = 'idle';

  // Analyseur micro pour l'état « écoute »
  let analyser = null, micData = null, audioCtx = null, micStream = null, micStarting = false;

  async function startMic() {
    if (micStarting || micStream) return;
    micStarting = true;
    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      audioCtx  = new (window.AudioContext || window.webkitAudioContext)();
      analyser  = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.75;
      audioCtx.createMediaStreamSource(micStream).connect(analyser);
      micData = new Uint8Array(analyser.frequencyBinCount);
    } catch {
      /* micro refusé : animation simulée */
    } finally {
      micStarting = false;
    }
  }

  function stopMic() {
    if (micStream) { micStream.getTracks().forEach(t => t.stop()); micStream = null; }
    if (audioCtx)  { audioCtx.close().catch(() => {}); audioCtx = null; }
    analyser = null; micData = null; micStarting = false;
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
    if (label) {
      label.textContent = STATE_LABELS[s] || 'EN VEILLE';
      label.dataset.state = s;
    }
    if (s === 'listening') startMic();
    else stopMic();
  }

  function micLevel() {
    if (!analyser || !micData) return 0;
    analyser.getByteFrequencyData(micData);
    let sum = 0;
    for (let i = 0; i < micData.length; i++) sum += micData[i];
    return sum / (micData.length * 255);
  }

  const STATE_TINTS = {
    idle:      { r: 64,  g: 220, b: 210 },
    listening: { r: 62,  g: 245, b: 165 },
    thinking:  { r: 255, g: 190, b: 90  },
    speaking:  { r: 120, g: 235, b: 255 },
  };

  let rotY = 0, rotX = 0.35;
  let last = 0;

  function draw(ts = 0) {
    requestAnimationFrame(draw);
    if (ts - last < 33) return;               // ~30 FPS
    last = ts;
    if (!SIZE) return;
    ctx.clearRect(0, 0, SIZE, SIZE);

    const t = performance.now() / 1000;
    const half = SIZE / 2;
    const sphereR = half * 0.60;
    const ringR   = half * 0.74;
    const level   = state === 'listening' ? micLevel() : 0;

    // Vitesse de rotation selon l'état
    let speed = 0.0035;
    if (state === 'thinking')  speed = 0.012;
    if (state === 'listening') speed = 0.006 + level * 0.02;
    if (state === 'speaking')  speed = 0.009;
    if (!REDUCED_MOTION) { rotY += speed; rotX = 0.35 + Math.sin(t * 0.3) * 0.08; }

    // Halo de fond
    const halo = ctx.createRadialGradient(CX, CY, sphereR * 0.2, CX, CY, half);
    halo.addColorStop(0, 'rgba(20,90,110,0.5)');
    halo.addColorStop(0.55, 'rgba(10,50,70,0.22)');
    halo.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = halo;
    ctx.fillRect(0, 0, SIZE, SIZE);

    // Sphère de particules
    const tint = STATE_TINTS[state] || STATE_TINTS.idle;
    const cosY = Math.cos(rotY), sinY = Math.sin(rotY);
    const cosX = Math.cos(rotX), sinX = Math.sin(rotX);
    const pulse = state === 'thinking' ? 1 + Math.sin(t * 6) * 0.04
                : state === 'speaking' ? 1 + Math.sin(t * 12) * 0.03
                : 1 + level * 0.15;

    for (const p of particles) {
      // rotation Y puis X
      const x1 = p.x * cosY + p.z * sinY;
      const z1 = -p.x * sinY + p.z * cosY;
      const y1 = p.y * cosX - z1 * sinX;
      const z2 = p.y * sinX + z1 * cosX;

      const depth = (z2 + 1) / 2;                       // 0 arrière → 1 avant
      const px = CX + x1 * sphereR * pulse;
      const py = CY + y1 * sphereR * pulse;
      const twinkle = 0.65 + Math.sin(t * 2.2 + p.j) * 0.35;
      const alpha = (0.12 + depth * 0.75) * twinkle;
      const size = (0.6 + depth * 1.5) * DPR;

      ctx.fillStyle = `rgba(${tint.r},${tint.g},${tint.b},${alpha.toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(px, py, size, 0, Math.PI * 2);
      ctx.fill();
    }

    // Cœur lumineux
    const core = ctx.createRadialGradient(CX, CY, 0, CX, CY, sphereR * 0.55);
    core.addColorStop(0, `rgba(${tint.r},${tint.g},${tint.b},0.16)`);
    core.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = core;
    ctx.fillRect(0, 0, SIZE, SIZE);

    // Anneau doré principal
    const ringPulse = 1 + Math.sin(t * 1.4) * 0.012 + level * 0.05;
    const rr = ringR * ringPulse;
    const ringGrad = ctx.createLinearGradient(CX - rr, CY - rr, CX + rr, CY + rr);
    ringGrad.addColorStop(0,   'rgba(255,150,40,0.95)');
    ringGrad.addColorStop(0.5, 'rgba(255,205,110,0.95)');
    ringGrad.addColorStop(1,   'rgba(230,120,30,0.95)');

    ctx.save();
    ctx.shadowColor = 'rgba(255,170,60,0.9)';
    ctx.shadowBlur  = 26 * DPR;
    ctx.strokeStyle = ringGrad;
    ctx.lineWidth   = 4.5 * DPR;
    ctx.beginPath();
    ctx.arc(CX, CY, rr, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();

    // Halo interne de l'anneau
    ctx.strokeStyle = 'rgba(255,200,120,0.25)';
    ctx.lineWidth = 10 * DPR;
    ctx.beginPath();
    ctx.arc(CX, CY, rr, 0, Math.PI * 2);
    ctx.stroke();

    // Arcs satellites tournants
    ctx.save();
    ctx.translate(CX, CY);
    ctx.rotate(t * 0.25);
    ctx.strokeStyle = 'rgba(255,182,61,0.35)';
    ctx.lineWidth = 1.4 * DPR;
    ctx.beginPath();
    ctx.arc(0, 0, rr + 9 * DPR, 0.2, 1.2);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(0, 0, rr + 9 * DPR, Math.PI + 0.5, Math.PI + 1.8);
    ctx.stroke();
    ctx.restore();

    // Cercle externe discret
    ctx.strokeStyle = 'rgba(53,224,210,0.10)';
    ctx.lineWidth = 1 * DPR;
    ctx.beginPath();
    ctx.arc(CX, CY, half * 0.92, 0, Math.PI * 2);
    ctx.stroke();

    // Étincelles orbitales sur l'anneau
    for (let i = 0; i < 3; i++) {
      const a = t * (0.4 + i * 0.13) + i * 2.1;
      const sx = CX + Math.cos(a) * rr;
      const sy = CY + Math.sin(a) * rr;
      ctx.fillStyle = 'rgba(255,230,170,0.9)';
      ctx.beginPath();
      ctx.arc(sx, sy, 1.8 * DPR, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  requestAnimationFrame(draw);

  return { setState, micLevel: () => (state === 'listening' ? micLevel() : 0), getState: () => state };
})();

window.JarvisOrb = JarvisOrb;

/* ── Waveform du dock ───────────────────────────────────── */

(() => {
  const canvas = document.getElementById('wave-canvas');
  if (!canvas || !JarvisOrb) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  const BARS = 48;
  const heights = new Float32Array(BARS);

  let last = 0;
  function draw(ts = 0) {
    requestAnimationFrame(draw);
    if (ts - last < 33) return;
    last = ts;
    ctx.clearRect(0, 0, W, H);

    const t = performance.now() / 1000;
    const state = JarvisOrb.getState();
    const level = JarvisOrb.micLevel();

    for (let i = 0; i < BARS; i++) {
      let target = 1.5;
      const centered = 1 - Math.abs(i - BARS / 2) / (BARS / 2);   // plus haut au centre
      if (state === 'idle') {
        target = (Math.sin(i * 0.5 + t * 2) * 0.5 + 0.5) * 4 * (0.4 + centered);
      } else if (state === 'listening') {
        const sim = (Math.sin(i * 0.8 + t * 7) * 0.5 + 0.5);
        target = (level > 0 ? level * 1.6 : sim * 0.6) * H * 0.42 * (0.35 + centered);
      } else if (state === 'thinking') {
        target = (Math.sin(t * 7 + i * 0.6) * 0.5 + 0.5) * H * 0.3 * (0.4 + centered);
      } else if (state === 'speaking') {
        const wave = Math.sin(i * 0.9 + t * 11) * 0.5 + Math.sin(i * 1.7 + t * 6) * 0.5;
        target = (wave * 0.5 + 0.5) * H * 0.42 * (0.35 + centered);
      }
      heights[i] += (target - heights[i]) * 0.3;
    }

    const barW = W / BARS;
    const color = state === 'listening' ? '82,245,165'
                : state === 'speaking'  ? '120,235,255'
                : '255,182,61';
    for (let i = 0; i < BARS; i++) {
      const h = Math.max(1, heights[i]);
      const x = i * barW + barW * 0.25;
      ctx.fillStyle = `rgba(${color},${0.35 + (h / (H * 0.45)) * 0.6})`;
      ctx.fillRect(x, H / 2 - h / 2, barW * 0.5, h);
    }
  }
  requestAnimationFrame(draw);
})();

/* ── Réseau d'agents autour de l'orb ────────────────────── */

/* [id de fenêtre, libellé, fx, fy, teinte] — positions en fraction de la scène */
const AGENTS = [
  ['win-rapport',       'Rédacteur',     0.395, 0.130, 'teal'],
  ['win-connecteurs',   'Connecteurs',   0.640, 0.145, 'teal'],
  ['win-routines',      'Routines',      0.800, 0.120, 'dim'],
  ['win-cve',           'Chercheur CVE', 0.150, 0.215, 'teal'],
  ['win-securite',      'Sécurité',      0.845, 0.270, 'teal'],
  ['win-triage',        'Analyste',      0.185, 0.395, 'teal'],
  ['win-memoire',       'Mémoire',       0.690, 0.385, 'teal'],
  ['win-veille',        'Vigie CVE',     0.140, 0.560, 'gold'],
  ['win-inbox',         'Inbox',         0.860, 0.520, 'dim'],
  ['win-methodes',      'Playbooks',     0.700, 0.640, 'teal'],
  ['win-investigation', 'Investigateur', 0.250, 0.680, 'gold'],
  ['win-approbations',  'Approbations',  0.575, 0.760, 'gold'],
  ['win-profil',        'Profil',        0.800, 0.690, 'teal'],
  ['win-dossiers',      'Dossiers',      0.115, 0.735, 'teal'],
];

const stage    = document.getElementById('command-stage');
const nodesEl  = document.getElementById('agent-nodes');
const linksSvg = document.getElementById('agent-links');

function layoutAgents() {
  if (!stage || !nodesEl || !linksSvg) return;
  const rect = stage.getBoundingClientRect();
  if (rect.width < 821) return;                       // fallback mobile via CSS

  const cx = rect.width / 2;
  const cy = rect.height * 0.46;
  const orbR = Math.min(rect.height * 0.46, 420) / 2;

  nodesEl.innerHTML = '';
  linksSvg.setAttribute('viewBox', `0 0 ${rect.width} ${rect.height}`);
  let paths = '';

  for (const [winId, name, fx, fy, tone] of AGENTS) {
    const x = fx * rect.width;
    const y = fy * rect.height;
    const side = x < cx ? 'left' : 'right';

    const node = document.createElement('div');
    node.className = 'agent-node';
    node.dataset.side = side;
    node.dataset.tone = tone;
    node.style.left = `${x}px`;
    node.style.top  = `${y}px`;
    node.innerHTML = `<span class="agent-dot"></span><span class="agent-label">${name}</span>`;
    node.addEventListener('click', () => openWindow(winId));
    nodesEl.appendChild(node);

    // Ligne en coude : segment horizontal vers le centre, puis diagonale
    // qui s'arrête à la lisière de l'orb.
    const dirX = side === 'left' ? 1 : -1;
    const elbowX = x + dirX * Math.max(30, Math.abs(cx - x) * 0.25);
    const dx = cx - elbowX, dy = cy - y;
    const dist = Math.hypot(dx, dy);
    const stop = Math.max(0, dist - orbR * 1.06);
    const ex = elbowX + (dx / dist) * stop;
    const ey = y + (dy / dist) * stop;
    const tint = tone === 'gold' ? '255,182,61' : '53,224,210';

    paths += `<path d="M ${x} ${y} L ${elbowX} ${y} L ${ex} ${ey}"
      fill="none" stroke="rgba(${tint},0.28)" stroke-width="1"/>`;
    paths += `<circle cx="${ex}" cy="${ey}" r="1.6" fill="rgba(${tint},0.5)"/>`;
  }
  linksSvg.innerHTML = paths;
}
window.addEventListener('resize', layoutAgents);
layoutAgents();

/* Grille mobile (les nœuds sont masqués sur petit écran) */
(() => {
  const grid = document.getElementById('mobile-agent-grid');
  if (!grid) return;
  for (const [winId, name] of AGENTS) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = name;
    btn.addEventListener('click', () => openWindow(winId));
    grid.appendChild(btn);
  }
})();

/* ── Fenêtres HUD ───────────────────────────────────────── */

const backdrop = document.getElementById('overlay-backdrop');
let currentWindow = null;

function openWindow(id) {
  closeWindow();
  closeModesMenu();
  const win = document.getElementById(id);
  if (!win) return;
  win.classList.remove('hidden');
  if (backdrop) backdrop.classList.remove('hidden');
  currentWindow = win;
}

function closeWindow() {
  if (currentWindow) currentWindow.classList.add('hidden');
  currentWindow = null;
  if (backdrop) backdrop.classList.add('hidden');
}

document.querySelectorAll('.hud-window [data-close]').forEach(btn => {
  btn.addEventListener('click', closeWindow);
});
if (backdrop) backdrop.addEventListener('click', closeWindow);
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { closeWindow(); closeModesMenu(); }
});

window.JarvisWindows = { open: openWindow, close: closeWindow };

/* ── Menu MODES ─────────────────────────────────────────── */

const modesMenu = document.getElementById('modes-menu');

function closeModesMenu() {
  if (modesMenu) modesMenu.classList.add('hidden');
}

(() => {
  const btn  = document.getElementById('modes-button');
  const grid = document.getElementById('modes-menu-grid');
  if (!btn || !modesMenu || !grid) return;

  const entries = [['win-chat', 'Conversation'], ...AGENTS.map(([id, name]) => [id, name])];
  for (const [winId, name] of entries) {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = name;
    b.addEventListener('click', () => openWindow(winId));
    grid.appendChild(b);
  }
  btn.addEventListener('click', () => modesMenu.classList.toggle('hidden'));
  modesMenu.addEventListener('click', e => {
    if (e.target === modesMenu) closeModesMenu();
  });
})();

/* ── Dock : chat / voix / nouvelle session ──────────────── */

const dockChat  = document.getElementById('dock-chat');
const dockVoice = document.getElementById('dock-voice');
const newChat   = document.getElementById('new-chat-button');

if (dockChat) dockChat.addEventListener('click', () => openWindow('win-chat'));

if (dockVoice) {
  dockVoice.addEventListener('click', () => {
    const connect    = document.getElementById('realtime-connect');
    const disconnect = document.getElementById('realtime-disconnect');
    const active = dockVoice.classList.contains('active');
    if (active) {
      if (disconnect) disconnect.click();
      dockVoice.classList.remove('active');
    } else {
      if (connect) connect.click();
      dockVoice.classList.add('active');
    }
  });
  // Resynchronise la pastille si le mode vocal est coupé depuis la fenêtre chat
  const disconnect = document.getElementById('realtime-disconnect');
  if (disconnect) disconnect.addEventListener('click', () => dockVoice.classList.remove('active'));
}

if (newChat) {
  newChat.addEventListener('click', () => {
    const log = document.getElementById('chat-log');
    const session = document.getElementById('chat-session');
    if (session) session.value = `session-${Date.now().toString(36)}`;
    if (log) {
      log.innerHTML = `<div class="message assistant"><span>Jarvis</span>
        <p>Nouvelle session ouverte. Dis-moi sur quoi tu veux travailler.</p></div>`;
    }
    openWindow('win-chat');
  });
}

/* ── Hooks d'état : chat & voix ─────────────────────────── */

const chatLog = document.getElementById('chat-log');
if (chatLog && JarvisOrb) {
  new MutationObserver(mutations => {
    for (const m of mutations) {
      for (const node of m.addedNodes) {
        if (node.classList && node.classList.contains('message') && node.classList.contains('assistant')) {
          JarvisOrb.setState('speaking');
          const text = node.textContent || '';
          const delay = Math.min(3000 + text.length * 30, 12000);
          setTimeout(() => JarvisOrb.setState('idle'), delay);
        }
      }
    }
  }).observe(chatLog, { childList: true });
}

const btnRecord   = document.getElementById('voice-record');
const btnStop     = document.getElementById('realtime-disconnect');
const btnRealtime = document.getElementById('realtime-connect');

if (btnRecord && JarvisOrb) {
  btnRecord.addEventListener('click', () => {
    JarvisOrb.setState('listening');
    setTimeout(() => { if (JarvisOrb.getState() === 'listening') JarvisOrb.setState('thinking'); }, 12000);
  });
}
if (btnRealtime && JarvisOrb) btnRealtime.addEventListener('click', () => JarvisOrb.setState('listening'));
if (btnStop && JarvisOrb)     btnStop.addEventListener('click', () => JarvisOrb.setState('idle'));

const chatForm = document.getElementById('chat-form');
if (chatForm && JarvisOrb) chatForm.addEventListener('submit', () => JarvisOrb.setState('thinking'));

/* ── Effet glitch sur la marque ─────────────────────────── */

const brand = document.querySelector('.hud-brand-name');
if (brand && !REDUCED_MOTION) {
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
  setTimeout(glitch, 800);
  brand.closest('.hud-brand').addEventListener('mouseenter', glitch);
}

})();

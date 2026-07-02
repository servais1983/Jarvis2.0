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

let userName = 'Steve';

async function updateGreeting() {
  const el = document.getElementById('hud-greeting');
  try {
    const res = await fetch('/profile/me');
    if (res.ok) {
      const profile = await res.json();
      if (profile && profile.display_name) userName = profile.display_name;
    }
  } catch { /* mode hors-ligne ou auth requise : prénom par défaut */ }
  if (el) el.textContent = `${greetingWord()}, ${userName}.`;

  // Personnalise aussi le premier message du chat s'il est encore d'origine
  const first = document.querySelector('#chat-log .message.assistant p');
  if (first && first.textContent.startsWith('Je suis en ligne')) {
    first.textContent = `${greetingWord()}, ${userName}. Je suis en ligne. Dis-moi sur quoi tu veux travailler.`;
  }

  // Accueil affiché sous l'orb (la synthèse vocale attend un geste utilisateur)
  JarvisVoice.showCaption(`${greetingWord()}, ${userName}. Je suis en ligne — parle-moi ou écris sous l'orb.`);
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
          ctx.strokeStyle = `rgba(90,169,255,${(1 - d / LINK_DIST) * 0.07})`;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }
    for (const p of points) {
      ctx.fillStyle = 'rgba(90,169,255,0.28)';
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
    idle:      { r: 96,  g: 172, b: 255 },
    listening: { r: 62,  g: 245, b: 165 },
    thinking:  { r: 255, g: 190, b: 90  },
    speaking:  { r: 165, g: 215, b: 255 },
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
    halo.addColorStop(0, 'rgba(15,45,90,0.5)');
    halo.addColorStop(0.55, 'rgba(8,25,55,0.22)');
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
    ctx.shadowColor = 'rgba(240,180,41,0.9)';
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
    ctx.strokeStyle = 'rgba(240,180,41,0.35)';
    ctx.lineWidth = 1.4 * DPR;
    ctx.beginPath();
    ctx.arc(0, 0, rr + 9 * DPR, 0.2, 1.2);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(0, 0, rr + 9 * DPR, Math.PI + 0.5, Math.PI + 1.8);
    ctx.stroke();
    ctx.restore();

    // Cercle externe discret
    ctx.strokeStyle = 'rgba(90,169,255,0.10)';
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
                : state === 'speaking'  ? '150,210,255'
                : '240,180,41';
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
  ['win-mcp',           'Outils MCP',    0.880, 0.800, 'gold'],
];

const stage    = document.getElementById('command-stage');
const nodesEl  = document.getElementById('agent-nodes');
const linksSvg = document.getElementById('agent-links');

/* ── Télémétrie live : compteurs sur les nœuds ──────────── */

function fxAuthHeaders() {
  const token = sessionStorage.getItem('jarvis_auth_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function fetchJson(path) {
  const res = await fetch(path, { headers: fxAuthHeaders() });
  if (!res.ok) throw new Error(String(res.status));
  return res.json();
}

const BADGE_SOURCES = {
  'win-inbox':        async () => (await fetchJson('/inbox')).length,
  'win-approbations': async () => (await fetchJson('/approvals?status=pending')).length,
  'win-dossiers':     async () => (await fetchJson('/investigation-cases')).filter(c => c.status === 'open').length,
  'win-veille':       async () => (await fetchJson('/watchlists')).length,
  'win-memoire':      async () => (await fetchJson('/knowledge/documents')).length,
  'win-methodes':     async () => (await fetchJson('/playbooks')).length,
  'win-connecteurs':  async () => (await fetchJson('/connectors/status')).filter(c => c.configured).length,
  'win-mcp':          async () => (await fetchJson('/mcp/tools')).length,
};
const badgeCounts = {};

function applyBadges() {
  document.querySelectorAll('[data-badge-for]').forEach(el => {
    const count = badgeCounts[el.dataset.badgeFor];
    if (count > 0) {
      el.textContent = count > 99 ? '99+' : String(count);
      el.classList.remove('hidden');
    } else {
      el.classList.add('hidden');
    }
  });
}

async function refreshBadges() {
  await Promise.all(Object.entries(BADGE_SOURCES).map(async ([winId, fn]) => {
    try { badgeCounts[winId] = await fn(); } catch { /* endpoint indisponible */ }
  }));
  applyBadges();
}
setInterval(refreshBadges, 60000);
refreshBadges();

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
    node.innerHTML = `<span class="agent-dot"></span><span class="agent-label">${name}</span>`
      + `<span class="agent-badge hidden" data-badge-for="${winId}"></span>`;
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
    const tint = tone === 'gold' ? '240,180,41' : '90,169,255';

    paths += `<path d="M ${x} ${y} L ${elbowX} ${y} L ${ex} ${ey}"
      fill="none" stroke="rgba(${tint},0.28)" stroke-width="1"/>`;
    paths += `<circle cx="${ex}" cy="${ey}" r="1.6" fill="rgba(${tint},0.5)"/>`;
  }
  linksSvg.innerHTML = paths;
  applyBadges();
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
    btn.innerHTML = `${name} <span class="agent-badge hidden" data-badge-for="${winId}"></span>`;
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
  if (id === 'win-mcp') mcpRefresh();
}

function closeWindow() {
  if (currentWindow) currentWindow.classList.add('hidden');
  currentWindow = null;
  if (backdrop) backdrop.classList.add('hidden');
  refreshBadges();          // les actions dans la fenêtre ont pu changer les compteurs
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

  const entries = [['win-chat', 'Console'], ...AGENTS.map(([id, name]) => [id, name])];
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

/* ══════════════════════════════════════════════════════════
   L'ORB PARLE — voix, oreilles et cerveau de Jarvis
   ══════════════════════════════════════════════════════════ */

/* ── Voix : synthèse vocale + sous-titres ───────────────── */

const JarvisVoice = (() => {
  const caption = document.getElementById('jarvis-caption');
  let typeTimer = null;
  let frVoice = null;

  function pickVoice() {
    const voices = speechSynthesis.getVoices();
    frVoice = voices.find(v => v.lang && v.lang.toLowerCase().startsWith('fr')) || null;
  }
  if (window.speechSynthesis) {
    pickVoice();
    speechSynthesis.onvoiceschanged = pickVoice;
  }

  function showCaption(text) {
    if (!caption) return;
    clearInterval(typeTimer);
    let i = 0;
    caption.textContent = '';
    typeTimer = setInterval(() => {
      i += 2;
      caption.textContent = text.slice(0, i);
      if (i >= text.length) clearInterval(typeTimer);
    }, 22);
  }

  function cleanForSpeech(text) {
    return String(text).replace(/[*_#`>|•]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 600);
  }

  function resumeAfterSpeech() {
    if (JarvisOrb) JarvisOrb.setState(JarvisEars.active() ? 'listening' : 'idle');
  }

  function speak(text) {
    const display = String(text).trim();
    showCaption(display.length > 420 ? display.slice(0, 420) + '…' : display);
    const spoken = cleanForSpeech(display);
    if (!window.speechSynthesis || !spoken) {
      // Pas de synthèse disponible : on anime l'orb le temps de lecture
      if (JarvisOrb) {
        JarvisOrb.setState('speaking');
        setTimeout(resumeAfterSpeech, Math.min(2000 + spoken.length * 40, 9000));
      }
      return;
    }
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(spoken);
    u.lang = 'fr-FR';
    if (frVoice) u.voice = frVoice;
    u.rate = 1.04;
    let started = false;
    u.onstart = () => { started = true; if (JarvisOrb) JarvisOrb.setState('speaking'); };
    u.onend = resumeAfterSpeech;
    u.onerror = resumeAfterSpeech;
    speechSynthesis.speak(u);
    // Certains environnements exposent l'API sans voix : ne pas rester bloqué
    setTimeout(() => { if (!started) resumeAfterSpeech(); }, 3000);
  }

  function stop() {
    if (window.speechSynthesis) speechSynthesis.cancel();
    clearInterval(typeTimer);
  }

  return { speak, stop, showCaption };
})();

/* ── Transcription : tout passe aussi dans la console ───── */

function escapeHtmlFx(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;');
}

function logMessage(role, content) {
  const log = document.getElementById('chat-log');
  if (!log) return;
  const wrapper = document.createElement('div');
  wrapper.className = `message ${role}`;
  wrapper.dataset.orb = '1';
  wrapper.innerHTML = `<span>${role === 'assistant' ? 'Jarvis' : 'Toi'}</span><p>${escapeHtmlFx(content)}</p>`;
  log.appendChild(wrapper);
  log.scrollTop = log.scrollHeight;
}

/* ── Cerveau : intentions et actions réelles ────────────── */

const COMMAND_TARGETS = [
  [/playbook|m[ée]thode|profil de t[âa]che/, 'win-methodes',      'Playbooks'],
  [/dossier|file soc|cas\b/,                 'win-dossiers',      'Dossiers'],
  [/inbox|livrable/,                         'win-inbox',         'Inbox'],
  [/m[ée]moire|document|connaissance/,       'win-memoire',       'Mémoire'],
  [/triage|analyste|alerte/,                 'win-triage',        'Triage'],
  [/cve|vuln[ée]rabilit/,                    'win-cve',           'Analyse CVE'],
  [/investigation|enqu[êe]te/,               'win-investigation', 'Investigation'],
  [/rapport|incident/,                       'win-rapport',       'Rapport'],
  [/veille|vigie|watchlist/,                 'win-veille',        'Veille CVE'],
  [/routine|automatisation/,                 'win-routines',      'Routines'],
  [/approbation/,                            'win-approbations',  'Approbations'],
  [/connecteur/,                             'win-connecteurs',   'Connecteurs'],
  [/profil\b/,                               'win-profil',        'Profil'],
  [/s[ée]curit[ée]|mfa|connexion/,           'win-securite',      'Sécurité'],
  [/console|transcription|historique/,       'win-chat',          'Console'],
  [/outils?( mcp)?|mcp/,                     'win-mcp',           'Outils MCP'],
];
const OPEN_VERB = /^\s*(ouvre|affiche|montre|va (dans|sur))\s+/i;

function respond(text) {
  logMessage('assistant', text);
  JarvisVoice.speak(text);
}

function summarizeResult(text) {
  const clean = text
    .replace(/(\p{L})(\d)/gu, '$1 $2')     // « Actifs27 » → « Actifs 27 »
    .replace(/\s+/g, ' ')
    .trim();
  return clean.length > 300 ? clean.slice(0, 300) + '…' : clean;
}

/* Attend qu'un bloc résultat soit rempli par app.js, puis le lit */
function watchResult(resultId, timeout = 25000) {
  return new Promise(resolve => {
    const el = document.getElementById(resultId);
    if (!el) return resolve('');
    const read = () => (el.innerText || el.textContent).trim();   // innerText garde les séparations
    const initial = read();
    const started = Date.now();
    const iv = setInterval(() => {
      const now = read();
      const busy = /en cours|génération|chargement/i.test(now);
      if (now && now !== initial && !busy) { clearInterval(iv); resolve(now); }
      else if (Date.now() - started > timeout) { clearInterval(iv); resolve(''); }
    }, 400);
  });
}

/* Ouvre un module, préremplit, déclenche l'action app.js et lit le résultat */
async function runModuleAction(winId, triggerId, resultId, announce, fills = {}) {
  openWindow(winId);
  for (const [id, value] of Object.entries(fills)) {
    const el = document.getElementById(id);
    if (el) el.value = value;
  }
  respond(announce);
  const trigger = document.getElementById(triggerId);
  if (trigger) {
    if (trigger.tagName === 'FORM') trigger.requestSubmit();
    else trigger.click();
  }
  const text = await watchResult(resultId);
  if (text) respond(summarizeResult(text));
  else respond("Je n'ai pas obtenu de résultat. Vérifie le module ouvert à l'écran.");
}

async function speakStatus() {
  try {
    const h = await fetchJson('/health');
    const parts = [`Tous les systèmes sont ${h.status === 'ok' ? 'opérationnels' : 'dégradés'}.`];
    const cases = badgeCounts['win-dossiers'];
    const approvals = badgeCounts['win-approbations'];
    const inbox = badgeCounts['win-inbox'];
    if (cases) parts.push(`${cases} dossier${cases > 1 ? 's' : ''} d'investigation ouvert${cases > 1 ? 's' : ''}.`);
    if (approvals) parts.push(`${approvals} approbation${approvals > 1 ? 's' : ''} en attente.`);
    if (inbox) parts.push(`${inbox} élément${inbox > 1 ? 's' : ''} dans l'inbox.`);
    if (parts.length === 1) parts.push('Rien ne requiert ton attention immédiate.');
    respond(parts.join(' '));
  } catch {
    respond('Le serveur ne répond pas. Je fonctionne en mode dégradé.');
  }
}

function speakCounts(lower) {
  const asks = [
    [/dossier|cas\b/,      'win-dossiers',     n => `Il y a ${n} dossier${n > 1 ? 's' : ''} d'investigation ouvert${n > 1 ? 's' : ''}.`],
    [/approbation/,        'win-approbations', n => `${n} approbation${n > 1 ? 's' : ''} en attente.`],
    [/inbox|livrable/,     'win-inbox',        n => `${n} élément${n > 1 ? 's' : ''} dans l'inbox.`],
    [/document|m[ée]moire/,'win-memoire',      n => `${n} document${n > 1 ? 's' : ''} en mémoire.`],
    [/playbook/,           'win-methodes',     n => `${n} playbook${n > 1 ? 's' : ''} enregistré${n > 1 ? 's' : ''}.`],
    [/watchlist|veille/,   'win-veille',       n => `${n} watchlist${n > 1 ? 's' : ''} active${n > 1 ? 's' : ''}.`],
    [/connecteur/,         'win-connecteurs',  n => `${n} connecteur${n > 1 ? 's' : ''} configuré${n > 1 ? 's' : ''}.`],
  ];
  for (const [re, winId, phrase] of asks) {
    if (re.test(lower)) {
      const n = badgeCounts[winId] ?? 0;
      return respond(n > 0 ? phrase(n) : 'Aucun pour le moment.');
    }
  }
  respond("Précise ce que tu veux compter : dossiers, approbations, inbox, documents, playbooks, watchlists ou connecteurs.");
}

function chatSessionId() {
  const el = document.getElementById('chat-session');
  return (el && el.value.trim()) || 'perso';
}

function resetSession() {
  const log = document.getElementById('chat-log');
  const session = document.getElementById('chat-session');
  if (session) session.value = `session-${Date.now().toString(36)}`;
  if (log) log.innerHTML = '';
}

/* Routeur principal : chaque phrase adressée à l'orb passe ici */
async function askJarvis(rawText) {
  const text = rawText.trim();
  if (!text) return;
  const lower = text.toLowerCase();

  // Interruption immédiate
  if (/^(stop|silence|chut|tais[- ]toi)\.?$/.test(lower)) {
    JarvisVoice.stop();
    JarvisVoice.showCaption('');
    if (JarvisOrb) JarvisOrb.setState(JarvisEars.active() ? 'listening' : 'idle');
    return;
  }

  logMessage('user', text);
  if (JarvisOrb) JarvisOrb.setState('thinking');
  JarvisVoice.showCaption('…');

  // 1. Navigation : « ouvre les dossiers »
  if (OPEN_VERB.test(lower)) {
    const rest = lower.replace(OPEN_VERB, '');
    for (const [re, winId, label] of COMMAND_TARGETS) {
      if (re.test(rest)) {
        openWindow(winId);
        return respond(`J'ouvre le module ${label}.`);
      }
    }
  }

  // 2. Analyse CVE directe : « analyse CVE-2021-44228 »
  const cve = text.match(/CVE-\d{4}-\d{4,}/i);
  if (cve) {
    return runModuleAction('win-cve', 'cve-form', 'cve-result',
      `J'analyse la ${cve[0].toUpperCase()}.`, { 'cve-id': cve[0].toUpperCase() });
  }

  // 3. Opérations SOC
  if (/brief (du jour|quotidien)|r[ée]sum[ée] (du jour|quotidien)/.test(lower)) {
    return runModuleAction('win-veille', 'daily-brief-form', 'daily-brief-result',
      'Je génère le brief quotidien.');
  }
  if (/brief de (quart|shift)|handover|rel[èe]ve/.test(lower)) {
    return runModuleAction('win-dossiers', 'refresh-shift-brief', 'shift-brief-result',
      'Je prépare le brief de quart.');
  }
  if (/\bsla\b|vieillissement/.test(lower)) {
    return runModuleAction('win-dossiers', 'refresh-sla-watch', 'sla-watch-result',
      'Je contrôle les SLA des dossiers.');
  }
  if (/priorit|file (soc|de travail)|par quoi je commence/.test(lower)) {
    return runModuleAction('win-dossiers', 'refresh-soc-queue', 'soc-queue-list',
      'Voici la file de travail priorisée.');
  }

  // 3 bis. Outils MCP : calculer ou exécuter un outil par son nom (prioritaire
  // sur le statut, car les noms d'outils peuvent contenir « système », etc.)
  const calc = text.match(/^calcule[:\s]+(.+)$/i);
  if (calc) {
    const tools = await mcpEnsureTools();
    const tool = tools.find(t => t.name === 'calcul');
    if (tool) {
      try {
        const data = await mcpCall(tool.server, tool.name, { expression: calc[1].trim() });
        return respond(data.content);
      } catch (err) {
        return respond(`L'outil de calcul a échoué : ${err.message || err}`);
      }
    }
    // pas d'outil de calcul : la question part au LLM ci-dessous
  }
  const useTool = text.match(/^(?:utilise|ex[ée]cute) l'outil\s+([\w.-]+)\s*(.*)$/i);
  if (useTool) {
    const tools = await mcpEnsureTools();
    const tool = tools.find(t => t.name.toLowerCase() === useTool[1].toLowerCase());
    if (!tool) return respond(`Je ne trouve pas d'outil MCP nommé « ${useTool[1]} ».`);
    let args = {};
    const rawArgs = useTool[2].trim();
    if (rawArgs) {
      try {
        args = JSON.parse(rawArgs);
      } catch {
        // Pas du JSON : si l'outil n'attend qu'un seul champ, on lui passe le texte
        const props = Object.keys((tool.input_schema || {}).properties || {});
        if (props.length === 1) args = { [props[0]]: rawArgs };
      }
    }
    try {
      const data = await mcpCall(tool.server, tool.name, args);
      return respond(summarizeResult(data.content || "L'outil n'a rien renvoyé."));
    } catch (err) {
      return respond(`L'appel de « ${tool.name} » a échoué : ${err.message || err}`);
    }
  }
  if (/quels outils|liste (les |tes )?outils/.test(lower)) {
    const tools = await mcpEnsureTools();
    if (!tools.length) {
      return respond("Aucun outil MCP n'est connecté. Configure mcp_servers.json pour m'en donner.");
    }
    openWindow('win-mcp');
    const names = tools.map(t => t.name).join(', ');
    return respond(`J'ai ${tools.length} outil${tools.length > 1 ? 's' : ''} MCP à disposition : ${names}.`);
  }

  // 4. Statut & compteurs
  if (/rapport de situation|statut|status|[ée]tat (du |des |g[ée]n)|es-tu (l[àa]|op[ée]rationnel)|tout va bien|\bsyst[èe]mes?\b/.test(lower)) {
    return speakStatus();
  }
  if (/combien (de|d')/.test(lower)) return speakCounts(lower);

  // 5. Heure, date, identité
  if (/quelle heure/.test(lower)) {
    const now = new Date();
    return respond(`Il est ${now.getHours()} heures ${String(now.getMinutes()).padStart(2, '0')}, ${userName}.`);
  }
  if (/quel jour|quelle date/.test(lower)) {
    return respond(`Nous sommes le ${new Date().toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}.`);
  }
  if (/qui es[- ]tu|pr[ée]sente[- ]toi/.test(lower)) {
    return respond(`Je suis Jarvis, ton copilote cybersécurité et assistant personnel, ${userName}. Je peux analyser des CVE, trier des alertes, mener des investigations, générer des briefs et piloter tous les modules à l'écran.`);
  }
  if (/nouvelle session|r[ée]initialise/.test(lower)) {
    resetSession();
    return respond(`Nouvelle session ouverte, ${userName}.`);
  }

  // 6. Par défaut : le LLM répond (local d'abord, via /chat)
  try {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...fxAuthHeaders() },
      body: JSON.stringify({ session_id: chatSessionId(), message: text }),
    });
    if (!res.ok) throw new Error(String(res.status));
    const data = await res.json();
    respond(data.answer || "Je n'ai pas de réponse à te donner.");
  } catch {
    respond("Je n'arrive pas à joindre le moteur de réponse. Vérifie que le serveur Jarvis est en ligne.");
  }
}

/* ── Outils MCP : fenêtre de pilotage + appels ──────────── */

let mcpTools = [];
let mcpSelectedTool = null;

function mcpArgsSkeleton(schema) {
  const skeleton = {};
  const props = (schema && schema.properties) || {};
  for (const [key, def] of Object.entries(props)) {
    if (def.type === 'integer' || def.type === 'number') skeleton[key] = 0;
    else if (def.type === 'boolean') skeleton[key] = false;
    else if (def.type === 'array') skeleton[key] = [];
    else if (def.type === 'object') skeleton[key] = {};
    else skeleton[key] = '';
  }
  return skeleton;
}

function mcpSelectTool(tool) {
  mcpSelectedTool = tool;
  const form = document.getElementById('mcp-call-form');
  const title = document.getElementById('mcp-call-title');
  const args = document.getElementById('mcp-call-args');
  if (!form || !title || !args) return;
  form.classList.remove('hidden');
  title.textContent = `${tool.server} · ${tool.name}`;
  args.value = JSON.stringify(mcpArgsSkeleton(tool.input_schema), null, 2);
}

async function mcpRefresh() {
  const serverList = document.getElementById('mcp-server-list');
  const toolList = document.getElementById('mcp-tool-list');
  if (!serverList || !toolList) return;
  serverList.textContent = 'Interrogation des serveurs MCP…';
  serverList.classList.remove('empty');
  try {
    const status = await fetchJson('/mcp/status');
    if (!status.servers.length) {
      serverList.classList.add('empty');
      serverList.innerHTML = 'Aucun serveur MCP configuré. Copie <code>mcp_servers.json.example</code> vers <code>mcp_servers.json</code> puis redémarre le serveur.';
      toolList.classList.add('empty');
      toolList.textContent = status.sdk_available
        ? 'Aucun outil disponible.'
        : "SDK MCP absent : pip install 'jarvis-cyber[mcp]'.";
      return;
    }
    serverList.innerHTML = '';
    for (const server of status.servers) {
      const item = document.createElement('div');
      item.className = 'mcp-item';
      item.innerHTML = `
        <span class="mcp-dot ${server.connected ? 'ok' : 'ko'}"></span>
        <strong>${escapeHtmlFx(server.name)}</strong>
        <span class="mcp-meta">${server.connected
          ? `${server.tools_count} outil${server.tools_count > 1 ? 's' : ''}`
          : escapeHtmlFx(server.error || 'injoignable')}</span>`;
      serverList.appendChild(item);
    }

    mcpTools = await fetchJson('/mcp/tools');
    if (!mcpTools.length) {
      toolList.classList.add('empty');
      toolList.textContent = 'Aucun outil exposé par les serveurs connectés.';
      return;
    }
    toolList.classList.remove('empty');
    toolList.innerHTML = '';
    for (const tool of mcpTools) {
      const item = document.createElement('div');
      item.className = 'mcp-item mcp-tool';
      item.innerHTML = `
        <div class="mcp-tool-text">
          <strong>${escapeHtmlFx(tool.name)}</strong>
          <span class="mcp-meta">${escapeHtmlFx(tool.server)} — ${escapeHtmlFx(tool.description)}</span>
        </div>
        <button type="button" class="secondary-button">UTILISER</button>`;
      item.querySelector('button').addEventListener('click', () => mcpSelectTool(tool));
      toolList.appendChild(item);
    }
  } catch (err) {
    serverList.classList.add('empty');
    serverList.textContent = `Statut MCP indisponible : ${err.message || err}`;
  }
}

async function mcpCall(server, tool, args) {
  const res = await fetch('/mcp/call', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...fxAuthHeaders() },
    body: JSON.stringify({ server, tool, arguments: args || {} }),
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch { /* corps non JSON */ }
    throw new Error(detail);
  }
  return res.json();
}

async function mcpEnsureTools() {
  if (!mcpTools.length) {
    try { mcpTools = await fetchJson('/mcp/tools'); } catch { /* MCP indisponible */ }
  }
  return mcpTools;
}

const mcpForm = document.getElementById('mcp-call-form');
if (mcpForm) {
  mcpForm.addEventListener('submit', async e => {
    e.preventDefault();
    if (!mcpSelectedTool) return;
    const resultEl = document.getElementById('mcp-result');
    const argsEl = document.getElementById('mcp-call-args');
    let args = {};
    try {
      args = JSON.parse(argsEl.value || '{}');
    } catch {
      resultEl.className = 'result';
      resultEl.textContent = 'Arguments invalides : le JSON ne se lit pas.';
      return;
    }
    resultEl.className = 'result';
    resultEl.textContent = 'Exécution en cours…';
    try {
      const data = await mcpCall(mcpSelectedTool.server, mcpSelectedTool.name, args);
      resultEl.textContent = data.content || '(réponse vide)';
      respond(summarizeResult(data.content || "L'outil n'a rien renvoyé."));
    } catch (err) {
      resultEl.textContent = `Échec : ${err.message || err}`;
    }
  });
}
const mcpRefreshBtn = document.getElementById('mcp-refresh');
if (mcpRefreshBtn) mcpRefreshBtn.addEventListener('click', mcpRefresh);

/* ── Oreilles : reconnaissance vocale continue ──────────── */

const JarvisEars = (() => {
  const micBtn = document.getElementById('orb-mic');
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let rec = null;
  let on = false;

  function start() {
    if (!SR) {
      respond('La reconnaissance vocale n’est pas disponible dans ce navigateur. Utilise le champ texte sous l’orb.');
      return;
    }
    if (on) return;
    on = true;
    if (micBtn) micBtn.classList.add('active');
    if (JarvisOrb) JarvisOrb.setState('listening');
    rec = new SR();
    rec.lang = 'fr-FR';
    rec.interimResults = true;
    rec.continuous = false;
    rec.onresult = e => {
      let final = '', interim = '';
      for (const r of e.results) {
        if (r.isFinal) final += r[0].transcript;
        else interim += r[0].transcript;
      }
      if (interim) JarvisVoice.showCaption(interim + ' …');
      if (final) {
        JarvisVoice.stop();            // barge-in : on coupe Jarvis s'il parlait
        askJarvis(final);
      }
    };
    rec.onend = () => { if (on && rec) { try { rec.start(); } catch { /* redémarrage refusé */ } } };
    rec.onerror = e => {
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
        stop();
        respond('Je n’ai pas accès au microphone. Autorise-le dans le navigateur.');
      }
    };
    try { rec.start(); } catch { /* déjà démarré */ }
  }

  function stop() {
    on = false;
    if (micBtn) micBtn.classList.remove('active');
    if (rec) { rec.onend = null; try { rec.stop(); } catch { /* déjà arrêté */ } rec = null; }
    if (JarvisOrb) JarvisOrb.setState('idle');
  }

  if (micBtn) micBtn.addEventListener('click', () => (on ? stop() : start()));
  return { active: () => on, stop };
})();

/* ── Entrée texte sous l'orb ────────────────────────────── */

const orbForm  = document.getElementById('orb-form');
const orbInput = document.getElementById('orb-input');
if (orbForm && orbInput) {
  orbForm.addEventListener('submit', e => {
    e.preventDefault();
    const text = orbInput.value.trim();
    if (!text) return;
    orbInput.value = '';
    JarvisVoice.stop();
    askJarvis(text);
  });
}

// Cliquer l'orb met le focus sur l'entrée : on lui parle directement
const orbClickable = document.getElementById('jarvis-orb');
if (orbClickable && orbInput) orbClickable.addEventListener('click', () => orbInput.focus());

// Bouton console (transcription complète + contrôles avancés)
const consoleBtn = document.getElementById('console-button');
if (consoleBtn) consoleBtn.addEventListener('click', () => openWindow('win-chat'));

// Nouvelle session
const newChat = document.getElementById('new-chat-button');
if (newChat) {
  newChat.addEventListener('click', () => {
    resetSession();
    respond(`Nouvelle session ouverte, ${userName}. Dis-moi sur quoi tu veux travailler.`);
  });
}

/* ── Console : les réponses du formulaire passent aussi par l'orb ── */

const chatLog = document.getElementById('chat-log');
if (chatLog) {
  new MutationObserver(mutations => {
    for (const m of mutations) {
      for (const node of m.addedNodes) {
        if (node.nodeType !== 1 || node.dataset.orb) continue;   // déjà géré par l'orb
        if (node.classList.contains('message') && node.classList.contains('assistant')) {
          const p = node.querySelector('p');
          if (p) JarvisVoice.speak(p.textContent || '');
        }
      }
    }
  }).observe(chatLog, { childList: true });
}

// Navigation rapide depuis le formulaire console (« ouvre … »)
document.addEventListener('submit', e => {
  if (e.target !== document.getElementById('chat-form')) return;
  const input = document.getElementById('chat-message');
  if (!input) return;
  const msg = input.value.trim().toLowerCase();
  if (!OPEN_VERB.test(msg)) return;
  const rest = msg.replace(OPEN_VERB, '');
  for (const [re, winId, label] of COMMAND_TARGETS) {
    if (re.test(rest)) {
      e.preventDefault();
      e.stopPropagation();
      input.value = '';
      openWindow(winId);
      respond(`J'ouvre le module ${label}.`);
      return;
    }
  }
}, true);

// Le formulaire console déclenche l'état « réflexion » de l'orb
const chatFormEl = document.getElementById('chat-form');
if (chatFormEl && JarvisOrb) chatFormEl.addEventListener('submit', () => JarvisOrb.setState('thinking'));

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

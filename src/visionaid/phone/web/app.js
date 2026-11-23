// VisionAId — page capteur : caméra arrière + IMU → PC (protocole v1, voir docs/protocol.md).
// JavaScript pur, sans dépendance. Fonctionne sur Safari iOS ≥ 15 et Chrome Android.
"use strict";

const PROTOCOL = 1;
const $ = (id) => document.getElementById(id);
const ui = {
  status: $("status"), start: $("start"), stop: $("stop"), capture: $("capture"),
  calibMode: $("calibMode"), video: $("video"), fps: $("fps"), imu: $("imu"), rtt: $("rtt"),
  age: $("age"), bubble: $("bubble"), levelText: $("levelText"), log: $("log"),
  notes: $("notes"), sendNotes: $("sendNotes"),
  sound: $("sound"), volume: $("volume"), volumeOut: $("volumeOut"), testSound: $("testSound"),
  talk: $("talk"), talkLabel: $("talkLabel"), talkHint: $("talkHint"), heard: $("heard"),
  typed: $("typed"), sendTyped: $("sendTyped"),
  connPills: document.querySelectorAll("[data-conn]"), waitCore: $("waitCore"),
  chkPc: $("chkPc"), chkGuide: $("chkGuide"), levelPill: $("levelPill"), advanced: $("advanced"),
  guideTalk: $("guideTalk"), stopGuide: $("stopGuide"), gTitle: $("gTitle"), gDist: $("gDist"),
  gSide: $("gSide"), dirDot: $("dirDot"), phasePill: $("phasePill"),
  screens: { connect: $("screenConnect"), wait: $("screenWait"), talk: $("screenTalk"), guide: $("screenGuide") },
};
// Objets connus : nom dit dans les titres (le PC envoie le nom de la fiche).
const OBJECTS = { gourde: "la gourde", cles: "les clés" }; // si l'ordinateur ne donne pas le nom
const audio = window.guideAudio;
audio.onStatus = (text, cls) => { ui.sound.textContent = text; ui.sound.className = cls || ""; };

// Réglages par défaut, remplacés par le message « welcome » du PC.
const cfg = {
  max_fps: 15, jpeg_quality: 0.7, imu_batch_ms: 50, capture_width: 640, capture_height: 480,
  ack_timeout_s: 1.0, ping_interval_s: 1.0,
};

const state = {
  running: false, ws: null, stream: null, wakeLock: null, seq: 0, busy: false,
  waitingAck: false, sentAt: 0, lastSend: 0, imuBuf: [], imuCount: 0, pingId: 0,
  pings: new Map(), lastRtt: null, lastRttId: null, reconnectDelay: 500, timers: [], hasImu: false,
  canvas: document.createElement("canvas"),
  voice: null, greeted: false, listening: null, spokenIds: new Set(),
  screen: "connect", controlled: false, guideOn: false, searching: false, target: "", guideState: "",
};

// ------------------------------------------------------------------ écrans
// connexion (Démarrer) → attente → Parler → guidage (distance et direction) ; un seul visible.
// Piloté par l'application de l'ordinateur, le téléphone attend que le guidage y soit lancé.
function showScreen(name) {
  if (state.screen === name) return;
  state.screen = name;
  for (const [k, el] of Object.entries(ui.screens)) el.hidden = k !== name;
  const h1 = ui.screens[name].querySelector("h1");
  if (h1) { h1.setAttribute("tabindex", "-1"); h1.focus({ preventScroll: true }); }
}

function setConn(text, cls) {
  for (const el of ui.connPills) {
    el.textContent = text;
    el.className = "pill" + (cls ? " " + cls : "");
  }
  ui.chkPc.className = cls === "ok" ? "ok" : "wait";
  ui.chkPc.textContent = cls === "ok" ? "Ordinateur connecté" : "Connexion à l'ordinateur…";
  ui.chkGuide.className = cls === "ok" ? "wait" : "";
  ui.chkGuide.textContent = cls === "ok" ? "Guidage : en attente" : "Guidage lancé sur l'ordinateur";
}

// Écran attendu, déduit d'un seul état (le même que celui de l'ordinateur) :
// - piloté par l'ordinateur et guidage pas lancé → attente ;
// - une recherche est en cours (dite au téléphone, ou objet choisi sur l'ordinateur) → guidage,
//   tout de suite, même avant la première consigne sonore ;
// - sinon (guidage lancé, à la voix, rien demandé encore) → Parler.
function expectedScreen() {
  if (state.controlled && !state.guideOn) return "wait";
  return state.searching ? "guide" : "talk";
}

function syncScreen() {
  if (!state.running) return;
  const s = expectedScreen();
  if (s === "wait") stopListening(true); // on peut parler sur Parler et pendant le guidage
  if (s === "guide" && state.screen !== "guide") showSearching();
  showScreen(s);
}

// Recherche lancée : titre « Je cherche … » en attendant la première consigne du PC.
function showSearching() {
  const obj = objName();
  ui.gTitle.textContent = `Je cherche ${obj}.`;
  ui.phasePill.textContent = "Recherche";
  ui.gDist.textContent = "…";
  ui.gSide.textContent = "tournez lentement";
  ui.dirDot.style.opacity = "0";
  state.guideState = "SEARCHING";
}

function setGuideOn(on) {
  state.guideOn = on;
  if (!on) state.searching = false;
  syncScreen();
}

function objName() {
  return state.spoken || OBJECTS[state.target] || "l'objet";
}

function setSearch(search) {
  state.searching = !!search;
  if (search && search.target) {
    state.target = search.target;
    state.spoken = search.spoken || "";
  }
  syncScreen();
}

function waitMessage() {
  if (!state.ws || ui.chkPc.className !== "ok") return "Connexion à l'ordinateur en cours.";
  return "Téléphone prêt. Le guidage se lance depuis l'ordinateur.";
}

// Outils de test du téléphone : seulement avec « ?outils » dans l'adresse. Le mode avancé de
// l'ordinateur ne change rien ici (il ouvre Rerun sur l'ordinateur).
const TOOLS = new URLSearchParams(location.search).has("outils");
function setAdvanced() {
  ui.advanced.hidden = !TOOLS;
  ui.video.classList.toggle("offscreen", !TOOLS);
}

// Consigne du PC → écran de guidage (titres courts : la voix dit le détail dans le casque).
function updateGuide(m) {
  const st = m.state || "IDLE";
  if (!state.running) return;
  // l'écran suit l'état (attente / Parler / guidage), jamais l'inverse : une consigne en retard
  // ou au repos (IDLE) ne fait pas changer d'écran
  // lancement en ligne de commande (sans l'application) : la consigne suffit à passer en guidage
  if (!state.controlled && !state.searching && st !== "IDLE") setSearch({});
  if (!state.searching || state.screen !== "guide" || st === "IDLE") return;
  const obj = objName();
  const searching = st === "SEARCHING";
  const titles = {
    SEARCHING: [`Je cherche ${obj}.`, "Recherche"],
    NAVIGATING: [`Vers ${obj}.`, "En route"],
    APPROACHING: [`Presque arrivé.`, "En route"],
    ARRIVED: ["Arrivé.", "Arrivée"],
    OBSTACLE_ALERT: ["Obstacle proche.", "Attention"],
    TRACKING_LOST: ["Arrêtez-vous un instant.", "Repérage"],
  };
  const [title, pill] = titles[st] || [`Vers ${obj}.`, "En route"];
  if (st !== state.guideState) {
    ui.gTitle.textContent = title;
    ui.phasePill.textContent = pill;
    state.guideState = st;
  }
  const d = Number.isFinite(m.dist) && !searching ? m.dist : null;
  ui.gDist.textContent = d === null ? (searching ? "…" : "–") : `${d.toFixed(1).replace(".", ",")} m`;
  const az = Number.isFinite(m.az) ? m.az : null;
  if (az === null || searching) {
    ui.dirDot.style.opacity = "0";
    ui.gSide.textContent = searching ? "tournez lentement" : "";
  } else {
    const deg = -az * 180 / Math.PI; // azimut positif à gauche ; à l'écran, gauche = angle négatif
    ui.dirDot.style.opacity = "1";
    ui.dirDot.style.transform = `rotate(${deg.toFixed(1)}deg)`;
    const a = Math.abs(deg), side = deg < 0 ? "gauche" : "droite";
    ui.gSide.textContent = a <= 10 ? "en face" : a <= 45 ? `légèrement à ${side}` : a <= 120 ? `à ${side}` : `derrière, à ${side}`;
  }
}

// Horloge du téléphone en secondes, commune aux images et aux capteurs.
const nowS = (perfMs) => (performance.timeOrigin + (perfMs ?? performance.now())) / 1000;

function log(msg) {
  const line = `${new Date().toLocaleTimeString()} ${msg}`;
  ui.log.textContent = (line + "\n" + ui.log.textContent).slice(0, 4000);
}

function setStatus(text, cls) {
  ui.status.textContent = text;
  ui.status.className = cls || "";
}

// ------------------------------------------------------------------ caméra
function openCamera() {
  return navigator.mediaDevices.getUserMedia({
    audio: false,
    video: {
      facingMode: { ideal: "environment" },
      // 4:3 (champ complet du capteur) ; le navigateur tourne l'image selon l'orientation
      width: { ideal: cfg.capture_width }, height: { ideal: cfg.capture_height },
      frameRate: { ideal: 30 },
    },
  });
}

// iOS peut couper la caméra sans le dire (son, voix, appel…) : la vidéo garde alors sa
// dernière image. Une image figée envoyée au PC est pire que rien (le PC croit que la
// personne ne bouge pas alors que les capteurs disent le contraire) : on ne l'envoie pas
// et on rouvre la caméra.
function watchTracks(stream) {
  for (const t of stream.getVideoTracks()) {
    t.onended = () => restartCamera("piste terminée");
    t.onmute = () => setTimeout(() => { if (t.muted) restartCamera("piste coupée"); }, 500);
  }
}

async function restartCamera(why) {
  if (!state.running || state.restarting) return;
  if (performance.now() - (state.lastRestart || 0) < 3000) return; // pas de relance en boucle
  state.restarting = true;
  state.lastRestart = performance.now();
  const info = `caméra figée (${why}) ; son=${navigator.audioSession ? navigator.audioSession.type : "?"}` +
    `, voix=${audio.speakingNow() ? "ordinateur" : window.speechSynthesis && speechSynthesis.speaking ? "navigateur" : "non"}, écran=${state.screen}`;
  log("Caméra relancée : " + info);
  send({ type: "event", text: info });
  try {
    if (state.stream) state.stream.getTracks().forEach((t) => t.stop());
    state.stream = await openCamera();
    watchTracks(state.stream);
    ui.video.srcObject = state.stream;
    await ui.video.play().catch(() => {});
  } catch (e) {
    log("Caméra impossible à rouvrir : " + e);
    send({ type: "event", text: "caméra impossible à rouvrir : " + (e.name || e) });
  } finally {
    state.sameFrames = 0;
    state.lastSig = "";
    state.restarting = false;
  }
}

// Empreinte d'une image JPEG : deux images identiques au bit près = caméra figée (un vrai
// capteur a toujours un peu de bruit).
function jpegSig(b) {
  let h = b.length;
  for (let i = 0; i < b.length; i += 61) h = (h * 31 + b[i]) | 0;
  return `${b.length}:${h}`;
}

// ------------------------------------------------------------------ démarrage
async function start() {
  if (!window.isSecureContext) {
    setStatus("Page non sécurisée : ouvrez l'adresse en https://, comme indiqué sur l'ordinateur.", "err");
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    setStatus("Caméra inaccessible dans ce navigateur.", "err");
    return;
  }
  ui.start.disabled = true;
  state.greeted = false;
  state.waitSpoken = false;
  state.guideOn = state.searching = false;
  // iOS : le son ne se déverrouille que dans le geste de l'utilisateur, avant toute attente
  audio.unlock();
  // iOS : la permission des capteurs doit être demandée dans le geste de l'utilisateur, en premier.
  try {
    if (typeof DeviceMotionEvent !== "undefined" && typeof DeviceMotionEvent.requestPermission === "function") {
      const r = await DeviceMotionEvent.requestPermission();
      if (r !== "granted") log("Capteurs de mouvement refusés : la pose sera moins robuste.");
    }
  } catch (e) {
    log("Permission capteurs : " + e);
  }
  window.addEventListener("devicemotion", onMotion);

  try {
    state.stream = await openCamera();
  } catch (e) {
    const why = {
      NotAllowedError: "accès à la caméra refusé (Réglages → Safari → Caméra)",
      NotFoundError: "aucune caméra trouvée",
      NotReadableError: "caméra déjà utilisée par une autre application",
      OverconstrainedError: "résolution demandée non disponible",
    }[e.name] || e.message || String(e);
    setStatus("Caméra : " + why, "err");
    ui.start.disabled = false;
    return;
  }
  watchTracks(state.stream);
  ui.video.srcObject = state.stream;
  await ui.video.play().catch(() => {});
  await new Promise((res) => (ui.video.videoWidth ? res() : ui.video.addEventListener("loadedmetadata", res, { once: true })));

  await requestWakeLock();
  document.addEventListener("visibilitychange", onVisibility);

  state.running = true;
  showScreen("wait"); // jusqu'au « welcome » : piloté par l'ordinateur ou non
  audio.start();
  ui.stop.disabled = false;
  ui.capture.disabled = false;
  ui.sendNotes.disabled = false;
  connect();
  scheduleFrames();
  state.timers.push(setInterval(flushImu, cfg.imu_batch_ms));
  state.timers.push(setInterval(sendPing, cfg.ping_interval_s * 1000));
  state.timers.push(setInterval(() => {
    if (state.running && !state.hasImu) ui.imu.textContent = "absente";
  }, 3000));
}

function stop() {
  state.running = false;
  stopListening(true);
  audio.stop();
  send({ type: "bye" });
  state.timers.forEach(clearInterval);
  state.timers = [];
  window.removeEventListener("devicemotion", onMotion);
  if (state.ws) state.ws.close();
  if (state.stream) state.stream.getTracks().forEach((t) => t.stop());
  if (state.wakeLock) state.wakeLock.release().catch(() => {});
  ui.start.disabled = false;
  ui.stop.disabled = true;
  ui.capture.disabled = true;
  state.greeted = false;
  state.waitSpoken = false;
  showScreen("connect");
  setStatus("Arrêté. Touchez Démarrer pour reprendre.", "");
}

async function requestWakeLock() {
  try {
    if ("wakeLock" in navigator) {
      state.wakeLock = await navigator.wakeLock.request("screen");
    } else {
      log("Verrou d'écran indisponible : désactivez le verrouillage automatique (Réglages → Luminosité).");
    }
  } catch (e) {
    log("Verrou d'écran : " + e);
  }
}

function onVisibility() {
  if (document.visibilityState === "visible" && state.running) requestWakeLock();
  if (document.visibilityState === "hidden" && state.running) log("Page masquée : la caméra peut être suspendue.");
}

// ------------------------------------------------------------------ connexion
function connect() {
  if (!state.running) return;
  const ws = new WebSocket(`wss://${location.host}/ws`);
  ws.binaryType = "arraybuffer";
  state.ws = ws;
  setStatus("Connexion à l'ordinateur…", "warn");
  setConn("Connexion…", "");
  ws.onopen = () => {
    state.reconnectDelay = 500;
    state.waitingAck = false;
    send({
      type: "hello", protocol: PROTOCOL, ua: navigator.userAgent,
      camera: { w: ui.video.videoWidth, h: ui.video.videoHeight },
      imu: state.hasImu, gyro_units: "deg/s", t_phone: nowS(),
    });
  };
  ws.onmessage = (ev) => {
    let m;
    try { m = JSON.parse(ev.data); } catch { return; }
    if (m.type === "welcome") {
      for (const k of Object.keys(cfg)) if (m[k] !== undefined && m[k] !== null) cfg[k] = m[k];
      setStatus(m.session ? `Connecté — enregistrement « ${m.session} »` : "Connecté", "ok");
      setConn("Connecté", "ok");
      state.controlled = !!m.controlled;
      const firstWelcome = state.screen === "wait" && !state.waitSpoken;
      state.guideOn = !!m.guide;
      setSearch(m.guide || !state.controlled ? m.search : null); // reconnexion : même écran qu'avant
      if (firstWelcome && state.screen === "wait") {
        state.waitSpoken = true;
        audio.speak(waitMessage(), false);
      }
      audio.setLevels(m.levels);
      setAdvanced();
      audio.configure(m.audio).then(() => { ui.testSound.disabled = !audio.ready; });
      onVoiceSettings(m.voice);
    } else if (m.type === "sound") {
      audio.onSound(m);
      updateGuide(m);
    } else if (m.type === "quit") {
      // VisionAId fermé sur l'ordinateur : silence, retour à la page de démarrage
      audio.cancelSpeech();
      stop();
      setStatus("VisionAId a été fermé sur l'ordinateur. Touchez Démarrer quand il sera relancé.", "warn");
      audio.speak("VisionAId est fermé sur l'ordinateur.", false);
    } else if (m.type === "test_sound") {
      audio.unlock();
      if (audio.test()) log("Test du son demandé par l'ordinateur.");
    } else if (m.type === "preview") {
      audio.preview(m.sound);
    } else if (m.type === "levels") {
      audio.setLevels(m.levels);
    } else if (m.type === "advanced") {
      setAdvanced();
    } else if (m.type === "guide") {
      setGuideOn(!!m.on);
      // guidage lancé depuis l'ordinateur, à la voix : on invite à parler
      if (m.on && m.mode !== "here" && state.voice && state.voice.mode === "stt") {
        audio.speak("Appuie sur le grand bouton Parler, puis dis ce que tu cherches.", false);
      }
    } else if (m.type === "speech") {
      if (!state.spokenIds.has(m.id)) {
        state.spokenIds.add(m.id);
        log("Voix : " + m.text);
        if (!state.voice || state.voice.tts !== false) audio.speak(m.text, !!m.duck);
      }
    } else if (m.type === "heard") {
      ui.heard.textContent = m.text ? `Compris : « ${m.text} »` : "Rien entendu";
      if (m.action === "search") {
        if (state.controlled) state.guideOn = true;
        setSearch({ target: m.target, spoken: m.spoken });
      } else if (m.action === "stop") {
        if (state.controlled) setGuideOn(false);
        else setSearch(null);
      }
      log(`Demande : « ${m.text} » → ${m.action}${m.target ? " (" + m.target + ")" : ""}`);
    } else if (m.type === "ack") {
      state.waitingAck = false;
    } else if (m.type === "pong") {
      const t0 = state.pings.get(m.id);
      if (t0 !== undefined) {
        state.lastRtt = (performance.now() - t0) / 1000;
        state.lastRttId = m.id;
        state.pings.delete(m.id);
      }
    } else if (m.type === "stats") {
      ui.fps.textContent = m.fps_in ?? "–";
      ui.imu.textContent = m.imu_hz ?? "–";
      ui.rtt.textContent = m.rtt_ms ?? "–";
      ui.age.textContent = m.frame_age_ms ?? "–";
    } else if (m.type === "error") {
      setStatus("PC : " + m.message, "err");
      log("Erreur du PC : " + m.message);
    }
  };
  ws.onclose = () => {
    if (state.ws === ws) state.ws = null;
    if (!state.running) return;
    setStatus(`Connexion perdue, nouvelle tentative dans ${(state.reconnectDelay / 1000).toFixed(1)} s…`, "warn");
    setConn("Connexion perdue…", "warn");
    setTimeout(connect, state.reconnectDelay);
    state.reconnectDelay = Math.min(state.reconnectDelay * 2, 5000);
  };
  ws.onerror = () => log("Erreur WebSocket (certificat installé ? même réseau ?)");
}

function send(obj) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) state.ws.send(JSON.stringify(obj));
}

function sendPing() {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return;
  const id = ++state.pingId;
  const t = performance.now();
  state.pings.set(id, t);
  if (state.pings.size > 20) state.pings.delete(state.pings.keys().next().value);
  // RTT de l'échange précédent, avec son identifiant (appariement côté PC)
  send({ type: "ping", id, t_phone: nowS(t), prev_id: state.lastRttId, rtt: state.lastRtt });
}

// ------------------------------------------------------------------ capteurs
function onMotion(e) {
  const r = e.rotationRate, a = e.accelerationIncludingGravity;
  if (!r || !a || r.alpha === null || a.x === null) return;
  state.hasImu = true;
  // repère appareil W3C ; gyro en deg/s : [beta (x), gamma (y), alpha (z)]
  state.imuBuf.push([nowS(e.timeStamp), r.beta, r.gamma, r.alpha, a.x, a.y, a.z]);
  if (++state.imuCount % 6 === 0) showLevel(a.x, a.y, a.z);
}

function flushImu() {
  if (!state.imuBuf.length) return;
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    if (state.imuBuf.length > 2000) state.imuBuf.splice(0, state.imuBuf.length - 2000);
    return;
  }
  send({ type: "imu", samples: state.imuBuf });
  state.imuBuf = [];
}

function showLevel(ax, ay, az) {
  // téléphone vertical en portrait : gravité selon +y (≈ 9,81)
  const roll = Math.atan2(ax, ay) * 180 / Math.PI;
  const pitch = Math.atan2(az, ay) * 180 / Math.PI;
  const x = Math.max(-45, Math.min(45, roll));
  ui.bubble.style.left = `calc(${50 + x}% - 14px)`;
  const ok = Math.abs(roll) < 10 && Math.abs(pitch) < 15;
  ui.bubble.style.background = ok ? "var(--ok)" : "var(--gold-dark)";
  ui.levelPill.hidden = false;
  ui.levelPill.textContent = ok ? "Téléphone bien droit" : "Redressez le téléphone";
  ui.levelPill.className = "pill " + (ok ? "ok" : "warn");
  ui.levelText.textContent = `Inclinaison : gauche/droite ${roll.toFixed(0)}°, avant/arrière ${pitch.toFixed(0)}°` +
    (ok ? " — bien placé" : " — redressez le téléphone");
}

// ------------------------------------------------------------------ images
function scheduleFrames() {
  if (!state.running) return;
  if ("requestVideoFrameCallback" in HTMLVideoElement.prototype) {
    ui.video.requestVideoFrameCallback((now, meta) => { onVideoFrame(meta); scheduleFrames(); });
  } else {
    setTimeout(() => { onVideoFrame(null); scheduleFrames(); }, 10);
  }
}

function onVideoFrame(meta) {
  if (!state.running || ui.calibMode.checked) return;
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN || state.busy) return;
  const t = performance.now();
  // contre-pression : on attend l'acquittement de l'image précédente (ou son délai d'expiration)
  if (state.waitingAck && t - state.sentAt < cfg.ack_timeout_s * 1000) return;
  if (t - state.lastSend < 1000 / cfg.max_fps) return;
  const capT = meta && Number.isFinite(meta.captureTime) ? meta.captureTime : t;
  sendFrame(nowS(capT), false);
}

function sendFrame(tPhone, calib) {
  const v = ui.video;
  const vw = v.videoWidth, vh = v.videoHeight;
  if (!vw || !vh) return;
  let w = vw, h = vh;
  if (!calib) { // réduction : le grand côté au plus égal au grand côté demandé
    const maxSide = Math.max(cfg.capture_width, cfg.capture_height);
    const s = Math.min(1, maxSide / Math.max(vw, vh));
    w = Math.round(vw * s); h = Math.round(vh * s);
  }
  const c = state.canvas;
  c.width = w; c.height = h;
  c.getContext("2d").drawImage(v, 0, 0, w, h);
  state.busy = true;
  const seq = ++state.seq;
  c.toBlob(async (blob) => {
    try {
      if (!blob || !state.ws || state.ws.readyState !== WebSocket.OPEN) return;
      const jpeg = new Uint8Array(await blob.arrayBuffer());
      if (!calib) {
        const sig = jpegSig(jpeg);
        if (sig === state.lastSig) {
          state.sameFrames = (state.sameFrames || 0) + 1;
          state.lastSend = performance.now(); // même cadence d'essai, sans rien envoyer
          if (state.sameFrames >= 8) restartCamera("image identique");
          return;
        }
        state.lastSig = sig;
        state.sameFrames = 0;
      }
      const hdr = new TextEncoder().encode(JSON.stringify({ type: "frame", seq, t_phone: tPhone, w, h, calib }));
      const buf = new Uint8Array(4 + hdr.length + jpeg.length);
      new DataView(buf.buffer).setUint32(0, hdr.length, false);
      buf.set(hdr, 4);
      buf.set(jpeg, 4 + hdr.length);
      state.ws.send(buf.buffer);
      if (!calib) {
        state.waitingAck = true;
        state.sentAt = performance.now();
        state.lastSend = state.sentAt;
      } else {
        log(`Vue de calibration ${seq} envoyée (${w}×${h}).`);
      }
    } finally {
      state.busy = false;
    }
  }, "image/jpeg", calib ? 0.95 : cfg.jpeg_quality);
}

// ------------------------------------------------------------------ voix : demande de l'utilisateur
// Deux reconnaissances : « whisper » (défaut) = on enregistre quelques secondes et le PC transcrit ;
// « phone » = reconnaissance de Safari (webkitSpeechRecognition), repli sur l'enregistrement.
// Le micro est coupé dès la fin : un casque Bluetooth repasse alors en stéréo de qualité.
function onVoiceSettings(v) {
  state.voice = v || null;
  if (v) { audio.voiceLang = v.lang || "fr-FR"; audio.voiceRate = v.rate || 1; }
  const stt = !!(v && v.mode === "stt");
  ui.talk.disabled = !stt;
  ui.guideTalk.disabled = !stt;
  ui.talkHint.hidden = !stt;
  if (!stt && v && v.target) ui.heard.textContent = `Objet cherché : ${v.target}`;
  // seul (sans l'application de l'ordinateur), le téléphone invite à parler dès la connexion
  if (!state.greeted && v && !state.controlled) {
    state.greeted = true;
    if (stt) audio.speak("Appuie sur le grand bouton Parler, puis dis ce que tu cherches.", false);
  }
}

function talk() {
  audio.unlock();
  if (state.listening) { stopListening(false); return; }
  audio.cancelSpeech();
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    ui.heard.textContent = "Micro inaccessible dans ce navigateur : écris l'objet ci-dessous";
    return;
  }
  audio.recording(true); // avant toute demande de micro, toujours dans le geste
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (state.voice && state.voice.stt === "phone" && SR) recognize(SR);
  else record();
}

function setListening(obj) {
  state.listening = obj;
  ui.talk.classList.toggle("listening", !!obj);
  ui.guideTalk.classList.toggle("listening", !!obj);
  ui.talkLabel.textContent = obj ? "J'écoute…" : "Parler";
  ui.talk.setAttribute("aria-label", obj ? "J'écoute : toucher pour finir" : "Parler : dire l'objet cherché");
}

function recognize(SR) {
  const r = new SR();
  r.lang = (state.voice && state.voice.lang) || "fr-FR";
  r.interimResults = false;
  r.maxAlternatives = 3;
  let done = false, fallback = false;
  r.onresult = (e) => {
    done = true;
    const alts = Array.from(e.results[0] || []).map((a) => a.transcript);
    ui.heard.textContent = `Entendu : « ${alts[0] || ""} »`;
    send({ type: "command", text: alts[0] || "", alternatives: alts.slice(1), source: "safari" });
  };
  r.onerror = (e) => {
    log("Reconnaissance du navigateur : " + e.error + " → enregistrement envoyé au PC");
    done = true;
    fallback = e.error !== "aborted";
  };
  r.onend = () => {
    if (state.listening && state.listening.rec === r) setListening(null);
    if (fallback) { record(); return; } // la session reste en « play-and-record »
    if (!done) ui.heard.textContent = "Rien entendu";
    audio.recording(false);
  };
  setListening({ rec: r, stop: () => r.stop() });
  audio.beep();
  r.start();
}

async function record() {
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  } catch (e) {
    audio.recording(false);
    ui.heard.textContent = "Micro : " + micError(e);
    log("Micro : " + e.name + " " + (e.message || ""));
    return;
  }
  const types = ["audio/mp4", "audio/webm;codecs=opus", "audio/webm", "audio/ogg"];
  const mime = types.find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || "";
  let rec;
  try { rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined); } catch (e) {
    stream.getTracks().forEach((t) => t.stop());
    audio.recording(false);
    ui.heard.textContent = "Enregistrement impossible sur ce navigateur";
    return;
  }
  const chunks = [];
  rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
  // fin automatique : silence de 0,9 s après la parole, ou durée maximale
  let analyser = null, srcNode = null, timer = null, spoke = false, lastLoud = performance.now();
  const t0 = performance.now(), maxMs = ((state.voice && state.voice.max_record_s) || 6) * 1000;
  try {
    srcNode = audio.ctx.createMediaStreamSource(stream);
    analyser = audio.ctx.createAnalyser();
    analyser.fftSize = 1024;
    srcNode.connect(analyser);
  } catch (e) { analyser = null; }
  const buf = new Float32Array(1024);
  const finish = () => { if (rec.state !== "inactive") rec.stop(); };
  timer = setInterval(() => {
    const now = performance.now();
    if (now - t0 > maxMs) return finish();
    if (!analyser) return;
    analyser.getFloatTimeDomainData(buf);
    let e = 0; for (const x of buf) e += x * x;
    const rms = Math.sqrt(e / buf.length);
    if (rms > 0.03) { spoke = true; lastLoud = now; }
    if (spoke && now - lastLoud > 900) finish();
    if (!spoke && now - t0 > 4000) finish();
  }, 50);
  rec.onstop = async () => {
    clearInterval(timer);
    try { if (srcNode) srcNode.disconnect(); } catch (e) { /* déjà déconnecté */ }
    stream.getTracks().forEach((t) => t.stop()); // micro coupé tout de suite
    setListening(null);
    audio.recording(false);
    const blob = new Blob(chunks, { type: rec.mimeType || mime || "audio/mp4" });
    if (!blob.size) { ui.heard.textContent = "Rien entendu"; return; }
    ui.heard.textContent = "Je réfléchis…";
    const b64 = await blobToBase64(blob);
    send({ type: "command_audio", mime: blob.type, data: b64 });
  };
  setListening({ rec, stop: finish });
  audio.beep();
  rec.start();
}

// Raison lisible d'un refus du micro, avec où le réautoriser selon le navigateur.
function isIOS() {
  const ua = navigator.userAgent;
  return /iPhone|iPad|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

function micError(e) {
  const ua = navigator.userAgent;
  const ios = isIOS();
  const where = ios
    ? "Réglages → Safari → Micro → Demander, puis recharge la page"
    : /Android/.test(ua)
      ? "touche le cadenas à côté de l'adresse → Autorisations → Micro, puis recharge la page"
      : "autorise le micro pour ce site (icône à côté de l'adresse), puis recharge la page";
  return {
    NotAllowedError: "accès refusé (" + where + ")",
    SecurityError: "accès refusé (" + where + ")",
    NotFoundError: "aucun micro trouvé",
    NotReadableError: "micro déjà utilisé par une autre application",
    AbortError: "micro indisponible pour l'instant, réessaie",
  }[e.name] || e.message || String(e);
}

function stopListening(abort) {
  const l = state.listening;
  if (!l) return;
  try { if (abort && l.rec && l.rec.abort) l.rec.abort(); else l.stop(); } catch (e) { /* déjà arrêté */ }
  if (abort) setListening(null);
}

function blobToBase64(blob) {
  return new Promise((res) => {
    const r = new FileReader();
    r.onload = () => res(String(r.result).split(",")[1] || "");
    r.readAsDataURL(blob);
  });
}

function sendTyped() {
  const text = ui.typed.value.trim();
  if (!text) return;
  send({ type: "command", text, source: "clavier" });
  ui.heard.textContent = `Envoyé : « ${text} »`;
  ui.typed.value = "";
}

// ------------------------------------------------------------------ boutons
ui.start.addEventListener("click", start);
ui.talk.addEventListener("click", talk);
ui.waitCore.addEventListener("click", () => {
  audio.unlock();
  audio.cancelSpeech();
  audio.speak(waitMessage(), false);
});
ui.guideTalk.addEventListener("click", talk);
ui.stopGuide.addEventListener("click", () => {
  audio.unlock();
  audio.cancelSpeech();
  send({ type: "command", text: "stop", source: "bouton" });
});
ui.sendTyped.addEventListener("click", sendTyped);
ui.typed.addEventListener("keydown", (e) => { if (e.key === "Enter") sendTyped(); });
ui.stop.addEventListener("click", stop);
ui.capture.addEventListener("click", () => {
  if (!ui.calibMode.checked) { log("Activez d'abord le mode calibration."); return; }
  if (!state.busy) sendFrame(nowS(), true);
});
function showVolume() {
  const v = +ui.volume.value;
  ui.volumeOut.textContent = `${v > 0 ? "+" : ""}${v} dB`;
}
ui.volume.value = String(audio.userDb);
showVolume();
ui.volume.addEventListener("input", () => { audio.setVolume(+ui.volume.value); showVolume(); });
ui.testSound.addEventListener("click", () => {
  audio.unlock();
  if (audio.test()) log("Test du son : gauche, droite, puis devant.");
});
ui.sendNotes.addEventListener("click", () => {
  send({ type: "notes", text: ui.notes.value });
  log("Notes envoyées.");
});
if (!window.isSecureContext) {
  setStatus("Page non sécurisée : ouvrez l'adresse en https://", "err");
}

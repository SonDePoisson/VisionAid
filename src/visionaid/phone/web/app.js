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
  voiceBox: $("voiceBox"), talk: $("talk"), heard: $("heard"), typed: $("typed"), sendTyped: $("sendTyped"),
};
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
};

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

// ------------------------------------------------------------------ démarrage
async function start() {
  if (!window.isSecureContext) {
    setStatus("Page non sécurisée : ouvrez l'adresse en https:// (certificat à installer, voir le PC).", "err");
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    setStatus("Caméra inaccessible dans ce navigateur.", "err");
    return;
  }
  ui.start.disabled = true;
  state.greeted = false;
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
    state.stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: {
        facingMode: { ideal: "environment" },
        // 4:3 (champ complet du capteur) ; le navigateur tourne l'image selon l'orientation
        width: { ideal: cfg.capture_width }, height: { ideal: cfg.capture_height },
        frameRate: { ideal: 30 },
      },
    });
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
  ui.video.srcObject = state.stream;
  await ui.video.play().catch(() => {});
  await new Promise((res) => (ui.video.videoWidth ? res() : ui.video.addEventListener("loadedmetadata", res, { once: true })));

  await requestWakeLock();
  document.addEventListener("visibilitychange", onVisibility);

  state.running = true;
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
  setStatus("Arrêté.", "");
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
  setStatus("Connexion au PC…", "warn");
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
      audio.configure(m.audio).then(() => { ui.testSound.disabled = !audio.ready; });
      onVoiceSettings(m.voice);
    } else if (m.type === "sound") {
      audio.onSound(m);
    } else if (m.type === "speech") {
      if (!state.spokenIds.has(m.id)) {
        state.spokenIds.add(m.id);
        log("Voix : " + m.text);
        if (!state.voice || state.voice.tts !== false) audio.speak(m.text, !!m.duck);
      }
    } else if (m.type === "heard") {
      ui.heard.textContent = m.text ? `Compris : « ${m.text} »` : "Rien entendu";
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
  ui.bubble.style.background = ok ? "var(--ok)" : "var(--warn)";
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
  ui.voiceBox.hidden = !stt;
  ui.talk.disabled = !stt;
  if (!state.greeted && v) {
    state.greeted = true;
    if (stt) audio.speak("Appuie sur le grand bouton Parler, puis dis ce que tu cherches.", false);
  }
}

function talk() {
  audio.unlock();
  if (state.listening) { stopListening(false); return; }
  audio.cancelSpeech();
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (state.voice && state.voice.stt === "phone" && SR) recognize(SR);
  else record();
}

function setListening(obj) {
  state.listening = obj;
  ui.talk.classList.toggle("listening", !!obj);
  ui.talk.textContent = obj ? "⏹ J'écoute… (appuie pour finir)" : "🎤 Parler";
}

function recognize(SR) {
  const r = new SR();
  r.lang = (state.voice && state.voice.lang) || "fr-FR";
  r.interimResults = false;
  r.maxAlternatives = 3;
  let done = false;
  r.onresult = (e) => {
    done = true;
    const alts = Array.from(e.results[0] || []).map((a) => a.transcript);
    ui.heard.textContent = `Entendu : « ${alts[0] || ""} »`;
    send({ type: "command", text: alts[0] || "", alternatives: alts.slice(1), source: "safari" });
  };
  r.onerror = (e) => {
    log("Reconnaissance de Safari : " + e.error + " → enregistrement envoyé au PC");
    done = true;
    setListening(null);
    if (e.error !== "aborted") record();
  };
  r.onend = () => { if (state.listening && state.listening.rec === r) setListening(null); if (!done) ui.heard.textContent = "Rien entendu"; audio.resume(); };
  setListening({ rec: r, stop: () => r.stop() });
  audio.beep();
  r.start();
}

async function record() {
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  } catch (e) {
    ui.heard.textContent = "Micro refusé (Réglages → Safari → Micro)";
    log("Micro : " + e);
    return;
  }
  const types = ["audio/mp4", "audio/webm;codecs=opus", "audio/webm", "audio/ogg"];
  const mime = types.find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || "";
  let rec;
  try { rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined); } catch (e) {
    stream.getTracks().forEach((t) => t.stop());
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
    audio.resume();
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

// VisionAId — rendu sonore du guidage sur le téléphone (Web Audio, spatialisation HRTF).
// Le PC décide quoi jouer (messages « sound », voir docs/protocol.md) ; ce fichier ne fait que
// l'exécuter : son d'exploration (objet pas encore trouvé), note du guide répétée et
// spatialisée (objet trouvé), alerte grave, son d'arrivée.
// Même rendu que le banc d'écoute ; logique commune côté PC dans visionaid/audio/director.py.
"use strict";

class GuideAudio {
  constructor() {
    this.ctx = null;
    this.cfg = null;
    this.buffers = {};
    this.ready = false;
    this.active = false; // guidage en cours (bouton Démarrer)
    this.cmd = null; // dernière consigne reçue
    this.lastMsg = 0; // performance.now() de la dernière consigne
    this.prevMode = "silent";
    this.next = 0; // prochaine note du guide (temps audio)
    this.alertNext = 0;
    this.timer = null;
    this.userDb = 0;
    this.onStatus = () => {};
    try { this.userDb = +(localStorage.getItem("visionaid.volume_db") || 0); } catch (e) { /* stockage indisponible */ }
  }

  // À appeler DANS le geste de l'utilisateur (bouton) : iOS n'autorise le son qu'ainsi.
  unlock() {
    if (!this.ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) { this.onStatus("Son indisponible dans ce navigateur", "err"); return; }
      this.ctx = new AC();
      // iOS ≥ 16.4 : joue même quand le bouton silencieux est activé
      try { if (navigator.audioSession) navigator.audioSession.type = "playback"; } catch (e) { /* ancien iOS */ }
      const c = this.ctx;
      this.master = c.createGain();
      this.master.connect(c.destination);
      // halo : réverbération légère, mono et sans graves (ne déplace pas la direction)
      this.haloIn = c.createGain();
      const hp = c.createBiquadFilter();
      hp.type = "highpass"; hp.frequency.value = 700;
      this.conv = c.createConvolver();
      this.conv.normalize = true;
      this.conv.buffer = this._haloIR();
      this.haloIn.connect(hp); hp.connect(this.conv); this.conv.connect(this.master);
      // chaîne spatialisée persistante : passe-bas (derrière) → HRTF → gain (derrière)
      this.lp = c.createBiquadFilter();
      this.lp.type = "lowpass"; this.lp.Q.value = 0.5; this.lp.frequency.value = 20000;
      this.pan = c.createPanner();
      this.pan.panningModel = "HRTF"; this.pan.distanceModel = "linear";
      this.pan.refDistance = 1; this.pan.maxDistance = 10000; this.pan.rolloffFactor = 0;
      this.backGain = c.createGain();
      this.lp.connect(this.pan); this.pan.connect(this.backGain); this.backGain.connect(this.master);
      this.lp.connect(this.haloIn);
      this._setPos(0, true);
    }
    this.ctx.resume();
    // tampon silencieux : finit de déverrouiller la sortie audio sur iOS
    const b = this.ctx.createBuffer(1, 1, this.ctx.sampleRate), s = this.ctx.createBufferSource();
    s.buffer = b; s.connect(this.ctx.destination); s.start();
  }

  // Réglages du PC (message « welcome ») : charge les sons.
  async configure(a) {
    if (!a) { this.onStatus("Le PC n'a pas envoyé de sons", "warn"); return; }
    if (!this.ctx) return;
    this.cfg = a;
    this.pan.panningModel = a.panning || "HRTF";
    this.haloIn.gain.value = a.halo_mix ?? 0.14;
    this._applyVolume();
    try {
      await Promise.all(Object.entries(a.sounds).map(async ([k, url]) => {
        if (this.buffers[k] && this.buffers[k].url === url) return;
        const r = await fetch(url);
        if (!r.ok) throw new Error(`${url} : ${r.status}`);
        const ab = await r.arrayBuffer();
        const buf = await new Promise((res, rej) => this.ctx.decodeAudioData(ab, res, rej));
        buf.url = url;
        this.buffers[k] = buf;
      }));
      this.ready = true;
      this.onStatus("Son prêt", "ok");
      if (!this.timer) this.timer = setInterval(() => this._tick(), 25);
    } catch (e) {
      this.onStatus("Sons introuvables : " + (e.message || e), "err");
    }
  }

  start() { this.active = true; this.cmd = null; this.lastMsg = 0; this.prevMode = "silent"; }
  stop() { this.active = false; this.cmd = null; this.prevMode = "silent"; }

  // Consigne du PC (~20 par seconde).
  onSound(m) {
    this.cmd = m;
    this.lastMsg = performance.now();
    if (!this.ready) return;
    if (m.event === "arrived") this._play("arrived", this.master, this.ctx.currentTime + 0.02);
    if (m.mode === "guide" || m.mode === "search") this._setPos(m.az, false, m.lowpass_hz, m.back_gain_db);
  }

  setVolume(db) {
    this.userDb = db;
    try { localStorage.setItem("visionaid.volume_db", String(db)); } catch (e) { /* stockage indisponible */ }
    this._applyVolume();
  }

  // Vérification du casque : gauche, droite, devant.
  test() {
    if (!this.ready) return false;
    const t = this.ctx.currentTime + 0.05;
    [[Math.PI / 2, 0], [-Math.PI / 2, 1.0], [0, 2.0]].forEach(([az, dt]) => {
      this._setPos(az, t + dt);
      this._playGuide(t + dt + 0.01, 0);
    });
    return true;
  }

  // ---------------------------------------------------------------- interne
  _applyVolume() {
    if (!this.master) return;
    const db = (this.cfg ? this.cfg.master_gain_db : 0) + this.userDb;
    this.master.gain.setTargetAtTime(Math.pow(10, db / 20), this.ctx.currentTime, 0.05);
  }

  // `at` : false = transition lissée maintenant, true = saut immédiat, nombre = saut à cet instant audio
  _setPos(az, at, lowpass = 20000, backDb = 0) {
    const c = this.ctx, tau = this.cfg ? this.cfg.smoothing_s : 0.05;
    const x = -Math.sin(az), z = -Math.cos(az); // auditeur vers −z, droite = +x ; azimut positif à gauche
    const set = (p, v) => {
      if (typeof at === "number") p.setValueAtTime(v, at);
      else if (at) { p.cancelScheduledValues(c.currentTime); p.setValueAtTime(v, c.currentTime); }
      else p.setTargetAtTime(v, c.currentTime, tau);
    };
    if (this.pan.positionX) { set(this.pan.positionX, x); set(this.pan.positionY, 0); set(this.pan.positionZ, z); }
    else this.pan.setPosition(x, 0, z);
    set(this.lp.frequency, lowpass);
    set(this.backGain.gain, Math.pow(10, backDb / 20));
  }

  _play(key, dest, when, extraDb = 0, maxDur = Infinity, fades = null) {
    const buf = this.buffers[key];
    if (!buf) return;
    const c = this.ctx, src = c.createBufferSource(), env = c.createGain();
    src.buffer = buf;
    const v = Math.pow(10, ((this.cfg.gains_db[key] || 0) + extraDb) / 20);
    const d = Math.min(buf.duration, maxDur);
    const fin = fades ? Math.min(fades[0], d / 3) : 0;
    const fout = Math.min(fades ? fades[1] : 0.12, d / 2);
    if (fin > 0) { env.gain.setValueAtTime(0, when); env.gain.linearRampToValueAtTime(v, when + fin); }
    else env.gain.setValueAtTime(v, when);
    if (d < buf.duration || fades) {
      env.gain.setValueAtTime(v, when + d - fout);
      env.gain.setTargetAtTime(0, when + d - fout, fout / 5); // extinction exponentielle
    }
    src.connect(env); env.connect(dest);
    src.start(when); src.stop(when + d + 0.05);
    src.onended = () => { src.disconnect(); env.disconnect(); };
  }

  _playGuide(when, extraDb) {
    const a = this.cfg;
    const dur = a.guide_notes >= 5 ? Infinity : a.guide_notes * a.guide_note_s;
    this._play("guide", this.lp, when, extraDb, dur, [a.fade_in_s, a.fade_out_s]);
  }

  // exploration : le son « search » entier (timbre distinct du guide), courts fondus
  _playSearch(when, extraDb) {
    this._play("search", this.lp, when, extraDb, Infinity, [0.01, 0.15]);
  }

  _tick() {
    if (!this.ready || !this.active) return;
    const now = this.ctx.currentTime;
    let mode = this.cmd ? this.cmd.mode : "silent";
    // plus de consigne du PC (Wi-Fi coupé, PC arrêté) : « arrête-toi » plutôt qu'un guide figé
    if (this.lastMsg > 0 && performance.now() - this.lastMsg > this.cfg.watchdog_s * 1000) mode = "alert";
    const pulsing = (m) => m === "guide" || m === "search";
    if (pulsing(mode)) {
      // nouveau rythme dès le passage recherche ↔ guidage
      if (!pulsing(this.prevMode) || mode !== this.prevMode || this.next < now) this.next = now + 0.02;
      const search = mode === "search" && this.buffers.search;
      while (this.next < now + 0.1) {
        if (search) this._playSearch(this.next, this.cmd.gain_db || 0);
        else this._playGuide(this.next, this.cmd.gain_db || 0);
        this.next += Math.max(0.2, this.cmd.interval || 1);
      }
    }
    if (mode === "alert") {
      if (this.prevMode !== "alert") this.alertNext = now + 0.02;
      while (this.alertNext < now + 0.1) {
        this._play("alert", this.master, this.alertNext);
        this.alertNext += this.cfg.alert_period_s;
      }
    }
    this.prevMode = mode;
  }

  // réponse impulsionnelle synthétique : bruit décroissant (~0,9 s), aigus amortis, mono
  _haloIR() {
    const c = this.ctx, n = Math.round(c.sampleRate * 0.9), ir = c.createBuffer(1, n, c.sampleRate);
    const d = ir.getChannelData(0);
    let lp = 0;
    for (let i = 0; i < n; i++) {
      const t = i / c.sampleRate;
      lp += 0.25 * ((Math.random() * 2 - 1) - lp);
      d[i] = lp * Math.exp(-t / 0.25) * Math.min(1, t / 0.01);
    }
    return ir;
  }
}

window.guideAudio = new GuideAudio();

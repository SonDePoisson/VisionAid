// VisionAId — rendu sonore du guidage sur le téléphone (Web Audio).
// Le PC décide quoi jouer (messages « sound », voir docs/protocol.md) ; ce fichier ne fait que
// l'exécuter, à l'identique du rendu hors ligne (visionaid/audio/renderer.py) :
// - chemin : note répétée (son 2, ou son 4 en recherche), placée par un pan stéréo
//   (StereoPannerNode, puissance constante : pan −1 = tout à gauche, rien à droite) ;
// - obstacles : nappe du son 1 en boucle, superposée, volume selon la distance ;
// - arrivée : son 3, une fois ;
// - phrases (messages « speech ») : synthèse vocale du navigateur (speechSynthesis) ; pendant une
//   phrase « duck » (objet trouvé), la couche chemin est suspendue, les obstacles restent.
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
    this.next = 0; // prochaine note du chemin (temps audio)
    this.loop = null; // source en boucle de la nappe des obstacles
    this.timer = null;
    this.userDb = 0;
    this.onStatus = () => {};
    this.voiceLang = "fr-FR";
    this.voiceRate = 1;
    this.duckUntil = 0; // performance.now() : couche chemin suspendue jusqu'à cet instant
    this.speaking = 0; // phrases « duck » en cours
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
      // couche chemin : notes → pan stéréo → sortie
      this.pan = c.createStereoPanner();
      this.pan.connect(this.master);
      // couche obstacles : nappe en boucle → gain variable → sortie
      this.obGain = c.createGain();
      this.obGain.gain.value = 0;
      this.obGain.connect(this.master);
    }
    this.ctx.resume();
    // iOS : la synthèse vocale aussi se déverrouille dans un geste de l'utilisateur
    try {
      if (!this.speechUnlocked && window.speechSynthesis) {
        const u = new SpeechSynthesisUtterance(" ");
        u.volume = 0;
        window.speechSynthesis.speak(u);
        this.speechUnlocked = true;
      }
    } catch (e) { /* pas de synthèse vocale */ }
    // tampon silencieux : finit de déverrouiller la sortie audio sur iOS
    const b = this.ctx.createBuffer(1, 1, this.ctx.sampleRate), s = this.ctx.createBufferSource();
    s.buffer = b; s.connect(this.ctx.destination); s.start();
  }

  // Réglages du PC (message « welcome ») : charge les sons.
  async configure(a) {
    if (!a) { this.onStatus("Le PC n'a pas envoyé de sons", "warn"); return; }
    if (!this.ctx) return;
    this.cfg = a;
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

  start() {
    this.active = true; this.cmd = null; this.lastMsg = 0; this.prevMode = "silent";
    this._startLoop();
  }

  stop() {
    this.active = false; this.cmd = null; this.prevMode = "silent";
    if (this.obGain) this._setObstacle(-120, 0.05);
    if (this.loop) { try { this.loop.stop(this.ctx.currentTime + 0.3); } catch (e) { /* déjà arrêtée */ } this.loop = null; }
  }

  // Consigne du PC (~20 par seconde).
  onSound(m) {
    this.cmd = m;
    this.lastMsg = performance.now();
    if (!this.ready) return;
    if (m.event === "arrived") this._play("arrived", this.master, this.ctx.currentTime + 0.02);
    if (m.mode === "guide" || m.mode === "search") this._setPan(m.pan || 0, false);
    this._setObstacle(m.obstacle_db ?? -120);
  }

  resume() { if (this.ctx) this.ctx.resume(); }

  // Phrase dite dans le casque. `duck` : chemin suspendu jusqu'à la fin de la phrase.
  speak(text, duck) {
    const ss = window.speechSynthesis;
    if (!ss || !text) return;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = this.voiceLang || "fr-FR";
    u.rate = this.voiceRate || 1;
    const voices = ss.getVoices ? ss.getVoices() : [];
    const lang = u.lang.toLowerCase();
    const v = voices.find((x) => x.lang && x.lang.toLowerCase() === lang && x.localService)
      || voices.find((x) => x.lang && x.lang.toLowerCase().startsWith(lang.slice(0, 2)));
    if (v) u.voice = v;
    if (duck) {
      this.speaking += 1;
      // garde-fou : jamais plus que la durée probable de la phrase (≈ 14 caractères/s) + 3 s
      this.duckUntil = Math.max(this.duckUntil, performance.now() + (text.length / 14) * 1000 / u.rate + 3000);
      const end = () => {
        this.speaking = Math.max(0, this.speaking - 1);
        if (!this.speaking) this.duckUntil = performance.now() + 300;
      };
      u.onend = end; u.onerror = end;
    }
    this.resume();
    ss.speak(u); // à la suite des phrases déjà en cours
  }

  cancelSpeech() {
    try { if (window.speechSynthesis) window.speechSynthesis.cancel(); } catch (e) { /* rien */ }
    this.speaking = 0; this.duckUntil = 0;
  }

  // Bip court : « parle maintenant ».
  beep() {
    if (!this.ctx) return;
    const c = this.ctx, o = c.createOscillator(), g = c.createGain(), t = c.currentTime + 0.01;
    o.frequency.value = 880;
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(0.25, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.001, t + 0.18);
    o.connect(g); g.connect(this.master || c.destination);
    o.start(t); o.stop(t + 0.2);
    o.onended = () => { o.disconnect(); g.disconnect(); };
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
    [[-1, 0], [1, 1.0], [0, 2.0]].forEach(([p, dt]) => {
      this._setPan(p, t + dt);
      this._play("guide", this.pan, t + dt + 0.01);
    });
    return true;
  }

  // ---------------------------------------------------------------- interne
  _applyVolume() {
    if (!this.master) return;
    const db = (this.cfg ? this.cfg.master_gain_db : 0) + this.userDb;
    this.master.gain.setTargetAtTime(Math.pow(10, db / 20), this.ctx.currentTime, 0.05);
  }

  // `at` : false = transition lissée maintenant, nombre = saut à cet instant audio
  _setPan(p, at) {
    const c = this.ctx, tau = this.cfg ? this.cfg.smoothing_s : 0.05;
    const v = Math.max(-1, Math.min(1, p));
    if (typeof at === "number") this.pan.pan.setValueAtTime(v, at);
    else this.pan.pan.setTargetAtTime(v, c.currentTime, tau);
  }

  _setObstacle(db, tau) {
    const t = tau ?? (this.cfg ? this.cfg.obstacle_smoothing_s : 0.3);
    const g = db <= -120 ? 0 : Math.pow(10, db / 20);
    this.obGain.gain.setTargetAtTime(g, this.ctx.currentTime, t);
  }

  _startLoop() {
    if (!this.ready || this.loop || !this.buffers.obstacle) return;
    const c = this.ctx, src = c.createBufferSource(), env = c.createGain();
    src.buffer = this.buffers.obstacle;
    src.loop = true; // fichier préparé bouclable sans couture
    env.gain.value = Math.pow(10, (this.cfg.gains_db.obstacle || 0) / 20);
    src.connect(env); env.connect(this.obGain);
    src.start(c.currentTime + 0.02);
    src.onended = () => { src.disconnect(); env.disconnect(); };
    this.loop = src;
  }

  _play(key, dest, when) {
    const buf = this.buffers[key];
    if (!buf) return;
    const c = this.ctx, src = c.createBufferSource(), env = c.createGain();
    src.buffer = buf;
    env.gain.value = Math.pow(10, (this.cfg.gains_db[key] || 0) / 20);
    src.connect(env); env.connect(dest);
    src.start(when);
    src.onended = () => { src.disconnect(); env.disconnect(); };
  }

  _tick() {
    if (!this.ready || !this.active) return;
    if (!this.loop) this._startLoop(); // sons chargés après Démarrer
    const now = this.ctx.currentTime;
    let mode = this.cmd ? this.cmd.mode : "silent";
    // plus de consigne du PC (Wi-Fi coupé, PC arrêté) : « arrête-toi » plutôt qu'un guide figé
    if (this.lastMsg > 0 && performance.now() - this.lastMsg > this.cfg.watchdog_s * 1000) {
      mode = "lost";
      if (this.prevMode !== "lost") this._setObstacle(this.cfg.lost_obstacle_db);
    }
    const ducked = performance.now() < this.duckUntil;
    if ((mode === "guide" || mode === "search") && !ducked) {
      // nouveau rythme dès le passage recherche ↔ chemin
      if (mode !== this.prevMode || this.next < now) this.next = now + 0.02;
      const key = mode === "search" && this.buffers.search ? "search" : "guide";
      while (this.next < now + 0.1) {
        this._play(key, this.pan, this.next);
        this.next += Math.max(0.2, this.cmd.interval || 1);
      }
    }
    this.prevMode = ducked ? "silent" : mode; // fin de phrase : le rythme repart aussitôt
  }
}

window.guideAudio = new GuideAudio();

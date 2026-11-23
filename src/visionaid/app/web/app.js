// VisionAId — interface de l'ordinateur. Lit l'état (/api/state) quatre fois par seconde et
// envoie les actions (/api/action). JavaScript pur, sans dépendance.
"use strict";

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

const SOUNDS = [
  ["general", "Volume général", "Tous les sons et la voix ensemble"],
  ["chemin", "Chemin", "Le son à suivre pour aller vers l'objet"],
  ["obstacles", "Obstacles", "Prévient quand un obstacle est proche"],
  ["recherche", "Recherche", "Pendant que VisionAId cherche l'objet"],
  ["arrivee", "Arrivée", "L'objet est à portée de main"],
  ["voix", "Voix des annonces", "Les phrases dites dans le casque"],
];
const VOLUME_DEFAULTS = { general: 80, chemin: 70, obstacles: 60, recherche: 50, arrivee: 70, voix: 80 };
const PHASES = ["ecoute", "recherche", "trouve", "route", "arrivee"];

const ui = {
  tab: "home", // onglet choisi : home | sounds | help | advanced
  overlay: null, // écran ouvert depuis l'accueil : phone | headset
  setupStep: "phone", // mise en route : phone | headset
  state: null,
  volumeTimer: null,
  lastQrUrl: "",
  shownView: "",
};

async function api(name, args) {
  try {
    const r = await fetch("/api/action", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, args: args || {} }),
    });
    return await r.json();
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

// ------------------------------------------------------------------ choix de l'écran
function currentView(st) {
  if (!st.prepared) return "prep";
  if (!st.settings.setup_done) return ui.setupStep;
  if (st.guiding) return "guide";
  if (ui.overlay) return ui.overlay;
  return ui.tab;
}

function showView(v) {
  if (ui.shownView === v) return;
  ui.shownView = v;
  $$("[data-view]").forEach((s) => { s.hidden = s.dataset.view !== v; });
  const setup = !ui.state.settings.setup_done && (v === "phone" || v === "headset");
  $("#setupSteps").hidden = !(v === "prep" || setup);
  $("#nav").hidden = v === "prep" || setup || v === "guide";
  $("#livePill").hidden = v !== "guide";
  $$("#nav a").forEach((a) => {
    if (a.dataset.tab === ui.tab && !ui.overlay) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  const titles = { prep: "Préparation", phone: "Connecter le téléphone", headset: "Tester le casque", home: "Accueil",
    guide: "Guidage en cours", sounds: "Les sons", advanced: "Mode avancé", help: "Aide" };
  document.title = `VisionAId – ${titles[v] || ""}`;
  const h1 = document.querySelector(`[data-view="${v}"] h1`);
  if (h1) { h1.setAttribute("tabindex", "-1"); h1.focus({ preventScroll: true }); }
  if (v === "sounds") renderSounds();
}

// ------------------------------------------------------------------ rendu
function render(st) {
  ui.state = st;
  const v = currentView(st);
  showView(v);
  renderSteps(v, st);
  renderEngine(st);
  if (v === "prep") renderPrep(st.prepare);
  if (v === "phone") renderPhone(st);
  if (v === "home") renderHome(st);
  if (v === "guide") renderGuide(st);
  if (v === "advanced") renderAdvanced(st);
}

function renderSteps(v, st) {
  const n = v === "prep" ? 1 : v === "phone" ? 2 : 3;
  $("#stepText").textContent = `Étape ${n} sur 3`;
  $$("#setupSteps .bars span").forEach((b, i) => b.classList.toggle("on", i < n));
}

function renderEngine(st) {
  const b = $("#engineBanner");
  const show = st.prepared && st.engine === "error";
  b.hidden = !show;
  if (show) $("#engineText").textContent = `Le guidage ne démarre pas : ${st.engine_error || "erreur inconnue"}.`;
}

function renderPrep(p) {
  $("#prepPct").textContent = `${p.percent} %`;
  $("#prepRing").setAttribute("aria-valuenow", String(p.percent));
  $("#prepRing").style.background = `conic-gradient(#f2a541 ${p.percent}%, #e9dfcb 0)`;
  $("#prepLeft").textContent = p.minutes_left ? `environ ${p.minutes_left} min` : (p.status === "running" ? "calcul du temps…" : "");
  const box = $("#prepSteps");
  box.innerHTML = "";
  for (const s of p.steps) {
    const li = document.createElement("li");
    const dot = document.createElement("span");
    dot.className = "dot " + ({ done: "done", running: "run", error: "err", pending: "todo" }[s.state] || "todo");
    dot.setAttribute("aria-hidden", "true");
    if (s.state === "done") dot.innerHTML = '<svg width="18" height="18"><use href="#check"></use></svg>';
    const t = document.createElement("span");
    const more = { done: " · terminé", running: ` · ${p.downloaded_gb.toLocaleString("fr-FR")} Go téléchargés`, error: " · échec", pending: "" }[s.state];
    t.textContent = s.label + (more || "");
    if (s.state === "pending") t.className = "muted";
    li.append(dot, t);
    box.append(li);
  }
  $("#prepError").hidden = p.status !== "error";
  $("#prepErrorText").textContent = "La préparation s'est arrêtée. Vérifiez la connexion à Internet, puis réessayez." +
    (p.error ? ` (${p.error.slice(0, 160)})` : "");
}

function renderPhone(st) {
  const urls = st.phone.urls || [];
  const url = urls[0] || "";
  if (url && url !== ui.lastQrUrl) {
    ui.lastQrUrl = url;
    $("#qr").src = "/api/qr.svg?text=" + encodeURIComponent(url);
  }
  $("#phoneUrl").textContent = urls.slice(0, 2).join("  ou  ");
  const on = st.phone.connected;
  const s = $("#phoneStatus");
  s.textContent = st.engine === "starting" ? "VisionAId démarre…" : on ? "Téléphone connecté" : "En attente du téléphone…";
  s.classList.toggle("ok", on);
  $("#phoneRing").classList.toggle("ok", on);
  const next = $("#phoneNext");
  next.classList.toggle("off", !on);
  next.setAttribute("aria-disabled", on ? "false" : "true");
  next.textContent = st.settings.setup_done ? "Terminé" : "Continuer";
  $("#phoneBack").hidden = !st.settings.setup_done;
}

function setCheck(li, ok, text) {
  const dot = li.querySelector(".dot");
  dot.className = "dot " + (ok ? "done" : "todo");
  dot.innerHTML = ok ? '<svg width="18" height="18"><use href="#check"></use></svg>' : "";
  li.querySelector("span:last-child").textContent = text;
}

function renderHome(st) {
  const s = st.settings;
  const phoneOk = st.phone.connected;
  setCheck($("#chkPhone"), phoneOk, phoneOk ? "Téléphone connecté" : st.engine === "starting" ? "VisionAId démarre…" : "Téléphone non connecté");
  setCheck($("#chkHeadset"), st.headset_today, st.headset_today ? "Casque testé aujourd'hui" : "Casque à tester");
  $("#homeTitle").textContent = phoneOk ? "Tout est prêt." : "Presque prêt.";
  const start = $("#startBtn");
  start.disabled = !phoneOk;
  start.setAttribute("aria-label", phoneOk ? "Démarrer le guidage" : "Démarrer le guidage : connectez d'abord le téléphone");
  const voice = s.mode === "voice";
  $("#modeVoice").classList.toggle("on", voice);
  $("#modeHere").classList.toggle("on", !voice);
  $("#modeVoice input").checked = voice;
  $("#modeHere input").checked = !voice;
  $("#voiceHint").hidden = !voice;
  $("#objects").hidden = voice;
  $$("#objects button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.object === s.object)));
}

function renderGuide(st) {
  const g = st.guide;
  const m = Math.floor(st.elapsed_s / 60), sec = st.elapsed_s % 60;
  $("#livePill").textContent = `Guidage en cours · ${m ? m + " min " : ""}${String(sec).padStart(m ? 2 : 1, "0")}${m ? "" : " s"}`;
  const idx = PHASES.indexOf(g.phase);
  $$("#phases li").forEach((li, i) => {
    li.classList.toggle("past", idx >= 0 && i < idx);
    if (i === idx) li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current");
  });
  setText("#gTitle", g.title);
  setText("#gDetail", g.detail);
  setText("#gBig", g.big);
  $("#gBig").classList.toggle("word", !/\d/.test(g.big));
  setText("#gSmall", g.small);
  setText("#gHeard", g.heard ? `« ${g.heard} »` : "—");
  setText("#gSpeech", g.last_speech ? `« ${g.last_speech} »` : "—");
  const dot = $("#dirDot");
  if (g.angle_deg === null || g.angle_deg === undefined) dot.style.opacity = "0";
  else { dot.style.opacity = "1"; dot.style.transform = `rotate(${g.angle_deg}deg)`; }
}

function setText(sel, text) {
  const el = $(sel);
  if (el.textContent !== text) el.textContent = text;
}

function renderSounds() {
  const st = ui.state;
  const vols = st.settings.volumes;
  const box = $("#soundRows");
  if (!box.children.length) {
    for (const [key, name, desc] of SOUNDS) {
      const li = document.createElement("li");
      li.innerHTML = `<div class="name"><label for="vol-${key}">${name}</label><span>${desc}</span></div>
        <div class="ctl"><input id="vol-${key}" type="range" min="0" max="100" step="5" data-vol="${key}">
        <output for="vol-${key}"></output>
        <button type="button" class="play" data-preview="${key}" aria-label="Écouter : ${name}">
        <svg width="22" height="22"><use href="#play"></use></svg></button></div>`;
      box.append(li);
    }
  }
  for (const [key] of SOUNDS) {
    const input = $(`#vol-${key}`);
    if (document.activeElement !== input) input.value = vols[key];
    showVolume(input);
  }
}

function showVolume(input) {
  const v = `${input.value} %`;
  input.nextElementSibling.textContent = v;
  input.setAttribute("aria-valuetext", v);
}

function renderAdvanced(st) {
  const s = st.settings;
  $$("[data-setting]").forEach((b) => b.setAttribute("aria-checked", String(!!s[b.dataset.setting])));
  $("#advLabel").textContent = s.advanced ? "Activé" : "Désactivé";
  $("#advBody").hidden = !s.advanced;
}

// ------------------------------------------------------------------ actions
async function onAction(name, el) {
  const st = ui.state;
  switch (name) {
    case "start": {
      if (!st.phone.connected) return;
      await api("start", { mode: st.settings.mode, object: st.settings.object });
      break;
    }
    case "stop": await api("stop"); break;
    case "test_sound": {
      await api("test_sound");
      playTestAnimation();
      break;
    }
    case "headset-ok": {
      await api("headset_ok");
      if (!st.settings.setup_done) await api("setup_done");
      ui.overlay = null; ui.tab = "home";
      break;
    }
    case "headset-help": {
      const help = $("#headsetHelp");
      help.hidden = !help.hidden;
      el.setAttribute("aria-expanded", String(!help.hidden));
      break;
    }
    case "phone-next": {
      if (!st.phone.connected) return;
      if (st.settings.setup_done) ui.overlay = null;
      else ui.setupStep = "headset";
      break;
    }
    case "back": {
      if (!st.settings.setup_done) ui.setupStep = "phone";
      else ui.overlay = null;
      break;
    }
    case "go-phone": ui.overlay = "phone"; break;
    case "go-headset": ui.overlay = "headset"; break;
    case "ask-quit": $("#quitModal").hidden = false; $("#quitModal .btn.ghost").focus(); return;
    case "cancel-quit": $("#quitModal").hidden = true; return;
    case "quit": {
      $("#quitModal").hidden = true;
      await api("quit");
      ui.closed = true;
      $("#closedModal").hidden = false;
      return;
    }
    case "reset-volumes": {
      await api("settings", { volumes: VOLUME_DEFAULTS });
      ui.state.settings.volumes = { ...VOLUME_DEFAULTS };
      renderSounds();
      $("#soundSaved").textContent = "Réglages d'origine rétablis.";
      return;
    }
    case "copy-report": await copyReport(); return;
    case "open_sessions": await api("open_sessions"); return;
    case "retry_prepare": await api("retry_prepare"); break;
    case "restart_engine": await api("restart_engine"); $("#restartNote").hidden = true; break;
    default: return;
  }
  ui.shownView = "";
  await refresh();
}

function playTestAnimation() {
  const chips = $$(".chip");
  const live = $("#testLive");
  const words = ["à gauche", "à droite", "devant"];
  let i = 0;
  clearInterval(ui.testTimer);
  const tick = () => {
    chips.forEach((c) => c.classList.toggle("on", +c.dataset.dir === i));
    if (i > 2) {
      clearInterval(ui.testTimer);
      live.textContent = "Test terminé.";
      $("#testLabel").innerHTML = "Rejouer<br>le test";
      return;
    }
    live.textContent = `Son joué ${words[i]}.`;
    i += 1;
  };
  tick();
  ui.testTimer = setInterval(tick, 1000);
}

async function copyReport() {
  const st = ui.state;
  const rep = {
    version: "0.1.0", ua: navigator.userAgent, platform: navigator.platform,
    engine: st.engine, engine_error: st.engine_error, phone: { connected: st.phone.connected, fps: st.phone.fps, imu_hz: st.phone.imu_hz, rtt_ms: st.phone.rtt_ms },
    guiding: st.guiding, guide: { phase: st.guide.phase, state: st.guide.state },
    settings: { ...st.settings }, prepared: st.prepared, prepare: st.prepare.status,
  };
  const text = JSON.stringify(rep, null, 2);
  const area = $("#report");
  area.value = text;
  area.hidden = false;
  let ok = false;
  try { await navigator.clipboard.writeText(text); ok = true; } catch (e) {
    area.select();
    try { ok = document.execCommand("copy"); } catch (e2) { ok = false; }
  }
  $("#copied").textContent = ok ? "Rapport copié." : "Copiez le texte ci-dessous.";
}

document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-action]");
  if (el) { e.preventDefault(); onAction(el.dataset.action, el); return; }
  const tab = e.target.closest("[data-tab]");
  if (tab) { e.preventDefault(); ui.tab = tab.dataset.tab; ui.overlay = null; ui.shownView = ""; render(ui.state); return; }
  const obj = e.target.closest("[data-object]");
  if (obj) { api("settings", { object: obj.dataset.object }).then(refresh); return; }
  const prev = e.target.closest("[data-preview]");
  if (prev) {
    api("preview", { sound: prev.dataset.preview });
    prev.classList.add("on");
    setTimeout(() => prev.classList.remove("on"), 1200);
    return;
  }
  const sw = e.target.closest("[data-setting]");
  if (sw) {
    const key = sw.dataset.setting;
    const on = sw.getAttribute("aria-checked") !== "true";
    sw.setAttribute("aria-checked", String(on));
    api("settings", { [key]: on }).then(refresh);
    if (key === "viz" || key === "record") $("#restartNote").hidden = false;
  }
});

document.addEventListener("change", (e) => {
  if (e.target.name === "mode") api("settings", { mode: e.target.value }).then(refresh);
});

document.addEventListener("input", (e) => {
  const key = e.target.dataset && e.target.dataset.vol;
  if (!key) return;
  showVolume(e.target);
  ui.state.settings.volumes[key] = +e.target.value;
  clearTimeout(ui.volumeTimer);
  ui.volumeTimer = setTimeout(async () => {
    await api("settings", { volumes: { [key]: +e.target.value } });
    $("#soundSaved").textContent = "Réglage enregistré.";
  }, 250);
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("#quitModal").hidden) $("#quitModal").hidden = true;
});

// ------------------------------------------------------------------ boucle
async function refresh() {
  if (ui.closed) return;
  try {
    const r = await fetch("/api/state", { cache: "no-store" });
    render(await r.json());
  } catch (e) {
    /* serveur arrêté : la page reste telle quelle */
  }
}

refresh();
setInterval(refresh, 250);

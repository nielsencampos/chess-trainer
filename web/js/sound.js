// Sounds generated in the browser with Web Audio: no files, no licenses, works offline.
// The browser only allows audio after a user gesture, so nothing plays before the first click.

import { getPref, setPref } from "./prefs.js";

const DEFAULT_VOLUME = 0.7;
const BOT_PITCH = 0.85;
const END_DELAY_S = 0.18;

/** @param {number} amount */
const jitter = (amount) => 1 + (Math.random() * 2 - 1) * amount;

/**
 * One knock of wood: a short bright click over a body that falls quickly in pitch.
 * @param {BaseAudioContext} context
 * @param {AudioNode} output
 * @param {number} time
 * @param {{pitch: number, level: number, decay?: number}} knock
 */
function knock(context, output, time, { pitch, level, decay = 0.08 }) {
  const frequency = pitch * jitter(0.04);
  const volume = level * jitter(0.1);

  const body = context.createOscillator();
  body.type = "triangle";
  body.frequency.setValueAtTime(frequency, time);
  body.frequency.exponentialRampToValueAtTime(frequency * 0.7, time + decay);
  const bodyGain = context.createGain();
  bodyGain.gain.setValueAtTime(volume, time);
  bodyGain.gain.exponentialRampToValueAtTime(0.001, time + decay);
  body.connect(bodyGain).connect(output);
  body.start(time);
  body.stop(time + decay);

  // A higher mode of the wood, which dies sooner.
  const mode = context.createOscillator();
  mode.type = "sine";
  mode.frequency.setValueAtTime(frequency * 2.6, time);
  const modeGain = context.createGain();
  modeGain.gain.setValueAtTime(volume * 0.35, time);
  modeGain.gain.exponentialRampToValueAtTime(0.001, time + decay * 0.45);
  mode.connect(modeGain).connect(output);
  mode.start(time);
  mode.stop(time + decay * 0.45);

  // The click of the contact.
  const length = Math.floor(context.sampleRate * 0.02);
  const buffer = context.createBuffer(1, length, context.sampleRate);
  const samples = buffer.getChannelData(0);
  for (let index = 0; index < length; index += 1) samples[index] = Math.random() * 2 - 1;
  const noise = context.createBufferSource();
  noise.buffer = buffer;
  const filter = context.createBiquadFilter();
  filter.type = "bandpass";
  filter.frequency.value = 2600;
  const noiseGain = context.createGain();
  noiseGain.gain.setValueAtTime(volume * 0.5, time);
  noiseGain.gain.exponentialRampToValueAtTime(0.001, time + 0.02);
  noise.connect(filter).connect(noiseGain).connect(output);
  noise.start(time);
}

/**
 * Schedules a sound. Separate from the player so it can be rendered without speakers.
 * @param {BaseAudioContext} context
 * @param {AudioNode} output
 * @param {"move" | "capture" | "castle" | "start" | "end"} type
 * @param {number} time
 * @param {boolean} [byBot]
 */
export function scheduleSound(context, output, type, time, byBot = false) {
  const shift = byBot ? BOT_PITCH : 1;
  switch (type) {
    case "move":
      knock(context, output, time, { pitch: 520 * shift, level: 0.7 });
      break;
    case "capture":
      knock(context, output, time, { pitch: 290 * shift, level: 1, decay: 0.11 });
      knock(context, output, time + 0.07, { pitch: 450 * shift, level: 0.3, decay: 0.05 });
      break;
    case "castle":
      knock(context, output, time, { pitch: 500 * shift, level: 0.6 });
      knock(context, output, time + 0.12, { pitch: 430 * shift, level: 0.6 });
      break;
    case "start":
      knock(context, output, time, { pitch: 480, level: 0.45, decay: 0.12 });
      knock(context, output, time + 0.15, { pitch: 660, level: 0.45, decay: 0.14 });
      break;
    case "end":
      knock(context, output, time + END_DELAY_S, { pitch: 660, level: 0.45, decay: 0.12 });
      knock(context, output, time + END_DELAY_S + 0.17, { pitch: 440, level: 0.45, decay: 0.18 });
      break;
    default:
      break;
  }
}

class SoundPlayer {
  constructor() {
    this.enabled = getPref("soundOn", true) === true;
    const volume = Number(getPref("soundVolume", DEFAULT_VOLUME));
    this.volume = Number.isFinite(volume) ? Math.min(1, Math.max(0, volume)) : DEFAULT_VOLUME;
    /** @type {AudioContext | null} */
    this.context = null;
    /** @type {GainNode | null} */
    this.master = null;
    this.unlocked = false;
    const unlock = () => {
      this.unlocked = true;
      this.ready();
      document.removeEventListener("pointerdown", unlock, true);
      document.removeEventListener("keydown", unlock, true);
    };
    document.addEventListener("pointerdown", unlock, true);
    document.addEventListener("keydown", unlock, true);
  }

  ready() {
    if (!this.context) {
      const Context = window.AudioContext ?? /** @type {any} */ (window).webkitAudioContext;
      if (!Context) return false;
      this.context = new Context();
      this.master = this.context.createGain();
      this.master.gain.value = this.volume;
      this.master.connect(this.context.destination);
    }
    if (this.context.state === "suspended") void this.context.resume();
    return true;
  }

  /**
   * @param {"move" | "capture" | "castle" | "start" | "end"} type
   * @param {boolean} [byBot]
   */
  play(type, byBot = false) {
    if (!this.enabled || !this.unlocked || !this.ready()) return;
    scheduleSound(this.context, this.master, type, this.context.currentTime, byBot);
    document.dispatchEvent(new CustomEvent("chess-trainer:sound", { detail: { type, byBot } }));
  }

  /**
   * @param {import("./rules.js").PlayedMove} move
   * @param {boolean} byBot
   */
  playMove(move, byBot) {
    if (move.castle) this.play("castle", byBot);
    else if (move.capture) this.play("capture", byBot);
    else this.play("move", byBot);
  }

  /** @param {boolean} enabled */
  setEnabled(enabled) {
    this.enabled = enabled;
    setPref("soundOn", enabled);
  }

  /** @param {number} volume */
  setVolume(volume) {
    this.volume = volume;
    setPref("soundVolume", volume);
    if (this.master) this.master.gain.value = volume;
  }
}

export const sound = new SoundPlayer();

/**
 * @param {HTMLButtonElement} button
 * @param {HTMLInputElement} slider
 * @param {(key: string) => string} t
 */
export function initSoundControls(button, slider, t) {
  const render = () => {
    button.textContent = t(sound.enabled ? "sound.on" : "sound.off");
    button.setAttribute("aria-pressed", String(sound.enabled));
    slider.disabled = !sound.enabled;
  };
  slider.value = String(sound.volume);
  slider.setAttribute("aria-label", t("sound.volume"));
  button.addEventListener("click", () => {
    sound.setEnabled(!sound.enabled);
    render();
    sound.play("move");
  });
  slider.addEventListener("input", () => sound.setVolume(Number(slider.value)));
  slider.addEventListener("change", () => sound.play("move")); // To hear the new volume.
  render();
}

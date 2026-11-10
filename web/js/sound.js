// Sounds generated in the browser with Web Audio: no files, no licenses, works offline.
// The browser only allows audio after a user gesture, so nothing plays before the first click.

import { onLocaleChange, t } from "./i18n.js";
import { getPref, setPref } from "./prefs.js";

const DEFAULT_VOLUME = 0.7;
const BOT_PITCH = 0.85;
const END_DELAY_S = 0.18;

/**
 * A random factor around 1, so repeated sounds are not identical.
 * @param {number} amount  The most it can differ from 1, such as 0.04.
 * @returns {number} The factor.
 */
const jitter = (amount) => 1 + (Math.random() * 2 - 1) * amount;

/**
 * One knock of wood: a short bright click over a body that falls quickly in pitch.
 * @param {BaseAudioContext} context  The audio context.
 * @param {AudioNode} output  Where the sound goes.
 * @param {number} time  When it starts, in the context's seconds.
 * @param {{pitch: number, level: number, decay?: number}} knock  Its pitch in Hz, its level,
 *   and how long it rings, in seconds.
 * @returns {void}
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
 * @param {BaseAudioContext} context  The audio context.
 * @param {AudioNode} output  Where the sound goes.
 * @param {"move" | "capture" | "castle" | "start" | "end"} type  The event.
 * @param {number} time  When it starts, in the context's seconds.
 * @param {boolean} [byBot]  A bot move sounds slightly lower.
 * @returns {void}
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

/** Plays the app's sounds, once the browser allows audio, at the stored volume. */
class SoundPlayer {
  /** Restores the stored on/off and volume, and waits for the first click or key to unlock audio. */
  constructor() {
    this.enabled = getPref("soundOn", true) === true;
    const volume = Number(getPref("soundVolume", DEFAULT_VOLUME));
    this.volume = Number.isFinite(volume) ? Math.min(1, Math.max(0, volume)) : DEFAULT_VOLUME;
    /** @type {AudioContext | null} */
    this.context = null;
    /** @type {GainNode | null} */
    this.master = null;
    this.unlocked = false;
    /** Allows audio after the first user gesture, then stops listening. */
    const unlock = () => {
      this.unlocked = true;
      this.ready();
      document.removeEventListener("pointerdown", unlock, true);
      document.removeEventListener("keydown", unlock, true);
    };
    document.addEventListener("pointerdown", unlock, true);
    document.addEventListener("keydown", unlock, true);
  }

  /**
   * Creates or resumes the audio context.
   * @returns {boolean} False if the browser has no Web Audio.
   */
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
   * Plays a sound if sound is on and audio is unlocked, and tells test hooks about it.
   * @param {"move" | "capture" | "castle" | "start" | "end"} type  The event.
   * @param {boolean} [byBot]  A bot move sounds slightly lower.
   * @returns {void}
   */
  play(type, byBot = false) {
    if (!this.enabled || !this.unlocked || !this.ready()) return;
    scheduleSound(this.context, this.master, type, this.context.currentTime, byBot);
    document.dispatchEvent(new CustomEvent("chess-trainer:sound", { detail: { type, byBot } }));
  }

  /**
   * Plays the sound of a move: castling, capture or a plain move.
   * @param {import("./rules.js").PlayedMove} move  The move played.
   * @param {boolean} byBot  Whether the bot played it.
   * @returns {void}
   */
  playMove(move, byBot) {
    if (move.castle) this.play("castle", byBot);
    else if (move.capture) this.play("capture", byBot);
    else this.play("move", byBot);
  }

  /**
   * Turns sound on or off and stores the choice.
   * @param {boolean} enabled  Whether sound is on.
   * @returns {void}
   */
  setEnabled(enabled) {
    this.enabled = enabled;
    setPref("soundOn", enabled);
  }

  /**
   * Sets and stores the volume.
   * @param {number} volume  From 0 to 1.
   * @returns {void}
   */
  setVolume(volume) {
    this.volume = volume;
    setPref("soundVolume", volume);
    if (this.master) this.master.gain.value = volume;
  }
}

/** The app's one sound player. */
export const sound = new SoundPlayer();

/**
 * Wires the sound button and the volume slider.
 * @param {HTMLButtonElement} button  Turns sound on and off.
 * @param {HTMLInputElement} slider  The volume, 0 to 1.
 * @returns {void}
 */
export function initSoundControls(button, slider) {
  /** Labels the button and enables the slider as sound is on or off. */
  const render = () => {
    button.textContent = t(sound.enabled ? "sound.on" : "sound.off");
    button.setAttribute("aria-pressed", String(sound.enabled));
    slider.disabled = !sound.enabled;
  };
  slider.value = String(sound.volume);
  /** Labels the slider in the current language. */
  const label = () => slider.setAttribute("aria-label", t("sound.volume"));
  label();
  onLocaleChange(() => {
    label();
    render();
  });
  button.addEventListener("click", () => {
    sound.setEnabled(!sound.enabled);
    render();
    sound.play("move");
  });
  slider.addEventListener("input", () => sound.setVolume(Number(slider.value)));
  slider.addEventListener("change", () => sound.play("move")); // To hear the new volume.
  render();
}

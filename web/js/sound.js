// The app's sounds: recordings by the project's author in web/sounds/, played with Web Audio.
// The browser only allows audio after a user gesture, so nothing plays before the first click.

import { onLocaleChange, t } from "./i18n.js";
import { getPref, setPref } from "./prefs.js";

/** @typedef {"move" | "capture" | "castle" | "check" | "clock" | "start" | "end"} SoundType */

/** @type {SoundType[]} */
export const SOUND_TYPES = ["move", "capture", "castle", "check", "clock", "start", "end"];

const DEFAULT_VOLUME = 0.7;
// A bot move plays a little slower, so it sounds slightly lower.
const BOT_RATE = 0.94;
// The end comes after the last move's sound, and the clock is pressed just after the move.
const END_DELAY_S = 0.2;
const CLOCK_DELAY_S = 0.25;

/**
 * Fetches and decodes every sound file.
 * @param {BaseAudioContext} context  Decodes the files. An AudioBuffer plays in any context.
 * @returns {Promise<Map<SoundType, AudioBuffer>>} Each type's sound; a file that fails is left out.
 */
export async function loadSounds(context) {
  const buffers = new Map();
  await Promise.all(
    SOUND_TYPES.map(async (type) => {
      try {
        const response = await fetch(new URL(`../sounds/${type}.wav`, import.meta.url));
        if (!response.ok) return;
        buffers.set(type, await context.decodeAudioData(await response.arrayBuffer()));
      } catch {
        // Without that file the event is silent; the game goes on.
      }
    }),
  );
  return buffers;
}

/**
 * Schedules a sound. Separate from the player so it can be rendered without speakers.
 * @param {BaseAudioContext} context  The audio context.
 * @param {AudioNode} output  Where the sound goes.
 * @param {AudioBuffer} buffer  The sound.
 * @param {number} time  When it starts, in the context's seconds.
 * @param {boolean} [byBot]  A bot move sounds slightly lower.
 * @returns {void}
 */
export function scheduleSound(context, output, buffer, time, byBot = false) {
  const source = context.createBufferSource();
  source.buffer = buffer;
  source.playbackRate.value = byBot ? BOT_RATE : 1;
  source.connect(output);
  source.start(time);
}

/**
 * The sound of a move, from its SAN: castling, then capture, then check, else a plain move.
 * @param {string} san  The move in SAN.
 * @returns {SoundType} The sound to play.
 */
export function moveSound(san) {
  if (san.startsWith("O-O")) return "castle";
  if (san.includes("x")) return "capture";
  if (/[+#]$/.test(san)) return "check";
  return "move";
}

/** Plays the app's sounds, once the browser allows audio, at the stored volume. */
class SoundPlayer {
  /**
   * Restores the stored on/off and volume, and waits for the first click or key to unlock audio.
   * @returns {void}
   */
  constructor() {
    this.enabled = getPref("soundOn", true) === true;
    const volume = Number(getPref("soundVolume", DEFAULT_VOLUME));
    this.volume = Number.isFinite(volume) ? Math.min(1, Math.max(0, volume)) : DEFAULT_VOLUME;
    /** @type {AudioContext | null} */
    this.context = null;
    /** @type {GainNode | null} */
    this.master = null;
    /** @type {Map<SoundType, AudioBuffer>} */
    this.buffers = new Map();
    /** @type {Promise<void> | null} */
    this.loading = null;
    // Decoding needs no gesture in an offline context, so the files are ready for the first move.
    if (typeof OfflineAudioContext !== "undefined") this.load(new OfflineAudioContext(1, 1, 44100));
    this.unlocked = false;
    /**
     * Allows audio after the first user gesture, then stops listening.
     * @returns {void}
     */
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
   * Starts loading the sound files, once.
   * @param {BaseAudioContext} context  Decodes them.
   * @returns {void}
   */
  load(context) {
    this.loading ??= loadSounds(context).then((buffers) => {
      this.buffers = buffers;
    });
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
      this.load(this.context);
    }
    if (this.context.state === "suspended") void this.context.resume();
    return true;
  }

  /**
   * Plays a sound if sound is on and audio is unlocked, and tells test hooks about it.
   * @param {SoundType} type  The event.
   * @param {{byBot?: boolean, delay?: number}} [options]  A bot move sounds slightly lower;
   *   `delay` is in seconds from now.
   * @returns {void}
   */
  play(type, { byBot = false, delay = 0 } = {}) {
    if (!this.enabled || !this.unlocked || !this.ready()) return;
    const context = /** @type {AudioContext} */ (this.context);
    const at = context.currentTime + (type === "end" ? END_DELAY_S : delay);
    /**
     * Schedules the sound, once its file is decoded.
     * @returns {void}
     */
    const start = () => {
      const buffer = this.buffers.get(type);
      if (buffer) scheduleSound(context, /** @type {GainNode} */ (this.master), buffer, at, byBot);
    };
    // Before the files are decoded, the sound plays as soon as they are, if still in time.
    if (this.buffers.has(type)) start();
    else void this.loading?.then(start);
    document.dispatchEvent(new CustomEvent("chess-trainer:sound", { detail: { type, byBot } }));
  }

  /**
   * Plays the sound of a move, and the clock being pressed after it in a timed game.
   * @param {string} san  The move in SAN.
   * @param {{byBot?: boolean, clock?: boolean}} [options]  Whether the bot played it, and
   *   whether a clock is pressed after it.
   * @returns {void}
   */
  playMove(san, { byBot = false, clock = false } = {}) {
    this.play(moveSound(san), { byBot });
    if (clock) this.play("clock", { byBot, delay: CLOCK_DELAY_S });
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
  /**
   * Labels the button and enables the slider as sound is on or off.
   * @returns {void}
   */
  const render = () => {
    button.textContent = t(sound.enabled ? "sound.on" : "sound.off");
    button.setAttribute("aria-pressed", String(sound.enabled));
    slider.disabled = !sound.enabled;
  };
  slider.value = String(sound.volume);
  /**
   * Labels the slider in the current language.
   * @returns {void}
   */
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

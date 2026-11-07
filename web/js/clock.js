// The two game clocks. The browser's clock is the authority; the server receives its values.

const TICK_MS = 100;
const LOW_TIME_MS = 20_000;
const LOW_TIME_SHARE = 0.1;

/**
 * @param {number} ms
 * @returns {string}
 */
export function formatClock(ms) {
  const totalSeconds = Math.ceil(Math.max(0, ms) / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${seconds}`
    : `${String(minutes).padStart(2, "0")}:${seconds}`;
}

export class Clocks {
  /**
   * @param {(color: "w" | "b") => void} onFlag
   * @param {() => void} onTick
   */
  constructor(onFlag, onTick) {
    this.onFlag = onFlag;
    this.onTick = onTick;
    this.enabled = false;
    this.increment = 0;
    this.movesToBonus = null;
    this.bonus = 0;
    this.lowTime = LOW_TIME_MS;
    this.remaining = { w: 0, b: 0 };
    this.movesMade = { w: 0, b: 0 };
    /** @type {"w" | "b" | null} */
    this.active = null;
    this.lastTick = 0;
    this.timer = 0;
  }

  /**
   * @param {{base_ms: number, increment_ms: number, moves_to_bonus: number | null,
   *   bonus_ms: number} | null} timeControl
   */
  reset(timeControl) {
    this.stop();
    this.enabled = timeControl !== null;
    this.increment = timeControl?.increment_ms ?? 0;
    this.movesToBonus = timeControl?.moves_to_bonus ?? null;
    this.bonus = timeControl?.bonus_ms ?? 0;
    this.remaining = { w: timeControl?.base_ms ?? 0, b: timeControl?.base_ms ?? 0 };
    this.movesMade = { w: 0, b: 0 };
    // A short game would otherwise start in red.
    this.lowTime = Math.min(LOW_TIME_MS, (timeControl?.base_ms ?? 0) * LOW_TIME_SHARE);
    this.onTick();
  }

  /** @param {"w" | "b"} color */
  start(color) {
    if (!this.enabled) return;
    this.settle();
    this.active = color;
    this.lastTick = performance.now();
    clearInterval(this.timer);
    this.timer = setInterval(() => this.tick(), TICK_MS);
    this.onTick();
  }

  stop() {
    this.settle();
    this.active = null;
    clearInterval(this.timer);
  }

  /**
   * A player finished a move: stop their time, add the increment and any bonus it earned.
   * @param {"w" | "b"} color
   */
  press(color) {
    if (!this.enabled) return;
    this.stop();
    this.remaining[color] += this.increment;
    this.movesMade[color] += 1;
    if (this.movesMade[color] === this.movesToBonus) this.remaining[color] += this.bonus;
    this.onTick();
  }

  /**
   * @param {"w" | "b"} color
   * @returns {number | null}
   */
  remainingMs(color) {
    if (!this.enabled) return null;
    this.settle();
    return Math.round(this.remaining[color]);
  }

  settle() {
    if (this.active === null) return;
    const now = performance.now();
    this.remaining[this.active] = Math.max(0, this.remaining[this.active] - (now - this.lastTick));
    this.lastTick = now;
  }

  tick() {
    const color = this.active;
    if (color === null) return;
    this.settle();
    this.onTick();
    if (this.remaining[color] <= 0) {
      this.stop();
      this.onFlag(color);
    }
  }
}

// The two game clocks. The browser's clock is the authority; the server receives its values.

const TICK_MS = 100;
const LOW_TIME_MS = 20_000;
const LOW_TIME_SHARE = 0.1;

/**
 * @param {number} ms
 * @returns {string}
 */
export function formatClock(ms) {
  const tenths = Math.ceil(Math.max(0, ms) / 100);
  if (tenths < 100) {
    return `00:${String(Math.floor(tenths / 10)).padStart(2, "0")}.${tenths % 10}`;
  }
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
    /** @type {{after_moves: number, add_ms: number}[]} */
    this.periods = [];
    this.delay = 0;
    /** @type {string | null} */
    this.delayKind = null;
    this.turnStartRemaining = 0;
    this.usDelayLeft = 0;
    this.lowTime = LOW_TIME_MS;
    this.remaining = { w: 0, b: 0 };
    this.movesMade = { w: 0, b: 0 };
    /** @type {"w" | "b" | null} */
    this.active = null;
    this.lastTick = 0;
    this.timer = 0;
  }

  /**
   * @param {{base_ms: number, increment_ms: number,
   *   periods: {after_moves: number, add_ms: number}[],
   *   delay_ms: number, delay_kind: string | null} | null} timeControl
   */
  reset(timeControl) {
    this.stop();
    this.enabled = timeControl !== null;
    this.increment = timeControl?.increment_ms ?? 0;
    this.periods = timeControl?.periods ?? [];
    this.delay = timeControl?.delay_ms ?? 0;
    this.delayKind = timeControl?.delay_kind ?? null;
    this.remaining = { w: timeControl?.base_ms ?? 0, b: timeControl?.base_ms ?? 0 };
    this.movesMade = { w: 0, b: 0 };
    // A short game would otherwise start in red.
    this.lowTime = Math.min(LOW_TIME_MS, (timeControl?.base_ms ?? 0) * LOW_TIME_SHARE);
    this.onTick();
  }

  /**
   * Puts the clocks back where a saved game left them.
   * @param {{w: number | null, b: number | null}} remaining
   * @param {{w: number, b: number}} movesMade
   */
  restore(remaining, movesMade) {
    if (!this.enabled) return;
    this.remaining = { w: remaining.w ?? this.remaining.w, b: remaining.b ?? this.remaining.b };
    this.movesMade = { ...movesMade };
    this.onTick();
  }

  /** @param {"w" | "b"} color */
  start(color) {
    if (!this.enabled) return;
    this.settle();
    this.active = color;
    this.turnStartRemaining = this.remaining[color];
    this.usDelayLeft = this.delayKind === "us" ? this.delay : 0;
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
   * A player finished a move: stop their time, then add the increment, any Bronstein refund
   * and the time of a new period.
   * @param {"w" | "b"} color
   */
  press(color) {
    if (!this.enabled) return;
    this.stop();
    this.remaining[color] += this.increment;
    if (this.delayKind === "bronstein") {
      const used = this.turnStartRemaining - this.remaining[color] + this.increment;
      this.remaining[color] += Math.min(used, this.delay);
    }
    this.movesMade[color] += 1;
    for (const period of this.periods) {
      if (this.movesMade[color] === period.after_moves) this.remaining[color] += period.add_ms;
    }
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
    let elapsed = now - this.lastTick;
    const free = Math.min(this.usDelayLeft, elapsed);
    this.usDelayLeft -= free;
    elapsed -= free;
    this.remaining[this.active] = Math.max(0, this.remaining[this.active] - elapsed);
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

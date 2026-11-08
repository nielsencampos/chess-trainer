"""Evaluates every position of the book once, so the evaluation bar never waits for them.

    uv run python -m app.book.evaluate_book --engine .cache/stockfish --depth 32 --workers 8

Writes `evals/book.json`, keyed by EPD: transpositions share one entry, and the line files in
`openings/` stay untouched. It can be stopped at any time and resumed: positions already
evaluated at the requested depth or deeper are kept. Each worker is its own Stockfish process
with one thread, at a low priority: at a fixed depth, separate processes go faster than threads.
"""

import argparse
import json
import multiprocessing
import os
import signal
import sys
import time
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

import chess
import chess.engine

from app.book.source import read_opening_files, replay

EVALS_FILE = Path("evals/book.json")
CHECKPOINT_EVERY = 20

_engine: chess.engine.SimpleEngine | None = None


def book_positions(openings: Path) -> dict[str, int]:
    """EPD -> the earliest ply it appears at, so the opening moves are evaluated first."""
    plies: dict[str, int] = {chess.Board().epd(): 0}
    for opening_file in read_opening_files(openings):
        for line in opening_file.lines:
            replayed = replay(line)
            for row in replayed.rows:
                plies[row.epd_before] = min(plies.get(row.epd_before, row.ply - 1), row.ply - 1)
            plies[replayed.final_epd] = min(
                plies.get(replayed.final_epd, len(line.moves)), len(line.moves)
            )
    return plies


def read_evals(path: Path) -> dict:
    if not path.exists():
        return {"engine": None, "positions": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def write_evals(path: Path, engine_name: str, positions: dict[str, dict]) -> None:
    """One position per line, sorted, so a new run shows as a readable diff."""
    path.parent.mkdir(parents=True, exist_ok=True)
    header = {
        "engine": engine_name,
        "updated": datetime.now(UTC).strftime("%Y-%m-%d"),
        "count": len(positions),
    }
    lines = [f'  "{key}": {json.dumps(value)}' for key, value in sorted(header.items())]
    body = ",\n".join(
        f"    {json.dumps(epd)}: {json.dumps(positions[epd], sort_keys=True)}"
        for epd in sorted(positions)
    )
    text = "{\n" + ",\n".join(lines) + ',\n  "positions": {\n' + body + "\n  }\n}\n"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _start_worker(engine_path: str, hash_mb: int) -> None:
    global _engine
    os.nice(10)
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # the main process decides when to stop
    _engine = chess.engine.SimpleEngine.popen_uci(engine_path)
    _engine.configure({"Threads": 1, "Hash": hash_mb})


def _evaluate(epd: str, depth: int) -> tuple[str, dict]:
    assert _engine is not None
    board = chess.Board.from_epd(epd)[0]
    if board.is_game_over():
        outcome = board.outcome()
        winner = None if outcome is None else outcome.winner
        cp = 0 if winner is None else (10_000 if winner == chess.WHITE else -10_000)
        return epd, {"cp": cp, "depth": depth}
    info = _engine.analyse(board, chess.engine.Limit(depth=depth))
    white = info["score"].white()
    result: dict = {"depth": int(info.get("depth", depth))}
    if white.mate() is not None:
        result["mate"] = white.mate()
    else:
        result["cp"] = white.score()
    pv = info.get("pv")
    if pv:
        result["best"] = pv[0].uci()
    return epd, result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--engine", default=".cache/stockfish")
    parser.add_argument("--depth", type=int, default=32)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 4))
    parser.add_argument("--hash-mb", type=int, default=256)
    parser.add_argument("--openings", type=Path, default=Path("openings"))
    parser.add_argument("--output", type=Path, default=EVALS_FILE)
    args = parser.parse_args()

    with chess.engine.SimpleEngine.popen_uci(args.engine) as probe:
        engine_name = probe.id.get("name", "unknown")
    plies = book_positions(args.openings)
    stored = read_evals(args.output)
    positions: dict[str, dict] = {
        epd: value for epd, value in stored["positions"].items() if epd in plies
    }
    todo = sorted(
        (epd for epd in plies if positions.get(epd, {}).get("depth", 0) < args.depth),
        key=lambda epd: (plies[epd], epd),
    )
    print(f"{len(plies)} positions, {len(todo)} to evaluate at depth {args.depth}", flush=True)
    if not todo:
        write_evals(args.output, engine_name, positions)
        return 0

    started = time.monotonic()
    done = 0
    # terminate() rather than close(): a worker's Stockfish keeps it alive otherwise, and each
    # Stockfish quits by itself when its worker is gone and its input closes.
    pool = multiprocessing.Pool(args.workers, _start_worker, (args.engine, args.hash_mb))
    try:
        for epd, value in pool.imap_unordered(partial(_evaluate, depth=args.depth), todo):
            positions[epd] = value
            done += 1
            if done % CHECKPOINT_EVERY == 0 or done == len(todo):
                write_evals(args.output, engine_name, positions)
                rate = (time.monotonic() - started) / done
                left = rate * (len(todo) - done)
                print(f"{done}/{len(todo)}  ~{left / 3600:.1f} h left", flush=True)
    except KeyboardInterrupt:
        print("stopping; what is done is saved", flush=True)
        write_evals(args.output, engine_name, positions)
        return 130
    finally:
        pool.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())

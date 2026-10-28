import { SPEEDS, type Speed } from "@/lib/playback";
import styles from "./Playback.module.css";

type Props = {
  playing: boolean;
  finished: boolean;
  speed: Speed;
  shown: number;
  total: number;
  onToggle: () => void;
  onRestart: () => void;
  onSpeed: (speed: Speed) => void;
  onSeek: (to: number) => void;
  /** How far in, in words a newcomer follows: "Round 2 of 4". */
  progress: string;
};

function Icon({ kind }: { kind: "play" | "pause" | "restart" }) {
  const paths = {
    play: "M5 3.5v9l7.5-4.5L5 3.5Z",
    pause: "M4.5 3.5h2.6v9H4.5v-9Zm4.4 0h2.6v9H8.9v-9Z",
    restart:
      "M8 2.5a5.5 5.5 0 1 0 5.2 7.3h-1.7A3.9 3.9 0 1 1 8 4.1c1 0 1.9.4 2.6 1L8.8 7h4.7V2.3l-1.7 1.7A5.5 5.5 0 0 0 8 2.5Z",
  };
  return (
    <svg viewBox="0 0 16 16" width="18" height="18" aria-hidden="true" focusable="false">
      <path d={paths[kind]} fill="currentColor" />
    </svg>
  );
}

/**
 * The bar at the foot of a replay, where a messenger's message box would be: play or pause, a
 * slider through the game, how far in, and how fast.
 */
export function Playback({ playing, finished, speed, shown, total, onToggle, onRestart, onSpeed, onSeek, progress }: Props) {
  const count = Math.min(shown, total);
  const label = finished ? "Watch again" : playing ? "Pause" : "Play";
  return (
    <div className={styles.bar} role="group" aria-label="Replay controls">
      <button
        type="button"
        className={styles.main}
        onClick={finished ? onRestart : onToggle}
        aria-label={label}
        title={label}
      >
        <Icon kind={finished ? "restart" : playing ? "pause" : "play"} />
        <span className="visually-hidden">{label}</span>
      </button>
      <input
        type="range"
        className={styles.scrub}
        min={0}
        max={total}
        value={count}
        onChange={(e) => onSeek(Number(e.target.value))}
        aria-label="Position in the game"
        aria-valuetext={progress}
        style={{ ["--filled" as string]: total ? `${(count / total) * 100}%` : "0%" }}
      />
      <span className={styles.progress}>{progress}</span>
      <div className={styles.speeds} role="radiogroup" aria-label="Speed">
        {SPEEDS.map((s) => (
          <button key={s.id} type="button" role="radio" aria-checked={speed === s.id} onClick={() => onSpeed(s.id)}>
            {s.label}
          </button>
        ))}
      </div>
    </div>
  );
}

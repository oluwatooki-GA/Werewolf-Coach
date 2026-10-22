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
};

function Icon({ kind }: { kind: "play" | "pause" | "restart" }) {
  const paths = {
    play: "M5 3.5v9l7.5-4.5L5 3.5Z",
    pause: "M4.5 3.5h2.6v9H4.5v-9Zm4.4 0h2.6v9H8.9v-9Z",
    restart:
      "M8 2.5a5.5 5.5 0 1 0 5.2 7.3h-1.7A3.9 3.9 0 1 1 8 4.1c1 0 1.9.4 2.6 1L8.8 7h4.7V2.3l-1.7 1.7A5.5 5.5 0 0 0 8 2.5Z",
  };
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      <path d={paths[kind]} fill="currentColor" />
    </svg>
  );
}

/** Play or pause, start over, how fast, and how far through the game you are. */
export function Playback({ playing, finished, speed, shown, total, onToggle, onRestart, onSpeed }: Props) {
  return (
    <div className={styles.bar} role="group" aria-label="Replay controls">
      <button
        type="button"
        className={styles.main}
        onClick={finished ? onRestart : onToggle}
        aria-label={finished ? "Watch again" : playing ? "Pause" : "Play"}
      >
        <Icon kind={finished ? "restart" : playing ? "pause" : "play"} />
        <span>{finished ? "Watch again" : playing ? "Pause" : "Play"}</span>
      </button>
      <div className={styles.speeds} role="radiogroup" aria-label="Speed">
        {SPEEDS.map((s) => (
          <button
            key={s.id}
            type="button"
            role="radio"
            aria-checked={speed === s.id}
            onClick={() => onSpeed(s.id)}
          >
            {s.label}
          </button>
        ))}
      </div>
      <span className={styles.progress}>
        {Math.min(shown, total)} of {total}
      </span>
    </div>
  );
}

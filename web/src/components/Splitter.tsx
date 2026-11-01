"use client";

import { useEffect, useRef, useState } from "react";
import styles from "./Splitter.module.css";

const STEP = 16;

/** The details column is the same width in every chat, so the reader sizes it once. */
export const INFO_KEY = "werewolf-coach.info-width";
export const INFO_DEFAULT = 368;
export const INFO_MIN = 288;
export const INFO_MAX = 640;

/**
 * The width of a panel the reader can change, kept within its limits and remembered between visits.
 * Returns the width in pixels, a setter, and a way back to the default.
 */
export function useWidth(key: string, fallback: number, min: number, max: number) {
  const [width, set] = useState(fallback);

  useEffect(() => {
    try {
      const saved = Number(localStorage.getItem(key));
      /* eslint-disable react-hooks/set-state-in-effect -- reads the browser once, after hydration */
      if (saved >= min && saved <= max) set(saved);
      /* eslint-enable react-hooks/set-state-in-effect */
    } catch {
      // private windows can refuse storage; the default is fine
    }
  }, [key, min, max]);

  function change(next: number) {
    const value = Math.round(Math.min(max, Math.max(min, next)));
    set(value);
    try {
      localStorage.setItem(key, String(value));
    } catch {
      // not remembered, still applied
    }
  }

  return [width, change, () => change(fallback)] as const;
}

type Props = {
  label: string;
  value: number;
  min: number;
  max: number;
  /** Which way the panel grows when the handle moves: a list on the left grows to the right. */
  grow: "left" | "right";
  onChange: (width: number) => void;
  onReset: () => void;
  className?: string;
  style?: React.CSSProperties;
};

/**
 * A draggable edge between two panels. It sits inside the frame that holds them, which is where the
 * width is measured from. Arrow keys move it too (Shift for a bigger step); a double click resets.
 */
export function Splitter({ label, value, min, max, grow, onChange, onReset, className, style }: Props) {
  const dragging = useRef(false);

  function widthAt(handle: HTMLElement, x: number) {
    const frame = handle.parentElement?.getBoundingClientRect();
    if (!frame) return value;
    return grow === "right" ? x - frame.left : frame.right - x;
  }

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={value}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      className={[styles.handle, className].filter(Boolean).join(" ")}
      style={style}
      onPointerDown={(event) => {
        dragging.current = true;
        event.currentTarget.setPointerCapture?.(event.pointerId);
        event.preventDefault();
      }}
      onPointerMove={(event) => {
        if (dragging.current) onChange(widthAt(event.currentTarget, event.clientX));
      }}
      onPointerUp={() => {
        dragging.current = false;
      }}
      onPointerCancel={() => {
        dragging.current = false;
      }}
      onDoubleClick={onReset}
      onKeyDown={(event) => {
        if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
        event.preventDefault();
        const toRight = event.key === "ArrowRight";
        const bigger = toRight === (grow === "right");
        const step = event.shiftKey ? STEP * 4 : STEP;
        onChange(value + (bigger ? step : -step));
      }}
    />
  );
}

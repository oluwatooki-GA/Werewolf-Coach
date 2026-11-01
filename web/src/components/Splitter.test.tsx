import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Splitter, useWidth } from "./Splitter";

function handle(grow: "left" | "right", value = 300) {
  const onChange = vi.fn();
  const onReset = vi.fn();
  render(
    <div data-testid="frame">
      <Splitter
        label="Chat list width"
        grow={grow}
        value={value}
        min={200}
        max={500}
        onChange={onChange}
        onReset={onReset}
      />
    </div>,
  );
  const frame = screen.getByTestId("frame");
  frame.getBoundingClientRect = () => ({ left: 0, right: 1000, top: 0, bottom: 0, width: 1000, height: 0, x: 0, y: 0, toJSON() {} });
  return { onChange, onReset, separator: screen.getByRole("separator", { name: "Chat list width" }) };
}

// jsdom has no PointerEvent, so a pointer event would arrive without its coordinates
if (!("PointerEvent" in window)) {
  class PointerEventStub extends MouseEvent {
    pointerId: number;
    constructor(type: string, init: MouseEventInit & { pointerId?: number } = {}) {
      super(type, init);
      this.pointerId = init.pointerId ?? 0;
    }
  }
  Object.defineProperty(window, "PointerEvent", { value: PointerEventStub });
}

afterEach(() => localStorage.clear());

describe("Splitter", () => {
  it("tells assistive tech its width and its limits", () => {
    const { separator } = handle("right");
    expect(separator).toHaveAttribute("aria-valuenow", "300");
    expect(separator).toHaveAttribute("aria-valuemin", "200");
    expect(separator).toHaveAttribute("aria-valuemax", "500");
  });

  it("grows a panel that grows to the right when the right arrow is pressed", () => {
    const { separator, onChange } = handle("right");
    fireEvent.keyDown(separator, { key: "ArrowRight" });
    expect(onChange).toHaveBeenLastCalledWith(316);
    fireEvent.keyDown(separator, { key: "ArrowLeft", shiftKey: true });
    expect(onChange).toHaveBeenLastCalledWith(236);
  });

  it("grows a panel that grows to the left when the left arrow is pressed", () => {
    const { separator, onChange } = handle("left");
    fireEvent.keyDown(separator, { key: "ArrowLeft" });
    expect(onChange).toHaveBeenLastCalledWith(316);
  });

  it("follows the pointer while it is dragged, from the frame's left edge", () => {
    const { separator, onChange } = handle("right");
    fireEvent.pointerDown(separator, { clientX: 300, pointerId: 1 });
    fireEvent.pointerMove(separator, { clientX: 420, pointerId: 1 });
    expect(onChange).toHaveBeenLastCalledWith(420);
    fireEvent.pointerUp(separator, { pointerId: 1 });
    onChange.mockClear();
    fireEvent.pointerMove(separator, { clientX: 450, pointerId: 1 });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("measures a panel on the right from the frame's right edge", () => {
    const { separator, onChange } = handle("left");
    fireEvent.pointerDown(separator, { clientX: 700, pointerId: 1 });
    fireEvent.pointerMove(separator, { clientX: 640, pointerId: 1 });
    expect(onChange).toHaveBeenLastCalledWith(360);
  });

  it("goes back to the default width on a double click", () => {
    const { separator, onReset } = handle("right");
    fireEvent.doubleClick(separator);
    expect(onReset).toHaveBeenCalled();
  });
});

describe("useWidth", () => {
  it("starts at the default, keeps within its limits and remembers the choice", () => {
    const { result } = renderHook(() => useWidth("test.width", 300, 200, 500));
    expect(result.current[0]).toBe(300);
    act(() => result.current[1](900));
    expect(result.current[0]).toBe(500);
    act(() => result.current[1](50));
    expect(result.current[0]).toBe(200);
    expect(localStorage.getItem("test.width")).toBe("200");
  });

  it("brings back a saved width, and ignores a saved one outside the limits", () => {
    localStorage.setItem("test.width", "420");
    const saved = renderHook(() => useWidth("test.width", 300, 200, 500));
    expect(saved.result.current[0]).toBe(420);
    localStorage.setItem("test.width", "9999");
    const wild = renderHook(() => useWidth("test.width", 300, 200, 500));
    expect(wild.result.current[0]).toBe(300);
  });

  it("goes back to the default", () => {
    const { result } = renderHook(() => useWidth("test.width", 300, 200, 500));
    act(() => result.current[1](400));
    act(() => result.current[2]());
    expect(result.current[0]).toBe(300);
  });
});

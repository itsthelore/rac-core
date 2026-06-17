// jsdom lacks ResizeObserver, which GraphView observes; a no-op keeps the
// viewport at its default size, which is enough to mount and render.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= ResizeObserverStub;

// Enable React 18's act() environment so state updates flush deterministically.
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

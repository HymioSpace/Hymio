type Viewport = Pick<HTMLElement, 'scrollHeight'> & { scrollTop: number };
type Anchor = Pick<HTMLElement, 'scrollIntoView'>;
type RequestFrame = (callback: FrameRequestCallback) => number;

export function scheduleLatestScroll({
  viewport,
  anchor,
  shouldFollow,
  requestFrame = requestAnimationFrame,
}: {
  viewport: Viewport | null;
  anchor: Anchor | null;
  shouldFollow: () => boolean;
  requestFrame?: RequestFrame;
}) {
  requestFrame(() => {
    requestFrame(() => {
      if (!viewport || !shouldFollow()) return;
      if (anchor) {
        anchor.scrollIntoView({ block: 'end', behavior: 'instant' });
      } else {
        viewport.scrollTop = viewport.scrollHeight;
      }
    });
  });
}

export const DRAG_THRESHOLD_PX = 5;

export function exceededDragThreshold(
  startX: number,
  startY: number,
  currentX: number,
  currentY: number,
  threshold = DRAG_THRESHOLD_PX,
): boolean {
  return Math.hypot(currentX - startX, currentY - startY) >= threshold;
}

export function isEditableTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement ||
    Boolean(target instanceof HTMLElement && target.isContentEditable)
  );
}

export function isShortcut(event: KeyboardEvent, key: string): boolean {
  return !event.altKey && event.key.toLowerCase() === key.toLowerCase();
}

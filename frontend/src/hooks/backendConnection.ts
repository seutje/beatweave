export interface BackendRetryOptions {
  attempts?: number;
  retryDelayMs?: number;
  shouldContinue?: () => boolean;
  wait?: (milliseconds: number) => Promise<void>;
}

const delay = (milliseconds: number) =>
  new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds));

export async function waitForBackend<T>(
  check: () => Promise<T>,
  {
    attempts = 91,
    retryDelayMs = 500,
    shouldContinue = () => true,
    wait = delay,
  }: BackendRetryOptions = {},
): Promise<T> {
  let lastError: unknown = new Error("Backend is unavailable");

  for (let attempt = 0; attempt < attempts && shouldContinue(); attempt += 1) {
    try {
      return await check();
    } catch (error) {
      lastError = error;
      if (attempt + 1 < attempts && shouldContinue()) {
        await wait(retryDelayMs);
      }
    }
  }

  throw lastError;
}

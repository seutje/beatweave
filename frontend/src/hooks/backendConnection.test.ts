import { describe, expect, it, vi } from "vitest";

import { waitForBackend } from "./backendConnection";

describe("backend startup connection", () => {
  it("keeps retrying while the packaged backend starts", async () => {
    const check = vi
      .fn<() => Promise<{ status: string }>>()
      .mockRejectedValueOnce(new Error("connection refused"))
      .mockRejectedValueOnce(new Error("connection refused"))
      .mockResolvedValue({ status: "ok" });
    const wait = vi.fn().mockResolvedValue(undefined);

    await expect(
      waitForBackend(check, { attempts: 3, retryDelayMs: 500, wait }),
    ).resolves.toEqual({ status: "ok" });
    expect(check).toHaveBeenCalledTimes(3);
    expect(wait).toHaveBeenCalledTimes(2);
    expect(wait).toHaveBeenCalledWith(500);
  });

  it("reports the final startup failure after the retry window", async () => {
    const failure = new Error("backend exited");
    const check = vi.fn<() => Promise<never>>().mockRejectedValue(failure);

    await expect(
      waitForBackend(check, {
        attempts: 3,
        wait: () => Promise.resolve(),
      }),
    ).rejects.toBe(failure);
    expect(check).toHaveBeenCalledTimes(3);
  });

  it("stops retrying when the owning component is disposed", async () => {
    let active = true;
    const check = vi.fn<() => Promise<never>>().mockRejectedValue(new Error());

    await expect(
      waitForBackend(check, {
        attempts: 3,
        shouldContinue: () => active,
        wait: () => {
          active = false;
          return Promise.resolve();
        },
      }),
    ).rejects.toBeInstanceOf(Error);
    expect(check).toHaveBeenCalledTimes(1);
  });
});

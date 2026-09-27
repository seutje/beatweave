import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "./client";

describe("API client", () => {
  afterEach(() => vi.restoreAllMocks());

  it("decodes the backend health response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          status: "ok",
          service: "beatweave-backend",
          version: "0.1.0",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await expect(api.health()).resolves.toEqual({
      status: "ok",
      service: "beatweave-backend",
      version: "0.1.0",
    });
  });
});

import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "./client";

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

  it("preserves user-visible provider failures", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: "llm_output_truncated",
            message:
              "Ollama reached its output limit before completing the structured response.",
          },
        }),
        { status: 422, headers: { "Content-Type": "application/json" } },
      ),
    );

    await expect(api.planning.generate()).rejects.toEqual(
      new ApiError(
        "Ollama reached its output limit before completing the structured response.",
        422,
        "llm_output_truncated",
      ),
    );
  });
});

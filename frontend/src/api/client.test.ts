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
          version: "0.3.4",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    await expect(api.health()).resolves.toEqual({
      status: "ok",
      service: "beatweave-backend",
      version: "0.3.4",
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

  it("handles standard FastAPI errors without masking the response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Not Found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(api.wan2gp.config()).rejects.toEqual(
      new ApiError("Not Found", 404),
    );
  });

  it("turns network failures into actionable local-backend guidance", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(
      new TypeError("Failed to fetch"),
    );

    await expect(api.health()).rejects.toMatchObject({
      code: "backend_unavailable",
      status: 0,
      message: expect.stringContaining("local backend"),
    });
  });
});

import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConnectionStatus } from "./ConnectionStatus.jsx";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ConnectionStatus", () => {
  it("reports a successful local backend health check", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          status: "ok",
          service: "airscan-backend",
          host: "127.0.0.1",
          port: 8000,
        }),
      }),
    );

    render(<ConnectionStatus />);

    expect(
      await screen.findByText("Connected to airscan-backend at 127.0.0.1:8000."),
    ).toBeInTheDocument();
  });

  it("reports an unavailable backend when the health request fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Network error")));

    render(<ConnectionStatus />);

    expect(await screen.findByText(/Local backend unavailable/)).toBeInTheDocument();
  });
});
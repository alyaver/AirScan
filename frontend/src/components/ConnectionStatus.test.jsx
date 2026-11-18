import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConnectionStatus } from "./ConnectionStatus.jsx";

class FakeWebSocket {
  static instances = [];

  constructor(url) {
    this.url = url;
    this.listeners = new Map();
    this.close = vi.fn();
    FakeWebSocket.instances.push(this);
  }

  addEventListener(type, handler) {
    this.listeners.set(type, handler);
  }

  emit(type, event = {}) {
    this.listeners.get(type)?.(event);
  }
}

afterEach(() => {
  FakeWebSocket.instances = [];
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("ConnectionStatus", () => {
  it("renders the initial live-feed connection state and device distinction", () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);

    render(<ConnectionStatus />);

    expect(
      screen.getByText("Connecting to the local AirScan live feed…"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("serial-state")).toHaveTextContent("CONNECTING");
    expect(
      screen.getByText(/USB serial connectivity and scan activity, not connection to a Wi-Fi access point/),
    ).toBeInTheDocument();
    expect(FakeWebSocket.instances[0].url).toBe("ws://localhost:3000/api/live");
  });

  it("renders the connected scanning snapshot from the WebSocket", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    render(<ConnectionStatus />);

    const socket = FakeWebSocket.instances[0];
    await act(async () => {
      socket.emit("open");
      socket.emit("message", {
        data: JSON.stringify({
          event_type: "snapshot",
          connection: {
            state: "CONNECTED_SCANNING",
            selected_port: "COM7",
            last_message_at: "2026-11-18T12:00:00Z",
            last_scan_at: "2026-11-18T11:59:59Z",
          },
          live: {
            connection_state: "CONNECTED_SCANNING",
            last_scan_at: "2026-11-18T11:59:59Z",
          },
        }),
      });
    });

    expect(
      await screen.findByText("ESP32 USB serial device is connected and scanning."),
    ).toBeInTheDocument();
    expect(screen.getByTestId("serial-state")).toHaveTextContent("CONNECTED_SCANNING");
    expect(screen.getByText("COM7")).toBeInTheDocument();
    expect(screen.getAllByText(/11\/18\/2026/)).toHaveLength(2);
  });

  it("shows backend errors and retries after the WebSocket closes", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", FakeWebSocket);
    render(<ConnectionStatus />);

    const firstSocket = FakeWebSocket.instances[0];
    await act(async () => {
      firstSocket.emit("message", {
        data: JSON.stringify({
          event_type: "connection_state",
          connection: {
            state: "ERROR",
            last_error: "device disconnected",
          },
          live: {
            connection_state: "ERROR",
            error: "device disconnected",
          },
        }),
      });
    });
    expect(screen.getByText("device disconnected")).toBeInTheDocument();

    await act(async () => {
      firstSocket.emit("close");
    });
    expect(screen.getByText("Local backend live feed closed. Retrying…")).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it("closes the WebSocket and cancels retries on unmount", () => {
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", FakeWebSocket);
    const { unmount } = render(<ConnectionStatus />);
    const socket = FakeWebSocket.instances[0];

    act(() => {
      socket.emit("close");
    });
    unmount();
    vi.advanceTimersByTime(1000);

    expect(socket.close).toHaveBeenCalledOnce();
    expect(FakeWebSocket.instances).toHaveLength(1);
  });
});
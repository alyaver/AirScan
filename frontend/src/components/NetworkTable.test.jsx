import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NetworkTable } from "./NetworkTable.jsx";

class FakeWebSocket {
  static instances = [];

  constructor() {
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

function emitScan(socket, networks, completedAt = "2026-11-18T12:00:00Z") {
  socket.emit("message", {
    data: JSON.stringify({
      event_type: "scan_update",
      latest_scan: {
        scan_id: 1,
        completed_at: completedAt,
        networks,
      },
    }),
  });
}

afterEach(() => {
  FakeWebSocket.instances = [];
  vi.restoreAllMocks();
});

describe("NetworkTable", () => {
  it("renders an explicit empty-scan state", () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);

    render(<NetworkTable />);

    expect(screen.getByText("No networks were found in the latest completed scan.")).toBeInTheDocument();
    expect(screen.getByText("Last observed: Never")).toBeInTheDocument();
  });

  it("renders hidden and duplicate-SSID networks as separate BSSID rows", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    render(<NetworkTable />);

    await act(async () => {
      emitScan(FakeWebSocket.instances[0], [
        {
          ssid: "Same name",
          bssid: "AA:BB:CC:DD:EE:01",
          rssi_dbm: -72,
          channel: 1,
          encryption: "Open",
        },
        {
          ssid: "",
          bssid: "AA:BB:CC:DD:EE:02",
          rssi_dbm: -41,
          channel: 6,
          encryption: "Encrypted",
        },
        {
          ssid: "Same name",
          bssid: "AA:BB:CC:DD:EE:03",
          rssi_dbm: -55,
          channel: 11,
          encryption: "Encrypted",
        },
      ]);
    });

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getAllByText("Same name")).toHaveLength(2);
    expect(screen.getByText("Hidden network")).toBeInTheDocument();
    expect(screen.getByText("AA:BB:CC:DD:EE:01")).toBeInTheDocument();
    expect(screen.getByText("AA:BB:CC:DD:EE:03")).toBeInTheDocument();
    expect(screen.getByText("-41 dBm")).toBeInTheDocument();
    expect(screen.getAllByText(/11\/18\/2026/)).toHaveLength(4);
  });

  it("sorts the latest scan by RSSI or SSID", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    render(<NetworkTable />);

    await act(async () => {
      emitScan(FakeWebSocket.instances[0], [
        {
          ssid: "Zulu",
          bssid: "AA:BB:CC:DD:EE:01",
          rssi_dbm: -70,
          channel: 1,
          encryption: "Open",
        },
        {
          ssid: "Alpha",
          bssid: "AA:BB:CC:DD:EE:02",
          rssi_dbm: -40,
          channel: 6,
          encryption: "Encrypted",
        },
      ]);
    });

    const tableRows = () => screen.getAllByRole("row").slice(1);
    expect(tableRows()[0]).toHaveTextContent("Alpha");

    fireEvent.click(screen.getByRole("button", { name: "SSID" }));

    expect(tableRows()[0]).toHaveTextContent("Alpha");
    expect(tableRows()[1]).toHaveTextContent("Zulu");
  });

  it("replaces old rows when a later completed scan arrives and closes on unmount", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    const { unmount } = render(<NetworkTable />);
    const socket = FakeWebSocket.instances[0];

    await act(async () => {
      emitScan(socket, [
        {
          ssid: "Old network",
          bssid: "AA:BB:CC:DD:EE:01",
          rssi_dbm: -60,
          channel: 1,
          encryption: "Open",
        },
      ]);
      emitScan(socket, []);
    });

    expect(screen.queryByText("Old network")).not.toBeInTheDocument();
    expect(screen.getByText("No networks were found in the latest completed scan.")).toBeInTheDocument();

    unmount();
    expect(socket.close).toHaveBeenCalledOnce();
  });
});
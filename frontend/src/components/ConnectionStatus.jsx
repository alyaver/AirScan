import { useEffect, useState } from "react";

import { createLiveSocket } from "../api/websocket.js";

const INITIAL_STATUS = {
  kind: "checking",
  state: "CONNECTING",
  selectedPort: null,
  lastMessageAt: null,
  lastScanAt: null,
  message: "Connecting to the local AirScan live feed…",
};

const RETRY_DELAY_MS = 1000;

function formatTimestamp(value) {
  if (!value) {
    return "Never";
  }

  const timestamp = new Date(value);
  return Number.isNaN(timestamp.getTime()) ? "Unknown" : timestamp.toLocaleString();
}

function statusFromEvent(event) {
  const connection = event.connection ?? {};
  const live = event.live ?? {};
  const state = connection.state ?? live.connection_state ?? "ERROR";

  return {
    kind: state === "ERROR" ? "error" : "connected",
    state,
    selectedPort: connection.selected_port ?? null,
    lastMessageAt: connection.last_message_at ?? null,
    lastScanAt: live.last_scan_at ?? connection.last_scan_at ?? null,
    message:
      state === "DISCONNECTED"
        ? "ESP32 USB serial device disconnected."
        : state === "CONNECTED_SCANNING"
          ? "ESP32 USB serial device is connected and scanning."
          : state === "CONNECTED_IDLE"
            ? "ESP32 USB serial device is connected and idle."
            : state === "RECONNECTING"
              ? "Reconnecting to the ESP32 USB serial device…"
              : state === "CONNECTING"
                ? "Connecting to the ESP32 USB serial device…"
                : connection.last_error ?? live.error ?? "ESP32 USB serial device reported an error.",
  };
}

export function ConnectionStatus() {
  const [status, setStatus] = useState(INITIAL_STATUS);

  useEffect(() => {
    let active = true;
    let socket;
    let retryTimer;

    function connect() {
      if (!active) {
        return;
      }

      setStatus((current) => ({
        ...current,
        kind: "checking",
        state: "CONNECTING",
        message: "Connecting to the local AirScan live feed…",
      }));

      socket = createLiveSocket({
        onOpen: () => {
          if (active) {
            setStatus((current) => ({
              ...current,
              kind: "connected",
              message: "Connected to the local AirScan live feed.",
            }));
          }
        },
        onMessage: (messageEvent) => {
          if (!active) {
            return;
          }

          try {
            setStatus(statusFromEvent(JSON.parse(messageEvent.data)));
          } catch {
            setStatus((current) => ({
              ...current,
              kind: "error",
              message: "Received an invalid live update from the local backend.",
            }));
          }
        },
        onError: () => {
          if (active) {
            setStatus((current) => ({
              ...current,
              kind: "unavailable",
              message: "Local backend live feed unavailable. Retrying…",
            }));
          }
        },
        onClose: () => {
          if (!active) {
            return;
          }

          setStatus((current) => ({
            ...current,
            kind: "unavailable",
            state: "RECONNECTING",
            message: "Local backend live feed closed. Retrying…",
          }));
          retryTimer = window.setTimeout(connect, RETRY_DELAY_MS);
        },
      });
    }

    connect();

    return () => {
      active = false;
      window.clearTimeout(retryTimer);
      socket?.close();
    };
  }, []);

  return (
    <div aria-live="polite">
      <p>{status.message}</p>
      <dl>
        <div>
          <dt>Serial state</dt>
          <dd data-testid="serial-state">{status.state}</dd>
        </div>
        <div>
          <dt>Selected port</dt>
          <dd>{status.selectedPort ?? "None"}</dd>
        </div>
        <div>
          <dt>Last message</dt>
          <dd>{formatTimestamp(status.lastMessageAt)}</dd>
        </div>
        <div>
          <dt>Last scan</dt>
          <dd>{formatTimestamp(status.lastScanAt)}</dd>
        </div>
      </dl>
      <p>
        This status represents USB serial connectivity and scan activity, not
        connection to a Wi-Fi access point.
      </p>
    </div>
  );
}
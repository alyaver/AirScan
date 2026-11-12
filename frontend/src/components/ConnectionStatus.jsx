import { useEffect, useState } from "react";

import { getBackendHealth } from "../api/client.js";

const INITIAL_STATUS = {
  kind: "checking",
  message: "Checking local backend availability…",
};

export function ConnectionStatus() {
  const [status, setStatus] = useState(INITIAL_STATUS);

  useEffect(() => {
    let active = true;

    async function checkBackend() {
      try {
        const health = await getBackendHealth();
        if (active) {
          setStatus({
            kind: "connected",
            message: `Connected to ${health.service} at ${health.host}:${health.port}.`,
          });
        }
      } catch {
        if (active) {
          setStatus({
            kind: "unavailable",
            message:
              "Local backend unavailable. Start the AirScan backend on 127.0.0.1:8000 and refresh this page.",
          });
        }
      }
    }

    checkBackend();

    return () => {
      active = false;
    };
  }, []);

  return (
    <p aria-live="polite">{status.message}</p>
  );
}
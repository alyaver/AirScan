import { useEffect, useMemo, useState } from "react";

import { createLiveSocket } from "../api/websocket.js";

const INITIAL_SCAN = {
  lastObservedAt: null,
  networks: [],
};

function formatTimestamp(value) {
  if (!value) {
    return "Never";
  }

  const timestamp = new Date(value);
  return Number.isNaN(timestamp.getTime()) ? "Unknown" : timestamp.toLocaleString();
}

function networkName(ssid) {
  return ssid === "" ? "Hidden network" : ssid;
}

function sortNetworks(networks, sortBy) {
  return [...networks].sort((first, second) => {
    if (sortBy === "ssid") {
      return networkName(first.ssid).localeCompare(networkName(second.ssid));
    }

    return second.rssi_dbm - first.rssi_dbm || first.bssid.localeCompare(second.bssid);
  });
}

export function NetworkTable() {
  const [scan, setScan] = useState(INITIAL_SCAN);
  const [sortBy, setSortBy] = useState("rssi");

  useEffect(() => {
    let active = true;
    const socket = createLiveSocket({
      onOpen: () => {},
      onClose: () => {},
      onError: () => {},
      onMessage: (messageEvent) => {
        if (!active) {
          return;
        }

        try {
          const event = JSON.parse(messageEvent.data);
          const latestScan = event.latest_scan;
          if (!latestScan || latestScan.scan_id === null) {
            return;
          }

          setScan({
            lastObservedAt: latestScan.completed_at,
            networks: latestScan.networks ?? [],
          });
        } catch {
          // ConnectionStatus reports transport errors; ignore malformed table updates.
        }
      },
    });

    return () => {
      active = false;
      socket.close();
    };
  }, []);

  const networks = useMemo(() => sortNetworks(scan.networks, sortBy), [scan.networks, sortBy]);

  return (
    <section aria-labelledby="networks-heading">
      <h2 id="networks-heading">Nearby networks</h2>
      <p>Last observed: {formatTimestamp(scan.lastObservedAt)}</p>
      <p>
        Sort by:{" "}
        <button type="button" onClick={() => setSortBy("rssi")} disabled={sortBy === "rssi"}>
          RSSI
        </button>{" "}
        <button type="button" onClick={() => setSortBy("ssid")} disabled={sortBy === "ssid"}>
          SSID
        </button>
      </p>
      {networks.length === 0 ? (
        <p>No networks were found in the latest completed scan.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">SSID</th>
              <th scope="col">BSSID</th>
              <th scope="col">RSSI</th>
              <th scope="col">Channel</th>
              <th scope="col">Encryption</th>
              <th scope="col">Last observed</th>
            </tr>
          </thead>
          <tbody>
            {networks.map((network) => (
              <tr key={network.bssid}>
                <td title={networkName(network.ssid)}>{networkName(network.ssid)}</td>
                <td>{network.bssid}</td>
                <td>{network.rssi_dbm} dBm</td>
                <td>{network.channel}</td>
                <td>{network.encryption}</td>
                <td>{formatTimestamp(scan.lastObservedAt)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
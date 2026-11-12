import { ConnectionStatus } from "./components/ConnectionStatus.jsx";

export default function App() {
  return (
    <main>
      <header>
        <p>Local Wi-Fi scanning dashboard</p>
        <h1>AirScan</h1>
        <p>
          The dashboard foundation is ready. Live Wi-Fi scan results and
          recording controls will be added in later milestones.
        </p>
      </header>

      <section aria-labelledby="connection-heading">
        <h2 id="connection-heading">Backend connection</h2>
        <ConnectionStatus />
      </section>

      <section aria-labelledby="next-heading">
        <h2 id="next-heading">Coming next</h2>
        <p>
          ESP32 serial communication and live scan data are not connected to
          this dashboard yet.
        </p>
      </section>
    </main>
  );
}
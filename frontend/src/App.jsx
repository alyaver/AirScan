import { ConnectionStatus } from "./components/ConnectionStatus.jsx";
import { NetworkTable } from "./components/NetworkTable.jsx";

export default function App() {
  return (
    <main>
      <header>
        <p>Local Wi-Fi scanning dashboard</p>
        <h1>AirScan</h1>
        <p>
          View nearby Wi-Fi networks received from the connected ESP32 device.
        </p>
      </header>

      <section aria-labelledby="connection-heading">
        <h2 id="connection-heading">ESP32 serial device status</h2>
        <ConnectionStatus />
      </section>

      <NetworkTable />
    </main>
  );
}
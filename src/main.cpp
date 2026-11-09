
#include <Arduino.h>
#include <WiFi.h>

void setup() {
    Serial.begin(115200);
    delay(1000);

    WiFi.mode(WIFI_STA);
    WiFi.disconnect();

    Serial.println("AirScan initialized!");
    Serial.println("Starting Wi-Fi scanner...");
}

void loop() {
    Serial.println("\nScanning nearby Wi-Fi networks...");

    int networkCount = WiFi.scanNetworks();

    if (networkCount < 0) {
        Serial.println("Wi-Fi scan failed.");
    } else {
        Serial.printf("Found %d networks:\n\n", networkCount);

        for (int i = 0; i < networkCount; i++) {
            Serial.printf("Network %d\n", i + 1);
            Serial.printf("  SSID: %s\n", WiFi.SSID(i).c_str());
            Serial.printf("  BSSID: %s\n", WiFi.BSSIDstr(i).c_str());
            Serial.printf("  RSSI: %d dBm\n", WiFi.RSSI(i));
            Serial.printf("  Channel: %d\n", WiFi.channel(i));
            Serial.printf("  Encryption: %s\n",
                WiFi.encryptionType(i) == WIFI_AUTH_OPEN
                    ? "Open" : "Encrypted");
            Serial.println();
        }
    }

    WiFi.scanDelete();
    delay(5000);
}

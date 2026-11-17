
#include <Arduino.h>
#include <WiFi.h>

namespace {

constexpr uint8_t kProtocolVersion = 1;
constexpr char kFirmwareVersion[] = "0.1.0";
constexpr unsigned long kMinimumScanIntervalMs = 5000;

uint32_t nextScanId = 1;
unsigned long lastScanStartedAt = 0;
bool scanInProgress = false;

void writeJsonString(const String& value) {
    Serial.print('"');

    for (size_t index = 0; index < value.length(); ++index) {
        const unsigned char character = value[index];

        switch (character) {
            case '"':
                Serial.print("\\\"");
                break;
            case '\\':
                Serial.print("\\\\");
                break;
            case '\b':
                Serial.print("\\b");
                break;
            case '\f':
                Serial.print("\\f");
                break;
            case '\n':
                Serial.print("\\n");
                break;
            case '\r':
                Serial.print("\\r");
                break;
            case '\t':
                Serial.print("\\t");
                break;
            default:
                if (character < 0x20) {
                    Serial.printf("\\u%04X", character);
                } else {
                    Serial.write(character);
                }
        }
    }

    Serial.print('"');
}

void writeCommonMessageFields(const char* messageType) {
    Serial.print("{\"protocol_version\":");
    Serial.print(kProtocolVersion);
    Serial.print(",\"message_type\":");
    writeJsonString(messageType);
    Serial.print(",\"device_timestamp_ms\":");
    Serial.print(millis());
}

String deviceId() {
    char value[19];
    const uint64_t macAddress = ESP.getEfuseMac();

    snprintf(
        value,
        sizeof(value),
        "esp32-%012llX",
        static_cast<unsigned long long>(macAddress)
    );

    return String(value);
}

void emitDeviceReady() {
    writeCommonMessageFields("device_ready");
    Serial.print(",\"device_id\":");
    writeJsonString(deviceId());
    Serial.print(",\"firmware_version\":");
    writeJsonString(kFirmwareVersion);
    Serial.println("}");
}

void emitScanResult(uint32_t scanId, int networkCount) {
    writeCommonMessageFields("scan_result");
    Serial.print(",\"scan_id\":");
    Serial.print(scanId);
    Serial.print(",\"networks\":[");

    for (int index = 0; index < networkCount; ++index) {
        if (index > 0) {
            Serial.print(',');
        }

        Serial.print("{\"ssid\":");
        writeJsonString(WiFi.SSID(index));
        Serial.print(",\"bssid\":");
        writeJsonString(WiFi.BSSIDstr(index));
        Serial.print(",\"rssi_dbm\":");
        Serial.print(WiFi.RSSI(index));
        Serial.print(",\"channel\":");
        Serial.print(WiFi.channel(index));
        Serial.print(",\"encryption\":");
        writeJsonString(
            WiFi.encryptionType(index) == WIFI_AUTH_OPEN ? "Open" : "Encrypted"
        );
        Serial.print('}');
    }

    Serial.println("]}");
}

void emitScanError(uint32_t scanId, int errorCode) {
    writeCommonMessageFields("scan_error");
    Serial.print(",\"scan_id\":");
    Serial.print(scanId);
    Serial.print(",\"error_code\":\"wifi_scan_failed\",");
    Serial.print("\"message\":");
    writeJsonString("WiFi.scanNetworks returned " + String(errorCode) + ".");
    Serial.println("}");
}

bool isScanDue(unsigned long now) {
    return now - lastScanStartedAt >= kMinimumScanIntervalMs;
}

}  // namespace

void setup() {
    Serial.begin(115200);
    delay(1000);

    WiFi.mode(WIFI_STA);
    WiFi.disconnect();

    lastScanStartedAt = millis() - kMinimumScanIntervalMs;
    emitDeviceReady();
}

void loop() {
    const unsigned long now = millis();
    if (scanInProgress || !isScanDue(now)) {
        return;
    }

    scanInProgress = true;
    lastScanStartedAt = now;

    const uint32_t scanId = nextScanId++;
    const int networkCount = WiFi.scanNetworks();

    if (networkCount < 0) {
        emitScanError(scanId, networkCount);
    } else {
        emitScanResult(scanId, networkCount);
    }

    WiFi.scanDelete();
    scanInProgress = false;
}

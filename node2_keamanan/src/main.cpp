/*
  Sistem Evacuation / Fire Alarm IoT - Firmware gabungan satu ESP32-C3
  Board: ESP32-C3 Super Mini (board normal, jangan gunakan board yang overheat)

  Topic MQTT dipertahankan agar kompatibel dengan dashboard Python:
    Publish : sensor/gas, sensor/suhu, sistem/rfid
    Subscribe: sistem/alarm (payload: BAHAYA atau AMAN)

  Catatan:
  - DFPlayer menggunakan UART1 pada GPIO0/GPIO1 agar terpisah dari UART0/Serial Monitor.
  - Jika microSD DFPlayer rusak/tidak terpasang, fungsi sensor, RFID, Wi-Fi, MQTT tetap berjalan;
    pemutaran audio ditandai belum siap.
  - Periksa bahwa output analog MQ-2 tidak pernah melebihi 3,3 V sebelum masuk ke GPIO2.
*/

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_AHTX0.h>
#include <SPI.h>
#include <MFRC522.h>
#include <DFRobotDFPlayerMini.h>
#include <math.h>

// ---------------- WIFI & MQTT ----------------
const char* WIFI_SSID     = "Samsom a24";
const char* WIFI_PASSWORD = "1234567890";
const char* MQTT_SERVER   = "10.85.199.87"; // IPv4 laptop yang menjalankan Mosquitto
const uint16_t MQTT_PORT  = 1883;
const char* MQTT_CLIENT_ID = "ESP32_EnvSecurity_One";

WiFiClient espClient;
PubSubClient mqttClient(espClient);

// ---------------- PIN ESP32-C3 SUPER MINI ----------------
// Dipertahankan dari program Node 1
static const int PIN_MQ2 = 2;     // AO MQ-2 -> GPIO2 (maksimum 3,3 V)
static const int SDA_PIN = 8;     // AHT10 SDA
static const int SCL_PIN = 9;     // AHT10 SCL

// Dipertahankan dari program Node 2 (MFRC522)
static const int RFID_SS_PIN   = 7;
static const int RFID_RST_PIN  = 10;
static const int RFID_SCK_PIN  = 4;
static const int RFID_MISO_PIN = 5;
static const int RFID_MOSI_PIN = 6;

// UART1 DFPlayer Mini. Hubungkan TX DFPlayer -> GPIO0 (RX ESP32),
// dan GPIO1 (TX ESP32) -> RX DFPlayer.
static const int DFPLAYER_RX_PIN = 0;
static const int DFPLAYER_TX_PIN = 1;

// ---------------- OBJEK PERANGKAT ----------------
Adafruit_AHTX0 aht;
MFRC522 mfrc522(RFID_SS_PIN, RFID_RST_PIN);
HardwareSerial dfSerial(1);
DFRobotDFPlayerMini dfPlayer;

bool ahtReady = false;
bool dfPlayerReady = false;
bool alarmAktif = false;

// ---------------- TIMER ----------------
unsigned long lastGasRead = 0;
unsigned long lastTempRead = 0;
unsigned long lastRfidScan = 0;
unsigned long lastWifiRetry = 0;
unsigned long lastMqttAttempt = 0;

const unsigned long GAS_INTERVAL_MS  = 1000;
const unsigned long TEMP_INTERVAL_MS = 5000;
const unsigned long RFID_INTERVAL_MS = 100;
const unsigned long WIFI_RETRY_MS    = 10000;
const unsigned long MQTT_RETRY_MS    = 5000;

// ---------------- MQTT CALLBACK ----------------
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String topicName(topic);
  String message;
  message.reserve(length + 1);
  for (unsigned int i = 0; i < length; ++i) {
    message += static_cast<char>(payload[i]);
  }

  Serial.print("MQTT masuk [");
  Serial.print(topicName);
  Serial.print("]: ");
  Serial.println(message);

  if (topicName != "sistem/alarm") return;

  if (message == "BAHAYA") {
    alarmAktif = true;
    Serial.println("Status alarm: BAHAYA");
    if (dfPlayerReady) {
      // File alarm pada microSD: /mp3/0001.mp3
      dfPlayer.playMp3Folder(1);
      dfPlayer.enableLoop();  // Ulangi track yang sedang diputar.
      Serial.println("Alarm mulai: /mp3/0001.mp3, mode ulang aktif.");
    } else {
      Serial.println("DFPlayer belum siap; perintah suara tidak dapat dijalankan.");
      Serial.println("Periksa microSD dan UART DFPlayer.");
    }
  } else if (message == "AMAN") {
    alarmAktif = false;
    if (dfPlayerReady) {
      dfPlayer.disableLoop();
      dfPlayer.stop();
      Serial.println("Alarm dihentikan dari GUI; mode ulang dimatikan.");
    }
    Serial.println("Status alarm: AMAN");
  }
}

// ---------------- WIFI ----------------
void startWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Menghubungkan Wi-Fi ke: ");
  Serial.println(WIFI_SSID);

  const unsigned long startTime = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startTime < 12000) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Wi-Fi connected. IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("Wi-Fi belum tersambung. Firmware tetap berjalan dan akan mencoba lagi.");
    lastWifiRetry = millis();
  }
}

// Koneksi dipelihara secara berkala agar fungsi pembacaan sensor tidak terkunci
// oleh loop reconnect MQTT yang menunggu tanpa batas.
void maintainConnections() {
  if (WiFi.status() != WL_CONNECTED) {
    if (millis() - lastWifiRetry >= WIFI_RETRY_MS) {
      lastWifiRetry = millis();
      Serial.println("Wi-Fi terputus; mencoba menyambung ulang...");
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    }
    return;
  }

  if (!mqttClient.connected() && millis() - lastMqttAttempt >= MQTT_RETRY_MS) {
    lastMqttAttempt = millis();
    Serial.print("Mencoba koneksi MQTT ke ");
    Serial.print(MQTT_SERVER);
    Serial.print(':');
    Serial.println(MQTT_PORT);

    if (mqttClient.connect(MQTT_CLIENT_ID)) {
      Serial.println("MQTT connected.");
      if (mqttClient.subscribe("sistem/alarm")) {
        Serial.println("Subscribe sistem/alarm: OK");
      } else {
        Serial.println("Subscribe sistem/alarm: GAGAL");
      }
    } else {
      Serial.print("MQTT gagal, rc=");
      Serial.println(mqttClient.state());
    }
  }

  if (mqttClient.connected()) {
    mqttClient.loop();
  }
}

// ---------------- MQTT PUBLISH ----------------
bool publishJson(const char* topic, const String& payload) {
  if (!mqttClient.connected()) {
    Serial.print("Publish dilewati, MQTT belum tersambung. Topic: ");
    Serial.println(topic);
    return false;
  }

  const bool ok = mqttClient.publish(topic, payload.c_str());
  Serial.print("-> Pub ");
  Serial.print(topic);
  Serial.print(ok ? " OK: " : " GAGAL: ");
  Serial.println(payload);
  return ok;
}

// ---------------- SENSOR MQ-2 ----------------
void readAndPublishGas() {
  const int gasValue = analogRead(PIN_MQ2);
  String payload = "{\"device\":\"Node_1\",\"tipe\":\"gas\",\"nilai\":";
  payload += String(gasValue);
  payload += "}";
  publishJson("sensor/gas", payload);
}

// ---------------- SENSOR AHT10/AHTX0 ----------------
void readAndPublishTemperature() {
  if (!ahtReady) return;

  sensors_event_t humidityEvent, temperatureEvent;
  aht.getEvent(&humidityEvent, &temperatureEvent);

  const float temperature = temperatureEvent.temperature;
  const float humidity = humidityEvent.relative_humidity;
  if (isnan(temperature) || isnan(humidity)) {
    Serial.println("Pembacaan AHT10 tidak valid; data tidak dipublikasikan.");
    return;
  }

  String payload = "{\"device\":\"Node_1\",\"suhu\":";
  payload += String(temperature, 2);
  payload += ",\"humidity\":";
  payload += String(humidity, 2);
  payload += "}";
  publishJson("sensor/suhu", payload);
}

// ---------------- RFID MFRC522 ----------------
void scanRFID() {
  if (!mfrc522.PICC_IsNewCardPresent()) return;
  if (!mfrc522.PICC_ReadCardSerial()) return;

  String uid;
  uid.reserve(mfrc522.uid.size * 2);
  char hexByte[3];
  for (byte i = 0; i < mfrc522.uid.size; ++i) {
    snprintf(hexByte, sizeof(hexByte), "%02X", mfrc522.uid.uidByte[i]);
    uid += hexByte;
  }

  Serial.print("Kartu RFID terdeteksi. UID: ");
  Serial.println(uid);

  String payload = "{\"device\":\"Node_2\",\"rfid\":\"";
  payload += uid;
  payload += "\"}";
  publishJson("sistem/rfid", payload);

  // Kartu berfungsi sebagai reset alarm seperti pada firmware Node 2 awal.
  if (alarmAktif) {
    alarmAktif = false;
    if (dfPlayerReady) {
      dfPlayer.disableLoop();
      dfPlayer.stop();
    }
    if (mqttClient.connected()) {
      const bool sent = mqttClient.publish("sistem/alarm", "AMAN");
      Serial.println(sent ? "RFID: status AMAN terkirim ke MQTT." : "RFID: gagal mengirim status AMAN.");
    } else {
      Serial.println("RFID: MQTT belum tersambung; status AMAN belum terkirim.");
    }
  }

  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();
}

// ---------------- SETUP ----------------
void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println();
  Serial.println("============================================");
  Serial.println("Sistem Evacuation / Fire Alarm IoT");
  Serial.println("Firmware gabungan: satu ESP32-C3");
  Serial.println("============================================");

  pinMode(PIN_MQ2, INPUT);
  analogReadResolution(12);

  // AHT10 menggunakan I2C pada GPIO8 (SDA) dan GPIO9 (SCL).
  Wire.begin(SDA_PIN, SCL_PIN);
  ahtReady = aht.begin(&Wire);
  Serial.println(ahtReady ? "AHT10 OK!" : "AHT10 tidak terdeteksi; data suhu dilewati.");

  // MFRC522 menggunakan SPI dengan pin custom seperti pada firmware Node 2.
  SPI.begin(RFID_SCK_PIN, RFID_MISO_PIN, RFID_MOSI_PIN, RFID_SS_PIN);
  mfrc522.PCD_Init();
  delay(50);
  byte version = mfrc522.PCD_ReadRegister(MFRC522::VersionReg);
  Serial.print("MFRC522 VersionReg: 0x");
  Serial.println(version, HEX);
  if (version == 0x00 || version == 0xFF) {
    Serial.println("Peringatan: MFRC522 belum terkonfirmasi; periksa kabel dan suplai 3,3 V.");
  } else {
    Serial.println("Inisialisasi MFRC522 selesai.");
  }

  // UART1 DFPlayer: GPIO0 sebagai RX ESP32, GPIO1 sebagai TX ESP32.
  dfSerial.begin(9600, SERIAL_8N1, DFPLAYER_RX_PIN, DFPLAYER_TX_PIN);
  dfPlayer.setTimeOut(500);
  Serial.println("Memeriksa DFPlayer Mini (microSD yang rusak dapat membuat tes gagal)...");
  dfPlayerReady = dfPlayer.begin(dfSerial, true, true);
  if (dfPlayerReady) {
    dfPlayer.setTimeOut(500);
    dfPlayer.volume(25);
    Serial.println("DFPlayer Mini siap.");
  } else {
    Serial.println("DFPlayer belum siap. Sensor, RFID, Wi-Fi, dan MQTT tetap dilanjutkan.");
    Serial.println("Catatan: inisialisasi DFPlayer belum membuktikan audio berfungsi.");
  }

  mqttClient.setServer(MQTT_SERVER, MQTT_PORT);
  mqttClient.setCallback(mqttCallback);
  mqttClient.setBufferSize(512);
  mqttClient.setKeepAlive(30);

  startWiFi();
  Serial.println("Setup selesai; masuk loop utama.");
}

// ---------------- LOOP ----------------
void loop() {
  maintainConnections();

  const unsigned long now = millis();

  if (now - lastGasRead >= GAS_INTERVAL_MS) {
    lastGasRead = now;
    readAndPublishGas();
  }

  if (now - lastTempRead >= TEMP_INTERVAL_MS) {
    lastTempRead = now;
    readAndPublishTemperature();
  }

  if (now - lastRfidScan >= RFID_INTERVAL_MS) {
    lastRfidScan = now;
    scanRFID();
  }

  // Membaca event yang dikirim oleh DFPlayer jika modul sudah siap.
  if (dfPlayerReady && dfPlayer.available()) {
    const uint8_t type = dfPlayer.readType();
    const int value = dfPlayer.read();
    Serial.print("Event DFPlayer, type=");
    Serial.print(type);
    Serial.print(", value=");
    Serial.println(value);

    // Beberapa modul DFPlayer/clone tidak mengulang track otomatis.
    // Jika audio selesai selama status BAHAYA, mulai kembali file yang sama.
    // Pemeriksaan event ini tidak memakai delay() dan tetap menjaga loop sensor.
    if (type == DFPlayerPlayFinished && alarmAktif) {
      dfPlayer.playMp3Folder(1);
      dfPlayer.enableLoop();
      Serial.println("Alarm masih BAHAYA: memutar ulang /mp3/0001.mp3.");
    }
  }
}

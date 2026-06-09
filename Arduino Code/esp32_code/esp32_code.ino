#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>

#define PIR_PIN 13

const char* ssid     = "VW Tiguan";
const char* password = "Pe1La2Na6";
const char* pc_url   = "http://192.168.1.213:5000/motion"; // <-- stavi IP svog PC-a

void setup() {
  Serial.begin(115200);
  pinMode(PIR_PIN, INPUT);

  WiFi.begin(ssid, password);
  Serial.print("Spajam na WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nSpojeno! IP: " + WiFi.localIP().toString());
}

void loop() {
  if (digitalRead(PIR_PIN) == HIGH) {
    Serial.println("Pokret! Šaljem signal na PC...");

    HTTPClient http;
    http.begin(pc_url);
    int code = http.POST("");
    Serial.println("PC odgovorio s kodom: " + String(code));
    http.end();

    delay(2000);
  }
}
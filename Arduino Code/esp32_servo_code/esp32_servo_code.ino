#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <ESP32Servo.h>
#include <ArduinoJson.h>

#define PIR_PIN        13
#define INDUCTIVE_PIN  34
#define SERVO1_PIN     25
#define SERVO2_PIN     26

const char* ssid     = "VW Tiguan";
const char* password = "Pe1La2Na6";
const char* pc_url   = "http://192.168.1.XXX:5000/motion";

Servo servo1;
Servo servo2;
WebServer server(80);

void servoAction(String result) {
  Serial.println("Servo akcija: " + result);

  //if (result == "metal") {
  //  servo1.write(45); // pomiče tobogan
  //  servo2.write(180); // pomiče dno od čaše 1
  //} else if (result == "red") {
  if (result == "red") {
    servo1.write(90); // pomiče tobogan
    servo2.write(180); // pomiče dno od čaše 1
  } else if (result == "round") {
    servo1.write(135); // pomiče tobogan
    servo2.write(180); // pomiče dno od čaše 1
  } else {
    // ništa prepoznato — ne radi ništa ili default
    servo1.write(0);
    servo2.write(0);
  }

  delay(3000);
  servo1.write(0);
  servo2.write(0);
}

void handleServo() {
  if (!server.hasArg("plain")) {
    server.send(400, "text/plain", "No body");
    return;
  }

  StaticJsonDocument<64> doc;
  deserializeJson(doc, server.arg("plain"));
  String result = doc["result"].as<String>();
  servoAction(result);
  server.send(200, "text/plain", "OK");
}

void sendMotionSignal() {
  HTTPClient http;
  http.begin(pc_url);
  int code = http.POST("");
  Serial.println("PC odgovorio: " + String(code));
  http.end();
}

void setup() {
  Serial.begin(115200);
  pinMode(PIR_PIN, INPUT);
  pinMode(INDUCTIVE_PIN, INPUT);

  servo1.attach(SERVO1_PIN);
  servo2.attach(SERVO2_PIN);
  servo1.write(0);
  servo2.write(0);

  WiFi.begin(ssid, password);
  Serial.print("Spajam na WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nSpojeno! IP: " + WiFi.localIP().toString());

  server.on("/servo", HTTP_POST, handleServo);
  server.begin();
}

void loop() {
  server.handleClient();

  // Induktivni senzor ima prioritet
  bool metal = digitalRead(INDUCTIVE_PIN) == LOW; // NPN: LOW = detektira
  if (metal) {
    Serial.println("Metal detektiran!");
    servoAction("metal");
    delay(2000); // čekaj da objekt prođe
    return;      // preskoči PIR provjeru
  }

  // Ako nije metal, čekaj PIR
  if (digitalRead(PIR_PIN) == HIGH) {
    Serial.println("Pokret detektiran, šaljem na PC za vizualnu detekciju...");
    sendMotionSignal();
    delay(2000);
  }
}
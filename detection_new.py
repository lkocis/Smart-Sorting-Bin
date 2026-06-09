import cv2
import requests
import numpy as np
import os
from datetime import datetime
import time
import threading
from flask import Flask
from flask import request as freq

CAM_URL = "http://192.168.1.162/capture"
ESP32_URL = "http://192.168.1.161"
FOLDER_PATH = "C:/Users/LKocis/Downloads/ESP 32 CAM detection/ESP32-CAM-detection/pictures"

event = threading.Event()
latest_frame = None
frame_lock = threading.Lock()

app = Flask(__name__)

@app.route("/motion", methods=["POST"])
def motion():
    print("Signal primljen od ESP32!")
    event.set()
    return "OK", 200

def run_flask():
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

def ensure_folder():
    os.makedirs(FOLDER_PATH, exist_ok=True)

def detect_red_color(img):
    hsv_img = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower_red1 = np.array([0, 100, 100])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([160, 100, 100])
    upper_red2 = np.array([180, 255, 255])
    mask1 = cv2.inRange(hsv_img, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv_img, lower_red2, upper_red2)
    red_mask = cv2.add(mask1, mask2)
    kernel = np.ones((5, 5), "uint8")
    red_mask = cv2.dilate(red_mask, kernel)
    contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    found = False
    for contour in contours:
        if cv2.contourArea(contour) > 500:
            x, y, w, h = cv2.boundingRect(contour)
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 255), 2)
            cv2.putText(img, "Red Object", (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            found = True
    return found

def detect_round(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (9, 9), 2)
    circles = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT, dp=1, minDist=20,
        param1=50, param2=30, minRadius=10, maxRadius=200
    )
    found = False
    if circles is not None:
        circles = np.uint16(np.around(circles))
        for i in circles[0, :]:
            cv2.circle(img, (i[0], i[1]), i[2], (0, 255, 0), 2)
            cv2.circle(img, (i[0], i[1]), 2, (0, 0, 255), 3)
            found = True
    return found

def take_picture():
    global latest_frame
    print("Cekam signal od ESP32...")
    print("Pokreni ESP32 s PIR senzorom.")

    while True:
        event.wait()

        try:
            response = requests.get(CAM_URL, timeout=5)
            if response.status_code == 200:
                img_array = np.array(bytearray(response.content), dtype=np.uint8)
                frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

                if frame is not None:
                    with frame_lock:
                        latest_frame = frame.copy()

                    cv2.imshow("ESP32-CAM", frame)

                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    file_name = f"img_{timestamp}.jpg"
                    cv2.imwrite(os.path.join(FOLDER_PATH, file_name), frame)
                    print(f"Slika spremljena: {file_name}")

        except requests.exceptions.Timeout:
            print("CAM nije odgovorio.")
        except Exception as e:
            print(f"Greška: {e}")

        event.clear()

        if cv2.waitKey(1) & 0xFF == 27:
            break

    cv2.destroyAllWindows()

def detection_worker():
    while True:
        event.wait()
        try:
            with frame_lock:
                if latest_frame is None:
                    event.clear()
                    continue
                img = latest_frame.copy()

            if detect_red_color(img):
                print("--- Detekcija: Crvena boja!")
                requests.post(f"{ESP32_URL}/servo", json={"result": "red"}, timeout=2)
            elif detect_round(img):
                print("--- Detekcija: Okrugli objekt!")
                requests.post(f"{ESP32_URL}/servo", json={"result": "round"}, timeout=2)
            else:
                print("--- Detekcija: Ništa nije pronađeno.")
                requests.post(f"{ESP32_URL}/servo", json={"result": "none"}, timeout=2)

            start_time = time.time()
            while time.time() - start_time < 4:
                cv2.imshow("Detection Result", img)
                if cv2.waitKey(1) & 0xFF == 27:
                    break

            cv2.destroyWindow("Detection Result")
            print("Spreman za sljedeći signal...")

        except Exception as e:
            print(f"Greška u detekciji: {e}")

        event.clear()

if __name__ == "__main__":
    ensure_folder()
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=detection_worker, daemon=True).start()
    take_picture()
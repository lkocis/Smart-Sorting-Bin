import cv2
import requests
import numpy as np
import time
import threading
import io
from PIL import Image
from flask import Flask

CAM_URL   = "http://172.20.10.9/capture"
ESP32_URL = "http://172.20.10.10"

motion_event = threading.Event()  
app = Flask(__name__)

@app.route("/motion", methods=["POST"])
def motion():
    print("\n[PIR] Signal primljen od ESP32!")
    motion_event.set()  
    return "OK", 200

def run_flask():
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

def detect_green_color(img):
    hsv_img = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # Zelena je jedan kontinuirani raspon nijanse (nema "wraparound" problem kao crvena)
    lower_green = np.array([36, 100, 100])
    upper_green = np.array([85, 255, 255])
    mask = cv2.inRange(hsv_img, lower_green, upper_green)

    kernel = np.ones((5, 5), "uint8")
    mask = cv2.dilate(mask, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    found = False
    for contour in contours:
        if cv2.contourArea(contour) > 500:
            x, y, w, h = cv2.boundingRect(contour)
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(img, "Green Object", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            found = True
    return found

def detect_round(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (9, 9), 2)
    circles = cv2.HoughCircles(
        blurred, cv2.HOUGH_GRADIENT, dp=1, minDist=50,
        param1=60, param2=50, minRadius=15, maxRadius=150
    )
    found = False
    if circles is not None:
        circles = np.uint16(np.around(circles))
        for i in circles[0, :]:
            cv2.circle(img, (i[0], i[1]), i[2], (0, 255, 0), 2)
            cv2.circle(img, (i[0], i[1]), 2, (0, 0, 255), 3)
            found = True
    return found

def dohvati_sliku():
    """Pokušava dohvatiti i dekodirati sliku s kamere. Vraća img ili None."""
    # Flushaj buffer kamere
    for _ in range(3):
        try:
            requests.get(CAM_URL, timeout=2)
            time.sleep(0.1)
        except:
            pass

    time.sleep(0.3)

    response = None
    for pokusaj in range(1, 4):
        try:
            response = requests.get(CAM_URL, timeout=4)
            if response.status_code == 200:
                break
        except requests.exceptions.RequestException:
            print(f"   [UPOZORENJE] Pokušaj {pokusaj}/3 nije uspio. Ponavljam...")
            time.sleep(0.5)

    if response is None or response.status_code != 200:
        print("[KRAJNJA GREŠKA] Kamera nedostupna.")
        return None

    print(f"[DEBUG] Response status: {response.status_code}")
    print(f"[DEBUG] Content-Type: {response.headers.get('Content-Type', 'N/A')}")
    print(f"[DEBUG] Veličina odgovora: {len(response.content)} bytes")

    # PRIVREMENO - spremi raw bytes na disk za inspekciju
    with open("debug_slika.jpg", "wb") as f:
        f.write(response.content)
    print("[DEBUG] Slika spremljena kao debug_slika.jpg")

    # Pokušaj dekodiranja s OpenCV
    img_array = np.array(bytearray(response.content), dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

    # Fallback na PIL ako OpenCV ne uspije
    if img is None:
        print("[UPOZORENJE] OpenCV nije uspio dekodirati, pokušavam s PIL...")
        try:
            pil_img = Image.open(io.BytesIO(response.content)).convert("RGB")
            img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            print("[INFO] PIL dekodiranje uspješno.")
        except Exception as pil_err:
            print(f"[GREŠKA] PIL također nije uspio: {pil_err}")
            return None

    return img

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    print("Sustav spreman. Čekam PIR signal s ESP32...")

    while True:
        motion_event.wait()
        motion_event.clear()

        print("[AKCIJA] Čistim buffer i uzimam najnoviju sliku...")
        time.sleep(1.5)

        img = dohvati_sliku()

        if img is None:
            print("[GREŠKA] Slika nije dostupna. Čekam novi predmet...")
            continue

        try:
            # DETEKCIJA
            result_str = "none"
            if detect_green_color(img):
                result_str = "green"
                print("--- Rezultat: ZELENO")
            elif detect_round(img):
                result_str = "round"
                print("--- Rezultat: OKRUGLO")
            else:
                print("--- Rezultat: NIŠTA")

            # PRIKAZ PROZORA NA 3 SEKUNDE
            cv2.namedWindow("Rezultat Detekcije", cv2.WINDOW_AUTOSIZE)
            cv2.imshow("Rezultat Detekcije", img)
            cv2.waitKey(3000)
            cv2.destroyWindow("Rezultat Detekcije")
            print("[INFO] Prozor zatvoren.")

            # SLANJE ODLUKE NA ESP32
            print(f"[SLANJE] Šaljem '{result_str}' na ESP32...")
            res = requests.post(f"{ESP32_URL}/servo", json={"result": result_str}, timeout=5)
            print(f"[ESP32 Odgovor] Status: {res.status_code}")
            print("--------------------------------------------------\nČekam novi predmet...")

        except Exception as e:
            print(f"[GREŠKA TIJEKOM PROCESA] {e}")
            cv2.destroyAllWindows()
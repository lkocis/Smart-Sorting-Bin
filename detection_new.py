import cv2
import requests
import numpy as np
import time
import threading
from flask import Flask

CAM_URL   = "http://10.9.0.238/capture"
ESP32_URL = "http://10.9.0.239"

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

def detect_red_color(img):
    hsv_img = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower_red1 = np.array([0, 100, 100])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([160, 100, 100])
    upper_red2 = np.array([180, 255, 255])
    mask1 = cv2.inRange(hsv_img, lower_red1, upper_red1)
    mask2 = cv2.add(mask1, cv2.inRange(hsv_img, lower_red2, upper_red2))
    
    kernel = np.ones((5, 5), "uint8")
    mask2 = cv2.dilate(mask2, kernel)
    contours, _ = cv2.findContours(mask2, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    found = False
    for contour in contours:
        if cv2.contourArea(contour) > 500:
            x, y, w, h = cv2.boundingRect(contour)
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 255), 2)
            cv2.putText(img, "Red Object", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
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

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    print("Sustav spreman. Čekam PIR signal s ESP32...")

    while True:
        motion_event.wait()
        motion_event.clear()  
        
        # 1. Korak: Pustimo predmet da se fizički smiri ispred kamere nakon okinutog PIR-a
        time.sleep(0.7) 
        
        print("[AKCIJA] Čistim buffer i uzimam najnoviju sliku...")
        
        response = None
        for pokusaj in range(1, 4):
            try:
                # 2. Korak: Prvi zahtjev služi SAMO da "izbaci" staru sliku iz memorije kamere
                # Taj rezultat odmah bacamo u smeće
                try:
                    requests.get(CAM_URL, timeout=2)
                except:
                    pass
                
                # Mala, ali ključna pauza (300ms) da kamera stigne snimiti POTPUNO NOVI okvir
                time.sleep(0.3)
                
                # 3. Korak: Drugi zahtjev povlači stvarnu, svježu sliku iz novog okvira
                response = requests.get(CAM_URL, timeout=4)
                if response.status_code == 200:
                    break 
            except requests.exceptions.RequestException:
                print(f"   [UPOZORENJE] Pokušaj {pokusaj}/3 nije uspio. Ponavljam...")
                time.sleep(0.5)
        
        if response is None or response.status_code != 200:
            print("[KRAJNJA GREŠKA] Kamera nedostupna. Čekam novi predmet...")
            continue

        try:
            img_array = np.array(bytearray(response.content), dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

            if img is None:
                print("[GREŠKA] Neuspješno dekodiranje slike.")
                continue

            # DETEKCIJA
            result_str = "none"
            if detect_red_color(img):
                result_str = "red"
                print("--- Rezultat: CRVENO")
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
            print("[INFO] Prozor zatvoren. Slika obrisana iz memorije.")

            # SLANJE ODLUKE NATRAG NA ESP32 ZA SERVO MOTORE
            print(f"[SLANJE] Šaljem '{result_str}' na ESP32...")
            res = requests.post(f"{ESP32_URL}/servo", json={"result": result_str}, timeout=5)
            print(f"[ESP32 Odgovor] Servo naredba poslana. Status: {res.status_code}")
            print("--------------------------------------------------\nČekam novi predmet...")

        except Exception as e:
            print(f"[GREŠKA TIJEKOM PROCESA] {e}")
            cv2.destroyAllWindows()
import cv2

# ===== STUDENT ID → NAME MAPPING =====
names = {
    1: "Anushya",
    2: "Tharania",
    3: "Jebisha",
    4: "Naethra",
    5: "Ramya",
    6: "Raji",
    7: "Dhana Laxmi",
    8: "Esai Kaviya",
    9: "Asha Devi",
    10: "Diviya",
    11: "Dharshini"
}

# ===== LOAD FACE DETECTOR =====
face_classifier = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

# ===== LOAD TRAINED MODEL =====
clf = cv2.face.LBPHFaceRecognizer_create()
clf.read("classifier.xml")


def detect_faces(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Improved detection settings
    faces = face_classifier.detectMultiScale(gray, 1.2, 5)

    present = []

    for (x, y, w, h) in faces:

        # ===== FACE PREPROCESSING =====
        face = gray[y:y+h, x:x+w]
        face = cv2.resize(face, (200, 200))   # 🔥 VERY IMPORTANT

        # ===== PREDICTION =====
        id, distance = clf.predict(face)

        confidence = int(100 * (1 - distance / 200))

        print("ID:", id, "Confidence:", confidence)  # Debug

        # ===== DECISION =====
        if confidence > 100:
            name = names.get(id, "Unknown")

            if name not in present:
                present.append(name)

            color = (0, 255, 0)
        else:
            name = "Unknown"
            color = (0, 0, 255)

        # ===== DISPLAY =====
        cv2.putText(img, f"{name} ({confidence}%)", (x, y-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

        cv2.rectangle(img, (x, y), (x+w, y+h), color, 2)

    return img, present


# ===== LOAD GROUP IMAGE =====
img = cv2.imread("C:/xampp/htdocs/final(sams)/group.jpeg")

# ===== SAFETY CHECK =====
if img is None:
    print("❌ Error: Image not found. Check path or file name!")
    exit()

# ===== RUN DETECTION =====
result, present = detect_faces(img)

# ===== FIND ABSENT STUDENTS =====
all_students = list(names.values())
absent = list(set(all_students) - set(present))

print("\n✅ Present Students:", present)
print("❌ Absent Students:", absent)

# ===== SHOW OUTPUT =====
cv2.imshow("Attendance Result", result)
cv2.waitKey(0)
cv2.destroyAllWindows()
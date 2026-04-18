import cv2
import os

face_classifier = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

def face_crop(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_classifier.detectMultiScale(gray, 1.3, 5)

    cropped_faces = []
    for (x, y, w, h) in faces:
        cropped_faces.append(img[y:y+h, x:x+w])

    return cropped_faces


# ===== INPUT STUDENT ID =====
student_id = input("Enter Student ID (number): ")

path = f"dataset/{student_id}"
os.makedirs(path, exist_ok=True)

cap = cv2.VideoCapture(0)
img_id = 0

while True:
    ret, frame = cap.read()

    faces = face_crop(frame)

    for face in faces:
        img_id += 1

        face = cv2.resize(face, (200, 200))
        face = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)

        file_name = f"{path}/{img_id}.jpg"
        cv2.imwrite(file_name, face)

        cv2.putText(face, str(img_id), (10, 30),
                    cv2.FONT_HERSHEY_COMPLEX, 1, (0,255,0), 2)

        cv2.imshow("Face Capture", face)

    if cv2.waitKey(1) == 13 or img_id >= 50:
        break

cap.release()
cv2.destroyAllWindows()

print("Dataset Created Successfully")
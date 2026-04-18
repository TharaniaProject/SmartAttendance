import cv2
import os
from deepface import DeepFace

DATASET_PATH = "dataset"
GROUP_IMAGE = "C:/xampp/htdocs/final(sams)/group.jpeg"

img = cv2.imread(GROUP_IMAGE)

if img is None:
    print("Image not found")
    exit()

# Detect faces using OpenCV (faster & stable)
face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
faces = face_cascade.detectMultiScale(
    gray,
    scaleFactor=1.05,
    minNeighbors=3,
    minSize=(50, 50)
)

present = []

for i, (x, y, w, h) in enumerate(faces):

    face_img = img[y:y+h, x:x+w]

    temp_path = f"temp_{i}.jpg"
    cv2.imwrite(temp_path, face_img)

    try:
        result = DeepFace.find(
    img_path=temp_path,
    db_path=DATASET_PATH,
    enforce_detection=False,
    model_name="Facenet",
    distance_metric="cosine",
    threshold=0.5
)

        name = "Unknown"

        if len(result) > 0 and len(result[0]) > 0:
           best = result[0].iloc[0]
           distance = best['distance']

           print("Distance:", distance)
           if distance < 0.8:   # 🔥 relaxed
                name = best['identity'].split(os.sep)[-2]
                if name not in present:
                    present.append(name)
    except:
        name = "Unknown"

    # Draw
    color = (0,255,0) if name != "Unknown" else (0,0,255)

    cv2.rectangle(img, (x,y), (x+w,y+h), color, 2)
    cv2.putText(img, name, (x,y-10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

# Only folders = students
all_students = [
    d for d in os.listdir(DATASET_PATH)
    if os.path.isdir(os.path.join(DATASET_PATH, d))
]

absent = list(set(all_students) - set(present))

print("\nPresent:", present)
print("Absent:", absent)

cv2.imshow("Result", img)
cv2.waitKey(0)
cv2.destroyAllWindows()

# Cleanup temp files
for i in range(len(faces)):
    temp = f"temp_{i}.jpg"
    if os.path.exists(temp):
        os.remove(temp)
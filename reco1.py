import cv2
import pickle
import numpy as np
import os
from deepface import DeepFace

# ===== LOAD EMBEDDINGS =====
with open("embeddings.pkl", "rb") as f:
    database = pickle.load(f)

print("✅ Embeddings Loaded")

# ===== LOAD IMAGE =====
img_path = "C:/xampp/htdocs/final(sams)/group_photo/group4.jpeg"
img = cv2.imread(img_path)

if img is None:
    print("❌ Image not found")
    exit()

# ===== DETECT FACES =====
faces = DeepFace.extract_faces(
    img_path=img_path,
    detector_backend="retinaface",
    enforce_detection=False
)

print("👤 Faces detected:", len(faces))

present = []

# ===== DISTANCE FUNCTION =====
def cosine_distance(a, b):
    return 1 - np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

# ===== PROCESS EACH FACE =====
for i, face in enumerate(faces):

    face_img = (face["face"] * 255).astype("uint8")

    embedding = DeepFace.represent(
        img_path=face_img,
        model_name="Facenet",
        enforce_detection=False
    )[0]["embedding"]

    best_name = "Unknown"
    best_score = 999

    # ===== COMPARE WITH DATABASE =====
    for person, embeddings in database.items():

        for db_emb in embeddings:

            dist = cosine_distance(embedding, db_emb)

            if dist < best_score:
                best_score = dist
                best_name = person

    print(f"Face {i} → {best_name} | Distance:", best_score)

    # ===== FINAL DECISION =====
    if best_score < 0.4:
        if best_name not in present:
            present.append(best_name)
        display_name = best_name
        color = (0, 255, 0)
    else:
        display_name = "Unknown"
        color = (0, 0, 255)

    # ===== DRAW RECTANGLE =====
    region = face["facial_area"]
    x, y, w, h = region["x"], region["y"], region["w"], region["h"]

    cv2.rectangle(img, (x, y), (x+w, y+h), color, 2)
    cv2.putText(img, display_name, (x, y-10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

# ===== FIND ALL STUDENTS =====
all_students = list(database.keys())

# ===== FIND ABSENTEES =====
absent = list(set(all_students) - set(present))

# ===== OUTPUT =====
print("\n✅ Present Students:", present)
print("❌ Absent Students:", absent)

# ===== SHOW IMAGE =====
cv2.imshow("Face Recognition Result", img)
cv2.waitKey(0)
cv2.destroyAllWindows()
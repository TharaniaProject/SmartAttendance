import cv2
import pickle
import numpy as np
from deepface import DeepFace

# ===== LOAD EMBEDDINGS =====
with open("embeddings.pkl", "rb") as f:
    database = pickle.load(f)

print("✅ Embeddings Loaded")


# ===== COSINE DISTANCE =====
def cosine_distance(a, b):
    return 1 - np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


# ===== MAIN FUNCTION =====
def recognize_faces(img_path):

    img = cv2.imread(img_path)

    if img is None:
        return [], []

    try:
        faces = DeepFace.extract_faces(
            img_path=img_path,
            detector_backend="retinaface",   # 🔥 ONLY CHANGE (opencv → retinaface)
            enforce_detection=False
        )

        print("👤 Faces detected:", len(faces))  # (optional debug)

    except Exception as e:
        print("Face detection error:", e)
        return [], []

    present = []
    used_ids = set()

    for face in faces:

        try:
            face_img = face["face"]

            # 🔥 SAFE NORMALIZATION (unchanged)
            if face_img.max() <= 1:
                face_img = (face_img * 255).astype("uint8")
            else:
                face_img = face_img.astype("uint8")

            embedding = DeepFace.represent(
                face_img,
                model_name="Facenet",
                enforce_detection=False
            )[0]["embedding"]

            best_id = None
            best_score = 999

            # ===== FIND BEST MATCH =====
            for person_id, embeddings in database.items():

                if person_id in used_ids:
                    continue

                for db_emb in embeddings:
                    dist = cosine_distance(embedding, db_emb)

                    if dist < best_score:
                        best_score = dist
                        best_id = person_id

            # ===== FINAL DECISION =====
            if best_score < 0.4 and best_id is not None:
                present.append(best_id)
                used_ids.add(best_id)

        except Exception as e:
            print("Face error:", e)
            continue

    all_students = list(database.keys())
    absent = list(set(all_students) - set(present))

    return present, absent
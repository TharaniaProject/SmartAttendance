import cv2
import pickle
import numpy as np
from deepface import DeepFace


with open("embeddings.pkl", "rb") as f:
    database = pickle.load(f)

print("Embeddings loaded:", list(database.keys()))



def cosine_distance(a, b):
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 1.0   
    return 1 - np.dot(a, b) / (norm_a * norm_b)



def recognize_faces(img_path):
    """
    Detect and recognise faces in img_path.
    Returns:
        present (list of short_name strings)
        absent  (list of short_name strings)

    MODIFY: change THRESHOLD (line ~55) to tune
            match strictness (lower = stricter).
    MODIFY: add/remove entries in DETECTOR_BACKENDS
            to control which detectors are tried.
    """

    img = cv2.imread(img_path)
    if img is None:
        print("Could not read image:", img_path)
        return [], []


    DETECTOR_BACKENDS = ["retinaface"]

    faces = []
    for backend in DETECTOR_BACKENDS:
        try:
            faces = DeepFace.extract_faces(
                img_path=img_path,
                detector_backend=backend,
                enforce_detection=False
            )
            if faces:
                print(f"Faces detected with {backend}: {len(faces)}")
                break
        except Exception as e:
            print(f"Backend '{backend}' failed: {e}")
            continue

    if not faces:
        print("No faces detected by any backend.")
        return [], []

    present   = []
    used_ids  = set()


    THRESHOLD = 0.4

    for face in faces:
        try:
            face_img = face["face"]


            if face_img.max() <= 1.0:
                face_img = (face_img * 255).astype("uint8")
            else:
                face_img = face_img.astype("uint8")

            if face_img.shape[0] < 20 or face_img.shape[1] < 20:
                print("Skipping very small face crop")
                continue

            embedding = DeepFace.represent(
                face_img,
                model_name="Facenet",
                enforce_detection=False
            )[0]["embedding"]

            best_id    = None
            best_score = 999.0

            for person_id, embeddings in database.items():
                if person_id in used_ids:
                    continue
                for db_emb in embeddings:
                    dist = cosine_distance(embedding, db_emb)
                    if dist < best_score:
                        best_score = dist
                        best_id    = person_id

            if best_score < THRESHOLD and best_id is not None:
                print(f"Matched: {best_id} (score={best_score:.3f})")
                present.append(best_id)
                used_ids.add(best_id)
            else:
                print(f"No match (best score={best_score:.3f})")

        except Exception as e:
            print("Face processing error:", e)
            continue

    all_students = list(database.keys())
    absent = list(set(all_students) - set(present))

    print(f"Present: {present}")
    print(f"Absent:  {absent}")

    return present, absent
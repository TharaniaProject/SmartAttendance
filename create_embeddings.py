import os
import pickle
from deepface import DeepFace

DATASET_PATH = "dataset"

print("⏳ Creating embeddings...")

database = {}

for person in os.listdir(DATASET_PATH):
    person_path = os.path.join(DATASET_PATH, person)

    if not os.path.isdir(person_path):
        continue

    embeddings = []

    for file in os.listdir(person_path):

        if not file.lower().endswith(('.jpg', '.jpeg', '.png')):
            continue

        img_path = os.path.join(person_path, file)

        try:
            embedding = DeepFace.represent(
                img_path=img_path,
                model_name="Facenet",
                enforce_detection=False
            )[0]["embedding"]

            embeddings.append(embedding)

        except:
            continue

    database[person] = embeddings

# ===== SAVE FILE =====
with open("embeddings.pkl", "wb") as f:
    pickle.dump(database, f)

print("✅ embeddings.pkl file created")
import cv2
import os
import numpy as np
from PIL import Image

def train_model():
    data_dir = "dataset"

    faces = []
    ids = []

    label_map = {}   # 🔥 name → id
    current_id = 0

    for root, dirs, files in os.walk(data_dir):
        for file in files:

            if not file.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue

            path = os.path.join(root, file)

            try:
                img = Image.open(path).convert('L')
                imageNp = np.array(img, 'uint8')

                name = os.path.basename(root)

                # 🔥 Assign ID automatically
                if name not in label_map:
                    label_map[name] = current_id
                    current_id += 1

                id = label_map[name]

                faces.append(imageNp)
                ids.append(id)

            except Exception as e:
                print("Error loading:", path)

    print("Total faces:", len(faces))
    print("Label Map:", label_map)

    if len(faces) == 0:
        print("❌ No training data found!")
        return

    ids = np.array(ids)

    clf = cv2.face.LBPHFaceRecognizer_create()
    clf.train(faces, ids)
    clf.write("classifier.xml")

    # 🔥 SAVE MAPPING (VERY IMPORTANT)
    import pickle
    with open("labels.pkl", "wb") as f:
        pickle.dump(label_map, f)

    print("✅ Training Completed")

train_model()
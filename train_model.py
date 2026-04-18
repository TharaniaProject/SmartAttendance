import cv2
import os
import numpy as np
from PIL import Image

def train_model():
    data_dir = "dataset"

    faces = []
    ids = []

    for root, dirs, files in os.walk(data_dir):
        for file in files:

            path = os.path.join(root, file)

            try:
                # Load image in grayscale
                img = Image.open(path).convert('L')
                imageNp = np.array(img, 'uint8')

                # Resize to fixed size (VERY IMPORTANT)
                imageNp = cv2.resize(imageNp, (200, 200))

                # Get ID from folder name
                student_id = int(os.path.basename(root))

                faces.append(imageNp)
                ids.append(student_id)

                cv2.imshow("Training", imageNp)
                cv2.waitKey(10)

            except:
                print("Skipping file:", path)

    ids = np.array(ids)

    # 🔥 Improved LBPH model
    clf = cv2.face.LBPHFaceRecognizer_create(
        radius=2,
        neighbors=10,
        grid_x=8,
        grid_y=8
    )

    clf.train(faces, ids)
    clf.write("classifier.xml")

    cv2.destroyAllWindows()
    print("✅ Training Completed Successfully")

train_model()
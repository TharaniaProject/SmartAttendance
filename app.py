from flask import Flask, render_template, request, redirect, session, jsonify
import mysql.connector
import cv2
import pickle
import numpy as np
import os
from deepface import DeepFace
from ai_detection import recognize_faces
app = Flask(__name__)
app.secret_key = "secret123"

# ✅ DB CONNECTION
db = mysql.connector.connect(
    host="localhost",
    user="student",
    password="Tharania@2005",
    database="smart_attendance",
    port=3307
)
cursor = db.cursor(dictionary=True)

# -------------------------------
# ✅ LOGIN PAGE
# -------------------------------
@app.route('/')
def home():
    return render_template('login.html')



# -------------------------------
# ✅ LOGIN LOGIC
# -------------------------------
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()

    # ✅ match HTML names
    user_id = data.get('userID')   # <-- IMPORTANT CHANGE
    password = data.get('password')

    cursor.execute(
        "SELECT * FROM users WHERE user_id=%s AND password=%s",
        (user_id, password)
    )
    user = cursor.fetchone()

    if user:
        session['user_id'] = user['user_id']   # ✅ store session

        return jsonify({
            "status": "success",
            "user_id": user['user_id'],
            "role": user['role']
        })

    return jsonify({
        "status": "fail",
        "message": "Invalid ID or Password"
    }), 401

# -------------------------------
# ✅ STUDENT DASHBOARD PAGE
# -------------------------------
@app.route('/student')
def student():
    if 'user_id' not in session:
        return redirect('/')
    return render_template('student_dashboard.html')

@app.route('/faculty')
def faculty():
    if 'user_id' not in session:
        return redirect('/')

    faculty_id = session['user_id']   # ✅ get logged-in ID

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        "SELECT name FROM faculty WHERE faculty_id=%s",
        (faculty_id,)
    )

    faculty = cursor.fetchone()

    # ✅ safety (if no data found)
    if not faculty:
        faculty = {"name": "Faculty"}

    return render_template('Faculty_dashboard.html', faculty=faculty)

@app.route('/get-subjects', methods=['POST'])
def get_subjects():
    import datetime
    data = request.get_json()
    course = data.get('course')
    year = data.get('year')
    semester = data.get('semester')
    day = data.get('day')  # May be empty string

    cursor = db.cursor(dictionary=True)

    query = """

    SELECT s.subject_id, s.subject_name, s.faculty_name, s.subject_code, t.hours,
           t.start_time, t.end_time, t.day, t.session, t.session_type
    FROM subjects s
    LEFT JOIN timetable t ON s.subject_id = t.subject_id
    WHERE s.course=%s AND s.year=%s AND s.semester=%s AND t.day=%s
    ORDER BY t.hours
    """
    params = [course, year, semester,day]



    cursor.execute(query, tuple(params))
    subjects = cursor.fetchall()

    # Convert timedelta to string
    for sub in subjects:
        if sub['start_time']:
            sub['start_time'] = (datetime.datetime.min + sub['start_time']).time().strftime("%H:%M")
        if sub['end_time']:
            sub['end_time'] = (datetime.datetime.min + sub['end_time']).time().strftime("%H:%M")

    return jsonify({"subjects": subjects})


@app.route('/admin')
def admin():
    return "Admin Dashboard (create later)"

# -------------------------------
# ✅ FETCH DASHBOARD DATA (IMPORTANT)
# -------------------------------
@app.route('/dashboard-data')
def dashboard_data():

    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    student_id = session['user_id']

    cursor.execute("SELECT * FROM students WHERE student_id=%s", (student_id,))
    student = cursor.fetchone()

    cursor.execute("""
        SELECT   s.subject_id, s.subject_name,
        ROUND(SUM(CASE WHEN a.status='Present' THEN 1 ELSE 0 END)*100/COUNT(*),2) AS percentage
        FROM attendance a
        JOIN subjects s ON a.subject_id = s.subject_id
        WHERE a.student_id=%s
        GROUP BY a.subject_id
    """, (student_id,))
    subjects = cursor.fetchall()
    cursor.execute("""
       SELECT
    SUM(status='present') AS present,
    COUNT(*) AS total
    FROM attendance
    WHERE student_id=%s
    """, (student_id,))
    result = cursor.fetchone()

    present = result['present'] or 0
    total = result['total'] or 1
    cumulative = round((present / total) * 100, 2)

    cursor.execute("""
        SELECT MONTH(date) as month,
        ROUND(SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END)*100/COUNT(*),2) AS percentage
        FROM attendance
        WHERE student_id=%s
        GROUP BY MONTH(date)
    """, (student_id,))
    monthly = cursor.fetchall()

    return jsonify({
        "student": student,
        "subjects": subjects,
        "monthly": monthly,
        "cumulative": cumulative
    })
@app.route('/recognize', methods=['POST'])
def recognize():
    file = request.files['image']

    path = "temp.jpg"
    file.save(path)

    # 🔥 CALL YOUR FUNCTION HERE
    present, absent = recognize_faces(path)

    return jsonify({
        "present": present,
        "absent": absent
    })

@app.route('/test')
def test():
    return "Flask OK ✅"

@app.route('/check-session')
def check_session():
    return {"session": dict(session)}
# ✅ LOGOUT
# -------------------------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/absent-history')
def absent_history():

    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    student_id = session.get('user_id')
    subject_id = request.args.get('subject_id')

    if not subject_id or subject_id == 'undefined':
        return jsonify([])
    subject_id = int(subject_id)

    cursor = db.cursor(dictionary=True)

    query = """
    SELECT
        a.date,
        DAYNAME(a.date) AS day,
        t.session,
        t.session_type,
        t.hours,
        CONCAT(
            TIME_FORMAT(t.start_time, '%h:%i %p'),
            ' - ',
            TIME_FORMAT(t.end_time, '%h:%i %p')
        ) AS time_slot,
        a.status

    FROM attendance a

    LEFT JOIN timetable t
        ON a.subject_id = t.subject_id
        AND UPPER(t.day) = UPPER(DAYNAME(a.date))

    WHERE a.student_id = %s
    AND a.subject_id = %s
    AND LOWER(a.status) = 'absent'
    """

    cursor.execute(query, (student_id, subject_id))
    data = cursor.fetchall()



    return jsonify(data)
# -------------------------------
# ✅ FACE RECOGNITION ATTENDANCE
# -------------------------------

# Load embeddings once
with open("embeddings.pkl", "rb") as f:
    database = pickle.load(f)

def cosine_distance(a, b):
    return 1 - np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

from werkzeug.utils import secure_filename
import os
print("📊 DATABASE CONTENT:")
for key in database.keys():
    print("KEY:", key)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/process_attendance', methods=['POST'])
def process_attendance():
    print("🔥 process_attendance called")

    # ============================
    # ✅ SESSION CHECK
    # ============================
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    file = request.files.get("image")
    subject_id = request.form.get("subject_id")

    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    if not subject_id or subject_id == "undefined":
        return jsonify({"error": "Invalid subject_id"}), 400

    try:
        subject_id = int(subject_id)
    except:
        return jsonify({"error": "Subject ID must be integer"}), 400

    # ============================
    # ✅ SAVE IMAGE
    # ============================
    img_path = "temp_upload.jpg"
    file.save(img_path)

    # ============================
    # ✅ FACE DETECTION
    # ============================
    try:
        faces = DeepFace.extract_faces(
            img_path=img_path,
            detector_backend="opencv",
            enforce_detection=False
        )
    except Exception as e:
        print("❌ Face Detection Error:", e)
        return jsonify({"error": "Face detection failed"}), 500

    if len(faces) == 0:
        return jsonify({"error": "No face detected"}), 400

    present = []
    used = set()

    # ============================
    # ✅ FACE MATCHING
    # ============================
    for face in faces:
        face_img = face["face"]

        face_img = (
            (face_img * 255).astype("uint8")
            if face_img.max() <= 1
            else face_img.astype("uint8")
        )

        embedding = DeepFace.represent(
            face_img,
            model_name="Facenet",
            enforce_detection=False
        )[0]["embedding"]

        best_match = None
        best_score = 999

        for short_name, embeddings in database.items():

            if short_name in used:
                continue

            for db_emb in embeddings:
                dist = cosine_distance(embedding, db_emb)

                if dist < best_score:
                    best_score = dist
                    best_match = short_name

        if best_score < 0.4 and best_match:
            present.append(best_match)
            used.add(best_match)

    # ============================
    # ✅ ABSENT
    # ============================
    all_short = list(database.keys())
    absent = list(set(all_short) - set(present))

    # ============================
    # ✅ FETCH STUDENTS USING short_name
    # ============================
    cursor.execute("""
        SELECT student_id, name, short_name, department, phone_No
        FROM students
    """)

    student_map = {
        row["short_name"]: {
            "student_id": str(row["student_id"]),
            "name": row["name"],
            "department": row["department"],
            "phone": row["phone_No"]
        }
        for row in cursor.fetchall()
    }

    # ============================
    # ✅ FORMAT RESPONSE
    # ============================
    present_students = []
    for s in present:
        if s in student_map:
            present_students.append(student_map[s])

    absent_students = []
    for s in absent:
        if s in student_map:
            absent_students.append(student_map[s])

    # ============================
    # ✅ INSERT ATTENDANCE
    # ============================
    try:
        for s in present:
            if s not in student_map:
                continue

            student_id = student_map[s]["student_id"]

            cursor.execute("""
                SELECT id FROM attendance
                WHERE student_id=%s AND subject_id=%s AND date=CURDATE()
            """, (student_id, subject_id))

            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO attendance
                    (student_id, subject_id, date, status, marked_by)
                    VALUES (%s, %s, CURDATE(), 'Present', 'Automatic')
                """, (student_id, subject_id))

        db.commit()

    except Exception as e:
        print("❌ DB ERROR:", e)
        return jsonify({"error": "Database insert failed"}), 500

    # ============================
    # ✅ RETURN JSON (IMPORTANT FIX)
    # ============================
    return jsonify({
        "present": present_students,
        "absent": absent_students
    })
@app.route('/get-students', methods=['POST'])
def get_students():
    data = request.get_json()
    subject_id = data.get('subject_id')

    if not subject_id:
        return jsonify({"error": "No subject"}), 400

    cursor = db.cursor(dictionary=True)

    # Get all students enrolled in this subject's course/year
    cursor.execute("""
        SELECT s.student_id, s.name, s.roll_no, s.phone_No, s.department,
               CASE WHEN a.status = 'Present' THEN 'PRESENT' ELSE 'ABSENT' END AS status
        FROM students s
        LEFT JOIN attendance a
            ON s.student_id = a.student_id
            AND a.subject_id = %s
            AND a.date = CURDATE()
        WHERE s.course = (SELECT course FROM subjects WHERE subject_id = %s)
          AND s.year   = (SELECT year   FROM subjects WHERE subject_id = %s)
    """, (subject_id, subject_id, subject_id))

    rows = cursor.fetchall()
    return jsonify({"students": rows})
#--------------------------
# ✅ RUN APP
# -------------------------------
if __name__ == '__main__':
    app.run(debug=True)

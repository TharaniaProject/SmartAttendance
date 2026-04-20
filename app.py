from flask import Flask, render_template, request, redirect, session, jsonify
import mysql.connector
from mysql.connector import pooling
import pickle
import numpy as np
import os
import datetime

# Optional (comment if build fails in cloud)
# from deepface import DeepFace
from ai_detection import recognize_faces

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")

# =========================
# DATABASE CONFIG (SAFE)
# =========================
db_config = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "smart_attendance"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "connection_timeout": 30,
}

# =========================
# CONNECTION POOL
# =========================
try:
    connection_pool = pooling.MySQLConnectionPool(
        pool_name="smart_pool",
        pool_size=5,
        **db_config
    )
except Exception as e:
    print("❌ DB Pool Error:", e)
    connection_pool = None

def get_cursor():
    if not connection_pool:
        raise Exception("Database not connected")
    conn = connection_pool.get_connection()
    cur = conn.cursor(dictionary=True)
    return conn, cur

# =========================
# LOAD EMBEDDINGS
# =========================
if os.path.exists("embeddings.pkl"):
    with open("embeddings.pkl", "rb") as f:
        database = pickle.load(f)
else:
    print("⚠ embeddings.pkl not found")
    database = {}

print("Embeddings loaded:", list(database.keys()))

# =========================
# UPLOAD FOLDER
# =========================
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# =========================
# ROUTES
# =========================
@app.route('/')
def home():
    return render_template('login.html')

# =========================
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    user_id = data.get('userID')
    password = data.get('password')

    conn, cur = get_cursor()
    try:
        cur.execute("SELECT * FROM users WHERE user_id=%s AND password=%s",
                    (user_id, password))
        user = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if user:
        session['user_id'] = user['user_id']
        return jsonify({"status": "success", "role": user['role']})

    return jsonify({"status": "fail"}), 401

# =========================
@app.route('/student')
def student():
    if 'user_id' not in session:
        return redirect('/')
    return render_template('student_dashboard.html')

# =========================
@app.route('/recognize', methods=['POST'])
def recognize():
    file = request.files['image']
    path = os.path.join(UPLOAD_FOLDER, "temp.jpg")
    file.save(path)

    present, absent = recognize_faces(path)
    return jsonify({"present": present, "absent": absent})

# =========================
@app.route('/process_attendance', methods=['POST'])
def process_attendance():

    if 'user_id' not in session:
        return jsonify({"error": "Session expired"}), 401

    file = request.files.get("image")
    subject_id = request.form.get("subject_id")

    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    try:
        subject_id = int(subject_id)
    except:
        return jsonify({"error": "Invalid subject_id"}), 400

    # Time (IST)
    from datetime import datetime
    from zoneinfo import ZoneInfo
    attendance_date = datetime.now(ZoneInfo("Asia/Kolkata")).date()

    # ✅ FIXED INDENTATION
    img_path = os.path.join(UPLOAD_FOLDER, "temp_upload.jpg")
    file.save(img_path)

    present_names, absent_names = recognize_faces(img_path)

    conn, cur = get_cursor()

    try:
        cur.execute("SELECT student_id, short_name FROM students")
        rows = cur.fetchall()

        student_map = {r["short_name"]: r["student_id"] for r in rows}

        for name in present_names:
            if name in student_map:
                cur.execute("""
                    INSERT INTO attendance (student_id, subject_id, date, status)
                    VALUES (%s, %s, %s, 'Present')
                    ON DUPLICATE KEY UPDATE status='Present'
                """, (student_map[name], subject_id, attendance_date))

        for name in absent_names:
            if name in student_map:
                cur.execute("""
                    INSERT INTO attendance (student_id, subject_id, date, status)
                    VALUES (%s, %s, %s, 'Absent')
                    ON DUPLICATE KEY UPDATE status='Absent'
                """, (student_map[name], subject_id, attendance_date))

        conn.commit()

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)})

    finally:
        cur.close()
        conn.close()

    return jsonify({"status": "success"})

# =========================
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# =========================
@app.route('/test')
def test():
    return "Flask running successfully!"

# =========================
# MAIN (FIXED FOR DEPLOYMENT)
# =========================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
from flask import Flask, render_template, request, redirect, session, jsonify
import mysql.connector
from mysql.connector import pooling
import pickle
import numpy as np
import os
from deepface import DeepFace
from ai_detection import recognize_faces

app = Flask(__name__)
app.secret_key = "secret123"

# =============================================
# CONNECTION POOL — survives idle timeouts
# =============================================
db_config = {
    "host":               "localhost",
    "user":               "student",
    "password":           "Tharania@2005",
    "database":           "smart_attendance",
    "port":               3307,
    "connection_timeout": 30,
}

connection_pool = pooling.MySQLConnectionPool(
    pool_name="smart_pool",
    pool_size=5,
    **db_config
)

def get_db():
    """Return a fresh connection from the pool."""
    return connection_pool.get_connection()


# =============================================
# LOAD FACE EMBEDDINGS (once at startup)
# =============================================
with open("embeddings.pkl", "rb") as f:
    database = pickle.load(f)

print("Embeddings loaded. Keys:", list(database.keys()))

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# =============================================
# HOME / LOGIN PAGE
# =============================================
@app.route('/')
def home():
    return render_template('login.html')


# =============================================
# LOGIN
# Table : users
# Cols  : user_id, password, role
# =============================================
@app.route('/login', methods=['POST'])
def login():
    data     = request.get_json()
    user_id  = data.get('userID')
    password = data.get('password')

    conn = get_db()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT * FROM users WHERE user_id = %s AND password = %s",
            (user_id, password)
        )
        user = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if user:
        session['user_id'] = user['user_id']
        return jsonify({
            "status":  "success",
            "user_id": user['user_id'],
            "role":    user['role']
        })

    return jsonify({"status": "fail", "message": "Invalid ID or Password"}), 401


# =============================================
# STUDENT DASHBOARD PAGE
# =============================================
@app.route('/student')
def student():
    if 'user_id' not in session:
        return redirect('/')
    return render_template('student_dashboard.html')


# =============================================
# FACULTY DASHBOARD PAGE
# Table : faculty
# Cols  : faculty_id, name
# =============================================
@app.route('/faculty')
def faculty():
    if 'user_id' not in session:
        return redirect('/')

    faculty_id = session['user_id']
    conn = get_db()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute(
            "SELECT name FROM faculty WHERE faculty_id = %s",
            (faculty_id,)
        )
        faculty = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not faculty:
        faculty = {"name": "Faculty"}

    return render_template('Faculty_dashboard.html', faculty=faculty)


# =============================================
# GET SUBJECTS FOR SELECTED DAY
# Tables : subjects (s), timetable (t)
# Cols s : subject_id, subject_name, subject_code,
#           faculty_name, course, year, semester
# Cols t : subject_id, day, start_time, end_time,
#           hours, session, session_type
# =============================================
@app.route('/get-subjects', methods=['POST'])
def get_subjects():
    import datetime
    data     = request.get_json()
    course   = data.get('course')
    year     = data.get('year')
    semester = data.get('semester')
    day      = data.get('day')

    if not all([course, year, semester, day]):
        return jsonify({"subjects": []})

    conn = get_db()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT
                s.subject_id,
                s.subject_name,
                s.subject_code,
                s.faculty_name,
                t.hours,
                t.start_time,
                t.end_time,
                t.day,
                t.session,
                t.session_type
            FROM subjects s
            LEFT JOIN timetable t ON s.subject_id = t.subject_id
            WHERE s.course    = %s
              AND s.year      = %s
              AND s.semester  = %s
              AND t.day       = %s
            ORDER BY t.hours
        """, (course, year, semester, day))
        subjects = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    # Convert timedelta → "HH:MM" string (MySQL returns TIME as timedelta)
    for sub in subjects:
        if sub['start_time']:
            sub['start_time'] = (
                datetime.datetime.min + sub['start_time']
            ).time().strftime("%H:%M")
        if sub['end_time']:
            sub['end_time'] = (
                datetime.datetime.min + sub['end_time']
            ).time().strftime("%H:%M")

    return jsonify({"subjects": subjects})


# =============================================
# ADMIN PAGE
# =============================================
@app.route('/admin')
def admin():
    return "Admin Dashboard (create later)"


# =============================================
# STUDENT DASHBOARD DATA
# Tables : students, attendance (a), subjects (s)
# Cols st: student_id
# Cols a : student_id, subject_id, status, date
# Cols s : subject_id, subject_name
# =============================================
@app.route('/dashboard-data')
def dashboard_data():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    student_id = session['user_id']
    conn = get_db()
    cur  = conn.cursor(dictionary=True)
    try:
        # Basic student info
        cur.execute(
            "SELECT * FROM students WHERE student_id = %s",
            (student_id,)
        )
        student = cur.fetchone()

        # Per-subject attendance percentage
        cur.execute("""
            SELECT
                s.subject_id,
                s.subject_name,
                ROUND(
                    SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) * 100
                    / COUNT(*),
                2) AS percentage
            FROM attendance a
            JOIN subjects s ON a.subject_id = s.subject_id
            WHERE a.student_id = %s
            GROUP BY a.subject_id, s.subject_name
        """, (student_id,))
        subjects = cur.fetchall()

        # Overall totals
        cur.execute("""
            SELECT
                SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) AS present,
                COUNT(*) AS total
            FROM attendance
            WHERE student_id = %s
        """, (student_id,))
        result     = cur.fetchone()
        present    = result['present'] or 0
        total      = result['total']   or 1
        cumulative = round((present / total) * 100, 2)

        # Monthly breakdown
        cur.execute("""
            SELECT
                MONTH(date) AS month,
                ROUND(
                    SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) * 100
                    / COUNT(*),
                2) AS percentage
            FROM attendance
            WHERE student_id = %s
            GROUP BY MONTH(date)
        """, (student_id,))
        monthly = cur.fetchall()

    finally:
        cur.close()
        conn.close()

    return jsonify({
        "student":    student,
        "subjects":   subjects,
        "monthly":    monthly,
        "cumulative": cumulative
    })


# =============================================
# RECOGNIZE ENDPOINT
# =============================================
@app.route('/recognize', methods=['POST'])
def recognize():
    file = request.files['image']
    path = "temp.jpg"
    file.save(path)
    present, absent = recognize_faces(path)
    return jsonify({"present": present, "absent": absent})


# =============================================
# TEST / SESSION CHECK
# =============================================
@app.route('/test')
def test():
    return "Flask OK"

@app.route('/check-session')
def check_session():
    return {"session": dict(session)}


# =============================================
# LOGOUT
# =============================================
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


# =============================================
# ABSENT HISTORY FOR STUDENT DASHBOARD
# Tables : attendance (a), timetable (t)
# Cols a : student_id, subject_id, date, status
# Cols t : subject_id, day, start_time, end_time,
#           session, session_type, hours
# =============================================
@app.route('/absent-history')
def absent_history():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    student_id = session.get('user_id')
    subject_id = request.args.get('subject_id')

    if not subject_id or subject_id == 'undefined':
        return jsonify([])

    try:
        subject_id = int(subject_id)
    except ValueError:
        return jsonify([])

    conn = get_db()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT
                a.date,
                DAYNAME(a.date) AS day,
                t.session,
                t.session_type,
                t.hours,
                CONCAT(
                    TIME_FORMAT(t.start_time, '%h:%i %p'),
                    ' - ',
                    TIME_FORMAT(t.end_time,   '%h:%i %p')
                ) AS time_slot,
                a.status
            FROM attendance a
            LEFT JOIN timetable t
                ON  a.subject_id = t.subject_id
                AND UPPER(t.day) = UPPER(DAYNAME(a.date))
            WHERE a.student_id    = %s
              AND a.subject_id    = %s
              AND LOWER(a.status) = 'absent'
            ORDER BY a.date DESC
        """, (student_id, subject_id))
        data = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return jsonify(data)


# =============================================
# PROCESS ATTENDANCE — FACE RECOGNITION
#
# Tables : students, attendance
# Cols students : student_id, name, short_name,
#                 department, phone_No
# Cols attendance: student_id, subject_id, date,
#                  status, marked_by
#
# IMPORTANT — run this SQL once in MySQL to
# enable the upsert (ON DUPLICATE KEY UPDATE):
#
#   ALTER TABLE attendance
#     ADD CONSTRAINT uq_att
#     UNIQUE (student_id, subject_id, date);
# =============================================
@app.route('/process_attendance', methods=['POST'])
def process_attendance():
    print("process_attendance called")

    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    file       = request.files.get("image")
    subject_id = request.form.get("subject_id")
    date_str   = request.form.get("date")

    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    if not subject_id or subject_id == "undefined":
        return jsonify({"error": "Invalid subject_id"}), 400

    try:
        subject_id = int(subject_id)
    except Exception:
        return jsonify({"error": "subject_id must be an integer"}), 400

    # ---- Resolve attendance date ----
    from datetime import datetime
    attendance_date = datetime.today().date()
    if date_str and date_str not in ("undefined", "null", ""):
        try:
            attendance_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        except Exception as e:
            print("Date parse error:", e)

    print("Attendance date:", attendance_date)

    # ---- Save image & run face recognition ----
    img_path = "temp_upload.jpg"
    file.save(img_path)

    # Uses ai_detection.recognize_faces() — single source of truth
    present_names, absent_names = recognize_faces(img_path)
    print("Present short_names:", present_names)
    print("Absent  short_names:", absent_names)

    # ---- Fetch all students mapped by short_name ----
    # Exact columns: student_id, name, short_name, department, phone_No
    conn = get_db()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT
                student_id,
                name,
                short_name,
                department,
                phone_No
            FROM students
        """)
        rows = cur.fetchall()

        student_map = {
            row["short_name"]: {
                "student_id": str(row["student_id"]),
                "name":       row["name"],
                "department": row["department"] or "-",
                "phone":      row["phone_No"]   or "-"
            }
            for row in rows
            if row["short_name"]
        }

        # ---- Upsert PRESENT ----
        for short in present_names:
            if short not in student_map:
                print(f"WARNING: short_name '{short}' not in students table")
                continue
            sid = student_map[short]["student_id"]
            cur.execute("""
                INSERT INTO attendance
                    (student_id, subject_id, date, status, marked_by)
                VALUES
                    (%s, %s, %s, 'Present', 'Automatic')
                ON DUPLICATE KEY UPDATE
                    status    = 'Present',
                    marked_by = 'Automatic'
            """, (sid, subject_id, attendance_date))

        # ---- Upsert ABSENT ----
        for short in absent_names:
            if short not in student_map:
                continue
            sid = student_map[short]["student_id"]
            cur.execute("""
                INSERT INTO attendance
                    (student_id, subject_id, date, status, marked_by)
                VALUES
                    (%s, %s, %s, 'Absent', 'Automatic')
                ON DUPLICATE KEY UPDATE
                    status    = 'Absent',
                    marked_by = 'Automatic'
            """, (sid, subject_id, attendance_date))

        conn.commit()

    except Exception as e:
        conn.rollback()
        print("DB ERROR:", e)
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

    present_students = [student_map[s] for s in present_names if s in student_map]
    absent_students  = [student_map[s] for s in absent_names  if s in student_map]

    return jsonify({
        "present": present_students,
        "absent":  absent_students,
        "date":    str(attendance_date)
    })


# =============================================
# GET STUDENTS FOR SUBJECT + DATE
#
# Tables : students (s), attendance (a),
#          subjects (sub)
# Cols s : student_id, name, phone_No,
#          department, course, year
# Cols a : student_id, subject_id, date, status
# Cols sub: course, year (looked up by subject_id)
#
# Filters students by the course + year that
# the chosen subject belongs to, then LEFT JOINs
# attendance for that subject + date so students
# with no row appear as ABSENT.
# =============================================
@app.route('/get-students', methods=['POST'])
def get_students():
    data       = request.get_json()
    subject_id = data.get('subject_id')
    date_str   = data.get('date')

    if not subject_id:
        return jsonify({"error": "No subject provided"}), 400

    from datetime import datetime
    attendance_date = datetime.today().date()
    if date_str and date_str not in ("undefined", "null", ""):
        try:
            attendance_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        except Exception as e:
            print("get_students date error:", e)

    print("Fetching students — subject:", subject_id, "date:", attendance_date)

    conn = get_db()
    cur  = conn.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT
                s.student_id,
                s.name,
                s.student_id  AS roll_no,
                s.phone_No,
                s.department,
                CASE
                    WHEN a.status = 'Present' THEN 'PRESENT'
                    ELSE 'ABSENT'
                END AS status
            FROM students s
            LEFT JOIN attendance a
                ON  s.student_id = a.student_id
                AND a.subject_id = %s
                AND a.date       = %s
            WHERE s.course = (
                SELECT course FROM subjects
                WHERE subject_id = %s LIMIT 1
            )
              AND s.year = (
                SELECT year FROM subjects
                WHERE subject_id = %s LIMIT 1
            )
            ORDER BY s.student_id
        """, (subject_id, attendance_date, subject_id, subject_id))
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return jsonify({"students": rows})


# =============================================
# RUN
# =============================================
if __name__ == '__main__':
    app.run(debug=True)
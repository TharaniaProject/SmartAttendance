from flask import Flask, render_template, request, redirect, session, jsonify
import mysql.connector
from mysql.connector import pooling
import pickle
import numpy as np
import os
import datetime
from deepface import DeepFace
from ai_detection import recognize_faces

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey")


db_config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "connection_timeout": 30,
}

try:
    connection_pool = pooling.MySQLConnectionPool(
        pool_name="smart_pool",
        pool_size=5,
        **db_config
    )
except Exception as e:
    print("❌ DB Pool Error:", e)

def get_db():
    """Return a fresh connection from the pool."""
    return connection_pool.get_connection()

def get_cursor():
    conn = connection_pool.get_connection()
    cur  = conn.cursor(dictionary=True)
    return conn, cur


if os.path.exists("embeddings.pkl"):
    with open("embeddings.pkl", "rb") as f:
        database = pickle.load(f)
else:
    print("⚠ embeddings.pkl not found")
    database = {}

print("Embeddings loaded. Keys:", list(database.keys()))

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)



@app.route('/')
def home():
    return render_template('login.html')



@app.route('/login', methods=['POST'])
def login():
    data     = request.get_json()
    user_id  = data.get('userID')
    password = data.get('password')

    conn, cur = get_cursor()
    try:
        cur.execute(
            "SELECT * FROM users WHERE user_id = %s AND password = %s",
            (user_id, password)
        )
        user = cur.fetchone()

        if user:
            try:
                ip = request.remote_addr
                cur.execute(
                    "INSERT INTO system_logs (user_id, ip, event) VALUES (%s, %s, 'Login')",
                    (user['user_id'], ip)
                )
                conn.commit()
            except Exception as log_err:
                print("Log insert error:", log_err)
    finally:
        cur.close()
        conn.close()

    if user:
        session['user_id']      = user['user_id']
        session['faculty_name'] = None          # will be set in /faculty route
        return jsonify({
            "status":  "success",
            "user_id": user['user_id'],
            "role":    user['role']
        })
    return jsonify({"status": "fail", "message": "Invalid ID or Password"}), 401



@app.route('/student')
def student():
    if 'user_id' not in session:
        return redirect('/')
    return render_template('student_dashboard.html')



@app.route('/faculty')
def faculty():
    if 'user_id' not in session:
        return redirect('/')

    faculty_id = session['user_id']
    conn, cur  = get_cursor()
    try:
        cur.execute("SELECT name FROM faculty WHERE faculty_id = %s", (faculty_id,))
        faculty_row = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    faculty_name = faculty_row['name'] if faculty_row and faculty_row.get('name') else "Professor"

    # Store in session so the JS endpoint /get-faculty-name can return it
    session['faculty_name'] = faculty_name

    return render_template('Faculty_dashboard.html', faculty={"name": faculty_name})




@app.route('/get-faculty-name')
def get_faculty_name():
    if 'user_id' not in session:
        return jsonify({"name": "Professor"}), 200

    # Try session cache first (set during /faculty route)
    cached = session.get('faculty_name')
    if cached:
        return jsonify({"name": cached})

    # Fallback: query DB directly
    faculty_id = session['user_id']
    conn, cur  = get_cursor()
    try:
        cur.execute("SELECT name FROM faculty WHERE faculty_id = %s", (faculty_id,))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    name = row['name'] if row and row.get('name') else "Professor"
    session['faculty_name'] = name          # cache for subsequent calls
    return jsonify({"name": name})



@app.route('/get-subjects', methods=['POST'])
def get_subjects():
    data     = request.get_json()
    course   = data.get('course')
    year     = data.get('year')
    semester = data.get('semester')
    day      = data.get('day')

    if not all([course, year, semester, day]):
        return jsonify({"subjects": []})

    conn, cur = get_cursor()
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

    # Convert timedelta → "HH:MM" string
    for sub in subjects:
        if sub['start_time'] and isinstance(sub['start_time'], datetime.timedelta):
            sub['start_time'] = (datetime.datetime.min + sub['start_time']).time().strftime("%H:%M")
        if sub['end_time'] and isinstance(sub['end_time'], datetime.timedelta):
            sub['end_time']   = (datetime.datetime.min + sub['end_time']).time().strftime("%H:%M")

    return jsonify({"subjects": subjects})



@app.route('/admin')
def admin():
    if 'user_id' not in session:
        return redirect('/')
    return render_template('Admin_Dashboard.html')



@app.route('/dashboard-data')
def dashboard_data():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    student_id = session['user_id']
    conn, cur  = get_cursor()
    try:
        cur.execute("SELECT * FROM students WHERE student_id = %s", (student_id,))
        student = cur.fetchone()

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



@app.route('/recognize', methods=['POST'])
def recognize():
    file = request.files['image']
    path = os.path.join(UPLOAD_FOLDER, "temp.jpg")
    file.save(path)

    present, absent = recognize_faces(path)
    return jsonify({"present": present, "absent": absent})



@app.route('/test')
def test():
    return "Flask OK"

@app.route('/check-session')
def check_session():
    return {"session": dict(session)}



@app.route('/logout')
def logout():
    user_id = session.get('user_id')
    if user_id:
        try:
            conn, cur = get_cursor()
            ip = request.remote_addr
            cur.execute(
                "INSERT INTO system_logs (user_id, ip, event) VALUES (%s, %s, 'Logout')",
                (user_id, ip)
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print("Logout log error:", e)
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

    try:
        subject_id = int(subject_id)
    except ValueError:
        return jsonify([])

    conn, cur = get_cursor()
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



@app.route('/process_attendance', methods=['POST'])
def process_attendance():
    print("process_attendance called")
    print("✅ process_attendance HIT")
    print("SESSION:", session)
    if 'user_id' not in session:
        print("❌ SESSION MISSING")
        return jsonify({"error": "Session expired. Please login again."}), 401
    file       = request.files.get("image")
    subject_id = request.form.get("subject_id")
    date_str   = request.form.get("date")

    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    if not subject_id or subject_id in ("undefined", "null", ""):
        return jsonify({"error": "Invalid subject_id"}), 400

    try:
        subject_id = int(subject_id)
    except:
        return jsonify({"error": "subject_id must be integer"}), 400

    # ✅ FIX: Use Indian timezone (IST)
    from datetime import datetime
    from zoneinfo import ZoneInfo

    india_time = datetime.now(ZoneInfo("Asia/Kolkata"))

    # ✅ FIX: Proper date handling
    attendance_date = india_time.date()

    print("Server UTC time:", datetime.utcnow())
    print("India time:", india_time)
    print("Attendance date:", attendance_date)

    # Save image
    img_path = os.path.join(UPLOAD_FOLDER, "temp_upload.jpg")
file.save(img_path)

    present_names, absent_names = recognize_faces(img_path)

    conn, cur = get_cursor()

    try:
        cur.execute("SELECT student_id, name, short_name, department, phone_No FROM students")
        rows = cur.fetchall()

        student_map = {
            row["short_name"]: {
                "student_id": row["student_id"],
                "name": row["name"],
                "department": row["department"] or "-",
                "phone": str(row["phone_No"]) if row["phone_No"] else "-"
            }
            for row in rows if row["short_name"]
        }

        inserted_present = []
        inserted_absent  = []

        for short in present_names:
            if short not in student_map:
                continue

            s = student_map[short]

            try:
                cur.execute("""
            INSERT INTO attendance (student_id, subject_id, date, status, marked_by)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE status = VALUES(status), marked_by = VALUES(marked_by)
        """, (s["student_id"], subject_id, attendance_date, 'Present', 'Automatic'))



                inserted_present.append(s)

            except Exception as err:
                print("Insert PRESENT error:", err)

        for short in absent_names:
            if short not in student_map:
                continue

            s = student_map[short]

            try:
                cur.execute("""
            INSERT INTO attendance (student_id, subject_id, date, status, marked_by)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE status = VALUES(status), marked_by = VALUES(marked_by)
            """, (s["student_id"], subject_id, attendance_date, 'Absent', 'Automatic'))


                inserted_absent.append(s)

            except Exception as err:
                print("Insert ABSENT error:", err)

        conn.commit()
        print("✅ Commit successful")

    except Exception as e:
        conn.rollback()
        print("❌ DB ERROR:", e)
        return jsonify({"error": str(e)}), 500

    finally:
        cur.close()
        conn.close()

    return jsonify({
        "present": inserted_present,
        "absent": inserted_absent,
        "date": str(attendance_date)
    })

@app.route('/get-students', methods=['POST'])
def get_students():
    data       = request.get_json()
    subject_id = data.get('subject_id')
    date_str   = data.get('date')

    if not subject_id:
        return jsonify({"error": "No subject provided"}), 400
    from datetime import datetime
    from zoneinfo import ZoneInfo
    attendance_date = datetime.now(ZoneInfo("Asia/Kolkata")).date()


    print("Fetching students — subject:", subject_id, "date:", attendance_date)

    conn, cur = get_cursor()
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
            WHERE s.course = (SELECT course FROM subjects WHERE subject_id = %s LIMIT 1)
              AND s.year   = (SELECT year   FROM subjects WHERE subject_id = %s LIMIT 1)
            ORDER BY s.student_id
        """, (subject_id, attendance_date, subject_id, subject_id))
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return jsonify({"students": rows})



@app.route('/admin/dashboard-stats')
def admin_dashboard_stats():
    conn, cur = get_cursor()
    try:
        cur.execute("SELECT COUNT(*) AS cnt FROM students")
        students_count = cur.fetchone()['cnt']

        cur.execute("SELECT COUNT(*) AS cnt FROM faculty")
        faculty_count = cur.fetchone()['cnt']

        cur.execute("SELECT COUNT(*) AS cnt FROM subjects")
        subjects_count = cur.fetchone()['cnt']

        try:
            cur.execute("SELECT COUNT(*) AS cnt FROM system_logs WHERE DATE(login_time) = CURDATE()")
            logins_today = cur.fetchone()['cnt']
        except Exception:
            logins_today = 0

        try:
            cur.execute("""
                SELECT l.user_id, u.role, l.login_time
                FROM system_logs l
                JOIN users u ON l.user_id = u.user_id
                ORDER BY l.login_time DESC LIMIT 8
            """)
            recent_logs = cur.fetchall()
            for row in recent_logs:
                if row.get('login_time'):
                    row['login_time'] = str(row['login_time'])
        except Exception:
            recent_logs = []
    finally:
        cur.close()
        conn.close()

    return jsonify({
        "students":     students_count,
        "faculty":      faculty_count,
        "subjects":     subjects_count,
        "logins_today": logins_today,
        "recent_logs":  recent_logs
    })



@app.route('/admin/students')
def admin_get_students():
    conn, cur = get_cursor()
    try:
        cur.execute("SELECT * FROM students ORDER BY student_id")
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    return jsonify({"students": rows})


@app.route('/admin/students/add', methods=['POST'])
def admin_add_student():
    data = request.get_json()
    conn, cur = get_cursor()
    try:
        cur.execute("""
            INSERT INTO students (student_id, name, department, year, semester, phone_No, course, short_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data['student_id'], data['name'],       data['department'],
            data['year'],       data['semester'],   data.get('phone_No', ''),
            data['course'],     data.get('short_name', '')
        ))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    finally:
        cur.close()
        conn.close()


@app.route('/admin/students/delete/<student_id>', methods=['DELETE'])
def admin_delete_student(student_id):
    conn, cur = get_cursor()
    try:
        cur.execute("DELETE FROM students WHERE student_id=%s", (student_id,))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    finally:
        cur.close()
        conn.close()


# ════════════════════════════════════════════════════════════
# ADMIN — FACULTY
# ════════════════════════════════════════════════════════════
@app.route('/admin/faculty')
def admin_get_faculty():
    conn, cur = get_cursor()
    try:
        cur.execute("SELECT * FROM faculty ORDER BY faculty_id")
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    return jsonify({"faculty": rows})


@app.route('/admin/faculty/add', methods=['POST'])
def admin_add_faculty():
    data = request.get_json()
    conn, cur = get_cursor()
    try:
        cur.execute("""
            INSERT INTO faculty (faculty_id, name, department, email)
            VALUES (%s, %s, %s, %s)
        """, (data['faculty_id'], data['name'], data['department'], data.get('email', '')))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    finally:
        cur.close()
        conn.close()


@app.route('/admin/faculty/delete/<faculty_id>', methods=['DELETE'])
def admin_delete_faculty(faculty_id):
    conn, cur = get_cursor()
    try:
        cur.execute("DELETE FROM faculty WHERE faculty_id=%s", (faculty_id,))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    finally:
        cur.close()
        conn.close()



@app.route('/admin/subjects')
def admin_get_subjects():
    conn, cur = get_cursor()
    try:
        cur.execute("SELECT * FROM subjects ORDER BY subject_id")
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    return jsonify({"subjects": rows})


@app.route('/admin/subjects/add', methods=['POST'])
def admin_add_subject():
    data = request.get_json()
    conn, cur = get_cursor()
    try:
        cur.execute("""
            INSERT INTO subjects
                (subject_code, subject_name, faculty_name, Department, course, year, faculty_id, semester)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data['subject_code'], data['subject_name'], data['faculty_name'],
            data['Department'],   data['course'],       data['year'],
            data.get('faculty_id', ''), data['semester']
        ))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    finally:
        cur.close()
        conn.close()


@app.route('/admin/subjects/delete/<int:subject_id>', methods=['DELETE'])
def admin_delete_subject(subject_id):
    conn, cur = get_cursor()
    try:
        cur.execute("DELETE FROM subjects WHERE subject_id=%s", (subject_id,))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    finally:
        cur.close()
        conn.close()



@app.route('/admin/courses')
def admin_get_courses():
    conn, cur = get_cursor()
    try:
        cur.execute("SELECT * FROM classes ORDER BY id")
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    return jsonify({"courses": rows})


@app.route('/admin/courses/add', methods=['POST'])
def admin_add_course():
    data = request.get_json()
    conn, cur = get_cursor()
    try:
        cur.execute("""
            INSERT INTO classes (course, department, year, semester)
            VALUES (%s, %s, %s, %s)
        """, (data['course'], data['department'], data['year'], data['semester']))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    finally:
        cur.close()
        conn.close()


@app.route('/admin/courses/delete/<int:course_id>', methods=['DELETE'])
def admin_delete_course(course_id):
    conn, cur = get_cursor()
    try:
        cur.execute("DELETE FROM classes WHERE id=%s", (course_id,))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    finally:
        cur.close()
        conn.close()



@app.route('/admin/timetable')
def admin_get_timetable():
    conn, cur = get_cursor()
    try:
        cur.execute("""
            SELECT t.*, s.subject_name
            FROM timetable t
            LEFT JOIN subjects s ON t.subject_id = s.subject_id
            ORDER BY FIELD(t.day,'Monday','Tuesday','Wednesday','Thursday','Friday'), t.hours
        """)
        rows = cur.fetchall()
        for row in rows:
            if row.get('start_time') and isinstance(row['start_time'], datetime.timedelta):
                row['start_time'] = (datetime.datetime.min + row['start_time']).strftime('%H:%M')
            if row.get('end_time') and isinstance(row['end_time'], datetime.timedelta):
                row['end_time']   = (datetime.datetime.min + row['end_time']).strftime('%H:%M')
    finally:
        cur.close()
        conn.close()
    return jsonify({"timetable": rows})


@app.route('/admin/timetable/add', methods=['POST'])
def admin_add_timetable():
    data = request.get_json()
    conn, cur = get_cursor()
    try:
        cur.execute("""
            INSERT INTO timetable
                (day, start_time, end_time, subject_code, subject_id, session, session_type, hours)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data['day'],          data['start_time'],  data['end_time'],
            data['subject_code'], data['subject_id'],  data['session'],
            data.get('session_type', 'Theory'),        data['hours']
        ))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    finally:
        cur.close()
        conn.close()


@app.route('/admin/timetable/delete/<int:tid>', methods=['DELETE'])
def admin_delete_timetable(tid):
    conn, cur = get_cursor()
    try:
        cur.execute("DELETE FROM timetable WHERE id=%s", (tid,))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    finally:
        cur.close()
        conn.close()



@app.route('/admin/users')
def admin_get_users():
    conn, cur = get_cursor()
    try:
        cur.execute("SELECT user_id, role FROM users ORDER BY user_id")
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    return jsonify({"users": rows})


@app.route('/admin/users/add', methods=['POST'])
def admin_add_user():
    data = request.get_json()
    conn, cur = get_cursor()
    try:
        cur.execute("""
            INSERT INTO users (user_id, password, role) VALUES (%s, %s, %s)
        """, (data['user_id'], data['password'], data['role']))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    finally:
        cur.close()
        conn.close()


@app.route('/admin/users/delete/<user_id>', methods=['DELETE'])
def admin_delete_user(user_id):
    conn, cur = get_cursor()
    try:
        cur.execute("DELETE FROM users WHERE user_id=%s", (user_id,))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    finally:
        cur.close()
        conn.close()



@app.route('/admin/logs')
def admin_get_logs():
    role_filter = request.args.get('role', '')
    conn, cur   = get_cursor()
    try:
        if role_filter:
            cur.execute("""
                SELECT l.id, l.user_id, u.role, l.login_time, l.ip, l.event
                FROM system_logs l
                JOIN users u ON l.user_id = u.user_id
                WHERE u.role = %s
                ORDER BY l.login_time DESC LIMIT 200
            """, (role_filter,))
        else:
            cur.execute("""
                SELECT l.id, l.user_id, u.role, l.login_time, l.ip, l.event
                FROM system_logs l
                JOIN users u ON l.user_id = u.user_id
                ORDER BY l.login_time DESC LIMIT 200
            """)
        logs = cur.fetchall()
        for row in logs:
            if row.get('login_time'):
                row['login_time'] = str(row['login_time'])
        return jsonify({"logs": logs})
    except Exception as e:
        print("Logs error:", e)
        return jsonify({"logs": [], "error": str(e)})
    finally:
        cur.close()
        conn.close()



if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=8080, debug=True)
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
import json
import csv
from io import StringIO
from datetime import datetime
import os
import tempfile
import config
from speech_server import transcribe_audio
import sqlite3
import random

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# Database connection
def get_db_connection():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

class DatabaseConnection:
    def __init__(self):
        self.connection = None
    
    def cursor(self):
        if not self.connection:
            self.connection = get_db_connection()
        return self.connection.cursor()
    
    def commit(self):
        if self.connection:
            self.connection.commit()
    
    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None

mysql = DatabaseConnection()

# -------------------- DB schema bootstrap --------------------

def _table_exists(cur, table):
    cur.execute(
        """
        SELECT COUNT(*) as c FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
        """,
        (config.DB_NAME, table)
    )
    return cur.fetchone()['c'] > 0


def _column_exists(cur, table, column):
    cur.execute(
        """
        SELECT COUNT(*) as c FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s
        """,
        (config.DB_NAME, table, column)
    )
    return cur.fetchone()['c'] > 0


SCHEMA_INITIALIZED = False

def init_schema_if_needed():
    global SCHEMA_INITIALIZED
    if SCHEMA_INITIALIZED:
        return
    try:
        cur = mysql.connection.cursor()
        # Ensure users table has face and voice auth columns
        if _table_exists(cur, 'users'):
            if not _column_exists(cur, 'users', 'face_image_path'):
                cur.execute("ALTER TABLE users ADD COLUMN face_image_path VARCHAR(255)")
            if not _column_exists(cur, 'users', 'voice_sample_path'):
                cur.execute("ALTER TABLE users ADD COLUMN voice_sample_path VARCHAR(255)")
        # Ensure exams table columns
        if _table_exists(cur, 'exams'):
            if not _column_exists(cur, 'exams', 'duration'):
                cur.execute("ALTER TABLE exams ADD COLUMN duration INT NOT NULL DEFAULT 60")
            if not _column_exists(cur, 'exams', 'published'):
                cur.execute("ALTER TABLE exams ADD COLUMN published TINYINT(1) DEFAULT 0")
            if not _column_exists(cur, 'exams', 'description'):
                cur.execute("ALTER TABLE exams ADD COLUMN description TEXT")
        # Ensure submissions has unique constraint for fallback upsert
        if _table_exists(cur, 'submissions'):
            # Try add unique key (ignore if exists)
            try:
                cur.execute("ALTER TABLE submissions ADD UNIQUE KEY uniq_submission (student_id, exam_id)")
            except Exception:
                pass
        # Create exam_attempts if missing
        if not _table_exists(cur, 'exam_attempts'):
            cur.execute(
                """
                CREATE TABLE exam_attempts (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    student_id INT NOT NULL,
                    exam_id INT NOT NULL,
                    status ENUM('in_progress','completed') DEFAULT 'in_progress',
                    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    submitted_at DATETIME,
                    total_score DECIMAL(6,2),
                    UNIQUE KEY uniq_attempt (student_id, exam_id)
                )
                """
            )
        # Create answers if missing
        if not _table_exists(cur, 'answers'):
            cur.execute(
                """
                CREATE TABLE answers (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    student_id INT NOT NULL,
                    exam_id INT NOT NULL,
                    question_id INT NOT NULL,
                    answer_text LONGTEXT,
                    selected_option VARCHAR(4),
                    is_correct TINYINT(1),
                    score DECIMAL(5,2),
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uniq_answer (student_id, exam_id, question_id)
                )
                """
            )
        mysql.connection.commit()
        cur.close()
    except Exception:
        # Silent fail to avoid blocking app startup
        pass
    SCHEMA_INITIALIZED = True

@app.before_request
def _schema_bootstrap():
    init_schema_if_needed()


# -------------------- Utility helpers --------------------

def require_login(role=None):
    def decorator(func):
        def wrapper(*args, **kwargs):
            if 'loggedin' not in session:
                return redirect(url_for('login'))
            if role and session.get('role') != role:
                return redirect(url_for('login'))
            return func(*args, **kwargs)
        wrapper.__name__ = func.__name__
        return wrapper
    return decorator


def fetch_exam(exam_id, ensure_published=False):
    cur = mysql.connection.cursor()
    # Avoid selecting non-existent columns like description on older schemas
    if ensure_published:
        cur.execute("SELECT id, title, duration, created_by, published FROM exams WHERE id=%s AND published=TRUE", [exam_id])
    else:
        cur.execute("SELECT id, title, duration, created_by, published FROM exams WHERE id=%s", [exam_id])
    exam = cur.fetchone()
    cur.close()
    return exam


def fetch_questions(exam_id):
    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT id, question_text, question_type, options, correct_answer FROM questions WHERE exam_id=%s ORDER BY id ASC",
        [exam_id]
    )
    questions = cur.fetchall()
    cur.close()
    # Normalize options JSON if present
    for q in questions:
        if q['options']:
            try:
                q['options'] = json.loads(q['options'])
            except Exception:
                # fallback: parse comma or newline as list and map to A-D
                opts = [o.strip() for o in q['options'].replace('\n', ',').split(',') if o.strip()]
                letters = ['A', 'B', 'C', 'D', 'E', 'F']
                q['options'] = {letters[i]: opts[i] for i in range(min(len(opts), len(letters)))}
        else:
            q['options'] = None
    return questions


def ensure_attempt(student_id, exam_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT id FROM exam_attempts WHERE student_id=%s AND exam_id=%s", (student_id, exam_id))
    attempt = cur.fetchone()
    if not attempt:
        cur.execute("INSERT INTO exam_attempts(student_id, exam_id, status) VALUES(%s, %s, 'in_progress')", (student_id, exam_id))
        mysql.connection.commit()
        attempt_id = cur.lastrowid
    else:
        attempt_id = attempt['id']
    cur.close()
    return attempt_id


def recalc_total_score(student_id, exam_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT COALESCE(SUM(score),0) as total FROM answers WHERE student_id=%s AND exam_id=%s", (student_id, exam_id))
    total = cur.fetchone()['total'] if cur.rowcount else 0
    cur.execute("UPDATE exam_attempts SET total_score=%s WHERE student_id=%s AND exam_id=%s", (total, student_id, exam_id))
    mysql.connection.commit()
    cur.close()
    return total


def auto_score_mcq_for_student(student_id, exam_id):
    # Evaluate MCQ answers by comparing selected_option or answer_text with correct_answer
    cur = mysql.connection.cursor()
    cur.execute(
        """
        SELECT a.id as answer_id, a.selected_option, a.answer_text, q.correct_answer, q.id as question_id
        FROM answers a
        JOIN questions q ON q.id=a.question_id
        WHERE a.student_id=%s AND a.exam_id=%s AND q.question_type='MCQ'
        """,
        (student_id, exam_id)
    )
    rows = cur.fetchall()
    for r in rows:
        is_correct = None
        if r['selected_option'] and r['correct_answer']:
            is_correct = (r['selected_option'].strip().upper() == r['correct_answer'].strip().upper())
        elif r['answer_text'] and r['correct_answer']:
            is_correct = (r['answer_text'].strip().lower() == r['correct_answer'].strip().lower())
        score = 1.0 if is_correct else 0.0
        cur.execute("UPDATE answers SET is_correct=%s, score=%s WHERE id=%s", (is_correct, score, r['answer_id']))
    mysql.connection.commit()
    cur.close()


# -------------------- Routes --------------------

@app.route('/')
def home():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']

        cur = mysql.connection.cursor()
        cur.execute("SELECT id, username, password, role FROM users WHERE username=%s AND role=%s", (username, role))
        user = cur.fetchone()
        cur.close()

        if user and password == user['password']:
            session['loggedin'] = True
            session['id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']

            if role == 'student':
                return redirect(url_for('student_dashboard'))
            else:
                return redirect(url_for('teacher_dashboard'))
        else:
            return render_template('login.html', error='Invalid credentials')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']

        try:
            cur = mysql.connection.cursor()
            cur.execute("INSERT INTO users(username, password, role) VALUES(%s, %s, %s)", (username, password, role))
            mysql.connection.commit()
            cur.close()
        except Exception as e:
            return render_template('register.html', error='Registration failed: {}'.format(str(e)))

        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/face_voice_auth', methods=['GET'])
def face_voice_auth():
    username = request.args.get('username')
    return render_template('face_voice_auth.html', username=username)


@app.route('/save_auth', methods=['POST'])
def save_auth():
    try:
        username = request.form['username']
        face_image = request.files['face']
        voice_sample = request.files['voice']

        # Ensure the user exists
        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM users WHERE username = %s", [username])
        user = cur.fetchone()
        cur.close()

        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        # Create a directory for the user if it doesn't exist
        user_auth_dir = os.path.join(app.root_path, 'uploads', 'auth_data', username)
        os.makedirs(user_auth_dir, exist_ok=True)

        # Save the files
        face_image_path = os.path.join(user_auth_dir, 'face.jpg')
        voice_sample_path = os.path.join(user_auth_dir, 'voice.webm')
        face_image.save(face_image_path)
        voice_sample.save(voice_sample_path)

        # Update the database
        cur = mysql.connection.cursor()
        cur.execute(
            "UPDATE users SET face_image_path = %s, voice_sample_path = %s WHERE username = %s",
            (face_image_path, voice_sample_path, username)
        )
        mysql.connection.commit()
        cur.close()

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500




# Dedicated signup route rendering signup.html
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', '').strip() or 'student'
        if not username or not password or role not in ('student','teacher'):
            return render_template('signup.html', error='Please fill all fields and choose a valid role.')
        try:
            cur = mysql.connection.cursor()
            cur.execute("INSERT INTO users(username, password, role) VALUES(%s, %s, %s)", (username, password, role))
            mysql.connection.commit()
            cur.close()
            return redirect(url_for('login'))
        except Exception as e:
            return render_template('signup.html', error='Registration failed: {}'.format(str(e)))
    return render_template('signup.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# -------------------- Teacher/Admin Dashboard --------------------

@app.route('/teacher/dashboard')
@require_login('teacher')
def teacher_dashboard():
    cur = mysql.connection.cursor()
    # Avoid dependency on created_at/description to work with older schemas
    cur.execute("SELECT id, title, duration, published FROM exams WHERE created_by=%s ORDER BY id DESC", [session['id']])
    exams = cur.fetchall()
    cur.close()
    return render_template('admin_dashboard.html', exams=exams)


@app.route('/create_exam', methods=['GET'])
@require_login('teacher')
def create_exam():
    return render_template('create_exam.html')


@app.route('/save_exam', methods=['POST'])
@require_login('teacher')
def save_exam():
    try:
        data = request.get_json(force=True)
        title = data.get('title') or data.get('examTitle')
        description = data.get('description')
        duration = int(data.get('duration'))
        questions = data.get('questions', [])

        if not title or not duration or not isinstance(questions, list) or len(questions) == 0:
            return jsonify({'success': False, 'message': 'Invalid payload'}), 400

        cur = mysql.connection.cursor()
        exam_id = None
        # Try insert with description; if column doesn't exist, fallback without it
        try:
            cur.execute(
                "INSERT INTO exams(title, description, duration, created_by, published) VALUES(%s, %s, %s, %s, FALSE)",
                (title, description, duration, session['id'])
            )
            mysql.connection.commit()
            exam_id = cur.lastrowid
        except Exception:
            cur.execute(
                "INSERT INTO exams(title, duration, created_by, published) VALUES(%s, %s, %s, FALSE)",
                (title, duration, session['id'])
            )
            mysql.connection.commit()
            exam_id = cur.lastrowid

        for idx, q in enumerate(questions, start=1):
            q_text = q.get('text') or q.get('question_text')
            q_type = q.get('type') or q.get('question_type')
            options = q.get('options')
            correct = q.get('correct') or q.get('correct_answer')
            options_json = json.dumps(options) if options else None
            cur.execute(
                "INSERT INTO questions(exam_id, question_text, question_type, options, correct_answer) VALUES(%s, %s, %s, %s, %s)",
                (exam_id, q_text, q_type, options_json, correct)
            )
        mysql.connection.commit()
        cur.close()
        return jsonify({'success': True, 'exam_id': exam_id, 'message': 'Exam saved successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/publish_exam/<int:exam_id>', methods=['POST'])
@require_login('teacher')
def publish_exam(exam_id):
    try:
        cur = mysql.connection.cursor()
        cur.execute("UPDATE exams SET published=TRUE WHERE id=%s AND created_by=%s", (exam_id, session['id']))
        mysql.connection.commit()
        cur.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# Backward-compatible publish endpoint
@app.route('/teacher/exams/<int:exam_id>/publish', methods=['POST'])
@require_login('teacher')
def publish_exam_legacy(exam_id):
    return publish_exam(exam_id)


@app.route('/delete_exam/<int:exam_id>', methods=['DELETE'])
@require_login('teacher')
def delete_exam(exam_id):
    try:
        # Ensure ownership
        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM exams WHERE id=%s AND created_by=%s", (exam_id, session['id']))
        if not cur.fetchone():
            cur.close()
            return jsonify({'success': False, 'message': 'Not found or not allowed'}), 404
        # Delete in order: answers -> attempts -> questions -> exam
        cur.execute("DELETE FROM answers WHERE exam_id=%s", [exam_id])
        cur.execute("DELETE FROM exam_attempts WHERE exam_id=%s", [exam_id])
        cur.execute("DELETE FROM questions WHERE exam_id=%s", [exam_id])
        cur.execute("DELETE FROM exams WHERE id=%s", [exam_id])
        mysql.connection.commit()
        cur.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/view_attempts/<int:exam_id>', methods=['GET'])
@require_login('teacher')
def view_attempts(exam_id):
    try:
        cur = mysql.connection.cursor()
        cur.execute(
            """
            SELECT a.student_id, u.username, a.status, a.total_score, a.started_at, a.submitted_at
            FROM exam_attempts a
            JOIN users u ON u.id=a.student_id
            WHERE a.exam_id=%s
            ORDER BY a.submitted_at DESC, a.started_at DESC
            """,
            [exam_id]
        )
        attempts = cur.fetchall()
        cur.close()
        return jsonify({'success': True, 'attempts': attempts})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# -------------------- Student Dashboard --------------------

@app.route('/student/dashboard')
@require_login('student')
def student_dashboard():
    return render_template('student_dashboard.html')


@app.route('/student/exams')
@require_login('student')
def student_exams():
    cur = mysql.connection.cursor()
    try:
        cur.execute(
            """
            SELECT e.id, e.title, e.duration
            FROM exams e
            WHERE e.published=TRUE
            AND NOT EXISTS (
                SELECT 1 FROM exam_attempts a WHERE a.student_id=%s AND a.exam_id=e.id
            )
            ORDER BY e.id DESC
            """,
            [session['id']]
        )
        exams = cur.fetchall()
    except Exception:
        # Fallback when exam_attempts table does not exist in older schema
        cur.execute("SELECT id, title, duration FROM exams WHERE published=TRUE ORDER BY id DESC")
        exams = cur.fetchall()
    finally:
        cur.close()
    return jsonify({'exams': exams})


@app.route('/student/exams_status')
@require_login('student')
def student_exams_status():
    cur = mysql.connection.cursor()
    # Try using exam_attempts for both available and completed
    try:
        cur.execute(
            """
            SELECT e.id, e.title, e.duration
            FROM exams e
            WHERE e.published=TRUE
            AND NOT EXISTS (
                SELECT 1 FROM exam_attempts a WHERE a.student_id=%s AND a.exam_id=e.id
            )
            ORDER BY e.id DESC
            """,
            [session['id']]
        )
        available = cur.fetchall()
        cur.execute(
            """
            SELECT e.id, e.title, e.duration
            FROM exams e
            WHERE e.published=TRUE
            AND EXISTS (
                SELECT 1 FROM exam_attempts a WHERE a.student_id=%s AND a.exam_id=e.id AND a.status='completed'
            )
            ORDER BY e.id DESC
            """,
            [session['id']]
        )
        completed = cur.fetchall()
        cur.close()
        return jsonify({'available': available, 'completed': completed})
    except Exception:
        # Fallback using legacy submissions table
        try:
            cur.execute(
                """
                SELECT e.id, e.title, e.duration
                FROM exams e
                WHERE e.published=TRUE AND e.id NOT IN (
                  SELECT s.exam_id FROM submissions s WHERE s.student_id=%s
                )
                ORDER BY e.id DESC
                """,
                [session['id']]
            )
            available = cur.fetchall()
            cur.execute(
                """
                SELECT e.id, e.title, e.duration
                FROM exams e
                WHERE e.published=TRUE AND e.id IN (
                  SELECT s.exam_id FROM submissions s WHERE s.student_id=%s
                )
                ORDER BY e.id DESC
                """,
                [session['id']]
            )
            completed = cur.fetchall()
            cur.close()
            return jsonify({'available': available, 'completed': completed})
        except Exception:
            cur.close()
            return jsonify({'available': [], 'completed': []})


# -------------------- Take Exam, Autosave, Submit --------------------

@app.route('/take_exam/<int:exam_id>')
@require_login('student')
def take_exam(exam_id):
    exam = fetch_exam(exam_id, ensure_published=True)
    if not exam:
        return "Exam not found or not published.", 404

    # Ensure attempt exists (tolerate missing table on older schema)
    try:
        ensure_attempt(session['id'], exam_id)
    except Exception:
        pass

    questions = fetch_questions(exam_id)

    # Preload existing answers if any (tolerate missing table)
    answers = {}
    try:
        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT question_id, answer_text, selected_option FROM answers WHERE student_id=%s AND exam_id=%s",
            (session['id'], exam_id)
        )
        answers = {row['question_id']: {'answer_text': row['answer_text'], 'selected_option': row['selected_option']} for row in cur.fetchall()}
        cur.close()
    except Exception:
        answers = {}

    exam_payload = {
        'id': exam['id'],
        'title': exam['title'],
        'description': exam.get('description'),
        'duration': exam['duration'],
        'questions': questions,
        'answers': answers
    }

    return render_template('take_exam.html', exam_json=json.dumps(exam_payload))


@app.route('/autosave', methods=['POST'])
@require_login('student')
def autosave():
    try:
        payload = request.get_json(force=True)
        exam_id = int(payload['exam_id'])
        answers = payload.get('answers', [])

        # Ensure attempt exists (tolerate missing table)
        try:
            ensure_attempt(session['id'], exam_id)
        except Exception:
            pass

        cur = mysql.connection.cursor()
        for ans in answers:
            qid = int(ans['question_id'])
            answer_text = ans.get('answer_text')
            selected_option = (ans.get('selected_option') or '').strip().upper() or None

            # Determine MCQ correctness on save (optional, will be finalized on submit)
            cur.execute("SELECT question_type, correct_answer FROM questions WHERE id=%s", [qid])
            q = cur.fetchone()
            is_correct = None
            score = None
            if q and q['question_type'] == 'MCQ' and selected_option and q['correct_answer']:
                is_correct = (selected_option == q['correct_answer'].strip().upper())
                score = 1.0 if is_correct else 0.0

            cur.execute(
                """
                INSERT INTO answers(student_id, exam_id, question_id, answer_text, selected_option, is_correct, score)
                VALUES(%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    answer_text=VALUES(answer_text),
                    selected_option=VALUES(selected_option),
                    is_correct=VALUES(is_correct),
                    score=COALESCE(VALUES(score), score)
                """,
                (session['id'], exam_id, qid, answer_text, selected_option, is_correct, score)
            )
        mysql.connection.commit()
        cur.close()

        # Optionally recalc partial total (without descriptive scores)
        recalc_total_score(session['id'], exam_id)
        return jsonify({'success': True, 'message': 'Progress auto-saved'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/proctoring/log', methods=['POST'])
@require_login('student')
def proctoring_log():
    try:
        payload = request.get_json(force=True)
        exam_id = int(payload['exam_id'])
        event_type = payload['event_type']
        
        attempt_id = ensure_attempt(session['id'], exam_id)
        
        cur = mysql.connection.cursor()
        cur.execute(
            "INSERT INTO proctoring_logs(attempt_id, event_type, timestamp) VALUES(%s, %s, %s)",
            (attempt_id, event_type, datetime.utcnow())
        )
        mysql.connection.commit()
        cur.close()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

import threading

import shutil

def record_audit_event(event_name, status, related_id=None, related_type=None, details=None):

    try:

        cur = mysql.connection.cursor()

        cur.execute(

            """

            INSERT INTO audit_events(event_name, status, related_id, related_type, details)

            VALUES (%s, %s, %s, %s, %s)

            """,

            (event_name, status, related_id, related_type, details)

        )

        mysql.connection.commit()

        cur.close()

    except Exception as e:

        print(f"Failed to record audit event: {e}")

def assemble_video_chunks(attempt_id):

    upload_folder = os.path.join(app.root_path, 'uploads', str(attempt_id))

    

    try:

        record_audit_event('video_assembly_started', 'in_progress', attempt_id, 'exam_attempt')

        

        if not os.path.exists(upload_folder):

            print(f"Assembly failed: Upload folder not found for attempt {attempt_id}")

            record_audit_event('video_assembly_failed', 'error', attempt_id, 'exam_attempt', 'Upload folder not found')

            return



        chunks = sorted(

            [f for f in os.listdir(upload_folder) if f.startswith('chunk_')],

            key=lambda x: int(x.split('_')[1].split('.')[0])

        )

        

        if not chunks:

            print(f"Assembly failed: No chunks found for attempt {attempt_id}")

            record_audit_event('video_assembly_failed', 'error', attempt_id, 'exam_attempt', 'No video chunks found')

            return



        assembled_video_path = os.path.join(upload_folder, 'assembled.webm')

        with open(assembled_video_path, 'wb') as assembled_file:

            for chunk_name in chunks:

                chunk_path = os.path.join(upload_folder, chunk_name)

                with open(chunk_path, 'rb') as chunk_file:

                    assembled_file.write(chunk_file.read())

        

        if config.PROCTORING_STORE_IN_DB:

            with open(assembled_video_path, 'rb') as f:

                video_blob = f.read()

            

            cur = mysql.connection.cursor()

            cur.execute(

                "INSERT INTO proctoring_videos(attempt_id, video_blob) VALUES (%s, %s)",

                (attempt_id, video_blob)

            )

            mysql.connection.commit()

            cur.close()

            record_audit_event('video_stored_in_db', 'success', attempt_id, 'exam_attempt')



        # Clean up chunk files

        for chunk_name in chunks:

            os.remove(os.path.join(upload_folder, chunk_name))

        

        record_audit_event('video_assembly_completed', 'success', attempt_id, 'exam_attempt')



    except Exception as e:

        print(f"Error during video assembly for attempt {attempt_id}: {e}")

        record_audit_event('video_assembly_failed', 'error', attempt_id, 'exam_attempt', str(e))

@app.route('/proctoring/chunk', methods=['POST'])

@require_login('student')

def proctoring_chunk():

    try:

        exam_id = int(request.form['exam_id'])

        chunk_order = int(request.form['chunk_order'])

        video_chunk = request.files['video_chunk']

        

        attempt_id = ensure_attempt(session['id'], exam_id)

        

        upload_folder = os.path.join(app.root_path, 'uploads', str(attempt_id))

        os.makedirs(upload_folder, exist_ok=True)

        chunk_path = os.path.join(upload_folder, f'chunk_{chunk_order}.webm')

        video_chunk.save(chunk_path)

        

        record_audit_event('video_chunk_uploaded', 'success', attempt_id, 'exam_attempt', f'Chunk {chunk_order} saved')

        

        return jsonify({'success': True})

    except Exception as e:

        return jsonify({'success': False, 'message': str(e)}), 500



@app.route('/proctoring/video/<int:attempt_id>')

@require_login('teacher')

def proctoring_video(attempt_id):

    if not config.PROCTORING_STORE_IN_DB:

        return "Video streaming is disabled.", 404



    cur = mysql.connection.cursor()

    cur.execute("SELECT video_blob FROM proctoring_videos WHERE attempt_id = %s", [attempt_id])

    video = cur.fetchone()

    cur.close()



    if not video or not video['video_blob']:

        return "Video not found.", 404



    video_blob = video['video_blob']

    video_size = len(video_blob)



    range_header = request.headers.get('Range', None)

    if not range_header:

        resp = Response(video_blob, mimetype='video/webm')

        resp.headers.add('Content-Length', str(video_size))

        return resp



    byte1, byte2 = 0, None

    import re
    m = re.search(r'(\d+)-(\d*)', range_header)

    g = m.groups()



    if g[0]: byte1 = int(g[0])

    if g[1]: byte2 = int(g[1])



    length = video_size - byte1

    if byte2 is not None:

        length = byte2 - byte1



    data = video_blob[byte1:byte1 + length]

    resp = Response(data, 206, mimetype='video/webm', direct_passthrough=True)

    resp.headers.add('Content-Range', f'bytes {byte1}-{byte1 + length - 1}/{video_size}')

    return resp

@app.route('/submit_exam/<int:exam_id>', methods=['POST'])

@require_login('student')

def submit_exam(exam_id):

    try:

        # Final autosave before submission

        # The request body is empty, so we can't rely on it.

        # The client should have already saved the final answers.

        

        # Auto-score MCQs and compute total

        auto_score_mcq_for_student(session['id'], exam_id)

        total = recalc_total_score(session['id'], exam_id)

        

        # Mark attempt as completed

        cur = mysql.connection.cursor()

        cur.execute(

            "UPDATE exam_attempts SET status='completed', submitted_at=%s WHERE student_id=%s AND exam_id=%s",

            (datetime.utcnow(), session['id'], exam_id)

        )

        mysql.connection.commit()

        attempt_id = cur.lastrowid

        cur.close()



        # Start video assembly in a background thread

        assembly_thread = threading.Thread(target=assemble_video_chunks, args=(attempt_id,))

        assembly_thread.start()

        

        record_audit_event('exam_submitted', 'success', attempt_id, 'exam_attempt')



        return jsonify({'success': True, 'redirect': url_for('student_dashboard'), 'total': total})

    except Exception as e:

        return jsonify({'success': False, 'message': str(e)}), 500





# -------------------- Results --------------------



@app.route('/results/<int:exam_id>')

@require_login()

def results(exam_id):

    exam = fetch_exam(exam_id)

    if not exam:

        return "Exam not found", 404



    cur = mysql.connection.cursor()



    if session['role'] == 'student':

        # Fetch this student's answers

        cur.execute(

            """

            SELECT q.id as question_id, q.question_text, q.question_type, q.correct_answer,

                   a.answer_text, a.selected_option, a.is_correct, a.score

            FROM questions q

            LEFT JOIN answers a ON a.question_id=q.id AND a.student_id=%s AND a.exam_id=%s

            WHERE q.exam_id=%s

            ORDER BY q.id ASC

            """,

            (session['id'], exam_id, exam_id)

        )

        qas = cur.fetchall()

        cur.execute("SELECT total_score, status FROM exam_attempts WHERE student_id=%s AND exam_id=%s", (session['id'], exam_id))

        attempt = cur.fetchone()

        cur.close()

        return render_template('results.html', role='student', exam=exam, qas=qas, attempt=attempt)

    

    # Teacher/Admin view: list all students who took the exam

    cur.execute(

        """

        SELECT u.username, a.id as attempt_id, a.total_score, a.status, a.started_at, a.submitted_at

        FROM exam_attempts a

        JOIN users u ON u.id=a.student_id

        WHERE a.exam_id=%s

        ORDER BY a.submitted_at DESC

        """,

        [exam_id]

    )

    students = cur.fetchall()

    cur.close()

    return render_template('results.html', role='teacher', exam=exam, students=students)





@app.route('/evaluate_exam/<int:exam_id>')

@require_login('teacher')

def evaluate_exam(exam_id):

    """

    Loads all student submissions for the given exam and renders the evaluation page.

    """

    exam = fetch_exam(exam_id)

    if not exam:

        return "Exam not found", 404



    cur = mysql.connection.cursor()

    # Get all students who attempted the exam

    cur.execute(

        """

        SELECT a.student_id, u.username, a.status, a.total_score

        FROM exam_attempts a

        JOIN users u ON u.id=a.student_id

        WHERE a.exam_id=%s

        ORDER BY a.submitted_at DESC, a.started_at DESC

        """,

        [exam_id]

    )

    students = cur.fetchall()



    # For each student, fetch their answers

    student_answers = {}

    for student in students:

        cur.execute(

            """

            SELECT q.id as question_id, q.question_text, q.question_type, q.correct_answer,

                   a.answer_text, a.selected_option, a.is_correct, a.score

            FROM questions q

            LEFT JOIN answers a ON a.question_id=q.id AND a.student_id=%s AND a.exam_id=%s

            WHERE q.exam_id=%s

            ORDER BY q.id ASC

            """,

            (student['student_id'], exam_id, exam_id)

        )

        student_answers[student['student_id']] = cur.fetchall()

    cur.close()



    return render_template('evaluate_exam.html', exam=exam, students=students, student_answers=student_answers)





@app.route('/grade/<int:exam_id>', methods=['POST'])

@require_login('teacher')

def grade_descriptive(exam_id):

    try:

        data = request.get_json(force=True)

        grades = data.get('grades', [])

        cur = mysql.connection.cursor()

        for g in grades:

            student_id = int(g['student_id'])

            question_id = int(g['question_id'])

            score = float(g['score'])

            cur.execute(

                "UPDATE answers SET score=%s WHERE student_id=%s AND exam_id=%s AND question_id=%s",

                (score, student_id, exam_id, question_id)

            )

            # Recalculate total per student

            recalc_total_score(student_id, exam_id)

        mysql.connection.commit()

        cur.close()

        return jsonify({'success': True})

    except Exception as e:

        return jsonify({'success': False, 'message': str(e)}), 500





@app.route('/plagiarism_check', methods=['POST'])

@require_login('teacher')

def plagiarism_check():

    try:

        data = request.get_json(force=True)

        text = data.get('text', '')

        # In a real application, you would use a plagiarism checking API

        # For now, we'll just return a random percentage

        plagiarism_percentage = random.uniform(0, 100)

        return jsonify({'success': True, 'plagiarism_percentage': plagiarism_percentage})

    except Exception as e:

        return jsonify({'success': False, 'message': str(e)}), 500





@app.route('/download_results/<int:exam_id>')

@require_login('teacher')

def download_results(exam_id):

    # Export CSV of students and their scores

    cur = mysql.connection.cursor()

    cur.execute(

        """

        SELECT u.username, a.total_score, a.status, a.started_at, a.submitted_at

        FROM exam_attempts a

        JOIN users u ON u.id=a.student_id

        WHERE a.exam_id=%s

        ORDER BY a.submitted_at DESC

        """,

        [exam_id]

    )

    rows = cur.fetchall()

    cur.close()



    si = StringIO()

    writer = csv.writer(si)

    writer.writerow(['Username', 'Total Score', 'Status', 'Started At', 'Submitted At'])

    for r in rows:

        writer.writerow([r['username'], r['total_score'], r['status'], r['started_at'], r['submitted_at']])



    output = si.getvalue()

    return Response(

        output,

        mimetype='text/csv',

        headers={'Content-Disposition': f'attachment; filename=exam_{exam_id}_results.csv'}

    )





# -------- Whisper transcription endpoint --------

@app.route('/transcribe', methods=['POST'])

def transcribe():

    print("Transcribe endpoint called")

    try:

        audio_file = request.files.get('audio')

        language = request.form.get('language', 'en')

        if not audio_file:

            print("No audio file provided")

            return jsonify({'success': False, 'message': 'No audio provided'}), 400



        with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as tmp:

            audio_path = tmp.name

            audio_file.save(audio_path)

        

        print(f"Audio saved to temporary file: {audio_path}")

        print(f"Saved file size: {os.path.getsize(audio_path)} bytes")  # <-- Added file size logging



        text = None

        try:

            text = transcribe_audio(audio_path, language=language)

            print(f"speech_server transcription successful: {text}")

        except Exception as e:

            print(f"speech_server transcription failed: {e}")

            text = None



        try:

            os.unlink(audio_path)

            print(f"Temporary file {audio_path} deleted.")

        except Exception as e:

            print(f"Error deleting temporary file {audio_path}: {e}")



        if not text:

            print("Transcription engine unavailable.")

            return jsonify({'success': False, 'message': 'Transcription engine unavailable'}), 500



        print(f"Transcription result: {text.strip()}")

        return jsonify({'success': True, 'text': text.strip()})

    except Exception as e:

        print(f"An error occurred in the transcribe endpoint: {e}")

        return jsonify({'success': False, 'message': str(e)}), 500





@app.route('/exam_instructions')

@require_login('student')

def exam_instructions():

    exam_id = request.args.get('exam_id')

    if not exam_id:

        return "Exam ID missing.", 400

    exam = fetch_exam(exam_id, ensure_published=True)

    if not exam:

        return "Exam not found.", 404

    return render_template('exam_instructions.html', exam=exam)



@app.route('/upload_chunk', methods=['POST'])

def upload_chunk():

    exam_id = request.form.get('exam_id')

    student_id = request.form.get('student_id')

    chunk_index = request.form.get('chunk_index')

    timestamp = request.form.get('timestamp')

    video_chunk = request.files.get('video_chunk')

    if not (exam_id and student_id and video_chunk):

        return jsonify({'success': False, 'message': 'Missing data'}), 400

    chunk_dir = os.path.join('proctor_chunks', f'exam_{exam_id}', f'student_{student_id}')

    os.makedirs(chunk_dir, exist_ok=True)

    chunk_path = os.path.join(chunk_dir, f'chunk_{chunk_index}_{timestamp}.webm')

    video_chunk.save(chunk_path)

    return jsonify({'success': True, 'path': chunk_path})



@app.route('/proctoring/results/<int:attempt_id>')

@require_login('teacher')

def proctoring_results(attempt_id):

    cur = mysql.connection.cursor()

    

    # Fetch attempt details

    cur.execute(

        """

        SELECT e.title as exam_title, u.username as student_username

        FROM exam_attempts ea

        JOIN exams e ON e.id = ea.exam_id

        JOIN users u ON u.id = ea.student_id

        WHERE ea.id = %s

        """,

        [attempt_id]

    )

    attempt = cur.fetchone()

    

    # Fetch proctoring logs

    cur.execute(

        "SELECT event_type, timestamp, screenshot_path FROM proctoring_logs WHERE attempt_id = %s ORDER BY timestamp ASC",

        [attempt_id]

    )

    logs = cur.fetchall()

    

    cur.close()

    

    return render_template('proctoring_results.html', attempt=attempt, logs=logs, attempt_id=attempt_id)



from flask import send_from_directory



# ... (existing code)



@app.route('/uploads/<path:filename>')

def uploaded_file(filename):

    return send_from_directory(os.path.join(app.root_path, 'uploads'), filename)



if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=config.FLASK_ENV == 'development')

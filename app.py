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
    if config.DATABASE_URL:
        # Production PostgreSQL
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(config.DATABASE_URL)
        return conn
    else:
        # Local SQLite
        conn = sqlite3.connect(config.DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def get_cursor(conn):
    if config.DATABASE_URL:
        return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        return conn.cursor()

class DatabaseConnection:
    def __init__(self):
        pass
    
    def cursor(self):
        self.connection = get_db_connection()
        return self.connection.cursor()
    
    def commit(self):
        if hasattr(self, 'connection') and self.connection:
            self.connection.commit()
    
    def close(self):
        if hasattr(self, 'connection') and self.connection:
            self.connection.close()

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
        # Skip schema initialization for SQLite as it uses MySQL syntax
        pass
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
    conn = get_db_connection()
    cur = get_cursor(conn)
    if ensure_published:
        if config.DATABASE_URL:
            cur.execute("SELECT id, title, duration, created_by, published FROM exams WHERE id=%s AND published=true", [exam_id])
        else:
            cur.execute("SELECT id, title, duration, created_by, published FROM exams WHERE id=? AND published=1", [exam_id])
    else:
        if config.DATABASE_URL:
            cur.execute("SELECT id, title, duration, created_by, published FROM exams WHERE id=%s", [exam_id])
        else:
            cur.execute("SELECT id, title, duration, created_by, published FROM exams WHERE id=?", [exam_id])
    exam = cur.fetchone()
    conn.close()
    return exam


def fetch_questions(exam_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, question_text, question_type, options, correct_answer FROM questions WHERE exam_id=? ORDER BY id ASC",
        [exam_id]
    )
    questions = cur.fetchall()
    conn.close()
    # Convert sqlite3.Row to dict and normalize options JSON if present
    result = []
    for q in questions:
        q_dict = dict(q)
        if q_dict['options']:
            try:
                q_dict['options'] = json.loads(q_dict['options'])
            except Exception:
                # fallback: parse comma or newline as list and map to A-D
                opts = [o.strip() for o in q_dict['options'].replace('\n', ',').split(',') if o.strip()]
                letters = ['A', 'B', 'C', 'D', 'E', 'F']
                q_dict['options'] = {letters[i]: opts[i] for i in range(min(len(opts), len(letters)))}
        else:
            q_dict['options'] = None
        result.append(q_dict)
    return result


def ensure_attempt(student_id, exam_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM exam_attempts WHERE student_id=? AND exam_id=?", (student_id, exam_id))
    attempt = cur.fetchone()
    if not attempt:
        cur.execute("INSERT INTO exam_attempts(student_id, exam_id, status) VALUES(?, ?, 'in_progress')", (student_id, exam_id))
        conn.commit()
        attempt_id = cur.lastrowid
    else:
        attempt_id = attempt['id']
    conn.close()
    return attempt_id


def recalc_total_score(student_id, exam_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(score),0) as total FROM answers WHERE student_id=? AND exam_id=?", (student_id, exam_id))
    result = cur.fetchone()
    total = result['total'] if result else 0
    cur.execute("UPDATE exam_attempts SET total_score=? WHERE student_id=? AND exam_id=?", (total, student_id, exam_id))
    conn.commit()
    conn.close()
    return total


def auto_score_mcq_for_student(student_id, exam_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT a.id as answer_id, a.selected_option, a.answer_text, q.correct_answer, q.id as question_id
        FROM answers a
        JOIN questions q ON q.id=a.question_id
        WHERE a.student_id=? AND a.exam_id=? AND q.question_type='MCQ'
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
        cur.execute("UPDATE answers SET is_correct=?, score=? WHERE id=?", (is_correct, score, r['answer_id']))
    conn.commit()
    conn.close()


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

        conn = get_db_connection()
        cur = get_cursor(conn)
        if config.DATABASE_URL:
            cur.execute("SELECT id, username, password, role FROM users WHERE username=%s AND role=%s", (username, role))
        else:
            cur.execute("SELECT id, username, password, role FROM users WHERE username=? AND role=?", (username, role))
        user = cur.fetchone()
        conn.close()

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
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO users(username, password, role) VALUES(?, ?, ?)", (username, password, role))
            conn.commit()
            conn.close()
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
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = ?", [username])
        user = cur.fetchone()
        
        if not user:
            conn.close()
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
        cur.execute(
            "UPDATE users SET face_image_path = ?, voice_sample_path = ? WHERE username = ?",
            (face_image_path, voice_sample_path, username)
        )
        conn.commit()
        conn.close()

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
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO users(username, password, role) VALUES(?, ?, ?)", (username, password, role))
            conn.commit()
            conn.close()
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
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, title, duration, published FROM exams WHERE created_by=? ORDER BY id DESC", [session['id']])
    exams = cur.fetchall()
    cur.execute("SELECT id, title, due_date, published FROM assignments WHERE created_by=? ORDER BY id DESC", [session['id']])
    assignments = cur.fetchall()
    conn.close()
    return render_template('admin_dashboard.html', exams=exams, assignments=assignments)


@app.route('/create_exam', methods=['GET'])
@require_login('teacher')
def create_exam():
    return render_template('create_exam.html')

@app.route('/create_assignment', methods=['GET'])
@require_login('teacher')
def create_assignment():
    return render_template('create_assignment.html')

@app.route('/save_assignment', methods=['POST'])
@require_login('teacher')
def save_assignment():
    try:
        print("Save assignment called")
        title = request.form.get('title')
        print(f"Title: {title}")
        
        if not title:
            return jsonify({'success': False, 'message': 'Title is required'}), 400
        
        assignment_type = request.form.get('assignment_type', 'questions')
        description = request.form.get('description', '')
        due_date = request.form.get('due_date')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Create assignment
        cur.execute(
            "INSERT INTO assignments(title, description, created_by, due_date, assignment_type) VALUES(?, ?, ?, ?, ?)",
            (title, description, session['id'], due_date, assignment_type)
        )
        assignment_id = cur.lastrowid
        print(f"Assignment created with ID: {assignment_id}")
        
        # Handle questions if assignment_type is 'questions'
        if assignment_type == 'questions':
            questions_data = request.form.get('questions_json')
            if questions_data:
                questions = json.loads(questions_data)
                for q in questions:
                    cur.execute(
                        "INSERT INTO assignment_questions(assignment_id, question_text, question_type, marks) VALUES(?, ?, ?, ?)",
                        (assignment_id, q['text'], q.get('type', 'descriptive'), q.get('marks', 1))
                    )
        
        conn.commit()
        conn.close()
        print("Assignment saved successfully")
        return jsonify({'success': True, 'assignment_id': assignment_id})
    except Exception as e:
        print(f"Error saving assignment: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/publish_assignment/<int:assignment_id>', methods=['POST'])
@require_login('teacher')
def publish_assignment(assignment_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE assignments SET published=1 WHERE id=? AND created_by=?", (assignment_id, session['id']))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/delete_assignment/<int:assignment_id>', methods=['DELETE'])
@require_login('teacher')
def delete_assignment(assignment_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM assignments WHERE id=? AND created_by=?", (assignment_id, session['id']))
        if not cur.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': 'Not found or not allowed'}), 404
        cur.execute("DELETE FROM assignments WHERE id=?", [assignment_id])
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/student/assignments')
@require_login('student')
def student_assignments():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get available assignments
    cur.execute(
        """
        SELECT a.id, a.title, a.description, a.due_date, a.assignment_type, a.question_paper_path,
               CASE WHEN s.id IS NOT NULL THEN 1 ELSE 0 END as submitted,
               s.status, s.feedback
        FROM assignments a
        LEFT JOIN assignment_submissions s ON a.id = s.assignment_id AND s.student_id = ?
        WHERE a.published = 1
        ORDER BY a.due_date ASC
        """,
        [session['id']]
    )
    assignments = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify({'assignments': assignments})

@app.route('/assignment/<int:assignment_id>')
@require_login('student')
def view_assignment(assignment_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get assignment details
    cur.execute("SELECT * FROM assignments WHERE id=? AND published=1", [assignment_id])
    assignment = cur.fetchone()
    if not assignment:
        return "Assignment not found", 404
    
    assignment = dict(assignment)
    
    # Get questions if it's a question-based assignment
    if assignment['assignment_type'] == 'questions':
        cur.execute("SELECT * FROM assignment_questions WHERE assignment_id=? ORDER BY id", [assignment_id])
        assignment['questions'] = [dict(row) for row in cur.fetchall()]
    
    conn.close()
    return render_template('view_assignment.html', assignment=assignment)

@app.route('/submit_assignment/<int:assignment_id>', methods=['POST'])
@require_login('student')
def submit_assignment(assignment_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if already submitted
        cur.execute("SELECT id FROM assignment_submissions WHERE assignment_id=? AND student_id=?", 
                   (assignment_id, session['id']))
        if cur.fetchone():
            return jsonify({'success': False, 'message': 'Already submitted'}), 400
        
        # Create submission
        submission_file_path = None
        if 'submission_file' in request.files:
            file = request.files['submission_file']
            if file.filename:
                upload_dir = os.path.join(app.root_path, 'uploads', 'submissions')
                os.makedirs(upload_dir, exist_ok=True)
                filename = f"{session['id']}_{assignment_id}_{int(datetime.now().timestamp())}_{file.filename}"
                submission_file_path = os.path.join(upload_dir, filename)
                file.save(submission_file_path)
        
        cur.execute(
            "INSERT INTO assignment_submissions(assignment_id, student_id, submission_file_path) VALUES(?, ?, ?)",
            (assignment_id, session['id'], submission_file_path)
        )
        submission_id = cur.lastrowid
        
        # Handle question answers
        answers_data = request.form.get('answers_json')
        if answers_data:
            answers = json.loads(answers_data)
            for answer in answers:
                cur.execute(
                    "INSERT INTO assignment_answers(submission_id, question_id, answer_text, selected_option) VALUES(?, ?, ?, ?)",
                    (submission_id, answer.get('question_id'), answer.get('answer_text'), answer.get('selected_option'))
                )
        
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


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

        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute(
            "INSERT INTO exams(title, description, duration, created_by, published) VALUES(?, ?, ?, ?, 0)",
            (title, description, duration, session['id'])
        )
        exam_id = cur.lastrowid

        for idx, q in enumerate(questions, start=1):
            q_text = q.get('text') or q.get('question_text')
            q_type = q.get('type') or q.get('question_type')
            options = q.get('options')
            correct = q.get('correct') or q.get('correct_answer')
            options_json = json.dumps(options) if options else None
            cur.execute(
                "INSERT INTO questions(exam_id, question_text, question_type, options, correct_answer) VALUES(?, ?, ?, ?, ?)",
                (exam_id, q_text, q_type, options_json, correct)
            )
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'exam_id': exam_id, 'message': 'Exam saved successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/publish_exam/<int:exam_id>', methods=['POST'])
@require_login('teacher')
def publish_exam(exam_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE exams SET published=1 WHERE id=? AND created_by=?", (exam_id, session['id']))
        conn.commit()
        conn.close()
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
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM exams WHERE id=? AND created_by=?", (exam_id, session['id']))
        if not cur.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': 'Not found or not allowed'}), 404
        # Delete in order: answers -> attempts -> questions -> exam
        cur.execute("DELETE FROM answers WHERE exam_id=?", [exam_id])
        cur.execute("DELETE FROM exam_attempts WHERE exam_id=?", [exam_id])
        cur.execute("DELETE FROM questions WHERE exam_id=?", [exam_id])
        cur.execute("DELETE FROM exams WHERE id=?", [exam_id])
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/view_attempts/<int:exam_id>', methods=['GET'])
@require_login('teacher')
def view_attempts(exam_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT a.student_id, u.username, a.status, a.total_score, a.started_at, a.submitted_at
            FROM exam_attempts a
            JOIN users u ON u.id=a.student_id
            WHERE a.exam_id=?
            ORDER BY a.submitted_at DESC, a.started_at DESC
            """,
            [exam_id]
        )
        attempts = [dict(row) for row in cur.fetchall()]
        conn.close()
        return jsonify({'success': True, 'attempts': attempts})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# -------------------- Student Dashboard --------------------

@app.route('/student/dashboard')
@require_login('student')
def student_dashboard():
    return render_template('student_dashboard.html')

@app.route('/student/performance')
@require_login('student')
def student_performance():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get exam history with scores
    cur.execute(
        """
        SELECT e.id, e.title, e.duration, a.total_score, a.submitted_at,
               (SELECT COUNT(*) FROM questions WHERE exam_id = e.id) as total_questions
        FROM exam_attempts a
        JOIN exams e ON e.id = a.exam_id
        WHERE a.student_id = ? AND a.status = 'completed'
        ORDER BY a.submitted_at DESC
        """,
        [session['id']]
    )
    exam_history = [dict(row) for row in cur.fetchall()]
    
    # Calculate analytics
    if exam_history:
        total_exams = len(exam_history)
        avg_score = sum(float(exam['total_score'] or 0) for exam in exam_history) / total_exams
        best_score = max(float(exam['total_score'] or 0) for exam in exam_history)
        recent_performance = [float(exam['total_score'] or 0) for exam in exam_history[:5]]
    else:
        total_exams = avg_score = best_score = 0
        recent_performance = []
    
    analytics = {
        'total_exams': total_exams,
        'avg_score': round(avg_score, 2),
        'best_score': best_score,
        'recent_performance': recent_performance
    }
    
    conn.close()
    return render_template('student_performance.html', 
                         exam_history=exam_history, 
                         analytics=analytics)

@app.route('/student/exam_details/<int:exam_id>')
@require_login('student')
def student_exam_details(exam_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get exam details with answers
    cur.execute(
        """
        SELECT q.question_text, q.question_type, q.correct_answer,
               a.answer_text, a.selected_option, a.is_correct, a.score
        FROM questions q
        LEFT JOIN answers a ON a.question_id = q.id AND a.student_id = ? AND a.exam_id = ?
        WHERE q.exam_id = ?
        ORDER BY q.id ASC
        """,
        (session['id'], exam_id, exam_id)
    )
    questions_details = [dict(row) for row in cur.fetchall()]
    
    # Get exam info and total score
    cur.execute("SELECT title, duration FROM exams WHERE id = ?", [exam_id])
    exam_info = dict(cur.fetchone())
    
    # Get total score from exam_attempts
    cur.execute(
        "SELECT total_score FROM exam_attempts WHERE student_id = ? AND exam_id = ?",
        (session['id'], exam_id)
    )
    attempt = cur.fetchone()
    exam_info['total_score'] = attempt['total_score'] if attempt else 0
    
    conn.close()
    return render_template('student_exam_details.html', 
                         exam_info=exam_info,
                         questions=questions_details)


@app.route('/student/exams')
@require_login('student')
def student_exams():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT e.id, e.title, e.duration
            FROM exams e
            WHERE e.published=1
            AND NOT EXISTS (
                SELECT 1 FROM exam_attempts a WHERE a.student_id=? AND a.exam_id=e.id
            )
            ORDER BY e.id DESC
            """,
            [session['id']]
        )
        exams = [dict(row) for row in cur.fetchall()]
    except Exception:
        # Fallback when exam_attempts table does not exist in older schema
        cur.execute("SELECT id, title, duration FROM exams WHERE published=1 ORDER BY id DESC")
        exams = [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
    return jsonify({'exams': exams})


@app.route('/student/exams_status')
@require_login('student')
def student_exams_status():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Get available exams (not attempted)
        cur.execute(
            """
            SELECT e.id, e.title, e.duration
            FROM exams e
            WHERE e.published=1
            AND NOT EXISTS (
                SELECT 1 FROM exam_attempts a WHERE a.student_id=? AND a.exam_id=e.id
            )
            ORDER BY e.id DESC
            """,
            [session['id']]
        )
        available = [dict(row) for row in cur.fetchall()]
        
        # Get completed exams
        cur.execute(
            """
            SELECT e.id, e.title, e.duration
            FROM exams e
            WHERE e.published=1
            AND EXISTS (
                SELECT 1 FROM exam_attempts a WHERE a.student_id=? AND a.exam_id=e.id AND a.status='completed'
            )
            ORDER BY e.id DESC
            """,
            [session['id']]
        )
        completed = [dict(row) for row in cur.fetchall()]
        
        conn.close()
        return jsonify({'available': available, 'completed': completed})
    except Exception as e:
        conn.close()
        return jsonify({'available': [], 'completed': [], 'error': str(e)})


# -------------------- Take Exam, Autosave, Submit --------------------

@app.route('/take_exam/<int:exam_id>')
@require_login('student')
def take_exam(exam_id):
    exam = fetch_exam(exam_id, ensure_published=True)
    if not exam:
        return "Exam not found or not published.", 404

    # Ensure attempt exists
    try:
        ensure_attempt(session['id'], exam_id)
    except Exception:
        pass

    questions = fetch_questions(exam_id)

    # Preload existing answers if any
    answers = {}
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT question_id, answer_text, selected_option FROM answers WHERE student_id=? AND exam_id=?",
            (session['id'], exam_id)
        )
        answers = {row['question_id']: {'answer_text': row['answer_text'], 'selected_option': row['selected_option']} for row in cur.fetchall()}
        conn.close()
    except Exception:
        answers = {}

    exam_payload = {
        'id': dict(exam)['id'] if exam else None,
        'title': dict(exam)['title'] if exam else '',
        'description': dict(exam).get('description', '') if exam else '',
        'duration': dict(exam)['duration'] if exam else 60,
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

        # Ensure attempt exists
        try:
            ensure_attempt(session['id'], exam_id)
        except Exception:
            pass

        conn = get_db_connection()
        cur = conn.cursor()
        for ans in answers:
            qid = int(ans['question_id'])
            answer_text = ans.get('answer_text')
            selected_option = (ans.get('selected_option') or '').strip().upper() or None

            # Check if answer exists
            cur.execute("SELECT id FROM answers WHERE student_id=? AND exam_id=? AND question_id=?", 
                       (session['id'], exam_id, qid))
            existing = cur.fetchone()
            
            if existing:
                cur.execute(
                    "UPDATE answers SET answer_text=?, selected_option=? WHERE student_id=? AND exam_id=? AND question_id=?",
                    (answer_text, selected_option, session['id'], exam_id, qid)
                )
            else:
                cur.execute(
                    "INSERT INTO answers(student_id, exam_id, question_id, answer_text, selected_option) VALUES(?, ?, ?, ?, ?)",
                    (session['id'], exam_id, qid, answer_text, selected_option)
                )
        
        conn.commit()
        conn.close()
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
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO proctoring_logs(attempt_id, event_type, timestamp) VALUES(?, ?, ?)",
            (attempt_id, event_type, datetime.utcnow())
        )
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

import threading

import shutil

def record_audit_event(event_name, status, related_id=None, related_type=None, details=None):

    try:

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(

            """

            INSERT INTO audit_events(event_name, status, related_id, related_type, details)

            VALUES (?, ?, ?, ?, ?)

            """,

            (event_name, status, related_id, related_type, details)

        )

        conn.commit()
        conn.close()

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

            

            conn = get_db_connection()
            cur = conn.cursor()

            cur.execute(

                "INSERT INTO proctoring_videos(attempt_id, video_blob) VALUES (?, ?)",

                (attempt_id, video_blob)

            )

            conn.commit()
            conn.close()

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



    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT video_blob FROM proctoring_videos WHERE attempt_id = ?", [attempt_id])

    video = cur.fetchone()

    conn.close()



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
        # Auto-score MCQs and compute total
        auto_score_mcq_for_student(session['id'], exam_id)
        total = recalc_total_score(session['id'], exam_id)
        
        # Mark attempt as completed
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE exam_attempts SET status='completed', submitted_at=? WHERE student_id=? AND exam_id=?",
            (datetime.utcnow(), session['id'], exam_id)
        )
        conn.commit()
        conn.close()

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



    conn = get_db_connection()
    cur = conn.cursor()



    if session['role'] == 'student':

        # Fetch this student's answers

        cur.execute(

            """

            SELECT q.id as question_id, q.question_text, q.question_type, q.correct_answer,

                   a.answer_text, a.selected_option, a.is_correct, a.score

            FROM questions q

            LEFT JOIN answers a ON a.question_id=q.id AND a.student_id=? AND a.exam_id=?

            WHERE q.exam_id=?

            ORDER BY q.id ASC

            """,

            (session['id'], exam_id, exam_id)

        )

        qas = [dict(row) for row in cur.fetchall()]

        cur.execute("SELECT total_score, status FROM exam_attempts WHERE student_id=? AND exam_id=?", (session['id'], exam_id))

        attempt = cur.fetchone()
        attempt = dict(attempt) if attempt else None

        conn.close()

        return render_template('results.html', role='student', exam=exam, qas=qas, attempt=attempt)

    

    # Teacher/Admin view: list all students who took the exam

    cur.execute(

        """

        SELECT u.username, a.id as attempt_id, a.total_score, a.status, a.started_at, a.submitted_at

        FROM exam_attempts a

        JOIN users u ON u.id=a.student_id

        WHERE a.exam_id=?

        ORDER BY a.submitted_at DESC

        """,

        [exam_id]

    )

    students = [dict(row) for row in cur.fetchall()]

    conn.close()

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



    conn = get_db_connection()
    cur = conn.cursor()

    # Get all students who attempted the exam

    cur.execute(

        """

        SELECT a.student_id, u.username, a.status, a.total_score

        FROM exam_attempts a

        JOIN users u ON u.id=a.student_id

        WHERE a.exam_id=?

        ORDER BY a.submitted_at DESC, a.started_at DESC

        """,

        [exam_id]

    )

    students = [dict(row) for row in cur.fetchall()]



    # For each student, fetch their answers

    student_answers = {}

    for student in students:

        cur.execute(

            """

            SELECT q.id as question_id, q.question_text, q.question_type, q.correct_answer,

                   a.answer_text, a.selected_option, a.is_correct, a.score

            FROM questions q

            LEFT JOIN answers a ON a.question_id=q.id AND a.student_id=? AND a.exam_id=?

            WHERE q.exam_id=?

            ORDER BY q.id ASC

            """,

            (student['student_id'], exam_id, exam_id)

        )

        student_answers[student['student_id']] = [dict(row) for row in cur.fetchall()]

    conn.close()



    return render_template('evaluate_exam.html', exam=exam, students=students, student_answers=student_answers)





@app.route('/grade/<int:exam_id>', methods=['POST'])
@require_login('teacher')
def grade_descriptive(exam_id):
    try:
        data = request.get_json(force=True)
        grades = data.get('grades', [])
        
        if not grades:
            return jsonify({'success': False, 'message': 'No grades provided'}), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        for g in grades:
            student_id = int(g['student_id'])
            question_id = int(g['question_id'])
            score = float(g['score'])
            
            # Check if answer record exists
            cur.execute(
                "SELECT id FROM answers WHERE student_id=? AND exam_id=? AND question_id=?",
                (student_id, exam_id, question_id)
            )
            existing = cur.fetchone()
            
            if existing:
                cur.execute(
                    "UPDATE answers SET score=? WHERE student_id=? AND exam_id=? AND question_id=?",
                    (score, student_id, exam_id, question_id)
                )
            else:
                cur.execute(
                    "INSERT INTO answers(student_id, exam_id, question_id, score) VALUES(?, ?, ?, ?)",
                    (student_id, exam_id, question_id, score)
                )
        
        conn.commit()
        
        # Recalculate total scores for all affected students
        for g in grades:
            recalc_total_score(int(g['student_id']), exam_id)
        
        conn.close()
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

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(

        """

        SELECT u.username, a.total_score, a.status, a.started_at, a.submitted_at

        FROM exam_attempts a

        JOIN users u ON u.id=a.student_id

        WHERE a.exam_id=?

        ORDER BY a.submitted_at DESC

        """,

        [exam_id]

    )

    rows = [dict(row) for row in cur.fetchall()]

    conn.close()



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

    conn = get_db_connection()
    cur = conn.cursor()

    

    # Fetch attempt details

    cur.execute(

        """

        SELECT e.title as exam_title, u.username as student_username

        FROM exam_attempts ea

        JOIN exams e ON e.id = ea.exam_id

        JOIN users u ON u.id = ea.student_id

        WHERE ea.id = ?

        """,

        [attempt_id]

    )

    attempt = cur.fetchone()
    attempt = dict(attempt) if attempt else None

    

    # Fetch proctoring logs

    cur.execute(

        "SELECT event_type, timestamp, screenshot_path FROM proctoring_logs WHERE attempt_id = ? ORDER BY timestamp ASC",

        [attempt_id]

    )

    logs = [dict(row) for row in cur.fetchall()]

    

    conn.close()

    

    return render_template('proctoring_results.html', attempt=attempt, logs=logs, attempt_id=attempt_id)



from flask import send_from_directory



# ... (existing code)



@app.route('/uploads/<path:filename>')

def uploaded_file(filename):

    return send_from_directory(os.path.join(app.root_path, 'uploads'), filename)



@app.route('/evaluate_assignment/<int:assignment_id>')
@require_login('teacher')
def evaluate_assignment(assignment_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM assignments WHERE id=? AND created_by=?", (assignment_id, session['id']))
    assignment = cur.fetchone()
    if not assignment:
        return "Assignment not found", 404
    
    assignment = dict(assignment)
    
    # Get all students who submitted the assignment
    cur.execute(
        """
        SELECT s.student_id, u.username, s.status, s.total_score, s.submitted_at, s.submission_file_path
        FROM assignment_submissions s
        JOIN users u ON u.id=s.student_id
        WHERE s.assignment_id=?
        ORDER BY s.submitted_at DESC
        """,
        [assignment_id]
    )
    students = [dict(row) for row in cur.fetchall()]
    
    conn.close()
    return render_template('evaluate_assignment.html', assignment=assignment, students=students)

@app.route('/download_assignment_results/<int:assignment_id>')
@require_login('teacher')
def download_assignment_results(assignment_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT u.username, s.total_score, s.status, s.submitted_at
        FROM assignment_submissions s
        JOIN users u ON u.id=s.student_id
        WHERE s.assignment_id=?
        ORDER BY s.submitted_at DESC
        """,
        [assignment_id]
    )
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()

    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['Username', 'Total Score', 'Status', 'Submitted At'])
    for r in rows:
        writer.writerow([r['username'], r['total_score'], r['status'], r['submitted_at']])

    output = si.getvalue()
    return Response(
        output,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=assignment_{assignment_id}_results.csv'}
    )

@app.route('/grade_assignment_submission', methods=['POST'])
@require_login('teacher')
def grade_assignment_submission():
    try:
        data = request.get_json()
        assignment_id = data['assignment_id']
        student_id = data['student_id']
        status = data['status']
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Update submission status
        cur.execute(
            "UPDATE assignment_submissions SET status=? WHERE assignment_id=? AND student_id=?",
            (status, assignment_id, student_id)
        )
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/view_submission_file/<int:assignment_id>/<int:student_id>')
@require_login('teacher')
def view_submission_file(assignment_id, student_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute(
        "SELECT submission_file_path FROM assignment_submissions WHERE assignment_id=? AND student_id=?",
        (assignment_id, student_id)
    )
    result = cur.fetchone()
    conn.close()
    
    if not result or not result['submission_file_path']:
        return "File not found", 404
    
    file_path = result['submission_file_path']
    return send_from_directory(os.path.dirname(file_path), os.path.basename(file_path))

@app.route('/add_assignment_feedback', methods=['POST'])
@require_login('teacher')
def add_assignment_feedback():
    try:
        data = request.get_json()
        assignment_id = data['assignment_id']
        student_id = data['student_id']
        feedback = data['feedback']
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute(
            "UPDATE assignment_submissions SET feedback=? WHERE assignment_id=? AND student_id=?",
            (feedback, assignment_id, student_id)
        )
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=config.FLASK_ENV == 'development')

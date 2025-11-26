# Add these routes to app.py

@app.route('/create_assignment', methods=['GET'])
@require_login('teacher')
def create_assignment():
    return render_template('create_assignment.html')

@app.route('/save_assignment', methods=['POST'])
@require_login('teacher')
def save_assignment():
    try:
        assignment_type = request.form.get('assignment_type')
        title = request.form.get('title')
        description = request.form.get('description')
        due_date = request.form.get('due_date')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Handle file upload for question paper
        question_paper_path = None
        if assignment_type == 'file_upload' and 'question_paper' in request.files:
            file = request.files['question_paper']
            if file.filename:
                upload_dir = os.path.join(app.root_path, 'uploads', 'assignments')
                os.makedirs(upload_dir, exist_ok=True)
                filename = f"{session['id']}_{int(datetime.now().timestamp())}_{file.filename}"
                question_paper_path = os.path.join(upload_dir, filename)
                file.save(question_paper_path)
        
        # Create assignment
        cur.execute(
            "INSERT INTO assignments(title, description, created_by, due_date, assignment_type, question_paper_path) VALUES(?, ?, ?, ?, ?, ?)",
            (title, description, session['id'], due_date, assignment_type, question_paper_path)
        )
        assignment_id = cur.lastrowid
        
        # Handle questions if assignment_type is 'questions'
        if assignment_type == 'questions':
            questions_data = request.form.get('questions_json')
            if questions_data:
                questions = json.loads(questions_data)
                for q in questions:
                    cur.execute(
                        "INSERT INTO assignment_questions(assignment_id, question_text, question_type, options, correct_answer, marks) VALUES(?, ?, ?, ?, ?, ?)",
                        (assignment_id, q['text'], q.get('type', 'descriptive'), 
                         json.dumps(q.get('options')) if q.get('options') else None,
                         q.get('correct_answer'), q.get('marks', 1))
                    )
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'assignment_id': assignment_id})
    except Exception as e:
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

@app.route('/student/assignments')
@require_login('student')
def student_assignments():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get available assignments
    cur.execute(
        """
        SELECT a.id, a.title, a.description, a.due_date, a.assignment_type, a.question_paper_path,
               CASE WHEN s.id IS NOT NULL THEN 1 ELSE 0 END as submitted
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
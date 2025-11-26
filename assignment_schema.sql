-- Add these tables to your database

CREATE TABLE assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    created_by INTEGER NOT NULL,
    due_date DATETIME,
    published INTEGER DEFAULT 0,
    assignment_type TEXT DEFAULT 'questions', -- 'questions' or 'file_upload'
    question_paper_path TEXT, -- for uploaded question papers
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE TABLE assignment_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assignment_id INTEGER NOT NULL,
    question_text TEXT NOT NULL,
    question_type TEXT DEFAULT 'descriptive', -- 'mcq', 'descriptive'
    options TEXT, -- JSON for MCQ options
    correct_answer TEXT,
    marks INTEGER DEFAULT 1,
    FOREIGN KEY (assignment_id) REFERENCES assignments(id)
);

CREATE TABLE assignment_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assignment_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'submitted', -- 'submitted', 'graded'
    total_score DECIMAL(6,2) DEFAULT 0,
    submission_file_path TEXT, -- for file submissions
    FOREIGN KEY (assignment_id) REFERENCES assignments(id),
    FOREIGN KEY (student_id) REFERENCES users(id),
    UNIQUE(assignment_id, student_id)
);

CREATE TABLE assignment_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL,
    question_id INTEGER,
    answer_text TEXT,
    selected_option TEXT,
    score DECIMAL(5,2) DEFAULT 0,
    feedback TEXT,
    FOREIGN KEY (submission_id) REFERENCES assignment_submissions(id),
    FOREIGN KEY (question_id) REFERENCES assignment_questions(id)
);
-- Voxiscribe schema: users, exams, questions, attempts, answers
-- Note: run this on a fresh database or migrate accordingly.

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    role ENUM('student', 'teacher') NOT NULL
);

CREATE TABLE IF NOT EXISTS exams (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    duration INT NOT NULL, -- minutes
    created_by INT NOT NULL,
    published BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS questions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    exam_id INT NOT NULL,
    question_text TEXT NOT NULL,
    question_type ENUM('MCQ', 'Descriptive') NOT NULL,
    -- Store MCQ options as JSON string or newline/comma-separated text
    options TEXT,
    -- For MCQ, store correct option key (e.g., 'A', 'B', 'C', 'D') or exact text
    correct_answer TEXT,
    FOREIGN KEY (exam_id) REFERENCES exams(id)
);

-- Track a student's attempt status per exam
CREATE TABLE IF NOT EXISTS exam_attempts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    exam_id INT NOT NULL,
    status ENUM('in_progress', 'completed') DEFAULT 'in_progress',
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    submitted_at DATETIME,
    total_score DECIMAL(6,2),
    UNIQUE KEY uniq_attempt (student_id, exam_id),
    FOREIGN KEY (student_id) REFERENCES users(id),
    FOREIGN KEY (exam_id) REFERENCES exams(id)
);

-- Store per-question answers to support autosave and scoring
CREATE TABLE IF NOT EXISTS answers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    exam_id INT NOT NULL,
    question_id INT NOT NULL,
    -- For descriptive answers
    answer_text LONGTEXT,
    -- For MCQ answers (A/B/C/D or matching text)
    selected_option VARCHAR(4),
    -- MCQ auto-evaluation flag
    is_correct BOOLEAN,
    -- Score per question (MCQ auto, descriptive manual)
    score DECIMAL(5,2),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_answer (student_id, exam_id, question_id),
    FOREIGN KEY (student_id) REFERENCES users(id),
    FOREIGN KEY (exam_id) REFERENCES exams(id),
    FOREIGN KEY (question_id) REFERENCES questions(id)
);

-- Legacy table kept for compatibility (not used by new flows)
CREATE TABLE IF NOT EXISTS submissions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    exam_id INT NOT NULL,
    answer_text TEXT,
    score INT,
    FOREIGN KEY (student_id) REFERENCES users(id),
    FOREIGN KEY (exam_id) REFERENCES exams(id)
);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_exams_published ON exams (published);
CREATE INDEX IF NOT EXISTS idx_questions_exam ON questions (exam_id);
CREATE INDEX IF NOT EXISTS idx_answers_student_exam ON answers (student_id, exam_id);
CREATE INDEX IF NOT EXISTS idx_attempts_student_exam ON exam_attempts (student_id, exam_id);

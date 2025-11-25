-- PostgreSQL schema for Voxiscribe
-- Run this on your PostgreSQL database

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('student', 'teacher')),
    face_image_path VARCHAR(255),
    voice_sample_path VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS exams (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    duration INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    published BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS questions (
    id SERIAL PRIMARY KEY,
    exam_id INTEGER NOT NULL,
    question_text TEXT NOT NULL,
    question_type VARCHAR(20) NOT NULL CHECK (question_type IN ('MCQ', 'Descriptive')),
    options TEXT,
    correct_answer TEXT,
    FOREIGN KEY (exam_id) REFERENCES exams(id)
);

CREATE TABLE IF NOT EXISTS exam_attempts (
    id SERIAL PRIMARY KEY,
    student_id INTEGER NOT NULL,
    exam_id INTEGER NOT NULL,
    status VARCHAR(20) DEFAULT 'in_progress' CHECK (status IN ('in_progress', 'completed')),
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    submitted_at TIMESTAMP,
    total_score DECIMAL(6,2),
    UNIQUE (student_id, exam_id),
    FOREIGN KEY (student_id) REFERENCES users(id),
    FOREIGN KEY (exam_id) REFERENCES exams(id)
);

CREATE TABLE IF NOT EXISTS answers (
    id SERIAL PRIMARY KEY,
    student_id INTEGER NOT NULL,
    exam_id INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    answer_text TEXT,
    selected_option VARCHAR(4),
    is_correct BOOLEAN,
    score DECIMAL(5,2),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (student_id, exam_id, question_id),
    FOREIGN KEY (student_id) REFERENCES users(id),
    FOREIGN KEY (exam_id) REFERENCES exams(id),
    FOREIGN KEY (question_id) REFERENCES questions(id)
);

CREATE TABLE IF NOT EXISTS submissions (
    id SERIAL PRIMARY KEY,
    student_id INTEGER NOT NULL,
    exam_id INTEGER NOT NULL,
    answer_text TEXT,
    score INTEGER,
    FOREIGN KEY (student_id) REFERENCES users(id),
    FOREIGN KEY (exam_id) REFERENCES exams(id)
);

CREATE TABLE IF NOT EXISTS proctoring_logs (
    id SERIAL PRIMARY KEY,
    attempt_id INTEGER NOT NULL,
    event_type VARCHAR(255) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    screenshot_path VARCHAR(255),
    FOREIGN KEY (attempt_id) REFERENCES exam_attempts(id)
);

CREATE TABLE IF NOT EXISTS proctoring_videos (
    id SERIAL PRIMARY KEY,
    attempt_id INTEGER NOT NULL,
    video_blob BYTEA,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (attempt_id) REFERENCES exam_attempts(id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    id SERIAL PRIMARY KEY,
    event_name VARCHAR(255) NOT NULL,
    related_id INTEGER,
    related_type VARCHAR(50),
    status VARCHAR(50),
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_exams_published ON exams (published);
CREATE INDEX IF NOT EXISTS idx_questions_exam ON questions (exam_id);
CREATE INDEX IF NOT EXISTS idx_answers_student_exam ON answers (student_id, exam_id);
CREATE INDEX IF NOT EXISTS idx_attempts_student_exam ON exam_attempts (student_id, exam_id);
CREATE INDEX IF NOT EXISTS idx_proctoring_logs_attempt ON proctoring_logs (attempt_id);
CREATE INDEX IF NOT EXISTS idx_proctoring_videos_attempt ON proctoring_videos (attempt_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_event ON audit_events (event_name, related_id, related_type);
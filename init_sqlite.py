#!/usr/bin/env python3
import sqlite3
import os

def create_database():
    """Initialize SQLite database with schema"""
    
    db_path = os.getenv('DATABASE_PATH', 'voxiscribe.db')
    
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        # Create tables
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('student', 'teacher')),
            face_image_path TEXT,
            voice_sample_path TEXT
        );

        CREATE TABLE IF NOT EXISTS exams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            duration INTEGER NOT NULL,
            created_by INTEGER NOT NULL,
            published BOOLEAN DEFAULT FALSE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            question_type TEXT NOT NULL CHECK (question_type IN ('MCQ', 'Descriptive')),
            options TEXT,
            correct_answer TEXT,
            FOREIGN KEY (exam_id) REFERENCES exams(id)
        );

        CREATE TABLE IF NOT EXISTS exam_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            exam_id INTEGER NOT NULL,
            status TEXT DEFAULT 'in_progress' CHECK (status IN ('in_progress', 'completed')),
            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            submitted_at DATETIME,
            total_score DECIMAL(6,2),
            UNIQUE (student_id, exam_id),
            FOREIGN KEY (student_id) REFERENCES users(id),
            FOREIGN KEY (exam_id) REFERENCES exams(id)
        );

        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            exam_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            answer_text TEXT,
            selected_option TEXT,
            is_correct BOOLEAN,
            score DECIMAL(5,2),
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (student_id, exam_id, question_id),
            FOREIGN KEY (student_id) REFERENCES users(id),
            FOREIGN KEY (exam_id) REFERENCES exams(id),
            FOREIGN KEY (question_id) REFERENCES questions(id)
        );

        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            exam_id INTEGER NOT NULL,
            answer_text TEXT,
            score INTEGER,
            FOREIGN KEY (student_id) REFERENCES users(id),
            FOREIGN KEY (exam_id) REFERENCES exams(id)
        );

        CREATE TABLE IF NOT EXISTS proctoring_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            screenshot_path TEXT,
            FOREIGN KEY (attempt_id) REFERENCES exam_attempts(id)
        );

        CREATE TABLE IF NOT EXISTS proctoring_videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id INTEGER NOT NULL,
            video_blob BLOB,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (attempt_id) REFERENCES exam_attempts(id)
        );

        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_name TEXT NOT NULL,
            related_id INTEGER,
            related_type TEXT,
            status TEXT,
            details TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # Create default admin user
        cur.execute("""
            INSERT OR IGNORE INTO users (username, password, role) 
            VALUES ('admin', 'admin123', 'teacher')
        """)
        
        conn.commit()
        conn.close()
        
        print("✅ SQLite database created successfully!")
        print("✅ Default admin user created (username: admin, password: admin123)")
        
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")

if __name__ == "__main__":
    create_database()
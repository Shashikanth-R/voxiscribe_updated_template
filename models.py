from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, LargeBinary
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

db = SQLAlchemy()

class User(db.Model):
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password = Column(String(200), nullable=False)
    role = Column(String(20), nullable=False, default='student') # student, teacher, admin

class Exam(db.Model):
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    created_by = Column(Integer, ForeignKey('user.id'), nullable=False)
    creator = relationship('User', backref=db.backref('exams', lazy=True))
    questions = relationship('Question', backref='exam', lazy=True, cascade="all, delete-orphan")

class Question(db.Model):
    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey('exam.id'), nullable=False)
    question_text = Column(Text, nullable=False)
    question_type = Column(String(50), nullable=False) # 'mcq', 'subjective'
    options = relationship('Option', backref='question', lazy=True, cascade="all, delete-orphan")

class Option(db.Model):
    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey('question.id'), nullable=False)
    option_text = Column(Text, nullable=False)
    is_correct = Column(db.Boolean, default=False, nullable=False)

class Submission(db.Model):
    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey('exam.id'), nullable=False)
    student_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    answers = relationship('Answer', backref='submission', lazy=True, cascade="all, delete-orphan")
    exam = relationship('Exam', backref='submissions')
    student = relationship('User', backref='submissions')

class Answer(db.Model):
    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey('submission.id'), nullable=False)
    question_id = Column(Integer, ForeignKey('question.id'), nullable=False)
    answer_text = Column(Text)
    question = relationship('Question')

class ProctoringLog(db.Model):
    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey('submission.id'), nullable=False)
    event_type = Column(String(100), nullable=False) # e.g., 'student_left_frame', 'multiple_faces'
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    screenshot = Column(LargeBinary, nullable=True) # Optional screenshot
    submission = relationship('Submission', backref=db.backref('proctoring_logs', lazy=True))

class ProctoringVideo(db.Model):
    __tablename__ = 'proctoring_videos'
    id = Column(Integer, primary_key=True)
    attempt_id = Column(Integer, ForeignKey('exam_attempts.id'), nullable=False)
    video_blob = Column(LargeBinary, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    attempt = relationship('ExamAttempt', backref=db.backref('proctoring_video', uselist=False))

class AuditEvent(db.Model):
    __tablename__ = 'audit_events'
    id = Column(Integer, primary_key=True)
    event_name = Column(String(255), nullable=False)
    related_id = Column(Integer)
    related_type = Column(String(50))
    status = Column(String(50))
    details = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
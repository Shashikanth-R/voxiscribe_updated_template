# Voxiscribe

A scaffolded Flask-based project structure.

## Structure

```
voxiscribe
├─ app.py
├─ config.py
├─ requirements.txt
├─ models.py
├─ init_db.py
├─ static/
│  ├─ css/
│  │  └─ main.css
│  └─ js/
│     ├─ voice.js
│     ├─ autosave.js
│     ├─ face_auth.js
│     └─ main.js
├─ templates/
│  ├─ layout.html
│  ├─ signup.html
│  ├─ login.html
│  ├─ user_dashboard.html
│  ├─ admin_dashboard.html
│  ├─ create_exam.html
│  ├─ take_exam.html
│  └─ result.html
└─ README.md
```

## Getting started

1. Create and activate a virtual environment (optional but recommended)
   - Windows (cmd):
     - python -m venv .venv
     - .venv\Scripts\activate
2. Install dependencies:
   - pip install -r requirements.txt
3. Run the app:
   - python app.py

This scaffold provides minimal templates and static assets to verify setup. Extend models and routes as needed.

from pathlib import Path

def write_file(path: str, content: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding='utf-8')
    print(f"Wrote {p.as_posix()}")


def main() -> None:
    files: dict[str, str] = {
        # Top-level files
        "app.py": """
from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('user_dashboard.html')

if __name__ == '__main__':
    app.run(debug=True)
""".lstrip(),
        "config.py": """
import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///voxiscribe.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
""".lstrip(),
        "requirements.txt": """
Flask>=3.0.0
Flask-SQLAlchemy>=3.1.1
python-dotenv>=1.0.0
""".strip() + "\n",
        "models.py": """
# Placeholder for SQLAlchemy models
# from flask_sqlalchemy import SQLAlchemy
# db = SQLAlchemy()
# Define your models here.
""".lstrip(),
        "init_db.py": """
# Placeholder for database initialization logic
# from app import app
# from models import db
# with app.app_context():
#     db.create_all()
""".lstrip(),

        # Static assets
        "static/css/main.css": """
/* Basic styles for Voxiscribe */
:root { color-scheme: light dark; }
body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 0; }
header { padding: 1rem; border-bottom: 1px solid #ddd; }
main { padding: 1rem; }
""".lstrip(),
        "static/js/voice.js": """
// Placeholder for voice-related features
console.log('[voice] ready');
""".lstrip(),
        "static/js/autosave.js": """
// Placeholder for autosave functionality
console.log('[autosave] ready');
""".lstrip(),
        "static/js/face_auth.js": """
// Placeholder for face authentication features
console.log('[face_auth] ready');
""".lstrip(),
        "static/js/main.js": """
// Main JS entry point
console.log('[main] Voxiscribe assets loaded');
""".lstrip(),

        # Templates
        "templates/layout.html": """
<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>{% block title %}Voxiscribe{% endblock %}</title>
    <link rel=\"stylesheet\" href=\"{{ url_for('static', filename='css/main.css') }}\" />
</head>
<body>
    <header>
        <h1>Voxiscribe</h1>
        <nav>
            <a href=\"/\">Home</a>
        </nav>
    </header>
    <main>
        {% block content %}{% endblock %}
    </main>
    <script src=\"{{ url_for('static', filename='js/main.js') }}\"></script>
</body>
</html>
""".lstrip(),
        "templates/signup.html": """
{% extends 'layout.html' %}
{% block title %}Sign Up - Voxiscribe{% endblock %}
{% block content %}
<h2>Sign Up</h2>
<form>
    <label>Username <input type=\"text\" name=\"username\" /></label><br />
    <label>Password <input type=\"password\" name=\"password\" /></label><br />
    <button type=\"submit\">Create account</button>
</form>
{% endblock %}
""".lstrip(),
        "templates/login.html": """
{% extends 'layout.html' %}
{% block title %}Log In - Voxiscribe{% endblock %}
{% block content %}
<h2>Log In</h2>
<form>
    <label>Username <input type=\"text\" name=\"username\" /></label><br />
    <label>Password <input type=\"password\" name=\"password\" /></label><br />
    <button type=\"submit\">Log in</button>
</form>
{% endblock %}
""".lstrip(),
        "templates/user_dashboard.html": """
{% extends 'layout.html' %}
{% block title %}Dashboard - Voxiscribe{% endblock %}
{% block content %}
<h2>User Dashboard</h2>
<p>Welcome to Voxiscribe. Your setup is complete.</p>
{% endblock %}
""".lstrip(),
        "templates/admin_dashboard.html": """
{% extends 'layout.html' %}
{% block title %}Admin Dashboard - Voxiscribe{% endblock %}
{% block content %}
<h2>Admin Dashboard</h2>
<p>Admin controls will go here.</p>
{% endblock %}
""".lstrip(),
        "templates/create_exam.html": """
{% extends 'layout.html' %}
{% block title %}Create Exam - Voxiscribe{% endblock %}
{% block content %}
<h2>Create Exam</h2>
<form>
    <label>Title <input type=\"text\" name=\"title\" /></label><br />
    <label>Description <textarea name=\"description\"></textarea></label><br />
    <button type=\"submit\">Save</button>
</form>
{% endblock %}
""".lstrip(),
        "templates/take_exam.html": """
{% extends 'layout.html' %}
{% block title %}Take Exam - Voxiscribe{% endblock %}
{% block content %}
<h2>Take Exam</h2>
<p>Exam taking interface will appear here.</p>
{% endblock %}
""".lstrip(),
        "templates/result.html": """
{% extends 'layout.html' %}
{% block title %}Result - Voxiscribe{% endblock %}
{% block content %}
<h2>Result</h2>
<p>Your exam results will be shown here.</p>
{% endblock %}
""".lstrip(),

        # README
        "README.md": """
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
     - .venv\\Scripts\\activate
2. Install dependencies:
   - pip install -r requirements.txt
3. Run the app:
   - python app.py

This scaffold provides minimal templates and static assets to verify setup. Extend models and routes as needed.
""".lstrip(),
    }

    for path, content in files.items():
        write_file(path, content)

    print("Voxiscribe structure generated.")


if __name__ == '__main__':
    main()

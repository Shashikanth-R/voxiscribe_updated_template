# Voxiscribe Deployment Guide

## Quick Deployment Steps

### 1. Initialize Database
```bash
python init_database.py
```

### 2. Set Environment Variables
Copy `.env.example` to `.env` and update values:
```bash
cp .env.example .env
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run Application
```bash
# Development
python app.py

# Production
gunicorn app:app --bind 0.0.0.0:5000
```

## Default Login Credentials
- **Username**: admin
- **Password**: admin123
- **Role**: teacher

## Git Commands for Deployment

### Initialize Git Repository
```bash
git init
git add .
git commit -m "Initial Voxiscribe deployment"
```

### Push to GitHub
```bash
git remote add origin https://github.com/yourusername/voxiscribe.git
git branch -M main
git push -u origin main
```

## Platform Deployment

### Render.com
1. Connect GitHub repository
2. Set build command: `pip install -r requirements.txt`
3. Set start command: `gunicorn app:app`
4. Add environment variables from `.env.example`

### Heroku
1. Install Heroku CLI
2. `heroku create voxiscribe-app`
3. `git push heroku main`
4. `heroku config:set SECRET_KEY=your-secret-key`

### Railway
1. Connect GitHub repository
2. Set start command: `gunicorn app:app --bind 0.0.0.0:$PORT`
3. Add environment variables

## Important Notes
- Change default admin password after first login
- Set strong SECRET_KEY in production
- Configure file upload limits for your hosting platform
- Voice transcription requires additional API setup
# Voxiscribe Deployment Guide for Render

## Prerequisites
1. GitHub account
2. Render account (free tier available)

## Deployment Steps

### 1. Push to GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/yourusername/voxiscribe.git
git push -u origin main
```

### 2. Create PostgreSQL Database on Render
1. Go to Render Dashboard
2. Click "New" → "PostgreSQL"
3. Name: `voxiscribe-db`
4. Database Name: `voxiscribe`
5. User: `voxiscribe_user`
6. Click "Create Database"
7. Copy the "External Database URL" for later

### 3. Run Database Schema
Connect to your PostgreSQL database and run:
```sql
-- Copy contents from database/postgresql_schema.sql
```

### 4. Deploy Web Service
1. Go to Render Dashboard
2. Click "New" → "Web Service"
3. Connect your GitHub repository
4. Configure:
   - Name: `voxiscribe`
   - Environment: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`

### 5. Set Environment Variables
In Render Web Service settings, add:
- `DATABASE_URL`: (paste the PostgreSQL URL from step 2)
- `SECRET_KEY`: (generate a secure random string)
- `FLASK_ENV`: `production`
- `PROCTORING_STORE_IN_DB`: `True`

### 6. Deploy
Click "Create Web Service" and wait for deployment to complete.

## Important Notes
- Voice transcription may have limited functionality on free tier
- File uploads are stored in temporary filesystem (will be lost on restart)
- For production, consider using cloud storage for uploads
- Database connection pooling may be needed for high traffic

## Troubleshooting
- Check Render logs for deployment issues
- Ensure all environment variables are set correctly
- Verify database schema is properly created
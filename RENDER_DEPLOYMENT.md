# Voxiscribe Deployment on Render - Fixed Version

## Quick Fix for Internal Server Error

The error occurs because the app expects a PostgreSQL database in production but is configured for SQLite locally.

## Step 1: Create PostgreSQL Database on Render

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click "New" → "PostgreSQL"
3. Configure:
   - Name: `voxiscribe-db`
   - Database Name: `voxiscribe`
   - User: `voxiscribe_user`
   - Region: Choose closest to you
4. Click "Create Database"
5. **Copy the "External Database URL"** - you'll need this

## Step 2: Initialize Database Schema

After your PostgreSQL database is created:

1. Connect to your database using the External Database URL
2. Run the SQL commands from `postgresql_schema.sql` file
3. This creates all required tables and default users

## Step 3: Deploy Web Service on Render

1. Go to Render Dashboard
2. Click "New" → "Web Service"
3. Connect your GitHub repository
4. Configure:
   - **Name**: `voxiscribe`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`

## Step 4: Set Environment Variables

In your Render Web Service settings, add these environment variables:

- `DATABASE_URL`: (paste the PostgreSQL External Database URL from Step 1)
- `SECRET_KEY`: `your-super-secret-key-here`
- `FLASK_ENV`: `production`
- `PROCTORING_STORE_IN_DB`: `True`

## Step 5: Deploy

Click "Create Web Service" and wait for deployment.

## Default Login Credentials

After deployment, you can login with:

**Admin/Teacher Account:**
- Username: `admin`
- Password: `admin123`
- Role: `teacher`

**Student Account:**
- Username: `student`
- Password: `student123`
- Role: `student`

## Troubleshooting

If you still get Internal Server Error:

1. Check Render logs for specific error messages
2. Ensure DATABASE_URL is correctly set
3. Verify PostgreSQL database is running
4. Make sure all environment variables are set

## Important Notes

- The app now supports both SQLite (local) and PostgreSQL (production)
- File uploads are stored in temporary filesystem on Render
- Voice transcription may have limited functionality on free tier
- Change default passwords after first login
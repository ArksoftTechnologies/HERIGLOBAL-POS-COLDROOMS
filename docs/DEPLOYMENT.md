# Deployment Guide

## Prerequisites
- Python 3.9 or higher
- PostgreSQL (recommended for production) or SQLite
- Web Server (Gunicorn, Nginx)

## Installation
1. **Clone Repository**:
   ```bash
   git clone <repository_url>
   cd heriglobal-pos
   ```

2. **Setup Virtual Environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration**:
   Create a `.env` file:
   ```
   FLASK_APP=app.py
   FLASK_ENV=production
   SECRET_KEY=<generate_secure_random_key>
   DATABASE_URL=postgresql://user:password@localhost/dbname
   ```

5. **Initialize Database**:
   ```bash
   flask db upgrade
   python migrations/initial_seed.py
   ```

## Running in Production
Use Gunicorn to serve the application:
```bash
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

## Static Files
Ensure your web server (Nginx) is configured to serve `/static` files directly for performance.

## Security Checklist
- [ ] `FLASK_ENV` set to `production`
- [ ] Strong `SECRET_KEY` set
- [ ] HTTPS enabled on web server
- [ ] Database passwords secure

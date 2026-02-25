#!/bin/bash

# Deployment Script for Heriglobal POS
# Usage: ./deploy.sh

echo "Starting deployment process..."

# 1. Pull latest changes
# git pull origin main

# 2. Activate virtual environment
# source venv/bin/activate

# 3. Install dependencies
# pip install -r requirements.txt

# 4. Migrate Database
# flask db upgrade

# 5. Seed Initial Data (optional, safe to run multiple times)
# python migrations/initial_seed.py

# 6. Collect Static Files (if using Flask-Collect or serving via Nginx)
# python manage.py collect_static

# 7. Restart Application Service
# systemctl restart heriglobal-pos

echo "Deployment completed!"

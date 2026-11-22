#!/bin/bash

# 0. Ensure required directories exist with proper permissions
echo "Setting up directories..."
APP_UID=${APP_UID:-1001}
APP_GID=${APP_GID:-1001}


# Create all needed directories (in case they don't exist in mounted volume)
mkdir -p \
 /app/media/uploads/batch_uploads \
 /app/media/output/defect_image \
 /app/media/output/puma \
 /app/media/output/top_five \
 /app/media/output/final_summary \
 /app/media/templates \
 /app/logs/puma_summary \
 /app/logs/image_processor \
 /app/logs/final_summary \
 /app/logs/top_five \
 /tmp/batch_uploads


# Fix ownership ONLY if running as root
if [ "$(id -u)" = "0" ]; then
    echo "Fixing ownership..."
    chown -R $APP_UID:$APP_GID /app/media /app/logs /tmp/batch_uploads || true
fi

# Safe permissions (NOT 777)
chmod -R 775 /app/media /app/logs /tmp/batch_uploads

# Ensure logs exist
touch /app/logs/app.log /app/logs/celery.log

echo "Directory setup complete"

# 1. Wait for Postgres to be ready (Prevents migration crashes)
echo "Waiting for database..."
# If you have 'netcat' installed in your Dockerfile, you can use:
# while ! nc -z db 5432; do sleep 1; done

# 2. Run Migrations
echo "Applying database migrations..."

python manage.py makemigrations

python manage.py migrate --noinput

pip install whitenoise

echo "Collecting static files..."
python manage.py collectstatic --noinput

# 3. Create Superuser
# It will use DJANGO_SUPERUSER_USERNAME and DJANGO_SUPERUSER_PASSWORD from .env
echo "Creating superuser..."
python manage.py createsuperuser --noinput || echo "Superuser already exists or skip."

# 4. Start the server
echo "Starting server..."
exec daphne -b 0.0.0.0 -p 8000 summary_backend.asgi:application
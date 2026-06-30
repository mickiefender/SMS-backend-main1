#!/bin/bash

# Setup script for Django + Supabase

echo "================================"
echo "School Management SaaS - Setup"
echo "================================"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "✓ .env file created. Please edit it with your Supabase credentials."
    echo ""
    echo "Edit the following values in .env:"
    echo "  - POSTGRES_HOST: Your Supabase host"
    echo "  - POSTGRES_PASSWORD: Your Supabase password"
    echo "  - DJANGO_SECRET_KEY: A random secret key"
    echo ""
else
    echo "✓ .env file already exists"
fi

echo ""
echo "Installing Python dependencies..."
pip install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✓ Dependencies installed successfully"
else
    echo "✗ Failed to install dependencies"
    exit 1
fi

echo ""
echo "Running database migrations..."
python manage.py migrate

if [ $? -eq 0 ]; then
    echo "✓ Database migrations completed"
else
    echo "✗ Failed to run migrations"
    exit 1
fi

echo ""
echo "Creating superuser..."
python manage.py createsuperuser

if [ $? -eq 0 ]; then
    echo "✓ Superuser created successfully"
else
    echo "✗ Failed to create superuser"
    exit 1
fi

echo ""
echo "================================"
echo "Setup Complete!"
echo "================================"
echo ""
echo "To start the development server, run:"
echo "  python manage.py runserver"
echo ""
echo "Django Admin: http://localhost:8000/admin"
echo "API Documentation: http://localhost:8000/api/schema/"

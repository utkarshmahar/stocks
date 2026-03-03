#!/bin/bash
# Initialize the database schema
set -e

echo "Waiting for Postgres..."
until pg_isready -h localhost -p 5432 -U trading 2>/dev/null; do
    sleep 1
done

echo "Running migrations..."
psql -h localhost -p 5432 -U trading -d trading -f /home/umahar/stocks/migrations/001_initial_schema.sql

echo "Database initialized."

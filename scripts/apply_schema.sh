#!/bin/bash

# Load environment variables
source ../.env

# Apply schema files in order
echo "Applying schema files..."

# Base schema first
if [ -f "../sql/schema.sql" ]; then
  echo "Applying base schema..."
  psql "postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@$POSTGRES_HOST/$POSTGRES_DB" -f ../sql/schema.sql
fi

# Entity-specific schemas
for schema in ../sql/*_schema.sql; do
  if [ -f "$schema" ]; then
    echo "Applying $schema..."
    psql "postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@$POSTGRES_HOST/$POSTGRES_DB" -f "$schema"
  fi
done

echo "Schema application complete!"

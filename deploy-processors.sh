
#!/bin/bash

set -e

echo "🚀 Building Docker images for quest and tournament processors..."

# Make sure Docker is logged in
echo "🔐 Please ensure you're logged in to Docker Hub with 'docker login'"

# Build and push quest-processor
echo "📦 Building quest-processor..."
cd src/services/quest-processor
docker build -t patronjay23/quest-processor:latest .
echo "⬆️ Pushing quest-processor..."
docker push patronjay23/quest-processor:latest

# Build and push tournament-processor  
echo "📦 Building tournament-processor..."
cd ../tournament-processor
docker build -t patronjay23/tournament-processor:latest .
echo "⬆️ Pushing tournament-processor..."
docker push patronjay23/tournament-processor:latest

cd ../../../

echo "✅ Docker images built and pushed successfully!"
echo ""
echo "📋 Task definitions are available at:"
echo "  - src/services/quest-processor/aws/task-definition.json"
echo "  - src/services/tournament-processor/aws/task-definition.json"
echo ""
echo "🏗️ You can now register these task definitions manually in AWS ECS"

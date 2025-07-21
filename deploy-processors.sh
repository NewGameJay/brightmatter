
#!/bin/bash

set -e

echo "🚀 Building Docker images for all processors..."

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

# Build and push social-auth-processor
echo "📦 Building social-auth-processor..."
cd ../social-auth-processor
docker build -t patronjay23/social-auth-processor:latest .
echo "⬆️ Pushing social-auth-processor..."
docker push patronjay23/social-auth-processor:latest

# Build and push leaderboard-processor
echo "📦 Building leaderboard-processor..."
cd ../leaderboard-processor
docker build -t patronjay23/leaderboard-processor:latest .
echo "⬆️ Pushing leaderboard-processor..."
docker push patronjay23/leaderboard-processor:latest

# Build and push event-processor
echo "📦 Building event-processor..."
cd ../event-processor
docker build -t patronjay23/event-processor:latest .
echo "⬆️ Pushing event-processor..."
docker push patronjay23/event-processor:latest

cd ../../../

echo "✅ All Docker images built and pushed successfully!"
echo ""
echo "📋 Task definitions are available at:"
echo "  - src/services/quest-processor/aws/task-definition.json"
echo "  - src/services/tournament-processor/aws/task-definition.json"
echo "  - src/services/social-auth-processor/aws/task-definition.json"
echo "  - src/services/leaderboard-processor/aws/task-definition.json"
echo "  - src/services/event-processor/aws/task-definition.json"
echo ""
echo "🏗️ You can now register these task definitions in AWS ECS"


#!/bin/bash

set -e

echo "🚀 Building and deploying quest and tournament processors..."

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
echo "📋 Task definitions are ready at:"
echo "  - src/services/quest-processor/aws/task-definition.json"
echo "  - src/services/tournament-processor/aws/task-definition.json"
echo ""
echo "🏗️ To deploy to ECS:"
echo "1. Register the task definitions:"
echo "   aws ecs register-task-definition --cli-input-json file://src/services/quest-processor/aws/task-definition.json"
echo "   aws ecs register-task-definition --cli-input-json file://src/services/tournament-processor/aws/task-definition.json"
echo ""
echo "2. Create services (replace with your subnet/security group IDs):"
echo "   aws ecs create-service \\"
echo "     --cluster brightmatter-oauth-cluster \\"
echo "     --service-name quest-processor \\"
echo "     --task-definition quest-processor \\"
echo "     --desired-count 1 \\"
echo "     --launch-type FARGATE \\"
echo "     --network-configuration \"awsvpcConfiguration={subnets=[YOUR_SUBNET_ID],securityGroups=[YOUR_SECURITY_GROUP_ID],assignPublicIp=ENABLED}\""
echo ""
echo "   aws ecs create-service \\"
echo "     --cluster brightmatter-oauth-cluster \\"
echo "     --service-name tournament-processor \\"
echo "     --task-definition tournament-processor \\"
echo "     --desired-count 1 \\"
echo "     --launch-type FARGATE \\"
echo "     --network-configuration \"awsvpcConfiguration={subnets=[YOUR_SUBNET_ID],securityGroups=[YOUR_SECURITY_GROUP_ID],assignPublicIp=ENABLED}\""
echo ""
echo "🎉 Deployment complete!"

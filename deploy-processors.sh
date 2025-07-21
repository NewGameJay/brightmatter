
#!/bin/bash

# Build and push quest-processor
echo "Building quest-processor..."
cd src/services/quest-processor
docker build -t patronjay23/quest-processor:latest .
docker push patronjay23/quest-processor:latest

# Build and push tournament-processor  
echo "Building tournament-processor..."
cd ../tournament-processor
docker build -t patronjay23/tournament-processor:latest .
docker push patronjay23/tournament-processor:latest

cd ../../../

# Register task definitions
echo "Registering task definitions..."
aws ecs register-task-definition --cli-input-json file://src/services/quest-processor/aws/task-definition.json
aws ecs register-task-definition --cli-input-json file://src/services/tournament-processor/aws/task-definition.json

# Create or update services in existing cluster
echo "Creating ECS services..."
aws ecs create-service \
  --cluster brightmatter-oauth-cluster \
  --service-name quest-processor \
  --task-definition quest-processor \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-0123456789abcdef0],securityGroups=[sg-0123456789abcdef0],assignPublicIp=ENABLED}"

aws ecs create-service \
  --cluster brightmatter-oauth-cluster \
  --service-name tournament-processor \
  --task-definition tournament-processor \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-0123456789abcdef0],securityGroups=[sg-0123456789abcdef0],assignPublicIp=ENABLED}"

echo "Deployment complete!"

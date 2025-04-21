set -e


if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
  echo "AWS credentials not found. Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables."
  exit 1
fi

AWS_REGION=${AWS_REGION:-ap-southeast-2}

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
if [ $? -ne 0 ]; then
  echo "Failed to get AWS account ID. Please check your AWS credentials."
  exit 1
fi

ECR_REPOSITORY_FLASK=${ECR_REPOSITORY_FLASK:-amalfi-results-flask}
ECR_REPOSITORY_FASTAPI=${ECR_REPOSITORY_FASTAPI:-amalfi-results-fastapi}

ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "Logging in to Amazon ECR..."
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_REGISTRY}

echo "Pulling latest images..."
docker pull ${ECR_REGISTRY}/${ECR_REPOSITORY_FLASK}:latest
docker pull ${ECR_REGISTRY}/${ECR_REPOSITORY_FASTAPI}:latest

echo "Stopping existing containers..."
docker-compose -f docker-compose.yml down || true

if ! docker network ls | grep -q amalfi_network; then
  echo "Creating amalfi_network..."
  docker network create amalfi_network
fi

cat > docker-compose.yml.new << EOL
version: '3.8'

services:
  flask_app:
    container_name: results_flask_app
    image: ${ECR_REGISTRY}/${ECR_REPOSITORY_FLASK}:latest
    pull_policy: always
    environment:
      - FLASK_APP=app.py
      - FLASK_ENV=production
      - FASTAPI_URL=http://fastapi_app:8000
    restart: always
    depends_on:
      - fastapi_app
    networks:
      - amalfi_network
    expose:
      - 5000

  fastapi_app:
    container_name: results_fastapi_app
    image: ${ECR_REGISTRY}/${ECR_REPOSITORY_FASTAPI}:latest
    pull_policy: always
    environment:
      - FLASK_APP_URL=http://flask_app:5000/api/notify
    restart: always
    networks:
      - amalfi_network
    volumes:
      - fastapi_data:/app/data
    expose:
      - 8000
      
networks:
  amalfi_network:
    external: true

volumes:
  fastapi_data:
    driver: local
EOL

mv docker-compose.yml.new docker-compose.yml

echo "Starting containers with forced pull..."
docker-compose pull --ignore-pull-failures
docker-compose up -d --force-recreate

echo "Verifying deployment..."
docker ps | grep results

echo "Deployment complete!"

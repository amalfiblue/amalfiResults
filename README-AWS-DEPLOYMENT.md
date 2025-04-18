# AWS Deployment for Amalfi Results

This document provides an overview of the AWS deployment setup for the Amalfi Results application using GitHub Actions.

## Overview

The Amalfi Results application is deployed to AWS using GitHub Actions for continuous integration and deployment. The deployment process involves:

1. Building Docker images for the Flask and FastAPI applications
2. Pushing these images to Amazon ECR (Elastic Container Registry)
3. Deploying the containers to an EC2 instance

## Architecture

![AWS Deployment Architecture](https://mermaid.ink/img/pako:eNp1kU1PwzAMhv9KlBMgdYceuExs4sQFcUHixiXKnDRbjdKkSjJtqvrvOG3XDgR78efn9WsnB2S1QQnSaXbWGtFYdOhZrVvUjp1QO-uI3VnTsgeUTjXWkbFqjZ6VaGxLbI3qiNVGOTKtc6xFZ9QKvSNWqNqhI_ZorekcK1RLzKEjVqJTa2-JvXvVEfPGdKg9-_DeqQ2xQq8bVOSMXhF7Uo3dEnvxrEXtWYXKrIhZVTcbYkfv1Zb9-Ky_Z_-Tn2dnOZzlcJ7DRQ6XOVzlcJ3DTQ63Odzl8JDDYw5POTzn8JLDaw7vOXzk8JnDVw7fP_CLH4zhKIejHI5zOMnhNIezHC5yuMzhKofrHG5yuMvhIYfHHJ5zeM3hPYfPHL5y-P4BzWyQdQ?type=png)

## Components

### GitHub Actions Workflow

The GitHub Actions workflow (`.github/workflows/deploy.yml`) automates the deployment process:

- Triggered on pushes to the main branch or manually
- Builds and pushes Docker images to ECR
- Deploys the containers to EC2 using SSH

### AWS Services

- **ECR (Elastic Container Registry)**: Stores Docker images for the Flask and FastAPI applications
- **EC2**: Hosts the containerized applications
- **IAM**: Manages permissions for GitHub Actions to interact with AWS services

## Setup Instructions

For detailed setup instructions, refer to the [AWS Deployment Setup Guide](docs/aws-deployment-setup.md).

### Quick Start

1. Create ECR repositories for Flask and FastAPI applications
2. Set up IAM role for GitHub Actions with ECR permissions
3. Launch and configure an EC2 instance with Docker and Docker Compose
4. Add required secrets to GitHub repository
5. Push changes to the main branch to trigger deployment

## Monitoring and Troubleshooting

- Monitor deployments in the GitHub Actions tab
- Check container logs on the EC2 instance using `docker logs <container_id>`
- Verify ECR repositories for image updates

## Security Considerations

- Use IAM roles with least privilege
- Regularly rotate AWS access keys
- Keep EC2 instances and Docker images updated
- Implement HTTPS for production deployments

## Additional Resources

- [AWS ECR Documentation](https://docs.aws.amazon.com/ecr/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Docker Documentation](https://docs.docker.com/)

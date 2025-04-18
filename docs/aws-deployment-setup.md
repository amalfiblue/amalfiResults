# AWS Deployment Setup Guide for Amalfi Results

This guide provides instructions for setting up AWS and GitHub credentials to enable automated deployment of the Amalfi Results application using GitHub Actions.

## Prerequisites

- AWS Account with administrative access
- GitHub repository for Amalfi Results
- Docker installed on your local machine (for testing)

## 1. AWS Setup

### 1.1 Create ECR Repositories

1. Log in to the AWS Management Console
2. Navigate to Amazon ECR (Elastic Container Registry)
3. Create two repositories:
   - `amalfi-results-flask` - For the Flask application
   - `amalfi-results-fastapi` - For the FastAPI application
4. Note the repository URIs for later use

### 1.2 Create IAM Role for GitHub Actions

1. Navigate to IAM (Identity and Access Management)
2. Create a new IAM Policy with the following permissions:
   ```json
   {
       "Version": "2012-10-17",
       "Statement": [
           {
               "Effect": "Allow",
               "Action": [
                   "ecr:GetAuthorizationToken",
                   "ecr:BatchCheckLayerAvailability",
                   "ecr:GetDownloadUrlForLayer",
                   "ecr:BatchGetImage",
                   "ecr:InitiateLayerUpload",
                   "ecr:UploadLayerPart",
                   "ecr:CompleteLayerUpload",
                   "ecr:PutImage"
               ],
               "Resource": "*"
           }
       ]
   }
   ```
3. Create a new IAM Role for GitHub Actions:
   - Select "Web Identity" as the trusted entity
   - Under "Identity Provider", select "GitHub Actions"
   - For "GitHub organization", enter your GitHub organization name (e.g., `amalfiblue`)
   - For "GitHub repository", enter the repository name (e.g., `amalfiResults`)
   - Attach the policy you created in step 2
   - Name the role `GitHubActionsECRRole`
   - Note the Role ARN for later use

### 1.3 Set Up EC2 Instance

1. Launch an EC2 instance:
   - Select Amazon Linux 2 or Ubuntu Server
   - Choose an instance type (t2.micro for testing, larger for production)
   - Configure security group to allow inbound traffic on ports 22 (SSH), 5000 (Flask), and 8000 (FastAPI)
   - Create or select an existing key pair for SSH access
   - Launch the instance

2. Install Docker and Docker Compose on the EC2 instance:
   ```bash
   # Connect to your EC2 instance
   ssh -i your-key.pem ec2-user@your-ec2-instance-ip
   
   # Install Docker (Amazon Linux 2)
   sudo yum update -y
   sudo amazon-linux-extras install docker -y
   sudo service docker start
   sudo usermod -a -G docker ec2-user
   
   # Install Docker Compose
   sudo curl -L "https://github.com/docker/compose/releases/download/v2.18.1/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
   sudo chmod +x /usr/local/bin/docker-compose
   
   # Install AWS CLI
   sudo yum install -y aws-cli
   
   # Log out and log back in for group changes to take effect
   exit
   ```

3. Configure AWS CLI on the EC2 instance:
   ```bash
   # Connect to your EC2 instance
   ssh -i your-key.pem ec2-user@your-ec2-instance-ip
   
   # Configure AWS CLI with credentials that have ECR access
   aws configure
   # Enter your AWS Access Key ID, Secret Access Key, region, and output format
   ```

## 2. GitHub Setup

### 2.1 Add GitHub Secrets

1. Navigate to your GitHub repository
2. Go to Settings > Secrets and variables > Actions
3. Add the following repository secrets:
   - `AWS_ROLE_ARN`: The ARN of the IAM role created in step 1.2 (e.g., `arn:aws:iam::123456789012:role/GitHubActionsECRRole`)
   - `AWS_REGION`: Your AWS region (e.g., `us-east-1`)
   - `ECR_REPOSITORY_FLASK`: The name of the Flask ECR repository (e.g., `amalfi-results-flask`)
   - `ECR_REPOSITORY_FASTAPI`: The name of the FastAPI ECR repository (e.g., `amalfi-results-fastapi`)
   - `EC2_HOST`: The public IP or DNS of your EC2 instance
   - `EC2_USERNAME`: The username for SSH access (e.g., `ec2-user` for Amazon Linux or `ubuntu` for Ubuntu)
   - `EC2_SSH_KEY`: The private SSH key content (the entire key, including BEGIN and END lines)

### 2.2 Enable GitHub Actions

1. Navigate to your GitHub repository
2. Go to Actions tab
3. Enable GitHub Actions if not already enabled

## 3. Testing the Deployment

1. Make a change to your repository and push to the main branch
2. Go to the Actions tab in your GitHub repository to monitor the workflow
3. Once the workflow completes, verify the deployment:
   - Check that the images were pushed to ECR
   - SSH into your EC2 instance and verify the containers are running:
     ```bash
     docker ps
     ```
   - Access the applications in your browser:
     - Flask app: `http://your-ec2-instance-ip:5000`
     - FastAPI app: `http://your-ec2-instance-ip:8000`

## 4. Troubleshooting

### 4.1 GitHub Actions Workflow Failures

- Check the workflow logs in the GitHub Actions tab
- Verify that all secrets are correctly set
- Ensure the IAM role has the necessary permissions

### 4.2 EC2 Deployment Issues

- SSH into the EC2 instance and check Docker logs:
  ```bash
  docker logs <container_id>
  ```
- Verify that the security group allows traffic on the required ports
- Check that Docker and Docker Compose are installed correctly

### 4.3 Container Connectivity Issues

- Ensure the Flask app can communicate with the FastAPI app
- Check that the environment variables are set correctly in the docker-compose.yml file

## 5. Security Considerations

- Use IAM roles with the principle of least privilege
- Regularly rotate AWS access keys
- Keep your EC2 instance and Docker images updated
- Consider using AWS Secrets Manager for sensitive information
- Implement HTTPS for production deployments

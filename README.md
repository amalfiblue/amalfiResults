# Amalfi Results

A system for processing and visualizing election results, specifically designed for Australian elections.

## Features

- Upload tally sheet images directly or via SMS
- Extract data using OCR
- Visualize election results in real-time
- Compare with historical data (2022 election)
- Analyze Two-Candidate Preferred (TCP) counts
- View results by electorate and polling booth

## Project Structure

- `flask_app/`: Main web application for displaying results
- `fastapi_app/`: Service for processing tally sheet images
- `utils/`: Utility modules for data processing
- `docker-compose.yml`: Docker Compose configuration

## Running Locally

### Using Poetry

For the Flask app:
```
cd flask_app
poetry install
poetry run flask run --host 0.0.0.0 --port 5000
```

For the FastAPI app:
```
cd fastapi_app
poetry install
poetry run uvicorn main:app --host 0.0.0.0 --port 8000
```

### Using Docker Compose

```
docker-compose up -d
```

## Deployment

### Manual Deployment

To manually pull and deploy the containers:

```bash
# Set your AWS credentials
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_REGION=your_region

# Run the deployment script
./deploy.sh
```

The deployment script will:
1. Log in to AWS ECR
2. Pull the latest container images
3. Create the required Docker network if it doesn't exist
4. Stop any existing containers
5. Start the containers with the latest images

### Automated Deployment

The repository includes GitHub Actions workflows for automated deployment to AWS ECR and EC2.
See `.github/workflows/deploy.yml` for details.

## API Endpoints

- Flask app: `http://localhost:5000`
- FastAPI app: `http://localhost:8000`

## Documentation

For more detailed documentation, see the `docs/` directory.

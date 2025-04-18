# Amalfi Results

A system for scanning tally sheet images, extracting data, and displaying results.

## Overview

This repository contains two main components:

1. **Flask App**: A web application for displaying tally sheet results
2. **FastAPI Service**: A service for scanning images using OCR, extracting data, and storing results

## Project Structure

```
amalfiResults/
├── flask_app/           # Flask web application
│   ├── app.py           # Main Flask application
│   ├── templates/       # HTML templates
│   └── static/          # Static assets (CSS, JS)
├── fastapi_app/         # FastAPI service
│   └── main.py          # Main FastAPI application
├── docker-compose.yml   # Docker configuration
└── README.md            # This file
```

## Features

- Upload and scan tally sheet images using OCR
- Extract structured data from images
- Store results in a database
- Display results in a web interface
- Real-time notifications when new results are available

## Setup and Installation

### Prerequisites

- Python 3.9+
- Poetry (for dependency management)
- Docker and Docker Compose (optional, for containerized deployment)

### Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/amalfiResults.git
   cd amalfiResults
   ```

2. Install dependencies for both applications:
   ```
   cd flask_app
   poetry install
   
   cd ../fastapi_app
   poetry install
   ```

3. Run the applications:
   
   **Flask App**:
   ```
   cd flask_app
   poetry run python app.py
   ```
   
   **FastAPI Service**:
   ```
   cd fastapi_app
   poetry run python main.py
   ```

### Docker Deployment

Alternatively, you can use Docker Compose to run both services:

```
docker-compose up -d
```

## API Endpoints

### FastAPI Service

- `POST /scan-image`: Upload and scan an image file
- `POST /inbound-sms`: Process SMS with attached media for scanning

### Flask App

- `GET /`: Home page
- `GET /results`: View all results
- `GET /api/results`: Get results as JSON
- `POST /api/notify`: Endpoint for FastAPI to notify of new results

## License

[MIT License](LICENSE)

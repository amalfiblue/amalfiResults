FROM python:3.9-slim

WORKDIR /app

# Install system dependencies for pytesseract
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry==1.5.1

# Copy Poetry configuration
COPY pyproject.toml /app/

# Configure Poetry to not create a virtual environment
RUN poetry config virtualenvs.create false

# Generate requirements.txt from Poetry and install dependencies
RUN poetry export -f requirements.txt -o requirements.txt && \
    pip install -r requirements.txt

# Copy application code and utils
COPY fastapi_app/ /app/
COPY utils/ /app/utils/

# Create data directory for database
RUN mkdir -p /app/data && chmod 777 /app/data

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

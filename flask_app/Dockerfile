FROM python:3.9-slim

WORKDIR /app

# Install Poetry and Gunicorn
RUN pip install poetry==1.5.1 gunicorn==21.2.0

# Copy Poetry configuration
COPY pyproject.toml /app/

# Configure Poetry to not create a virtual environment
RUN poetry config virtualenvs.create false

# Generate requirements.txt from Poetry and install dependencies
RUN poetry export -f requirements.txt -o requirements.txt && \
    pip install -r requirements.txt

# Copy application code
COPY . /app/
COPY utils /app/utils
# Create data directory for database
RUN mkdir -p /app/data && chmod 777 /app/data

# Expose port
EXPOSE 5000

# Run the application with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "app:app"]

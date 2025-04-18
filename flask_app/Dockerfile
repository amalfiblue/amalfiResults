FROM python:3.9-slim

WORKDIR /app

# Install Poetry
RUN pip install poetry==1.5.1

# Copy Poetry configuration
COPY pyproject.toml /app/

# Configure Poetry to not create a virtual environment
RUN poetry config virtualenvs.create false

# Generate requirements.txt from Poetry and install dependencies
RUN poetry export -f requirements.txt -o requirements.txt && \
    pip install -r requirements.txt

# Copy application code
COPY . /app/

# Expose port
EXPOSE 5000

# Run the application
CMD ["python", "app.py"]

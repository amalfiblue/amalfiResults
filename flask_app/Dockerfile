FROM python:3.9-slim

WORKDIR /app

# Install Poetry and Gunicorn
RUN pip install poetry==1.5.1 gunicorn==21.2.0

# Copy the entire project first
COPY . /app/

# Configure Poetry to not create a virtual environment
RUN poetry config virtualenvs.create false

# Install dependencies including local packages
RUN cd /app/flask_app && \
    poetry export -f requirements.txt -o requirements.txt && \
    pip install -r requirements.txt && \
    pip install -e /app

# Create data directory for database
RUN mkdir -p /app/data && chmod 777 /app/data

# Set working directory to flask app
WORKDIR /app/flask_app

# Expose port
EXPOSE 5000

# Run the application with Gunicorn using eventlet worker for socket.io support
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--worker-class", "eventlet", "--workers", "1", "app:app"]

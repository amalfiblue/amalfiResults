FROM python:3.9-slim

WORKDIR /app

# Install Poetry and Gunicorn
RUN pip install poetry==1.5.1 gunicorn==21.2.0

# Copy only the flask app and common utilities
COPY flask_app /app/flask_app
COPY common /app/common
COPY wait-for-fastapi.sh /app/wait-for-fastapi.sh

# Make the wait script executable
RUN chmod +x /app/wait-for-fastapi.sh

# Configure Poetry to not create a virtual environment
RUN poetry config virtualenvs.create false

# Install dependencies
RUN cd /app/flask_app && \
    poetry export -f requirements.txt -o requirements.txt && \
    pip install -r requirements.txt

# Create data directory for database
RUN mkdir -p /app/data && chmod 777 /app/data

# Set working directory to flask app
WORKDIR /app/flask_app

# Expose port
EXPOSE 5000

# Run the application with Gunicorn using gevent worker for socket.io support
CMD ["sh", "-c", "/app/wait-for-fastapi.sh && gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker --bind 0.0.0.0:5000 app:app"]
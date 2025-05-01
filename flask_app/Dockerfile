FROM python:3.9-slim

WORKDIR /app

# Install Poetry and Gunicorn
RUN pip install poetry==1.5.1 gunicorn==21.2.0

# Copy only the flask app and common utilities
COPY flask_app /app/flask_app
COPY common /app/common

# Configure Poetry to not create a virtual environment
RUN poetry config virtualenvs.create false

# Install dependencies
RUN cd /app/flask_app && \
    poetry export -f requirements.txt -o requirements.txt && \
    # pip install gunicorn geventwebsocket && \
    pip install -r requirements.txt

# Create data directory for database
RUN mkdir -p /app/data && chmod 777 /app/data

# Set working directory to flask app
WORKDIR /app/flask_app

# Expose port
EXPOSE 5000

# Run the application with Gunicorn using eventlet worker for socket.io support
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--worker-class", "eventlet", "--workers", "1", "app:app"]
# CMD ["gunicorn", "-k", "geventwebsocket.gunicorn.workers.GeventWebSocketWorker", "-w", "1", "-b", "0.0.0.0:5000", "app:app"]
# Use Python 3.13 slim image
FROM python:3.13-slim

# Create a non-root user with home directory
RUN groupadd -r appuser && useradd -r -g appuser -m -d /home/appuser appuser

# Set working directory
WORKDIR /app

# Ensure appuser can write to home directory
RUN mkdir -p /home/appuser && chown -R appuser:appuser /home/appuser

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Change ownership to non-root user
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port (Railway will set PORT env var)
EXPOSE 8000

# Start the application using PORT environment variable
# Railway provides PORT, but we need to use a shell to expand it
CMD uvicorn webhook_app:app --host 0.0.0.0 --port ${PORT:-8000}


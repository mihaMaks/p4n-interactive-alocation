# Use official Python 3.11 image as base
FROM python:3.11-slim

# Install uv binary
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# Set work directory
WORKDIR /app
RUN mkdir -p /app/data /app/meshes /app/uploads


# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libx11-6 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt ./

# Create a project virtual environment and install pinned dependencies with uv.
RUN uv venv /app/.venv --python 3.11 && \
    uv pip install --python /app/.venv/bin/python -r requirements.txt && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /root/.cache

# Copy project files
COPY . .


# Expose the correct backend port
EXPOSE 5009

# Default command (adjust as needed)
# CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5009", "backend.api.app:create_app()"]
# CMD ["sh", "-c", "gunicorn -w 4 -b 0.0.0.0:5009 --timeout 120 'backend.api.app:create_app()'"]
# CMD ["python", "run_backend.py"]
CMD ["sh", "-c", "gunicorn -w 4 -b 0.0.0.0:$PORT --timeout 120 'backend.api.app:create_app()'"]

# try to run on my local machine
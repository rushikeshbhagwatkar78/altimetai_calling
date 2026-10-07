FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (build tools, ffmpeg, curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ffmpeg \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user for Hugging Face Spaces compatibility
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# Copy complete application files
COPY --chown=user:user . .

# Prepare upload and runtime directories with permissions
RUN mkdir -p uploads && chmod -R 777 /app && chmod +x start.sh

USER user

# Expose default HTTP port for Hugging Face Spaces
EXPOSE 7860

# Container Startup
CMD ["/app/start.sh"]

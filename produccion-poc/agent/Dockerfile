FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for pg8000/SSL
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent code
COPY . .

# Force rebuild: v2
# AgentCore entrypoint
CMD ["python", "agent.py"]

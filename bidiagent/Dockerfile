FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV CONTAINER_ENV=1
EXPOSE 8080

CMD ["uvicorn", "agent:app", "--host", "0.0.0.0", "--port", "8080"]

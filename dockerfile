# roles/log-stack/files/alert-translator/Dockerfile
FROM python:alpine

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app.py .

CMD ["python", "app.py"]
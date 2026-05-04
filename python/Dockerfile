FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY fers_script.py .
COPY digi_script.py .

ENTRYPOINT ["bash"]

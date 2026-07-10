FROM python:3.10

WORKDIR /app

COPY . .

RUN pip install -r backend/requirements.txt

EXPOSE 5000

CMD ["python", "backend/run.py"]
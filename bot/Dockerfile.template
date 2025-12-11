FROM python:3.11-slim-bookworm

WORKDIR /app

COPY . .

RUN pip3 install -r requirements.txt

CMD ["app/app.py"]
ENTRYPOINT ["python3"]

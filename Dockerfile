FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./requirements.txt
COPY ucl_prediction_center/requirements.txt ./ucl_prediction_center/requirements.txt
RUN python -m pip install --upgrade pip && pip install -r requirements.txt

COPY railway_worker.py ./railway_worker.py
COPY ucl_prediction_center ./ucl_prediction_center
COPY UEFA*.xlsx ./

CMD ["python", "railway_worker.py"]

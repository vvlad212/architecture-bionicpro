FROM apache/airflow:2.9.1-python3.11

ARG AIRFLOW_VERSION=2.9.1

COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir \
    "apache-airflow==${AIRFLOW_VERSION}" \
    -r /requirements.txt

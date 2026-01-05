# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

ARG ROOT_PATH="/intempus_synchronizer"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=${ROOT_PATH}

RUN apt update; apt install -y python3-dev default-libmysqlclient-dev build-essential pkg-config

RUN pip install --upgrade pip; pip install pipenv

COPY app ${ROOT_PATH}/app
COPY pyproject.toml Pipfile Pipfile.lock ${ROOT_PATH}/

WORKDIR ${ROOT_PATH}

# Dev stage
FROM base AS dev

ENV PIPENV_VENV_IN_PROJECT=1
RUN pipenv install --dev

ENV VIRTUAL_ENV=${ROOT_PATH}/.venv
ENV PIPENV_ACTIVE=1
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

WORKDIR ${ROOT_PATH}/app
CMD ["fastapi", "dev", "main.py", "--host", "0.0.0.0", "--port", "8000"]

# Prod stage
FROM base AS prod

RUN pipenv install --system --deploy

WORKDIR ${ROOT_PATH}/app
CMD ["fastapi", "run", "main.py", "--host", "0.0.0.0", "--port", "8000"]

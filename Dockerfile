FROM python:3.9

# Set environment variables
# ENV PYTHONUNBUFFERED 1

# audio utils for rendering midi
RUN apt-get update && \
    apt-get install -y ffmpeg fluidsynth normalize-audio


WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./app /code/app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
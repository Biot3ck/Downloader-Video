# Local staging image; base image must already exist. No public download worker is started.
FROM clipora-worker:v8-dns
USER root
COPY wheels /opt/wheels
COPY requirements-web.lock /opt/requirements-web.lock
RUN python -m pip install --no-index --no-deps --require-hashes --find-links=/opt/wheels -r /opt/requirements-web.lock \
    && rm -rf /opt/wheels
COPY clipora_v8_web /srv/clipora_v8_web
COPY clipora_v8_browser_real_mp4 /srv/clipora_v8_browser_real_mp4
WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001:10001
ENTRYPOINT ["python", "-B", "-m", "uvicorn", "clipora_v8_web.main:app_factory", "--factory"]
CMD ["--host", "0.0.0.0", "--port", "8080", "--no-proxy-headers", "--no-access-log", "--limit-concurrency", "32", "--timeout-keep-alive", "5"]

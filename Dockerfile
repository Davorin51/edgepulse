FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY edgepulse ./edgepulse
RUN pip install --no-cache-dir . && useradd --create-home app && mkdir /data && chown app:app /data
COPY dist ./dist
USER app
ENV EDGEPULSE_DB=/data/edgepulse.sqlite3 EDGEPULSE_HOST=0.0.0.0
EXPOSE 8000
CMD ["python", "-m", "edgepulse.server"]

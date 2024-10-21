#!/bin/sh

wait_for_elasticsearch() {
  echo "Waiting for Elasticsearch..."
  for i in $(seq 1 30); do
    if curl -s http://elasticsearch:9200 >/dev/null; then
      echo "Elasticsearch is up"
      return 0
    fi
    echo "Attempt $i: Elasticsearch not ready. Retrying in 5 seconds..."
    sleep 5
  done
  echo "Error: Elasticsearch did not become available in time"
  return 1
}

if ! wait_for_elasticsearch; then
  exit 1
fi

FLAG_FILE=/app/init_done.flag

if [ ! -f "$FLAG_FILE" ]; then
    echo "Running prep.py..."
    python prep.py
    touch $FLAG_FILE
else
    echo "Initialization already done. Skipping prep.py."
fi

exec streamlit run app.py
set -e

max_retries=30
retry_interval=2
retry_count=0

echo "Waiting for FastAPI service to be available..."

while [ $retry_count -lt $max_retries ]; do
  if ip=$(getent hosts results_fastapi_app | awk '{ print $1 }'); then
    echo "FastAPI service IP resolved: $ip"
    
    if curl -s -o /dev/null -w "%{http_code}" "http://$ip:8000/api/health" | grep -q "200"; then
      echo "FastAPI service is available!"
      export FASTAPI_URL="http://$ip:8000"
      exec "$@"
      exit 0
    else
      echo "FastAPI service not yet responsive, waiting..."
    fi
  else
    echo "Could not resolve FastAPI service IP, trying direct IP resolution..."
    
    if ip=$(ping -c 1 -W 1 results_fastapi_app | grep PING | awk -F'[()]' '{print $2}'); then
      echo "FastAPI IP from ping: $ip"
      export FASTAPI_URL="http://$ip:8000"
      
      if curl -s -o /dev/null -w "%{http_code}" "http://$ip:8000/api/health" | grep -q "200"; then
        echo "FastAPI service is available!"
        exec "$@"
        exit 0
      fi
    fi
  fi
  
  retry_count=$((retry_count+1))
  echo "Retry $retry_count/$max_retries... waiting for FastAPI service"
  sleep $retry_interval
done

echo "Could not connect to FastAPI service after $max_retries attempts."
echo "Falling back to hostname, but DNS resolution may still fail."
export FASTAPI_URL="http://results_fastapi_app:8000"
exec "$@"

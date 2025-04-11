#!/bin/bash

# Function to refresh credentials
refresh_credentials() {
  # Get credentials from ECS container metadata endpoint
  CREDS=$(curl -s 169.254.170.2$AWS_CONTAINER_CREDENTIALS_RELATIVE_URI)
  
  # Extract credentials and set as environment variables
  export AWS_ACCESS_KEY_ID=$(echo $CREDS | jq -r '.AccessKeyId')
  export AWS_SECRET_ACCESS_KEY=$(echo $CREDS | jq -r '.SecretAccessKey')
  export AWS_SESSION_TOKEN=$(echo $CREDS | jq -r '.Token')
  export AWS_REGION=$(curl -s 169.254.169.254/latest/meta-data/placement/region || echo "us-east-1")
  
  echo "AWS credentials refreshed at $(date)"
}

# Initial credential fetch
refresh_credentials

# Start credential refresh in background
(
  while true; do
    # Sleep for 30 minutes (1800 seconds)
    sleep 1800
    refresh_credentials
  done
) &

# Execute the main application
exec "$@"
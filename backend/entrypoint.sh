#!/bin/sh

#
# Copyright 2025 Amazon.com, Inc. and its affiliates. All Rights Reserved.
#
# Licensed under the Amazon Software License (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
#   http://aws.amazon.com/asl/
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.
#

# Function to check if running in ECS
is_running_in_ecs() {
  # Try to access the ECS metadata endpoint with a 1 second timeout
  if curl -s --connect-timeout 1 http://169.254.170.2 > /dev/null 2>&1; then
    echo "Running in ECS environment"
    return 0
  else
    echo "Not running in ECS environment"
    return 1
  fi
}

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

env

# Check if running in ECS and refresh credentials if so
if is_running_in_ecs; then
  refresh_credentials
else
  echo "Skipping credential refresh - not in ECS environment"
fi

if [ "$DEV_MODE" = "true" ]; then
  echo "Running in DEV_MODE with inotifywait..."

  # Start the initial process
  python nova_s2s_backend.py &
  PID=$!

  # Monitor directory for changes
  while true; do
    inotifywait -r -e modify,create,delete /app --format "%e %w%f"
    echo "Change detected, restarting process..."

    # Kill the previous process if it exists
    if [ -n "$PID" ]; then
      kill $PID 2>/dev/null || true
      wait $PID 2>/dev/null || true
    fi

    # Start the process again
    python nova_s2s_backend.py &
    PID=$!
  done
else
  echo "Running in normal mode..."
  exec python nova_s2s_backend.py
fi

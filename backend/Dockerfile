FROM python:3.13-alpine

WORKDIR /app

# Copy requirements file
COPY requirements.txt ./

# Install dependencies
RUN apk add --update jq curl py-pip inotify-tools
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Python files and .env
COPY nova_s2s_backend.py knowledge_base_lookup.py retrieve_user_profile.py cognito.py entrypoint.sh .env ./

# Expose the WebSocket port
EXPOSE 80

ENV LOGLEVEL=INFO

RUN chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]

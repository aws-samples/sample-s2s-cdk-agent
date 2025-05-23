FROM python:3.13-alpine

WORKDIR /app

# Copy all the files under backend
COPY . ./

# Install dependencies
RUN apk add --update jq curl py-pip inotify-tools
RUN pip install --no-cache-dir -r requirements.txt

# Expose the WebSocket port
EXPOSE 80

ENV LOGLEVEL=INFO

ENV MCP_PORT=8000

RUN chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]

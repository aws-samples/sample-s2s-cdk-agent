const userDataScript = `#!/bin/bash
# Update system packages
dnf update -y

# Install Node.js
dnf install -y nodejs npm git

# Install PM2 for process management
npm install -g pm2

# Create app directory
mkdir -p /home/ec2-user/gowssip

# Set ownership
chown -R ec2-user:ec2-user /home/ec2-user/gowssip

# Switch to ec2-user for the rest of the setup
sudo -u ec2-user bash << 'EOF'
cd /home/ec2-user/gowssip

# Clone the application files
cat > /home/ec2-user/gowssip/src/index.js << 'INDEXJS'
${require("fs").readFileSync(path.join(__dirname, "../../src/index.js"), "utf8")}
INDEXJS

cat > /home/ec2-user/gowssip/src/client.js << 'CLIENTJS'
${require("fs").readFileSync(path.join(__dirname, "../../src/client.js"), "utf8")}
CLIENTJS

cat > /home/ec2-user/gowssip/src/consts.js << 'CONSTSJS'
${require("fs").readFileSync(path.join(__dirname, "../../src/consts.js"), "utf8")}
CONSTSJS

# Create package.json
cat > /home/ec2-user/gowssip/package.json << 'PACKAGEJSON'
${require("fs").readFileSync(path.join(__dirname, "../../package.json"), "utf8")}
PACKAGEJSON

# Install dependencies
npm install

# Start the application with PM2
pm2 start src/index.js --name gowssip
pm2 startup
pm2 save
EOF

# Configure nginx as a reverse proxy (optional)
dnf install -y nginx
cat > /etc/nginx/conf.d/gowssip.conf << 'EOF'
server {
listen 80;
server_name _;

location / {
    proxy_pass http://localhost:3000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection 'upgrade';
    proxy_set_header Host $host;
    proxy_cache_bypass $http_upgrade;
}


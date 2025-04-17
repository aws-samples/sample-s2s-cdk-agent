# Gowssip

SIP to WebSocket connections for voice applications.

## Local Development

1. Install dependencies:
   ```
   npm install
   ```

2. Run the application:
   ```
   npm run dev
   ```

3. The application will be available at http://localhost:3000

## Deployment

This application can be deployed to AWS using the CDK project in the `cdk/` directory.

### Prerequisites for Deployment

- AWS CLI configured with appropriate credentials
- Node.js and npm installed
- AWS CDK installed (`npm install -g aws-cdk`)

### Deployment Steps

1. Navigate to the CDK directory:
   ```
   cd cdk
   ```

2. Install dependencies:
   ```
   npm install
   ```

3. Create an EC2 key pair named `gowssip-key` in the AWS Console (EC2 > Key Pairs)

4. Deploy the stack:
   ```
   cdk deploy
   ```

5. After deployment, the application will be accessible at the EC2 instance's public IP or DNS name.

### Security Features

- IP whitelisting: Only your IP address can access the EC2 instance
- Security group rules restrict access to SSH (22), HTTP (80), HTTPS (443), and application port (3000)
- IAM role with necessary permissions for Bedrock

For more details on the deployment, see the [CDK README](./cdk/README.md).

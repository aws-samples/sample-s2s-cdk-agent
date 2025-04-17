# Gowssip CDK Deployment

This CDK project deploys the Gowssip application to an EC2 instance with IP whitelisting.

## Prerequisites

- AWS CLI configured with appropriate credentials
- Node.js and npm installed
- AWS CDK installed (`npm install -g aws-cdk`)

## Setup

1. Install dependencies:
   ```
   npm install
   ```

2. Create an EC2 key pair named `gowssip-key` in the AWS Console (EC2 > Key Pairs)

3. Deploy the stack:
   ```
   cdk deploy
   ```

## Security Features

- IP whitelisting: Only your IP address (15.248.6.252) can access the EC2 instance
- Security group rules restrict access to SSH (22), HTTP (80), HTTPS (443), and application port (3000)
- IAM role with necessary permissions for Bedrock

## Application Access

After deployment, you can access the application at:
- http://[EC2-PUBLIC-IP]:3000
- http://[EC2-PUBLIC-DNS]:3000

## Updating Your IP Address

If your IP address changes, update the `myIp` variable in `lib/gowssip-stack.ts` and redeploy:

```typescript
const myIp = 'your-new-ip/32';
```

## Cleanup

To remove all resources:

```
cdk destroy
```

#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { GowssipStack } from '../lib/gowssip-stack';

const app = new cdk.App();
new GowssipStack(app, 'GowssipStack', {
  env: { 
    account: process.env.CDK_DEFAULT_ACCOUNT, 
    region: process.env.CDK_DEFAULT_REGION || 'us-east-1'
  },
  description: 'Gowssip application deployment with IP whitelisting'
});

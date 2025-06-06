/**
 * Copyright 2025 Amazon.com, Inc. and its affiliates. All Rights Reserved.
 *
 * Licensed under the Amazon Software License (the "License").
 * You may not use this file except in compliance with the License.
 * A copy of the License is located at
 *
 *   http://aws.amazon.com/asl/
 *
 * or in the "license" file accompanying this file. This file is distributed
 * on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
 * express or implied. See the License for the specific language governing
 * permissions and limitations under the License.
 */

import * as cdk from "aws-cdk-lib";
import * as cognito from "aws-cdk-lib/aws-cognito";
import * as cr from "aws-cdk-lib/custom-resources";
import * as ecr from "aws-cdk-lib/aws-ecr-assets";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as elbv2 from "aws-cdk-lib/aws-elasticloadbalancingv2";
import * as events from "aws-cdk-lib/aws-events";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as s3deploy from "aws-cdk-lib/aws-s3-deployment";
import * as targets from "aws-cdk-lib/aws-events-targets";
import * as path from "path";
import { Construct } from "constructs";
import { Duration } from "aws-cdk-lib";
import { NodejsFunction } from "aws-cdk-lib/aws-lambda-nodejs";

import EnforceDeletionPolicy from "./EnforceDeletionPolicyAspect";
import { NetworkStack } from "./network-stack";

export interface S2SAppStackProps extends cdk.StackProps {
  networkStack: NetworkStack;
  cognitoDomainPrefix: string;
  knowledgeBaseId: string;
  dynamoDbTableName: string;
}

export class S2SAppStack extends cdk.Stack {
  userPool: cognito.UserPool;
  userPoolClient: cognito.UserPoolClient;
  userPoolDomain: cognito.UserPoolDomain;
  cloudFrontUrl: string;
  networkStack: NetworkStack;

  createAuthResources(cognitoDomainPrefix: string) {
    this.userPool = new cognito.UserPool(this, "WebSocketUserPool", {
      selfSignUpEnabled: false,
      autoVerify: { email: true },
      standardAttributes: {
        email: { required: true, mutable: true },
      },
      passwordPolicy: {
        minLength: 8,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: true,
      },
      featurePlan:
        process.env.ENV === "prod"
          ? cognito.FeaturePlan.PLUS
          : cognito.FeaturePlan.ESSENTIALS,
    });

    this.userPoolClient = this.userPool.addClient("WebSocketAppClient", {
      authFlows: {
        userPassword: true,
        userSrp: true,
      },
      preventUserExistenceErrors: true,
      oAuth: {
        flows: {
          authorizationCodeGrant: true,
          implicitCodeGrant: true,
        },
        scopes: [
          cognito.OAuthScope.EMAIL,
          cognito.OAuthScope.OPENID,
          cognito.OAuthScope.PROFILE,
        ],
        callbackUrls: [this.cloudFrontUrl],
        logoutUrls: [this.cloudFrontUrl],
      },
    });

    const uniquePrefix: string = `auth-${process.env.ENV || "dev"}-${
      this.region
    }-${this.account}`;

    this.userPoolDomain = this.userPool.addDomain("WebSocketDomain", {
      cognitoDomain: {
        domainPrefix: uniquePrefix,
      },
    });
  }

  createEcsResources(knowledgeBaseId: string, dynamoDbTableName: string) {
    const ecsCluster = new ecs.Cluster(this, "WebsocketCluster", {
      vpc: this.networkStack.vpc,
      containerInsights: true,
    });

    const taskRole = new iam.Role(this, "WebsocketTaskRole", {
      assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
    });

    const dynamoDbReadPolicy = new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ["dynamodb:GetItem", "dynamodb:BatchGetItem", "dynamodb:Scan", "dynamodb:Query", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"],
      resources: [
        `arn:aws:dynamodb:${this.region}:${this.account}:table/${dynamoDbTableName}`,
        `arn:aws:dynamodb:${this.region}:${this.account}:table/${dynamoDbTableName}/index/*`,
      ],
    });

    const bedrockKnowledgeBasePolicy = new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ["bedrock:Retrieve"],
      resources: [
        `arn:aws:bedrock:${this.region}:${this.account}:knowledge-base/${knowledgeBaseId}`,
      ],
    });

    taskRole.addToPolicy(dynamoDbReadPolicy);
    taskRole.addToPolicy(bedrockKnowledgeBasePolicy);

    taskRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["bedrock:InvokeModel*"],
        resources: [
          `arn:aws:bedrock:${this.region}::foundation-model/amazon.nova-sonic-v1:0`,
        ],
      })
    );

    const wsTaskDef = new ecs.FargateTaskDefinition(this, "WebsocketTaskDef", {
      memoryLimitMiB: 2048,
      cpu: 1024,
      taskRole,
      ephemeralStorageGiB: 30,
      runtimePlatform: {
        cpuArchitecture: ecs.CpuArchitecture.ARM64,
        operatingSystemFamily: ecs.OperatingSystemFamily.LINUX,
      },
    });
    return { ecsCluster, wsTaskDef };
  }

  createContainerDefinition(
    ecsCluster: ecs.Cluster,
    wsTaskDef: ecs.TaskDefinition
  ) {
    wsTaskDef.addContainer("WebsocketContainer", {
      image: ecs.ContainerImage.fromAsset(
        path.join(__dirname, "../../backend"),
        {
          buildArgs: {},
          platform: ecr.Platform.LINUX_ARM64,
        }
      ),
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: "websocket" }),
      environment: {
        NODE_ENV: "production",
        PORT: "80",
        MCP_PORT: "8000",
        USER_POOL_ID: this.userPool.userPoolId,
        CLIENT_ID: this.userPoolClient.userPoolClientId,
      },
      portMappings: [
        {
          containerPort: 80,
          hostPort: 80,
          protocol: ecs.Protocol.TCP,
        },
      ],
    });

    const wsService = new ecs.FargateService(this, "WebsocketService", {
      cluster: ecsCluster,
      taskDefinition: wsTaskDef,
      desiredCount: 2,
      securityGroups: [this.networkStack.ecsSg],
      assignPublicIp: false,
      enableExecuteCommand: false, // This removes GuardDuty VPCe, making automatic destruction almost impossible
    });
    return wsService;
  }

  registerLoadBalancerTarget(wsService: ecs.FargateService) {
    this.networkStack.mainListener.addTargets("WebsocketTargets", {
      port: 80,
      targets: [wsService],
      healthCheck: {
        enabled: true,
        port: "80",
        protocol: elbv2.Protocol.TCP, // TCP for NLB
        interval: Duration.seconds(60),
        timeout: Duration.seconds(10),
        healthyThresholdCount: 2,
        unhealthyThresholdCount: 2,
      },
    });
  }

  // Temporary workaround to force credential refresh every 5 hours by stopping tasks
  // (until official Python SDK supports automatic credential fetching from ECS task role)
  temp_addTasksRotateLambda(
    ecsService: ecs.FargateService,
    ecsCluster: ecs.Cluster
  ) {
    const taskRotater = new NodejsFunction(this, "ECSTaskRotateLambda", {
      runtime: lambda.Runtime.NODEJS_LATEST,
      entry: path.join(__dirname, "../lambda/ecsTaskRotater/index.ts"),
      handler: "handler",
      timeout: Duration.minutes(10),
      environment: {
        ECS_CLUSTER_NAME: ecsCluster.clusterName,
        ECS_SERVICE_NAME: ecsService.serviceName,
      },
    });
    taskRotater.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["ecs:ListTasks", "ecs:StopTask"],
        resources: ["*"],
        conditions: {
          ArnEquals: {
            "ecs:cluster": ecsCluster.clusterArn,
          },
        },
      })
    );
    // Create EventBridge rule to trigger the Lambda every 5 hours: before credentials expire (6 hours)
    const rule = new events.Rule(this, "ScheduleTaskRotation", {
      schedule: events.Schedule.rate(Duration.hours(5)),
      description: "Triggers ECS task rotation every 5 hours",
    });

    // Add the Lambda function as a target for the rule
    rule.addTarget(new targets.LambdaFunction(taskRotater));
  }

  createFrontendConfig() {
    const configCreatorFunction = new lambda.Function(
      this,
      "ConfigJsCreatorFunction",
      {
        runtime: lambda.Runtime.NODEJS_LATEST,
        handler: "lambda.handler",
        code: lambda.Code.fromAsset(
          path.join(__dirname, "../lambda/configCreator")
        ),
        timeout: Duration.minutes(1),
      }
    );

    const configProvider = new cr.Provider(this, "ConfigProvider", {
      onEventHandler: configCreatorFunction,
    });

    this.networkStack.frontendBucket.grantWrite(configCreatorFunction);

    const configResource = new cdk.CustomResource(this, "ConfigJsResource", {
      serviceToken: configProvider.serviceToken,
      properties: {
        userPoolId: this.userPool.userPoolId,
        clientId: this.userPoolClient.userPoolClientId,
        nlbUrl: `http://${this.networkStack.nlb.loadBalancerDnsName}:80`,
        cloudFrontUrl: this.cloudFrontUrl,
        bucketName: this.networkStack.frontendBucket.bucketName,
        cognitoDomain: `https://${this.userPoolDomain.domainName}.auth.${this.region}.amazoncognito.com`,
        // Adding a version or timestamp ensures this runs on every deployment
        version: Date.now().toString(),
      },
    });

    configResource.node.addDependency(this.userPool);
    configResource.node.addDependency(this.userPoolClient);
    configResource.node.addDependency(this.networkStack.nlb);
    configResource.node.addDependency(this.networkStack.frontendDistribution);

    const configContent = configResource.getAttString("configContent");

    const frontendDeployment = new s3deploy.BucketDeployment(
      this,
      "DeployFrontend",
      {
        sources: [
          s3deploy.Source.asset(path.join(__dirname, "../../frontend/dist")),
          // Use data source for the dynamically generated config
          s3deploy.Source.data("config.js", configContent),
        ],
        destinationBucket: this.networkStack.frontendBucket,
        distribution: this.networkStack.frontendDistribution,
        distributionPaths: ["/*"],
      }
    );
    // Workaround to enable destruction of cloudFront cache invalidation
    frontendDeployment.handlerRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "cloudfront:GetInvalidation",
          "cloudfront:CreateInvalidation",
        ],
        resources: ["*"],
      })
    );
  }

  logOutputs() {
    new cdk.CfnOutput(this, "FrontendUrl", {
      value: this.cloudFrontUrl,
      description: "Frontend URL",
    });

    new cdk.CfnOutput(this, "BackendUrl", {
      value: `${this.cloudFrontUrl}/api`,
      description: "Backend API Endpoint",
    });

    new cdk.CfnOutput(this, "NlbUrl", {
      value: `http://${this.networkStack.nlb.loadBalancerDnsName}:80`,
      description: "NLB URL (Direct)",
    });

    new cdk.CfnOutput(this, "CognitoUserPoolId", {
      value: this.userPool.userPoolId,
      description: "Cognito User Pool ID",
    });

    new cdk.CfnOutput(this, "CognitoAppClientId", {
      value: this.userPoolClient.userPoolClientId,
      description: "Cognito App Client ID",
    });

    new cdk.CfnOutput(this, "CognitoDomain", {
      value: `https://${this.userPoolDomain.domainName}.auth.${this.region}.amazoncognito.com`,
      description: "Cognito Domain",
    });
  }

  constructor(scope: Construct, id: string, props: S2SAppStackProps) {
    super(scope, id, props);

    // Setup.
    this.networkStack = props.networkStack;
    this.cloudFrontUrl = `https://${this.networkStack.frontendDistribution.distributionDomainName}`;

    // Create resources.
    this.createAuthResources(props.cognitoDomainPrefix);
    const { ecsCluster, wsTaskDef } = this.createEcsResources(
      props.knowledgeBaseId,
      props.dynamoDbTableName
    );
    const wsService = this.createContainerDefinition(ecsCluster, wsTaskDef);
    this.registerLoadBalancerTarget(wsService);
    // This is a temporary workaround to the lack of credential refresh in the experimental Python SDK
    this.temp_addTasksRotateLambda(wsService, ecsCluster);

    this.createFrontendConfig();

    // Conclusion.
    this.logOutputs();

    if (process.env.ENV !== "prod") {
      cdk.Aspects.of(this).add(
        new EnforceDeletionPolicy(cdk.RemovalPolicy.DESTROY)
      );
    }
  }
}

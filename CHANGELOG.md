# Change Log

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

- [feature] Easier system prompt adjustment from the UI
- [developer experience] Easier custom tool extension

## [0.1.1] - 2025-04-16

- [bug fix] Sample application works after 6 hours.

Backend stopped working after 6 hours due to AWS credential expiration. The experimental Python SDK does not handle this credential refresh natively yet, so we built a manual credential fetching logic in the backend from the ECS role. See https://github.com/aws-samples/sample-sonic-cdk-agent/pull/8 for details.

- [developer experience] ECS logs don't contain confusing errors from NLB health checks.

NLB health checks sent empty TCP packets for health checks and the backend WebSocket process kept outputting logs so much every minute. It was hard to find the right logs for your tool invocation and build on top of this sample. Now, it contains essential logs only. See https://github.com/aws-samples/sample-sonic-cdk-agent/pull/9 for details.

- [chore] Updated outdated dependencies

## [0.1.0] - 2025-04-09

- Initial version released.

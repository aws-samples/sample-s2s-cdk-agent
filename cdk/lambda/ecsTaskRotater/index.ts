const AWS = require("aws-sdk");
const ecs = new AWS.ECS();

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

exports.handler = async (event: any) => {
  const cluster = process.env.ECS_CLUSTER_NAME;
  const service = process.env.ECS_SERVICE_NAME;
  const delayBetweenStops = 60000; // 60 seconds default

  try {
    // List running tasks for the service
    const { taskArns } = await ecs
      .listTasks({
        cluster,
        serviceName: service,
        desiredStatus: "RUNNING",
      })
      .promise();

    let successfulStops = 0;
    const errors = [];
    console.log(`Retrieved running tasks: ${taskArns}`);

    // Process tasks sequentially
    for (const taskArn of taskArns) {
      try {
        await ecs
          .stopTask({
            cluster,
            task: taskArn,
            reason: "Rolling restart one task at a time",
          })
          .promise();

        successfulStops++;
        console.log(`Stopped task ${taskArn}`);

        // Wait for new task to become healthy
        if (taskArns.length > 1) {
          await sleep(delayBetweenStops);
        }
      } catch (error) {
        console.error(`Failed to stop ${taskArn}:`, error);
        errors.push(`${taskArn}: ${error}`);
      }
    }

    const resultMessage = `Stopped ${successfulStops}/${taskArns.length} tasks.`;
    if (errors.length > 0) {
      return {
        statusCode: 207, // Multi-status
        body: JSON.stringify({
          message: resultMessage,
          errors,
        }),
      };
    }

    return resultMessage;
  } catch (error) {
    console.error("Critical error:", error);
    throw new Error(`Restart failed: ${error}`);
  }
};

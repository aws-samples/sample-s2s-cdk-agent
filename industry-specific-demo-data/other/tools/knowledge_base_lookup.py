#!/usr/bin/env python3

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

import json
import boto3
import sys
import os
from dotenv import load_dotenv


def get_knowledge_base_id():
    """
    Loads and returns the knowledge base ID from the .env file.
    """
    # Load environment variables from .env file
    load_dotenv()

    # Get the knowledge base ID
    knowledge_base_id = os.getenv("KNOWLEDGE_BASE_ID")

    if not knowledge_base_id:
        raise ValueError("KNOWLEDGE_BASE_ID not found in .env file")

    return knowledge_base_id


def main(query):
    knowledge_base_id = get_knowledge_base_id()
    try:
        bedrock_agent = boto3.client("bedrock-agent-runtime")

        # Retrieve from your KB using the query
        response = bedrock_agent.retrieve(
            knowledgeBaseId=knowledge_base_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": 5}
            },
        )

        # Format the results
        results = []
        for item in response.get("retrievalResults", []):
            result = {
                "content": item.get("content", {}).get("text", ""),
                "location": item.get("location", {})
                .get("s3Location", {})
                .get("uri", ""),
                "score": item.get("score", 0.0),
            }

            if "metadata" in item and item["metadata"]:
                result["metadata"] = item["metadata"]

            results.append(result)

        # Create the output JSON
        output = {"query": query, "results": results, "result_count": len(results)}

        return output

    except Exception as e:
        error = {"error": f"Error querying knowledge base: {str(e)}"}
        print(json.dumps(error))
        return 1


if __name__ == "__main__":
    sys.exit(main(""))

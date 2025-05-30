#!/bin/bash

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

set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting deployment...${NC}"

# Setup industry-specific demo
echo -e "${BLUE}Setting up industry-specific demo${NC}"
echo -e "${YELLOW}Available industries:${NC}"

# List available industries from the industry-specific-demo-data folder
available_industries=()
for dir in ./industry-specific-demo-data/*/; do
  if [ -d "$dir" ]; then
    industry=$(basename "$dir")
    if [[ "$industry" != "__pycache__" ]]; then
      available_industries+=("$industry")
      echo -e "  - ${GREEN}$industry${NC}"
    fi
  fi
done

# Prompt user to select an industry
echo -e "${YELLOW}Please enter the name of the industry you want to use:${NC}"
read selected_industry

# Validate the selected industry
valid_industry=false
for industry in "${available_industries[@]}"; do
  if [[ "$industry" == "$selected_industry" ]]; then
    valid_industry=true
    break
  fi
done

if [[ "$valid_industry" == false ]]; then
  echo -e "${RED}Error: '$selected_industry' is not a valid industry.${NC}"
  echo -e "${YELLOW}Available industries: ${available_industries[*]}${NC}"
  exit 1
fi

echo -e "${GREEN}Setting up demo for $selected_industry industry...${NC}"

# 0. Copy industry specific .env file
echo -e "${RED}Copy .env file to backend...${NC}"
cp -r "./industry-specific-demo-data/$selected_industry/.env" "./backend/"

# Remove existing tools directory if it exists
if [ -d "./backend/tools" ]; then
  echo -e "${YELLOW}Removing existing tools directory...${NC}"
  rm -f ./backend/tools/*.py
fi

# Copy industry-specific tools to backend
echo -e "${YELLOW}Copying $selected_industry tools to backend...${NC}"
# echo -e "cp -r "./industry-specific-demo-data/$selected_industry/tools" "./backend/""
cp -r "./industry-specific-demo-data/$selected_industry/tools" "./backend/"
echo -e "${GREEN}Successfully copied $selected_industry tools to backend.${NC}"

# 1. Check and display AWS credentials and region
echo -e "${GREEN}Checking AWS credentials and region...${NC}"
echo -ne "${YELLOW}AWS Identity:${NC} "
aws sts get-caller-identity --output text --query 'Arn'

echo -ne "\n${YELLOW}AWS Region:${NC} "
aws ec2 describe-availability-zones --output text --query 'AvailabilityZones[0].[RegionName]'
echo ""

npm install

# 2. Install frontend dependencies for specific industry
echo -e "${GREEN}Copying $selected_industry system prompts and config information to frontend...${NC}"
cp -r "./industry-specific-demo-data/$selected_industry/config/" "./frontend/public"
echo -e "${GREEN}Successfully copied $selected_industry system prompt and config data to backend.${NC}"

# Ask user if they want to import sample data
echo -e "${YELLOW}Would you like to import sample data for $selected_industry? (y/N)${NC}"
read -r import_data
import_data=${import_data:-n}

if [[ "$import_data" == "y" || "$import_data" == "Y" ]]; then
  echo -e "${GREEN}Importing sample data for $selected_industry...${NC}"
  
  # Check if import script exists
  import_script="./industry-specific-demo-data/$selected_industry/sample-data/import_data_to_dynamodb.py"
  if [ -f "$import_script" ]; then
    echo -e "${BLUE}Setting up Python virtual environment...${NC}"
    venv_dir="./.venv"

    # Create venv if it doesn't exist
    if [ ! -d "$venv_dir" ]; then
      python3 -m venv "$venv_dir"
      echo -e "${GREEN}Virtual environment created at $venv_dir${NC}"
    else
      echo -e "${YELLOW}Virtual environment already exists. Reusing it.${NC}"
    fi

    # Activate the virtual environment
    source "$venv_dir/bin/activate"

    # Install dependencies from requirements.txt
    requirements_file="./industry-specific-demo-data/$selected_industry/sample-data/requirements.txt"
    if [ -f "$requirements_file" ]; then
      echo -e "${BLUE}Installing dependencies from $requirements_file...${NC}"
      pip install -r "$requirements_file"
      echo -e "${GREEN}Dependencies installed successfully.${NC}"
    else
      echo -e "${YELLOW}No requirements.txt found at $requirements_file. Skipping dependency install.${NC}"
    fi

    # Run the import script
    echo -e "${BLUE}Running import script...${NC}"
    if python "$import_script"; then
      echo -e "${GREEN}Sample data imported successfully.${NC}"
    else
      echo -e "${RED}❌ Sample data import script failed. Exiting.${NC}"
      deactivate
      exit 1
    fi
    # Deactivate venv after running
    deactivate
    echo -e "${GREEN}Sample data imported successfully.${NC}"
  else
    echo -e "${RED}Import script not found at $import_script${NC}"
    # echo -e "${YELLOW}Skipping data import.${NC}"
    exit 1
  fi
else
  echo -e "${BLUE}Skipping sample data import.${NC}"
fi

npm run build:frontend

echo -e "${GREEN}Deploying the CDK stacks...${NC}"
cd cdk
npx aws-cdk deploy --all --require-approval never

echo "${GREEN}✅️ Deployment script exited with status 0.${NC}"
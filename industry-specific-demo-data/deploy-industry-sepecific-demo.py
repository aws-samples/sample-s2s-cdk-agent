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

import shutil
import subprocess
import sys
import os
from pathlib import Path

def print_colored(text, color):
    colors = {
        'green': '\033[0;32m',
        'yellow': '\033[1;33m',
        'red': '\033[0;31m',
        'blue': '\033[0;34m',
        'end': '\033[0m'
    }
    print(f"{colors[color]}{text}{colors['end']}")

def list_industries(base_path):
    industries = []
    for item in base_path.iterdir():
        if item.is_dir() and item.name != '__pycache__':
            industries.append(item.name)
    return industries

def copy_tree(src, dst):
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

def main():
    print_colored("Starting deployment...", "green")

    demo_data_path = Path(__file__).parent.resolve()  # Now inside industry-specific-demo-data
    base_dir = demo_data_path.parent  # Go up to project root
    industries = list_industries(demo_data_path)

    print_colored("Setting up industry-specific demo", "blue")
    print_colored("Available industries:", "yellow")
    for industry in industries:
        print_colored(f"  - {industry}", "green")

    selected_industry = input("Please enter the name of the industry you want to use: ").strip()

    if selected_industry not in industries:
        print_colored(f"Error: '{selected_industry}' is not a valid industry.", "red")
        print_colored("Available industries: " + ", ".join(industries), "yellow")
        sys.exit(1)

    print_colored(f"Setting up demo for {selected_industry} industry...", "green")

    # Copy .env file
    env_src = demo_data_path / selected_industry / ".env"
    env_dst = base_dir / "backend" / ".env"
    home_dir = base_dir / ".env"
    print_colored("Copying .env file to backend and home directory...", "red")
    shutil.copy(env_src, env_dst)
    shutil.copy(env_src, home_dir)

    # Confirm and remove existing backend/tools/*.py
    tools_path = base_dir / "backend" / "tools"
    if tools_path.exists():
        confirm_delete = input(f"Are you sure you want delete existing tools in the backend folder? (y/N): ").strip().lower()
        if confirm_delete == 'y':
            # Delete existing tools
            print_colored("Removing existing tools directory...", "yellow")
            shutil.rmtree(tools_path)                
            
            # Now copy tools for the select industry
            tools_src = demo_data_path / selected_industry / "tools"
            print_colored(f"Copying tools from {tools_src} to backend...", "yellow")
            copy_tree(tools_src, tools_path)
        else:
            print_colored("Skipping deletion of existing tools directory.", "blue")


    # Check AWS identity
    print_colored("Checking AWS credentials and region...", "green")
    subprocess.run(["aws", "sts", "get-caller-identity", "--output", "text", "--query", "Arn"])
    subprocess.run(["aws", "ec2", "describe-availability-zones", "--output", "text", "--query", "AvailabilityZones[0].[RegionName]"])

    # npm install
    subprocess.run(["npm", "install"], cwd=str(base_dir), check=True)

    # Copy config to frontend
    frontend_config_src = demo_data_path / selected_industry / "config"
    home_dir_config_dst = base_dir / "config"
    frontend_config_dst = base_dir / "frontend" / "public"
    print_colored(f"Copying {selected_industry} config to frontend...", "green")
    copy_tree(frontend_config_src, frontend_config_dst)
    copy_tree(frontend_config_src, home_dir_config_dst)

    # Sample data import
    import_choice = input(f"Would you like to import sample data for {selected_industry}? (y/N): ").strip().lower()
    if import_choice == 'y':
        print_colored(f"Importing sample data for {selected_industry}...", "green")
        import_script = demo_data_path / selected_industry / "sample-data" / "import_data_to_dynamodb.py"
        requirements = demo_data_path / selected_industry / "sample-data" / "requirements.txt"
        venv_path = base_dir / ".venv"

        if not venv_path.exists():
            print_colored("Creating virtual environment...", "blue")
            subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)

        # Activate virtual env and install dependencies
        bin_dir = "Scripts" if os.name == "nt" else "bin"
        pip_path = venv_path / bin_dir / "pip"
        python_path = venv_path / bin_dir / "python"

        if requirements.exists():
            print_colored(f"Installing dependencies from {requirements}...", "blue")
            subprocess.run([str(pip_path), "install", "-r", str(requirements)], check=True)

        # Run the import script
        print_colored("Running import script...", "blue")
        result = subprocess.run([str(python_path), str(import_script)])
        if result.returncode != 0:
            print_colored("❌ Sample data import failed.", "red")
            sys.exit(1)

    else:
        print_colored("Skipping sample data import.", "blue")

    # Build frontend
    subprocess.run(["npm", "run", "build:frontend"], cwd=str(base_dir), check=True)

    # Deploy CDK
    print_colored("Deploying the CDK stacks...", "green")
    subprocess.run(["npx", "aws-cdk", "deploy", "--all", "--require-approval", "never"], cwd=str(base_dir / "cdk"))

    print_colored("✅ Deployment script exited with status 0.", "green")

if __name__ == "__main__":
    main()

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

import boto3
import csv
import os
from dotenv import load_dotenv
from decimal import Decimal

def load_env_variables():
    """Load environment variables from .env file"""
    load_dotenv(dotenv_path="backend/.env")
    table_name = os.getenv('DYNAMODB_TABLE_NAME')
    if not table_name:
        raise ValueError("DYNAMODB_TABLE_NAME not found in .env file")
    return table_name

def create_dynamodb_table(table_name):
    """Create DynamoDB table if it doesn't exist"""
    dynamodb = boto3.resource('dynamodb')
    
    # Check if table already exists
    existing_tables = list(dynamodb.tables.all())
    if table_name in [table.name for table in existing_tables]:
        print(f"Table {table_name} already exists")
        return dynamodb.Table(table_name)
    
    # Create table with phone_number as partition key
    table = dynamodb.create_table(
        TableName=table_name,
        KeySchema=[
            {'AttributeName': 'phone_number', 'KeyType': 'HASH'}  # Partition key
        ],
        AttributeDefinitions=[
            {'AttributeName': 'phone_number', 'AttributeType': 'S'}
        ],
        ProvisionedThroughput={
            'ReadCapacityUnits': 5,
            'WriteCapacityUnits': 5
        }
    )
    
    # Wait until the table exists
    table.meta.client.get_waiter('table_exists').wait(TableName=table_name)
    print(f"Table {table_name} created successfully")
    return table

def import_data_to_dynamodb(table, csv_file_path):
    """Import data from CSV file to DynamoDB table"""
    with open(csv_file_path, mode='r') as csv_file:
        csv_reader = csv.DictReader(csv_file)
        
        # Batch write items to DynamoDB
        with table.batch_writer() as batch:
            for row in csv_reader:
                # Convert empty strings to None
                for key, value in row.items():
                    if value == '':
                        row[key] = None
                    # Convert numeric values to Decimal for DynamoDB
                    elif key in ['monthly_bill', 'data_usage_gb']:
                        row[key] = Decimal(str(value))
                    elif key == 'minutes_used':
                        row[key] = int(value)
                
                # Add item to batch
                batch.put_item(Item=row)
    
    print(f"Data imported successfully from {csv_file_path}")

def main():
    # Load table name from .env file
    table_name = load_env_variables()
    
    # Define CSV file path
    csv_file_path = 'industry-specific-demo-data/telco/sample-data/telco_customer_sample_data.csv'
    
    # Create DynamoDB table
    table = create_dynamodb_table(table_name)
    
    # Import data to DynamoDB
    import_data_to_dynamodb(table, csv_file_path)
    
    print("Process completed successfully")
    return 1

if __name__ == "__main__":
    main()

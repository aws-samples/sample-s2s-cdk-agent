import boto3
import csv
import os
from decimal import Decimal

def create_table_if_not_exists(dynamodb_client, table_name):
    """Create the DynamoDB table if it doesn't exist"""
    
    # Check if table already exists
    existing_tables = dynamodb_client.list_tables()['TableNames']
    if table_name in existing_tables:
        print(f"Table {table_name} already exists")
        return 
    
    # Create table with airpointsNumber as partition key and bookingReference as sort key
    response = dynamodb_client.create_table(
        TableName=table_name,
        KeySchema=[
            {'AttributeName': 'airpointsNumber', 'KeyType': 'HASH'},  # Partition key
            {'AttributeName': 'bookingReference', 'KeyType': 'RANGE'}  # Sort key
        ],
        AttributeDefinitions=[
            {'AttributeName': 'airpointsNumber', 'AttributeType': 'S'},
            {'AttributeName': 'bookingReference', 'AttributeType': 'S'}
        ],
        BillingMode='PAY_PER_REQUEST',
        GlobalSecondaryIndexes=[
            {
                'IndexName': f'{table_name}-index',
                'KeySchema': [
                    {'AttributeName': 'bookingReference', 'KeyType': 'HASH'},  # Partition key for GSI
                    {'AttributeName': 'airpointsNumber', 'KeyType': 'RANGE'}   # Sort key for GSI
                ],
                'Projection': {
                    'ProjectionType': 'ALL'
                }
            }
        ]
    )
    
    print(f"Creating table {table_name}...")
    
    # Wait for table to be created
    waiter = dynamodb_client.get_waiter('table_exists')
    waiter.wait(TableName=table_name)
    print(f"Table {table_name} created successfully")

def import_csv_to_dynamodb(csv_file_path, table_name, region='us-east-1'):
    """Import data from CSV file to DynamoDB table"""
    
    # Initialize DynamoDB client and resource
    dynamodb_client = boto3.client('dynamodb', region_name=region)
    dynamodb = boto3.resource('dynamodb', region_name=region)
    
    # Create table if it doesn't exist
    create_table_if_not_exists(dynamodb_client, table_name)
    
    # Get table resource
    table = dynamodb.Table(table_name)
    
    # Read and import CSV data
    with open(csv_file_path, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        
        # Process each row in the CSV
        for row in reader:
            # Convert empty strings to None
            item = {k: (v if v != '' else None) for k, v in row.items()}
            
            # Convert numeric values to Decimal for DynamoDB compatibility
            for key, value in item.items():
                if value is not None:
                    # Ensure airpointsNumber is always a string
                    if key == 'airpointsNumber':
                        item[key] = str(value)
                    else:
                        try:
                            # Try to convert to Decimal if it's a number
                            float_val = float(value)
                            item[key] = Decimal(str(float_val))
                        except (ValueError, TypeError):
                            # Keep as string if not a number
                            pass
            
            # Ensure required keys exist
            if 'airpointsNumber' not in item or 'bookingReference' not in item:
                print(f"Skipping row, missing required keys: {item}")
                continue
                
            # Put item in DynamoDB
            try:
                table.put_item(Item=item)
                print(f"Added item: {item['airpointsNumber']} - {item['bookingReference']}")
            except Exception as e:
                print(f"Error adding item {item}: {str(e)}")

def main():
    table_name = 'agentic_ai_demo_customer_data'
    csv_file_path = 'results-updated-airpoints-ref.csv'
    
    # Check if CSV file exists
    if not os.path.exists(csv_file_path):
        print(f"CSV file not found: {csv_file_path}")
        return
    
    import_csv_to_dynamodb(csv_file_path, table_name)
    print("Import completed")

if __name__ == "__main__":
    main()

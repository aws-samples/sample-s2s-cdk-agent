#!/usr/bin/env python3
"""
Import script for travel company sample data.
This script imports the sample CSV data into DynamoDB tables.
"""

import os
import csv
import boto3
import logging
from datetime import datetime
from decimal import Decimal
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')

def create_table(table_name, key_schema, attribute_definitions, global_secondary_indexes=None):
    """Create a DynamoDB table if it doesn't exist."""
    try:
        create_params = {
            'TableName': table_name,
            'KeySchema': key_schema,
            'AttributeDefinitions': attribute_definitions,
            'BillingMode': 'PAY_PER_REQUEST'
        }
        
        if global_secondary_indexes:
            create_params['GlobalSecondaryIndexes'] = global_secondary_indexes
            
        table = dynamodb.create_table(**create_params)
        logger.info(f"Creating table {table_name}...")
        table.wait_until_exists()
        logger.info(f"Table {table_name} created successfully")
        return table
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            logger.info(f"Table {table_name} already exists")
            return dynamodb.Table(table_name)
        else:
            logger.error(f"Error creating table {table_name}: {e}")
            raise

def import_customer_bookings():
    """Import customer bookings data."""
    table_name = 'thl_customer_bookings'
    
    # Create table if it doesn't exist
    table = create_table(
        table_name=table_name,
        key_schema=[
            {'AttributeName': 'contact_phone', 'KeyType': 'HASH'},
            {'AttributeName': 'booking_ref', 'KeyType': 'RANGE'}
        ],
        attribute_definitions=[
            {'AttributeName': 'contact_phone', 'AttributeType': 'S'},
            {'AttributeName': 'booking_ref', 'AttributeType': 'S'}
        ],
        global_secondary_indexes=[
            {
                'IndexName': table_name+'-index',
                'KeySchema': [
                    {'AttributeName': 'booking_ref', 'KeyType': 'HASH'},
                    {'AttributeName': 'contact_phone', 'KeyType': 'RANGE'}
                ],
                'Projection': {
                    'ProjectionType': 'ALL'
                }
            }
        ]
    )
    
    # Import data from CSV
    with open('customer_bookings.csv', mode='r') as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            # Parse itinerary into a list
            if 'itinerary' in row:
                row['itinerary'] = row['itinerary'].split(',')
            
            # Convert date strings to ISO format
            if 'trip_start' in row:
                row['trip_start'] = row['trip_start']
            if 'trip_end' in row:
                row['trip_end'] = row['trip_end']
                
            # Ensure all fields are properly formatted
            item = {
                'contact_phone': row['contact_phone'],
                'booking_ref': row['booking_ref'],
                'accommodation_id': row['accomodation_id'],
                'accommodation_name': row['accomodation_name'],
                'accommodation_location': row['accomodation_location'],
                'customer_name': row['customer_name'],
                'customer_email': row['customer_email'],
                'vehicle_reg': row['vehicle_reg'],
                'vehicle_model': row['vehicle_model'],
                'trip_start': row['trip_start'],
                'trip_end': row['trip_end'],
                'itinerary': row['itinerary']
            }
            
            try:
                table.put_item(Item=item)
                logger.info(f"Added booking for {item['contact_phone']} with booking ref {item['booking_ref']}")
            except ClientError as e:
                logger.error(f"Error adding booking {item['booking_ref']} for {item['contact_phone']}: {e}")

def import_vehicle_information():
    """Import vehicle information data."""
    table_name = 'thl_vehicle_information'
    
    # Create table if it doesn't exist
    table = create_table(
        table_name=table_name,
        key_schema=[{'AttributeName': 'registration', 'KeyType': 'HASH'}],
        attribute_definitions=[{'AttributeName': 'registration', 'AttributeType': 'S'}]
    )
    
    # Import data from CSV
    with open('vehicle_information.csv', mode='r') as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            # Convert string 'true'/'false' to boolean
            if 'gps_enabled' in row:
                row['gps_enabled'] = row['gps_enabled'].lower() == 'true'
            
            try:
                table.put_item(Item=row)
                logger.info(f"Added vehicle: {row['registration']}")
            except ClientError as e:
                logger.error(f"Error adding vehicle {row['registration']}: {e}")

def import_accommodation_options():
    """Import accommodation options data."""
    table_name = 'thl_accommodation_options'
    
    # Create table if it doesn't exist
    table = create_table(
        table_name=table_name,
        key_schema=[{'AttributeName': 'accommodation_id', 'KeyType': 'HASH'}],
        attribute_definitions=[{'AttributeName': 'accommodation_id', 'AttributeType': 'S'}]
    )
    
    # Import data from CSV
    with open('accommodation_options.csv', mode='r') as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            # Convert string values to appropriate types
            if 'latitude' in row:
                row['latitude'] = Decimal(str(row['latitude']).strip('"'))
            if 'longitude' in row:
                row['longitude'] = Decimal(str(row['longitude']).strip('"'))
            if 'powered_sites_available' in row:
                row['powered_sites_available'] = int(row['powered_sites_available'])
            if 'unpowered_sites_available' in row:
                row['unpowered_sites_available'] = int(row['unpowered_sites_available'])
            if 'cabins_available' in row:
                row['cabins_available'] = int(row['cabins_available'])
            if 'family_friendly' in row:
                row['family_friendly'] = row['family_friendly'].lower() == 'true'
            if 'pet_friendly' in row:
                row['pet_friendly'] = row['pet_friendly'].lower() == 'true'
            if 'amenities' in row:
                row['amenities'] = row['amenities'].split(',')
            
            # Add the id field using the accomodation_id value
            row['accommodation_id'] = row['accomodation_id']
            
            try:
                table.put_item(Item=row)
                logger.info(f"Added accommodation: {row['accomodation_id']} - {row['accomodation_name']}")
            except ClientError as e:
                logger.error(f"Error adding accommodation {row['accomodation_id']}: {e}")

def import_nearby_services():
    """Import nearby services data."""
    table_name = 'thl_nearby_services'
    
    # Create table if it doesn't exist
    table = create_table(
        table_name=table_name,
        key_schema=[{'AttributeName': 'id', 'KeyType': 'HASH'}],
        attribute_definitions=[{'AttributeName': 'id', 'AttributeType': 'S'}]
    )
    
    # Import data from CSV
    with open('nearby_services.csv', mode='r') as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            # Convert string values to appropriate types
            if 'latitude' in row:
                row['latitude'] = Decimal(str(row['latitude']).strip('"'))
            if 'longitude' in row:
                row['longitude'] = Decimal(str(row['longitude']).strip('"'))
            if 'rating' in row:
                row['rating'] = Decimal(str(row['rating']).strip('"'))
            
            try:
                table.put_item(Item=row)
                logger.info(f"Added service: {row['id']} - {row['name']}")
            except ClientError as e:
                logger.error(f"Error adding service {row['id']}: {e}")

def import_appliance_troubleshooting():
    """Import appliance troubleshooting data."""
    table_name = 'thl_appliance_troubleshooting'
    
    # Create table if it doesn't exist
    table = create_table(
        table_name=table_name,
        key_schema=[
            {'AttributeName': 'appliance_type', 'KeyType': 'HASH'},
            {'AttributeName': 'model', 'KeyType': 'RANGE'}
        ],
        attribute_definitions=[
            {'AttributeName': 'appliance_type', 'AttributeType': 'S'},
            {'AttributeName': 'model', 'AttributeType': 'S'}
        ]
    )
    
    # Import data from CSV
    with open('appliance_troubleshooting.csv', mode='r') as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            # Convert solution to list format
            if 'solution' in row:
                row['solution'] = row['solution'].split('\n')
            
            try:
                table.put_item(Item=row)
                logger.info(f"Added troubleshooting: {row['appliance_type']} - {row['model']}")
            except ClientError as e:
                logger.error(f"Error adding troubleshooting {row['appliance_type']} - {row['model']}: {e}")

def main():
    """Main function to import all data."""
    try:
        # Change to the directory containing this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(script_dir)
        
        # Import all data
        import_customer_bookings()
        import_vehicle_information()
        import_accommodation_options()
        import_nearby_services()
        import_appliance_troubleshooting()
        
        logger.info("Data import completed successfully")
    except Exception as e:
        logger.error(f"Error during data import: {e}")

if __name__ == "__main__":
    main()

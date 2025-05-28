# THL Sonic Digital Concierge

This module implements a voice assistant for Tourism Holdings Limited (THL) campervan customers, providing support during their travel journey.

## Use Cases

### Use Case 1: Appliance Troubleshooting

A customer nearing the end of their trip has trouble with an appliance (e.g., fridge):

1. Customer initiates a Sonic chat through the app or by calling customer service
2. THL Sonic recognizes the customer based on booking reference or vehicle registration
3. THL Sonic acknowledges the problem and identifies the specific appliance model
4. Customer describes the issue
5. THL Sonic provides troubleshooting suggestions
6. If the customer can't address the issue immediately, THL Sonic:
   - Sends troubleshooting steps via email/SMS/in-app message
   - Creates a service ticket for the service team (to help with vehicle turnaround)

### Use Case 2: Itinerary Change Assistance

A family is delayed during their trip and needs to change their accommodation plans:

1. Customer initiates a Sonic chat
2. THL Sonic greets them and asks about their trip
3. Customer explains the delay and asks for alternative accommodation options
4. THL Sonic:
   - Checks CamperMate for nearby options
   - Suggests family-friendly alternatives with powered sites
   - Offers to make a reservation
   - Provides navigation assistance to the new location
   - Suggests a restaurant along the route based on estimated arrival time

## Tools

The THL Sonic Digital Concierge includes the following tools:

1. **Customer Lookup**: Identifies customers by booking reference, vehicle registration, or name
2. **Appliance Troubleshooting**: Provides solutions for common appliance issues
3. **Accommodation Finder**: Locates available accommodation options based on location and preferences
4. **Booking Manager**: Creates, modifies, or cancels accommodation bookings
5. **Nearby Services**: Finds restaurants, service centers, and other points of interest
6. **Notification Sender**: Sends information to customers via email, SMS, or in-app messages
7. **Navigation Helper**: Provides directions and navigation assistance

## Sample Data

The module includes sample data for:

1. Customer bookings
2. Vehicle information
3. Accommodation options
4. Nearby services
5. Appliance troubleshooting guides

## Setup

To deploy the THL Sonic Digital Concierge:

```bash
./setup.sh travel
```

This will:
1. Create necessary AWS resources (DynamoDB tables, Cognito user pool, etc.)
2. Import sample data
3. Deploy the application

## Testing

After deployment, you can test the application by:

1. Creating a test user in Cognito
2. Accessing the application through the provided URL
3. Logging in with the test user credentials
4. Initiating a voice conversation

## Customization

You can customize the THL Sonic Digital Concierge by:

1. Modifying the system prompt in `config/system_prompt.txt`
2. Adding or updating sample data in the `data` directory
3. Extending the tools in the `tools` directory

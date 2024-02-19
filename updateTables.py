import boto3
import json
from botocore.exceptions import ClientError
from googleapiclient.discovery import build
from google.oauth2 import service_account
from datetime import datetime, timedelta

credentials = service_account.Credentials.from_service_account_file(
    'credentials.json',
    scopes=['https://www.googleapis.com/auth/calendar']
)

# note to self: move this stuff elsewhere later
# connect to DynamoDB
dynamodb = boto3.resource('dynamodb')
  
# get the tables
table_new = dynamodb.Table('ap_events_new')
table_old = dynamodb.Table('ap_events_old')

# get our Google OAuth Client ID/Secret from AWS Secrets Manager
def get_secret():
    global google_oauth_client_id
    global google_oauth_secret_id

    secret_name = "googleOAuthCalendar"
    region_name = "us-east-1"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    secret_response = client.get_secret_value(SecretId=secret_name)
    secret_string = secret_response['SecretString']
    secret_dict = json.loads(secret_string)  # Assuming JSON format
    google_oauth_client_id = secret_dict['google_oauth_client_id']
    google_oauth_secret_id = secret_dict['google_oauth_client_secret']

def get_table_items(table_name):
    # Get all items from the table
    table = dynamodb.Table(table_name)
    response = table.scan()  
    return response['Items']

def delete_gcal_event(event_id):
    # Build the service
    service = build('calendar', 'v3', credentials=credentials)

    # Delete the event
    service.events().delete(calendarId='primary', eventId=event_id).execute()


def add_gcal_event(start_time, end_time):
    # Build the service
    service = build('calendar', 'v3', credentials=credentials)

    # Define the event
    event = {
        'summary': 'New Event',
        'start': {
            'dateTime': datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S').isoformat(),
            'timeZone': 'America/Los_Angeles',
        },
        'end': {
            'dateTime': datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S').isoformat(),
            'timeZone': 'America/Los_Angeles',
        },
    }

    # Add the event to the calendar
    event = service.events().insert(calendarId='primary', body=event).execute()

    # Return the ID of the new event
    return event['id']

def delete_table_items(table_name):
    # Get the table
    table = dynamodb.Table(table_name)

    # Scan the table
    response = table.scan()

    # Delete each item
    with table.batch_writer() as batch:
        for item in response['Items']:
            batch.delete_item(Key={'gCalID': item['gCalID']})

def update_calendar_events():
    # Get items from old and new tables
    old_table_items = get_table_items('ap_events_old')
    new_table_items = get_table_items('ap_events_new')

    # Compare date and time ranges
    old_dates = {(item['times'].split(' - ')[0], item['times'].split(' - ')[1]) for item in old_table_items}
    new_dates = {(item['times'].split(' - ')[0], item['times'].split(' - ')[1]) for item in new_table_items}

    if not new_table_items:
        for item in old_table_items:
            delete_gcal_event(item['gCalID'])
            
        return
    if old_dates != new_dates:
        # Delete old events from Google Calendar
        for item in old_table_items:
            delete_gcal_event(item['gCalID'])

        # Add new events to Google Calendar and store new items with gcal event ids in a temporary dictionary
        new_items_with_gcal_id = []
        for item in new_table_items:
            start_time, end_time = item['times'].split(' - ')
            gcal_event_id = add_gcal_event(start_time, end_time)
            item['gCalID'] = gcal_event_id
            new_items_with_gcal_id.append(item)

        # Delete all items from old table
        delete_table_items('ap_events_old')

        # Write new items with gcal event ids to old table
        with table_old.batch_writer() as batch:
            for item in new_items_with_gcal_id:
                batch.put_item(Item=item)

        # Delete all items from new table
        delete_table_items('ap_events_new')

def lambda_handler(event, context):
  get_secret()
  update_calendar_events()

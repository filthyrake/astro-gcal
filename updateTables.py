import boto3
import json
import logging
import os
from botocore.exceptions import ClientError
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta

logging.basicConfig(level=logging.DEBUG)
cal_id = os.environ.get('googleCalendarID')

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

    try:
        # Delete the event
        service.events().delete(calendarId=cal_id, eventId=event_id).execute()
    except HttpError as e:
        # Check if the error message contains "Resource has been deleted"
        if "Resource has been deleted" in str(e):
            # Ignore the error and continue
            logging.warning(f"Attempted to delete an event that has already been deleted: {event_id}")
        else:
            # If the error is something else, re-raise it
            raise


def add_gcal_event(start_time, end_time):
    try:
        # Log the start and end times
        logging.debug(f"Adding event with start time {start_time} and end time {end_time}")
        # Build the service
        service = build('calendar', 'v3', credentials=credentials)

        # Define the event
        event = {
            'summary': 'Good Astro Weather',
            'start': {
                'dateTime': datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S').isoformat(),
                'timeZone': 'America/Los_Angeles',
            },
            'end': {
                'dateTime': datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S').isoformat(),
                'timeZone': 'America/Los_Angeles',
            },
        }

        # Log the event details
        logging.debug(f"Event details: {event}")

        # Add the event to the calendar
        event = service.events().insert(calendarId=cal_id, body=event).execute()

        # Log the response from the Google Calendar API
        logging.debug(f"Response from Google Calendar API: {event}")

        # Return the ID of the new event
        return event['id']
    except Exception as e:
        logging.error(f"An error occurred while adding the event: {e}")
        return None

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
    try:
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
                    # Log the item being written to the table
                    logging.debug(f"Writing item to old table: {item}")
                    batch.put_item(Item=item)

        # Only delete items from new table if they have been successfully added to old table
        delete_table_items('ap_events_new')
    except Exception as e:
        logging.error(f"An error occurred while updating calendar events: {e}")

def lambda_handler(event, context):
  get_secret()
  update_calendar_events()

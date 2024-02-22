import json
import requests
import boto3
import os
import logging
import uuid
from pytz import timezone
from astral import LocationInfo
from astral.location import Location
from astral.sun import sun
from itertools import groupby
from operator import itemgetter
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.errors import HttpError

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

API_URL="https://astrosphericpublicaccess.azurewebsites.net/api/GetForecastData_V1"
LAT = os.environ.get('LAT')
LONG = os.environ.get('LONG')
MY_CITY = os.environ.get('CITY')
MY_STATE = os.environ.get('STATE')
MY_TIMEZONE = os.environ.get('TIMEZONE')
cal_id = os.environ.get('googleCalendarID')
json_object = json.loads('{}') 

credentials = service_account.Credentials.from_service_account_file(
    'credentials.json',
    scopes=['https://www.googleapis.com/auth/calendar']
)

time_zone = timezone(MY_TIMEZONE)

def get_forecast():
  global json_object
  get_secret()
  data = {'Latitude': LAT, 'Longitude': LONG, 'APIKey': API_KEY}
  headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}

  response = requests.post(API_URL, data=json.dumps(data), headers=headers)
  
  json_object = response.json()
  print(json_object)

good_seeing_offsets=[]
good_seeing_transparency_offsets=[]
good_seeing_transparency_clouds_offsets=[]
final_good_offsets=[]

# lets set our location for the astral library
city = LocationInfo(MY_CITY, MY_STATE, MY_TIMEZONE, LAT, LONG)
final_city = Location(city)

# connect to DynamoDB
dynamodb = boto3.resource('dynamodb')
  
# get the tables
table_old = dynamodb.Table('ap_events_old')

events = []

# get our astrospheric API key from AWS Secrets Manager
def get_secret():
    global API_KEY

    secret_name = "astrosphericAPIKey"
    region_name = "us-east-1"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    secret_response = client.get_secret_value(SecretId=secret_name)
    secret_string = secret_response['SecretString']
    secret_dict = json.loads(secret_string)  
    API_KEY = secret_dict['API_KEY']

def get_google_oauth_credentials_from_secrets_manager():
    secret_name = "googleOAuthCalendar"
    region_name = "us-east-1"

    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    secret_response = client.get_secret_value(SecretId=secret_name)
    secret_string = secret_response['SecretString']
    secret_dict = json.loads(secret_string)  # Assuming JSON format
    return secret_dict['google_oauth_client_id'], secret_dict['google_oauth_client_secret']

def event_exists(events, event):
    if not events:
        return False
    for existing_event in events:
        if existing_event['start'] == event['start'] and existing_event['end'] == event['end']:
            return True
    return False

def time_in_range(start, end, current):
    """Returns whether current is in the range [start, end]"""
    return start <= current <= end

def populate_table(events):
  # write items to the table
  with table_old.batch_writer() as batch:
      for event in events:
          # convert start and end times to strings and set gCalID to "none"
          times = f"{event['start']} - {event['end']}"
          item = {
              'uuid': event['id'], 
              'times': times,
              'gCalID': 'none'
          }
          batch.put_item(Item=item)

def update_calendar_events(service):
    try:
        logging.debug("Fetching all items from table...")
        table_items = get_all_items_from_table(table_old)

        table_dates = {(item['times'].split(' - ')[0], item['times'].split(' - ')[1]) for item in table_items if item['gCalID'] != 'none'}
        new_dates = {(item['times'].split(' - ')[0], item['times'].split(' - ')[1]) for item in events}

        logging.debug(f"Table dates: {table_dates}")
        logging.debug(f"New dates: {new_dates}")

        if not events:
            logging.debug("No new events. Deleting all existing events from Google Calendar...")
            for item in table_items:
                delete_event_from_google_calendar(service, item['gCalID'])
            return

        if table_dates != new_dates:
            logging.debug("Dates have changed. Updating Google Calendar events...")
            for item in table_items:
                delete_event_from_google_calendar(service, item['gCalID'])

            items_with_gcal_id = []
            for item in events:
              start_time, end_time = item['times'].split(' - ')
              logging.debug(f"Adding event with start time {start_time} and end time {end_time} to Google Calendar...")
              gcal_event_id = add_event_to_google_calendar(service, start_time, end_time)
              item['gCalID'] = gcal_event_id
              update_item_in_table(table_old, item['times'], item['id'], gcal_event_id)

            logging.debug("Deleting all items from DynamoDB table...")
            delete_all_items_from_table(table_old)

            logging.debug("Writing new items to DynamoDB table...")
            with table_old.batch_writer() as batch:
                for item in items_with_gcal_id:
                    logging.debug(f"Writing item to table: {item}")
                    batch.put_item(Item=item)

    except Exception as e:
        logging.error(f"An error occurred while updating calendar events: {e}")

def get_all_items_from_table(table_old):
    response = table_old.scan()  
    return response['Items']

def delete_event_from_google_calendar(service, event_id):
    if event_id == 'none':
        return
    try:
        service.events().delete(calendarId=cal_id, eventId=event_id).execute()
    except HttpError as e:
        if "Resource has been deleted" in str(e):
            logging.warning(f"Attempted to delete an event that has already been deleted: {event_id}")
            # Remove the event from the DynamoDB table
            table_old.delete_item(Key={'id': event_id})
        else:
            raise

def add_event_to_google_calendar(service, start_time, end_time):
    try:
        logging.debug(f"Adding event with start time {start_time} and end time {end_time}")

        event = {
            'summary': 'Good Astro Weather',
            'start': {
                'dateTime': datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S%z').isoformat(),
                'timeZone': 'America/Los_Angeles',
            },
            'end': {
                'dateTime': datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S%z').isoformat(),
                'timeZone': 'America/Los_Angeles',
            },
        }

        logging.debug(f"Event details: {event}")

        event = service.events().insert(calendarId=cal_id, body=event).execute()

        logging.debug(f"Response from Google Calendar API: {event}")

        return event['id']
    except Exception as e:
        logging.error(f"An error occurred while adding the event: {e}")
        return None

def delete_all_items_from_table(table):
    response = table.scan()

    with table.batch_writer() as batch:
        for item in response['Items']:
            batch.delete_item(Key={'uuid': item['uuid']})

def update_item_in_table(table, times, uuid, gCalID):
    table.update_item(
        Key={
            'uuid': uuid,
            'times': times
        },
        UpdateExpression='SET gCalID = :val1',
        ExpressionAttributeValues={
            ':val1': gCalID
        }
    )

def lambda_handler(event, context):
  logging.info('Lambda function started')
  try: get_forecast()
  except Exception as e:
    logging.error(f"An error occurred while getting the forecast: {e}")
    return
  start_time = datetime.fromisoformat(json_object["LocalStartTime"])

  #we only consider the seeing "Good" if it's 2 or higher
  good_seeing_offsets = [offset['HourOffset'] for offset in json_object['Astrospheric_Seeing'] if offset['Value']['ActualValue'] >= 2]
  #we only consider the transparency "Good" if it's 23 or lower
  good_seeing_transparency_offsets = [offset for offset in good_seeing_offsets if json_object['Astrospheric_Transparency'][offset]['Value']['ActualValue'] <= 23]
  #we only consider the clouds "Good" if it's 30 or lower (representing 30% cloud cover)
  good_seeing_transparency_clouds_offsets = [offset for offset in good_seeing_transparency_offsets if json_object['RDPS_CloudCover'][offset]['Value']['ActualValue'] <= 30]

  final_good_offsets = []
  for offset in good_seeing_transparency_clouds_offsets:
    offset_time = start_time + timedelta(hours=offset)
    offset_date = offset_time.date()
    night_time = sun(city.observer, date=offset_date, tzinfo=city.timezone)
    dusk = night_time['dusk']
    dawn_time = sun(city.observer, date=(offset_date + timedelta(days=1)), tzinfo=city.timezone)
    dawn = dawn_time['dawn']  
    if (time_in_range(dusk, dawn, time_zone.localize(offset_time))):
      final_good_offsets.append(offset)

  print(final_good_offsets)
  for k, g in groupby(enumerate(final_good_offsets), lambda ix: ix[0] - ix[1]):
      temp_list = list(map(itemgetter(1), g))
      print(f"Group: {temp_list}")  # print the current group of offsets
      if len(temp_list) > 2:
          event_start = (start_time + timedelta(hours=temp_list[0])).replace(tzinfo=time_zone)
          event_end = (start_time + timedelta(hours=temp_list[-1])).replace(tzinfo=time_zone)
          print(f"Event start: {event_start}, Event end: {event_end}")  # print the start and end times of the event
          # adjust event start and end times to be within the range of dawn and dusk
          dusk = sun(city.observer, date=event_start.date(), tzinfo=city.timezone)['dusk']
          dawn = sun(city.observer, date=(event_end.date() + timedelta(days=1)), tzinfo=city.timezone)['dawn']
          event_start = max(event_start, dusk.replace(tzinfo=time_zone))
          event_end = min(event_end, dawn.replace(tzinfo=time_zone))
          print(f"Adjusted event start: {event_start}, Adjusted event end: {event_end}")  # print the adjusted start and end times
          # check if the event duration is at least 2 hours
          if event_end - event_start >= timedelta(hours=2):
              event = {
                  'id': str(uuid.uuid4()),  # Add a unique ID to each event
                  'start': event_start,
                  'end': event_end,
                  'times': f"{event_start} - {event_end}"
              }
              print(f"Event: {event}")  # print the event
              # check if event already exists in the list
              if not event_exists(events, event):
                  events.append(event)
                  print(f"Event added: {event}")  # print the event that was added
              else:
                  print(f"Event already exists: {event}")  # print if the event already exists
          else:
              print(f"Event duration is less than 2 hours: {event_end - event_start}")  # print if the event duration is less than 2 hours
      else:
          print(f"Group length is less than 2: {len(temp_list)}")  # print if the group length is less than 2

  # populate "new" table in database
  print("Events:\n")
  print(events)
  populate_table(events)
  google_oauth_client_id, google_oauth_secret_id = get_google_oauth_credentials_from_secrets_manager()
  service = build('calendar', 'v3', credentials=credentials)
  update_calendar_events(service)
  logging.info('Lambda function completed')

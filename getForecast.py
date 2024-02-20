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

logger = logging.getLogger()
logger.setLevel(logging.INFO)

API_URL="https://astrosphericpublicaccess.azurewebsites.net/api/GetForecastData_V1"
LAT = os.environ.get('LAT')
LONG = os.environ.get('LONG')
MY_CITY = os.environ.get('CITY')
MY_STATE = os.environ.get('STATE')
MY_TIMEZONE = os.environ.get('TIMEZONE')
json_object = json.loads('{}') 

time_zone = timezone(MY_TIMEZONE)

def get_forecast():
  global json_object
  get_secret()
  data = {'Latitude': LAT, 'Longitude': LONG, 'APIKey': API_KEY}
  headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}

  response = requests.post(API_URL, data=json.dumps(data), headers=headers)
  
  json_object = response.json()

good_seeing_offsets=[]
good_seeing_transparency_offsets=[]
good_seeing_transparency_clouds_offsets=[]
final_good_offsets=[]

# Let's set our location for the astral library
city = LocationInfo(MY_CITY, MY_STATE, MY_TIMEZONE, LAT, LONG)
final_city = Location(city)

# note to self: move this stuff elsewhere later
# connect to DynamoDB
dynamodb = boto3.resource('dynamodb')
  
# get the tables
table_new = dynamodb.Table('ap_events_new')

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
    secret_dict = json.loads(secret_string)  # Assuming JSON format
    API_KEY = secret_dict['API_KEY']

def event_exists(events, event):
    for existing_event in events:
        if existing_event['start'] == event['start'] and existing_event['end'] == event['end']:
            return True
    return False

def time_in_range(start, end, current):
    """Returns whether current is in the range [start, end]"""
    return start <= current <= end

def populate_table(events):
  # Write items to the table
  with table_new.batch_writer() as batch:
      for event in events:
          # Convert start and end times to strings and set gCalID to "none"
          times = f"{event['start']} - {event['end']}"
          item = {
              'id': event['id'],  # Use the unique ID as the key
              'times': times,
              'gCalID': 'none'
          }
          batch.put_item(Item=item)

def lambda_handler(event, context):
  logging.info('Lambda function started')
  get_forecast()
  start_time = datetime.fromisoformat(json_object["LocalStartTime"])

  good_seeing_offsets = [offset['HourOffset'] for offset in json_object['Astrospheric_Seeing'] if offset['Value']['ActualValue'] >= 2]

  good_seeing_transparency_offsets = [offset for offset in good_seeing_offsets if json_object['Astrospheric_Transparency'][offset]['Value']['ActualValue'] <= 23]

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

  for k, g in groupby(enumerate(final_good_offsets), lambda ix: ix[0] - ix[1]):
      temp_list = list(map(itemgetter(1), g))
      if len(temp_list) > 2:
          event_start = start_time + timedelta(hours=temp_list[0])
          event_end = start_time + timedelta(hours=temp_list[-1])
          # Adjust event start and end times to be within the range of dawn and dusk
          event_start = max(event_start, dusk)
          event_end = min(event_end, dawn)
          # Check if the event duration is at least 2 hours
          if event_end - event_start >= timedelta(hours=2):
              event = {
                  'id': str(uuid.uuid4()),  # Add a unique ID to each event
                  'start': event_start,
                  'end': event_end
              }
              # Check if event already exists in the list
              if not event_exists(events, event):
                  events.append(event)
  # populate "new" table in database
  populate_table(events)
  logging.info('Lambda function completed')

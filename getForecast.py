import json
import requests
import boto3
import os
import logging
from botocore.exceptions import ClientError
from pytz import timezone
from astral import LocationInfo
from astral.location import Location
from astral.sun import sun
from itertools import groupby
from operator import itemgetter
from datetime import datetime, timedelta

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
  print(json_object)

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

# generate events from the final_good_offsets list
# events should have start and end times
# this will be the basis for our calendar event generation later
# for now we just want something easy to store in the tables/database later
events = []

# get our astrospheric API key from AWS Secrets Manager
# to-do: adapt from the default AWS example code
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

def time_in_range(start, end, current):
    """Returns whether current is in the range [start, end]"""
    return start <= current <= end

# populate_table function to populate the ap_events_new table in the dynamodb database with the events
def populate_table(events):
  # Write items to the table
  with table_new.batch_writer() as batch:
      for event in events:
          # Convert start and end times to strings and set GCalID to "none"
          item = {
              'times': f"{event['start']} - {event['end']}",
              'GCalID': 'none'
          }
          batch.put_item(Item=item)

def lambda_handler(event, context):
  logging.info('Lambda function started')
  get_forecast()
  start_time = datetime.fromisoformat(json_object["LocalStartTime"])

  for offset in json_object['Astrospheric_Seeing']:
    if offset['Value']['ActualValue'] >= 2:
      good_seeing_offsets.append(offset['HourOffset'])

  for offset in good_seeing_offsets:
    transparency = json_object['Astrospheric_Transparency'][offset]
    if transparency['Value']['ActualValue'] <= 23:
      good_seeing_transparency_offsets.append(transparency['HourOffset'])

  for offset in good_seeing_transparency_offsets:
    cloudcover = json_object['RDPS_CloudCover'][offset]
    if cloudcover['Value']['ActualValue'] <= 30:
      good_seeing_transparency_clouds_offsets.append(cloudcover['HourOffset'])

  for offset in good_seeing_transparency_clouds_offsets:
    offset_time = start_time + timedelta(hours=offset)
    offset_date = offset_time.date()
    night_time = sun(city.observer, date=offset_date, tzinfo=final_city.timezone)
    dusk = night_time['dusk']
    dawn_time = sun(city.observer, date=(offset_date + timedelta(days=1)), tzinfo=final_city.timezone)
    dawn = dawn_time['dawn']  
    if (time_in_range(dusk, dawn, time_zone.localize(offset_time))):
      final_good_offsets.append(offset)

  for k, g in groupby(enumerate(final_good_offsets), lambda ix: ix[0] - ix[1]):
    temp_list = list(map(itemgetter(1), g))
    if len(temp_list) > 2:
      event_start = start_time + timedelta(hours=temp_list[0])
      event_end = start_time + timedelta(hours=temp_list[-1])
      event = {
        'start': event_start,
        'end': event_end
      }
      events.append(event)

  # populate "new" table in database
  populate_table(events)
  logging.info('Lambda function completed')

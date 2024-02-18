import json
import requests
import pytz
import boto3
from pytz import timezone
from astral import LocationInfo
from astral.location import Location
from astral.sun import sun
from itertools import groupby
from operator import itemgetter
from datetime import datetime, timedelta

API_KEY="<API_KEY>"

API_URL="https://astrosphericpublicaccess.azurewebsites.net/api/GetForecastData_V1"
LAT="<YOUR_LAT>"
LONG="<YOUR_LONG>"

time_zone = timezone('America/Los_Angeles')

data = {'Latitude': LAT, 'Longitude': LONG, 'APIKey': API_KEY}
headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}

response = requests.post(API_URL, data=json.dumps(data), headers=headers)

json_object = response.json()

good_seeing_offsets=[]
good_seeing_transparency_offsets=[]
good_seeing_transparency_clouds_offsets=[]
final_good_offsets=[]

# Let's set our location for the astral library
city = LocationInfo("<city>", "<state>", "America/Los_Angeles", LAT, LONG)
antioch = Location(city)


start_time = datetime.fromisoformat(json_object["LocalStartTime"])

def time_in_range(start, end, current):
    """Returns whether current is in the range [start, end]"""
    return start <= current <= end


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
  night_time = sun(city.observer, date=offset_date, tzinfo=antioch.timezone)
  dusk = night_time['dusk']
  dawn_time = sun(city.observer, date=(offset_date + timedelta(days=1)), tzinfo=antioch.timezone)
  dawn = dawn_time['dawn']  
  if (time_in_range(dusk, dawn, time_zone.localize(offset_time))):
    final_good_offsets.append(offset)

# generate events from the final_good_offsets list
# events should have start and end times
# this will be the basis for our calendar event generation later
# for now we just want something easy to store in the tables/database later
events = []

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


# note to self: move this stuff elsewhere later
# connect to DynamoDB
dynamodb = boto3.resource('dynamodb')
  
# get the tables
table_new = dynamodb.Table('ap_events_new')
table_old = dynamodb.Table('ap_events_old')
table_changes = dynamodb.Table('ap_events_changes')

# populate the ap_events_new table in the database with the events
def populate_table(events):
  # write events to the table
  with table_new.batch_writer() as batch:
    for event in events:
      batch.put_item(Item=event)

# compare ap_events_new and ap_events_old tables, only comparing the date and time ranges and no other fields
# if there are any differences, output the differences to the ap_events_changes table
# still need to add update/delete flag logic, for when the entire event is gone or just the time range is updated
def compare_tables():
 
  # get the items from the tables
  items_new = table_new.scan()['Items']
  items_old = table_old.scan()['Items']
  
  # compare the items
  for item_new in items_new:
    for item_old in items_old:
      if item_new['start'] == item_old['start'] and item_new['end'] == item_old['end']:
        # the items are the same
        break
    else:
      # the item is not in the old table
      table_changes.put_item(Item=item_new)
  
  for item_old in items_old:
    for item_new in items_new:
      if item_old['start'] == item_new['start'] and item_old['end'] == item_new['end']:
        # the items are the same
        break
    else:
      # the item is not in the new table
      table_changes.put_item(Item=item_old)


# populate "new" table in database
populate_table(events)

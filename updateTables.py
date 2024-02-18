import boto3

# note to self: move this stuff elsewhere later
# connect to DynamoDB
dynamodb = boto3.resource('dynamodb')
  
# get the tables
table_new = dynamodb.Table('ap_events_new')
table_old = dynamodb.Table('ap_events_old')
table_changes = dynamodb.Table('ap_events_changes')

# compare ap_events_new and ap_events_old tables, only comparing the date and time ranges and no other fields
# if there are any differences, output the differences to the ap_events_changes table
# still need to add update/delete flag logic, for when the entire event is gone or just the time range is updated
def compare_tables():
 
  # Get the items from the tables
  items_new = table_new.scan()['Items']
  items_old = table_old.scan()['Items']
  
  # Compare the items
  for item_new in items_new:
    for item_old in items_old:
      if item_new['start'] == item_old['start'] and item_new['end'] == item_old['end']:
        # The items are the same
        break
    else:
      # The item is not in the old table
      table_changes.put_item(Item=item_new)
  
  for item_old in items_old:
    for item_new in items_new:
      if item_old['start'] == item_new['start'] and item_old['end'] == item_new['end']:
        # The items are the same
        break
    else:
      # The item is not in the new table
      table_changes.put_item(Item=item_old)

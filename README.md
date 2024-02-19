# astro-gcal
The Goal:

I got tired of constantly keeping an Astrospheric tab open and checking it all the time to figure out when I might be able to have a night of astrophotography.  So I had the idea of writing a tool to automatically create/delete/update events on my google calendar (based on the metrics I define for acceptable weather) whenever the forecast is right.

This is intended to be run out of AWS, using a series of Lambdas and DynamoDB.  This requires a Pro Astrospheric account in order to get an Astrospheric API key.


Current Status: FULLY WORKING (I think) - but very still in development

Currently we are successfully querying the astrospheric API for the forecast and writing the date/time ranges that meet our predefined requirements to DynamoDB.  getForecast.py is now functionally complete.  We are also now able to create Calendar events in Google Calendar when updateTables.py is run.  This is now technically "functionally complete" but I am very much leaving this listed as still in development until I have time to do some more refactoring, code cleanups, write docs, etc...

TO-DO:
* Add more tests/etc
* Write installation/usage instructions
* See if there's an easier way to do some of this?  This has a LOT of steps involved to get up and running.  Maybe containerize it.  I know this is broadly overengineered :D that was a bit intentional, but now I need to make it packageable.


# Installation Instructions
(VERY in progress)
* Create 2 AWS Lambda functions, called getForecast and updateTables.  Copy the contents of getForecast.py and updateTables.py into their respective functions lambda_function.py file.
* Create Environment Variables in the getForecast Lambda for CITY, STATE, LAT, LONG, and TIMEZONE and populate them accordingly.
* Create an Environment Variable in the updateTables Lambda for googleCalendarID and populate it with the google calendar ID of the google calendar you want to create events on.
* Get your Astrospheric API key and put it into a secret in AWS Secrets Manager called astrosphericAPIKey with the Secret Key set to API_KEY and the Secret Value set to your API Key from Astrospheric.
* Create 2 DynamoDB tables: ap_events_new and ap_events_old (still need to add schema details here).
* Create a State Machine in AWS Step Functions - set it up to use Lambda: Invoke for getForecast and then have that call Lambda:Invoke for updateTables.
* Create a Schedule in Amazon EventBridge Scheduler - set it up to run on a cron schedule every 6 hours (no point updating more often because of Astrospheric-side stuff), and have it run your State Machine
* Make sure everything has the relevant permissions
* Create Google Cloud Service Account, grant it permissions to your calendar, download its credentials.json file.  You can either upload this to run with your updateTables lambda OR you can migrate this into Secrets Manager (which is on my long-term roadmap for this)

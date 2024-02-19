# astro-gcal
The Goal:

I got tired of constantly keeping an Astrospheric tab open and checking it all the time to figure out when I might be able to have a night of astrophotography.  So I had the idea of writing a tool to automatically create/delete/update events on my google calendar (based on the metrics I define for acceptable weather) whenever the forecast is right.

This is intended to be run out of AWS, using a series of Lambdas and DynamoDB.  This requires a Pro Astrospheric account in order to get an Astrospheric API key.


Current Status: NOT FULLY WORKING - still in development

Currently we are successfully querying the astrospheric API for the forecast and writing the date/time ranges that meet our predefined requirements to DynamoDB.  getForecast.py is now functionally complete.  We are also now able to create Calendar events in Google Calendar when updateTables.py is run.  This is now technically "functionally complete" but I am very much leaving this listed as still in development until I have time to do some more refactoring, code cleanups, write docs, etc...

TO-DO:
* Add more tests/etc
* Write installation/usage instructions

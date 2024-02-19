# astro-gcal
The Goal:

I got tired of constantly keeping an Astrospheric tab open and checking it all the time to figure out when I might be able to have a night of astrophotography.  So I had the idea of writing a tool to automatically create/delete/update events on my google calendar (based on the metrics I define for acceptable weather) whenever the forecast is right.

This is intended to be run out of AWS, using a series of Lambdas and DynamoDB.  This requires a Pro Astrospheric account in order to get an Astrospheric API key.


Current Status: NOT FULLY WORKING - still in development

Currently we are successfully querying the astrospheric API for the forecast and writing the date/time ranges that meet our predefined requirements to DynamoDB.  getForecast.py is now functionally complete.

TO-DO:
* Test code for new/old comparison and calendar event changes
* Test GCal integration
* Add more tests/etc
* Write installation/usage instructions

Why havent I finished all this yet?  Well, testing is a bit tricky since the weather for my house is actually quite poor at the moment :D so the API doesnt return any events that meet my criteria within the time window it returns.  So I've gotta wait and then I can test and bugfix further.

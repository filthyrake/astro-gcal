# astro-gcal
The Goal:

I got tired of constantly keeping an Astrospheric tab open and checking it all the time to figure out when I might be able to have a night of astrophotography.  So I had the idea of writing a tool to automatically create/delete/update events on my google calendar (based on the metrics I define for acceptable weather) whenever the forecast is right.

This is intended to be run out of AWS, using a series of Lambdas and DynamoDB.


Current Status: NOT WORKING - still in development

Currently we are successfully querying the astrospheric API for the forecast and hopefully writing date/time ranges that meet our predefined requirements to DynamoDB.

TO-DO:
* Finish code for new/old comparison and generate corrected changes table
* Actual GCal integration
* Move secrets into secret manager

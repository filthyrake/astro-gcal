# astro-gcal
automatically create/manage events on your google calendar based on forecasts from astrospheric
This is intended to be run out of AWS, using a series of Lambdas and a DB of some sort.


Current Status: NOT WORKING - still in development

Currently we are successfully querying the astrospheric API for the forecast and starting to create date/time ranges that meet our predefined requirements.

TO-DO:
Write this stuff to a table
Actual GCal integration

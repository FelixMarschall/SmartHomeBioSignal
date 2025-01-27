# Biothermal Harmony

Connect your smartwatch to HomeAssistant to receive bio-signals such as wrist temperature.

A classifier will then determine whether to activate the heater or air conditioner based on the received data.

## Addon for HomeAssistant

Add this link to HomeAssistant Addons or use the installer:
https://github.com/FelixMarschall/HA_BioSignal_Addon

## Requirements

- Python 3.12 or higher
- Poetry
- HomeAssistant env

## Config

* Get a Homeassistant token and insert it into ``config.yaml`` 
* make sure its reachable under http://homeassistant.local:8123

## Running the App

To run the Dash application, use the following command:

``poetry run python dash_app/src/app``
import logging
from dash import Dash
from dash.dependencies import Input, Output
from flask import Flask, request, jsonify
import dash_bootstrap_components as dbc
from homeassistant_api import Client
import os
import yaml
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SENSOR = 'empty'
THERMOSTAT = 'empty'
received_data = {}

current_directory = os.getcwd()
print(f"Current working directory: {current_directory}")

if os.path.isfile("/data/options.json"):
    with open('/data/options.json', "r") as json_file:
        options_config = json.load(json_file)
        if len(options_config['credential_secret']) >= 10:
            token = options_config['credential_secret']
            logging.info("Token from options.json setted.")
elif os.path.isfile("../config.yaml"):
    with open('../config.yaml', "r") as yaml_file:
        config = yaml.safe_load(yaml_file)
        if len(config['homeassistant_token']) >= 10:
            token = config['homeassistant_token']
            logging.info("Token from config.yaml setted.")

ha_client = Client(
    api_url = 'http://homeassistant.local:8123/api',
    token = token
) 

logger.info(ha_client.check_api_running())

def register_callbacks(app: Dash):
    pass
    # @app.callback(
    #     Output('temperature-display', 'children'),
    #     [Input('thermostat-dropdown', 'value')]
    # )
    # def update_temperature_display(selected_thermostat):
    #     # Logic to get temperature for the selected thermostat
    #     return f"Temperature for {selected_thermostat}"

    # @app.callback(
    #     Output('classifier-values-display', 'children'),
    #     [Input('thermostat-dropdown', 'value')]
    # )
    # def update_classifier_values_display(selected_thermostat):
    #     # Logic to get classifier values for the selected thermostat
    #     return f"Classifier values for {selected_thermostat}"
    
    # @app.callback([Input("sensor_input", "value")])
    # def output_text(value):
    #     logger.info(f"Input value: {value}")
    #     return value

def create_app(app: Dash, server: Flask):
    register_callbacks(app)

    @server.route('/post-route', methods=['POST'])
    def post_route():
        data = request.json
        logger.info(f"Data received: {data}")
        return jsonify({"message": "Data received", "data": data})

    return app
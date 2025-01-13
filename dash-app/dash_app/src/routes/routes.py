import logging
from dash import Dash
from dash.dependencies import Input, Output, State
from flask import Flask, request, jsonify
import dash_bootstrap_components as dbc
from homeassistant_api import Client
import os
import yaml
import json
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

thermostate: str = "empty"
received_data = pd.DataFrame(columns=['hr', 'hrv', 'temp'], index=pd.to_datetime([]))

if os.path.isfile("/data/options.json"):
    with open("/data/options.json", "r") as json_file:
        options_config = json.load(json_file)
        if len(options_config["credential_secret"]) >= 10:
            token = options_config["credential_secret"]
            logging.info("Token from options.json setted.")
elif os.path.isfile("../config.yaml"):
    with open("../config.yaml", "r") as yaml_file:
        config = yaml.safe_load(yaml_file)
        if len(config["homeassistant_token"]) >= 10:
            token = config["homeassistant_token"]
            logging.info("Token from config.yaml setted.")

ha_client = Client(api_url="http://homeassistant.local:8123/api", token=token)


def register_callbacks(app: Dash):
    @app.callback(
        Output("output-div", "children"),
        [Input("submit-val", "n_clicks")],
        [State("thermo_input", "value")],
    )
    def update_output(n_clicks, value):
        if n_clicks is not None:
            # get text from input')
            logger.info(f"Button clicked with input value: {value}")
            ha_client.async_get_entities()
            entity = ha_client.get_entity(entity_id=value)
            logger.info(f"Entity: {entity}")
            thermostate = value
            return f"Input value: {value}"
        return ""

    @app.callback(Output("output-data", "children"), Input("interval", "n_intervals"))
    def update_on_interval(n):
        logger.info(f"received_data: {received_data}")

        return f"Interval fired {n} times, received data: {received_data}"


def create_app(app: Dash, server: Flask):
    register_callbacks(app)

    @server.route("/data", methods=["POST"])
    def post_route():
        data = request.json
        logger.info(f"Data received: {data}")

        global received_data
        # Assuming data contains a timestamp and a value
        timestamp = pd.to_datetime(data['timestamp'])
        new_data = pd.DataFrame(
                                {'hr': [data['hr']],
                                 'hrv': [data['hrv']],
                                 'temp': [data['temp']]},
                                index=[timestamp])
        received_data = pd.concat([received_data, new_data])
        return jsonify({"message": "Data received", "data": data})

    return app

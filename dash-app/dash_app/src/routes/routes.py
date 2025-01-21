import logging
from dash import Dash
from dash.dependencies import Input, Output, State
from flask import Flask, request, jsonify
import dash_bootstrap_components as dbc
from homeassistant_api import Client
import os
import yaml
import json
import datetime
from data_processing.ThermalControlUnit import ThermalControlUnit, UserConfig
from data_processing.PreprocessingUnit import (
    construct_dataset_df,
)
from dash import dash_table
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

thermostate: str = "empty"
received_data = pd.DataFrame(columns=["hr", "hrv", "temp"], index=pd.to_datetime([]))

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

try:
    ha_client = Client(api_url="http://homeassistant.local:8123/api", token=token)
except Exception as e:
    logging.error(f"Error: {e}")
    ha_client = None


def register_callbacks(app: Dash):
    @app.callback(
        Output("output-div", "children"),
        [Input("submit-val", "n_clicks")],
        [State("thermo_input", "value")],
    )
    def update_output(n_clicks, value):
        if n_clicks is not None:
            logger.info(f"Button clicked with input value: {value}")
            ha_client.async_get_entities()
            entity = ha_client.get_entity(entity_id=value)
            logger.info(f"Entity: {entity}")
            thermostate = value
            return f"Input value: {value}"
        return ""

    @app.callback(
        Output("watch-table", "data"),
        Output("watch-graph", "figure"),
        Input("interval", "n_intervals"),
    )
    def update_on_interval(n):

        figure = {
            "data": [
                {
                    "x": received_data.index,
                    "y": received_data["hr"],
                    "type": "line",
                    "name": "HR",
                },
                {
                    "x": received_data.index,
                    "y": received_data["hrv"],
                    "type": "line",
                    "name": "HRV",
                },
                {
                    "x": received_data.index,
                    "y": received_data["temp"],
                    "type": "line",
                    "name": "Body Temperature",
                },
            ],
            "layout": {"title": "Sensor Data Over Time"},
        }

        return (
            received_data.tail(5)
            .reset_index()
            .rename(columns={"index": "ts"})
            .to_dict("records"),
            figure,
        )


def create_app(app: Dash, server: Flask):
    register_callbacks(app)

    data_dir = "data"
    server.config["data_dir"] = data_dir
    os.mkdir(data_dir)

    user_config = UserConfig()
    server.config["thermal_control_unit"] = ThermalControlUnit(
        sensor_data_dir=data_dir, user_config=user_config, logger=logger
    )

    @server.route("/data", methods=["POST"])
    def post_route():
        data = request.json
        logger.info(f"Data received: {data}")
        return jsonify({"message": "Data received", "data": data})

    @server.route("/config/room/temp", methods=["POST"])
    def set_room_temp():
        data = request.json

        if "room_temp" in data:
            room_temp = data["room_temp"]

            server.config["thermal_control_unit"].apply_user_preference(
                float(room_temp)
            )

            return jsonify({"message": "Configured room temperature preference."})

        else:
            return jsonify({"message": "Invalid request. Missing 'room_temp' key."})

    @server.route("/control/thermal", methods=["POST"])
    def control_thermal():
        data = request.json

        if ("sensor_data" in data) and ("user_feedback" in data):
            sensor_data = data["sensor_data"]
            user_feedback = data["user_feedback"]

            # construct dataset
            complete_dataset = construct_dataset_df(sensor_data, user_feedback)

            csv_file_name = datetime.datetime.now().strftime("%Y-%m-%d")
            csv_path = os.path.join(server.config["data_dir"], f"{csv_file_name}.csv")

            if os.path.exists(csv_path):
                complete_dataset.to_csv(csv_path, mode="a", header=False)
            else:
                complete_dataset.to_csv(csv_path)

            # apply decision making process
            actions = server.config["thermal_control_unit"].decision_making()

            return jsonify(
                {"message": f"Thermal Actions applied (off=0, on=1): {actions}"}
            )

        else:
            return jsonify(
                {
                    "message": "Invalid request. Missing 'sensor_data' or 'user_feedback' key."
                }
            )

    @server.route("/control/thermal/cancel", methods=["POST"])
    def cancel_thermal():
        actions = server.config["thermal_control_unit"].rollback_last_decision()

        return jsonify(
            {
                "message": f"Rollback applied. Thermal Actions applied (off=0, on=1): {actions}"
            }
        )

    return app

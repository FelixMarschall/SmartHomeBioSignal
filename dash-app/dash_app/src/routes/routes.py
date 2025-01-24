import logging
from dash import Dash
from dash.dependencies import Input, Output, State
from flask import Flask, request, jsonify
import dash_bootstrap_components as dbc
from homeassistant_api import Client, History
import os
import yaml
import json
from datetime import datetime
from dash_app.src.data_processing.ThermalControlUnit import (
    ThermalControlUnit,
    UserConfig,
)
from dash_app.src.data_processing.PreprocessingUnit import (
    construct_dataset_df,
)
from dash import dash_table
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


### Configure
TEMP_SENSOR: str = "sensor.felix_weather_temperatur"
HUM_SENSOR: str = "sensor.felix_weather_luftfeuchtigkeit"

temp_temp_sensor: pd.DataFrame = None
temp_hum_sensor: pd.DataFrame = None

thermostate: str = "empty"
received_data = pd.DataFrame(columns=["hr", "hrv", "temp"], index=pd.to_datetime([]))

### dummy data, is replaced with real data from Home Assistant in the functions
temperature_data = pd.read_csv("dash_app/src/assets/data/history_temp.csv")
humidity_data = pd.read_csv("dash_app/src/assets/data/history_hum.csv")

### search for homeassistant token in options.json or config.yaml
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
    logger.info("Connecting to Home Assistant API")
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
        Output("smarthome-graph", "figure"),
        Input("interval", "n_intervals"),
    )
    def update_on_interval(n):

        watch_figure = {
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

        if ha_client is not None:
            global temp_hum_sensor, temp_temp_sensor
            if temp_hum_sensor is None:
                history: History = ha_client.get_entity(entity_id=HUM_SENSOR).get_history()
                data = [
                    {
                        "entity_id": state.entity_id,
                        "last_updated": state.last_updated,
                        "state": state.state,
                    }
                    for state in history.states
                ]
                df = pd.DataFrame(data)
                temp_hum_sensor = df
                temp_hum_sensor["last_updated"] = pd.to_datetime(df["last_updated"])
                temp_hum_sensor = df.set_index("last_updated")
            if temp_temp_sensor is None:
                history: History = ha_client.get_entity(entity_id=TEMP_SENSOR).get_history()
                data = [
                    {
                        "entity_id": state.entity_id,
                        "last_updated": state.last_updated,
                        "state": state.state,
                    }
                    for state in history.states
                ]
                df = pd.DataFrame(data)
                temp_temp_sensor = df
                temp_temp_sensor["last_updated"] = pd.to_datetime(df["last_updated"])
                temp_temp_sensor = df.set_index("last_updated")

        smarthome_figure = {
            "data": [
                {
                    "x": temp_temp_sensor.index,
                    "y": temp_temp_sensor["state"],
                    "type": "line",
                    "name": "Room Temperature (°C)",	
                },
                {
                    "x": temp_hum_sensor.index,
                    "y": temp_hum_sensor["state"],
                    "type": "line",
                    "name": "Room Humidity (%)",
                }
            ],
            "layout": {"title": "Smart Home Sensor Data Over Time"},
        }

        return (
            received_data.tail(5)
            .reset_index()
            .rename(columns={"index": "ts"})
            .to_dict("records"),
            watch_figure,
            smarthome_figure,
        )


def create_app(app: Dash, server: Flask):
    register_callbacks(app)

    app_base_dir = "dash_app/src/assets"
    data_dir = os.path.join(app_base_dir, "data")
    server.config["data_dir"] = data_dir

    if not os.path.exists(data_dir):
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

            csv_file_name = datetime.now().strftime("%Y-%m-%d")
            csv_path = os.path.join(server.config["data_dir"], f"{csv_file_name}.csv")

            if os.path.exists(csv_path):
                complete_dataset.to_csv(csv_path, mode="a", header=False, index=False)
            else:
                complete_dataset.to_csv(csv_path, index=False)

            # apply decision making process
            actions = server.config["thermal_control_unit"].decision_making()
            logger.info("Decision made")

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

    @server.route("/sensor/temperature", methods=["GET"])
    def get_temperature():
        if ha_client is not None:
            history: History = ha_client.get_entity(entity_id=TEMP_SENSOR).get_history()
            data = [
                {
                    "entity_id": state.entity_id,
                    "last_updated": state.last_updated,
                    "state": state.state,
                }
                for state in history.states
            ]
            df = pd.DataFrame(data)
            global temp_temp_sensor
            temp_temp_sensor = df
            temp_temp_sensor["last_updated"] = pd.to_datetime(df["last_updated"])
            temp_temp_sensor = df.set_index("last_updated")

            return df.to_json()
        # dummy data
        today = datetime.today()
        temperature_data["last_changed"] = pd.to_datetime(
            temperature_data["last_changed"]
        )
        temperature_data["last_changed"] = temperature_data["last_changed"].apply(
            lambda x: x.replace(year=today.year, month=today.month, day=today.day)
        )
        temperature_data["last_changed"] = temperature_data["last_changed"].dt.strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        return temperature_data.to_json()

    @server.route("/sensor/humidity", methods=["GET"])
    def get_humidity():
        if ha_client is not None:
            history: History = ha_client.get_entity(entity_id=HUM_SENSOR).get_history()
            data = [
                {
                    "entity_id": state.entity_id,
                    "last_updated": state.last_updated,
                    "state": state.state,
                }
                for state in history.states
            ]
            df = pd.DataFrame(data)
            global temp_hum_sensor
            temp_hum_sensor = df
            temp_hum_sensor["last_updated"] = pd.to_datetime(df["last_updated"])
            temp_hum_sensor = df.set_index("last_updated")

            return df.to_json()

        # dummy data
        today = datetime.today()
        humidity_data["last_changed"] = pd.to_datetime(humidity_data["last_changed"])
        humidity_data["last_changed"] = humidity_data["last_changed"].apply(
            lambda x: x.replace(year=today.year, month=today.month, day=today.day)
        )
        humidity_data["last_changed"] = humidity_data["last_changed"].dt.strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        return humidity_data.to_json()

    return app

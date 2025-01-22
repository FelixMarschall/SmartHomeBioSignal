import pandas as pd
import joblib
from dateutil import parser
import requests
from typing import Union, Dict
import io
import os
import logging


def construct_watch_sensor_data_df(data_dict: Dict) -> pd.DataFrame:
    wearable_df = pd.DataFrame(data_dict)

    wearable_df["timestamp"] = pd.to_datetime(
        wearable_df["timestamp"]
        .apply(parser.parse)
        .apply(lambda x: x.strftime("%Y-%m-%d- %H:%M:%S"))
    )

    wearable_clip_values = {
        "wrist_temp_in_celsius": (14, 43),
        "heart_rate_in_bpm": (40, 210),
    }

    for column, (min_val, max_val) in wearable_clip_values.items():
        wearable_df[column] = wearable_df[column].clip(lower=min_val, upper=max_val)

    wearable_df.insert(
        len(wearable_df.columns) - 1,
        "ibi_in_ms",
        60_000 / wearable_df["heart_rate_in_bpm"],
    )

    wearable_df.set_index("timestamp", inplace=True)

    wearable_mean_5s_df = wearable_df.resample("5s").mean()
    wearable_std_5s_df = wearable_df.resample("5s").std()

    # assign most frequent label to the 5s window
    wearable_resampled_df = wearable_mean_5s_df.copy()

    # create the hrv sdnn feature
    wearable_resampled_df["sdnn_in_ms"] = wearable_std_5s_df["ibi_in_ms"]

    wearable_resampled_df.reset_index(inplace=True)

    return wearable_resampled_df


def construct_smarthome_sensor_data_df() -> pd.DataFrame:
    logging.info("Fetching sensor data...")
    humidity_sensor_endpoint = "http://localhost:8050/sensor/humidity"
    humidity_df = get_sensor_last_changed_df(
        humidity_sensor_endpoint, "room_humidity_in_pct"
    )

    logging.info("Fetching temperature sensor data...")
    temperature_sensor_endpoint = "http://localhost:8050/sensor/temperature"
    temperature_df = get_sensor_last_changed_df(
        temperature_sensor_endpoint, "room_temp_in_celsius"
    )

    logging.info("Merging sensor data...")
    smarthome_sensor_df = pd.merge(humidity_df, temperature_df, on="timestamp")

    logging.info("Sensor data merged.")
    logging.info("Preprocessing sensor data...")
    sensor_clip_values = {
        "room_temp_in_celsius": (10, 45),
        "room_humidity_in_pct": (0, 100),
    }
    for column, (min_val, max_val) in sensor_clip_values.items():
        smarthome_sensor_df[column] = smarthome_sensor_df[column].clip(
            lower=min_val, upper=max_val
        )
    logging.info("Sensor data preprocessed.")
    return smarthome_sensor_df


def get_sensor_last_changed_df(endpoint: str, column_name: str):
    response = requests.get(endpoint)
    df = pd.read_json(io.StringIO(response.text))
    print("df head", df.head())

    df["last_changed"] = pd.to_datetime(
        df["last_changed"]
        .apply(parser.parse)
        .apply(lambda x: x.strftime("%Y-%m-%d- %H:%M:%S"))
    )

    # timestamp col needs to be index to use resample
    df.set_index("last_changed", inplace=True)
    resampled_df = df.resample("5s").ffill()

    # retrieve last_changed column
    resampled_df.reset_index(inplace=True)
    resampled_df.drop(columns=["entity_id"], inplace=True)

    resampled_df.rename(
        columns={"last_changed": "timestamp", "state": column_name}, inplace=True
    )

    return resampled_df


def construct_dataset_df(sensor_data: Dict, user_feedback: Union[int, None] = None):
    # preprocess watch data
    logging.info("Constructing watch data...")

    watch_df = construct_watch_sensor_data_df(data_dict=sensor_data)

    # print("watch_df", watch_df.head())

    logging.info("Watch data constructed.")
    logging.info("Constructing smarthome data...")
    smarthome_df = construct_smarthome_sensor_data_df()

    print("smarthome_df", smarthome_df.head())

    # merge sensor data
    logging.info("Merging sensor data...")
    complete_dataset = pd.merge(watch_df, smarthome_df, on="timestamp")
    
    logging.info("Sensor data merged.")
    print("complete_dataset", complete_dataset.head())

    # feature engineering
    complete_dataset["wrist_room_temp_delta_in_celsius"] = (
        complete_dataset["wrist_temp_in_celsius"]
        - complete_dataset["room_temp_in_celsius"]
    )

    # sort columns
    complete_dataset = complete_dataset.reindex(
        columns=[
            "wrist_temp_in_celsius",
            "room_temp_in_celsius",
            "wrist_room_temp_delta_in_celsius",
            "room_humidity_in_pct",
            "heart_rate_in_bpm",
            "ibi_in_ms",
            "sdnn_in_ms",
            "timestamp",
        ]
    )

    dataset_no_timestamp = complete_dataset.drop(columns=["timestamp"])

    # check if file exists
    logging.info("Loading model...")
    model_path = "dash_app/src/assets/model/adaboost_deploy_v1.joblib"
    if not os.path.exists(model_path):
        raise FileNotFoundError("Model file not found. Please check the model path.")

    model = joblib.load(model_path)
    prediction = model.predict(dataset_no_timestamp)

    complete_dataset["classifier_prediction"] = prediction
    complete_dataset["heat"] = float("nan")
    complete_dataset["cool"] = float("nan")
    complete_dataset["humidify"] = float("nan")
    complete_dataset["dry"] = float("nan")
    complete_dataset["user_feedback"] = float("nan")
    complete_dataset.at[complete_dataset.index[-1], "user_feedback"] = user_feedback

import math
import datetime
from pydantic import BaseModel
from typing import Union
import pandas as pd
import numpy as np
from logging import Logger


class UserConfig(BaseModel):
    optimal_room_temp_celsius: float
    rollback_optimal_room_temp_celsius: Union[float, None] = None
    has_user_set_optimal_room_temp: bool = False
    last_feedback: Union[int, None] = 0

    def __init__(self, **data):
        super().__init__(**data)
        self.optimal_room_temp_celsius = self.get_season_based_room_temp()

    def get_season_based_room_temp(self):
        month = datetime.datetime.now().month

        if month in [3, 4, 5]:
            season = "spring"
        elif month in [6, 7, 8]:
            season = "summer"
        elif month in [9, 10, 11]:
            season = "autumn"
        else:
            season = "winter"

        SEASON_OPTIMAL_TEMPERATURES_CELSIUS = {
            "spring": 21.0,
            "summer": 20.0,
            "autumn": 21.0,
            "winter": 22.0,
        }

        return SEASON_OPTIMAL_TEMPERATURES_CELSIUS[season]

    def update_optimal_room_temp(self, new_temp: Union[float, None] = None) -> None:
        if new_temp:
            # persist previous optimal room temp for potential rollback
            self.rollback_optimal_room_temp_celsius = self.optimal_room_temp_celsius

            # apply new optimal room temp
            self.optimal_room_temp_celsius = new_temp
            self.has_user_set_optimal_room_temp = True

            return None

        if not self.has_user_set_optimal_room_temp:
            self.optimal_room_temp_celsius = self.get_season_based_room_temp()


class ThermalControlUnit:

    MIN_ROOM_TEMP = 18.0
    MAX_ROOM_TEMP = 26.0
    MIN_SKIN_TEMP = 30.0
    MAX_SKIN_TEMP = 38.0
    MIN_HUMIDITY = 20.0
    MAX_HUMIDITY = 80.0

    def __init__(
        self,
        sensor_data_dir: str,
        user_config: UserConfig,
        include_last_x_hours: int = 8,
        logger: Union[Logger, None] = None,
    ):
        self.sensor_data_dir = sensor_data_dir
        self.sensor_df = self.get_sensor_data()

        self.include_last_x_hours = include_last_x_hours
        self.user_config = user_config

        if logger:
            self.logger = logger
        else:
            self.logger = Logger("ThermalControlUnit", level="INFO")

        self.room_temp_range = np.arange(
            ThermalControlUnit.MIN_ROOM_TEMP,
            ThermalControlUnit.MAX_ROOM_TEMP + 0.01,
            0.01,
        )

    def apply_user_preference(self, room_temp: float) -> None:
        self.user_config.update_optimal_room_temp(new_temp=room_temp)

    def decision_making(self) -> dict[str, int]:
        # fetch new data
        self.update_sensor_data_cache()

        latest_measurement = self.sensor_df.iloc[-1]

        # high level decision making
        high_level_actions = self.high_level_decision_making(latest_measurement)

        self.logger.info(f"Proposed high level actions: {high_level_actions}")

        # check low level decision making process for heat/cooling potential
        current_actions = high_level_actions
        if high_level_actions["heat"] == 0 and high_level_actions["cool"] == 0:
            low_level_actions = self.low_level_decision_making()

            self.logger.info(f"Proposed low level actions: {low_level_actions}")

            # update current actions with low level actions
            current_actions["cool"] = low_level_actions["cool"]
            current_actions["heat"] = low_level_actions["heat"]

        # find latest decisions to compare
        decision_df = self.sensor_df.loc[
            :,
            [
                "timestamp",
                "room_temp_in_celsius",
                "room_humidity_in_pct",
                "heat",
                "cool",
                "humidify",
                "dry",
            ],
        ]
        decision_df = decision_df.dropna()

        # prevent contradiction of old decisions within reasonable decision timeframe
        if not decision_df.empty:
            last_decision = decision_df.iloc[-1]
            current_actions = self.overwrite_contradicting_actions(
                current_actions, last_decision
            )

            self.rollback_decision = last_decision.iloc[:, 1:]

        # apply actions
        self.apply_actions(
            latest_record=self.sensor_df.iloc[-1], actions=current_actions
        )

        # persist which actions were applied to easily revert them if cancelled by user
        self.applied_decision = self.sensor_df.loc[
            -1, ["room_temp_in_celsius", "room_humidity_in_pct"]
        ]
        for column in current_actions.keys():
            self.applied_decision[column] = current_actions[column]

        # write actions to csv
        self.persist_actions(current_actions)

        return current_actions

    def rollback_last_decision(self) -> dict[str, int]:
        # use the decision before the last one to roll back changes
        current_actions = self.rollback_decision[
            ["heat", "cool", "humidify", "dry"]
        ].to_dict()
        self.apply_actions(
            latest_record=self.rollback_decision, actions=current_actions
        )

        # update latest applied decision
        self.applied_decision = self.rollback_decision

        # rollback to previous optimal room temp
        self.user_config.update_optimal_room_temp(
            new_temp=self.user_config.rollback_optimal_room_temp_celsius
        )

        # write actions to csv
        self.persist_actions(current_actions)

        return current_actions

    def update_sensor_data_cache(self) -> None:
        # filter df for today's newer data
        today_sensor_df = self.get_sensor_data(yesterday=False)
        old_sensor_df_latest_timestamp = max(self.sensor_df["timestamp"])

        today_sensor_df = today_sensor_df[
            today_sensor_df["timestamp"] > old_sensor_df_latest_timestamp
        ]

        list_of_dfs_to_combine = [self.sensor_df, today_sensor_df]

        # if the day is not the same between new df and old df we need to include yesterday's data
        current_timestamp = datetime.datetime.now()
        if current_timestamp.day != old_sensor_df_latest_timestamp.day:
            yesterday_sensor_df = self.get_sensor_data(yesterday=True)
            yesterday_sensor_df = yesterday_sensor_df[
                yesterday_sensor_df["timestamp"] > old_sensor_df_latest_timestamp
            ]

            list_of_dfs_to_combine.append(yesterday_sensor_df)

        # combine all dfs
        new_sensor_df = pd.concat(list_of_dfs_to_combine)

        # filter for last x hours of data
        latest_timestamp = max(new_sensor_df["timestamp"])
        cutoff_timestamp = latest_timestamp - datetime.timedelta(
            hours=self.include_last_x_hours
        )
        new_sensor_df = new_sensor_df[new_sensor_df["timestamp"] > cutoff_timestamp]

        # sort by ascending timestamp
        new_sensor_df = new_sensor_df.sort_values(by="timestamp", ascending=True)

        # Update: sensor data
        self.sensor_df = new_sensor_df

        # Update: time based user config params
        self.user_config.update_optimal_room_temp()

    def get_sensor_data(self, yesterday=False):
        df = pd.read_csv(self.get_csv_file_path(yesterday=yesterday))

        df["timestamp"] = pd.to_datetime(df["timestamp"])

        return df

    def get_csv_file_path(self, yesterday=False) -> str:
        date = self.__get_date(yesterday)
        csv_file_path = f"{self.sensor_data_dir}/{date}.csv"

        return csv_file_path

    def __get_date(self, yesterday: bool) -> str:
        date = datetime.datetime.now()

        if yesterday:
            date = datetime.datetime.now() - datetime.timedelta(days=1)

        return date.strftime("%Y-%m-%d")

    # --- Decision Making: Validate value range integrity as a first quick check
    def high_level_decision_making(
        self, latest_measurement: pd.Series
    ) -> dict[str, int]:
        """Takes a high level look at the features & where they land in the value ranges"""
        actions = {
            "heat": 0,
            "cool": 0,
            "humidify": 0,
            "dry": 0,
        }

        room_temp_action = self.check_room_temperature(latest_measurement)
        skin_temp_action = self.check_skin_temperature(latest_measurement)
        room_humidity_action = self.check_room_humidity(latest_measurement)

        # Cooling
        if (room_temp_action == "cool" and skin_temp_action != "heat") or (
            room_temp_action != "heat" and skin_temp_action == "cool"
        ):
            actions["cool"] = 1
        # Heating
        elif (room_temp_action == "heat" and skin_temp_action != "cool") or (
            room_temp_action != "cool" and skin_temp_action == "heat"
        ):
            actions["heat"] = 1

        # Humidity
        if room_humidity_action:
            actions[room_humidity_action] = 1

        return actions

    def check_room_temperature(self, latest_measurement: pd.Series) -> Union[str, None]:
        proposed_action = None
        if (
            latest_measurement["room_temp_in_celsius"]
            < ThermalControlUnit.MIN_ROOM_TEMP
        ):
            proposed_action = "heat"
        elif (
            latest_measurement["room_temp_in_celsius"]
            > ThermalControlUnit.MAX_ROOM_TEMP
        ):
            proposed_action = "cool"

        return proposed_action

    def check_skin_temperature(self, latest_measurement: pd.Series) -> Union[str, None]:
        proposed_action = None
        if (
            latest_measurement["wrist_temp_in_celsius"]
            < ThermalControlUnit.MIN_SKIN_TEMP
        ):
            proposed_action = "heat"
        elif (
            latest_measurement["wrist_temp_in_celsius"]
            > ThermalControlUnit.MAX_SKIN_TEMP
        ):
            proposed_action = "cool"

        return proposed_action

    def check_room_humidity(self, latest_measurement: pd.Series) -> Union[str, None]:
        proposed_action = None
        if latest_measurement["room_humidity_in_pct"] < ThermalControlUnit.MIN_HUMIDITY:
            proposed_action = "humidify"
        elif (
            latest_measurement["room_humidity_in_pct"] > ThermalControlUnit.MAX_HUMIDITY
        ):
            proposed_action = "dry"

        return proposed_action

    # --- Decision Making: Temperature features & comfort zones to determine actions & action parameters
    def low_level_decision_making(self) -> dict[str, int]:
        actions = {
            "heat": 0,
            "cool": 0,
            "humidify": 0,
            "dry": 0,
        }

        # pick most common classifier prediction over a lag of the last 12 measurements (=1 min)
        CLASSIFIER_LAG_WINDOW = 12
        most_common_classifier_prediction = self.sensor_df.loc[
            -CLASSIFIER_LAG_WINDOW:, ["classifier_prediction"]
        ].mode()[0]

        latest_record = self.sensor_df.iloc[-1]
        if pd.notnull(latest_record["user_feedback"]):
            user_feedback = latest_record["user_feedback"]
        else:
            user_feedback = None

        # No user feedback = action only based on classifier
        if user_feedback is None:
            self.shift_optimal_room_temperature(zone=most_common_classifier_prediction)

            if most_common_classifier_prediction == 1:
                actions["cool"] = 1

            elif most_common_classifier_prediction == -1:
                actions["heat"] = 1

        # User feedback: it's warm
        elif (
            # it's hot
            (user_feedback == 2)
            # user feedback agrees with classifier for slight change
            or (user_feedback == 1 and most_common_classifier_prediction == 1)
            # user feedback does not contradict the previous action
            or (user_feedback == 1 and self.last_feedback in [1, 0, None])
        ):
            self.shift_optimal_room_temperature(user_feedback)

            actions["cool"] = 1

        # User feedback: it's cool
        elif (
            # it's cold
            (user_feedback == -2)
            # user feedback agrees with classifier for slight change
            or (user_feedback == -1 and most_common_classifier_prediction == -1)
            # user feedback does not contradict the previous action
            or (user_feedback == -1 and self.last_feedback in [-1, 0, None])
        ):
            self.shift_optimal_room_temperature(user_feedback)

            actions["heat"] = 1

        self.last_feedback = user_feedback

        return actions

    def shift_optimal_room_temperature(self, zone: int):
        # if the input zone is 2 (= hot) we need to shift the base temperature
        # to the left (= -2) to recalibrate the range
        input_zone_to_target_zone_range = {
            -2: (2.0, 3.0),
            -1: (1.0, 2.0),
            0: (-1.0, 1.0),
            1: (-2.0, -1.0),
            2: (-3.0, -2.0),
        }
        target_zone_ashrae_range = input_zone_to_target_zone_range.get(zone)

        target_zone_temperature_range = [
            temp
            for temp in self.room_temp_range
            if target_zone_ashrae_range[0]
            <= self.calculate_ashrae_value(temp)
            <= target_zone_ashrae_range[1]
        ]

        # range can be empty, if one zone would completely fall outside of the min/max temp range
        #  of the room temp
        new_optimal_room_temp = None
        if target_zone_temperature_range:
            new_optimal_room_temp = (
                target_zone_temperature_range[0] + target_zone_temperature_range[-1]
            ) / 2

            self.user_config.update_optimal_room_temp(new_temp=new_optimal_room_temp)

    def calculate_ashrae_value(self, measured_room_temperature: float) -> int:
        return int(
            3
            * (
                (
                    2
                    / (
                        1
                        + math.exp(
                            -1
                            * (
                                measured_room_temperature
                                - self.user_config.optimal_room_temp_celsius
                            )
                        )
                    )
                )
                - 1
            )
        )

    # --- Decision Making: Logical Error Correction
    def overwrite_contradicting_actions(self, current_actions, last_decision):
        BLOCK_CONTRADICTORY_ACTIONS_FOR_X_MINS = 30

        # reset current actions to neutral action if it opposes a previous decision within a short timeframe
        current_datetime = datetime.datetime.now()
        earliest_timestamp_for_change = current_datetime - datetime.timedelta(
            minutes=BLOCK_CONTRADICTORY_ACTIONS_FOR_X_MINS
        )

        # Heat / Cool contradiction prevention
        if (
            (last_decision["heat"] == 1)
            and (current_actions["cool"] == 1)
            and (last_decision["timestamp"] > earliest_timestamp_for_change)
        ):
            current_actions["cool"] = 0
        elif (
            (last_decision["cool"] == 1)
            and (current_actions["heat"] == 1)
            and (last_decision["timestamp"] > earliest_timestamp_for_change)
        ):
            current_actions["heat"] = 0

        # Humidify / Dry contradiction prevention
        if (
            (last_decision["humidify"] == 1)
            and (current_actions["dry"] == 1)
            and (last_decision["timestamp"] > earliest_timestamp_for_change)
        ):
            current_actions["dry"] = 0
        elif (
            (last_decision["dry"] == 1)
            and (current_actions["humidify"] == 1)
            and (last_decision["timestamp"] > earliest_timestamp_for_change)
        ):
            current_actions["humidify"] = 0

        return current_actions

    # --- Smart Home Integration
    def apply_actions(self, latest_record: pd.Series, actions: dict[str, int]) -> None:
        # Temperature Control
        if actions["heat"] == 1:
            self.trigger_heater(latest_record)
        elif actions["cool"] == 1:
            self.trigger_cooler(latest_record)

        # Humidity Control
        if actions["humidify"] == 1:
            self.trigger_humidifier(latest_record)
        elif actions["dry"] == 1:
            self.trigger_window_opener(latest_record)

    def trigger_heater(self, latest_record: pd.Series) -> None:
        self.logger.info("Heating...")
        # TODO: implement heater control with corresponding smarthome API call
        # use self.user_config.optimal_room_temp_celsius as target temperature

    def trigger_cooler(self, latest_record: pd.Series) -> None:
        self.logger.info("Cooling...")
        # TODO: implement cooler control with corresponding smarthome API call
        # use self.user_config.optimal_room_temp_celsius as target temperature

    def trigger_humidifier(self, latest_record: pd.Series) -> None:
        self.logger.info("Humidifying...")
        # TODO: implement humidifier control with corresponding smarthome API call

    def trigger_window_opener(self, latest_record: pd.Series) -> None:
        self.logger.info("Opening window...")
        # TODO: implement window opener control with corresponding smarthome API call

    # --- Data Management
    def persist_actions(self, actions: dict[str, int]):
        current_df = self.get_sensor_data()

        for action, value in actions.items():
            current_df.at[current_df.index[-1], action] = value

        current_df.to_csv(self.get_csv_file_path(), index=False)


# Test cases
def main():
    sensor_data_dir = "data/sensor_data"
    user_config = UserConfig()

    tcu = ThermalControlUnit(sensor_data_dir=sensor_data_dir, user_config=user_config)

    tcu.decision_making()

    # TODO: add simulation for different cases


if __name__ == "__main__":
    main()

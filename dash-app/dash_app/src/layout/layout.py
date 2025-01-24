from dash import html, dcc, Dash
import dash_bootstrap_components as dbc
from dash import dash_table
import plotly.express as px


df = px.data.iris()  # iris is a pandas DataFrame
fig = px.scatter(df, x="sepal_width", y="sepal_length")


def create_layout(dash: Dash):
    return dbc.Container(
        [
            dbc.Row(
                dbc.Col(
                    [
                        dcc.Interval(id="interval", interval=3000),  # 5 seconds
                        html.Img(
                            src=dash.get_asset_url("logo.png"), style={"width": "200px"}
                        ),
                        html.H1(
                            "BioThermal Harmony",
                            className="text-center",
                            style={"margin-top": "50px"},
                        ),
                        # dbc.Col(
                        #     [
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.H4("Overview", className="card-title"),
                                    html.P(
                                        "This application allows you to monitor and control the temperature "
                                        "of various thermostats and sensors. You can select a thermostat entity "
                                        "and a sensor entity to view the current temperature and classifier values.",
                                        className="card-text",
                                    ),
                                ]
                            ),
                            className="mb-4",
                        ),
                        dbc.Row(
                            [
                                dbc.Col(
                                    html.H4(
                                        "Select Thermostate Entity:",
                                        className="text-center",
                                    ),
                                    width=4,
                                ),
                                dbc.Col(
                                    dbc.Input(
                                        id="thermo_input",
                                        placeholder="Type name id of thermostate...",
                                        type="text",
                                    ),
                                    width=3,
                                ),
                                dbc.Col(
                                    dbc.Button(
                                        "Submit",
                                        id="submit-val",
                                        color="primary",
                                    ),
                                    width=3,
                                ),
                                html.Div(id="output-div"),
                                html.Div(id="output-data"),

                            ],
                            justify="center",
                            # align="center",
                            style={"margin-bottom": "20px"},
                        ),
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.H4("Watch Data", className="card-title"),
                                    dash_table.DataTable(
                                        id="watch-table",
                                        columns=[
                                            {"name": "ts", "id": "ts"},
                                            {"name": "HR", "id": "hr"},
                                            {"name": "HRV", "id": "hrv"},
                                            {
                                                "name": "Body Temperature",
                                                "id": "temp",
                                            },
                                        ],
                                        style_table={
                                            "width": "50%",
                                            "margin": "0 auto",
                                        },
                                        style_cell={
                                            "fontSize": "14px",
                                            "textAlign": "center",
                                        },
                                    ),
                                    dcc.Graph(id="watch-graph"),
                                    html.H4("Smart Home Data", className="card-title"),
                                    dcc.Graph(id="smarthome-graph"),
                                ]

                            ),
                            className="mb-2",
                        ),
                        #     ],
                        #     width=6,
                        # ),
                        dbc.Card(
                            dbc.CardBody(
                                [
                                    html.H4("Classifier", className="card-title"),
                                    dcc.Graph(figure=fig),
                                ]
                            ),
                            className="mb-2",
                        ),
                        #     ],
                        #     width=6,
                        # ),
                    ],
                    width=6,
                ),
                justify="center",
            )
        ],
        fluid=True,
        style={"textAlign": "center"},
    )

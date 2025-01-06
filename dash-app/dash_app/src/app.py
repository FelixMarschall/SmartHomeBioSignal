from dash import Dash
import dash_bootstrap_components as dbc
from routes import routes
from flask import Flask, request, jsonify

from layout import layout

server = Flask(__name__)
app = Dash(__name__, server=server, external_stylesheets=[dbc.themes.BOOTSTRAP])

app = routes.create_app(app, server)

app.layout = layout.create_layout(app)

def main():
    app.run_server(host='0.0.0.0',debug=True)

if __name__ == '__main__':
    main()
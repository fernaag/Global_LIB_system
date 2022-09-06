#%%
import json
import urllib
import numpy as np
import pandas as pd
from cycler import cycler
import seaborn as sns
import os
import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from dash import Dash, dcc, html, Input, Output
#%%
app = Dash(__name__)

fig = go.Figure()

df = pd.read_pickle(os.getcwd()+'/visualizations/data/primary_material_demand_new')
rec = pd.read_pickle(os.getcwd()+'/visualizations/data/secondary_material_demand_new') 
flows = pd.read_pickle(os.getcwd()+'/visualizations/data/system_flows_new') 
out = pd.read_pickle(os.getcwd()+'/visualizations/data/outflows') 
stock = pd.read_pickle(os.getcwd()+'/visualizations/data/stock') 
slb = pd.read_pickle(os.getcwd()+'/visualizations/data/slb_capacity') 

app.layout = html.Div(
    [
        html.Div(
            [
                html.Div(
                    [
                        html.P("Stock scenario"),
                        dcc.Dropdown(
                            id="stock_scenario",
                            options = df['Stock_scenario'].unique(),
                            value='Medium',
                        ),
                    ]
                ),
                html.Div(
                    [
                        html.P("EV penetration scenario"),
                        dcc.Dropdown(
                            id="ev_scenario",
                            options=df['EV_penetration_scenario'].unique(),
                            value='SD',
                        ),
                    ]
                ),
                html.Div(
                    [
                        html.P("Material"),
                        dcc.Dropdown(
                            id="material",
                            options=df['Material'].unique(),
                            value='Ni',
                        ),
                    ]
                ),
                html.Div(
                    [
                        html.P("Vehicle size"),
                        dcc.Dropdown(
                            id="vehicle_size",
                            options=df['Vehicle_size_scenario'].unique(),
                            value='Constant',
                        ),
                    ]
                ),
                html.Div(
                    [
                        html.P("Battery chemistry scenario"),
                        dcc.Dropdown(
                            id="chem_scenario",
                            options = df['Chemistry_scenario'].unique(),
                            value='BNEF',
                        ),
                    ]
                ),
                html.Div(
                    [
                        html.P("Reuse scenario"),
                        dcc.Dropdown(
                            id="reuse_scenario",
                            options=df['Reuse_scenario'].unique(),
                            value='Direct recycling',
                        ),
                    ]
                ),
                html.Div(
                    [
                        html.P("Recycling process"),
                        dcc.Dropdown(
                            id="recycling_process",
                            options=df['Recycling_Process'].unique(),
                            value='Pyrometallurgy',
                        ),
                    ]
                ),
                html.Div(
                    [
                        dcc.Graph(
                            id="primary", hoverData={"points": [{"customdata": "2021"}]}
                        )
                    ],
                    style={
                        "width": "100%",
                        "display": "inline-block",
                        "padding": "0 20",
                    },
                ),
                html.Div(
                    [
                        dcc.Graph(id="flows"),
                    ],
                    style={"display": "inline-block", "width": "49%"},
                ),
                html.Div(
                    [dcc.Graph(figure=fig, id="outflows")],
                    style={
                        "width": "49%",
                        "display": "inline-block",
                        "padding": "0 20",
                    },
                ),
                html.Div(
                    [dcc.Graph(figure=fig, id="stock")],
                    style={
                        "width": "49%",
                        "display": "inline-block",
                        "padding": "0 20",
                    },
                ),
                html.Div(
                    [dcc.Graph(figure=fig, id="slb_stock")],
                    style={
                        "width": "49%",
                        "display": "inline-block",
                        "padding": "0 20",
                    },
                ),
            ]
        )
    ]
)

@app.callback(
    Output("primary", "figure"),
    Input("stock_scenario", "value"),
    Input("ev_scenario", "value"),
    Input("chem_scenario", "value"),
    Input("reuse_scenario", "value"),
    Input("vehicle_size", "value"),
    Input("recycling_process", "value"),
    Input("material", "value"),
)

def plot(
    stock_scenario,
    ev_scenario,
    chem_scenario,
    reuse_scenario,
    vehicle_size,
    recycling_process,
    material,
    ):
    stock_scenario = stock_scenario
    ev_scenario = ev_scenario
    chem_scenario = chem_scenario
    reuse_scenario = reuse_scenario
    material = material
    recycling_process = recycling_process
    vehicle_size = vehicle_size

    
    fig = px.area(
            df, x=range(2010,2051),
            y=[df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']==material)&\
                    (df['Recycling_Process']==recycling_process)].value.values, \
                    rec[(rec['Stock_scenario']==stock_scenario) & (rec['Chemistry_scenario']==chem_scenario)& \
                    (rec['EV_penetration_scenario']==ev_scenario)& (rec['Vehicle_size_scenario']==vehicle_size)&\
                    (rec['Reuse_scenario']==reuse_scenario) & (rec['Material']==material)&\
                    (rec['Recycling_Process']==recycling_process)].value.values],
                color_discrete_sequence=px.colors.qualitative.Set1,
        )
    fig.update_layout(title_text=rec[(rec['Stock_scenario']==stock_scenario) & (rec['Chemistry_scenario']==chem_scenario)& \
                    (rec['EV_penetration_scenario']==ev_scenario)& (rec['Vehicle_size_scenario']==vehicle_size)&\
                    (rec['Reuse_scenario']==reuse_scenario) & (rec['Material']==material)&\
                    (rec['Recycling_Process']==recycling_process)].Material.values[0] + ' demand for LIBs', font_size=16)
    fig.update_yaxes(title_text="Material demand [t]")
    fig.update_xaxes(title_text="Year")
    return fig

@app.callback(
    Output("flows", "figure"),
    Input("stock_scenario", "value"),
    Input("ev_scenario", "value"),
    Input("chem_scenario", "value"),
    Input("vehicle_size", "value"),
)

def plot(
    stock_scenario,
    ev_scenario,
    chem_scenario,
    vehicle_size,
    ):
    stock_scenario = stock_scenario
    ev_scenario = ev_scenario
    chem_scenario = chem_scenario
    vehicle_size = vehicle_size

    fig = px.area(
            flows,
            x=flows[(flows['Stock_scenario']==stock_scenario) & (flows['Chemistry_scenario']==chem_scenario)& \
                    (flows['EV_penetration_scenario']==ev_scenario)& (flows['Vehicle_size_scenario']==vehicle_size)].Time.values,
            y=flows[(flows['Stock_scenario']==stock_scenario) & (flows['Chemistry_scenario']==chem_scenario)& \
                    (flows['EV_penetration_scenario']==ev_scenario)& (flows['Vehicle_size_scenario']==vehicle_size)].value.values,
            color=flows[(flows['Stock_scenario']==stock_scenario) & (flows['Chemistry_scenario']==chem_scenario)& \
                 (flows['EV_penetration_scenario']==ev_scenario)& (flows['Vehicle_size_scenario']==vehicle_size)].Battery_Chemistry.values,
            line_group=flows[(flows['Stock_scenario']==stock_scenario) & (flows['Chemistry_scenario']==chem_scenario)& \
                 (flows['EV_penetration_scenario']==ev_scenario)& (flows['Vehicle_size_scenario']==vehicle_size)].Drive_Train.values,
            color_discrete_sequence=px.colors.qualitative.Alphabet,
        )
    fig.update_layout(title_text='Inflows by chemistry', font_size=16)
    fig.update_yaxes(title_text="Vehicle sales [million]")
    fig.update_xaxes(title_text="Year")

    return fig

@app.callback(
    Output("outflows", "figure"),
    Input("stock_scenario", "value"),
    Input("ev_scenario", "value"),
    Input("chem_scenario", "value"),
    Input("vehicle_size", "value"),
)

def plot(
    stock_scenario,
    ev_scenario,
    chem_scenario,
    vehicle_size,
    ):
    stock_scenario = stock_scenario
    ev_scenario = ev_scenario
    chem_scenario = chem_scenario
    vehicle_size = vehicle_size

    fig = px.area(
            out,
            x=out[(out['Stock_scenario']==stock_scenario) & (out['Chemistry_scenario']==chem_scenario)& \
                    (out['EV_penetration_scenario']==ev_scenario)& (out['Vehicle_size_scenario']==vehicle_size)].Time.values,
            y=out[(out['Stock_scenario']==stock_scenario) & (out['Chemistry_scenario']==chem_scenario)& \
                    (out['EV_penetration_scenario']==ev_scenario)& (out['Vehicle_size_scenario']==vehicle_size)].value.values,
            color=out[(out['Stock_scenario']==stock_scenario) & (out['Chemistry_scenario']==chem_scenario)& \
                 (out['EV_penetration_scenario']==ev_scenario)& (out['Vehicle_size_scenario']==vehicle_size)].Battery_Chemistry.values,
            line_group=out[(out['Stock_scenario']==stock_scenario) & (out['Chemistry_scenario']==chem_scenario)& \
                 (out['EV_penetration_scenario']==ev_scenario)& (out['Vehicle_size_scenario']==vehicle_size)].Drive_Train.values,
            color_discrete_sequence=px.colors.qualitative.Alphabet,
        )
    fig.update_layout(title_text='Outflows by chemistry', font_size=16)
    fig.update_yaxes(title_text="Vehicle outflows [million]")
    fig.update_xaxes(title_text="Year")

    return fig

@app.callback(
    Output("stock", "figure"),
    Input("stock_scenario", "value"),
    Input("ev_scenario", "value"),
    Input("vehicle_size", "value"),
)

def plot(
    stock_scenario,
    ev_scenario,
    vehicle_size,
    ):
    ev_scenario = ev_scenario
    stock_scenario = stock_scenario
    vehicle_size = vehicle_size

    fig = px.area(
            stock,
            x=stock[(stock['Stock_scenario']==stock_scenario)& \
                    (stock['EV_penetration_scenario']==ev_scenario)& (stock['Vehicle_size_scenario']==vehicle_size)].Time.values,
            y=stock[(stock['Stock_scenario']==stock_scenario) & \
                    (stock['EV_penetration_scenario']==ev_scenario)& (stock['Vehicle_size_scenario']==vehicle_size)].value.values,
            color=stock[(stock['Stock_scenario']==stock_scenario) & \
                 (stock['EV_penetration_scenario']==ev_scenario)& (stock['Vehicle_size_scenario']==vehicle_size)].Drive_Train.values,
            line_group=stock[(stock['Stock_scenario']==stock_scenario) & \
                 (stock['EV_penetration_scenario']==ev_scenario)& (stock['Vehicle_size_scenario']==vehicle_size)].Size.values,
            color_discrete_sequence=px.colors.qualitative.Set1,
        )
    fig.update_layout(title_text='Stock by drive train', font_size=16)
    fig.update_yaxes(title_text="Vehicle stock [million]")
    fig.update_xaxes(title_text="Year")

    return fig

@app.callback(
    Output("slb_stock", "figure"),
    Input("stock_scenario", "value"),
    Input("ev_scenario", "value"),
    Input("vehicle_size", "value"),
    Input("chem_scenario", "value"),
    Input("reuse_scenario", "value"),
)

def plot(
    stock_scenario,
    ev_scenario,
    vehicle_size,
    chem_scenario,
    reuse_scenario,
    ):
    stock_scenario = stock_scenario
    ev_scenario = ev_scenario
    vehicle_size = vehicle_size
    chem_scenario = chem_scenario
    reuse_scenario = reuse_scenario

    fig = px.area(
            slb,
            x=slb[(slb['Stock_scenario']==stock_scenario) & \
                    (slb['EV_penetration_scenario']==ev_scenario)& (slb['Vehicle_size_scenario']==vehicle_size)\
                        & (slb['Reuse_scenario']==reuse_scenario)& (slb['Chemistry_scenario']==chem_scenario)].Time.values,
            y=slb[(slb['Stock_scenario']==stock_scenario) & \
                    (slb['EV_penetration_scenario']==ev_scenario)& (slb['Vehicle_size_scenario']==vehicle_size)\
                        & (slb['Reuse_scenario']==reuse_scenario)& (slb['Chemistry_scenario']==chem_scenario)].value.values,
            color=slb[(slb['Stock_scenario']==stock_scenario) & \
                 (slb['EV_penetration_scenario']==ev_scenario)& (slb['Vehicle_size_scenario']==vehicle_size)\
                     & (slb['Reuse_scenario']==reuse_scenario)& (slb['Chemistry_scenario']==chem_scenario)].Battery_Chemistry.values,
            color_discrete_sequence=px.colors.qualitative.Alphabet,
        )
    fig.update_layout(title_text='SLB installed capacity', font_size=16)
    fig.update_yaxes(title_text="Capacity [MWh]")
    fig.update_xaxes(title_text="Year")

    return fig

if __name__ == "__main__":
    app.run_server(host="127.0.0.1", port="8050", debug=True)


from inspect import trace
import json
from unicodedata import name
import urllib
from xml.sax.handler import feature_string_interning
from matplotlib.pyplot import legend
import numpy as np
import pandas as pd
from cycler import cycler
import seaborn as sns
import os
import dash
from dash import dcc
from dash import html
from dash.dependencies import Input, Output
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from dash import Dash, dcc, html, Input, Output
import base64
import dash_bootstrap_components as dbc
app = dash.Dash(
    external_stylesheets=[dbc.themes.BOOTSTRAP]
)

# fig_mat = go.Figure()
# fig_in = go.Figure()
# fig_out = go.Figure()
# fig_stock = go.Figure()
# fig_slb = go.Figure()
df = pd.read_pickle(os.getcwd()+'/data/primary_material_demand_new')
rec = pd.read_pickle(os.getcwd()+'/data/secondary_material_demand_new') 
flows = pd.read_pickle(os.getcwd()+'/data/system_flows_new') 
out = pd.read_pickle(os.getcwd()+'/data/outflows') 
stock = pd.read_pickle(os.getcwd()+'/data/stock') 
slb = pd.read_pickle(os.getcwd()+'/data/slb_capacity') 
logo_path = os.getcwd()+'/data/indecol.png'
# Adding identified col to material demand
df['Type'] = 'Primary'
rec['Type'] = 'Recycled'
df = pd.concat([df,rec])
# Adding logo
html.Img(src=logo_path)
# Using base64 encoding and decoding
def b64_image(image_filename):
    with open(image_filename, 'rb') as f:
      image = f.read()
    return 'data:image/png;base64,' + base64.b64encode(image).decode('utf-8')
#calling the above function
app.layout = html.Div(
    [
        html.Div(
            [
                html.Div([
                    html.Img(src=b64_image(logo_path), style={'height':'10%', 'width':'10%'}),                 
                    ],
                    style={
                        'display': 'inline-block',
                        'vertical-align': 'top',
                        'width': '50%',
                        'height': '50%',
                        'margin-left': '10px',        }
                ),
        #         html.Div([
        #                 html.H2('Interactive visualization tool to explore material demand and secondary availability \n \
        #                         of lithium-ion batteries for electric vehicles using the MATILDA model'),
        #             ],
        #             style={
        #                 'display': 'inline-block',
        #                 'vertical-align': 'top',
        #                 'width': '100%',
        #                 'height': '100%',
        #                 'margin-right': '1000px'
        # }
                # ),
                dcc.Tabs(id="tabs_graph", value='tab-about', 
                style={'width': '100vw'},
                children=[
                dcc.Tab(label='About', value='tab-about'),
                dcc.Tab(label='Vehicle layer', value='tab-vehicles'),
                dcc.Tab(label='Battery layer', value='tab-batteries'),  
                dcc.Tab(label='Material layer', value='tab-materials')]),
                html.Div(
                    [
                        html.P("Stock scenario"),
                        dcc.Dropdown(
                            id="stock_scenario",
                            options = df['Stock_scenario'].unique(),
                            value='Medium',
                        ),
                    ],
                    style={
                        'display': 'inline-block',
                        'vertical-align': 'top',
                        'width': '10%',
                        'height': '100%',
                        'margin-left': '0px'
        },
                ),
                html.Div(
                    [
                        html.P("EV penetration scenario"),
                        dcc.Dropdown(
                            id="ev_scenario",
                            options=df['EV_penetration_scenario'].unique(),
                            value='SD',
                        ),
                    ],
                    style={
                        'display': 'inline-block',
                        'vertical-align': 'top',
                        'width': '10%',
                        'height': '100%',
                        'margin-left': '50px'
        },
                ),
        #         html.Div(
        #             [
        #                 html.P("Material"),
        #                 dcc.Dropdown(
        #                     id="material",
        #                     options=df['Material'].unique(),
        #                     value='Li',
        #                 ),
        #             ],
        #             style={
        #                 'display': 'inline-block',
        #                 'vertical-align': 'top',
        #                 'width': '10%',
        #                 'height': '100%',
        #                 'margin-left': '55px'
        # },
        #         ),
                html.Div(
                    [
                        html.P("Vehicle size"),
                        dcc.Dropdown(
                            id="vehicle_size",
                            options=df['Vehicle_size_scenario'].unique(),
                            value='Constant',
                        ),
                    ],
                    style={
                        'display': 'inline-block',
                        'vertical-align': 'top',
                        'width': '10%',
                        'height': '100%',
                        'margin-left': '60px'
        },
                ),
                html.Div(
                    [
                        html.P("Battery chemistry scenario"),
                        dcc.Dropdown(
                            id="chem_scenario",
                            options = df['Chemistry_scenario'].unique(),
                            value='BNEF',
                        ),
                    ],
                    style={
                        'display': 'inline-block',
                        'vertical-align': 'top',
                        'width': '12%',
                        'height': '100%',
                        'margin-left': '78px'
        },
                ),
                html.Div(
                    [
                        html.P("Reuse scenario"),
                        dcc.Dropdown(
                            id="reuse_scenario",
                            options=df['Reuse_scenario'].unique(),
                            value='LFP reused',
                        ),
                    ],
                    style={
                        'display': 'inline-block',
                        'vertical-align': 'top',
                        'width': '10%',
                        'height': '100%',
                        'margin-left': '90px'
        },
                ),
                html.Div(
                    [
                        html.P("Recycling process"),
                        dcc.Dropdown(
                            id="recycling_process",
                            options=df['Recycling_Process'].unique(),
                            value='Direct',
                        ),
                    ],
                    style={
                        'display': 'inline-block',
                        'vertical-align': 'top',
                        'width': '10%',
                        'height': '100%',
                        'margin-left': '100px'
        },
                ),

                html.Div(id='graph'),
            ]
        )
    ]
)

@app.callback(
    [
    Output("graph", "children"),
    ],
    Input("stock_scenario", "value"),
    Input("ev_scenario", "value"),
    Input("chem_scenario", "value"),
    Input("reuse_scenario", "value"),
    Input("vehicle_size", "value"),
    Input("recycling_process", "value"),
    #Input("material", "value"), 
    Input("tabs_graph", "value"), 
)

def plot(
    stock_scenario,
    ev_scenario,
    chem_scenario,
    reuse_scenario,
    vehicle_size,
    recycling_process,
    #material,
    tabs_graph,
    ):
    stock_scenario = stock_scenario
    ev_scenario = ev_scenario
    chem_scenario = chem_scenario
    reuse_scenario = reuse_scenario
    #material = material
    recycling_process = recycling_process
    vehicle_size = vehicle_size
    tabs_graph = tabs_graph
    if tabs_graph == 'tab-about':
        return [html.Div([
            html.H3('Interactive visualization tool for the global lithium-ion battery material demand for passenger vehicles',
                    style={"height": "2vh", "margin-top":"1%", "margin-left":"1%"}),
            html.Div([
                html.P('Based on the article "Evaluating strategies for material use in lithium-ion batteries for electric vehicles using the global MATILDa model" (under review) '
                       'by Fernando Aguilar Lopez, Romain G. Billy and Daniel B. Müller.'),
                html.P('Please use the tabs to navigate between the different graphs, and the filters to select scenarios parameters'),
                html.P("Complete code and data are available on GitHub:"),
                html.A('https://github.com/fernaag/Global_LIB_system', 
                       href='https://github.com/fernaag/Global_LIB_system')
            ],
                style={"margin-top":"3%", "margin-left":"1%"})
        ])]
        
    elif tabs_graph =='tab-materials':
        fig_ni = px.area(
            df, 
            x=df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Ni')&\
                    (df['Recycling_Process']==recycling_process)].Time.values,
            y=df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Ni')&\
                    (df['Recycling_Process']==recycling_process)].value.values,
                color_discrete_sequence=px.colors.qualitative.Set1, 
                color =df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Ni')&\
                    (df['Recycling_Process']==recycling_process)].Type.values,
                labels={'color':'Material demand'},
        )
        fig_ni.update_layout(title_text=rec[(rec['Stock_scenario']==stock_scenario) & (rec['Chemistry_scenario']==chem_scenario)& \
                        (rec['EV_penetration_scenario']==ev_scenario)& (rec['Vehicle_size_scenario']==vehicle_size)&\
                        (rec['Reuse_scenario']==reuse_scenario) & (rec['Material']=='Ni')&\
                        (rec['Recycling_Process']==recycling_process)].Material.values[0] + ' demand for LIBs', font_size=16)
        fig_ni.update_yaxes(title_text="Material demand [t/year]")
        fig_ni.update_xaxes(title_text="Year")
        
        fig_li = px.area(
            df, 
            x=df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Li')&\
                    (df['Recycling_Process']==recycling_process)].Time.values,
            y=df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Li')&\
                    (df['Recycling_Process']==recycling_process)].value.values,
                color_discrete_sequence=px.colors.qualitative.Set1, 
                color =df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Li')&\
                    (df['Recycling_Process']==recycling_process)].Type.values,
                labels={'color':'Material demand'},
        )
        fig_li.update_layout(title_text=rec[(rec['Stock_scenario']==stock_scenario) & (rec['Chemistry_scenario']==chem_scenario)& \
                        (rec['EV_penetration_scenario']==ev_scenario)& (rec['Vehicle_size_scenario']==vehicle_size)&\
                        (rec['Reuse_scenario']==reuse_scenario) & (rec['Material']=='Li')&\
                        (rec['Recycling_Process']==recycling_process)].Material.values[0] + ' demand for LIBs', font_size=16)
        fig_li.update_yaxes(title_text="Material demand [t/year]")
        fig_li.update_xaxes(title_text="Year")
        
        fig_co = px.area(
            df, 
            x=df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Co')&\
                    (df['Recycling_Process']==recycling_process)].Time.values,
            y=df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Co')&\
                    (df['Recycling_Process']==recycling_process)].value.values,
                color_discrete_sequence=px.colors.qualitative.Set1, 
                color =df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Co')&\
                    (df['Recycling_Process']==recycling_process)].Type.values,
                labels={'color':'Material demand'},
        )
        fig_co.update_layout(title_text=rec[(rec['Stock_scenario']==stock_scenario) & (rec['Chemistry_scenario']==chem_scenario)& \
                        (rec['EV_penetration_scenario']==ev_scenario)& (rec['Vehicle_size_scenario']==vehicle_size)&\
                        (rec['Reuse_scenario']==reuse_scenario) & (rec['Material']=='Co')&\
                        (rec['Recycling_Process']==recycling_process)].Material.values[0] + ' demand for LIBs', font_size=16)
        fig_co.update_yaxes(title_text="Material demand [t/year]")
        fig_co.update_xaxes(title_text="Year")
        
        fig_p = px.area(
            df, 
            x=df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='P')&\
                    (df['Recycling_Process']==recycling_process)].Time.values,
            y=df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='P')&\
                    (df['Recycling_Process']==recycling_process)].value.values,
                color_discrete_sequence=px.colors.qualitative.Set1, 
                color =df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='P')&\
                    (df['Recycling_Process']==recycling_process)].Type.values,
                labels={'color':'Material demand'},
        )
        fig_p.update_layout(title_text=rec[(rec['Stock_scenario']==stock_scenario) & (rec['Chemistry_scenario']==chem_scenario)& \
                        (rec['EV_penetration_scenario']==ev_scenario)& (rec['Vehicle_size_scenario']==vehicle_size)&\
                        (rec['Reuse_scenario']==reuse_scenario) & (rec['Material']=='P')&\
                        (rec['Recycling_Process']==recycling_process)].Material.values[0] + ' demand for LIBs', font_size=16)
        fig_p.update_yaxes(title_text="Material demand [t/year]")
        fig_p.update_xaxes(title_text="Year")
        
        fig_al = px.area(
            df, 
            x=df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Al')&\
                    (df['Recycling_Process']==recycling_process)].Time.values,
            y=df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Al')&\
                    (df['Recycling_Process']==recycling_process)].value.values,
                color_discrete_sequence=px.colors.qualitative.Set1, 
                color =df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Al')&\
                    (df['Recycling_Process']==recycling_process)].Type.values,
                labels={'color':'Material demand'},
        )
        fig_al.update_layout(title_text=rec[(rec['Stock_scenario']==stock_scenario) & (rec['Chemistry_scenario']==chem_scenario)& \
                        (rec['EV_penetration_scenario']==ev_scenario)& (rec['Vehicle_size_scenario']==vehicle_size)&\
                        (rec['Reuse_scenario']==reuse_scenario) & (rec['Material']=='Al')&\
                        (rec['Recycling_Process']==recycling_process)].Material.values[0] + ' demand for LIBs', font_size=16)
        fig_al.update_yaxes(title_text="Material demand [t/year]")
        fig_al.update_xaxes(title_text="Year")
        
        fig_c = px.area(
            df, 
            x=df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Graphite')&\
                    (df['Recycling_Process']==recycling_process)].Time.values,
            y=df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Graphite')&\
                    (df['Recycling_Process']==recycling_process)].value.values,
                color_discrete_sequence=px.colors.qualitative.Set1, 
                color =df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Graphite')&\
                    (df['Recycling_Process']==recycling_process)].Type.values,
                labels={'color':'Material demand'},
        )
        fig_c.update_layout(title_text=rec[(rec['Stock_scenario']==stock_scenario) & (rec['Chemistry_scenario']==chem_scenario)& \
                        (rec['EV_penetration_scenario']==ev_scenario)& (rec['Vehicle_size_scenario']==vehicle_size)&\
                        (rec['Reuse_scenario']==reuse_scenario) & (rec['Material']=='Graphite')&\
                        (rec['Recycling_Process']==recycling_process)].Material.values[0] + ' demand for LIBs', font_size=16)
        fig_c.update_yaxes(title_text="Material demand [t/year]")
        fig_c.update_xaxes(title_text="Year")
        
        fig_mn = px.area(
            df, 
            x=df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Mn')&\
                    (df['Recycling_Process']==recycling_process)].Time.values,
            y=df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Mn')&\
                    (df['Recycling_Process']==recycling_process)].value.values,
                color_discrete_sequence=px.colors.qualitative.Set1, 
                color =df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Mn')&\
                    (df['Recycling_Process']==recycling_process)].Type.values,
                labels={'color':'Material demand'},
        )
        fig_mn.update_layout(title_text=rec[(rec['Stock_scenario']==stock_scenario) & (rec['Chemistry_scenario']==chem_scenario)& \
                        (rec['EV_penetration_scenario']==ev_scenario)& (rec['Vehicle_size_scenario']==vehicle_size)&\
                        (rec['Reuse_scenario']==reuse_scenario) & (rec['Material']=='Mn')&\
                        (rec['Recycling_Process']==recycling_process)].Material.values[0] + ' demand for LIBs', font_size=16)
        fig_mn.update_yaxes(title_text="Material demand [t/year]")
        fig_mn.update_xaxes(title_text="Year")
        
        fig_cu = px.area(
            df, 
            x=df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Cu')&\
                    (df['Recycling_Process']==recycling_process)].Time.values,
            y=df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Cu')&\
                    (df['Recycling_Process']==recycling_process)].value.values,
                color_discrete_sequence=px.colors.qualitative.Set1, 
                color =df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Cu')&\
                    (df['Recycling_Process']==recycling_process)].Type.values,
                labels={'color':'Material demand'},
        )
        fig_cu.update_layout(title_text=rec[(rec['Stock_scenario']==stock_scenario) & (rec['Chemistry_scenario']==chem_scenario)& \
                        (rec['EV_penetration_scenario']==ev_scenario)& (rec['Vehicle_size_scenario']==vehicle_size)&\
                        (rec['Reuse_scenario']==reuse_scenario) & (rec['Material']=='Cu')&\
                        (rec['Recycling_Process']==recycling_process)].Material.values[0] + ' demand for LIBs', font_size=16)
        fig_cu.update_yaxes(title_text="Material demand [t/year]")
        fig_cu.update_xaxes(title_text="Year")
        
        fig_si = px.area(
            df, 
            x=df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Si')&\
                    (df['Recycling_Process']==recycling_process)].Time.values,
            y=df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Si')&\
                    (df['Recycling_Process']==recycling_process)].value.values,
                color_discrete_sequence=px.colors.qualitative.Set1, 
                color =df[(df['Stock_scenario']==stock_scenario) & (df['Chemistry_scenario']==chem_scenario)& \
                    (df['EV_penetration_scenario']==ev_scenario)& (df['Vehicle_size_scenario']==vehicle_size)&\
                    (df['Reuse_scenario']==reuse_scenario) & (df['Material']=='Si')&\
                    (df['Recycling_Process']==recycling_process)].Type.values,
                labels={'color':'Material demand'},
        )
        fig_si.update_layout(title_text=rec[(rec['Stock_scenario']==stock_scenario) & (rec['Chemistry_scenario']==chem_scenario)& \
                        (rec['EV_penetration_scenario']==ev_scenario)& (rec['Vehicle_size_scenario']==vehicle_size)&\
                        (rec['Reuse_scenario']==reuse_scenario) & (rec['Material']=='Si')&\
                        (rec['Recycling_Process']==recycling_process)].Material.values[0] + ' demand for LIBs', font_size=16)
        fig_si.update_yaxes(title_text="Material demand [t/year]")
        fig_si.update_xaxes(title_text="Year")
        return [html.Div([
            
                dbc.Row([
                    dcc.Graph(
                            figure=fig_ni, id="primary_ni"
                        ,
                    style={
                        "width": "33%",
                        "display": "inline-block",
                        "padding": "0 20",
                    }),
                dcc.Graph(
                            figure=fig_li, id="primary_li"
                        ,
                    style={
                        "width": "33%",
                        "display": "inline-block",
                        "padding": "0 20",
                    }),
                dcc.Graph(
                            figure=fig_co, id="primary_co"
                        ,
                    style={
                        "width": "33%",
                        "display": "inline-block",
                        "padding": "0 20",
                    }),
                dcc.Graph(
                            figure=fig_p, id="primary_ni"
                        ,
                    style={
                        "width": "33%",
                        "display": "inline-block",
                        "padding": "0 20",
                    }),
                dcc.Graph(
                            figure=fig_al, id="primary_li"
                        ,
                    style={
                        "width": "33%",
                        "display": "inline-block",
                        "padding": "0 20",
                    }),
                dcc.Graph(
                            figure=fig_c, id="primary_co"
                        ,
                    style={
                        "width": "33%",
                        "display": "inline-block",
                        "padding": "0 20",
                    }),
                dcc.Graph(
                            figure=fig_mn, id="primary_ni"
                        ,
                    style={
                        "width": "33%",
                        "display": "inline-block",
                        "padding": "0 20",
                    }),
                dcc.Graph(
                            figure=fig_cu, id="primary_li"
                        ,
                    style={
                        "width": "33%",
                        "display": "inline-block",
                        "padding": "0 20",
                    }),
                dcc.Graph(
                            figure=fig_si, id="primary_co"
                        ,
                    style={
                        "width": "33%",
                        "display": "inline-block",
                        "padding": "0 20",
                    }),
        ]),
        ])]

        
    elif tabs_graph =='tab-batteries':
        fig_in = px.area(
                flows,
                x=flows[(flows['Stock_scenario']==stock_scenario) & (flows['Chemistry_scenario']==chem_scenario)& \
                        (flows['EV_penetration_scenario']==ev_scenario)& (flows['Vehicle_size_scenario']==vehicle_size)].Time.values,
                y=flows[(flows['Stock_scenario']==stock_scenario) & (flows['Chemistry_scenario']==chem_scenario)& \
                        (flows['EV_penetration_scenario']==ev_scenario)& (flows['Vehicle_size_scenario']==vehicle_size)].value.values,
                color=flows[(flows['Stock_scenario']==stock_scenario) & (flows['Chemistry_scenario']==chem_scenario)& \
                    (flows['EV_penetration_scenario']==ev_scenario)& (flows['Vehicle_size_scenario']==vehicle_size)].Battery_Chemistry.values,
                line_group=flows[(flows['Stock_scenario']==stock_scenario) & (flows['Chemistry_scenario']==chem_scenario)& \
                    (flows['EV_penetration_scenario']==ev_scenario)& (flows['Vehicle_size_scenario']==vehicle_size)].Drive_Train.values,
                color_discrete_sequence=px.colors.qualitative.Alphabet, labels={'color':'Chemistry'}
            )
        fig_in.update_layout(title_text='Inflows by chemistry', font_size=16)
        fig_in.update_yaxes(title_text="Vehicle sales [million]")
        fig_in.update_xaxes(title_text="Year")
        
        # Adding outflows
        fig_out = px.area(
                out,
                x=out[(out['Stock_scenario']==stock_scenario) & (out['Chemistry_scenario']==chem_scenario)& \
                        (out['EV_penetration_scenario']==ev_scenario)& (out['Vehicle_size_scenario']==vehicle_size)].Time.values,
                y=out[(out['Stock_scenario']==stock_scenario) & (out['Chemistry_scenario']==chem_scenario)& \
                        (out['EV_penetration_scenario']==ev_scenario)& (out['Vehicle_size_scenario']==vehicle_size)].value.values,
                color=out[(out['Stock_scenario']==stock_scenario) & (out['Chemistry_scenario']==chem_scenario)& \
                    (out['EV_penetration_scenario']==ev_scenario)& (out['Vehicle_size_scenario']==vehicle_size)].Battery_Chemistry.values,
                line_group=out[(out['Stock_scenario']==stock_scenario) & (out['Chemistry_scenario']==chem_scenario)& \
                    (out['EV_penetration_scenario']==ev_scenario)& (out['Vehicle_size_scenario']==vehicle_size)].Drive_Train.values,
                color_discrete_sequence=px.colors.qualitative.Alphabet, labels={'color':'Chemistry'}
            )
        fig_out.update_layout(title_text='Outflows by chemistry', font_size=16)
        fig_out.update_yaxes(title_text="Vehicle outflows [million]")
        fig_out.update_xaxes(title_text="Year")
        
        fig_slb = px.area(
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
            color_discrete_sequence=px.colors.qualitative.Alphabet, labels={'color':'Chemistry'}
        )
        fig_slb.update_layout(title_text='SLB installed capacity', font_size=16)
        fig_slb.update_yaxes(title_text="Capacity [MWh]")
        fig_slb.update_xaxes(title_text="Year")
        
        return  [html.Div([
            
                dbc.Row([     
                        dcc.Graph(figure=fig_in, id="flows",
                        style={"display": "inline-block", "width": "49%"}),
                        
                        dcc.Graph(figure=fig_out, id="outflows",
                        style={
                            "width": "49%",
                            "display": "inline-block",
                            "padding": "0 20"}),
                
                        dcc.Graph(figure=fig_slb, id="slb_stock",
                        style={
                            "width": "49%",
                            "display": "inline-block",
                            "padding": "0 20"
                        }),
        ])
            ])
                ]
            
    # Adding stock Figure
    elif tabs_graph =='tab-vehicles':    
        fig_stock = px.area(
            stock,
            x=stock[(stock['Stock_scenario']==stock_scenario)& \
                    (stock['EV_penetration_scenario']==ev_scenario)& (stock['Vehicle_size_scenario']==vehicle_size)].Time.values,
            y=stock[(stock['Stock_scenario']==stock_scenario) & \
                    (stock['EV_penetration_scenario']==ev_scenario)& (stock['Vehicle_size_scenario']==vehicle_size)].value.values,
            color=stock[(stock['Stock_scenario']==stock_scenario) & \
                 (stock['EV_penetration_scenario']==ev_scenario)& (stock['Vehicle_size_scenario']==vehicle_size)].Drive_Train.values,
            line_group=stock[(stock['Stock_scenario']==stock_scenario) & \
                 (stock['EV_penetration_scenario']==ev_scenario)& (stock['Vehicle_size_scenario']==vehicle_size)].Size.values,
            color_discrete_sequence=px.colors.qualitative.Set1, labels={'color':'Drive train'}
        )
        fig_stock.update_layout(title_text='Stock by drive train', font_size=16)
        fig_stock.update_yaxes(title_text="Vehicle stock [million]")
        fig_stock.update_xaxes(title_text="Year")
        return html.Div(
                    [dcc.Graph(figure=fig_stock, id="stock")],
                    style={
                        "width": "100%",
                        "display": "inline-block",
                        "padding": "0 20",
                    },
                ),
        
    # Adding SLB stock
        

# if __name__ == "__main__":
#     app.run_server(host="127.0.0.1", port="8050", debug=True)

if __name__ == '__main__':
    
    # for running the app on localhost (on your computer) uncomment the next line:

    #sankey_app_parameters.run_server(debug=True)

    # for running the app on the NTNU Openstack server uncomment the next line:

    app.run_server(host="0.0.0.0", port="8051", debug=False)


# MATILDA model

## This repo contains the code to run the global MATILDA model related to the publication: "Evaluating strategies for managing resource use in lithium-ion batteries for electric vehicles using the global MATILDA model"

Below you can find a decription of the data and folders included in this repository as well as the requirements and data structure needed to run it.

1) data_handling -> fitting_and_preparation folders: contain several .ipynb scripts which take the raw data, process it into scenarios, and creates ODYM-ready arrays with the corresponding aspects and sizes. The raw data is not included here due to size limitations on GitHub but can be found in the SI of the manuscript. The data paths need to be updated accordingly.
2) docs: Contains condiguration files to run ODYM framework
    - Files: ODYM_Classification file contains the main elements included in the model
    - Files: ODYM_Config file contains a summary of all elements included for each aspect and their respective index in the model. This file should be used to consult which index relates to what goods
3) odym: Contains requirements needed to run ODYM framework
4) results: 
    - overview: Contains all plots generated from the MATILDA model that are included in the main manuscript.
    - SI: Contains all plots generated from the MATILDA model that are included in the SI.
5) MATILDA.py is the main script that runs the dynamic stock model based on the parameters. The functions that generate the relevant plots are defined at the end of the script and need to be called for them to execute. This also applies to the long lifetime and battery reuse and replacement scenarios.
    - The input data files as numpy arrays are provided openly in the following repository: https://doi.org/10.5281/zenodo.7252047 
    - To run the model, the files need to be downloaded and the path to read them in MATILDA needs to be updated as indicated in the code
6) product_component_model.py and ODYM_Classes.py: Needed to compute the stock dynamics. The product_component_model presented here is an extention to the framework presented by Aguilar Lopez at al. here: https://doi.org/10.1111/jiec.13316 
7) requirements.txt: Requierments needed to run the model
8) visualizations: Running dashboard.py allows the user to initialize a dynamic and interactive visualization tool to explore all of the scenarios included in MATILDA. They can be reached by going to the following site in a web browser while running the script: http://127.0.0.1:8050/

All model scenarios can be explored at the following website: http://10.212.26.107:8051/ (to be made publically available soon)
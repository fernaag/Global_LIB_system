# %%
# Load a local copy of the current ODYM branch:
from gc import set_debug
import sys
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import pickle
from seaborn.palettes import color_palette
import xlrd
import pylab
from copy import deepcopy
import logging as log
import xlwt
import tqdm
import math
from scipy.stats import norm
from tqdm import tqdm
import time
import matplotlib
import product_component_model as pcm
mpl_logger = log.getLogger("matplotlib")
mpl_logger.setLevel(log.WARNING)
# For Ipython Notebook only
### Preamble

# add ODYM module directory to system path, relative
MainPath = os.path.join(os.getcwd(), 'odym', 'modules')
sys.path.insert(0, MainPath)

# add ODYM module directory to system path, absolute
sys.path.insert(0, os.path.join(os.getcwd(), 'odym', 'modules'))

# Specify path to dynamic stock model and to datafile, relative
DataPath = os.path.join( 'docs', 'files')

# Specify path to dynamic stock model and to datafile, absolute
DataPath = os.path.join(os.getcwd(), 'docs', 'Files')

import ODYM_Classes as msc # import the ODYM class file
import ODYM_Functions as msf # import the ODYM function file
import dynamic_stock_model as dsm # import the dynamic stock model library

# Initialize loggin routine
log_verbosity = eval("log.DEBUG")
log_filename = 'LogFileTest.md'
[Mylog, console_log, file_log] = msf.function_logger(log_filename, os.getcwd(),
                                                     log_verbosity, log_verbosity)
Mylog.info('### 1. - Initialize.')

#Read main script parameters
#Load project-specific config file
ProjectSpecs_ConFile = 'ODYM_Config_Vehicle_System.xlsx'
Model_Configfile     = xlrd.open_workbook(os.path.join(DataPath, ProjectSpecs_ConFile))
ScriptConfig         = {'Model Setting': Model_Configfile.sheet_by_name('Config').cell_value(3,3)} # Dictionary with config parameters
Model_Configsheet    = Model_Configfile.sheet_by_name('Setting_' + ScriptConfig['Model Setting'])

Name_Scenario        = Model_Configsheet.cell_value(3,3)
print(Name_Scenario)

#Read control and selection parameters into dictionary
ScriptConfig         = msf.ParseModelControl(Model_Configsheet,ScriptConfig)

Mylog.info('Read and parse config table, including the model index table, from model config sheet.')
IT_Aspects,IT_Description,IT_Dimension,IT_Classification,IT_Selector,IT_IndexLetter,\
PL_Names,PL_Description,PL_Version,PL_IndexStructure,PL_IndexMatch,PL_IndexLayer,\
PrL_Number,PrL_Name,PrL_Comment,PrL_Type,ScriptConfig = msf.ParseConfigFile(Model_Configsheet,ScriptConfig,Mylog)    

class_filename       = 'ODYM_Classifications_Master_Vehicle_System.xlsx'
Classfile            = xlrd.open_workbook(os.path.join(DataPath,class_filename))
Classsheet           = Classfile.sheet_by_name('MAIN_Table')
MasterClassification = msf.ParseClassificationFile_Main(Classsheet,Mylog)


Mylog.info('Define model classifications and select items for model classifications according to information provided by config file.')
ModelClassification  = {} # Dict of model classifications
for m in range(0,len(IT_Aspects)):
    ModelClassification[IT_Aspects[m]] = deepcopy(MasterClassification[IT_Classification[m]])
    EvalString = msf.EvalItemSelectString(IT_Selector[m],len(ModelClassification[IT_Aspects[m]].Items))
    if EvalString.find(':') > -1: # range of items is taken
        RangeStart = int(EvalString[0:EvalString.find(':')])
        RangeStop  = int(EvalString[EvalString.find(':')+1::])
        ModelClassification[IT_Aspects[m]].Items = ModelClassification[IT_Aspects[m]].Items[RangeStart:RangeStop]           
    elif EvalString.find('[') > -1: # selected items are taken
        ModelClassification[IT_Aspects[m]].Items = [ModelClassification[IT_Aspects[m]].Items[i] for i in eval(EvalString)]
    elif EvalString == 'all':
        None
    else:
        Mylog.error('Item select error for aspect ' + IT_Aspects[m] + ' were found in datafile.')
        break

# Define model index table and parameter dictionary
Mylog.info('### 2.2 - Define model index table and parameter dictionary')
Model_Time_Start = int(min(ModelClassification['Time'].Items))
Model_Time_End   = int(max(ModelClassification['Time'].Items))
Model_Duration   = Model_Time_End - Model_Time_Start + 1

Mylog.info('Define index table dataframe.')
IndexTable = pd.DataFrame({'Aspect'        : IT_Aspects,  # 'Time' and 'Element' must be present!
                           'Description'   : IT_Description,
                           'Dimension'     : IT_Dimension,
                           'Classification': [ModelClassification[Aspect] for Aspect in IT_Aspects],
                           'IndexLetter'   : IT_IndexLetter})  # Unique one letter (upper or lower case) indices to be used later for calculations.

# Default indexing of IndexTable, other indices are produced on the fly
IndexTable.set_index('Aspect', inplace=True)

# Add indexSize to IndexTable:
IndexTable['IndexSize'] = pd.Series([len(IndexTable.Classification[i].Items) for i in range(0, len(IndexTable.IndexLetter))],
                                    index=IndexTable.index)

# list of the classifications used for each indexletter
IndexTable_ClassificationNames = [IndexTable.Classification[i].Name for i in range(0, len(IndexTable.IndexLetter))]


# Define dimension sizes
Nt = len(IndexTable.Classification[IndexTable.index.get_loc('Time')].Items)
Nc = len(IndexTable.Classification[IndexTable.index.get_loc('Age-cohort')].Items)
Ng = len(IndexTable.Classification[IndexTable.index.get_loc('Good')].Items)
Nr = len(IndexTable.Classification[IndexTable.index.get_loc('Region')].Items)
Ne = len(IndexTable.Classification[IndexTable.index.get_loc('Element')].Items)
Nb = len(IndexTable.Classification[IndexTable.index.get_loc('Battery_Chemistry')].Items)
Np = len(IndexTable.Classification[IndexTable.index.get_loc('Battery_Parts')].Items)
Ns = len(IndexTable.Classification[IndexTable.index.get_loc('Size')].Items)
Nh = len(IndexTable.Classification[IndexTable.index.get_loc('Recycling_Process')].Items)
NS = len(IndexTable.Classification[IndexTable.index.get_loc('Scenario')].Items)
Na = len(IndexTable.Classification[IndexTable.index.get_loc('Chemistry_Scenarios')].Items)
Nz = len(IndexTable.Classification[IndexTable.index.get_loc('Stock_Scenarios')].Items)
NR = len(IndexTable.Classification[IndexTable.index.get_loc('Reuse_Scenarios')].Items)
NE = len(IndexTable.Classification[IndexTable.index.get_loc('Energy_Storage_Scenarios')].Items)


ParameterDict = {}
mo_start = 0 # set mo for re-reading a certain parameter
ParameterDict['Vehicle_stock']= msc.Parameter(Name = 'Vehicle_stock',
                                                             ID = 1,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'z,r,t', #t=time, h=units
                                                             Values = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/03_scenario_data/global_model/IUS/regionalized_IUS_OICA_new.npy'), 
                                                             Uncert=None,
                                                             Unit = '# passenger cars')
# ParameterDict['Vehicle_sales']= msc.Parameter(Name = 'Vehicle_sales',
#                                                              ID = 1,
#                                                              P_Res = None,
#                                                              MetaData = None,
#                                                              Indices = 'r,t', #t=time, h=units
#                                                              Values = np.load('/Users/fernaag/Box/BATMAN/Coding/Norwegian_Model/Pickle_files/Prepared files for model/Inflow_driven/Total_sales_combined_and_fitted.npy'),
#                                                              Uncert=None,
#                                                              Unit = '# of vehicles')

ParameterDict['Drive_train_shares']= msc.Parameter(Name = 'Drive_train_shares',
                                                             ID = 2,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'S,g,t', #t=time, h=units
                                                             Values = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/03_scenario_data/global_model/motorEnergy/motorEnergy_IEA.npy'), # in %
                                                             Uncert=None,
                                                             Unit = '%')

ParameterDict['Segment_shares']= msc.Parameter(Name = 'Segment_shares',
                                                             ID = 3,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'g,s,c', #t=time, h=units
                                                             Values = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/03_scenario_data/global_model/vehicle_size/vehicleSize_motorEnergy_passengerCars.npy'), # in %
                                                             Uncert=None,
                                                             Unit = '%')

ParameterDict['Battery_chemistry_shares']= msc.Parameter(Name = 'Battery_chemistry_shares',
                                                             ID = 3,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'a,g,b,c', #t=time, h=units
                                                             Values = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/03_scenario_data/global_model/batteryChemistry/batteryChemistry_batteryScenarios.npy'), # in %
                                                             Uncert=None,
                                                             Unit = '%')



ParameterDict['Materials']= msc.Parameter(Name = 'Materials',
                                                             ID = 3,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'g,b,p,e', #t=time, h=units
                                                             Values = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/03_scenario_data/global_model/materialContent/matContent_motorEnergy_vehicleSize_batteryChemistry.npy'), # in kg 
                                                             Uncert=None,
                                                             Unit = '%')

ParameterDict['Capacity']= msc.Parameter(Name = 'Capacity',
                                                             ID = 3,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'b,p,c', #t=time, h=units
                                                             Values = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/03_scenario_data/global_model/batteryCapacity.npy'),
                                                             Uncert=None,
                                                             Unit = '%')


ParameterDict['Degradation']= msc.Parameter(Name = 'Degradation',
                                                             ID = 3,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'b,t,c', #t=time, h=units
                                                             Values = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/03_scenario_data/global_model/batteryCapacity/degradation.npy'),
                                                             Uncert=None,
                                                             Unit = '%')

ParameterDict['Battery_Weight']= msc.Parameter(Name = 'Battery_Weight',
                                                             ID = 3,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'g,s,b', #t=time, h=units
                                                             Values = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/03_scenario_data/global_model/batteryWeight/batteryWeight_motorEnergy_segment_batteryChemistry.npy'), # in kg
                                                             Uncert=None,
                                                             Unit = 'kg')
ParameterDict['Battery_Parts']= msc.Parameter(Name = 'Parts',
                                                             ID = 3,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'g,s,b,p', #t=time, h=units
                                                             Values = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/03_scenario_data/global_model/batteryParts/batteryParts_motorEnergy.npy'),
                                                             Uncert=None,
                                                             Unit = '%')

ParameterDict['Reuse_rate']= msc.Parameter(Name = 'Reuse',
                                                             ID = 3,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'R,b,t', #t=time, h=units
                                                             Values = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/03_scenario_data/global_model/recyclingRate/recycingRate_batteryChemistry_batteryPart_recyclingProcess_reuseScenario.npy'),
                                                             Uncert=None,
                                                             Unit = '%')

ParameterDict['Recycling_efficiency']= msc.Parameter(Name = 'Efficiency',
                                                             ID = 3,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'e,h', #t=time, h=units
                                                             Values = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/03_scenario_data/global_model/recycling_efficiencies/recyclingEfficiency_recyclingProcess.npy'),
                                                             Uncert=None,
                                                             Unit = '%')


ParameterDict['Storage_demand']= msc.Parameter(Name = 'Storage_demand',
                                                             ID = 3,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'E,t', #t=time, h=units
                                                             Values = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/03_scenario_data/global_model/energyStorage/demandStationaryStorage.npy'),
                                                             Uncert=None,
                                                             Unit = 'GWh')

MaTrace_System = msc.MFAsystem(Name = 'MaTrace_Vehicle_Fleet_Global', 
                      Geogr_Scope = 'Global', 
                      Unit = 'Vehicles', 
                      ProcessList = [], 
                      FlowDict = {}, 
                      StockDict = {},
                      ParameterDict = ParameterDict, 
                      Time_Start = Model_Time_Start, 
                      Time_End = Model_Time_End, 
                      IndexTable = IndexTable, 
                      Elements = IndexTable.loc['Element'].Classification.Items) # Initialize MFA system

# Add processes to system
for m in range(0, len(PrL_Number)):
    MaTrace_System.ProcessList.append(msc.Process(Name = PrL_Name[m], ID   = PrL_Number[m]))

# Define the flows of the system, and initialise their values:
# Define vehicle flows
MaTrace_System.FlowDict['F_2_3'] = msc.Flow(Name = 'Sold xEVs from retailer flowing into use phase', P_Start = 2, P_End = 3,
                                            Indices = 'z,S,r,g,s,t', Values=None)
MaTrace_System.FlowDict['F_3_4'] = msc.Flow(Name = 'Outflows from use phase to market', P_Start = 3, P_End = 4,
                                            Indices = 'z,S,r,g,s,t,c', Values=None)
MaTrace_System.StockDict['S_3']   = msc.Stock(Name = 'xEV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,r,g,s,t', Values=None)
MaTrace_System.StockDict['S_C_3']   = msc.Stock(Name = 'xEV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,r,g,s,t,c', Values=None)
MaTrace_System.StockDict['dS_3']  = msc.Stock(Name = 'xEV stock change', P_Res = 3, Type = 1,
                                              Indices = 'z,S,r,g,s,t', Values=None)


# Define battery flows in number of batteries
MaTrace_System.FlowDict['M_1_2'] = msc.Flow(Name = 'Batteries sold to vehicle manufacturer', P_Start = 1, P_End = 2,
                                            Indices = 'z,S,a,r,g,s,b,t', Values=None)
MaTrace_System.FlowDict['M_1_3'] = msc.Flow(Name = 'Batteries sold for replacement in in-use stock', P_Start = 1, P_End = 3,
                                            Indices = 'z,S,a,r,g,s,b,t', Values=None)
MaTrace_System.FlowDict['M_2_3'] = msc.Flow(Name = 'Batteries in sold vehicles', P_Start = 2, P_End = 3,
                                            Indices = 'z,S,a,r,g,s,b,t', Values=None)
MaTrace_System.FlowDict['M_3_4_tc'] = msc.Flow(Name = 'Outflows from batteries in vechiles from use phase by cohort', P_Start = 3, P_End = 4,
                                            Indices = 'z,S,a,r,g,s,b,t,c', Values=None)
MaTrace_System.FlowDict['M_3_4'] = msc.Flow(Name = 'Outflows from batteries in vechiles from use phase', P_Start = 3, P_End = 4,
                                            Indices = 'z,S,a,r,g,s,b,t', Values=None)
MaTrace_System.FlowDict['M_4_5'] = msc.Flow(Name = 'From of LIBs after vehicle has been dismantled', P_Start = 4, P_End = 5,
                                            Indices = 'z,S,a,r,g,s,b,t,c', Values=None)
MaTrace_System.FlowDict['M_3_5'] = msc.Flow(Name = 'Outflows of failed batteries', P_Start = 3, P_End = 5,
                                            Indices = 'z,S,a,r,g,s,b,t,c', Values=None)
MaTrace_System.FlowDict['M_5_3'] = msc.Flow(Name = 'Inflwos from battery reuse', P_Start = 5, P_End = 3,
                                            Indices = 'z,S,a,r,g,s,b,t', Values=None)
MaTrace_System.StockDict['M_3']   = msc.Stock(Name = 'xEV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,r,g,s,b,t', Values=None)
MaTrace_System.StockDict['M_C_3']   = msc.Stock(Name = 'xEV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,r,g,s,b,t,c', Values=None)
MaTrace_System.StockDict['dM_3']  = msc.Stock(Name = 'xEV stock change', P_Res = 3, Type = 1,
                                              Indices = 'z,S,a,r,g,s,b,t,c', Values=None)

# Define battery flows in weight of batteries
MaTrace_System.FlowDict['B_1_2'] = msc.Flow(Name = 'Batteries sold to vehicle manufacturer', P_Start = 1, P_End = 2,
                                            Indices = 'z,S,a,r,g,s,b,t', Values=None)
MaTrace_System.FlowDict['B_1_3'] = msc.Flow(Name = 'Batteries sold for replacement in in-use stock', P_Start = 1, P_End = 3,
                                            Indices = 'z,S,a,r,g,s,b,t', Values=None)
MaTrace_System.FlowDict['B_2_3'] = msc.Flow(Name = 'Batteries in sold vehicles', P_Start = 2, P_End = 3,
                                            Indices = 'z,S,a,r,g,s,b,t', Values=None)
MaTrace_System.FlowDict['B_3_4_tc'] = msc.Flow(Name = 'Outflows from batteries in vechiles from use phase by cohort', P_Start = 3, P_End = 4,
                                            Indices = 'z,S,a,r,g,s,b,t,c', Values=None)
MaTrace_System.FlowDict['B_3_4'] = msc.Flow(Name = 'Outflows from batteries in vechiles from use phase', P_Start = 3, P_End = 4,
                                            Indices = 'z,S,a,r,g,s,b,t', Values=None)
MaTrace_System.FlowDict['B_4_5'] = msc.Flow(Name = 'From of LIBs after vehicle has been dismantled', P_Start = 4, P_End = 5,
                                            Indices = 'z,S,a,r,g,s,b,t,c', Values=None)
MaTrace_System.FlowDict['B_3_5'] = msc.Flow(Name = 'Outflows of failed batteries', P_Start = 3, P_End = 5,
                                            Indices = 'z,S,a,r,g,s,b,t,c', Values=None)
MaTrace_System.FlowDict['B_5_3'] = msc.Flow(Name = 'Inflwos from battery reuse', P_Start = 5, P_End = 3,
                                            Indices = 'z,S,a,r,g,s,b,t', Values=None)
MaTrace_System.StockDict['B_3']   = msc.Stock(Name = 'Battery in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,r,g,s,b,t', Values=None)
MaTrace_System.StockDict['B_C_3']   = msc.Stock(Name = 'Battery in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,r,g,s,b,t,c', Values=None)
MaTrace_System.StockDict['dB_3']  = msc.Stock(Name = 'Battery stock change', P_Res = 3, Type = 1,
                                              Indices = 'z,S,a,r,g,s,b,t,c', Values=None)

## Flows to be used for battery parts
MaTrace_System.FlowDict['P_1_2'] = msc.Flow(Name = 'Batteries sold to vehicle manufacturer by part', P_Start = 1, P_End = 2,
                                            Indices = 'z,S,a,r,g,s,b,p,t', Values=None)
MaTrace_System.FlowDict['P_1_3'] = msc.Flow(Name = 'Batteries sold for replacement in in-use stock by part', P_Start = 1, P_End = 3,
                                            Indices = 'z,S,a,r,g,s,b,p,t', Values=None)
MaTrace_System.FlowDict['P_2_3'] = msc.Flow(Name = 'Batteries in sold vehicles by part', P_Start = 2, P_End = 3,
                                            Indices = 'z,S,a,r,g,s,b,p,t', Values=None)
MaTrace_System.FlowDict['P_3_4_tc'] = msc.Flow(Name = 'Outflows from batteries in vechiles from use phase by cohort by part', P_Start = 3, P_End = 4,
                                            Indices = 'z,S,a,r,g,s,b,p,t,c', Values=None)
MaTrace_System.FlowDict['P_3_4'] = msc.Flow(Name = 'Outflows from batteries in vechiles from use phase by part', P_Start = 3, P_End = 4,
                                            Indices = 'z,S,a,r,g,s,b,p,t', Values=None)
MaTrace_System.FlowDict['P_4_5'] = msc.Flow(Name = 'From of LIBs after vehicle has been dismantled by part', P_Start = 4, P_End = 5,
                                            Indices = 'z,S,a,r,g,s,b,p,t,c', Values=None)
MaTrace_System.FlowDict['P_3_5'] = msc.Flow(Name = 'Outflows of failed batteries by part', P_Start = 3, P_End = 5,
                                            Indices = 'z,S,a,r,g,s,b,p,t,c', Values=None)
MaTrace_System.FlowDict['P_5_3'] = msc.Flow(Name = 'Inflwos from battery reuse by part', P_Start = 5, P_End = 3,
                                            Indices = 'z,S,a,r,g,s,b,p,t', Values=None)
MaTrace_System.FlowDict['P_5_6'] = msc.Flow(Name = 'Reused batteries for stationary storage', P_Start = 5, P_End = 6,
                                            Indices = 'z,S,a,R,r,g,b,p,t,c', Values=None)
MaTrace_System.FlowDict['P_1_6'] = msc.Flow(Name = 'New batteries share for stationary storage', P_Start = 0, P_End = 6,
                                            Indices = 'z,S,a,R,r,g,b,p,t,c', Values=None) # Formerly P06
MaTrace_System.FlowDict['P_6_7'] = msc.Flow(Name = 'ELB collection', P_Start = 6, P_End = 7,
                                            Indices = 'z,S,a,R,r,b,p,t,c', Values=None)
MaTrace_System.FlowDict['P_7_8'] = msc.Flow(Name = 'Flow to recycling after stationary use', P_Start = 7, P_End = 8,
                                            Indices = 'z,S,a,R,r,b,p,t,c', Values=None)
MaTrace_System.FlowDict['P_5_8'] = msc.Flow(Name = 'Share being direcly recycled', P_Start = 5, P_End = 8,
                                            Indices = 'z,S,a,R,r,b,p,t,c', Values=None)


MaTrace_System.StockDict['P_3']   = msc.Stock(Name = 'Battery in-use stock by part', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,r,g,s,b,p,t', Values=None)
MaTrace_System.StockDict['P_C_3']   = msc.Stock(Name = 'Battery in-use stock by part', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,r,g,s,b,p,t,c', Values=None)
MaTrace_System.StockDict['dP_3']  = msc.Stock(Name = 'Battery stock change by part', P_Res = 3, Type = 1,
                                              Indices = 'z,S,a,r,g,s,b,p,t,c', Values=None)
MaTrace_System.StockDict['dP_6']  = msc.Stock(Name = 'Stock change of batteries in stationary storage', P_Res = 3, Type = 1,
                                              Indices = 'z,S,a,R,r,b,p,t,c', Values=None)
MaTrace_System.StockDict['P_6']   = msc.Stock(Name = 'Stock of batteries in stationary storage', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,r,b,p,t', Values=None)
MaTrace_System.StockDict['P_C_6']   = msc.Stock(Name = 'Stock of batteries in stationary storage by cohort', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,r,b,p,t,c', Values=None)

# Energy layer
MaTrace_System.StockDict['C_3']   = msc.Stock(Name = 'xEV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,r,g,b,t', Values=None)
MaTrace_System.StockDict['C_6']   = msc.Stock(Name = 'xEV in-use stock', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,r,b,t', Values=None)

## Flows to be used for materials
MaTrace_System.FlowDict['E_1_2'] = msc.Flow(Name = 'Materials sold to vehicle manufacturer by part', P_Start = 1, P_End = 2,
                                            Indices = 'z,S,a,r,p,e,t', Values=None)
MaTrace_System.FlowDict['E_1_3'] = msc.Flow(Name = 'Materials sold for replacement in in-use stock by part', P_Start = 1, P_End = 3,
                                            Indices = 'z,S,a,r,b,p,e,t', Values=None)
MaTrace_System.FlowDict['E_2_3'] = msc.Flow(Name = 'Materials in sold vehicles by part', P_Start = 2, P_End = 3,
                                            Indices = 'z,S,a,r,b,p,e,t', Values=None)
MaTrace_System.FlowDict['E_3_4'] = msc.Flow(Name = 'Outflows from batteries in vechiles from use phase by Materials', P_Start = 3, P_End = 4,
                                            Indices = 'z,S,a,r,b,p,e,t', Values=None)
MaTrace_System.FlowDict['E_4_5'] = msc.Flow(Name = 'From of LIBs after vehicle has been dismantled by Materials', P_Start = 4, P_End = 5,
                                            Indices = 'z,S,a,r,b,p,e,t', Values=None)
MaTrace_System.FlowDict['E_3_5'] = msc.Flow(Name = 'Outflows of failed batteries by Materials', P_Start = 3, P_End = 5,
                                            Indices = 'z,S,a,r,b,p,e,t', Values=None)
MaTrace_System.FlowDict['E_5_3'] = msc.Flow(Name = 'Inflwos from battery reuse by Materials', P_Start = 5, P_End = 3,
                                            Indices = 'z,S,a,r,b,p,e,t', Values=None)
MaTrace_System.FlowDict['E_5_6'] = msc.Flow(Name = 'Reused Materials for stationary storage', P_Start = 5, P_End = 6,
                                            Indices = 'z,S,a,R,r,b,p,e,t', Values=None)
MaTrace_System.FlowDict['E_1_6'] = msc.Flow(Name = 'New Materials share for stationary storage', P_Start = 0, P_End = 6,
                                            Indices = 'z,S,a,R,r,b,p,e,t', Values=None) # Formerly P06
MaTrace_System.FlowDict['E_6_7'] = msc.Flow(Name = 'Materials ELB collection', P_Start = 6, P_End = 7,
                                            Indices = 'z,S,a,R,r,b,p,e,t', Values=None)
MaTrace_System.FlowDict['E_7_8'] = msc.Flow(Name = 'Flow to recycling after stationary use', P_Start = 7, P_End = 8,
                                            Indices = 'z,S,a,R,r,b,p,e,t', Values=None)
MaTrace_System.FlowDict['E_5_8'] = msc.Flow(Name = 'Share being direcly recycled', P_Start = 5, P_End = 8,
                                            Indices = 'z,S,a,R,r,b,p,e,t', Values=None)
MaTrace_System.FlowDict['E_8_1'] = msc.Flow(Name = 'Secondary materials for battery produciton', P_Start = 8, P_End = 1,
                                            Indices = 'z,S,a,R,r,p,e,h,t', Values=None)
MaTrace_System.FlowDict['E_8_0'] = msc.Flow(Name = 'Secondary materials losses', P_Start = 8, P_End = 0,
                                            Indices = 'z,S,a,R,r,p,e,h,t', Values=None)
MaTrace_System.FlowDict['E_0_1'] = msc.Flow(Name = 'Promary materials for battery produciton', P_Start = 0, P_End = 1,
                                            Indices = 'z,S,a,R,r,p,e,h,t', Values=None)
MaTrace_System.FlowDict['E_primary_Inflows'] = msc.Flow(Name = 'Total inflows resulting from the sum of second hand and retailer sales', P_Start = 2, P_End = 3,
                                            Indices = 'z,S,a,R,r,e,p,t', Values=None) #zSarept
MaTrace_System.StockDict['E_3']   = msc.Stock(Name = 'xEV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,r,b,p,e,t', Values=None)
MaTrace_System.StockDict['Ed_3']  = msc.Stock(Name = 'xEV stock change', P_Res = 3, Type = 1,
                                              Indices = 'z,S,a,r,b,p,e,t', Values=None)
MaTrace_System.StockDict['E_6']   = msc.Stock(Name = 'xEV in-use stock', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,r,g,e,t', Values=None)

MaTrace_System.StockDict['Ed_6']  = msc.Stock(Name = 'xEV stock change', P_Res = 6, Type = 1,
                                              Indices = 'z,S,a,R,r,e,t', Values=None)

MaTrace_System.Initialize_FlowValues()  # Assign empty arrays to flows according to dimensions.
MaTrace_System.Initialize_StockValues() # Assign empty arrays to flows according to dimensions.



### Preparing SLB model
'''
To calculate the amount of batteries that can be reused, we look at the share of batteries that will still be 
useful for tau_cm amount of years according to the technical lifetime of the battery.
That share will go into second use. We then define an inflow driven model to calculate the stock dynamics there. 
Since the battery battery lifetime is the amount of time a battery is considered to be technically suitable for the
intended purpose, it makes sense that we use one technical lifetime for transportation and one for reuse criteria. 
For this reason, failed batteries in the in-use stock can still be considered for stationary applications. 
'''
# Define SLB model to calculate the desired sf function. The lt of the component here needs to be the same as the one defined above.
# tau_cm in this case will be the minimum amount of time a battery should be useful for to go into SLB
tau_cm = 5
lt_cm  = np.array([12])
sd_cm  = np.array([5])


# %%
r=5 #choose the regions to be calculated-. r is GLOBAL
cap = np.zeros((NS, Nr, Ng, Ns, Nb, Nt))
for z in range(Nz):
    #for r in range(0,Nr):
        for S in range(NS):
            for g in range(0,Ng):
                # In this case we assume that the product and component have the same lifetimes and set the delay as 3 years for both goods
                Model                                                     = pcm.ProductComponentModel(t = range(0,Nt), s_pr = MaTrace_System.ParameterDict['Vehicle_stock'].Values[z,r,:]/1000, lt_pr = {'Type': 'Normal', 'Mean': np.array([16]), 'StdDev': np.array([4]) }, \
                    lt_cm = {'Type': 'Normal', 'Mean': lt_cm, 'StdDev': sd_cm})
                Model.case_3()

                MaTrace_System.StockDict['S_C_3'].Values[z,S,r,g,:,:,:]             = np.einsum('sc,tc->stc', MaTrace_System.ParameterDict['Segment_shares'].Values[g,:,:] ,np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.sc_pr.copy()))
                MaTrace_System.StockDict['S_3'].Values[z,S,r,g,:,:]                 = np.einsum('stc->st', MaTrace_System.StockDict['S_C_3'].Values[z,S,r,g,:,:,:])
                MaTrace_System.FlowDict['F_2_3'].Values[z,S,r,g,:,:]              = np.einsum('sc,c->sc', MaTrace_System.ParameterDict['Segment_shares'].Values[g,:,:],np.einsum('c,c->c', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.i_pr.copy()))
                MaTrace_System.FlowDict['F_3_4'].Values[z,S,r,g,:,:,:]              = np.einsum('sc,tc->stc', MaTrace_System.ParameterDict['Segment_shares'].Values[g,:,:],np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:] , Model.oc_pr.copy()))
                

                ### Battery chemistry layer: Here we use the battery stock instead of the vehicle stock
                MaTrace_System.StockDict['M_C_3'].Values[z,S,:,r,g,:,:,:,:]     = np.einsum('abc,stc->asbtc', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , np.einsum('sc,tc->stc', MaTrace_System.ParameterDict['Segment_shares'].Values[g,:,:] \
                    ,np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.sc_cm.copy())))
                MaTrace_System.StockDict['M_3'].Values[z,S,:,r,g,:,:,:]         = np.einsum('asbtc->asbt', MaTrace_System.StockDict['M_C_3'].Values[z,S,:,r,g,:,:,:,:])
                # Battery inflows within car
                MaTrace_System.FlowDict['M_2_3'].Values[z,S,:,r,g,:,:,:]        = np.einsum('abt,st->asbt', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] ,MaTrace_System.FlowDict['F_2_3'].Values[z,S,r,g,:,:])
                # Battery replacements: Total battery inflows minus inflows of batteries in cars
                MaTrace_System.FlowDict['M_1_3'].Values[z,S,:,r,g,:,:,:]        = np.einsum('abt,st->asbt', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , np.einsum('sc,c->sc', MaTrace_System.ParameterDict['Segment_shares'].Values[g,:,:], \
                    np.einsum('c,c->c', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.i_cm.copy()))) - MaTrace_System.FlowDict['M_2_3'].Values[z,S,:,r,g,:,:,:]
                # Battery outflows in car
                MaTrace_System.FlowDict['M_3_4_tc'].Values[z,S,:,r,g,:,:,:,:]   = np.einsum('abc,stc->asbtc', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , MaTrace_System.FlowDict['F_3_4'].Values[z,S,r,g,:,:,:])
                MaTrace_System.FlowDict['M_3_4'].Values[z,S,:,r,g,:,:,:]        = np.einsum('asbtc->asbt', MaTrace_System.FlowDict['M_3_4_tc'].Values[z,S,:,r,g,:,:,:,:])
                # Batteries after vehicle has been dismantled
                MaTrace_System.FlowDict['M_4_5'].Values[z,S,:,r,g,:,:,:,:]      = MaTrace_System.FlowDict['M_3_4_tc'].Values[z,S,:,r,g,:,:,:,:] 
                # Battery outflows due to battery failures: Total battery outflows minus vehicle outflows
                

                ### Battery by weight layer: Multiply the numbers by the weight factor for each chemistry and size
                # Stocks
                MaTrace_System.StockDict['B_C_3'].Values[z,S,:,r,g,:,:,:,:]     = np.einsum('sb,asbtc->asbtc', MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:] , MaTrace_System.StockDict['M_C_3'].Values[z,S,:,r,g,:,:,:,:])
                MaTrace_System.StockDict['B_3'].Values[z,S,:,r,g,:,:,:]         = np.einsum('asbtc->asbt', MaTrace_System.StockDict['B_C_3'].Values[z,S,:,r,g,:,:,:,:])
                MaTrace_System.FlowDict['B_1_3'].Values[z,S,:,r,g,:,:,:]        = np.einsum('asbt,sb->asbt', MaTrace_System.FlowDict['M_1_3'].Values[z,S,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:])
                MaTrace_System.FlowDict['B_2_3'].Values[z,S,:,r,g,:,:,:]        = np.einsum('asbt,sb->asbt', MaTrace_System.FlowDict['M_2_3'].Values[z,S,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:])
                MaTrace_System.FlowDict['B_3_4_tc'].Values[z,S,:,r,g,:,:,:,:]   = np.einsum('asbtc,sb->asbtc', MaTrace_System.FlowDict['M_3_4_tc'].Values[z,S,:,r,g,:,:,:,:], MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:])
                MaTrace_System.FlowDict['B_3_4'].Values[z,S,:,r,g,:,:,:]        = np.einsum('asbtc->asbt', MaTrace_System.FlowDict['B_3_4_tc'].Values[z,S,:,r,g,:,:,:,:] )
                MaTrace_System.FlowDict['B_4_5'].Values[z,S,:,r,g,:,:,:,:]      = MaTrace_System.FlowDict['B_3_4_tc'].Values[z,S,:,r,g,:,:,:,:] 
                MaTrace_System.FlowDict['B_5_3'].Values[z,S,:,r,g,:,:,:]        = np.einsum('asbt,sb->asbt', MaTrace_System.FlowDict['M_5_3'].Values[z,S,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:])
                

                ### Battery parts layer
                MaTrace_System.StockDict['P_C_3'].Values[z,S,:,r,g,:,:,:,:,:]   = np.einsum('sbp,asbtc->asbptc', MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:] , MaTrace_System.StockDict['B_C_3'].Values[z,S,:,r,g,:,:,:,:])
                MaTrace_System.StockDict['P_3'].Values[z,S,:,r,g,:,:,:,:]       = np.einsum('asbptc->asbpt', MaTrace_System.StockDict['P_C_3'].Values[z,S,:,r,g,:,:,:,:,:])
                MaTrace_System.FlowDict['P_1_3'].Values[z,S,:,r,g,:,:,:,:]      = np.einsum('asbc,sbp->asbpc', MaTrace_System.FlowDict['B_1_3'].Values[z,S,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:]) 
                MaTrace_System.FlowDict['P_2_3'].Values[z,S,:,r,g,:,:,:,:]      = np.einsum('asbc,sbp->asbpc', MaTrace_System.FlowDict['B_2_3'].Values[z,S,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:]) 
                MaTrace_System.FlowDict['P_3_4_tc'].Values[z,S,:,r,g,:,:,:,:,:] = np.einsum('asbtc,sbp->asbptc', MaTrace_System.FlowDict['B_3_4_tc'].Values[z,S,:,r,g,:,:,:,:], MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:])
                MaTrace_System.FlowDict['P_3_4'].Values[z,S,:,r,g,:,:,:,:]      = np.einsum('asbptc->asbpt', MaTrace_System.FlowDict['P_3_4_tc'].Values[z,S,:,r,g,:,:,:,:,:])
                MaTrace_System.FlowDict['P_4_5'].Values[z,S,:,r,g,:,:,:,:,:]    = MaTrace_System.FlowDict['P_3_4_tc'].Values[z,S,:,r,g,:,:,:,:,:]
                MaTrace_System.FlowDict['P_5_3'].Values[z,S,:,r,g,:,:,:,:]      = np.einsum('asbt,sbp->asbpt', MaTrace_System.FlowDict['B_5_3'].Values[z,S,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:])
                
                '''
                We calculate the flows of battery modules into reuse. Sicne the casing and other battery parts are assumed to go directly into recyling, 
                we just write this loop for the modules with index 0 and separately define that all other battery parts go to recycling. 
                We also consider batteries that caused vehicle outflows, as the requirements here are lower. We can take them out if it does not make sense. 

                The reuse parameter does not indicate the share of batteries that are reused. Rather, it is a condition to reflect decisions on which battery chemistries to 
                reuse. LFP scenario for instance will define that only LFP chemistries are considered for reuse, but they health assessment still needs to happen. 
                '''
                # Calculate inflows to SLB only for the modules. We consider batteries that came from failed vehicles as well, since flow P_3_5 only contains failed batteries
                MaTrace_System.FlowDict['P_5_6'].Values[z,S,:,:,r,g,:,0,:,:]  = np.einsum('Rbt,asbtc->aRbtc', MaTrace_System.ParameterDict['Reuse_rate'].Values[:,:,:], \
                    MaTrace_System.FlowDict['P_3_4_tc'].Values[z,S,:,r,g,:,:,0,:,:]) # * Model_slb.sf_cm[t+tau_cm,c] + MaTrace_System.FlowDict['P_3_5'].Values[z,S,:,r,g,:,:,0,t,c]* Model_slb.sf_cm[t+tau_cm,c]) # TODO: Possibly subtract P_5_3 flow if implemented
                '''
                Since the batteries are moving from being used in transport to being used in stationary storage, the "lifetime" is no longer the same. 
                In transportation, we define the lifetime to be the time that the battery is still useful for that purpose, which is widely considered
                to be until it reaches 80% of its initial capacity. The distribution of the lifetime helps us account for batteries that are more 
                intensely used than others, but by the time of outflow they should all have more or less the same capacity of around 80%. 

                Therefore, the remaining second life can be approximated with a normal distribution that would have an initial capacity of 80% and would
                follow its own degradation curve.  
                '''
# Computing SLB stock after aggregating inflows
Model_slb                                                       = pcm.ProductComponentModel(t = range(0,Nt),  lt_cm = {'Type': 'Normal', 'Mean': lt_cm, 'StdDev': sd_cm})
# Compute the survival curve of the batteries with the additional lenght for the last tau years

'''
Define the SLB model in advance. We do not compute everything using the dsm as it only takes i as input
and takes too long to compute. Instead, we define the functions ourselves using the sf computed with dsm. 
'''
lt_slb                               = np.array([6]) # We could have different lifetimes for the different chemistries
sd_slb                               = np.array([2]) 
inflows                             = np.zeros((Nz,NS, Na, NR, Nb, Nt))
inflows = np.einsum('zSaRgbtc->zSaRbt',MaTrace_System.FlowDict['P_5_6'].Values[:,:,:,:,r,:,:,0,:,:])
for z in range(Nz):
    for S in range(NS):
        for a in range(Na):
            for R in range(NR):
                for b in range(Nb):
                    slb_model                        = dsm.DynamicStockModel(t=range(0,Nt), lt={'Type': 'Normal', 'Mean': lt_slb, 'StdDev': sd_slb}, i=inflows[z,S,a,R,b,:])
                    slb_model.compute_s_c_inflow_driven()
                    slb_model.compute_o_c_from_s_c()
                    slb_model.compute_stock_total()
                    MaTrace_System.StockDict['P_C_6'].Values[z,S,a,R,r,b,0,:,:] = slb_model.s_c.copy()
                    MaTrace_System.FlowDict['P_6_7'].Values[z,S,a,R,r,b,0,:,:] = slb_model.o_c.copy()
'''
We will leave this other approach for the moment
MaTrace_System.StockDict['P_C_6'].Values[:,:,:,:,r,:,0,:,:]     = np.einsum('zSaRbt,tc->zSaRbtc', np.einsum('zSaRgbtc->zSaRbt',MaTrace_System.FlowDict['P_5_6'].Values[:,:,:,:,r,:,:,0,:,:]), slb_model.sf)
# Compute SLB outflows
MaTrace_System.FlowDict['P_6_7'].Values[:,:,:,:,r,:,0,1::,:]    = -1 * np.diff(MaTrace_System.StockDict['P_C_6'].Values[:,:,:,:,r,:,0,:,:], n=1, axis=5) # Difference over time -> axis=3
for t in range(Nt):
    MaTrace_System.FlowDict['P_6_7'].Values[:,:,:,:,r,:,0,t,t]  = np.einsum('zSaRgbtc->zSaRb',MaTrace_System.FlowDict['P_5_6'].Values[:,:,:,:,r,:,:,0,:,:]) - MaTrace_System.StockDict['P_C_6'].Values[:,:,:,:,r,:,0,t,t]
'''
# Compute total stock
MaTrace_System.StockDict['P_6'].Values[:,:,:,:,r,:,0,:]         = np.einsum('zSaRbtc->zSaRbt', MaTrace_System.StockDict['P_C_6'].Values[:,:,:,:,r,:,0,:,:])
MaTrace_System.FlowDict['P_7_8'].Values[:,:,:,:,r,:,0,:,:]                  = MaTrace_System.FlowDict['P_6_7'].Values[:,:,:,:,r,:,0,:,:]
# Calculate battery parts going directly to recycling: Total outflows minus reuse
for R in range(NR):
    MaTrace_System.FlowDict['P_5_8'].Values[:,:,:,R,r,:,:,:,:]            =  np.einsum('zSagsbptc->zSabptc', MaTrace_System.FlowDict['P_3_4_tc'].Values[:,:,:,r,:,:,:,:,:,:]) - np.einsum('zSagbptc->zSabptc',MaTrace_System.FlowDict['P_5_6'].Values[:,:,:,R,r,:,:,:,:,:])

### Material layer
MaTrace_System.StockDict['E_3'].Values[:,:,:,r,:,:,:,:]           = np.einsum('zSagsbpt,gbpe->zSabpet', MaTrace_System.StockDict['P_3'].Values[:,:,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:])
MaTrace_System.FlowDict['E_1_3'].Values[:,:,:,r,:,:,:,:]          = np.einsum('zSagsbpc,gbpe->zSabpec', MaTrace_System.FlowDict['P_1_3'].Values[:,:,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
MaTrace_System.FlowDict['E_2_3'].Values[:,:,:,r,:,:,:,:]          = np.einsum('zSagsbpc,gbpe->zSabpec', MaTrace_System.FlowDict['P_2_3'].Values[:,:,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
MaTrace_System.FlowDict['E_3_4'].Values[:,:,:,r,:,:,:,:]          = np.einsum('zSagsbpt,gbpe->zSabpet', MaTrace_System.FlowDict['P_3_4'].Values[:,:,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
MaTrace_System.FlowDict['E_4_5'].Values[:,:,:,r,:,:,:]            = MaTrace_System.FlowDict['E_3_4'].Values[z,S,:,r,:,:,:,:]
MaTrace_System.FlowDict['E_3_5'].Values[:,:,:,r,:,:,:,:]          = np.einsum('zSagsbptc,gbpe->zSabpet', MaTrace_System.FlowDict['P_3_5'].Values[:,:,:,r,:,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
MaTrace_System.FlowDict['E_5_3'].Values[:,:,:,r,:,:,:,:]          = np.einsum('zSagsbpt,gbpe->zSabpet', MaTrace_System.FlowDict['P_5_3'].Values[:,:,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
MaTrace_System.FlowDict['E_5_6'].Values[:,:,:,:,r,:,:,:,:]        = np.einsum('zSaRgbptc,gbpe->zSaRbpet', MaTrace_System.FlowDict['P_5_6'].Values[:,:,:,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
MaTrace_System.FlowDict['E_5_8'].Values[:,:,:,:,r,:,:,:,:]        = np.einsum('zSaRbptc,gbpe->zSaRbpet', MaTrace_System.FlowDict['P_5_8'].Values[:,:,:,:,r,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
MaTrace_System.FlowDict['E_6_7'].Values[:,:,:,:,r,:,:,:,:]        = np.einsum('zSaRbptc,gbpe->zSaRbpet', MaTrace_System.FlowDict['P_6_7'].Values[:,:,:,:,r,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
MaTrace_System.FlowDict['E_7_8'].Values[:,:,:,:,r,:,:,:,:]        = np.einsum('zSaRbptc,gbpe->zSaRbpet', MaTrace_System.FlowDict['P_7_8'].Values[:,:,:,:,r,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 


# Solving energy layer: Multiply stocks with capacity and degradation parameters
MaTrace_System.StockDict['C_3'].Values[:,:,:,:,:,:,:] = np.einsum('zSargsbptc, btc->zSargbt', np.einsum('zSargsbptc, bpc -> zSargsbptc', MaTrace_System.StockDict['P_C_3'].Values[:,:,:,:,:,:,:], MaTrace_System.ParameterDict['Capacity'].Values[:,:,:]),  MaTrace_System.ParameterDict['Degradation'].Values[:,:,:])
MaTrace_System.StockDict['C_6'].Values[:,:,:,:,:,:,:] = np.einsum('zSaRrbptc, btc->zSaRrbt', np.einsum('zSaRrbptc, bpc -> zSaRrbptc', MaTrace_System.StockDict['P_C_6'].Values[:,:,:,:,:,:,:,:,:], MaTrace_System.ParameterDict['Capacity'].Values[:,:,:]),  MaTrace_System.ParameterDict['Degradation'].Values[:,:,:])


MaTrace_System.FlowDict['E_8_1'].Values[:,:,:,:,r,:,:,:,:] = np.einsum('eh, zSaRbpet->zSaRpeht', MaTrace_System.ParameterDict['Recycling_efficiency'].Values[:,:], (MaTrace_System.FlowDict['E_7_8'].Values[:,:,:,:,r,:,:,:,:] + MaTrace_System.FlowDict['E_5_8'].Values[:,:,:,:,r,:,:,:,:]))
for R in range(NR):
    for h in range(Nh):
        MaTrace_System.FlowDict['E_0_1'].Values[:,:,:,R,r,:,:,h,:] = np.einsum('zSabpet->zSapet', MaTrace_System.FlowDict['E_2_3'].Values[:,:,:,r,:,:,:,:]) - MaTrace_System.FlowDict['E_8_1'].Values[:,:,:,R,r,:,:,h,:]# Solving recycling loop
# %%
# # Exporting vehicle flows
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/vehicle_stock_array', np.einsum('zSrgst->zSrgt', MaTrace_System.StockDict['S_3'].Values[:,:,:,:,:,:]), allow_pickle=True)
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/vehicle_outflow_array', np.einsum('zSrgstc->zSrgt', MaTrace_System.FlowDict['F_3_4'].Values[:,:,:,:,:,:,:]), allow_pickle=True)
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/vehicle_inflow_array', np.einsum('zSrgst->zSrgt', MaTrace_System.FlowDict['F_2_3'].Values[:,:,:,:,:,:]), allow_pickle=True)

# # Exporting battery flows
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/battery_inflow_array', np.einsum('zSargsbpt->zSarbpt', MaTrace_System.FlowDict['P_2_3'].Values[:,:,:,:,:,:,:,:,:]), allow_pickle=True) # z,S,a,r,g,s,b,p,t
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/battery_outflow_array', np.einsum('zSargsbpt->zSarbpt', MaTrace_System.FlowDict['P_3_4'].Values[:,:,:,:,:,:,:,:,:]), allow_pickle=True) # z,S,a,r,g,s,b,p,t
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/battery_reuse_array', np.einsum('zSaRrgbptc->zSaRrbpt', MaTrace_System.FlowDict['P_5_6'].Values[:,:,:,:,:,:,:,:,:,:]), allow_pickle=True) # z,S,a,R,r,g,s,b,p,t,c
# # np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/battery_reuse_to_recycling_array',  MaTrace_System.FlowDict['P_6_7'].Values[:,:,:,:,:,:,:,:], allow_pickle=True) # zSaRrbpt
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/battery_recycling_array',  np.einsum('zSaRrbptc->zSaRrbpt' ,MaTrace_System.FlowDict['P_5_8'].Values[:,:,:,:,:,:,:,:,:]), allow_pickle=True)
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/slb_stock_array', MaTrace_System.StockDict['P_6'].Values[:,:,:,:,:,:,:,:], allow_pickle=True) # z,S,a,R,r,g,s,b,p,t,c


# # Exporting material flows
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_inflow_array',  MaTrace_System.FlowDict['E_0_1'].Values[:,:,:,:,:,:,:,:,:], allow_pickle=True) # zSaRrpet
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_outflow_array', np.einsum('zSarbpet->zSarept', MaTrace_System.FlowDict['E_3_4'].Values[:,:,:,:,:,:,:,:]), allow_pickle=True) # z,S,a,r,g,s,b,p,e,t
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_reuse_array', np.einsum('zSaRrbpet->zSaRrept', MaTrace_System.FlowDict['E_5_6'].Values[:,:,:,:,:,:,:,:,:]), allow_pickle=True) # z,S,a,R,r,g,s,b,p,e,t,cnp.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_reuse_to_recycling_array',  MaTrace_System.FlowDict['E_6_7'].Values[:,:,:,:,:,:,:,:], allow_pickle=True) # zSaRrpet
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_recycling_array',  np.einsum('zSaRrbpet->zSaRrept' ,MaTrace_System.FlowDict['E_5_8'].Values[:,:,:,:,:,:,:,:,:]), allow_pickle=True)
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_recycled_process_array', np.einsum('zSaRrpeht->zSaRrepht', MaTrace_System.FlowDict['E_8_1'].Values[:,:,:,:,:,:,:,:,:]), allow_pickle=True)
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_losses_array', np.einsum('zSaRrpeht->zSaRrept', MaTrace_System.FlowDict['E_8_0'].Values[:,:,:,:,:,:,:,:,:]), allow_pickle=True)

# ### Exporting Equinor data
# np.save('/Users/fernaag/Box/BATMAN/Partners/Equinor/material_demand_NCX', np.einsum('rgsbpet->et', MaTrace_System.FlowDict['E_1_3'].Values[1,1,0,:,:,:,:,:,:,70:]/1000000)) # Demand
# np.save('/Users/fernaag/Box/BATMAN/Partners/Equinor/material_demand_LFP', np.einsum('rgsbpet->et', MaTrace_System.FlowDict['E_1_3'].Values[1,1,1,:,:,:,:,:,:,70:]/1000000)) # Demand
# np.save('/Users/fernaag/Box/BATMAN/Partners/Equinor/average_recycled_content',  (np.einsum('rpeht->et', MaTrace_System.FlowDict['E_8_1'].Values[1,1,0,1,:,:,:,:,70:])/1000000 / np.einsum('rgsbpet->et', MaTrace_System.FlowDict['E_1_3'].Values[1,1,0,:,:,:,:,:,:,70:]/1000000) + \
#         np.einsum('rpeht->et', MaTrace_System.FlowDict['E_8_1'].Values[1,1,1,1,:,:,:,:,70:]/1000000)/np.einsum('rgsbpet->et', MaTrace_System.FlowDict['E_1_3'].Values[1,1,1,:,:,:,:,:,:,70:]/1000000))/2*100) # Maximum available materials
# # Set color cycles
# #MaTrace_System.FlowDict['E_8_1'] = msc.Flow(Name = 'Secondary materials for battery produciton', P_Start = 8, P_End = 1,
# #                                            Indices = 'z,S,a,R,r,p,e,h,t', Values=None)
from cycler import cycler
import seaborn as sns
r=5
custom_cycler = cycler(color=sns.color_palette('Set2', 20)) #'Set2', 'Paired', 'YlGnBu'
#%%
def results_Sofia():
    # Exporting results for Sofia
    # Baseline values for the stock
    stock  = pd.DataFrame({'Stock':np.einsum('st->t', MaTrace_System.StockDict['S_3'].Values[1,1,r,1,:,:])/1000})
    # Baseline values for inflows
    inflow = pd.DataFrame({'Inflow':np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[1,1,r,1,:,:])/1000})
    #Baseline values for outflows
    outflow= pd.DataFrame({'Outflow':np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[1,1,r,1,:,:])/1000})
    # Export version
    Model_output = pd.concat([stock, inflow, outflow], axis=1)
    Model_output.set_index(np.arange(1950,2051),inplace=True)
    Model_output.to_excel('/Users/fernaag/Library/CloudStorage/Box-Box/Teaching/Master_Students/Sofia Genovesi/Model_Output.xlsx')

def plots():
    for j, z in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Stock_Scenarios')].Items):
        for i, S in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Scenario')].Items):
            ### Outflows per DT
            ### Stock per DT
            fig, ax = plt.subplots(figsize=(8,7))
            ax.set_prop_cycle(custom_cycler)
            ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                        np.einsum('gst->gt',MaTrace_System.StockDict['S_3'].Values[j,i,r,:,:,55::]/1000000))
            #ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], MaTrace_System.ParameterDict['Vehicle_stock'].Values[i,r,55::])
            ax.set_ylabel('Nr. of Vehicles [billion]',fontsize =18)
            right_side = ax.spines["right"]
            right_side.set_visible(False)
            top = ax.spines["top"]
            top.set_visible(False)
            ax.legend(MaTrace_System.IndexTable['Classification']['Good'].Items, loc='upper left',prop={'size':15})
            ax.set_title('Stock per drive train {} scenario'.format(S), fontsize=20)
            ax.set_xlabel('Year',fontsize =16)
            #ax.set_ylim([0,5])
            ax.tick_params(axis='both', which='major', labelsize=18)
            fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/Stock_per_DT'.format(z,S))       

            fig, ax = plt.subplots(figsize=(8,7))
            ax.set_prop_cycle(custom_cycler)
            ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                        np.einsum('gstc->gt', MaTrace_System.FlowDict['F_3_4'].Values[j,i,r,:,:,55::,:]/1000)) 
            ax.set_ylabel('Outflows [million]',fontsize =18)
            right_side = ax.spines["right"]
            right_side.set_visible(False)
            top = ax.spines["top"]
            top.set_visible(False)
            ax.legend(MaTrace_System.IndexTable['Classification']['Good'].Items, loc='upper left',prop={'size':15})
            ax.set_title('Vehicle outflows per drive train {} scenario'.format(S), fontsize=20)
            ax.set_xlabel('Year',fontsize =18)
            ax.tick_params(axis='both', which='major', labelsize=15)
            fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/Outflows_per_DT'.format(z,S))


            ### Inflows per DT
            fig, ax = plt.subplots(figsize=(8,7))
            ax.set_prop_cycle(custom_cycler)
            ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                        np.einsum('gst->gt', MaTrace_System.FlowDict['F_2_3'].Values[j,i,r,:,:,55:]/1000))
            ax.set_ylabel('Nr. of Vehicles [million]',fontsize =16)
            right_side = ax.spines["right"]
            right_side.set_visible(False)
            top = ax.spines["top"]
            top.set_visible(False)
            ax.legend(MaTrace_System.IndexTable['Classification']['Good'].Items, loc='upper left',prop={'size':15})
            ax.set_title('Inflows per drive train {} scenario'.format(S), fontsize=16)
            ax.set_xlabel('Year',fontsize =16)
            ax.tick_params(axis='both', which='major', labelsize=15)
            fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/Inflows_per_DT'.format(z,S))

            # Energy storage needs
            fig, ax = plt.subplots(figsize=(8,7))
            ax.set_prop_cycle(custom_cycler)
            ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65:], 
                        MaTrace_System.ParameterDict['Storage_demand'].Values[0,65:])
            ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65:], 
                        MaTrace_System.ParameterDict['Storage_demand'].Values[1,65:])
            ax.set_ylabel('GWh',fontsize =16)
            right_side = ax.spines["right"]
            right_side.set_visible(False)
            top = ax.spines["top"]
            top.set_visible(False)
            ax.legend(['IRENA base', 'IRENA renewable energy'], loc='upper left',prop={'size':16})
            ax.set_title('Demand for energy storage', fontsize=16)
            ax.set_xlabel('Year',fontsize =16)
            ax.tick_params(axis='both', which='major', labelsize=15)
            fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/overview/Storage_range')

            ### Stock per DT and S
            for g in range(0,Ng):
                fig, ax = plt.subplots(figsize=(8,7))
                ax.set_prop_cycle(custom_cycler)
                ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                            MaTrace_System.StockDict['S_3'].Values[j,i,r,g,:,55::]/1000)
                right_side = ax.spines["right"]
                right_side.set_visible(False)
                top = ax.spines["top"]
                top.set_visible(False)
                ax.set_ylabel('Nr. of Vehicles [million]',fontsize =18)
                ax.legend(MaTrace_System.IndexTable['Classification']['Size'].Items, loc='upper left',prop={'size':15})
                ax.set_title('{} stock per segment'.format(MaTrace_System.IndexTable['Classification']['Good'].Items[g]), fontsize=20)
                ax.set_xlabel('Year',fontsize =18)
                ax.tick_params(axis='both', which='major', labelsize=15)
                fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/{}_stock_per_S'.format(z,S, MaTrace_System.IndexTable['Classification']['Good'].Items[g]))

            ### Stock per battery part
            fig, ax = plt.subplots(figsize=(8,7))
            ax.set_prop_cycle(custom_cycler)
            ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                        np.einsum('sbpt->pt', MaTrace_System.StockDict['P_3'].Values[j,i,0,r,1,:,:,:,55::]/1000000))
            right_side = ax.spines["right"]
            right_side.set_visible(False)
            top = ax.spines["top"]
            top.set_visible(False)
            ax.set_ylabel('Weight [Mt]',fontsize =18)
            ax.legend(MaTrace_System.IndexTable['Classification']['Battery_Parts'].Items, loc='upper left',prop={'size':15})
            ax.set_title('Battery weight stock per part', fontsize=20)
            ax.set_xlabel('Year',fontsize =18)
            ax.tick_params(axis='both', which='major', labelsize=15)
            fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/Stock_BEV_per_part'.format(z,S))

            

            ### SLB stock
            for a,k in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Chemistry_Scenarios')].Items):
                fig, ax = plt.subplots(figsize=(8,7))
                ax.set_prop_cycle(custom_cycler)
                ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                            [MaTrace_System.StockDict['P_6'].Values[j,i,a,0,r,b,0,55::]/1000000 for b in np.einsum('rbt->b', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,:,1,:,70:]).nonzero()[0].tolist()])
                #ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], MaTrace_System.ParameterDict['Vehicle_stock'].Values[i,r,55::]) #z,S,a,R,r,b,p,t
                ax.set_ylabel('Modules [kt]',fontsize =18)
                right_side = ax.spines["right"]
                right_side.set_visible(False)
                top = ax.spines["top"]
                top.set_visible(False)
                ax.legend([MaTrace_System.IndexTable['Classification']['Battery_Chemistry'].Items[i] for i in np.einsum('rbt->b', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,:,1,:,70:]).nonzero()[0].tolist()], loc='upper left',prop={'size':15})
                ax.set_title('SLB sotck per chemistry {} {} scenario'.format(S, k), fontsize=20)
                ax.set_xlabel('Year',fontsize =16)
                #ax.set_ylim([0,5])
                ax.tick_params(axis='both', which='major', labelsize=18)
                fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/SLB_stock_chemistry_{}'.format(z,S,k))

            # ### Stock in weight per material
            for a, b in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Chemistry_Scenarios')].Items):
            ########### Energy Layer #############

                ### BEV capacity 
                fig, ax = plt.subplots(figsize=(12,8))
                ax.set_prop_cycle(custom_cycler)
                ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[71:], 
                            [MaTrace_System.StockDict['C_3'].Values[j,i,a,r,1,x,71:]/1000000 for x in np.einsum('rbt->b', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,:,1,:,70:]).nonzero()[0].tolist()]) #
                ax.set_ylabel('Capacity [TWh]',fontsize =16)
                right_side = ax.spines["right"]
                right_side.set_visible(False)
                top = ax.spines["top"]
                top.set_visible(False)
                ax.legend([MaTrace_System.IndexTable['Classification']['Battery_Chemistry'].Items[x] for x in np.einsum('rbt->b', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,:,1,:,70:]).nonzero()[0].tolist()], loc='upper left',prop={'size':10})
                ax.set_title('Capacity of BEV Fleet {}'.format(b), fontsize=16)
                ax.set_xlabel('Year', fontsize =16)
                ax.tick_params(axis='both', which='major', labelsize=15)
                ax.tick_params(axis='x', which='major', rotation=90)
                fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/BEV_capacity_{}_scenario'.format(z,S, b))
                ### Available capacity SLB

                for w, R in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Reuse_Scenarios')].Items):
                    fig, ax = plt.subplots(figsize=(12,8))
                    ax.set_prop_cycle(custom_cycler)
                    ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[71:], 
                                [MaTrace_System.StockDict['C_6'].Values[j,i,a,w,r,x,71:]/1000 for x in np.einsum('rbt->b', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,:,1,:,70:]).nonzero()[0].tolist()]) 
                    ax.set_ylabel('SLB Energy Capacity [GWh]',fontsize =16)
                    right_side = ax.spines["right"]
                    right_side.set_visible(False)
                    top = ax.spines["top"]
                    top.set_visible(False)
                    ax.legend([MaTrace_System.IndexTable['Classification']['Battery_Chemistry'].Items[x] for x in np.einsum('rbt->b', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,:,1,:,70:]).nonzero()[0].tolist()], loc='upper left',prop={'size':10})
                    ax.set_title('Energy availability SLB {} {}'.format(b, R), fontsize=16)
                    ax.set_xlabel('Year',fontsize =16)
                    ax.tick_params(axis='both', which='major', labelsize=15)
                    ax.tick_params(axis='x', which='major', rotation=90)
                    fig.show()
                    fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/SLB_capacity_{}_{}_scenario'.format(z,S, b, R))

            #     fig, ax = plt.subplots(figsize=(8,7))
            #     ax.set_prop_cycle(custom_cycler)
            #     ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
            #                 np.moveaxis(np.einsum('rgsbpet->et', MaTrace_System.StockDict['E_3'].Values[j,i,a,:,:,:,:,:,:,55:]),0,1))
            #     right_side = ax.spines["right"]
            #     right_side.set_visible(False)
            #     top = ax.spines["top"]
            #     top.set_visible(False)
            #     ax.set_ylabel('Weight [Mt]',fontsize =18)
            #     ax.legend(MaTrace_System.IndexTable['Classification']['Element'].Items, loc='upper left',prop={'size':15})
            #     ax.set_title('Material stock {} scenario'.format(b), fontsize=20)
            #     ax.set_xlabel('Year',fontsize =18)
            #     ax.tick_params(axis='both', which='major', labelsize=15)
            #     fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/Material_stock_{}_scenario'.format(z,S, b))

            #     # Material inflows
            #     fig, ax = plt.subplots(figsize=(8,7))
            #     ax.set_prop_cycle(custom_cycler)
            #     ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
            #                 np.moveaxis(np.einsum('rgsbpet->et', MaTrace_System.FlowDict['E_1_3'].Values[j,i,a,:,:,:,:,:,:,55:]/1000000), 1,0))
            #     right_side = ax.spines["right"]
            #     right_side.set_visible(False)
            #     top = ax.spines["top"]
            #     top.set_visible(False)
            #     ax.set_ylabel('Weight [Mt]',fontsize =18)
            #     ax.legend(MaTrace_System.IndexTable['Classification']['Element'].Items, loc='upper left',prop={'size':15})
            #     ax.set_title('Material demand {} scenario'.format(b), fontsize=20)
            #     ax.set_xlabel('Year',fontsize =18)
            #     ax.tick_params(axis='both', which='major', labelsize=15)
            #     fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/Material_demand_{}_scenario'.format(z,S, b))

            #     # Weight stock
            #     fig, ax = plt.subplots(figsize=(8,7))
            #     ax.set_prop_cycle(custom_cycler)
            #     ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
            #                 np.moveaxis(np.einsum('rgsbpet->et', MaTrace_System.FlowDict['E_1_3'].Values[j,i,a,:,:,:,:,:,:,55:]/1000000), 1,0))
            #     right_side = ax.spines["right"]
            #     right_side.set_visible(False)
            #     top = ax.spines["top"]
            #     top.set_visible(False)
            #     ax.set_ylabel('Weight [Mt]',fontsize =18)
            #     ax.legend(MaTrace_System.IndexTable['Classification']['Element'].Items, loc='upper left',prop={'size':15})
            #     ax.set_title('Material demand {} scenario'.format(b), fontsize=20)
            #     ax.set_xlabel('Year',fontsize =18)
            #     ax.tick_params(axis='both', which='major', labelsize=15)
            #     fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/Material_demand_{}_scenario'.format(z,S, b))

                ### Stock per chemistry BEV
                fig, ax = plt.subplots(figsize=(8,7))
                ax.set_prop_cycle(custom_cycler)
                ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], 
                            [np.einsum('rst->t', MaTrace_System.StockDict['M_3'].Values[j,i,a,:,1,:,k,70:]/1000) for k in np.einsum('rbt->b', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,:,1,:,70:]).nonzero()[0].tolist()], linewidth=0)
                ax.set_ylabel('Nr. of Vehicles [million]',fontsize =16)
                right_side = ax.spines["right"]
                right_side.set_visible(False)
                top = ax.spines["top"]
                top.set_visible(False)
                ax.legend([MaTrace_System.IndexTable['Classification']['Battery_Chemistry'].Items[k] for k in np.einsum('rbt->b', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,:,1,:,70:]).nonzero()[0].tolist()], loc='upper left',prop={'size':10})
                ax.set_title('BEV stock by chemistry {} scenario'.format(b), fontsize=16)
                ax.set_xlabel('Year',fontsize =16)
                ax.tick_params(axis='both', which='major', labelsize=15)
                fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/Stock_BEV_per_chemistry_{}_scenario'.format(z,S,b))

            
    #         # Sensitivity to lifetime
            fig, ax = plt.subplots(figsize=(8,7))
            ax.set_prop_cycle(custom_cycler)
            material_set3 = np.array([0,6,7])
            right_side = ax.spines["right"]
            right_side.set_visible(False)
            top = ax.spines["top"]
            top.set_visible(False)
            ax.set_ylabel('Maximum recycled content [%]',fontsize =18)
            #ax.legend(['Li', 'Si', 'Mn', 'Co'], loc='upper left',prop={'size':15})
            ax.set_title('Recycled content for Ni dominated scenario', fontsize=20)
            ax.set_xlabel('Year',fontsize =18)
            ax.tick_params(axis='both', which='major', labelsize=15)
            for i, e in enumerate(material_set3):
                    if e == 0:
                            ax.plot([2030, 2035], [4, 10], 'bx',label='Li targets',markersize=8)
                    if e == 6:
                            ax.plot([2030, 2035], [12, 20], 'gx',label='Co targets',markersize=8)
                    if e == 7:
                            ax.plot([2030, 2035], [4, 12], 'r*',label='Ni targets',markersize=8)

                    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[j,1,0,2,:,:,e,1
                    ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[j,1,0,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[j,1,0,:,:,:,e,70:])/1000000)*100, label='{} with reuse'.format(IndexTable.Classification[IndexTable.index.get_loc('Element')].Items[e]),linewidth=3.0)
                    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[j,1,0,1,:,:,e,1
                    ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[j,1,0,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[j,1,0,:,:,:,e,70:])/1000000)*100, label='{} no reuse'.format(IndexTable.Classification[IndexTable.index.get_loc('Element')].Items[e]),linewidth=3.0)
                    ax.legend(loc='upper left',prop={'size':13})
                    fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/Recycled_content_lifetime'.format(z, S))
    # Sensitivity to recycling technology
            fig, ax = plt.subplots(figsize=(8,7))
            ax.set_prop_cycle(custom_cycler)
            material_set3 = np.array([0,6,7])
            right_side = ax.spines["right"]
            right_side.set_visible(False)
            top = ax.spines["top"]
            top.set_visible(False)
            ax.set_ylabel('Maximum recycled content [%]',fontsize =18)
            #ax.legend(['Li', 'Si', 'Mn', 'Co'], loc='upper left',prop={'size':15})
            ax.set_title('Recycled content for LFP dominated scenario no reuse', fontsize=20)
            ax.set_xlabel('Year',fontsize =18)
            ax.tick_params(axis='both', which='major', labelsize=15)
            for i, e in enumerate(material_set3):
                    if e == 0:
                            ax.plot([2030, 2035], [4, 10], 'x',label='Li targets',markersize=8)
                    if e == 6:
                            ax.plot([2030, 2035], [12, 20], 'x',label='Co targets',markersize=8)
                    if e == 7:
                            ax.plot([2030, 2035], [4, 12], '*',label='Ni targets',markersize=8)

                    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[j,1,1,1,:,:,e,0
                    ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[j,1,1,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[j,1,1,:,:,:,e,70:])/1000000)*100, label='{} Direct'.format(IndexTable.Classification[IndexTable.index.get_loc('Element')].Items[e]),linewidth=3.0)
                    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[j,1,1,1,:,:,e,1
                    ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[j,1,1,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[j,1,1,:,:,:,e,70:])/1000000)*100, label='{} Hydromet.'.format(IndexTable.Classification[IndexTable.index.get_loc('Element')].Items[e]),linewidth=3.0)
                    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[j,1,1,1,:,:,e,2
                    ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[j,1,1,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[j,1,1,:,:,:,e,70:])/1000000)*100, label='{} Pyromet'.format(IndexTable.Classification[IndexTable.index.get_loc('Element')].Items[e]),linewidth=3.0)
                    ax.legend(loc='upper left',prop={'size':13})
                    fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/Recycled_content_recycling_process'.format(z, S))

def rec_content_tech():
    # Sensitivity to technology development
    from cycler import cycler
    import seaborn as sns
    z = 1 
    S = 1
    h = 1
    rec_cycler = cycler(color=sns.color_palette('tab20c', 20)) #'Set2', 'Paired', 'YlGnBu'
    alt_cycler = (cycler(color=['maroon','brown', 'red', 'coral', 'midnightblue', 'navy','blue', 'cornflowerblue', 'darkgreen', 'green', 'yellowgreen', 'lawngreen']) *
          cycler(linestyle=['-']))

    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(rec_cycler)
    material_set3 = np.array([0,6,7])
    right_side = ax.spines["right"]
    right_side.set_visible(False)
    top = ax.spines["top"]
    top.set_visible(False)
    ax.set_ylabel('Maximum recycled content [%]',fontsize =18)
    #ax.legend(['Li', 'Si', 'Mn', 'Co'], loc='upper left',prop={'size':15})
    ax.set_title('Recycled content for different chemistries', fontsize=20)
    ax.set_xlabel('Year',fontsize =18)
    ax.tick_params(axis='both', which='major', labelsize=15)
    for i, e in enumerate(material_set3):
        if e == 0:
                ax.plot([2030, 2035], [4, 10], 'd',label='Li targets',markersize=8)
        if e == 6:
                ax.plot([2030, 2035], [12, 20], 'x',label='Co targets',markersize=8)
        if e == 7:
                ax.plot([2030, 2035], [4, 12], '*',label='Ni targets',markersize=8)

        ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,0,1,:,:,e,h
        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,0,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,0,:,:,:,e,70:])/1000000)*100, label='{} Ni-rich (NCX)'.format(IndexTable.Classification[IndexTable.index.get_loc('Element')].Items[e]),linewidth=2)
        ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,1,1,:,:,e,h
        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,1,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,1,:,:,:,e,70:])/1000000)*100, label='{} LFP'.format(IndexTable.Classification[IndexTable.index.get_loc('Element')].Items[e]),linewidth=2)
        ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,2,1,:,:,e,h
        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,2,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,2,:,:,:,e,70:])/1000000)*100, label='{} Next generation'.format(IndexTable.Classification[IndexTable.index.get_loc('Element')].Items[e]),linewidth=2)
        ax.legend(loc='upper left',prop={'size':13})
        ax.set_ylim([0,100])
        #ax.set_xlim([2020,2040])
        #ax.xaxis.set_ticks(np.arange(2020, 2041, 5))
        fig.savefig(os.getcwd() + '/results/overview/rec_content_chemistries')

def rec_content_lifetime():
    # Sensitivity to technology development
    from cycler import cycler
    import seaborn as sns
    z = 1 
    S = 1
    h = 1
    rec_cycler = cycler(color=sns.color_palette('tab20c', 20)) #'Set2', 'Paired', 'YlGnBu'
    alt_cycler = (cycler(color=['maroon','brown', 'red', 'coral', 'midnightblue', 'navy','blue', 'cornflowerblue', 'darkgreen', 'green', 'yellowgreen', 'lawngreen']) *
          cycler(linestyle=['-']))
    custom_cycler = cycler(color=sns.color_palette('Paired', 20)) #'Set2', 'Paired', 'YlGnBu'
    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(custom_cycler)
    material_set3 = np.array([0,6,7])
    right_side = ax.spines["right"]
    right_side.set_visible(False)
    top = ax.spines["top"]
    top.set_visible(False)
    ax.set_ylabel('Maximum recycled content [%]',fontsize =18)
    #ax.legend(['Li', 'Si', 'Mn', 'Co'], loc='upper left',prop={'size':15})
    ax.set_title('Recycled content for Ni dominated scenario', fontsize=20)
    ax.set_xlabel('Year',fontsize =18)
    ax.tick_params(axis='both', which='major', labelsize=15)
    for i, e in enumerate(material_set3):
            if e == 0:
                    ax.plot([2030, 2035], [4, 10], 'bx',label='Li targets',markersize=8)
            if e == 6:
                    ax.plot([2030, 2035], [12, 20], 'gx',label='Co targets',markersize=8)
            if e == 7:
                    ax.plot([2030, 2035], [4, 12], 'r*',label='Ni targets',markersize=8)

            ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[j,1,0,2,:,:,e,1
            ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[j,1,0,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[j,1,0,:,:,:,e,70:])/1000000)*100, label='{} with reuse'.format(IndexTable.Classification[IndexTable.index.get_loc('Element')].Items[e]),linewidth=3.0)
            ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[j,1,0,1,:,:,e,1
            ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[j,1,0,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[j,1,0,:,:,:,e,70:])/1000000)*100, label='{} no reuse'.format(IndexTable.Classification[IndexTable.index.get_loc('Element')].Items[e]),linewidth=3.0)
            ax.legend(loc='upper left',prop={'size':13})
    fig.savefig(os.getcwd() + '/results/overview/rec_content_chemistries')

def rec_content_strategies():
    from cycler import cycler
    import seaborn as sns
    e13_replacements = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E13_case6.npy')
    e23_replacements = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E23_case6.npy')
    e81_replacements = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E81_case6.npy')
    bau = MaTrace_System.FlowDict['E_0_1'].Values[1,1,6,0,r,:,:,1,:].sum(axis=0)

    z = 1 
    S = 1
    h = 1
    a = 6
    e = 7 # Ni
    R = 0
    rec_cycler = cycler(color=sns.color_palette('Set2', 20)) #'Set2', 'Paired', 'YlGnBu'
    alt_cycler = (cycler(color=['maroon','brown', 'red', 'coral', 'midnightblue', 'navy','blue', 'cornflowerblue', 'darkgreen', 'green', 'yellowgreen', 'lawngreen']) *
          cycler(linestyle=['-']))

    fig, ax = plt.subplots(3,1, figsize=(15,20))
    ax[0].set_prop_cycle(rec_cycler)
    right_side = ax[0].spines["right"]
    right_side.set_visible(False)
    top = ax[0].spines["top"]
    top.set_visible(False)
    ax[0].set_ylabel('Maximum recycled content [%]',fontsize =18)
    #ax.legend(['Li', 'Si', 'Mn', 'Co'], loc='upper left',prop={'size':15})
    ax[0].set_title('a) Recycled content for Ni', fontsize=20)
    ax[0].set_xlabel('Year',fontsize =18)
    ax[0].tick_params(axis='both', which='major', labelsize=15)
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
    ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, linewidth=2)
    
    a=1 # shift to LFP
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
    ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, linewidth=2)
    
    a = 6
    R = 2 # All reuse
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
    ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, linewidth=2)
    
    R = 1 # Baseline
    z=0
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
    ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, '--', linewidth=2)
    
    z = 1 # Baseline
    h=0
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
    ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, linewidth=2)
    
    h=1
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
    ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, linewidth=2)
    
    
    ax[0].plot([2030, 2035], [4, 12], 'r*', markersize=8)
    
    ax[0].legend(['Business as usual', 'Shift to LFP', 'Reuse', 'Fleet reduction', 'Direct recycling', 'Replacements and reuse', 'EU targets'], loc='upper left',prop={'size':13})
    ax[0].set_ylim([0,100])
    ax[0].set_xlim([2020,2040])
    ax[0].xaxis.set_ticks(np.arange(2020, 2041, 5))
    
    ##### Plotting Co
    z = 1 
    S = 1
    h = 1
    a = 6
    e = 6 # Co
    R = 0
    ax[1].set_prop_cycle(rec_cycler)
    right_side = ax[1].spines["right"]
    right_side.set_visible(False)
    top = ax[1].spines["top"]
    top.set_visible(False)
    ax[1].set_ylabel('Maximum recycled content [%]',fontsize =18)
    #ax.legend(['Li', 'Si', 'Mn', 'Co'], loc='upper left',prop={'size':15})
    ax[1].set_title('b) Recycled content for Co', fontsize=20)
    ax[1].set_xlabel('Year',fontsize =18)
    ax[1].tick_params(axis='both', which='major', labelsize=15)
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
    ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, linewidth=2)
    
    a=1 # shift to LFP
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
    ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, linewidth=2)
    
    a = 6
    R = 2 # All reuse
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
    ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, linewidth=2)
    
    R = 1 # Baseline
    z=0
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
    ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, '--', linewidth=2)
    
    z = 1 # Baseline
    h=0
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
    ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, linewidth=2)
    
    h=1
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
    ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, linewidth=2)
    
    ax[1].plot([2030, 2035], [12, 20], 'r*', markersize=8)
    
    ax[1].legend(['Business as usual', 'Shift to LFP', 'Reuse', 'Fleet reduction', 'Direct recycling', 'Replacements and reuse', 'EU targets'], loc='upper left',prop={'size':13})
    ax[1].set_ylim([0,100])
    ax[1].set_xlim([2020,2040])
    ax[1].xaxis.set_ticks(np.arange(2020, 2041, 5))
    
    ##### Plotting Li
    z = 1 
    S = 1
    h = 1
    a = 6
    e = 0 # Co
    R = 0
    ax[2].set_prop_cycle(rec_cycler)
    right_side = ax[2].spines["right"]
    right_side.set_visible(False)
    top = ax[2].spines["top"]
    top.set_visible(False)
    ax[2].set_ylabel('Maximum recycled content [%]',fontsize =18)
    #ax.legend(['Li', 'Si', 'Mn', 'Co'], loc='upper left',prop={'size':15})
    ax[2].set_title('c) Recycled content for Li', fontsize=20)
    ax[2].set_xlabel('Year',fontsize =18)
    ax[2].tick_params(axis='both', which='major', labelsize=15)
    ax[2].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
    ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, linewidth=2)
    
    a=1 # shift to LFP
    ax[2].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
    ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100,':', linewidth=2)
    
    a = 6
    R = 2 # All reuse
    ax[2].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
    ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, linewidth=2)
    
    R = 1 # Baseline
    z=0
    ax[2].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
    ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, '--', linewidth=2)
    
    z = 1 # Baseline
    h=0
    ax[2].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
    ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, linewidth=2)
    
    h=1
    ax[2].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
    ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, linewidth=2)
    
    ax[2].plot([2030, 2035], [4, 10], 'r*', markersize=8)
    
    ax[2].legend(['Business as usual', 'Shift to LFP', 'Reuse', 'Fleet reduction', 'Direct recycling',  'Replacements and reuse', 'EU targets'], loc='upper left',prop={'size':13})
    ax[2].set_ylim([0,100])
    ax[2].set_xlim([2020,2040])
    ax[2].xaxis.set_ticks(np.arange(2020, 2041, 5))
    
    fig.savefig(os.getcwd() + '/results/overview/rec_content_strategies', dpi=300)

def flows():
    fig, ax = plt.subplots(1,2, figsize=(17,8))
    ax[0].set_prop_cycle(custom_cycler)
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[0,0,r,1,:,55:]/1000), 'y--', label='Low STEP')
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[1,0,r,1,:,55:]/1000), 'yx', label='Medium STEP')
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[2,0,r,1,:,55:]/1000), 'y.', label='High STEP')
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[0,1,r,1,:,55:]/1000), 'b--', label='Low SD')
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[1,1,r,1,:,55:]/1000), 'bx', label='Medium SD')
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[2,1,r,1,:,55:]/1000), 'b.', label='High SD')
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[0,2,r,1,:,55:]/1000), 'r--', label='Low Net Zero')
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[1,2,r,1,:,55:]/1000), 'rx', label='Medium Net Zero')
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[2,2,r,1,:,55:]/1000), 'r.', label='High Net Zero')
    ax[0].set_ylabel('Nr. of Vehicles [million]',fontsize =18)
    right_side = ax[0].spines["right"]
    right_side.set_visible(False)
    top = ax[0].spines["top"]
    top.set_visible(False)
    ax[0].legend(loc='upper left',prop={'size':16})
    ax[0].set_title('a) Yearly new vehicle registrations', fontsize=20)
    ax[0].set_xlabel('Year',fontsize =18)
    ax[0].tick_params(axis='both', which='major', labelsize=16)
    ax[0].set_ylim([0,700])
    ax[0].set_xlim([2015,2050])
    ax[0].grid()
    
    ax[1].set_prop_cycle(custom_cycler)
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[0,0,r,1,:,55:,:]/1000), 'y--', label='Low STEP')
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[2,0,r,1,:,55:,:]/1000), 'y.', label='High STEP')
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[1,0,r,1,:,55:,:]/1000), 'yx', label='Medium STEP')
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[0,1,r,1,:,55:,:]/1000), 'b--', label='Low SD')
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[1,1,r,1,:,55:,:]/1000), 'bx', label='Medium SD')
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[2,1,r,1,:,55:,:]/1000), 'b.', label='High SD')
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[0,2,r,1,:,55:,:]/1000), 'r--', label='Low Net Zero')
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[1,2,r,1,:,55:,:]/1000), 'rx', label='Medium Net Zero')
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[2,2,r,1,:,55:,:]/1000), 'r.', label='High Net Zero')
    ax[1].set_ylabel('Nr. of Vehicles [million]',fontsize =18)
    right_side = ax[1].spines["right"]
    right_side.set_visible(False)
    top = ax[1].spines["top"]
    top.set_visible(False)
    ax[1].legend(loc='upper left',prop={'size':16})
    ax[1].set_title('b) Yearly vehicle outflows', fontsize=20)
    ax[1].set_xlabel('Year',fontsize =18)
    ax[1].tick_params(axis='both', which='major', labelsize=16)
    ax[1].set_ylim([0,700])
    ax[1].set_xlim([2015,2050])
    ax[1].grid()
    fig.savefig(os.getcwd() + '/results/overview/system_flows', dpi=300)

def slb_stock():
    ### SLB stock
    #for a,k in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Chemistry_Scenarios')].Items):
    #custom_cycler = cycler(color=sns.color_palette('tab30', 20)) #'Set2', 'Paired', 'YlGnBu'
    from matplotlib import cm
    from matplotlib.colors import ListedColormap
    yellow = cm.get_cmap('Wistia', 3)# combine it all
    blue = cm.get_cmap('Blues', 3)# combine it all
    red = cm.get_cmap('Reds', 3)# combine it all
    newcolors = np.vstack((yellow(np.linspace(0, 1, 3)),
                       blue(np.linspace(0, 1, 3)),
                        red(np.linspace(0, 1, 3))))# create a new colormaps with a name of OrangeBlue
    a = 0 # Just use a baseline chemistry NCX
    R = 2 # All reused scenario
    z = 0
    S = 0
    fig, ax = plt.subplots(figsize=(8,7))
    #ax.pcolormesh(cmap=slb_cycle)
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000 ,\
                    0, color = 'y', alpha = 0.3, label='Low STEP')
    last = MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000
    z=1
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000 ,\
                    last, color = 'y', alpha = 0.6, label='Medium STEP')
    last = MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000
    z=2
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000 ,\
                    last, color = 'y', alpha = 0.9, label='High STEP')
    last = MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000
    z=0
    S=1
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000 ,\
                    last, color = 'b', alpha = 0.3, label='Low SD')
    last = MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000
    z=1
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000 ,\
                    last, color = 'b', alpha = 0.6, label='Medium SD')
    last = MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000
    z=2
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000 ,\
                    last, color = 'b', alpha = 0.9, label='High SD')
    last = MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000
    z=0
    S=2
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000 ,\
                    last, color = 'r', alpha = 0.3, label='Low Net Zero')
    last = MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000
    z=1
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000 ,\
                    last, color = 'r', alpha = 0.6, label='Medium Net Zero')
    last = MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000
    z=2
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000 ,\
                    last, color = 'r', alpha = 0.9, label='High Net Zero')
    
    ax.set_ylabel('Modules [kt]',fontsize =18) 
    
    # Adding capacity
    ax2 = ax.twinx()
    ax2.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['C_6'].Values[z,S,a,R,r,:,55::].sum(axis=0)/1000000, color = 'r')
    ax2.set_ylim(0)
    ax2.set_ylabel('Capacity [TWh]',fontsize =18)
    ax.set_ylim(0)
    right_side = ax.spines["right"]
    right_side.set_visible(False)
    top = ax.spines["top"]
    top.set_visible(False)
    ax.legend(loc='upper left',prop={'size':15})
    ax.set_title('SLB stock in weight and capacity', fontsize=20)
    ax.set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax.tick_params(axis='both', which='major', labelsize=18)
    ax2.tick_params(axis='y', which='major', labelsize=18)
    ax.set_xlim([2015, 2050])
    fig.savefig(os.getcwd() + '/results/overview/slb_stock')

def slb_capacity():
    ### SLB stock
    #for a,k in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Chemistry_Scenarios')].Items):
    #custom_cycler = cycler(color=sns.color_palette('tab30', 20)) #'Set2', 'Paired', 'YlGnBu'
    from matplotlib import cm
    from matplotlib.colors import ListedColormap
    yellow = cm.get_cmap('Wistia', 3)# combine it all
    blue = cm.get_cmap('Blues', 3)# combine it all
    red = cm.get_cmap('Reds', 3)# combine it all
    newcolors = np.vstack((yellow(np.linspace(0, 1, 3)),
                       blue(np.linspace(0, 1, 3)),
                        red(np.linspace(0, 1, 3))))# create a new colormaps with a name of OrangeBlue
    a = 0 # Just use a baseline chemistry NCX
    R = 2 # All reused scenario
    z = 0
    S = 0
    fig, ax = plt.subplots(figsize=(8,7))
    #ax.pcolormesh(cmap=slb_cycle)
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['C_6'].Values[z,S,a,R,r,:,55::].sum(axis=0)/1000000 ,\
                    0, color = 'y', alpha = 0.3)
    last = MaTrace_System.StockDict['C_6'].Values[z,S,a,R,r,:,55::].sum(axis=0)/1000000
    z=1
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['C_6'].Values[z,S,a,R,r,:,55::].sum(axis=0)/1000000 ,\
                    last, color = 'y', alpha = 0.6)
    last = MaTrace_System.StockDict['C_6'].Values[z,S,a,R,r,:,55::].sum(axis=0)/1000000
    z=2
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['C_6'].Values[z,S,a,R,r,:,55::].sum(axis=0)/1000000 ,\
                    last, color = 'y', alpha = 0.9)
    last = MaTrace_System.StockDict['C_6'].Values[z,S,a,R,r,:,55::].sum(axis=0)/1000000
    z=0
    S=1
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['C_6'].Values[z,S,a,R,r,:,55::].sum(axis=0)/1000000 ,\
                    last, color = 'b', alpha = 0.3)
    last = MaTrace_System.StockDict['C_6'].Values[z,S,a,R,r,:,55::].sum(axis=0)/1000000
    z=1
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['C_6'].Values[z,S,a,R,r,:,55::].sum(axis=0)/1000000 ,\
                    last, color = 'b', alpha = 0.6)
    last = MaTrace_System.StockDict['C_6'].Values[z,S,a,R,r,:,55::].sum(axis=0)/1000000
    z=2
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['C_6'].Values[z,S,a,R,r,:,55::].sum(axis=0)/1000000 ,\
                    last, color = 'b', alpha = 0.9)
    last = MaTrace_System.StockDict['C_6'].Values[z,S,a,R,r,:,55::].sum(axis=0)/1000000
    z=0
    S=2
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['C_6'].Values[z,S,a,R,r,:,55::].sum(axis=0)/1000000 ,\
                    last, color = 'r', alpha = 0.3)
    last = MaTrace_System.StockDict['C_6'].Values[z,S,a,R,r,:,55::].sum(axis=0)/1000000
    z=1
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['C_6'].Values[z,S,a,R,r,:,55::].sum(axis=0)/1000000 ,\
                    last, color = 'r', alpha = 0.6)
    last = MaTrace_System.StockDict['C_6'].Values[z,S,a,R,r,:,55::].sum(axis=0)/1000000
    z=2
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['C_6'].Values[z,S,a,R,r,:,55::].sum(axis=0)/1000000 ,\
                    last, color = 'r', alpha = 0.9)
    ax.set_ylabel('Modules [TWh]',fontsize =18)
    right_side = ax.spines["right"]
    right_side.set_visible(False)
    top = ax.spines["top"]
    top.set_visible(False)
    ax.legend([], loc='upper left',prop={'size':15})
    ax.set_title('SLB stock in weight and capacity', fontsize=20)
    ax.set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax.tick_params(axis='both', which='major', labelsize=18)
    ax.set_xlim([2015, 2050])
    fig.savefig(os.getcwd() + '/results/overview/slb_stock', dpi=300)

def chemistry_scenarios():
    
    from cycler import cycler
    import seaborn as sns
    r=5
    custom_cycler = cycler(color=sns.color_palette('Paired', 20)) #'Set2', 'Paired', 'YlGnBu'

    for a,b in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Chemistry_Scenarios')].Items):
        fig, ax = plt.subplots(figsize=(8,7))
        ax.set_prop_cycle(custom_cycler)
        ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], 
                    [ MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,1,i,70:] for i in np.einsum('bt->b', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,1,:,70:]).nonzero()[0].tolist()]) # We only select the chemistries that are included in the given model run
        ax.set_ylabel('Share [%]',fontsize =16)
        right_side = ax.spines["right"]
        right_side.set_visible(False)
        top = ax.spines["top"]
        top.set_visible(False)
        ax.legend([MaTrace_System.IndexTable['Classification']['Battery_Chemistry'].Items[i] for i in np.einsum('bt->b', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,1,:,70:]).nonzero()[0].tolist()], loc='best',prop={'size':10})
        ax.set_title('Chemistry shares {} scenario'.format(b), fontsize=16)
        ax.set_xlabel('Year',fontsize =16)
        ax.tick_params(axis='both', which='major', labelsize=15)
        
def strategies_comparative():
    from cycler import cycler
    import seaborn as sns
    r=5
    custom_cycler = cycler(color=sns.color_palette('Set2', 20)) #'Set2', 'Paired', 'YlGnBu'
    # Load replacement results
    e01_replacements = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E01_case6.npy')
        # Define storylines
    bau = MaTrace_System.FlowDict['E_0_1'].Values[1,1,6,0,r,:,:,1,:].sum(axis=0)
    fig, ax = plt.subplots(4,2,figsize=(20,28))
    ax[0,0].set_prop_cycle(custom_cycler)
    e = 7 # Ni
    z = 1 # Baseline
    S = 1 # Baseline
    a = 6 # BNEF
    R = 0 # LFP reuse
    h = 1 # Hydrometallurgical
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, linewidth=4)
    a = 1 # High LFP
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    a = 6 # BNEF
    R = 2 # All reuse
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    R = 0 # LFP reused
    z = 0 # Low
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    z = 1 # Low
    h = 0 # Direct
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    h = 1 # Hydrometallurgy
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000)
    ax[0,0].set_ylabel('Primary Ni demand [Mt]',fontsize =18)
    right_side = ax[0,0].spines["right"]
    right_side.set_visible(False)
    top = ax[0,0].spines["top"]
    top.set_visible(False)
    ax[0,0].legend(['Business as usual', 'Shift to LFP', 'Second-life', 'Fleet reduction', 'Efficient recycling', 'Replacements and reuse'], loc='upper left',prop={'size':15})
    ax[0,0].set_title('a) Nickel', fontsize=20)
    ax[0,0].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[0,0].tick_params(axis='both', which='major', labelsize=18)

    ## Plot Li
    ax[0,1].set_prop_cycle(custom_cycler)
    e = 0 # Li
    z = 1 # Baseline
    S = 1 # Baseline
    a = 6 # BNEF
    R = 0 # LFP reuse
    h = 1 # Hydrometallurgical
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, linewidth=4)
    a = 1 # High LFP

    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    a = 6 # BNEF
    R = 2 # All reuse
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    R = 0 # LFP reused
    z = 0 # Low
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    z = 1 # Low
    h = 0 # Direct
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    h = 1 # Hydro
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000)
    ax[0,1].set_ylabel('Primary Li demand [Mt]',fontsize =18)
    right_side = ax[0,1].spines["right"]
    right_side.set_visible(False)
    top = ax[0,1].spines["top"]
    top.set_visible(False)
    ax[0,1].legend(['Business as usual', 'Shift to LFP', 'Second-life', 'Fleet reduction', 'Efficient recycling', 'Replacements and reuse'], loc='upper left',prop={'size':15})
    ax[0,1].set_title('b) Lithium', fontsize=20)
    ax[0,1].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[0,1].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot Co
    ax[1,0].set_prop_cycle(custom_cycler)
    e = 6 # Co
    z = 1 # Baseline
    S = 1 # Baseline
    a = 6 # BNEF
    R = 0 # LFP reuse
    h = 1 # Hydrometallurgical
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, linewidth=4)
    a = 1 # High LFP
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    a = 6 # BNEF
    R = 2 # All reuse
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    R = 0 # LFP reused
    z = 0 # Low
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    z = 1 # Low
    h = 0 # Direct
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    h = 1 # Hydro
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000)
    ax[1,0].set_ylabel('Primary Co demand [Mt]',fontsize =18)
    right_side = ax[1,0].spines["right"]
    right_side.set_visible(False)
    top = ax[1,0].spines["top"]
    top.set_visible(False)
    ax[1,0].legend(['Business as usual', 'Shift to LFP', 'Second-life', 'Fleet reduction', 'Efficient recycling', 'Replacements and reuse'], loc='upper left',prop={'size':15})
    ax[1,0].set_title('c) Cobalt', fontsize=20)
    ax[1,0].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[1,0].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot P
    ax[1,1].set_prop_cycle(custom_cycler)
    e = 4 # P
    z = 1 # Baseline
    S = 1 # Baseline
    a = 6 # BNEF
    R = 0 # LFP reuse
    h = 1 # Hydrometallurgical
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, linewidth=4)
    a = 1 # High LFP
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    a = 6 # BNEF
    R = 2 # All reuse
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    R = 0 # LFP reused
    z = 0 # Low
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    z = 1 # Low
    h = 0 # Direct
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    h = 1 # Direct
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000)
    ax[1,1].set_ylabel('Primary P demand [Mt]',fontsize =18)
    right_side = ax[1,1].spines["right"]
    right_side.set_visible(False)
    top = ax[1,1].spines["top"]
    top.set_visible(False)
    ax[1,1].legend(['Business as usual', 'Shift to LFP', 'Second-life', 'Fleet reduction', 'Efficient recycling', 'Replacements and reuse'], loc='upper left',prop={'size':15})
    ax[1,1].set_title('d) Phosphorous', fontsize=20)
    ax[1,1].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[1,1].tick_params(axis='both', which='major', labelsize=18)

    ## Plot Al
    ax[2,0].set_prop_cycle(custom_cycler)
    e = 2 # Al
    z = 1 # Baseline
    S = 1 # Baseline
    a = 6 # BNEF
    R = 0 # LFP reuse
    h = 1 # Hydrometallurgical
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, linewidth=4)
    a = 1 # High LFP
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    a = 6 # BNEF
    R = 2 # All reuse
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    R = 0 # LFP reused
    z = 0 # Low
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    z = 1 # Low
    h = 0 # Direct
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    h = 1 # Hydro
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000)
    ax[2,0].set_ylabel('Primary Al demand [Mt]',fontsize =18)
    right_side = ax[2,0].spines["right"]
    right_side.set_visible(False)
    top = ax[2,0].spines["top"]
    top.set_visible(False)
    ax[2,0].legend(['Business as usual', 'Shift to LFP', 'Second-life', 'Fleet reduction', 'Efficient recycling', 'Replacements and reuse'], loc='upper left',prop={'size':15})
    ax[2,0].set_title('e) Aluminium', fontsize=20)
    ax[2,0].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[2,0].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot Graphite
    ax[2,1].set_prop_cycle(custom_cycler)
    e = 1 # Graphite
    z = 1 # Baseline
    S = 1 # Baseline
    a = 6 # BNEF
    R = 0 # LFP reuse
    h = 1 # Hydrometallurgical
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, linewidth=4)
    a = 1 # High LFP
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    a = 6 # BNEF
    R = 2 # All reuse
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    R = 0 # LFP reused
    z = 0 # Low
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    z = 1 # Low
    h = 0 # Direct
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    h = 1 # Hydro
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000)
    ax[2,1].set_ylabel('Primary Graphite demand [Mt]',fontsize =18)
    right_side = ax[2,1].spines["right"]
    right_side.set_visible(False)
    top = ax[2,1].spines["top"]
    top.set_visible(False)
    ax[2,1].legend(['Business as usual', 'Shift to LFP', 'Second-life', 'Fleet reduction', 'Efficient recycling', 'Replacements and reuse'], loc='upper left',prop={'size':15})
    ax[2,1].set_title('f) Graphite', fontsize=20)
    ax[2,1].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[2,1].tick_params(axis='both', which='major', labelsize=18)
    
    
    ## Plot Mn
    ax[3,0].set_prop_cycle(custom_cycler)
    e = 5 # Mn
    z = 1 # Baseline
    S = 1 # Baseline
    a = 6 # BNEF
    R = 0 # LFP reuse
    h = 1 # Hydrometallurgical
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, linewidth=4)
    a = 1 # High LFP
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    a = 6 # BNEF
    R = 2 # All reuse
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    R = 0 # LFP reused
    z = 0 # Low
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    z = 1 # Low
    h = 0 # Direct
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    h = 1 # Hydro
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000)
    ax[3,0].set_ylabel('Primary Mn demand [Mt]',fontsize =18)
    right_side = ax[3,0].spines["right"]
    right_side.set_visible(False)
    top = ax[3,0].spines["top"]
    top.set_visible(False)
    ax[3,0].legend(['Business as usual', 'Shift to LFP', 'Second-life', 'Fleet reduction', 'Efficient recycling', 'Replacements and reuse'], loc='upper left',prop={'size':15})
    ax[3,0].set_title('g) Manganese', fontsize=20)
    ax[3,0].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[3,0].tick_params(axis='both', which='major', labelsize=18)
    
    
    ## Plot Si
    ax[3,1].set_prop_cycle(custom_cycler)
    e = 3 # Si
    z = 1 # Baseline
    S = 1 # Baseline
    a = 6 # BNEF
    R = 0 # LFP reuse
    h = 1 # Hydrometallurgical
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, linewidth=4)
    a = 1 # High LFP
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    a = 6 # BNEF
    R = 2 # All reuse
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    R = 0 # LFP reused
    z = 0 # Low
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    z = 1 # Low
    h = 0 # Direct
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000)
    h = 1 # Hydro
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000)
    ax[3,1].set_ylabel('Primary Si demand [Mt]',fontsize =18)
    right_side = ax[3,1].spines["right"]
    right_side.set_visible(False)
    top = ax[3,1].spines["top"]
    top.set_visible(False)
    ax[3,1].legend(['Business as usual', 'Shift to LFP', 'Second-life', 'Fleet reduction', 'Efficient recycling', 'Replacements and reuse'], loc='upper left',prop={'size':15})
    ax[3,1].set_title('h) Silicon', fontsize=20)
    ax[3,1].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[3,1].tick_params(axis='both', which='major', labelsize=18)
    fig.savefig(os.getcwd() + '/results/overview/resource_strategies', dpi=300)

def sensitivity_analysis():
    from cycler import cycler
    import seaborn as sns
    from matplotlib.lines import Line2D
    r=5
    custom_cycler = cycler(color=sns.color_palette('magma', 4)) #'Set2', 'Paired', 'YlGnBu'
    # Load replacement results
    e01_replacements = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E01_case6.npy')
    # Define storylines
    sustainable = e01_replacements[0,2,2,2,r,:,:,0,:].sum(axis=0)
    resource = MaTrace_System.FlowDict['E_0_1'].Values[1,2,0,0,r,:,:,0,:].sum(axis=0)
    bau = MaTrace_System.FlowDict['E_0_1'].Values[1,1,6,0,r,:,:,1,:].sum(axis=0)
    slow = MaTrace_System.FlowDict['E_0_1'].Values[2,0,1,1,r,:,:,1,:].sum(axis=0)
    fig, ax = plt.subplots(4,2,figsize=(20,28))
    # Define sensitivity analysis for Ni
    e = 7 # Ni
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,2,4,5,6]:
                for R in range(NR):
                    for h in range(Nh):
                        if S==0:
                            # Values from case 3
                            ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'cornflowerblue', alpha=0.05)
                            # Values from case 6
                            ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'cornflowerblue', alpha=0.05)
                        if S==1:
                            # Values from case 3
                            ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                            # Values from case 6
                            ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                        if S==2:
                            # Values from case 3
                            ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'salmon', alpha=0.05)
                            # Values from case 6
                            ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'salmon', alpha=0.05)
    
    ax[0,0].set_prop_cycle(custom_cycler)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[0,0].set_ylabel('Primary Ni demand [Mt]',fontsize =18)
    right_side = ax[0,0].spines["right"]
    right_side.set_visible(False)
    top = ax[0,0].spines["top"]
    top.set_visible(False)
    custom_lines = [Line2D([0], [0], color='cornflowerblue', lw=1),
                Line2D([0], [0], color='silver', lw=1),
                Line2D([0], [0], color='salmon', lw=1),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[3], lw=3)]
    ax[0,0].legend(custom_lines, ['STEP', 'SD', 'Net Zero', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[0,0].set_title('a) Nickel', fontsize=20)
    ax[0,0].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[0,0].tick_params(axis='both', which='major', labelsize=18)

    ## Plot Li
    ax[0,1].set_prop_cycle(custom_cycler)
    e = 0 # Li
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,2,4,5,6]:
                for R in range(NR):
                    for h in range(Nh):
                        if S==0:
                            # Values from case 3
                            ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'cornflowerblue', alpha=0.05)
                            # Values from case 6
                            ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'cornflowerblue', alpha=0.05)
                        if S==1:
                            # Values from case 3
                            ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                            # Values from case 6
                            ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                        if S==2:
                            # Values from case 3
                            ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'salmon', alpha=0.05)
                            # Values from case 6
                            ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'salmon', alpha=0.05)
    
    ax[0,1].set_prop_cycle(custom_cycler)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[0,1].set_ylabel('Primary Li demand [Mt]',fontsize =18)
    right_side = ax[0,1].spines["right"]
    right_side.set_visible(False)
    top = ax[0,1].spines["top"]
    top.set_visible(False)
    custom_lines = [Line2D([0], [0], color='cornflowerblue', lw=1),
                Line2D([0], [0], color='silver', lw=1),
                Line2D([0], [0], color='salmon', lw=1),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[3], lw=3)]
    ax[0,1].legend(custom_lines, ['STEP', 'SD', 'Net Zero', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[0,1].set_title('b) Lithium', fontsize=20)
    ax[0,1].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[0,1].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot Co
    ax[1,0].set_prop_cycle(custom_cycler)
    e = 6 # Co
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,2,4,5,6]:
                for R in range(NR):
                    for h in range(Nh):
                        if S==0:
                            # Values from case 3
                            ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'cornflowerblue', alpha=0.05)
                            # Values from case 6
                            ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'cornflowerblue', alpha=0.05)
                        if S==1:
                            # Values from case 3
                            ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                            # Values from case 6
                            ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                        if S==2:
                            # Values from case 3
                            ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'salmon', alpha=0.05)
                            # Values from case 6
                            ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'salmon', alpha=0.05)
    
    ax[1,0].set_prop_cycle(custom_cycler)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[1,0].set_ylabel('Primary Co demand [Mt]',fontsize =18)
    right_side = ax[1,0].spines["right"]
    right_side.set_visible(False)
    top = ax[1,0].spines["top"]
    top.set_visible(False)
    custom_lines = [Line2D([0], [0], color='cornflowerblue', lw=1),
                Line2D([0], [0], color='silver', lw=1),
                Line2D([0], [0], color='salmon', lw=1),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[3], lw=3)]
    ax[1,0].legend(custom_lines, ['STEP', 'SD', 'Net Zero', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[1,0].set_title('c) Cobalt', fontsize=20)
    ax[1,0].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[1,0].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot P
    ax[1,1].set_prop_cycle(custom_cycler)
    e = 4 # P
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,2,4,5,6]:
                for R in range(NR):
                    for h in range(Nh):
                        if S==0:
                            # Values from case 3
                            ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'cornflowerblue', alpha=0.05)
                            # Values from case 6
                            ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'cornflowerblue', alpha=0.05)
                        if S==1:
                            # Values from case 3
                            ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                            # Values from case 6
                            ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                        if S==2:
                            # Values from case 3
                            ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'salmon', alpha=0.05)
                            # Values from case 6
                            ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'salmon', alpha=0.05)
    
    ax[1,1].set_prop_cycle(custom_cycler)
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[1,1].set_ylabel('Primary P demand [Mt]',fontsize =18)
    right_side = ax[1,1].spines["right"]
    right_side.set_visible(False)
    top = ax[1,1].spines["top"]
    top.set_visible(False)
    custom_lines = [Line2D([0], [0], color='cornflowerblue', lw=1),
                Line2D([0], [0], color='silver', lw=1),
                Line2D([0], [0], color='salmon', lw=1),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[3], lw=3)]
    ax[1,1].legend(custom_lines, ['STEP', 'SD', 'Net Zero', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[1,1].set_title('d) Phosphorous', fontsize=20)
    ax[1,1].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[1,1].tick_params(axis='both', which='major', labelsize=18)

    ## Plot Al
    ax[2,0].set_prop_cycle(custom_cycler)
    e = 2 # Al
    for z in range(Nz):
        for S in range(NS):
            for a in range(Na):
                for R in range(NR):
                    for h in range(Nh):
                        if S==0:
                            # Values from case 3
                            ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'cornflowerblue', alpha=0.05)
                            # Values from case 6
                            ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'cornflowerblue', alpha=0.05)
                        if S==1:
                            # Values from case 3
                            ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                            # Values from case 6
                            ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                        if S==2:
                            # Values from case 3
                            ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'salmon', alpha=0.05)
                            # Values from case 6
                            ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'salmon', alpha=0.05)
    
    ax[2,0].set_prop_cycle(custom_cycler)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[2,0].set_ylabel('Primary Al demand [Mt]',fontsize =18)
    right_side = ax[2,0].spines["right"]
    right_side.set_visible(False)
    top = ax[2,0].spines["top"]
    top.set_visible(False)
    custom_lines = [Line2D([0], [0], color='cornflowerblue', lw=1),
                Line2D([0], [0], color='silver', lw=1),
                Line2D([0], [0], color='salmon', lw=1),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[3], lw=3)]
    ax[2,0].legend(custom_lines, ['STEP', 'SD', 'Net Zero', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[2,0].set_title('e) Aluminium', fontsize=20)
    ax[2,0].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[2,0].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot Graphite
    ax[2,1].set_prop_cycle(custom_cycler)
    e = 1 # Graphite
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,2,4,5,6]:
                for R in range(NR):
                    for h in range(Nh):
                        if S==0:
                            # Values from case 3
                            ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'cornflowerblue', alpha=0.05)
                            # Values from case 6
                            ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'cornflowerblue', alpha=0.05)
                        if S==1:
                            # Values from case 3
                            ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                            # Values from case 6
                            ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                        if S==2:
                            # Values from case 3
                            ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'salmon', alpha=0.05)
                            # Values from case 6
                            ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'salmon', alpha=0.05)
    
    ax[2,1].set_prop_cycle(custom_cycler)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[2,1].set_ylabel('Primary Graphite demand [Mt]',fontsize =18)
    right_side = ax[2,1].spines["right"]
    right_side.set_visible(False)
    top = ax[2,1].spines["top"]
    top.set_visible(False)
    custom_lines = [Line2D([0], [0], color='cornflowerblue', lw=1),
                Line2D([0], [0], color='silver', lw=1),
                Line2D([0], [0], color='salmon', lw=1),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[3], lw=3)]
    ax[2,1].legend(custom_lines, ['STEP', 'SD', 'Net Zero', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[2,1].set_title('f) Graphite', fontsize=20)
    ax[2,1].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[2,1].tick_params(axis='both', which='major', labelsize=18)
    
    
    ## Plot Mn
    ax[3,0].set_prop_cycle(custom_cycler)
    e = 5 # Mn
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,2,4,5,6]:
                for R in range(NR):
                    for h in range(Nh):
                        if S==0:
                            # Values from case 3
                            ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'cornflowerblue', alpha=0.05)
                            # Values from case 6
                            ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'cornflowerblue', alpha=0.05)
                        if S==1:
                            # Values from case 3
                            ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                            # Values from case 6
                            ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                        if S==2:
                            # Values from case 3
                            ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'salmon', alpha=0.05)
                            # Values from case 6
                            ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'salmon', alpha=0.05)
    
    ax[3,0].set_prop_cycle(custom_cycler)
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[3,0].set_ylabel('Primary Mn demand [Mt]',fontsize =18)
    right_side = ax[3,0].spines["right"]
    right_side.set_visible(False)
    top = ax[3,0].spines["top"]
    top.set_visible(False)
    custom_lines = [Line2D([0], [0], color='cornflowerblue', lw=1),
                Line2D([0], [0], color='silver', lw=1),
                Line2D([0], [0], color='salmon', lw=1),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[3], lw=3)]
    ax[3,0].legend(custom_lines, ['STEP', 'SD', 'Net Zero', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[3,0].set_title('g) Manganese', fontsize=20)
    ax[3,0].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[3,0].tick_params(axis='both', which='major', labelsize=18)
    
    
    ## Plot Si
    ax[3,1].set_prop_cycle(custom_cycler)
    e = 3 # Si
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,2,4,5,6]:
                for R in range(NR):
                    for h in range(Nh):
                        if S==0:
                            # Values from case 3
                            ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'cornflowerblue', alpha=0.05)
                            # Values from case 6
                            ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'cornflowerblue', alpha=0.05)
                        if S==1:
                            # Values from case 3
                            ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                            # Values from case 6
                            ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                        if S==2:
                            # Values from case 3
                            ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'salmon', alpha=0.05)
                            # Values from case 6
                            ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'salmon', alpha=0.05)
    
    ax[3,1].set_prop_cycle(custom_cycler)
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[3,1].set_ylabel('Primary Si demand [Mt]',fontsize =18)
    right_side = ax[3,1].spines["right"]
    right_side.set_visible(False)
    top = ax[3,1].spines["top"]
    top.set_visible(False)
    custom_lines = [Line2D([0], [0], color='cornflowerblue', lw=1),
                Line2D([0], [0], color='silver', lw=1),
                Line2D([0], [0], color='salmon', lw=1),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[3], lw=3)]
    ax[3,1].legend(custom_lines, ['STEP', 'SD', 'Net Zero', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[3,1].set_title('h) Silicon', fontsize=20)
    ax[3,1].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[3,1].tick_params(axis='both', which='major', labelsize=18)
    fig.savefig(os.getcwd() + '/results/overview/sensitivity_analysis', dpi=300)

def sensitivity_analysis_newcolor():
    from cycler import cycler
    import seaborn as sns
    from matplotlib.lines import Line2D
    r=5
    custom_cycler = cycler(color=sns.color_palette('cool', 4)) #'Set2', 'Paired', 'YlGnBu'
    # Load replacement results
    e01_replacements = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E01_case6.npy')
    # Define storylines
    sustainable = e01_replacements[0,2,2,2,r,:,:,0,:].sum(axis=0)
    resource = MaTrace_System.FlowDict['E_0_1'].Values[1,2,0,0,r,:,:,0,:].sum(axis=0)
    bau = MaTrace_System.FlowDict['E_0_1'].Values[1,1,6,0,r,:,:,1,:].sum(axis=0)
    slow = MaTrace_System.FlowDict['E_0_1'].Values[2,0,1,1,r,:,:,1,:].sum(axis=0)
    fig, ax = plt.subplots(4,2,figsize=(20,28))
    # Define sensitivity analysis for Ni
    e = 7 # Ni
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,2,4,5,6]:
                for R in range(NR):
                    for h in range(Nh):
                        if S==0:
                            # Values from case 3
                            ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                            # Values from case 6
                            ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                        if S==1:
                            # Values from case 3
                            ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                            # Values from case 6
                            ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                        if S==2:
                            # Values from case 3
                            ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
                            # Values from case 6
                            ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
    
    ax[0,0].set_prop_cycle(custom_cycler)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[0,0].set_ylabel('Primary Ni demand [Mt]',fontsize =18)
    right_side = ax[0,0].spines["right"]
    right_side.set_visible(False)
    top = ax[0,0].spines["top"]
    top.set_visible(False)
    custom_lines = [Line2D([0], [0], color='powderblue', lw=1),
                Line2D([0], [0], color='dodgerblue', lw=1),
                Line2D([0], [0], color='blueviolet', lw=1),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[3], lw=3)]
    ax[0,0].legend(custom_lines, ['STEP', 'SD', 'Net Zero', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[0,0].set_title('a) Nickel', fontsize=20)
    ax[0,0].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[0,0].tick_params(axis='both', which='major', labelsize=18)

    ## Plot Li
    ax[0,1].set_prop_cycle(custom_cycler)
    e = 0 # Li
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,2,4,5,6]:
                for R in range(NR):
                    for h in range(Nh):
                        if S==0:
                            # Values from case 3
                            ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                            # Values from case 6
                            ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                        if S==1:
                            # Values from case 3
                            ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                            # Values from case 6
                            ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                        if S==2:
                            # Values from case 3
                            ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
                            # Values from case 6
                            ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
    
    ax[0,1].set_prop_cycle(custom_cycler)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[0,1].set_ylabel('Primary Li demand [Mt]',fontsize =18)
    right_side = ax[0,1].spines["right"]
    right_side.set_visible(False)
    top = ax[0,1].spines["top"]
    top.set_visible(False)
    custom_lines = [Line2D([0], [0], color='powderblue', lw=1),
                Line2D([0], [0], color='dodgerblue', lw=1),
                Line2D([0], [0], color='blueviolet', lw=1),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[3], lw=3)]
    ax[0,1].legend(custom_lines, ['STEP', 'SD', 'Net Zero', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[0,1].set_title('b) Lithium', fontsize=20)
    ax[0,1].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[0,1].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot Co
    ax[1,0].set_prop_cycle(custom_cycler)
    e = 6 # Co
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,2,4,5,6]:
                for R in range(NR):
                    for h in range(Nh):
                        if S==0:
                            # Values from case 3
                            ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                            # Values from case 6
                            ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                        if S==1:
                            # Values from case 3
                            ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                            # Values from case 6
                            ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                        if S==2:
                            # Values from case 3
                            ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
                            # Values from case 6
                            ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
    
    ax[1,0].set_prop_cycle(custom_cycler)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[1,0].set_ylabel('Primary Co demand [Mt]',fontsize =18)
    right_side = ax[1,0].spines["right"]
    right_side.set_visible(False)
    top = ax[1,0].spines["top"]
    top.set_visible(False)
    custom_lines = [Line2D([0], [0], color='powderblue', lw=1),
                Line2D([0], [0], color='dodgerblue', lw=1),
                Line2D([0], [0], color='blueviolet', lw=1),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[3], lw=3)]
    ax[1,0].legend(custom_lines, ['STEP', 'SD', 'Net Zero', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[1,0].set_title('c) Cobalt', fontsize=20)
    ax[1,0].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[1,0].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot P
    ax[1,1].set_prop_cycle(custom_cycler)
    e = 4 # P
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,2,4,5,6]:
                for R in range(NR):
                    for h in range(Nh):
                        if S==0:
                            # Values from case 3
                            ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                            # Values from case 6
                            ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                        if S==1:
                            # Values from case 3
                            ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                            # Values from case 6
                            ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                        if S==2:
                            # Values from case 3
                            ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
                            # Values from case 6
                            ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
    
    ax[1,1].set_prop_cycle(custom_cycler)
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[1,1].set_ylabel('Primary P demand [Mt]',fontsize =18)
    right_side = ax[1,1].spines["right"]
    right_side.set_visible(False)
    top = ax[1,1].spines["top"]
    top.set_visible(False)
    custom_lines = [Line2D([0], [0], color='powderblue', lw=1),
                Line2D([0], [0], color='dodgerblue', lw=1),
                Line2D([0], [0], color='blueviolet', lw=1),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[3], lw=3)]
    ax[1,1].legend(custom_lines, ['STEP', 'SD', 'Net Zero', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[1,1].set_title('d) Phosphorous', fontsize=20)
    ax[1,1].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[1,1].tick_params(axis='both', which='major', labelsize=18)

    ## Plot Al
    ax[2,0].set_prop_cycle(custom_cycler)
    e = 2 # Al
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,2,4,5,6]:
                for R in range(NR):
                    for h in range(Nh):
                        if S==0:
                            # Values from case 3
                            ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                            # Values from case 6
                            ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                        if S==1:
                            # Values from case 3
                            ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                            # Values from case 6
                            ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                        if S==2:
                            # Values from case 3
                            ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
                            # Values from case 6
                            ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
    
    ax[2,0].set_prop_cycle(custom_cycler)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[2,0].set_ylabel('Primary Al demand [Mt]',fontsize =18)
    right_side = ax[2,0].spines["right"]
    right_side.set_visible(False)
    top = ax[2,0].spines["top"]
    top.set_visible(False)
    custom_lines = [Line2D([0], [0], color='powderblue', lw=1),
                Line2D([0], [0], color='dodgerblue', lw=1),
                Line2D([0], [0], color='blueviolet', lw=1),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[3], lw=3)]
    ax[2,0].legend(custom_lines, ['STEP', 'SD', 'Net Zero', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[2,0].set_title('e) Aluminium', fontsize=20)
    ax[2,0].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[2,0].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot Graphite
    ax[2,1].set_prop_cycle(custom_cycler)
    e = 1 # Graphite
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,2,4,5,6]:
                for R in range(NR):
                    for h in range(Nh):
                        if S==0:
                            # Values from case 3
                            ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                            # Values from case 6
                            ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                        if S==1:
                            # Values from case 3
                            ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                            # Values from case 6
                            ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                        if S==2:
                            # Values from case 3
                            ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
                            # Values from case 6
                            ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
    
    ax[2,1].set_prop_cycle(custom_cycler)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[2,1].set_ylabel('Primary Graphite demand [Mt]',fontsize =18)
    right_side = ax[2,1].spines["right"]
    right_side.set_visible(False)
    top = ax[2,1].spines["top"]
    top.set_visible(False)
    custom_lines = [Line2D([0], [0], color='powderblue', lw=1),
                Line2D([0], [0], color='dodgerblue', lw=1),
                Line2D([0], [0], color='blueviolet', lw=1),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[3], lw=3)]
    ax[2,1].legend(custom_lines, ['STEP', 'SD', 'Net Zero', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[2,1].set_title('f) Graphite', fontsize=20)
    ax[2,1].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[2,1].tick_params(axis='both', which='major', labelsize=18)
    
    
    ## Plot Mn
    ax[3,0].set_prop_cycle(custom_cycler)
    e = 5 # Mn
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,2,4,5,6]:
                for R in range(NR):
                    for h in range(Nh):
                        if S==0:
                            # Values from case 3
                            ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                            # Values from case 6
                            ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                        if S==1:
                            # Values from case 3
                            ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                            # Values from case 6
                            ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                        if S==2:
                            # Values from case 3
                            ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
                            # Values from case 6
                            ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
    
    ax[3,0].set_prop_cycle(custom_cycler)
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[3,0].set_ylabel('Primary Mn demand [Mt]',fontsize =18)
    right_side = ax[3,0].spines["right"]
    right_side.set_visible(False)
    top = ax[3,0].spines["top"]
    top.set_visible(False)
    custom_lines = [Line2D([0], [0], color='powderblue', lw=1),
                Line2D([0], [0], color='dodgerblue', lw=1),
                Line2D([0], [0], color='blueviolet', lw=1),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[3], lw=3)]
    ax[3,0].legend(custom_lines, ['STEP', 'SD', 'Net Zero', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[3,0].set_title('g) Manganese', fontsize=20)
    ax[3,0].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[3,0].tick_params(axis='both', which='major', labelsize=18)
    
    
    ## Plot Si
    ax[3,1].set_prop_cycle(custom_cycler)
    e = 3 # Si
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,2,4,5,6]:
                for R in range(NR):
                    for h in range(Nh):
                        if S==0:
                            # Values from case 3
                            ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                            # Values from case 6
                            ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                        if S==1:
                            # Values from case 3
                            ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                            # Values from case 6
                            ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                        if S==2:
                            # Values from case 3
                            ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
                            # Values from case 6
                            ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
    
    ax[3,1].set_prop_cycle(custom_cycler)
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[3,1].set_ylabel('Primary Si demand [Mt]',fontsize =18)
    right_side = ax[3,1].spines["right"]
    right_side.set_visible(False)
    top = ax[3,1].spines["top"]
    top.set_visible(False)
    custom_lines = [Line2D([0], [0], color='powderblue', lw=1),
                Line2D([0], [0], color='dodgerblue', lw=1),
                Line2D([0], [0], color='blueviolet', lw=1),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 4)[3], lw=3)]
    ax[3,1].legend(custom_lines, ['STEP', 'SD', 'Net Zero', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[3,1].set_title('h) Silicon', fontsize=20)
    ax[3,1].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[3,1].tick_params(axis='both', which='major', labelsize=18)
    fig.savefig(os.getcwd() + '/results/overview/sensitivity_analysis_cool', dpi=300)

def sensitivity_analysis_grey():
    from cycler import cycler
    import seaborn as sns
    from matplotlib.lines import Line2D
    r=5
    custom_cycler = cycler(color=sns.color_palette('magma', 4)) #'Set2', 'Paired', 'YlGnBu'
    # Load replacement results
    e01_replacements = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E01_case6.npy')
    # Define storylines
    sustainable = e01_replacements[0,2,2,2,r,:,:,0,:].sum(axis=0)
    resource = MaTrace_System.FlowDict['E_0_1'].Values[1,2,0,0,r,:,:,0,:].sum(axis=0)
    bau = MaTrace_System.FlowDict['E_0_1'].Values[1,1,6,0,r,:,:,1,:].sum(axis=0)
    slow = MaTrace_System.FlowDict['E_0_1'].Values[2,0,1,1,r,:,:,1,:].sum(axis=0)
    fig, ax = plt.subplots(4,2,figsize=(20,28))
    # Define sensitivity analysis for Ni
    e = 7 # Ni
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,2,4,5,6]:
                for R in range(NR):
                    for h in range(Nh):
                            # Values from case 3
                            ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                            # Values from case 6
                            ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
    
    ax[0,0].set_prop_cycle(custom_cycler)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[0,0].set_ylabel('Primary Ni demand [Mt]',fontsize =18)
    right_side = ax[0,0].spines["right"]
    right_side.set_visible(False)
    top = ax[0,0].spines["top"]
    top.set_visible(False)
    custom_lines = [
                Line2D([0], [0], color='silver', lw=1),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[3], lw=3)]
    ax[0,0].legend(custom_lines, ['Scenario range', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[0,0].set_title('a) Nickel', fontsize=20)
    ax[0,0].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[0,0].tick_params(axis='both', which='major', labelsize=18)

    ## Plot Li
    ax[0,1].set_prop_cycle(custom_cycler)
    e = 0 # Li
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,2,4,5,6]:
                for R in range(NR):
                    for h in range(Nh):
                            # Values from case 3
                            ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                            # Values from case 6
                            ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
    
    ax[0,1].set_prop_cycle(custom_cycler)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[0,1].set_ylabel('Primary Li demand [Mt]',fontsize =18)
    right_side = ax[0,1].spines["right"]
    right_side.set_visible(False)
    top = ax[0,1].spines["top"]
    top.set_visible(False)
    custom_lines = [
                Line2D([0], [0], color='silver', lw=1),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[3], lw=3)]
    ax[0,1].legend(custom_lines, ['Scenario Range', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[0,1].set_title('b) Lithium', fontsize=20)
    ax[0,1].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[0,1].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot Co
    ax[1,0].set_prop_cycle(custom_cycler)
    e = 6 # Co
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,2,4,5,6]:
                for R in range(NR):
                    for h in range(Nh):
                            # Values from case 3
                            ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                            # Values from case 6
                            ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
    
    ax[1,0].set_prop_cycle(custom_cycler)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[1,0].set_ylabel('Primary Co demand [Mt]',fontsize =18)
    right_side = ax[1,0].spines["right"]
    right_side.set_visible(False)
    top = ax[1,0].spines["top"]
    top.set_visible(False)
    custom_lines = [
                Line2D([0], [0], color='silver', lw=1),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[3], lw=3)]
    ax[1,0].legend(custom_lines, ['Scenario range', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[1,0].set_title('c) Cobalt', fontsize=20)
    ax[1,0].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[1,0].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot P
    ax[1,1].set_prop_cycle(custom_cycler)
    e = 4 # P
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,2,4,5,6]:
                for R in range(NR):
                    for h in range(Nh):
                            # Values from case 3
                            ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                            # Values from case 6
                            ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
    
    ax[1,1].set_prop_cycle(custom_cycler)
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[1,1].set_ylabel('Primary P demand [Mt]',fontsize =18)
    right_side = ax[1,1].spines["right"]
    right_side.set_visible(False)
    top = ax[1,1].spines["top"]
    top.set_visible(False)
    custom_lines = [
                Line2D([0], [0], color='silver', lw=1),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[3], lw=3)]
    ax[1,1].legend(custom_lines, ['Scenario range', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[1,1].set_title('d) Phosphorous', fontsize=20)
    ax[1,1].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[1,1].tick_params(axis='both', which='major', labelsize=18)

    ## Plot Al
    ax[2,0].set_prop_cycle(custom_cycler)
    e = 2 # Al
    for z in range(Nz):
        for S in range(NS):
            for a in range(Na):
                for R in range(NR):
                    for h in range(Nh):
                            # Values from case 3
                            ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                            # Values from case 6
                            ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
    
    ax[2,0].set_prop_cycle(custom_cycler)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[2,0].set_ylabel('Primary Al demand [Mt]',fontsize =18)
    right_side = ax[2,0].spines["right"]
    right_side.set_visible(False)
    top = ax[2,0].spines["top"]
    top.set_visible(False)
    custom_lines = [
                Line2D([0], [0], color='silver', lw=1),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[3], lw=3)]
    ax[2,0].legend(custom_lines, ['Scenario range', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[2,0].set_title('e) Aluminium', fontsize=20)
    ax[2,0].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[2,0].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot Graphite
    ax[2,1].set_prop_cycle(custom_cycler)
    e = 1 # Graphite
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,2,4,5,6]:
                for R in range(NR):
                    for h in range(Nh):
                            # Values from case 3
                            ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                            # Values from case 6
                            ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
    ax[2,1].set_prop_cycle(custom_cycler)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[2,1].set_ylabel('Primary Graphite demand [Mt]',fontsize =18)
    right_side = ax[2,1].spines["right"]
    right_side.set_visible(False)
    top = ax[2,1].spines["top"]
    top.set_visible(False)
    custom_lines = [
                Line2D([0], [0], color='silver', lw=1),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[3], lw=3)]
    ax[2,1].legend(custom_lines, ['Scenario range', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[2,1].set_title('f) Graphite', fontsize=20)
    ax[2,1].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[2,1].tick_params(axis='both', which='major', labelsize=18)
    
    
    ## Plot Mn
    ax[3,0].set_prop_cycle(custom_cycler)
    e = 5 # Mn
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,2,4,5,6]:
                for R in range(NR):
                    for h in range(Nh):
                            # Values from case 3
                            ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                            # Values from case 6
                            ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
    
    ax[3,0].set_prop_cycle(custom_cycler)
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[3,0].set_ylabel('Primary Mn demand [Mt]',fontsize =18)
    right_side = ax[3,0].spines["right"]
    right_side.set_visible(False)
    top = ax[3,0].spines["top"]
    top.set_visible(False)
    custom_lines = [
                Line2D([0], [0], color='silver', lw=1),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[3], lw=3)]
    ax[3,0].legend(custom_lines, ['Scenario range', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[3,0].set_title('g) Manganese', fontsize=20)
    ax[3,0].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[3,0].tick_params(axis='both', which='major', labelsize=18)
    
    
    ## Plot Si
    ax[3,1].set_prop_cycle(custom_cycler)
    e = 3 # Si
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,2,4,5,6]:
                for R in range(NR):
                    for h in range(Nh):
                        # Values from case 3
                        ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
                        # Values from case 6
                        ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, 'silver', alpha=0.05)
    
    ax[3,1].set_prop_cycle(custom_cycler)
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        slow[e,65::]/1000000, linewidth=3, label='Slow transition')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        bau[e,65::]/1000000,  linewidth=3, label='Business as usual')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        resource[e,65::]/1000000,  linewidth=3, label='Resource oriented')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        sustainable[e,65::]/1000000,  linewidth=3, label='Sustainable future')
    ax[3,1].set_ylabel('Primary Si demand [Mt]',fontsize =18)
    right_side = ax[3,1].spines["right"]
    right_side.set_visible(False)
    top = ax[3,1].spines["top"]
    top.set_visible(False)
    custom_lines = [
                Line2D([0], [0], color='silver', lw=1),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('magma', 4)[3], lw=3)]
    ax[3,1].legend(custom_lines, ['Scenario range', 'Slow transition', 'Business as usual', 'Resource oriented', 'Sustainable future'], loc='upper left',prop={'size':15})
    ax[3,1].set_title('h) Silicon', fontsize=20)
    ax[3,1].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[3,1].tick_params(axis='both', which='major', labelsize=18)
    fig.savefig(os.getcwd() + '/results/overview/sensitivity_analysis_grey', dpi=300)

def Ni_strategies_combined():
    from cycler import cycler
    import seaborn as sns
    r=5
    custom_cycler = cycler(color=sns.color_palette('Set2', 20)) #'Set2', 'Paired', 'YlGnBu'
    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(custom_cycler)
    e = 7 # Ni
    z = 1 # Baseline
    S = 1 # Baseline
    a = 0 # High Ni
    R = 2 # All reuse
    h = 2 # Pyrometallurgy
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000, linewidth=4)
    h = 0 # Direct recycling
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000)
    z = 0 # Low vehicle ownership
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000)
    a = 1 # High LFP
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000)
    R = 1 # No reuse
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000)
    ax.set_ylabel('Primary Ni demand [kt]',fontsize =18)
    right_side = ax.spines["right"]
    right_side.set_visible(False)
    top = ax.spines["top"]
    top.set_visible(False)
    ax.legend(['Baseline', 'Efficient recycling', 'Fleet reduction', 'Move to LFP', 'No reuse'], loc='upper left',prop={'size':15})
    ax.set_title('Strategies for Ni use management', fontsize=20)
    ax.set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax.tick_params(axis='both', which='major', labelsize=18)

def Ni_strategies_combined_wedge():
    from cycler import cycler
    import seaborn as sns
    r=5
    custom_cycler = cycler(color=sns.color_palette('Set2', 20)) #'Set2', 'Paired', 'YlGnBu'
    fig, ax = plt.subplots(figsize=(8,7))
    
    ax.set_prop_cycle(custom_cycler)
    e = 7 # Ni
    z = 1 # Baseline
    S = 1 # Baseline
    a = 0 # High Ni
    R = 2 # All reuse
    h = 2 # Pyrometallurgy
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000,\
                    np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,0,65::])/1000, alpha=0.5)
    h = 0 # Direct recycling
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000,\
                    np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[0,S,a,R,r,:,e,h,65::])/1000, alpha=0.5)
    z = 0 # Low vehicle ownership
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000,\
                    np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,1,R,r,:,e,h,65::])/1000, alpha=0.5)
    a = 1 # High LFP
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000,\
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,1,r,:,e,h,65::])/1000, alpha=0.5)
    R = 1 # No reuse
    # ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
    #         np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000, \
    #             np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,r,:,e,h,65::])/1000)
    ax.set_ylabel('Primary Ni demand [kt]',fontsize =18)
    right_side = ax.spines["right"]
    right_side.set_visible(False)
    top = ax.spines["top"]
    top.set_visible(False)
    ax.legend(['Baseline', 'Efficient recycling', 'Fleet reduction', 'Move to LFP', 'No reuse'], loc='upper left',prop={'size':15})
    ax.set_title('Strategies for Ni use management', fontsize=20)
    ax.set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax.tick_params(axis='both', which='major', labelsize=18)

def export_P():
    results = os.path.join(os.getcwd(), 'results')
    #np.save(results+'/arrays/P_demand_vehicles_global', np.einsum('zSaRpht->zSaRht', MaTrace_System.FlowDict['E_0_1'].Values[:,:,:,:,r,:,4,:,:])/1000)
    
def export_Li():
    np.save('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/Li_demand_vehicles_global', np.einsum('zSaRpht->zSaRht', MaTrace_System.FlowDict['E_0_1'].Values[:,:,:,:,r,:,0,:,:])/1000)

# %%
def model_case_6():
    ########## This scenario should only be run to get the values with battery reuse and replacement
    lt_cm  = np.array([12])
    sd_cm  = np.array([5])

    ###
    replacement_rate = 0.5
    reuse_rate = 0.8
    for z in range(Nz):
        #for r in range(0,Nr):
            for S in range(NS):
                for g in range(0,Ng):
                    # In this case we assume that the product and component have the same lifetimes and set the delay as 3 years for both goods
                    Model                                                     = pcm.ProductComponentModel(t = range(0,Nt), s_pr = MaTrace_System.ParameterDict['Vehicle_stock'].Values[z,r,:]/1000, lt_pr = {'Type': 'Normal', 'Mean': np.array([16]), 'StdDev': np.array([4]) }, \
                        lt_cm = {'Type': 'Normal', 'Mean': lt_cm, 'StdDev': sd_cm}, replacement_coeff=replacement_rate, reuse_coeff=reuse_rate)
                    Model.case_6()

                    MaTrace_System.StockDict['S_C_3'].Values[z,S,r,g,:,:,:]             = np.einsum('sc,tc->stc', MaTrace_System.ParameterDict['Segment_shares'].Values[g,:,:] ,np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.sc_pr.copy()))
                    MaTrace_System.StockDict['S_3'].Values[z,S,r,g,:,:]                 = np.einsum('stc->st', MaTrace_System.StockDict['S_C_3'].Values[z,S,r,g,:,:,:])
                    MaTrace_System.FlowDict['F_2_3'].Values[z,S,r,g,:,:]              = np.einsum('sc,c->sc', MaTrace_System.ParameterDict['Segment_shares'].Values[g,:,:],np.einsum('c,c->c', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.i_pr.copy()))
                    MaTrace_System.FlowDict['F_3_4'].Values[z,S,r,g,:,:,:]              = np.einsum('sc,tc->stc', MaTrace_System.ParameterDict['Segment_shares'].Values[g,:,:],np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:] , Model.oc_pr.copy()))
                    

                    ### Battery chemistry layer: Here we use the battery stock instead of the vehicle stock
                    MaTrace_System.StockDict['M_C_3'].Values[z,S,:,r,g,:,:,:,:]     = np.einsum('abc,stc->asbtc', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , np.einsum('sc,tc->stc', MaTrace_System.ParameterDict['Segment_shares'].Values[g,:,:] \
                        ,np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.sc_cm.copy())))
                    MaTrace_System.StockDict['M_3'].Values[z,S,:,r,g,:,:,:]         = np.einsum('asbtc->asbt', MaTrace_System.StockDict['M_C_3'].Values[z,S,:,r,g,:,:,:,:])
                    # Battery inflows within car
                    MaTrace_System.FlowDict['M_2_3'].Values[z,S,:,r,g,:,:,:]        = np.einsum('abt,st->asbt', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] ,MaTrace_System.FlowDict['F_2_3'].Values[z,S,r,g,:,:])
                    # Battery replacements: Total battery inflows minus inflows of batteries in cars
                    MaTrace_System.FlowDict['M_1_3'].Values[z,S,:,r,g,:,:,:]        = np.einsum('abt,st->asbt', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , np.einsum('sc,c->sc', MaTrace_System.ParameterDict['Segment_shares'].Values[g,:,:], \
                        np.einsum('c,c->c', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.i_cm.copy()))) - MaTrace_System.FlowDict['M_2_3'].Values[z,S,:,r,g,:,:,:]
                    # Battery outflows in car
                    MaTrace_System.FlowDict['M_3_4_tc'].Values[z,S,:,r,g,:,:,:,:]   = np.einsum('abc,stc->asbtc', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , MaTrace_System.FlowDict['F_3_4'].Values[z,S,r,g,:,:,:])
                    MaTrace_System.FlowDict['M_3_4'].Values[z,S,:,r,g,:,:,:]        = np.einsum('asbtc->asbt', MaTrace_System.FlowDict['M_3_4_tc'].Values[z,S,:,r,g,:,:,:,:])
                    # Batteries after vehicle has been dismantled
                    MaTrace_System.FlowDict['M_4_5'].Values[z,S,:,r,g,:,:,:,:]      = MaTrace_System.FlowDict['M_3_4_tc'].Values[z,S,:,r,g,:,:,:,:] 
                    # Battery outflows due to battery failures: Total battery outflows minus vehicle outflows
                    MaTrace_System.FlowDict['M_3_5'].Values[z,S,:,r,g,:,:,:,:]      = np.einsum('abc,stc->asbtc', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , np.einsum('sc,tc->stc', MaTrace_System.ParameterDict['Segment_shares'].Values[g,:,:], \
                        np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:] , Model.oc_cm.copy()))) - MaTrace_System.FlowDict['M_4_5'].Values[z,S,:,r,g,:,:,:,:]
                    # Reused batteries from mass balance: M53 = dS3 - M13 - M23 + M34 + M35
                    # Compute stock change
                    dS  = np.zeros((Ng,Na,Ns,Nb,Nt))
                    dS[g,:,:,:,1:]  = np.diff(MaTrace_System.StockDict['M_3'].Values[z,S,:,r,g,:,:,:]) # Stock change at year 0 = 0, doesn't make a difference since no EVs in 1950
                    MaTrace_System.FlowDict['M_5_3'].Values[z,S,:,r,g,:,:,:]      = dS[g,:,:,:,:] \
                        - MaTrace_System.FlowDict['M_1_3'].Values[z,S,:,r,g,:,:,:] - MaTrace_System.FlowDict['M_2_3'].Values[z,S,:,r,g,:,:,:] \
                            + MaTrace_System.FlowDict['M_3_4'].Values[z,S,:,r,g,:,:,:] + np.einsum('asbtc->asbt',MaTrace_System.FlowDict['M_3_5'].Values[z,S,:,r,g,:,:,:,:])


                    ### Battery by weight layer: Multiply the numbers by the weight factor for each chemistry and size
                    # Stocks
                    MaTrace_System.StockDict['B_C_3'].Values[z,S,:,r,g,:,:,:,:]     = np.einsum('sb,asbtc->asbtc', MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:] , MaTrace_System.StockDict['M_C_3'].Values[z,S,:,r,g,:,:,:,:])
                    MaTrace_System.StockDict['B_3'].Values[z,S,:,r,g,:,:,:]         = np.einsum('asbtc->asbt', MaTrace_System.StockDict['B_C_3'].Values[z,S,:,r,g,:,:,:,:])
                    MaTrace_System.FlowDict['B_1_3'].Values[z,S,:,r,g,:,:,:]        = np.einsum('asbt,sb->asbt', MaTrace_System.FlowDict['M_1_3'].Values[z,S,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:])
                    MaTrace_System.FlowDict['B_2_3'].Values[z,S,:,r,g,:,:,:]        = np.einsum('asbt,sb->asbt', MaTrace_System.FlowDict['M_2_3'].Values[z,S,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:])
                    MaTrace_System.FlowDict['B_3_4_tc'].Values[z,S,:,r,g,:,:,:,:]   = np.einsum('asbtc,sb->asbtc', MaTrace_System.FlowDict['M_3_4_tc'].Values[z,S,:,r,g,:,:,:,:], MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:])
                    MaTrace_System.FlowDict['B_3_4'].Values[z,S,:,r,g,:,:,:]        = np.einsum('asbtc->asbt', MaTrace_System.FlowDict['B_3_4_tc'].Values[z,S,:,r,g,:,:,:,:] )
                    MaTrace_System.FlowDict['B_4_5'].Values[z,S,:,r,g,:,:,:,:]      = MaTrace_System.FlowDict['B_3_4_tc'].Values[z,S,:,r,g,:,:,:,:] 
                    MaTrace_System.FlowDict['B_3_5'].Values[z,S,:,r,g,:,:,:,:]      = np.einsum('asbtc,sb->asbtc', MaTrace_System.FlowDict['M_3_5'].Values[z,S,:,r,g,:,:,:,:], MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:])
                    MaTrace_System.FlowDict['B_5_3'].Values[z,S,:,r,g,:,:,:]        = np.einsum('asbt,sb->asbt', MaTrace_System.FlowDict['M_5_3'].Values[z,S,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:])
                    

                    ### Battery parts layer
                    MaTrace_System.StockDict['P_C_3'].Values[z,S,:,r,g,:,:,:,:,:]   = np.einsum('sbp,asbtc->asbptc', MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:] , MaTrace_System.StockDict['B_C_3'].Values[z,S,:,r,g,:,:,:,:])
                    MaTrace_System.StockDict['P_3'].Values[z,S,:,r,g,:,:,:,:]       = np.einsum('asbptc->asbpt', MaTrace_System.StockDict['P_C_3'].Values[z,S,:,r,g,:,:,:,:,:])
                    MaTrace_System.FlowDict['P_1_3'].Values[z,S,:,r,g,:,:,:,:]      = np.einsum('asbc,sbp->asbpc', MaTrace_System.FlowDict['B_1_3'].Values[z,S,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:]) 
                    MaTrace_System.FlowDict['P_2_3'].Values[z,S,:,r,g,:,:,:,:]      = np.einsum('asbc,sbp->asbpc', MaTrace_System.FlowDict['B_2_3'].Values[z,S,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:]) 
                    MaTrace_System.FlowDict['P_3_4_tc'].Values[z,S,:,r,g,:,:,:,:,:] = np.einsum('asbtc,sbp->asbptc', MaTrace_System.FlowDict['B_3_4_tc'].Values[z,S,:,r,g,:,:,:,:], MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:])
                    MaTrace_System.FlowDict['P_3_4'].Values[z,S,:,r,g,:,:,:,:]      = np.einsum('asbptc->asbpt', MaTrace_System.FlowDict['P_3_4_tc'].Values[z,S,:,r,g,:,:,:,:,:])
                    MaTrace_System.FlowDict['P_4_5'].Values[z,S,:,r,g,:,:,:,:,:]    = MaTrace_System.FlowDict['P_3_4_tc'].Values[z,S,:,r,g,:,:,:,:,:]
                    MaTrace_System.FlowDict['P_3_5'].Values[z,S,:,r,g,:,:,:,:,:]      = np.einsum('asbtc,sbp->asbptc', MaTrace_System.FlowDict['B_3_5'].Values[z,S,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:])
                    MaTrace_System.FlowDict['P_5_3'].Values[z,S,:,r,g,:,:,:,:]      = np.einsum('asbt,sbp->asbpt', MaTrace_System.FlowDict['B_5_3'].Values[z,S,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:])
                    
                    '''
                    We calculate the flows of battery modules into reuse. Sicne the casing and other battery parts are assumed to go directly into recyling, 
                    we just write this loop for the modules with index 0 and separately define that all other battery parts go to recycling. 
                    We also consider batteries that caused vehicle outflows, as the requirements here are lower. We can take them out if it does not make sense. 

                    The reuse parameter does not indicate the share of batteries that are reused. Rather, it is a condition to reflect decisions on which battery chemistries to 
                    reuse. LFP scenario for instance will define that only LFP chemistries are considered for reuse, but they health assessment still needs to happen. 
                    '''
                    # Calculate inflows to SLB only for the modules. We consider batteries that came from failed vehicles as well, since flow P_3_5 only contains failed batteries
                    MaTrace_System.FlowDict['P_5_6'].Values[z,S,:,:,r,g,:,0,:,:]  = np.einsum('Rbt,asbtc->aRbtc', MaTrace_System.ParameterDict['Reuse_rate'].Values[:,:,:], \
                        MaTrace_System.FlowDict['P_3_4_tc'].Values[z,S,:,r,g,:,:,0,:,:]) # * Model_slb.sf_cm[t+tau_cm,c] + MaTrace_System.FlowDict['P_3_5'].Values[z,S,:,r,g,:,:,0,t,c]* Model_slb.sf_cm[t+tau_cm,c]) # TODO: Possibly subtract P_5_3 flow if implemented
                    '''
                    Since the batteries are moving from being used in transport to being used in stationary storage, the "lifetime" is no longer the same. 
                    In transportation, we define the lifetime to be the time that the battery is still useful for that purpose, which is widely considered
                    to be until it reaches 80% of its initial capacity. The distribution of the lifetime helps us account for batteries that are more 
                    intensely used than others, but by the time of outflow they should all have more or less the same capacity of around 80%. 

                    Therefore, the remaining second life can be approximated with a normal distribution that would have an initial capacity of 80% and would
                    follow its own degradation curve.  
                    '''
    # Computing SLB stock after aggregating inflows
    Model_slb                                                       = pcm.ProductComponentModel(t = range(0,Nt),  lt_cm = {'Type': 'Normal', 'Mean': lt_cm, 'StdDev': sd_cm})
    # Compute the survival curve of the batteries with the additional lenght for the last tau years

    '''
    Define the SLB model in advance. We do not compute everything using the dsm as it only takes i as input
    and takes too long to compute. Instead, we define the functions ourselves using the sf computed with dsm. 
    '''
    lt_slb                               = np.array([6]) # We could have different lifetimes for the different chemistries
    sd_slb                               = np.array([2]) 
    inflows                             = np.zeros((Nz,NS, Na, NR, Nb, Nt))
    inflows = np.einsum('zSaRgbtc->zSaRbt',MaTrace_System.FlowDict['P_5_6'].Values[:,:,:,:,r,:,:,0,:,:])
    for z in range(Nz):
        for S in range(NS):
            for a in range(Na):
                for R in range(NR):
                    for b in range(Nb):
                        slb_model                        = dsm.DynamicStockModel(t=range(0,Nt), lt={'Type': 'Normal', 'Mean': lt_slb, 'StdDev': sd_slb}, i=inflows[z,S,a,R,b,:])
                        slb_model.compute_s_c_inflow_driven()
                        slb_model.compute_o_c_from_s_c()
                        slb_model.compute_stock_total()
                        MaTrace_System.StockDict['P_C_6'].Values[z,S,a,R,r,b,0,:,:] = slb_model.s_c.copy()
                        MaTrace_System.FlowDict['P_6_7'].Values[z,S,a,R,r,b,0,:,:] = slb_model.o_c.copy()
    '''
    We will leave this other approach for the moment
    MaTrace_System.StockDict['P_C_6'].Values[:,:,:,:,r,:,0,:,:]     = np.einsum('zSaRbt,tc->zSaRbtc', np.einsum('zSaRgbtc->zSaRbt',MaTrace_System.FlowDict['P_5_6'].Values[:,:,:,:,r,:,:,0,:,:]), slb_model.sf)
    # Compute SLB outflows
    MaTrace_System.FlowDict['P_6_7'].Values[:,:,:,:,r,:,0,1::,:]    = -1 * np.diff(MaTrace_System.StockDict['P_C_6'].Values[:,:,:,:,r,:,0,:,:], n=1, axis=5) # Difference over time -> axis=3
    for t in range(Nt):
        MaTrace_System.FlowDict['P_6_7'].Values[:,:,:,:,r,:,0,t,t]  = np.einsum('zSaRgbtc->zSaRb',MaTrace_System.FlowDict['P_5_6'].Values[:,:,:,:,r,:,:,0,:,:]) - MaTrace_System.StockDict['P_C_6'].Values[:,:,:,:,r,:,0,t,t]
    '''
    # Compute total stock
    MaTrace_System.StockDict['P_6'].Values[:,:,:,:,r,:,0,:]         = np.einsum('zSaRbtc->zSaRbt', MaTrace_System.StockDict['P_C_6'].Values[:,:,:,:,r,:,0,:,:])
    MaTrace_System.FlowDict['P_7_8'].Values[:,:,:,:,r,:,0,:,:]                  = MaTrace_System.FlowDict['P_6_7'].Values[:,:,:,:,r,:,0,:,:]
    # Calculate battery parts going directly to recycling: Total outflows minus reuse
    for R in range(NR):
        MaTrace_System.FlowDict['P_5_8'].Values[:,:,:,R,r,:,:,:,:]            =  np.einsum('zSagsbptc->zSabptc', MaTrace_System.FlowDict['P_3_4_tc'].Values[:,:,:,r,:,:,:,:,:,:]) \
            + np.einsum('zSagsbptc->zSabptc',MaTrace_System.FlowDict['P_3_5'].Values[:,:,:,r,:,:,:,:,:,:]) - np.einsum('zSagbptc->zSabptc',MaTrace_System.FlowDict['P_5_6'].Values[:,:,:,R,r,:,:,:,:,:])

    ### Material layer
    MaTrace_System.StockDict['E_3'].Values[:,:,:,r,:,:,:,:]           = np.einsum('zSagsbpt,gbpe->zSabpet', MaTrace_System.StockDict['P_3'].Values[:,:,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:])
    MaTrace_System.FlowDict['E_1_3'].Values[:,:,:,r,:,:,:,:]          = np.einsum('zSagsbpc,gbpe->zSabpec', MaTrace_System.FlowDict['P_1_3'].Values[:,:,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
    MaTrace_System.FlowDict['E_2_3'].Values[:,:,:,r,:,:,:,:]          = np.einsum('zSagsbpc,gbpe->zSabpec', MaTrace_System.FlowDict['P_2_3'].Values[:,:,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
    MaTrace_System.FlowDict['E_3_4'].Values[:,:,:,r,:,:,:,:]          = np.einsum('zSagsbpt,gbpe->zSabpet', MaTrace_System.FlowDict['P_3_4'].Values[:,:,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
    MaTrace_System.FlowDict['E_4_5'].Values[:,:,:,r,:,:,:]            = MaTrace_System.FlowDict['E_3_4'].Values[z,S,:,r,:,:,:,:]
    MaTrace_System.FlowDict['E_3_5'].Values[:,:,:,r,:,:,:,:]          = np.einsum('zSagsbptc,gbpe->zSabpet', MaTrace_System.FlowDict['P_3_5'].Values[:,:,:,r,:,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
    MaTrace_System.FlowDict['E_5_3'].Values[:,:,:,r,:,:,:,:]          = np.einsum('zSagsbpt,gbpe->zSabpet', MaTrace_System.FlowDict['P_5_3'].Values[:,:,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
    MaTrace_System.FlowDict['E_5_6'].Values[:,:,:,:,r,:,:,:,:]        = np.einsum('zSaRgbptc,gbpe->zSaRbpet', MaTrace_System.FlowDict['P_5_6'].Values[:,:,:,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
    MaTrace_System.FlowDict['E_5_8'].Values[:,:,:,:,r,:,:,:,:]        = np.einsum('zSaRbptc,gbpe->zSaRbpet', MaTrace_System.FlowDict['P_5_8'].Values[:,:,:,:,r,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
    MaTrace_System.FlowDict['E_6_7'].Values[:,:,:,:,r,:,:,:,:]        = np.einsum('zSaRbptc,gbpe->zSaRbpet', MaTrace_System.FlowDict['P_6_7'].Values[:,:,:,:,r,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
    MaTrace_System.FlowDict['E_7_8'].Values[:,:,:,:,r,:,:,:,:]        = np.einsum('zSaRbptc,gbpe->zSaRbpet', MaTrace_System.FlowDict['P_7_8'].Values[:,:,:,:,r,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 


    # Solving energy layer: Multiply stocks with capacity and degradation parameters
    MaTrace_System.StockDict['C_3'].Values[:,:,:,:,:,:,:] = np.einsum('zSargsbptc, btc->zSargbt', np.einsum('zSargsbptc, bpc -> zSargsbptc', MaTrace_System.StockDict['P_C_3'].Values[:,:,:,:,:,:,:], MaTrace_System.ParameterDict['Capacity'].Values[:,:,:]),  MaTrace_System.ParameterDict['Degradation'].Values[:,:,:])
    MaTrace_System.StockDict['C_6'].Values[:,:,:,:,:,:,:] = np.einsum('zSaRrbptc, btc->zSaRrbt', np.einsum('zSaRrbptc, bpc -> zSaRrbptc', MaTrace_System.StockDict['P_C_6'].Values[:,:,:,:,:,:,:,:,:], MaTrace_System.ParameterDict['Capacity'].Values[:,:,:]),  MaTrace_System.ParameterDict['Degradation'].Values[:,:,:])


    MaTrace_System.FlowDict['E_8_1'].Values[:,:,:,:,r,:,:,:,:] = np.einsum('eh, zSaRbpet->zSaRpeht', MaTrace_System.ParameterDict['Recycling_efficiency'].Values[:,:], (MaTrace_System.FlowDict['E_7_8'].Values[:,:,:,:,r,:,:,:,:] + MaTrace_System.FlowDict['E_5_8'].Values[:,:,:,:,r,:,:,:,:]))
    for R in range(NR):
        for h in range(Nh):
            MaTrace_System.FlowDict['E_0_1'].Values[:,:,:,R,r,:,:,h,:] = np.einsum('zSabpet->zSapet', MaTrace_System.FlowDict['E_2_3'].Values[:,:,:,r,:,:,:,:]) - MaTrace_System.FlowDict['E_8_1'].Values[:,:,:,R,r,:,:,h,:]# Solving recycling loop 
        ## Exporting these results for latter plotting
        np.save('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output//E01_case6', MaTrace_System.FlowDict['E_0_1'].Values[:,:,:,:,:,:,:,:,:])
        np.save('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E81_case6', MaTrace_System.FlowDict['E_8_1'].Values[:,:,:,:,:,:,:,:,:])
        np.save('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E13_case6', MaTrace_System.FlowDict['E_1_3'].Values[:,:,:,:,:,:,:,:])
        np.save('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output//E23_case6', MaTrace_System.FlowDict['E_2_3'].Values[:,:,:,:,:,:,:,:])

# %%

# %%

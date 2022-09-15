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
xlrd.xlsx.Element_has_iter = True


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
NV = len(IndexTable.Classification[IndexTable.index.get_loc('Size_Scenarios')].Items)


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
                                                             Indices = 'V,g,s,c', #t=time, h=units
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


ParameterDict['Degradation']= msc.Parameter(Name = 'Degradation', # Starts at 1 (suitable for vehicles but not SLBs)
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
                                            Indices = 'z,S,V,r,g,s,t', Values=None)
MaTrace_System.FlowDict['F_3_4'] = msc.Flow(Name = 'Outflows from use phase to market', P_Start = 3, P_End = 4,
                                            Indices = 'z,S,V,r,g,s,t,c', Values=None)
MaTrace_System.StockDict['S_3']   = msc.Stock(Name = 'xEV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,V,r,g,s,t', Values=None)
MaTrace_System.StockDict['S_C_3']   = msc.Stock(Name = 'xEV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,V,r,g,s,t,c', Values=None)
MaTrace_System.StockDict['dS_3']  = msc.Stock(Name = 'xEV stock change', P_Res = 3, Type = 1,
                                              Indices = 'z,S,V,r,g,s,t', Values=None)


# Define battery flows in number of batteries
MaTrace_System.FlowDict['M_1_2'] = msc.Flow(Name = 'Batteries sold to vehicle manufacturer', P_Start = 1, P_End = 2,
                                            Indices = 'z,S,a,V,r,g,s,b,t', Values=None)
MaTrace_System.FlowDict['M_1_3'] = msc.Flow(Name = 'Batteries sold for replacement in in-use stock', P_Start = 1, P_End = 3,
                                            Indices = 'z,S,a,V,r,g,s,b,t', Values=None)
MaTrace_System.FlowDict['M_2_3'] = msc.Flow(Name = 'Batteries in sold vehicles', P_Start = 2, P_End = 3,
                                            Indices = 'z,S,a,V,r,g,s,b,t', Values=None)
MaTrace_System.FlowDict['M_3_4_tc'] = msc.Flow(Name = 'Outflows from batteries in vechiles from use phase by cohort', P_Start = 3, P_End = 4,
                                            Indices = 'z,S,a,V,r,g,s,b,t,c', Values=None)
MaTrace_System.FlowDict['M_3_4'] = msc.Flow(Name = 'Outflows from batteries in vechiles from use phase', P_Start = 3, P_End = 4,
                                            Indices = 'z,S,a,V,r,g,s,b,t', Values=None)
MaTrace_System.FlowDict['M_4_5'] = msc.Flow(Name = 'From of LIBs after vehicle has been dismantled', P_Start = 4, P_End = 5,
                                            Indices = 'z,S,a,V,r,g,s,b,t,c', Values=None)
MaTrace_System.FlowDict['M_3_5'] = msc.Flow(Name = 'Outflows of failed batteries', P_Start = 3, P_End = 5,
                                            Indices = 'z,S,a,V,r,g,s,b,t,c', Values=None)
MaTrace_System.FlowDict['M_5_3'] = msc.Flow(Name = 'Inflwos from battery reuse', P_Start = 5, P_End = 3,
                                            Indices = 'z,S,a,V,r,g,s,b,t', Values=None)
MaTrace_System.StockDict['M_3']   = msc.Stock(Name = 'xEV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,V,r,g,s,b,t', Values=None)
MaTrace_System.StockDict['M_C_3']   = msc.Stock(Name = 'xEV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,V,r,g,s,b,t,c', Values=None)
MaTrace_System.StockDict['dM_3']  = msc.Stock(Name = 'xEV stock change', P_Res = 3, Type = 1,
                                              Indices = 'z,S,a,V,r,g,s,b,t,c', Values=None)

# Define battery flows in weight of batteries
MaTrace_System.FlowDict['B_1_2'] = msc.Flow(Name = 'Batteries sold to vehicle manufacturer', P_Start = 1, P_End = 2,
                                            Indices = 'z,S,a,V,r,g,s,b,t', Values=None)
MaTrace_System.FlowDict['B_1_3'] = msc.Flow(Name = 'Batteries sold for replacement in in-use stock', P_Start = 1, P_End = 3,
                                            Indices = 'z,S,a,V,r,g,s,b,t', Values=None)
MaTrace_System.FlowDict['B_2_3'] = msc.Flow(Name = 'Batteries in sold vehicles', P_Start = 2, P_End = 3,
                                            Indices = 'z,S,a,V,r,g,s,b,t', Values=None)
MaTrace_System.FlowDict['B_3_4_tc'] = msc.Flow(Name = 'Outflows from batteries in vechiles from use phase by cohort', P_Start = 3, P_End = 4,
                                            Indices = 'z,S,a,V,r,g,s,b,t,c', Values=None)
MaTrace_System.FlowDict['B_3_4'] = msc.Flow(Name = 'Outflows from batteries in vechiles from use phase', P_Start = 3, P_End = 4,
                                            Indices = 'z,S,a,V,r,g,s,b,t', Values=None)
MaTrace_System.FlowDict['B_4_5'] = msc.Flow(Name = 'From of LIBs after vehicle has been dismantled', P_Start = 4, P_End = 5,
                                            Indices = 'z,S,a,V,r,g,s,b,t,c', Values=None)
MaTrace_System.FlowDict['B_3_5'] = msc.Flow(Name = 'Outflows of failed batteries', P_Start = 3, P_End = 5,
                                            Indices = 'z,S,a,V,r,g,s,b,t,c', Values=None)
MaTrace_System.FlowDict['B_5_3'] = msc.Flow(Name = 'Inflwos from battery reuse', P_Start = 5, P_End = 3,
                                            Indices = 'z,S,a,V,r,g,s,b,t', Values=None)
MaTrace_System.StockDict['B_3']   = msc.Stock(Name = 'Battery in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,V,r,g,s,b,t', Values=None)
MaTrace_System.StockDict['B_C_3']   = msc.Stock(Name = 'Battery in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,V,r,g,s,b,t,c', Values=None)
MaTrace_System.StockDict['dB_3']  = msc.Stock(Name = 'Battery stock change', P_Res = 3, Type = 1,
                                              Indices = 'z,S,a,V,r,g,s,b,t,c', Values=None)

## Flows to be used for battery parts
MaTrace_System.FlowDict['P_1_2'] = msc.Flow(Name = 'Batteries sold to vehicle manufacturer by part', P_Start = 1, P_End = 2,
                                            Indices = 'z,S,a,V,r,g,s,b,p,t', Values=None)
MaTrace_System.FlowDict['P_1_3'] = msc.Flow(Name = 'Batteries sold for replacement in in-use stock by part', P_Start = 1, P_End = 3,
                                            Indices = 'z,S,a,V,r,g,s,b,p,t', Values=None)
MaTrace_System.FlowDict['P_2_3'] = msc.Flow(Name = 'Batteries in sold vehicles by part', P_Start = 2, P_End = 3,
                                            Indices = 'z,S,a,V,r,g,s,b,p,t', Values=None)
MaTrace_System.FlowDict['P_3_4_tc'] = msc.Flow(Name = 'Outflows from batteries in vechiles from use phase by cohort by part', P_Start = 3, P_End = 4,
                                            Indices = 'z,S,a,V,r,g,s,b,p,t,c', Values=None)
MaTrace_System.FlowDict['P_3_4'] = msc.Flow(Name = 'Outflows from batteries in vechiles from use phase by part', P_Start = 3, P_End = 4,
                                            Indices = 'z,S,a,V,r,g,s,b,p,t', Values=None)
MaTrace_System.FlowDict['P_4_5'] = msc.Flow(Name = 'From of LIBs after vehicle has been dismantled by part', P_Start = 4, P_End = 5,
                                            Indices = 'z,S,a,V,r,g,s,b,p,t,c', Values=None)
MaTrace_System.FlowDict['P_3_5'] = msc.Flow(Name = 'Outflows of failed batteries by part', P_Start = 3, P_End = 5,
                                            Indices = 'z,S,a,V,r,g,s,b,p,t,c', Values=None)
MaTrace_System.FlowDict['P_5_3'] = msc.Flow(Name = 'Inflwos from battery reuse by part', P_Start = 5, P_End = 3,
                                            Indices = 'z,S,a,V,r,g,s,b,p,t', Values=None)
MaTrace_System.FlowDict['P_5_6'] = msc.Flow(Name = 'Reused batteries for stationary storage', P_Start = 5, P_End = 6,
                                            Indices = 'z,S,a,R,V,r,g,b,p,t,c', Values=None)
MaTrace_System.FlowDict['P_1_6'] = msc.Flow(Name = 'New batteries share for stationary storage', P_Start = 0, P_End = 6,
                                            Indices = 'z,S,a,R,V,r,g,b,p,t,c', Values=None) # Formerly P06
MaTrace_System.FlowDict['P_6_7'] = msc.Flow(Name = 'ELB collection', P_Start = 6, P_End = 7,
                                            Indices = 'z,S,a,R,V,r,g,b,p,t,c', Values=None)
MaTrace_System.FlowDict['P_7_8'] = msc.Flow(Name = 'Flow to recycling after stationary use', P_Start = 7, P_End = 8,
                                            Indices = 'z,S,a,R,V,r,g,b,p,t,c', Values=None)
MaTrace_System.FlowDict['P_5_8'] = msc.Flow(Name = 'Share being direcly recycled', P_Start = 5, P_End = 8,
                                            Indices = 'z,S,a,R,V,r,g,b,p,t,c', Values=None)


MaTrace_System.StockDict['P_3']   = msc.Stock(Name = 'Battery in-use stock by part', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,V,r,g,s,b,p,t', Values=None)
MaTrace_System.StockDict['P_C_3']   = msc.Stock(Name = 'Battery in-use stock by part', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,V,r,g,s,b,p,t,c', Values=None)
MaTrace_System.StockDict['dP_3']  = msc.Stock(Name = 'Battery stock change by part', P_Res = 3, Type = 1,
                                              Indices = 'z,S,a,V,r,g,s,b,p,t,c', Values=None)
MaTrace_System.StockDict['dP_6']  = msc.Stock(Name = 'Stock change of batteries in stationary storage', P_Res = 3, Type = 1,
                                              Indices = 'z,S,a,R,V,r,b,p,t,c', Values=None)
MaTrace_System.StockDict['P_6']   = msc.Stock(Name = 'Stock of batteries in stationary storage', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,V,r,b,p,t', Values=None)
MaTrace_System.StockDict['P_C_6']   = msc.Stock(Name = 'Stock of batteries in stationary storage by cohort', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,V,r,g,b,p,t,c', Values=None)

# Energy layer
MaTrace_System.StockDict['C_3']   = msc.Stock(Name = 'xEV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,V,r,g,t', Values=None)
MaTrace_System.StockDict['C_6']   = msc.Stock(Name = 'xEV in-use stock', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,V,r,b,t', Values=None)
MaTrace_System.FlowDict['C_2_3'] = msc.Flow(Name = 'Batteries in sold vehicles', P_Start = 2, P_End = 3,
                                            Indices = 'z,S,a,V,r,g,s,b,t', Values=None)
MaTrace_System.FlowDict['C_5_6'] = msc.Flow(Name = 'Batteries in sold vehicles', P_Start = 5, P_End = 6,
                                            Indices = 'z,S,a,V,r,g,s,b,t', Values=None)

## Flows to be used for materials
MaTrace_System.FlowDict['E_1_2'] = msc.Flow(Name = 'Materials sold to vehicle manufacturer by part', P_Start = 1, P_End = 2,
                                            Indices = 'z,S,a,V,r,p,e,t', Values=None)
MaTrace_System.FlowDict['E_1_3'] = msc.Flow(Name = 'Materials sold for replacement in in-use stock by part', P_Start = 1, P_End = 3,
                                            Indices = 'z,S,a,V,r,p,e,t', Values=None)
MaTrace_System.FlowDict['E_2_3'] = msc.Flow(Name = 'Materials in sold vehicles by part', P_Start = 2, P_End = 3,
                                            Indices = 'z,S,a,V,r,p,e,t', Values=None)
MaTrace_System.FlowDict['E_3_4'] = msc.Flow(Name = 'Outflows from batteries in vechiles from use phase by Materials', P_Start = 3, P_End = 4,
                                            Indices = 'z,S,a,V,r,p,e,t', Values=None)
MaTrace_System.FlowDict['E_4_5'] = msc.Flow(Name = 'From of LIBs after vehicle has been dismantled by Materials', P_Start = 4, P_End = 5,
                                            Indices = 'z,S,a,V,r,p,e,t', Values=None)
MaTrace_System.FlowDict['E_3_5'] = msc.Flow(Name = 'Outflows of failed batteries by Materials', P_Start = 3, P_End = 5,
                                            Indices = 'z,S,a,V,r,p,e,t', Values=None)
MaTrace_System.FlowDict['E_5_3'] = msc.Flow(Name = 'Inflwos from battery reuse by Materials', P_Start = 5, P_End = 3,
                                            Indices = 'z,S,a,V,r,p,e,t', Values=None)
MaTrace_System.FlowDict['E_5_6'] = msc.Flow(Name = 'Reused Materials for stationary storage', P_Start = 5, P_End = 6,
                                            Indices = 'z,S,a,R,V,r,p,e,t', Values=None)
MaTrace_System.FlowDict['E_1_6'] = msc.Flow(Name = 'New Materials share for stationary storage', P_Start = 0, P_End = 6,
                                            Indices = 'z,S,a,R,V,r,p,e,t', Values=None) # Formerly P06
MaTrace_System.FlowDict['E_6_7'] = msc.Flow(Name = 'Materials ELB collection', P_Start = 6, P_End = 7,
                                            Indices = 'z,S,a,R,V,r,p,e,t', Values=None)
MaTrace_System.FlowDict['E_7_8'] = msc.Flow(Name = 'Flow to recycling after stationary use', P_Start = 7, P_End = 8,
                                            Indices = 'z,S,a,R,V,r,p,e,t', Values=None)
MaTrace_System.FlowDict['E_5_8'] = msc.Flow(Name = 'Share being direcly recycled', P_Start = 5, P_End = 8,
                                            Indices = 'z,S,a,R,V,r,p,e,t', Values=None)
MaTrace_System.FlowDict['E_8_1'] = msc.Flow(Name = 'Secondary materials for battery produciton', P_Start = 8, P_End = 1,
                                            Indices = 'z,S,a,R,V,r,p,e,h,t', Values=None)
MaTrace_System.FlowDict['E_8_0'] = msc.Flow(Name = 'Secondary materials losses', P_Start = 8, P_End = 0,
                                            Indices = 'z,S,a,R,V,r,p,e,h,t', Values=None)
MaTrace_System.FlowDict['E_0_1'] = msc.Flow(Name = 'Promary materials for battery produciton', P_Start = 0, P_End = 1,
                                            Indices = 'z,S,a,R,V,r,p,e,h,t', Values=None)
MaTrace_System.FlowDict['E_primary_Inflows'] = msc.Flow(Name = 'Total inflows resulting from the sum of second hand and retailer sales', P_Start = 2, P_End = 3,
                                            Indices = 'z,S,a,R,V,r,e,p,t', Values=None) #zSarept
MaTrace_System.StockDict['E_3']   = msc.Stock(Name = 'xEV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,V,r,p,e,t', Values=None)
MaTrace_System.StockDict['Ed_3']  = msc.Stock(Name = 'xEV stock change', P_Res = 3, Type = 1,
                                              Indices = 'z,S,a,V,r,p,e,t', Values=None)
MaTrace_System.StockDict['E_6']   = msc.Stock(Name = 'xEV in-use stock', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,V,r,g,e,t', Values=None)

MaTrace_System.StockDict['Ed_6']  = msc.Stock(Name = 'xEV stock change', P_Res = 6, Type = 1,
                                              Indices = 'z,S,a,R,r,e,t', Values=None)

MaTrace_System.Initialize_FlowValues()  # Assign empty arrays to flows according to dimensions.
MaTrace_System.Initialize_StockValues() # Assign empty arrays to flows according to dimensions.


#%%
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



r=5 #choose the regions to be calculated-. r is GLOBAL
cap = np.zeros((NS, Nr, Ng, Ns, Nb, Nt))
for z in range(Nz):
    #for r in range(0,Nr):
        for S in range(NS):
            for g in [1,2]:
                # In this case we assume that the product and component have the same lifetimes and set the delay as 3 years for both goods
                Model                                                     = pcm.ProductComponentModel(t = range(0,Nt), s_pr = MaTrace_System.ParameterDict['Vehicle_stock'].Values[z,r,:]/1000, lt_pr = {'Type': 'Normal', 'Mean': np.array([16]), 'StdDev': np.array([4]) }, \
                    lt_cm = {'Type': 'Normal', 'Mean': lt_cm, 'StdDev': sd_cm})
                Model.case_3()

                MaTrace_System.StockDict['S_C_3'].Values[z,S,:,r,g,:,:,:]             = np.einsum('Vsc,tc->Vstc', MaTrace_System.ParameterDict['Segment_shares'].Values[:,g,:,:] ,np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.sc_pr.copy()))
                MaTrace_System.StockDict['S_3'].Values[z,S,:,r,g,:,:]                 = np.einsum('Vstc->Vst', MaTrace_System.StockDict['S_C_3'].Values[z,S,:,r,g,:,:,:])
                MaTrace_System.FlowDict['F_2_3'].Values[z,S,:,r,g,:,:]              = np.einsum('Vsc,c->Vsc', MaTrace_System.ParameterDict['Segment_shares'].Values[:,g,:,:],np.einsum('c,c->c', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.i_pr.copy()))
                MaTrace_System.FlowDict['F_3_4'].Values[z,S,:,r,g,:,:,:]              = np.einsum('Vsc,tc->Vstc', MaTrace_System.ParameterDict['Segment_shares'].Values[:,g,:,:],np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:] , Model.oc_pr.copy()))
                

                ### Battery chemistry layer: Here we use the battery stock instead of the vehicle stock
                MaTrace_System.StockDict['M_C_3'].Values[z,S,:,:,r,g,:,:,:,:]     = np.einsum('abc,Vstc->aVsbtc', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , np.einsum('Vsc,tc->Vstc', MaTrace_System.ParameterDict['Segment_shares'].Values[:,g,:,:] \
                    ,np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.sc_cm.copy())))
                MaTrace_System.StockDict['M_3'].Values[z,S,:,:,r,g,:,:,:]         = np.einsum('aVsbtc->aVsbt', MaTrace_System.StockDict['M_C_3'].Values[z,S,:,:,r,g,:,:,:,:])
                # Battery inflows within car
                MaTrace_System.FlowDict['M_2_3'].Values[z,S,:,:,r,g,:,:,:]        = np.einsum('abt,Vst->aVsbt', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] ,MaTrace_System.FlowDict['F_2_3'].Values[z,S,:,r,g,:,:])
                # Battery replacements: Total battery inflows minus inflows of batteries in cars
                MaTrace_System.FlowDict['M_1_3'].Values[z,S,:,:,r,g,:,:,:]        = np.einsum('abc,Vsc->aVsbc', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , np.einsum('Vsc,c->Vsc', MaTrace_System.ParameterDict['Segment_shares'].Values[:,g,:,:], \
                    np.einsum('c,c->c', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.i_cm.copy()))) - MaTrace_System.FlowDict['M_2_3'].Values[z,S,:,:,r,g,:,:,:]
                # Battery outflows in car
                MaTrace_System.FlowDict['M_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:]   = np.einsum('abc,Vstc->aVsbtc', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , MaTrace_System.FlowDict['F_3_4'].Values[z,S,:,r,g,:,:,:])
                MaTrace_System.FlowDict['M_3_4'].Values[z,S,:,:,r,g,:,:,:]        = np.einsum('aVsbtc->aVsbt', MaTrace_System.FlowDict['M_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:])
                # Batteries after vehicle has been dismantled
                MaTrace_System.FlowDict['M_4_5'].Values[z,S,:,:,r,g,:,:,:,:]      = MaTrace_System.FlowDict['M_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:] 
                # Battery outflows due to battery failures: Total battery outflows minus vehicle outflows
                

                ### Battery by weight layer: Multiply the numbers by the weight factor for each chemistry and size
                # Stocks
                MaTrace_System.StockDict['B_C_3'].Values[z,S,:,:,r,g,:,:,:,:]     = np.einsum('sb,aVsbtc->aVsbtc', MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:] , MaTrace_System.StockDict['M_C_3'].Values[z,S,:,:,r,g,:,:,:,:])
                MaTrace_System.StockDict['B_3'].Values[z,S,:,:,r,g,:,:,:]         = np.einsum('aVsbtc->aVsbt', MaTrace_System.StockDict['B_C_3'].Values[z,S,:,:,r,g,:,:,:,:])
                MaTrace_System.FlowDict['B_1_3'].Values[z,S,:,:,r,g,:,:,:]        = np.einsum('aVsbt,sb->aVsbt', MaTrace_System.FlowDict['M_1_3'].Values[z,S,:,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:])
                MaTrace_System.FlowDict['B_2_3'].Values[z,S,:,:,r,g,:,:,:]        = np.einsum('aVsbt,sb->aVsbt', MaTrace_System.FlowDict['M_2_3'].Values[z,S,:,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:])
                MaTrace_System.FlowDict['B_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:]   = np.einsum('aVsbtc,sb->aVsbtc', MaTrace_System.FlowDict['M_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:], MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:])
                MaTrace_System.FlowDict['B_3_4'].Values[z,S,:,:,r,g,:,:,:]        = np.einsum('aVsbtc->aVsbt', MaTrace_System.FlowDict['B_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:] )
                MaTrace_System.FlowDict['B_4_5'].Values[z,S,:,:,r,g,:,:,:,:]      = MaTrace_System.FlowDict['B_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:] 
                # MaTrace_System.FlowDict['B_5_3'].Values[z,S,:,:,r,g,:,:,:]        = np.einsum('aVsbt,sb->aVsbt', MaTrace_System.FlowDict['M_5_3'].Values[z,S,:,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:])
                

                ### Battery parts layer
                MaTrace_System.StockDict['P_C_3'].Values[z,S,:,:,r,g,:,:,:,:,:]   = np.einsum('sbp,aVsbtc->aVsbptc', MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:] , MaTrace_System.StockDict['B_C_3'].Values[z,S,:,:,r,g,:,:,:,:])
                MaTrace_System.StockDict['P_3'].Values[z,S,:,:,r,g,:,:,:,:]       = np.einsum('aVsbptc->aVsbpt', MaTrace_System.StockDict['P_C_3'].Values[z,S,:,:,r,g,:,:,:,:,:])
                MaTrace_System.FlowDict['P_1_3'].Values[z,S,:,:,r,g,:,:,:,:]      = np.einsum('aVsbc,sbp->aVsbpc', MaTrace_System.FlowDict['B_1_3'].Values[z,S,:,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:]) 
                MaTrace_System.FlowDict['P_2_3'].Values[z,S,:,:,r,g,:,:,:,:]      = np.einsum('aVsbc,sbp->aVsbpc', MaTrace_System.FlowDict['B_2_3'].Values[z,S,:,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:]) 
                MaTrace_System.FlowDict['P_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:,:] = np.einsum('aVsbtc,sbp->aVsbptc', MaTrace_System.FlowDict['B_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:], MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:])
                MaTrace_System.FlowDict['P_3_4'].Values[z,S,:,:,r,g,:,:,:,:]      = np.einsum('aVsbptc->aVsbpt', MaTrace_System.FlowDict['P_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:,:])
                MaTrace_System.FlowDict['P_4_5'].Values[z,S,:,:,r,g,:,:,:,:,:]    = MaTrace_System.FlowDict['P_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:,:]
                # MaTrace_System.FlowDict['P_5_3'].Values[z,S,:,:,r,g,:,:,:,:]      = np.einsum('aVsbt,sbp->aVsbpt', MaTrace_System.FlowDict['B_5_3'].Values[z,S,:,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:])
                
                '''
                We calculate the flows of battery modules into reuse. Sicne the casing and other battery parts are assumed to go directly into recyling, 
                we just write this loop for the modules with index 0 and separately define that all other battery parts go to recycling. 
                We also consider batteries that caused vehicle outflows, as the requirements here are lower. We can take them out if it does not make sense. 

                The reuse parameter does not indicate the share of batteries that are reused. Rather, it is a condition to reflect decisions on which battery chemistries to 
                reuse. LFP scenario for instance will define that only LFP chemistries are considered for reuse, but they health assessment still needs to happen. 
                '''
                # Calculate inflows to SLB only for the modules. We consider batteries that came from failed vehicles as well, since flow P_3_5 only contains failed batteries
                MaTrace_System.FlowDict['P_5_6'].Values[z,S,:,:,:,r,g,:,0,:,:]  = np.einsum('Rbt,aVsbtc->aRVbtc', MaTrace_System.ParameterDict['Reuse_rate'].Values[:,:,:], \
                    MaTrace_System.FlowDict['P_3_4_tc'].Values[z,S,:,:,r,g,:,:,0,:,:]) # * Model_slb.sf_cm[t+tau_cm,c] + MaTrace_System.FlowDict['P_3_5'].Values[z,S,:,r,g,:,:,0,t,c]* Model_slb.sf_cm[t+tau_cm,c]) # TODO: Possibly subtract P_5_3 flow if implemented
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
#%%
'''
Define the SLB model in advance. We do not compute everything using the dsm as it only takes i as input
and takes too long to compute. Instead, we define the functions ourselves using the sf computed with dsm. 
'''
lt_slb                               = np.array([6]) # We could have different lifetimes for the different chemistries
sd_slb                               = np.array([2]) 
inflows                             = np.zeros((Nz,NS, Na, NR, NV,Ng,Nb, Nt))
inflows = np.einsum('zSaRVgbtc->zSaRVgbt',MaTrace_System.FlowDict['P_5_6'].Values[:,:,:,:,:,r,:,:,0,:,:])
for z in range(Nz):
    for S in range(NS):
        for a in range(Na):
            for R in range(NR):
                for b in range(Nb):
                    for V in range(NV):
                        for g in [1,2]: # Only BEV, PHEV
                            slb_model                        = dsm.DynamicStockModel(t=range(0,Nt), lt={'Type': 'Normal', 'Mean': lt_slb, 'StdDev': sd_slb}, i=inflows[z,S,a,R,V,g,b,:])
                            slb_model.compute_s_c_inflow_driven()
                            slb_model.compute_o_c_from_s_c()
                            slb_model.compute_stock_total()
                            MaTrace_System.StockDict['P_C_6'].Values[z,S,a,R,V,r,g,b,0,:,:] = slb_model.s_c.copy()
                            MaTrace_System.FlowDict['P_6_7'].Values[z,S,a,R,V,r,g,b,0,:,:] = slb_model.o_c.copy()

#%%
# Compute total stock
for a in range(Na):
    MaTrace_System.StockDict['P_6'].Values[:,:,a,:,:,r,:,0,:]         = np.einsum('zSRVgbtc->zSRVbt', MaTrace_System.StockDict['P_C_6'].Values[:,:,a,:,:,r,:,:,0,:,:])
    MaTrace_System.FlowDict['P_7_8'].Values[:,:,a,:,:,r,:,:,0,:,:]                  = MaTrace_System.FlowDict['P_6_7'].Values[:,:,a,:,:,r,:,:,0,:,:]
    # Calculate battery parts going directly to recycling: Total outflows minus reuse
    for R in range(NR):
        MaTrace_System.FlowDict['P_5_8'].Values[:,:,a,R,:,r,:,:,:,:,:]            =  np.einsum('zSVgsbptc->zSVgbptc', MaTrace_System.FlowDict['P_3_4_tc'].Values[:,:,a,:,r,:,:,:,:,:,:]) - MaTrace_System.FlowDict['P_5_6'].Values[:,:,a,R,:,r,:,:,:,:,:]

#%%
### Material layer
for z in range(Nz):
    # for S in range(NS):
        for a in range(Na):
            MaTrace_System.StockDict['E_3'].Values[z,:,a,:,r,:,:,:]           = np.einsum('SVgsbpt,gbpe->SVpet', MaTrace_System.StockDict['P_3'].Values[z,:,a,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:])
            MaTrace_System.FlowDict['E_1_3'].Values[z,:,a,:,r,:,:,:]          = np.einsum('SVgsbpc,gbpe->SVpec', MaTrace_System.FlowDict['P_1_3'].Values[z,:,a,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
            MaTrace_System.FlowDict['E_2_3'].Values[z,:,a,:,r,:,:,:]          = np.einsum('SVgsbpc,gbpe->SVpec', MaTrace_System.FlowDict['P_2_3'].Values[z,:,a,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
            MaTrace_System.FlowDict['E_3_4'].Values[z,:,a,:,r,:,:,:]          = np.einsum('SVgsbpt,gbpe->SVpet', MaTrace_System.FlowDict['P_3_4'].Values[z,:,a,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
            MaTrace_System.FlowDict['E_4_5'].Values[z,:,a,:,r,:,:,:]          = MaTrace_System.FlowDict['E_3_4'].Values[z,:,a,:,r,:,:,:]
            MaTrace_System.FlowDict['E_3_5'].Values[z,:,a,:,r,:,:,:]          = np.einsum('SVgsbptc,gbpe->SVpet', MaTrace_System.FlowDict['P_3_5'].Values[z,:,a,:,r,:,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
            # MaTrace_System.FlowDict['E_5_3'].Values[z,:,a,:,r,:,:,:]          = np.einsum('SVgsbpt,gbpe->SVpet', MaTrace_System.FlowDict['P_5_3'].Values[z,:,a,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
            MaTrace_System.FlowDict['E_5_6'].Values[z,:,a,:,:,r,:,:,:]        = np.einsum('SRVgbptc,gbpe->SRVpet', MaTrace_System.FlowDict['P_5_6'].Values[z,:,a,:,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
            MaTrace_System.FlowDict['E_5_8'].Values[z,:,a,:,:,r,:,:,:]        = np.einsum('SRVgbptc,gbpe->SRVpet', MaTrace_System.FlowDict['P_5_8'].Values[z,:,a,:,:,r,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
            MaTrace_System.FlowDict['E_6_7'].Values[z,:,a,:,:,r,:,:,:]        = np.einsum('SRVgbptc,gbpe->SRVpet', MaTrace_System.FlowDict['P_6_7'].Values[z,:,a,:,:,r,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
            MaTrace_System.FlowDict['E_7_8'].Values[z,:,a,:,:,r,:,:,:]        = np.einsum('SRVgbptc,gbpe->SRVpet', MaTrace_System.FlowDict['P_7_8'].Values[z,:,a,:,:,r,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
            MaTrace_System.FlowDict['E_8_1'].Values[z,:,a,:,:,r,:,:,:,:]      = np.einsum('eh, SRVpet->SRVpeht', MaTrace_System.ParameterDict['Recycling_efficiency'].Values[:,:], (MaTrace_System.FlowDict['E_7_8'].Values[z,:,a,:,:,r,:,:,:] + MaTrace_System.FlowDict['E_5_8'].Values[z,:,a,:,:,r,:,:,:]))
            for R in range(NR):
                for h in range(Nh):
                    MaTrace_System.FlowDict['E_0_1'].Values[z,:,a,R,:,r,:,:,h,:] =  MaTrace_System.FlowDict['E_2_3'].Values[z,:,a,:,r,:,:,:] - MaTrace_System.FlowDict['E_8_1'].Values[z,:,a,R,:,r,:,:,h,:]# +MaTrace_System.FlowDict['E_1_3'].Values[z,:,a,:,r,:,:,:] # Solving recycling loop z,S,a,R,V,r,p,e,h,t

# %%
# Storylines
from cycler import cycler
import seaborn as sns
r=5
custom_cycler = cycler(color=sns.color_palette('Set2', 20)) #'Set2', 'Paired', 'YlGnBu'
e01_replacements = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E01_case6.npy')
e01_long_lt = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E01_long_lt.npy')
e23_long_lt = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E23_long_lt.npy')
e81_replacements = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E81_case6.npy')
# sustainable = e01_replacements[0,2,2,2,r,:,:,0,:].sum(axis=0) # z,S,a,R,V,r,p,e,h,t
# resource = MaTrace_System.FlowDict['E_0_1'].Values[1,2,0,0,1,r,:,:,0,:].sum(axis=0)
# bau = MaTrace_System.FlowDict['E_0_1'].Values[1,1,6,0,1,r,:,:,1,:].sum(axis=0)
# slow = MaTrace_System.FlowDict['E_0_1'].Values[2,0,1,1,1,r,:,:,1,:].sum(axis=0)
# scen_5 = MaTrace_System.FlowDict['E_0_1'].Values[2,2,5,2,1,r,:,:,2,:].sum(axis=0)


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

def rec_content_sensitivity():
    from cycler import cycler
    import seaborn as sns
    from matplotlib.lines import Line2D
    e13_replacements = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E13_case6.npy') # zSarbpet
    e23_replacements = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E23_case6.npy') # zSarbpet
    e81_replacements = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E81_case6.npy')# zSaRrpeht
    
    fig, ax = plt.subplots(4,2,figsize=(20,28))
    # Define sensitivity analysis for Ni
    e = 7 # Ni
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,2,4,5,6]:
                for R in range(NR):
                    for h in range(Nh):
                        if h==0:
                            # Values from case 3
                            ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[0], alpha=0.02)
                            # Values from case 6
                            ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[0], alpha=0.02)
                        if h==1:
                            # Values from case 3
                            ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[1], alpha=0.02)
                            # # Values from case 6
                            ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[1], alpha=0.02)
                        if h==2:
                            # Values from case 3
                            ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[2], alpha=0.02)
                            # Values from case 6
                            ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[2], alpha=0.02)
    scen_cycler = cycler(color=sns.color_palette('viridis_r', 5))
    ax[0,0].set_prop_cycle(scen_cycler)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[0,2,2,2,:,:,e,0
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[0,2,2,:,:,:,e,70:] + e23_replacements[0,2,2,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,2,0,0,:,:,e,0
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,2,0,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,2,0,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,1,6,0,:,:,e,1
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,1,6,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,1,6,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,0,1,1,:,:,e,1
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,0,1,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,0,1,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[2,2,5,2,:,:,e,2
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[2,2,5,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[2,2,5,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[0,0].set_ylabel('Recycled content Ni [%]',fontsize =18)
    right_side = ax[0,0].spines["right"]
    right_side.set_visible(False)
    top = ax[0,0].spines["top"]
    top.set_visible(False)
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
                        if h==0:
                            # Values from case 3
                            ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[0], alpha=0.02)
                            # Values from case 6
                            ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[0], alpha=0.02)
                        if h==1:
                            # Values from case 3
                            ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[1], alpha=0.02)
                            # # Values from case 6
                            ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[1], alpha=0.02)
                        if h==2:
                            # Values from case 3
                            ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[2], alpha=0.02)
                            # Values from case 6
                            ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[2], alpha=0.02)
    ax[0,1].set_prop_cycle(scen_cycler)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[0,2,2,2,:,:,e,0
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[0,2,2,:,:,:,e,70:] + e23_replacements[0,2,2,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,2,0,0,:,:,e,0
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,2,0,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,2,0,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,1,6,0,:,:,e,1
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,1,6,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,1,6,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,0,1,1,:,:,e,1
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,0,1,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,0,1,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[2,2,5,2,:,:,e,2
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[2,2,5,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[2,2,5,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[0,1].set_ylabel('Recycled content Li [%]',fontsize =18)
    right_side = ax[0,1].spines["right"]
    right_side.set_visible(False)
    top = ax[0,1].spines["top"]
    top.set_visible(False)
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
                        if h==0:
                            # Values from case 3
                            ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[0], alpha=0.02)
                            # Values from case 6
                            ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[0], alpha=0.02)
                        if h==1:
                            # Values from case 3
                            ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[1], alpha=0.02)
                            # # Values from case 6
                            ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[1], alpha=0.02)
                        if h==2:
                            # Values from case 3
                            ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[2], alpha=0.02)
                            # Values from case 6
                            ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[2], alpha=0.02)
    ax[1,0].set_prop_cycle(scen_cycler)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[0,2,2,2,:,:,e,0
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[0,2,2,:,:,:,e,70:] + e23_replacements[0,2,2,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,2,0,0,:,:,e,0
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,2,0,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,2,0,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,1,6,0,:,:,e,1
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,1,6,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,1,6,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,0,1,1,:,:,e,1
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,0,1,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,0,1,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[2,2,5,2,:,:,e,2
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[2,2,5,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[2,2,5,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[1,0].set_ylabel('Recycled content Co [%]',fontsize =18)
    right_side = ax[1,0].spines["right"]
    right_side.set_visible(False)
    top = ax[1,0].spines["top"]
    top.set_visible(False)
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
                        if h==0:
                            # Values from case 3
                            ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[0], alpha=0.02)
                            # Values from case 6
                            ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[0], alpha=0.02)
                        if h==1:
                            # Values from case 3
                            ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[1], alpha=0.02)
                            # # Values from case 6
                            ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[1], alpha=0.02)
                        if h==2:
                            # Values from case 3
                            ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[2], alpha=0.02)
                            # Values from case 6
                            ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[2], alpha=0.02)
    ax[1,1].set_prop_cycle(scen_cycler)
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[0,2,2,2,:,:,e,0
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[0,2,2,:,:,:,e,70:] + e23_replacements[0,2,2,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,2,0,0,:,:,e,0
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,2,0,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,2,0,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,1,6,0,:,:,e,1
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,1,6,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,1,6,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,0,1,1,:,:,e,1
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,0,1,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,0,1,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[2,2,5,2,:,:,e,2
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[2,2,5,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[2,2,5,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[1,1].set_ylabel('Recycled content P [%]',fontsize =18)
    right_side = ax[1,1].spines["right"]
    right_side.set_visible(False)
    top = ax[1,1].spines["top"]
    top.set_visible(False)
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
                        if h==0:
                            # Values from case 3
                            ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[0], alpha=0.02)
                            # Values from case 6
                            ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[0], alpha=0.02)
                        if h==1:
                            # Values from case 3
                            ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[1], alpha=0.02)
                            # # Values from case 6
                            ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[1], alpha=0.02)
                        if h==2:
                            # Values from case 3
                            ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[2], alpha=0.02)
                            # Values from case 6
                            ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[2], alpha=0.02)
    ax[2,0].set_prop_cycle(scen_cycler)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[0,2,2,2,:,:,e,0
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[0,2,2,:,:,:,e,70:] + e23_replacements[0,2,2,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,2,0,0,:,:,e,0
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,2,0,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,2,0,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,1,6,0,:,:,e,1
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,1,6,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,1,6,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,0,1,1,:,:,e,1
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,0,1,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,0,1,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[2,2,5,2,:,:,e,2
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[2,2,5,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[2,2,5,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[2,0].set_ylabel('Recycled content Al [%]',fontsize =18)
    right_side = ax[2,0].spines["right"]
    right_side.set_visible(False)
    top = ax[2,0].spines["top"]
    top.set_visible(False)
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
                        if h==0:
                            # Values from case 3
                            ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[0], alpha=0.02)
                            # Values from case 6
                            ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[0], alpha=0.02)
                        if h==1:
                            # Values from case 3
                            ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[1], alpha=0.02)
                            # # Values from case 6
                            ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[1], alpha=0.02)
                        if h==2:
                            # Values from case 3
                            ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[2], alpha=0.02)
                            # Values from case 6
                            ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[2], alpha=0.02)
    ax[2,1].set_prop_cycle(scen_cycler)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[0,2,2,2,:,:,e,0
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[0,2,2,:,:,:,e,70:] + e23_replacements[0,2,2,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,2,0,0,:,:,e,0
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,2,0,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,2,0,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,1,6,0,:,:,e,1
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,1,6,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,1,6,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,0,1,1,:,:,e,1
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,0,1,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,0,1,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[2,2,5,2,:,:,e,2
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[2,2,5,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[2,2,5,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[2,1].set_ylabel('Recycled content C [%]',fontsize =18)
    right_side = ax[2,1].spines["right"]
    right_side.set_visible(False)
    top = ax[2,1].spines["top"]
    top.set_visible(False)
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
                        if h==0:
                            # Values from case 3
                            ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[0], alpha=0.02)
                            # Values from case 6
                            ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[0], alpha=0.02)
                        if h==1:
                            # Values from case 3
                            ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[1], alpha=0.02)
                            # # Values from case 6
                            ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[1], alpha=0.02)
                        if h==2:
                            # Values from case 3
                            ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[2], alpha=0.02)
                            # Values from case 6
                            ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[2], alpha=0.02)
    ax[3,0].set_prop_cycle(scen_cycler)
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[0,2,2,2,:,:,e,0
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[0,2,2,:,:,:,e,70:] + e23_replacements[0,2,2,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,2,0,0,:,:,e,0
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,2,0,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,2,0,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,1,6,0,:,:,e,1
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,1,6,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,1,6,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,0,1,1,:,:,e,1
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,0,1,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,0,1,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[2,2,5,2,:,:,e,2
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[2,2,5,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[2,2,5,:,:,:,e,70:])/1000000)*100, linewidth=3)
    ax[3,0].set_ylabel('Recycled content Mn [%]',fontsize =18)
    right_side = ax[3,0].spines["right"]
    right_side.set_visible(False)
    top = ax[3,0].spines["top"]
    top.set_visible(False)
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
                        if h==0:
                            # Values from case 3
                            ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[0], alpha=0.02)
                            # Values from case 6
                            ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[0], alpha=0.02)
                        if h==1:
                            # Values from case 3
                            ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[1], alpha=0.02)
                            # # Values from case 6
                            ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[1], alpha=0.02)
                        if h==2:
                            # Values from case 3
                            ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[z,S,a,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[2], alpha=0.02)
                            # Values from case 6
                            ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[z,S,a,R,:,:,e,h
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[z,S,a,:,:,:,e,70:] + e23_replacements[z,S,a,:,:,:,e,70:])/1000000)*100, color=sns.color_palette('viridis_r', 3)[2], alpha=0.02)
    ax[3,1].set_prop_cycle(scen_cycler)
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', e81_replacements[0,2,2,2,:,:,e,0
                                        ,70:]/1000000)/np.einsum('rbpt->t', (e13_replacements[0,2,2,:,:,:,e,70:] + e23_replacements[0,2,2,:,:,:,e,70:])/1000000)*100, linewidth=3, label='Resource efficient')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,2,0,0,:,:,e,0
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,2,0,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,2,0,:,:,:,e,70:])/1000000)*100, linewidth=3, label='Slow transition')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,1,6,0,:,:,e,1
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,1,6,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,1,6,:,:,:,e,70:])/1000000)*100, linewidth=3, label='Baseline')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[1,0,1,1,:,:,e,1
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[1,0,1,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[1,0,1,:,:,:,e,70:])/1000000)*100, linewidth=3, label='Efficient recycling')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpt->t', MaTrace_System.FlowDict['E_8_1'].Values[2,2,5,2,:,:,e,2
                                        ,70:]/1000000)/np.einsum('rbpt->t', (MaTrace_System.FlowDict['E_1_3'].Values[2,2,5,:,:,:,e,70:] + MaTrace_System.FlowDict['E_2_3'].Values[2,2,5,:,:,:,e,70:])/1000000)*100, linewidth=3, label='Resource intensive')
    ax[3,1].set_ylabel('Recycled content Si [%]',fontsize =18)
    right_side = ax[3,1].spines["right"]
    right_side.set_visible(False)
    top = ax[3,1].spines["top"]
    top.set_visible(False)
    custom_lines = [Line2D([0], [0], color=sns.color_palette('viridis_r', 3)[0], lw=1),
                Line2D([0], [0], color=sns.color_palette('viridis_r', 3)[1], lw=1),
                Line2D([0], [0], color=sns.color_palette('viridis_r', 3)[2], lw=1),
                Line2D([0], [0], color=sns.color_palette('viridis_r', 5)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('viridis_r', 5)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('viridis_r', 5)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('viridis_r', 5)[3], lw=3),
                Line2D([0], [0], color=sns.color_palette('viridis_r', 5)[4], lw=3)
                ]
    ax[3,1].set_title('h) Silicon', fontsize=20)
    ax[3,1].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[3,1].tick_params(axis='both', which='major', labelsize=18)
    lines_labels = [ax.get_legend_handles_labels() for ax in fig.axes]
    lines, labels = [sum(lol, []) for lol in zip(*lines_labels)]
    fig.legend(custom_lines, ['Direct recycling', 'Hydrometallurgical recycling', 'Pyrometallurgical recycling']+labels, loc='lower left', prop={'size':20}, bbox_to_anchor =(0.1, 0), ncol = 3, columnspacing = 1, handletextpad = 2, handlelength = 2)
    #fig.legend(scen_lines, ['Slow EV penetration scenarios', 'Medium EV penetration scenarios', 'Fast EV penetration scenarios'], loc='upper left',prop={'size':20}, bbox_to_anchor =(1, 0.7), fontsize=20)
    # Add title
    fig.suptitle('Recycled content by material for all scenarios', fontsize=30)
    fig.subplots_adjust(top=0.92, bottom=0.08)
    fig.savefig(os.getcwd() + '/results/overview/rec_content_sensitivity', dpi=300)

def flows():
    fig, ax = plt.subplots(1,2, figsize=(17,8))
    ax[0].set_prop_cycle(custom_cycler)
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[0,0,1,r,1,:,55:]/1000), 'y--', label='Low STEP')
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[1,0,1,r,1,:,55:]/1000), 'yx', label='Medium STEP')
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[2,0,1,r,1,:,55:]/1000), 'y.', label='High STEP')
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[0,1,1,r,1,:,55:]/1000), 'b--', label='Low SD')
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[1,1,1,r,1,:,55:]/1000), 'bx', label='Medium SD')
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[2,1,1,r,1,:,55:]/1000), 'b.', label='High SD')
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[0,2,1,r,1,:,55:]/1000), 'r--', label='Low Net Zero')
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[1,2,1,r,1,:,55:]/1000), 'rx', label='Medium Net Zero')
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[2,2,1,r,1,:,55:]/1000), 'r.', label='High Net Zero')
    ax[0].set_ylabel('Nr. of Vehicles [million]',fontsize =18)
    right_side = ax[0].spines["right"]
    right_side.set_visible(False)
    top = ax[0].spines["top"]
    top.set_visible(False)
    ax[0].legend(loc='upper left',prop={'size':16})
    ax[0].set_title('a) Yearly new vehicle registrations', fontsize=20)
    ax[0].set_xlabel('Year',fontsize =18)
    ax[0].tick_params(axis='both', which='major', labelsize=16)
    ax[0].set_ylim([0,500])
    ax[0].set_xlim([2015,2050])
    ax[0].grid()
    
    ax[1].set_prop_cycle(custom_cycler)
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[0,0,1,r,1,:,55:,:]/1000), 'y--', label='Low STEP')
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[2,0,1,r,1,:,55:,:]/1000), 'y.', label='High STEP')
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[1,0,1,r,1,:,55:,:]/1000), 'yx', label='Medium STEP')
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[0,1,1,r,1,:,55:,:]/1000), 'b--', label='Low SD')
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[1,1,1,r,1,:,55:,:]/1000), 'bx', label='Medium SD')
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[2,1,1,r,1,:,55:,:]/1000), 'b.', label='High SD')
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[0,2,1,r,1,:,55:,:]/1000), 'r--', label='Low Net Zero')
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[1,2,1,r,1,:,55:,:]/1000), 'rx', label='Medium Net Zero')
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[2,2,1,r,1,:,55:,:]/1000), 'r.', label='High Net Zero')
    ax[1].set_ylabel('Nr. of Vehicles [million]',fontsize =18)
    right_side = ax[1].spines["right"]
    right_side.set_visible(False)
    top = ax[1].spines["top"]
    top.set_visible(False)
    ax[1].legend(loc='upper left',prop={'size':16})
    ax[1].set_title('b) Yearly vehicle outflows', fontsize=20)
    ax[1].set_xlabel('Year',fontsize =18)
    ax[1].tick_params(axis='both', which='major', labelsize=16)
    ax[1].set_ylim([0,500])
    ax[1].set_xlim([2015,2050])
    ax[1].grid()
    fig.savefig(os.getcwd() + '/results/overview/system_flows', dpi=600, bbox_inches='tight')

def flows_alt():
    custom_cycler = cycler(color=sns.color_palette('Paired', 20)) #'Set2', 'Paired', 'YlGnBu'
    fig, ax = plt.subplots(1,3, figsize=(21,10))
    ax[0].set_prop_cycle(custom_cycler)
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[0,0,1,r,1,:,55:]/1000))
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[0,0,1,r,1,:,55:,:]/1000))
    
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[0,1,1,r,1,:,55:]/1000))
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[0,1,1,r,1,:,55:,:]/1000))
    
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[0,2,1,r,1,:,55:]/1000))
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[0,2,1,r,1,:,55:,:]/1000))
    
    fill_cycler = cycler(color=sns.color_palette('Set1', 20)) #'Set2', 'Paired', 'YlGnBu'
    ax[0].set_prop_cycle(fill_cycler)
    ax[0].fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55:],np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[0,2,1,r,1,:,55:]/1000),\
        np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[0,2,1,r,1,:,55:,:]/1000), alpha=0.2)
    ax[0].fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55:],np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[0,0,1,r,1,:,55:]/1000),\
        np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[0,0,1,r,1,:,55:,:]/1000), alpha=0.2)
    ax[0].fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55:],np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[0,1,1,r,1,:,55:]/1000),\
        np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[0,1,1,r,1,:,55:,:]/1000), alpha=0.2)
    
    ax[0].set_ylabel('Nr. of Vehicles [million]',fontsize =18)
    right_side = ax[0].spines["right"]
    right_side.set_visible(False)
    top = ax[0].spines["top"]
    top.set_visible(False)
    ax[0].set_title('a) Low stock scenarios', fontsize=20)
    ax[0].set_xlabel('Year',fontsize =18)
    ax[0].tick_params(axis='both', which='major', labelsize=16)
    ax[0].set_ylim([0,450])
    ax[0].set_xlim([2015,2050])
    ax[0].grid()
    
    custom_cycler = cycler(color=sns.color_palette('Paired', 20)) #'Set2', 'Paired', 'YlGnBu'
    ax[1].set_prop_cycle(custom_cycler)
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[1,0,1,r,1,:,55:]/1000))
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[1,0,1,r,1,:,55:,:]/1000))
    
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[1,1,1,r,1,:,55:]/1000))
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[1,1,1,r,1,:,55:,:]/1000))
    
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[1,2,1,r,1,:,55:]/1000))
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[1,2,1,r,1,:,55:,:]/1000))
    
    fill_cycler = cycler(color=sns.color_palette('Set1', 20)) #'Set2', 'Paired', 'YlGnBu'
    ax[1].set_prop_cycle(fill_cycler)
    ax[1].fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55:],np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[1,2,1,r,1,:,55:]/1000),\
        np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[1,2,1,r,1,:,55:,:]/1000), alpha=0.2)
    ax[1].fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55:],np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[1,0,1,r,1,:,55:]/1000),\
        np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[1,0,1,r,1,:,55:,:]/1000), alpha=0.2)
    ax[1].fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55:],np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[1,1,1,r,1,:,55:]/1000),\
        np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[1,1,1,r,1,:,55:,:]/1000), alpha=0.2)
    
    ax[1].set_ylabel('Nr. of Vehicles [million]',fontsize =18)
    right_side = ax[1].spines["right"]
    right_side.set_visible(False)
    top = ax[1].spines["top"]
    top.set_visible(False)
    ax[1].set_title('b) Medium stock scenarios', fontsize=20)
    ax[1].set_xlabel('Year',fontsize =18)
    ax[1].tick_params(axis='both', which='major', labelsize=16)
    ax[1].set_ylim([0,450])
    ax[1].set_xlim([2015,2050])
    ax[1].grid()
    
    custom_cycler = cycler(color=sns.color_palette('Paired', 20)) #'Set2', 'Paired', 'YlGnBu'    ax[2].set_prop_cycle(custom_cycler)
    ax[2].set_prop_cycle(custom_cycler)
    ax[2].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[2,0,1,r,1,:,55:]/1000), label='STEP inflows')
    ax[2].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[2,0,1,r,1,:,55:,:]/1000), label='STEP outflows')
    
    ax[2].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[2,1,1,r,1,:,55:]/1000), label='SD inflows')
    ax[2].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[2,1,1,r,1,:,55:,:]/1000), label='SD outflows')
    
    ax[2].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[2,2,1,r,1,:,55:]/1000), label='Net Zero inflows')
    ax[2].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[2,2,1,r,1,:,55:,:]/1000), label='Net Zero outflows')
    
    fill_cycler = cycler(color=sns.color_palette('Set1', 20)) #'Set2', 'Paired', 'YlGnBu'
    ax[2].set_prop_cycle(fill_cycler)
    ax[2].fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55:],np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[2,2,1,r,1,:,55:]/1000),\
        np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[2,2,1,r,1,:,55:,:]/1000), label='Inflow-outflow gap Net Zero', alpha=0.2)
    ax[2].fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55:],np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[2,0,1,r,1,:,55:]/1000),\
        np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[2,0,1,r,1,:,55:,:]/1000), label='Inflow-outflow gap needs SD', alpha=0.2)
    ax[2].fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55:],np.einsum('st->t', MaTrace_System.FlowDict['F_2_3'].Values[2,1,1,r,1,:,55:]/1000),\
        np.einsum('stc->t', MaTrace_System.FlowDict['F_3_4'].Values[2,1,1,r,1,:,55:,:]/1000), label='Inflow-outflow gap needs STEP', alpha=0.2)
    
    ax[2].set_ylabel('Nr. of Vehicles [million]',fontsize =18)
    right_side = ax[1].spines["right"]
    right_side.set_visible(False)
    top = ax[1].spines["top"]
    top.set_visible(False)
    ax[2].set_title('c) High stock scenarios', fontsize=20)
    ax[2].set_xlabel('Year',fontsize =18)
    ax[2].tick_params(axis='both', which='major', labelsize=16)
    ax[2].set_ylim([0,450])
    ax[2].set_xlim([2015,2050])
    ax[2].grid()
    fig.legend(loc='lower left', prop={'size':20}, bbox_to_anchor =(0.1, -0.1), ncol = 3, columnspacing = 1, handletextpad = 2, handlelength = 2)
    fig.savefig(os.getcwd() + '/results/overview/system_flows_alt', dpi=600, bbox_inches='tight')

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
                    0, color = 'b', alpha = 0.3, label='Low STEP')
    last = MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000
    z=1
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000 ,\
                    last, color = 'b', alpha = 0.6, label='Medium STEP')
    last = MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000
    z=2
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000 ,\
                    last, color = 'b', alpha = 0.9, label='High STEP')
    last = MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000
    z=0
    S=1
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000 ,\
                    last, color = 'g', alpha = 0.3, label='Low SD')
    last = MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000
    z=1
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000 ,\
                    last, color = 'g', alpha = 0.6, label='Medium SD')
    last = MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000
    z=2
    ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                MaTrace_System.StockDict['P_6'].Values[z,S,a,R,r,:,0,55::].sum(axis=0)/1000000 ,\
                    last, color = 'g', alpha = 0.9, label='High SD')
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
        fig.savefig(os.getcwd() + f'/results/SI/chemistry_scenario_{b}.pdf', dpi=600, bbox_inches='tight')

def strategies_comparative():
    from cycler import cycler
    import seaborn as sns
    r=5
    custom_cycler = cycler(color=sns.color_palette('tab10', 20)) #'Set2', 'Paired', 'YlGnBu'
    # Load replacement results
    e01_replacements = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E01_case6.npy')
        # Define storylines
    fig, ax = plt.subplots(4,2,figsize=(20,28))
    ax[0,0].set_prop_cycle(custom_cycler)
    e = 7 # Ni
    z = 1 # Baseline
    S = 1 # Baseline
    a = 6 # BNEF
    R = 0 # LFP reuse
    V = 1 # Baseline vehicle size
    h = 1 # Hydrometallurgical
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, linewidth=4)
    a = 1 # High LFP
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    a = 0 # NCX
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    a = 2 # Next_Gen
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    a=6
    z = 0 # Low
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    z = 1 # Base
    h = 0 # Direct
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    h = 1 # Hydro
    S=2
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    S=1
    V=0
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    V=1
    h = 1 # Hydrometallurgy
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000)
    ax[0,0].set_ylabel('Primary Ni demand [Mt]',fontsize =18)
    right_side = ax[0,0].spines["right"]
    right_side.set_visible(False)
    top = ax[0,0].spines["top"]
    top.set_visible(False)
    ax[0,0].set_title('a) Nickel', fontsize=20)
    ax[0,0].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[0,0].tick_params(axis='both', which='major', labelsize=18)
    ax[0,0].grid()
    ## Plot Li
    ax[0,1].set_prop_cycle(custom_cycler)
    e = 0 # Li
    z = 1 # Baseline
    S = 1 # Baseline
    a = 6 # BNEF
    R = 0 # LFP reuse
    h = 1 # Hydrometallurgical
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, linewidth=4)
    a = 1 # High LFP

    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    a = 0 # NCX
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    a = 2 # Next gen
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    a = 6 # LFP reused
    z = 0 # Low
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    z = 1 # Low
    h = 0 # Direct
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    h = 1 # Hydro
    S = 2 # net zero
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    S=1 #base
    V=0
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    V = 1 # base
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000)
    ax[0,1].set_ylabel('Primary Li demand [Mt]',fontsize =18)
    right_side = ax[0,1].spines["right"]
    right_side.set_visible(False)
    top = ax[0,1].spines["top"]
    top.set_visible(False)
    ax[0,1].set_title('b) Lithium', fontsize=20)
    ax[0,1].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[0,1].tick_params(axis='both', which='major', labelsize=18)
    ax[0,1].grid()
    ## Plot Co
    ax[1,0].set_prop_cycle(custom_cycler)
    e = 6 # Co
    z = 1 # Baseline
    S = 1 # Baseline
    a = 6 # BNEF
    R = 0 # LFP reuse
    h = 1 # Hydrometallurgical
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, linewidth=4)
    a = 1 # High LFP
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    a = 0 # NCX
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    a = 2 # Next gen
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    a = 6
    z = 0 # Low
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    z = 1 # Low
    h = 0 # Direct
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    h = 1 # base
    S = 2
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    S = 1 # base
    V = 0 # smaller
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    V = 1 # base
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000)
    ax[1,0].set_ylabel('Primary Co demand [Mt]',fontsize =18)
    right_side = ax[1,0].spines["right"]
    right_side.set_visible(False)
    top = ax[1,0].spines["top"]
    top.set_visible(False)
    ax[1,0].set_title('c) Cobalt', fontsize=20)
    ax[1,0].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[1,0].tick_params(axis='both', which='major', labelsize=18)
    ax[1,0].grid()
    ## Plot P
    ax[1,1].set_prop_cycle(custom_cycler)
    e = 4 # P
    z = 1 # Baseline
    S = 1 # Baseline
    a = 6 # BNEF
    R = 0 # LFP reuse
    h = 1 # Hydrometallurgical
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, linewidth=4)
    a = 1 # High LFP
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    a = 0 # NCX
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    a = 2 # Next gen
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    a = 6 #base
    z = 0 # Low
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    z = 1 # Low
    h = 0 # Direct
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    h = 1 # Low
    S = 2 # Direct
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    S = 1 # Low
    V = 0 # Direct
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    V = 1 # Direct
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000)
    ax[1,1].set_ylabel('Primary P demand [Mt]',fontsize =18)
    right_side = ax[1,1].spines["right"]
    right_side.set_visible(False)
    top = ax[1,1].spines["top"]
    top.set_visible(False)
    ax[1,1].set_title('d) Phosphorous', fontsize=20)
    ax[1,1].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[1,1].tick_params(axis='both', which='major', labelsize=18)
    ax[1,1].grid()
    ## Plot Al
    ax[2,0].set_prop_cycle(custom_cycler)
    e = 2 # Al
    z = 1 # Baseline
    S = 1 # Baseline
    a = 6 # BNEF
    R = 0 # LFP reuse
    h = 1 # Hydrometallurgical
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, linewidth=4)
    a = 1 # High LFP
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    a = 0 # NCX
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    a = 2 # Nextgen
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    a = 6
    z = 0 # Low
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    z = 1 # Low
    h = 0 # Direct
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    h = 1 # Low
    S = 2 # Direct
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    S = 1 # Low
    V = 0 # Direct
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    V=1
    h = 1 # Hydro
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000)
    ax[2,0].set_ylabel('Primary Al demand [Mt]',fontsize =18)
    right_side = ax[2,0].spines["right"]
    right_side.set_visible(False)
    top = ax[2,0].spines["top"]
    top.set_visible(False)
    ax[2,0].set_title('e) Aluminium', fontsize=20)
    ax[2,0].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[2,0].tick_params(axis='both', which='major', labelsize=18)
    ax[2,0].grid()
    ## Plot Graphite
    ax[2,1].set_prop_cycle(custom_cycler)
    e = 1 # Graphite
    z = 1 # Baseline
    S = 1 # Baseline
    a = 6 # BNEF
    R = 0 # LFP reuse
    h = 1 # Hydrometallurgical
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, linewidth=4)
    a = 1 # High LFP
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    a = 0 # NCx
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    a = 2 # NCx
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    a=6
    z = 0 # Low
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    z = 1 # Low
    h = 0 # Direct
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    h = 1 # Low
    S = 2 # Direct
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    S = 1 # Low
    V = 0 # Direct
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    V=1
    h = 1 # Hydro
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000)
    ax[2,1].set_ylabel('Primary Graphite demand [Mt]',fontsize =18)
    right_side = ax[2,1].spines["right"]
    right_side.set_visible(False)
    top = ax[2,1].spines["top"]
    top.set_visible(False)
    ax[2,1].set_title('f) Graphite', fontsize=20)
    ax[2,1].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[2,1].tick_params(axis='both', which='major', labelsize=18)
    ax[2,1].grid()
    
    ## Plot Mn
    ax[3,0].set_prop_cycle(custom_cycler)
    e = 5 # Mn
    z = 1 # Baseline
    S = 1 # Baseline
    a = 6 # BNEF
    R = 0 # LFP reuse
    h = 1 # Hydrometallurgical
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, linewidth=4)
    a = 1 # High LFP
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    a = 0 # BNEF
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    a = 2 # BNEF
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    a=6
    z = 0 # Low
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    z = 1 # Low
    h = 0 # Direct
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    h = 1 # Low
    S = 2 # Direct
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    S = 1 # Low
    V = 0 # Direct
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000)
    V=1
    h = 1 # Hydro
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000)
    ax[3,0].set_ylabel('Primary Mn demand [Mt]',fontsize =18)
    right_side = ax[3,0].spines["right"]
    right_side.set_visible(False)
    top = ax[3,0].spines["top"]
    top.set_visible(False)
    ax[3,0].set_title('g) Manganese', fontsize=20)
    ax[3,0].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[3,0].tick_params(axis='both', which='major', labelsize=18)
    ax[3,0].grid()
    
    ## Plot Si
    ax[3,1].set_prop_cycle(custom_cycler)
    e = 3 # Si
    z = 1 # Baseline
    S = 1 # Baseline
    a = 6 # BNEF
    R = 0 # LFP reuse
    h = 1 # Hydrometallurgical
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, linewidth=4, label='Baseline')
    a = 1 # High LFP
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, label='Shift to LFP')
    a = 0 # BNEF
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, label = 'Shift to high Ni')
    a = 2 # BNEF
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, label = 'Shift to next gen.')
    a=6
    z = 0 # Low
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, label = 'Smaller fleet')
    z = 1 # Low
    h = 0 # Direct
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, label = 'Efficient recycling')
    h = 1 # Low
    S = 2 # Direct
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, label = 'Faster electrification')
    S = 1 # Low
    V = 0 # Direct
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, label = 'Smaller batteries')
    V=1
    h = 1 # Hydro
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
            np.einsum('pt->t', e01_replacements[z,S,a,R,r,:,e,h,65::])/1000000, label = 'Replacements')
    ax[3,1].set_ylabel('Primary Si demand [Mt]',fontsize =18)
    right_side = ax[3,1].spines["right"]
    right_side.set_visible(False)
    top = ax[3,1].spines["top"]
    top.set_visible(False)
    ax[3,1].set_title('h) Silicon', fontsize=20)
    ax[3,1].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[3,1].tick_params(axis='both', which='major', labelsize=18)
    ax[3,1].grid()
    
    fig.suptitle('Primary resource use sensitivity to parameters', fontsize=30, y=0.92)
    fig.legend(loc='lower left', prop={'size':20}, bbox_to_anchor =(0.2, 0.05), ncol = 3, columnspacing = 1, handletextpad = 2, handlelength = 2)
    fig.savefig(os.getcwd() + '/results/overview/resource_strategies', dpi=600, bbox_inches = 'tight')

    from cycler import cycler

def sensitivity_over_time():
    import seaborn as sns
    r=5
    custom_cycler = (cycler(color=sns.color_palette('Set1', 5)) *
                     cycler(linestyle=['-', '--']))
    #'Set2', 'Paired', 'YlGnBu'
    # Load replacement results
    
        # Define storylines
    fig, ax = plt.subplots(3,3,figsize=(22,28))
    baseline = MaTrace_System.FlowDict['E_0_1'].Values[1,1,3,0,1,r,:,:,2,:].sum(axis=0)
    ax[0,0].set_prop_cycle(custom_cycler)
    z = 1
    S= 1
    R=0
    V=1
    h=2
    a = 1 # High LFP
    
    for e in range(Ne-1): # Don't include "other materials"
        ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[72::], 
                (MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,72::].sum(axis=0)-baseline[e,72::])/baseline[e,72::]*100, linewidth=2)
    ax[0,0].set_title('a) Shift to LFP', fontsize=20)
    ax[0,0].set_xlabel('Year',fontsize =16)
    ax[0,0].tick_params(axis='both', which='major', labelsize=18)
    ax[0,0].set_ylabel('Change [%]',fontsize =18)
    right_side = ax[0,0].spines["right"]
    right_side.set_visible(False)
    top = ax[0,0].spines["top"]
    top.set_visible(False)
    
    ax[0,1].set_prop_cycle(custom_cycler)
    a = 0 # NCX
    for e in range(Ne-1): # Don't include "other materials"
        ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[72::], 
                (MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,72::].sum(axis=0)-baseline[e,72::])/baseline[e,72::]*100, linewidth=2)
    ax[0,1].set_title('b) Shift to high Ni', fontsize=20)
    ax[0,1].set_xlabel('Year',fontsize =16)
    ax[0,1].tick_params(axis='both', which='major', labelsize=18)
    ax[0,1].set_ylabel('Change [%]',fontsize =18)
    right_side = ax[0,1].spines["right"]
    right_side.set_visible(False)
    top = ax[0,1].spines["top"]
    top.set_visible(False)
    
    ax[0,2].set_prop_cycle(custom_cycler)
    a = 4 # Next gen BNEF
    for e in range(Ne-1): # Don't include "other materials"
        ax[0,2].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[72::], 
                (MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,72::].sum(axis=0)-baseline[e,72::])/baseline[e,72::]*100, linewidth=2)
    ax[0,2].set_title('c) Shift to Li-air and Li-S', fontsize=20)
    ax[0,2].set_xlabel('Year',fontsize =16)
    ax[0,2].tick_params(axis='both', which='major', labelsize=18)
    ax[0,2].set_ylabel('Change [%]',fontsize =18)
    right_side = ax[0,2].spines["right"]
    right_side.set_visible(False)
    top = ax[0,2].spines["top"]
    top.set_visible(False)
    
    ax[1,0].set_prop_cycle(custom_cycler)
    a = 3 # Base
    z = 0
    for e in range(Ne-1): # Don't include "other materials"
        ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[72::], 
                (MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,72::].sum(axis=0)-baseline[e,72::])/baseline[e,72::]*100, linewidth=2)
    ax[1,0].set_title('d) Smaller fleet', fontsize=20)
    ax[1,0].set_xlabel('Year',fontsize =16)
    ax[1,0].tick_params(axis='both', which='major', labelsize=18)
    ax[1,0].set_ylabel('Change [%]',fontsize =18)
    right_side = ax[1,0].spines["right"]
    right_side.set_visible(False)
    top = ax[1,0].spines["top"]
    top.set_visible(False)
    ax[1,0].set_ylim([-40,0])
    
    ax[1,1].set_prop_cycle(custom_cycler)
    z = 1 # Base
    h = 0
    for e in range(Ne-1): # Don't include "other materials"
        ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[72::], 
                (MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,72::].sum(axis=0)- baseline[e,72::])/baseline[e,72::]*100, linewidth=2)
    ax[1,1].set_title('e) Efficient recycling', fontsize=20)
    ax[1,1].set_xlabel('Year',fontsize =16)
    ax[1,1].tick_params(axis='both', which='major', labelsize=18)
    ax[1,1].set_ylabel('Change [%]',fontsize =18)
    right_side = ax[1,1].spines["right"]
    right_side.set_visible(False)
    top = ax[1,1].spines["top"]
    top.set_visible(False)
    
    ax[1,2].set_prop_cycle(custom_cycler)
    h = 2 # Base
    S = 2
    for e in range(Ne-1): # Don't include "other materials"
        ax[1,2].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[72::], 
                (MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,72::].sum(axis=0)- baseline[e,72::])/baseline[e,72::]*100, linewidth=2)
    ax[1,2].set_title('f) Faster electrification', fontsize=20)
    ax[1,2].set_xlabel('Year',fontsize =16)
    ax[1,2].tick_params(axis='both', which='major', labelsize=18)
    ax[1,2].set_ylabel('Change [%]',fontsize =18)
    right_side = ax[1,2].spines["right"]
    right_side.set_visible(False)
    top = ax[1,2].spines["top"]
    top.set_visible(False)
    ax[1,2].set_ylim([0,145])
    
    ax[2,0].set_prop_cycle(custom_cycler)
    S = 1 # Base
    V = 0
    for e in range(Ne-1): # Don't include "other materials"
        ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[72::], 
                (MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,72::].sum(axis=0)- baseline[e,72::])/baseline[e,72::]*100, linewidth=2)
    ax[2,0].set_title('g) Smaller batteries', fontsize=20)
    ax[2,0].set_xlabel('Year',fontsize =16)
    ax[2,0].tick_params(axis='both', which='major', labelsize=18)
    ax[2,0].set_ylabel('Change [%]',fontsize =18)
    right_side = ax[2,0].spines["right"]
    right_side.set_visible(False)
    top = ax[2,0].spines["top"]
    top.set_visible(False)
    
    ax[2,1].set_prop_cycle(custom_cycler)
    V = 1 # Base
    for e in range(Ne-1): # Don't include "other materials"
        ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[72::], 
                (e01_replacements[z,S,a,R,V,r,:,e,h,72::].sum(axis=0)- baseline[e,72::])/baseline[e,72::]*100, linewidth=2)
    ax[2,1].set_title('h) Reuse and replacements', fontsize=20)
    ax[2,1].set_xlabel('Year',fontsize =16)
    ax[2,1].tick_params(axis='both', which='major', labelsize=18)
    ax[2,1].set_ylabel('Change [%]',fontsize =18)
    right_side = ax[2,1].spines["right"]
    right_side.set_visible(False)
    top = ax[2,1].spines["top"]
    top.set_visible(False)
    ax[2,1].set_ylim([-23,0])
    
    ax[2,2].set_prop_cycle(custom_cycler)
    V = 1 # Base
    for e in range(Ne-1): # Don't include "other materials"
        ax[2,2].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[72::], 
                (e01_long_lt[z,S,a,R,V,r,:,e,h,72::].sum(axis=0)- baseline[e,72::])/baseline[e,72::]*100, linewidth=2, label=IndexTable.Classification[IndexTable.index.get_loc('Element')].Items[e])
    ax[2,2].set_title('j) Longer lifetime', fontsize=20)
    ax[2,2].set_xlabel('Year',fontsize =16)
    ax[2,2].tick_params(axis='both', which='major', labelsize=18)
    ax[2,2].set_ylabel('Change [%]',fontsize =18)
    right_side = ax[2,2].spines["right"]
    right_side.set_visible(False)
    top = ax[2,2].spines["top"]
    top.set_visible(False)
    ax[2,2].set_ylim([-17,0])
    
    fig.legend(loc='lower left', prop={'size':25}, bbox_to_anchor =(0.25, 0.03), ncol = 5, columnspacing = 1, handletextpad = 0.5, handlelength = 2)
    fig.suptitle('Change in material demand for a given intervention', fontsize=30)
    fig.subplots_adjust(top=0.92)
    fig.savefig(os.getcwd() + '/results/overview/sensitivity_over_time', dpi=600, bbox_inches='tight')
    
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
    EV1 = MaTrace_System.FlowDict['E_0_1'].Values[1,0,1,1,1,r,:,:,2,:].sum(axis=0)
    EV2 = MaTrace_System.FlowDict['E_0_1'].Values[1,0,0,0,2,r,:,:,2,:].sum(axis=0)
    EV3 = MaTrace_System.FlowDict['E_0_1'].Values[1,1,3,0,1,r,:,:,2,:].sum(axis=0)
    EV4 = MaTrace_System.FlowDict['E_0_1'].Values[2,2,4,2,1,r,:,:,1,:].sum(axis=0)
    EV5 = e01_replacements[0,2,7,0,0,r,:,:,0,:].sum(axis=0)

    fig, ax = plt.subplots(4,2,figsize=(26,28))
    # Define sensitivity analysis for Ni
    e = 7 # Ni
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                                # Values from case 6
                                ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                                # Values from case 6
                                ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
                                # Values from case 6
                                ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
    scen_cycler = cycler(color= [sns.color_palette('tab20c')[8], sns.color_palette('tab20c')[9],sns.color_palette('tab20c')[4], sns.color_palette('tab20c')[0], sns.color_palette('tab20c')[1]] )
    ax[0,0].set_prop_cycle(scen_cycler)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV3[e,65::]/1000000,  linewidth=3)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
                                        2.51, 'k', marker="*", markersize=15) # Mine production of Ni, page 50 of report. In metal content
    ax[0,0].set_ylabel('Primary Ni demand [Mt]',fontsize =18)
    right_side = ax[0,0].spines["right"]
    right_side.set_visible(False)
    top = ax[0,0].spines["top"]
    top.set_visible(False)
    ax[0,0].set_title('a) Nickel', fontsize=20)
    ax[0,0].set_xlabel('Year',fontsize =16)
    ax[0,0].set_ylim([0,17.5])
    ax[0,0].set_xlim([2019,2050])
    ax[0,0].tick_params(axis='both', which='major', labelsize=18)

    ## Plot Li
    ax[0,1].set_prop_cycle(custom_cycler)
    e = 0 # Li
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                                # Values from case 6
                                ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                                # Values from case 6
                                ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
                                # Values from case 6
                                ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
    ax[0,1].set_prop_cycle(scen_cycler)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    EV3[e,65::]/1000000,  linewidth=3)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
                                        0.085, 'k', marker="*", markersize=15) # Li minerals production, page 44, Li content world total
    ax[0,1].set_ylabel('Primary Li demand [Mt]',fontsize =18)
    right_side = ax[0,1].spines["right"]
    right_side.set_visible(False)
    top = ax[0,1].spines["top"]
    top.set_visible(False)
    ax[0,1].set_title('b) Lithium', fontsize=20)
    ax[0,1].set_xlabel('Year',fontsize =16)
    ax[0,1].set_ylim([0,4.5])
    ax[0,1].set_xlim([2019,2050])
    ax[0,1].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot Co
    ax[1,0].set_prop_cycle(custom_cycler)
    e = 6 # Co
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                                # Values from case 6
                                ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                                # Values from case 6
                                ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
                                # Values from case 6
                                ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
    
    ax[1,0].set_prop_cycle(scen_cycler)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV3[e,65::]/1000000,  linewidth=3)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
                                        0.126, 'k', marker="*", markersize=15) # Co mine production, page 16, metal content world total
    ax[1,0].set_ylabel('Primary Co demand [Mt]',fontsize =18)
    right_side = ax[1,0].spines["right"]
    right_side.set_visible(False)
    top = ax[1,0].spines["top"]
    top.set_visible(False)
    ax[1,0].set_title('c) Cobalt', fontsize=20)
    ax[1,0].set_xlabel('Year',fontsize =16)
    ax[1,0].set_ylim([0,3])
    ax[1,0].set_xlim([2019,2050])
    ax[1,0].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot P
    ax[1,1].set_prop_cycle(custom_cycler)
    e = 4 # P
    from mpl_toolkits.axes_grid1 import make_axes_locatable
    divider = make_axes_locatable(ax[1,1])
    ax2 = divider.new_vertical(size="15%", pad=0.1)
    fig.add_axes(ax2)
    ax2.set_ylim(29, 31.5)
    ax[1,1].set_ylim([0,13])
    ax2.tick_params(bottom=False, labelbottom=False)
    ax2.spines['top'].set_visible(False)
    ax2.spines['bottom'].set_visible(False)
    # From https://matplotlib.org/examples/pylab_examples/broken_axis.html
    d = .02  # how big to make the diagonal lines in axes coordinates
    # arguments to pass to plot, just so we don't keep repeating them
    kwargs = dict(transform=ax2.transAxes, color='k', clip_on=False)
    ax2.plot((-d, +d), (-d, 10*d), **kwargs)        # top-left diagonal
    #ax2.plot((1 - d, 1 + d), (-d, 10*d), **kwargs)  # top-right diagonal

    kwargs.update(transform=ax[1,1].transAxes)  # switch to the bottom axes
    ax2.plot((-d, +d), (1 - d, 1 + d), **kwargs)  # bottom-left diagonal
    #ax2.plot((1 - d, 1 + d), (1 - d, 1 + d), **kwargs)  # bottom-right diagonal
    ax2.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
                                        30.72, 'k', marker="*", markersize=15) # Phosphate rock production

    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                                # Values from case 6
                                ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                                # Values from case 6
                                ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
                                # Values from case 6
                                ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
    
    ax[1,1].set_prop_cycle(scen_cycler)
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3)
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3)
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV3[e,65::]/1000000,  linewidth=3)
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3)
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3)
    right_side = ax[1,1].spines["right"]
    ax[1,1].set_ylabel('Primary P demand [Mt]',fontsize =18)
    right_side.set_visible(False)
    top = ax[1,1].spines["top"]
    top.set_visible(False)
    right_side2 = ax2.spines["right"]
    right_side2.set_visible(False)
    ax2.set_xlim([2019,2050])
    ax2.set_title('d) Phosphorus', fontsize=20)
    ax2.tick_params(axis='both', which='major', labelsize=18)
    ax[1,1].set_xlabel('Year',fontsize =16)
    ax[1,1].set_xlim([2019,2050])
    ax[1,1].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot Al
    ax[2,0].set_prop_cycle(custom_cycler)
    e = 2 # Al
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                                # Values from case 6
                                ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                                # Values from case 6
                                ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
                                # Values from case 6
                                ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
    
    ax[2,0].set_prop_cycle(scen_cycler)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV3[e,65::]/1000000,  linewidth=3)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
                                        65.4, 'k', marker="*", markersize=15) # production of primary aluminium, page 4
    ax[2,0].set_ylabel('Primary Al demand [Mt]',fontsize =18)
    right_side = ax[2,0].spines["right"]
    right_side.set_visible(False)
    top = ax[2,0].spines["top"]
    top.set_visible(False)
    ax[2,0].set_title('e) Aluminium', fontsize=20)
    ax[2,0].set_xlabel('Year',fontsize =16)
    ax[2,0].set_ylim([0,70])
    ax[2,0].set_xlim([2019,2050])
    ax[2,0].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot Graphite
    ax[2,1].set_prop_cycle(custom_cycler)
    e = 1 # Graphite
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                                # Values from case 6
                                ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                                # Values from case 6
                                ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
                                # Values from case 6
                                ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
    
    ax[2,1].set_prop_cycle(scen_cycler)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV3[e,65::]/1000000,  linewidth=3)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
                                        1, 'k', marker="*", markersize=15) # Production of graphite, page 29
    ax[2,1].set_ylabel('Primary Graphite demand [Mt]',fontsize =18)
    right_side = ax[2,1].spines["right"]
    right_side.set_visible(False)
    top = ax[2,1].spines["top"]
    top.set_visible(False)
    ax[2,1].set_title('f) Graphite', fontsize=20)
    ax[2,1].set_xlabel('Year',fontsize =16)
    ax[2,1].set_ylim([0,35])
    ax[2,1].set_xlim([2019,2050])
    ax[2,1].tick_params(axis='both', which='major', labelsize=18)
    
    
    ## Plot Mn
    ax[3,0].set_prop_cycle(custom_cycler)
    e = 5 # Mn
    divider = make_axes_locatable(ax[3,0])
    ax3 = divider.new_vertical(size="15%", pad=0.1)
    fig.add_axes(ax3)
    ax3.set_ylim(19, 21)
    ax[3,0].set_ylim([0,2.75])
    ax3.tick_params(bottom=False, labelbottom=False)
    ax3.spines['top'].set_visible(False)
    ax3.spines['bottom'].set_visible(False)
    # From https://matplotlib.org/examples/pylab_examples/broken_axis.html
    d = .02  # how big to make the diagonal lines in axes coordinates
    # arguments to pass to plot, just so we don't keep repeating them
    kwargs = dict(transform=ax3.transAxes, color='k', clip_on=False)
    ax3.plot((-d, +d), (-d, 10*d), **kwargs)        # top-left diagonal
    #ax3.plot((1 - d, 1 + d), (-d, 10*d), **kwargs)  # top-right diagonal

    kwargs.update(transform=ax[3,0].transAxes)  # switch to the bottom axes
    ax3.plot((-d, +d), (1 - d, 1 + d), **kwargs)  # bottom-left diagonal
    #ax3.plot((1 - d, 1 + d), (1 - d, 1 + d), **kwargs)  # bottom-right diagonal
    ax3.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
                                        20, 'k', marker="*", markersize=15) # Phosphate rock production

    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                                # Values from case 6
                                ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                                # Values from case 6
                                ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
                                # Values from case 6
                                ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
    
    ax[3,0].set_prop_cycle(scen_cycler)
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3)
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3)
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV3[e,65::]/1000000,  linewidth=3)
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3)
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3)
    ax[3,0].set_ylabel('Primary Mn demand [Mt]',fontsize =18)
    right_side = ax[3,0].spines["right"]
    right_side.set_visible(False)
    top = ax[3,0].spines["top"]
    top.set_visible(False)
    right_side2 = ax3.spines["right"]
    right_side2.set_visible(False)
    ax3.set_xlim([2019,2050])
    ax3.set_title('g) Manganese', fontsize=20)
    ax3.tick_params(axis='both', which='major', labelsize=18)
    ax[3,0].set_xlabel('Year',fontsize =16)
    ax[3,0].set_xlim([2019,2050])
    ax[3,0].tick_params(axis='both', which='major', labelsize=18)
    
    
    ## Plot Cu
    ax[3,1].set_prop_cycle(custom_cycler)
    e = 8 # Cu
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                                # Values from case 6
                                ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                                # Values from case 6
                                ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
                                # Values from case 6
                                ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
    
    ax[3,1].set_prop_cycle(scen_cycler)
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3, label='MRS1, Slow transition')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3, label='MRS2, Slow transition - technology oriented')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV3[e,65::]/1000000,  linewidth=3, label='MRS3, Moderate transition - baseline')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3, label='MRS4, Fast transition - focus on electrification')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3, label='MRS5, Fast transition - systemic solutions')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
                                        24.9, 'k', marker="*", markersize=15) # Refined production of copper, page 20
    ax[3,1].set_ylabel('Primary Cu demand [Mt]',fontsize =18)
    right_side = ax[3,1].spines["right"]
    right_side.set_visible(False)
    top = ax[3,1].spines["top"]
    top.set_visible(False)
    # sns.color_palette('tab20c')[8], sns.color_palette('tab20c')[9],sns.color_palette('tab20c')[4], sns.color_palette('tab20c')[0], sns.color_palette('tab20c')[1]
    custom_lines = [Line2D([0], [0], color='w', lw=3),
                Line2D([0], [0], color=sns.color_palette('tab20c')[8], lw=3),
                Line2D([0], [0], color=sns.color_palette('tab20c')[9], lw=3),
                Line2D([0], [0], color=sns.color_palette('tab20c')[4], lw=3),
                Line2D([0], [0], color=sns.color_palette('tab20c')[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('tab20c')[1], lw=3)]
                
    scen_lines = [Line2D([0], [0], color='w', lw=3),
                Line2D([0], [0], color=sns.color_palette('Pastel2', 5)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('Pastel2', 5)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('Pastel2', 5)[2], lw=3)]
    
    prod_line = [
                Line2D([0],[0] , marker='*', markersize=15, color='k', linewidth=0)]
    
    ax[3,1].set_title('h) Copper', fontsize=20)
    ax[3,1].set_xlabel('Year',fontsize =16)
    ax[3,1].set_ylim([0,26])
    ax[3,1].set_xlim([2019,2050])
    ax[3,1].tick_params(axis='both', which='major', labelsize=18)
    lines_labels = [ax.get_legend_handles_labels() for ax in fig.axes]
    lines, labels = [sum(lol, []) for lol in zip(*lines_labels)]
    fig.legend(custom_lines, ['Scenarios']+labels, loc='upper left', prop={'size':20}, bbox_to_anchor =(0.1, 0.05), ncol = 1, columnspacing = 1, handletextpad = 1, handlelength = 1)
    fig.legend(scen_lines, ['EV penetration']+['Slow', 'Moderate', 'Fast'], loc='upper left', prop={'size':20}, bbox_to_anchor =(0.45, 0.05), ncol = 1, columnspacing = 1, handletextpad = 1, handlelength = 1)
    fig.legend(prod_line, ['Current production*'], loc='upper left',prop={'size':20}, bbox_to_anchor =(0.45, -0.02), ncol = 1, columnspacing = 1, handletextpad = 1, handlelength = 1)
    # Add title
    fig.suptitle('Primary resource use use to meet storage demand', fontsize=30)
    fig.subplots_adjust(top=0.92, bottom=0.08)
    fig.savefig(os.getcwd() + '/results/overview/sensitivity_analysis_complete_new', dpi=600, bbox_inches='tight')

def sensitivity_analysis_recycling():
    from cycler import cycler
    import seaborn as sns
    from matplotlib.lines import Line2D
    r=5
    custom_cycler = cycler(color=sns.color_palette('cool', 4)) #'Set2', 'Paired', 'YlGnBu'
    # Load replacement results
    e81_replacements = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E81_case6.npy')
    # Define storylines
    EV1 = MaTrace_System.FlowDict['E_8_1'].Values[1,0,1,1,1,r,:,:,2,:].sum(axis=0)
    EV2 = MaTrace_System.FlowDict['E_8_1'].Values[1,0,0,0,2,r,:,:,2,:].sum(axis=0)
    EV3 = MaTrace_System.FlowDict['E_8_1'].Values[1,1,3,0,1,r,:,:,2,:].sum(axis=0)
    EV4 = MaTrace_System.FlowDict['E_8_1'].Values[2,2,4,2,1,r,:,:,1,:].sum(axis=0)
    EV5 = e81_replacements[0,2,7,0,0,r,:,:,0,:].sum(axis=0)

    fig, ax = plt.subplots(4,2,figsize=(26,28))
    # Define sensitivity analysis for Ni
    e = 7 # Ni
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                                # Values from case 6
                                ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                                # Values from case 6
                                ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
                                # Values from case 6
                                ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
    scen_cycler = cycler(color= [sns.color_palette('tab20c')[8], sns.color_palette('tab20c')[9],sns.color_palette('tab20c')[4], sns.color_palette('tab20c')[0], sns.color_palette('tab20c')[1]] )
    ax[0,0].set_prop_cycle(scen_cycler)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV3[e,65::]/1000000,  linewidth=3)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3)
    # ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
    #                                     2.51, 'k', marker="*", markersize=15) # Mine production of Ni, page 50 of report. In metal content
    ax[0,0].set_ylabel('Primary Ni demand [Mt]',fontsize =18)
    right_side = ax[0,0].spines["right"]
    right_side.set_visible(False)
    top = ax[0,0].spines["top"]
    top.set_visible(False)
    ax[0,0].set_title('a) Nickel', fontsize=20)
    ax[0,0].set_xlabel('Year',fontsize =16)
    # ax[0,0].set_ylim([0,17.5])
    ax[0,0].set_xlim([2019,2050])
    ax[0,0].tick_params(axis='both', which='major', labelsize=18)

    ## Plot Li
    ax[0,1].set_prop_cycle(custom_cycler)
    e = 0 # Li
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                                # Values from case 6
                                ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                                # Values from case 6
                                ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
                                # Values from case 6
                                ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
    ax[0,1].set_prop_cycle(scen_cycler)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    EV3[e,65::]/1000000,  linewidth=3)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3)
    # ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
    #                                     0.085, 'k', marker="*", markersize=15) # Li minerals production, page 44, Li content world total
    ax[0,1].set_ylabel('Primary Li demand [Mt]',fontsize =18)
    right_side = ax[0,1].spines["right"]
    right_side.set_visible(False)
    top = ax[0,1].spines["top"]
    top.set_visible(False)
    ax[0,1].set_title('b) Lithium', fontsize=20)
    ax[0,1].set_xlabel('Year',fontsize =16)
    # ax[0,1].set_ylim([0,4.5])
    ax[0,1].set_xlim([2019,2050])
    ax[0,1].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot Co
    ax[1,0].set_prop_cycle(custom_cycler)
    e = 6 # Co
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                                # Values from case 6
                                ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                                # Values from case 6
                                ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
                                # Values from case 6
                                ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
    
    ax[1,0].set_prop_cycle(scen_cycler)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV3[e,65::]/1000000,  linewidth=3)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3)
    # ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
    #                                     0.126, 'k', marker="*", markersize=15) # Co mine production, page 16, metal content world total
    ax[1,0].set_ylabel('Primary Co demand [Mt]',fontsize =18)
    right_side = ax[1,0].spines["right"]
    right_side.set_visible(False)
    top = ax[1,0].spines["top"]
    top.set_visible(False)
    ax[1,0].set_title('c) Cobalt', fontsize=20)
    ax[1,0].set_xlabel('Year',fontsize =16)
    # ax[1,0].set_ylim([0,3])
    ax[1,0].set_xlim([2019,2050])
    ax[1,0].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot P
    ax[1,1].set_prop_cycle(custom_cycler)
    e = 4 # P
    # from mpl_toolkits.axes_grid1 import make_axes_locatable
    # divider = make_axes_locatable(ax[1,1])
    # ax2 = divider.new_vertical(size="15%", pad=0.1)
    # fig.add_axes(ax2)
    # ax2.set_ylim(29, 31.5)
    # ax[1,1].set_ylim([0,13])
    # ax2.tick_params(bottom=False, labelbottom=False)
    # ax2.spines['top'].set_visible(False)
    # ax2.spines['bottom'].set_visible(False)
    # # From https://matplotlib.org/examples/pylab_examples/broken_axis.html
    # d = .02  # how big to make the diagonal lines in axes coordinates
    # # arguments to pass to plot, just so we don't keep repeating them
    # kwargs = dict(transform=ax2.transAxes, color='k', clip_on=False)
    # ax2.plot((-d, +d), (-d, 10*d), **kwargs)        # top-left diagonal
    # #ax2.plot((1 - d, 1 + d), (-d, 10*d), **kwargs)  # top-right diagonal

    # kwargs.update(transform=ax[1,1].transAxes)  # switch to the bottom axes
    # ax2.plot((-d, +d), (1 - d, 1 + d), **kwargs)  # bottom-left diagonal
    # #ax2.plot((1 - d, 1 + d), (1 - d, 1 + d), **kwargs)  # bottom-right diagonal
    # ax2.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
    #                                     30.72, 'k', marker="*", markersize=15) # Phosphate rock production

    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                                # Values from case 6
                                ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                                # Values from case 6
                                ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
                                # Values from case 6
                                ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
    
    ax[1,1].set_prop_cycle(scen_cycler)
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3)
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3)
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV3[e,65::]/1000000,  linewidth=3)
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3)
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3)
    right_side = ax[1,1].spines["right"]
    ax[1,1].set_ylabel('Primary P demand [Mt]',fontsize =18)
    right_side.set_visible(False)
    top = ax[1,1].spines["top"]
    top.set_visible(False)
    # right_side2 = ax2.spines["right"]
    # right_side2.set_visible(False)
    # ax2.set_xlim([2019,2050])
    # ax2.set_title('d) Phosphorus', fontsize=20)
    # ax2.tick_params(axis='both', which='major', labelsize=18)
    ax[1,1].set_xlabel('Year',fontsize =16)
    ax[1,1].set_xlim([2019,2050])
    ax[1,1].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot Al
    ax[2,0].set_prop_cycle(custom_cycler)
    e = 2 # Al
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                                # Values from case 6
                                ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                                # Values from case 6
                                ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
                                # Values from case 6
                                ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
    
    ax[2,0].set_prop_cycle(scen_cycler)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV3[e,65::]/1000000,  linewidth=3)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3)
    # ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
    #                                     65.4, 'k', marker="*", markersize=15) # production of primary aluminium, page 4
    ax[2,0].set_ylabel('Primary Al demand [Mt]',fontsize =18)
    right_side = ax[2,0].spines["right"]
    right_side.set_visible(False)
    top = ax[2,0].spines["top"]
    top.set_visible(False)
    ax[2,0].set_title('e) Aluminium', fontsize=20)
    ax[2,0].set_xlabel('Year',fontsize =16)
    # ax[2,0].set_ylim([0,70])
    ax[2,0].set_xlim([2019,2050])
    ax[2,0].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot Graphite
    ax[2,1].set_prop_cycle(custom_cycler)
    e = 1 # Graphite
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                                # Values from case 6
                                ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                                # Values from case 6
                                ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.01)
                                # Values from case 6
                                ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
    
    ax[2,1].set_prop_cycle(scen_cycler)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV3[e,65::]/1000000,  linewidth=3)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3)
    # ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
    #                                     1, 'k', marker="*", markersize=15) # Production of graphite, page 29
    ax[2,1].set_ylabel('Primary Graphite demand [Mt]',fontsize =18)
    right_side = ax[2,1].spines["right"]
    right_side.set_visible(False)
    top = ax[2,1].spines["top"]
    top.set_visible(False)
    ax[2,1].set_title('f) Graphite', fontsize=20)
    ax[2,1].set_xlabel('Year',fontsize =16)
    # ax[2,1].set_ylim([0,35])
    ax[2,1].set_xlim([2019,2050])
    ax[2,1].tick_params(axis='both', which='major', labelsize=18)
    
    
    ## Plot Mn
    ax[3,0].set_prop_cycle(custom_cycler)
    e = 5 # Mn
    # divider = make_axes_locatable(ax[3,0])
    # ax3 = divider.new_vertical(size="15%", pad=0.1)
    # fig.add_axes(ax3)
    # ax3.set_ylim(19, 21)
    # ax[3,0].set_ylim([0,2.75])
    # ax3.tick_params(bottom=False, labelbottom=False)
    # ax3.spines['top'].set_visible(False)
    # ax3.spines['bottom'].set_visible(False)
    # # From https://matplotlib.org/examples/pylab_examples/broken_axis.html
    # d = .02  # how big to make the diagonal lines in axes coordinates
    # # arguments to pass to plot, just so we don't keep repeating them
    # kwargs = dict(transform=ax3.transAxes, color='k', clip_on=False)
    # ax3.plot((-d, +d), (-d, 10*d), **kwargs)        # top-left diagonal
    # #ax3.plot((1 - d, 1 + d), (-d, 10*d), **kwargs)  # top-right diagonal

    # kwargs.update(transform=ax[3,0].transAxes)  # switch to the bottom axes
    # ax3.plot((-d, +d), (1 - d, 1 + d), **kwargs)  # bottom-left diagonal
    # #ax3.plot((1 - d, 1 + d), (1 - d, 1 + d), **kwargs)  # bottom-right diagonal
    # ax3.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
    #                                     20, 'k', marker="*", markersize=15) # Phosphate rock production

    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                                # Values from case 6
                                ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                                # Values from case 6
                                ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
                                # Values from case 6
                                ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
    
    ax[3,0].set_prop_cycle(scen_cycler)
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3)
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3)
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV3[e,65::]/1000000,  linewidth=3)
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3)
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3)
    ax[3,0].set_ylabel('Primary Mn demand [Mt]',fontsize =18)
    right_side = ax[3,0].spines["right"]
    right_side.set_visible(False)
    top = ax[3,0].spines["top"]
    top.set_visible(False)
    # right_side2 = ax3.spines["right"]
    # right_side2.set_visible(False)
    # ax3.set_xlim([2019,2050])
    # ax3.set_title('g) Manganese', fontsize=20)
    # ax3.tick_params(axis='both', which='major', labelsize=18)
    ax[3,0].set_xlabel('Year',fontsize =16)
    ax[3,0].set_xlim([2019,2050])
    ax[3,0].tick_params(axis='both', which='major', labelsize=18)
    
    
    ## Plot Cu
    ax[3,1].set_prop_cycle(custom_cycler)
    e = 8 # Cu
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                                # Values from case 6
                                ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[0], alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                                # Values from case 6
                                ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[1], alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
                                # Values from case 6
                                ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e81_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, color=sns.color_palette('Pastel2', 5)[2], alpha=0.02)
    
    ax[3,1].set_prop_cycle(scen_cycler)
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3, label='MRS1, Slow transition')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3, label='MRS2, Slow transition - technology oriented')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV3[e,65::]/1000000,  linewidth=3, label='MRS3, Moderate transition - baseline')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3, label='MRS4, Fast transition - focus on electrification')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3, label='MRS5, Fast transition - systemic solutions')
    # ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
    #                                     24.9, 'k', marker="*", markersize=15) # Refined production of copper, page 20
    ax[3,1].set_ylabel('Primary Cu demand [Mt]',fontsize =18)
    right_side = ax[3,1].spines["right"]
    right_side.set_visible(False)
    top = ax[3,1].spines["top"]
    top.set_visible(False)
    # sns.color_palette('tab20c')[8], sns.color_palette('tab20c')[9],sns.color_palette('tab20c')[4], sns.color_palette('tab20c')[0], sns.color_palette('tab20c')[1]
    custom_lines = [Line2D([0], [0], color='w', lw=3),
                Line2D([0], [0], color=sns.color_palette('tab20c')[8], lw=3),
                Line2D([0], [0], color=sns.color_palette('tab20c')[9], lw=3),
                Line2D([0], [0], color=sns.color_palette('tab20c')[4], lw=3),
                Line2D([0], [0], color=sns.color_palette('tab20c')[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('tab20c')[1], lw=3)]
                
    scen_lines = [Line2D([0], [0], color='w', lw=3),
                Line2D([0], [0], color=sns.color_palette('Pastel2', 5)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('Pastel2', 5)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('Pastel2', 5)[2], lw=3)]
    
    prod_line = [
                Line2D([0],[0] , marker='*', markersize=15, color='k', linewidth=0)]
    
    ax[3,1].set_title('h) Copper', fontsize=20)
    ax[3,1].set_xlabel('Year',fontsize =16)
    # ax[3,1].set_ylim([0,26])
    ax[3,1].set_xlim([2019,2050])
    ax[3,1].tick_params(axis='both', which='major', labelsize=18)
    lines_labels = [ax.get_legend_handles_labels() for ax in fig.axes]
    lines, labels = [sum(lol, []) for lol in zip(*lines_labels)]
    fig.legend(custom_lines, ['Scenarios']+labels, loc='upper left', prop={'size':20}, bbox_to_anchor =(0.1, 0.05), ncol = 1, columnspacing = 1, handletextpad = 1, handlelength = 1)
    fig.legend(scen_lines, ['EV penetration']+['Slow', 'Moderate', 'Fast'], loc='upper left', prop={'size':20}, bbox_to_anchor =(0.45, 0.05), ncol = 1, columnspacing = 1, handletextpad = 1, handlelength = 1)
    # fig.legend(prod_line, ['Current production*'], loc='upper left',prop={'size':20}, bbox_to_anchor =(0.45, -0.02), ncol = 1, columnspacing = 1, handletextpad = 1, handlelength = 1)
    # Add title
    fig.suptitle('Recycled materials for each scenario', fontsize=30)
    fig.subplots_adjust(top=0.92, bottom=0.08)
    fig.savefig(os.getcwd() + '/results/overview/sensitivity_analysis_recycling_new', dpi=600, bbox_inches='tight')

def sensitivity_analysis_complete():
    from cycler import cycler
    import seaborn as sns
    from matplotlib.lines import Line2D
    r=5
    custom_cycler = cycler(color=sns.color_palette('cool', 4)) #'Set2', 'Paired', 'YlGnBu'
    # Load replacement results
    e01_replacements = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E01_case6.npy')
    # Define storylines
    EV1 = MaTrace_System.FlowDict['E_0_1'].Values[1,0,1,1,1,r,:,:,2,:].sum(axis=0)
    EV2 = MaTrace_System.FlowDict['E_0_1'].Values[1,0,0,0,2,r,:,:,2,:].sum(axis=0)
    EV3 = MaTrace_System.FlowDict['E_0_1'].Values[1,1,3,0,1,r,:,:,2,:].sum(axis=0)
    EV4 = MaTrace_System.FlowDict['E_0_1'].Values[2,2,4,2,1,r,:,:,1,:].sum(axis=0)
    EV5 = e01_replacements[0,2,7,0,0,r,:,:,0,:].sum(axis=0)

    fig, ax = plt.subplots(4,2,figsize=(22,28))
    # Define sensitivity analysis for Ni
    e = 7 # Ni
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.01)
                                # Values from case 6
                                ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.01)
                                # Values from case 6
                                ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.01)
                                # Values from case 6
                                ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
    scen_cycler = cycler(color=sns.color_palette('cool', 5))
    ax[0,0].set_prop_cycle(scen_cycler)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV3[e,65::]/1000000,  linewidth=3)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3)
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
                                        2.51, 'k', marker="*", markersize=15) # Mine production of Ni, page 50 of report. In metal content
    ax[0,0].set_ylabel('Primary Ni demand [Mt]',fontsize =18)
    right_side = ax[0,0].spines["right"]
    right_side.set_visible(False)
    top = ax[0,0].spines["top"]
    top.set_visible(False)
    ax[0,0].set_title('a) Nickel', fontsize=20)
    ax[0,0].set_xlabel('Year',fontsize =16)
    ax[0,0].set_ylim([0,17.5])
    ax[0,0].set_xlim([2019,2050])
    ax[0,0].tick_params(axis='both', which='major', labelsize=18)

    ## Plot Li
    ax[0,1].set_prop_cycle(custom_cycler)
    e = 0 # Li
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.01)
                                # Values from case 6
                                ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.01)
                                # Values from case 6
                                ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.01)
                                # Values from case 6
                                ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
    ax[0,1].set_prop_cycle(scen_cycler)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                    EV3[e,65::]/1000000,  linewidth=3)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3)
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
                                        0.085, 'k', marker="*", markersize=15) # Li minerals production, page 44, Li content world total
    ax[0,1].set_ylabel('Primary Li demand [Mt]',fontsize =18)
    right_side = ax[0,1].spines["right"]
    right_side.set_visible(False)
    top = ax[0,1].spines["top"]
    top.set_visible(False)
    ax[0,1].set_title('b) Lithium', fontsize=20)
    ax[0,1].set_xlabel('Year',fontsize =16)
    ax[0,1].set_ylim([0,4.5])
    ax[0,1].set_xlim([2019,2050])
    ax[0,1].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot Co
    ax[1,0].set_prop_cycle(custom_cycler)
    e = 6 # Co
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.01)
                                # Values from case 6
                                ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.01)
                                # Values from case 6
                                ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.01)
                                # Values from case 6
                                ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
    
    ax[1,0].set_prop_cycle(scen_cycler)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV3[e,65::]/1000000,  linewidth=3)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3)
    ax[1,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
                                        0.126, 'k', marker="*", markersize=15) # Co mine production, page 16, metal content world total
    ax[1,0].set_ylabel('Primary Co demand [Mt]',fontsize =18)
    right_side = ax[1,0].spines["right"]
    right_side.set_visible(False)
    top = ax[1,0].spines["top"]
    top.set_visible(False)
    ax[1,0].set_title('c) Cobalt', fontsize=20)
    ax[1,0].set_xlabel('Year',fontsize =16)
    ax[1,0].set_ylim([0,3])
    ax[1,0].set_xlim([2019,2050])
    ax[1,0].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot P
    ax[1,1].set_prop_cycle(custom_cycler)
    e = 4 # P
    from mpl_toolkits.axes_grid1 import make_axes_locatable
    divider = make_axes_locatable(ax[1,1])
    ax2 = divider.new_vertical(size="15%", pad=0.1)
    fig.add_axes(ax2)
    ax2.set_ylim(29, 31.5)
    ax[1,1].set_ylim([0,13])
    ax2.tick_params(bottom=False, labelbottom=False)
    ax2.spines['top'].set_visible(False)
    ax2.spines['bottom'].set_visible(False)
    # From https://matplotlib.org/examples/pylab_examples/broken_axis.html
    d = .02  # how big to make the diagonal lines in axes coordinates
    # arguments to pass to plot, just so we don't keep repeating them
    kwargs = dict(transform=ax2.transAxes, color='k', clip_on=False)
    ax2.plot((-d, +d), (-d, 10*d), **kwargs)        # top-left diagonal
    #ax2.plot((1 - d, 1 + d), (-d, 10*d), **kwargs)  # top-right diagonal

    kwargs.update(transform=ax[1,1].transAxes)  # switch to the bottom axes
    ax2.plot((-d, +d), (1 - d, 1 + d), **kwargs)  # bottom-left diagonal
    #ax2.plot((1 - d, 1 + d), (1 - d, 1 + d), **kwargs)  # bottom-right diagonal
    ax2.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
                                        30.72, 'k', marker="*", markersize=15) # Phosphate rock production

    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.01)
                                # Values from case 6
                                ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.01)
                                # Values from case 6
                                ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.01)
                                # Values from case 6
                                ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
    
    ax[1,1].set_prop_cycle(scen_cycler)
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3)
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3)
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV3[e,65::]/1000000,  linewidth=3)
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3)
    ax[1,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3)
    right_side = ax[1,1].spines["right"]
    ax[1,1].set_ylabel('Primary P demand [Mt]',fontsize =18)
    right_side.set_visible(False)
    top = ax[1,1].spines["top"]
    top.set_visible(False)
    right_side2 = ax2.spines["right"]
    right_side2.set_visible(False)
    ax2.set_xlim([2019,2050])
    ax2.set_title('d) Phosphorus', fontsize=20)
    ax2.tick_params(axis='both', which='major', labelsize=18)
    ax[1,1].set_xlabel('Year',fontsize =16)
    ax[1,1].set_xlim([2019,2050])
    ax[1,1].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot Al
    ax[2,0].set_prop_cycle(custom_cycler)
    e = 2 # Al
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.01)
                                # Values from case 6
                                ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.01)
                                # Values from case 6
                                ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.01)
                                # Values from case 6
                                ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
    
    ax[2,0].set_prop_cycle(scen_cycler)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV3[e,65::]/1000000,  linewidth=3)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3)
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
                                        65.4, 'k', marker="*", markersize=15) # production of primary aluminium, page 4
    ax[2,0].set_ylabel('Primary Al demand [Mt]',fontsize =18)
    right_side = ax[2,0].spines["right"]
    right_side.set_visible(False)
    top = ax[2,0].spines["top"]
    top.set_visible(False)
    ax[2,0].set_title('e) Aluminium', fontsize=20)
    ax[2,0].set_xlabel('Year',fontsize =16)
    ax[2,0].set_ylim([0,70])
    ax[2,0].set_xlim([2019,2050])
    ax[2,0].tick_params(axis='both', which='major', labelsize=18)
    
    ## Plot Graphite
    ax[2,1].set_prop_cycle(custom_cycler)
    e = 1 # Graphite
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.01)
                                # Values from case 6
                                ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.01)
                                # Values from case 6
                                ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.01)
                                # Values from case 6
                                ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
    
    ax[2,1].set_prop_cycle(scen_cycler)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV3[e,65::]/1000000,  linewidth=3)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3)
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
                                        1, 'k', marker="*", markersize=15) # Production of graphite, page 29
    ax[2,1].set_ylabel('Primary Graphite demand [Mt]',fontsize =18)
    right_side = ax[2,1].spines["right"]
    right_side.set_visible(False)
    top = ax[2,1].spines["top"]
    top.set_visible(False)
    ax[2,1].set_title('f) Graphite', fontsize=20)
    ax[2,1].set_xlabel('Year',fontsize =16)
    ax[2,1].set_ylim([0,35])
    ax[2,1].set_xlim([2019,2050])
    ax[2,1].tick_params(axis='both', which='major', labelsize=18)
    
    
    ## Plot Mn
    ax[3,0].set_prop_cycle(custom_cycler)
    e = 5 # Mn
    divider = make_axes_locatable(ax[3,0])
    ax3 = divider.new_vertical(size="15%", pad=0.1)
    fig.add_axes(ax3)
    ax3.set_ylim(19, 21)
    ax[3,0].set_ylim([0,2.75])
    ax3.tick_params(bottom=False, labelbottom=False)
    ax3.spines['top'].set_visible(False)
    ax3.spines['bottom'].set_visible(False)
    # From https://matplotlib.org/examples/pylab_examples/broken_axis.html
    d = .02  # how big to make the diagonal lines in axes coordinates
    # arguments to pass to plot, just so we don't keep repeating them
    kwargs = dict(transform=ax3.transAxes, color='k', clip_on=False)
    ax3.plot((-d, +d), (-d, 10*d), **kwargs)        # top-left diagonal
    #ax3.plot((1 - d, 1 + d), (-d, 10*d), **kwargs)  # top-right diagonal

    kwargs.update(transform=ax[3,0].transAxes)  # switch to the bottom axes
    ax3.plot((-d, +d), (1 - d, 1 + d), **kwargs)  # bottom-left diagonal
    #ax3.plot((1 - d, 1 + d), (1 - d, 1 + d), **kwargs)  # bottom-right diagonal
    ax3.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
                                        20, 'k', marker="*", markersize=15) # Phosphate rock production

    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.01)
                                # Values from case 6
                                ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.01)
                                # Values from case 6
                                ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.01)
                                # Values from case 6
                                ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
    
    ax[3,0].set_prop_cycle(scen_cycler)
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3)
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3)
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV3[e,65::]/1000000,  linewidth=3)
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3)
    ax[3,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3)
    ax[3,0].set_ylabel('Primary Mn demand [Mt]',fontsize =18)
    right_side = ax[3,0].spines["right"]
    right_side.set_visible(False)
    top = ax[3,0].spines["top"]
    top.set_visible(False)
    right_side2 = ax3.spines["right"]
    right_side2.set_visible(False)
    ax3.set_xlim([2019,2050])
    ax3.set_title('g) Manganese', fontsize=20)
    ax3.tick_params(axis='both', which='major', labelsize=18)
    ax[3,0].set_xlabel('Year',fontsize =16)
    ax[3,0].set_xlim([2019,2050])
    ax[3,0].tick_params(axis='both', which='major', labelsize=18)
    
    
    ## Plot Cu
    ax[3,1].set_prop_cycle(custom_cycler)
    e = 8 # Cu
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.01)
                                # Values from case 6
                                ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'powderblue', alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.01)
                                # Values from case 6
                                ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.01)
                                # Values from case 6
                                ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pt->t', e01_replacements[z,S,a,R,V,r,:,e,h,65::])/1000000, 'blueviolet', alpha=0.02)
    
    ax[3,1].set_prop_cycle(scen_cycler)
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[e,65::]/1000000, linewidth=3, label='MRS1, Slow transition')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[e,65::]/1000000,  linewidth=3, label='MRS2, Slow transition - technology oriented')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV3[e,65::]/1000000,  linewidth=3, label='MRS3, Moderate transition - baseline')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[e,65::]/1000000,  linewidth=3, label='MRS4, fast transition - focus on electrification')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[e,65::]/1000000,  linewidth=3, label='MRS5, fast transition - systemic solutions')
    ax[3,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70], 
                                        24.9, 'k', marker="*", markersize=15) # Refined production of copper, page 20
    ax[3,1].set_ylabel('Primary Cu demand [Mt]',fontsize =18)
    right_side = ax[3,1].spines["right"]
    right_side.set_visible(False)
    top = ax[3,1].spines["top"]
    top.set_visible(False)
    custom_lines = [Line2D([0], [0], color='powderblue', lw=1),
                Line2D([0], [0], color='dodgerblue', lw=1),
                Line2D([0], [0], color='blueviolet', lw=1),
                Line2D([0], [0], color=sns.color_palette('cool', 5)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 5)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 5)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 5)[3], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 5)[4], lw=3),
                Line2D([0],[0] , marker='*', markersize=15, color='k', linewidth=0)
                ]
    scen_lines = [Line2D([0], [0], color='powderblue', lw=1),
                Line2D([0], [0], color='dodgerblue', lw=1),
                Line2D([0], [0], color='blueviolet', lw=1)]
    ax[3,1].set_title('h) Copper', fontsize=20)
    ax[3,1].set_xlabel('Year',fontsize =16)
    ax[3,1].set_ylim([0,26])
    ax[3,1].set_xlim([2019,2050])
    ax[3,1].tick_params(axis='both', which='major', labelsize=18)
    lines_labels = [ax.get_legend_handles_labels() for ax in fig.axes]
    lines, labels = [sum(lol, []) for lol in zip(*lines_labels)]
    fig.legend(custom_lines, ['Low EV penetration', 'Medium EV penetration', 'Fast EV penetration']+labels+['Current production*'], loc='lower left', prop={'size':20}, bbox_to_anchor =(0.05, 0), ncol = 3, columnspacing = 1, handletextpad = 1, handlelength = 1)
    #fig.legend(scen_lines, ['Slow EV penetration scenarios', 'Medium EV penetration scenarios', 'Fast EV penetration scenarios'], loc='upper left',prop={'size':20}, bbox_to_anchor =(1, 0.7), fontsize=20)
    # Add title
    fig.suptitle('Resource use per technology used to meet storage demand', fontsize=30)
    fig.subplots_adjust(top=0.92, bottom=0.08)
    fig.savefig(os.getcwd() + '/results/overview/sensitivity_analysis_complete', dpi=600, bbox_inches='tight')

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

    for e in range(Ne-1): # Don't include "other materials"
            ax2.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                    MaTrace_System.FlowDict['E_0_1'].Values[1,1,5,0,1,r,:,e,1,70::].sum(axis=0)/1000, linewidth=2)
            ax2.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                    e01_long_lt[1,1,5,0,1,r,:,e,1,70::].sum(axis=0)/1000, linewidth=2)
            ax2.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                    MaTrace_System.FlowDict['E_2_3'].Values[1,1,5,1,r,:,e,70::].sum(axis=0)/1000, linewidth=2)
            ax2.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                    e23_long_lt[1,1,5,1,r,:,e,70::].sum(axis=0)/1000, linewidth=2)
    
def material_use_lt():
    from cycler import cycler
    import seaborn as sns
    r=5
    custom_cycler = (cycler(color=sns.color_palette('Set1', 6)) *
                     cycler(linestyle=['-', '--', ':']))
    e = 7
    a = 3
    R = 1
    h = 1
    fig, ax = plt.subplots(1,2,figsize=(14,10))
    e01 = MaTrace_System.FlowDict['E_0_1'].Values[1,1,a,R,1,r,:,e,h,:].sum(axis=0)
    e01_long_lt = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E01_long_lt.npy')[1,1,a,R,1,r,:,e,h,:].sum(axis=0)
    e81 = MaTrace_System.FlowDict['E_8_1'].Values[1,1,a,R,1,r,:,e,h,:].sum(axis=0)
    e81_long_lt = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E81_long_lt.npy')[1,1,a,R,1,r,:,e,h,:].sum(axis=0)
    f23 = MaTrace_System.FlowDict['F_2_3'].Values[1,1,1,r,1,:,:].sum(axis=0) + MaTrace_System.FlowDict['F_2_3'].Values[1,1,1,r,2,:,:].sum(axis=0) 
    f23_long_lt = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/F23_long_lt.npy')[1,1,1,r,1,:,:].sum(axis=0) + np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/F23_long_lt.npy')[1,1,1,r,2,:,:].sum(axis=0)
    f34 = MaTrace_System.FlowDict['F_3_4'].Values[1,1,1,r,1,:,:,:].sum(axis=0) + MaTrace_System.FlowDict['F_3_4'].Values[1,1,1,r,2,:,:,:].sum(axis=0)
    f34_long_lt = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/F34_long_lt.npy')[1,1,1,r,1,:,:,:].sum(axis=0) + np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/F34_long_lt.npy')[1,1,1,r,2,:,:,:].sum(axis=0)
    
    ax[0].set_prop_cycle(custom_cycler)
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                f23[70:], linewidth=2, label='Inflows baseline')
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                f34[70:,:].sum(axis=1), linewidth=2, label='Outflows baseline')
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                f23[70:]-f34[70:,:].sum(axis=1), linewidth=2, label='Stock change baseline')
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                f23_long_lt[70:], linewidth=2, label='Inflows long lifetime')
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                f34_long_lt[70:,:].sum(axis=1), linewidth=2, label='Outflows long lifetime')
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                f23_long_lt[70:]-f34_long_lt[70:,:].sum(axis=1), linewidth=2, label='Stock change long lifetime')
    print((f23[70:]-f34[70:,:].sum(axis=1)).sum())
    print((f23_long_lt[70:]-f34_long_lt[70:,:].sum(axis=1)).sum())
    ax[0].set_title('a) Inflows and outflows of BEVs & PHEVs', fontsize=20)
    ax[0].set_xlabel('Year',fontsize =16)
    ax[0].tick_params(axis='both', which='major', labelsize=18)
    ax[0].set_ylabel('Number [thousands]',fontsize =18)
    right_side = ax[0].spines["right"]
    right_side.set_visible(False)
    top = ax[0].spines["top"]
    top.set_visible(False)
    ax[0].set_ylim(0,0.4e6)
    ax[0].legend()
    
    custom_cycler = (cycler(color=sns.color_palette('Set1', 6)) *
                     cycler(linestyle=['-', '--',':']))
    ax[1].set_prop_cycle(custom_cycler)
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                e01[70:], linewidth=2, label='Primary materials baseline')
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                e81[70:], linewidth=2, label='Recycled materials baseline')
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                e01[70:]+e81[70:], linewidth=2, label='Total materials baseline')
    
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                e01_long_lt[70:], linewidth=2, label='Primary materials long lifetime')
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                e81_long_lt[70:], linewidth=2, label='Recycled materials baseline')
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                e01_long_lt[70:]+e81_long_lt[70:], linewidth=2, label='Total materials long lifetime')
    ax2 = ax[1].twinx()

    ax2.bar(2049, e01.sum(), 1, color=sns.color_palette('Set1', 6)[0], alpha=0.8, label='Commulative primary baseline')
    ax2.bar(2049, e81.sum(), 1, bottom=e01.sum(), color=sns.color_palette('Set1', 6)[0], alpha=0.4, label='Commulative recycled baseline')
    ax2.bar(2050, e01_long_lt.sum(), 1, color=sns.color_palette('Set1', 6)[1], alpha=0.8, label='Commulative primary long lifetime')
    ax2.bar(2050, e81_long_lt.sum(), 1, bottom=e01_long_lt.sum(), color=sns.color_palette('Set1', 6)[1], alpha=0.4, label='Commulative recycled long lifetime')
    ax2.legend(loc='center left')
    ax[1].set_title('b) Ni demand', fontsize=20)
    ax[1].set_xlabel('Year',fontsize =16)
    ax[1].tick_params(axis='both', which='major', labelsize=18)
    ax[1].set_ylabel('Weight [t]',fontsize =18)
    right_side = ax[1].spines["right"]
    right_side.set_visible(False)
    top = ax[1].spines["top"]
    top.set_visible(False)
    ax[1].legend(loc='upper left')
    ax[1].set_ylim(0,1.2e7)
    fig.savefig(os.getcwd() + '/results/overview/Material_demand.pdf', dpi=600, bbox_inches='tight')

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

def graphical_abstract():
    from cycler import cycler
    import seaborn as sns
    from matplotlib.lines import Line2D
    r=5
    custom_cycler = cycler(color=sns.color_palette('cool', 4)) #'Set2', 'Paired', 'YlGnBu'
    # Load replacement results
    e01_replacements = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E01_case6.npy')
    # Define storylines
    EV1 = MaTrace_System.FlowDict['E_0_1'].Values[1,0,1,1,1,r,:,:,2,:].sum(axis=0)
    EV2 = MaTrace_System.FlowDict['E_0_1'].Values[1,1,3,0,1,r,:,:,2,:].sum(axis=0)
    EV3 = MaTrace_System.FlowDict['E_0_1'].Values[1,0,0,0,2,r,:,:,2,:].sum(axis=0)
    EV4 = MaTrace_System.FlowDict['E_0_1'].Values[2,2,4,2,1,r,:,:,1,:].sum(axis=0)
    EV5 = e01_replacements[0,2,7,0,0,r,:,:,0,:].sum(axis=0)

    fig, ax = plt.subplots(figsize=(12,12))
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for V in range(NV):
                        for h in range(Nh):
                            if S==0:
                                # Values from case 3
                                ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pet->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,:-1,h,65::])/1000000, 'powderblue', alpha=0.01)
                                # Values from case 6
                                ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pet->t', e01_replacements[z,S,a,R,V,r,:,:-1,h,65::])/1000000, 'powderblue', alpha=0.02)
                            if S==1:
                                # Values from case 3
                                ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pet->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,:-1,h,65::])/1000000, 'dodgerblue', alpha=0.01)
                                # Values from case 6
                                ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pet->t', e01_replacements[z,S,a,R,V,r,:,:-1,h,65::])/1000000, 'dodgerblue', alpha=0.02)
                            if S==2:
                                # Values from case 3
                                ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                            np.einsum('pet->t', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,:-1,h,65::])/1000000, 'blueviolet', alpha=0.01)
                                # Values from case 6
                                ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        np.einsum('pet->t', e01_replacements[z,S,a,R,V,r,:,:-1,h,65::])/1000000, 'blueviolet', alpha=0.02)
    scen_cycler = cycler(color=sns.color_palette('cool', 5))
    ax.set_prop_cycle(scen_cycler)
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV1[:-1,65::].sum(axis=0)/1000000, linewidth=3, label='EV-MRP1')
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV3[:-1,65::].sum(axis=0)/1000000,  linewidth=3, label='EV-MRP2')
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV2[:-1,65::].sum(axis=0)/1000000,  linewidth=3, label='EV-MRP3')
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV4[:-1,65::].sum(axis=0)/1000000,  linewidth=3, label='EV-MRP4')
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                                        EV5[:-1,65::].sum(axis=0)/1000000,  linewidth=3, label='EV-MRP5')
    ax.set_ylabel('Total primary material demand [Mt]',fontsize =18)
    right_side = ax.spines["right"]
    right_side.set_visible(False)
    top = ax.spines["top"]
    top.set_visible(False)
    ax.set_title('Range of scenarios and EV-MRPs', fontsize=24)
    ax.set_xlabel('Year',fontsize =18)
    ax.set_ylim([0,150])
    ax.set_xlim([2019,2050])
    ax.tick_params(axis='both', which='major', labelsize=18)
    custom_lines = [Line2D([0], [0], color='powderblue', lw=1),
                Line2D([0], [0], color='dodgerblue', lw=1),
                Line2D([0], [0], color='blueviolet', lw=1),
                Line2D([0], [0], color=sns.color_palette('cool', 5)[0], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 5)[1], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 5)[2], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 5)[3], lw=3),
                Line2D([0], [0], color=sns.color_palette('cool', 5)[4], lw=3)
                ]
    scen_lines = [Line2D([0], [0], color='powderblue', lw=1),
                Line2D([0], [0], color='dodgerblue', lw=1),
                Line2D([0], [0], color='blueviolet', lw=1)]
    lines_labels = [ax.get_legend_handles_labels() for ax in fig.axes]
    lines, labels = [sum(lol, []) for lol in zip(*lines_labels)]
    fig.legend(custom_lines, ['Slow EV penetration scenarios', 'Medium EV penetration scenarios', 'Fast EV penetration scenarios']+labels, loc='upper left', prop={'size':20}, bbox_to_anchor =(0.13, 0.85), ncol = 2, columnspacing = 1, handletextpad = 1, handlelength = 1) #
    fig.savefig(os.getcwd() + '/results/overview/graphical_abstract', dpi=600, bbox_inches='tight')

def sensitivity_table():
    import seaborn as sns
    z, S, a, R, V, e, h = pd.core.reshape.util.cartesian_product(
    [
        IndexTable.Classification[IndexTable.index.get_loc("Stock_Scenarios")].Items,
        IndexTable.Classification[IndexTable.index.get_loc("Scenario")].Items,
        IndexTable.Classification[IndexTable.index.get_loc("Chemistry_Scenarios")].Items,
        IndexTable.Classification[IndexTable.index.get_loc("Reuse_Scenarios")].Items,
        IndexTable.Classification[IndexTable.index.get_loc('Size_Scenarios')].Items,
        IndexTable.Classification[IndexTable.index.get_loc("Element")].Items,
        IndexTable.Classification[IndexTable.index.get_loc("Recycling_Process")].Items
    ]
    )
    
    primary_materials = pd.DataFrame(
        dict(Stock_Scenarios=z, EV_Scenario=S, Chemistry_Scenario=a, Reuse_Scenario=R, Size_Scenarios=V, Element=e, Recycling_Process=h)
    )
    r=5
    ### Adding data to the dataframes
    materials = np.einsum('zSaRVpeht->zSaRVeh', MaTrace_System.FlowDict['E_0_1'].Values[:,:,:,:,:,r,:,:,:,:])
    materials_replacement = np.einsum('pet->e', e01_replacements[1,1,3,0,1,r,:,:,2,:])
    materials_long_lt = np.einsum('pet->e', e01_long_lt[1,1,3,0,1,r,:,:,2,:])
    baseline = np.einsum('pet->e', MaTrace_System.FlowDict['E_0_1'].Values[1,1,3,0,1,r,:,:,2,:])
    # Calculate relative difference to baseline
    sensitivity = np.zeros((Nz, NS, Na, NR, NV,Ne, Nh))
    for z in range(Nz):
        for S in range(NS):
            for a in range(Na):
                for R in range(NR):
                    for V in range(NV):
                        for e in range(Ne):
                            for h in range(Nh):
                                sensitivity[z,S,a,R,V,e,h] = (materials[z,S,a,R,V,e,h]-baseline[e])/baseline[e]
    sensitivity_replacements = (materials_replacement-baseline)/baseline
    sensitivity_long_lt= (materials_long_lt-baseline)/baseline
    # Add values to table
    for z, stock in enumerate(
        IndexTable.Classification[IndexTable.index.get_loc("Stock_Scenarios")].Items
    ):
        for S, ev in enumerate(
            IndexTable.Classification[IndexTable.index.get_loc("Scenario")].Items
        ):
            for a, chem in enumerate(
                IndexTable.Classification[IndexTable.index.get_loc("Chemistry_Scenarios")].Items
            ):
                for R, reuse in enumerate(
                    IndexTable.Classification[IndexTable.index.get_loc("Reuse_Scenarios")].Items
                ):
                    for V, size in enumerate(
                    IndexTable.Classification[IndexTable.index.get_loc("Size_Scenarios")].Items
                    ):
                        for e, mat in enumerate(
                            IndexTable.Classification[IndexTable.index.get_loc("Element")].Items
                        ):
                            for h, rec in enumerate(
                                IndexTable.Classification[IndexTable.index.get_loc("Recycling_Process")].Items
                            ):
                                primary_materials.loc[
                                    (primary_materials.Stock_Scenarios == stock)
                                    & (primary_materials.EV_Scenario == ev)
                                    & (primary_materials.Chemistry_Scenario == chem)
                                    & (primary_materials.Reuse_Scenario == reuse)
                                    & (primary_materials.Size_Scenarios == size)
                                    & (primary_materials.Element == mat)
                                    & (primary_materials.Recycling_Process == rec),
                                    "value",
                                ] = sensitivity[z, S, a, R, V, e, h]
    shift_to_lfp = primary_materials.loc[ (primary_materials.Stock_Scenarios == 'Medium')
                                & (primary_materials.EV_Scenario == 'SD')
                                & (primary_materials.Chemistry_Scenario == 'LFP')
                                & (primary_materials.Reuse_Scenario == 'LFP reused')
                                & (primary_materials.Size_Scenarios == 'Constant')
                                & (primary_materials.Recycling_Process == 'Pyrometallurgy')]
    shift_to_lfp.reset_index(inplace=True, drop=True)
    shift_to_lfp.drop(['Stock_Scenarios', 'EV_Scenario', 'Chemistry_Scenario', 'Reuse_Scenario', 'Size_Scenarios','Recycling_Process'], axis=1, inplace=True)
    shift_to_lfp.set_index('Element', inplace=True)
    shift_to_lfp.rename(columns={'value':'Shift to LFP'}, inplace=True)

    shift_to_NCX = primary_materials.loc[ (primary_materials.Stock_Scenarios == 'Medium')
                                & (primary_materials.EV_Scenario == 'SD')
                                & (primary_materials.Chemistry_Scenario == 'NCX')
                                & (primary_materials.Reuse_Scenario == 'LFP reused')
                                & (primary_materials.Size_Scenarios == 'Constant')
                                & (primary_materials.Recycling_Process == 'Pyrometallurgy')]
    shift_to_NCX.reset_index(inplace=True, drop=True)
    shift_to_NCX.drop(['Stock_Scenarios', 'EV_Scenario', 'Chemistry_Scenario', 'Reuse_Scenario', 'Size_Scenarios','Recycling_Process'], axis=1, inplace=True)
    shift_to_NCX.set_index('Element', inplace=True)
    shift_to_NCX.rename(columns={'value':'Shift to high Ni chemistries'}, inplace=True)

    shift_to_next_gen = primary_materials.loc[ (primary_materials.Stock_Scenarios == 'Medium')
                                & (primary_materials.EV_Scenario == 'SD')
                                & (primary_materials.Chemistry_Scenario == 'Next_gen_BNEF')
                                & (primary_materials.Reuse_Scenario == 'LFP reused')
                                & (primary_materials.Size_Scenarios == 'Constant')
                                & (primary_materials.Recycling_Process == 'Pyrometallurgy')]
    shift_to_next_gen.reset_index(inplace=True, drop=True)
    shift_to_next_gen.drop(['Stock_Scenarios', 'EV_Scenario', 'Chemistry_Scenario', 'Reuse_Scenario', 'Size_Scenarios','Recycling_Process'], axis=1, inplace=True)
    shift_to_next_gen.set_index('Element', inplace=True)
    shift_to_next_gen.rename(columns={'value':'Shift to Next generation chemistries'}, inplace=True)


    fleet_reduction = primary_materials.loc[ (primary_materials.Stock_Scenarios == 'Low')
                                & (primary_materials.EV_Scenario == 'SD')
                                & (primary_materials.Chemistry_Scenario == 'BNEF')
                                & (primary_materials.Reuse_Scenario == 'LFP reused')
                                & (primary_materials.Size_Scenarios == 'Constant')
                                & (primary_materials.Recycling_Process == 'Pyrometallurgy')]
    fleet_reduction.reset_index(inplace=True, drop=True)
    fleet_reduction.drop(['Stock_Scenarios', 'EV_Scenario', 'Chemistry_Scenario', 'Reuse_Scenario', 'Size_Scenarios','Recycling_Process'], axis=1, inplace=True)
    fleet_reduction.set_index('Element', inplace=True)
    fleet_reduction.rename(columns={'value':'Smaller fleet'}, inplace=True)


    eff_recycling = primary_materials.loc[ (primary_materials.Stock_Scenarios == 'Medium')
                                & (primary_materials.EV_Scenario == 'SD')
                                & (primary_materials.Chemistry_Scenario == 'BNEF')
                                & (primary_materials.Reuse_Scenario == 'LFP reused')
                                & (primary_materials.Size_Scenarios == 'Constant')
                                & (primary_materials.Recycling_Process == 'Direct')]
    eff_recycling.reset_index(inplace=True, drop=True)
    eff_recycling.drop(['Stock_Scenarios', 'EV_Scenario', 'Chemistry_Scenario', 'Reuse_Scenario', 'Size_Scenarios','Recycling_Process'], axis=1, inplace=True)
    eff_recycling.set_index('Element', inplace=True)
    eff_recycling.rename(columns={'value':'Efficient recycling'}, inplace=True)

    faster_ev = primary_materials.loc[ (primary_materials.Stock_Scenarios == 'Medium')
                                & (primary_materials.EV_Scenario == 'Net Zero')
                                & (primary_materials.Chemistry_Scenario == 'BNEF')
                                & (primary_materials.Reuse_Scenario == 'LFP reused')
                                & (primary_materials.Size_Scenarios == 'Constant')
                                & (primary_materials.Recycling_Process == 'Pyrometallurgy')]
    faster_ev.reset_index(inplace=True, drop=True)
    faster_ev.drop(['Stock_Scenarios', 'EV_Scenario', 'Chemistry_Scenario', 'Reuse_Scenario', 'Size_Scenarios','Recycling_Process'], axis=1, inplace=True)
    faster_ev.set_index('Element', inplace=True)
    faster_ev.rename(columns={'value':'Faster electrification'}, inplace=True)
    
    smaller_ev = primary_materials.loc[ (primary_materials.Stock_Scenarios == 'Medium')
                                & (primary_materials.EV_Scenario == 'SD')
                                & (primary_materials.Chemistry_Scenario == 'BNEF')
                                & (primary_materials.Reuse_Scenario == 'LFP reused')
                                & (primary_materials.Size_Scenarios == 'Shift to small cars')
                                & (primary_materials.Recycling_Process == 'Pyrometallurgy')]
    smaller_ev.reset_index(inplace=True, drop=True)
    smaller_ev.drop(['Stock_Scenarios', 'EV_Scenario', 'Chemistry_Scenario', 'Reuse_Scenario', 'Size_Scenarios','Recycling_Process'], axis=1, inplace=True)
    smaller_ev.set_index('Element', inplace=True)
    smaller_ev.rename(columns={'value':'Smaller batteries'}, inplace=True)

    # Concatenating everything into table
    table = pd.concat([shift_to_lfp, shift_to_NCX, shift_to_next_gen, fleet_reduction, eff_recycling, faster_ev, smaller_ev], axis=1)
    table['Replacements'] = sensitivity_replacements
    table['Longer LIB lifetime'] = sensitivity_long_lt
    cm = sns.diverging_palette(133, 10, n=10, as_cmap=True) # 240 for blue and 133 for green
    table = table.style.background_gradient(cmap=cm, axis=None, vmax=1, vmin=-1)          

    # Create a Pandas Excel writer using XlsxWriter as the engine.
    writer = pd.ExcelWriter(os.path.join(os.getcwd(), 'results/sensitivity_table.xlsx'), engine='xlsxwriter')
    # Write each dataframe to a different worksheet.
    table.to_excel(writer, sheet_name='results')
    # Close the Pandas Excel writer and output the Excel file.
    writer.save()
    
def export_P():
    results = os.path.join(os.getcwd(), 'results')
    np.save('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/P_demand_vehicles_global_primary', np.einsum('zSaRpht->zSaRht', MaTrace_System.FlowDict['E_0_1'].Values[:,:,:,:,1,r,:,4,:,:])/1000) # z,S,a,R,V,r,p,e,h,t
    np.save('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/P_demand_vehicles_global_recycled', np.einsum('zSaRpht->zSaRht', MaTrace_System.FlowDict['E_8_1'].Values[:,:,:,:,1,r,:,4,:,:])/1000) # z,S,a,R,V,r,p,e,h,t
    
def export_Li():
    np.save('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/Li_demand_vehicles_global_primary', np.einsum('zSaRVpht->zSaRVht', MaTrace_System.FlowDict['E_0_1'].Values[:,:,:,:,:,r,:,0,:,:])/1000)
    np.save('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/Li_demand_vehicles_global_recycled', np.einsum('zSaRVpht->zSaRVht', MaTrace_System.FlowDict['E_8_1'].Values[:,:,:,:,:,r,:,0,:,:])/1000)

def export_mean_Al():
    al_values = np.zeros((NS, Na, NV, Np, Nt))
    for S in range(NS):
        for a in range(Na):
            for V in range(NV):
                for p in range(Np):
                    al_values[S,a,V,p,:] = (MaTrace_System.FlowDict['E_0_1'].Values[0,S,a,0,V,r,p,2,0,:] + MaTrace_System.FlowDict['E_8_1'].Values[0,S,a,0,V,r,p,2,0,:])/np.einsum('gst->t',MaTrace_System.FlowDict['F_2_3'].Values[0,S,V,r,:,:,:])
    np.save('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/average_Al_content', al_values)
       
def export_Ni():
    results = os.path.join(os.getcwd(), 'results')
    np.save('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/Ni_demand_vehicles_global_primary', np.einsum('zSaRspht->zSaRsht', MaTrace_System.FlowDict['E_0_1'].Values[:,:,:,:,:,r,:,7,:,:])/1000) # z,S,a,R,V,r,p,e,h,t
    np.save('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/Ni_demand_vehicles_global_recycled', np.einsum('zSaRspht->zSaRsht', MaTrace_System.FlowDict['E_8_1'].Values[:,:,:,:,:,r,:,7,:,:])/1000) # z,S,a,R,V,r,p,e,h,t

def export_primary_demand_df(): 
    z,S,a,R,V,r,p,e,h,t = pd.core.reshape.util.cartesian_product(
##z,S,a,R,V,r,p,e,h,t
    [
    IndexTable.Classification[IndexTable.index.get_loc("Stock_Scenarios")].Items,
    IndexTable.Classification[IndexTable.index.get_loc("Scenario")].Items,
    ['NCX', 'LFP', 'Next_Gen_LFP', 'BNEF', 'Next_Gen_BNEF'],
    IndexTable.Classification[IndexTable.index.get_loc("Reuse_Scenarios")].Items,
    IndexTable.Classification[IndexTable.index.get_loc("Size_Scenarios")].Items,
    ['Global'],
    #IndexTable.Classification[IndexTable.index.get_loc("Battery_Parts")].Items,
    IndexTable.Classification[IndexTable.index.get_loc("Element")].Items[:-1],
    IndexTable.Classification[IndexTable.index.get_loc("Recycling_Process")].Items,
    IndexTable.Classification[IndexTable.index.get_loc("Time")].Items[60::]
    ]
    )

    file = pd.DataFrame(
        dict(Stock_scenario=z, EV_penetration_scenario=S, Chemistry_scenario=a, Reuse_scenario=R, Vehicle_size_scenario = V, Region=r,  Material=e,Recycling_Process=h, Time=t)
    )

    values = []
    r=5
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for v in range(NV):
                        for p in range(Np):
                            for e in range(Ne-1):
                                for h in range(Nh):
                                    for t in range(60,Nt):
                                        value = MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,v,r,:,e,h,t].sum(axis=0)/1000 #z,S,a,R,V,r,p,e,h,t
                                        values.append(value)

    file['value'] = values
        
    writer = pd.ExcelWriter('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/02_harmonized_data/parameter_values/primary_material_demand.xlsx', engine='xlsxwriter')
    # Write each dataframe to a different worksheet.
    for z,Z in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Stock_Scenarios')].Items):
        for s,S in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Scenario')].Items):
            file[(file['Stock_scenario']==Z) & (file['EV_penetration_scenario']==S)].to_excel(writer, sheet_name=Z+'_'+S)
    # Close the Pandas Excel writer and output the Excel file.
    writer.save()
   
def export_primary_demand_df_new(): 
    z,S,a,R,V,r,e,h,t = pd.core.reshape.util.cartesian_product(
##z,S,a,R,V,r,p,e,h,t
    [
    IndexTable.Classification[IndexTable.index.get_loc("Stock_Scenarios")].Items,
    IndexTable.Classification[IndexTable.index.get_loc("Scenario")].Items,
    ['NCX', 'LFP', 'Next_Gen_LFP', 'BNEF', 'Next_Gen_BNEF'],
    IndexTable.Classification[IndexTable.index.get_loc("Reuse_Scenarios")].Items,
    IndexTable.Classification[IndexTable.index.get_loc("Size_Scenarios")].Items,
    ['Global'],
    #IndexTable.Classification[IndexTable.index.get_loc("Battery_Parts")].Items,
    IndexTable.Classification[IndexTable.index.get_loc("Element")].Items[:-1],
    IndexTable.Classification[IndexTable.index.get_loc("Recycling_Process")].Items,
    IndexTable.Classification[IndexTable.index.get_loc("Time")].Items[60::]
    ]
    )

    file = pd.DataFrame(
        dict(Stock_scenario=z, EV_penetration_scenario=S, Chemistry_scenario=a, Reuse_scenario=R, Vehicle_size_scenario = V, Region=r,  Material=e,Recycling_Process=h, Time=t)
    )

    values = []
    r=5
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for v in range(NV):
                        for e in range(Ne-1):
                            for h in range(Nh):
                                for t in range(60,Nt):
                                    value = MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,v,r,:,e,h,t].sum(axis=0)/1000 #z,S,a,R,V,r,p,e,h,t
                                    values.append(value)

    file['value'] = values
        
    writer = pd.ExcelWriter('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/02_harmonized_data/parameter_values/primary_material_demand_new.xlsx', engine='xlsxwriter')
    file.to_excel(writer)
    file.to_pickle('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/02_harmonized_data/parameter_values/primary_material_demand_new')
    writer.save()
    
def export_secondary_availability_df_new(): 
    z,S,a,R,V,r,e,h,t = pd.core.reshape.util.cartesian_product(
    [
    IndexTable.Classification[IndexTable.index.get_loc("Stock_Scenarios")].Items,
    IndexTable.Classification[IndexTable.index.get_loc("Scenario")].Items,
    ['NCX', 'LFP', 'Next_Gen_LFP', 'BNEF', 'Next_Gen_BNEF'],
    IndexTable.Classification[IndexTable.index.get_loc("Reuse_Scenarios")].Items,
    IndexTable.Classification[IndexTable.index.get_loc("Size_Scenarios")].Items,
    ['Global'],
    #IndexTable.Classification[IndexTable.index.get_loc("Battery_Parts")].Items,
    IndexTable.Classification[IndexTable.index.get_loc("Element")].Items[:-1],
    IndexTable.Classification[IndexTable.index.get_loc("Recycling_Process")].Items,
    IndexTable.Classification[IndexTable.index.get_loc("Time")].Items[60::]
    ]
    )
    
    file = pd.DataFrame(
        dict(Stock_scenario=z, EV_penetration_scenario=S, Chemistry_scenario=a, Reuse_scenario=R, Vehicle_size_scenario = V, Region=r,  Material=e,Recycling_Process=h, Time=t)
    )

    values = []
    r=5
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for v in range(NV):
                        for e in range(Ne-1):
                            for h in range(Nh):
                                for t in range(60,Nt):
                                    value = MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,v,r,:,e,h,t].sum(axis=0)/1000 #z,S,a,R,V,r,p,e,h,t
                                    values.append(value)

    file['value'] = values
        
    writer = pd.ExcelWriter('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/02_harmonized_data/parameter_values/secondary_material_demand_new.xlsx', engine='xlsxwriter')
    file.to_excel(writer)
    file.to_pickle('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/02_harmonized_data/parameter_values/secondary_material_demand_new')
    writer.save()
    
def export_secondary_availability_df(): 
    z,S,a,R,V,r,p,e,h,t = pd.core.reshape.util.cartesian_product(
    ##z,S,a,R,V,r,p,e,h,t
    [
        IndexTable.Classification[IndexTable.index.get_loc("Stock_Scenarios")].Items,
        IndexTable.Classification[IndexTable.index.get_loc("Scenario")].Items,
        ['NCX', 'LFP', 'Next_Gen_LFP', 'BNEF', 'Next_Gen_BNEF'],
        IndexTable.Classification[IndexTable.index.get_loc("Reuse_Scenarios")].Items,
        IndexTable.Classification[IndexTable.index.get_loc("Size_Scenarios")].Items,
        ['Global'],
        IndexTable.Classification[IndexTable.index.get_loc("Battery_Parts")].Items,
        IndexTable.Classification[IndexTable.index.get_loc("Element")].Items[:-1],
        IndexTable.Classification[IndexTable.index.get_loc("Recycling_Process")].Items,
        IndexTable.Classification[IndexTable.index.get_loc("Time")].Items
    ]
    )
    
    file = pd.DataFrame(
        dict(Stock_scenario=z, EV_penetration_scenario=S, Chemistry_scenario=a, Reuse_scenario=R, Vehicle_size_scenario = V, Region=r, Battery_part=p, Material=e,Recycling_Process=h, Time=t)
    )

    values = []
    r=5
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for v in range(NV):
                        for p in range(Np):
                            for e in range(Ne-1):
                                for h in range(Nh):
                                    for t in range(Nt):
                                        value = MaTrace_System.FlowDict['E_8_1'].Values[z,S,a,R,v,r,p,e,h,t]/1000 #z,S,a,R,V,r,p,e,h,t
                                        values.append(value)

    file['value'] = values
        
    writer = pd.ExcelWriter('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/02_harmonized_data/parameter_values/secondary_material_availability.xlsx', engine='xlsxwriter')
    # Write each dataframe to a different worksheet.
    for z,Z in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Stock_Scenarios')].Items):
        for s,S in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Scenario')].Items):
            file[(file['Stock_scenario']==Z) & (file['EV_penetration_scenario']==S)].to_excel(writer, sheet_name=Z+'_'+S)
    # Close the Pandas Excel writer and output the Excel file.
    writer.save()
    
def export_storylines(): 
    e,t = pd.core.reshape.util.cartesian_product(
    [
        IndexTable.Classification[IndexTable.index.get_loc("Element")].Items[:-1],
        IndexTable.Classification[IndexTable.index.get_loc("Time")].Items
    ]
    )
    
    file = pd.DataFrame(
        dict( Material=e, Time=t)
    )
    file2 = pd.DataFrame(
        dict( Material=e, Time=t)
    )
    
    e01_replacements = np.load('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E01_case6.npy')
    # Define storylines
    EV1 = MaTrace_System.FlowDict['E_0_1'].Values[1,0,1,1,1,r,:,:,2,:].sum(axis=0)
    EV2 = MaTrace_System.FlowDict['E_0_1'].Values[1,1,3,0,1,r,:,:,2,:].sum(axis=0)
    EV3 = MaTrace_System.FlowDict['E_0_1'].Values[1,0,0,0,2,r,:,:,2,:].sum(axis=0)
    EV4 = MaTrace_System.FlowDict['E_0_1'].Values[2,2,4,2,1,r,:,:,1,:].sum(axis=0)
    EV5 = e01_replacements[0,2,7,0,0,r,:,:,0,:].sum(axis=0)
    # Also export recycled materials
    EV1r = MaTrace_System.FlowDict['E_8_1'].Values[1,0,1,1,1,r,:,:,2,:].sum(axis=0)
    EV2r = MaTrace_System.FlowDict['E_8_1'].Values[1,1,3,0,1,r,:,:,2,:].sum(axis=0)
    EV3r = MaTrace_System.FlowDict['E_8_1'].Values[1,0,0,0,2,r,:,:,2,:].sum(axis=0)
    EV4r = MaTrace_System.FlowDict['E_8_1'].Values[2,2,4,2,1,r,:,:,1,:].sum(axis=0)
    EV5r = e81_replacements[0,2,7,0,0,r,:,:,0,:].sum(axis=0)
    
    values = []
    for e in range(Ne-1):
        for t in range(Nt):
            value = EV1[e,t]/1000
            values.append(value)
    
    file['MRS1'] = values
    
    values = []
    for e in range(Ne-1):
        for t in range(Nt):
            value = EV2[e,t]/1000
            values.append(value)
    
    file['MRS2'] = values
    
    values = []
    for e in range(Ne-1):
        for t in range(Nt):
            value = EV3[e,t]/1000
            values.append(value)
    
    file['MRS3'] = values
    
    values = []
    for e in range(Ne-1):
        for t in range(Nt):
            value = EV4[e,t]/1000
            values.append(value)
    
    file['MRS4'] = values
    
    values = []
    for e in range(Ne-1):
        for t in range(Nt):
            value = EV5[e,t]/1000
            values.append(value)
    
    file['MRS5'] = values
    
    # Exporting secondary materials
    values = []
    for e in range(Ne-1):
        for t in range(Nt):
            value = EV1r[e,t]/1000
            values.append(value)
    
    file2['MRS1'] = values
    
    values = []
    for e in range(Ne-1):
        for t in range(Nt):
            value = EV2r[e,t]/1000
            values.append(value)
    
    file2['MRS2'] = values
    
    values = []
    for e in range(Ne-1):
        for t in range(Nt):
            value = EV3r[e,t]/1000
            values.append(value)
    
    file2['MRS3'] = values
    
    values = []
    for e in range(Ne-1):
        for t in range(Nt):
            value = EV4r[e,t]/1000
            values.append(value)
    
    file2['MRS4'] = values
    
    values = []
    for e in range(Ne-1):
        for t in range(Nt):
            value = EV5r[e,t]/1000
            values.append(value)
    
    file2['MRS5'] = values
    writer = pd.ExcelWriter('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/02_harmonized_data/parameter_values/EV_MRS.xlsx', engine='xlsxwriter')
    # Write each dataframe to a different worksheet.
    file.to_excel(writer, sheet_name='Primary_materials')
    file2.to_excel(writer, sheet_name='Secondary_materials')
    # Close the Pandas Excel writer and output the Excel file.
    writer.save()
 
def export_battery_flows():
    z,S,a,V,r,g,s,b,t = pd.core.reshape.util.cartesian_product(
    #z,S,a,V,r,g,s,b,t
    [
        IndexTable.Classification[IndexTable.index.get_loc("Stock_Scenarios")].Items,
        IndexTable.Classification[IndexTable.index.get_loc("Scenario")].Items,
        ['NCX', 'LFP', 'Next_Gen_LFP', 'BNEF', 'Next_Gen_BNEF'],
        IndexTable.Classification[IndexTable.index.get_loc("Size_Scenarios")].Items,
        ['Global'],
        ['BEV', 'PHEV', 'Other'],
        IndexTable.Classification[IndexTable.index.get_loc("Size")].Items,
        IndexTable.Classification[IndexTable.index.get_loc("Battery_Chemistry")].Items[1:-4],
        IndexTable.Classification[IndexTable.index.get_loc("Time")].Items
    ]
    )
    
    file = pd.DataFrame(
        dict(Stock_scenario=z, EV_penetration_scenario=S, Chemistry_scenario=a, Vehicle_size_scenario = V, Region=r, Drive_Train=g, Size=s,Battery_Chemistry=b, Time=t)
    )
    file2 = pd.DataFrame(
        dict(Stock_scenario=z, EV_penetration_scenario=S, Chemistry_scenario=a, Vehicle_size_scenario = V, Region=r, Drive_Train=g, Size=s,Battery_Chemistry=b, Time=t)
    )
    values = []
    r=5
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for v in range(NV):
                    for g in range(1,Ng):
                        for s in range(Ns):
                            for b in [1,2,3,4,5,6,7,8,9,10,11,12]:
                                for t in range(Nt):
                                    value = MaTrace_System.FlowDict['M_2_3'].Values[z,S,a,v,r,g,s,b,t]/1000 #z,S,a,R,V,r,p,e,h,t
                                    values.append(value)

    file['value'] = values
    file['unit'] = 'million'
    
    values = []
    r=5
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for v in range(NV):
                    for g in range(1,Ng):
                        for s in range(Ns):
                            for b in [1,2,3,4,5,6,7,8,9,10,11,12]:
                                for t in range(Nt):
                                    value = MaTrace_System.FlowDict['M_3_4'].Values[z,S,a,v,r,g,s,b,t]/1000 #z,S,a,R,V,r,p,e,h,t
                                    values.append(value)

    file2['value'] = values
    file2['unit'] = 'million'
    
    writer = pd.ExcelWriter('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/02_harmonized_data/parameter_values/system_flows.xlsx', engine='xlsxwriter')
    # Write each dataframe to a different worksheet.
    for z,Z in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Stock_Scenarios')].Items):
        for s,S in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Scenario')].Items):
            file[(file['Stock_scenario']==Z) & (file['EV_penetration_scenario']==S)].to_excel(writer, sheet_name=Z+'_stock_'+S+'inflows')
            file2[(file2['Stock_scenario']==Z) & (file2['EV_penetration_scenario']==S)].to_excel(writer, sheet_name=Z+'_stock_'+S+'outflows')
    # Close the Pandas Excel writer and output the Excel file.
    writer.save()
 
def export_battery_flows_new():
    z,S,a,V,g,b,t = pd.core.reshape.util.cartesian_product(
    #z,S,a,V,r,g,s,b,t
    [
        IndexTable.Classification[IndexTable.index.get_loc("Stock_Scenarios")].Items,
        IndexTable.Classification[IndexTable.index.get_loc("Scenario")].Items,
        ['NCX', 'LFP', 'Next_Gen_LFP', 'BNEF', 'Next_Gen_BNEF'],
        IndexTable.Classification[IndexTable.index.get_loc("Size_Scenarios")].Items,
        ['BEV', 'OTHER', 'PHEV'],
        IndexTable.Classification[IndexTable.index.get_loc("Battery_Chemistry")].Items[1:-4],
        IndexTable.Classification[IndexTable.index.get_loc("Time")].Items[60::]
    ]
    )
    
    file = pd.DataFrame(
        dict(Stock_scenario=z, EV_penetration_scenario=S, Chemistry_scenario=a, Vehicle_size_scenario = V, Drive_Train=g, Battery_Chemistry=b, Time=t)
    )
    file2 = pd.DataFrame(
        dict(Stock_scenario=z, EV_penetration_scenario=S, Chemistry_scenario=a, Vehicle_size_scenario = V,  Drive_Train=g, Battery_Chemistry=b, Time=t)
    )
    values = []
    r=5
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for v in range(NV):
                    for g in range(1,Ng):
                        for b in [1,2,3,4,5,6,7,8,9,10,11,12]:
                            for t in range(60,Nt):
                                value = MaTrace_System.FlowDict['M_2_3'].Values[z,S,a,v,r,g,:,b,t].sum()/1000 #z,S,a,R,V,r,p,e,h,t
                                values.append(value)

    file['value'] = values
    file['unit'] = 'million'
    
    values = []
    r=5
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for v in range(NV):
                    for g in range(1,Ng):
                        for b in [1,2,3,4,5,6,7,8,9,10,11,12]:
                            for t in range(60,Nt):
                                value = MaTrace_System.FlowDict['M_3_4'].Values[z,S,a,v,r,g,:,b,t].sum()/1000 #z,S,a,R,V,r,p,e,h,t
                                values.append(value)

    file2['value'] = values
    file2['unit'] = 'million'
    
    writer = pd.ExcelWriter('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/02_harmonized_data/parameter_values/system_flows_new.xlsx', engine='xlsxwriter')
    file.to_excel(writer)
    file.to_pickle('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/02_harmonized_data/parameter_values/system_flows_new')
    file2.to_pickle('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/02_harmonized_data/parameter_values/outflows')

    
    writer.save()

def export_slb_stock():
    # Calculate capacity
    # z,S,a,R,V,r,t
    r=5
    MaTrace_System.StockDict['C_6'].Values[:,:,:,:,:,r,:,:] = np.einsum('zSaRVgbtc,btc->zSaRVbt',MaTrace_System.StockDict['P_C_6'].Values[:,:,:,:,:,r,:,:,0,:,:], MaTrace_System.ParameterDict['Degradation'].Values[:,:,:])
    z,S,a,R,V,b,t = pd.core.reshape.util.cartesian_product(
    [
        IndexTable.Classification[IndexTable.index.get_loc("Stock_Scenarios")].Items,
        IndexTable.Classification[IndexTable.index.get_loc("Scenario")].Items,
        ['NCX', 'LFP', 'Next_Gen_LFP', 'BNEF', 'Next_Gen_BNEF'],
        IndexTable.Classification[IndexTable.index.get_loc("Reuse_Scenarios")].Items,
        IndexTable.Classification[IndexTable.index.get_loc("Size_Scenarios")].Items,
        IndexTable.Classification[IndexTable.index.get_loc("Battery_Chemistry")].Items[1:-4],
        IndexTable.Classification[IndexTable.index.get_loc("Time")].Items[60::]
    ]
    )
    
    file = pd.DataFrame(
        dict(Stock_scenario=z, EV_penetration_scenario=S, Chemistry_scenario=a, Reuse_scenario = R, Vehicle_size_scenario = V, Battery_Chemistry=b, Time=t)
    )
    values = []
    r=5
    for z in range(Nz):
        for S in range(NS):
            for a in [0,1,3,4,7]:
                for R in range(NR):
                    for v in range(NV):
                        for b in [1,2,3,4,5,6,7,8,9,10,11,12]:
                            for t in range(60,Nt):
                                value = MaTrace_System.StockDict['C_6'].Values[z,S,a,R,v,r,b,t]/1000 #z,S,a,R,V,r,p,e,h,t
                                values.append(value)

    file['value'] = values
    file['unit'] = 'MWh'
    
    writer = pd.ExcelWriter('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/02_harmonized_data/parameter_values/slb_capacity.xlsx', engine='xlsxwriter')
    file.to_excel(writer)
    file.to_pickle('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/02_harmonized_data/parameter_values/slb_capacity')
    
    writer.save()
 
def export_stock():
    r=5
    z,S,V,g,s,t = pd.core.reshape.util.cartesian_product(
    [
        IndexTable.Classification[IndexTable.index.get_loc("Stock_Scenarios")].Items,
        IndexTable.Classification[IndexTable.index.get_loc("Scenario")].Items,
        IndexTable.Classification[IndexTable.index.get_loc("Size_Scenarios")].Items,
        IndexTable.Classification[IndexTable.index.get_loc("Good")].Items,
        IndexTable.Classification[IndexTable.index.get_loc("Size")].Items,
        IndexTable.Classification[IndexTable.index.get_loc("Time")].Items[60::]
    ]
    )
    
    file = pd.DataFrame(
        dict(Stock_scenario=z, EV_penetration_scenario=S, Vehicle_size_scenario = V, Drive_Train = g, Size = s,  Time=t)
    )
    values = []
    r=5
    # z,S,V,r,g,s,t
    for z in range(Nz):
        for S in range(NS):
            for v in range(NV):
                for g in range(Ng):
                    for s in range(Ns):
                        for t in range(60,Nt):
                                value = MaTrace_System.StockDict['S_3'].Values[z,S,v,r,g,s,t].sum()/1000 #z,S,a,R,V,r,p,e,h,t
                                values.append(value)

    file['value'] = values
    file['unit'] = 'Million'
    
    writer = pd.ExcelWriter('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/02_harmonized_data/parameter_values/stock.xlsx', engine='xlsxwriter')
    file.to_excel(writer)
    file.to_pickle('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/02_harmonized_data/parameter_values/stock')
    
    writer.save()
 
def export_sensitivity_over_time():
    r=5
    baseline = MaTrace_System.FlowDict['E_0_1'].Values[1,1,3,0,1,r,:,:,2,:].sum(axis=0)
    z = 1
    S= 1
    R=0
    V=1
    h=2
    a = 1 # High LFP
    df = pd.DataFrame(columns=['Year','Material','Shift to LFP', 'Shift to high Ni', 'Shift to LiS, Li-Air', 'Less stock growth', 'More efficient recycling', 'Faster EV penetration', 'Shift to smaller EVs', 'Battery repairs', 'Longer lifetime'])
    for e,E in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Element')].Items[0:-1]):
        
        lfp = MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,72::].sum(axis=0)-baseline[e,72::]/baseline[e,72::]*100
        
        a = 0 # NCX
        ncx= MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,72::].sum(axis=0)-baseline[e,72::]/baseline[e,72::]*100
        
        a = 4 # Next gen BNEF
        nxtgn = MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,72::].sum(axis=0)-baseline[e,72::]/baseline[e,72::]*100
        
        a = 3 # Base
        z = 0
        lstock = MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,72::].sum(axis=0)-baseline[e,72::]/baseline[e,72::]*100
        
        z = 1 # Base
        h = 0
        eff_rec = MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,72::].sum(axis=0)- baseline[e,72::]/baseline[e,72::]*100

        h = 2 # Base
        S = 2
        hev = MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,72::].sum(axis=0)- baseline[e,72::]/baseline[e,72::]*100

        S = 1 # Base
        V = 0
        sev = MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,V,r,:,e,h,72::].sum(axis=0)- baseline[e,72::]/baseline[e,72::]*100
        
        V = 1 # Base
        rep = e01_replacements[z,S,a,R,V,r,:,e,h,72::].sum(axis=0)- baseline[e,72::]/baseline[e,72::]*100
        
        V = 1 # Base
        lglt = e01_long_lt[z,S,a,R,V,r,:,e,h,72::].sum(axis=0)- baseline[e,72::]/baseline[e,72::]*100
        
        result = pd.DataFrame({'Year':IndexTable.Classification[IndexTable.index.get_loc('Time')].Items[72::],'Material':E,'Shift to LFP': lfp, 'Shift to high Ni': ncx, 'Shift to LiS, Li-Air': nxtgn, 'Less stock growth': lstock, 'More efficient recycling':eff_rec, 'Faster EV penetration':hev, 'Shift to smaller EVs': sev, 'Battery repairs':rep, 'Longer lifetime':lglt})
        df = pd.concat([df, result])
    
    df.to_excel('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/02_harmonized_data/parameter_values/sensitivity_over_time.xlsx')
        
def calculate_capacities():
    MaTrace_System.FlowDict['C_2_3'].Values[:,:,:,:,r,:,:,:,:] = np.einsum('zSaVgsbt,bt->zSaVgsbt', MaTrace_System.FlowDict['B_2_3'].Values[:,:,:,:,r,:,:,:,:], \
        MaTrace_System.ParameterDict['Capacity'].Values[:,0,:])
    MaTrace_System.FlowDict['C_5_6'].Values[:,:,:,:,r,:,:,:,:] = np.einsum('zSaVgsbt,bt->zSaVgsbt', MaTrace_System.FlowDict['B_2_3'].Values[:,:,:,:,r,:,:,:,:], \
        MaTrace_System.ParameterDict['Capacity'].Values[:,0,:])
    # Assume that only 50% of vehicles are V2G ready, and only 50% parked and plugged and that they only make 50% of their capacity available for V2G
    v2g = 0.5
    parked = 0.5
    cap_av = 0.5
    MaTrace_System.StockDict['C_3'].Values[:,:,:,:,r,:,:] = v2g * parked * cap_av * np.einsum('zSaVgsbtc,bc->zSaVgt', MaTrace_System.StockDict['B_C_3'].Values[:,:,:,:,r,:,:,:,:,:], \
        MaTrace_System.ParameterDict['Capacity'].Values[:,0,:])
    # Assume that all SLBs are equally degraded to 70% of original capacity
    deg = 0.7
    MaTrace_System.StockDict['C_6'].Values[:,:,:,:,:,r,:,:] = deg * np.einsum('zSaRVgbtc,bc->zSaRVbt', MaTrace_System.StockDict['P_C_6'].Values[:,:,:,:,:,r,:,:,0,:,:], \
        MaTrace_System.ParameterDict['Capacity'].Values[:,0,:])

    # Plot results
    '''
    Plotting the results for just a few example scenarios with an unconstrained model. 
    This means that we do not restrict the capacity we install to the demand for energy
    storage, but we just install whatever is available. We can compare these impacts to 
    using only new batteries instead in a first iteration. 
    '''
    fig, ax = plt.subplots(1,2, figsize=(20,7))
    stock_cycler = cycler(color=sns.color_palette('Pastel1', 20)) #'Set2', 'Paired', 'YlGnBu'
    custom_cycler = cycler(color=sns.color_palette('Set3', 20)) #'Set2', 'Paired', 'YlGnBu'
    z = 1 
    S = 1 
    a = 0
    V = 1
    R = 2
    ax[0].set_prop_cycle(custom_cycler)
    ax[0].stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                np.einsum('gsbt->bt', MaTrace_System.FlowDict['C_2_3'].Values[z,S,a,V,r,:,:,:,55::]/1e6))
    ax[0].set_ylabel('Capacity [TWh]',fontsize =18)
    right_side = ax[0].spines["right"]
    right_side.set_visible(False)
    top = ax[0].spines["top"]
    top.set_visible(False)
    ax[0].legend([MaTrace_System.IndexTable['Classification']['Battery_Chemistry'].Items[k] for k in np.einsum('bt->b', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,1,:,55:]).nonzero()[0].tolist()], loc='upper left',prop={'size':10})
    ax[0].set_title('Inflow of battery capacity by chemistry', fontsize=20)
    ax[0].set_xlabel('Year',fontsize =16)
    #ax.set_ylim([0,5])
    ax[0].tick_params(axis='both', which='major', labelsize=18)

    ax[1].set_prop_cycle(stock_cycler)
    ax[1].stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                [np.einsum('gt->t', MaTrace_System.StockDict['C_3'].Values[z,S,a,V,r,:,55::]/1e6),\
                    np.einsum('bt->t', MaTrace_System.StockDict['C_6'].Values[z,S,a,R,V,r,:,55::]/1e6)]) 
    ax[1].set_ylabel('Capacity stock [TWh]',fontsize =18)
    right_side = ax[1].spines["right"]
    right_side.set_visible(False)
    top = ax[1].spines["top"]
    top.set_visible(False)
    ax[1].legend(['V2G', 'SLB'], loc='upper left',prop={'size':15})
    ax[1].set_title('Installed capacity by technology', fontsize=20)
    ax[1].set_xlabel('Year',fontsize =18)
    ax[1].tick_params(axis='both', which='major', labelsize=15)
    #fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/capacities')



def model_case_6():
    ########## This scenario should only be run to get the values with battery reuse and replacement
    replacement_rate = 0.8
    reuse_rate = 0.8
    lt_cm  = np.array([12])
    sd_cm  = np.array([5])


    r =5
    for z in range(Nz):
        #for r in range(0,Nr):
        for S in range(NS):
            for g in [1,2]:
                # In this case we assume that the product and component have the same lifetimes and set the delay as 3 years for both goods
                Model                                                     = pcm.ProductComponentModel(t = range(0,Nt), s_pr = MaTrace_System.ParameterDict['Vehicle_stock'].Values[z,r,:]/1000, lt_pr = {'Type': 'Normal', 'Mean': np.array([16]), 'StdDev': np.array([4]) }, \
                    lt_cm = {'Type': 'Normal', 'Mean': lt_cm, 'StdDev': sd_cm}, replacement_coeff=replacement_rate, reuse_coeff=reuse_rate)
                Model.case_6()

                MaTrace_System.StockDict['S_C_3'].Values[z,S,:,r,g,:,:,:]             = np.einsum('Vsc,tc->Vstc', MaTrace_System.ParameterDict['Segment_shares'].Values[:,g,:,:] ,np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.sc_pr.copy()))
                MaTrace_System.StockDict['S_3'].Values[z,S,:,r,g,:,:]                 = np.einsum('Vstc->Vst', MaTrace_System.StockDict['S_C_3'].Values[z,S,:,r,g,:,:,:])
                MaTrace_System.FlowDict['F_2_3'].Values[z,S,:,r,g,:,:]              = np.einsum('Vsc,c->Vsc', MaTrace_System.ParameterDict['Segment_shares'].Values[:,g,:,:],np.einsum('c,c->c', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.i_pr.copy()))
                MaTrace_System.FlowDict['F_3_4'].Values[z,S,:,r,g,:,:,:]              = np.einsum('Vsc,tc->Vstc', MaTrace_System.ParameterDict['Segment_shares'].Values[:,g,:,:],np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:] , Model.oc_pr.copy()))
                

                ### Battery chemistry layer: Here we use the battery stock instead of the vehicle stock
                MaTrace_System.StockDict['M_C_3'].Values[z,S,:,:,r,g,:,:,:,:]     = np.einsum('abc,Vstc->aVsbtc', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , np.einsum('Vsc,tc->Vstc', MaTrace_System.ParameterDict['Segment_shares'].Values[:,g,:,:] \
                    ,np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.sc_cm.copy())))
                MaTrace_System.StockDict['M_3'].Values[z,S,:,:,r,g,:,:,:]         = np.einsum('aVsbtc->aVsbt', MaTrace_System.StockDict['M_C_3'].Values[z,S,:,:,r,g,:,:,:,:])
                # Battery inflows within car
                MaTrace_System.FlowDict['M_2_3'].Values[z,S,:,:,r,g,:,:,:]        = np.einsum('abt,Vst->aVsbt', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] ,MaTrace_System.FlowDict['F_2_3'].Values[z,S,:,r,g,:,:])
                # Battery replacements: Total battery inflows minus inflows of batteries in cars
                MaTrace_System.FlowDict['M_1_3'].Values[z,S,:,:,r,g,:,:,:]        = np.einsum('abc,Vsc->aVsbc', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , np.einsum('Vsc,c->Vsc', MaTrace_System.ParameterDict['Segment_shares'].Values[:,g,:,:], \
                    np.einsum('c,c->c', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.i_cm.copy()))) - MaTrace_System.FlowDict['M_2_3'].Values[z,S,:,:,r,g,:,:,:]
                # Battery outflows in car
                MaTrace_System.FlowDict['M_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:]   = np.einsum('abc,Vstc->aVsbtc', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , MaTrace_System.FlowDict['F_3_4'].Values[z,S,:,r,g,:,:,:])
                MaTrace_System.FlowDict['M_3_4'].Values[z,S,:,:,r,g,:,:,:]        = np.einsum('aVsbtc->aVsbt', MaTrace_System.FlowDict['M_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:])
                # Batteries after vehicle has been dismantled
                MaTrace_System.FlowDict['M_4_5'].Values[z,S,:,:,r,g,:,:,:,:]      = MaTrace_System.FlowDict['M_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:] 
                # Battery outflows due to battery failures: Total battery outflows minus vehicle outflows
                

                ### Battery by weight layer: Multiply the numbers by the weight factor for each chemistry and size
                # Stocks
                MaTrace_System.StockDict['B_C_3'].Values[z,S,:,:,r,g,:,:,:,:]     = np.einsum('sb,aVsbtc->aVsbtc', MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:] , MaTrace_System.StockDict['M_C_3'].Values[z,S,:,:,r,g,:,:,:,:])
                MaTrace_System.StockDict['B_3'].Values[z,S,:,:,r,g,:,:,:]         = np.einsum('aVsbtc->aVsbt', MaTrace_System.StockDict['B_C_3'].Values[z,S,:,:,r,g,:,:,:,:])
                MaTrace_System.FlowDict['B_1_3'].Values[z,S,:,:,r,g,:,:,:]        = np.einsum('aVsbt,sb->aVsbt', MaTrace_System.FlowDict['M_1_3'].Values[z,S,:,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:])
                MaTrace_System.FlowDict['B_2_3'].Values[z,S,:,:,r,g,:,:,:]        = np.einsum('aVsbt,sb->aVsbt', MaTrace_System.FlowDict['M_2_3'].Values[z,S,:,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:])
                MaTrace_System.FlowDict['B_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:]   = np.einsum('aVsbtc,sb->aVsbtc', MaTrace_System.FlowDict['M_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:], MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:])
                MaTrace_System.FlowDict['B_3_4'].Values[z,S,:,:,r,g,:,:,:]        = np.einsum('aVsbtc->aVsbt', MaTrace_System.FlowDict['B_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:] )
                MaTrace_System.FlowDict['B_4_5'].Values[z,S,:,:,r,g,:,:,:,:]      = MaTrace_System.FlowDict['B_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:] 
                # MaTrace_System.FlowDict['B_5_3'].Values[z,S,:,:,r,g,:,:,:]        = np.einsum('aVsbt,sb->aVsbt', MaTrace_System.FlowDict['M_5_3'].Values[z,S,:,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:])
                

                ### Battery parts layer
                MaTrace_System.StockDict['P_C_3'].Values[z,S,:,:,r,g,:,:,:,:,:]   = np.einsum('sbp,aVsbtc->aVsbptc', MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:] , MaTrace_System.StockDict['B_C_3'].Values[z,S,:,:,r,g,:,:,:,:])
                MaTrace_System.StockDict['P_3'].Values[z,S,:,:,r,g,:,:,:,:]       = np.einsum('aVsbptc->aVsbpt', MaTrace_System.StockDict['P_C_3'].Values[z,S,:,:,r,g,:,:,:,:,:])
                MaTrace_System.FlowDict['P_1_3'].Values[z,S,:,:,r,g,:,:,:,:]      = np.einsum('aVsbc,sbp->aVsbpc', MaTrace_System.FlowDict['B_1_3'].Values[z,S,:,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:]) 
                MaTrace_System.FlowDict['P_2_3'].Values[z,S,:,:,r,g,:,:,:,:]      = np.einsum('aVsbc,sbp->aVsbpc', MaTrace_System.FlowDict['B_2_3'].Values[z,S,:,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:]) 
                MaTrace_System.FlowDict['P_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:,:] = np.einsum('aVsbtc,sbp->aVsbptc', MaTrace_System.FlowDict['B_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:], MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:])
                MaTrace_System.FlowDict['P_3_4'].Values[z,S,:,:,r,g,:,:,:,:]      = np.einsum('aVsbptc->aVsbpt', MaTrace_System.FlowDict['P_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:,:])
                MaTrace_System.FlowDict['P_4_5'].Values[z,S,:,:,r,g,:,:,:,:,:]    = MaTrace_System.FlowDict['P_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:,:]
                # MaTrace_System.FlowDict['P_5_3'].Values[z,S,:,:,r,g,:,:,:,:]      = np.einsum('aVsbt,sbp->aVsbpt', MaTrace_System.FlowDict['B_5_3'].Values[z,S,:,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:])
                
                '''
                We calculate the flows of battery modules into reuse. Sicne the casing and other battery parts are assumed to go directly into recyling, 
                we just write this loop for the modules with index 0 and separately define that all other battery parts go to recycling. 
                We also consider batteries that caused vehicle outflows, as the requirements here are lower. We can take them out if it does not make sense. 

                The reuse parameter does not indicate the share of batteries that are reused. Rather, it is a condition to reflect decisions on which battery chemistries to 
                reuse. LFP scenario for instance will define that only LFP chemistries are considered for reuse, but they health assessment still needs to happen. 
                '''
                # Calculate inflows to SLB only for the modules. We consider batteries that came from failed vehicles as well, since flow P_3_5 only contains failed batteries
                MaTrace_System.FlowDict['P_5_6'].Values[z,S,:,:,:,r,g,:,0,:,:]  = np.einsum('Rbt,aVsbtc->aRVbtc', MaTrace_System.ParameterDict['Reuse_rate'].Values[:,:,:], \
                    MaTrace_System.FlowDict['P_3_4_tc'].Values[z,S,:,:,r,g,:,:,0,:,:]) # * Model_slb.sf_cm[t+tau_cm,c] + MaTrace_System.FlowDict['P_3_5'].Values[z,S,:,r,g,:,:,0,t,c]* Model_slb.sf_cm[t+tau_cm,c]) # TODO: Possibly subtract P_5_3 flow if implemented
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
    inflows                             = np.zeros((Nz,NS, Na, NR, NV,Ng,Nb, Nt))
    inflows = np.einsum('zSaRVgbtc->zSaRVgbt',MaTrace_System.FlowDict['P_5_6'].Values[:,:,:,:,:,r,:,:,0,:,:])
    for z in range(Nz):
        for S in range(NS):
            for a in range(Na):
                for R in range(NR):
                    for b in range(Nb):
                        for V in range(NV):
                            for g in [1,2]: # Only BEV, PHEV
                                slb_model                        = dsm.DynamicStockModel(t=range(0,Nt), lt={'Type': 'Normal', 'Mean': lt_slb, 'StdDev': sd_slb}, i=inflows[z,S,a,R,V,g,b,:])
                                slb_model.compute_s_c_inflow_driven()
                                slb_model.compute_o_c_from_s_c()
                                slb_model.compute_stock_total()
                                MaTrace_System.StockDict['P_C_6'].Values[z,S,a,R,V,r,g,b,0,:,:] = slb_model.s_c.copy()
                                MaTrace_System.FlowDict['P_6_7'].Values[z,S,a,R,V,r,g,b,0,:,:] = slb_model.o_c.copy()

    # Compute total stock
    for a in range(Na):
        MaTrace_System.StockDict['P_6'].Values[:,:,a,:,:,r,:,0,:]         = np.einsum('zSRVgbtc->zSRVbt', MaTrace_System.StockDict['P_C_6'].Values[:,:,a,:,:,r,:,:,0,:,:])
        MaTrace_System.FlowDict['P_7_8'].Values[:,:,a,:,:,r,:,:,0,:,:]                  = MaTrace_System.FlowDict['P_6_7'].Values[:,:,a,:,:,r,:,:,0,:,:]
        # Calculate battery parts going directly to recycling: Total outflows minus reuse
        for R in range(NR):
            MaTrace_System.FlowDict['P_5_8'].Values[:,:,a,R,:,r,:,:,:,:,:]            =  np.einsum('zSVgsbptc->zSVgbptc', MaTrace_System.FlowDict['P_3_4_tc'].Values[:,:,a,:,r,:,:,:,:,:,:]) - MaTrace_System.FlowDict['P_5_6'].Values[:,:,a,R,:,r,:,:,:,:,:]

    ### Material layer
    for z in range(Nz):
        # for S in range(NS):
            for a in range(Na):
                MaTrace_System.StockDict['E_3'].Values[z,:,a,:,r,:,:,:]           = np.einsum('SVgsbpt,gbpe->SVpet', MaTrace_System.StockDict['P_3'].Values[z,:,a,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:])
                MaTrace_System.FlowDict['E_1_3'].Values[z,:,a,:,r,:,:,:]          = np.einsum('SVgsbpc,gbpe->SVpec', MaTrace_System.FlowDict['P_1_3'].Values[z,:,a,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
                MaTrace_System.FlowDict['E_2_3'].Values[z,:,a,:,r,:,:,:]          = np.einsum('SVgsbpc,gbpe->SVpec', MaTrace_System.FlowDict['P_2_3'].Values[z,:,a,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
                MaTrace_System.FlowDict['E_3_4'].Values[z,:,a,:,r,:,:,:]          = np.einsum('SVgsbpt,gbpe->SVpet', MaTrace_System.FlowDict['P_3_4'].Values[z,:,a,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
                MaTrace_System.FlowDict['E_4_5'].Values[z,:,a,:,r,:,:,:]          = MaTrace_System.FlowDict['E_3_4'].Values[z,:,a,:,r,:,:,:]
                MaTrace_System.FlowDict['E_3_5'].Values[z,:,a,:,r,:,:,:]          = np.einsum('SVgsbptc,gbpe->SVpet', MaTrace_System.FlowDict['P_3_5'].Values[z,:,a,:,r,:,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
                # MaTrace_System.FlowDict['E_5_3'].Values[z,:,a,:,r,:,:,:]          = np.einsum('SVgsbpt,gbpe->SVpet', MaTrace_System.FlowDict['P_5_3'].Values[z,:,a,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
                MaTrace_System.FlowDict['E_5_6'].Values[z,:,a,:,:,r,:,:,:]        = np.einsum('SRVgbptc,gbpe->SRVpet', MaTrace_System.FlowDict['P_5_6'].Values[z,:,a,:,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
                MaTrace_System.FlowDict['E_5_8'].Values[z,:,a,:,:,r,:,:,:]        = np.einsum('SRVgbptc,gbpe->SRVpet', MaTrace_System.FlowDict['P_5_8'].Values[z,:,a,:,:,r,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
                MaTrace_System.FlowDict['E_6_7'].Values[z,:,a,:,:,r,:,:,:]        = np.einsum('SRVgbptc,gbpe->SRVpet', MaTrace_System.FlowDict['P_6_7'].Values[z,:,a,:,:,r,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
                MaTrace_System.FlowDict['E_7_8'].Values[z,:,a,:,:,r,:,:,:]        = np.einsum('SRVgbptc,gbpe->SRVpet', MaTrace_System.FlowDict['P_7_8'].Values[z,:,a,:,:,r,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
                MaTrace_System.FlowDict['E_8_1'].Values[z,:,a,:,:,r,:,:,:,:]      = np.einsum('eh, SRVpet->SRVpeht', MaTrace_System.ParameterDict['Recycling_efficiency'].Values[:,:], (MaTrace_System.FlowDict['E_7_8'].Values[z,:,a,:,:,r,:,:,:] + MaTrace_System.FlowDict['E_5_8'].Values[z,:,a,:,:,r,:,:,:]))
                for R in range(NR):
                    for h in range(Nh):
                        MaTrace_System.FlowDict['E_0_1'].Values[z,:,a,R,:,r,:,:,h,:] =  MaTrace_System.FlowDict['E_2_3'].Values[z,:,a,:,r,:,:,:] - MaTrace_System.FlowDict['E_8_1'].Values[z,:,a,R,:,r,:,:,h,:]# +MaTrace_System.FlowDict['E_1_3'].Values[z,:,a,:,r,:,:,:] # Solving recycling loop z,S,a,R,V,r,p,e,h,t

    np.save('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E01_case6', MaTrace_System.FlowDict['E_0_1'].Values[:,:,:,:,:,:,:,:,:,:])
    np.save('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E81_case6', MaTrace_System.FlowDict['E_8_1'].Values[:,:,:,:,:,:,:,:,:,:])
    np.save('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E13_case6', MaTrace_System.FlowDict['E_1_3'].Values[:,:,:,:,:,:,:,:])
    np.save('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E23_case6', MaTrace_System.FlowDict['E_2_3'].Values[:,:,:,:,:,:,:,:])

def model_long_lt():
    lt_cm  = np.array([16])
    sd_cm  = np.array([5])

    r=5
    for z in range(Nz):
        #for r in range(0,Nr):
        for S in range(NS):
            for g in [1,2]:
                # In this case we assume that the product and component have the same lifetimes and set the delay as 3 years for both goods
                Model                                                     = pcm.ProductComponentModel(t = range(0,Nt), s_pr = MaTrace_System.ParameterDict['Vehicle_stock'].Values[z,r,:]/1000, lt_pr = {'Type': 'Normal', 'Mean': np.array([16]), 'StdDev': np.array([4]) }, \
                    lt_cm = {'Type': 'Normal', 'Mean': lt_cm, 'StdDev': sd_cm})
                Model.case_3()

                MaTrace_System.StockDict['S_C_3'].Values[z,S,:,r,g,:,:,:]             = np.einsum('Vsc,tc->Vstc', MaTrace_System.ParameterDict['Segment_shares'].Values[:,g,:,:] ,np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.sc_pr.copy()))
                MaTrace_System.StockDict['S_3'].Values[z,S,:,r,g,:,:]                 = np.einsum('Vstc->Vst', MaTrace_System.StockDict['S_C_3'].Values[z,S,:,r,g,:,:,:])
                MaTrace_System.FlowDict['F_2_3'].Values[z,S,:,r,g,:,:]              = np.einsum('Vsc,c->Vsc', MaTrace_System.ParameterDict['Segment_shares'].Values[:,g,:,:],np.einsum('c,c->c', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.i_pr.copy()))
                MaTrace_System.FlowDict['F_3_4'].Values[z,S,:,r,g,:,:,:]              = np.einsum('Vsc,tc->Vstc', MaTrace_System.ParameterDict['Segment_shares'].Values[:,g,:,:],np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:] , Model.oc_pr.copy()))
                

                ### Battery chemistry layer: Here we use the battery stock instead of the vehicle stock
                MaTrace_System.StockDict['M_C_3'].Values[z,S,:,:,r,g,:,:,:,:]     = np.einsum('abc,Vstc->aVsbtc', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , np.einsum('Vsc,tc->Vstc', MaTrace_System.ParameterDict['Segment_shares'].Values[:,g,:,:] \
                    ,np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.sc_cm.copy())))
                MaTrace_System.StockDict['M_3'].Values[z,S,:,:,r,g,:,:,:]         = np.einsum('aVsbtc->aVsbt', MaTrace_System.StockDict['M_C_3'].Values[z,S,:,:,r,g,:,:,:,:])
                # Battery inflows within car
                MaTrace_System.FlowDict['M_2_3'].Values[z,S,:,:,r,g,:,:,:]        = np.einsum('abt,Vst->aVsbt', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] ,MaTrace_System.FlowDict['F_2_3'].Values[z,S,:,r,g,:,:])
                # Battery replacements: Total battery inflows minus inflows of batteries in cars
                MaTrace_System.FlowDict['M_1_3'].Values[z,S,:,:,r,g,:,:,:]        = np.einsum('abc,Vsc->aVsbc', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , np.einsum('Vsc,c->Vsc', MaTrace_System.ParameterDict['Segment_shares'].Values[:,g,:,:], \
                    np.einsum('c,c->c', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.i_cm.copy()))) - MaTrace_System.FlowDict['M_2_3'].Values[z,S,:,:,r,g,:,:,:]
                # Battery outflows in car
                MaTrace_System.FlowDict['M_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:]   = np.einsum('abc,Vstc->aVsbtc', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , MaTrace_System.FlowDict['F_3_4'].Values[z,S,:,r,g,:,:,:])
                MaTrace_System.FlowDict['M_3_4'].Values[z,S,:,:,r,g,:,:,:]        = np.einsum('aVsbtc->aVsbt', MaTrace_System.FlowDict['M_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:])
                # Batteries after vehicle has been dismantled
                MaTrace_System.FlowDict['M_4_5'].Values[z,S,:,:,r,g,:,:,:,:]      = MaTrace_System.FlowDict['M_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:] 
                # Battery outflows due to battery failures: Total battery outflows minus vehicle outflows
                

                ### Battery by weight layer: Multiply the numbers by the weight factor for each chemistry and size
                # Stocks
                MaTrace_System.StockDict['B_C_3'].Values[z,S,:,:,r,g,:,:,:,:]     = np.einsum('sb,aVsbtc->aVsbtc', MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:] , MaTrace_System.StockDict['M_C_3'].Values[z,S,:,:,r,g,:,:,:,:])
                MaTrace_System.StockDict['B_3'].Values[z,S,:,:,r,g,:,:,:]         = np.einsum('aVsbtc->aVsbt', MaTrace_System.StockDict['B_C_3'].Values[z,S,:,:,r,g,:,:,:,:])
                MaTrace_System.FlowDict['B_1_3'].Values[z,S,:,:,r,g,:,:,:]        = np.einsum('aVsbt,sb->aVsbt', MaTrace_System.FlowDict['M_1_3'].Values[z,S,:,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:])
                MaTrace_System.FlowDict['B_2_3'].Values[z,S,:,:,r,g,:,:,:]        = np.einsum('aVsbt,sb->aVsbt', MaTrace_System.FlowDict['M_2_3'].Values[z,S,:,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:])
                MaTrace_System.FlowDict['B_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:]   = np.einsum('aVsbtc,sb->aVsbtc', MaTrace_System.FlowDict['M_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:], MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:])
                MaTrace_System.FlowDict['B_3_4'].Values[z,S,:,:,r,g,:,:,:]        = np.einsum('aVsbtc->aVsbt', MaTrace_System.FlowDict['B_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:] )
                MaTrace_System.FlowDict['B_4_5'].Values[z,S,:,:,r,g,:,:,:,:]      = MaTrace_System.FlowDict['B_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:] 
                # MaTrace_System.FlowDict['B_5_3'].Values[z,S,:,:,r,g,:,:,:]        = np.einsum('aVsbt,sb->aVsbt', MaTrace_System.FlowDict['M_5_3'].Values[z,S,:,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Weight'].Values[g,:,:])
                

                ### Battery parts layer
                MaTrace_System.StockDict['P_C_3'].Values[z,S,:,:,r,g,:,:,:,:,:]   = np.einsum('sbp,aVsbtc->aVsbptc', MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:] , MaTrace_System.StockDict['B_C_3'].Values[z,S,:,:,r,g,:,:,:,:])
                MaTrace_System.StockDict['P_3'].Values[z,S,:,:,r,g,:,:,:,:]       = np.einsum('aVsbptc->aVsbpt', MaTrace_System.StockDict['P_C_3'].Values[z,S,:,:,r,g,:,:,:,:,:])
                MaTrace_System.FlowDict['P_1_3'].Values[z,S,:,:,r,g,:,:,:,:]      = np.einsum('aVsbc,sbp->aVsbpc', MaTrace_System.FlowDict['B_1_3'].Values[z,S,:,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:]) 
                MaTrace_System.FlowDict['P_2_3'].Values[z,S,:,:,r,g,:,:,:,:]      = np.einsum('aVsbc,sbp->aVsbpc', MaTrace_System.FlowDict['B_2_3'].Values[z,S,:,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:]) 
                MaTrace_System.FlowDict['P_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:,:] = np.einsum('aVsbtc,sbp->aVsbptc', MaTrace_System.FlowDict['B_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:], MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:])
                MaTrace_System.FlowDict['P_3_4'].Values[z,S,:,:,r,g,:,:,:,:]      = np.einsum('aVsbptc->aVsbpt', MaTrace_System.FlowDict['P_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:,:])
                MaTrace_System.FlowDict['P_4_5'].Values[z,S,:,:,r,g,:,:,:,:,:]    = MaTrace_System.FlowDict['P_3_4_tc'].Values[z,S,:,:,r,g,:,:,:,:,:]
                # MaTrace_System.FlowDict['P_5_3'].Values[z,S,:,:,r,g,:,:,:,:]      = np.einsum('aVsbt,sbp->aVsbpt', MaTrace_System.FlowDict['B_5_3'].Values[z,S,:,:,r,g,:,:,:], MaTrace_System.ParameterDict['Battery_Parts'].Values[g,:,:,:])
                
                '''
                We calculate the flows of battery modules into reuse. Sicne the casing and other battery parts are assumed to go directly into recyling, 
                we just write this loop for the modules with index 0 and separately define that all other battery parts go to recycling. 
                We also consider batteries that caused vehicle outflows, as the requirements here are lower. We can take them out if it does not make sense. 

                The reuse parameter does not indicate the share of batteries that are reused. Rather, it is a condition to reflect decisions on which battery chemistries to 
                reuse. LFP scenario for instance will define that only LFP chemistries are considered for reuse, but they health assessment still needs to happen. 
                '''
                # Calculate inflows to SLB only for the modules. We consider batteries that came from failed vehicles as well, since flow P_3_5 only contains failed batteries
                MaTrace_System.FlowDict['P_5_6'].Values[z,S,:,:,:,r,g,:,0,:,:]  = np.einsum('Rbt,aVsbtc->aRVbtc', MaTrace_System.ParameterDict['Reuse_rate'].Values[:,:,:], \
                    MaTrace_System.FlowDict['P_3_4_tc'].Values[z,S,:,:,r,g,:,:,0,:,:]) # * Model_slb.sf_cm[t+tau_cm,c] + MaTrace_System.FlowDict['P_3_5'].Values[z,S,:,r,g,:,:,0,t,c]* Model_slb.sf_cm[t+tau_cm,c]) # TODO: Possibly subtract P_5_3 flow if implemented
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
    #%%
    '''
    Define the SLB model in advance. We do not compute everything using the dsm as it only takes i as input
    and takes too long to compute. Instead, we define the functions ourselves using the sf computed with dsm. 
    '''
    lt_slb                               = np.array([6]) # We could have different lifetimes for the different chemistries
    sd_slb                               = np.array([2]) 
    inflows                             = np.zeros((Nz,NS, Na, NR, NV,Ng,Nb, Nt))
    inflows = np.einsum('zSaRVgbtc->zSaRVgbt',MaTrace_System.FlowDict['P_5_6'].Values[:,:,:,:,:,r,:,:,0,:,:])
    for z in range(Nz):
        for S in range(NS):
            for a in range(Na):
                for R in range(NR):
                    for b in range(Nb):
                        for V in range(NV):
                            for g in [1,2]: # Only BEV, PHEV
                                slb_model                        = dsm.DynamicStockModel(t=range(0,Nt), lt={'Type': 'Normal', 'Mean': lt_slb, 'StdDev': sd_slb}, i=inflows[z,S,a,R,V,g,b,:])
                                slb_model.compute_s_c_inflow_driven()
                                slb_model.compute_o_c_from_s_c()
                                slb_model.compute_stock_total()
                                MaTrace_System.StockDict['P_C_6'].Values[z,S,a,R,V,r,g,b,0,:,:] = slb_model.s_c.copy()
                                MaTrace_System.FlowDict['P_6_7'].Values[z,S,a,R,V,r,g,b,0,:,:] = slb_model.o_c.copy()

    #%%
    # Compute total stock
    for a in range(Na):
        MaTrace_System.StockDict['P_6'].Values[:,:,a,:,:,r,:,0,:]         = np.einsum('zSRVgbtc->zSRVbt', MaTrace_System.StockDict['P_C_6'].Values[:,:,a,:,:,r,:,:,0,:,:])
        MaTrace_System.FlowDict['P_7_8'].Values[:,:,a,:,:,r,:,:,0,:,:]                  = MaTrace_System.FlowDict['P_6_7'].Values[:,:,a,:,:,r,:,:,0,:,:]
        # Calculate battery parts going directly to recycling: Total outflows minus reuse
        for R in range(NR):
            MaTrace_System.FlowDict['P_5_8'].Values[:,:,a,R,:,r,:,:,:,:,:]            =  np.einsum('zSVgsbptc->zSVgbptc', MaTrace_System.FlowDict['P_3_4_tc'].Values[:,:,a,:,r,:,:,:,:,:,:]) - MaTrace_System.FlowDict['P_5_6'].Values[:,:,a,R,:,r,:,:,:,:,:]

    #%%
    ### Material layer
    for z in range(Nz):
        # for S in range(NS):
            for a in range(Na):
                MaTrace_System.StockDict['E_3'].Values[z,:,a,:,r,:,:,:]           = np.einsum('SVgsbpt,gbpe->SVpet', MaTrace_System.StockDict['P_3'].Values[z,:,a,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:])
                MaTrace_System.FlowDict['E_1_3'].Values[z,:,a,:,r,:,:,:]          = np.einsum('SVgsbpc,gbpe->SVpec', MaTrace_System.FlowDict['P_1_3'].Values[z,:,a,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
                MaTrace_System.FlowDict['E_2_3'].Values[z,:,a,:,r,:,:,:]          = np.einsum('SVgsbpc,gbpe->SVpec', MaTrace_System.FlowDict['P_2_3'].Values[z,:,a,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
                MaTrace_System.FlowDict['E_3_4'].Values[z,:,a,:,r,:,:,:]          = np.einsum('SVgsbpt,gbpe->SVpet', MaTrace_System.FlowDict['P_3_4'].Values[z,:,a,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
                MaTrace_System.FlowDict['E_4_5'].Values[z,:,a,:,r,:,:,:]          = MaTrace_System.FlowDict['E_3_4'].Values[z,:,a,:,r,:,:,:]
                MaTrace_System.FlowDict['E_3_5'].Values[z,:,a,:,r,:,:,:]          = np.einsum('SVgsbptc,gbpe->SVpet', MaTrace_System.FlowDict['P_3_5'].Values[z,:,a,:,r,:,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
                # MaTrace_System.FlowDict['E_5_3'].Values[z,:,a,:,r,:,:,:]          = np.einsum('SVgsbpt,gbpe->SVpet', MaTrace_System.FlowDict['P_5_3'].Values[z,:,a,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
                MaTrace_System.FlowDict['E_5_6'].Values[z,:,a,:,:,r,:,:,:]        = np.einsum('SRVgbptc,gbpe->SRVpet', MaTrace_System.FlowDict['P_5_6'].Values[z,:,a,:,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
                MaTrace_System.FlowDict['E_5_8'].Values[z,:,a,:,:,r,:,:,:]        = np.einsum('SRVgbptc,gbpe->SRVpet', MaTrace_System.FlowDict['P_5_8'].Values[z,:,a,:,:,r,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
                MaTrace_System.FlowDict['E_6_7'].Values[z,:,a,:,:,r,:,:,:]        = np.einsum('SRVgbptc,gbpe->SRVpet', MaTrace_System.FlowDict['P_6_7'].Values[z,:,a,:,:,r,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
                MaTrace_System.FlowDict['E_7_8'].Values[z,:,a,:,:,r,:,:,:]        = np.einsum('SRVgbptc,gbpe->SRVpet', MaTrace_System.FlowDict['P_7_8'].Values[z,:,a,:,:,r,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) 
                MaTrace_System.FlowDict['E_8_1'].Values[z,:,a,:,:,r,:,:,:,:]      = np.einsum('eh, SRVpet->SRVpeht', MaTrace_System.ParameterDict['Recycling_efficiency'].Values[:,:], (MaTrace_System.FlowDict['E_7_8'].Values[z,:,a,:,:,r,:,:,:] + MaTrace_System.FlowDict['E_5_8'].Values[z,:,a,:,:,r,:,:,:]))
                for R in range(NR):
                    for h in range(Nh):
                        MaTrace_System.FlowDict['E_0_1'].Values[z,:,a,R,:,r,:,:,h,:] =  MaTrace_System.FlowDict['E_2_3'].Values[z,:,a,:,r,:,:,:] - MaTrace_System.FlowDict['E_8_1'].Values[z,:,a,R,:,r,:,:,h,:]# +MaTrace_System.FlowDict['E_1_3'].Values[z,:,a,:,r,:,:,:] # Solving recycling loop z,S,a,R,V,r,p,e,h,t

    np.save('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E01_long_lt', MaTrace_System.FlowDict['E_0_1'].Values[:,:,:,:,:,:,:,:,:,:])
    np.save('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E81_long_lt', MaTrace_System.FlowDict['E_8_1'].Values[:,:,:,:,:,:,:,:,:,:])
    np.save('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E13_long_lt', MaTrace_System.FlowDict['E_1_3'].Values[:,:,:,:,:,:,:,:])
    np.save('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/E23_long_lt', MaTrace_System.FlowDict['E_2_3'].Values[:,:,:,:,:,:,:,:])
    np.save('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/F23_long_lt', MaTrace_System.FlowDict['F_2_3'].Values[:,:,:,:,:,:,:])
    np.save('/Users/fernaag/Library/CloudStorage/Box-Box/BATMAN/Data/Database/data/04_model_output/F34_long_lt', MaTrace_System.FlowDict['F_3_4'].Values[:,:,:,:,:,:,:,:])

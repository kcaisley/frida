Usage: 
1) To get help for usage                                                        
  pvs [ -h | -help ]

2) To get version information                                                   
  pvs [ -v | -version ]

3) To run layout verification                                                   
  a) Options that apply to all flows (DRC, LVL/XOR, ERC, PERC, LVS, ANT, FILL, EXT)
                                                                                
  pvs
      [-license_timeout]          How long to wait (seconds) if a license is not
                                  immediately available.                        
      [-license_notshared]        In DP, do not use LVS licenses in a DRC run,  
                                  or DRC licenses in an LVS run.                
                                  (For PVS licenses only).                      
      [-license_dp_continue]      In DP, if PVS cannot obtain the required      
                                  number of licenses, continue with fewer CPUs  
                                  based on the number of licenses obtained.     
                                  (For PVS licenses only).                      
      [-use_pvs_licenses]         Use only PVS licenses.                        
      [-use_pegasus_licenses]     Use only Pegasus licenses.                    
      [-show_license]             Show the licenses required for the run        
      [-license_schema <213|pre213>]  Specify license schema, 213 is default    
                                  then exit.                                    
      [-dp {n [-lsf]} | {n:h|h -rsh|-ssh} [-dpdir dirName] [-dpsubdir path]     
                                  Run PVS with multi-CPU                        
                                  n: number of total processors                 
                                  h: Host name list                             
                                  dirName: directory for slave outputs          
                                  path: path for DP temporary files             
                                  -rsh,-ssh,-lsf: distribute mode               
      [-mp {h -rsh|-ssh} | {n [-lsf]} [-mt m] [-mpdir dirName] [-dpsubdir path]]
                                  Run PVS with multi-CPU                        
                                  h: Host name list                             
                                  n: number of slave processes                  
                                  m: number of threads per slave process        
                                  dirName: directory for slave outputs          
                                  path: path for temporary files                
                                  -rsh,-ssh,-lsf: distribute mode               
      [-dplsfconfig|-mplsfconfig config_file]                                   
                                  specifies flexible lsf resource control       
      [-dptimeout val]            Specifies how long to wait for DP processes   
                                  to start.                                     
      [-dpnoseq]                  Enable output master log file out-of-sequence.
      [-log log_file]             Specify file to write logging output.         
      [-resdb_log log_file]       Specify name of log file for generating gds/oasis results.
      [-disable_enc_parser_log]   Specify not to output encrypted statements in log file during rule deck parsing.
      [-outrule]                  Output effective rule file.                   
      [-flatten | -f]             Special option for extracting flat.           
      [-gds filename]             Specifies GDS input layout database.          
      [-oasis filename ]          Specifies OASIS input layout database.        
      [-oalib filename]           Activates DFII input and specifies the OA     
                                  library to read the top cell from.            
      [-oamap filename]           Specifies the layer map file to use.          
      [-oaomap filename]          Specifies the object map file to use.         
      [-oacmap filename]          Specifies the cell map file to use.           
      [-oapath dirname]           Specifies the directory in which the library  
                                  definition file can be found.                 
      [-oaview viewName]          Specifies the view name of the top cell.      
      [-top_cell cellName]        Specifies the primary cell name.              
      [-ascrdb | -gdsrdb | -oasrdb file]    Override 'results_db' statement in rule deck. 
      [-ui_data | -no_ui_data]    Generate (or do not generate) data for PVS    
                                  Debugging GUI (default).                      
      [-control filename]         Specifies the control file created by PVS GUI.
      [-time2error]               Enables time to error feature.                
      [-run_dir dirname]          Specifies the run directory.                  
      rulefile                    PVL rule file                                 
                                                                                
  b) Options that apply to DRC/LVL/XOR/FILL flows                               
      [-drc]                      Specify tool flow type as DRC flow.           
      [-dfm_data]                 Generate the data for running PVS DFM RV      
      [-big_coordinate]           Use 64bit coordinate                          
      [-bwf waiver_setup_file]    Specifies the waiver setup file.              
      [-fill]                     All OUTPUT commands default to -AUTOREF       
      [-antenna_bbox_file filename]                                             
                                  Specifies LEF Antenna information file.       
      [-kzp]                      Keeps zero width paths while reading layouts. 
      [-flatten_output]           Enable output flattened db result.            
                                                                                
  b1) Options that apply to V-DRC flow                                          
      [ -simResultsDir |          Use simulation results or a net-voltage file  
        -netVoltageFile ]         for the voltage input.                        
      [-simRun]                   The simulation run name (with -simResultsDir) 
      [-simCorner]                The simulation corner   (with -simResultsDir) 
      [-simTopCell]               The top cell (for both input types).          
      [-layTopCell]               The layout top cell (if not the same).        
      [-netToTextLayerMap]        Net-to-text layer mapping file (NTLM).        
      [-lvsRunDir]                The LVS results dir (input).                  
      [-lvsRunName]               The LVS run name (input).                     
                                                                                
  c) Options that apply to ERC flow                                             
      [-erc]                      Specify tool flow type as ERC flow.           
      [-bwf waiver_setup_file]    Specifies the waiver setup file.              
      [-spice ext_file_name]      Output layout extracted netlist to specified  
                                  file.                                         
      [-rc_data | -no_rc_data]                                                  
                                  Generate or do not generate (DEFAULT) the data
                                  for running Quantus.                          
      [-output_complete_pathchk_results]                                        
                                  output complete results for pathchk/erc_pathchk rules
                                                                                
  d) Options that apply to LVS flow                                             
      [-lvs]                      Specify tool flow type as LVS flow.           
      [-spice ext_file_name]      Output layout extracted netlist to specified  
                                  file.                                         
      [-rc_data | -no_rc_data]                                                  
                                  Generate or do not generate (DEFAULT) the data
                                  for running Quantus.                          
      [-hcell hcell_file]         Specify the name and location of HCELL file.  
      [-genHierCells scriptFile]  Generate the hcells file using a hier cells   
                                  script.                                       
      [-genHierCells]             Generate the hcells file using the default    
                                  hier cells script                             
      [-alignGenHierCellsOutput]  Generate the hcells file in alignment format  
                                  for easy reading                              
      [-automatch]                Sets the automatch flag for the LVS engine    
      [-check_schematic]          Read the schematic early in the flow to see   
                                  if it has errors.                             
      [-keep_source_cells]        Generate the hcells file by the genHierCells  
                                  for the source only.                          
      [-source_top_cell cellName] Specify the source primary cell name for the  
                                  run.                                          
      [-source_cdl fileName]      Specify a source CDL file for the run.        
      [-source_verilog fileName]  Specify a source VERILOG file for the run.    
      [-layout_cdl fileName]      Specify a layout CDL file for the run.        
      [-layout_verilog fileName]  Specify a layout VERILOG file for the run.    
      [-layout_top_cell cellName] Specify layout primary cell name for the run. 
      [-out_special_text]         keep special characters in layout text labels.
      [-siggen ]                  Generate signature for device.  
      [-siggen_output fileName ]  Output device signature to the specified file.
      [-no_compare]               Do not run netlist comparison.                
      [-output_complete_pathchk_results]                                        
                                  output complete results for pathchk/erc_pathchk rules
                                                                                
  e) Options that apply to EXTRACTION flows                                     
      [-ext]                      Specify tool flow type as Extraction flow.    
      [-spice ext_file_name]      Output layout extracted netlist to specified  
                                  file.                                         
      [-rc_data | -no_rc_data]                                                  
                                  Generate or do not generate (DEFAULT) the data
                                  for running Quantus.                          
                                                                                
  f) Options that apply to Quantus flows                                        
      [-rule2qrc lvsfileName]     Generate a lvsfile for Quantus flow.          
                                                                                
  g) Options that apply to PERC flow                                            
      [-perc]                     Specifies tool flow type as specific ERC flow.
      [-perc_waiver_file  file]   Specifies the perc waiver setup file.         
      [-ecdb]                     Specifies the ecdb file to rerun PERC without regenerating ecdb data.
      [-ui_data | -no_ui_data]    Generate (or do not generate) data for PVS; -ui_data is required
                                  to perform topology-based check in case of layout input.
      [-automatch]                Causes a hierarchical checking of the design using automatically
                                  generated list cells.
      [-hcell fileName]           Causes a hierarchical checking of the design using user-defined
                                  list of cells.
      [-ui_data | -no_ui_data]    Generate or do not generate (DEFAULT) data for running point to
                                  point resistance check.
      [-lic_queue [<timeout>]]    Enables Quantus to queue for licenses with an optional timeout
                                  value in seconds in a point to point resistance check flow.
      [-source_cdl fileName]      Specify a source CDL file for the run.        
      [-source_verilog fileName]  Specify a source VERILOG file for the run.    
      [-source_top_cell cellName] Specify the source primary cell name for the run. 
      [-layout_cdl fileName]      Specify a layout CDL file for the run.        
      [-layout_verilog fileName]  Specify a layout VERILOG file for the run.    
      [-layout_top_cell cellName] Specify layout primary cell name for the run. 
      [-perc_use_lic_xl]          Use PERC_XL license instead of the PERC license. 
      [-output_complete_pathchk_results]                                        
                                  output complete results for pathchk/erc_pathchk rules
      [-in_mem]                   keep DB in memory for better performance for big output data. 
      [-percDP n]                 Run perc using n number of processors. 
                                                                                
  h) Options that apply to CV flow                                       
      [-cv]                       Specifies tool flow type as specific Constraint Validation flow.
      [-rsFile fileName]          Specify the run-specific file name for the run.
      [OPTIONS]                   Specify the list of options allowable in command line or in rsFile.
                                  Use either rsFile or list of options or both in command line. To get
                                  whole list of CV flow options use: pvs -cv [-h | -help].

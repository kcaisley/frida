# Command line interface (basic)

```
$ openroad -h
OpenROAD v2.0-24135-gb57dad1953 
Features included (+) or not (-): +GPU +GUI +Python
This program is licensed under the BSD-3 license. See the LICENSE file for details.
Components of this program may be licensed under more restrictive licenses which must be honored.
Usage: openroad [-help] [-version] [-no_init] [-no_splash] [-exit] [-gui] [-threads count|max] [-log file_name] [-metrics file_name] [-no_settings] [-minimize] cmd_file
  -help                 show help and exit
  -version              show version and exit
  -no_init              do not read .openroad init file
  -threads count|max    use count threads
  -no_splash            do not show the license splash at startup
  -exit                 exit after reading cmd_file
  -gui                  start in gui mode
  -minimize             start the gui minimized
  -no_settings          do not load the previous gui settings
  -python               start with python interpreter [limited to db operations]
  -log <file_name>      write a log in <file_name>
  -metrics <file_name>  write metrics in <file_name> in JSON format
  cmd_file              source cmd_file
```

# Interactive mode commands (all features)

```
openroad> help
add_global_connection [-net net_name] [-inst_pattern inst_name_pattern]
   [-pin_pattern pin_name_pattern] [(-power|-ground)] [-region region_name]
   [-defer_connection] 

add_label -position  {x y}
                                  [-anchor anchor]
                                  [-color color]
                                  [-size size]
                                  [-name name]
                                  text

add_pdn_connect [-grid grid_name] -layers list_of_2_layers
   [-cut_pitch pitch_value] [-fixed_vias list_of_vias]
   [-dont_use_vias list_of_vias] [-max_rows rows] [-max_columns columns]
   [-ongrid ongrid_layers] [-split_cuts split_cuts_mapping]
   [-split_cuts_staggered] 

add_pdn_ring [-grid grid_name] [-layers list_of_2_layer_names]
   [-widths (width_value|list_of_width_values)]
   [-spacings (spacing_value|list_of_spacing_values)]
   [-core_offsets (offset_value|list_of_offset_values)]
   [-pad_offsets (offset_value|list_of_offset_values)]
   [-connect_to_pad_layers layers] [-power_pads list_of_pwr_pads]
   [-ground_pads list_of_gnd_pads] [-nets list_of_nets]
   [-starts_with (POWER|GROUND)] [-add_connect] [-extend_to_boundary]
   [-connect_to_pads] [-allow_out_of_die] 
                                     
add_pdn_stripe [-grid grid_name] -layer layer_name [-width width_value]
   [-followpins] [-extend_to_core_ring] [-pitch pitch_value]
   [-spacing spacing_value] [-offset offset_value] [-starts_with (POWER|GROUND)]
   [-extend_to_boundary] [-snap_to_grid] [-number_of_straps count]
   [-nets list_of_nets] 

add_sroute_connect -net net -layers list_of_2_layers -cut_pitch
   list_of_2_pitch_values [-outerNet outerNet] [-fixed_vias list_of_vias]
   [-max_rows rows] [-max_columns columns] [-metalwidths metalwidths]
   [-metalspaces metalspaces] [-ongrid ongrid_layers] [-insts inst] 

add_to_physical_cluster
   [-modinst path | -inst inst_name | -physical_cluster cluster_name]
   cluster_name 

add_worker_address [-host host] [-port port] 

adjust_rc [-res_factor res] [-cc_factor cc] [-gndc_factor gndc] 

all_clocks 
all_inputs [-no_clocks] 
all_outputs 
all_registers [-clock clocks] [-rise_clock clocks] [-fall_clock clocks] [-cells]
   [-data_pins] [-clock_pins] [-async_pins] [-output_pins] [-level_sensitive]
   [-edge_triggered] 
analyze_power_grid -net net_name [-corner corner] [-error_file error_file]
   [-voltage_file voltage_file] [-enable_em] [-em_outfile em_file]
   [-vsrc voltage_source_file] [-source_type FULL|BUMPS|STRAPS] [-allow_reuse] 

assign_ground_net -domain domain_name -net snet_name 
assign_io_bump -net net [-terminal terminal] [-dont_route] inst 
assign_ndr -ndr name  (-net name | -all_clocks) 
assign_power_net -domain domain_name -net snet_name 
balance_row_usage 
bench_read_spef filename  
bench_verilog filename  
bench_wires [-met_cnt mcnt] [-cnt count] [-len wire_len] [-over] [-diag] [-all]
   [-db_only] [-v1] [-under_met layer] [-w_list width] [-s_list space]
   [-over_dist dist] [-under_dist dist] 

bench_wires_gen [  -len		length_in_min_widths ] [	 -met	  	metal	 ]
   [	 -mlist	  	metal_list	 ] [	 -width	  	multiplier_width_list	 ]
   [	 -spacing	  	multiplier_spacing_list	 ]
   [	 -couple_width	  	multiplier_coupling_width_list	 ]
   [	 -couple_spacing	  	multiplier_coupling_spacing_list ]
   [	 -over_width	  	multiplier_over_width_list	 ]
   [	 -over_spacing	  	multiplier_over_spacing_list	 ]
   [	 -under_width	  	multiplier_under_width_list	 ]
   [	 -under_spacing	  	multiplier_under_spacing_list	 ]
   [	 -over2_width	  	multiplier_over2_width_list	 ]
   [	 -over2_spacing	  	multiplier_over2_spacing_list	 ]
   [	 -under2_width	  	multiplier_under2_width_list	 ]
   [	 -under2_spacing	  	multiplier_under2_spacing_list	 ]
   [	 -dbg	  	dbg_flag	 ] [	 -wire_cnt	  	wire_count	 ]
   [	 -offset_over	  	offset_over	 ] [	 -offset_under	  	offset_under	 ]
   [	 -under_dist	  	max_dist_to_under_met	 ]
   [	 -over_dist	  	max_dist_to_over_met	 ] [  -diag ] [  -over ] [  -under ]
   [  -over_under ] 

buffer_ports [-inputs] [-outputs] [-max_utilization util]
   [-buffer_cell buf_cell] [-verbose] 
check_antennas [-verbose] [-report_violating_nets] [-report_file report_file]
   [-net net] 

check_axioms 
check_placement [-verbose] [-disallow_one_site_gaps]
   [-report_file_name file_name] 
check_power_grid -net power_net [-error_file error_file] [-floorplanning]
   [-dont_require_terminals] 

check_setup [-verbose] [-no_input_delay] [-no_output_delay] [-multiple_clock]
   [-no_clock] [-unconstrained_endpoints] [-loops] [-generated_clocks]
   [> filename] [>> filename]  
clear_global_connect 
clear_io_pin_constraints 
clock_tree_synthesis [-wire_unit unit] [-buf_list buflist] [-root_buf buf]
   [-clk_nets nets] [-tree_buf buf] [-distance_between_buffers]
   [-branching_point_buffers_distance] [-clustering_exponent]
   [-clustering_unbalance_ratio] [-sink_clustering_size]
   [-sink_clustering_max_diameter] [-macro_clustering_size]
   [-macro_clustering_max_diameter] [-sink_clustering_enable] [-balance_levels]
   [-sink_clustering_levels levels] [-num_static_layers]
   [-sink_clustering_buffer] [-obstruction_aware] [-no_obstruction_aware]
   [-apply_ndr strategy] [-sink_buffer_max_cap_derate] [-dont_use_dummy_load]
   [-delay_buffer_derate] [-library] [-repair_clock_nets] [-no_insertion_delay] 

cluster_flops [-tray_weight tray_weight] [-timing_weight timing_weight]
   [-max_split_size max_split_size] [-num_paths num_paths]  
configure_cts_characterization [-max_cap cap] [-max_slew slew]
   [-slew_steps slew_steps] [-cap_steps cap_steps]   
connect_by_abutment 
connect_pin net pin 
create_blockage [-region {x1 y1 x2 y2}] [-inst instance] [-max_density density]
   [-soft] 
create_child_physical_clusters [-top_module | -modinst path] 
create_clock [-name name] [-period period] [-waveform waveform] [-add]
   [-comment comment] [pins] 
create_generated_clock [-name clock_name] -source master_pin
   [-master_clock clock] [-divide_by divisor | -multiply_by multiplier]
   [-duty_cycle duty_cycle] [-invert] [-edges edge_list]
   [-edge_shift edge_shift_list] [-combinational] [-add] [-comment comment]
   port_pin_list 
create_logic_port [-direction direction] port_name  
create_menu_item [-name name] -text item_text -script tcl_script
   [-path menu_path] [-shortcut key_shortcut] [-echo] 

create_ndr -name name [-spacing val] [-width val] [-via val] 
create_physical_cluster cluster_name 
create_power_domain [-elements elements] name  
create_power_switch [-domain domain] [-output_supply_port output_supply_port]
   [-input_supply_port input_supply_port] [-control_port control_port]
   [-on_state on_state] name 

create_toolbar_button [-name name] -text button_text -script tcl_script [-echo] 

create_voltage_area [-name name] [-coordinate coordinates]
   [-guard_band_x guard_x] [-guard_band_y guard_y] cells  
create_voltage_domain domain_name -area  {llx lly urx ury}
current_design [design] 
current_instance [instance] 
cut_rows [-endcap_master endcap_master] [-halo_width_x halo_x]
   [-halo_width_y halo_y] [-row_min_width row_min_width] 

define_clock_layer_range layers  
define_corners corner1 [corner2] ... 
define_layer_range layers  
define_pdn_grid [-name <name>] [-macro] [-existing]
   [-grid_over_pg_pins|-grid_over_boundary]
   [-voltage_domains <list_of_voltage_domains>]
   [-orient <list_of_valid_orientations>] [-instances <list_of_instances>]
   [-cells <list_of_cell_names> ] [-default] [-halo <list_of_halo_values>]
   [-pins <list_of_pin_layers>] [-starts_with (POWER|GROUND)]
   [-obstructions <list_of_layers>] [-power_switch_cell <name>]
   [-power_control <signal_name>] [-power_control_network (STAR|DAISY)] 

define_pin_shape_pattern [-layer layer] [-x_step x_step] [-y_step y_step]
   [-region region] [-size size] [-pin_keepout dist] 
define_power_switch_cell -name  <name>  -control <control_pin>  [-acknowledge <acknowledge_pin>]  -power_switchable <power_switchable_pin>  -power <power_pin>  -ground <ground_pin> 
define_process_corner [-ext_model_index index] filename 

define_rcx_corners [-corner_list cornerList] 

delete_clock [-all] clocks 
delete_from_list list objs 
delete_generated_clock [-all] clocks 
delete_instance inst 
delete_net net 
delete_physical_cluster cluster_name 
delete_voltage_domain domain_name 
density_fill [-rules rules_file] [-area {lx ly ux uy}] 
design_is_routed [-verbose]  
detailed_placement [-max_displacement disp|{disp_x disp_y}]
   [-disallow_one_site_gaps] [-report_file_name file_name] 
detailed_route [-output_maze filename] [-output_drc filename]
   [-output_cmap filename] [-output_guide_coverage filename]
   [-drc_report_iter_step step] [-db_process_node name] [-disable_via_gen]
   [-droute_end_iter iter] [-via_in_pin_bottom_layer layer]
   [-via_in_pin_top_layer layer] [-via_access_layer layer] [-or_seed seed]
   [-or_k k] [-bottom_routing_layer layer] [-top_routing_layer layer]
   [-verbose level] [-distributed] [-remote_host rhost] [-remote_port rport]
   [-shared_volume vol] [-cloud_size sz] [-clean_patches] [-no_pin_access]
   [-min_access_points count] [-save_guide_updates] [-repair_pdn_vias layer]
   [-single_step_dr] 

detailed_route_debug [-pa] [-ta] [-dr] [-maze] [-net name] [-pin name]
   [-box x1 y1 x2 y2] [-dump_last_worker] [-iter iter] [-pa_markers] [-dump_dr]
   [-dump_dir dir] [-snapshot_dir dir] [-pa_edge] [-pa_commit]
   [-write_net_tracks] 

detailed_route_run_worker [-dump_dir dir] [-worker_dir dir] [-drc_rpt drc] 

detailed_route_worker_debug [-maze_end_iter iter] [-drc_cost d_cost]
   [-marker_cost m_cost] [-fixed_shape_cost f_cost] [-marker_decay m_decay]
   [-ripup_mode mode] [-follow_guide f_guide] 

diff_spef [-file filename] [-spef_corner spef_num] [-ext_corner ext_num]
   [-r_res] [-r_cap] [-r_cc_cap] [-r_conn] 

disconnect_pin net -all|pin 
display_timing_cone pin [-fanin] [-fanout] [-off] 

draw_route_guides net_names [-show_segments] [-show_pin_locations]  
elapsed_run_time 
eliminate_dead_logic 
estimate_parasitics -placement|-global_routing [-spef_file filename] 
evaluate_hypergraph_solution -num_parts num_parts -balance_constraint
   balance_constraint -hypergraph_file hypergraph_file -solution_file
   solution_file [-base_balance base_balance] [-scale_factor scale_factor]
   [-vertex_dimension vertex_dimension]
   [-hyperedge_dimension hyperedge_dimension] [-fixed_file fixed_file]
   [-group_file group_file] [-e_wt_factors e_wt_factors]
   [-v_wt_factors v_wt_factors]   
evaluate_part_design_solution [-num_parts num_parts]
   [-balance_constraint balance_constraint] [-base_balance base_balance]
   [-scale_factor scale_factor] [-timing_aware_flag timing_aware_flag]
   [-top_n top_n] [-fence_flag fence_flag] [-fence_lx fence_lx]
   [-fence_ly fence_ly] [-fence_ux fence_ux] [-fence_uy fence_uy]
   [-fixed_file fixed_file] [-community_file community_file]
   [-group_file group_file] [-hypergraph_file hypergraph_file]
   [-hypergraph_int_weight_file hypergraph_int_weight_file]
   [-solution_file solution_file] [-net_timing_factor net_timing_factor]
   [-path_timing_factor path_timing_factor]
   [-path_snaking_factor path_snaking_factor]
   [-timing_exp_factor timing_exp_factor] [-extra_delay extra_delay]
   [-guardband_flag guardband_flag] [-e_wt_factors e_wt_factors]
   [-v_wt_factors v_wt_factors]  
example_instance [-name name] 
exclude_io_pin_region -region region  
execute_dft_plan 
extract_parasitics [-ext_model_file filename] [-corner cornerIndex]
   [-corner_cnt count] [-max_res ohms] [-coupling_threshold fF]
   [-debug_net_id id] [-dbg dbg_num ] [-lef_res] [-lef_rc] [-cc_model track]
   [-context_depth depth] [-no_merge_via_res] [-skip_over_cell ] [-version] 

filler_placement [-prefix prefix] [-verbose] filler_masters  
find_timing_paths [-from from_list|-rise_from from_list|-fall_from from_list]
   [-through through_list|-rise_through through_list|-fall_through through_list]
   [-to to_list|-rise_to to_list|-fall_to to_list]
   [-path_delay min|min_rise|min_fall|max|max_rise|max_fall|min_max]
   [-unconstrained] [-corner corner] [-group_path_count path_count]
   [-endpoint_path_count path_count] [-unique_paths_to_endpoint]
   [-slack_max slack_max] [-slack_min slack_min] [-sort_by_slack]
   [-path_group group_name] 
focus_net net [-remove] [-clear] 

gen_rcx_model [-spef_file_list spefList] [-corner_list cornerList]
   [-out_file outfilename] [-comment comment] [-version version]
   [-pattern pattern] 

gen_solver_patterns [-process_file process_file] [-process_name process_name]
   [-version version] [-wire_cnt wire_count] [-len wire_len] [-w_list widths]
   [-s_list spacings] [-over_dist dist] [-under_dist dist] 

get_cells [-hierarchical] [-hsc separator] [-filter expr] [-regexp] [-nocase]
   [-quiet] [-of_objects objects] [patterns] 
get_clocks [-regexp] [-nocase] [-quiet] [-filter expr] [patterns] 
get_fanin -to sink_list [-flat] [-only_cells] [-startpoints_only]
   [-levels level_count] [-pin_levels pin_count]
   [-trace_arcs timing|enabled|all] 
get_fanout -from source_list [-flat] [-only_cells] [-endpoints_only]
   [-levels level_count] [-pin_levels pin_count]
   [-trace_arcs timing|enabled|all] 
get_full_name object 
get_hier_module design_name 
get_lib_cells [-hsc separator] [-regexp] [-nocase] [-quiet] [-filter expr]
   [-of_objects objects] [patterns] 
get_lib_pins [-hsc separator] [-regexp] [-nocase] [-quiet] [-filter expr]
   [-of_objects objects] [patterns] 
get_libs [-regexp] [-nocase] [-quiet] [-filter expr] [patterns] 
get_model_corners [-ext_model_file file_name] 

get_name object 
get_nets [-hierarchical] [-hsc separator] [-regexp] [-nocase] [-quiet]
   [-filter expr] [-of_objects objects] [patterns] 
get_pins [-hierarchical] [-hsc separator] [-quiet] [-filter expr] [-regexp]
   [-nocase] [-of_objects objects] [patterns] 
get_ports [-quiet] [-filter expr] [-regexp] [-nocase] [-of_objects objects]
   [patterns] 
get_property
   [-object_type library|liberty_library|cell|liberty_cell|instance|pin|net|port|clock|timing_arc]
   object property 
get_timing_edges [-from from_pin] [-to to_pin] [-of_objects objects]
   [-filter expr] 
global_connect 
global_placement [-skip_initial_place] [-skip_nesterov_place] [-timing_driven]
   [-routability_driven] [-disable_timing_driven] [-disable_routability_driven]
   [-incremental] [-skip_io] [-bin_grid_count grid_count]
   [-density target_density] [-init_density_penalty init_density_penalty]
   [-init_wirelength_coef init_wirelength_coef] [-min_phi_coef min_phi_coef]
   [-max_phi_coef max_phi_coef] [-reference_hpwl reference_hpwl]
   [-overflow overflow] [-initial_place_max_iter initial_place_max_iter]
   [-initial_place_max_fanout initial_place_max_fanout] [-routability_use_grt]
   [-routability_target_rc_metric routability_target_rc_metric]
   [-routability_check_overflow routability_check_overflow]
   [-routability_max_density routability_max_density]
   [-routability_max_inflation_iter routability_max_inflation_iter]
   [-routability_inflation_ratio_coef routability_inflation_ratio_coef]
   [-routability_max_inflation_ratio routability_max_inflation_ratio]
   [-routability_rc_coefficients routability_rc_coefficients]
   [-keep_resize_below_overflow keep_resize_below_overflow]
   [-timing_driven_net_reweight_overflow timing_driven_net_reweight_overflow]
   [-timing_driven_net_weight_max timing_driven_net_weight_max]
   [-timing_driven_nets_percentage timing_driven_nets_percentage]
   [-pad_left pad_left] [-pad_right pad_right] [-disable_revert_if_diverge]
   [-enable_routing_congestion] 

global_route [-guide_file out_file] [-congestion_iterations iterations]
   [-congestion_report_file file_name] [-congestion_report_iter_step steps]
   [-grid_origin origin] [-critical_nets_percentage percent] [-allow_congestion]
   [-verbose] [-start_incremental] [-end_incremental] [-use_cugr] 

global_route_debug [-st]        # Show the Steiner Tree generated by stt
  [-rst]      # Show the Rectilinear Steiner Tree generated by FastRoute
  [-tree2D]   # Show the Rectilinear Steiner Tree generated by FastRoute after overflow iterations
  [-tree3D]   # Show The Rectilinear Steiner Tree 3D after layer assignment
  [-saveSttInput file_name] # Save the stt input for a net on file_name
  [-net name]

group_path -name group_name [-weight weight] [-critical_range range] [-default]
   [-comment comment] [-from from_list] [-rise_from from_list]
   [-fall_from from_list] [-through through_list] [-rise_through through_list]
   [-fall_through through_list] [-to to_list] [-rise_to to_list]
   [-fall_to to_list] 
help [pattern] 
improve_placement [-random_seed seed] [-max_displacement disp|{disp_x disp_y}]
   [-disallow_one_site_gaps]  
include [-e|-echo] [-v|-verbose] filename [> filename] [>> filename] 
init_rcx_model [-corner_names name_list] [-met_cnt met_cnt] 

initialize_floorplan [-utilization util] [-aspect_ratio ratio]
   [-core_space space | {bottom top left right}]
   [-die_area {lx ly ux uy | x1 y1 x2 y2 ...}]
   [-core_area {lx ly ux uy | x1 y1 x2 y2 ...}] [-additional_sites site_names]
   [-site site_name] [-row_parity NONE|ODD|EVEN] [-flip_sites site_names] 
insert_decap -target_cap target_cap -cells cell_info [-net net_name]  
insert_tiecells tie_pin [-prefix prefix] 

link_design [-hier] [-omit_filename_prop] top_cell_name 
log_begin filename  
log_end 
make_fake_io_site -name name -width width -height height 
make_instance inst_path lib_cell 
make_io_bump_array -bump master -origin  {x y}  -rows rows  -columns columns  -pitch {x y}  [-prefix prefix]
make_io_sites -horizontal_site site -vertical_site site -corner_site site
   -offset offset [-rotation_horizontal rotation] [-rotation_vertical rotation]
   [-rotation_corner rotation] [-ring_index index] 

make_net net_path 
make_port port_name direction 
make_rows 
					       [-core_space space | {bottom top left right}] [-core_area {lx ly ux uy}] [-additional_sites site_names] [-site site_name] [-row_parity NONE|ODD|EVEN] [-flip_sites site_names]
make_tracks [layer] [-x_pitch x_pitch] [-y_pitch y_pitch] [-x_offset x_offset]
   [-y_offset y_offset] 
man name [-manpath manpath] [-no_pager] 
map_power_switch [-switch_name_list switch_name_list] [-lib_cells lib_cells]
   [-port_map port_map] 

optimize_mirroring 
pdngen [-skip_trim] [-dont_add_pins] [-reset] [-ripup] [-report_only]
   [-check_only] [-failed_via_report file] [-verbose] 

pin_access [-db_process_node name] [-bottom_routing_layer layer]
   [-top_routing_layer layer] [-via_access_layer layer]
   [-via_in_pin_bottom_layer layer] [-via_in_pin_top_layer layer]
   [-min_access_points count] [-verbose level] [-distributed]
   [-remote_host rhost] [-remote_port rport] [-shared_volume vol]
   [-cloud_size sz] 

place_bondpad -bond master [-offset {x y}] [-rotation rotation] ioinsts 
place_corners [-ring_index index] master 
place_endcaps 
  # Simplified
  [-corner master] [-edge_corner master] 
  [-endcap masters]  
  [-endcap_horizontal masters]  [-endcap_vertical master]  
  [-prefix prefix]

  # Full options
  [-left_top_corner master] [-right_top_corner master] [-left_bottom_corner master] [-right_bottom_corner master] 
  [-left_top_edge master] [-right_top_edge master] [-left_bottom_edge master] [-right_bottom_edge master] 
  [-left_edge master]  [-right_edge master]  
  [-top_edge masters]  [-bottom_edge masters]

place_inst -name inst_name   (-origin xy_origin | -location xy_location)  [-orientation orientation]  [-cell library_cell]  [-status status]
place_io_fill -row row_name [-permit_overlaps masters] masters 
place_io_terminals inst_terms [-allow_non_top_layer] 
place_macro -macro_name macro_name -location location [-orientation orientation]
   [-exact] [-allow_overlap] 

place_pad [-master master] -row row_name -location x_or_y_offset -mirror name 
place_pads -row row_name pads 
place_pin [-pin_name pin_name] [-layer layer] [-location location]
   [-pin_size pin_size] [-force_to_die_boundary] [-placed_status] 

place_pins [-hor_layers h_layers] [-ver_layers v_layers] [-random_seed seed]
   [-random] [-corner_avoidance distance] [-min_distance min_dist]
   [-min_distance_in_tracks] [-exclude region] [-group_pins pin_list]
   [-annealing] [-write_pin_placement file_name] 

place_tapcells -master tapcell_master -distance dist 

placement_cluster 
rdl_route -layer layer [-bump_via access_via] [-pad_via access_via]
   [-width width] [-spacing spacing] [-turn_penalty penalty] [-allow45]
   [-max_iterations iterations] nets 
read_db [-hier] filename 
read_def [-floorplan_initialize|-incremental|-child] [-continue_on_errors]
   [-tech name] filename 
read_global_route_segments file_name  
read_guides file_name  
read_lef [-tech] [-library] [-tech_name name] filename 
read_liberty [-corner corner] [-min] [-max] [-infer_latches] filename 
read_partitioning -read_file name [-instance_map_file file_path]  
read_power_activities [-scope scope] -vcd filename  
read_rcx_tables [-corner_name corner_name] [-file in_file_name]
   [-wire_index wire] [-over] [-under] [-over_under] [-diag] 

read_saif [-scope scope] filename  
read_sdc [-echo] filename 
read_sdf [-path path] [-corner corner] [-cond_use min|max|min_max]
   [-unescaped_dividers] filename 
read_spef [-corner corner] [-min] [-max] [-path path] [-pin_cap_included]
   [-keep_capacitive_coupling] [-coupling_reduction_factor factor] [-reduce]
   [-delete_after_reduce] filename 
read_upf [-file file]  
read_vcd [-scope scope] filename  
read_verilog filename 
remove_buffers instances  
remove_fillers 
remove_from_physical_cluster
   [-parent_module module_name -modinst modinst_name | -inst inst_name | -physical_cluster cluster_name]
   cluster_name 

remove_io_bump inst 
remove_io_bump_array -bump master 
remove_io_rows 
repair_antennas diode_cell [-iterations iterations] [-ratio_margin ratio_margin] 
repair_clock_inverters 
repair_clock_nets [-max_wire_length max_wire_length] 
repair_design [-max_wire_length max_wire_length] [-max_utilization util]
   [-slew_margin slack_margin] [-cap_margin cap_margin] [-buffer_gain gain]
   [-pre_placement] [-match_cell_footprint] [-verbose] 
repair_pdn_vias [-net net_name] -all 

repair_tie_fanout lib_port [-separation dist] [-max_fanout fanout] [-verbose] 
repair_timing [-setup] [-hold] [-recover_power percent_of_paths_with_slack]
   [-setup_margin setup_margin] [-hold_margin hold_margin]
   [-slack_margin slack_margin] [-libraries libs] [-allow_setup_violations]
   [-sequence move_string] [-skip_pin_swap] [-skip_gate_cloning]
   [-skip_size_down] [-skip_buffering] [-skip_buffer_removal] [-skip_last_gasp]
   [-skip_vt_swap] [-repair_tns tns_end_percent] [-max_passes passes]
   [-max_buffer_percent buffer_percent] [-max_utilization util]
   [-match_cell_footprint] [-max_repairs_per_pass max_repairs_per_pass]
   [-verbose] 
replace_arith_modules [-path_count num_critical_paths] [-slack_threshold float]
   [-target opto_goal]  
replace_cell instance lib_cell 
replace_hier_module instance module 
report_activity_annotation [-report_unannotated] [-report_annotated]  
report_annotated_check [-setup] [-hold] [-recovery] [-removal] [-nochange]
   [-width] [-period] [-max_skew] [-max_lines lines] [-report_annotated]
   [-report_unannotated] [-constant_arcs] 
report_annotated_delay [-cell] [-net] [-from_in_ports] [-to_out_ports]
   [-max_lines lines] [-report_annotated] [-report_unannotated] [-constant_arcs] 
report_arrival pin 
report_buffers [-filtered]  
report_cell_usage [-verbose] [module_inst] [-file file] [-stage stage] 
report_check_types [-violators] [-verbose] [-corner corner]
   [-format slack_only|end] [-max_delay] [-min_delay] [-recovery] [-removal]
   [-clock_gating_setup] [-clock_gating_hold] [-max_slew] [-min_slew]
   [-max_fanout] [-min_fanout] [-max_capacitance] [-min_capacitance]
   [-min_pulse_width] [-min_period] [-max_skew] [-net net] [-digits digits]
   [-no_line_splits] [> filename] [>> filename] 
report_checks [-from from_list|-rise_from from_list|-fall_from from_list]
   [-through through_list|-rise_through through_list|-fall_through through_list]
   [-to to_list|-rise_to to_list|-fall_to to_list] [-unconstrained]
   [-path_delay min|min_rise|min_fall|max|max_rise|max_fall|min_max]
   [-corner corner] [-group_path_count path_count]
   [-endpoint_path_count path_count] [-unique_paths_to_endpoint]
   [-slack_max slack_max] [-slack_min slack_min] [-sort_by_slack]
   [-path_group group_name]
   [-format full|full_clock|full_clock_expanded|short|end|slack_only|summary|json]
   [-fields capacitance|slew|input_pin|net|src_attr] [-digits digits]
   [-no_line_splits] [> filename] [>> filename] 
report_clock_latency [-clock clocks] [-corner corner]
   [-include_internal_latency] [-digits digits] 
report_clock_min_period [-clocks clocks] [-include_port_paths]  
report_clock_properties [clocks] 
report_clock_skew [-setup|-hold] [-clock clocks] [-corner corner]
   [-include_internal_latency] [-digits digits] 
report_clock_skew_metric [-setup] | [-hold] 
report_constant pin|instance|net 
report_cts [-out_file file]   
report_dcalc [-from from_pin] [-to to_pin] [-corner corner] [-min] [-max]
   [-digits digits] 
report_design_area 
report_design_area_metrics 
report_dft_config  
report_dft_plan [-verbose] 
report_disabled_edges 
report_dont_touch 
report_dont_use 
report_edges [-from from_pin] [-to to_pin] 
report_equiv_cells -match_cell_footprint -all -vt  
report_erc_metrics 
report_floating_nets [-verbose] [> filename] [>> filename] 
report_fmax_metric 
report_global_connect 
report_group group 
report_instance [-connections] [-verbose] instance_path [> filename]
   [>> filename] 
report_layer_rc [-corner corner] 
report_lib_cell cell_name [> filename] [>> filename] 
report_logic_depth_histogram [-num_bins num_bins] [-exclude_buffers]
   [-exclude_inverters] 
report_long_wires count [> filename] [>> filename] 
report_net [-corner corner] [-digits digits] net_path [> filename] [>> filename] 
report_object_full_names objects 
report_object_names objects 
report_opt_config 
report_overdriven_nets [-include_parallel_driven] [-verbose] [> filename]
   [>> filename] 
report_parasitic_annotation [-report_unannotated] 
report_path [-min|-max]
   [-format full|full_clock|full_clock_expanded|short|end|summary]
   [-fields capacitance|slew|input_pin|net|src_attr] [-digits digits]
   [-no_line_splits] [> filename] [>> filename] pin  ^|r|rise|v|f|fall
report_physical_clusters 
report_power [-instances instances] [-highest_power_instances count]
   [-corner corner] [-digits digits] [> filename] [>> filename]  
report_power_metric [-corner corner_name] 
report_pulse_width_checks [-verbose] [-corner corner] [-digits digits]
   [-no_line_splits] [pins] [> filename] [>> filename] 
report_required pin 
report_slack pin 
report_slews [-corner corner] pin 
report_timing_histogram [-num_bins num_bins] [-setup|-hold] 
report_tns [-min] [-max] [-digits digits] 
report_tns_metric [-setup] | [-hold] 
report_units 
report_units_metric 
report_voltage_domains 
report_wire_length [-net net_list] [-file file] [-global_route]
   [-detailed_route] [-verbose] 

report_wns [-min] [-max] [-digits digits] 
report_worst_negative_slack_metric [-setup] | [-hold] 
report_worst_slack [-min] [-max] [-digits digits] 
report_worst_slack_metric [-setup] | [-hold] 
reset_dont_use 
reset_opt_config [-limit_sizing_area] [-limit_sizing_leakage]
   [-keep_sizing_site] [-keep_sizing_vt] [-sizing_area_limit]
   [-sizing_leakage_limit] [-set_early_sizing_cap_ratio]
   [-set_early_buffer_sizing_cap_ratio] [-disable_buffer_pruning]  
restructure [-slack_threshold slack] [-depth_threshold depth]
   [-target area|timing] [-abc_logfile logfile] [-liberty_file liberty_file]
   [-tielo_port tielow_port] [-tiehi_port tiehigh_port] [-work_dir workdir_name] 
                                    
resynth [-corner corner] 
rtl_macro_placer -max_num_macro max_num_macro -min_num_macro min_num_macro
   -max_num_inst max_num_inst -min_num_inst min_num_inst -tolerance tolerance
   -max_num_level max_num_level -coarsening_ratio coarsening_ratio
   -large_net_threshold large_net_threshold -signature_net_threshold
   signature_net_threshold -halo_width halo_width -halo_height halo_height
   -fence_lx fence_lx -fence_ly fence_ly -fence_ux fence_ux -fence_uy fence_uy
   -area_weight area_weight -outline_weight outline_weight -wirelength_weight
   wirelength_weight -guidance_weight guidance_weight -fence_weight fence_weight
   -boundary_weight boundary_weight -notch_weight notch_weight
   -macro_blockage_weight macro_blockage_weight -pin_access_th pin_access_th
   -target_util target_util -target_dead_space target_dead_space -min_ar min_ar
   -report_directory report_directory -write_macro_placement file_name   
run_load_balancer [-host host] [-port port] [-workers_domain workers_domain] 

run_worker [-host host] [-port port] [-i] 

save_animated_gif -start|-add|-end [-area {x0 y0 x1 y1}] [-width width]
   [-resolution microns_per_pixel] [-delay delay] [path] 

save_clocktree_image [-width width] [-height height] [-corner corner] -clock
   clock path 

save_histogram_image [-width width] [-height height] [-mode mode] path 

save_image [-area {x0 y0 x1 y1}] [-width width] [-resolution microns_per_pixel]
   [-display_option option] path 

scan_opt  
scan_replace  
select -type object_type [-name name_regex] [-case_insensitive]
   [-highlight group] [-filter attribute_and_value] 

set_assigned_check -setup|-hold|-recovery|-removal [-rise] [-fall]
   [-corner corner] [-min] [-max] [-from from_pins] [-to to_pins]
   [-clock rise|fall] [-cond sdf_cond] check_value 
set_assigned_delay -cell|-net [-rise] [-fall] [-corner corner] [-min] [-max]
   [-from from_pins] [-to to_pins] delay 
set_assigned_transition [-rise] [-fall] [-corner corner] [-min] [-max] slew pins 
set_case_analysis 0|1|zero|one|rise|rising|fall|falling pins 
set_clock_gating_check [-setup setup_time] [-hold hold_time] [-rise] [-fall]
   [-low] [-high] [objects] 
set_clock_groups [-name name] [-logically_exclusive] [-physically_exclusive]
   [-asynchronous] [-allow_paths] [-comment comment] -group clocks 
set_clock_latency [-source] [-clock clock] [-rise] [-fall] [-min] [-max]
   [-early] [-late] delay objects 
set_clock_sense [-positive] [-negative] [-pulse pulse_type] [-stop_propagation]
   [-clock clocks] pins 
set_clock_transition [-rise] [-fall] [-min] [-max] transition clocks 
set_clock_uncertainty [-from|-rise_from|-fall_from from_clock]
   [-to|-rise_to|-fall_to to_clock] [-rise] [-fall] [-setup] [-hold] uncertainty
   [objects] 
set_cmd_units [-capacitance cap_unit] [-resistance res_unit] [-time time_unit]
   [-voltage voltage_unit] [-current current_unit] [-power power_unit]
   [-distance distance_unit] 
set_data_check [-from from_pin] [-rise_from from_pin] [-fall_from from_pin]
   [-to to_pin] [-rise_to to_pin] [-fall_to to_pin] [-setup | -hold]
   [-clock clock] margin 
set_debug_level tool group level  
set_dft_config [-max_length max_length] [-max_chains max_chains]
   [-clock_mixing clock_mixing]
   [-scan_enable_name_pattern scan_enable_name_pattern]
   [-scan_in_name_pattern scan_in_name_pattern]
   [-scan_out_name_pattern scan_out_name_pattern] 
                                        
set_disable_inferred_clock_gating objects  
set_disable_timing [-from from_port] [-to to_port] objects 
set_domain_area domain_name -area  {llx lly urx ury}
set_domain_voltage [-domain domain] [-voltage voltage] 

set_dont_touch nets_instances 
set_dont_use lib_cells 
set_drive [-rise] [-fall] [-min] [-max] resistance ports 
set_driving_cell [-lib_cell cell] [-library library] [-rise] [-fall] [-min]
   [-max] [-pin pin] [-from_pin from_pin] [-input_transition_rise trans_rise]
   [-input_transition_fall trans_fall] [-multiply_by factor] [-dont_scale]
   [-no_design_rule] ports 
set_false_path [-setup] [-hold] [-rise] [-fall] [-reset_path] [-comment comment]
   [-from from_list] [-rise_from from_list] [-fall_from from_list]
   [-through through_list] [-rise_through through_list]
   [-fall_through through_list] [-to to_list] [-rise_to to_list]
   [-fall_to to_list] 
set_fanout_load fanout ports 
set_global_routing_layer_adjustment layer adj  
set_global_routing_random [-seed seed]
   [-capacities_perturbation_percentage percent] [-perturbation_amount value] 
                                                 
set_global_routing_region_adjustment region [-layer layer]
   [-adjustment adjustment]   
set_hierarchy_separator seperator  
set_ideal_latency [-rise] [-fall] [-min] [-max] delay objects 
set_ideal_net nets  
set_ideal_network [-no_propagation] objects 
set_ideal_transition [-rise] [-fall] [-min] [-max] transition_time objects 
set_input_delay [-rise] [-fall] [-max] [-min] [-clock clock] [-clock_fall]
   [-reference_pin ref_pin] [-source_latency_included]
   [-network_latency_included] [-add_delay] delay port_pin_list 
set_input_transition [-rise] [-fall] [-min] [-max] transition ports 
set_io_pin_constraint [-direction direction] [-pin_names names] [-region region]
   [-mirrored_pins pins] [-group] [-order] 
set_isolation [-domain domain] [-applies_to applies_to]
   [-clamp_value clamp_value] [-isolation_signal isolation_signal]
   [-isolation_sense isolation_sense] [-location location] [-update] name 

set_layer_rc [-layer layer] [-via via_layer] [-capacitance cap]
   [-resistance res] [-corner corner] 
set_level_shifter [-domain domain] [-elements elements]
   [-exclude_elements exclude_elements] [-source source] [-sink sink]
   [-use_functional_equivalence use_functional_equivalence]
   [-applies_to applies_to] [-applies_to_boundary applies_to_boundary]
   [-rule rule] [-threshold threshold] [-no_shift] [-force_shift]
   [-location location] [-input_supply input_supply]
   [-output_supply output_supply] [-internal_supply internal_supply]
   [-name_prefix name_prefix] [-name_suffix name_suffix] [-instance instance]
   [-update] [-use_equivalence use_equivalence] name 

set_level_shifter_cell [-level_shifter level_shifter] [-cell_name cell_name]
   [-input_port input_port] [-output_port output_port] 

set_level_shifter_strategy [-rule rule_type] 
set_level_shifter_threshold [-voltage volt] 
set_load [-corner corner] [-rise] [-fall] [-max] [-min] [-subtract_pin_load]
   [-pin_load] [-wire_load] capacitance objects 
set_logic_dc port_list 
set_logic_one port_list 
set_logic_zero port_list 
set_macro_extension extension  
set_macro_guidance_region -macro_name macro_name -region region  
set_max_area area 
set_max_capacitance cap objects 
set_max_delay [-rise] [-fall] [-ignore_clock_latency] [-reset_path] [-probe]
   [-comment comment] [-from from_list] [-rise_from from_list]
   [-fall_from from_list] [-through through_list] [-rise_through through_list]
   [-fall_through through_list] [-to to_list] [-rise_to to_list]
   [-fall_to to_list] delay 
set_max_dynamic_power power [unit] 
set_max_fanout fanout objects 
set_max_layer maxLayer  
set_max_leakage_power power [unit] 
set_max_time_borrow limit objects 
set_max_transition [-clock_path] [-data_path] [-rise] [-fall] slew objects 
set_min_capacitance cap objects 
set_min_delay [-rise] [-fall] [-ignore_clock_latency] [-reset_path] [-probe]
   [-comment comment] [-from from_list] [-rise_from from_list]
   [-fall_from from_list] [-through through_list] [-rise_through through_list]
   [-fall_through through_list] [-to to_list] [-rise_to to_list]
   [-fall_to to_list] delay 
set_min_layer minLayer  
set_min_pulse_width [-low] [-high] value [objects] 
set_multicycle_path [-setup] [-hold] [-rise] [-fall] [-start] [-end]
   [-reset_path] [-comment comment] [-from from_list] [-rise_from from_list]
   [-fall_from from_list] [-through through_list] [-rise_through through_list]
   [-fall_through through_list] [-to to_list] [-rise_to to_list]
   [-fall_to to_list] path_multiplier 
set_ndr_layer_rule tech ndr layerName input isSpacing 
set_ndr_rules tech ndr values isSpacing 
set_nets_to_route net_names  
set_operating_conditions [-analysis_type single|bc_wc|on_chip_variation]
   [-library lib] [condition] [-min min_condition] [-max max_condition]
   [-min_library min_lib] [-max_library max_lib] 
set_opt_config [-limit_sizing_area] [-limit_sizing_leakage] [-keep_sizing_site]
   [-keep_sizing_vt] [-sizing_area_limit] [-sizing_leakage_limit]
   [-set_early_sizing_cap_ratio] [-set_early_buffer_sizing_cap_ratio]
   [-disable_buffer_pruning]  
set_output_delay [-rise] [-fall] [-max] [-min] [-clock clock] [-clock_fall]
   [-reference_pin ref_pin] [-source_latency_included]
   [-network_latency_included] [-add_delay] delay port_pin_list 
set_pdnsim_inst_power -inst instance -power power [-corner corner] 
set_pdnsim_net_voltage -net net_name -voltage volt [-corner corner] 
set_pdnsim_source_settings [-bump_dx pitch] [-bump_dy pitch] [-bump_size size]
   [-bump_interval interval] [-strap_track_pitch pitch] 
set_pin_length [-hor_length h_length] [-ver_length v_length] 

set_pin_length_extension [-hor_extension h_ext] [-ver_extension v_ext] 

set_pin_thick_multiplier [-hor_multiplier h_mult] [-ver_multiplier v_mult] 

set_placement_padding -global|-masters masters|-instances insts
   [-right site_count] [-left site_count] [instances]  
set_pocv_sigma_factor factor  
set_port_fanout_number [-corner corner] [-max] [-min] fanout ports 
set_power_activity [-global] [-input] [-input_ports ports] [-pins pins]
   [-activity activity | -density density] [-duty duty] [-clock clock] 
set_propagated_clock objects 
set_pvt insts [-min] [-max] [-process process] [-voltage voltage]
   [-temperature temperature] 
set_resistance [-min] [-max] resistance nets 
set_routing_alpha alpha [-net net_name] [-min_fanout fanout] [-min_hpwl hpwl]
   [-clock_nets] 

set_routing_layers [-signal min-max] [-clock min-max]   
set_sense [-type clock|data] [-positive] [-negative] [-pulse pulse_type]
   [-stop_propagation] [-clocks clocks] pins 
set_simulated_annealing [-temperature temperature] [-max_iterations iters]
   [-perturb_per_iter perturbs] [-alpha alpha] 

set_timing_derate -early|-late [-rise] [-fall] [-clock] [-data] [-net_delay]
   [-cell_delay] [-cell_check] derate [objects] 
set_units [-time time_unit] [-capacitance cap_unit] [-resistance res_unit]
   [-voltage voltage_unit] [-current current_unit] [-power power_unit]
   [-distance distance_unit] 
set_voltage [-min min_case_value] [-object_list power_nets] max_case_voltage 
set_voltage_domain -name domain_name -power power_net_name -ground
   ground_net_name [-region region_name]
   [-secondary_power secondary_power_net_name]
   [-switched_power switched_power_net_name] 
set_wire_load_min_block_size block_size 
set_wire_load_mode top|enclosed|segmented 
set_wire_load_model -name model_name [-library lib_name] [-min] [-max] [objects] 
set_wire_load_selection_group [-library lib] [-min] [-max] group_name [objects] 
set_wire_rc [-clock] [-signal] [-data] [-layers layers] [-layer layer]
   [-h_resistance h_res] [-h_capacitance h_cap] [-v_resistance v_res]
   [-v_capacitance v_cap] [-resistance res] [-capacitance cap] [-corner corner] 
show_copying 
show_splash 
show_warranty 
simulated_annealing_debug [-iters_between_paintings iters]
   [-no_pause_mode no_pause_mode] 

suppress_message tool id  
suppress_msg msg_ids 
tapcell [-tapcell_master tapcell_master] [-tap_prefix tap_prefix]
   [-endcap_master endcap_master] [-endcap_prefix endcap_prefix]
   [-distance dist] [-disallow_one_site_gaps] [-halo_width_x halo_x]
   [-halo_width_y halo_y] [-row_min_width row_min_width]
   [-tap_nwin2_master tap_nwin2_master] [-tap_nwin3_master tap_nwin3_master]
   [-tap_nwout2_master tap_nwout2_master] [-tap_nwout3_master tap_nwout3_master]
   [-tap_nwintie_master tap_nwintie_master]
   [-tap_nwouttie_master tap_nwouttie_master]
   [-cnrcap_nwin_master cnrcap_nwin_master]
   [-cnrcap_nwout_master cnrcap_nwout_master]
   [-incnrcap_nwin_master incnrcap_nwin_master]
   [-incnrcap_nwout_master incnrcap_nwout_master] [-tbtie_cpp tbtie_cpp]
   [-endcap_cpp endcap_cpp] [-no_cell_at_top_bottom]  
tapcell_ripup [-tap_prefix tap_prefix] [-endcap_prefix endcap_prefix] 

tee -file filename -variable name [-append] [-quiet] command 
triton_part_design [-num_parts num_parts]
   [-balance_constraint balance_constraint] [-base_balance base_balance]
   [-scale_factor scale_factor] [-seed seed]
   [-timing_aware_flag timing_aware_flag] [-top_n top_n]
   [-placement_flag placement_flag] [-fence_flag fence_flag]
   [-fence_lx fence_lx] [-fence_ly fence_ly] [-fence_ux fence_ux]
   [-fence_uy fence_uy] [-fixed_file fixed_file]
   [-community_file community_file] [-group_file group_file]
   [-solution_file solution_file] [-net_timing_factor net_timing_factor]
   [-path_timing_factor path_timing_factor]
   [-path_snaking_factor path_snaking_factor]
   [-timing_exp_factor timing_exp_factor] [-extra_delay extra_delay]
   [-guardband_flag guardband_flag] [-e_wt_factors e_wt_factors]
   [-v_wt_factors v_wt_factors] [-placement_wt_factors placement_wt_factors]
   [-thr_coarsen_hyperedge_size_skip thr_coarsen_hyperedge_size_skip]
   [-thr_coarsen_vertices thr_coarsen_vertices]
   [-thr_coarsen_hyperedges thr_coarsen_hyperedges]
   [-coarsening_ratio coarsening_ratio] [-max_coarsen_iters max_coarsen_iters]
   [-adj_diff_ratio adj_diff_ratio]
   [-min_num_vertices_each_part min_num_vertices_each_part]
   [-num_initial_solutions num_initial_solutions]
   [-num_best_initial_solutions num_best_initial_solutions]
   [-refiner_iters refiner_iters] [-max_moves max_moves]
   [-early_stop_ratio early_stop_ratio]
   [-total_corking_passes total_corking_passes] [-v_cycle_flag v_cycle_flag ]
   [-max_num_vcycle max_num_vcycle]
   [-num_coarsen_solutions num_coarsen_solutions]
   [-num_vertices_threshold_ilp num_vertices_threshold_ilp]
   [-global_net_threshold global_net_threshold]   
triton_part_hypergraph -hypergraph_file hypergraph_file -num_parts num_parts
   -balance_constraint balance_constraint [-base_balance base_balance]
   [-scale_factor scale_factor] [-seed seed]
   [-vertex_dimension vertex_dimension]
   [-hyperedge_dimension hyperedge_dimension]
   [-placement_dimension placement_dimension] [-fixed_file fixed_file]
   [-community_file community_file] [-group_file group_file]
   [-placement_file placement_file] [-e_wt_factors e_wt_factors]
   [-v_wt_factors <v_wt_factors>] [-placement_wt_factors <placement_wt_factors>]
   [-thr_coarsen_hyperedge_size_skip thr_coarsen_hyperedge_size_skip]
   [-thr_coarsen_vertices thr_coarsen_vertices]
   [-thr_coarsen_hyperedges thr_coarsen_hyperedges]
   [-coarsening_ratio coarsening_ratio] [-max_coarsen_iters max_coarsen_iters]
   [-adj_diff_ratio adj_diff_ratio]
   [-min_num_vertices_each_part min_num_vertices_each_part]
   [-num_initial_solutions num_initial_solutions]
   [-num_best_initial_solutions num_best_initial_solutions]
   [-refiner_iters refiner_iters] [-max_moves max_moves]
   [-early_stop_ratio early_stop_ratio]
   [-total_corking_passes total_corking_passes] [-v_cycle_flag v_cycle_flag ]
   [-max_num_vcycle max_num_vcycle]
   [-num_coarsen_solutions num_coarsen_solutions]
   [-num_vertices_threshold_ilp num_vertices_threshold_ilp]
   [-global_net_threshold global_net_threshold]   
unset_case_analysis pins 
unset_clock_groups [-logically_exclusive] [-physically_exclusive]
   [-asynchronous] [-name names] [-all] 
unset_clock_latency [-source] [-clock clock] objects 
unset_clock_transition clocks 
unset_clock_uncertainty [-from|-rise_from|-fall_from from_clock]
   [-to|-rise_to|-fall_to to_clock] [-rise] [-fall] [-setup] [-hold] [objects] 
unset_data_check [-from from_pin] [-rise_from from_pin] [-fall_from from_pin]
   [-to to_pin] [-rise_to to_pin] [-fall_to to_pin] [-setup | -hold]
   [-clock clock] 
unset_disable_inferred_clock_gating objects  
unset_disable_timing [-from from_port] [-to to_port] objects 
unset_dont_touch nets_instances 
unset_dont_use lib_cells 
unset_input_delay [-rise] [-fall] [-max] [-min] [-clock clock] [-clock_fall]
   port_pin_list 
unset_output_delay [-rise] [-fall] [-max] [-min] [-clock clock] [-clock_fall]
   port_pin_list 
unset_path_exceptions [-setup] [-hold] [-rise] [-fall] [-from from_list]
   [-rise_from from_list] [-fall_from from_list] [-through through_list]
   [-rise_through through_list] [-fall_through through_list] [-to to_list]
   [-rise_to to_list] [-fall_to to_list] 
unset_power_activity [-global] [-input] [-input_ports ports] [-pins pins]
   [-clock clock] 
unset_propagated_clock objects 
unset_timing_derate 
unsuppress_message tool id  
unsuppress_msg msg_ids 
use_interface_cell -domain domain -strategy strategy -lib_cells lib_cells
   interface_implementation_name 

user_run_time 
with_output_to_variable var  { cmds }
write_abstract_lef [-bloat_factor amount|-bloat_occupied_layers] filename 
write_cdl [-include_fillers] -masters masters_filenames out_filename  
write_db filename 
write_def [-version version] filename 
write_gate_gnuplot -gates  {{instance input_port driver_port edge [delay]}...} -plot_pins plot_pins -plot_basename plot_basename [-corner corner] [-min] [-max]
write_gate_spice -gates  {{instance input_port driver_port edge [delay]}...} -spice_filename spice_filename -lib_subckt_file lib_subckts_file -model_file model_file -power power -ground ground [-simulator hspice|ngspice|xyce] [-corner corner] [-min] [-max]
write_global_route_segments file_name  
write_guides filename  
write_lef filename 
write_macro_placement file_name  
write_partition_verilog [-port_prefix prefix] [-module_suffix suffix]
   [-partitioning_id id] [file] 

write_path_spice -path_args path_args -spice_directory spice_directory
   -lib_subckt_file lib_subckts_file -model_file model_file -power power -ground
   ground [-simulator hspice|ngspice|xyce] 
write_pg_spice -net net_name [-vsrc vsrc_file] [-corner corner]
   [-source_type FULL|BUMPS|STRAPS] spice_file 
  
write_pin_placement file_name [-placed_status]  
write_rcx_model [-file out_file_name] 

write_rules [-file filename] [-dir dir] [-name name] [-db] 

write_sdc [-map_hpins] [-digits digits] [-gzip] [-no_timestamp] filename 
write_sdf [-corner corner] [-divider /|.] [-include_typ] [-digits digits]
   [-gzip] [-no_timestamp] [-no_version] filename 
write_spef [-net_id net_id] [-nets nets] [-coordinates] filename  
write_timing_model [-corner corner] [-library_name lib_name]
   [-cell_name cell_name] filename 
write_upf file 
write_verilog [-sort] [-include_pwr_gnd] [-remove_cells cells] filename 
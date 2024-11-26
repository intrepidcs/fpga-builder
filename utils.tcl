# Copyright (c) 2022, Intrepid Control Systems, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# Set up builtin args
# They're in the back so user can use front if needed
set num_builtin_args 7
set builtin_args_start_idx [expr $argc - $num_builtin_args]
set stats_idx [expr $builtin_args_start_idx + 0]
set threads_idx [expr $builtin_args_start_idx + 1]
set bd_only_idx [expr $builtin_args_start_idx + 2]
set synth_only_idx [expr $builtin_args_start_idx + 3]
set impl_only_idx [expr $builtin_args_start_idx + 4]
set force_idx [expr $builtin_args_start_idx + 5]
set use_vitis_idx [expr $builtin_args_start_idx + 6]

set stats_file [lindex $argv $stats_idx]
set max_threads [lindex $argv $threads_idx]
set bd_only [lindex $argv $bd_only_idx]
set synth_only [lindex $argv $synth_only_idx]
set impl_only [lindex $argv $impl_only_idx]
set force [lindex $argv $force_idx]
set use_vitis [lindex $argv $use_vitis_idx]

puts "stats_file: $stats_file"
puts "max_threads: $max_threads"

# Stats tracking variables
set synth_time 0
set total_start 0
set impl_time 0
set report_time 0
set export_time 0
set global_start 0
set bitstream_time 0
set setup_start [clock seconds]
set setup_time 0

# Build tracking variables
set worst_slack 0
set lut_util 0
set ram_util 0
set ultra_ram_util 0
set total_power 0

proc build {proj_name top_name proj_dir} {
  global synth_time
  global total_start
  global impl_time
  global report_time
  global export_time
  global total_start
  global setup_start
  global setup_time
  global bitstream_time
  global stats_file
  global max_threads
  global synth_only

  set output_dir [file normalize $proj_dir/../output]

  configure_warnings_and_errors

  # If anything happened before now, that was setup (BD generation etc)
  set setup_time [expr [clock seconds] - $setup_start]
  puts "Building!"
  set_param general.maxThreads $max_threads
  if {$total_start == 0} {
    # Some other methods of running this start the clock earlier
    # Do it here if no one else did
    set total_start [clock seconds]
    set setup_time 0
  }

  # Synth
  set start [clock seconds]
  launch_runs -jobs $max_threads -verbose synth_1
  wait_on_run synth_1
  if {[get_property PROGRESS [get_runs synth_1]] != "100%"} {
    error "ERROR: Synthesis failed"
    exit 1
  }
  set synth_time [expr [clock seconds] - $start]
  open_run synth_1
  
  if {$synth_only != 1} {
    # Impl
    set start [clock seconds]
    launch_runs -jobs $max_threads -verbose impl_1
    wait_on_run impl_1
    if {[get_property PROGRESS [get_runs impl_1]] != "100%"} {
      error "ERROR: Implementation failed"
      exit 1
    }
    set impl_time [expr [clock seconds] - $start]
    
    # Report
    set start [clock seconds]
    open_run impl_1
    set timing_rpt [file normalize "$stats_file/../timing.rpt"]
    report_timing_summary -delay_type min_max -report_unconstrained -max_paths 10 -input_pins -file $timing_rpt
    global worst_slack
    set worst_slack [get_property SLACK [get_timing_paths -delay_type min_max -nworst 1]]
    set timing_pass [expr {$worst_slack >= 0}]
    if {$timing_pass == 0} {
      puts "ERROR: Failed to meet timing! Worst path slack was $worst_slack"
      exit 1
    } else {
      puts "Timing met with $worst_slack ns of slack"
    }
  }

  # Utilization
  set util_rpt [file normalize "$stats_file/../utilization.rpt"]
  report_utilization -file $util_rpt
  set lut_line [lindex [grep "Slice LUTs" $util_rpt] 0]
  if { $lut_line == ""} {
    set lut_line [lindex [grep "CLB LUTs" $util_rpt] 0]
    set lut_column 6
  } else {
    set lut_column 5
  }
  set lut_line_split [split $lut_line "|"]
  global lut_util
  set lut_util [string trim [lindex $lut_line_split $lut_column]]
  if { $lut_util >= 80} {
    puts "CRITICAL WARNING: Part is nearly full ($lut_util %), expect timing problems if anything changed!!"
  } else {
    puts "LUT utilization is $lut_util %"
  }

  set ram_line [lindex [grep "Block RAM Tile" $util_rpt] 0]
  set ram_line_split [split $ram_line "|"]
  global ram_util
  set ram_util [string trim [lindex $ram_line_split $lut_column]]
  if { $ram_util >= 85} {
    puts "CRITICAL WARNING: Part RAM is nearly full ($ram_util %), expect issues inserting ILA!!"
  } else {
    puts "RAM utilization is $ram_util %"
  }

  set uram_line [lindex [grep "URAM" $util_rpt] 0]
  set uram_line_split [split $uram_line "|"]
  global ultra_ram_util
  set ultra_ram_util [string trim [lindex $uram_line_split $lut_column]]
  if { $ultra_ram_util >= 85} {
    puts "CRITICAL WARNING: Part UltraRAM is nearly full ($ultra_ram_util %)!!"
  } else {
    puts "UltraRAM utilization is $ultra_ram_util %"
  }

  set util_hier_rpt [file normalize "$stats_file/../utilization_hierarchical.rpt"]
  report_utilization -hierarchical -file $util_hier_rpt

  exit_if_synth_only

  # Power
  set power_rpt [file normalize "$stats_file/../power.rpt"]
  report_power -file $power_rpt
  set power_line [lindex [grep "Total On-Chip Power (W)" $power_rpt] 0]
  set power_line_split [split $power_line "|"]
  global total_power
  set total_power [string trim [lindex $power_line_split 2]]
  set report_time [expr [clock seconds] - $start]
  
  exit_if_impl_only
  
  # Bitstream
  set start [clock seconds]
  launch_runs impl_1 -to_step write_bitstream -jobs $max_threads
  wait_on_run impl_1
  set bitstream_time [expr [clock seconds] - $start]
  
  # Export
  puts "Exporting files..."
  set start [clock seconds]
  
  set bitstream ${proj_dir}/${proj_name}.runs/impl_1/${top_name}.bit
  global use_vitis
  if {[file exists $bitstream]} {
    if { $use_vitis == 1 } {
      set xsa $output_dir/${top_name}.xsa
      write_hw_platform -fixed -include_bit -force -file $xsa
    } else {
    file copy -force $bitstream $output_dir/
    set hwdef ${proj_dir}/${proj_name}.runs/impl_1/${top_name}.hwdef

    if {[file exists $hwdef]} {
      write_hwdef -force -file $hwdef
      
      set sysdef ${proj_dir}/${proj_name}.runs/impl_1/${top_name}.sysdef
      write_sysdef -force -hwdef ${hwdef} -bitfile ${bitstream} -file ${sysdef}

      set hdf $output_dir/${top_name}.hdf
      file copy -force ${sysdef} ${hdf}
    } else {
      puts "ERROR: No HDF found! Should be $hwdef"
      exit 1
    }
    }

  } else {
    puts "ERROR: No bitstream found! Should be $bitstream"
    exit 1
  }

  set proj_ltx ${proj_dir}/${proj_name}.runs/impl_1/${top_name}.ltx
  set ltx $output_dir/design_1_wrapper.ltx
  if {[file exists $proj_ltx]} {
    file copy -force ${proj_ltx} ${ltx}
  }
  set export_time [expr [clock seconds] - $start]
  
  report_stats

  close_project
}

proc report_stats {} {
  global setup_time
  global synth_time
  global total_start
  global impl_time
  global report_time
  global export_time
  global total_start
  global stats_file
  global bitstream_time
  # Build stats
  global worst_slack
  global lut_util
  global ram_util
  global ultra_ram_util
  global total_power
  set total_time [expr [clock seconds] - $total_start]
  
  set stats_chan [open $stats_file "w+"]
  puts $stats_chan "# Time stats"
  puts $stats_chan "setup_time:     $setup_time sec"
  puts $stats_chan "synth_time:     $synth_time sec"
  puts $stats_chan "impl_time:      $impl_time sec"
  puts $stats_chan "report_time:    $report_time sec"
  puts $stats_chan "bitstream_time: $bitstream_time sec"
  puts $stats_chan "export_time:    $export_time sec"
  puts $stats_chan "total_time:     $total_time sec"
  puts $stats_chan "# Build stats"
  puts $stats_chan "worst_slack:    $worst_slack ns"
  puts $stats_chan "lut_util:       ${lut_util}%"
  puts $stats_chan "ram_util:       ${ram_util}%"
  puts $stats_chan "ultra_ram_util: ${ultra_ram_util}%"
  puts $stats_chan "total_power:    $total_power W"
  close $stats_chan
}

proc build_device {proj_name top proj_dir} {
  exit_if_bd_only
  build $proj_name $top $proj_dir
}

proc build_block { filelist build_dir device generics} {
  set proj_name "proj"
  # User must call their top level wrapper entity top
  set top_name "top"
  set part $device
  set proj_dir $build_dir/$proj_name
  clean_proj_if_needed $proj_dir
  
  puts "Running vivado out of [pwd]"
  
  # Make clean
  if {[file exists $proj_dir]} {
    file delete -force $proj_dir
  }
  create_project -force $proj_name $proj_dir -part $part
  configure_warnings_and_errors
  
  # Add files
  add_files_from_filelist $filelist

  # Settings
  set_property target_language VHDL [current_project]
  set_property top $top_name [current_fileset]
  set_property "xpm_libraries" "XPM_CDC XPM_FIFO XPM_MEMORY" [current_project]
  set_property STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY none [get_runs synth_1]
  set_property STEPS.OPT_DESIGN.IS_ENABLED false [get_runs impl_1]

  # Set generics
  dict for {k v} $generics {
    puts "Setting top level param $k to $v"
    set_property generic $k=$v [current_fileset]
  }

  build $proj_name $top_name $proj_dir
}

proc clean_proj_if_needed {proj_dir} {
  global argv
  global total_start
  global setup_start
  if {[file exists $proj_dir]} {
    global force
    if {$force == 0} {
      puts "ERROR: Project dir $proj_dir already exists, provide -f/--force to force delete"
      exit 1
    }
  }
  set total_start [clock seconds]
  set setup_start [clock seconds]
  file delete -force $proj_dir
}

proc exit_if_bd_only {} {
  global bd_only
  global setup_time
  global setup_start
  if {$bd_only == 1} {
    set setup_time [expr [clock seconds] - $setup_start]
    report_stats
    exit 0
  }
}

proc exit_if_impl_only {} {
  global impl_only
  if {$impl_only == 1} {
    report_stats
    exit 0
  }
}

proc exit_if_synth_only {} {
  global synth_only
  if {$synth_only == 1} {
    report_stats
    exit 0
  }
}

proc add_files_from_filelist {filelist} {
  source $filelist
  foreach {path lib standard} $all_sources {
    add_files $path
    set file_obj [get_files -of_objects [get_filesets sources_1] [list "*$path"]]
    if {[string compare $standard "N/A"] != 0} {
      set_property -name "file_type" -value $standard -objects $file_obj
    }
    if {[string compare $lib "N/A"] != 0} {
      set_property -name "library" -value $lib -objects $file_obj
    }
  }
  puts "Added files!"
}

proc dict_get_default {dict param default} {
  if { [dict exists $dict $param] } {
    set value [dict get $dict $param]
  } else {
    # Default on
    set value $default
  }
  return $value
}

proc build_device_from_params {params} {
  # Grab things from the dict
  set proj_name [dict get $params proj_name ]
  set vivado_year [dict get $params vivado_year ]
  set part [dict get $params part ]
  set top [dict get $params top ]
  set ip_repo [dict get $params ip_repo ]
  set hdl_files [dict_get_default $params hdl_files ""]
  set constraints_files [dict_get_default $params constraints_files ""]
  set bd_file [dict get $params bd_file ]
  set synth_strategy [dict get $params synth_strategy ]
  set impl_strategy [dict get $params impl_strategy ]
  set origin_dir [dict get $params origin_dir]
  set use_power_opt [dict_get_default $params use_power_opt 1]

  # #############################################################################

  set proj_dir [pwd]/$proj_name
  clean_proj_if_needed $proj_dir

  # Create project
  create_project $proj_name $proj_dir

  configure_warnings_and_errors

  # Set the directory path for the new project
  set proj_dir [get_property directory [current_project]]

  # Set project properties
  set obj [get_projects $proj_name]
  set_property "default_lib" "xil_defaultlib" $obj
  set_property -name "ip_cache_permissions" -value "read write" -objects $obj
  set_property -name "ip_output_repo" -value "$proj_dir/$proj_name.cache/ip" -objects $obj
  set_property "part" "$part" $obj
  set_property "sim.ip.auto_export_scripts" "1" $obj
  set_property -name "ip_interface_inference_priority" -value "" -objects $obj
  set_property "simulator_language" "Mixed" $obj
  set_property "target_language" "VHDL" $obj
  set_property -name "enable_vhdl_2008" -value "1" -objects $obj
  set_property -name "xpm_libraries" -value "XPM_CDC XPM_FIFO XPM_MEMORY" -objects $obj

  # #############################################################################
  # HDL files
  # #############################################################################

  # Create 'sources_1' fileset (if not found)
  if {[string equal [get_filesets -quiet sources_1] ""]} {
    create_fileset -srcset sources_1
  }

  if { $hdl_files != ""} {
  add_files -norecurse -fileset [get_filesets sources_1] $hdl_files
  } else {
    puts "WARNING: No hdl files specified, assuming all are in IP cores"
  }

  # #############################################################################
  # IP files
  # #############################################################################
  # Set IP repository paths
  set ip_repo_paths "[file normalize "$origin_dir$ip_repo"]"
  set_property "ip_repo_paths" "$ip_repo_paths"  [current_fileset]

  # Rebuild user ip_repo's index before adding any source files
  update_ip_catalog -rebuild

  #upgrade_ip [get_ips]

  # #############################################################################
  # Constraints files
  # #############################################################################

  # Create 'constrs_1' fileset (if not found)
  if {[string equal [get_filesets -quiet constrs_1] ""]} {
    create_fileset -constrset constrs_1
  }

  if { $constraints_files != ""} {
  add_files -norecurse -fileset [get_filesets constrs_1] $constraints_files
  } else {
    puts "CRITICAL WARNING: No constraints specified, if this isn't a test project, you need constraints!"
  }

  # Create 'sim_1' fileset (if not found)
  if {[string equal [get_filesets -quiet sim_1] ""]} {
    create_fileset -simset sim_1
  }

  # #############################################################################
  # Simulation settings
  # #############################################################################

  # Set 'sim_1' fileset object
  set obj [get_filesets sim_1]
  # Empty (no sources present)

  # Set 'sim_1' fileset properties
  set obj [get_filesets sim_1]
  set_property "top" $top $obj
  set_property "xelab.nosort" "1" $obj
  set_property "xelab.unifast" "" $obj

  # #############################################################################
  # Synthesis and implementation
  # #############################################################################
  # Create 'synth_1' run (if not found)
  if {[string equal [get_runs -quiet synth_1] ""]} {
    create_run -name synth_1 -part $part -flow {Vivado Synthesis $vivado_year} -strategy $synth_strategy -constrset constrs_1
  } else {
    set_property strategy $synth_strategy [get_runs synth_1]
    set_property flow "Vivado Synthesis $vivado_year" [get_runs synth_1]
  }
  set obj [get_runs synth_1]
  set_property "needs_refresh" "1" $obj
  set_property "part" "$part" $obj

  # set the current synth run
  current_run -synthesis [get_runs synth_1]

  # Create 'impl_1' run (if not found)
  if {[string equal [get_runs -quiet impl_1] ""]} {
    create_run -name impl_1 -part $part -flow {Vivado Implementation $vivado_year} -strategy $impl_strategy -constrset constrs_1 -parent_run synth_1
  } else {
    set_property strategy $impl_strategy [get_runs impl_1]
    set_property flow "Vivado Implementation $vivado_year" [get_runs impl_1]
  }
  set obj [get_runs impl_1]
  set_property "needs_refresh" "1" $obj
  set_property "part" "$part" $obj
  set_property -name "steps.power_opt_design.is_enabled" -value "$use_power_opt" -objects $obj
  set_property -name "steps.post_place_power_opt_design.is_enabled" -value "$use_power_opt" -objects $obj
  set_property "steps.write_bitstream.args.readback_file" "0" $obj
  set_property "steps.write_bitstream.args.verbose" "0" $obj

  # set the current impl run
  current_run -implementation [get_runs impl_1]

  # #############################################################################
  # Block design files
  # #############################################################################

  # Create block design
  set ret [source $bd_file]
  if {${ret} != "" } {
    exit ${ret}
  }

  # Generate the wrapper
  set design_name [get_bd_designs]
  make_wrapper -files [get_files $design_name.bd] -top -import

  # Set the top level after make_wrapper so it exists to set as top if needed
  set_property "top" $top [get_filesets sources_1]
  update_compile_order -fileset sources_1

  save_bd_design
  validate_bd_design

  # Update the compile order
  update_compile_order -fileset sources_1
  update_compile_order -fileset sim_1

  puts "INFO: Project created:$proj_name"
  build_device $proj_name $top $proj_dir
}

proc grep { {a} {fs {*}} } {
  set o [list]
  foreach n [lsort -incr -dict [glob $fs]] {
    set f [open $n r]
    set c 0
    set new 1
    while {[eof $f] == 0} {
        set l [gets $f]
        incr c
        if {[string first $a $l] > -1} {
          lappend o "$l"
          # if {$new == 1} {set new 0; append o "*** $n:" \n}
          # append o "$c:$l" \n
        }
    }
    close $f
  }
  return $o
}

proc get_ip_repo_paths {origin_dir ip_repo part} {
  set ip_dirs [glob -type d -dir "[file normalize $origin_dir/$ip_repo]" "*"]
  set ip_repo_paths [list]
  foreach ip_dir $ip_dirs {
    # First, check if there is a part specific component
    # This requires a standard directory structure
    set is_zynq [string match "xc7z*" $part]
    set is_uplus [string match "xczu*" $part]
    if {$is_zynq == 0 && $is_uplus == 0} {
      puts "ERROR: Unknown part type for $part.  Probably need to update pattern match"
      report_stats
      exit 1
    }
    if {$is_zynq == 1} {
      set part_ip_dir "${ip_dir}/zynq"
    } else {
      set part_ip_dir "${ip_dir}/zynquplus"
    }
    set part_component "${part_ip_dir}/component.xml"
    if { [file exists $part_component] } {
      puts "Adding IP $part_ip_dir"
      lappend ip_repo_paths $part_ip_dir
    } else {
      # Didn't find a part specific IP
      # Ideally component is at root, but some old IP has it in random places
      # Just add the directory, it's in there somewhere
      puts "Adding IP $ip_dir"
      lappend ip_repo_paths $ip_dir
    }
  }
  return $ip_repo_paths
}

proc configure_warnings_and_errors {} {
  puts "INFO: Setting severities"
  # Force error if parameter name not found on IP core.  Found on IP upgrade with generic name changes
  set_msg_config -id {BD 41-1276} -new_severity {ERROR}
}

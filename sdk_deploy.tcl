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

set ws [lindex $argv 0]
set bsp_libs [lindex $argv 1]
set hdf [lindex $argv 2]

# set the workspace
puts "Setting workspace to $ws"
setws $ws

set projs [getprojects -type all]
puts "projs=$projs"
set hw_proj [getprojects -type hw]
puts "hw_proj=$hw_proj"

# Check if workspace is fresh (no projects)
if {[llength $hw_proj] == 0} {
	puts "Fresh workspace detected, importing all projects from $ws"
	importprojects $ws
} else {
	set hw_proj [getprojects -type hw]
	puts "hw_proj=$hw_proj"
	set bsp_projs [getprojects -type bsp]
	puts "bsp_projs=$bsp_projs"
	set sw_projs [getprojects -type app]
	puts "sw_projs=$sw_projs"
	
	# Remove the projects
	# this clears the workspace to fix issues with removed files
	puts "Removing projects..."
	foreach i $projs {
		catch { deleteprojects -name $i -workspace-only }
	}
	
	# import the projects
	puts "Importing projects..."
	foreach i $projs {
		importprojects $ws/$i
	}
}

# Refresh project lists after import
set projs [getprojects -type all]
set hw_proj [getprojects -type hw]
puts "hw_proj=$hw_proj"
set bsp_projs [getprojects -type bsp]
puts "bsp_projs=$bsp_projs"
set sw_projs [getprojects -type app]
puts "sw_projs=$sw_projs"

# set the repo for the custom bsp libraries
if {[file exists $bsp_libs]} {
    puts "Adding repository $bsp_libs"
    repo -set $bsp_libs
    repo -scan
}

# update hardware specification file
puts "Updating hw spec $hdf"
updatehw -hw $hw_proj -newhwspec $hdf

# regenerate BSP source files

set success 0
set num_tries 5
while { $success == 0 } {
    puts "Regenerating BSP source files"
    if { [ catch {
        foreach i $bsp_projs {
            puts "Regenerating $i"
            regenbsp -bsp $i
            puts "Updating MSS $ws/$i/system.mss"
            updatemss -mss $ws/$i/system.mss
        }
        set success 1
    } err ] } {
        # Grrrr windows resource owner problems
        # Try it a couple times
        if { $num_tries == 0} {
            puts "Tried a few times but something's goofy, dying"
            exit 1
        }
        incr num_tries -1
        puts "Something happened, let's try that again"
        puts "Tries remaining: $num_tries"
    }
}

puts "Done!"

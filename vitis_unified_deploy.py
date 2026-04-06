# Copyright (c) 2026, Intrepid Control Systems, Inc.
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

import vitis
import argparse
import sys

# Parse command line arguments
parser = argparse.ArgumentParser(
    description="Generate Vitis workspace from workspace name"
)
parser.add_argument("workspace", type=str, help="Workspace name")
parser.add_argument("xsa", type=str, help="XSA file path")
args = parser.parse_args()
print(f"Generating Vitis workspace '{args.workspace}' from XSA '{args.xsa}'")
error = False

try:
    # open Vitis client and set workspace
    client = vitis.create_client()
    client.set_workspace(path=args.workspace)

    # update hardware platform with new XSA
    # TODO support generic name for hardware platform
    platform = client.get_component("Hardware")
    status = platform.update_hw(hw_design=args.xsa)

except Exception as e:
    print(f"Exception during execution: {e}")
    error = True
    raise e
finally:
    print("Closing session")
    # close the session
    client.close()
    vitis.dispose()

if error:
    sys.exit(1)
else:
    sys.exit(0)

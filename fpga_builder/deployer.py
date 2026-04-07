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

"""
Copyright 2021 Intrepid Control Systems
Author: Nathan Francque

General script for deploying FPGA designs

"""

import shutil
import argparse
from pathlib import Path
from os import environ
from .utils import (
    query_yes_no,
    repo_clean,
    run_cmd,
    FILE_DIR,
    success,
    warning,
    err,
    print,
    XILINX_BIN_EXTENSION,
    check_output,
    check_tool,
)

SDK_DEPLOY_SCRIPT = FILE_DIR / "../sdk_deploy.tcl"
VITIS_DEPLOY_SCRIPT = FILE_DIR / "../vitis_deploy.tcl"
VITIS_UNIFIED_DEPLOY_SCRIPT = FILE_DIR / "../vitis_unified_deploy.py"


def deploy(args, device, run_dir, output_dir=None, vivado_version=None):
    """
    Deploys an existing FPGA image

    Args:
        None

    Returns:
        None

    """
    if "CI_SERVER" in environ:
        args.for_gitlab = True
    if not output_dir:
        output_dir = "hw"
    deploy_(
        run_dir,
        device,
        args.for_gitlab,
        args.commit,
        args.dry_run,
        output_dir,
        args.no_branch_confirm,
        vivado_version,
    )


def _find_hardware_file(run_dir, device, tool):
    """Find and validate the hardware file (HDF/XSA)."""
    hdf_dir = run_dir / "build" / device / "output"
    hwext = "XSA" if tool != "sdk" else "HDF"
    hdfs = list(hdf_dir.glob(f"*.{hwext.lower()}"))

    if len(hdfs) == 0:
        err(f"ERROR: No {hwext}s found in {hdf_dir}")
        exit(1)
    if len(hdfs) > 1:
        err(f"ERROR: Multiple {hwext}s found in {hdf_dir}")
        exit(1)

    hdf = hdfs[0].resolve()
    if not hdf.exists():
        err(f"ERROR: {hwext} {hdf} does not exist")
        exit(1)

    return hdf, hwext


def _validate_deploy_dir(deploy_dir):
    """Ensure deployment directory exists, creating it if necessary."""
    if not deploy_dir.exists():
        print(f"Creating deploy directory {deploy_dir}...")
        deploy_dir.mkdir(parents=True, exist_ok=True)


def _execute_deploy_tool(tool, checkout_dir, hdf_dst, version, device):
    """Execute the appropriate deployment tool based on version."""
    hdf_dst_posix = str(hdf_dst).replace("\\", "/")

    if tool == "vitis_unified":
        return vitis_unified_deploy(checkout_dir, hdf_dst_posix, version, device)
    elif tool == "vitis":
        return vitis_deploy(checkout_dir, hdf_dst_posix, version, device)
    else:
        return sdk_deploy(checkout_dir, hdf_dst, version)


def _configure_git_user(checkout_dir):
    """Configure git user for GitLab deployment."""
    run_cmd(
        'git config user.email "gitlab_deploy_user@intrepidcs.com"',
        cwd=checkout_dir,
        silent=False,
    )
    run_cmd(
        'git config user.name "Gitlab Deploy User"',
        cwd=checkout_dir,
        silent=False,
    )


def _commit_changes(checkout_dir, changed_dir, msg, for_gitlab):
    """Commit and optionally push changes."""
    run_cmd(f"git add {changed_dir} -u", cwd=checkout_dir)
    if for_gitlab:
        _configure_git_user(checkout_dir)
    run_cmd(f'git commit -m "{msg}"', cwd=checkout_dir)
    if for_gitlab:
        run_cmd("git push", cwd=checkout_dir)


def _print_commit_message(msg, dry_run):
    """Print commit message or warnings based on repo state."""
    if dry_run:
        return

    if not repo_clean():
        print(
            "****WARNING: REPO NOT CLEAN, "
            "THIS SHOULD NOT BE THE OFFICIAL MR BUILD****"
        )
        print(
            "\tPlease rebuild after committing unsave worked "
            "and an hdf commit message will be provided"
        )
    else:
        success(
            "Please copy the following for your commit message "
            "after regenerating bsp:\n"
        )
        print(f"\t{msg}")


def deploy_(
    run_dir,
    device,
    for_gitlab,
    commit,
    dry_run,
    output_dir,
    override_branch_check,
    version=None,
):
    """
    Deploys the hdf for the provided configuration

    Args:
        run_dir:      Directory where the deploy was started
        device:       The name of the device to commit to,
                      must be a valid project name
        for_gitlab:   When True, uses gitlab environment variables
                      instead of git commands. Also commits to local
                      repo without pushing
        commit:       Controls whether the deploy will also auto commit
        dry_run:      Only print, don't do anything
        override_branch_check: Overrides check before copy that branch
                               is the same as the hw repo

    Returns:
        None

    """
    version = version or "2019.1"
    tool = check_tool(version)

    # Validate deployment directory
    deploy_dir = (run_dir.parent / output_dir).resolve()
    _validate_deploy_dir(deploy_dir)
    checkout_dir = get_git_root_directory(deploy_dir)

    # Find hardware file
    hdf, hwext = _find_hardware_file(run_dir, device, tool)
    hdf_dst = (deploy_dir / hdf.name).resolve()

    # Copy and deploy
    print(f"Copying {hwext} from {hdf} to {hdf_dst}...")
    if dry_run:
        msg = f"Update hardware from {get_current_commit_url()}"
        _print_commit_message(msg, dry_run=False)
        return

    if not override_branch_check:
        verify_branch(hdf.parent, checkout_dir)

    shutil.copy(hdf, hdf_dst)
    changed_dir = _execute_deploy_tool(tool, checkout_dir, hdf_dst, version, device)

    # Handle git commit
    msg = f"Update hardware from {get_current_commit_url()}"
    if commit:
        print(f"Committing {hdf_dst}...")
        _commit_changes(checkout_dir, changed_dir, msg, for_gitlab)
    else:
        _print_commit_message(msg, dry_run)


def get_current_branch(for_gitlab=False, cwd=None):
    """
    Gets the name of the branch currently active in the git repo at cwd

    Args:
        for_gitlab: When True, uses gitlab environment variables instead of git commands

    Returns:
        The branch name

    """
    if for_gitlab:
        branch = environ.get("CI_COMMIT_BRANCH")
    else:
        branch = check_output("git branch --show-current", cwd=cwd)
        branch = branch.strip().replace("\n", "")
    return branch


def get_current_commit_hash():
    """
    Gets the hash of the commit currently active in the git repo at cwd

    Args:
        None

    Returns:
        The commit hash

    """
    hash = check_output("git log --pretty=format:'%H' -n 1")
    hash = hash.replace("'", "")
    return hash


def get_remote_url():
    """
    Gets the url of the remote currently active in the git repo at cwd

    Args:
        None

    Returns:
        The remote url in the form git@host:group/repo.git

    """
    url = check_output("git config --get remote.origin.url")
    return url


def get_git_root_directory(cwd=None):
    """
    Gets the root directory of the git repo

    Args:
        None

    Returns:
        The root directory

    """
    path = check_output("git rev-parse --show-toplevel", cwd=cwd)
    return Path(path)


def get_current_commit_url():
    """
    Gets the url of the remote for the current commit currently active in the git repo at cwd

    Args:
        None

    Returns:
        The remote url in the form host/group/repo/-/commit/hash

    """
    url = get_remote_url()
    # Reformat into url-y version
    url = url.replace(":", "/")
    url = url.replace("git@", "https://")
    url = url.replace(".git", "")
    # Remove credentials if present
    if "@" in url:
        url = url.split("//")[0] + "//" + url.split("@")[-1]
    url += "/-/commit/" + get_current_commit_hash()
    return url


def sdk_deploy(checkout_dir, hdf, version):
    ws = hdf.parent.parent
    bsp_libs = ws.parent.parent / "submodules" / "zynq_bsp_libs"
    print(ws, bsp_libs, hdf)
    tcl_args = [ws, bsp_libs, hdf]
    run_sdk(SDK_DEPLOY_SCRIPT, tcl_args, version)
    return ws


def vitis_deploy(checkout_dir, xsa, version, device):
    ws = checkout_dir / "projects" / device
    platform_tcl = ws / "platform.tcl"
    run_sdk(platform_tcl, version=version)
    return ws


def vitis_unified_deploy(checkout_dir, xsa, version, device):
    ws = Path(xsa).parent.parent.parent
    py_args = [ws, xsa]
    run_vitis_unified(VITIS_UNIFIED_DEPLOY_SCRIPT, py_args, version=version)
    return ws


def run_sdk(script, tcl_args=None, version=None):
    if version is None:
        version = "2019.1"
    xsct_cmd = get_xsct_cmd(version)
    if tcl_args:
        tcl_args = [str(arg) for arg in tcl_args]
        args_string = " ".join(tcl_args)
    else:
        args_string = ""
    cmd = f"{xsct_cmd} {script} {args_string}"
    run_cmd(cmd)


def run_vitis_unified(script, py_args=None, version=None):
    vitis_cmd = get_vitis_cmd(version)
    if py_args:
        py_args = [str(arg) for arg in py_args]
        args_string = " ".join(py_args)
    else:
        args_string = ""
    cmd = f"{vitis_cmd} -s {script} {args_string}"
    run_cmd(cmd)


def get_xsct_cmd(version):
    xsct_cmd = shutil.which("xsct")
    if xsct_cmd is not None:
        xsct_path = Path(xsct_cmd)
        if (
            xsct_path.parent.parent.name == version
            or xsct_path.parent.parent.parent.name == version
        ):
            print(f"Found Vivado {version} on PATH at {xsct_cmd}")
            # Easy enough, the one on path was what we wanted
            return xsct_cmd

    # Didn't find it, look through environment variables
    version_name = version.replace(".", "_")
    builder_xsct_env_var = f"FPGA_BUILDER_SDK_{version_name}_INSTALL_DIR"
    if builder_xsct_env_var in environ:
        xsct_install_dir = Path(environ.get(builder_xsct_env_var))
        if xsct_install_dir.exists():
            xsct_cmd = xsct_install_dir / f"bin/xsct{XILINX_BIN_EXTENSION}"
            return xsct_cmd
        else:
            err(
                f"Specified install dir from {builder_xsct_env_var} was {xsct_install_dir}, but does not exist"
            )
            exit(1)

    # Last chance, try guessing off the usual install path
    xsct_cmd = Path(f"C:/Xilinx/SDK/{version}/bin/xsct{XILINX_BIN_EXTENSION}")
    if xsct_cmd.exists():
        return xsct_cmd

    # Last chance, try guessing off the usual install path
    xsct_cmd = Path(f"C:/Xilinx/Vitis/{version}/bin/xsct{XILINX_BIN_EXTENSION}")
    if xsct_cmd.exists():
        return xsct_cmd

    # Last chance, try guessing off the usual install path
    xsct_cmd = Path(f"C:/Xilinx/{version}/Vitis/bin/xsct{XILINX_BIN_EXTENSION}")
    if xsct_cmd.exists():
        return xsct_cmd

    # Couldn't find anything, die :(
    err(
        f"ERROR: XSCT {version} not found.  Run setup script or set {builder_xsct_env_var}"
    )
    exit(1)


def get_vitis_cmd(version):
    vitis_cmd = shutil.which("vitis")
    if vitis_cmd is not None:
        vitis_path = Path(vitis_cmd)
        if (
            vitis_path.parent.parent.name == version
            or vitis_path.parent.parent.parent.name == version
        ):
            print(f"Found Vitis {version} on PATH at {vitis_cmd}")
            # Easy enough, the one on path was what we wanted
            return vitis_cmd

    # Didn't find it, look through environment variables
    version_name = version.replace(".", "_")
    builder_vitis_env_var = f"FPGA_BUILDER_VITIS_{version_name}_INSTALL_DIR"
    if builder_vitis_env_var in environ:
        vitis_install_dir = Path(environ.get(builder_vitis_env_var))
        if vitis_install_dir.exists():
            vitis_cmd = vitis_install_dir / f"bin/vitis{XILINX_BIN_EXTENSION}"
            return vitis_cmd
        else:
            err(
                f"Specified install dir from {builder_vitis_env_var} was {vitis_install_dir}, but does not exist"
            )
            exit(1)

    # Last chance, try guessing off the usual install path
    vitis_cmd = Path(f"C:/Xilinx/Vitis/{version}/bin/vitis{XILINX_BIN_EXTENSION}")
    if vitis_cmd.exists():
        return vitis_cmd

    # Last chance, try guessing off the usual install path
    vitis_cmd = Path(f"C:/Xilinx/{version}/Vitis/bin/vitis{XILINX_BIN_EXTENSION}")
    if vitis_cmd.exists():
        return vitis_cmd

    # Couldn't find anything, die :(
    err(
        f"ERROR: Vitis {version} not found.  Run setup script or set {builder_vitis_env_var}"
    )
    exit(1)


def verify_branch(this_dir, deploy_dir):
    this_branch = get_current_branch(cwd=this_dir)
    deploy_branch = get_current_branch(cwd=deploy_dir)
    if this_branch != deploy_branch:
        this_repo = get_git_root_dir(this_dir)
        deploy_repo = get_git_root_dir(deploy_dir)
        question_string = (
            f"Branch for {this_repo} is {this_branch}, "
            f"but branch for {deploy_repo} is {deploy_branch}, do you want to continue?"
        )
        keep_going = query_yes_no(question_string, print_func=warning)
        if not keep_going:
            err("Dying :(")
            exit(1)


def get_git_root_dir(dir):
    cmd = "git rev-parse --show-toplevel"
    output = check_output(cmd, cwd=dir)
    return output


def get_parser():
    """
    Gets a parser for the program

    Args:
        None

    Returns:
        An unparsed argparse instance

    """
    parser = argparse.ArgumentParser(
        "Deploy a built hdf.  If running locally, assumes deploy folder is stored at base_dir/..",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser = setup_deploy_parser(parser)
    return parser


def setup_deploy_parser(parser):
    parser.add_argument(
        "-g",
        "--for-gitlab",
        action="store_true",
        help="Uses gitlab environment variables to get branch/commit instead of local git.  Will be auto-set in CI",
        default=False,
    )
    parser.add_argument(
        "-c",
        "--commit",
        action="store_true",
        help="Controls whether the deployment also commits to the repo.  False for now until deployment is planned out",
        default=False,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Just prints out what deployment would do without executing it, useful for testing",
        default=False,
    )
    parser.add_argument(
        "--no-branch-confirm",
        action="store_true",
        help="Overrides check to wait for user input verifying this is the correct branch to deploy to",
        default=False,
    )
    return parser

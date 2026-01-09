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

General script for building FPGA designs

"""

import argparse
from pathlib import Path
import shutil
import socket
import sys
from os import environ
from .utils import (
    warning,
    err,
    info,
    critical_warning,
    repo_clean,
    run_cmd,
    FILE_DIR,
    success,
    print,
    query_yes_no,
    caller_dir,
    XILINX_BIN_EXTENSION,
    check_vitis,
)
from . import deployer

BASE_DIR = Path(environ.get("BASE_DIR", ".")).resolve()

BUILD_BLK_TCL_SCRIPT = FILE_DIR / "../build_block.tcl"

BUILD_COMMANDS = ["build", "build-deploy"]
DEPLOY_COMMANDS = ["deploy", "build-deploy"]

# DEBUG_ALLOW_GIT_DIRTY = True

# Don't care much about packages, part and speed grade most important
ZYNQ_7020_2 = "xc7z020clg400-2"
ZYNQ_7035_2 = "xc7z035fbg676-2"
ZYNQ_7030_2 = "xc7z030fbg676-2"


def build_default(
    device_names,
    tcl_scripts,
    run_dirs=None,
    tcl_arg_dict=None,
    deploy_hw_dirs=None,
    vivado_versions=None,
):
    """
    Parses arguments and runs the build on the selected device
    Provides default arguments if no overrides needed
    Arguments are all dictionaries keyed by device name

    Args:
        run_tcl:        The tcl script to run for the build
        run_dir:        Optionally specify where to run the build
        device_names:   Device name targets.  `all` is inferred
        tcl_arg_dict:   tcl args to provide to each build
        deploy_hw_dirs: Dirs to put the deployment in, defaults to hw
        vivado_versions: Versions of vivado to use, defaults to 2019.1

    """
    parser = get_parser(device_names)
    args = parser.parse_args()
    if len(args.device) == 1 and args.device[0] == "all":
        devices = device_names
    else:
        if isinstance(args.device, str):
            args.device = [args.device]

        # remove duplicates and maintain order
        devices = sorted(set(args.device), key=lambda x: args.device.index(x))
        if len(devices) != len(args.device):
            err("ERROR: Device specified multiple times")
            exit(1)

    do_build = args.command in BUILD_COMMANDS
    do_deploy = args.command in DEPLOY_COMMANDS
    if do_build and args.gui:
        if len(devices) > 1:
            err("ERROR: Can only open one device in gui")
            exit(1)
        if do_deploy:
            err("ERROR: Can't combine gui with deploy")
            exit(1)
        device = devices[0]
        if run_dirs:
            run_dir = run_dirs[device]
        else:
            run_dir = caller_dir() / "build" / device
        if vivado_versions:
            vivado_version = vivado_versions[device]
        else:
            vivado_version = "2019.1"
        projects = list(run_dir.rglob("*.xpr"))
        if not projects:
            err("ERROR: No project found.  Maybe need to generate first?")
            exit(1)
        if len(projects) > 1:
            err("ERROR: Found multiple projects for device?")
            exit(1)
        project = projects[0]
        open_vivado_gui(project, vivado_version, run_dir)
        exit()
    clean, output = repo_clean()
    if not clean:
        if do_deploy and args.commit:
            err(
                "ERROR: Cannot commit deployment from an unclean repo.  Please clean the following"
            )
            print(output)
            exit(1)
        else:
            warning("WARNING: Repo is not in clean state!\n")
            print(output)

            deploy_string = (
                " Deployment commit message will **not** be generated"
                if do_deploy
                else ""
            )
            if not query_yes_no(
                f"Would you like to continue anyways?{deploy_string}", default=None
            ):
                info("exiting...")
                exit(1)

    if do_build:
        print(f"Building devices: {devices}")
    if do_deploy:
        print(f"Deploying devices: {devices}")

    for device in devices:
        if do_build:
            print(f"Building {device}...")
            run_tcl = tcl_scripts[device]
            if run_dirs:
                run_dir = run_dirs[device]
            else:
                run_dir = caller_dir() / "build" / device
            if tcl_arg_dict:
                tcl_args = tcl_arg_dict[device]
            else:
                tcl_args = None
            if vivado_versions:
                vivado_version = vivado_versions[device]
            else:
                vivado_version = None
            build(run_tcl, args, run_dir, tcl_args, vivado_version)
        if do_deploy:
            print(f"Deploying {device}...")
            # Deploy stuff
            if deploy_hw_dirs:
                if isinstance(deploy_hw_dirs[device], list):
                    output_dirs = deploy_hw_dirs[device]
                else:
                    output_dirs = [deploy_hw_dirs[device]]
            else:
                output_dirs = [None]

            vivado_version = vivado_versions[device] if vivado_versions else None

            for output_dir in output_dirs:
                deployer.deploy(
                    args,
                    device,
                    caller_dir(),
                    output_dir,
                    vivado_version=vivado_version,
                )


def open_vivado_gui(project, vivado_version, run_dir):
    vivado_cmd = get_vivado_cmd(vivado_version)
    cmd = f"{vivado_cmd} {project}"
    run_cmd(cmd, blocking=False, cwd=run_dir)


def build(run_tcl, args, run_dir=None, tcl_args=None, vivado_version=None):
    """
    R the build on the selected device

    Args:
        run_tcl:        The tcl script to run for the build
        args:           The arguments, at least from `get_parser().parse_args()`
        run_dir:        Optionally specify where to run the build
        vivado_version: Vivado version to use, defaults to 2019.1

    """
    if not run_dir:
        run_dir = Path(run_tcl).parent
    run_vivado(
        run_tcl,
        run_dir,
        args.num_threads,
        args.bd_only,
        args.synth_only,
        args.impl_only,
        args.force,
        tcl_args,
        vivado_version,
    )
    stats = get_stats(run_dir, args.num_threads)
    print(stats)
    success("Done!")


def run_vivado(
    build_tcl,
    run_dir,
    num_threads,
    bd_only,
    synth_only,
    impl_only,
    force,
    tcl_args,
    version=None,
):
    """
    Runs vivado to run the build of the selected run directory

    Args:
        build_tcl:   The tcl file to run
        run_dir:     The directory to run the build in
        num_threads: The number of threads to build with
        bd_only:     Only generate the BD
        synth_only:  Only synthesize
        impl_only:   Only implement, don't generate bitstream
        force:       Force delete of existing project
        version:     Vivado version to use, defaults to 2019.1

    Raises:
        Exception if the build fails

    Returns:
        None

    """
    if version is None:
        version = "2019.1"
    vivado_cmd = get_vivado_cmd(version)
    script_path = Path(build_tcl).resolve()
    stats_file = get_stats_file(run_dir, num_threads)
    output_dir = stats_file.parent
    if output_dir.exists():
        if not force:
            err(f"{output_dir} already exists, provide --force to delete")
            exit(1)
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    log = output_dir / "vivado.log"
    stats_file = str(stats_file.as_posix())
    bd_only_arg = 1 if bd_only else 0
    synth_only_arg = 1 if synth_only else 0
    impl_only_arg = 1 if impl_only else 0
    force_arg = 1 if force else 0
    use_vitis_arg = check_vitis(version)
    default_args = [
        stats_file,
        num_threads,
        bd_only_arg,
        synth_only_arg,
        impl_only_arg,
        force_arg,
        use_vitis_arg,
    ]
    default_args = [str(arg) for arg in default_args]
    args = []
    if tcl_args:
        # User args go at front if provided
        args = [str(arg) for arg in tcl_args]
    # Defaults will be at the back so we can use these internally
    args.extend(default_args)
    arg_string = " ".join('"' + item + '"' for item in args)
    cmd_string = f"{vivado_cmd} -mode batch -log '{log}' -nojournal -source '{script_path}' -tclargs {arg_string}"
    if not run_dir.exists():
        run_dir.mkdir(parents=True)
    print("Running:", cmd_string)
    print(f"cwd will be {run_dir}")

    def line_handler(line):
        if line.startswith("ERROR:"):
            err(line)
        if line.startswith("CRITICAL WARNING:"):
            critical_warning(line)
        elif line.startswith("WARNING:"):
            warning(line)
        else:
            info(line)

    run_cmd(cmd_string, cwd=run_dir, line_handler=line_handler)


def get_vivado_cmd(version):
    """
    Determines the command to be used to run the requested vivado version
    Search order is PATH, FPGA_BUILDER_VIVADO_{VERSION}_INSTALL_DIR, default Xilinx Path
    {VERSION} for "2019.1" would be "2019_1"

    Args:
        version: String representing the vivado version, i.e. "2019.1"

    Returns:
        A Path to the vivado command to use

    Raises:
        If no search paths find this vivado version, exits with code

    """
    vivado_cmd = shutil.which("vivado")
    if vivado_cmd is not None:
        vivado_version = Path(vivado_cmd).parent.parent.name
        if vivado_version == version:
            # Easy enough, the one on path was what we wanted
            return vivado_cmd

    # Didn't find it, look through environment variables
    version_name = version.replace(".", "_")
    builder_vivado_env_var = f"FPGA_BUILDER_VIVADO_{version_name}_INSTALL_DIR"
    if builder_vivado_env_var in environ:
        vivado_install_dir = Path(environ.get(builder_vivado_env_var))
        if vivado_install_dir.exists():
            vivado_cmd = vivado_install_dir / f"bin/vivado{XILINX_BIN_EXTENSION}"
            return vivado_cmd
        else:
            err(
                f"Specified install dir from {builder_vivado_env_var} was {vivado_install_dir}, but does not exist"
            )
            exit(1)

    # Last chance, try guessing off the usual install path
    vivado_cmd = Path(f"C:/Xilinx/Vivado/{version}/bin/vivado{XILINX_BIN_EXTENSION}")
    if vivado_cmd.exists():
        return vivado_cmd

    # Couldn't find anything, die :(
    err(
        f"ERROR: Vivado {version} not found.  Run setup script or set {builder_vivado_env_var}"
    )
    exit(1)


def get_stats_file(run_dir, num_threads):
    """
    Gets the path to the stats file for the configuration

    Args:
        run_dir:     A directory with a run.tcl to be used as the top level build file
        num_threads: The number of threads to build with

    Returns:
        A unique path to a text file that can be populated with stats about the build

    """
    hostname = socket.gethostname()
    os = sys.platform
    filename = f"stats_{hostname}_{os}_p{num_threads}.txt"
    return (run_dir / "output" / filename).resolve()


def get_stats(run_dir, num_threads):
    """
    Simply returns the annotated contents of the stats file for the configuration

    Args:
        run_dir:     A directory with a run.tcl to be used as the top level build file
        num_threads: The number of threads to build with

    Returns:
        The name of the file, followed by the contents of it

    """
    stats_file = get_stats_file(run_dir, num_threads)
    ret = str(stats_file) + "\n"
    with open(stats_file, "r") as file:
        ret += file.read()
    return ret


def get_build_parser():
    parser = argparse.ArgumentParser(
        "Run vivado build", formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser = _add_build_args(parser)
    return parser


def get_parser(device_names):
    """
    Generates default argument parser for builder
    Individual devices can extend as necessary

    Args:
        device_names: Valid individual build targets, `all` is inferred

    Returns:
        An argparse parser

    """
    main_parser = argparse.ArgumentParser(
        "Manage FPGA build/deploy cycle",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # Initialize subparsers
    subparsers = main_parser.add_subparsers(help="sub-command help", dest="command")
    build_parser = subparsers.add_parser("build", help="Build device")
    deploy_parser = subparsers.add_parser("deploy", help="Deploy hdf")
    build_deploy_parser = subparsers.add_parser(
        "build-deploy", help="Build device and deploy hdf once complete"
    )
    # Set up the actual arguments
    build_parser = _add_build_args(build_parser)
    deploy_parser = _add_deploy_args(deploy_parser)
    build_deploy_parser = _add_build_args(build_deploy_parser)
    build_deploy_parser = _add_deploy_args(build_deploy_parser)
    # Set them all up with eligible targets
    targets = device_names.copy()
    targets.append("all")
    parsers = [build_parser, deploy_parser, build_deploy_parser]
    if len(device_names) > 1:
        nargs = "+"
        default = None
    else:
        # This makes it optional if only one device
        nargs = "*"
        default = device_names[0]
    for parser in parsers:
        parser.add_argument(
            "device",
            help="The names of the devices to build. Multiple can be specified by listing 'device1 device2'.",
            choices=targets,
            default=default,
            nargs=nargs,
        )
    return main_parser


def _add_build_args(parser):
    group = parser.add_argument_group("build", "Build Arguments")
    group.add_argument(
        "-p",
        "--num-threads",
        default=5,
        help="The number of threads to use for the test(s)",
    )
    group.add_argument(
        "--bd-only",
        default=False,
        action="store_true",
        help="Only generate the BD",
    )
    group.add_argument(
        "--synth-only",
        default=False,
        action="store_true",
        help="Only synthesize, no implementation",
    )
    group.add_argument(
        "--impl-only",
        default=False,
        action="store_true",
        help="Only implement, don't generate bitstream",
    )
    group.add_argument(
        "-f",
        "--force",
        default=False,
        action="store_true",
        help="Force delete of existing project",
    )
    group.add_argument(
        "--gui",
        default=False,
        action="store_true",
        help="Just open the vivado project in the gui",
    )
    return parser


def _add_deploy_args(parser):
    group = parser.add_argument_group("deploy", "Deploy Arguments")
    group = deployer.setup_deploy_parser(group)
    return parser


def build_block(
    blk_dir, top_level, constraints=None, other_files=None, device=None, generics=None
):
    """
    Runs a build for a block with a manifest

    Args:
        blk_dir:     The block with a manifest to build
        top_level:   The top level file to build
        constraints: Optional list of constraint files
        other_files: Any other vhdl files required to complete the build
        device:      Part number of a xilinx part to run the build against, 7020 by default
        generics:    Optional generics to top level

    Returns:
        None

    """
    from vivado_util import generate_filelist

    if device is None:
        device = ZYNQ_7020_2

    build_dir = BASE_DIR / "scratch/build" / blk_dir.name
    dsn_files = [top_level]
    if other_files:
        dsn_files.extend(other_files)
    dsn_file_tuples = [(file, "VHDL 2008") for file in dsn_files]
    other_files = {"vhdl": {"work": dsn_file_tuples}}
    if constraints:
        other_files["xdc"] = constraints
    generate_filelist(BASE_DIR, build_dir, other_files=other_files)

    if generics is None:
        num_generics = 0
        generics_pairs = "N/A"
    else:
        num_generics = len(generics)
        generics_pairs = []
        for key, value in generics.items():
            generics_pairs.append(key)
            generics_pairs.append(value)

    tcl_args = [
        build_dir / "filelist.tcl",
        build_dir,
        device,
        num_generics,
        *generics_pairs,
    ]
    parser = get_build_parser()
    args = parser.parse_args()
    # Don't generate a bitstream since this is just for checking stuff
    args.impl_only = True
    build(BUILD_BLK_TCL_SCRIPT, args, build_dir, tcl_args)

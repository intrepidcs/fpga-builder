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

Utils for fpga build and deploy mechanism

"""

import subprocess
from pathlib import Path
import sys

try:
    from colorama import Fore, Style, init as colorama_init

    HAS_COLORAMA = True
except ImportError:
    print("Colorama not present, falling back to no color")
    HAS_COLORAMA = False
import shlex
import inspect

if HAS_COLORAMA:
    colorama_init(strip=False)

FILE_DIR = Path(__file__).parent.absolute()

default_print = print

XILINX_BIN_EXTENSION = ".bat" if sys.platform == "win32" else ""


def run_cmd(cmd, cwd=None, silent=False, line_handler=None, blocking=True):
    """
    Simply runs the provided command in a subshell
    Throws an exception if return code was non zero

    Args:
        cmd:          The command to run
        cwd:          The directory to execute from, set to cwd if None
        silent:       When true, does not print out what command it's running
        line_handler: Function of a string that is each line.  If not provided, just prints output
        blocking:     When false, just runs and exits

    Returns:
        None
    """
    if not cwd:
        cwd = Path.cwd()

    def err_msg(p):
        return f"""
      command: {cmd}
      cwd:     {cwd}
      rc:      {p.returncode}
    """

    if not silent:
        print()
        print("=============================================================")
        print("Running command:")
        print(cmd)
        print(f"From directory {cwd}")

    cmd = cmd.replace("\\", "\\\\")
    split_cmd = shlex.split(cmd)
    if blocking:
        stdout = subprocess.PIPE
        stderr = subprocess.STDOUT
        close_fds = False
        shell = False
    else:
        # TODO See if there's a better way to do this
        stdout = None
        stderr = None
        close_fds = True
        shell = True
    try:
        process = subprocess.Popen(
            split_cmd,
            stdout=stdout,
            stderr=stderr,
            cwd=cwd,
            close_fds=close_fds,
            shell=shell,
        )
    except (FileNotFoundError, OSError) as e:
        err(f"Command was {cmd}")
        err(f"Split command was {split_cmd}")
        raise (e)
    if not blocking:
        return 0
    while process.poll() is None:
        output = process.stdout.readline()
        if output:
            line = output.decode("utf-8").strip()
            if line_handler:
                # Specific runners can handle fancy printing with colors and stuff
                line_handler(line)
            else:
                # Otherwise fall back to regular printing
                print(line)
    rc = process.poll()
    if rc != 0:
        raise Exception(err_msg(process))
    if not silent:
        print("=============================================================")
    return rc


def err(*args, **kwargs):
    if HAS_COLORAMA:
        print(Fore.RED + Style.BRIGHT, end="")
    print(*args, **kwargs)
    if HAS_COLORAMA:
        print(Fore.RESET + Style.RESET_ALL, end="")


def critical_warning(*args, **kwargs):
    if HAS_COLORAMA:
        print(Fore.MAGENTA + Style.BRIGHT, end="")
    print(*args, **kwargs)
    if HAS_COLORAMA:
        print(Fore.RESET + Style.RESET_ALL, end="")


def warning(*args, **kwargs):
    if HAS_COLORAMA:
        print(Fore.YELLOW, end="")
    print(*args, **kwargs)
    if HAS_COLORAMA:
        print(Fore.RESET + Style.RESET_ALL, end="")


def info(*args, **kwargs):
    # In case we want info colors later?
    if HAS_COLORAMA:
        print(Fore.RESET, end="")
    print(*args, **kwargs)
    if HAS_COLORAMA:
        print(Fore.RESET + Style.RESET_ALL, end="")


def success(*args, **kwargs):
    if HAS_COLORAMA:
        print(Fore.GREEN, end="")
    print(*args, **kwargs)
    if HAS_COLORAMA:
        print(Fore.RESET)


def print(*args, **kwargs):
    kwargs["flush"] = True
    default_print(*args, **kwargs)


def caller_dir():
    """
    Returns the directory of the file that called into the **current context**
    In another words, not what called this function, but what called the function
    that called this one
    Useful to keep using relative directories while using different files

    Returns:
        A Path to the directory that called the function calling this one

    """
    # Use the second one up since calling this will invoke another stack frame
    frame = inspect.stack()[2]
    filename = frame[0].f_code.co_filename
    dir = Path(filename).resolve().parent
    return dir


def repo_clean():
    """
    Checks if git repo is in a clean state

    Args:
        None

    Returns:
        True if the repo is in a clean state

    """
    cmd = "git status --porcelain"
    output = subprocess.run(cmd, capture_output=True, shell=True).stdout
    if output:
        output = cmd + "\n" + output.decode("utf-8")
        # This git command should be empty if everything is good to go
        if "DEBUG_ALLOW_GIT_DIRTY" in globals():
            # Provide dev option to bypass check
            # Do not expose as command line option
            print("********************************************")
            print("**** WARNING: Bypassing git clean check ****")
            print("********************************************")
            return globals()["DEBUG_ALLOW_GIT_DIRTY"], output
        else:
            return False, output
    return True, ""


# https://stackoverflow.com/questions/3041986/apt-command-line-interface-like-yes-no-input
def query_yes_no(question, default="yes", print_func=None):
    """Ask a yes/no question via raw_input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
            It must be "yes" (the default), "no" or None (meaning
            an answer is required of the user).

    The "answer" return value is True for "yes" or False for "no".
    """
    valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    if print_func is None:
        print_func = print

    while True:
        print_func(f"{question} {prompt}", end="")
        choice = input().lower()
        if default is not None and choice == "":
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            print_func("Please respond with 'yes' or 'no' " "(or 'y' or 'n').", end="")


def check_output(cmd, cwd=None):
    return subprocess.check_output(shlex.split(cmd), cwd=cwd).decode().strip()


# check version to see if Vitis or SDK is being used
def check_vitis(version):
    ver_parts = version.split(".")
    if int(ver_parts[0]) <= 2019 and int(ver_parts[1]) <= 1:
        return 0
    else:
        return 1

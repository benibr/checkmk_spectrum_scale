#!/usr/bin/env python3
import argparse
import sys
import os
import subprocess
import csv
import socket

STATE_OK = 0
STATE_WARNING = 1
STATE_CRITICAL = 2
STATE_UNKNOWN = 3


class CheckResult:
    """Simple storage class for return values of the script"""

    def __init__(self, returnCode=None, serviceName=None, returnMessage=None, metrics=None):

        if returnCode is None:
            self.returnCode = STATE_UNKNOWN
        else:
            self.returnCode = returnCode

        if serviceName is None:
            self.serviceName = "UNKNOWN"
        else:
            self.serviceName = serviceName

        if returnMessage is None:
            self.returnMessage = "UNKNOWN"
        else:
            self.returnMessage = returnMessage

        if metrics is None:
            self.metrics = None
        else:
            self.metrics = metrics

    def printMonitoringOutput(self):
        """
        Concatenate full message and print it, then exit with returnCode

        Error:
            Prints unknown state if the all variables in the instance are default.
        """
        returnText = f"{self.returnCode} \"{self.serviceName}\""
        if self.metrics is not None:
            returnText = returnText + " " + self.metrics
        else:
            returnText = returnText + " - "
        returnText = returnText + " " + self.returnMessage
        print(returnText)
        sys.exit(self.returnCode)


def getRowByFields(table, criteria):
    for row in table:
        if set(criteria.items()).issubset(row.items()):
            return row


def executeBashCommand(command):
    """
    Args:
        command    -    command to execute in bash

    Return:
        Returned string from command
    """
    print(f"running command '{command}'", file=sys.stderr)
    process = subprocess.Popen(
        command.split(), stdout=subprocess.PIPE, universal_newlines=True)
    return str(process.communicate()[0])


def checkRequirements():
    """
    Check if following tools are installed on the system:
        -IBM Spectrum Scale
    """

    if not (os.path.isdir("/usr/lpp/mmfs/bin/") and os.path.isfile("/usr/lpp/mmfs/bin/mmhealth")):
        checkResult = CheckResult()
        checkResult.returnCode = STATE_CRITICAL
        checkResult.returnMessage = "CRITICAL - No IBM Spectrum Scale Installation detected."
        checkResult.printMonitoringOutput()


def createCheck(args):
    text = f"""#!/bin/bash
/usr/lib/check_mk_agent/local/checkmk_spectrum_scale.py health --node {args.node} --component {args.component}
"""
    fname = f"/usr/lib/check_mk_agent/local/checkmk_spectrum_scale_health_node_{args.node}_{args.component}"
    with open(fname, 'w') as file:
        file.write(text)
    os.chmod(fname, 0o755)
    sys.exit(STATE_OK)


def getNodeName():
    """
    Try to get local nodes name from env var (usually not set when checkMK executes check)
    the default to asking the cluster for the nodes name
    and if that failes, use Unix gethostname
    """
    name = os.getenv('HOSTNAME')
    if not name:
        criteria = {"component": "NODE", "entitytype": "NODE"}
        output = executeBashCommand(
            f"/usr/lpp/mmfs/bin/mmhealth node show -Y")
        stateOutput = (row for row in output.split(
            "\n") if row.startswith("mmhealth:State:"))
        table = csv.DictReader(stateOutput, delimiter=":")
        row = getRowByFields(table, criteria)
        try:
            name = row["entityname"]
        except TypeError:
            pass
    if not name:
        name = socket.gethostname()
    return name


def checkNodeHealth(args):
    state = None
    checkResult = CheckResult()
    comp = args.component.title()
    checkResult.serviceName = f"Spectrum Scale {comp} Health"

    output = executeBashCommand(
        f"/usr/lpp/mmfs/bin/mmhealth node show -N {args.node} -Y")
    stateOutput = (row for row in output.split(
        "\n") if row.startswith("mmhealth:State:"))
    table = csv.DictReader(stateOutput, delimiter=":")
    criteria = {"component": args.component.upper(), "entitytype": "NODE"}
    row = getRowByFields(table, criteria)
    try:
        state = row["status"]
    except TypeError:
        checkResult.returnMessage = f"UNKNOWN: Health for Component '{comp}' on node '{args.node}' not found"
    finally:
        if ((state == "HEALTHY") or (state == "TIPS")):
            checkResult.returnCode = STATE_OK
            checkResult.returnMessage = f"OK: {comp} is in state '{str(state)}'"
        elif (state == "DEGRADED"):
            checkResult.returnCode = STATE_WARNING
            checkResult.returnMessage = f"WARNING: {comp} is in state '{str(state)}'"
        elif (state == "FAILED"):
            checkResult.returnCode = STATE_CRITICAL
            checkResult.returnMessage = f"CRITICAL: {comp} is in state '{str(state)}'"
    checkResult.printMonitoringOutput()


def argumentParser():
    """
    Parse the arguments from the command line
    """
    _hostname = getNodeName()
    parser = argparse.ArgumentParser(
        description='Check heath of the GPFS node')
    parser.add_argument('--create-check', dest='createCheck', action='store_true',
                        help='Create a local check file to the specified command for checkMK discovery')

    subParser = parser.add_subparsers()
    healthParser = subParser.add_parser(
        'health', help='Check the health on a node')
    healthParser.add_argument('-n', '--node', dest='node', action='store',
                              help='Check state of the nodes', default=_hostname)
    healthParser.add_argument('--component', dest='component', action='store',
                              help='Check state of the nodes', default='NODE')
    return parser


if __name__ == '__main__':
    if len(sys.argv) == 1:
        sys.argv.append("health")

    parser = argumentParser()
    args = parser.parse_args()

    if args.createCheck:
        createCheck(args)

    checkRequirements()
    checkNodeHealth(args)

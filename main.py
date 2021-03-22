from configparser import ConfigParser
import re
import sys
import time

"""
Authors: Quinn Burrell and Alex McCarty
Date:    21 March 2021
Purpose: Parses router.ini files and does basic error checks
"""

file = sys.argv[1]  # Holds the variable given in the command line
config = ConfigParser()  # Creates an instance of the config parser
config.read(file)  # Config parser reads the given router file

# Create an empty dictionary which will hold info about the router
router_dict = {}

# Router ID
router_num = int((config['router']['router_id']))  # Extracts router id from config file
if 1 <= router_num <= 64000:  # Checks id is a valid id
    router_dict['router-id'] = router_num  # If valid then gets added to the router dictionary
else:
    sys.exit("Please enter a router id between 1 and 64000")  # Error

# Input ports
inputs = config['router']['input_ports'].split(', ')  # Extracts input ports from config file
input_ports = []
neighbours = []

for entry in inputs:
    entry = int(entry)
    if 1024 < entry < 64000:  # Checks input port is valid
        input_ports.append(entry)  # If valid, appends to list fo input ports
        neighbours.append(int((entry - (router_num * 1000))/100))  # Finds the router id of the neighbouring router
    else:
        sys.exit("Please enter input port values between 1024 and 64000")  # Error

router_dict['input-ports'] = input_ports  # All valid input ports are added to the router dictionary

# Outputs
out = config['router']['outputs'].split(', ')  # Extracts outputs from the config file
output_ports = []

for entry in out:
    re_result = re.search("(.*)-(.)-(.)", entry).groups()  # Uses a regex to split the values of the entry
    output_port, metric, router_id = [int(i) for i in re_result]  # Changes all values to ints
    if 1024 <= output_port <= 64000:  # Checks port number is valid
        if output_port not in router_dict['input-ports']:  # Checks this port number is not also an input port
            if router_id in neighbours:  # Checks that the output port has a matching input port for that router
                output_ports.append([output_port, metric, router_id])
            else:
                sys.exit("Your input ports do not match your output ports. Please update your configuration file")  # Error
        else:
            sys.exit("Please make sure you do not have the same entry in your input and output port fields")  # Error
    else:
        sys.exit("Please make sure your port numbers are between 1024 and 64000")  # Error

router_dict['outputs'] = output_ports  # Adds all valid outputs to the router dictionary

start = time.time()
router_dict['timer-started'] = start  # Adds when the router turned on to the router dictionary

print(router_dict)
